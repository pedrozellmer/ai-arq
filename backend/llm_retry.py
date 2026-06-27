# -*- coding: utf-8 -*-
"""Wrapper com retry + backoff exponencial pra chamadas Claude.

Problema: rate limit (429), overloaded (529) e timeouts da Anthropic API
vinham fazendo a análise de uma prancha falhar silenciosamente (retornava
items=[]), sem retry. Um projeto de 20 pranchas podia perder 3-4 pranchas
por rate limit burst durante `analyze_all_sheets`.

Este módulo concentra o retry em um lugar só. Todos os pontos que hoje
chamam `client.messages.create(...)` devem usar `call_with_retry(client, ...)`
pra herdar o comportamento.

Política:
- 429 / 529 / timeout: retry com backoff exponencial (2s, 4s, 8s, 16s, 32s,
  64s, 90s, 90s) — cobre ~5min de sobrecarga (529 "overloaded" da Anthropic
  costuma durar minutos; cobertura curta fazia o projeto inteiro falhar e o
  usuário re-subir na mão. Caso ivaldogss 16/06: só funcionou na 4ª tentativa
  manual em ~5min — agora a 1ª já aguenta).
- Outros erros: não retenta (erro de prompt, API key inválida, etc).
- Máximo 8 tentativas por padrão.
- Respeita o header `retry-after` quando presente.

Observação sobre Anthropic SDK:
- A exceção `anthropic.RateLimitError` tem status_code=429.
- A exceção `anthropic.APIStatusError` cobre 5xx incluindo 529 (overloaded).
- `anthropic.APITimeoutError` / `anthropic.APIConnectionError` cobrem rede.
"""
import time
import random
from typing import Any

try:
    import anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False


def _is_retryable(exc: Exception) -> bool:
    """True se a exceção é transitória e vale retentar."""
    if not _HAS_ANTHROPIC:
        return False

    # Rate limit clássico
    if isinstance(exc, anthropic.RateLimitError):
        return True

    # APIStatusError: verificar status_code
    if isinstance(exc, anthropic.APIStatusError):
        status = getattr(exc, "status_code", None)
        # 429 (rate limit, caso não venha como RateLimitError)
        # 529 (Anthropic overloaded)
        # 5xx em geral — tentar de novo uma vez, pode ser blip
        if status in (429, 529) or (isinstance(status, int) and 500 <= status < 600):
            return True

    # Timeouts e problemas de conexão
    if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
        return True

    # Fallback genérico: mensagem contém 429/529/overloaded/rate_limit/timeout
    msg = str(exc).lower()
    if any(tok in msg for tok in ("rate_limit", "rate limit", "429", "529",
                                   "overloaded", "timeout", "timed out")):
        return True

    return False


def _extract_retry_after(exc: Exception) -> float | None:
    """Se a API mandou um Retry-After em segundos, respeitar."""
    try:
        resp = getattr(exc, "response", None)
        if resp is None:
            return None
        headers = getattr(resp, "headers", {})
        if not headers:
            return None
        ra = headers.get("retry-after") or headers.get("Retry-After")
        if ra is None:
            return None
        # pode vir como segundos (int) ou HTTP date — só tratamos o int case
        return float(ra)
    except Exception:
        return None


def call_with_retry(
    client: Any,
    *,
    max_retries: int = 8,
    base_delay: float = 2.0,
    max_delay: float = 90.0,
    tag: str = "anthropic",
    **kwargs: Any,
) -> Any:
    """Wrapper em torno de `client.messages.create(**kwargs)` com retry.

    Args:
        client: instância de `anthropic.Anthropic`.
        max_retries: tentativas adicionais além da 1ª (default 8 → até 9 chamadas).
        base_delay: delay inicial em segundos (dobra a cada tentativa).
        max_delay: teto do backoff.
        tag: string pra log identificar qual chamada tá retentando.
        **kwargs: passados direto pra `messages.create`.

    Returns:
        O mesmo objeto retornado por `client.messages.create(...)`.

    Raises:
        A última exceção, se todas as tentativas falharem.
    """
    last_exc: Exception | None = None
    delay = base_delay

    for attempt in range(max_retries + 1):
        try:
            return client.messages.create(**kwargs)
        except Exception as e:
            last_exc = e

            if not _is_retryable(e) or attempt >= max_retries:
                # Não é transitório, ou esgotou: propaga
                raise

            # Respeitar Retry-After se veio
            sleep_for = _extract_retry_after(e) or delay
            # jitter pra não sincronizar retries em paralelo
            sleep_for = min(max_delay, sleep_for) + random.uniform(0, 0.5)

            status = getattr(e, "status_code", "?")
            print(f"[llm_retry:{tag}] tentativa {attempt + 1}/{max_retries + 1} "
                  f"falhou ({type(e).__name__} status={status}); "
                  f"dormindo {sleep_for:.1f}s antes de retentar")

            time.sleep(sleep_for)
            delay = min(max_delay, delay * 2)

    # Não deveria chegar aqui, mas por segurança
    if last_exc:
        raise last_exc
    raise RuntimeError("call_with_retry: loop terminou sem exception nem retorno")


def call_with_retry_stream(
    client: Any,
    *,
    max_retries: int = 8,
    base_delay: float = 2.0,
    max_delay: float = 90.0,
    tag: str = "anthropic-stream",
    **kwargs: Any,
) -> Any:
    """Igual a call_with_retry, mas via STREAMING (client.messages.stream).

    Por quê: chamada NÃO-streaming com max_tokens alto (ex.: 16000) numa planta
    grande gera uma resposta longa que estoura o timeout da requisição — o erro
    vinha mascarado como "IA sobrecarregada" (timeout é retryable, então tentava
    ~5min e desistia, sempre). Streaming mantém a conexão viva recebendo a
    resposta aos poucos, então não estoura timeout em geração longa.

    Retorna o Message FINAL (mesmo formato de messages.create — .content[0].text).
    """
    last_exc: Exception | None = None
    delay = base_delay

    for attempt in range(max_retries + 1):
        try:
            with client.messages.stream(**kwargs) as stream:
                return stream.get_final_message()
        except Exception as e:
            last_exc = e

            if not _is_retryable(e) or attempt >= max_retries:
                raise

            sleep_for = _extract_retry_after(e) or delay
            sleep_for = min(max_delay, sleep_for) + random.uniform(0, 0.5)

            status = getattr(e, "status_code", "?")
            print(f"[llm_retry_stream:{tag}] tentativa {attempt + 1}/{max_retries + 1} "
                  f"falhou ({type(e).__name__} status={status}); "
                  f"dormindo {sleep_for:.1f}s antes de retentar")

            time.sleep(sleep_for)
            delay = min(max_delay, delay * 2)

    if last_exc:
        raise last_exc
    raise RuntimeError("call_with_retry_stream: loop terminou sem exception nem retorno")
