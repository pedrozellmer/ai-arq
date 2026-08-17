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
import unicodedata as _ud


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
    # 🚨 Termos do caso REAL que passou reto (rafaelcmnz@, 05/08): a
    # observação avisava "inclui faces duplas ... e possíveis duplicações
    # ... dividir por 2" e a regra gravou 1960,75 ml assim mesmo. Quando o
    # próprio texto diz que o número está dobrado ou somado de mais, ele não
    # é a quantidade da linha.
    r"faces?\s+dupla|"
    r"duplica[çc]|"
    r"dividir\s+por\s*\d|"
    r"ambos\s+os\s+pavimentos|"
    r"todos\s+os\s+pavimentos|"
    r"soma\s+de\s+todas\s+as\s+linhas|"
    r"multiplicar\s+pel|"
    r"sem\s+p[ée][-\s]?direito",
    _re.IGNORECASE)


def medida_e_base_de_calculo(obs):
    """True quando a observação diz que o número citado é PONTO DE PARTIDA
    (derivação, soma de vários tipos, falta de pé-direito) e não a quantidade
    daquela linha. Nesse caso não se recupera nada."""
    return bool(obs) and bool(_RE_BASE_DE_CALCULO.search(str(obs)))


def num_br_para_float(bruto):
    """'12.642,38' → 12642.38. O parser pt-BR ÚNICO do motor.

    🪤 '12.642,38' vale doze mil. Ler como float direto daria 12,64 — erro de
    1000×, a mesma armadilha do valor em R$ do cronograma (onde a regra é
    "1 parser só"). Esta lógica estava enterrada dentro de
    `medida_de_comprimento_na_observacao`; foi extraída em 08/08 pra que a
    leitura de ÁREA do quadro da prancha use exatamente ela, em vez de eu
    escrever uma segunda e as duas divergirem com o tempo.
    """
    if bruto is None:
        return None
    bruto = str(bruto).strip()
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


def medida_de_comprimento_na_observacao(obs):
    """Devolve o comprimento em metros citado na observação, ou None."""
    if not obs:
        return None
    m = _RE_COMPRIMENTO.search(str(obs))
    if not m:
        return None
    return num_br_para_float(m.group(1))


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
                # 🪤 A frase dizia "pode incluir linha que não é TUBULAÇÃO" —
                # texto fixo, colado em item de alvenaria, de peitoril e de
                # revestimento de pilar. Falar de tubulação numa linha de
                # alvenaria faz o cliente desconfiar do aviso inteiro.
                "motivo": (f"⚠ QUANTIDADE RECUPERADA: o motor mediu {n} m neste "
                           f"layer e a linha tinha saído zerada. Marcado como "
                           f"ESTIMADO — a soma do layer pode incluir traço que "
                           f"não é deste item. Confira antes de orçar.")}

    if u in LENGTH_UNITS_OK:
        return {}                                  # unidade certa e com número

    # 2) mesmo número, rótulo errado (tolerância de centavo)
    if abs(q - medida) <= max(0.01, medida * 0.001):
        return {"unit": "m",
                "motivo": (f"⚠ UNIDADE CORRIGIDA: a observação mede {n} m de "
                           f"comprimento, mas o item saiu em '{unit}'. "
                           f"Comprimento não é área nem contagem.")}

    return {}


# ══════════════════════════════════════════════════════════════════════
#  LAYER DE CARIMBO ≠ DESENHO DA OBRA
# ══════════════════════════════════════════════════════════════════════
# 🪤 Caso HOTEL BRISAS (05/08/2026): o motor leu texto do layer
# "Fundo Logotipo" — o fundo do CARIMBO da prancha — e criou dois serviços
# ("Lastro de concreto magro", "Viga de baldrame"). Serviço que nasce do
# carimbo pode nem existir na obra.
#
# 🚨 "LEGENDA" NÃO ENTRA NESTA LISTA, de propósito. Legenda é conteúdo de
# engenharia legítimo e costuma ser a MELHOR fonte: os 4.638 kg de aço do
# próprio HOTEL BRISAS saíram do quadro de aço, e a potência de 1990 W do
# caso ConfortAr saiu do layer 'LCVP_LEGENDA 2'. Bloquear legenda quebraria
# medição boa. O alvo é a MOBÍLIA da prancha (selo, moldura, logotipo).
#
# Lista curta e conferida no banco: os únicos layers de carimbo que
# realmente produziram item são 'Fundo Logotipo', 'FUNDO' e 'Muldura'.
#
# 🔁 REPROPOSTO E REJEITADO DE NOVO em 09/08/2026. A auditoria do board pediu
# "observação cuja fonte é texto/legenda nunca vira confirmado". Fui conferir os
# 23 itens (de 595 confirmados, 3,9%) que declaram fonte de texto:
#   66ebe2d9  91,7 / 88,8 / 53,41 / 28,6 kg — "linha Ø8.0 da TABELA DE QUANTITATIVOS"
#   6c986633  809,55 / 806,31 / 803,07 kg  — "QUADRO/RESUMO DE AÇO lido da prancha"
#   04c3f98e  60 un                        — "'60 ESTACAS DE CONCRETO fck > 30,0 MPa'"
# É o quadro do próprio projetista. A regra proposta rebaixaria TUDO isso —
# quebraria medição boa, exatamente o que o parágrafo acima já protegia.
# 🔑 E o cliente não fica no escuro: a observação começa com "Fonte: texto layer
# X", e a tela de revisão mostra os primeiros 110 caracteres — ele lê a
# procedência antes de qualquer outra coisa.
# ⚖️ O que sobra é nuance de PALAVRA, não de correção: o selo diz "MEDIDO do CAD"
# para número que veio do arquivo mas não da geometria. Resolver isso pede um
# TERCEIRO estado ("lido da prancha"), que mexe no sistema de cores inteiro —
# decisão de produto do Pedro, não conserto de motor. Não fazer por conta.
_CARIMBO_SPLIT = _re.compile(r"[-_\s./\\|:$]+")
# Prefixo só pra token longo e sem ambiguidade.
# 🪤 'LOGO' NÃO pode ser prefixo: casaria com LOGRADOURO, que é conteúdo de
# implantação. Por isso vive na lista de igualdade exata.
_CARIMBO_PREFIXO = ("CARIMB", "LOGOTIP", "MOLDUR", "MULDUR", "TIMBRE")
_CARIMBO_EXATO = {"FUNDO", "LOGO", "SELO", "MARGEM"}


def layer_is_carimbo(layer_name) -> bool:
    """True se o layer é a MOBÍLIA da prancha (selo/moldura/logotipo).

    Compara por TOKEN, nunca por substring: 'Fachada Fundos' e 'ESCADA' não
    podem cair aqui. Quem chama nunca apaga o item — avisa e rebaixa.
    """
    if not layer_name:
        return False
    for tok in _CARIMBO_SPLIT.split(str(layer_name).upper()):
        if not tok:
            continue
        if tok in _CARIMBO_EXATO:
            return True
        if tok.startswith(_CARIMBO_PREFIXO):
            return True
    return False


# ─── Área total lida do QUADRO DE ÁREAS, por regra (08/08/2026) ──────────────
# 🚨 POR QUE existe: a área total do projeto sai HOJE só da IA lendo o quadro de
# áreas da prancha. Medido em 08/08 — o MESMO arquivo, rodado duas vezes no
# mesmo motor, deu **458,54 m² e 177 m²**. E a temperatura já é 0 (conferido no
# /api/health): temperatura zero é decodificação gulosa, não garantia de
# determinismo. Não existe flag que conserte.
#
# 🔑 A conclusão que isso força: número que dá pra ler por REGRA não deveria ser
# lido por modelo de linguagem. O quadro de áreas é TEXTO dentro do DXF — o
# motor já extrai esses textos e os manda pro prompt. Ler daqui é determinístico
# e de graça.
#
# ⚠️ Isto NÃO substitui a IA: entra como mais uma leitura no consenso
# (`_pick_area_consensus`), que já agrupa por ±5% e tira a moda. Se o quadro não
# existir ou não casar, nada muda — o comportamento antigo continua.
_RE_AREA_QUADRO = _re.compile(
    r"(?ix)"
    r"\b(?:a|[áa]rea)\s*\.?\s*"                       # "A." ou "ÁREA"
    r"(total|constru[íi]da|constr\.?|do\s+terreno|terreno|[úu]til|privativa)?"
    r"\s*[:=]?\s*"
    r"([0-9][0-9\.,]{1,14})"                          # o número, formato pt-BR
    r"\s*(?:m2|m²|m\^2)\b"                            # exige a unidade
)

# Rótulos que NÃO são a área do projeto — terreno é o lote, não a construção.
_AREA_ROTULO_IGNORAR = ("terreno", "do terreno")


def areas_do_texto_da_prancha(textos):
    """Extrai candidatos a ÁREA TOTAL do texto da prancha, sem IA.

    Recebe uma lista de strings (os TEXT/MTEXT do DXF) e devolve lista de
    floats em m², já com o parser pt-BR único (`num_br_para_float`).

    🪤 Descarta 'área do terreno' de propósito: é o lote, não a obra — usar isso
    como área do projeto infla tudo que depende dela.
    🪤 Descarta valores absurdos (>1.000.000 m²), que em prancha normalmente são
    número de cota ou coordenada capturados por engano.
    """
    achados = []
    for t in (textos or []):
        s = str(t or "")
        if not s or "m" not in s.lower():
            continue
        for m in _RE_AREA_QUADRO.finditer(s):
            rotulo = (m.group(1) or "").strip().lower()
            if any(r in rotulo for r in _AREA_ROTULO_IGNORAR):
                continue
            v = num_br_para_float(m.group(2))
            if v and 1.0 <= v <= 1_000_000.0:
                achados.append(v)
    return achados


# ── Regra dos 100%: numa lista PLANA, o pai não pode ser irmão do filho ──────
#
# Princípio clássico de EAP/WBS: a soma dos filhos fecha o pai, e nenhum
# entregável aparece em dois ramos. A planilha do AI.arq é uma lista PLANA — não
# existe coluna de pai. Quando o motor entrega uma linha que É UM TOTAL ao lado
# das linhas que a compõem, quem soma a coluna conta DUAS VEZES o mesmo serviço.
#
# Medido em 08/08/2026 sobre 69 projetos reais (contas de teste fora):
#   7f7ef56a  "SUBTOTAL — Concreto C25/30 — Todas as sapatas"  12,4 m³ vs 2 sapatas  = 14,3 m³
#   66ebe2d9  "Armadura total de aço — peso total conforme"   362,7 kg vs 4 armaduras = 262,5 kg
#   1d995d72  "Quartos — área total dos quartos do pavimento" 124,4 m² vs 6 quartos   = 120,7 m²
#   d7c82c39  "Forro — ... área total"                        335,4 m² vs 1 parte     = 335,4 m² (idêntico)
#
# 🪤 Unidade "vb" fica DE FORA: verba é sempre 1, então "total=1 / parte=1" casa
#    sempre e não prova nada — eram 8 dos 17 casos brutos, todos ruído.
# 🪤 A palavra "geral" sozinha NÃO conta como total: "tomadas de uso geral" é
#    tipo de tomada, não somatório (falso positivo real, job 60837aaf).
# 🪤 Compara só entre IRMÃS de verdade — mesma unidade E mesma disciplina. Sem
#    isso, "área total" casaria com a soma de qualquer m² do projeto.
#
# A regra só APONTA. Quem aplica (main.py) rebaixa confirmado→estimado e escreve
# o aviso; NUNCA apaga, soma nem move quantidade — decidir qual das duas linhas
# fica seria adivinhar. Mesmo desenho de `is_unit_mismatch_countable`.

# 🪤 É `tota(?:l|is)`, NÃO `totais?` — "totais?" quer dizer "totai" + s opcional e
# nunca casa com "total". O teste da camada 1 pegou; a olho passaria batido.
_RE_LINHA_TOTAL = _re.compile(
    r"(?i)\b(?:sub\s*-?\s*)?tota(?:l|is)\b|\bsomat[óo]rios?\b|\bsoma\s+d[eoa]s?\b")

# Unidade sem grandeza: "1" casa com "1" e não prova nada.
UNIDADES_SEM_GRANDEZA = {"", "vb", "vb.", "verba", "cj", "cj.", "gl", "un.g"}


# ── Contagem de texto repetido: o número que a gente jogava fora ─────────────
#
# 🐛 O extrator fazia `set(textos)` antes de montar o prompt. Isso DESTRUÍA a
# contagem: se "Bebedouro" aparecia 7× na prancha, a IA via a palavra UMA vez e
# devolvia quantidade 0 — "Quantidade não indicada explicitamente".
#
# Medido em 08/08/2026 nos 69 projetos reais: **1.080 de 3.408 linhas zeradas
# (31,7%)**, e **514 delas (47,6%) já citavam a camada de origem**. Dessas, 468
# seguem exatamente este molde:
#     "Fonte: texto layer 'txt' — 'Bebedouro'. Quantidade não indicada."
# Ou seja: o motor sabia O QUÊ e ONDE, e mesmo assim entregou zero.
#
# 🔑 Regra da casa (08/08): número que dá pra CONTAR não pode depender de IA.
# Contar quantas vezes o texto aparece é determinístico — sai do arquivo.
#
# 🪤 Isto conta OCORRÊNCIA DE TEXTO, não objeto. Duas etiquetas podem apontar o
# mesmo equipamento, e um título se repete em toda prancha. Por isso entra no
# prompt como EVIDÊNCIA FORTE, nunca como verdade — a regra dura nº1 continua
# valendo: só vira "confirmado" o que foi medido na geometria.

# 🪤 Cota de nível repetida NÃO é contagem de objeto. Medido no DXF real
# AFP-AQ-LO-229 em 08/08: os 2 textos mais repetidos eram "+0,00" (×18) e
# "+0,01" (×18) — 18 marcações de nível, zero objetos. Se isso entrasse como
# evidência de quantidade, a IA criaria "18 unidades" do nada.
# 🪤 Aceita espaço NO MEIO: fragmento de cota vem como "4, 42" ou "6,28 32" e
# escapava do padrão antigo (`[\d.,]*` sem \s), casando com área de região.
_RE_SO_NUMERO = _re.compile(r"^[+\-±]?\s*\d[\d.,\s]*$")

# 🪤 Cabeçalho de quadro/legenda repete uma vez por linha da tabela e NÃO é item.
# Visto nas pranchas reais 0326.CGR e 0226.HWB em 08/08: "descrição" ×4,
# "legenda" ×4, "observações" ×4, "repr." ×4 — são as colunas do quadro.
# 🚨 Sem isto, o ×N que eu acabei de ligar PIORA o problema: antes a palavra
# aparecia solta; agora vem com "×4" do lado, parecendo quantidade.
# Só casa a palavra SOZINHA — "Descrição do forro" continua contando.
_CABECALHO_DE_QUADRO = {
    "descricao", "descricoes", "legenda", "legendas", "observacao", "observacoes",
    "obs", "repr", "representacao", "quantidade", "quant", "qtd", "qtde",
    "item", "itens", "unid", "unidade", "un", "und", "codigo", "cod",
    "referencia", "ref", "tipo", "nome", "area", "escala", "data", "folha",
    "prancha", "revisao", "rev", "total", "subtotal", "material", "acabamento",
}


def _sem_acento(s):
    _t = _ud.normalize("NFKD", str(s or ""))
    return "".join(c for c in _t if not _ud.combining(c))


def texto_conta_objeto(s):
    """False quando repetir o texto NÃO diz quantos objetos existem:
    (a) texto que é só número — cota, nível, elevação;
    (b) cabeçalho de quadro/legenda isolado — "Descrição", "Qtd", "Obs".
    True para rótulo de verdade ("LM1", "Bebedouro", "Porta PM2")."""
    t = " ".join(str(s or "").split())
    if _RE_SO_NUMERO.match(t):
        return False
    chave = _sem_acento(t).lower().strip(" .:;-–—()[]")
    return chave not in _CABECALHO_DE_QUADRO


def contar_textos_repetidos(texts, min_len=3):
    """Agrupa textos iguais (ignorando caixa e espaço repetido) e devolve
    [(forma_mais_comum, n)] ordenado por n DESC e depois alfabético.

    A ordem importa: quem corta a lista em N pega primeiro os mais repetidos —
    justamente os contáveis. Ordenar alfabeticamente (o que o código antigo
    fazia) descartava os repetidos por acaso da letra inicial.
    """
    grupos = {}
    for t in (texts or []):
        s = " ".join(str(t if t is not None else "").split())
        if len(s) < min_len:
            continue
        grupos.setdefault(s.casefold(), {})
        grupos[s.casefold()][s] = grupos[s.casefold()].get(s, 0) + 1

    saida = []
    for _k, formas in grupos.items():
        # forma mais frequente; empate resolve pela que vem antes, pra ser estável
        forma = sorted(formas.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        saida.append((forma, sum(formas.values())))
    saida.sort(key=lambda x: (-x[1], x[0].casefold()))
    return saida


# ── Unidade do item × unidade oficial do SINAPI ──────────────────────────────
#
# 🔑 A tabela `sinapi_composicao` tem 10.284 serviços com a UNIDADE OFICIAL de
# cada um, está no banco desde abril e nunca foi usada pra conferir nada. Quando
# a IA escolhe um código SINAPI cuja unidade é M2 e a nossa linha sai em `ml`,
# uma das duas está errada — e isso dá pra ver de graça.
#
# Medido em 09/08: 8,9% dos itens em m² tinham a unidade CONVERTIDA de `ml`/`un`
# pelo próprio motor ("Unidade ajustada de ml para m²"), ~6.971 m² fabricados.
#
# ⚖️ SÓ AVISA, nunca rebaixa nem corrige. Motivo: o conflito diz que UMA das
# duas está errada, não QUAL. O código SINAPI foi escolhido por IA e é o lado
# menos confiável — rebaixar puniria medição boa por causa de um match ruim.
# Mesma doutrina da calibração por densidade (regra dura nº3: ratio ALERTA).

# Grandeza de cada unidade. O que não está aqui é incomparável de propósito:
# 'vb'/'cj' (verba, conjunto) são coringas nossos, 'H'/'MES'/'CHP'/'CHI' são
# mão de obra e equipamento do SINAPI e nunca descrevem um item de prancha.
_GRANDEZA_DA_UNIDADE = {
    "m2": "area", "m²": "area", "m2.": "area", "m².": "area",
    "m3": "volume", "m³": "volume",
    "m": "comprimento", "ml": "comprimento", "mts": "comprimento",
    "metro": "comprimento", "metros": "comprimento", "m linear": "comprimento",
    "un": "contagem", "und": "contagem", "unid": "contagem", "pc": "contagem",
    "pç": "contagem", "peca": "contagem", "peça": "contagem",
    "kg": "massa", "t": "massa", "ton": "massa",
    "l": "capacidade", "lt": "capacidade", "litro": "capacidade",
}


def grandeza_da_unidade(u):
    """'m²'→'area', 'ML'→'comprimento', 'vb'→None (incomparável)."""
    return _GRANDEZA_DA_UNIDADE.get(" ".join(str(u or "").split()).lower())


def unidade_conflita_com_sinapi(unidade_item, unidade_sinapi):
    """True quando as duas descrevem GRANDEZAS diferentes (área × comprimento,
    contagem × área...). False quando batem, quando são a mesma grandeza, ou
    quando qualquer uma é incomparável — na dúvida, cala a boca."""
    a = grandeza_da_unidade(unidade_item)
    b = grandeza_da_unidade(unidade_sinapi)
    if not a or not b:
        return False
    return a != b


# ── O elo que faltava: o RÓTULO está dentro de QUAL região? ──────────────────
#
# 🔑 O motor sabia as duas metades e nunca as juntava:
#   "texto 'PISO CERÂMICO' no layer 'txt'"        → O QUÊ
#   "contorno fechado no layer 'ARQ' = 289,97 m²" → QUANTO
# Medido em 09/08: 1.080 de 3.408 linhas (31,7%) saem ZERADAS, e 514 delas já
# citam a camada de origem. O motor sabe o quê e onde, e entrega zero.
#
# É o mesmo mecanismo que os líderes chineses de 算量 usam (Glodon: 提取边线 +
# 提取标注 e cruza) e que o paper de Zhao et al. (Automation in Construction 180,
# 2025) mediu em 20.306/20.306 trechos com 1,83% de desvio.
#
# ⚖️ Aqui a regra só PROPÕE o par. Quem decide usar é o prompt — e a linha
# resultante sai `estimado`, nunca `confirmado`: o texto estar dentro da região
# é forte indício de que fala dela, não prova.

def casar_texto_com_regiao(textos, regioes, max_por_regiao=1, min_preenchimento=0.55):
    """Para cada região fechada, acha o texto que cai DENTRO dela.

    `textos`:  itens com `.position` (x, y) e `.text`/`.layer`
    `regioes`: itens com `.bbox` (x_min, y_min, x_max, y_max), `.area`, `.layer`

    Devolve [{area, layer_da_regiao, texto, layer_do_texto}] — só os pares.

    🪤 Casa com a MENOR região que contém o texto. Sem isso, o contorno do
    pavimento inteiro engoliria todos os rótulos e cada cômodo receberia a área
    do andar — erro pior que não medir.
    🪤 Região sem bbox fica de fora, não chuta.
    🪤 EXIGE PREENCHIMENTO (`min_preenchimento`): retângulo NÃO é a forma. Uma
    hachura em L, em anel ou espalhada tem um retângulo enorme que engole texto
    que não é dela — medido em 09/08 numa prancha real: "Sili da Silva" (nome no
    carimbo) casou com 982 m² e "proj. armário" com 2.768 m². Se a área real
    ocupa pouco do próprio retângulo, o retângulo não diz nada sobre o que está
    dentro. Fill = area / (largura × altura).
    🪤 Texto que não nomeia objeto (só número, cabeçalho de quadro) fica de fora
    — reusa `texto_conta_objeto`, a mesma trava da contagem de repetidos.
    """
    _regs = []
    for r in (regioes or []):
        b = getattr(r, "bbox", None) or (r.get("bbox") if isinstance(r, dict) else None)
        a = getattr(r, "area", None) if not isinstance(r, dict) else r.get("area")
        if not b or len(b) != 4 or not a or a <= 0:
            continue
        _pat = (getattr(r, "pattern", "") if not isinstance(r, dict) else r.get("pattern")) or ""
        _larg, _alt = float(b[2]) - float(b[0]), float(b[3]) - float(b[1])
        if _larg <= 0 or _alt <= 0:
            continue
        # 🪤 A trava do preenchimento: forma esparsa tem retângulo mentiroso.
        # 🚨 O valor vem PRONTO do extrator (`preenchimento`), NUNCA calculado
        # aqui: `area` está em m² e `bbox` na unidade crua do desenho — dividir
        # um pelo outro deu 0,000 em 310 de 310 hachuras reais. Se o campo não
        # existir (dado antigo/dict de teste), calcula pelo bbox assumindo que
        # as duas estão na mesma unidade.
        _fill = (getattr(r, "preenchimento", None) if not isinstance(r, dict)
                 else r.get("preenchimento"))
        if _fill is None:
            _fill = float(a) / (_larg * _alt)
        if float(_fill) < min_preenchimento:
            continue
        _regs.append((float(b[0]), float(b[1]), float(b[2]), float(b[3]), float(a),
                      (getattr(r, "layer", "") if not isinstance(r, dict) else r.get("layer")) or "",
                      "contorno fechado" if "contorno" in _pat.lower() else "hachura"))
    if not _regs:
        return []
    # menor primeiro: o cômodo ganha do pavimento
    _regs.sort(key=lambda z: (z[2] - z[0]) * (z[3] - z[1]))

    usados, pares = {}, []
    for t in (textos or []):
        p = getattr(t, "position", None) if not isinstance(t, dict) else t.get("position")
        s = (getattr(t, "text", "") if not isinstance(t, dict) else t.get("text")) or ""
        if not p or len(p) < 2 or not str(s).strip():
            continue
        # Só número ou cabeçalho de quadro não nomeia objeto — mesma trava da
        # contagem de repetidos. Mata par tipo "4, 42" → 31,87 m².
        if not texto_conta_objeto(s):
            continue
        x, y = float(p[0]), float(p[1])
        for i, (x0, y0, x1, y1, a, ly, orig) in enumerate(_regs):
            if x0 <= x <= x1 and y0 <= y <= y1:
                if usados.get(i, 0) >= max_por_regiao:
                    break
                usados[i] = usados.get(i, 0) + 1
                pares.append({
                    "area": round(a, 2),
                    "layer_da_regiao": ly,
                    "origem": orig,
                    "texto": " ".join(str(s).split())[:80],
                    "layer_do_texto": (getattr(t, "layer", "") if not isinstance(t, dict)
                                       else t.get("layer")) or "",
                })
                break
    return pares


# ══════════════════════════════════════════════════════════════════════
#  UNIDADE IMPERIAL EM PROJETO BRASILEIRO — desconfiar, nunca corrigir
#
# Medido em 10/08/2026 no `error_log` (stage motor:unidade): 9 pranchas
# declararam Polegadas — 7 da escola FNDE da Amanda (349e75a5) e 2 de outros
# clientes. As 7 da Amanda são TODAS as elétricas do projeto: não é arquivo
# estragado, é o template de elétrica do projetista saindo em polegada.
# Nas nove, `cotas=-`: nenhuma tinha cota pra confirmar nem desmentir o
# cabeçalho, e nenhuma foi corrigida.
#
# Escola pública brasileira não é desenhada em polegada. Se o desenho está em
# mm e a gente aplica 0,0254, cada medida sai 25,4× maior.
#
# 🚨 SÓ AVISA. Adivinhar "deve ser mm" seria copiar valor de outro contexto
# (regra dura nº3) — e é o mesmo tipo de conserto esperto que 3 céticos
# derrubaram em 10/08 no resgate da linha zerada. Quem prova escala é a cota da
# prancha; sem ela, quem decide é o cliente.
_IMPERIAIS_INSUNITS = {
    1: ("polegadas", 0.0254),
    2: ("pés", 0.3048),
    3: ("milhas", 1609.344),
    8: ("micropolegadas", 0.0000254),
    10: ("jardas", 0.9144),
}


def aviso_unidade_imperial(insunits, dim_status=None):
    """Frase de alerta quando o cabeçalho declara unidade imperial e as cotas
    NÃO provaram a escala. Devolve None quando não há o que avisar.

    `dim_status`: resultado da validação por cotas — 'validada' ou 'corrigida'
    significam escala provada, e aí não se avisa nada.
    """
    try:
        _ins = int(insunits)
    except (TypeError, ValueError):
        return None
    if _ins not in _IMPERIAIS_INSUNITS:
        return None
    if dim_status in ("validada", "corrigida"):
        return None
    nome, fator = _IMPERIAIS_INSUNITS[_ins]
    return (f"o cabeçalho do arquivo declara {nome} (unidade imperial) e a "
            f"prancha não tem cota que confirme a escala. Em projeto brasileiro "
            f"isso costuma ser configuração do CAD, não o desenho: se estiver "
            f"errado, as medidas desta prancha saem cerca de {fator / 0.001:.0f}× "
            f"maiores que o real. Confira a escala antes de orçar")


# ══════════════════════════════════════════════════════════════════════
#  SELO BRANCO COM QUANTIDADE ZERO — é contradição, não é medição
#
# 🚨 Regra dura nº1 pelo avesso. O BRANCO ("✓ MEDIDO do CAD") é a afirmação
# mais forte da planilha: este número saiu da geometria. Uma linha branca com
# quantidade 0 afirma duas coisas incompatíveis — que o motor mediu, e que o
# resultado é nada. O cliente lê "medido: 0" e conclui que o serviço não
# existe no projeto, quando a verdade é que a gente não conseguiu medir.
#
# Achado em 10/08/2026 no 1º projeto da Amanda (349e75a5, escola FNDE de 14
# pranchas): 4 linhas brancas com 0 — e a observação de cada uma CARREGAVA o
# número medido ("área de contorno fechado no layer ARQ-COBERTURA = 752,21
# m²"; "comprimento do layer 'EL-Condutos (Teto)' = 79,65 m"). O número se
# perdeu entre a medição e a coluna; o selo ficou para trás.
#
# 🪤 Não é só descuido do modelo. `_apply_area_honesty` (main.py:4337) zera a
# quantidade DE PROPÓSITO quando a área veio de Vision e não da geometria, e
# esse ramo não toca no selo — enquanto o ramo vizinho, que preenche, rebaixa
# pra estimado (linha 4327). Mas aquele caminho só olha unidade de ÁREA, e 3
# das 4 linhas da Amanda eram `ml`. Por isso a regra mora AQUI, no fim da
# esteira e valendo pra qualquer origem, em vez de remendar um por um os
# caminhos que zeram.
#
# 🚨 Esta regra NUNCA inventa número — tentar adivinhar a quantidade a partir
# da observação foi proposto em 10/08 e MORREU sob 3 céticos em dado real
# (ver `corrigir_comprimento_medido` e o bloco de _RE_BASE_DE_CALCULO). Aqui
# só se desfaz uma afirmação que o projeto não sustenta: cai o branco, a
# linha vira laranja "a confirmar", e a quantidade continua exatamente 0.
def selos_sem_medida(items):
    """Índices das linhas seladas como MEDIDAS que saíram sem quantidade.

    `items`: lista de dicts ou de objetos com confidence/quantity.
    Devolve lista de dicts {indice, descricao, unidade} — na ordem original.
    """
    achados = []
    for i, it in enumerate(items or []):
        selo = _campo_do_item(it, "confidence", "")
        selo = str(getattr(selo, "value", selo) or "").strip().lower()
        if selo != "confirmado":
            continue
        try:
            q = float(_campo_do_item(it, "quantity", 0) or 0)
        except (TypeError, ValueError):
            q = 0.0
        if q > 0:
            continue
        achados.append({
            "indice": i,
            "descricao": str(_campo_do_item(it, "description", "") or "")[:60],
            "unidade": str(_campo_do_item(it, "unit", "") or "").strip(),
        })
    return achados


def _campo_do_item(it, nome, padrao=""):
    """Lê o campo tanto de dict quanto de objeto (BudgetItem)."""
    v = it.get(nome, padrao) if isinstance(it, dict) else getattr(it, nome, padrao)
    return padrao if v is None else v


def linhas_pai_e_filho(items, tolerancia=0.35):
    """Acha a linha que é um TOTAL convivendo com as linhas que a compõem.

    `items`: lista de dicts ou de objetos com description/unit/quantity/discipline.
    Devolve lista de dicts — só os suspeitos, na ordem em que aparecem:
      {indice, descricao, unidade, quantidade, n_partes, soma_partes, folga,
       indices_partes}

    Dispara quando a soma das linhas IRMÃS (mesma unidade e mesma disciplina,
    sem a palavra "total") fica dentro de `tolerancia` do valor da linha-total.
    """
    norm = []
    for it in (items or []):
        desc = str(_campo_do_item(it, "description", "") or "")
        unidade = str(_campo_do_item(it, "unit", "") or "").strip().lower()
        try:
            q = float(_campo_do_item(it, "quantity", 0) or 0)
        except (TypeError, ValueError):
            q = 0.0
        disc = str(_campo_do_item(it, "discipline", "") or "").strip().lower()
        prancha = str(_campo_do_item(it, "ref_sheet", "") or "").strip().lower()
        norm.append((desc, unidade, q, disc, bool(_RE_LINHA_TOTAL.search(desc)), prancha))

    achados = []
    for i, (desc, unidade, q, disc, e_total, prancha) in enumerate(norm):
        if not e_total or q <= 0 or unidade in UNIDADES_SEM_GRANDEZA:
            continue
        partes = [(j, n) for j, n in enumerate(norm)
                  if j != i and n[1] == unidade and n[3] == disc and n[2] > 0 and not n[4]]
        # 🔑 PRANCHA PRIMEIRO (16/08/2026, caso Eduarda 42c354a1): o quadro de
        # aço tem UM total POR PRANCHA, e as partes dele são as bitolas DA
        # MESMA prancha. Misturar as 12 pranchas somava tudo contra cada total
        # e a folga estourava — 0 marcados em 71 linhas de kg com totais
        # óbvios. Se a mesma prancha tem partes, compara só com elas; senão,
        # cai no comportamento antigo (total geral do projeto).
        _mesma_prancha = [(j, n) for j, n in partes if prancha and n[5] == prancha]
        if _mesma_prancha:
            partes = _mesma_prancha
        if not partes:
            continue
        soma = sum(n[2] for _, n in partes)
        if soma <= 0:
            continue
        folga = abs(soma - q) / q
        if folga < tolerancia:
            achados.append({
                "indice": i,
                "descricao": desc,
                "unidade": unidade,
                "quantidade": q,
                "n_partes": len(partes),
                "soma_partes": round(soma, 2),
                "folga": round(folga, 3),
                "indices_partes": [j for j, _ in partes],
            })
    return achados


# ══════════════════════════════════════════════════════════════════════
#  ATRIBUTO DISTINTIVO — o que NUNCA pode ser fundido (regra dura nº4)
# ══════════════════════════════════════════════════════════════════════
# 🚨 Por que existe (17/08/2026, caso Eduarda): a passada 2 do
# `_consolidate_items` funde dois itens quando as descrições têm >= 2
# palavras em comum. Em projeto ESTRUTURAL toda linha compartilha
# "armadura" + "vigas" — então Ø8, Ø12,5 e Ø16 caíam na mesma família e a
# linha fundida ficava com a quantidade de UMA só.
#
# Medido em bancada com o padrão real (12 pranchas × 6 bitolas):
#   72 linhas / 18.168 kg  ->  1 linha / 508 kg   (97% da obra evaporou)
#
# Bitola é atributo que muda a COMPRA: aço Ø8 e Ø16 são materiais
# diferentes, com preço e dobra diferentes. Fundir viola a regra dura nº4
# ("cor, PD, tipo específico nunca somem porque afetam compra real") e
# ainda entrega um número que não corresponde a nada (regra nº1).
#
# Esta função extrai os atributos que IDENTIFICAM o item dentro da
# família. Se dois itens têm atributos distintos e não-vazios, eles NÃO
# são duplicata um do outro — seja qual for a semelhança do texto.

# 🪤 1ª versão comparava por INTERSEÇÃO de todos os atributos juntos — e
# "CA-50" em comum fazia Ø8 e Ø16 parecerem o mesmo item (o teste pegou).
# O certo é comparar POR CATEGORIA: bitola com bitola, classe com classe.
# Mesma categoria + valor diferente = item diferente, ponto.
_ATRIB_POR_CATEGORIA = (
    # bitola/diâmetro — a que motivou tudo (aço Ø8 ≠ aço Ø16)
    ("bitola", (
        _re.compile(r"(?:ø|\bo\b|diam[eê]tro|diam|bitola)\s*(\d{1,3}(?:[.,]\d)?)\s*mm", _re.I),
        _re.compile(r"ø\s*(\d{1,3}(?:[.,]\d)?)", _re.I),
    )),
    # classe do aço: CA-50 ≠ CA-60 (materiais diferentes, preço diferente)
    ("classe_aco", (_re.compile(r"\bca[\s\-]?(\d{2})\b", _re.I),)),
    # resistência do concreto: fck 25 ≠ fck 30
    ("fck", (_re.compile(r"\bfck\s*(\d{2,3})\b", _re.I),)),
    # dimensão: 10x10 ≠ 25x15
    ("dimensao", (_re.compile(r"\b(\d{1,3}(?:[.,]\d{1,2})?\s*[x×]\s*\d{1,3}(?:[.,]\d{1,2})?)\b", _re.I),)),
    # código de projeto/legenda: LM1 ≠ LM2, P3 ≠ P7
    # código de projeto/legenda. 🪤 Aceita HÍFEN e prefixo de 2 letras: sem
    # isso "Porta de madeira PM-01" e "Porta de vidro PV-01" fundiam numa linha
    # só — bug PRÉ-EXISTENTE que o controle negativo desta correção revelou.
    # Inclui V\d (viga) e P\d (pilar): "vigas V1 a V12" e "vigas V13 a V31" são
    # trechos DIFERENTES da obra e não devem ser deduplicados entre si.
    ("codigo", (_re.compile(
        r"\b((?:pm|pv|pe|lm|ln|lum|dry|dw|div|pd|ve|vm|p|j|v)[\s\-]?\d{1,3})\b",
        _re.I),)),
)


def atributos_distintivos(desc: str) -> dict:
    """{categoria: valor} dos atributos que IDENTIFICAM o item na família.

    Categorias: bitola, classe_aco, fck, dimensao, codigo. Vazio = nada
    distintivo (a fusão segue as regras antigas).
    """
    out = {}
    if not desc:
        return out
    s = str(desc)
    for cat, regexes in _ATRIB_POR_CATEGORIA:
        for rx in regexes:
            m = rx.search(s)
            if m:
                v = (m.group(1) or "").strip().lower()
                v = _re.sub(r"\s+", "", v).replace(",", ".")
                v = v.lstrip("0") or "0"
                if v:
                    out[cat] = v
                break
    return out


def pode_fundir(desc_a: str, desc_b: str) -> bool:
    """False quando os dois itens têm a MESMA categoria com valor DIFERENTE.

    🪤 Categoria presente em só um dos dois não bloqueia: "Armadura — total"
    (sem bitola) continua fundível com qualquer irmã pelas regras antigas —
    senão isto viraria um "nunca funde" e desfaria consolidação legítima
    (réplica por departamento, variante de legenda).
    """
    a, b = atributos_distintivos(desc_a), atributos_distintivos(desc_b)
    for cat in set(a) & set(b):
        if a[cat] != b[cat]:
            return False
    return True
