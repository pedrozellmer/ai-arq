# -*- coding: utf-8 -*-
"""Cliente da Meta Graph API para o Instagram."""
import os
import hmac
import hashlib
import logging
import httpx
from typing import Optional

logger = logging.getLogger("instagram_api")

GRAPH_API_BASE = "https://graph.instagram.com/v21.0"
GRAPH_FB_BASE = "https://graph.facebook.com/v21.0"


class MetaGraphAPI:
    """Wrapper para a Meta Graph API (Instagram Business)."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        ig_user_id: Optional[str] = None,
        app_secret: Optional[str] = None,
    ):
        self.access_token = access_token or os.getenv("META_ACCESS_TOKEN", "")
        self.ig_user_id = ig_user_id or os.getenv("IG_USER_ID", "")
        self.app_secret = app_secret or os.getenv("META_APP_SECRET", "")

    # ── Verificacao de assinatura do webhook ──
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verifica X-Hub-Signature-256 do webhook."""
        if not self.app_secret or not signature:
            return False
        expected = "sha256=" + hmac.new(
            self.app_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    # ── Mensagens (DMs) ──
    def send_message(self, recipient_id: str, text: str) -> dict:
        """Envia mensagem direta para um usuario do Instagram."""
        url = f"{GRAPH_API_BASE}/me/messages"
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": text[:1000]},  # limite do Instagram
        }
        return self._request("POST", url, json=payload)

    def get_conversations(self, limit: int = 20) -> list[dict]:
        """Lista conversas recentes."""
        url = f"{GRAPH_API_BASE}/{self.ig_user_id}/conversations"
        params = {"limit": limit, "fields": "participants,updated_time"}
        resp = self._request("GET", url, params=params)
        return resp.get("data", [])

    def get_messages(self, conversation_id: str, limit: int = 20) -> list[dict]:
        """Busca mensagens de uma conversa."""
        url = f"{GRAPH_API_BASE}/{conversation_id}"
        params = {"fields": f"messages.limit({limit}){{message,from,created_time}}"}
        resp = self._request("GET", url, params=params)
        msgs = resp.get("messages", {}).get("data", [])
        return msgs

    # ── Publicacao de conteudo ──
    def create_media_container(
        self,
        image_url: str,
        caption: str,
        media_type: str = "IMAGE",
    ) -> Optional[str]:
        """Cria container de midia (passo 1 da publicacao).

        Args:
            image_url: URL publica da imagem
            caption: Legenda do post
            media_type: IMAGE, CAROUSEL_ALBUM, STORIES, REELS
        """
        url = f"{GRAPH_API_BASE}/{self.ig_user_id}/media"
        payload = {
            "image_url": image_url,
            "caption": caption,
        }
        if media_type == "STORIES":
            payload["media_type"] = "STORIES"

        resp = self._request("POST", url, json=payload)
        return resp.get("id")

    def publish_media(self, creation_id: str) -> Optional[str]:
        """Publica o container de midia (passo 2)."""
        url = f"{GRAPH_API_BASE}/{self.ig_user_id}/media_publish"
        payload = {"creation_id": creation_id}
        resp = self._request("POST", url, json=payload)
        return resp.get("id")

    def check_media_status(self, creation_id: str) -> str:
        """Verifica status do container (FINISHED, IN_PROGRESS, ERROR)."""
        url = f"{GRAPH_API_BASE}/{creation_id}"
        params = {"fields": "status_code"}
        resp = self._request("GET", url, params=params)
        return resp.get("status_code", "UNKNOWN")

    # ── Token ──
    def refresh_long_lived_token(self) -> Optional[str]:
        """Renova token de longa duracao (valido por 60 dias)."""
        url = f"{GRAPH_FB_BASE}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": os.getenv("META_APP_ID", ""),
            "client_secret": self.app_secret,
            "fb_exchange_token": self.access_token,
        }
        resp = self._request("GET", url, params=params)
        new_token = resp.get("access_token")
        if new_token:
            self.access_token = new_token
            logger.info("Token renovado com sucesso")
        return new_token

    # ── Request interno ──
    def _request(self, method: str, url: str, **kwargs) -> dict:
        """Faz request HTTP com token de acesso e retry."""
        params = kwargs.pop("params", {})
        params["access_token"] = self.access_token

        for attempt in range(3):
            try:
                with httpx.Client(timeout=30) as client:
                    resp = client.request(method, url, params=params, **kwargs)

                if resp.status_code == 429:
                    # Rate limit — esperar e tentar de novo
                    import time
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"Rate limit atingido, esperando {wait}s...")
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                return resp.json()

            except httpx.HTTPStatusError as e:
                logger.error(f"Meta API erro {e.response.status_code}: {e.response.text}")
                if attempt == 2:
                    return {"error": str(e), "status_code": e.response.status_code}
            except Exception as e:
                logger.error(f"Meta API request falhou: {e}")
                if attempt == 2:
                    return {"error": str(e)}

        return {"error": "Max retries exceeded"}
