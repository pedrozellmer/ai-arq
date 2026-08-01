# -*- coding: utf-8 -*-
"""Endpoints FastAPI para o agente Instagram da AI.arq."""
import os
import json
import time
import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from instagram_api import MetaGraphAPI
from instagram_agent import generate_dm_reply, generate_post_content, get_next_theme
from instagram_image import generate_tip_post, generate_promo_post, generate_stat_post
import instagram_store as store

logger = logging.getLogger("instagram_webhook")

router = APIRouter(prefix="/api/instagram", tags=["Instagram Agent"])


# ══════════════════════════════════════════════════
#  Gate de admin (28/07/2026)
# ══════════════════════════════════════════════════
# Antes disto, TODA rota deste arquivo era aberta: qualquer pessoa publicava
# post, desligava o agente, aprovava a fila e lia as conversas privadas de
# quem manda DM pro perfil. Agora as rotas de escrita e as de leitura de
# conversa exigem o mesmo admin do resto do sistema.
#
# 🪤 Ficam ABERTAS de propósito (quem chama não tem como mandar JWT):
#   - GET/POST /webhook        → a Meta chama
#   - POST /scheduler/tick     → o pg_cron do Supabase chama
#   - GET /image/{filename}    → a Meta baixa a imagem pra publicar
def _admin(request: Request):
    """Exige admin. Import tardio de main pra não criar import circular."""
    from main import _require_admin
    return _require_admin(request)

# ══════════════════════════════════════════════════
#  Webhook — Verificacao (GET)
# ══════════════════════════════════════════════════

@router.get("/webhook")
async def webhook_verify(
    request: Request,
):
    """Verificacao do webhook do Meta (hub.challenge).

    O Meta manda um GET com hub.mode, hub.verify_token e hub.challenge.
    Se o verify_token bater, retornamos hub.challenge.
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    verify_token = os.getenv("META_VERIFY_TOKEN", "")

    if mode == "subscribe" and token == verify_token:
        logger.info("Webhook verificado com sucesso!")
        store.log_activity("webhook_verified")
        return PlainTextResponse(content=challenge, status_code=200)

    logger.warning(f"Webhook verificacao falhou: mode={mode}, token={token}")
    raise HTTPException(403, "Verificacao falhou")


# ══════════════════════════════════════════════════
#  Webhook — Receber eventos (POST)
# ══════════════════════════════════════════════════

@router.post("/webhook")
async def webhook_receive(request: Request):
    """Recebe eventos do Instagram (mensagens, etc).

    IMPORTANTE: Deve retornar 200 em menos de 5 segundos,
    senao o Meta tenta de novo e pode desativar o webhook.
    """
    body = await request.body()

    # Verificar assinatura. Se o app secret está configurado (produção), a
    # assinatura é OBRIGATÓRIA. Fix 2026-07-22: antes, um request SEM o header
    # X-Hub-Signature-256 pulava a verificação (bypass trivial).
    signature = request.headers.get("X-Hub-Signature-256", "")
    api = MetaGraphAPI()
    if api.app_secret and not api.verify_signature(body, signature):
        logger.warning("Webhook IG: assinatura ausente ou invalida")
        raise HTTPException(403, "Assinatura invalida")

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "JSON invalido")

    # Processar em background (retornar 200 rapido)
    threading.Thread(
        target=_process_webhook_event,
        args=(data,),
        daemon=True,
    ).start()

    return JSONResponse({"status": "ok"}, status_code=200)


def _process_webhook_event(data: dict):
    """Processa evento do webhook em background thread."""
    try:
        # Estrutura do payload do Instagram Messaging:
        # { "entry": [{ "messaging": [{ "sender": {"id": "..."}, "message": {"mid": "...", "text": "..."} }] }] }
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                _handle_message_event(event)
    except Exception as e:
        logger.error(f"Erro processando webhook: {e}")
        store.log_activity("webhook_error", {"error": str(e)})


def _handle_message_event(event: dict):
    """Processa uma mensagem recebida."""
    config = store.get_config()

    if not config.get("agent_enabled") or not config.get("auto_reply_enabled"):
        logger.info("Agente desativado, ignorando mensagem")
        return

    sender = event.get("sender", {})
    sender_id = sender.get("id", "")
    message = event.get("message", {})
    message_id = message.get("mid", "")
    message_text = message.get("text", "")

    if not sender_id or not message_text:
        return

    # Deduplicacao
    if store.is_message_processed(message_id):
        return
    store.mark_message_processed(message_id)

    # Verificar limite diario
    if config.get("messages_sent_today", 0) >= config.get("max_messages_per_day", 200):
        logger.warning("Limite diario de mensagens atingido")
        store.log_activity("rate_limit_hit", {"type": "messages"})
        return

    # Ignorar mensagens do proprio bot
    ig_user_id = os.getenv("IG_USER_ID", "")
    if sender_id == ig_user_id:
        return

    logger.info(f"Mensagem recebida de {sender_id}: {message_text[:50]}...")

    # Buscar historico da conversa
    history = store.get_conversation(sender_id)

    # Salvar mensagem do usuario
    store.add_message(sender_id, "user", message_text)

    # Gerar resposta com IA
    reply = generate_dm_reply(history, message_text)

    # Enviar resposta via Meta Graph API
    api = MetaGraphAPI()
    result = api.send_message(sender_id, reply)

    if "error" not in result:
        # Salvar resposta do agente
        store.add_message(sender_id, "assistant", reply)

        # Atualizar contadores
        store.update_config(
            messages_sent_today=config.get("messages_sent_today", 0) + 1,
            last_message_at=datetime.now(timezone.utc).isoformat(),
        )

        store.log_activity("dm_replied", {
            "sender_id": sender_id,
            "message_preview": message_text[:50],
            "reply_preview": reply[:50],
        })
        logger.info(f"Resposta enviada para {sender_id}")
    else:
        store.log_activity("dm_error", {
            "sender_id": sender_id,
            "error": str(result.get("error")),
        })
        logger.error(f"Erro enviando resposta: {result}")


# ══════════════════════════════════════════════════
#  Publicacao de posts
# ══════════════════════════════════════════════════

class PostRequest(BaseModel):
    topic: Optional[str] = None
    content_type: Optional[str] = "DICA_ARQUITETURA"
    image_url: Optional[str] = None  # URL publica da imagem (se ja tiver)


@router.post("/post")
async def create_post(req: PostRequest, request: Request):
    """Gera conteudo com IA e publica no Instagram. Admin-only.

    Se nenhum topic for fornecido, usa o proximo tema do calendario rotativo.
    """
    _admin(request)
    config = store.get_config()

    if not config.get("agent_enabled") or not config.get("auto_post_enabled"):
        raise HTTPException(400, "Agente de posts desativado")

    # Verificar limite diario (25 posts/dia no Instagram)
    if config.get("posts_published_today", 0) >= 25:
        raise HTTPException(429, "Limite diario de posts atingido")

    # Determinar tema
    if req.topic:
        topic = req.topic
        content_type = req.content_type or "DICA_ARQUITETURA"
    else:
        # Proximo tema do calendario rotativo
        last_idx = config.get("last_theme_index", -1)
        theme = get_next_theme(last_idx)
        topic = theme["topic"]
        content_type = theme["type"]
        store.update_config(last_theme_index=theme["index"])

    # Gerar conteudo com IA em background
    def _publish():
        try:
            store.log_activity("post_generating", {"topic": topic})

            # 1. Gerar legenda e dados da imagem com Claude
            content = generate_post_content(topic, content_type)

            # 2. Gerar imagem com Pillow
            image_type = content.get("image_type", "tip")
            if image_type == "promo":
                image_path = generate_promo_post(
                    headline=content.get("image_title", topic),
                    subtitle=content.get("image_body", ""),
                )
            elif image_type == "stat":
                image_path = generate_stat_post(
                    stat_number=content.get("image_stat_number", "130+"),
                    stat_label=content.get("image_stat_label", "itens"),
                    description=content.get("image_body", ""),
                )
            else:
                image_path = generate_tip_post(
                    title=content.get("image_title", topic),
                    body=content.get("image_body", ""),
                    category=content_type.replace("_", " ").title(),
                )

            # 3. Montar legenda completa
            caption = content.get("caption", topic)
            hashtags = content.get("hashtags", [])
            if hashtags:
                caption += "\n\n" + " ".join(f"#{h.replace('#','')}" for h in hashtags)

            # 4. Publicar via Meta Graph API
            # Nota: A imagem precisa ser acessivel por URL publica.
            # Vamos servir temporariamente pelo proprio backend.
            image_url = req.image_url
            if not image_url:
                # Servir a imagem localmente — precisa de URL publica do backend
                backend_url = os.getenv("BACKEND_URL", "https://ai-arq.onrender.com")
                filename = os.path.basename(image_path)
                image_url = f"{backend_url}/api/instagram/image/{filename}"

            api = MetaGraphAPI()
            creation_id = api.create_media_container(image_url, caption)

            if not creation_id or "error" in str(creation_id):
                store.log_activity("post_error", {"error": f"Falha ao criar container: {creation_id}"})
                return

            # Esperar container ficar pronto (max 30s)
            for _ in range(6):
                status = api.check_media_status(creation_id)
                if status == "FINISHED":
                    break
                time.sleep(5)

            # Publicar
            media_id = api.publish_media(creation_id)

            store.update_config(
                posts_published_today=config.get("posts_published_today", 0) + 1,
                last_post_at=datetime.now(timezone.utc).isoformat(),
            )

            store.add_scheduled_post({
                "topic": topic,
                "type": content_type,
                "caption_preview": caption[:100],
                "media_id": media_id,
                "status": "published",
                "published_at": datetime.now(timezone.utc).isoformat(),
            })

            store.log_activity("post_published", {
                "topic": topic,
                "media_id": media_id,
            })
            logger.info(f"Post publicado: {topic}")

        except Exception as e:
            logger.error(f"Erro publicando post: {e}")
            store.log_activity("post_error", {"error": str(e), "topic": topic})

    threading.Thread(target=_publish, daemon=True).start()

    return {"status": "generating", "topic": topic, "type": content_type}


# ══════════════════════════════════════════════════
#  Servir imagens geradas (para a Meta Graph API)
# ══════════════════════════════════════════════════

from fastapi.responses import FileResponse
import tempfile

IMAGES_DIR = os.path.join(tempfile.gettempdir(), "aiarq_jobs", "instagram", "images")

@router.get("/image/{filename}")
async def serve_image(filename: str):
    """Serve imagem gerada para que o Instagram possa baixar."""
    filepath = os.path.join(IMAGES_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "Imagem nao encontrada")
    return FileResponse(filepath, media_type="image/jpeg")


# ══════════════════════════════════════════════════
#  Endpoints administrativos
# ══════════════════════════════════════════════════

@router.get("/status")
async def agent_status():
    """Retorna status do agente Instagram."""
    config = store.get_config()
    return {
        "agent_enabled": config.get("agent_enabled", False),
        "auto_reply_enabled": config.get("auto_reply_enabled", False),
        "auto_post_enabled": config.get("auto_post_enabled", False),
        "messages_sent_today": config.get("messages_sent_today", 0),
        "posts_published_today": config.get("posts_published_today", 0),
        "last_message_at": config.get("last_message_at"),
        "last_post_at": config.get("last_post_at"),
        "max_messages_per_day": config.get("max_messages_per_day", 200),
    }


class ToggleRequest(BaseModel):
    agent_enabled: Optional[bool] = None
    auto_reply_enabled: Optional[bool] = None
    auto_post_enabled: Optional[bool] = None


@router.post("/toggle")
async def toggle_agent(req: ToggleRequest, request: Request):
    """Liga/desliga o agente ou funcionalidades individuais. Admin-only."""
    _admin(request)
    updates = {}
    if req.agent_enabled is not None:
        updates["agent_enabled"] = req.agent_enabled
    if req.auto_reply_enabled is not None:
        updates["auto_reply_enabled"] = req.auto_reply_enabled
    if req.auto_post_enabled is not None:
        updates["auto_post_enabled"] = req.auto_post_enabled

    if updates:
        store.update_config(**updates)
        store.log_activity("config_changed", updates)

    return {"status": "ok", **store.get_config()}


@router.get("/conversations")
async def list_conversations(request: Request, limit: int = Query(50, le=100)):
    """Lista conversas recentes. Admin-only — é DM de gente real."""
    _admin(request)
    return store.list_conversations(limit)


@router.get("/conversations/{sender_id}")
async def get_conversation(sender_id: str, request: Request):
    """Retorna historico completo de uma conversa. Admin-only."""
    _admin(request)
    return store.get_conversation(sender_id)


@router.get("/activity")
async def get_activity(request: Request, limit: int = Query(50, le=200)):
    """Retorna log de atividade do agente. Admin-only."""
    _admin(request)
    return store.get_activity_log(limit)


@router.get("/posts")
async def list_posts(request: Request):
    """Lista posts publicados e agendados. Admin-only."""
    _admin(request)
    return store.get_scheduled_posts()


# ══════════════════════════════════════════════════
#  Post automatico agendado
# ══════════════════════════════════════════════════

_auto_post_running = False


def start_auto_poster(interval_hours: int = 24):
    """Inicia thread que posta automaticamente a cada N horas.

    Chamado uma vez na inicializacao do app.
    """
    global _auto_post_running
    if _auto_post_running:
        return
    _auto_post_running = True

    def _loop():
        while _auto_post_running:
            try:
                config = store.get_config()
                if config.get("agent_enabled") and config.get("auto_post_enabled"):
                    # Verificar se ja postou recentemente
                    last_post = config.get("last_post_at")
                    should_post = True

                    if last_post:
                        from datetime import datetime, timezone
                        try:
                            last_dt = datetime.fromisoformat(last_post)
                            hours_since = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
                            interval = config.get("post_interval_hours", 24)
                            if hours_since < interval:
                                should_post = False
                        except Exception:
                            pass

                    if should_post:
                        logger.info("Auto-poster: gerando novo post...")
                        last_idx = config.get("last_theme_index", -1)
                        theme = get_next_theme(last_idx)

                        # Importar funcao de post aqui para evitar circular
                        from instagram_agent import generate_post_content
                        content = generate_post_content(theme["topic"], theme["type"])

                        # Gerar imagem
                        image_type = content.get("image_type", "tip")
                        if image_type == "promo":
                            image_path = generate_promo_post(
                                headline=content.get("image_title", theme["topic"]),
                                subtitle=content.get("image_body", ""),
                            )
                        elif image_type == "stat":
                            image_path = generate_stat_post(
                                stat_number=content.get("image_stat_number", "130+"),
                                stat_label=content.get("image_stat_label", "itens"),
                                description=content.get("image_body", ""),
                            )
                        else:
                            image_path = generate_tip_post(
                                title=content.get("image_title", theme["topic"]),
                                body=content.get("image_body", ""),
                                category=theme["type"].replace("_", " ").title(),
                            )

                        # Montar legenda
                        caption = content.get("caption", theme["topic"])
                        hashtags = content.get("hashtags", [])
                        if hashtags:
                            caption += "\n\n" + " ".join(f"#{h.replace('#','')}" for h in hashtags)

                        # Publicar
                        backend_url = os.getenv("BACKEND_URL", "https://ai-arq.onrender.com")
                        filename = os.path.basename(image_path)
                        image_url = f"{backend_url}/api/instagram/image/{filename}"

                        api = MetaGraphAPI()
                        creation_id = api.create_media_container(image_url, caption)

                        if creation_id and "error" not in str(creation_id):
                            for _ in range(6):
                                status = api.check_media_status(creation_id)
                                if status == "FINISHED":
                                    break
                                time.sleep(5)

                            media_id = api.publish_media(creation_id)

                            store.update_config(
                                posts_published_today=config.get("posts_published_today", 0) + 1,
                                last_post_at=datetime.now(timezone.utc).isoformat(),
                                last_theme_index=theme["index"],
                            )

                            store.add_scheduled_post({
                                "topic": theme["topic"],
                                "type": theme["type"],
                                "caption_preview": caption[:100],
                                "media_id": media_id,
                                "status": "published",
                                "published_at": datetime.now(timezone.utc).isoformat(),
                            })

                            store.log_activity("auto_post_published", {
                                "topic": theme["topic"],
                                "media_id": media_id,
                            })
                            logger.info(f"Auto-post publicado: {theme['topic']}")
                        else:
                            store.log_activity("auto_post_error", {
                                "error": f"Container creation failed: {creation_id}",
                            })

            except Exception as e:
                logger.error(f"Auto-poster erro: {e}")
                store.log_activity("auto_post_error", {"error": str(e)})

            # Dormir 1 hora e verificar de novo
            time.sleep(3600)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    logger.info("Auto-poster iniciado")


# ══════════════════════════════════════════════════
#  Agendador de posts (scheduler)
#  Lê instagram_scheduled_posts no Supabase e publica posts cujo
#  publish_at <= now() e status='pending'.
# ══════════════════════════════════════════════════

import urllib.request
import urllib.parse


def _supa_select(table: str, query: str) -> list:
    """Helper: SELECT direto via REST API do Supabase."""
    url = f"{os.getenv('SUPABASE_URL', 'https://kqjabzwgbfuivzlcfvvu.supabase.co')}/rest/v1/{table}?{query}"
    # service_role: o scheduler é backend puro (server-side no Render). Com a
    # chave anon ele dependia da policy pública de instagram_scheduled_posts —
    # que era um buraco (qualquer um agendava/publicava). (auditoria 2026-07-13)
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
    req = urllib.request.Request(url, method="GET")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"_supa_select erro: {e}")
        return []


def _supa_upsert(table: str, data: dict, on_conflict: str) -> bool:
    """Helper: UPSERT via REST API (insere ou atualiza por on_conflict)."""
    url = f"{os.getenv('SUPABASE_URL', 'https://kqjabzwgbfuivzlcfvvu.supabase.co')}/rest/v1/{table}?on_conflict={on_conflict}"
    # service_role: o scheduler é backend puro (server-side no Render). Com a
    # chave anon ele dependia da policy pública de instagram_scheduled_posts —
    # que era um buraco (qualquer um agendava/publicava). (auditoria 2026-07-13)
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "resolution=merge-duplicates,return=minimal")
    try:
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception as e:
        logger.error(f"_supa_upsert erro: {e}")
        return False


def _supa_update(table: str, match_field: str, match_value: str, data: dict) -> bool:
    """Helper: PATCH via REST API."""
    url = f"{os.getenv('SUPABASE_URL', 'https://kqjabzwgbfuivzlcfvvu.supabase.co')}/rest/v1/{table}?{match_field}=eq.{urllib.parse.quote(match_value)}"
    # service_role: o scheduler é backend puro (server-side no Render). Com a
    # chave anon ele dependia da policy pública de instagram_scheduled_posts —
    # que era um buraco (qualquer um agendava/publicava). (auditoria 2026-07-13)
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="PATCH")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    try:
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception as e:
        logger.error(f"_supa_update erro: {e}")
        return False


@router.post("/scheduler/tick")
async def scheduler_tick(request: Request, force_slot: Optional[str] = None):
    """Roda 1 ciclo do agendador.

    - Busca posts em 'pending' onde publish_at <= now() (ou força um slot específico via ?force_slot=dia1)
    - Pra cada um: publica via Meta API, atualiza status
    - Chamado pelo pg_cron (que envia X-Tick-Secret desde 01/08)

    Gate da auditoria 01/08/2026: era POST público — qualquer um podia disparar
    o ciclo, e force_slot publicava post agendado ANTES da data. Retrocompatível:
    sem TICK_SECRET no ambiente, segue aberto.
    """
    _tick = os.getenv("TICK_SECRET", "")
    if _tick and request.headers.get("X-Tick-Secret", "") != _tick:
        raise HTTPException(401, "Tick não autorizado")
    api = MetaGraphAPI()
    if not api.access_token or not api.ig_user_id:
        return {"ok": False, "error": "META_ACCESS_TOKEN ou IG_USER_ID não configurados"}

    # Busca posts pendentes
    if force_slot:
        query = f"slot_key=eq.{force_slot}&status=eq.pending&select=*"
    else:
        # publish_at <= now() (urlencoded)
        now_iso = datetime.now(timezone.utc).isoformat()
        query = f"status=eq.pending&publish_at=lte.{urllib.parse.quote(now_iso)}&select=*&order=publish_at.asc"

    pending = _supa_select("instagram_scheduled_posts", query)

    if not pending:
        return {"ok": True, "message": "Nada pra publicar agora", "checked_at": datetime.now(timezone.utc).isoformat()}

    results = []
    for post in pending[:3]:  # max 3 por tick pra evitar rate limit
        slot = post["slot_key"]
        try:
            # marca como 'publishing' pra evitar race
            _supa_update("instagram_scheduled_posts", "id", post["id"], {
                "status": "publishing",
                "attempts": (post.get("attempts") or 0) + 1,
            })

            # Cria container de mídia conforme media_type
            media_type = post.get("media_type") or "feed"
            if media_type == "reel":
                creation_id = api.create_reel_container(
                    video_url=post.get("video_url") or "",
                    caption=post["caption"],
                    thumbnail_url=post.get("thumbnail_url"),
                    share_to_feed=True,
                )
            elif media_type == "story":
                creation_id = api.create_story_container(
                    image_url=post["image_url"],
                )
            elif media_type == "carousel":
                # Carrossel: cria 1 item container por imagem, depois parent CAROUSEL
                image_urls = post.get("image_urls") or []
                if isinstance(image_urls, str):
                    try:
                        image_urls = json.loads(image_urls)
                    except Exception:
                        image_urls = []
                if not image_urls or len(image_urls) < 2:
                    _supa_update("instagram_scheduled_posts", "id", post["id"], {
                        "status": "failed",
                        "error_message": "Carrossel precisa de 2+ imagens em image_urls",
                    })
                    results.append({"slot": slot, "status": "failed", "error": "no_images"})
                    continue
                # cria todos os filhos
                children_ids = []
                child_error = None
                for url in image_urls[:10]:
                    cid = api.create_carousel_item(image_url=url)
                    if not cid or "error" in str(cid).lower():
                        child_error = f"item falhou: {cid}"
                        break
                    children_ids.append(cid)
                if child_error or not children_ids:
                    _supa_update("instagram_scheduled_posts", "id", post["id"], {
                        "status": "failed",
                        "error_message": child_error or "nenhum item criado",
                    })
                    results.append({"slot": slot, "status": "failed", "error": child_error})
                    continue
                # cria parent
                creation_id = api.create_carousel_container(
                    children_ids=children_ids,
                    caption=post["caption"],
                )
            else:  # feed (default)
                creation_id = api.create_media_container(
                    image_url=post["image_url"],
                    caption=post["caption"],
                )

            if not creation_id or "error" in str(creation_id).lower():
                _supa_update("instagram_scheduled_posts", "id", post["id"], {
                    "status": "failed",
                    "error_message": f"Container falhou: {creation_id}",
                })
                results.append({"slot": slot, "status": "failed", "error": "container"})
                continue

            # Aguarda o container FICAR PRONTO antes de publicar. Reel e carousel
            # levam tempo (a Meta processa o vídeo/álbum) — publicar cedo devolve
            # "Publish falhou: None". Antes era sleep fixo de 15s, que não bastava
            # pro reel (bug dos reels 14/07). Agora faz POLLING do status.
            import time
            if media_type in ("reel", "carousel"):
                max_checks = 36 if media_type == "reel" else 12  # ~3min reel / ~1min carousel
                for _ in range(max_checks):
                    time.sleep(5)
                    try:
                        st = api.check_media_status(creation_id)
                    except Exception:
                        st = "UNKNOWN"
                    if st in ("FINISHED", "ERROR"):
                        break
            else:
                time.sleep(3)
            media_id = api.publish_media(creation_id)

            if media_id and "error" not in str(media_id).lower():
                _supa_update("instagram_scheduled_posts", "id", post["id"], {
                    "status": "published",
                    "media_id": str(media_id),
                    "published_at": datetime.now(timezone.utc).isoformat(),
                })
                results.append({"slot": slot, "status": "published", "media_id": str(media_id)})
                store.log_activity("scheduled_post_published", {"slot": slot, "media_id": str(media_id)})
            else:
                _supa_update("instagram_scheduled_posts", "id", post["id"], {
                    "status": "failed",
                    "error_message": f"Publish falhou: {media_id}",
                })
                results.append({"slot": slot, "status": "failed", "error": str(media_id)})

        except Exception as e:
            logger.error(f"scheduler_tick: erro processando {slot}: {e}")
            _supa_update("instagram_scheduled_posts", "id", post["id"], {
                "status": "failed",
                "error_message": str(e)[:500],
            })
            results.append({"slot": slot, "status": "failed", "error": str(e)})

    return {"ok": True, "processed": len(results), "results": results}


@router.get("/scheduler/list")
async def scheduler_list(request: Request):
    """Lista todos os posts agendados com status atual. Admin-only."""
    _admin(request)
    posts = _supa_select(
        "instagram_scheduled_posts",
        "select=slot_key,status,media_type,publish_at,published_at,attempts,error_message,media_id,video_url,image_url&order=publish_at.asc",
    )
    return {"posts": posts, "now": datetime.now(timezone.utc).isoformat()}


@router.post("/insights/sync")
async def insights_sync(request: Request, force: bool = False):
    """Sincroniza insights (likes/reach/saves/etc) dos posts publicados.

    - Cache de 5min: se sincronizou recentemente, retorna do banco direto
    - Use ?force=true pra forçar re-sync ignorando cache

    Admin-only: gasta chamada da Graph API.
    """
    _admin(request)
    # Cache: se synced_at mais recente < 5min, retorna do DB
    if not force:
        recent = _supa_select(
            "instagram_post_insights",
            "select=synced_at&order=synced_at.desc&limit=1",
        )
        if recent and recent[0].get("synced_at"):
            try:
                last = datetime.fromisoformat(recent[0]["synced_at"].replace("Z", "+00:00"))
                age_sec = (datetime.now(timezone.utc) - last).total_seconds()
                if age_sec < 300:
                    cached = _supa_select(
                        "instagram_post_insights",
                        "select=*&order=synced_at.desc",
                    )
                    return {"ok": True, "cached": True, "age_seconds": int(age_sec), "insights": cached}
            except Exception:
                pass

    api = MetaGraphAPI()
    if not api.access_token:
        return {"ok": False, "error": "META_ACCESS_TOKEN não configurado"}

    published = _supa_select(
        "instagram_scheduled_posts",
        "status=eq.published&select=slot_key,media_id,media_type&order=published_at.desc",
    )
    if not published:
        return {"ok": True, "synced": 0, "message": "Nenhum post publicado ainda"}

    synced = 0
    errors = []
    for post in published:
        media_id = post.get("media_id")
        slot_key = post.get("slot_key")
        if not media_id:
            continue
        media_type = post.get("media_type") or "feed"
        insights = api.get_media_insights(media_id, media_type=media_type)
        if "error" in insights:
            errors.append({
                "slot": slot_key,
                "media_type": media_type,
                "error": str(insights.get("error"))[:120],
                "details": str(insights.get("details", ""))[:300],
            })
            continue
        row = {
            "media_id": media_id,
            "slot_key": slot_key,
            "reach": insights.get("reach", 0),
            "likes": insights.get("likes", 0),
            "comments": insights.get("comments", 0),
            "saves": insights.get("saved", 0),
            "shares": insights.get("shares", 0),
            "total_interactions": insights.get("total_interactions", 0),
            "views": insights.get("views", 0) or insights.get("plays", 0),
            "profile_visits": insights.get("profile_visits", 0),
            "follows": insights.get("follows", 0),
            "raw_data": insights,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        if _supa_upsert("instagram_post_insights", row, "media_id"):
            synced += 1
        else:
            errors.append({"slot": slot_key, "error": "upsert failed"})

    fresh = _supa_select(
        "instagram_post_insights",
        "select=*&order=synced_at.desc",
    )
    return {"ok": True, "synced": synced, "errors": errors, "insights": fresh}


@router.get("/insights/list")
async def insights_list(request: Request):
    """Retorna últimos insights salvos no banco (não chama Graph API). Admin-only."""
    _admin(request)
    rows = _supa_select(
        "instagram_post_insights",
        "select=*&order=synced_at.desc",
    )
    return {"insights": rows, "count": len(rows)}


@router.post("/scheduler/approve")
async def scheduler_approve(slot_key: str, request: Request, action: str = "approve"):
    """Aprova ou rejeita post em pending_approval (geralmente Reel). Admin-only.

    action='approve' -> status vira 'pending' (tick vai publicar)
    action='reject'  -> status vira 'canceled'
    """
    _admin(request)
    if action not in ("approve", "reject"):
        return {"ok": False, "error": "action deve ser 'approve' ou 'reject'"}

    posts = _supa_select(
        "instagram_scheduled_posts",
        f"slot_key=eq.{urllib.parse.quote(slot_key)}&select=*",
    )
    if not posts:
        return {"ok": False, "error": f"slot {slot_key} não encontrado"}

    post = posts[0]
    if post["status"] not in ("pending_approval",):
        return {
            "ok": False,
            "error": f"slot está com status '{post['status']}' (esperado pending_approval)",
        }

    new_status = "pending" if action == "approve" else "canceled"
    _supa_update("instagram_scheduled_posts", "id", post["id"], {"status": new_status})

    return {
        "ok": True,
        "slot_key": slot_key,
        "previous_status": "pending_approval",
        "new_status": new_status,
    }
