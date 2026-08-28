# -*- coding: utf-8 -*-
"""Cache por CONTEÚDO da chamada de IA — carimba o payload, não os ingredientes.

🎯 O PROBLEMA. Toda leitura de prancha custa uma chamada de IA, e a mesma
prancha é lida de novo em três situações: o cliente reprocessa, o job cai e
retoma sozinho, e a bancada de avaliação roda o mesmo arquivo dezenas de vezes.
Além do custo, o motor NÃO é determinístico: a mesma prancha já deu 22 e 34
itens. Servir a leitura anterior do MESMO payload dá as duas coisas de uma vez.

🔑 O PRINCÍPIO QUE DECIDE O DESENHO. Não manter lista dos ingredientes do
prompt. Carimbar o payload que literalmente vai pra API. Assim, mexer no
SYSTEM_PROMPT, na diretiva de pé-direito, na env do modelo ou na temperatura
muda a chave SOZINHO — sem ninguém lembrar de bumpar versão na mão.

🪤 **ESSA ARMADILHA JÁ ESTÁ MATERIALIZADA NO REPO.** `pdfvec_carimbo.py:220`
faz cache por conteúdo com chave `sha256(arquivo):página:_PROMPT_VERSION`, e o
`_PROMPT_VERSION = "v3"` é string bumpada A MÃO. Pior: a chave **não inclui o
modelo**. Trocar Haiku por Sonnet ali serve a resposta do modelo velho, calada.
A própria skill do projeto (`content-hash-cache-pattern`) avisa em "when NOT to
use": *resultados que dependem de parâmetros além do conteúdo do arquivo*.

🔒 LISTA NEGRA, NUNCA LISTA BRANCA. Hasheia tudo em `kwargs` EXCETO o que é
comprovadamente não-semântico. Parâmetro novo que alguém acrescentar amanhã
entra no hash por padrão. Lista branca foi exatamente o que matou o instrumento
do cadastro em 27/08 (a chave `campo` era descartada calada porque não estava
numa lista) — o custo de errar pra cá é servir resposta velha, que é pior.

📌 GUARDA A RESPOSTA CRUA, não os itens já parseados. Assim, conserto no parser
volta a valer sobre o que está em cache; só mudança de PROMPT precisa invalidar.
O checkpoint atual (`_ckpt_save`) guarda o parseado e perde isso.

✅ PAYLOAD ESTÁVEL, MEDIDO ANTES DE CONSTRUIR (28/08): 4 extrações do mesmo DXF
de 24 MB, em subprocessos separados (portanto `PYTHONHASHSEED` diferente em
cada), deram sha256 idêntico e mesmo tamanho. Sem isso o cache nasceria com 0%
de acerto e todo este arquivo seria trabalho jogado fora.
🪤 Isso foi provado em UM arquivo. Não é prova universal — é o motivo de o modo
SOMBRA existir.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

# ── o que NÃO entra no carimbo ────────────────────────────────────────────────
# 🔒 Só entra aqui o que comprovadamente não muda a RESPOSTA da IA.
# Mexer nesta lista é decisão de gente: `test_llm_cache.py` reprova se ela
# crescer sem alguém atualizar o teste junto.
_NAO_SEMANTICO = frozenset({
    "tag",           # só rótulo de log
    "max_retries",   # política de retry
    "base_delay",
    "max_delay",
    "cache_system",  # prompt caching da Anthropic: muda o CUSTO, não a resposta
    "cache",         # o parâmetro deste próprio cache
    "extra_headers",
    "stream",
    "timeout",
})

# 🪤 Namespace pra invalidação de EMERGÊNCIA, não é o mecanismo normal. O
# mecanismo normal é o payload mudar sozinho. Se você está tentado a bumpar
# isto, pergunte primeiro por que a mudança não entrou no payload.
_NAMESPACE = "aiarq-llm-cache|v1"

_TABELA = "llm_cache"


def _modo() -> str:
    """'off' | 'sombra' | 'on'.

    🪤 O DEFAULT É SOMBRA de propósito: calcula a chave, registra acerto e erro,
    e NÃO serve do cache. Serve pra medir a taxa real de acerto antes de mudar
    o resultado de um cliente sequer — e é a única forma de pegar cedo o caso
    "payload instável = 0% de acerto" sem estragar leitura de ninguém.
    """
    v = (os.environ.get("LLM_CACHE") or "sombra").strip().lower()
    return v if v in ("off", "sombra", "on") else "sombra"


def carimbo(kwargs: dict) -> str:
    """sha256 do payload que vai pra API, menos o que não muda a resposta.

    Recebe o `kwargs` DEPOIS do `_scrub_payload` (determinístico e idempotente)
    e ANTES do `_apply_system_cache` — de propósito: `cache_control` e
    `extra_headers` são decisão de custo da Anthropic e não podem invalidar
    o cache de conteúdo.
    """
    limpo = {k: v for k, v in kwargs.items() if k not in _NAO_SEMANTICO}
    corpo = json.dumps(limpo, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256((_NAMESPACE + "|" + corpo).encode("utf-8")).hexdigest()


def _texto_da_resposta(resp: Any) -> str:
    """Extrai o texto de um Message da Anthropic. Vazio se não der."""
    try:
        partes = []
        for bloco in (getattr(resp, "content", None) or []):
            t = getattr(bloco, "text", None)
            if t:
                partes.append(t)
        return "".join(partes)
    except Exception:
        return ""


def pode_gravar(resp: Any) -> tuple[bool, str]:
    """Decide se a resposta merece ir pro cache. Devolve (pode, motivo).

    🚨 A TRAVA QUE MAIS IMPORTA: resposta cortada no teto de tokens. Medido em
    24/08, `stop_reason='max_tokens'` acontece em ~22% das leituras de DXF —
    gravar uma dessas congelaria a leitura MUTILADA e ela voltaria pra sempre,
    inclusive depois de a gente consertar o corte. É o pior estrago possível
    aqui: um bug antigo servido como se fosse resposta boa.
    """
    razao = getattr(resp, "stop_reason", None)
    if razao and razao != "end_turn":
        return False, "stop_reason=%s" % razao
    if not _texto_da_resposta(resp).strip():
        return False, "resposta vazia"
    return True, "ok"


# ── acesso ao banco (best-effort: falhar aqui NUNCA derruba a extração) ───────

def _rest():
    """Importa tarde pra este módulo poder ser testado sem carregar o main.py.

    🔒 `_supa_rest_service` (service role) e não `_supa_rest_as_user`: este
    código roda em thread de processamento, sem `request` em escopo. A tabela
    fica com RLS ligada e ZERO policies — só service_role enxerga, que é a
    convenção do projeto.
    """
    from main import _supa_rest_service  # type: ignore
    return _supa_rest_service


def ler(chave: str) -> dict | None:
    """A resposta guardada, ou None. Silencioso: erro de rede = miss.

    🪤 Best-effort de verdade: se o Supabase estiver fora, a leitura da prancha
    tem que seguir normalmente. Cache que derruba extração é pior que cache
    nenhum.
    """
    if _modo() == "off":
        return None
    try:
        st, linhas = _rest()(
            "GET", _TABELA,
            params={"cache_key": "eq.%s" % chave,
                    "select": "response_text,stop_reason,model,created_at",
                    "limit": "1"})
        if st != 200 or not linhas:
            return None
        return linhas[0]
    except Exception:
        return None


def gravar(chave: str, resp: Any, meta: dict) -> bool:
    """Guarda a resposta CRUA. Devolve se conseguiu. Nunca levanta."""
    if _modo() == "off":
        return False
    ok, _motivo = pode_gravar(resp)
    if not ok:
        return False
    try:
        # 🪤 `resolution=ignore-duplicates`: duas threads podem terminar a MESMA
        # leitura ao mesmo tempo (o auto-resume faz isso). Sem isto, a segunda
        # levanta erro de chave duplicada — que este try engoliria, mas gerando
        # ruído no log de erro pra uma situação perfeitamente normal.
        st, _ = _rest()(
            "POST", _TABELA,
            body={
                "cache_key": chave,
                "tag": str(meta.get("tag") or "")[:60],
                "model": str(meta.get("model") or "")[:80],
                "temperature": meta.get("temperature"),
                "max_tokens": meta.get("max_tokens"),
                "response_text": _texto_da_resposta(resp),
                "stop_reason": str(getattr(resp, "stop_reason", "") or "")[:40],
                "engine_ver": str(os.environ.get("RENDER_GIT_COMMIT") or "")[:12],
            },
            prefer="resolution=ignore-duplicates")
        return 200 <= st < 300
    except Exception:
        return False
