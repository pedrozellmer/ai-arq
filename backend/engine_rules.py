# -*- coding: utf-8 -*-
"""Regras DETERMINÍSTICAS do motor (sem IA, sem rede, sem deps pesadas).

Extraído de main.py/analyzer.py para: (1) eliminar duplicação — o salvage de JSON
estava copiado nos dois arquivos — e (2) permitir testes automáticos (a "rede de
segurança") que rodam em segundos sem chamar a IA. Ver tests/test_engine_rules.py.

REGRA: só stdlib aqui (re, json). NUNCA importar anthropic/supabase/fastapi —
é o que deixa este módulo testável isolado e rápido.
"""
import json as _json
import re as _re


def extract_balanced_obj(s, start):
    """Do índice de um '{', retorna (objeto JSON balanceado como str, índice após).
    Se não fechar (JSON truncado), retorna (None, start). Respeita strings e escapes
    (uma chave '}' dentro de uma string NÃO conta)."""
    depth = 0
    in_str = False
    esc = False
    i = start
    n = len(s)
    while i < n:
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return s[start:i + 1], i + 1
        i += 1
    return None, start


def salvage_truncated_json(s):
    """Recupera os itens COMPLETOS de um JSON truncado (resposta da IA cortada no
    teto de tokens numa prancha grande). Em vez de perder TUDO, devolve o que deu.
    Nunca lança. Retorna {"items": [...]} e, se achar, "project_data". Caso Ademir."""
    out = {"items": []}
    try:
        pi = s.index('"project_data"')
        bstart = s.index('{', pi)
        pd_obj, _ = extract_balanced_obj(s, bstart)
        if pd_obj:
            out["project_data"] = _json.loads(pd_obj)
    except Exception:
        pass
    try:
        ii = s.index('"items"')
        astart = s.index('[', ii)
        i = astart + 1
        n = len(s)
        while i < n:
            while i < n and s[i] not in '{]':
                i += 1
            if i >= n or s[i] == ']':
                break
            obj, end = extract_balanced_obj(s, i)
            if not obj:
                break
            try:
                out["items"].append(_json.loads(obj))
            except Exception:
                pass
            i = end
    except Exception:
        pass
    return out


def normalize_items_payload(parsed):
    """A IA às vezes devolve um array cru [...] em vez de {"items":[...]} (mais comum
    no prompt estrutural). Embrulha pra o caller nunca fazer .get() num list — bug
    'list object has no attribute get' que derrubou o job do Luciano (27/06)."""
    if isinstance(parsed, list):
        return {"items": parsed}
    if not isinstance(parsed, dict):
        return {"items": []}
    return parsed


_ACO_PAT = _re.compile(r'armadura|estribo|ferragem|vergalh|\baço\b', _re.IGNORECASE)
_FORMA_PAT = _re.compile(r'f[ôo]rma', _re.IGNORECASE)


def should_force_steel_kg(description):
    """Em projeto ESTRUTURAL, aço/armadura/estribo é SEMPRE kg (regra de norma,
    universal). True quando a descrição é claramente de aço E não é fôrma (m²).
    NÃO casa 'concreto armado' (concreto/fôrma) — só o aço de verdade. Caso Luciano."""
    d = description or ""
    return bool(_ACO_PAT.search(d)) and not _FORMA_PAT.search(d)


def is_likely_wrong_type(quantities, threshold=0.75):
    """Guardrail de tipo (caso Magno): um projeto marcado ESTRUTURAL que sai com
    quase tudo zerado provavelmente é arquitetura marcada errada no upload. True se
    >= threshold (75%) dos itens têm quantidade 0/None. Estrutural de verdade
    (Luciano: 44% zerado) fica abaixo do corte e NÃO dispara."""
    qs = list(quantities or [])
    if not qs:
        return False
    zeros = sum(1 for q in qs if not (q or 0))
    return zeros / len(qs) >= threshold


def extraction_has_quality_caveat(metadata) -> bool:
    """TRAVA DE PROCEDÊNCIA (regra nº1). True se a extração geométrica veio com
    RESSALVA que impede confirmar: estéril (0 medições), unidade suspeita/absurda,
    ou xref não resolvido. Nenhum item de um DXF com ressalva pode sair
    'confirmado' (branco/medido) — só REBAIXA pra estimado, nunca promove.
    Fecha o furo de a IA carimbar 'medido' num número que não dá pra confiar."""
    if not metadata:
        return False
    return bool(
        metadata.get("extracao_esteril")
        or metadata.get("unidade_suspeita")
        or metadata.get("alerta_unidade")
        or metadata.get("xref_nao_resolvido")
    )


_BLOCK_NAME_RE = _re.compile(
    r"bloco(?:\s+cad)?\s*['\"‘’“”]\s*([^'\"‘’“”]+?)\s*['\"‘’“”]",
    _re.IGNORECASE,
)


def extract_block_name(description):
    """Extrai o nome do bloco CAD citado na descrição (entre aspas, após 'bloco'),
    ex: "bloco CAD 'cad-escr-02'" → 'cad-escr-02'; "bloco 'fogão'" → 'fogão'.
    Retorna None se não houver. Usado pra DEDUP: o mesmo bloco citado em itens de
    disciplinas diferentes é a MESMA contagem física (a IA às vezes duplica — 14
    cadeiras 'cad-escr-02' viravam 28). 'bloco cerâmico/de concreto' (sem aspas)
    NÃO casa, então alvenaria não é afetada."""
    if not description:
        return None
    m = _BLOCK_NAME_RE.search(description)
    if not m:
        return None
    name = (m.group(1) or "").strip().lower()
    if len(name) < 2 or name in ("cad", "x", "xx"):
        return None
    return name
