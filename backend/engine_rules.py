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


def response_truncated(stop_reason) -> bool:
    """#7 — resposta da IA cortada no teto de tokens = leitura possivelmente
    INCOMPLETA (disciplinas/itens podem ter ficado de fora). Sinal de 1ª classe
    pra AVISAR o cliente, independente de o JSON ter parseado ok — o pior é
    entregar planilha parcial parecendo completa (caso Ademir). Anthropic:
    Message.stop_reason == 'max_tokens'. Fonte única do 'número mágico' pra os
    dois caminhos (DXF + Vision) não divergirem."""
    return str(stop_reason or "").strip() == "max_tokens"


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


_NONSENSE_PAT = _re.compile(r"se[çc][ãa]o\s+transversal|[áa]rea\s+de\s+se[çc][ãa]o|cross.?section", _re.IGNORECASE)


def is_nonsense_item(description):
    """Item-ARTEFATO que não é quantitativo real: 'área de seção transversal' de
    parede = a hachura da ESPESSURA da parede virou item de m². Ninguém compra
    'seção transversal' — é lixo de extração. Caso Thamiry (projeto drywall)."""
    if not description:
        return False
    return bool(_NONSENSE_PAT.search(description))


_TYPE_CODE_PAT = _re.compile(r"\b(DRY|DW|DIV|PAR|PV)[\s\-]?(\d{1,3})\b", _re.IGNORECASE)


def extract_type_code(description):
    """Extrai código de TIPO de divisória/parede (DRY 07, DW-12, DIV 03...) pra
    consolidar o MESMO tipo que aparece em várias pranchas. None se não houver.
    Em projeto multi-prancha de drywall, o mesmo tipo se fragmenta em dezenas de
    linhas (caso Thamiry: 191 itens, 156 zerados)."""
    if not description:
        return None
    m = _TYPE_CODE_PAT.search(description)
    if not m:
        return None
    return f"{m.group(1).upper()} {m.group(2)}"


# ── Honestidade de área: superfície de piso x item pontual/linear/localizado ────
# Usado por _apply_area_honesty (main.py): num PDF SEM cota, quando o cliente INFORMA
# a área total, só os itens que REALMENTE cobrem o piso/forro inteiro herdam essa
# área. Contagem (interruptor, ponto), faixa/demarcação e cômodo específico (banheiro,
# cabine) NÃO — senão a área do projeto vira "quantidade" de coisa que não cobre o
# chão. Bug LAAV 27/07: cliente informou 335,4 m² e 17 itens herdaram a mesma
# metragem, vários absurdos (interruptor = 335 m², faixa de 5 cm = 335 m²).

# Unidades que a IA de Vision às vezes CHUTA num PDF sem cota (tratadas como "medida").
AREA_UNITS_HONESTY = {"m²", "m2", "m", "ml", "m³", "m3", "mts", "m2.", "m²."}
# Subconjunto: m² de superfície — candidato a receber a área INFORMADA.
FLOOR_M2_UNITS = {"m²", "m2", "m2.", "m²."}
# Superfícies HORIZONTAIS que escalam com a área de piso (o item É a superfície).
# "impermeabiliz" saiu daqui de propósito: impermeabilização é sempre localizada
# (área molhada/banheiro/laje técnica) — se for de laje, o "laje" abaixo já pega.
FLOOR_AREA_KW = ("piso", "contrapiso", "forro", "laje", "regulariz", "teto")
# Bloqueia itens que MENCIONAM piso/forro mas NÃO cobrem a área toda:
#  - contagem/pontual (a palavra "piso" é só a altura, ex "H=1,10m do piso acabado"):
#    ponto, interruptor, tomada, luminária, ralo, spot, arandela
#  - linear/faixa: faixa, demarcação, vaga, rodapé
#  - cômodo/área específica: parede, azulejo, banheiro, wc, vestiário, sanitário,
#    área molhada, cabine, nicho
FLOOR_AREA_BLOCK_KW = (
    "rodap", "parede", "azulej", "meia parede",
    "ponto", "interruptor", "tomada", "luminár", "ralo", "spot", "arandela",
    "faixa", "demarca", "vaga",
    "banheiro", "wc", "vestiár", "sanitár", "molhad", "cabine", "nicho",
    # posicionado por ALTURA ("a 1,00m do piso") ou móvel/aparelho que menciona
    # piso de raspão — pego no teste real do LAAV (bancada, bebedouro). "m do piso"
    # (não "h=") pra não bloquear contrapiso com espessura tipo "H=5cm".
    "m do piso", "bancada", "balcão", "balcao", "bebedouro", "purificador",
)


def is_floor_surface(desc):
    """True se a descrição é uma SUPERFÍCIE horizontal que cobre ~a área toda
    (piso/forro/laje/teto) — não um item pontual, linear ou de cômodo específico.
    Heurística por palavra-chave; a medição real só vem da geometria do CAD.
    Ver _apply_area_honesty em main.py e os testes em test_engine_rules.py."""
    d = (desc or "").lower()
    return (any(k in d for k in FLOOR_AREA_KW)
            and not any(b in d for b in FLOOR_AREA_BLOCK_KW))


# ── Coerência de unidade: item CONTÁVEL não sai em metro/m² ──────────────────
# Caso Rafael (visto em 01/08/2026, job ed655532): "Condulete de dados —
# 155,6 ml — CONFIRMADO". Condulete é caixa: conta-se em unidade. O motor mediu
# 155,6 m de infra linear (fix do Fábio) e a IA pendurou os metros na linha
# ERRADA — o condulete virou falso-medido e o eletroduto ficou zerado.
# A regra só REBAIXA (confirmado → estimado) e anota; nunca apaga nem move
# quantidade — mover seria adivinhar a qual linha os metros pertencem.

COUNTABLE_KW = (
    "condulete", "caixa de passagem", "caixa de piso", "caixa 4x2", "caixa 4x4",
    "tomada", "interruptor", "ponto de dados", "ponto de rede", "ponto de tv",
    "ponto de multimídia", "ponto de multimidia", "rack", "patch panel",
    "luminária", "luminaria", "spot", "arandela", "quadro de distribuição",
    "quadro de distribuicao", "disjuntor",
)

LINEAR_UNITS = ("m", "ml", "m linear", "metro", "metros", "m²", "m2", "m³", "m3")


def is_unit_mismatch_countable(desc, unit):
    """True se a descrição é de item CONTÁVEL (caixa/ponto/aparelho) mas a
    unidade veio linear/de área — quantidade não pode ser medição desse item.

    Cuidado deliberado: "eletroduto", "eletrocalha", "cabeamento" NÃO estão na
    lista — esses são lineares de verdade. A regra pega só o que jamais deveria
    sair em metros."""
    d = (desc or "").lower()
    u = (unit or "").strip().lower().replace("²", "2").replace("³", "3")
    if u not in LINEAR_UNITS:
        return False
    return any(k in d for k in COUNTABLE_KW)
