# -*- coding: utf-8 -*-
"""Escritório (piloto DTZ, 23/09/2026) — o CONVITE.

É a única parte do escritório que precisa do servidor. Tarefas, atas,
comentários e membros a tela lê e grava direto no banco com o login da pessoa:
quem decide quem pode o quê é a RLS + os gatilhos das tabelas `escritorio_*`
(migração em `migrations_pendentes/escritorio_piloto_dtz_banco.sql`, 34
situações provadas no banco). Aqui fica só o que o banco, de propósito, NÃO
deixa ninguém fazer pela tela:

  • gerar o token do convite e mandar o e-mail;
  • ATIVAR a pessoa no aceite — a RLS proíbe o próprio admin de ativar alguém
    (`escritorio_membro_guarda`: "só o aceite do convite (servidor) ativa").

O token nunca é guardado: o banco tem só o SHA-256 dele (`convite_hash`). O
link leva o token no FRAGMENTO (`#t=...`), que o navegador não manda pra
servidor nenhum — não cai em log de CDN nem de analytics.

A pessoa NÃO precisa ter Google: entra com Google ou cria senha com o e-mail do
convite (decisão do Pedro, 23/09). A pasta do Drive é outra conversa (etapa do
Drive): lá o Google exige conta Google pra editar.
"""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/escritorio", tags=["Escritório"])

SITE = "https://ai.arq.br"
VALIDADE_DIAS = 14
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TETO = {"nome": 120, "funcao": 60, "telefone": 40}

# injetados por main.configurar_escritorio (evita import circular com main.py)
_SERVICO = None      # _supa_rest_service(method, path, body=None, params=None, prefer=None, timeout=15)
_COMO_USUARIO = None  # _supa_rest_as_user(request, method, path, body=None, params=None, prefer=None, timeout=15)
_USUARIO = None      # _get_user_from_request(request) -> {"id","email"} | None
_ENVIAR = None       # _send_email_smtp(to, subject, html, text="", log_kind=..., job_id="") -> bool
_MOLDURA = None      # _email_wrap(title, body_html, cta_text, cta_url, ..., reason=..., preheader=...)
_REGISTRAR = None    # _log_error(stage, msg, severity=...)


def configurar(servico, como_usuario, usuario, enviar, moldura, registrar=None):
    global _SERVICO, _COMO_USUARIO, _USUARIO, _ENVIAR, _MOLDURA, _REGISTRAR
    _SERVICO, _COMO_USUARIO, _USUARIO = servico, como_usuario, usuario
    _ENVIAR, _MOLDURA, _REGISTRAR = enviar, moldura, registrar


# ── peças puras (testáveis sem banco) ──────────────────────────────────────

def hash_do_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def novo_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def link_do_convite(token: str) -> str:
    return f"{SITE}/convite.html#t={token}"


def normalizar_email(bruto) -> str:
    email = str(bruto or "").strip().lower()
    if not email or len(email) > 254 or not _EMAIL.match(email):
        raise HTTPException(400, "Confira o e-mail: ele parece incompleto.")
    return email


def texto_curto(bruto, campo: str):
    """None/vazio → None; acima do teto → 400 em português ANTES do CHECK do banco."""
    if bruto is None:
        return None
    t = str(bruto).strip()
    if not t:
        return None
    if len(t) > _TETO[campo]:
        raise HTTPException(400, f"O campo {campo} passou de {_TETO[campo]} caracteres.")
    return t


def mascarar(email: str) -> str:
    """'rafael.souza@exemplo.com' → 'ra***@exemplo.com' (a página pública do convite não expõe o e-mail inteiro)."""
    nome, _, dominio = (email or "").partition("@")
    if not dominio:
        return ""
    return f"{nome[:2]}***@{dominio}"


def expirado(expira_iso, agora=None) -> bool:
    if not expira_iso:
        return True
    try:
        exp = datetime.fromisoformat(str(expira_iso).replace("Z", "+00:00"))
    except ValueError:
        return True
    return (agora or datetime.now(timezone.utc)) >= exp


def _escapar(t) -> str:
    return (str(t or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


TETO_ASSUNTO = 52  # a régua da casa (tests/test_emails_eficientes.py): o que cabe na tela do celular


def assunto_do_convite(quem_convida: str, projeto: str) -> str:
    """'Daniela te convidou: Residência Alto da Boa Vista', cortado com '…' no teto."""
    primeiro = (str(quem_convida or "").split() or ["Alguém"])[0]
    a = f"{primeiro} te convidou: {projeto}"
    return a if len(a) <= TETO_ASSUNTO else a[:TETO_ASSUNTO - 1].rstrip() + "…"


def email_do_convite(quem_convida: str, email_de_quem_convida: str, projeto: str, link: str):
    """(assunto, html, texto). Sem Reply-To trocado: a porta única de e-mail não
    tem esse parâmetro e não vale mexer nela por isso — o e-mail de quem convida
    vai escrito no corpo."""
    q, p = _escapar(quem_convida), _escapar(projeto)
    assunto = assunto_do_convite(quem_convida, projeto)
    corpo = (
        f'<p style="margin:0 0 12px;"><b>{q}</b> te convidou para trabalhar no projeto '
        f'<b>{p}</b> no AI.arq: tarefas, atas de reunião e os arquivos do projeto num lugar só.</p>'
        '<p style="margin:0 0 12px;">Pra entrar, clique no botão. Dá pra usar a conta Google '
        'ou criar uma senha com este mesmo e-mail — não precisa preencher cadastro.</p>'
        f'<p style="margin:0;color:#64748b;font-size:13px;">O convite vale {VALIDADE_DIAS} dias. '
        f'Dúvida sobre o projeto? Fale com {q}'
        + (f' em {_escapar(email_de_quem_convida)}' if email_de_quem_convida else '') + '.</p>')
    html = _MOLDURA(f"Convite para {projeto}", corpo, cta_text="Aceitar convite", cta_url=link,
                    reason=f"Você recebeu este e-mail porque {quem_convida} digitou seu endereço num convite.",
                    preheader=f"{quem_convida} te chamou para o projeto {projeto}.")
    texto = (f"{quem_convida} te convidou para o projeto {projeto} no AI.arq.\n\n"
             f"Aceitar convite: {link}\n\nO convite vale {VALIDADE_DIAS} dias.")
    return assunto, html, texto


# ── acesso ao banco ────────────────────────────────────────────────────────

def _um(resp):
    """(status, json) → primeira linha, None se vazio; 502 se o banco falhou.
    🪤 vazio ≠ falhou: (200, []) é "não existe"; (500, None) é "não sei"."""
    status, dados = resp
    if status in (0,) or status >= 500 or dados is None:
        raise HTTPException(502, "O banco não respondeu agora. Tente de novo em instantes.")
    if status >= 400:
        raise HTTPException(502, "Não consegui ler o convite agora. Tente de novo em instantes.")
    return dados[0] if isinstance(dados, list) and dados else None


def _papel(request, projeto_id: str):
    """O papel de quem está logado, perguntado AO BANCO com o login dele."""
    status, dados = _COMO_USUARIO(request, "POST", "rpc/escritorio_papel", body={"p_projeto": projeto_id})
    if status >= 500 or status == 0:
        raise HTTPException(502, "O banco não respondeu agora. Tente de novo em instantes.")
    return dados if isinstance(dados, str) else None


def _exige_login(request):
    u = _USUARIO(request)
    if not u:
        raise HTTPException(401, "Entre na sua conta pra continuar.")
    return u


# ── rotas ──────────────────────────────────────────────────────────────────

@router.post("/projetos/{projeto_id}/convites")
def convidar(projeto_id: str, request: Request, corpo: dict):
    """Admin convida (ou reconvida) alguém pelo e-mail. Devolve o LINK também,
    pra ela poder mandar pelo WhatsApp se o e-mail demorar."""
    eu = _exige_login(request)
    if _papel(request, projeto_id) != "dono":
        raise HTTPException(403, "Só a admin do projeto convida pessoas.")
    email = normalizar_email(corpo.get("email"))
    if email == (eu.get("email") or "").lower():
        raise HTTPException(400, "Esse é o seu próprio e-mail.")
    campos = {k: texto_curto(corpo.get(k), k) for k in ("nome", "funcao", "telefone")}

    projeto = _um(_SERVICO("GET", "escritorio_projetos",
                           params={"id": f"eq.{projeto_id}", "select": "id,nome,dono"}))
    if not projeto:
        raise HTTPException(404, "Projeto não encontrado.")
    atual = _um(_SERVICO("GET", "escritorio_membros",
                         params={"projeto_id": f"eq.{projeto_id}", "email": f"eq.{email}",
                                 "select": "id,status"}))
    if atual and atual["status"] == "ativo":
        raise HTTPException(409, "Essa pessoa já está no projeto.")

    token = novo_token()
    agora = datetime.now(timezone.utc)
    linha = {"convite_hash": hash_do_token(token),
             "convite_expira": (agora + timedelta(days=VALIDADE_DIAS)).isoformat(),
             "convidado_em": agora.isoformat(),
             **{k: v for k, v in campos.items() if v is not None}}
    if atual:  # convidado de novo (token novo) ou removido voltando
        linha.update({"status": "convidado", "user_id": None, "aceito_em": None, "removido_em": None})
        status, dados = _SERVICO("PATCH", "escritorio_membros", body=linha,
                                 params={"id": f"eq.{atual['id']}", "projeto_id": f"eq.{projeto_id}"},
                                 prefer="return=representation")
    else:
        linha.update({"projeto_id": projeto_id, "email": email, "papel": "freela", "status": "convidado"})
        status, dados = _SERVICO("POST", "escritorio_membros", body=linha, prefer="return=representation")
    if status >= 300 or not dados:
        raise HTTPException(502, "Não consegui registrar o convite agora. Tente de novo em instantes.")

    admin = _um(_SERVICO("GET", "escritorio_membros",
                         params={"projeto_id": f"eq.{projeto_id}", "papel": "eq.dono", "select": "nome,email"})) or {}
    quem = admin.get("nome") or eu.get("email") or "Alguém"
    link = link_do_convite(token)
    assunto, html, texto = email_do_convite(quem, admin.get("email") or eu.get("email"), projeto["nome"], link)
    enviado = bool(_ENVIAR(email, assunto, html, texto, log_kind="escritorio_convite"))
    return {"ok": True, "membro_id": dados[0]["id"], "email_enviado": enviado, "link": link,
            "expira_em": linha["convite_expira"]}


@router.post("/convite/ver")
def ver_convite(corpo: dict):
    """Página pública do convite: o que mostrar ANTES do login. Sem e-mail inteiro."""
    token = str(corpo.get("token") or "")
    if len(token) < 20:
        raise HTTPException(404, "Convite não encontrado.")
    m = _um(_SERVICO("GET", "escritorio_membros",
                     params={"convite_hash": f"eq.{hash_do_token(token)}",
                             "select": "email,status,convite_expira,projeto_id"}))
    if not m or m["status"] != "convidado":
        raise HTTPException(404, "Este convite não vale mais. Peça um novo a quem te convidou.")
    p = _um(_SERVICO("GET", "escritorio_projetos", params={"id": f"eq.{m['projeto_id']}", "select": "nome"})) or {}
    admin = _um(_SERVICO("GET", "escritorio_membros",
                         params={"projeto_id": f"eq.{m['projeto_id']}", "papel": "eq.dono", "select": "nome"})) or {}
    return {"projeto": p.get("nome") or "", "convidado_por": admin.get("nome") or "",
            "email": mascarar(m["email"]), "expirado": expirado(m["convite_expira"])}


@router.post("/convite/aceitar")
def aceitar_convite(request: Request, corpo: dict):
    """Logado (Google OU senha) + token válido → vira membro ativo. Só aqui alguém é ativado."""
    eu = _exige_login(request)
    token = str(corpo.get("token") or "")
    if len(token) < 20:
        raise HTTPException(404, "Convite não encontrado.")
    m = _um(_SERVICO("GET", "escritorio_membros",
                     params={"convite_hash": f"eq.{hash_do_token(token)}",
                             "select": "id,projeto_id,email,nome,status,convite_expira"}))
    if not m or m["status"] != "convidado":
        raise HTTPException(404, "Este convite não vale mais. Peça um novo a quem te convidou.")
    if expirado(m["convite_expira"]):
        raise HTTPException(410, "Este convite venceu. Peça um novo a quem te convidou.")
    ja = _um(_SERVICO("GET", "escritorio_membros",
                      params={"projeto_id": f"eq.{m['projeto_id']}", "user_id": f"eq.{eu['id']}",
                              "status": "eq.ativo", "select": "id"}))
    if ja:
        raise HTTPException(409, "Você já está neste projeto com esta conta.")
    ativar = {"user_id": eu["id"], "status": "ativo",
              "aceito_em": datetime.now(timezone.utc).isoformat(),
              "convite_hash": None, "convite_expira": None}
    if not m.get("nome"):   # o admin não deu nome: vale o do cadastro (a pessoa não edita a própria linha)
        try:
            perfil = _um(_SERVICO("GET", "profiles", params={"user_id": f"eq.{eu['id']}", "select": "full_name"})) or {}
        except HTTPException:
            perfil = {}   # nome é bônus: sem ele a tela mostra o começo do e-mail
        nome = str(perfil.get("full_name") or "").strip()[:120]
        if nome:
            ativar["nome"] = nome
    status, dados = _SERVICO("PATCH", "escritorio_membros",
                             body=ativar,
                             params={"id": f"eq.{m['id']}", "status": "eq.convidado"},
                             prefer="return=representation")
    if status >= 300 or not dados:
        raise HTTPException(502, "Não consegui confirmar o convite agora. Tente de novo em instantes.")
    outro_email = (eu.get("email") or "").lower() != (m["email"] or "").lower()
    return {"ok": True, "projeto_id": m["projeto_id"],
            # conta com e-mail diferente do convite: vale (o token prova que o convite chegou
            # a ela), mas a tela avisa — a pasta do Drive vai ser compartilhada com ESTA conta.
            "email_da_conta_diferente": outro_email}
