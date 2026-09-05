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


def detectar_laco_repeticao(texto: str, tokens_saida: int = 0) -> dict:
    """A IA entrou em laco de repeticao e queimou a resposta inteira?

    🚨 26/08/2026, caso Amanda (job 43a799c0). De 4 pranchas, 1 chegou na
    planilha. Duas devolveram ZERO item com stop=max_tokens -- e o log dizia
    `perdidos=0`. O que a IA escrevia:

        RACIOCINIO: Passo 1 - Inventario de layers: ... [15 mil chars corretos]
        +1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1
        [ate esgotar os 32.000 tokens -- nunca emite o JSON]

    Ela soma bloco por bloco porque o conversor da um nome por INSTANCIA
    (1.570 nomes pra 1.570 pecas), e `temperature=0` -- decodificacao gulosa --
    nao deixa escapar do laco.

    🔑 DOIS SINAIS, porque um so engana:
      1. DENSIDADE. "+1" e UM token de dois caracteres, entao a resposta fica
         com ~1,05 caractere por token contra 2,5 a 3,0 de texto normal.
         Medido: laco 1,03/1,05/1,06/1,08 | normal 2,46/2,47/2,53/2,57/2,64.
         A separacao e limpa e nao depende de saber QUAL padrao se repete.
      2. REPETICAO LITERAL, no fim do texto (e onde o laco mora).

    🪤 Densidade sozinha nao basta: resposta legitima cheia de numero tambem
    tokeniza denso. Repeticao sozinha tambem nao: lista JSON tem estrutura
    repetida por natureza. Exigir OS DOIS e o que separa.

    🪤 Isto NAO conserta o laco -- so o torna visivel. E o laco e NOVO: as 4
    unicas ocorrencias do acervo sao de 26/08, todas do mesmo cliente. As
    leituras de 24/08 com `stop=max_tokens` sao OUTRO defeito -- cortaram no
    teto e mesmo assim entregaram 112, 156 e 162 itens. Mesmo sintoma, causa
    diferente; por isso o detector olha densidade e repeticao, nao o stop.

    Devolve {"laco": bool, "padrao": str, "repeticoes": int, "densidade": float}.
    """
    t = texto or ""
    fora = {"laco": False, "padrao": "", "repeticoes": 0, "densidade": 0.0}
    if len(t) < 2000:
        return fora
    densidade = len(t) / float(tokens_saida) if tokens_saida else 0.0

    # maior corrida de um padrao curto NO FIM do texto (onde o laco mora)
    cauda = t[-3000:]
    melhor_pad, melhor_rep = "", 0
    for tam in range(1, 9):
        pad = cauda[-tam:]
        if not pad.strip():
            continue
        n = 0
        i = len(cauda)
        while i - tam >= 0 and cauda[i - tam:i] == pad:
            n += 1
            i -= tam
        if n > melhor_rep:
            melhor_pad, melhor_rep = pad, n

    # 60 repeticoes de um padrao de <=8 chars = ~500 chars da mesma coisa.
    # Lista JSON legitima nao faz isso: os valores mudam.
    repetindo = melhor_rep >= 60
    denso = 0 < densidade <= 1.8     # medido: laco <=1,08 | normal >=2,46

    fora.update({"laco": bool(repetindo and (denso or tokens_saida == 0)),
                 "padrao": melhor_pad, "repeticoes": melhor_rep,
                 "densidade": round(densidade, 2)})
    return fora


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


# ── ESCALA DIVERGENTE ENTRE PRANCHAS DO MESMO JOB (regra nº1) ──────────────
# Um prédio tem UMA unidade. Se as pranchas do mesmo job resolvem pra fatores
# que diferem 100× ou 1000×, pelo menos uma está errada e não se sabe qual.
# Réguas que PROVAM a escala (cota do próprio desenho, ou rótulo de área que
# bate com a geometria). Plausibilidade e DIMLFAC são inferência, não prova.
REGUAS_QUE_PROVAM = ("validada", "corrigida", "corrigida_lfac", "provada_por_rotulo")

# Abaixo disto é ruído de arredondamento; 10× já é erro de unidade inteira.
DIVERGENCIA_MINIMA = 10.0

# Unidades cujo número depende da ESCALA do desenho. Contagem ('un', 'pç') NÃO
# entra: contar bloco não depende de escala — decisão deliberada de 17/08.
UNIDADES_DE_ESCALA = ("m", "m²", "m2", "m³", "m3", "ml", "cm", "mm", "km", "m.l")


def escala_divergente(escalas):
    """As pranchas do mesmo job discordam da unidade entre si?

    `escalas`: lista de dicts {prancha, fator, regua, unidade}.
    Devolve (divergiu, pranchas_suspeitas:set, resumo:str).

    🪤 Só APONTA. Quem rebaixa selo é o chamador — e só rebaixa, nunca promove.

    Regra: se alguma prancha PROVOU a escala por cota, esse fator é a verdade e
    quem discorda dele é suspeito. Se nenhuma provou, ninguém é confiável e
    todas entram — porque aí não há árbitro.
    """
    val = [e for e in (escalas or [])
           if isinstance(e, dict) and (e.get("fator") or 0) > 0]
    if len(val) < 2:
        return (False, set(), "")
    fatores = sorted({round(float(e["fator"]), 9) for e in val})
    if len(fatores) < 2 or fatores[-1] / fatores[0] < DIVERGENCIA_MINIMA:
        return (False, set(), "")

    provadas = [e for e in val if str(e.get("regua") or "") in REGUAS_QUE_PROVAM]
    fat_provados = {round(float(e["fator"]), 9) for e in provadas}
    if len(fat_provados) == 1:
        verdade = fat_provados.pop()
        suspeitas = {e["prancha"] for e in val
                     if round(float(e["fator"]), 9) != verdade}
        motivo = ("%d prancha(s) provaram a escala por cota (fator %s) e %d "
                  "discordam" % (len(provadas), verdade, len(suspeitas)))
    else:
        # nenhuma provou, ou as provadas discordam entre si: sem árbitro
        suspeitas = {e["prancha"] for e in val}
        motivo = ("nenhuma prancha provou a escala por cota — não há como saber "
                  "qual das %d leituras está certa" % len(fatores))

    resumo = ("As pranchas deste projeto foram lidas em escalas diferentes "
              "(fatores %s — diferença de %.0f×). %s."
              % (", ".join(str(f) for f in fatores),
                 fatores[-1] / fatores[0], motivo))
    return (True, suspeitas, resumo)


def item_e_de_escala(unidade) -> bool:
    """A quantidade deste item depende da escala do desenho?"""
    u = str(unidade or "").strip().lower().replace(" ", "")
    return u in UNIDADES_DE_ESCALA


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
# Subconjunto: COMPRIMENTO. Está dentro de AREA_UNITS_HONESTY (a peneira de
# honestidade vale igual pra metro linear chutado), mas NÃO é área — e a
# mensagem que o cliente recebe quando a linha é zerada precisa saber a
# diferença. 🩸 01/09/2026: 25 itens lineares do job 144c1f04 (rodapé, soleira,
# tubulação frigorígena, perfil de LED) saíram com "Área NÃO medida ... informe
# a área no upload" — substantivo errado e conselho que não resolve nada pra
# quem precisa de METRO.
# 🪤 NÃO chamar isto de LINEAR_UNITS: esse nome JÁ EXISTE mais abaixo (linha
# ~439) e é uma coisa diferente — uma tupla que inclui m², m2, m³ e m3, usada
# pela normalização de unidade. Eu tropecei nisso hoje: defini LINEAR_UNITS
# aqui, o de baixo sobrescreveu calado (mesmo módulo, quem vem depois vence), e
# item de m² passou a receber a frase de comprimento. Quem pegou foi o CONTROLE
# do teste — o que testa o caminho que estava CERTO.
UNIDADES_SO_COMPRIMENTO = {"ml", "m"}
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

# 🩸 31/08/2026 (caso Flavio, job f271473f): "Rasgo em laje de concreto armado
# para implantação de nova escada" herdou a ÁREA TOTAL informada pelo cliente e
# saiu com 400 m² — um vão de escada caracol. São palavras do ATO de intervenção
# parcial: o item MENCIONA laje/piso, mas cobre um recorte, não a superfície.
# 🪤 NÃO acrescentar "escada" nem "corte": `is_floor_surface("Piso da escada em
# granito")` é True e ISSO ESTÁ CERTO — piso de escada é superfície. Bloquear o
# OBJETO derrubaria o caso legítimo; bloqueia-se o ATO.
#
# 🚨 31/08, AUDITORIA DO MESMO DIA: estas palavras nasceram DENTRO de
# FLOOR_AREA_BLOCK_KW, e essa lista é compartilhada por três ramos da
# honestidade — dois que CRIAM número e um que PRESERVA medição nossa. O
# resultado foi apagar dado medido: o item real do job eva97d1d (Construtora
# Mr, 26/08) "Remoção de revestimento cerâmico existente em piso", 13,60 m²
# MEDIDOS da geometria do PDF, passou a sair ZERADO — e com a linha dizendo as
# duas coisas ao mesmo tempo ("Medido da GEOMETRIA do PDF" + "Área NÃO
# medida"), que é exatamente a frase falsa que o conserto de 26/08 nasceu pra
# matar. 1 dos 16 itens que aquele ramo já salvou na história.
# 🔑 A REGRA: bloquear o ato de intervenção só vale onde a gente vai INVENTAR
# um número a partir de uma declaração (área informada pelo cliente, medição da
# prancha). Onde já existe medição NOSSA, um "rasgo" de 13,6 m² medidos é
# 13,6 m² — a palavra na descrição não desmente a régua.
FLOOR_ATO_PARCIAL_KW = (
    "rasgo", "abertura", "vão", "vao", "furo", "recorte", "demoli", "remoç",
    "remoc", "shaft",
)


def is_floor_surface(desc):
    """True se a descrição é uma SUPERFÍCIE horizontal que cobre ~a área toda
    (piso/forro/laje/teto) — não um item pontual, linear ou de cômodo específico.
    Heurística por palavra-chave; a medição real só vem da geometria do CAD.
    Ver _apply_area_honesty em main.py e os testes em test_engine_rules.py."""
    d = (desc or "").lower()
    return (any(k in d for k in FLOOR_AREA_KW)
            and not any(b in d for b in FLOOR_AREA_BLOCK_KW))


def is_floor_surface_para_criar(desc):
    """Como `is_floor_surface`, MAIS a peneira do ato de intervenção parcial.

    Use esta onde o motor vai ESCREVER um número que não existia — a área que o
    cliente declarou, ou a medição da prancha atribuída a um item zerado. Um
    "rasgo em laje" não recebe a área do pavimento.

    🚫 NÃO use onde o número JÁ EXISTE e só está sendo preservado: ali a palavra
    na descrição não desmente uma medição nossa, e bloquear APAGA dado (ver o
    comentário de FLOOR_ATO_PARCIAL_KW acima).
    """
    d = (desc or "").lower()
    return is_floor_surface(d) and not any(b in d for b in FLOOR_ATO_PARCIAL_KW)


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
    return tipo_de_conflito_de_unidade(unidade_item, unidade_sinapi) is not None


# Grandezas em que NOSSO lado é o suspeito: medir comprimento, área ou volume
# é afirmar uma dimensão do desenho. Contar não é — contar é sempre uma base
# legítima, e o SINAPI só usa outra pra precificar.
_NOSSAS_GRANDEZAS_DIMENSIONAIS = ("comprimento", "area", "volume")


def tipo_de_conflito_de_unidade(unidade_item, unidade_sinapi):
    """Que TIPO de divergência é esta? `None` = nenhuma.

    Devolve `"base"` quando as duas medidas são plausíveis e só diferem de
    base (a gente CONTA janela, o SINAPI PRECIFICA por m²), ou `"grandeza"`
    quando o lado suspeito é o NOSSO — medimos uma dimensão que não é a do
    serviço.

    🩸 04/09/2026, do 1º projeto da Caroline (Bolognesi). Ela recebeu, e
    apagou em 3 minutos, uma linha com a nossa própria observação:

        "⚠ CONFERIR A UNIDADE: o serviço SINAPI 103689 é medido em M2, e
         esta linha saiu em un. Uma das duas está errada."

    🔑 MEDIDO na base: **160 itens, 39 projetos, 29 clientes** receberam esse
    aviso. E **89 deles (56%) são FALSO ALARME** — "Janela maxim-ar, 46 un"
    contra M2, "Bloco cerâmico, un" contra M2, "Estaca, 187 un" contra M.
    Contar janela está certo; a SINAPI é que precifica por área. Nenhuma das
    duas está errada, e a gente afirmava que uma estava.

    🪤 Alarme que grita 56% à toa é [[alarme sem controle]]: ensina o cliente a
    ignorar — e dilui os **27 casos reais** (11 clientes), que são justamente
    os "Ripas de madeira 1,18 ml" contra M2, onde a gente pegou o comprimento
    de um layer e chamou de item de área.

    🪤 A assimetria NÃO é "contagem nunca conflita". É quem mediu: se NÓS
    dissemos comprimento/área/volume e o serviço é de outra grandeza, o número
    é de outra coisa. Se nós CONTAMOS, contar é base legítima pra qualquer
    item físico. Conferido contra a matriz inteira do banco antes de escrever.
    """
    _a = grandeza_da_unidade(unidade_item)
    _b = grandeza_da_unidade(unidade_sinapi)
    if not _a or not _b or _a == _b:
        return None
    if _a in _NOSSAS_GRANDEZAS_DIMENSIONAIS:
        return "grandeza"
    return "base"


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


# Provas de que a quantidade saiu da GEOMETRIA do desenho (o que autoriza o selo
# branco "✓ MEDIDO do CAD"). São as frases que o próprio motor escreve quando
# mede: hachura, INSERT de bloco, comprimento de layer, polilinha.
_PROVA_GEOMETRIA = (
    "hachura", "insert", "contagem de blocos", "polilinha", "polyline",
    "comprimento do layer", "comprimento total do layer", "somatória de linhas",
    "somatoria de linhas", "área hachurada", "area hachurada",
    # 🚨 29/08/2026 — FALTAVAM TRÊS, e o guarda acusava medição de verdade.
    #
    # Achado ao conferir os 81 que a rota `/api/admin/selo-historico` aponta:
    # "Condutos no teto — Fonte: layer 'EL-Condutos (Teto)' = 9,92 m" estava na
    # lista de acusados. Isso é comprimento de layer, é geometria pura.
    #
    # 🔑 Os nomes abaixo são os TÍTULOS DAS SEÇÕES que o próprio extrator
    # escreve no prompt (dwg_extractor.py:327, :345, :419) — é literalmente o
    # texto que a IA copia quando cita a fonte. Guarda que não conhece o
    # vocabulário do próprio motor acusa o motor de inventar.
    #
    # 🪤 Guarda que acusa errado é ignorado, e aí para de proteger. O custo do
    # falso positivo aqui não é teórico: 81 itens de 21 clientes dependem deste
    # número pra virar (ou não) uma decisão de rebaixamento retroativo.
    "comprimentos por layer", "atributo de bloco", "atributos do bloco",
    "atributos de bloco",
)

# 🪤 "layer" sozinho NÃO serve como prova: "Fonte: texto layer 'ARQ-TEXTO 1'"
# é justamente o caso de 24/08 que criou este guarda. O que prova é a forma
# de MEDIÇÃO — layer seguido de um valor com unidade:
#     "layer 'EL-Condutos (Teto)' = 9.92 m"     → mediu
#     "texto layer 'ARQ-TEXTO 1': 'AREA = ...'"  → leu texto
# 🪤 `re` NÃO existe com esse nome aqui — o módulo usa `import re as _re`.
# Escrevi `re.compile` e o pyflakes barrou. Mesma família do `re.sub` sem import
# que derrubou o deploy em 21/08 e criou a regra de rodar pyflakes antes do
# push. Terceira aparição do mesmo erro; a regra pegou nas três.
_PROVA_LAYER_MEDIDO = _re.compile(
    r"(?<!texto\s)layer\s*['\"‘’][^'\"‘’]{1,60}['\"‘’]\s*=\s*[\d.,]+\s*(m²|m2|m³|m3|ml|m\b|un\b)",
    _re.IGNORECASE)

# Procedências que são LEITURA DE TEXTO — legítimas como estimativa, nunca como
# medição. O projetista escreveu um número na prancha; a gente não mediu nada.
_PROCEDENCIA_TEXTO = (
    "texto", "carimbo", "legenda", "rótulo", "rotulo", "tabela", "quadro",
)

# 🚨 29/08/2026 — A EXCEÇÃO DO QUADRO DE AÇO, e por que ela NÃO é um furo.
#
# O caso que criou este guarda em 24/08 foi de MÁ ATRIBUIÇÃO, não de leitura:
# "AREA TOTAL CLINICA = 264,54 m²" colado na linha "Piso — revestimento". O
# número era real; a gente é que ADIVINHOU a que item ele pertencia.
#
# 🔑 A linha que separa os dois casos:
#   • TABELA COM COLUNAS ROTULADAS — o desenho diz o que cada número é. A
#     coluna BITOLA diz a bitola, a COMPR diz o comprimento, a PESO diz o peso.
#     Não há adivinhação de atribuição.
#   • TEXTO SOLTO — nós chutamos a que item a frase se refere. É o caso de 24/08.
#
# E o quadro de aço tem duas conferências que texto solto nunca tem:
#   (a) cada linha contra a massa linear da NBR 7480 (comp × kg/m ≈ peso);
#   (b) a soma das bitolas contra o TOTAL declarado na própria prancha.
#
# ⚖️ E o argumento decisivo: geometria NÃO CONSEGUE pesar armadura — a prancha
# não desenha barra por barra. Exigir geometria aqui significaria que aço NUNCA
# poderia ser medido, em nenhum projeto, nunca. O selo que a planilha promete é
# "✓ MEDIDO do CAD", e este peso veio do CAD. Chamá-lo de "⚠ ESTIMADO" seria
# MENOS honesto: não é estimativa nossa, é o número que o engenheiro calculou.
#
# 🔒 A exceção é ESTREITA de propósito: só o quadro/resumo de aço, nomeado.
# Qualquer outra procedência de texto continua sendo acusada.
_QUADRO_DE_ACO = (
    "quadro/resumo de aço", "quadro de aço", "resumo de aço",
    "quadro/resumo de aco", "quadro de aco", "resumo de aco",
    "quadro de ferragens", "quadro de ferro",
)


def quantidades_da_geometria(items):
    """Quantas linhas têm QUANTIDADE que saiu da geometria do desenho.

    🩸 03/09/2026 — A DOENÇA QUE ISTO CURA, EM CINCO LUGARES DE UMA VEZ.
    O motor contava `confidence == 'confirmado'`, achava zero, e escrevia ao
    cliente que **"os números vieram de texto lido das pranchas"**. São dois
    fatos diferentes:
      • SELO zero  = nenhum item passou na conferência que libera o branco;
      • ORIGEM     = de onde a quantidade saiu.
    O job `b5ce23ff` (EDVALDO, maior lead B2B) prova que dá pra ter selo zero
    com geometria medida: 90,86 m² de laje saíram de **hachura do layer LAJE**
    e 169,83 m de viga saíram do **comprimento das linhas do layer VIGA**, e
    ele leu que a planilha dele era transcrição de legenda.

    🔑 Afirmar procedência sem olhar a procedência é a regra dura nº1 pelo
    avesso: lá é "não diga MEDIDO sem medir"; aqui é "não diga QUE NÃO MEDIU
    sem olhar". Os dois erram sobre a mesma coisa — a origem do número.

    Usa o MESMO critério de `selos_sem_geometria` (`_PROVA_GEOMETRIA` e
    `_PROVA_LAYER_MEDIDO`), porque duas definições de "veio da geometria" numa
    casa só é como ter duas balanças.

    🪤 Exige `quantity > 0`. Observação que CITA hachura numa linha zerada não é
    quantidade tirada de hachura — o item "Escada — Fôrma" do mesmo job diz
    "área hachurada" e no texto seguinte "NÃO calculada".

    Devolve -1 quando não deu pra contar. Nunca 0 por engano: quem chama usa o
    -1 pra CALAR sobre origem, e calar é melhor que afirmar errado.
    """
    try:
        n = 0
        for it in (items or []):
            try:
                q = float(_campo_do_item(it, "quantity", 0) or 0)
            except (TypeError, ValueError):
                q = 0.0
            if q <= 0:
                continue
            obs = str(_campo_do_item(it, "observations", "") or "").lower()
            if any(p in obs for p in _PROVA_GEOMETRIA) or _PROVA_LAYER_MEDIDO.search(obs):
                n += 1
        return n
    except Exception:
        return -1


def selos_sem_geometria(items):
    """Índices das linhas seladas como MEDIDAS cuja procedência é só TEXTO.

    🚨 24/08/2026: medido no acervo, 61 itens em 19 projetos de 15 clientes
    saíram com "✓ MEDIDO do CAD" tendo como fonte apenas um texto lido da
    prancha — 33.962 m² entre eles. Exemplos reais entregues:
      • "Fonte: texto layer 'ARQ-TEXTO 1': 'AREA TOTAL CLINICA = 264,54 m²'"
        colado na linha "Piso — revestimento de piso interno" (o total do prédio
        virou a metragem de um acabamento);
      • "Conforme legenda código 06 — área APROXIMADA explícita" com selo de
        medido.
    Ler a quantidade da legenda é comportamento documentado e desejado; o que
    não pode é ela usar o selo que o produto reserva para a geometria.

    Só REBAIXA. Nunca promove nada — na dúvida, o item continua como está.
    Devolve [{indice, descricao, unidade, motivo}].
    """
    achados = []
    for i, it in enumerate(items or []):
        selo = _campo_do_item(it, "confidence", "")
        selo = str(getattr(selo, "value", selo) or "").strip().lower()
        if selo != "confirmado":
            continue
        obs = str(_campo_do_item(it, "observations", "") or "").lower()
        # 🚨 29/08/2026 — ESTE ATALHO DESLIGAVA O GUARDA PRA TODO O CAMINHO DXF.
        #
        # `main.py` carimbava `origem="dxf_geom"` em TODO item vindo de DXF, sem
        # olhar de onde a quantidade saiu. Como a primeira linha deste laço era
        # "origem dxf_geom fecha a questão", o guarda pulava o caminho inteiro —
        # ele só funcionava de fato para itens de PDF.
        #
        # 📊 Medido no acervo: 492 itens confirmados com esse rótulo, e 46 deles
        # com procedência SÓ de texto (38 do aço, 8 outros em 5 projetos de
        # cliente). Esses 8 eram vazamento silencioso desde 24/08.
        #
        # 🔑 Agora a origem só ABSOLVE quando o próprio texto confirma geometria.
        # Rótulo não é prova; a frase que o motor escreveu quando mediu é.
        if (str(_campo_do_item(it, "origem", "") or "").strip().lower() == "dxf_geom"
                and any(p in obs for p in _PROVA_GEOMETRIA)):
            continue
        if not obs:
            continue                     # sem procedência escrita: não acusa
        if any(p in obs for p in _PROVA_GEOMETRIA):
            continue                     # mediu de verdade
        if _PROVA_LAYER_MEDIDO.search(obs):
            continue                     # "layer 'X' = 9,92 m" é medição
        # ⚖️ Quadro de aço: tabela com colunas rotuladas, conferida contra a NBR
        # e contra o total da prancha. Ver o comentário longo em _QUADRO_DE_ACO.
        if any(p in obs for p in _QUADRO_DE_ACO):
            continue
        if not any(p in obs for p in _PROCEDENCIA_TEXTO):
            continue                     # não sabemos o que é: não acusa
        achados.append({
            "indice": i,
            "descricao": str(_campo_do_item(it, "description", "") or "")[:60],
            "unidade": str(_campo_do_item(it, "unit", "") or "").strip(),
            "motivo": "procedência é leitura de texto, não medição da geometria",
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


# ══════════════════════════════════════════════════════════════════════
#  RESSALVA POR DIMENSÃO — nem toda ressalva atinge todo item
# ══════════════════════════════════════════════════════════════════════
# 🚨 Por que existe (17/08/2026): `extraction_has_quality_caveat` é
# tudo-ou-nada. Uma ressalva de UNIDADE (escala suspeita, corrigida por
# plausibilidade) rebaixa TODOS os itens do DXF pra estimado — inclusive
# CONTAGEM DE BLOCO, que não depende de escala nenhuma: 32 janelas são 32
# INSERTs contados, meça-se em milímetro ou em milha.
#
# Custo medido nos últimos 30 dias: de 1.090 linhas em `un`, só 28% saem
# medidas — e parte disso é contagem legítima rebaixada por ressalva de
# escala. No arquivo do Giovani, as 32 janelas e as 4 geladeiras viraram
# estimado por causa do cabeçalho mentiroso, que não tem nada a ver com
# contar bloco.
#
# 🪤 As outras ressalvas CONTINUAM valendo pra tudo:
#   - extração estéril (0 medições) → nada é confiável, nem contagem;
#   - xref não resolvido → a geometria contada pode estar incompleta;
#   - duto com medição suspeita → é sobre comprimento, mas o item é de duto.
# Só a de UNIDADE é dimensional por natureza.

_UNIDADES_QUE_DEPENDEM_DE_ESCALA = {
    "m", "ml", "m²", "m2", "m³", "m3", "km", "cm", "mm",
}

_RESSALVAS_SO_DE_ESCALA = ("unidade_suspeita", "alerta_unidade")


def caveat_atinge_unidade(metadata, unidade: str) -> bool:
    """A ressalva desta extração impede confirmar um item DESTA unidade?

    - Sem ressalva nenhuma → False.
    - Ressalva NÃO-dimensional (estéril, xref, duto) → True pra qualquer item.
    - Ressalva SÓ de escala → True apenas pra unidade que depende de escala
      (m, m², m³ e afins). Contagem (`un`), peso (`kg`), verba (`vb`) e tempo
      (`mês`) passam — não se medem com régua.
    """
    if not metadata:
        return False
    _outras = bool(
        metadata.get("extracao_esteril")
        or metadata.get("xref_nao_resolvido")
        or metadata.get("duto_medicao_suspeita")
    )
    if _outras:
        return True
    _so_escala = any(metadata.get(k) for k in _RESSALVAS_SO_DE_ESCALA)
    if not _so_escala:
        return False
    return (unidade or "").strip().lower() in _UNIDADES_QUE_DEPENDEM_DE_ESCALA


# ══════════════════════════════════════════════════════════════════════
#  5ª RÉGUA — o rótulo de área que BATE com a geometria prova a unidade
# ══════════════════════════════════════════════════════════════════════
# 🚨 Descoberta em 17/08/2026 no arquivo do Giovani (75a774af), depois de
# corrigir a unidade por plausibilidade. O pareamento rótulo↔região devolveu:
#
#     "57,16m²"  →  hachura mede  57.16 m²
#     "55,49m²"  →  hachura mede  55.49 m²
#     "62,70m²"  →  hachura mede  62.70 m²
#     "60,87m²"  →  hachura mede  60.87 m²
#
# O número que o PROJETISTA escreveu e o que a GEOMETRIA mede, batendo na
# segunda casa decimal, em quatro ambientes. Isso é a mesma natureza de prova
# da régua das cotas — dado escrito × dado medido — e é a prova mais forte de
# unidade que existe num DXF: se a escala estivesse errada por 10×, 100× ou
# 1000×, nenhum par bateria.
#
# 💰 Por que importa: medido em 30 dias, de 492 linhas em m² só 2 saíram
# MEDIDAS (0,4%). Contar bloco funciona (28%); medir superfície não. Esta é a
# única evidência que vi capaz de virar esse número — e m² é o que o
# orçamentista mais usa (piso, forro, pintura, revestimento).
#
# 🚨 Ela PROMOVE pra 'confirmado' — a direção perigosa da regra nº1. Por isso
# as travas são duras: mínimo de 2 pares independentes, tolerância apertada,
# e o rótulo tem que ser inequivocamente uma ÁREA (traz "m²" escrito).

_RE_ROTULO_AREA = _re.compile(
    r"^\s*(\d{1,5}(?:[.,]\d{1,2})?)\s*(?:m²|m2|M²|M2)\s*$")

_AREA_MIN_PARES = 2       # 1 par pode ser coincidência; 2 independentes, não
_AREA_TOL = 0.02          # ±2%, mesma régua das cotas
_AREA_MIN_M2 = 1.0        # ambiente menor que 1 m² não serve de prova


def rotulo_area_como_numero(texto: str):
    """Número (em m²) de um rótulo que é INEQUIVOCAMENTE uma área.

    Exige o "m²" escrito: "57,16m²" → 57.16. "57,16" sozinho devolve None —
    poderia ser cota, nível, código. Sem ambiguidade não há prova.
    """
    m = _RE_ROTULO_AREA.match(str(texto or ""))
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    return v if v >= _AREA_MIN_M2 else None


def unidade_provada_por_rotulo(pares, tol: float = _AREA_TOL) -> dict:
    """A unidade está PROVADA pelos rótulos de área da própria prancha?

    `pares`: saída de `casar_texto_com_regiao` — [{texto, area, ...}].
    Devolve {'provada': bool, 'n_batem', 'n_rotulos_area', 'exemplos'}.

    Prova = pelo menos `_AREA_MIN_PARES` rótulos de área batendo ±tol com a
    região que rotulam. 🪤 Só conta rótulos DISTINTOS: a mesma área repetida
    em 4 ambientes iguais é uma evidência, não quatro.
    """
    vistos = set()
    batem = []
    n_rot = 0
    for p in (pares or []):
        alvo = rotulo_area_como_numero(p.get("texto"))
        if alvo is None:
            continue
        n_rot += 1
        try:
            medida = float(p.get("area") or 0)
        except (TypeError, ValueError):
            continue
        if medida <= 0:
            continue
        if abs(medida - alvo) / alvo <= tol:
            chave = round(alvo, 2)
            if chave in vistos:
                continue
            vistos.add(chave)
            batem.append({"texto": p.get("texto"), "alvo": alvo,
                          "medida": round(medida, 2)})
    return {
        "provada": len(batem) >= _AREA_MIN_PARES,
        "n_batem": len(batem),
        "n_rotulos_area": n_rot,
        "exemplos": batem[:5],
    }


# ══════════════════════════════════════════════════════════════════════════
#  🧬 MERGE DE LEITURAS — a melhor prancha de cada
# ══════════════════════════════════════════════════════════════════════════
#
# Pedro, 24/08/2026: *"não podemos fazer um merge entre as planilhas e unificar
# isso pelo motor tb? tipo um terceiro projeto"*.
#
# 🔑 POR QUE ISSO É PRECISO. A releitura de um projeto NÃO é superconjunto da
# leitura antiga. Caso Alan (e1c48ed7 × ev597afa), medido no banco:
#   • nas 3 pranchas NOVAS (que morriam no KeyError): ganho puro, 0 → 151 itens
#   • nas 4 pranchas que JÁ iam: PERDA pura, 147 → 112 itens, 92 → 72 medidos
#   • as 38 portas dele (23 P80E + 9 P80 + 4 P60T + 1 P70 + 1 PD120, 34 MEDIDAS)
#     viraram uma linha só: "Portas internas", quantidade 0, estimado
# Escolher a melhor prancha de cada lado dá 307 itens e 179 medidos, contra 92
# do original e 151 da releitura.
#
# 🚨 A INVARIANTE QUE IMPEDE DUPLICAR: cada prancha entra INTEIRA, de UM lado só.
# Nunca se mistura leitura dentro da mesma prancha. Sem isso, o mesmo item
# apareceria duas vezes com nomes diferentes (a IA batiza diferente a cada
# leitura — ver project_nao_determinismo_e_da_ia_20260810).

_MERGE_STOP = frozenset("""
CAD LED PVC MDF LTS BTU ABNT NBR CPU USB PCD MED CAIXA PORTA PISO PAREDE FORRO
TOMADA SALA AREA ÁREA TOTAL BANCO VIDRO METAL LOGO TAG NOVO NOVA TIPO UNID
ALTURA LARGURA REF OBS GERAL EXISTENTE MANTER DEMOLIR
""".split())

_RX_MERGE_TOKEN = _re.compile(r"(?<![A-Za-zÀ-ú])([A-Z][A-Z0-9]{2,7})(?![a-z])")


def merge_tokens(descricao: str) -> set:
    """Códigos de identidade dentro da descrição: 'IVP', 'CFTV', 'P80E', 'DCAH'.

    São eles que denunciam o MESMO objeto contado em duas pranchas — a prancha
    de elétrica e a de segurança mostram o mesmo sensor.

    🪤 Palavra portuguesa em caixa alta ('CAIXA', 'PORTA') não é identidade e
    gera alarme falso; a stoplist existe pra isso e pode crescer.
    """
    achados = set()
    for t in _RX_MERGE_TOKEN.findall(str(descricao or "")):
        t = t.upper()
        if t not in _MERGE_STOP:
            achados.add(t)
    return achados


def merge_sobreposicoes(itens) -> list:
    """Mesmo código aparecendo em pranchas DIFERENTES — candidatos a dobra.

    🚨 Isto APENAS APONTA. Não soma, não apaga, não escolhe. Regra dura nº3
    (ratio só alerta) e a lição de 17/08: uma passada que "removia duplicata"
    achou que Ø8 e Ø16 eram a mesma coisa e derrubou 18.168 kg para 508 kg.

    Devolve, por (código, unidade): quanto daria SE alguém somasse, quanto é a
    maior linha sozinha, e em que pranchas está — pra decisão humana.
    """
    porto = {}
    for it in itens or []:
        d = (it or {}).get("description") or ""
        pr = str((it or {}).get("ref_sheet") or "").strip()
        un = str((it or {}).get("unit") or "").strip()
        try:
            q = float((it or {}).get("quantity") or 0)
        except Exception:
            q = 0.0
        if not pr or q <= 0:
            continue
        for t in merge_tokens(d):
            e = porto.setdefault((t, un), {"codigo": t, "unidade": un,
                                           "linhas": [], "pranchas": set()})
            e["linhas"].append({"prancha": pr, "descricao": d[:90], "quantidade": q})
            e["pranchas"].add(pr)

    saida = []
    for e in porto.values():
        if len(e["pranchas"]) < 2:
            continue          # numa prancha só não é dobra entre pranchas
        # 🚨 24/08, olhando a tela pela 1ª vez: o CFTV saía como
        #   "13 em AQ-E · 9 em EL-E · 3 em EL-E · 2 em EL-E · 1 em EL-E · ..."
        # Seis entradas da MESMA prancha — que são 6 tipos de câmera diferentes
        # (CFTV3, CFTV8, CFTV16, CFTV4, CFTV12, DOME), não duplicata entre si.
        # A pergunta é sempre ENTRE pranchas: "a prancha X e a Y estão mostrando
        # o mesmo equipamento?". Somar por prancha primeiro é o que torna o
        # número comparável — e o "somando daria" para de exagerar o alarme.
        por_prancha = {}
        for l in e["linhas"]:
            d = por_prancha.setdefault(l["prancha"], {"prancha": l["prancha"],
                                                      "quantidade": 0.0, "linhas": 0})
            d["quantidade"] += l["quantidade"]
            d["linhas"] += 1
        blocos = sorted(por_prancha.values(), key=lambda d: -d["quantidade"])
        for b in blocos:
            b["quantidade"] = round(b["quantidade"], 2)
        soma = sum(b["quantidade"] for b in blocos)
        saida.append({
            "codigo": e["codigo"],
            "unidade": e["unidade"],
            "pranchas": sorted(e["pranchas"]),
            # `linhas` agora é UMA entrada por prancha — a granularidade da
            # pergunta. O detalhe item a item continua na planilha.
            "linhas": blocos,
            "soma_se_somar": round(soma, 2),
            # 🔑 O contraste que decide: se somar dá muito mais que a maior
            # prancha sozinha, ou são coisas diferentes ou é dobra — e é ISSO
            # que o humano precisa olhar.
            "maior_sozinho": round(max(b["quantidade"] for b in blocos), 2),
        })
    saida.sort(key=lambda x: -x["soma_se_somar"])
    return saida


def merge_plano(itens_pai, itens_filho) -> dict:
    """Qual leitura vence CADA prancha. Não mistura nada por dentro.

    Critério: mais MEDIDO ganha; empate desempata por nº de itens; empate total
    fica com o ORIGINAL — o cliente já viu aquilo, e trocar sem ganho é churn.

    🪤 "Melhor" aqui é por PRANCHA, não pela planilha inteira. No agregado o
    filhote do Alan parecia melhor (151 × 92) e ainda assim tinha perdido 20
    medições nas pranchas que já funcionavam.
    """
    def _resumo(itens):
        d = {}
        for it in itens or []:
            k = str((it or {}).get("ref_sheet") or "").strip()
            if not k:
                continue
            e = d.setdefault(k, {"itens": 0, "medidos": 0})
            e["itens"] += 1
            if (it or {}).get("confidence") == "confirmado":
                e["medidos"] += 1
        return d

    ra, rf = _resumo(itens_pai), _resumo(itens_filho)
    plano = []
    for k in sorted(set(ra) | set(rf)):
        a, f = ra.get(k), rf.get(k)
        if a and not f:
            lado, motivo = "pai", "só a leitura original tem esta prancha"
        elif f and not a:
            lado, motivo = "filho", "só a releitura tem esta prancha"
        elif f["medidos"] > a["medidos"]:
            lado, motivo = "filho", f"mediu mais ({f['medidos']} × {a['medidos']})"
        elif a["medidos"] > f["medidos"]:
            lado, motivo = "pai", f"mediu mais ({a['medidos']} × {f['medidos']})"
        elif f["itens"] > a["itens"]:
            lado, motivo = "filho", f"mesmo medido, mais itens ({f['itens']} × {a['itens']})"
        else:
            lado, motivo = "pai", "empate — fica com o que o cliente já viu"
        esc = a if lado == "pai" else f
        plano.append({"prancha": k, "lado": lado, "motivo": motivo,
                      "pai": a, "filho": f,
                      "itens": esc["itens"], "medidos": esc["medidos"]})

    return {
        "pranchas": plano,
        "total_itens": sum(p["itens"] for p in plano),
        "total_medidos": sum(p["medidos"] for p in plano),
        "do_pai": [p["prancha"] for p in plano if p["lado"] == "pai"],
        "do_filho": [p["prancha"] for p in plano if p["lado"] == "filho"],
    }


def merge_itens(itens_pai, itens_filho, plano: dict) -> list:
    """Aplica o plano: devolve os itens escolhidos, COPIADOS SEM ALTERAÇÃO.

    🚨 Regra dura nº1: nada é promovido aqui. Um item que chegou 'estimado' sai
    'estimado'. O merge escolhe DE ONDE vem a linha, nunca o que ela vale.
    🚨 Regra dura nº4: discipline/section vêm junto — a taxonomia não é refeita.
    """
    lado_da = {p["prancha"]: p["lado"] for p in plano.get("pranchas", [])}
    saida = []
    for origem, itens in (("pai", itens_pai), ("filho", itens_filho)):
        for it in itens or []:
            pr = str((it or {}).get("ref_sheet") or "").strip()
            if pr and lado_da.get(pr) == origem:
                saida.append(dict(it))
    return saida


# ── A MEDIÇÃO ESTAVA NA OBSERVAÇÃO E A QUANTIDADE VINHA ZERO (26/08/2026) ──
_RX_LAYER_MEDIDO = _re.compile(
    r"(?:área|area)\s+hachurada\s+do\s+layer\s+['\"\u2018\u2019\u201c\u201d]?(?P<ly>[^'\"\u2018\u2019\u201c\u201d=]+?)"
    r"['\"\u2018\u2019\u201c\u201d]?\s*=\s*(?P<v>[0-9]+(?:[.,][0-9]+)?)\s*m[²2]"
    r"|comprimento\s+do\s+layer\s+['\"\u2018\u2019\u201c\u201d]?(?P<ly2>[^'\"\u2018\u2019\u201c\u201d=]+?)"
    r"['\"\u2018\u2019\u201c\u201d]?\s*=\s*(?P<v2>[0-9]+(?:[.,][0-9]+)?)\s*m\b",
    _re.IGNORECASE)

_UNI_AREA = {"m²", "m2"}
_UNI_LINEAR = UNIDADES_SO_COMPRIMENTO   # fonte única: o público lá de cima

_TOL_PROCEDENCIA = 0.01      # 1% — é pra confirmar a NOSSA medição, não arredondar


_RX_NUM_COM_UNIDADE = _re.compile(
    r"([0-9]{1,3}(?:\.[0-9]{3})*(?:[.,][0-9]+)?)\s*(m²|m2|ml|m)\b", _re.IGNORECASE)


def quantidade_medida_pelo_pdf(observacao, unidade, area_pdf=0, comprimento_pdf=0,
                               tol=0.01):
    """Igual à `quantidade_da_procedencia`, mas para a medição VETORIAL do PDF.

    🚨 26/08/2026, caso **Construtora Mr** (cliente do dia, baixou às 13:20).
    Rodado em modo avaliação isolada depois do conserto, o resultado mostrou o
    padrão de novo — a IA escreve a medição NOSSA na observação e deixa a
    quantidade em zero:

        "Piso cerâmico/porcelanato"  qtd 0
            obs: "Área total medida vetorialmente: 13,6 m² (3 ambientes)"
        "Rodapé em cerâmica"         qtd 0
            obs: "perímetro total de paredes medido vetorialmente (38,8 m)"

    O motor mediu 13,6 m² de ambiente e 38,8 m de parede no PDF dele — os dois
    números estão escritos nas linhas, e as duas linhas saem vazias.

    🔑 A PROVA NÃO É O TEXTO, É A IGUALDADE. Só preenche quando o número citado
    bate (±1%) com um valor que NÓS medimos nesta leitura (`rooms_m2` ou
    `walls_m` do motor vetorial). Não casa a frase — casa o NÚMERO. Por isso
    não importa como a IA escreveu.

    📐 `area_pdf` e `comprimento_pdf` aceitam um NÚMERO ou uma LISTA de números.
    Passe a lista com a medição de cada PRANCHA: em job multi-página a soma não
    corresponde a nada físico, e comparar contra ela faz a régua nunca casar
    (caso Flavio, 31/08 — 16 pranchas, `resgate_pdf=0` com medição existindo).

    🚨 E a família da unidade tem que bater: área com área, comprimento com
    comprimento. É essa trava que segura o caso perigoso do MESMO cliente:

        "Parede de alvenaria"  obs: "38,8 m de paredes medidas vetorialmente
                                     × pé-direito 2,70 m = 104,8 m² bruto"

    Aqui a IA **inventou o pé-direito de 2,70 m** — ninguém informou. O 38,8
    existe na observação e bate com a nossa medição, mas é COMPRIMENTO num item
    de m²: não entra. E o 104,8 não bate com medição nenhuma: também não entra.
    A linha continua zerada, que é o certo — não medimos altura.

    🚫 Não promove confiança: quem chama mantém o `confidence` da IA. A escala
    do PDF veio do carimbo, e carimbo é declaração, não prova.
    """
    if not observacao or not unidade:
        return None
    u = str(unidade).strip().lower()

    # 🩸 31/08/2026 (caso Flavio) — A RÉGUA COMPARAVA CONTRA A SOMA DO JOB.
    # `area_pdf` chegava como `_pdfvec_area_m2`, que acumula página a página.
    # Num projeto de 16 pranchas do mesmo imóvel isso é a mesma casa contada
    # várias vezes (741,8 m² num imóvel de 400). A observação do item cita o
    # número da PRANCHA dele — 80,5 m² — e 80,5 nunca bate ±1% com 741,8.
    # Resultado no log: `resgate_pdf=0`, que se lê como "não havia o que
    # resgatar" quando a verdade é "a régua estava medindo a coisa errada".
    # Agora aceita uma LISTA de alvos (as medições por prancha) além do número
    # único — retrocompatível com quem passa float.
    # 🪤 O que NÃO se afrouxa junto: a tolerância continua ±1% e a família de
    # unidade continua obrigatória. Mais alvos já aumenta a chance de casar por
    # coincidência; relaxar os dois freios ao mesmo tempo seria trocar linha
    # zerada por número inventado.
    def _alvos(v):
        if v is None:
            return []
        if isinstance(v, (int, float)):
            return [float(v)] if float(v) > 0 else []
        try:
            return sorted({round(float(x), 4) for x in v if float(x or 0) > 0})
        except (TypeError, ValueError):
            return []

    if u in _UNI_AREA:
        alvos = _alvos(area_pdf)
    elif u in _UNI_LINEAR:
        alvos = _alvos(comprimento_pdf)
    else:
        return None
    if not alvos:
        return None
    for m in _RX_NUM_COM_UNIDADE.finditer(str(observacao)):
        bruto, uni_txt = m.group(1), m.group(2).lower()
        # a unidade escrita ao lado do número também tem que ser da família certa
        if u in _UNI_AREA and uni_txt not in ("m²", "m2"):
            continue
        if u in _UNI_LINEAR and uni_txt not in ("ml", "m"):
            continue
        try:
            valor = float(bruto.replace(".", "").replace(",", ".")
                          if bruto.count(",") == 1 and "." in bruto
                          else bruto.replace(",", "."))
        except (TypeError, ValueError):
            continue
        if valor <= 0:
            continue
        if any(abs(valor / alvo - 1.0) <= tol for alvo in alvos):
            return round(valor, 2)
    return None


def quantidade_da_procedencia(observacao, unidade, areas_por_layer=None,
                              comprimentos_por_layer=None):
    """Devolve a quantidade quando a observação CITA uma medição nossa que
    CONFERE com a extração — senão devolve None.

    🚨 26/08/2026, caso Alan (job de 24/08 21:39): 31 de 73 linhas de área e
    comprimento saíram com quantidade ZERO **tendo o número medido escrito na
    própria observação**:

        "Forro de gesso acartonado"   qtd 0  obs: "área hachurada do layer
                                                   -TEFOR = 26.54 m² (17 hachuras)"
        "Revestimento de parede"      qtd 0  obs: "área hachurada do layer
                                                   '-TEPAR' = 268.39 m²"
        "Execução de parede nova"     qtd 0  obs: "comprimento do layer
                                                   '-TEPAR' = 302.14 m"

    O motor mediu, a IA citou o layer e o valor, e a coluna de quantidade veio
    vazia. Medido no acervo: **126 de 1.579** linhas zeradas de área/comprimento
    (8,0%) têm um número medido na observação.

    🔑 ISTO NÃO CONFIA NO TEXTO. O texto só diz ONDE olhar; quem decide é a
    extração. O valor citado tem que bater (±1%) com `get_areas_by_layer()` ou
    `get_walls_by_layer()` do MESMO layer. Se o layer não existe, ou o número
    não confere, devolve None e a linha continua zerada.
    🪤 É a trava que separa isto do experimento REPROVADO de 25/08, onde proibir
    `quantity=0` no prompt destravou 30 de 31 linhas — com chute redondo (50,
    80, 40 m²), só 2 a 5 batendo com algo da prancha. Zero honesto é melhor que
    chute plausível; medição nossa confirmada é melhor que os dois.

    🚫 NÃO promove confiança: quem chama mantém o `confidence` que a IA deu.
    Preencher a quantidade e carimbar 'medido' são passos diferentes.
    """
    if not observacao or not unidade:
        return None
    u = str(unidade).strip().lower()
    obs = str(observacao)
    for m in _RX_LAYER_MEDIDO.finditer(obs):
        e_area = m.group("ly") is not None
        layer = (m.group("ly") if e_area else m.group("ly2")) or ""
        bruto = (m.group("v") if e_area else m.group("v2")) or ""
        layer = layer.strip().strip("'\"\u2018\u2019\u201c\u201d ")
        if not layer:
            continue
        if e_area and u not in _UNI_AREA:
            continue          # citou área e o item é linear: não serve
        if (not e_area) and u not in _UNI_LINEAR:
            continue
        try:
            valor = float(bruto.replace(",", "."))
        except (TypeError, ValueError):
            continue
        if valor <= 0:
            continue
        fonte = (areas_por_layer if e_area else comprimentos_por_layer) or {}
        real = fonte.get(layer)
        if real is None:      # tenta sem diferenciar maiúscula (layer do CAD varia)
            _bx = {str(k).strip().lower(): v for k, v in fonte.items()}
            real = _bx.get(layer.lower())
        if real is None:
            continue
        try:
            real = float(real)
        except (TypeError, ValueError):
            continue
        if real <= 0:
            continue
        if abs(valor / real - 1.0) <= _TOL_PROCEDENCIA:
            return round(valor, 2)
    return None


# ── ITEM CUJA IDENTIDADE É O BLOCO DO CAD (regra nº1) ──────────────────────
# 🩸 04/09/2026, olhando o 1º projeto da Caroline (Bolognesi). A planilha dela
# trazia "Equipamento não identificado — bloco CAD '1258C37_v' — verificar com
# projetista", 1 un, carimbado **✓ MEDIDO DO CAD**.
#
# 🔑 MEDIDO na base inteira: 75 itens assim em projetos de cliente, 55 deles
# com o selo branco (5% de TODO o branco da história). E das 6 vezes em que um
# cliente rejeitou um item BRANCO, **6 de 6 eram desta classe** — é a única
# coisa que faz alguém apagar algo que a gente disse ter medido.
#
# Nomes reais que já saíram na planilha de um cliente pagante, todos brancos:
#     'ftjrtf' · 'WGWRRG' · '6we4f65we4f' · 'dgcfr' · 'esw3r' · 'CP525_p'
#
# O que a geometria prova aqui é que existem N ocorrências DE ALGUMA COISA. Não
# prova QUE COISA é. "✓ Medido do CAD" numa linha que o cliente não consegue
# orçar é a regra nº1 ao contrário: o selo mais forte no item mais fraco.
#
# 🪤 A fronteira é estreita de propósito, e foi calibrada contra a base:
#   • só CONTAGEM (un/pç) — em m²/ml "não identificado" quase sempre fala do
#     MATERIAL ("cobertura — material não identificado"), e o item existe;
#   • "Portas ... não identificadas POR bloco específico" fica de fora — porta
#     é item identificado, o que falta é o bloco;
#   • "Janela j3 — conforme bloco 'j3'", "Difusor/Grelha", "Esquadria flexível"
#     e "Mobiliário — bloco e48" ficam de fora: o nome do item é real, só o
#     tipo é que falta.
# Sem esses três cortes a regra pegava 58 itens em vez de 75 e levava junto
# item legítimo — conferido item a item antes de escrever.
_RE_TEM_BLOCO = _re.compile(r"bloco|layer", _re.I)
_RE_LIDERA_BLOCO = _re.compile(r"^\s*(blocos?|elementos?)\s", _re.I)
_RE_NAO_IDENT = _re.compile(
    r"(bloco|layer)[^.]{0,60}n[ãa]o\s+identificad"
    r"|n[ãa]o\s+identificad[^.]{0,60}(bloco|layer)", _re.I)
# "não identificados POR bloco específico" = o item existe, o bloco é que falta.
_RE_IDENT_POR = _re.compile(r"n[ãa]o\s+identificad[oa]s?\s+por\s", _re.I)
_UNIDADES_DE_CONTAGEM = ("un", "pç", "pc", "und", "unid")


def item_e_bloco_sem_identidade(descricao, unidade) -> bool:
    """A identidade deste item é o nome de um bloco do CAD? Só APONTA.

    Quem rebaixa o selo é o chamador — e só rebaixa, nunca promove.
    """
    _d = str(descricao or "")
    if str(unidade or "").strip().lower() not in _UNIDADES_DE_CONTAGEM:
        return False
    if not _RE_TEM_BLOCO.search(_d):
        return False
    if _RE_IDENT_POR.search(_d):
        return False
    return bool(_RE_LIDERA_BLOCO.search(_d) or _RE_NAO_IDENT.search(_d))


# ── PAREDE MENOR QUE O PERÍMETRO POSSÍVEL (regra nº1) ──────────────────────
# 🩸 04/09/2026, no 1º projeto da Caroline (Bolognesi). O motor mediu
# **17,18 m** de parede numa casa de **46,79 m²** — e daí saiu a alvenaria
# (44,67 m² = 17,18 × 2,60), o chapisco e o rodapé.
#
# 🔑 Entre todos os retângulos de mesma área, o QUADRADO tem o menor perímetro.
# Então nenhuma edificação pode ter menos parede que `4·√área`:
#
#     4 · √46,79 = 27,36 m   contra   17,18 m medidos
#
# Faltam 59% de parede — e isso IGNORANDO as paredes internas, que só aumentam
# o mínimo. Não é regra de bolso nem benchmark de obra: é geometria, e por isso
# não esbarra na regra nº3 (ratio só alerta). O limite é uma impossibilidade.
#
# 🔑 MEDIDO na base: dos 19 projetos de cliente em que a gente mede parede em
# metro, **3 (16%) estão abaixo do mínimo** — humberto.oliveira 88% abaixo,
# marcioeng72 42%, Caroline 59%. Onze itens BRANCOS saíram desses três.
#
# 🪤 Folga de 5%: o limite é exato só pro quadrado perfeito sem parede interna,
# e medição tem ruído. Os três casos reais estão 42–88% abaixo — a folga não
# muda nenhum deles e evita alarme em planta quase quadrada.
# 🪤 SÓ APONTA. Não corrige o número (regra nº3) — corrigir seria inventar
# parede que ninguém mediu. Quem rebaixa o selo é o chamador.
_FOLGA_PERIMETRO = 0.95


def parede_abaixo_do_minimo(comprimento_m, area_m2):
    """(impossível, mínimo_m). `impossível` = há parede faltando, com certeza.

    `área` é a área de piso medida/lida; `comprimento` é a metragem de parede
    que o motor apurou. Devolve (False, 0.0) quando não dá pra avaliar.
    """
    try:
        _c = float(comprimento_m or 0)
        _a = float(area_m2 or 0)
    except (TypeError, ValueError):
        return False, 0.0
    if _c <= 0 or _a <= 0:
        return False, 0.0
    _minimo = 4.0 * (_a ** 0.5)
    return (_c < _minimo * _FOLGA_PERIMETRO), _minimo


# 🩸 04/09/2026, rodando o conserto num arquivo REAL (filhote `ev6edc7e` da
# Caroline). O guarda do mínimo de parede não disparou — porque nessa rodada a
# parede saiu só em **m²**, e ele só olhava `ml`/`m`. O motor não é
# determinístico: o MESMO arquivo produziu "17,18 ml" numa rodada e
# "44,67 m²" na outra. Guarda que depende da forma do item guarda metade.
#
# 🔑 Mas o comprimento NÃO se perde — ele fica escrito na observação:
#     "comprimento total do layer PAREDES = 17,18 m (confirmado)
#      × pé-direito estimado 2,60 m = 44,67 m²"
# Ler dali é EXATO. A alternativa que eu ia usar — supor um pé-direito mínimo
# pra converter m² em metro — foi medida e daria **72% de disparo** (13 de 18
# projetos), que é o alarme sem controle de novo. Por este caminho dá 31%
# (5 de 16), que é taxa de defeito, não de ruído.
_RE_COMPR_LAYER = _re.compile(
    r"comprimento\s+total\s+do\s+layer[^=]{0,60}=\s*([0-9]+(?:[.,][0-9]+)?)\s*m",
    _re.I)


def comprimento_de_parede_na_observacao(observacao):
    """O comprimento de parede que a observação declara, em metros. None se não há."""
    _m = _RE_COMPR_LAYER.search(str(observacao or ""))
    if not _m:
        return None
    try:
        return float(_m.group(1).replace(",", "."))
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════════════════
#  ADMINISTRAÇÃO LOCAL DE OBRA — o motor chutava o PRAZO
# ══════════════════════════════════════════════════════════════════════════
# 🩸 04/09/2026. O prompt mandava emitir "Administração local de obra
# (un: mês — quantidade conforme prazo)". A IA obedecia e INVENTAVA a duração
# da obra. Medido em 156 projetos de cliente:
#
#     79 itens · unidade "mês" em 76 · quantidade de 0 a 18 · média 3,8
#     29 dos 79 (37%) saíram ZERO — "Administração local de obra — 0 meses"
#
# Os outros quatro preliminares saem como verba (260 de 346) e têm 7,5% de
# zero. Só este chuta tempo. E é o mais EDITADO do grupo na revisão: 5 edições
# para 9 aprovações — o cliente conserta o nosso palpite.
#
# 🔑 Prazo de obra não sai de planta, sai de cronograma. É a regra dura nº5:
# publicar "3 meses" é a gente virar orçamentista por um instante.
#
# 🪤 O PRÓPRIO PROJETO JÁ NÃO CONFIA NESTE NÚMERO. O cronograma se recusa a
# consumi-lo, e o comentário lá (main.py, caso Eloídes 03/08) diz por quê:
# "usar esse chute aqui seria o cronograma aprendendo com o palpite dele mesmo
# e chamando de informação". Só o quantitativo ainda o publicava.
#
# 🚫 NÃO remove o item: medido, os Preliminares são APROVADOS (58 aprovações de
# 9 pessoas contra 11 rejeições de 3) — tirá-los iria contra o que o cliente
# faz com eles. O que sai é o número inventado, não a linha.
_RE_ADMIN_LOCAL = _re.compile(
    r"administra(?:ç|c)(?:ã|a)o\s+local", _re.I)

# Unidades de TEMPO: é o que denuncia o chute de prazo. "vb" não é chute —
# verba é justamente dizer "isto é um item, o valor é do orçamentista".
_UNIDADES_DE_TEMPO = (
    "mes", "mês", "meses", "dia", "dias", "semana", "semanas",
    "hora", "horas", "h", "ano", "anos",
)

_FRASE_SEM_PRAZO = (
    "⚠ A duração da obra NÃO foi medida — ela não sai da planta. Este item "
    "entra como verba; o prazo vem do cronograma ou do orçamentista."
)


def administracao_local_com_prazo_chutado(descricao, unidade):
    """O item é administração local de obra cotada em unidade de TEMPO?

    Só isso: a pergunta é sobre a natureza do item, não sobre o valor. Um
    item com quantidade 3 e outro com 0 são o mesmo defeito — nos dois a
    unidade declara um prazo que ninguém mediu.
    """
    if not _RE_ADMIN_LOCAL.search(str(descricao or "")):
        return False
    return str(unidade or "").strip().lower() in _UNIDADES_DE_TEMPO


def normalizar_administracao_local(descricao, unidade, observacao=""):
    """Devolve (unidade, quantidade, observação) já corrigidos, ou None.

    None = a regra não se aplica; quem chama não mexe em nada.
    🪤 Quantidade 1 de propósito, nunca 0: zero era metade do defeito (37% dos
    casos), e uma verba com quantidade 0 não é honestidade, é linha quebrada.
    """
    if not administracao_local_com_prazo_chutado(descricao, unidade):
        return None
    _obs = str(observacao or "")
    if _FRASE_SEM_PRAZO in _obs:
        return ("vb", 1.0, _obs)
    return ("vb", 1.0, (_FRASE_SEM_PRAZO + " " + _obs).strip()[:1000])
