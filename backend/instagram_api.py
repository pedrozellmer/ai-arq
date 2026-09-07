# -*- coding: utf-8 -*-
"""Cliente da Meta Graph API para o Instagram."""
import os
import hmac
import hashlib
import logging
import httpx
from typing import Optional

logger = logging.getLogger("instagram_api")

# A versão sai por env var porque VERSÃO DE API TEM PRAZO: pelo changelog da
# Meta a v21.0 é desativada em 21/01/2027. Com a versão cravada no código, a
# descoberta vira "os posts pararam de sair" num sábado; com env var, vira uma
# linha no painel do Render.
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")
GRAPH_API_BASE = f"https://graph.instagram.com/{GRAPH_API_VERSION}"
GRAPH_FB_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Renovação de token não leva versão no caminho e não fica no host do Facebook.
# Ver refresh_long_lived_token().
IG_REFRESH_URL = "https://graph.instagram.com/refresh_access_token"


def _id_ou_erro(resp: dict):
    """Devolve o id do container, ou o MOTIVO da recusa da Meta.

    🚨 Por que existe (13/08/2026): as 6 funções de criar container faziam
    `return resp.get("id")`. Quando a Meta recusa, `_request` devolve
    {"error": ..., "status_code": ..., "details": "<mensagem real da Meta>"} —
    e o `.get("id")` jogava isso fora, virando `None`.

    Resultado prático: 4 posts falharam entre 09/08 e 13/08 e o painel só
    dizia "Container falhou: None" / "item falhou: None". O motivo verdadeiro
    (token expirado? permissão? imagem recusada?) existia na resposta e era
    descartado a um passo de ser gravado.

    Quem chama testa `"error" in str(...)` pra decidir falha, então devolver a
    string do erro mantém esse contrato E leva o motivo pro banco.
    """
    if not isinstance(resp, dict):
        return None
    _id = resp.get("id")
    if _id:
        return _id
    if resp.get("error") or resp.get("details"):
        _det = str(resp.get("details") or resp.get("error") or "")[:300]
        _cod = resp.get("status_code")
        return f"error: HTTP {_cod} — {_det}" if _cod else f"error: {_det}"
    return None


class MetaGraphAPI:
    """Wrapper para a Meta Graph API (Instagram Business)."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        ig_user_id: Optional[str] = None,
        app_secret: Optional[str] = None,
    ):
        # Ordem: argumento explícito → banco → env var.
        #
        # 🚨 O banco entra no meio porque a renovação automática precisa de um
        # lugar durável para guardar o token novo: um processo não altera a
        # própria env var, então sem isto o token renovado morreria no primeiro
        # deploy. A env var continua sendo a semente (primeira execução, e
        # fallback se o banco estiver fora). Ver token_store.py.
        if access_token:
            self.access_token = access_token
        else:
            self.access_token = os.getenv("META_ACCESS_TOKEN", "")
            try:
                from token_store import ler as _ler_token
                do_banco = _ler_token().get("token")
                if do_banco:
                    self.access_token = do_banco
            except Exception as _e:  # noqa: BLE001
                # Banco fora não pode impedir publicação: segue com a env var.
                logger.warning("token_store indisponível, usando env: %s", _e)

        self.ig_user_id = ig_user_id or os.getenv("IG_USER_ID", "")
        self.app_secret = app_secret or os.getenv("META_APP_SECRET", "")
        # Preenchido por refresh_long_lived_token(); quem chama precisa do
        # valor real para gravar a data de expiração certa, em vez de supor 60.
        self.ultimo_expires_in: Optional[int] = None

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
        """Cria container de midia (passo 1 da publicacao). Pra IMAGE/STORIES.

        Args:
            image_url: URL publica da imagem
            caption: Legenda do post
            media_type: IMAGE, CAROUSEL_ALBUM, STORIES
        """
        url = f"{GRAPH_API_BASE}/{self.ig_user_id}/media"
        payload = {
            "image_url": image_url,
            "caption": caption,
        }
        if media_type == "STORIES":
            payload["media_type"] = "STORIES"
            # Stories nao tem caption (ignorada pelo Meta)

        resp = self._request("POST", url, json=payload)
        return _id_ou_erro(resp)

    def create_reel_container(
        self,
        video_url: str,
        caption: str,
        thumbnail_url: Optional[str] = None,
        share_to_feed: bool = True,
    ) -> Optional[str]:
        """Cria container de Reel (MP4 vertical 9:16).

        Args:
            video_url: URL publica do MP4 (deve ser .mp4, max 100MB, 15-90s)
            caption: Legenda do Reel (max 2200 chars)
            thumbnail_url: URL publica da imagem de capa (opcional)
            share_to_feed: Se True, Reel tambem aparece no feed (recomendado)
        """
        url = f"{GRAPH_API_BASE}/{self.ig_user_id}/media"
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],
            "share_to_feed": share_to_feed,
        }
        if thumbnail_url:
            payload["cover_url"] = thumbnail_url

        resp = self._request("POST", url, json=payload)
        return _id_ou_erro(resp)

    def create_carousel_item(
        self,
        image_url: str,
    ) -> Optional[str]:
        """Cria container de item filho de carrossel (passo 1a por item).

        Args:
            image_url: URL pública da imagem do slide
        """
        url = f"{GRAPH_API_BASE}/{self.ig_user_id}/media"
        payload = {
            "image_url": image_url,
            "is_carousel_item": True,
        }
        resp = self._request("POST", url, json=payload)
        return _id_ou_erro(resp)

    def create_carousel_container(
        self,
        children_ids: list[str],
        caption: str,
    ) -> Optional[str]:
        """Cria container parent de carrossel (passo 2 — depois de criar todos os filhos).

        Args:
            children_ids: lista de creation_ids dos itens (até 10)
            caption: legenda do carrossel
        """
        url = f"{GRAPH_API_BASE}/{self.ig_user_id}/media"
        payload = {
            "media_type": "CAROUSEL",
            "caption": caption[:2200],
            "children": ",".join(children_ids),
        }
        resp = self._request("POST", url, json=payload)
        return _id_ou_erro(resp)

    def create_story_container(
        self,
        image_url: str,
    ) -> Optional[str]:
        """Cria container de Story (imagem 1080x1920 vertical 9:16).

        Args:
            image_url: URL publica da imagem (PNG/JPG, max 8MB)
        """
        url = f"{GRAPH_API_BASE}/{self.ig_user_id}/media"
        payload = {
            "image_url": image_url,
            "media_type": "STORIES",
        }
        resp = self._request("POST", url, json=payload)
        return _id_ou_erro(resp)

    def publish_media(self, creation_id: str) -> Optional[str]:
        """Publica o container de midia (passo 2)."""
        url = f"{GRAPH_API_BASE}/{self.ig_user_id}/media_publish"
        payload = {"creation_id": creation_id}
        resp = self._request("POST", url, json=payload)
        return _id_ou_erro(resp)

    def check_media_status(self, creation_id: str) -> str:
        """Verifica status do container (FINISHED, IN_PROGRESS, ERROR)."""
        url = f"{GRAPH_API_BASE}/{creation_id}"
        params = {"fields": "status_code"}
        resp = self._request("GET", url, params=params)
        return resp.get("status_code", "UNKNOWN")

    # ── Insights ──
    def get_media_insights(self, media_id: str, media_type: str = "feed", metrics: Optional[list[str]] = None) -> dict:
        """Busca insights de um post publicado (likes, reach, saves, etc).

        Args:
            media_id: ID retornado por publish_media
            media_type: feed | reel | story (define quais métricas são válidas)
            metrics: lista explícita (sobrescreve default por tipo)

        Returns:
            dict com {metric_name: value, ...} ou {"error": "...", "details": "..."}
        """
        if not metrics:
            if media_type == "reel":
                metrics = ["reach", "likes", "comments", "saved", "shares", "total_interactions", "views", "plays"]
            elif media_type == "story":
                metrics = ["reach", "replies", "shares", "total_interactions"]
            else:  # feed (IMAGE/CAROUSEL)
                metrics = ["reach", "likes", "comments", "saved", "shares", "total_interactions", "follows", "profile_visits"]
        url = f"{GRAPH_API_BASE}/{media_id}/insights"
        params = {"metric": ",".join(metrics)}
        resp = self._request("GET", url, params=params)
        if "error" in resp:
            return resp
        out = {}
        for m in resp.get("data", []):
            name = m.get("name")
            values = m.get("values") or []
            if values:
                out[name] = values[0].get("value", 0)
        return out

    # ── Token ──
    def refresh_long_lived_token(self) -> Optional[str]:
        """Renova o token de longa duração. Devolve o novo token, ou None.

        🚨 CORRIGIDO EM 06/09/2026. A versão anterior nunca funcionou, por dois
        motivos independentes:

        1. Chamava `graph.facebook.com/<versão>/oauth/access_token` com
           `grant_type=fb_exchange_token` — o fluxo do FACEBOOK Login. Este
           cliente publica em `graph.instagram.com`, ou seja, usa Instagram
           Login, cujo endpoint de renovação é outro e não leva versão no
           caminho.
        2. Passava `client_id=os.getenv("META_APP_ID")`, e META_APP_ID não
           existe no .env deste projeto. A chamada saía com client_id vazio.

        Verificado contra a API real, com token inválido de propósito:
            endpoint antigo → 400 "Missing client_id parameter"  (nem chega ao token)
            endpoint novo   → 400 "Invalid OAuth access token"   (valida o token)

        A função falhava na primeira checagem de parâmetro, sempre.

        ⚠ E ela NUNCA ERA CHAMADA: não há cron nem endpoint que a invoque neste
        backend. Corrigir o código não basta — sem alguém chamando, o token
        continua sem renovação automática. Ver `token_status.py`.

        Regras oficiais do fluxo Instagram Login:
        - só renova token com pelo menos 24h de vida e ainda não expirado;
        - o renovado vale 60 dias A PARTIR DA RENOVAÇÃO;
        - passados 60 dias sem renovar, morre em definitivo e só um novo
          Business Login manual recupera. Daí renovar a cada ~30 dias.
        """
        # `_request` já injeta o access_token nos params.
        resp = self._request("GET", IG_REFRESH_URL,
                             params={"grant_type": "ig_refresh_token"})
        new_token = resp.get("access_token")
        if new_token:
            self.access_token = new_token
            segundos = resp.get("expires_in")
            self.ultimo_expires_in = int(segundos) if segundos else None
            if segundos:
                logger.info("Token renovado — expira em %s dias (%ss)",
                            int(segundos) // 86400, segundos)
            else:
                logger.info("Token renovado com sucesso")
        else:
            logger.error("Falha ao renovar token: %s", resp)
        return new_token

    def token_valido(self) -> bool:
        """O token atual ainda funciona? Não gasta uma renovação para responder.

        Existe para o diagnóstico: `refresh` só pode ser chamado em token vivo,
        então perguntar "está vivo?" antes evita transformar uma checagem numa
        renovação desnecessária.
        """
        resp = self._request("GET", f"{GRAPH_API_BASE}/me",
                             params={"fields": "id,username"})
        return bool(isinstance(resp, dict) and resp.get("id"))

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
                    return {"error": str(e), "status_code": e.response.status_code, "details": e.response.text[:500]}
            except Exception as e:
                logger.error(f"Meta API request falhou: {e}")
                if attempt == 2:
                    return {"error": str(e)}

        return {"error": "Max retries exceeded"}
