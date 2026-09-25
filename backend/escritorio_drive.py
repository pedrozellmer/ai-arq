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

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

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


def _drive(method, caminho, token, params=None, corpo=None):
    url = "https://www.googleapis.com/drive/v3/" + caminho
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return _HTTP(method, url, token=token, corpo=corpo)


# ── conexões guardadas ─────────────────────────────────────────────────────

def _conexao(user_id: str):
    st, linhas = esc._SERVICO("GET", "escritorio_drive_conexoes",
                              params={"user_id": f"eq.{user_id}", "select": "user_id,google_email,token_cifrado"})
    if st >= 300 or linhas is None:
        raise HTTPException(502, "O banco não respondeu agora. Tente de novo em instantes.")
    return linhas[0] if linhas else None


def _acesso(user_id: str) -> str:
    """Chave de acesso de curta duração da conta ligada (renova com o refresh token cifrado)."""
    em_cache = _CACHE_ACESSO.get(user_id)
    if em_cache and em_cache[1] > time.time() + 60:
        return em_cache[0]
    c = _conexao(user_id)
    if not c:
        raise HTTPException(409, "O Google Drive não está conectado.")
    st, r = _HTTP("POST", "https://oauth2.googleapis.com/token", form={
        "client_id": CLIENT_ID, "client_secret": _segredo_do_cliente(),
        "refresh_token": decifrar(c["token_cifrado"]), "grant_type": "refresh_token"})
    if st != 200 or not r or not r.get("access_token"):
        if r and r.get("error") == "invalid_grant":   # a pessoa revogou no Google, ou o token venceu
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


def _volta(projeto: str, resultado: str) -> RedirectResponse:
    destino = f"{SITE}/escritorio.html?drive={urllib.parse.quote(resultado)}"
    destino += f"#/p/{projeto}/arquivos" if projeto else "#/"
    return RedirectResponse(destino, status_code=302)


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
    st_s, _ = esc._SERVICO("POST", "escritorio_drive_conexoes",
                           body={"user_id": dados["u"], "google_email": email,
                                 "token_cifrado": cifrar(r["refresh_token"]),
                                 "atualizado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                           params={"on_conflict": "user_id"},
                           prefer="resolution=merge-duplicates,return=minimal")
    if st_s >= 300:
        return _volta(projeto, "erro")
    _CACHE_ACESSO.pop(dados["u"], None)
    return _volta(projeto, "ok")


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
    st, r = _drive("GET", "files", tok, params={
        "q": f"'{pai}' in parents and mimeType='{PASTA}' and trashed=false",
        "fields": "files(id,name)", "orderBy": "name", "pageSize": "200",
        "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
    if st != 200 or r is None:
        raise HTTPException(502, "O Google não respondeu agora. Tente de novo em instantes.")
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


def _dentro_da_pasta(tok: str, alvo: str, raiz: str, limite: int = 12) -> bool:
    """`alvo` é a própria pasta do projeto ou está dentro dela (sobe pelos pais, com limite)."""
    atual, vistos = alvo, 0
    while atual and vistos <= limite:
        if atual == raiz:
            return True
        st, f = _drive("GET", f"files/{atual}", tok, params={"fields": "parents", "supportsAllDrives": "true"})
        if st != 200 or not f or not f.get("parents"):
            return False
        atual, vistos = f["parents"][0], vistos + 1
    return False


@router.get("/projetos/{projeto_id}/arquivos")
def projeto_arquivos(projeto_id: str, request: Request, pasta: str = ""):
    """A lista da pasta do projeto (ou de uma subpasta DELA), pra admin e pra equipe, com a chave da dona."""
    esc._exige_login(request)
    if not esc._papel(request, projeto_id):
        raise HTTPException(403, "Você não faz parte deste projeto.")
    p = _dono_do_projeto(projeto_id)
    if not p.get("pasta_id"):
        return {"sem_pasta": True}
    if not _conexao(p["dono"]):
        return {"sem_conexao": True, "pasta": {"id": p["pasta_id"], "nome": p.get("pasta_caminho") or ""}}
    tok = _acesso(p["dono"])
    alvo = p["pasta_id"] if not pasta else id_da_pasta(pasta)
    if alvo != p["pasta_id"] and not _dentro_da_pasta(tok, alvo, p["pasta_id"]):
        raise HTTPException(403, "Essa pasta não é deste projeto.")
    st, r = _drive("GET", "files", tok, params={
        "q": f"'{alvo}' in parents and trashed=false",
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink,iconLink,size,lastModifyingUser(displayName))",
        "orderBy": "folder,name", "pageSize": "300",
        "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
    if st != 200 or r is None:
        raise HTTPException(502, "O Google não respondeu agora. Tente de novo em instantes.")
    return {"pasta": {"id": p["pasta_id"], "nome": p.get("pasta_caminho") or "", "atual": alvo},
            "arquivos": [{"id": f["id"], "nome": f.get("name") or "", "pasta": f.get("mimeType") == PASTA,
                          "tipo": f.get("mimeType") or "", "link": f.get("webViewLink") or "",
                          "icone": f.get("iconLink") or "", "tamanho": f.get("size"),
                          "mudou_em": f.get("modifiedTime"),
                          "por": (f.get("lastModifyingUser") or {}).get("displayName") or ""}
                         for f in r.get("files", [])]}


# ── compartilhamento com a equipe ──────────────────────────────────────────

def sincronizar(projeto_id: str) -> dict:
    """Equipe ativa = quem tem acesso de edição à pasta. Cria o que falta, tira de quem saiu (e da pasta
    antiga, se a admin trocou). Só mexe nas permissões que NÓS criamos. Nunca derruba quem chamou:
    falha vira item em `falhas`."""
    p = _dono_do_projeto(projeto_id)
    if not p.get("pasta_id") or not _conexao(p["dono"]):
        return {"compartilhados": 0, "tirados": 0, "falhas": []}
    tok = _acesso(p["dono"])
    st_m, membros = esc._SERVICO("GET", "escritorio_membros", params={
        "projeto_id": f"eq.{projeto_id}", "status": "eq.ativo", "papel": "eq.freela", "select": "id,user_id"})
    st_r, feitos = esc._SERVICO("GET", "escritorio_drive_permissoes", params={
        "projeto_id": f"eq.{projeto_id}", "select": "id,membro_id,pasta_id,permission_id,email"})
    if st_m >= 300 or st_r >= 300 or membros is None or feitos is None:
        return {"compartilhados": 0, "tirados": 0, "falhas": ["banco"]}
    ids = [m["user_id"] for m in membros if m.get("user_id")]
    emails = {}
    if ids:
        st_e, perfis = esc._SERVICO("GET", "profiles", params={
            "user_id": "in.(" + ",".join(ids) + ")", "select": "user_id,email"})
        if st_e < 300 and perfis:
            emails = {str(x["user_id"]): (x.get("email") or "").strip().lower() for x in perfis}
    ativos = {m["id"]: emails.get(str(m.get("user_id")), "") for m in membros}
    feito_por_membro = {f.get("membro_id"): f for f in feitos if f.get("pasta_id") == p["pasta_id"]}
    compartilhados, tirados, falhas = 0, 0, []
    # tira: quem saiu, e o que ficou na pasta antiga
    for f in feitos:
        if f.get("pasta_id") == p["pasta_id"] and f.get("membro_id") in ativos:
            continue
        st_d, _ = _drive("DELETE", f"files/{f['pasta_id']}/permissions/{f['permission_id']}", tok,
                         params={"supportsAllDrives": "true"})
        if st_d in (200, 204, 404):
            esc._SERVICO("DELETE", "escritorio_drive_permissoes", params={"id": f"eq.{f['id']}"})
            tirados += 1
        else:
            falhas.append(f.get("email") or "?")
    # dá: quem está ativo e ainda não tem
    for membro_id, email in ativos.items():
        if membro_id in feito_por_membro:
            continue
        if not email:
            falhas.append("(sem e-mail)")
            continue
        st_c, perm = _drive("POST", f"files/{p['pasta_id']}/permissions", tok,
                            params={"sendNotificationEmail": "true", "supportsAllDrives": "true"},
                            corpo={"role": "writer", "type": "user", "emailAddress": email})
        if st_c == 200 and perm and perm.get("id"):
            esc._SERVICO("POST", "escritorio_drive_permissoes", body={
                "projeto_id": projeto_id, "membro_id": membro_id, "email": email,
                "pasta_id": p["pasta_id"], "permission_id": perm["id"]})
            compartilhados += 1
        else:
            falhas.append(email)
    return {"compartilhados": compartilhados, "tirados": tirados, "falhas": falhas}


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
