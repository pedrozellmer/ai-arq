# -*- coding: utf-8 -*-
"""Persistência em JSON para o agente Instagram (mesmo padrão do JobsStore)."""
import os
import json
import tempfile
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("instagram_store")

INSTAGRAM_DIR = os.path.join(tempfile.gettempdir(), "aiarq_jobs", "instagram")
os.makedirs(INSTAGRAM_DIR, exist_ok=True)


def _load_json(filename: str) -> dict | list:
    path = os.path.join(INSTAGRAM_DIR, filename)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_json(filename: str, data):
    path = os.path.join(INSTAGRAM_DIR, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erro salvando {filename}: {e}")


# ══════════════════════════════════════════════════
#  Configuracao do agente
# ══════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "agent_enabled": False,
    "auto_reply_enabled": False,
    "auto_post_enabled": False,
    "post_interval_hours": 24,
    "max_messages_per_day": 200,
    "messages_sent_today": 0,
    "posts_published_today": 0,
    "last_post_at": None,
    "last_message_at": None,
    "token_expires_at": None,
    "counter_reset_date": None,
}


def get_config() -> dict:
    config = _load_json("_config.json")
    if not config:
        config = DEFAULT_CONFIG.copy()
        _save_json("_config.json", config)

    # Reset contadores diarios
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if config.get("counter_reset_date") != today:
        config["messages_sent_today"] = 0
        config["posts_published_today"] = 0
        config["counter_reset_date"] = today
        _save_json("_config.json", config)

    return config


def update_config(**kwargs):
    config = get_config()
    config.update(kwargs)
    _save_json("_config.json", config)


# ══════════════════════════════════════════════════
#  Historico de conversas
# ══════════════════════════════════════════════════

MAX_HISTORY_PER_SENDER = 20


def get_conversation(sender_id: str) -> list[dict]:
    """Retorna historico de mensagens com um sender (ultimas N)."""
    convos = _load_json("_conversations.json")
    return convos.get(sender_id, [])


def add_message(sender_id: str, role: str, text: str):
    """Adiciona mensagem ao historico. role = 'user' ou 'assistant'."""
    convos = _load_json("_conversations.json")
    if sender_id not in convos:
        convos[sender_id] = []

    convos[sender_id].append({
        "role": role,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Manter apenas as ultimas N mensagens
    convos[sender_id] = convos[sender_id][-MAX_HISTORY_PER_SENDER:]
    _save_json("_conversations.json", convos)


def list_conversations(limit: int = 50) -> list[dict]:
    """Lista todas as conversas com ultima mensagem."""
    convos = _load_json("_conversations.json")
    result = []
    for sender_id, msgs in convos.items():
        if msgs:
            last = msgs[-1]
            result.append({
                "sender_id": sender_id,
                "last_message": last["text"][:100],
                "last_role": last["role"],
                "last_at": last["timestamp"],
                "message_count": len(msgs),
            })
    result.sort(key=lambda x: x["last_at"], reverse=True)
    return result[:limit]


# ══════════════════════════════════════════════════
#  Deduplicacao de mensagens
# ══════════════════════════════════════════════════

MAX_PROCESSED_IDS = 5000


def is_message_processed(message_id: str) -> bool:
    ids = _load_json("_processed_ids.json")
    if not isinstance(ids, list):
        ids = []
    return message_id in ids


def mark_message_processed(message_id: str):
    ids = _load_json("_processed_ids.json")
    if not isinstance(ids, list):
        ids = []
    ids.append(message_id)
    # Manter apenas os ultimos N IDs
    ids = ids[-MAX_PROCESSED_IDS:]
    _save_json("_processed_ids.json", ids)


# ══════════════════════════════════════════════════
#  Log de atividade
# ══════════════════════════════════════════════════

MAX_LOG_ENTRIES = 500


def log_activity(action: str, details: Optional[dict] = None):
    """Registra atividade do agente."""
    logs = _load_json("_activity_log.json")
    if not isinstance(logs, list):
        logs = []

    logs.append({
        "action": action,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    logs = logs[-MAX_LOG_ENTRIES:]
    _save_json("_activity_log.json", logs)


def get_activity_log(limit: int = 50) -> list[dict]:
    logs = _load_json("_activity_log.json")
    if not isinstance(logs, list):
        return []
    return list(reversed(logs[-limit:]))


# ══════════════════════════════════════════════════
#  Calendario de conteudo
# ══════════════════════════════════════════════════

def get_scheduled_posts() -> list[dict]:
    posts = _load_json("_content_calendar.json")
    if not isinstance(posts, list):
        return []
    return posts


def add_scheduled_post(post: dict):
    posts = get_scheduled_posts()
    post["created_at"] = datetime.now(timezone.utc).isoformat()
    post["status"] = post.get("status", "scheduled")
    posts.append(post)
    _save_json("_content_calendar.json", posts)


def update_post_status(index: int, status: str, **extra):
    posts = get_scheduled_posts()
    if 0 <= index < len(posts):
        posts[index]["status"] = status
        posts[index].update(extra)
        _save_json("_content_calendar.json", posts)
