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
import os
import time
import random
from typing import Any

try:
    import anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False


def _clean_str(s: str) -> str:
    """Remove surrogates soltos / bytes não-codificáveis em UTF-8. Fast-path:
    string sã volta intacta. CAD brasileiro às vezes tem MTEXT com surrogate
    órfão (lixo de encoding) → a API responde 400 'invalid high surrogate' e o
    job inteiro morre disfarçado de 'IA sobrecarregada' (caso Rodrigo 19/07)."""
    try:
        s.encode("utf-8")
        return s
    except UnicodeEncodeError:
        return s.encode("utf-8", "ignore").decode("utf-8", "ignore")


def _scrub_payload(kwargs: dict) -> dict:
    """Limpa recursivamente todo texto de messages/system antes do envio.
    Imagens (base64 ascii) passam pelo fast-path sem alteração."""
    def _walk(obj):
        if isinstance(obj, str):
            return _clean_str(obj)
        if isinstance(obj, list):
            return [_walk(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        return obj
    for _k in ("messages", "system"):
        if _k in kwargs:
            kwargs[_k] = _walk(kwargs[_k])
    return kwargs


# ── Prompt caching (economia de custo) ──────────────────────────────────────
# Marca o system prompt como cacheável ("ephemeral", TTL ~5min). Quando o MESMO
# system se repete em chamadas próximas (ex.: SYSTEM_PROMPT da leitura de prancha,
# reusado em TODA prancha do projeto), a Anthropic cobra os tokens do prefixo
# cacheado ~90% mais barato na leitura. Ligado só onde o prefixo é grande E
# estático (ver cache_system nos call sites). Provado 23/07: cache_read confirmado.
# Header beta é necessário no anthropic==0.40.0 (pinado no Render) e inócuo em
# versões novas onde caching já é GA.
_PROMPT_CACHE_BETA = "prompt-caching-2024-07-31"


def _apply_system_cache(kwargs: dict) -> dict:
    """Torna o system prompt cacheável. Idempotente e seguro:
    - system string  → vira 1 bloco de texto com cache_control.
    - system já-lista → põe cache_control no ÚLTIMO bloco (fim do prefixo).
    - sem system      → não faz nada (nem adiciona header).
    Se o prefixo for menor que o mínimo do modelo (1024 tok Sonnet/Opus, 2048
    Haiku), a API só IGNORA o marcador — sem erro e sem cobrança extra.

    Kill switch: env LLM_PROMPT_CACHE=0 desliga tudo (no-op) sem deploy — rede
    de segurança pro caminho que gera a planilha, caso o cache dê problema."""
    if os.environ.get("LLM_PROMPT_CACHE", "1") == "0":
        return kwargs
    sysv = kwargs.get("system")
    if isinstance(sysv, str) and sysv.strip():
        kwargs["system"] = [{
            "type": "text",
            "text": sysv,
            "cache_control": {"type": "ephemeral"},
        }]
    elif isinstance(sysv, list) and sysv:
        last = sysv[-1]
        if isinstance(last, dict) and "cache_control" not in last:
            sysv[-1] = {**last, "cache_control": {"type": "ephemeral"}}
    else:
        return kwargs  # nada a cachear → não mexe no header
    # header beta sem clobberar um anthropic-beta já existente
    hdrs = dict(kwargs.get("extra_headers") or {})
    existing = hdrs.get("anthropic-beta")
    if existing and _PROMPT_CACHE_BETA not in existing:
        hdrs["anthropic-beta"] = f"{existing},{_PROMPT_CACHE_BETA}"
    else:
        hdrs["anthropic-beta"] = _PROMPT_CACHE_BETA
    kwargs["extra_headers"] = hdrs
    return kwargs


def _is_bad_request(exc: Exception) -> bool:
    """400 invalid_request — erro PERMANENTE nosso (payload inválido), NUNCA
    'sobrecarga'. Não deve ser rotulado como transitório nem re-tentado à toa."""
    if _HAS_ANTHROPIC and isinstance(exc, anthropic.APIStatusError):
        if getattr(exc, "status_code", None) == 400:
            return True
    return "invalid_request_error" in str(exc) or "invalid high surrogate" in str(exc)


def _is_retryable(exc: Exception) -> bool:
    """True se a exceção é transitória e vale retentar."""
    if _is_bad_request(exc):
        return False  # 400 é nosso; retentar só empurra o mesmo lixo de novo
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


# ── Classificação de erro por TEXTO (pra quem só tem a string já achatada) ──
# main.py junta sheet_errors/dxf_errors (strings) e precisa decidir a copy: só
# chamar de "provedor sobrecarregado" com PROVA de transitório. 400/401/403/404/
# 413/invalid_request/surrogate são PERMANENTES e NUNCA viram "é o provedor,
# reprocesse" — era essa inversão de default que prendia o cliente em loop
# (caso Rodrigo 19/07: model-id errado dava 404 em todo DXF e virava "sobrecarga").

# Marcadores de erro PERMANENTE (nosso/arquivo) — reprocessar sozinho não conserta.
_PERMANENT_TOKENS = (
    "invalid_request", "invalid high surrogate", "surrogate", "bad_request",
    "invalid json", "request body is not valid", "request too large",
    "authentication_error", "permission_error", "not_found_error",
    "status=400", "status=401", "status=403", "status=404", "status=413",
    "status=422",
)
# Marcadores de erro TRANSITÓRIO (provedor/infra) — PROVA de que reprocessar resolve.
_TRANSIENT_TOKENS = (
    "rate_limit", "rate limit", "429", "529", "overloaded", "timeout",
    "timed out", "sobrecarregad", "connection", "status=500", "status=502",
    "status=503", "status=504",
    # Erros de rede CRUS que escapam da tipagem do SDK no MEIO do streaming
    # (socket cai durante a leitura do corpo) — chegam sem status_code, mas são
    # transitórios e valem re-tentar. Reconhecidos pelo type=<Classe> no prefixo
    # (ver analyzer.py / main.py) ou pela mensagem de baixo nível do SO/httpx.
    "broken pipe", "brokenpipeerror", "remoteprotocolerror", "protocolerror",
    "incompleteread", "econnreset", "reset by peer", "disconnected",
    "connectionreset", "connectionaborted", "connectionerror",
)


def classify_error_text(text: str) -> str:
    """Classifica uma mensagem de erro JÁ achatada em 'transient' | 'permanent'
    | 'unknown'. Permanente vence transitório quando os dois aparecem — nunca
    culpar o provedor havendo prova de erro nosso/de arquivo. 'unknown' é
    tratado como NÃO-transitório pelo chamador (não vira 'sobrecarga')."""
    msg = (text or "").lower()
    if any(t in msg for t in _PERMANENT_TOKENS):
        return "permanent"
    if any(t in msg for t in _TRANSIENT_TOKENS):
        return "transient"
    return "unknown"


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
    cache_system: bool = False,
    **kwargs: Any,
) -> Any:
    """Wrapper em torno de `client.messages.create(**kwargs)` com retry.

    Args:
        client: instância de `anthropic.Anthropic`.
        max_retries: tentativas adicionais além da 1ª (default 8 → até 9 chamadas).
        base_delay: delay inicial em segundos (dobra a cada tentativa).
        max_delay: teto do backoff.
        tag: string pra log identificar qual chamada tá retentando.
        cache_system: se True, marca o system prompt como cacheável (economia de
            custo em chamadas repetidas com o mesmo system). Ver _apply_system_cache.
        **kwargs: passados direto pra `messages.create`.

    Returns:
        O mesmo objeto retornado por `client.messages.create(...)`.

    Raises:
        A última exceção, se todas as tentativas falharem.
    """
    kwargs = _scrub_payload(kwargs)  # limpa surrogates antes do 1º envio
    if cache_system:
        kwargs = _apply_system_cache(kwargs)
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
    cache_system: bool = False,
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
    kwargs = _scrub_payload(kwargs)  # limpa surrogates antes do 1º envio
    if cache_system:
        kwargs = _apply_system_cache(kwargs)
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
# deploy: restart 19/07 23h — destravar job órfão do Rodrigo (sem mudança funcional)
