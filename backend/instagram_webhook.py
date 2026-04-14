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

    # Verificar assinatura (opcional em dev, obrigatorio em prod)
    signature = request.headers.get("X-Hub-Signature-256", "")
    api = MetaGraphAPI()
    if signature and not api.verify_signature(body, signature):
        logger.warning("Assinatura do webhook invalida!")
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
async def create_post(req: PostRequest):
    """Gera conteudo com IA e publica no Instagram.

    Se nenhum topic for fornecido, usa o proximo tema do calendario rotativo.
    """
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
async def toggle_agent(req: ToggleRequest):
    """Liga/desliga o agente ou funcionalidades individuais."""
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
async def list_conversations(limit: int = Query(50, le=100)):
    """Lista conversas recentes."""
    return store.list_conversations(limit)


@router.get("/conversations/{sender_id}")
async def get_conversation(sender_id: str):
    """Retorna historico completo de uma conversa."""
    return store.get_conversation(sender_id)


@router.get("/activity")
async def get_activity(limit: int = Query(50, le=200)):
    """Retorna log de atividade do agente."""
    return store.get_activity_log(limit)


@router.get("/posts")
async def list_posts():
    """Lista posts publicados e agendados."""
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
