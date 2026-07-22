# -*- coding: utf-8 -*-
"""WhatsApp Business Platform (Cloud API oficial da Meta) — envio de notificação
transacional + webhook. Espelha o padrão do email (_send_email_smtp) e do webhook
do Instagram (mesma Graph API, mesmo esquema de assinatura X-Hub-Signature-256).

DORMENTE por design: sem as env vars (WHATSAPP_TOKEN + WHATSAPP_PHONE_ID) a função
de envio só loga "não configurado" e devolve False — NÃO quebra nada. Ligar é só
setar as env no Render depois que os templates forem aprovados.

Env vars:
  WHATSAPP_TOKEN         Bearer token (System User de longa duração — não o de teste)
  WHATSAPP_PHONE_ID      Phone Number ID do número dedicado na Cloud API
  WHATSAPP_VERIFY_TOKEN  token de verificação do webhook (fallback: META_VERIFY_TOKEN)
  WHATSAPP_APP_SECRET    app secret p/ validar assinatura (fallback: META_APP_SECRET)

Regra dura: só trafega o número do ARQUITETO (dono da conta) e o nome do projeto —
NUNCA o conteúdo do CAD do cliente final dele (AI.arq é operador — ver CLAUDE.md).
"""
import os
import json
import hmac
import hashlib
import logging
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse

logger = logging.getLogger("whatsapp_notify")

router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp"])

_GRAPH_VER = "v21.0"


# ── helpers de ambiente ────────────────────────────────────────────────
def _env(*names, default=""):
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return default


def is_configured() -> bool:
    """True só quando o número + token estão setados (senão fica dormente)."""
    return bool(os.getenv("WHATSAPP_TOKEN") and os.getenv("WHATSAPP_PHONE_ID"))


def _normalize_phone_br(raw: str) -> str:
    """Normaliza pra E.164 sem o '+' (formato que a Cloud API espera), ex.:
    '(21) 98207-9721' -> '5521982079721'. Best-effort pra número brasileiro."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("55") and len(digits) in (12, 13):
        return digits                 # já tem código do país
    if len(digits) in (10, 11):       # DDD + número, sem país
        return "55" + digits
    return digits                     # deixa como veio (best-effort)


# ── log em whatsapp_sent_log (Supabase REST, service_role) ─────────────
def _log_send(row: dict):
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        return
    try:
        req = urllib.request.Request(
            f"{url}/rest/v1/whatsapp_sent_log",
            data=json.dumps(row).encode("utf-8"),
            method="POST",
        )
        req.add_header("apikey", key)
        req.add_header("Authorization", f"Bearer {key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Prefer", "return=minimal")
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        logger.warning("[whatsapp] log falhou (não-fatal): %s", e)


# ── ENVIO de template ──────────────────────────────────────────────────
def send_whatsapp_template(to: str, template_name: str, body_params=None,
                           button_url_param: str = None, lang: str = "pt_BR",
                           kind: str = "whatsapp", job_id: str = None) -> bool:
    """Envia um template APROVADO (categoria utility) pro número `to`.

    body_params: lista de strings pros {{1}},{{2}}... do corpo.
    button_url_param: valor dinâmico do botão de URL (ex.: job_id), se o template
      tiver botão de URL dinâmica. Best-effort — NUNCA levanta exceção.
    """
    body_params = body_params or []
    phone = _normalize_phone_br(to)
    if not phone:
        _log_send({"to_phone": to, "template": template_name, "kind": kind,
                   "status": "skip", "error": "telefone vazio/inválido", "job_id": job_id})
        return False
    if not is_configured():
        # Dormente: sem credenciais, não manda nada (e não quebra o fluxo).
        logger.info("[whatsapp] não configurado (sem WHATSAPP_TOKEN/PHONE_ID) — pulando envio de '%s'", template_name)
        _log_send({"to_phone": phone, "template": template_name, "kind": kind,
                   "status": "skip", "error": "WhatsApp não configurado", "job_id": job_id})
        return False

    token = os.getenv("WHATSAPP_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
    components = []
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(p)} for p in body_params],
        })
    if button_url_param is not None:
        components.append({
            "type": "button", "sub_type": "url", "index": "0",
            "parameters": [{"type": "text", "text": str(button_url_param)}],
        })
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {"name": template_name, "language": {"code": lang},
                     **({"components": components} if components else {})},
    }
    try:
        req = urllib.request.Request(
            f"https://graph.facebook.com/{_GRAPH_VER}/{phone_id}/messages",
            data=json.dumps(payload).encode("utf-8"), method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        msg_id = (((data.get("messages") or [{}])[0]) or {}).get("id")
        _log_send({"to_phone": phone, "template": template_name, "kind": kind,
                   "params": {"body": body_params, "button": button_url_param},
                   "status": "sent", "wa_message_id": msg_id, "job_id": job_id})
        logger.info("[whatsapp] '%s' enviado pra %s (id=%s)", template_name, phone, msg_id)
        return True
    except urllib.error.HTTPError as e:
        try:
            err = e.read().decode("utf-8")[:400]
        except Exception:
            err = str(e)
        logger.warning("[whatsapp] HTTP %s ao enviar '%s': %s", e.code, template_name, err)
        _log_send({"to_phone": phone, "template": template_name, "kind": kind,
                   "status": "error", "error": f"HTTP {e.code}: {err}", "job_id": job_id})
        return False
    except Exception as e:
        logger.warning("[whatsapp] erro ao enviar '%s': %s", template_name, e)
        _log_send({"to_phone": phone, "template": template_name, "kind": kind,
                   "status": "error", "error": str(e)[:400], "job_id": job_id})
        return False


# ── WEBHOOK — verificação (GET) ────────────────────────────────────────
@router.get("/webhook")
async def whatsapp_webhook_verify(request: Request):
    """Verificação do webhook (hub.challenge), igual ao do Instagram."""
    p = request.query_params
    mode = p.get("hub.mode")
    token = p.get("hub.verify_token")
    challenge = p.get("hub.challenge")
    verify_token = _env("WHATSAPP_VERIFY_TOKEN", "META_VERIFY_TOKEN")
    if mode == "subscribe" and verify_token and token == verify_token:
        logger.info("[whatsapp] webhook verificado")
        return PlainTextResponse(content=challenge or "", status_code=200)
    logger.warning("[whatsapp] verificação do webhook falhou (mode=%s)", mode)
    raise HTTPException(403, "Verificação falhou")


# ── WEBHOOK — receber eventos (POST) ───────────────────────────────────
def _verify_sig(body: bytes, signature: str) -> bool:
    secret = _env("WHATSAPP_APP_SECRET", "META_APP_SECRET")
    if not secret:
        return True  # sem secret configurado, não bloqueia (dev)
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@router.post("/webhook")
async def whatsapp_webhook_receive(request: Request):
    """Recebe status de entrega (sent/delivered/read/failed) e mensagens. Precisa
    responder 200 rápido (<5s) senão a Meta re-tenta e pode desativar o webhook."""
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    # Se o app secret está configurado (produção), a assinatura é OBRIGATÓRIA.
    # _verify_sig retorna True só quando NÃO há secret (dev). Fix 2026-07-22:
    # antes um request SEM o header pulava a verificação (bypass trivial).
    if not _verify_sig(body, sig):
        logger.warning("[whatsapp] webhook: assinatura ausente ou inválida")
        raise HTTPException(403, "Assinatura inválida")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "JSON inválido")
    threading.Thread(target=_process_wh_event, args=(data,), daemon=True).start()
    return JSONResponse({"status": "ok"}, status_code=200)


def _process_wh_event(data: dict):
    """Loga status de entrega em background (best-effort)."""
    try:
        for entry in data.get("entry", []):
            for ch in entry.get("changes", []):
                val = ch.get("value", {}) or {}
                for st in val.get("statuses", []):
                    _log_send({
                        "to_phone": st.get("recipient_id"),
                        "template": "(status)",
                        "kind": "status",
                        "status": st.get("status"),
                        "wa_message_id": st.get("id"),
                        "error": (st.get("errors") or [{}])[0].get("title") if st.get("errors") else None,
                    })
    except Exception as e:
        logger.warning("[whatsapp] processar webhook falhou: %s", e)
