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
import contextlib
import contextvars
from typing import Any

try:
    import anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False


# ─────────────────────────────────────────────────────────────────────────────
#  Custo por projeto: de quem foi o gasto (06/09/2026)
# ─────────────────────────────────────────────────────────────────────────────
# 🚨 O Pedro perguntou "quanto custa processar um projeto" e não havia resposta:
# o registro que existia (error_log stage='llm:cache') não dizia QUAL MODELO
# gastou nem DE QUEM foi o gasto. Sem modelo não vira reais; sem job_id não dá
# pra separar cliente de bancada — e na janela medida havia MAIS avaliação nossa
# (38) do que projeto de cliente (39).
#
# 🪤 POR QUE ContextVar E NÃO VARIÁVEL DE MÓDULO: a sombra do PDF é disparada
# DENTRO do process_job (main.py:12664), dorme 8s (pdf_vector.py:405) e trabalha
# por até 180s (pdf_vector.py:32) — ela ATRAVESSA o semáforo de 1 job
# (main.py:6198) e roda junto com o PRÓXIMO projeto. Uma global carimbaria o
# custo do projeto A no projeto B: regra dura nº2 violada, e em silêncio.
# Medido em Python 3.13: thread nova nasce com contexto VAZIO (não herda), e o
# anyio copia o contexto por chamada HTTP. Os dois fatos tornam a ContextVar
# segura por construção — o ÚNICO jeito de vazar é chamar `.set()` solto dentro
# de um worker de pool reusado, e é isso que o guarda proíbe.
_JOB_ATUAL: contextvars.ContextVar = contextvars.ContextVar("aiarq_job_id", default=None)


@contextlib.contextmanager
def escopo_job(job_id: str | None):
    """Marca o dono do gasto de IA enquanto o bloco roda. SEMPRE faz reset.

    🚨 Este é o ÚNICO lugar autorizado a chamar `_JOB_ATUAL.set`. Um `.set()`
    solto dentro de um worker de ThreadPoolExecutor VAZA pra tarefa seguinte
    naquele worker (medido) — com set+reset no finally, a seguinte lê None.
    """
    token = _JOB_ATUAL.set(job_id or None)
    try:
        yield
    finally:
        try:
            _JOB_ATUAL.reset(token)
        except ValueError:
            # Token criado em outro Context (gerador / fronteira de await).
            # Telemetria não pode derrubar o job DEPOIS do trabalho pronto.
            _JOB_ATUAL.set(None)


# Catálogo FECHADO de etapas. O `escopo` sai DAQUI, nunca da presença do job_id:
# derivar de "tem dono? então é de projeto" tornaria o guarda de órfãos
# tautológico — toda chamada que perdesse o dono seria reetiquetada 'plataforma'
# e a consulta daria 0 pra sempre, lavando exatamente o defeito que ela procura.
_ETAPAS: dict[str, str] = {
    "dxf": "projeto",                  # extração de DXF (main.py:9391)
    "prancha": "projeto",              # analyzer.py:1243 (tag crua: "analyzer:<arquivo>")
    "sinapi_pick": "projeto",          # sinapi_matcher.py:584
    "classifier": "projeto",           # classifier.py:186
    "salvage-layout-counts": "projeto",  # main.py:6379
    "pdfvec-carimbo": "projeto",       # pdfvec_carimbo.py:170
    "memorial-intro": "projeto",       # main.py:20571
    "chat-projeto": "projeto",         # main.py:18102
    "agent": "projeto",                # agent.py:756 (tag crua: "agent:job=<id>")
    "filhote-juiz": "projeto",         # main.py:24302
    "merge-juiza": "plataforma",       # main.py:25032 — bancada, não cliente
    "chat-publico": "plataforma",      # main.py:17961 — visitante, sem projeto
    "admin-sugestao-anexo": "plataforma",  # main.py:24173
    "instagram": "plataforma",
    # Classificação do catálogo SINAPI: script de carga, rodado à parte —
    # nenhum arquivo do backend importa sinapi_classifier. Custo da casa, não
    # de projeto. (Achado pelo próprio guarda de cobertura, 06/09.)
    "sinapi_batch": "plataforma",          # sinapi_classifier.py:160
}

# A tag de produção carrega o NOME DO ARQUIVO DO CLIENTE em dois pontos
# (analyzer.py:1243, main.py:9391) e o job_id num terceiro (agent.py:756).
# Normalizar aqui resolve os três de uma vez: a etapa vira slug agrupável e
# nome de arquivo de cliente NÃO entra numa tabela de dinheiro interno (nº6).
_PREFIXO_ETAPA = {"analyzer": "prancha", "dxf": "dxf", "agent": "agent"}


def _etapa_e_escopo(tag: str) -> tuple[str, str]:
    base = (tag or "").split(":", 1)[0].strip() or "desconhecido"
    etapa = _PREFIXO_ETAPA.get(base, base)
    return etapa, _ETAPAS.get(etapa, "desconhecido")


_PRECOS_CACHE: dict[str, Any] = {"ate": 0.0, "mapa": None}
_PRECOS_TTL_S = 600


def _precos() -> dict:
    """{modelo: (versao, in, out, cache_read, cache_write)}. Falha -> {} (custo NULL)."""
    agora = time.time()
    if _PRECOS_CACHE["mapa"] is not None and agora < _PRECOS_CACHE["ate"]:
        return _PRECOS_CACHE["mapa"]
    mapa: dict = {}
    try:
        from main import _supa_rest_service
        _st, _rows = _supa_rest_service(
            "GET", "llm_precos",
            params={"select": "modelo,vigencia_inicio,usd_in_mtok,usd_out_mtok,"
                              "usd_cache_read_mtok,usd_cache_write_mtok",
                    "order": "vigencia_inicio.desc"})
        for r in (_rows or []):
            m = r.get("modelo")
            if m and m not in mapa:   # a primeira é a vigência mais recente
                mapa[m] = ("%s@%s" % (m, r.get("vigencia_inicio")),
                           float(r.get("usd_in_mtok") or 0),
                           float(r.get("usd_out_mtok") or 0),
                           float(r.get("usd_cache_read_mtok") or 0),
                           float(r.get("usd_cache_write_mtok") or 0))
    except Exception:
        mapa = {}
    _PRECOS_CACHE["mapa"] = mapa
    # 🪤 Guarda o TTL mesmo quando a leitura falhou: senão cada chamada de IA
    # tentaria ler preço de novo e a telemetria viraria o gargalo do motor.
    _PRECOS_CACHE["ate"] = agora + _PRECOS_TTL_S
    return mapa


def _custo_usd(modelo: str | None, novo: int, le: int, esc: int, out: int):
    """(custo, preco_ver) ou (None, None). Modelo sem preço casado NUNCA dá 0."""
    if not modelo:
        return None, None
    p = _precos().get(modelo)
    if not p:
        return None, None
    ver, u_in, u_out, u_le, u_esc = p
    total = (novo * u_in + le * u_le + esc * u_esc + out * u_out) / 1e6
    return round(total, 6), ver


def _gravar_uso(*, tag: str, resultado: str, modelo=None, job_id=None,
                novo=None, le=None, esc=None, out=None,
                cache_marcado: bool = False, erro=None) -> None:
    """UMA linha por passagem por call_with_retry. Sempre. Nunca levanta.

    🔑 O PRINCÍPIO: linha ausente, somada por SUM e dividida por projeto, é
    indistinguível de custo baixo. Então o que varia é o `resultado`
    ('api' | 'cache' | 'sem_usage' | 'falhou') e se os tokens vêm NULL — a
    CONTAGEM de chamadas fica certa mesmo quando o valor não é conhecido.
    """
    if os.environ.get("LLM_USO_TELEMETRIA", "1") == "0":
        return
    # 🩸 06/09/2026 — a BANCADA estava escrevendo na tabela de PRODUÇÃO. Dois
    # testes de `test_cache_telemetria.py` chamam `_registrar_uso` com uma
    # resposta falsa; assim que ele passou a gravar de verdade, cada rodada da
    # suíte inseria linha de mentira na conta de custo do Pedro. Descoberto
    # porque a sequence da tabela pulou pra 13 sem ninguém ter subido nada.
    # Custo inventado é pior que custo ausente: ele tem cara de fato.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        etapa, escopo = _etapa_e_escopo(tag)
        dono = job_id or _JOB_ATUAL.get()
        linha = {
            "etapa": etapa, "escopo": escopo, "resultado": resultado,
            "job_id": dono or None, "modelo": modelo or None,
            "cache_marcado": bool(cache_marcado),
        }
        if resultado in ("api", "cache"):
            linha.update({"tokens_novos": int(novo or 0),
                          "tokens_cache_read": int(le or 0),
                          "tokens_cache_write": int(esc or 0),
                          "tokens_saida": int(out or 0)})
            custo, ver = _custo_usd(modelo, int(novo or 0), int(le or 0),
                                    int(esc or 0), int(out or 0))
            if custo is not None:
                linha["custo_usd"] = custo
                linha["preco_ver"] = ver
        if erro:
            linha["erro"] = str(erro)[:200]
        from main import _supabase_insert
        _supabase_insert("llm_uso", linha)
    except Exception:
        # Telemetria NUNCA derruba o fluxo do cliente.
        pass


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
    Se o prefixo for menor que o mínimo do modelo, a API só IGNORA o marcador —
    sem erro e sem cobrança extra. Mínimos (doc oficial jul/2026): Sonnet 4.6 e
    Opus 4.8 = 1024 tok; Opus 4.7 = 2048; Opus 4.6 = 4096; Haiku 4.5 = 4096.

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



def _registrar_uso(tag: str, resp, cache_system: bool, model=None, job_id=None) -> None:
    """Grava o resultado REAL do prompt caching, por chamada.

    🚨 24/08/2026: o caching foi ligado em 23/07 e conferido com duas chamadas
    manuais naquele dia. Um mês depois a Anthropic avisou de novo que o hit rate
    está baixo — e a gente não tinha COMO saber, porque nada aqui olhava
    `response.usage`. Medir é mais barato que adivinhar.

    A doc define a conta assim:
        total_input = cache_read + cache_creation + input_tokens
    e o preço: leitura do cache custa 10% do input, escrita custa 125%. Então
    `pct_cacheado` abaixo é, na prática, o quanto da conta a gente está pagando
    barato.

    Best-effort e silencioso: nunca pode derrubar uma extração por causa de
    telemetria.
    """
    # 🔑 06/09/2026 — o modelo REAL vem da resposta quando ela diz quem respondeu:
    # o modelo do DXF muda por variável de ambiente SEM deploy (main.py:2498,
    # DXF_EXTRACT_MODEL), e sem o id certo os mesmos tokens custam 3× mais ou
    # menos. Sem modelo, nenhum custo é reconstituível.
    _modelo = getattr(resp, "model", None) or model
    if os.environ.get("LLM_CACHE_TELEMETRIA", "1") == "0":
        return
    try:
        u = getattr(resp, "usage", None)
        if u is None:
            # 🪤 Antes isto era `return` puro: uma chamada que ACONTECEU e foi
            # COBRADA sumia sem rastro, e o projeto parecia mais barato do que
            # foi. Agora vira linha com tokens NULL — "não sei quanto custou"
            # é diferente de "custou zero".
            _gravar_uso(tag=tag, resultado="sem_usage", modelo=_modelo,
                        job_id=job_id, cache_marcado=cache_system,
                        erro="usage_ausente")
            return
        _le = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        _esc = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
        _novo = int(getattr(u, "input_tokens", 0) or 0)
        _out = int(getattr(u, "output_tokens", 0) or 0)
        _tot = _le + _esc + _novo
        if _tot <= 0:
            _gravar_uso(tag=tag, resultado="sem_usage", modelo=_modelo,
                        job_id=job_id, cache_marcado=cache_system,
                        erro="usage_zerado")
            return
        _gravar_uso(tag=tag, resultado="api", modelo=_modelo, job_id=job_id,
                    novo=_novo, le=_le, esc=_esc, out=_out,
                    cache_marcado=cache_system)
        _pct = round(100.0 * _le / _tot, 1)
        print(f"[llm_cache:{tag}] total_in={_tot} cache_read={_le} ({_pct}%) "
              f"cache_write={_esc} novo={_novo} out={_out} "
              f"marcado={'sim' if cache_system else 'nao'}")
        # 🪤 O import é local e dentro do try: llm_retry.py é usado por módulos
        # que NÃO importam o main.py (analyzer, classifier, pdfvec_carimbo), e
        # importar o main aqui criaria ciclo — e o main conecta em Supabase e
        # Stripe no import.
        try:
            from main import _log_error
            _log_error("llm:cache",
                       f"{tag} total_in={_tot} read={_le} ({_pct}%) "
                       f"write={_esc} novo={_novo} out={_out} "
                       f"marcado={int(bool(cache_system))} "
                       f"modelo={_modelo or '?'}")
        except Exception:
            pass
    except Exception:
        pass



# ─────────────────────────────────────────────────────────────────────────────
#  Cache por conteúdo (llm_cache.py). Opt-in por call site: `cache=True`.
# ─────────────────────────────────────────────────────────────────────────────

class _RespostaDoCache:
    """Imita o Message da Anthropic no que quem chama realmente usa.

    🪤 Quem consome faz `resp.content[0].text` e `resp.stop_reason`. Devolver um
    dict quebraria os dois. Isto NÃO é um mock de teste — é o formato de
    resposta do caminho de cache em produção.
    """
    class _Bloco:
        def __init__(self, texto):
            self.text = texto
            self.type = "text"

    def __init__(self, texto, stop_reason="end_turn"):
        self.content = [self._Bloco(texto)]
        self.stop_reason = stop_reason
        self.usage = None          # 🔑 tokens REAIS gastos: nenhum
        self.do_cache = True


def _cache_antes(kwargs: dict, *, tag: str, cache: bool):
    """(chave, resposta_do_cache_ou_None).

    🪤 No modo SOMBRA (default) calcula a chave, registra acerto/erro no log e
    devolve None — ou seja, NÃO serve do cache. Isso mede a taxa real de acerto
    sem mudar o resultado de um cliente sequer. Ligar de verdade é trocar a env
    LLM_CACHE pra "on", sem deploy.
    """
    if not cache:
        return None, None
    try:
        import llm_cache as _lc
        chave = _lc.carimbo(kwargs)
        guardado = _lc.ler(chave)
        modo = _lc._modo()
        if guardado:
            print("[llm_cache:acerto] tag=%s modo=%s chave=%s" % (tag, modo, chave[:12]))
            if modo == "on":
                return chave, _RespostaDoCache(guardado.get("response_text") or "",
                                               guardado.get("stop_reason") or "end_turn")
        else:
            print("[llm_cache:erro] tag=%s modo=%s chave=%s" % (tag, modo, chave[:12]))
        return chave, None
    except Exception as e:
        # cache que derruba extração é pior que cache nenhum
        print("[llm_cache] falhou na leitura, seguindo sem cache: %s" % e)
        return None, None


def _cache_depois(chave, resp, kwargs: dict, *, tag: str) -> None:
    """Grava a resposta CRUA. Nunca levanta."""
    if not chave:
        return
    try:
        import llm_cache as _lc
        _lc.gravar(chave, resp, {
            "tag": tag,
            "model": kwargs.get("model"),
            "temperature": kwargs.get("temperature"),
            "max_tokens": kwargs.get("max_tokens"),
        })
    except Exception:
        pass


def call_with_retry(
    client: Any,
    *,
    max_retries: int = 8,
    base_delay: float = 2.0,
    max_delay: float = 90.0,
    tag: str = "anthropic",
    cache_system: bool = False,
    cache: bool = False,
    job_id: str | None = None,
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
        job_id: dono do gasto, quando o call site sabe. Vale MAIS que a
            ContextVar — use nos pontos que rodam fora da thread do job (rota
            HTTP, pool de threads), onde o contexto não chega. 🪤 É parâmetro
            NOMEADO de propósito: assim não entra em `kwargs`, não vai pro
            `messages.create` e não invalida as chaves do llm_cache.
        **kwargs: passados direto pra `messages.create`.

    Returns:
        O mesmo objeto retornado por `client.messages.create(...)`.

    Raises:
        A última exceção, se todas as tentativas falharem.
    """
    kwargs = _scrub_payload(kwargs)  # limpa surrogates antes do 1º envio
    _chave, _do_cache = _cache_antes(kwargs, tag=tag, cache=cache)
    if _do_cache is not None:
        # 🔑 Cache servido é economia AFIRMADA, não deduzida de um buraco: sem
        # esta linha, ligar o LLM_CACHE faria o custo por projeto cair e
        # ninguém saberia se foi economia ou telemetria quebrada.
        _gravar_uso(tag=tag, resultado="cache", modelo=kwargs.get("model"),
                    job_id=job_id, novo=0, le=0, esc=0, out=0)
        return _do_cache
    if cache_system:
        kwargs = _apply_system_cache(kwargs)
    last_exc: Exception | None = None
    delay = base_delay

    for attempt in range(max_retries + 1):
        try:
            _resp = client.messages.create(**kwargs)
            _registrar_uso(tag, _resp, cache_system,
                           model=kwargs.get("model"), job_id=job_id)
            _cache_depois(_chave, _resp, kwargs, tag=tag)
            return _resp
        except Exception as e:
            last_exc = e

            if not _is_retryable(e) or attempt >= max_retries:
                # 🪤 Chamada que estoura o timeout DEPOIS de o modelo já ter
                # gerado saída é COBRADA pela Anthropic. Sem esta linha a
                # subcontagem se concentraria justamente nos jobs ruins.
                _gravar_uso(tag=tag, resultado="falhou",
                            modelo=kwargs.get("model"), job_id=job_id,
                            cache_marcado=cache_system, erro=type(e).__name__)
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
    cache: bool = False,
    job_id: str | None = None,
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
    # 🔑 O carimbo sai DEPOIS do scrub (determinístico) e ANTES do
    # _apply_system_cache: `cache_control` e `extra_headers` são decisão de
    # CUSTO da Anthropic e não podem invalidar o cache de conteúdo.
    _chave, _do_cache = _cache_antes(kwargs, tag=tag, cache=cache)
    if _do_cache is not None:
        _gravar_uso(tag=tag, resultado="cache", modelo=kwargs.get("model"),
                    job_id=job_id, novo=0, le=0, esc=0, out=0)
        return _do_cache
    if cache_system:
        kwargs = _apply_system_cache(kwargs)
    last_exc: Exception | None = None
    delay = base_delay

    for attempt in range(max_retries + 1):
        try:
            with client.messages.stream(**kwargs) as stream:
                _resp = stream.get_final_message()
            _registrar_uso(tag, _resp, cache_system,
                           model=kwargs.get("model"), job_id=job_id)
            _cache_depois(_chave, _resp, kwargs, tag=tag)
            return _resp
        except Exception as e:
            last_exc = e

            if not _is_retryable(e) or attempt >= max_retries:
                _gravar_uso(tag=tag, resultado="falhou",
                            modelo=kwargs.get("model"), job_id=job_id,
                            cache_marcado=cache_system, erro=type(e).__name__)
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
