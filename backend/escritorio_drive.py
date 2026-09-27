"""Escritório × Google Drive (piloto, 24/09/2026).

Decisões do Pedro: o Drive fica DENTRO do app; cada projeto do Escritório aponta pra UMA pasta do Drive
da admin; a equipe recebe acesso SÓ àquela pasta; permissão completa do Drive (`drive`) no piloto, sem
auditoria (tela "app não verificado" pra quem conecta). O Google Cloud é o projeto `ai-arq` (conta da
empresa), cliente OAuth "AI.arq Escritório (Drive)".

Como funciona (tudo pelo SERVIDOR — o site bloqueia scripts e iframes do Google na CSP, de propósito):
  • conectar: a tela pede a URL (`/iniciar`, com login), o navegador vai pro Google, o Google volta no
    `/callback` com um código; o servidor troca por uma chave de acesso de longa duração (refresh token)
    e guarda CIFRADA em `escritorio_drive_conexoes` (tabela só do servidor, sem RLS pra ninguém);
  • escolher a pasta: navegador de pastas nosso (`/pastas`) ou o link colado; o servidor confere que é
    uma pasta que a conta enxerga e grava `pasta_id`/`pasta_caminho` no projeto;
  • listar: o servidor lista com a chave da DONA do projeto; quem é da equipe vê a lista pelo servidor
    (subpastas só se estiverem DENTRO da pasta do projeto — senão, pelo id, alguém listaria o Drive
    inteiro da admin);
  • compartilhar: cada membro ativo ganha acesso de edição à pasta (e-mail da conta dele); quem sai
    perde. Só mexemos no que NÓS criamos (`escritorio_drive_permissoes`): o que a admin compartilhou
    à mão no Drive fica como está.
🔐 A chave de cifra sai do segredo do servidor (HKDF da service key): girar a service key obriga a
reconectar — melhor que uma chave nova no Render que alguém esquece de configurar.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

import escritorio as esc

router = APIRouter(prefix="/api/escritorio", tags=["Escritório — Drive"])

SITE = "https://ai.arq.br"
API = "https://api.ai.arq.br"
REDIRECT_URI = f"{API}/api/escritorio/drive/callback"
ESCOPO = "https://www.googleapis.com/auth/drive"
# o ID do cliente OAuth é PÚBLICO (vai na URL do Google); o segredo mora só no Render.
# 🪤 NUNCA escrever um ID "de memória": este foi LIDO no console em 24/09 (cliente "AI.arq Escritório (Drive)",
# projeto ai-arq). Um ID digitado de cabeça antes disso saiu errado — por isso a regra.
CLIENT_ID = os.environ.get("GOOGLE_DRIVE_CLIENT_ID", "558106235498-326qm7cs59908avo3mkmvjr7vusak0sf.apps.googleusercontent.com")
PASTA = "application/vnd.google-apps.folder"
_VIDA_DO_ESTADO = 600          # 10 min pra voltar do Google
_TETO_DA_LISTA = 2000         # itens numa pasta (a lista segue as páginas até aqui e avisa se cortou)
_CACHE_ACESSO: dict = {}      # user_id → (access_token, expira_em)


# ── cifra e assinatura ─────────────────────────────────────────────────────

def _segredo_base() -> bytes:
    s = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not s:
        raise HTTPException(503, "O Drive está indisponível agora (servidor sem configuração).")
    return s.encode("utf-8")


def _chave(para: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"aiarq-escritorio-drive",
                info=para).derive(_segredo_base())


def cifrar(texto: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(_chave(b"token"))).encrypt(texto.encode("utf-8")).decode("ascii")


def decifrar(cifrado: str) -> str:
    from cryptography.fernet import Fernet, InvalidToken
    try:
        return Fernet(base64.urlsafe_b64encode(_chave(b"token"))).decrypt(cifrado.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        raise HTTPException(409, "A conexão com o Drive precisa ser refeita. Conecte de novo.")


def assinar_estado(dados: dict) -> str:
    corpo = base64.urlsafe_b64encode(json.dumps(dados, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
    sig = hmac.new(_chave(b"estado"), corpo.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{corpo}.{sig}"


def ler_estado(estado: str, agora=None) -> dict:
    """O `state` que volta do Google: assinado por nós e com prazo. Qualquer coisa fora disso = recusa."""
    try:
        corpo, sig = str(estado or "").rsplit(".", 1)
    except ValueError:
        raise HTTPException(400, "Retorno do Google inválido.")
    esperado = hmac.new(_chave(b"estado"), corpo.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, esperado):
        raise HTTPException(400, "Retorno do Google inválido.")
    dados = json.loads(base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)).decode("utf-8"))
    if float(dados.get("exp", 0)) < (agora or time.time()):
        raise HTTPException(400, "O tempo pra conectar acabou. Tente de novo.")
    return dados


def id_da_pasta(entrada: str) -> str:
    """Aceita o id puro ou o link da pasta (drive.google.com/drive/folders/<id>, ...?id=<id>)."""
    t = str(entrada or "").strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]{10,})", t) or re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", t)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", t):
        return t
    raise HTTPException(400, "Não reconheci o link da pasta. Abra a pasta no Drive e copie o endereço da barra.")


# ── conversa com o Google ──────────────────────────────────────────────────

def _http(method, url, token=None, form=None, corpo=None, timeout=20):
    """(status, json|None). Trocável nos testes (`_HTTP`)."""
    dados, cab = None, {}
    if form is not None:
        dados = urllib.parse.urlencode(form).encode("utf-8")
        cab["Content-Type"] = "application/x-www-form-urlencoded"
    elif corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        cab["Content-Type"] = "application/json"
    if token:
        cab["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=dados, method=method, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8") or "{}"
            return r.status, (json.loads(txt) if txt.strip() else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, None
    except Exception:
        return 0, None


_HTTP = _http


def _segredo_do_cliente() -> str:
    s = os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET", "")
    if not s or not CLIENT_ID:
        raise HTTPException(503, "O Drive ainda não foi configurado no servidor.")
    return s


def _drive(method, caminho, token, params=None, corpo=None, timeout=None):
    url = "https://www.googleapis.com/drive/v3/" + caminho
    if params:
        url += "?" + urllib.parse.urlencode(params)
    if timeout:
        return _HTTP(method, url, token=token, corpo=corpo, timeout=timeout)
    return _HTTP(method, url, token=token, corpo=corpo)


def _q_texto(s: str) -> str:
    """Texto dentro de aspas simples na busca do Drive (parâmetro q): escapa \\ e '."""
    return str(s or "").replace("\\", "\\\\").replace("'", "\\'")


def _motivo_do_google(r) -> str:
    """O `reason` do erro do Google (storageQuotaExceeded, cannotCopyFile…), ou ''."""
    try:
        e = (r or {}).get("error") or {}
        return str(((e.get("errors") or [{}])[0]).get("reason") or e.get("status") or "")
    except Exception:
        return ""


# ── conexões guardadas ─────────────────────────────────────────────────────

def _conexao(user_id: str):
    st, linhas = esc._SERVICO("GET", "escritorio_drive_conexoes",
                              params={"user_id": f"eq.{user_id}", "select": "user_id,google_email,token_cifrado"})
    if st >= 300 or linhas is None:
        raise HTTPException(502, "O banco não respondeu agora. Tente de novo em instantes.")
    return linhas[0] if linhas else None


def _esquecer_conexao(user_id: str) -> None:
    """🩸 26/09 (auditoria DRV-2): a conexão MORTA (revogada no Google, cifra girada) ficava no banco — /drive/status
    dizia "conectado" e a tela não tinha como reconectar. Apagando, a tela cai no "Conecte o seu Google Drive"."""
    _CACHE_ACESSO.pop(user_id, None)
    st, _ = esc._SERVICO("DELETE", "escritorio_drive_conexoes", params={"user_id": f"eq.{user_id}"})
    if st >= 300 or st == 0:
        esc._registrar("escritorio:drive", f"conexão morta não foi apagada (HTTP {st})")


def _acesso(user_id: str) -> str:
    """Chave de acesso de curta duração da conta ligada (renova com o refresh token cifrado)."""
    em_cache = _CACHE_ACESSO.get(user_id)
    if em_cache and em_cache[1] > time.time() + 60:
        return em_cache[0]
    c = _conexao(user_id)
    if not c:
        raise HTTPException(409, "O Google Drive não está conectado.")
    try:
        refresh = decifrar(c["token_cifrado"])
    except HTTPException:
        _esquecer_conexao(user_id)          # cifra girada: a chave guardada não abre mais
        raise
    st, r = _HTTP("POST", "https://oauth2.googleapis.com/token", form={
        "client_id": CLIENT_ID, "client_secret": _segredo_do_cliente(),
        "refresh_token": refresh, "grant_type": "refresh_token"})
    if st != 200 or not r or not r.get("access_token"):
        if r and r.get("error") == "invalid_grant":   # a pessoa revogou no Google, ou o token venceu
            _esquecer_conexao(user_id)
            raise HTTPException(409, "O acesso ao Drive foi cortado no Google. Conecte de novo.")
        raise HTTPException(502, "O Google não respondeu agora. Tente de novo em instantes.")
    _CACHE_ACESSO[user_id] = (r["access_token"], time.time() + int(r.get("expires_in") or 3000))
    return r["access_token"]


def _dono_do_projeto(projeto_id: str) -> dict:
    p = esc._um(esc._SERVICO("GET", "escritorio_projetos",
                             params={"id": f"eq.{projeto_id}", "select": "id,dono,nome,pasta_id,pasta_caminho"}))
    if not p:
        raise HTTPException(404, "Projeto não encontrado.")
    return p


# ── rotas: conectar ────────────────────────────────────────────────────────

@router.post("/drive/iniciar")
def drive_iniciar(request: Request, corpo: dict):
    """A URL do Google pra conectar o Drive. Só quem está no piloto (é a admin que conecta)."""
    eu = esc._exige_login(request)
    if not esc._no_piloto(eu["id"]):
        raise HTTPException(403, "O Escritório está em piloto fechado.")
    _segredo_do_cliente()      # sem o segredo no servidor, nem manda pro Google
    projeto = str(corpo.get("projeto_id") or "")
    estado = assinar_estado({"u": eu["id"], "p": projeto if re.fullmatch(r"[0-9a-f-]{36}", projeto) else "",
                             "n": base64.urlsafe_b64encode(os.urandom(9)).decode("ascii"),
                             "exp": time.time() + _VIDA_DO_ESTADO})
    q = {"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": ESCOPO,
         "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": estado}
    if eu.get("email"):
        q["login_hint"] = eu["email"]
    return {"url": "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(q)}


def _volta(projeto: str, resultado: str, pendente: str = "") -> RedirectResponse:
    destino = f"{SITE}/escritorio.html?drive={urllib.parse.quote(resultado)}"
    if pendente:
        destino += f"&c={urllib.parse.quote(pendente)}"
    destino += f"#/p/{projeto}/arquivos" if projeto else "#/"
    return RedirectResponse(destino, status_code=302)


# 🔒 26/09 (auditoria DRV-9): o retorno do Google não tem login — quem é a pessoa vinha só do `state`. Alguém do
# piloto podia mandar o link do /iniciar pra OUTRA pessoa: ela autorizava com a conta Google dela e o Drive dela
# ficava ligado na conta de quem mandou. Agora a conexão nasce PENDENTE (10 min, em memória: 1 worker) e só vale
# quando a tela LOGADA como quem começou confirma — mostrando qual conta Google vai ser ligada.
_PENDENTES: dict = {}


def _guardar_pendente(user_id: str, refresh: str, email) -> str:
    agora = time.time()
    for k in [k for k, v in _PENDENTES.items() if v["exp"] < agora]:
        _PENDENTES.pop(k, None)
    chave = base64.urlsafe_b64encode(os.urandom(18)).decode("ascii").rstrip("=")
    _PENDENTES[chave] = {"u": user_id, "cifrado": cifrar(refresh), "email": email, "exp": agora + _VIDA_DO_ESTADO}
    return chave


@router.post("/drive/confirmar")
def drive_confirmar(request: Request, corpo: dict):
    """A tela logada confirma a conexão que voltou do Google. Só a MESMA conta que começou em /iniciar."""
    eu = esc._exige_login(request)
    chave = str((corpo or {}).get("c") or "")
    p = _PENDENTES.get(chave)
    if not p or p["exp"] < time.time():
        _PENDENTES.pop(chave, None)
        raise HTTPException(404, "Essa conexão expirou. Conecte o Drive de novo.")
    if p["u"] != eu["id"]:
        # não consome: quem começou ainda pode confirmar na aba dele
        raise HTTPException(403, "Essa conexão foi começada por outra conta do AI.arq.")
    if (corpo or {}).get("recusar") is True:
        _PENDENTES.pop(chave, None)
        try:
            _HTTP("POST", "https://oauth2.googleapis.com/revoke", form={"token": decifrar(p["cifrado"])})
        except HTTPException:
            pass
        return {"ok": True, "recusado": True}
    st_s, _ = esc._SERVICO("POST", "escritorio_drive_conexoes",
                           body={"user_id": eu["id"], "google_email": p["email"], "token_cifrado": p["cifrado"],
                                 "atualizado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                           params={"on_conflict": "user_id"},
                           prefer="resolution=merge-duplicates,return=minimal")
    if st_s >= 300 or st_s == 0:
        raise HTTPException(502, "Não consegui gravar a conexão agora. Tente de novo em instantes.")
    _PENDENTES.pop(chave, None)
    _CACHE_ACESSO.pop(eu["id"], None)
    return {"ok": True, "email": p["email"]}


@router.post("/drive/pendente")
def drive_pendente(request: Request, corpo: dict):
    """Qual conta Google a confirmação vai ligar (pra tela mostrar antes do clique). Só pra quem começou."""
    eu = esc._exige_login(request)
    p = _PENDENTES.get(str((corpo or {}).get("c") or ""))
    if not p or p["exp"] < time.time() or p["u"] != eu["id"]:
        raise HTTPException(404, "Essa conexão expirou. Conecte o Drive de novo.")
    return {"email": p["email"]}


@router.get("/drive/callback")
def drive_callback(state: str = "", code: str = "", error: str = ""):
    """O Google volta aqui. Não tem login (é o navegador vindo do Google): quem é a pessoa vem do
    `state` que NÓS assinamos em /iniciar."""
    try:
        dados = ler_estado(state)
    except HTTPException:
        return _volta("", "erro")      # nunca deixa a pessoa numa página crua do servidor
    projeto = dados.get("p") or ""
    if error or not code:
        return _volta(projeto, "negado")
    st, r = _HTTP("POST", "https://oauth2.googleapis.com/token", form={
        "code": code, "client_id": CLIENT_ID, "client_secret": _segredo_do_cliente(),
        "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code"})
    if st != 200 or not r:
        return _volta(projeto, "erro")
    if ESCOPO not in str(r.get("scope") or "").split():
        # a tela do Google deixa desmarcar a caixinha do Drive: conectou sem dar a permissão
        return _volta(projeto, "sem-permissao")
    if not r.get("refresh_token"):
        return _volta(projeto, "erro")
    st_a, sobre = _drive("GET", "about", r.get("access_token"), params={"fields": "user(emailAddress)"})
    email = ((sobre or {}).get("user") or {}).get("emailAddress") if st_a == 200 else None
    # 🔒 26/09 (auditoria DRV-9): nada é gravado aqui — a tela logada confirma (POST /drive/confirmar)
    return _volta(projeto, "confirmar", _guardar_pendente(dados["u"], r["refresh_token"], email))


@router.get("/drive/status")
def drive_status(request: Request):
    eu = esc._exige_login(request)
    c = _conexao(eu["id"])
    return {"conectado": bool(c), "email": (c or {}).get("google_email"),
            "configurado": bool(os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET") and CLIENT_ID)}


@router.post("/drive/desconectar")
def drive_desconectar(request: Request):
    eu = esc._exige_login(request)
    c = _conexao(eu["id"])
    if c:
        try:
            _HTTP("POST", "https://oauth2.googleapis.com/revoke", form={"token": decifrar(c["token_cifrado"])})
        except HTTPException:
            pass   # token ilegível: apagar a linha basta
        esc._SERVICO("DELETE", "escritorio_drive_conexoes", params={"user_id": f"eq.{eu['id']}"})
    _CACHE_ACESSO.pop(eu["id"], None)
    return {"ok": True}


# ── rotas: pastas e arquivos ───────────────────────────────────────────────

@router.get("/drive/pastas")
def drive_pastas(request: Request, pai: str = "root"):
    """Navegador de pastas da PRÓPRIA conta ligada (pra escolher a pasta do projeto)."""
    eu = esc._exige_login(request)
    tok = _acesso(eu["id"])
    pai = "root" if pai in ("", "root") else id_da_pasta(pai)
    # 26/09 (auditoria DRV-5): da 201ª pasta em diante a admin não conseguia escolher — segue as páginas
    pastas, pagina = [], None
    while True:
        params = {"q": f"'{pai}' in parents and mimeType='{PASTA}' and trashed=false",
                  "fields": "nextPageToken,files(id,name)", "orderBy": "name", "pageSize": "500",
                  "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
        if pagina:
            params["pageToken"] = pagina
        st, r = _drive("GET", "files", tok, params=params)
        if st != 200 or r is None:
            raise HTTPException(502, "O Google não respondeu agora. Tente de novo em instantes.")
        pastas += r.get("files", [])
        pagina = r.get("nextPageToken")
        if not pagina or len(pastas) >= _TETO_DA_LISTA:
            break
    r = {"files": pastas}
    atual = {"id": "root", "nome": "Meu Drive", "pai": None}
    if pai != "root":
        st_p, p = _drive("GET", f"files/{pai}", tok, params={"fields": "id,name,parents", "supportsAllDrives": "true"})
        if st_p == 200 and p:
            atual = {"id": p["id"], "nome": p.get("name") or "Pasta", "pai": (p.get("parents") or ["root"])[0]}
    return {"atual": atual, "pastas": [{"id": f["id"], "nome": f.get("name") or ""} for f in r.get("files", [])]}


@router.post("/projetos/{projeto_id}/pasta")
def projeto_pasta(projeto_id: str, request: Request, corpo: dict):
    """A admin liga o projeto a uma pasta do Drive dela. O servidor confere que é pasta e que a conta
    enxerga; grava; e já compartilha com a equipe ativa."""
    eu = esc._exige_login(request)
    if esc._papel(request, projeto_id) != "dono":
        raise HTTPException(403, "Só a admin do projeto escolhe a pasta.")
    pasta = id_da_pasta(corpo.get("pasta"))
    tok = _acesso(eu["id"])
    st, f = _drive("GET", f"files/{pasta}", tok, params={"fields": "id,name,mimeType,trashed", "supportsAllDrives": "true"})
    if st == 404 or (st == 200 and (not f or f.get("mimeType") != PASTA or f.get("trashed"))):
        raise HTTPException(400, "Isso não é uma pasta que a sua conta do Drive enxerga.")
    if st != 200:
        raise HTTPException(502, "O Google não respondeu agora. Tente de novo em instantes.")
    st_u, _ = esc._SERVICO("PATCH", "escritorio_projetos",
                           body={"pasta_id": f["id"], "pasta_caminho": f.get("name") or "", "armazenamento": "google_drive"},
                           params={"id": f"eq.{projeto_id}"})
    if st_u >= 300:
        raise HTTPException(502, "Não consegui gravar a pasta agora. Tente de novo em instantes.")
    return {"ok": True, "pasta": {"id": f["id"], "nome": f.get("name") or ""}, **sincronizar(projeto_id)}


def _dentro_da_pasta(tok: str, alvo: str, raiz: str, limite: int = 12, bloquear_limitado: bool = False) -> bool:
    """`alvo` é a própria pasta do projeto ou está dentro dela (sobe pelos pais, com limite).
    `bloquear_limitado` (a EQUIPE, 26/09 — auditoria DRV-6): pasta com "acesso limitado" no Drive
    (inheritedPermissionsDisabled) no caminho recusa — a lista é feita com a conta da DONA, que enxerga tudo."""
    atual, vistos = alvo, 0
    campos = "parents,inheritedPermissionsDisabled" if bloquear_limitado else "parents"
    while atual and vistos <= limite:
        if atual == raiz:
            return True
        st, f = _drive("GET", f"files/{atual}", tok, params={"fields": campos, "supportsAllDrives": "true"})
        if st != 200 or not f or not f.get("parents"):
            return False
        if bloquear_limitado and f.get("inheritedPermissionsDisabled"):
            return False
        atual, vistos = f["parents"][0], vistos + 1
    return False


def _ancestrais_ate(tok: str, alvo: str, raiz: str, limite: int = 12):
    """[alvo, pai, avô, …, raiz] subindo pelos pais até a pasta do projeto; None se não chegar nela."""
    caminho, atual = [], alvo
    while atual and len(caminho) <= limite:
        caminho.append(atual)
        if atual == raiz:
            return caminho
        st, f = _drive("GET", f"files/{atual}", tok, params={"fields": "parents", "supportsAllDrives": "true"})
        if st != 200 or not f or not f.get("parents"):
            return None
        atual = f["parents"][0]
    return None


def pasta_do_fornecedor(projeto_id: str, entrada) -> dict:
    """26/09 (perfis): a subpasta do projeto que o fornecedor vai LER no Drive. Tem que estar DENTRO da pasta do
    projeto e não pode ser ela própria (aí ele veria o projeto inteiro). Conferida com a conta da dona."""
    alvo = id_da_pasta(entrada)
    p = _dono_do_projeto(projeto_id)
    if not p.get("pasta_id"):
        raise HTTPException(409, "Ligue a pasta do Drive a este projeto antes de escolher a pasta do fornecedor.")
    if alvo == p["pasta_id"]:
        raise HTTPException(400, "Essa é a pasta do projeto inteiro. Escolha uma subpasta dela pro fornecedor.")
    if not _conexao(p["dono"]):
        raise HTTPException(409, "O Google Drive não está conectado.")
    tok = _acesso(p["dono"])
    st, f = _drive("GET", f"files/{alvo}", tok, params={"fields": "id,name,mimeType,trashed", "supportsAllDrives": "true"})
    if st == 404 or (st == 200 and (not f or f.get("mimeType") != PASTA or f.get("trashed"))):
        raise HTTPException(400, "Isso não é uma pasta do Drive do projeto.")
    if st != 200:
        raise HTTPException(502, "O Google não respondeu agora. Tente de novo em instantes.")
    if not _dentro_da_pasta(tok, alvo, p["pasta_id"]):
        raise HTTPException(400, "Essa pasta não está dentro da pasta do projeto.")
    return {"id": f["id"], "nome": str(f.get("name") or "")[:300]}


esc._PASTA_DO_FORNECEDOR = pasta_do_fornecedor


@router.get("/projetos/{projeto_id}/arquivos")
def projeto_arquivos(projeto_id: str, request: Request, pasta: str = ""):
    """A lista da pasta do projeto (ou de uma subpasta DELA), pra admin e pra equipe, com a chave da dona.
    26/09 (perfis): o fornecedor lista só a subpasta que a admin separou pra ele; o cliente não navega na pasta
    (recebe cada arquivo pelas Emissões)."""
    eu = esc._exige_login(request)
    papel = esc._papel(request, projeto_id)
    if papel == "cliente":
        raise HTTPException(403, "Os arquivos chegam pra você pelas Emissões.")
    if papel not in ("dono", "freela", "fornecedor"):
        raise HTTPException(403, "Você não faz parte deste projeto.")
    equipe = papel != "dono"
    p = _dono_do_projeto(projeto_id)
    if not p.get("pasta_id"):
        return {"sem_pasta": True}
    raiz, nome_raiz = p["pasta_id"], p.get("pasta_caminho") or ""
    if papel == "fornecedor":
        m = esc._um(esc._SERVICO("GET", "escritorio_membros", params={
            "projeto_id": f"eq.{projeto_id}", "user_id": f"eq.{eu['id']}", "status": "eq.ativo",
            "papel": "eq.fornecedor", "select": "drive_pasta_id,drive_pasta_nome"}))
        if not m or not m.get("drive_pasta_id"):
            return {"sem_pasta": True, "fornecedor": True}
        raiz, nome_raiz = m["drive_pasta_id"], m.get("drive_pasta_nome") or ""
    if not _conexao(p["dono"]):
        return {"sem_conexao": True, "pasta": {"id": raiz, "nome": nome_raiz}}
    tok = _acesso(p["dono"])
    # a admin pode ter tirado a pasta do fornecedor de dentro do projeto depois: aí o id dele não vale mais
    if raiz != p["pasta_id"] and not _dentro_da_pasta(tok, raiz, p["pasta_id"]):
        raise HTTPException(403, "A pasta que a admin separou pra você não está mais no projeto.")
    alvo = raiz if not pasta else id_da_pasta(pasta)
    if alvo != raiz and not _dentro_da_pasta(tok, alvo, raiz, bloquear_limitado=equipe):
        raise HTTPException(403, "Essa pasta não é deste projeto.")
    # 26/09 (auditoria DRV-5): pageSize 300 cortava calado (e o Google pode devolver MENOS por página) — segue as
    # páginas até o teto e diz quando cortou, em vez de a tela chamar 300 de "tudo"
    arquivos, pagina, truncado = [], None, False
    while True:
        params = {"q": f"'{alvo}' in parents and trashed=false",
                  "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,iconLink,size,lastModifyingUser(displayName),inheritedPermissionsDisabled)",
                  "orderBy": "folder,name", "pageSize": "500",
                  "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
        if pagina:
            params["pageToken"] = pagina
        st, r = _drive("GET", "files", tok, params=params)
        if st != 200 or r is None:
            raise HTTPException(502, "O Google não respondeu agora. Tente de novo em instantes.")
        arquivos += r.get("files", [])
        pagina = r.get("nextPageToken")
        if not pagina:
            break
        if len(arquivos) >= _TETO_DA_LISTA:
            truncado = True
            break
    # 26/09 (auditoria DRV-6): a lista usa a conta da DONA, que vê tudo — o que a admin marcou com "acesso limitado"
    # no Drive (a equipe não abre lá) também não aparece pra equipe aqui
    if equipe:
        arquivos = [f for f in arquivos if not f.get("inheritedPermissionsDisabled")]
    r = {"files": arquivos}
    return {"pasta": {"id": raiz, "nome": nome_raiz, "atual": alvo}, "truncado": truncado,
            "arquivos": [{"id": f["id"], "nome": f.get("name") or "", "pasta": f.get("mimeType") == PASTA,
                          "tipo": f.get("mimeType") or "", "link": f.get("webViewLink") or "",
                          "icone": f.get("iconLink") or "", "tamanho": f.get("size"),
                          "mudou_em": f.get("modifiedTime"),
                          "por": (f.get("lastModifyingUser") or {}).get("displayName") or ""}
                         for f in r.get("files", [])]}


# ── emitir: cópia com R00, R01… na pasta "Emitidos" ────────────────────────
# 23/09 (Pedro): "renomear com R00/R01 ao emitir" e "é uma CÓPIA" — o original segue sendo o arquivo de
# TRABALHO; o que foi pro cliente vira uma cópia com a revisão no nome, dentro de "Emitidos".

EMITIDOS = "Emitidos"
_GOOGLE_NATIVO = "application/vnd.google-apps."     # Docs, Planilhas… não têm extensão no nome
_ATALHO = "application/vnd.google-apps.shortcut"
_ESPERA_DA_COPIA = 90       # s: a cópia é feita no Google (não passa pelo servidor), mas arquivo grande demora
_REV_NO_FIM = re.compile(r"[ _-]+R\d{2}$", re.I)
_ID_DRIVE = re.compile(r"[A-Za-z0-9_-]{10,200}")


def nome_da_emissao(nome: str, revisao: int, nativo: bool = False) -> str:
    """'Planta baixa.dwg' + 3 → 'Planta baixa_R03.dwg'. Uma revisão que já estivesse no fim do nome sai
    ('Planta_R02.dwg' → 'Planta_R03.dwg', nunca 'Planta_R02_R03.dwg')."""
    base, ext = str(nome or "").strip(), ""
    m = None if nativo else re.match(r"^(.+?)(\.[A-Za-z0-9]{1,8})$", base)
    if m:
        base, ext = m.group(1), m.group(2)
    base = _REV_NO_FIM.sub("", base).strip() or "arquivo"
    return f"{base[:290]}_R{revisao:02d}{ext}"


def _pasta_emitidos(tok: str, raiz: str) -> str:
    """A pasta "Emitidos" direto dentro da pasta do projeto — criada na 1ª emissão."""
    return _subpasta_da_dona(tok, raiz, EMITIDOS)


def _subpasta_da_dona(tok: str, raiz: str, nome: str) -> str:
    """Uma subpasta fixa ("Emitidos", "Fotos") direto dentro da pasta do projeto — criada na 1ª vez."""
    st, r = _drive("GET", "files", tok, params={
        "q": f"'{raiz}' in parents and name='{_q_texto(nome)}' and mimeType='{PASTA}' and trashed=false",
        "fields": "files(id,ownedByMe,driveId)", "orderBy": "createdTime", "pageSize": "10",
        "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
    if st != 200 or r is None:
        raise HTTPException(502, "O Google não respondeu agora. Tente de novo em instantes.")
    # 26/09 (auditoria DRV-3): no Drive pessoal, quem cria a pasta é o DONO dela — uma "Emitidos" criada por alguém
    # da equipe continuaria dele depois que ele saísse. Só reaproveita a da dona (ou de Drive compartilhado, onde
    # tudo é do próprio drive); senão cria a dela.
    for f in r.get("files", []):
        if f.get("ownedByMe") or f.get("driveId"):
            return f["id"]
    st_c, nova = _drive("POST", "files", tok, params={"supportsAllDrives": "true", "fields": "id"},
                        corpo={"name": nome, "mimeType": PASTA, "parents": [raiz]})
    if st_c != 200 or not nova or not nova.get("id"):
        raise HTTPException(502, f"Não consegui criar a pasta {nome} no Drive. Tente de novo em instantes.")
    return nova["id"]


@router.post("/projetos/{projeto_id}/emitir")
def projeto_emitir(projeto_id: str, request: Request, corpo: dict):
    """A admin emite um arquivo da pasta do projeto. A revisão é POR ARQUIVO (R00 na 1ª vez, depois R01…),
    contada no banco; a cópia vai pra "Emitidos" e fica travada contra edição no Drive (a dona destrava lá
    se precisar). Nada muda no original."""
    eu = esc._exige_login(request)
    if esc._papel(request, projeto_id) != "dono":
        raise HTTPException(403, "Só a admin do projeto emite.")
    arquivo = str((corpo or {}).get("arquivo_id") or "").strip()
    if not _ID_DRIVE.fullmatch(arquivo):
        raise HTTPException(400, "Arquivo inválido.")
    nota = str((corpo or {}).get("nota") or "").strip()[:1000] or None
    p = _dono_do_projeto(projeto_id)
    if not p.get("pasta_id"):
        raise HTTPException(409, "Ligue a pasta do Drive a este projeto antes de emitir.")
    if not _conexao(p["dono"]):
        raise HTTPException(409, "O Google Drive não está conectado.")
    tok = _acesso(p["dono"])
    st, f = _drive("GET", f"files/{arquivo}", tok,
                   params={"fields": "id,name,mimeType,parents,trashed", "supportsAllDrives": "true"})
    if st == 404 or (st == 200 and (not f or f.get("trashed"))):
        raise HTTPException(404, "Esse arquivo não está mais no Drive.")
    if st != 200:
        raise HTTPException(502, "O Google não respondeu agora. Tente de novo em instantes.")
    if f.get("mimeType") == PASTA:
        raise HTTPException(400, "Pasta não se emite: escolha um arquivo.")
    # 26/09 (auditoria DRV-2): copiar um ATALHO copia só o atalho — a "R00" apontaria pro arquivo vivo
    if f.get("mimeType") == _ATALHO:
        raise HTTPException(400, "Isso é um atalho do Drive. Emita o arquivo original.")
    pai = (f.get("parents") or [""])[0]
    caminho = _ancestrais_ate(tok, pai, p["pasta_id"]) if pai else None
    if caminho is None:
        raise HTTPException(403, "Esse arquivo não é da pasta deste projeto.")
    emitidos = _pasta_emitidos(tok, p["pasta_id"])
    # 26/09 (auditoria LOG-C3): cópia movida pra uma SUBPASTA de Emitidos também é cópia (antes só o pai direto)
    if emitidos in caminho:
        raise HTTPException(400, "Esse já é uma cópia emitida. Emita o arquivo de trabalho.")
    st_r, ja = esc._SERVICO("GET", "escritorio_emissoes", params={
        "projeto_id": f"eq.{projeto_id}", "arquivo_id": f"eq.{arquivo}", "select": "revisao",
        "order": "revisao.desc", "limit": "1"})
    if st_r >= 300 or st_r == 0 or ja is None:
        raise HTTPException(502, "O banco não respondeu agora. Tente de novo em instantes.")
    rev = int(ja[0]["revisao"]) + 1 if ja else 0
    if rev > 99:
        raise HTTPException(409, "Este arquivo já chegou à R99.")
    original = str(f.get("name") or "arquivo")
    nome = nome_da_emissao(original, rev, str(f.get("mimeType") or "").startswith(_GOOGLE_NATIVO))
    # 🔒 a revisão é RESERVADA no banco ANTES da cópia: dois cliques juntos não viram duas R03 (a chave única
    # projeto+arquivo+revisão barra o 2º) nem deixam cópia órfã no Drive.
    st_i, linha = esc._SERVICO("POST", "escritorio_emissoes", body={
        "projeto_id": projeto_id, "arquivo_id": arquivo, "arquivo_nome": original[:300], "revisao": rev,
        "copia_nome": nome, "nota": nota, "emitido_por": eu["id"]}, prefer="return=representation")
    if st_i == 409:
        raise HTTPException(409, f"A R{rev:02d} deste arquivo acabou de ser emitida. Atualize a página.")
    if st_i >= 300 or st_i == 0 or not linha:
        raise HTTPException(502, "Não consegui registrar a emissão agora. Tente de novo em instantes.")
    emissao_id = linha[0]["id"]
    st_c, copia = _drive("POST", f"files/{arquivo}/copy", tok,
                         params={"supportsAllDrives": "true", "fields": "id,name,webViewLink"},
                         corpo={"name": nome, "parents": [emitidos]}, timeout=_ESPERA_DA_COPIA)
    if st_c == 0:
        # 🩸 26/09 (auditoria LOG-C2/DRV-3): sem resposta (tempo esgotado) NÃO é "nada foi emitido" — o Google
        # pode ter feito a cópia. Procura pelo nome em Emitidos antes de desfazer a reserva.
        st_b, achou = _drive("GET", "files", tok, params={
            "q": f"'{emitidos}' in parents and name='{_q_texto(nome)}' and trashed=false",
            "fields": "files(id,name,webViewLink)", "orderBy": "createdTime desc", "pageSize": "1",
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
        if st_b == 200 and achou and achou.get("files"):
            st_c, copia = 200, achou["files"][0]
    if st_c != 200 or not copia or not copia.get("id"):
        st_d, _ = esc._SERVICO("DELETE", "escritorio_emissoes", params={"id": f"eq.{emissao_id}"})
        if st_d >= 300 or st_d == 0:
            esc._registrar("escritorio:emitir", f"a cópia falhou e a reserva {emissao_id} ficou no banco (HTTP {st_d})")
        # 26/09 (auditoria LOG-C7): recusa DEFINITIVA do Google não é "tente de novo"
        motivo = _motivo_do_google(copia)
        if motivo in ("storageQuotaExceeded", "quotaExceeded"):
            raise HTTPException(409, "O Google Drive da admin está cheio: libere espaço lá e emita de novo. Nada foi emitido.")
        if motivo in ("cannotCopyFile", "fileNotDownloadable", "insufficientFilePermissions", "forbidden"):
            raise HTTPException(409, "O Google não deixa copiar este arquivo (o dono dele bloqueou cópia, ou a conta "
                                     "conectada não pode copiar). Nada foi emitido.")
        raise HTTPException(502, "O Google não fez a cópia agora. Nada foi emitido; tente de novo.")
    st_u, _ = esc._SERVICO("PATCH", "escritorio_emissoes", params={"id": f"eq.{emissao_id}"},
                           body={"copia_id": copia["id"], "copia_nome": str(copia.get("name") or nome)[:320]})
    if st_u >= 300 or st_u == 0:
        esc._registrar("escritorio:emitir", f"emissão {emissao_id} ficou sem o id da cópia (HTTP {st_u})")
    # 🔒 26/09 (auditoria SEG-1): trava que SÓ a dona destrava (ownerRestricted). Sem isso qualquer pessoa da
    # equipe (editora da pasta) tirava a trava e mudava o que foi ao cliente. Confere na resposta se pegou.
    st_t, trava = _drive("PATCH", f"files/{copia['id']}", tok,
                         params={"supportsAllDrives": "true", "fields": "contentRestrictions"},
                         corpo={"contentRestrictions": [{"readOnly": True, "ownerRestricted": True,
                                                         "reason": f"Emitido como R{rev:02d} pelo AI.arq"}]})
    travada = st_t == 200 and any(c.get("readOnly") and c.get("ownerRestricted")
                                  for c in ((trava or {}).get("contentRestrictions") or []))
    if not travada:
        esc._registrar("escritorio:emitir", f"emissão {emissao_id}: a trava da cópia não pegou (HTTP {st_t})")
    envio = {"mandados": 0, "falhas": []}
    if (corpo or {}).get("para"):
        # a emissão já existe: falha ao mandar NÃO desfaz a emissão (a tela manda de novo pelo /mandar)
        try:
            envio = _mandar(projeto_id, {"id": emissao_id, "copia_id": copia["id"]}, corpo.get("para"), eu["id"], tok)
        except HTTPException as x:
            envio = {"mandados": 0, "falhas": ["banco"], "erro": x.detail}
    return {"ok": True, "emissao_id": emissao_id, "revisao": rev, "nome": str(copia.get("name") or nome),
            "link": copia.get("webViewLink") or "", "travada": travada, **envio}


# ── mandar a emissão pro cliente / fornecedor (perfis, 26/09) ──────────────

def _hoje_no_brasil() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - 3 * 3600))


def _mandar(projeto_id: str, emissao: dict, para, quem: str, tok: str) -> dict:
    """Dá acesso de LEITURA à cópia emitida — só ao ARQUIVO, nunca à pasta Emitidos (lá estão as emissões dos
    outros) — a cada cliente/fornecedor ATIVO escolhido, e grava em escritorio_emissao_destinos. O Google avisa a
    pessoa por e-mail (sem o aviso ele recusa compartilhar com e-mail que não é conta Google). Pro cliente, registra
    'enviado' (a tela mostra "Enviada ao cliente"). Quem já tem, fica como está."""
    ids = []
    for x in (para if isinstance(para, list) else []):
        x = str(x or "").strip().lower()
        if esc._UUID.match(x) and x not in ids:
            ids.append(x)
    ids = ids[:20]
    if not ids:
        return {"mandados": 0, "falhas": []}
    if not emissao.get("copia_id"):
        raise HTTPException(409, "Essa emissão não tem a cópia registrada. Emita de novo.")
    st, membros = esc._SERVICO("GET", "escritorio_membros", params={
        "projeto_id": f"eq.{projeto_id}", "id": "in.(" + ",".join(ids) + ")", "status": "eq.ativo",
        "papel": "in.(cliente,fornecedor)", "select": "id,papel,email_conta"})
    st_d, ja = esc._SERVICO("GET", "escritorio_emissao_destinos", params={
        "emissao_id": f"eq.{emissao['id']}", "select": "membro_id,permission_id"})
    if st >= 300 or st == 0 or membros is None or st_d >= 300 or st_d == 0 or ja is None:
        raise HTTPException(502, "O banco não respondeu agora. Tente de novo em instantes.")
    validos = {str(m["id"]): m for m in membros}
    linha_de = {str(d["membro_id"]): d for d in ja}
    falhas = [i for i in ids if i not in validos]      # não é cliente nem fornecedor ativo DESTE projeto
    mandados, pro_cliente = 0, False
    for mid in ids:
        m = validos.get(mid)
        if not m:
            continue
        if (linha_de.get(mid) or {}).get("permission_id"):
            continue                                  # já mandada pra essa pessoa
        email = str(m.get("email_conta") or "").strip().lower()
        if not email:
            falhas.append(mid)
            continue
        st_p, perm = _drive("POST", f"files/{emissao['copia_id']}/permissions", tok,
                            params={"sendNotificationEmail": "true", "supportsAllDrives": "true"},
                            corpo={"role": "reader", "type": "user", "emailAddress": email})
        if st_p != 200 or not perm or not perm.get("id"):
            falhas.append(mid)
            continue
        linha = {"permission_id": perm["id"], "enviado_por": quem,
                 "enviado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if mid in linha_de:     # mandada antes e retirada (a pessoa saiu e voltou): reaproveita a linha
            st_g, _ = esc._SERVICO("PATCH", "escritorio_emissao_destinos", body=linha, params={
                "emissao_id": f"eq.{emissao['id']}", "membro_id": f"eq.{mid}"})
        else:
            st_g, _ = esc._SERVICO("POST", "escritorio_emissao_destinos", body={
                "emissao_id": emissao["id"], "projeto_id": projeto_id, "membro_id": mid, **linha})
        if st_g >= 300 or st_g == 0:
            # sem o registro, ninguém tiraria esse acesso depois: desfaz no Drive
            _drive("DELETE", f"files/{emissao['copia_id']}/permissions/{perm['id']}", tok,
                   params={"supportsAllDrives": "true"})
            falhas.append(mid)
            continue
        mandados += 1
        pro_cliente = pro_cliente or m.get("papel") == "cliente"
    if pro_cliente:
        st_e, ev = esc._SERVICO("GET", "escritorio_emissao_eventos", params={
            "emissao_id": f"eq.{emissao['id']}", "tipo": "eq.enviado", "select": "id"})
        if st_e < 300 and st_e != 0 and ev == []:
            esc._SERVICO("POST", "escritorio_emissao_eventos", body={
                "emissao_id": emissao["id"], "projeto_id": projeto_id, "tipo": "enviado",
                "em": _hoje_no_brasil(), "registrado_por": quem})
    return {"mandados": mandados, "falhas": falhas}


@router.post("/projetos/{projeto_id}/emissoes/{emissao_id}/mandar")
def projeto_mandar_emissao(projeto_id: str, emissao_id: str, request: Request, corpo: dict):
    """Manda uma emissão JÁ FEITA pra cliente/fornecedor (ou pra mais alguém depois). Só a admin."""
    eu = esc._exige_login(request)
    if esc._papel(request, projeto_id) != "dono":
        raise HTTPException(403, "Só a admin do projeto manda emissões.")
    if not esc._UUID.match(str(emissao_id or "")):
        raise HTTPException(404, "Emissão não encontrada.")
    e = esc._um(esc._SERVICO("GET", "escritorio_emissoes", params={
        "id": f"eq.{emissao_id}", "projeto_id": f"eq.{projeto_id}", "select": "id,copia_id"}))
    if not e:
        raise HTTPException(404, "Emissão não encontrada.")
    p = _dono_do_projeto(projeto_id)
    if not _conexao(p["dono"]):
        raise HTTPException(409, "O Google Drive não está conectado.")
    return {"ok": True, **_mandar(projeto_id, e, (corpo or {}).get("para"), eu["id"], _acesso(p["dono"]))}


# ── compartilhamento com a equipe ──────────────────────────────────────────

_PAPEIS_DE_EDICAO = {"writer", "fileOrganizer", "organizer", "owner"}


def _permissoes_da_pasta(tok: str, pasta_id: str):
    """{e-mail: {"id", "role"}} de quem JÁ tem acesso de usuário à pasta, por qualquer caminho. None = não li."""
    out, pagina = {}, None
    for _ in range(10):
        params = {"fields": "nextPageToken,permissions(id,emailAddress,role,type,deleted)",
                  "supportsAllDrives": "true", "pageSize": "100"}
        if pagina:
            params["pageToken"] = pagina
        st, r = _drive("GET", f"files/{pasta_id}/permissions", tok, params=params)
        if st != 200 or r is None:
            return None
        for x in r.get("permissions", []):
            if x.get("type") == "user" and x.get("emailAddress") and not x.get("deleted"):
                out[str(x["emailAddress"]).strip().lower()] = {"id": x.get("id"), "role": x.get("role")}
        pagina = r.get("nextPageToken")
        if not pagina:
            return out
    return None     # pasta com mais de 1.000 permissões: melhor não decidir pela metade


def sincronizar(projeto_id: str) -> dict:
    """Equipe ativa = quem tem acesso de edição à pasta. Cria o que falta, tira de quem saiu (e da pasta
    antiga, se a admin trocou). Nunca derruba quem chamou: falha vira item em `falhas`.

    26/09 (auditoria do Escritório, 5 lentes):
      • o e-mail que ganha acesso é o da CONTA, confirmado, gravado pelo servidor no aceite
        (`escritorio_membros.email_conta`) — não o `profiles.email`, que a própria pessoa edita pela API;
      • sem conexão/pasta devolve `sem_conexao`/`sem_pasta` (a tela avisa; antes voltava tudo zero, calado);
      • 404 no DELETE só vale como "já saiu" se a conta enxerga a pasta (senão é "não consigo ver", e o
        registro fica pra tentar de novo);
      • quem JÁ tinha acesso de edição dado pela admin à mão (`ja_existia`) não é tocado: nem ao entrar, nem
        ao sair;
      • quem segue ativo noutro projeto com a MESMA pasta não perde o acesso quando sai deste.
    26/09 (perfis): o FORNECEDOR ganha LEITURA só na subpasta que a admin separou pra ele; o CLIENTE não ganha
    pasta (recebe arquivo por arquivo nas Emissões). Quem saiu perde também os arquivos emitidos que recebeu."""
    p = _dono_do_projeto(projeto_id)
    base = {"compartilhados": 0, "tirados": 0, "falhas": []}
    if not p.get("pasta_id"):
        return {**base, "sem_pasta": True}
    if not _conexao(p["dono"]):
        return {**base, "sem_conexao": True}
    tok = _acesso(p["dono"])
    st_m, membros = esc._SERVICO("GET", "escritorio_membros", params={
        "projeto_id": f"eq.{projeto_id}", "status": "eq.ativo", "papel": "in.(freela,fornecedor,cliente)",
        "select": "id,papel,email_conta,drive_pasta_id"})
    st_r, feitos = esc._SERVICO("GET", "escritorio_drive_permissoes", params={
        "projeto_id": f"eq.{projeto_id}", "select": "id,membro_id,pasta_id,permission_id,email,ja_existia"})
    if st_m >= 300 or st_r >= 300 or membros is None or feitos is None:
        return {**base, "falhas": ["banco"]}
    # quem deve ter o quê: a equipe EDITA a pasta do projeto; o fornecedor LÊ a subpasta dele (se a admin escolheu)
    quer = {}
    for m in membros:
        if m.get("papel") == "freela":
            quer[m["id"]] = (p["pasta_id"], "writer")
        elif m.get("papel") == "fornecedor" and m.get("drive_pasta_id"):
            quer[m["id"]] = (m["drive_pasta_id"], "reader")
    ativos = {m["id"]: str(m.get("email_conta") or "").strip().lower() for m in membros if m["id"] in quer}
    feito_por_membro = {f.get("membro_id"): f for f in feitos
                        if f.get("membro_id") in quer and f.get("pasta_id") == quer[f["membro_id"]][0]}
    compartilhados, tirados, falhas = 0, 0, []
    enxerga = {}

    def _enxerga(pasta):
        if pasta not in enxerga:
            st_v, _ = _drive("GET", f"files/{pasta}", tok, params={"fields": "id", "supportsAllDrives": "true"})
            enxerga[pasta] = st_v == 200
        return enxerga[pasta]

    # tira: quem saiu, o que ficou na pasta antiga (do projeto ou do fornecedor)
    for f in feitos:
        if f.get("membro_id") in quer and f.get("pasta_id") == quer[f["membro_id"]][0]:
            continue
        apagar_registro = bool(f.get("ja_existia"))          # a admin deu à mão: fica como estava no Drive
        if not apagar_registro:
            st_o, outros = esc._SERVICO("GET", "escritorio_drive_permissoes", params={
                "pasta_id": f"eq.{f['pasta_id']}", "email": f"eq.{f.get('email') or ''}",
                "projeto_id": f"neq.{projeto_id}", "select": "id"})
            if st_o >= 300 or outros is None:
                falhas.append(f.get("email") or "?")
                continue
            apagar_registro = bool(outros)                    # outro projeto com a mesma pasta ainda usa
        if apagar_registro:
            esc._SERVICO("DELETE", "escritorio_drive_permissoes", params={"id": f"eq.{f['id']}"})
            continue
        st_d, _ = _drive("DELETE", f"files/{f['pasta_id']}/permissions/{f['permission_id']}", tok,
                         params={"supportsAllDrives": "true"})
        if st_d in (200, 204) or (st_d == 404 and _enxerga(f["pasta_id"])):
            esc._SERVICO("DELETE", "escritorio_drive_permissoes", params={"id": f"eq.{f['id']}"})
            tirados += 1
        else:
            falhas.append(f.get("email") or "?")
    # dá: quem está ativo e ainda não tem
    ja_tem = {}          # pasta → {e-mail: permissão} de quem já tem acesso (lido uma vez por pasta)
    for membro_id, email in ativos.items():
        if membro_id in feito_por_membro:
            continue
        pasta, papel_drive = quer[membro_id]
        if not email:
            falhas.append("(sem e-mail confirmado)")
            continue
        if pasta not in ja_tem:
            ja_tem[pasta] = _permissoes_da_pasta(tok, pasta)
        if ja_tem[pasta] is None:
            falhas.append(email)
            continue
        antes = ja_tem[pasta].get(email)
        # já tem o bastante (dado à mão pela admin): registra como ja_existia e não mexe
        basta = _PAPEIS_DE_EDICAO if papel_drive == "writer" else _PAPEIS_DE_EDICAO | {"reader", "commenter"}
        if antes and antes.get("role") in basta:
            esc._SERVICO("POST", "escritorio_drive_permissoes", body={
                "projeto_id": projeto_id, "membro_id": membro_id, "email": email, "pasta_id": pasta,
                "permission_id": antes.get("id") or "", "ja_existia": True})
            continue
        st_c, perm = _drive("POST", f"files/{pasta}/permissions", tok,
                            params={"sendNotificationEmail": "true", "supportsAllDrives": "true"},
                            corpo={"role": papel_drive, "type": "user", "emailAddress": email})
        if st_c == 200 and perm and perm.get("id"):
            esc._SERVICO("POST", "escritorio_drive_permissoes", body={
                "projeto_id": projeto_id, "membro_id": membro_id, "email": email,
                "pasta_id": pasta, "permission_id": perm["id"]})
            compartilhados += 1
        else:
            falhas.append(email)
    ativos_de_fora = {m["id"] for m in membros if m.get("papel") in ("cliente", "fornecedor")}
    emi_tirados, emi_falhas = _tirar_emissoes_de_quem_saiu(projeto_id, tok, ativos_de_fora)
    return {"compartilhados": compartilhados, "tirados": tirados + emi_tirados, "falhas": falhas + emi_falhas}


def _tirar_emissoes_de_quem_saiu(projeto_id: str, tok: str, ativos_de_fora: set):
    """Quem saiu do projeto (ou não é mais cliente/fornecedor ativo) perde o acesso aos ARQUIVOS emitidos que
    recebeu. A linha do destino fica (é o histórico de pra quem foi); só o `permission_id` some."""
    st, dest = esc._SERVICO("GET", "escritorio_emissao_destinos", params={
        "projeto_id": f"eq.{projeto_id}", "permission_id": "not.is.null",
        "select": "emissao_id,membro_id,permission_id"})
    if st >= 300 or st == 0 or dest is None:
        return 0, ["banco (emissões)"]
    sair = [d for d in dest if d.get("membro_id") not in ativos_de_fora]
    if not sair:
        return 0, []
    ids = sorted({str(d["emissao_id"]) for d in sair})
    st_e, emis = esc._SERVICO("GET", "escritorio_emissoes", params={
        "id": "in.(" + ",".join(ids) + ")", "select": "id,copia_id"})
    if st_e >= 300 or st_e == 0 or emis is None:
        return 0, ["banco (emissões)"]
    copia_de = {str(e["id"]): e.get("copia_id") for e in emis}
    tirados, falhas = 0, []
    for d in sair:
        copia = copia_de.get(str(d["emissao_id"]))
        st_d = 404
        if copia:
            st_d, _ = _drive("DELETE", f"files/{copia}/permissions/{d['permission_id']}", tok,
                             params={"supportsAllDrives": "true"})
        # 404: o arquivo (ou o acesso) já não existe — nada a tirar. A cópia é da dona: ela sempre enxerga.
        if st_d in (200, 204, 404):
            st_u, _ = esc._SERVICO("PATCH", "escritorio_emissao_destinos", body={"permission_id": None}, params={
                "emissao_id": f"eq.{d['emissao_id']}", "membro_id": f"eq.{d['membro_id']}"})
            if st_u >= 300 or st_u == 0:
                falhas.append("banco (emissões)")
                continue
            tirados += 1 if st_d != 404 else 0
        else:
            falhas.append("emissão")
    return tirados, falhas


def limpar_conta(user_id: str) -> dict:
    """🔒 26/09 (auditoria LGPD-1/DRV-8): pedido de exclusão de conta (hoje manual, por e-mail). ANTES de apagar o usuário
    — a cascata do banco apaga o REGISTRO do que o AI.arq compartilhou, mas não o compartilhamento no Google —
    desfaz o que o Escritório fez no Drive:
      • onde a pessoa é EQUIPE: sai do projeto (removido) e a pasta é sincronizada (ela perde o acesso);
      • onde ela é DONA: saem os acessos que NÓS demos à equipe (menos os que ela já tinha dado à mão) e a autorização
        do Google é revogada.
    Devolve o que fez e quanto ficou pendente (o pendente fica registrado)."""
    feito = {"saiu_de": 0, "tirados": 0, "pendentes": 0, "projetos_da_dona": 0, "google_revogado": False}
    st, linhas = esc._SERVICO("GET", "escritorio_membros", params={
        "user_id": f"eq.{user_id}", "select": "id,projeto_id,papel,status"})
    if st >= 300 or st == 0 or linhas is None:
        raise HTTPException(502, "O banco não respondeu agora. Tente de novo em instantes.")
    agora = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for m in linhas:
        # 26/09 (perfis): equipe, fornecedor ou cliente — todo mundo que não é a dona sai e perde o que recebeu
        if m.get("papel") == "dono" or m.get("status") != "ativo":
            continue
        st_p, _ = esc._SERVICO("PATCH", "escritorio_membros", body={"status": "removido", "removido_em": agora},
                               params={"id": f"eq.{m['id']}", "status": "eq.ativo"})
        if st_p >= 300 or st_p == 0:
            feito["pendentes"] += 1
            continue
        feito["saiu_de"] += 1
        try:
            r = sincronizar(m["projeto_id"])
            feito["tirados"] += r.get("tirados", 0)
            if r.get("falhas") or r.get("sem_conexao"):
                feito["pendentes"] += 1
        except Exception:
            feito["pendentes"] += 1
    st_d, projs = esc._SERVICO("GET", "escritorio_projetos", params={"dono": f"eq.{user_id}", "select": "id"})
    if st_d >= 300 or st_d == 0 or projs is None:
        raise HTTPException(502, "O banco não respondeu agora. Tente de novo em instantes.")
    conexao = _conexao(user_id)
    tok = None
    if conexao:
        try:
            tok = _acesso(user_id)
        except HTTPException:
            tok = None
    for p in projs:
        feito["projetos_da_dona"] += 1
        st_r, feitos = esc._SERVICO("GET", "escritorio_drive_permissoes", params={
            "projeto_id": f"eq.{p['id']}", "select": "id,pasta_id,permission_id,ja_existia"})
        if st_r >= 300 or feitos is None:
            feito["pendentes"] += 1
            continue
        for f in feitos:
            if not f.get("ja_existia"):
                if not tok:
                    feito["pendentes"] += 1
                    continue
                st_x, _ = _drive("DELETE", f"files/{f['pasta_id']}/permissions/{f['permission_id']}", tok,
                                 params={"supportsAllDrives": "true"})
                if st_x not in (200, 204, 404):
                    feito["pendentes"] += 1
                    continue
                feito["tirados"] += 1
            esc._SERVICO("DELETE", "escritorio_drive_permissoes", params={"id": f"eq.{f['id']}"})
        # e os arquivos emitidos que ela mandou pra clientes/fornecedores (a conta dela vai sumir; o acesso não pode ficar)
        if tok:
            n, falhas = _tirar_emissoes_de_quem_saiu(p["id"], tok, set())
            feito["tirados"] += n
            feito["pendentes"] += len(falhas)
        else:
            st_q, resta = esc._SERVICO("GET", "escritorio_emissao_destinos", params={
                "projeto_id": f"eq.{p['id']}", "permission_id": "not.is.null", "select": "membro_id"})
            if st_q >= 300 or st_q == 0 or resta is None or resta:
                feito["pendentes"] += len(resta or [None])
    if conexao:
        try:
            _HTTP("POST", "https://oauth2.googleapis.com/revoke", form={"token": decifrar(conexao["token_cifrado"])})
            feito["google_revogado"] = True
        except HTTPException:
            pass
        esc._SERVICO("DELETE", "escritorio_drive_conexoes", params={"user_id": f"eq.{user_id}"})
        _CACHE_ACESSO.pop(user_id, None)
    if feito["pendentes"]:
        esc._registrar("escritorio:limpar-conta", f"conta {user_id}: {feito['pendentes']} acesso(s) no Drive não tirado(s)")
    return feito


def _email_da_administracao() -> str:
    import main as _main          # o mesmo ADMIN_EMAIL de todas as rotas de admin (lido só na hora)
    return _main.ADMIN_EMAIL


@router.post("/admin/limpar-conta")
def admin_limpar_conta(request: Request, corpo: dict):
    """Só a administração do AI.arq (a página de cada usuário no admin chama antes de excluir a conta)."""
    eu = esc._exige_login(request)
    if str(eu.get("email") or "").strip().lower() != _email_da_administracao():
        raise HTTPException(403, "Só a administração do AI.arq.")
    uid = str((corpo or {}).get("user_id") or "")
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", uid):
        raise HTTPException(400, "user_id inválido.")
    return {"ok": True, **limpar_conta(uid)}


def faxina(limite: int = 20) -> dict:
    """Tick horário: permissão que NÓS demos a quem já não está ativo no projeto → sincroniza de novo aquele
    projeto (a retirada na hora falhou, ou a conexão estava caída). Nunca levanta; pendência fica registrada."""
    st, feitos = esc._SERVICO("GET", "escritorio_drive_permissoes", params={"select": "projeto_id,membro_id"})
    if st >= 300 or feitos is None:
        esc._registrar("escritorio:drive-faxina", f"não li as permissões (HTTP {st})")
        return {"erro": st}
    # 26/09 (perfis): o arquivo emitido que ainda está com quem saiu também conta
    st_e, emitidos = esc._SERVICO("GET", "escritorio_emissao_destinos", params={
        "permission_id": "not.is.null", "select": "projeto_id,membro_id"})
    if st_e >= 300 or emitidos is None:
        esc._registrar("escritorio:drive-faxina", f"não li os destinos das emissões (HTTP {st_e})")
        return {"erro": st_e}
    feitos = list(feitos) + list(emitidos)
    ids = sorted({str(f["membro_id"]) for f in feitos if f.get("membro_id")})
    ativos = set()
    if ids:
        st_m, membros = esc._SERVICO("GET", "escritorio_membros", params={
            "id": "in.(" + ",".join(ids) + ")", "select": "id,status"})
        if st_m >= 300 or membros is None:
            esc._registrar("escritorio:drive-faxina", f"não li os membros (HTTP {st_m})")
            return {"erro": st_m}
        ativos = {str(m["id"]) for m in membros if m.get("status") == "ativo"}
    projetos = sorted({f["projeto_id"] for f in feitos if str(f.get("membro_id") or "") not in ativos})
    feito = {"projetos": len(projetos), "tirados": 0, "pendentes": 0}
    for pid in projetos[:limite]:
        try:
            r = sincronizar(pid)
        except Exception as e:
            feito["pendentes"] += 1
            esc._registrar("escritorio:drive-faxina", f"projeto {pid}: {type(e).__name__}: {str(e)[:160]}")
            continue
        feito["tirados"] += r.get("tirados", 0)
        if r.get("falhas") or r.get("sem_conexao"):
            feito["pendentes"] += 1
            esc._registrar("escritorio:drive-faxina",
                           f"projeto {pid}: acesso ao Drive não tirado ({'sem conexão' if r.get('sem_conexao') else str(len(r['falhas'])) + ' falha(s)'})")
    return feito


@router.post("/projetos/{projeto_id}/drive/sincronizar")
def projeto_sincronizar(projeto_id: str, request: Request):
    esc._exige_login(request)
    if esc._papel(request, projeto_id) != "dono":
        raise HTTPException(403, "Só a admin do projeto mexe no acesso à pasta.")
    return {"ok": True, **sincronizar(projeto_id)}


def sincronizar_em_segundo_plano(projeto_id: str):
    """Depois do aceite de um convite: compartilha a pasta sem atrasar a resposta pra quem aceitou."""
    def _vai():
        try:
            sincronizar(projeto_id)
        except Exception as e:     # nunca derruba o aceite; fica registrado
            esc._registrar("escritorio:drive-sincronizar", f"{type(e).__name__}: {str(e)[:200]}")
    threading.Thread(target=_vai, daemon=True).start()


esc._DEPOIS_DO_ACEITE = sincronizar_em_segundo_plano


# ── fotos do projeto (perfis, 26/09 — decisão do Pedro: "pasta Fotos no Drive"; sobem equipe e fornecedor) ──
# O arquivo mora na pasta "Fotos" dentro da pasta do projeto, no Drive da dona; o banco guarda só legenda, etapa, data
# e "pro cliente" (escritorio_fotos). Sobe e aparece pelo SERVIDOR: o cliente não tem acesso à pasta no Drive, e a
# imagem chega na tela pelo login (nenhum link aberto do Google).

FOTOS = "Fotos"
_FOTO_TETO = 12 * 1024 * 1024        # por foto (a do celular tem 3–6 MB)
_FOTOS_POR_VEZ = 10
_FOTOS_TOTAL = 40 * 1024 * 1024      # por envio: 1 processo no Render, não dá pra segurar mais que isso na memória
_TAMANHOS = {"miniatura": 480, "grande": 1600}
_MINIATURA_DO_GOOGLE = re.compile("^https://[a-z0-9.-]+[.]googleusercontent[.]com/")
_ENVIO_RN = bytes([13, 10])


def _bruto(method, url, token=None, corpo=None, tipo=None, timeout=60):
    """(status, bytes, content-type) — pra subir e baixar imagem. Trocável nos testes (`_BRUTO`)."""
    cab = {}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    if tipo:
        cab["Content-Type"] = tipo
    req = urllib.request.Request(url, data=corpo, method=method, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(_FOTO_TETO + 1), r.headers.get("Content-Type") or ""
    except urllib.error.HTTPError as e:
        return e.code, b"", ""
    except Exception:
        return 0, b"", ""


_BRUTO = _bruto


def tipo_da_foto(dados: bytes):
    """(mime, extensão) pelos PRIMEIROS BYTES — nunca pelo nome do arquivo nem pelo que o navegador disse."""
    if dados[:3] == bytes([0xFF, 0xD8, 0xFF]):
        return "image/jpeg", "jpg"
    if dados[:8] == bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]):
        return "image/png", "png"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp", "webp"
    if dados[4:8] == b"ftyp" and dados[8:12] in (b"heic", b"heix", b"heim", b"heis", b"mif1", b"msf1"):
        return "image/heic", "heic"
    return None, None


def _subir_pro_drive(tok: str, pasta: str, nome: str, mime: str, dados: bytes):
    """Upload multipart do Drive (metadados + bytes num envio só). (status, {"id","name"} | {})."""
    fronteira = "aiarq" + base64.urlsafe_b64encode(os.urandom(12)).decode("ascii").rstrip("=")
    f, rn = fronteira.encode("ascii"), _ENVIO_RN
    meta = json.dumps({"name": nome, "parents": [pasta]}).encode("utf-8")
    corpo = b"".join([b"--", f, rn, b"Content-Type: application/json; charset=UTF-8", rn, rn, meta, rn,
                      b"--", f, rn, b"Content-Type: ", mime.encode("ascii"), rn, rn, dados, rn,
                      b"--", f, b"--", rn])
    st, bruto, _ = _BRUTO("POST", "https://www.googleapis.com/upload/drive/v3/files"
                                  "?uploadType=multipart&supportsAllDrives=true&fields=id,name",
                          tok, corpo, "multipart/related; boundary=" + fronteira, timeout=120)
    try:
        return st, (json.loads(bruto.decode("utf-8")) if st == 200 and bruto else {})
    except (ValueError, UnicodeDecodeError):
        return st, {}


@router.post("/projetos/{projeto_id}/fotos")
def projeto_fotos_subir(projeto_id: str, request: Request, fotos: list[UploadFile] = File(...),
                        legenda: str = Form(""), etapa: str = Form(""), pro_cliente: str = Form("")):
    """Equipe e fornecedor sobem fotos da obra. Vão pra pasta Fotos do Drive da dona; "pro cliente" é decisão da
    EQUIPE (o fornecedor manda, a equipe decide o que o cliente vê — o banco também barra ele de mudar depois)."""
    eu = esc._exige_login(request)
    papel = esc._papel(request, projeto_id)
    if papel not in ("dono", "freela", "fornecedor"):
        raise HTTPException(403, "Só a equipe e os fornecedores do projeto sobem fotos.")
    if not fotos:
        raise HTTPException(400, "Escolha pelo menos uma foto.")
    if len(fotos) > _FOTOS_POR_VEZ:
        raise HTTPException(400, f"Mande até {_FOTOS_POR_VEZ} fotos por vez.")
    leg = esc._texto_sem_controle(legenda, 200)
    et = esc._texto_sem_controle(etapa, 80)
    pro = papel in ("dono", "freela") and str(pro_cliente or "").strip().lower() in ("1", "true", "sim", "on")
    lidas, total = [], 0
    for n, arq in enumerate(fotos, 1):
        dados = arq.file.read(_FOTO_TETO + 1)
        if len(dados) > _FOTO_TETO:
            raise HTTPException(413, f"A foto {n} passou de {_FOTO_TETO // 1048576} MB.")
        mime, ext = tipo_da_foto(dados)
        if not mime:
            raise HTTPException(415, f"A foto {n} não é uma imagem que o AI.arq aceita (JPG, PNG, WEBP ou HEIC).")
        total += len(dados)
        if total > _FOTOS_TOTAL:
            raise HTTPException(413, f"Esse envio passou de {_FOTOS_TOTAL // 1048576} MB. Mande em partes menores.")
        lidas.append((dados, mime, ext))
    p = _dono_do_projeto(projeto_id)
    if not p.get("pasta_id"):
        raise HTTPException(409, "A admin ainda não ligou a pasta do Drive a este projeto.")
    if not _conexao(p["dono"]):
        raise HTTPException(409, "O Google Drive do projeto está desconectado. Avise a admin.")
    tok = _acesso(p["dono"])
    pasta = _subpasta_da_dona(tok, p["pasta_id"], FOTOS)
    dia = _hoje_no_brasil()
    base = " ".join(re.sub("[^0-9A-Za-zÀ-ÿ _-]+", " ", leg or "foto").split())[:60] or "foto"
    feitas, falhas = [], 0
    for i, (dados, mime, ext) in enumerate(lidas, 1):
        nome = f"{dia} {base} {i:02d}.{ext}" if len(lidas) > 1 else f"{dia} {base}.{ext}"
        st, meta = _subir_pro_drive(tok, pasta, nome, mime, dados)
        if st != 200 or not meta.get("id"):
            falhas += 1
            continue
        st_i, linha = esc._SERVICO("POST", "escritorio_fotos", body={
            "projeto_id": projeto_id, "drive_file_id": meta["id"], "legenda": leg, "etapa": et,
            "pro_cliente": pro, "enviada_por": eu["id"]}, prefer="return=representation")
        if st_i >= 300 or st_i == 0 or not linha:
            # sem o registro a foto não aparece em lugar nenhum: não deixa órfã no Drive
            _drive("DELETE", f"files/{meta['id']}", tok, params={"supportsAllDrives": "true"})
            falhas += 1
            continue
        feitas.append(linha[0])
    if not feitas:
        raise HTTPException(502, "As fotos não subiram agora. Tente de novo em instantes.")
    return {"ok": True, "fotos": feitas, "falhas": falhas}


@router.get("/projetos/{projeto_id}/fotos/{foto_id}/imagem")
def projeto_foto_imagem(projeto_id: str, foto_id: str, request: Request, tam: str = "miniatura"):
    """A imagem, pelo login. QUEM pode ver é o banco que responde: a linha só volta pra quem pode (o cliente, só
    as "pro cliente"). Miniatura do próprio Google no tamanho pedido; sem miniatura ainda, o original (no teto)."""
    esc._exige_login(request)
    if not esc._UUID.match(str(foto_id or "")):
        raise HTTPException(404, "Foto não encontrada.")
    st, linhas = esc._COMO_USUARIO(request, "GET", "escritorio_fotos", params={
        "id": f"eq.{foto_id}", "projeto_id": f"eq.{projeto_id}", "select": "drive_file_id"})
    if st == 0 or st >= 500:
        raise HTTPException(502, "O banco não respondeu agora. Tente de novo em instantes.")
    if st >= 300 or not isinstance(linhas, list) or not linhas:
        raise HTTPException(404, "Foto não encontrada.")
    fid = str(linhas[0].get("drive_file_id") or "")
    if not _ID_DRIVE.fullmatch(fid):
        raise HTTPException(404, "Foto não encontrada.")
    p = _dono_do_projeto(projeto_id)
    if not _conexao(p["dono"]):
        raise HTTPException(409, "O Google Drive do projeto está desconectado.")
    tok = _acesso(p["dono"])
    st_f, f = _drive("GET", f"files/{fid}", tok, params={"fields": "thumbnailLink", "supportsAllDrives": "true"})
    if st_f == 404:
        raise HTTPException(404, "A foto não está mais no Drive.")
    if st_f != 200 or f is None:
        raise HTTPException(502, "O Google não respondeu agora. Tente de novo em instantes.")
    link, st_b, dados, tipo = str(f.get("thumbnailLink") or ""), 0, b"", ""
    if _MINIATURA_DO_GOOGLE.match(link):
        lado = _TAMANHOS.get(tam, _TAMANHOS["miniatura"])
        st_b, dados, tipo = _BRUTO("GET", re.sub("=s[0-9]+$", f"=s{lado}", link), tok)
    if st_b != 200 or not dados:
        st_b, dados, tipo = _BRUTO("GET", f"https://www.googleapis.com/drive/v3/files/{fid}?alt=media&supportsAllDrives=true", tok)
        if st_b != 200 or not dados or len(dados) > _FOTO_TETO:
            raise HTTPException(502, "A foto ainda está sendo preparada no Drive. Tente de novo em instantes.")
    mime = tipo.split(";")[0].strip() if tipo.startswith("image/") else (tipo_da_foto(dados)[0] or "application/octet-stream")
    return Response(content=dados, media_type=mime,
                    headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@router.delete("/projetos/{projeto_id}/fotos/{foto_id}")
def projeto_foto_apagar(projeto_id: str, foto_id: str, request: Request):
    """A admin apaga qualquer foto; equipe e fornecedor, as que subiram. Vai pra LIXEIRA do Drive (volta em 30 dias)."""
    eu = esc._exige_login(request)
    papel = esc._papel(request, projeto_id)
    if not esc._UUID.match(str(foto_id or "")):
        raise HTTPException(404, "Foto não encontrada.")
    f = esc._um(esc._SERVICO("GET", "escritorio_fotos", params={
        "id": f"eq.{foto_id}", "projeto_id": f"eq.{projeto_id}", "select": "id,drive_file_id,enviada_por"}))
    if not f or not papel:
        raise HTTPException(404, "Foto não encontrada.")
    if not (papel == "dono" or (papel in ("freela", "fornecedor") and str(f.get("enviada_por")) == eu["id"])):
        raise HTTPException(403, "Só quem subiu a foto (ou a admin) apaga.")
    p = _dono_do_projeto(projeto_id)
    if not _conexao(p["dono"]):
        raise HTTPException(409, "O Google Drive do projeto está desconectado: a foto não foi apagada.")
    st_d, _ = _drive("PATCH", f"files/{f['drive_file_id']}", _acesso(p["dono"]),
                     params={"supportsAllDrives": "true"}, corpo={"trashed": True})
    if st_d not in (200, 404):
        raise HTTPException(502, "O Google não respondeu agora. A foto não foi apagada.")
    st, _ = esc._SERVICO("DELETE", "escritorio_fotos", params={"id": f"eq.{foto_id}", "projeto_id": f"eq.{projeto_id}"})
    if st >= 300 or st == 0:
        raise HTTPException(502, "A foto foi pra lixeira do Drive, mas não saiu da lista agora. Tente de novo.")
    return {"ok": True}
