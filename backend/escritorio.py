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
# 🔒 o convite sai pelo NOSSO e-mail: sem teto, uma conta viraria canal de spam.
# Piloto: uma pessoa convidando a equipe cabe folgado em 40 por dia.
CONVITES_POR_DIA = 40
# 🔒 A3 (24/09): por destinatário também — sem isto, reenviar pro mesmo endereço
# bombardeava a caixa de alguém pelo nosso domínio.
CONVITES_POR_DESTINO_DIA = 3
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TETO = {"nome": 120, "funcao": 60, "telefone": 40}

# injetados por main.configurar_escritorio (evita import circular com main.py)
_SERVICO = None      # _supa_rest_service(method, path, body=None, params=None, prefer=None, timeout=15)
_COMO_USUARIO = None  # _supa_rest_as_user(request, method, path, body=None, params=None, prefer=None, timeout=15)
_USUARIO = None      # _get_user_from_request(request) -> {"id","email"} | None
_ENVIAR = None       # _send_email_smtp(to, subject, html, text="", log_kind=..., job_id="") -> bool
_MOLDURA = None      # _email_wrap(title, body_html, cta_text, cta_url, ..., reason=..., preheader=...)
_REGISTRAR = None    # _log_error(stage, msg, severity=...)
_DEPOIS_DO_ACEITE = None  # escritorio_drive: compartilha a pasta do projeto com quem acabou de entrar


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
    # 🔒 sem caractere de controle: nome com quebra de linha entraria no ASSUNTO do e-mail
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(bruto)).strip()
    if not t:
        return None
    if len(t) > _TETO[campo]:
        raise HTTPException(400, f"O campo {campo} passou de {_TETO[campo]} caracteres.")
    return t


def mascarar(email: str) -> str:
    """'pessoa.equipe@exemplo.com' → 'pe***@exemplo.com' (a página pública do convite não expõe o e-mail inteiro)."""
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
    """'Admin te convidou: Projeto Exemplo', cortado com '…' no teto."""
    primeiro = (str(quem_convida or "").split() or ["Alguém"])[0]
    a = re.sub(r"[\x00-\x1f\x7f]+", " ", f"{primeiro} te convidou: {projeto}").strip()
    return a if len(a) <= TETO_ASSUNTO else a[:TETO_ASSUNTO - 1].rstrip() + "…"


def email_do_convite(quem_convida: str, email_de_quem_convida: str, projeto: str, link: str,
                     moldura=None):
    """(assunto, html, texto). Sem Reply-To trocado: a porta única de e-mail não
    tem esse parâmetro e não vale mexer nela por isso — o e-mail de quem convida
    vai escrito no corpo."""
    q, p = _escapar(quem_convida), _escapar(projeto)
    assunto = assunto_do_convite(quem_convida, projeto)
    corpo = (
        f'<p style="margin:0 0 12px;"><b>{q}</b> te convidou para trabalhar no projeto '
        f'<b>{p}</b> no AI.arq: tarefas, atas de reunião e os arquivos do projeto num lugar só.</p>'
        '<p style="margin:0 0 12px;">Pra entrar, clique no botão. Dá pra usar a conta Google '
        'ou criar uma senha com este mesmo e-mail. Antes de entrar, você preenche um cadastro rápido '
        'e aceita os Termos de Uso e a Política de Privacidade do AI.arq.</p>'
        f'<p style="margin:0;color:#64748b;font-size:13px;">O convite vale {VALIDADE_DIAS} dias. '
        f'Dúvida sobre o projeto? Fale com {q}'
        + (f' em {_escapar(email_de_quem_convida)}' if email_de_quem_convida else '') + '.</p>')
    # a prévia do painel passa a moldura de verdade: não depende de quem configurou o módulo por último
    # 🔒 A2 (24/09): título, prévia e rodapé também são HTML — nome de projeto como
    # "<a href=...>" virava botão falso saindo do nosso domínio. Tudo vai escapado.
    html = (moldura or _MOLDURA)(f"Convite para {p}", corpo, cta_text="Aceitar convite", cta_url=link,
                    reason=f"Você recebeu este e-mail porque {q} digitou seu endereço num convite.",
                    preheader=f"{q} te chamou para o projeto {p}.")
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


def _contar(params) -> int:
    status, linhas = _SERVICO("GET", "escritorio_convites_enviados", params={**params, "select": "id"})
    if status >= 500 or status == 0 or linhas is None or status >= 400:
        raise HTTPException(502, "O banco não respondeu agora. Tente de novo em instantes.")
    return len(linhas)


def convites_nas_ultimas_24h(user_id: str, agora=None, destino: str = "", projeto_id: str = "") -> tuple:
    """(e-mails de convite desta conta, e-mails pra este destinatário NESTE projeto) nas últimas 24 h.

    🔒 A3 (24/09): cada ENVIO vira uma linha em escritorio_convites_enviados, que só o servidor
    escreve (o destino guardado é o SHA-256 do e-mail). O teto por destinatário é POR PROJETO:
    convidar a mesma estagiária pra 4 projetos no mesmo dia é uso normal (revisão adversarial 24/09).
    🪤 Banco fora aqui é 502, não "0": contar zero liberaria o envio exatamente quando não sei."""
    agora = agora or datetime.now(timezone.utc)
    desde = (agora - timedelta(hours=24)).isoformat()
    por_conta = _contar({"admin": f"eq.{user_id}", "enviado_em": f"gte.{desde}"})
    por_destino = 0
    if destino:
        filtro = {"destino_hash": f"eq.{hash_do_token(destino)}", "enviado_em": f"gte.{desde}"}
        if projeto_id:
            filtro["projeto_id"] = f"eq.{projeto_id}"
        por_destino = _contar(filtro)
    return por_conta, por_destino


def _registrar(stage: str, msg: str):
    if _REGISTRAR:
        try:
            _REGISTRAR(stage, msg, severity="warning")
        except Exception:
            pass


def _reservar_envio(user_id: str, projeto_id: str, destino: str):
    """Grava o envio ANTES de mandar e devolve o id da reserva (None = não consegui gravar).
    Reservar primeiro e contar depois (contando a própria reserva) fecha a corrida de dois
    pedidos em paralelo passando juntos pelo teto (revisão adversarial 24/09)."""
    status, dados = _SERVICO("POST", "escritorio_convites_enviados",
                             body={"admin": user_id, "projeto_id": projeto_id,
                                   "destino_hash": hash_do_token(destino)}, prefer="return=representation")
    if status >= 300 or status == 0 or not dados:
        _registrar("escritorio:teto-convite", f"reserva do envio de convite falhou (HTTP {status}) — e-mail NÃO enviado")
        return None
    return dados[0].get("id")


def _cancelar_reserva(reserva_id):
    status, _ = _SERVICO("DELETE", "escritorio_convites_enviados", params={"id": f"eq.{reserva_id}"})
    if status >= 300 or status == 0:
        _registrar("escritorio:teto-convite", f"reserva {reserva_id} não foi desfeita (HTTP {status}) — conta a mais no teto")


def _no_piloto(user_id: str) -> bool:
    """🔒 A1 (24/09): quem manda convite tem que estar na lista do piloto (tabela só do servidor).
    O card do painel não é trava — a API é pública."""
    status, linhas = _SERVICO("GET", "escritorio_piloto", params={"user_id": f"eq.{user_id}", "select": "user_id"})
    if status >= 500 or status == 0 or linhas is None:
        raise HTTPException(502, "O banco não respondeu agora. Tente de novo em instantes.")
    return bool(linhas)


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
    if not _no_piloto(eu["id"]):
        raise HTTPException(403, "O Escritório está em piloto fechado.")
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
                                 "select": "id,status,convite_expira"}))
    if atual and atual["status"] == "ativo":
        raise HTTPException(409, "Essa pessoa já está no projeto.")

    agora = datetime.now(timezone.utc)
    # 🔒 Reenvio de convite AINDA VÁLIDO com o e-mail já no teto: NÃO troca o link. Trocar matava o
    # link do e-mail que a pessoa já tem, e o novo não saía por e-mail (2ª revisão, 24/09).
    # Convite novo, vencido ou de quem saiu não tem link vivo a perder: segue e devolve o link.
    if atual and atual["status"] == "convidado" and not expirado(atual.get("convite_expira"), agora):
        try:
            por_conta, por_destino = convites_nas_ultimas_24h(eu["id"], agora, destino=email, projeto_id=projeto_id)
        except HTTPException:
            por_conta = por_destino = 0   # não sei contar: segue; a contagem depois da reserva decide o e-mail
        if por_conta >= CONVITES_POR_DIA or por_destino >= CONVITES_POR_DESTINO_DIA:
            raise HTTPException(429, "Hoje o convite já saiu por e-mail o bastante, então o link não foi trocado: "
                                     "o do último e-mail continua valendo. Se a pessoa não acha o e-mail, cancele "
                                     "o convite e convide de novo, que o link novo aparece aqui pra você mandar.")
    token = novo_token()
    linha = {"convite_hash": hash_do_token(token),
             "convite_expira": (agora + timedelta(days=VALIDADE_DIAS)).isoformat(),
             "convidado_em": agora.isoformat(),
             **{k: v for k, v in campos.items() if v is not None}}
    if atual:  # convidado de novo (token novo) ou removido voltando
        linha.update({"status": "convidado", "user_id": None, "aceito_em": None, "removido_em": None})
        if atual["status"] != "convidado":
            linha["visto_por"] = None   # quem saiu e volta: a conta que abriu o convite antigo não vale mais
            linha["pode_baixar"] = False  # e a permissão de baixar recomeça desligada (a admin libera de novo)
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
    # 🔒 O teto segura o NOSSO E-MAIL, nunca o convite: passou do teto, o convite nasce igual e
    # o link volta pra admin mandar pela conversa que já usa (a tela mostra "mande o link abaixo").
    enviado, motivo = False, None
    reserva = _reservar_envio(eu["id"], projeto_id, email)
    if reserva is None:
        motivo = "nao_contou"
    else:
        try:
            por_conta, por_destino = convites_nas_ultimas_24h(eu["id"], agora, destino=email, projeto_id=projeto_id)
        except HTTPException:
            por_conta = por_destino = None
        if por_conta is None:
            motivo = "nao_contou"                        # na dúvida, não manda
        elif por_conta > CONVITES_POR_DIA:
            motivo = "teto_conta"
        elif por_destino > CONVITES_POR_DESTINO_DIA:
            motivo = "teto_destino"
        if motivo:
            _cancelar_reserva(reserva)
        else:
            try:
                enviado = bool(_ENVIAR(email, assunto, html, texto, log_kind="escritorio_convite"))
            except Exception as e:                       # a reserva fica: tentativa conta pro teto
                _registrar("escritorio:convite-email", f"SMTP falhou no convite: {type(e).__name__}")
                enviado = False
            if not enviado and not motivo:
                motivo = "email_falhou"
    return {"ok": True, "membro_id": dados[0]["id"], "email_enviado": enviado, "motivo_sem_email": motivo,
            "link": link, "expira_em": linha["convite_expira"]}


def _recusa_se_nao_vale(m):
    """404 = link trocado por um convite mais novo, ou cancelado (a linha não tem mais este hash);
    409 = já foi usado (a pessoa entrou); 404 também pra quem saiu do projeto."""
    if not m:
        raise HTTPException(404, "Este link não vale mais: foi trocado por um convite mais novo ou cancelado. "
                                 "Use o e-mail de convite mais recente ou fale com quem te convidou.")
    if m["status"] == "ativo":
        raise HTTPException(409, "Este convite já foi usado. Se foi você, entre na sua conta: o projeto está no seu Escritório.")
    if m["status"] != "convidado":
        raise HTTPException(404, "Este convite não vale mais. Peça um novo a quem te convidou.")


@router.post("/convite/ver")
def ver_convite(corpo: dict):
    """Página pública do convite: o que mostrar ANTES do login. Sem e-mail inteiro."""
    token = str(corpo.get("token") or "")
    if len(token) < 20:
        raise HTTPException(404, "Convite não encontrado.")
    m = _um(_SERVICO("GET", "escritorio_membros",
                     params={"convite_hash": f"eq.{hash_do_token(token)}",
                             "select": "email,status,convite_expira,projeto_id"}))
    _recusa_se_nao_vale(m)
    p = _um(_SERVICO("GET", "escritorio_projetos", params={"id": f"eq.{m['projeto_id']}", "select": "nome"})) or {}
    admin = _um(_SERVICO("GET", "escritorio_membros",
                         params={"projeto_id": f"eq.{m['projeto_id']}", "papel": "eq.dono", "select": "nome"})) or {}
    return {"projeto": p.get("nome") or "", "convidado_por": admin.get("nome") or "",
            "email": mascarar(m["email"]), "expirado": expirado(m["convite_expira"])}


@router.post("/convite/visto")
def convite_visto(request: Request, corpo: dict):
    """A conta logada chegou na confirmação do convite (ou disse "não sou eu"/"agora não").

    🔒 2ª revisão (24/09): a varredura de e-mails reconhecia o convidado pelo e-mail do convite
    (falha se ele entra com OUTRO) ou por um texto livre do cadastro (qualquer um escreve).
    Aqui é o servidor que grava, com login + token, QUAL conta abriu o convite; enquanto ele
    estiver pendente e no prazo, essa conta não leva a esteira de cliente novo. Só o servidor
    escreve `visto_por` (o banco barra a tela). `dispensar` só desliga o que é da própria conta."""
    eu = _exige_login(request)
    token = str(corpo.get("token") or "")
    if len(token) < 20:
        raise HTTPException(404, "Convite não encontrado.")
    m = _um(_SERVICO("GET", "escritorio_membros",
                     params={"convite_hash": f"eq.{hash_do_token(token)}",
                             "select": "id,projeto_id,status,convite_expira,visto_por"}))
    _recusa_se_nao_vale(m)
    dispensar = bool(corpo.get("dispensar"))
    if dispensar and str(m.get("visto_por") or "") != eu["id"]:
        return {"ok": True, "visto": False}
    if not dispensar and expirado(m["convite_expira"]):
        raise HTTPException(410, "Este convite venceu. Peça um novo a quem te convidou.")
    if not dispensar:
        # a admin conferindo o próprio link (ou quem já está no projeto) não é "quem abriu o convite":
        # sem isto ela saía da esteira dela e APAGAVA a marca do convidado de verdade (3ª revisão, 24/09)
        ja = _um(_SERVICO("GET", "escritorio_membros",
                          params={"projeto_id": f"eq.{m['projeto_id']}", "user_id": f"eq.{eu['id']}",
                                  "status": "eq.ativo", "select": "id"}))
        if ja:
            return {"ok": True, "visto": False}
    params = {"id": f"eq.{m['id']}", "status": "eq.convidado"}
    if dispensar:
        params["visto_por"] = f"eq.{eu['id']}"
    status, _ = _SERVICO("PATCH", "escritorio_membros", body={"visto_por": None if dispensar else eu["id"]},
                         params=params)
    if status >= 300 or status == 0:
        raise HTTPException(502, "O banco não respondeu agora. Tente de novo em instantes.")
    return {"ok": True, "visto": not dispensar}


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
    _recusa_se_nao_vale(m)
    if expirado(m["convite_expira"]):
        raise HTTPException(410, "Este convite venceu. Peça um novo a quem te convidou.")
    ja = _um(_SERVICO("GET", "escritorio_membros",
                      params={"projeto_id": f"eq.{m['projeto_id']}", "user_id": f"eq.{eu['id']}",
                              "status": "eq.ativo", "select": "id"}))
    if ja:
        # a admin conferindo o próprio link (ou quem já está no projeto): não é erro e NÃO gasta o
        # convite — a tela dizia "Este convite já foi usado" com ele valendo (4ª revisão, 24/09)
        return {"ok": True, "ja_membro": True, "projeto_id": m["projeto_id"]}
    # quem SAIU do projeto e volta por um convite novo com OUTRO e-mail: a linha antiga ainda segura
    # o user_id e o índice único (projeto, user) barrava o aceite pra sempre (502) (4ª revisão, 24/09)
    antiga = _um(_SERVICO("GET", "escritorio_membros",
                          params={"projeto_id": f"eq.{m['projeto_id']}", "user_id": f"eq.{eu['id']}",
                                  "status": "eq.removido", "select": "id"}))
    if antiga:
        st_sol, _ = _SERVICO("PATCH", "escritorio_membros", body={"user_id": None},
                             params={"id": f"eq.{antiga['id']}", "status": "eq.removido"})
        if st_sol >= 300 or st_sol == 0:
            raise HTTPException(502, "Não consegui confirmar o convite agora. Tente de novo em instantes.")
    # o hash FICA depois do aceite (status 'ativo' já impede reuso): assim o 2º clique no link
    # sabe dizer "já foi usado" em vez de "trocado ou cancelado" (revisão adversarial 24/09)
    ativar = {"user_id": eu["id"], "status": "ativo",
              "aceito_em": datetime.now(timezone.utc).isoformat()}
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
    if _DEPOIS_DO_ACEITE:          # a pasta do Drive do projeto (em segundo plano: nunca atrasa o aceite)
        try:
            _DEPOIS_DO_ACEITE(m["projeto_id"])
        except Exception:
            pass
    outro_email = (eu.get("email") or "").lower() != (m["email"] or "").lower()
    return {"ok": True, "projeto_id": m["projeto_id"],
            # conta com e-mail diferente do convite: vale (o token prova que o convite chegou
            # a ela), mas a tela avisa — a pasta do Drive vai ser compartilhada com ESTA conta.
            "email_da_conta_diferente": outro_email}
