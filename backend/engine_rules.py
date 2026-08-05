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
        # 04/08: layer de duto que é HACHURA (o comprimento todo em
        # micro-segmento), ou curva de duto que ficou fora do pareamento e
        # ainda conta as duas faces. Nos dois casos o número existe, parece
        # medição e NÃO é. Sem entrar aqui, o aviso morria no log e o item
        # saía branco na planilha. Ver _corrigir_duto_linha_dupla.
        or metadata.get("duto_medicao_suspeita")
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


# ── O motor mediu, escreveu na observação, e a linha saiu errada ─────────────
# Caso Eloídes (03/08/2026, job 2f9f81c2 — projeto de incêndio, 112 MB):
#   "Tubulação de hidrantes"  → unidade m²  · qtd 12.642,38 · obs: "= 12.642,38 m"
#   "Tubulação de sprinklers" → unidade un  · qtd 0         · obs: "= 28.714,56 m"
#   "Conexões RetFire"        → unidade un  · qtd 0         · obs: "= 295,04 m"
# No MESMO projeto, 3 itens iguais saíram certos em `ml`. Ou seja: a extração
# mediu bem; quem erra é o rótulo que a IA pendura na linha.
#
# 12.642,38 **m²** de tubulação de aço é número absurdo que, se passar, vira
# erro caro no orçamento. E entregar 0 tendo medido 28,7 km é
# `feedback_evidencia_nao_sobrevive` na veia — o dado existe, escrito ali do lado.
#
# 🔒 A regra é CONSERVADORA de propósito. Só age quando a medida está na
# observação DO PRÓPRIO ITEM (não move nada entre linhas — essa é a diferença
# em relação ao caso Rafael acima, onde mover seria adivinhar) e só em dois
# casos sem ambiguidade:
#   1. quantidade == medida, mas a unidade não é de comprimento → só o rótulo
#      está errado; corrige a unidade e mantém tudo o mais.
#   2. quantidade 0/vazia, havendo medida → a medição foi descartada; recupera
#      o número e **rebaixa pra estimado**, nunca pra confirmado (soma de layer
#      pode contar linha a mais; quem valida é o cliente — regra dura nº1).
# Fora desses dois casos NÃO mexe: quantidade diferente da medida pode ser uma
# conta legítima (comprimento × largura, desconto de trecho...).

LENGTH_UNITS_OK = {"m", "ml", "metro", "metros", "m linear", "mts"}

# "= 12.642,38 m" / "= 295,04m" / "= 1.285,22 metros" — exige o 'm' isolado,
# então m² e m³ NÃO casam (senão a regra "corrigiria" uma área de verdade).
# 🪤 O vão entre "comprimento total" e o "=" NÃO pode atravessar frase. Com
# `[^=]{0,80}` a regra pescou a altura de um corrimão: a observação dizia
# "Comprimento total não calculado — confirmar com projeto. Texto ARQ_CAIXILHOS:
# 'CORRIMO-h=1,00m'", e ela pulou até o "=" da frase SEGUINTE e leu 1,00 m como
# se fosse o comprimento do guarda-corpo. Proibir '.' e '|' no vão prende a
# leitura na mesma frase — que é a única em que o "=" se refere ao comprimento.
_RE_COMPRIMENTO = _re.compile(
    r"comprimento\s+total[^=.|]{0,60}?=\s*"
    r"(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:[.,]\d+)?)\s*"
    r"(?:m|metros?|ml)\b(?![²³23])",
    _re.IGNORECASE)

# ─────────────────────────────────────────────────────────────────────────────
# 🚨 O número citado nem sempre É a resposta — muitas vezes é a BASE DE CÁLCULO.
#
# Achado em 03/08/2026 varrendo as linhas zeradas reais. Nestes 4 casos a regra
# original preencheria um número ERRADO, que é pior que deixar vazio:
#
#   "Derivado do comprimento total de paredes (layer A-WALL = 722,39 ml).
#    Quantidade de guia = 2 × comprimento linear"     → certo é 1444,78, não 722,39
#   "Comprimento por tipo não disponível"             → 965,77 é a soma de TODOS
#                                                        os tipos; a linha é UM tipo
#   "Comprimento de juntas estimado A PARTIR DO
#    comprimento total de paredes"                    → fita não mede o mesmo que parede
#   "Área de pintura não calculável ... o comprimento
#    total de paredes = ..."                          → área precisa de pé-direito
#
# Quando a própria observação diz que o número é ponto de partida, a regra sai
# de fininho. Vazio o cliente preenche; errado ele compra errado — e é a tese que
# a gente publica ("planilha honesta e incompleta é melhor que completa e errada").
_RE_BASE_DE_CALCULO = _re.compile(
    r"deriv[ao]d[ao]\s+d|"
    r"estimad[ao]\s+a\s+partir|"
    r"calculad[ao]\s+a\s+partir|"
    r"proporcional\s+a|"          # "perfis proporcional ao comprimento de paredes"
    r"sem\s+discrimina|"          # "sem discriminação de comprimento por seção"
    r"n[ãa]o\s+calcul[áa]vel|"
    r"n[ãa]o\s+[ée]\s+poss[íi]vel\s+(?:separar|discriminar|dividir)|"
    r"por\s+tipo\s+n[ãa]o\s+(?:dispon[íi]vel|discriminad|segregad)|"
    r"n[ãa]o\s+(?:segregad|discriminad)[ao]\s+(?:no|por)|"
    r"inclui\s+todos\s+os\s+tipos|"
    r"m[úu]ltiplas\s+vistas|"
    r"sem\s+p[ée][-\s]?direito",
    _re.IGNORECASE)


def medida_e_base_de_calculo(obs):
    """True quando a observação diz que o número citado é PONTO DE PARTIDA
    (derivação, soma de vários tipos, falta de pé-direito) e não a quantidade
    daquela linha. Nesse caso não se recupera nada."""
    return bool(obs) and bool(_RE_BASE_DE_CALCULO.search(str(obs)))


def medida_de_comprimento_na_observacao(obs):
    """Devolve o comprimento em metros citado na observação, ou None.

    🪤 Número em pt-BR: '12.642,38' = doze mil. Ler isso como float direto daria
    12,64 — erro de 1000×, a mesma armadilha do valor em R$ do cronograma."""
    if not obs:
        return None
    m = _RE_COMPRIMENTO.search(str(obs))
    if not m:
        return None
    bruto = m.group(1)
    if "," in bruto:
        bruto = bruto.replace(".", "").replace(",", ".")
    elif bruto.count(".") > 1 or (
            "." in bruto and len(bruto.rsplit(".", 1)[1]) == 3):
        bruto = bruto.replace(".", "")     # 12.642 / 1.285.220 = milhar
    try:
        v = float(bruto)
    except ValueError:
        return None
    return v if v > 0 else None


def _num_br(v):
    """12642.38 → '12.642,38'. Formata SÓ o número: aplicar troca de vírgula e
    ponto na frase inteira embaralha a pontuação do texto (e essa frase vai
    parar na observação que o cliente lê)."""
    return f"{v:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def corrigir_comprimento_medido(desc, unit, quantity, obs):
    """Devolve dict de correções ({} = não mexer) pro item cuja observação traz
    um 'comprimento total = N m'. Ver o bloco de comentário acima."""
    medida = medida_de_comprimento_na_observacao(obs)
    if medida is None:
        return {}
    # 🚨 O número é base de cálculo, não resposta — ver _RE_BASE_DE_CALCULO.
    if medida_e_base_de_calculo(obs):
        return {}
    u = (unit or "").strip().lower()
    try:
        q = float(quantity or 0)
    except (TypeError, ValueError):
        q = 0.0

    n = _num_br(medida)

    # 1) mediu e entregou ZERO — vem primeiro, e vale mesmo com a unidade certa.
    # 🪤 Este caso passou batido na 1ª versão: eu saía cedo quando a unidade já
    # era de comprimento, achando "então está tudo certo". O 2º projeto da
    # Eloídes (df4f00ca, 191 itens) mostrou 2 itens em `ml` com quantidade 0 —
    # rótulo certo, medição jogada fora do mesmo jeito. Unidade certa não diz
    # nada sobre a quantidade.
    if q <= 0:
        return {"quantity": round(medida, 2),
                "unit": unit if u in LENGTH_UNITS_OK else "m",
                "confidence": "estimado",
                "motivo": (f"⚠ QUANTIDADE RECUPERADA: o motor mediu {n} m neste "
                           f"layer e a linha tinha saído zerada. Marcado como "
                           f"ESTIMADO — a soma do layer pode incluir linha que não "
                           f"é tubulação. Confira antes de orçar.")}

    if u in LENGTH_UNITS_OK:
        return {}                                  # unidade certa e com número

    # 2) mesmo número, rótulo errado (tolerância de centavo)
    if abs(q - medida) <= max(0.01, medida * 0.001):
        return {"unit": "m",
                "motivo": (f"⚠ UNIDADE CORRIGIDA: a observação mede {n} m de "
                           f"comprimento, mas o item saiu em '{unit}'. "
                           f"Comprimento não é área nem contagem.")}

    return {}
