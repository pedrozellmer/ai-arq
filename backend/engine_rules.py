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
    'list object has no attribute get' que derrubou o job do cliente-88 (27/06).

    🩸 22/09/2026 (job ee801b82) — E ÀS VEZES ELA ANINHA. A prancha do poço
    de sucção voltou `{"project_data": {"kept_elements": [...], "items": [6]}}`
    e os dois laços (PDF e DXF) só leem `result["items"]` no topo: os 6 itens,
    785,7 kg de aço entre eles, sumiram sem uma linha de log. Quando o topo não
    tem item, sobe a lista de UM nível abaixo e deixa a marca
    `_items_aninhados` pra o main registrar — consertar calado esconderia que
    o formato da IA variou. O resto do objeto (project_data) fica como veio."""
    if isinstance(parsed, list):
        return {"items": parsed}
    if not isinstance(parsed, dict):
        return {"items": []}
    _topo = parsed.get("items")
    if _topo:
        return parsed
    if _topo is not None and not isinstance(_topo, list):
        # um "items" que não é lista nem nulo: fica como sempre ficou
        return parsed
    for _chave, _dentro in parsed.items():
        if not isinstance(_dentro, dict):
            continue
        _lista = _dentro.get("items")
        # 🪤 só lista com ao menos um OBJETO: lista de texto não é item, e o
        # laço do main descartaria cada um no except, calado de novo.
        if isinstance(_lista, list) and any(isinstance(x, dict) for x in _lista):
            _out = dict(parsed)
            _out["items"] = list(_lista)
            _out["_items_aninhados"] = {"de": str(_chave), "n": len(_lista)}
            return _out
    return parsed


def motivo_da_prancha_sem_item(parsed):
    """Por que a leitura (já parseada, ANTES do normalize) não trouxe item.

    None quando há item (no topo ou um nível abaixo). "items-vazio" quando a IA
    respondeu no formato pedido e disse que não há nada ("items": []). E
    "sem-chave-items" quando ela respondeu OUTRA coisa — só project_data,
    como a prancha de fundação do job ee801b82 (🩸 22/09/2026). As duas não
    são a mesma coisa: a 1ª é uma resposta, a 2ª é uma pergunta não respondida."""
    if (normalize_items_payload(parsed).get("items") or []):
        return None
    if isinstance(parsed, list):
        return "items-vazio"
    if isinstance(parsed, dict):
        if "items" in parsed:
            return "items-vazio"
        if any(isinstance(v, dict) and "items" in v for v in parsed.values()):
            return "items-vazio"
    return "sem-chave-items"


def registros_da_leitura(result, nome_prancha):
    """(stage, mensagem) pro error_log a partir das marcas que o analyzer e o
    normalize deixam no resultado da prancha.

    🩸 22/09/2026 (job ee801b82) — duas pranchas de 7 sumiram sem registro
    nenhum: uma com os itens aninhados, outra sem item e sem erro. O aviso de
    cobertura só conhecia `result["error"]`. Uma função só, chamada pelos dois
    laços do main, pra o log não depender de alguém lembrar de cada marca."""
    out = []
    if not isinstance(result, dict):
        return out
    nome = str(nome_prancha or "prancha").strip() or "prancha"
    _an = result.get("_items_aninhados")
    if isinstance(_an, dict):
        out.append(("motor:items-aninhados",
                    "%s: a IA pôs %s item(ns) dentro de '%s' em vez do topo — "
                    "lidos de lá (antes eram descartados calados)"
                    % (nome, _an.get("n"), _an.get("de"))))
    _rl = result.get("_releitura")
    if isinstance(_rl, dict):
        _msg = ("%s: 1ª leitura sem item (%s); releitura corretiva deu %s item(ns)"
                % (nome, _rl.get("motivo"), _rl.get("itens")))
        if _rl.get("falhou"):
            _msg += " — a releitura falhou: %s" % _rl.get("falhou")
        out.append(("motor:prancha-releitura", _msg))
    _si = result.get("_sem_item")
    if isinstance(_si, dict):
        out.append(("motor:prancha-sem-item",
                    "%s: lida sem erro e sem nenhum item (motivo=%s, releu=%s) — "
                    "entrou no aviso de cobertura"
                    % (nome, _si.get("motivo"), bool(_si.get("releu")))))
    return out


def aviso_de_prancha_sem_item(nomes):
    """A frase pro cliente quando prancha(s) foram lidas e não deram item.

    🩸 22/09/2026 (job ee801b82): a prancha de fundação foi lida, não gerou
    linha, e nenhum texto disse isso — o aviso de cobertura só contava erro.
    🚫 Não promete que reprocessar resolve: ninguém mediu que resolve, e o
    reprocesso gasto à toa é o erro que a casa já pagou (ver
    `aviso_de_leitura_cortada`)."""
    nomes = [str(n).strip() for n in (nomes or []) if str(n or "").strip()]
    if not nomes:
        return ""
    _lista = ", ".join(nomes)
    if len(_lista) > 280:
        _lista = _lista[:277].rstrip(", ") + "…"
    if len(nomes) == 1:
        _cab = "ℹ 1 prancha foi lida e não gerou nenhum item nesta planilha"
        _se = "Se ela tem desenho, quadro ou lista a quantificar, esses itens não estão aqui"
    else:
        _cab = ("ℹ %d pranchas foram lidas e não geraram nenhum item nesta planilha"
                % len(nomes))
        _se = ("Se alguma delas tem desenho, quadro ou lista a quantificar, esses "
               "itens não estão aqui")
    return "%s: %s. %s — confira antes de fechar o levantamento." % (_cab, _lista, _se)


_ACO_PAT = _re.compile(r'armadura|estribo|ferragem|vergalh|\baço\b', _re.IGNORECASE)
_FORMA_PAT = _re.compile(r'f[ôo]rma', _re.IGNORECASE)


#: Unidades que dizem o que o número É sem ser peso: verba, conjunto, serviço,
#: tempo, "sem unidade" declarado. Trocar o rótulo delas por kg não converte
#: nada — só inventa um peso (o forçador troca a ETIQUETA, nunca a conta).
UNIDADES_QUE_NAO_VIRAM_KG = frozenset({
    "vb", "vb.", "verba", "gl", "global", "cj", "cj.", "conj", "conjunto",
    "un.g", "sv", "serv", "serviço", "servico",
    "mês", "mes", "h", "hora", "dia",
    "—", "–", "-",
})


def should_force_steel_kg(description, unit=None):
    """Em projeto ESTRUTURAL, aço/armadura/estribo é SEMPRE kg (regra de norma,
    universal). True quando a descrição é claramente de aço E não é fôrma (m²).
    NÃO casa 'concreto armado' (concreto/fôrma) — só o aço de verdade. Caso cliente-88.

    🩸 22/09/2026 — job ee801b82: "Projeto executivo complementar (detalhamento
    de armadura…)" chegou da IA em `vb`, quantidade 1, e saiu na planilha como
    **1 kg** — o padrão casou "armadura" dentro do nome de um SERVIÇO. O
    forçador só troca o rótulo (não converte), então verba que vira kg é um
    peso inventado somado no total de aço.
    📏 Medido no llm_cache (começa em 28/08) × project_items, pela mesma
    descrição: o forçador trocou 4 rótulos, e nenhum era aço de verdade — 1
    verba (este) e 3 linhas "sem itens quantificáveis" com unidade "—". É piso:
    descrição que a consolidação reescreveu não casa.
    🔑 `unit` é opcional pra não mudar quem chama sem ela: sem unidade, vale a
    regra antiga (só a descrição).
    """
    d = description or ""
    if unit is not None and str(unit).strip().lower() in UNIDADES_QUE_NAO_VIRAM_KG:
        return False
    return bool(_ACO_PAT.search(d)) and not _FORMA_PAT.search(d)


def is_likely_wrong_type(quantities, threshold=0.75):
    """Guardrail de tipo (caso cliente-90): um projeto marcado ESTRUTURAL que sai com
    quase tudo zerado provavelmente é arquitetura marcada errada no upload. True se
    >= threshold (75%) dos itens têm quantidade 0/None. Estrutural de verdade
    (cliente-88: 44% zerado) fica abaixo do corte e NÃO dispara."""
    qs = list(quantities or [])
    if not qs:
        return False
    zeros = sum(1 for q in qs if not (q or 0))
    return zeros / len(qs) >= threshold


def detectar_laco_repeticao(texto: str, tokens_saida: int = 0) -> dict:
    """A IA entrou em laco de repeticao e queimou a resposta inteira?

    🚨 26/08/2026, caso cliente-16 (job 43a799c0). De 4 pranchas, 1 chegou na
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
    'seção transversal' — é lixo de extração. Caso cliente-24 (projeto drywall)."""
    if not description:
        return False
    return bool(_NONSENSE_PAT.search(description))


_TYPE_CODE_PAT = _re.compile(r"\b(DRY|DW|DIV|PAR|PV)[\s\-]?(\d{1,3})\b", _re.IGNORECASE)


def extract_type_code(description):
    """Extrai código de TIPO de divisória/parede (DRY 07, DW-12, DIV 03...) pra
    consolidar o MESMO tipo que aparece em várias pranchas. None se não houver.
    Em projeto multi-prancha de drywall, o mesmo tipo se fragmenta em dezenas de
    linhas (caso cliente-24: 191 itens, 156 zerados)."""
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

# 🩸 31/08/2026 (caso cliente-14, job f271473f): "Rasgo em laje de concreto armado
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
# resultado foi apagar dado medido: o item real do job eva97d1d (cliente-41,
# 26/08) "Remoção de revestimento cerâmico existente em piso", 13,60 m²
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


# ── Camada de base × ACABAMENTO (16/09/2026) ────────────────────────────────
# O passo 7 do `_apply_area_honesty` dá a área medida da prancha pra UMA linha
# zerada de cada família (piso, forro). A pergunta que faltava: quando OUTRA
# linha da mesma prancha e da mesma família já tem número, a vaga está ocupada?
#
# ✅ DECIDIDO (Pedro, 15/09): CAMADA NÃO OCUPA A VAGA. Contrapiso com número não
# impede o piso de acabamento vazio de receber a área — os dois cobrem o mesmo
# chão, um embaixo do outro, e camada é a forma MAIS COMUM no banco (desde
# 01/08: piso 16 grupos em 11 jobs, forro 8 em 6). Quem ocupa é só OUTRO
# ACABAMENTO do mesmo tipo: dois pisos de acabamento, dois forros. Aí a linha
# vazia fica em branco COM aviso — porque ali a área da prancha já foi falada.
#
# 🪤 A lista é NEGATIVA de propósito. Classificar errado como "camada" devolve o
# comportamento de hoje (a linha vazia recebe a área, estimada); classificar
# errado como "acabamento" APAGA um preenchimento que hoje acontece. Na dúvida,
# camada. Por isso pintura/massa/verniz entram aqui: "pintura epóxi de piso" é
# acabamento na vida real, mas tratá-la como camada não muda nada do que já sai.
# 🩸 16/09, revisão adversarial: a 1ª lista deixava "LAJE" passar como
# acabamento — e laje é a base por definição. "Laje de cobertura 120 m²" tomava
# a vaga do piso vazio da mesma prancha, que é o "camada ocupando" que a decisão
# proíbe. Junto vieram dois nomes de mercado que a lista não previa: "argamassa
# COLANTE AC-III" (a lista só tinha "de assentamento") e "manta ACÚSTICA" (só
# tinha asfáltica). Por isso as três entradas ficaram curtas: laje, argamassa,
# manta. E "tátil", que é acabamento de faixa — cobre 8 m² de 102, não a vaga.
CAMADA_DE_BASE_KW = (
    "contrapiso", "contra-piso", "contra piso", "regulariza", "lastro",
    "impermeabiliz", "nivelamento", "preparo de base", "camada de", "berço",
    "berco", "argamassa", "manta", "laje", "isolamento", "barreira de vapor",
    "pintura", "massa corrida", "massa pva", "emassamento", "selador",
    "fundo preparador", "textura", "verniz", "tátil", "tatil",
)


def e_acabamento_de_superficie(desc):
    """True quando a linha É o acabamento da superfície — o piso que se pisa, o
    forro que se vê —, e não a camada que vai embaixo nem a pintura que vai em
    cima.

    Usada pra decidir quem OCUPA a vaga do passo 7. Só acabamento ocupa.
    """
    d = (desc or "").lower()
    if any(k in d for k in CAMADA_DE_BASE_KW):
        return False
    return is_floor_surface_para_criar(d)


# ── Coerência de unidade: item CONTÁVEL não sai em metro/m² ──────────────────
# Caso cliente-40 (visto em 01/08/2026, job ed655532): "Condulete de dados —
# 155,6 ml — CONFIRMADO". Condulete é caixa: conta-se em unidade. O motor mediu
# 155,6 m de infra linear (fix do cliente-73) e a IA pendurou os metros na linha
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
# Caso cliente-70 (03/08/2026, job 2f9f81c2 — projeto de incêndio, 112 MB):
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
# em relação ao caso cliente-40 acima, onde mover seria adivinhar) e só em dois
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
    # 🚨 Termos do caso REAL que passou reto (cliente-06@, 05/08): a
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


#: A ORAÇÃO DA FONTE: de "Fonte:" até o primeiro ponto final.
#: 🪤 O recorte é o conserto de um erro meu. A palavra "soma" solta aparece
#: quase sempre em RESSALVA, não como procedência — medido no acervo:
#:   "Verificar sobreposição com demais layers antes de somar ao total."
#:   "...não somado para evitar dupla contagem"
#: Essas são contagens diretas, e rebaixá-las seria roubar selo legítimo.
#: Dentro da oração da fonte, a mesma palavra é a procedência.
_RE_ORACAO_DA_FONTE = _re.compile(r"[Ff]onte\s*:[^.]{0,200}")
_RE_PALAVRA_DE_SOMA = _re.compile(r"\bsoma\w*\b|somat[óo]rio", _re.IGNORECASE)

#: 🪤 A palavra de soma NEGADA não é procedência — é ressalva. Medido no acervo:
#: "não somado para evitar dupla contagem", "verificar sobreposição antes de
#: somar", "os blocos de corte não somam ao total". Todas são contagem DIRETA,
#: e rebaixá-las seria roubar selo legítimo.
_RE_NEGACAO = _re.compile(r"\b(?:n[ãa]o|sem|evitar|antes\s+de)\b[^.]{0,22}$",
                          _re.IGNORECASE)

#: Um "+" com número dos DOIS lados, tolerando só unidade/rótulo curto no meio
#: ("2 un) + tipo 2", "18,65 + 20,10", "(40+10", "544699(4) + 547524(3)").
_RE_PARCELA_ESQ = _re.compile(r"\d[\s\w²º°)\-]{0,8}$")
#: 🪤 O lado direito tolera aspas e pontuação de NOME DE BLOCO, e olha mais
#: longe: "…(1 un) + 'PORTA - PADRÃO-2100514-FACHADA'" é um caso REAL que estava
#: em `confirmado` e a janela curta deixava passar. Formato de observação tem
#: cauda longa — cada rodada de medição contra o acervo achou um jeito novo de o
#: modelo escrever a mesma soma.
_RE_PARCELA_DIR = _re.compile(r"[\s\w²º°()'\"\-]{0,20}\d")
#: "tomada 2P+T": nome de produto, não adição.
_RE_PRODUTO_P_MAIS_T = (_re.compile(r"\dP\s*$", _re.IGNORECASE),
                        _re.compile(r"\s*T\b", _re.IGNORECASE))
#: 🪤 Aqui havia uma exceção pra "cotas +792.63, +795.57" — e a SABOTAGEM provou
#: que ela era INALCANÇÁVEL: a vírgula colada antes do "+" já reprova no lado
#: ESQUERDO, que exige dígito seguido só de letra/espaço/parêntese. Código que
#: nunca roda não é cinto de segurança: é peso morto que engana quem lê depois.
#: Foi removida, e o caso das cotas segue coberto — com teste que prova.


def _tem_aritmetica_de_parcelas(texto: str) -> bool:
    """Varre CADA "+" com o contexto dele.

    🩸 A 1ª versão casava um padrão grande e perdia soma de verdade: num item que
    citava "tomada 2P+T" e somava tipos logo depois, o casamento do nome do
    produto ENGOLIA o trecho onde a soma estava, e a linha escapava. Varrer sinal
    a sinal é o que faz a exceção valer por OCORRÊNCIA, como ela promete.
    """
    for i, ch in enumerate(texto):
        if ch != "+":
            continue
        # 🪤 A JANELA e o REGEX têm que crescer JUNTOS. Alarguei o padrão da
        # direita pra 20 e esqueci a fatia, que continuava em 10 — o caso real
        # "…(1 un) + 'PORTA - PADRÃO-…'" seguiu escapando com o regex "certo".
        esq, dir_ = texto[max(0, i - 12):i], texto[i + 1:i + 25]
        if not _RE_PARCELA_ESQ.search(esq):
            continue                      # sem número à esquerda: não é adição
        if not _RE_PARCELA_DIR.match(dir_):
            continue                      # sem número à direita
        if _RE_PRODUTO_P_MAIS_T[0].search(esq) and _RE_PRODUTO_P_MAIS_T[1].match(dir_):
            continue                      # "2P+T"
        return True
    return False


def a_fonte_declarada_e_uma_soma(obs) -> bool:
    """A observação diz, ela mesma, que o número veio de somar parcelas?

    🚨 18/09/2026 — REGRA DURA Nº1, medida. O prompt manda, com todas as letras:
    *"se você multiplicou, somou ou fez qualquer cálculo além de copiar o valor,
    NÃO é confirmado"*. E o modelo, a temperature 0.7, obedece mais ou menos
    metade das vezes. Sobraram linhas dizendo "✓ MEDIDO" com a própria
    observação declarando "tipo1=5 + tipo2=1 = 6 un".

    🩸 A 1ª versão desta régua exigia a palavra GRUDADA no "Fonte:" — e a
    revisão adversarial mostrou que eu não tinha matado o sorteio, só mudado ele
    de lugar. Quem escolhe a ordem das palavras é o mesmo modelo:

        "Fonte: soma de todos os tipos de 'Montante retangular'..."     → pegava
        "Fonte: CONTAGEM DE BLOCOS — soma de todos os tipos..."         → ESCAPAVA

    Mesma peça, mesmo desenho, duas rodadas: o que decidia o selo era o modelo
    ter enfiado sete palavras entre "Fonte:" e "soma". Medido: a régua estreita
    pegava 89 e deixava passar 57 — 39% da população real, incluindo aritmética
    pura sem a palavra ("ESTAR 18,65 + 20,10 + ... = 172,10 m²", em branco).
    A régua nova pega 161. 🪤 E eu havia justificado o estreitamento com uma
    amostra de 12 que superestimou o risco em ~4× — amostra pequena não decide
    régua de produção.

    🔑 Ela olha o FATO por dois caminhos independentes: a palavra de soma dentro
    da ORAÇÃO DA FONTE, ou aritmética de parcelas em qualquer lugar. Continua
    andando só pra um lado: rebaixa, nunca promove. Não soma nada e não toca
    quantidade — por isso não esbarra no guarda da bitola, que existe pra
    impedir SOMAR.

    🪤 O que ela NÃO faz: julgar se a soma está certa. "soma de 4 INSERTs = 6 un"
    pode estar aritmeticamente perfeita — e continua não sendo leitura direta,
    que é o que o selo branco promete ao cliente.
    """
    if not obs:
        return False
    texto = str(obs)
    oracao = _RE_ORACAO_DA_FONTE.search(texto)
    if oracao:
        _o = oracao.group(0)
        for m in _RE_PALAVRA_DE_SOMA.finditer(_o):
            # 🪤 A palavra NEGADA é ressalva, não procedência — e a oração da
            # fonte nem sempre termina antes dela: quando a observação inteira é
            # uma frase só, "não somado para evitar dupla contagem" cai DENTRO
            # do recorte. Sem esta checagem a régua rebaixava contagem direta.
            if _RE_NEGACAO.search(_o[:m.start()]):
                continue
            return True
    return _tem_aritmetica_de_parcelas(texto)


def selo_apos_regra_da_soma(conf, obs):
    """Aplica a regra ao par (selo, observação). Devolve `(conf, obs, rebaixou)`.

    🚨 18/09/2026 — esta função existe por causa do SEGUNDO achado da revisão
    adversarial, e ele é de método, não de regra. A decisão morava solta dentro
    de `process_job` (3.000 linhas), e por isso NENHUM guarda conseguia
    executá-la: os seis testes do lado do motor liam o `main.py` como texto ou
    como AST. A revisão provou o buraco movendo o bloco pra DEPOIS de o item ser
    montado — código morto, e os 19 guardas seguiram verdes. É a doença da
    miniatura: cinco meses de código inalcançável atrás de um docstring que
    jurava funcionar.

    🔑 Agora o rebaixamento é uma função que o guarda CHAMA, e o que sobra no
    `main.py` é uma linha só — cuja POSIÇÃO ainda importa e é cobrada à parte.
    """
    if conf == "confirmado" and a_fonte_declarada_e_uma_soma(obs):
        aviso = ("⚠ SOMA, não leitura direta — a quantidade veio de somar "
                 "parcelas, então não sai como medida. Confira o total antes "
                 "de orçar. ")
        return "estimado", aviso + str(obs or ""), True
    return conf, obs, False


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


#: Área e volume: numa linha dessas, um comprimento é no máximo a BASE da conta.
_UNIDADES_DE_AREA_OU_VOLUME = {"m²", "m2", "m2.", "m².", "m³", "m3"}


def corrigir_comprimento_medido(desc, unit, quantity, obs, texto_de_pdf=False):
    """Devolve dict de correções ({} = não mexer) pro item cuja observação traz
    um 'comprimento total = N m'. Ver o bloco de comentário acima.

    `texto_de_pdf`: o texto da observação foi escrito lendo PDF? Quem responde
    é `models.texto_veio_da_leitura_de_pdf(origem, tem_cad)`, e quem chama
    passa a resposta. 🪤 22/09 (revisão): a 1ª versão recebia a origem e a
    comparava aqui com "vision_pdf" — uma 5ª cópia, escrita à mão, da pergunta
    que `models` responde (o guarda de cópias reprovou a bancada). Este
    módulo é só stdlib e não importa `models`; por isso recebe o veredito.

    🩸 22/09/2026 — job f8d8e6d8 (só PDF): a fôrma de vigas veio da IA com
    24,3 m², a honestidade de área zerou, e ESTA regra "recuperou" 32,40 m — a
    conta da própria IA ("2×16,20=32,40m") —, trocou m² por m e escreveu "o
    motor mediu 32,40 m neste layer". Três mentiras numa linha: PDF não tem
    layer, o número é da IA, e fôrma é área.
    📏 60 d, sem avaliação: 3 recuperações em PDF (3 jobs), as 3 erradas — duas
    fôrmas de área viradas em metro e um montante de 69,1 m que vinha de uma
    escala adivinhada por votação e que a honestidade tinha zerado. Em CAD são
    19 linhas em 7 jobs, e lá o layer existe: o CAD fica como estava.
    🔑 Em texto lido de PDF a regra não recupera número nenhum (quem decide o
    número de PDF é a honestidade de área, que já passou) — nem em m² nem em
    metro: o montante de 69,1 m ESTAVA em `ml` — e não troca unidade de área
    ou volume por comprimento. `texto_de_pdf` tem default que mantém a regra
    antiga pra quem chama sem ele.
    """
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
    do_pdf = bool(texto_de_pdf)

    # 1) mediu e entregou ZERO — vem primeiro, e vale mesmo com a unidade certa.
    # 🪤 Este caso passou batido na 1ª versão: eu saía cedo quando a unidade já
    # era de comprimento, achando "então está tudo certo". O 2º projeto da
    # cliente-70 (df4f00ca, 191 itens) mostrou 2 itens em `ml` com quantidade 0 —
    # rótulo certo, medição jogada fora do mesmo jeito. Unidade certa não diz
    # nada sobre a quantidade.
    if q <= 0:
        if do_pdf:
            return {}             # número da IA não volta como "o motor mediu"
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
    if do_pdf and u in _UNIDADES_DE_AREA_OU_VOLUME:
        return {}                                  # em PDF, área não vira metro

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


#: Tokens de layer que carregam ANOTAÇÃO, não elemento construtivo.
#: 🩸 09/09/2026 — o caso que criou isto: num projeto de pórtico, `ARQ_TEX-4`
#: respondia por **3.782 m dos 4.258 m** somados como "layer de parede" (88,8%),
#: e a alvenaria de verdade (`ARQ_ALV`) somava 119 m. No arquivo vizinho o topo
#: era `ARQ_TXT-2`. O cliente recebeu linhas como *"Acabamento/textura — linear
#: layer ARQ_TEX-3, 109,40 ml"* com selo **BRANCO** — e ninguém precifica isso
#: (regra dura nº5: quem precifica é um orçamentista humano).
#: 🔑 O comprimento É medido; o que não se sustenta é o par "nome de layer na
#: descrição + selo de MEDIDO". Rebaixar é o conserto, apagar não: o nome do
#: layer no item é ponteiro DELIBERADO em outro caminho (infra linear), pra o
#: cliente reconhecer a origem e completar.
#: 📏 Medido antes de ligar, com ESTE vocabulário (remedido depois de alargar
#: o prefixo TEXT): **60 de 2.121 itens confirmados (2,8%)**, em 29 de 118
#: projetos — e **ZERO projeto perde a cobrabilidade**, porque todos têm
#: outra linha medida de verdade. A primeira medição, com o conjunto mais
#: estreito, dizia 41 em 21: alargar a régua e não remedir teria deixado um
#: número velho fingindo ser medição.
#: 🪤 `TEXT` é PREFIXO, não token exato — os nomes reais do nosso banco são
#: `TEXTOS`, `TEXTO_TABELAS`, `ELE-TEXTOS`, `G-ANNO-TEXT`, `PDF_TEXT`. Meu
#: primeiro conjunto era exato e ficou mais ESTREITO que a régua de substring
#: que já existia — a bancada pegou (guarda antigo de sobreposição). Conferido
#: no acervo: nenhum layer com "TEXTURA" tem item confirmado, então o prefixo
#: não custa nada hoje; se aparecer, `TEXTURA` é decoração de desenho e o
#: comprimento dela também não é serviço.
_ANOTACAO_PREFIXO = ("ANNO", "ANOTA", "LEGEND", "TITUL", "TITLE", "HACH",
                     "CARIMB", "CHAMAD", "TEXT", "COTA", "NOTA")
_ANOTACAO_EXATO = {"TXT", "TEX", "DIM", "DIMS", "DETL", "LEG", "TAG"}


def layer_is_anotacao(layer_name) -> bool:
    """True se o layer carrega TEXTO/COTA/LEGENDA/HACHURA — não obra.

    🪤 Compara por TOKEN, nunca por substring — a mesma trava de
    `layer_is_carimbo`. Sem isso 'ARQ_TEXTURA_PISO' e, pior, qualquer layer que
    contenha 'dim' (como 'JARDIM') cairia aqui.

    🔒 Direção segura: um falso positivo custa um selo branco; um falso
    negativo custa uma quantidade inventada com cara de medição. Na dúvida,
    rebaixa — é a regra dura nº1.
    """
    if not layer_name:
        return False
    for tok in _CARIMBO_SPLIT.split(str(layer_name).upper()):
        if not tok:
            continue
        if tok in _ANOTACAO_EXATO:
            return True
        if tok.startswith(_ANOTACAO_PREFIXO):
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


def areas_do_texto_da_prancha_rotuladas(textos):
    """Como `areas_do_texto_da_prancha`, mas devolve (rótulo, valor).

    🚨 20/09/2026 — POR QUE O RÓTULO PRECISA SAIR DAQUI. O regex captura de
    propósito `total`, `construída`, `útil` e `privativa` (só o terreno é
    descartado), então a lista de valores mistura os AMBIENTES com as linhas de
    TOTAL do próprio quadro. Enquanto o único consumidor era o consenso de área
    total, tanto fazia. Passou a não dar: a régua do recorte de ambientes
    compara essa lista com o que a geometria recortou, e uma linha "ÁREA TOTAL
    2.350 m²" entrando como ambiente faz a soma do autor dar quase o dobro do
    próprio total — e vira "ambiente acima do teto de 500" que não existe.

    🪤 É a regra dos 100% logo abaixo, de novo: numa lista PLANA o pai não pode
    ser irmão do filho. Aqui o pai vinha sem crachá.

    Rótulo normalizado e CURTO ('', 'total', 'construida', 'util',
    'privativa'); nunca o texto que o autor escreveu — o repositório é público
    e esta lista vai pro log.
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
                if rotulo.startswith("constr"):
                    rotulo = "construida"
                elif rotulo.startswith(("util", "útil")):
                    rotulo = "util"
                elif rotulo.startswith("privativa"):
                    rotulo = "privativa"
                elif rotulo.startswith("total"):
                    rotulo = "total"
                else:
                    rotulo = ""
                achados.append((rotulo, v))
    return achados


def areas_do_texto_da_prancha(textos):
    """Extrai candidatos a ÁREA TOTAL do texto da prancha, sem IA.

    Recebe uma lista de strings (os TEXT/MTEXT do DXF) e devolve lista de
    floats em m², já com o parser pt-BR único (`num_br_para_float`).

    🪤 Descarta 'área do terreno' de propósito: é o lote, não a obra — usar isso
    como área do projeto infla tudo que depende dela.
    🪤 Descarta valores absurdos (>1.000.000 m²), que em prancha normalmente são
    número de cota ou coordenada capturados por engano.
    🔑 Assinatura e retorno INALTERADOS de propósito: o consenso de área e o
    ramo `len(_ar)==1` do `process_job` dependem exatamente disto. Quem precisa
    saber o que é ambiente e o que é total usa a versão rotulada acima.
    """
    return [v for _rotulo, v in areas_do_texto_da_prancha_rotuladas(textos)]


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


# 🪤 As chaves de `_GRANDEZA_DA_UNIDADE` são identificadores internos e
# aparecem SEM acento ("area"). Esta linha vai pra observação que o cliente lê
# na planilha — nome interno na cara dele é desleixo visível.
_NOME_DA_GRANDEZA = {
    "area": "área", "volume": "volume", "comprimento": "comprimento",
    "contagem": "contagem", "massa": "massa", "capacidade": "capacidade",
}


def quantidade_apos_troca_de_unidade(qtd, de, para):
    """A unidade da linha foi reescrita. O número sobrevive? Devolve (qtd, nota).

    🩸 14/09/2026 — MEDIDO na base: o motor reescreveu a unidade de **550
    linhas mudando a GRANDEZA FÍSICA**, e **235 delas saíram COM número** —
    o mesmo número, agora medindo outra coisa:

      · 1.200 m de cabo 3×2,5mm²  →  "1.200 **un**"
      · 1.634 m² de rede de sprinkler → "1.634 **un**"
      · 1.505 m de PERÍMETRO de parede → "1.505 **m²**" de revestimento
      · 1.999 kg de aço CA-50 → "1.999 **un**"

    Isto é pior que linha vazia: vazia o cliente preenche, com número ele
    ORÇA. O próprio motor já chamava o efeito pelo nome desde 09/08, na
    observação acima: *"~6.971 m² fabricados"*.

    🔑 A reescrita em si está CERTA e fica: piso se orça em m², não em ml.
    O que não pode é o número atravessar a troca. Metro não vira unidade, e
    converter exigiria um dado que a planta não deu (largura, bitola, peso
    por metro). Então a quantidade vai a ZERO — que é a pergunta honesta,
    a mesma doutrina da derivação de pintura — e o número lido fica escrito
    na observação, pra não perder o levantamento.

    🪤 Troca que NÃO muda a grandeza passa intacta: `cj`→`un`, `m`→`ml`,
    `kg`→`kg` são 138 linhas de puro rótulo e o número continua valendo.
    Unidade incomparável (`vb`, `%`, `mês`) também passa: na dúvida, cala.

    🪤 A nota vai na FRENTE: `revisao.html` mostra só os 110 primeiros
    caracteres da observação e o resto fica num hover que não existe no
    celular.
    """
    try:
        q = float(qtd or 0)
    except (TypeError, ValueError):
        return qtd, ""
    if q <= 0:
        return qtd, ""
    g_de, g_para = grandeza_da_unidade(de), grandeza_da_unidade(para)
    if g_de is None or g_para is None or g_de == g_para:
        return qtd, ""          # só rótulo, ou incomparável: o número vale
    _n = ("%g" % q) if q == int(q) else ("%.2f" % q)
    return 0, (
        "⚠ QUANTIDADE EM BRANCO DE PROPÓSITO: a leitura levantou %s %s, e este "
        "item se mede em %s — %s e %s são grandezas diferentes, e converter "
        "exigiria um dado que a planta não dá. Preferimos deixar em branco a "
        "entregar um número que mede outra coisa."
        % (_n, de, para, _NOME_DA_GRANDEZA.get(g_de, g_de),
           _NOME_DA_GRANDEZA.get(g_para, g_para)))


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

    🩸 04/09/2026, do 1º projeto da cliente-22. Ela recebeu, e
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
    que não é dela — medido em 09/08 numa prancha real: "Nome No Carimbo" (nome no
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
# declararam Polegadas — 7 da escola pública da cliente-16 (349e75a5) e 2 de outros
# clientes. As 7 da cliente-16 são TODAS as elétricas do projeto: não é arquivo
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
# Achado em 10/08/2026 no 1º projeto da cliente-16 (349e75a5, escola pública de 14
# pranchas): 4 linhas brancas com 0 — e a observação de cada uma CARREGAVA o
# número medido ("área de contorno fechado no layer ARQ-COBERTURA = 752,21
# m²"; "comprimento do layer 'EL-Condutos (Teto)' = 79,65 m"). O número se
# perdeu entre a medição e a coluna; o selo ficou para trás.
#
# 🪤 Não é só descuido do modelo. `_apply_area_honesty` (main.py:4337) zera a
# quantidade DE PROPÓSITO quando a área veio de Vision e não da geometria, e
# esse ramo não toca no selo — enquanto o ramo vizinho, que preenche, rebaixa
# pra estimado (linha 4327). Mas aquele caminho só olha unidade de ÁREA, e 3
# das 4 linhas da cliente-16 eram `ml`. Por isso a regra mora AQUI, no fim da
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
    O job `b5ce23ff` (cliente-69, maior lead B2B) prova que dá pra ter selo zero
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
        # 🔑 PRANCHA PRIMEIRO (16/08/2026, caso cliente-20 42c354a1): o quadro de
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
# 🚨 Por que existe (17/08/2026, caso cliente-20): a passada 2 do
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
#  FUSÃO POR QUANTIDADE IGUAL — só junta o que é o MESMO item
# ══════════════════════════════════════════════════════════════════════
# 🩸 22/09/2026 (jobs 844603fb e f8d8e6d8). As passadas 1 e 2 do
# `_consolidate_items` juntam linhas com a MESMA quantidade e ficam com a
# quantidade de UMA só. Existem pra tirar o dobro de verdade: o mesmo item
# lido em duas pranchas/vistas ("Forro — Varanda" e "Forro de gesso liso —
# Varanda"), ou a mesma medida que veio em unidades trocadas (m² × ml).
# Só que quantidade igual é coincidência comum, e o critério era "mesmo
# primeiro substantivo OU 2 palavras em comum":
#   - 844603fb (planta de pontos): interruptor sumiu dentro de tomada (as duas
#     dizem "simples monopolar") e o ponto de tomada a H=1,80 m dentro do de
#     H=1,30 m (a chave da passada 1 corta tudo depois do " — "). Dos 67
#     interruptores que a IA contou, a planilha ficou com 10;
#   - f8d8e6d8 (estrutura): o concreto do poço de sucção dentro do concreto do
#     poço com depósito de areia; o do radier EL.332.70 dentro do da laje
#     EL.335.60; a fôrma de um poço dentro da do outro, em pranchas diferentes.
# 🔑 Agora a fusão exige as DUAS coisas:
#   (1) nada que diferencie os dois (`motivo_para_nao_fundir`);
#   (2) prova de que é o mesmo item (`prova_de_mesmo_item`).
# 🪤 Na dúvida ficam duas linhas: duplicar é um erro que o arquiteto VÊ na
# planilha; apagar é um que ele não tem como ver (a mesma decisão que a
# passada 6 tomou em 06/09).
# 🪤 `pode_fundir`, acima, fica como estava: a passada 6 (o aviso de "aparece
# em N pranchas"), a 3 e a réplica da 1 — as que SOMAM ou só avisam — ainda
# usam só ele. Esta régua é das fusões que GUARDAM A QUANTIDADE DE UMA SÓ.

# artigo, preposição e as palavras genéricas da chave da passada 1.
# 🪤 Menos o MATERIAL ("cerâmico", "metálico"), que a chave trata como genérico:
# aqui "Piso cerâmico" × "Piso vinílico" são dois pisos.
_VAZIAS_FUSAO = frozenset((
    "a", "o", "e", "ou", "as", "os", "de", "do", "da", "dos", "das", "d",
    "para", "p", "com", "c", "em", "no", "na", "nos", "nas", "ao", "aos",
    "por", "sem", "sob", "sobre", "entre", "ate", "um", "uma", "cada",
    "nova", "novo", "novas", "novos", "existente", "existentes", "conforme",
    "especificacao", "especificacoes", "projeto", "instalacao", "execucao",
    "fornecimento", "fornecida", "fornecido", "tipo", "tipos", "cor", "modelo",
    "padrao", "altura", "comprimento", "largura", "espessura", "area", "areas",
    "m2", "m", "un", "ml",
    "incluindo", "inclui", "inclusive", "incluso", "inclusos", "total",
))

# posição na obra: guarda-corpo da fachada frontal não é o da lateral leste
_POSICOES_FUSAO = frozenset((
    "frontal", "lateral", "fundos", "posterior", "norte", "sul", "leste", "oeste",
))

# unidades que medem (comprimento/área/volume): a IA troca uma pela outra na
# MESMA medida. "6 m²" de armário × "6 un" de módulo não é troca, é outra coisa.
_UNIDADES_DE_MEDIDA_FUSAO = frozenset(("m", "ml", "m²", "m³"))

# palavras de linha VAGA: dizem o que falta na prancha, não o que o item é.
# 🔑 Sem elas "Forro — Varanda — tipo e acabamento a confirmar" (a leitura
# vaga) cabe em "Forro de gesso liso — Varanda (37,98 m²)" (a completa).
_LACUNA_FUSAO = frozenset((
    "confirmar", "confirmado", "confirmada", "definir", "definido", "definida",
    "especificado", "especificada", "especificados", "especificadas",
    "especificar", "informado", "informada", "indicado", "indicada",
    "indicados", "indicadas", "indicacao", "legenda", "prancha", "pranchas",
    "planta", "plantas", "nesta", "neste", "desta", "deste", "analisada",
    "analisadas", "memorial", "descritivo", "visivel", "identificado",
    "identificada", "identificados", "identificadas", "nao", "acabamento",
    "detalhe", "fabricante", "referencia", "estimado", "estimada", "ver",
    "mesmo", "mesma", "geral", "item", "itens",
))

# palavras de ação que vêm ANTES do item ("Assentamento de piso" é piso)
_ACOES_FUSAO = frozenset((
    "aplicacao", "assentamento", "colocacao", "montagem", "levantamento",
    "construcao", "confeccao", "implantacao", "execucao", "fornecimento",
    "instalacao", "fabricacao",
))

# pares que se EXCLUEM: parede interna não é parede externa
_OPOSTOS_FUSAO = (
    ("interna", "externa"), ("masculino", "feminino"), ("fria", "quente"),
    ("entrada", "saida"), ("superior", "inferior"), ("esquerda", "direita"),
    ("positiva", "negativa"), ("agua", "esgoto"), ("maior", "menor"),
)

# aparelhos: ponto de esgoto do mictório não é o da bacia e do lavatório.
# 🪤 Sem "banheira": na raiz ela é "banheir", a mesma de "banheiro" (ambiente).
_APARELHOS_FUSAO = frozenset((
    "bacia", "vaso", "mictorio", "lavatorio", "pia", "cuba", "tanque", "chuveiro",
    "ducha", "bebedouro", "torneira", "ralo", "filtro", "geladeira",
    "fogao", "cooktop", "forno", "microondas", "lavadora", "secadora",
))

# cor do material: "cor VERDE COLONIAL" × "cor branco neve" são duas pinturas.
# 🪤 "(cor ciano na planta)" é a cor do HACHURADO do desenho, não do material —
# sai antes de comparar.
_CORES_FUSAO = frozenset((
    "branco", "preto", "cinza", "grafite", "verde", "azul", "amarelo", "vermelho",
    "marrom", "bege", "rosa", "roxo", "laranja", "dourado", "prata", "creme",
    "terracota", "vinho", "caramelo",
))
_RX_COR_DO_DESENHO = _re.compile(
    r"(?:\bcor\s+)?[\w/\s\-]{0,40}?\s+(?:na|da|em)\s+planta\b|\bhachura\s+\w+", _re.IGNORECASE)
# "cor CAMURÇA" × "cor AREIA": o nome que vem depois de "cor" também é cor
_RX_NOME_DA_COR = _re.compile(r"\bcor(?:es)?\s*[:=]?\s+([a-z]{3,})", _re.IGNORECASE)

# elementos e superfícies da obra: radier não é laje, parede não é forro
_ELEMENTOS_FUSAO = frozenset((
    "poco", "caixa", "reservatorio", "cisterna", "tanque", "camara", "bloco",
    "laje", "radier", "sapata", "viga", "pilar", "muro", "cortina", "escada",
    "rampa", "galeria", "estaca", "tubulao", "baldrame", "marquise",
    "platibanda", "parede", "forro", "teto", "piso", "fachada", "calcada",
))

# ambientes: o piso da varanda não é o piso da sala de TV
_AMBIENTES_FUSAO = frozenset((
    "sala", "quarto", "qto", "suite", "dormitorio", "banheiro", "bwc", "wc",
    "lavabo", "cozinha", "copa", "varanda", "sacada", "terraco", "closet",
    "escritorio", "circulacao", "corredor", "hall", "deposito", "lavanderia",
    "garagem", "recepcao", "estar", "jantar", "despensa", "gourmet",
    "quiosque", "auditorio", "vestiario", "refeitorio", "almoxarifado",
    "guarita", "lixeira", "estacionamento", "mezanino", "banho",
))
# 🩸 22/09/2026 (revisão): "Ralo — Lavabo 01" × "Ralo — Banho de Serviço" fundiam — "banho"
# não era ambiente. Na raiz ele é "banh" e o banheiro é "banheir": o sinônimo junta os
# dois, senão "Banho social" × "Banheiro social" (o mesmo cômodo) viraria um conflito.
_SINONIMOS_AMBIENTE_FUSAO = {"banho": "banheiro"}

# estruturas que costumam ter NOME ("poço de sucção", "caixa de inspeção")
_NOMEADAS_FUSAO = frozenset((
    "poco", "caixa", "reservatorio", "cisterna", "tanque", "camara", "bloco",
    "laje", "casa", "galeria", "estacao", "torre", "muro", "cortina",
))
_PREP_DO_NOME = frozenset(("de", "do", "da", "dos", "das", "com", "c", "d", "para", "p"))

# rótulo: "Banheiro 01" × "Banheiro 02", "Conjunto CD" × "Conjunto CE", "Lote 01"
# 🪤 o rótulo é número ou SIGLA EM MAIÚSCULA: "casa de bombas" não tem rótulo "de"
# 🩸 22/09/2026 (revisão): "posição 1" × "posição 2" de um bloqueio de madeira fundiam
# (os números soltos dos dois lados se cancelavam) — "posição" também rotula.
_RX_ROTULO = _re.compile(
    r"(?i:\b(conjunto|lote|bloco|torre|quadra|setor|ala|trecho|etapa|fase|apto|"
    r"apartamento|sala|quarto|qto|su[ií]te|banheiro|wc|bwc|quiosque|dormit[oó]rio|"
    r"garagem|vaga|jardim|servi[cç]o|circ|circuito|posi[cç][aã]o|pos))s?\.?\s+(?:n[º°o.]\s*)?"
    r"([A-Z]{0,3}\d{1,3}(?:[.\-]\d{1,3})*|[A-Z]{1,3})\b")

# até onde vai a CABEÇA da descrição — o nome do item, antes do detalhe.
# 🪤 Inclui os cortes da chave da passada 1 (" departamento ", " sala "...): sem
# eles "Demarcação — departamento RH" e "— departamento Marketing", réplicas que a
# passada 1 SOMA de propósito, teriam nomes que se excluem.
_RX_FIM_DA_CABECA = _re.compile(
    r"\s[—–-]\s|[(,;:]|\sconforme\s|\s/\s|\s(?:departamento|deptos|do depto|da sala|sala|"
    r"para sala)\s", _re.IGNORECASE)

# 🔑 cobertura mínima: quanto do que a descrição MAIS CURTA diz tem que estar
# na outra. 📏 Replay de 22/09 (33 jobs de cliente, llm_cache de 60 d): entre
# 0,60 e 0,75 ficam duplicatas de verdade ("Piso — Garagem (17,38 m²) — a
# definir" × "Piso em concreto desempenado — Garagem"; "Transporte de material
# excedente (bota-fora)" em duas pranchas); abaixo de 0,60 começam os pares
# diferentes que nenhuma outra régua pega ("Ponto de detecção de incêndio —
# acionador manual" × "— sensor/detector", 0,57).
COBERTURA_MINIMA_FUSAO = 0.60

_NUMERO_EXTENSO = {"uma": "1", "um": "1", "duas": "2", "dois": "2", "tres": "3",
                   "quatro": "4"}


def _raiz_fusao(t: str) -> str:
    """Raiz grosseira: plural e gênero ("internas" e "internos" → "intern")."""
    if any(ch.isdigit() for ch in t):
        return _re.sub(r"(?<!\d)0+(?=\d)", "", t)          # "p09" == "p9", "100" fica
    if len(t) > 4 and t.endswith("oes"):
        t = t[:-3] + "ao"                                  # botões → botao
    elif len(t) > 5 and t.endswith(("res", "zes", "les")):
        t = t[:-2]                                         # interruptores
    elif len(t) > 4 and t.endswith("ns"):
        t = t[:-2] + "m"                                   # ferragens
    elif len(t) > 3 and t.endswith("s"):
        t = t[:-1]
    # 🪤 sem cortar o "o" de "-ão": "portao" viraria "porta"
    if len(t) >= 5 and t[-1] in "ao" and not t.endswith("ao"):
        t = t[:-1]                                         # preto/preta
    return t


# os vocabulários acima, na mesma raiz em que os tokens são comparados
_LACUNA_R = frozenset(map(_raiz_fusao, _LACUNA_FUSAO))
_ACOES_R = frozenset(map(_raiz_fusao, _ACOES_FUSAO))
_OPOSTOS_R = tuple((_raiz_fusao(x), _raiz_fusao(y)) for x, y in _OPOSTOS_FUSAO)
_ELEMENTOS_R = frozenset(map(_raiz_fusao, _ELEMENTOS_FUSAO))
_AMBIENTES_R = frozenset(map(_raiz_fusao, _AMBIENTES_FUSAO))
_SINONIMO_AMBIENTE_R = {_raiz_fusao(k): _raiz_fusao(v) for k, v in _SINONIMOS_AMBIENTE_FUSAO.items()}
_NOMEADAS_R = frozenset(map(_raiz_fusao, _NOMEADAS_FUSAO))
_POSICOES_R = frozenset(map(_raiz_fusao, _POSICOES_FUSAO))
_APARELHOS_R = frozenset(map(_raiz_fusao, _APARELHOS_FUSAO))
_CORES_R = frozenset(map(_raiz_fusao, _CORES_FUSAO))


def _texto_fusao(desc: str) -> str:
    return _sem_acento(desc or "").lower()


def _tokens_fusao(desc: str) -> list:
    """Palavras que dizem o que o item É, em ordem, já na raiz.

    Número com casa decimal ou com unidade ("37,98 m²", "3 cm") sai: é MEDIDA,
    e medida é comparada pelos atributos. Número solto fica ("Suíte 03").
    """
    s = _texto_fusao(desc)
    s = _re.sub(r"\d+[.,]\d+", " ", s)
    s = _re.sub(r"\b\d+\s*(?:mm|cm|m|m2|m3|kg|w|a|v|l|btu|mpa)\b", " ", s)
    out = []
    for t in _re.findall(r"[a-z0-9]+", s):
        if len(t) < 2 or t in _VAZIAS_FUSAO:
            continue
        out.append(_raiz_fusao(t))
    return out


def _substantivo_fusao(tokens: list) -> str:
    """O primeiro nome de coisa: "Execução de alvenaria nova" → alvenaria."""
    for t in tokens:
        if len(t) >= 3 and not any(ch.isdigit() for ch in t) \
                and t not in _ACOES_R and t not in _LACUNA_R:
            return t
    return ""


def _conjunto(regexes, s, norm) -> frozenset:
    vals = set()
    for rx in regexes:
        for m in rx.finditer(s):
            v = norm(m)
            if v:
                vals.add(v)
    return frozenset(vals)


def _num(v: str) -> float:
    return float(str(v).replace(",", "."))


def _norm_altura(m) -> str:
    """Altura em centímetros. "0,30 cm do piso" é erro de digitação de metro."""
    try:
        v = _num(m.group(1))
    except (TypeError, ValueError):
        return ""
    u = (m.group(2) or "").lower() if m.re.groups >= 2 else ""
    if u == "m" or (u == "cm" and v < 5) or (not u and v < 10):
        v *= 100
    return str(int(round(v)))


_RX_ALTURA = (
    _re.compile(r"\b[Hh]\s*[=:]\s*(\d{1,3}(?:[.,]\d{1,2})?)\s*(cm|m)?(?![a-z0-9])", _re.I),
    _re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*(cm|m)\s+do\s+piso", _re.I),
    _re.compile(r"\baltura\s*(?:de\s*)?(\d{1,3}(?:[.,]\d{1,2})?)\s*(cm|m)\b", _re.I),
)
# corrente: "20A", "10 A", "2P+T-20A" — A MAIÚSCULO, senão "110 a 120" casaria
_RX_CORRENTE = (_re.compile(r"(?<![\w.,])(\d{1,3})\s?A\b"),)
_RX_TENSAO = (_re.compile(r"(?<![\w.,])(\d{2,3})\s?V(?:CA|AC)?\b"),)
_RX_POTENCIA = (_re.compile(
    r"(?<![\w.,])(\d{1,3}\.\d{3}(?:,\d)?|\d{1,4}(?:[.,]\d)?)\s?[Ww]\b"),)
_RX_BTU = (_re.compile(r"(\d{1,3}(?:[.\s]?\d{3})?)\s*btu", _re.I),)
_RX_LITROS = (_re.compile(r"(?<![\w.,])(\d{1,3}(?:[.\s]?\d{3})?)\s*(?:l|litros)\b", _re.I),)
_RX_TECLAS = (_re.compile(r"\b(\d|uma|duas|tres|tr[eê]s|quatro)\s+teclas?\b", _re.I),)
_RX_NIVEL = (
    _re.compile(r"\bel\s*\.?\s*[+\-]?\s*(\d{1,4}[.,]\d{1,3})", _re.I),
    _re.compile(r"\bn[ií]vel\s*[+\-]?\s*(\d{1,4}[.,]\d{1,3})", _re.I),
)
_RX_PAVIMENTO = (
    _re.compile(r"\b(t[eé]rreo|subsolo|mezanino)\b", _re.I),
    _re.compile(r"\bpavimento\s+(superior|\d{1,2})\b", _re.I),
    _re.compile(r"\b(\d{1,2})\s*[ºo°]\s*(?:pav|andar)", _re.I),
)
# medida: "80×80cm", "0,90 × 2,10 m", "4x2" — em qualquer ordem ("2×4" = "4×2")
_RX_MEDIDA = (_re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[.,]\d{1,2})?)\s*[x×]\s*(\d{1,3}(?:[.,]\d{1,2})?)(?![\d])", _re.I),)
# 🩸 22/09/2026 (revisão): a prancha em polegada traz o métrico entre colchetes —
# "altura 2'-6\" [762mm]" × "2'-6 1/2\" [775mm]" são duas peças.
_RX_MEDIDA_MM = (_re.compile(r"\[\s*(\d{1,4}(?:[.,]\d{1,2})?)\s*mm\s*\]", _re.I),)
# bitola: "diâmetro 32mm", "ø25", "DN 50", "Ø3/4\"" (o `pode_fundir` não lê o "â")
_RX_BITOLA = (
    _re.compile(r"(?:di[aâ]metro|diam\.?|ø|⌀|\bdn)\s*(\d{1,2}\s*/\s*\d{1,2}|\d{1,3}(?:[.,]\d)?)", _re.I),
)
# código de projeto/legenda: LM05c, PM02, CP.01, EEM.03, EQc.13, P21, V3
_RX_CODIGO = (_re.compile(
    r"(?<![A-Za-z0-9.])([A-Z]{1,4}[a-z]?(?:\.[A-Za-z]{1,3})*)[.\-]?(\d{1,3}(?:[.\-]\d{1,3})*)"
    r"(?:[.\-]?([a-zA-Z]))?(?![A-Za-z0-9])"),)
_NAO_E_CODIGO = frozenset(("NBR", "ABNT", "CA", "DN", "PVC", "BTU", "IP", "AF", "EL",
                           "NR", "ISO", "UV", "LED", "KW", "A", "W", "MPA", "TR", "CPVC"))


def _norm_simples(m) -> str:
    return _re.sub(r"\s+", "", m.group(1) or "").replace(",", ".").lower()


def _norm_numero(m) -> str:
    try:
        return "%g" % _num(_re.sub(r"[\s.](?=\d{3}\b)", "", m.group(1)))
    except (TypeError, ValueError):
        return ""


def _norm_bitola(m) -> str:
    v = _re.sub(r"\s+", "", m.group(1) or "")
    if "/" in v:
        return v                                   # polegada: "3/4"
    try:
        return "%g" % _num(v)                      # "5,0" == "5"
    except (TypeError, ValueError):
        return ""


def _norm_teclas(m) -> str:
    v = _sem_acento(m.group(1) or "").lower()
    return _NUMERO_EXTENSO.get(v, v)


def _norm_nivel(m) -> str:
    try:
        return "%.2f" % _num(m.group(1))
    except (TypeError, ValueError):
        return ""


def _norm_pavimento(m) -> str:
    return _sem_acento(m.group(1) or "").lower()


def _norm_medida(m) -> str:
    try:
        a, b = sorted((_num(m.group(1)), _num(m.group(2))))
    except (TypeError, ValueError):
        return ""
    return "%gx%g" % (a, b)


def _norm_codigo(m) -> str:
    pre = m.group(1) or ""
    if pre.upper().split(".")[0] in _NAO_E_CODIGO:
        return ""
    # "QLF-10-1" × "QLF-10-2", "QTR-10-A" × "QTR-10-B", "T1.14" × "T1.15"
    num = "-".join(str(int(p)) for p in _re.split(r"[.\-]", m.group(2)))
    return "%s%s%s" % (pre.upper(), num, (m.group(3) or "").lower())


def _atributos_fusao(desc: str) -> dict:
    """{categoria: conjunto de valores} — o que muda a COMPRA do item."""
    s = str(desc or "")
    cats = {
        "altura": _conjunto(_RX_ALTURA, s, _norm_altura),
        "corrente": _conjunto(_RX_CORRENTE, s, _norm_simples),
        "tensao": _conjunto(_RX_TENSAO, s, _norm_simples),
        "potencia": _conjunto(_RX_POTENCIA, s, _norm_numero),
        "btu": _conjunto(_RX_BTU, s, _norm_numero),
        "litros": _conjunto(_RX_LITROS, s, _norm_numero),
        "teclas": _conjunto(_RX_TECLAS, s, _norm_teclas),
        "nivel": _conjunto(_RX_NIVEL, s, _norm_nivel),
        "pavimento": _conjunto(_RX_PAVIMENTO, s, _norm_pavimento),
        "medida": _conjunto(_RX_MEDIDA, s, _norm_medida),
        "medida_mm": _conjunto(_RX_MEDIDA_MM, s, _norm_numero),
        "bitola": _conjunto(_RX_BITOLA, s, _norm_bitola),
        "codigo": _conjunto(_RX_CODIGO, s, _norm_codigo),
    }
    return {k: v for k, v in cats.items() if v}


def assinatura_de_atributos(desc: str) -> tuple:
    """Os atributos de compra num formato que entra em CHAVE de agrupamento.

    🩸 22/09/2026 (844603fb): a chave da passada 1 corta tudo depois do " — ",
    e "Ponto de tomada — H=1,80m" e "Ponto de tomada — H=1,30m" viravam a mesma
    linha. Com a assinatura na chave, a altura não some antes de ser comparada.
    """
    _at = dict(_atributos_fusao(desc))
    _at.update({"rotulo:" + k: v for k, v in _rotulos_fusao(desc).items()})
    return tuple(sorted((k, tuple(sorted(v))) for k, v in _at.items()))


def _prancha_da_ref(ref_sheet: str) -> str:
    """Arquivo + página: "x.pdf (p3 · Planta)" → "x.pdf#p3". Vazio = sem prancha."""
    r = str(ref_sheet or "").strip()
    arq = r.split(" (")[0].strip().lower()
    m = _re.search(r"\(\s*p(\d+)\b", r)
    return arq + ("#p" + m.group(1) if m else "")


# número de REFERÊNCIA não é rótulo do item: "NBR 9050", "SINAPI AF_01/2024",
# "planta baixa 38 e fachadas 39/40", "keynote 26". Um lado citar a norma e o
# outro não, não faz deles dois itens.
_RX_NUMERO_DE_REFERENCIA = _re.compile(
    r"\b(?:nbr|abnt|sinapi|sicor|tcpo|af|ed|prancha|pranchas|folha|folhas|vista|vistas|"
    r"nota|notas|keynote|item|itens|detalhe|detalhes|corte|cortes|planta|plantas|baixa|"
    r"legenda|rev|revisao|fachada|fachadas|elevacao|elevacoes|serie|circuito|circuitos)"
    r"\b[\s._\-:ºo°n]*[\d][\d\s,e/._\-]*", _re.IGNORECASE)


# número com sufixo MINÚSCULO colado: "Comando 1a" × "Comando 1b"
_RX_NUMERO_COM_LETRA = _re.compile(r"(?<![\w.,/])(\d{1,3})([a-z])(?!\w)")


def _numeros_fusao(desc: str) -> frozenset:
    """Números soltos que ROTULAM o item ("Circulação 01", "Pl.vi.fi.02", "Comando 1a")."""
    s = _texto_fusao(desc)
    s = _RX_NUMERO_DE_REFERENCIA.sub(" ", s)
    s = _re.sub(r"\d+[.,]\d+", " ", s)
    s = _re.sub(r"\b\d+\s*(?:mm|cm|m|m2|m3|kg|w|a|v|l|btu|mpa|x)\b", " ", s)
    s = _re.sub(r"\d+\s*[x×]\s*\d+", " ", s)
    out = {str(int(n)) for n in _re.findall(r"(?<![a-z0-9])(\d{1,3})(?![a-z0-9])", s)}
    # 🩸 22/09/2026 (revisão): "Comando 1a (16S)" × "Comando 1b (6S)" de um sistema DALI
    # fundiam. Lido no texto CRU: em minúsculas o "1a" some como ampère, e o sufixo
    # MAIÚSCULO é unidade (10A, 220V) — só o minúsculo é rótulo.
    # 🪤 Sem tirar acento: o NFKD faz do ordinal "1ª categoria" um "1a", e a mesma
    # escavação lida em duas pranchas deixava de fundir (replay, c378477f).
    cru = _RX_NUMERO_DE_REFERENCIA.sub(" ", str(desc or ""))
    out.update("%d%s" % (int(n), l) for n, l in _RX_NUMERO_COM_LETRA.findall(cru))
    return frozenset(out)


def _rotulos_fusao(desc: str) -> dict:
    """{"banheiro": {"1"}, "conjunto": {"CD"}} — o rótulo que separa gêmeos."""
    out: dict = {}
    for m in _RX_ROTULO.finditer(str(desc or "")):
        chave = _raiz_fusao(_sem_acento(m.group(1)).lower())
        v = m.group(2)
        out.setdefault(chave, set()).add(str(int(v)) if v.isdigit() else v)
    return {k: frozenset(v) for k, v in out.items()}


def perfil_de_fusao(desc: str, unidade: str = "", ref_sheet: str = "") -> dict:
    """Tudo o que as duas réguas abaixo comparam, calculado UMA vez por item."""
    brutos = _re.findall(r"[a-z0-9]+", _texto_fusao(desc))
    toks = _tokens_fusao(desc)
    cabeca = _RX_FIM_DA_CABECA.split(str(desc or ""), maxsplit=1)[0]
    # nome de estrutura: lido na sequência CRUA (com as preposições)
    nomes: dict = {}
    for i, t in enumerate(brutos):
        r = _raiz_fusao(t)
        if r not in _NOMEADAS_R:
            continue
        q = set()
        j = i + 1
        if j < len(brutos) and brutos[j] in _PREP_DO_NOME:
            for k in range(j + 1, min(j + 3, len(brutos))):
                w = brutos[k]
                if w in _VAZIAS_FUSAO or w in _PREP_DO_NOME:
                    continue
                rw = _raiz_fusao(w)
                if not any(ch.isdigit() for ch in w) and rw not in _LACUNA_R:
                    q.add(rw)
                break
        nomes.setdefault(r, set()).update(q)
    # ambiente com NOME: "WC Hóspedes" × "WC Bebê", "Quarto Casal" × "Quarto Bebê"
    ambientes_nomes: dict = {}
    for i, t in enumerate(brutos):
        r = _raiz_fusao(t)
        if r not in _AMBIENTES_R:
            continue
        r = _SINONIMO_AMBIENTE_R.get(r, r)
        j = i + 1
        while j < len(brutos) and brutos[j] in _PREP_DO_NOME:
            j += 1
        q = set()
        if j < len(brutos):
            w = brutos[j]
            rw = _raiz_fusao(w)
            if w.isalpha() and len(w) >= 3 and w not in _VAZIAS_FUSAO \
                    and rw not in _LACUNA_R and rw not in _ACOES_R:
                q.add(rw)
        ambientes_nomes.setdefault(r, set()).update(q)
    _sem_desenho = _RX_COR_DO_DESENHO.sub(" ", str(desc or ""))
    cores = set(t for t in _tokens_fusao(_sem_desenho) if t in _CORES_R)
    for _m in _RX_NOME_DA_COR.finditer(_sem_acento(_sem_desenho)):
        _c = _raiz_fusao(_m.group(1).lower())
        if _c not in _VAZIAS_FUSAO and _c not in _LACUNA_R:
            cores.add(_c)
    cores = frozenset(cores)
    _u = (unidade or "").strip().lower().replace("2", "²").replace("3", "³")
    return {
        "desc": desc or "",
        "unidade": _u,
        "prancha": _prancha_da_ref(ref_sheet),
        "substantivo": _substantivo_fusao(toks),
        "palavras": frozenset(t for t in toks if t not in _LACUNA_R and t not in _ACOES_R),
        "cabeca": frozenset(t for t in _tokens_fusao(cabeca)
                            if t not in _LACUNA_R and t not in _ACOES_R),
        "raizes": frozenset(toks),
        "atributos": _atributos_fusao(desc),
        "rotulos": _rotulos_fusao(desc),
        # número solto que rotula o item (medida, unidade e norma já saíram)
        "numeros": _numeros_fusao(desc),
        "elementos": frozenset(t for t in toks if t in _ELEMENTOS_R),
        "ambientes": frozenset(_SINONIMO_AMBIENTE_R.get(t, t) for t in toks if t in _AMBIENTES_R),
        "ambientes_nomes": {k: frozenset(v) for k, v in ambientes_nomes.items()},
        "posicoes": frozenset(t for t in toks if t in _POSICOES_R),
        "aparelhos": frozenset(t for t in toks if t in _APARELHOS_R),
        "cores": cores,
        "nomes": {k: frozenset(v) for k, v in nomes.items()},
    }


def _perfil(x) -> dict:
    return x if isinstance(x, dict) else perfil_de_fusao(x)


def motivo_para_nao_fundir(a, b) -> str:
    """'' quando nada DIFERENCIA os dois itens; senão, o motivo em poucas palavras.

    `a` e `b` são perfis (`perfil_de_fusao`) ou descrições. Cada regra só
    bloqueia quando os DOIS lados dizem algo e o que dizem se exclui — atributo
    presente de um lado só não bloqueia (a leitura vaga não diz a altura).
    """
    a, b = _perfil(a), _perfil(b)
    if a["substantivo"] and b["substantivo"] and a["substantivo"] != b["substantivo"]:
        return "substantivo %s × %s" % (a["substantivo"], b["substantivo"])
    if not pode_fundir(a["desc"], b["desc"]):
        return "atributo (bitola/classe/fck/medida/código)"
    for cat in set(a["atributos"]) & set(b["atributos"]):
        va, vb = a["atributos"][cat], b["atributos"][cat]
        # 🪤 código: basta cada lado ter um que o outro não tem — o modelo
        # "RX-24" em comum não faz o filtro FX1 virar o FX2
        if (not (va & vb)) or (cat == "codigo" and (va - vb) and (vb - va)):
            return "%s %s × %s" % (cat, "/".join(sorted(va - vb or va))[:30],
                                   "/".join(sorted(vb - va or vb))[:30])
    for cat in set(a["rotulos"]) & set(b["rotulos"]):
        if not (a["rotulos"][cat] & b["rotulos"][cat]):
            return "rotulo %s %s × %s" % (cat, "/".join(sorted(a["rotulos"][cat])),
                                          "/".join(sorted(b["rotulos"][cat])))
    # número: como o código, basta cada lado ter um que o outro não tem
    # ("tipo 1 — ambiente 9" × "tipo 1 — ambiente 105")
    if (a["numeros"] - b["numeros"]) and (b["numeros"] - a["numeros"]):
        return "numeros %s × %s" % ("/".join(sorted(a["numeros"] - b["numeros"]))[:20],
                                    "/".join(sorted(b["numeros"] - a["numeros"]))[:20])
    # 🔑 o NOME do item (a cabeça, antes do primeiro " — ", vírgula ou
    # parêntese): cada um tem uma palavra que o outro não tem → são dois itens
    # ("Interruptor duplo" × "Interruptor intermediário", "Portão de acesso" ×
    # "Portão de saída"). Se um nome cabe no outro, não é conflito ("Forro" ×
    # "Forro de gesso liso").
    if (a["cabeca"] - b["cabeca"]) and (b["cabeca"] - a["cabeca"]):
        return "nomes %s × %s" % ("/".join(sorted(a["cabeca"] - b["cabeca"]))[:40],
                                  "/".join(sorted(b["cabeca"] - a["cabeca"]))[:40])
    ra, rb = a["raizes"], b["raizes"]
    for x, y in _OPOSTOS_R:
        if (x in ra and y not in ra and y in rb and x not in rb) or \
                (y in ra and x not in ra and x in rb and y not in rb):
            return "lados opostos %s × %s" % (x, y)
    if a["elementos"] and b["elementos"] and not (a["elementos"] & b["elementos"]):
        return "elementos %s × %s" % ("/".join(sorted(a["elementos"])),
                                      "/".join(sorted(b["elementos"])))
    if a["ambientes"] and b["ambientes"] and not (a["ambientes"] & b["ambientes"]):
        return "ambientes %s × %s" % ("/".join(sorted(a["ambientes"])),
                                      "/".join(sorted(b["ambientes"])))
    for amb in set(a["ambientes_nomes"]) & set(b["ambientes_nomes"]):
        qa, qb = a["ambientes_nomes"][amb], b["ambientes_nomes"][amb]
        if qa and qb and not (qa & qb):
            return "ambiente %s %s × %s" % (amb, "/".join(sorted(qa)), "/".join(sorted(qb)))
    for cat in ("posicoes", "aparelhos", "cores"):
        if a[cat] and b[cat] and not (a[cat] & b[cat]):
            return "%s %s × %s" % (cat, "/".join(sorted(a[cat])), "/".join(sorted(b[cat])))
    for est in set(a["nomes"]) & set(b["nomes"]):
        qa, qb = a["nomes"][est], b["nomes"][est]
        if qa and qb and not (qa & qb):
            return "%s %s × %s" % (est, "/".join(sorted(qa)), "/".join(sorted(qb)))
    # 🔑 Em pranchas diferentes, "o poço" de uma não prova ser "o poço de
    # sucção" da outra (f8d8e6d8: a fôrma de 22 m² de dois poços).
    if a["prancha"] and b["prancha"] and a["prancha"] != b["prancha"]:
        for p, q in ((a, b), (b, a)):
            for est, nomes in p["nomes"].items():
                if nomes and not (nomes & q["raizes"]):
                    return "%s %s só numa das pranchas" % (est, "/".join(sorted(nomes)))
    return ""


def prova_de_mesmo_item(a, b) -> bool:
    """A mesma quantidade só junta com PROVA de que é o mesmo item:

    - a mesma medida veio em unidades diferentes (a IA errou a unidade de UM
      item: 222,11 m² e 222,11 ml da mesma linha de LED); ou
    - uma descrição CABE na outra: pelo menos `COBERTURA_MINIMA_FUSAO` do que a
      mais curta diz do item está na mais longa ("Forro — Varanda — a
      confirmar" cabe em "Forro de gesso liso — Varanda (37,98 m²)").
    """
    a, b = _perfil(a), _perfil(b)
    if " ".join(a["desc"].lower().split()) == " ".join(b["desc"].lower().split()):
        return True                                  # a mesma linha, repetida
    if a["unidade"] != b["unidade"] and {a["unidade"], b["unidade"]} <= _UNIDADES_DE_MEDIDA_FUSAO:
        return True
    return cobertura_fusao(a, b) >= COBERTURA_MINIMA_FUSAO


def cobertura_fusao(a, b) -> float:
    """Fração das palavras da descrição mais curta que a outra também tem."""
    a, b = _perfil(a), _perfil(b)
    pa, pb = a["palavras"], b["palavras"]
    menor, maior = (pa, pb) if len(pa) <= len(pb) else (pb, pa)
    if not menor:
        return 0.0
    return len(menor & maior) / len(menor)


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
# escala. No arquivo do cliente-81, as 32 janelas e as 4 geladeiras viraram
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
# 🚨 Descoberta em 17/08/2026 no arquivo do cliente-81 (75a774af), depois de
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
# leitura antiga. Caso cliente-19 (e1c48ed7 × ev597afa), medido no banco:
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
    filhote do cliente-19 parecia melhor (151 × 92) e ainda assim tinha perdido 20
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

    🚨 26/08/2026, caso **cliente-41** (cliente do dia, baixou às 13:20).
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
    (caso cliente-14, 31/08 — 16 pranchas, `resgate_pdf=0` com medição existindo).

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

    # 🩸 31/08/2026 (caso cliente-14) — A RÉGUA COMPARAVA CONTRA A SOMA DO JOB.
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

    🚨 26/08/2026, caso cliente-19 (job de 24/08 21:39): 31 de 73 linhas de área e
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
# 🩸 04/09/2026, olhando o 1º projeto da cliente-22. A planilha dela
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

# 🩸 14/09/2026 — SETA DE COTA VENDIDA COMO PORTA, COM SELO BRANCO.
# Medido na base: **7 linhas em 5 projetos de cliente, 5 delas `confirmado`,
# 40 unidades** entregues como MEDIDAS — de 17/07 até hoje. Num deles, os dois
# itens sozinhos eram **52,6% de tudo que o projeto vendia como medido**:
#   · "Pontos de conexão / sprinklers / derivações — bloco _DOT"     17 un ✓
#   · "Esquadrias gerais — bloco _Open90 (portas com abertura 90°)"  13 un ✓
#
# 🔑 `_DOT` e `_OPEN90` NÃO são blocos do projetista: são os nomes reservados
# que o próprio AutoCAD instala para as PONTAS DE SETA de cota. O desenho tinha
# 59 cotas. A contagem de INSERTs está certa — o que é falso é a identidade, e
# o selo branco diz ao cliente que aquilo foi medido do projeto.
#
# 🪤 Por que uma régua NOVA em vez de alargar a frase: a fronteira acima é
# estreita de propósito e está certa — "Porta de abrir 90° — conforme bloco
# 'j3'" tem item real e só falta o tipo. Aqui o item NÃO é real. Lista FECHADA
# de nomes de sistema, com fronteira dos dois lados: um bloco de projetista
# chamado `PORTA_OPEN90` ou `DOT-01` não pode ser pego junto.
_RE_BLOCO_DE_SISTEMA = _re.compile(
    r"(?<![A-Za-z0-9_])_("
    r"archtick|box(?:blank|filled)|closed(?:blank|filled)?|"
    r"datum(?:blank|filled)|dot(?:blank|small)?|integral|none|oblique|"
    r"open(?:30|90)?|origin2?|small"
    r")(?![A-Za-z0-9_])", _re.I)


def item_e_bloco_sem_identidade(descricao, unidade) -> bool:
    """A identidade deste item é o nome de um bloco do CAD? Só APONTA.

    Quem rebaixa o selo é o chamador — e só rebaixa, nunca promove.
    """
    _d = str(descricao or "")
    if str(unidade or "").strip().lower() not in _UNIDADES_DE_CONTAGEM:
        return False
    if not _RE_TEM_BLOCO.search(_d):
        return False
    # 🪤 O corte do "identificados POR bloco" NÃO vale para bloco de sistema:
    # ali o item é real e falta o bloco; aqui o "item" é uma ponta de cota.
    if _RE_BLOCO_DE_SISTEMA.search(_d):
        return True
    if _RE_IDENT_POR.search(_d):
        return False
    return bool(_RE_LIDERA_BLOCO.search(_d) or _RE_NAO_IDENT.search(_d))


# ── PAREDE MENOR QUE O PERÍMETRO POSSÍVEL (regra nº1) ──────────────────────
# 🩸 04/09/2026, no 1º projeto da cliente-22. O motor mediu
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
# metro, **3 (16%) estão abaixo do mínimo** — cliente-07 88% abaixo,
# cliente-08 42%, cliente-22 59%. Onze itens BRANCOS saíram desses três.
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
# cliente-22). O guarda do mínimo de parede não disparou — porque nessa rodada a
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
# consumi-lo, e o comentário lá (main.py, caso cliente-70 03/08) diz por quê:
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


def e_administracao_local(descricao):
    """O item é administração local de obra, em qualquer unidade?

    Régua ÚNICA do reconhecimento. Quem pergunta: o prazo chutado (logo abaixo)
    e a junção das linhas repetidas (main.py `_juntar_admin_local`, 15/09). Duas
    cópias do regex divergiriam na primeira redação nova da IA.
    """
    return bool(_RE_ADMIN_LOCAL.search(str(descricao or "")))


def e_administracao_local_pura(descricao):
    """A descrição COMEÇA com administração local — não embala outro serviço?

    🩸 15/09/2026 (revisão da junção): o reconhecimento acima casa em qualquer
    posição, então "Serviços preliminares — mobilização, canteiro e
    administração local" e "Serviços de coordenação e administração local"
    também passavam. Juntar essas levaria o escopo delas junto. Quem junta
    linha repetida pergunta ESTA.
    """
    return bool(_RE_ADMIN_LOCAL.match(str(descricao or "").strip()))


def administracao_local_com_prazo_chutado(descricao, unidade):
    """O item é administração local de obra cotada em unidade de TEMPO?

    Só isso: a pergunta é sobre a natureza do item, não sobre o valor. Um
    item com quantidade 3 e outro com 0 são o mesmo defeito — nos dois a
    unidade declara um prazo que ninguém mediu.
    """
    if not e_administracao_local(descricao):
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


# ══════════════════════════════════════════════════════════════════════════
#  RETRATO DO SELO — instrumento, NÃO conserto
# ══════════════════════════════════════════════════════════════════════════
# 🩸 04/09/2026. Medido em 156 projetos: **53% não têm uma única linha branca**
# e o selo VARIA entre rodadas do mesmo commit (duas rodadas com 3 s de
# diferença deram 9 e 6 medidos). Enquanto isso for verdade, nenhum conserto de
# selo pode ser provado — foi assim que o conserto de 26/08 passou 9 dias
# parecendo ter funcionado, sem ninguém ter contador pra dizer.
#
# 🔑 O que falta medir é o OUTRO LADO do guarda que já existe. `selos_sem_medida`
# olha branco SEM prova (e rebaixa). Ninguém olha laranja COM prova — o teto do
# que poderia ser branco. Sem esse número, mexer no selo é no escuro.
#
# 🚫 ISTO NÃO PROMOVE NADA, e não pode passar a promover. Regra dura nº1: só é
# branco o que veio da geometria, e quem decide isso é o caminho de medição, não
# um contador. Promover a partir daqui seria ressuscitar o cross-check
# aposentado e o "área lida vira medida" — os dois já refutados com medição.
# Este módulo devolve NÚMERO. Quem chama, LOGA.
#
# 🪤 Usa AS MESMAS constantes do guarda que rebaixa (`_PROVA_GEOMETRIA`,
# `_PROVA_LAYER_MEDIDO`). Uma segunda definição de "prova" divergiria da
# primeira em semanas, e aí os dois lados contariam coisas diferentes com o
# mesmo nome.


def _tem_prova_de_geometria(observacao):
    """A observação declara medição de geometria? Mesma régua do `selos_sem_medida`."""
    _obs = str(observacao or "").lower()
    if not _obs:
        return False
    if any(p in _obs for p in _PROVA_GEOMETRIA):
        return True
    return bool(_PROVA_LAYER_MEDIDO.search(_obs))


def retrato_do_selo(items):
    """Fotografia do selo deste job. SÓ CONTA — não altera item nenhum.

    Devolve dict com:
      itens, brancos, laranjas, zerados,
      laranja_com_prova  → o TETO do que poderia virar branco (nunca vira aqui),
      branco_sem_prova   → o inverso; deve ser ~0 porque `selos_sem_medida` já
                           rebaixa. Se subir, é regressão daquele guarda.
    """
    # 🩸 04/09 — RELENDO O PRÓPRIO DIFF. A 1ª versão reimplementava aqui a
    # pergunta "este branco tem prova?" com as mesmas duas constantes do
    # `selos_sem_geometria`. Parecia idêntico e NÃO era: aquele guarda tem
    # ABSOLVIÇÕES que eu não copiei — a principal é o QUADRO DE AÇO (tabela com
    # colunas rotuladas, que ele deliberadamente não rebaixa). Medido no próprio
    # comentário dele: 38 dos 46 confirmados com procedência de texto são aço.
    # Minha versão os acusaria, e o alarme crítico abaixo dispararia FALSO em
    # todo projeto com quadro de aço — alarme sem controle, que a gente desliga
    # em duas semanas e perde o instrumento inteiro.
    # 🔑 Então não reimplemento: PERGUNTO AO GUARDA. O número passa a ser
    # exatamente "o que o `selos_sem_geometria` ainda acusaria depois de ter
    # rodado" — que é 0 quando ele funcionou. Zero divergência possível.
    try:
        branco_sem_prova = len(selos_sem_geometria(items or []))
    except Exception:
        branco_sem_prova = 0
    n = brancos = zerados = laranja_com_prova = 0
    for it in (items or []):
        n += 1
        selo = _campo_do_item(it, "confidence", "")
        selo = str(getattr(selo, "value", selo) or "").strip().lower()
        try:
            qtd = float(_campo_do_item(it, "quantity", 0) or 0)
        except (TypeError, ValueError):
            qtd = 0.0
        if qtd == 0:
            zerados += 1
        prova = _tem_prova_de_geometria(_campo_do_item(it, "observations", ""))
        if selo == "confirmado":
            brancos += 1
        elif qtd > 0 and prova:
            # 🚫 Contado, NUNCA promovido. Ver o bloco de comentário acima.
            laranja_com_prova += 1
    return {
        "itens": n,
        "brancos": brancos,
        "laranjas": n - brancos,
        "zerados": zerados,
        "laranja_com_prova": laranja_com_prova,
        "branco_sem_prova": branco_sem_prova,
    }


# ══════════════════════════════════════════════════════════════════════════
#  NÚMERO QUE O PRÓPRIO MOTOR DIZ SER PARCIAL não pode levar selo BRANCO
# ══════════════════════════════════════════════════════════════════════════
# 🩸 05/09/2026. MEDIDO: 4 itens com selo ✓ MEDIDO cuja observação, na mesma
# linha, diz que o número é um pedaço:
#
#   "comprimento total do layer SAN = 1,42 m. Valor provavelmente parcial"
#   "layer 'A-DUTO-E' = 3,93 m. Trecho curto — provável trecho parcial"
#   "1 ocorrência listada: 9.71 m². Parcial — existem +229 pares não listados"
#
# A geometria FOI medida — por isso o `selos_sem_geometria` os absolve, e com
# razão. O defeito é outro: mediu-se um PEDAÇO e carimbou-se como se fosse o
# item inteiro. O cliente vê 1,42 m de esgoto num prédio e um selo de confiança.
# Regra dura nº1: "medido" quer dizer que a medição é DO ITEM.
#
# 🚫 SÓ REBAIXA. Não corrige o número (regra nº3) — corrigir seria inventar o
# resto que ninguém mediu. E nunca promove nada.
#
# 🪤 A palavra "parcial" sozinha NÃO serve: "planta parcial do 2º pavimento"
# fala do DESENHO, não da medição. Por isso a janela de contexto antes da
# palavra — é a diferença entre guarda e ruído, e alarme com ruído a gente
# desliga em duas semanas.
# 🩸 A 1ª VERSÃO DESTE GUARDA TINHA 80% DE PRECISÃO E EU SÓ VI MEDINDO.
# Ela casava "parcial" e descontava quando vinha depois de palavra de desenho
# ("planta parcial"). Rodei nos 6 brancos reais que contêm a palavra: acertou 4,
# errou 1 — o job `66ebe2d9` diz "(comprimentos PARCIAIS em cm)" falando das
# BARRAS INDIVIDUAIS de uma tabela de aço, não do total entregue. Rebaixar o
# selo de um item legítimo é o custo que [[feedback_alarme_sem_controle_20260826]]
# descreve: o alarme perde crédito e alguém o desliga.
#
# 🔑 Invertido para lista POSITIVA: exige frase que afirme que o VALOR ENTREGUE
# é um pedaço. Falha pra menos (deixa passar redação nova) e nunca pra mais —
# que é o lado certo de errar quando se mexe no selo do cliente.
_FRASES_DE_VALOR_PARCIAL = (
    _re.compile(r"valor\s+(?:\w+\s+){0,2}parcia(?:l|is)", _re.IGNORECASE),
    _re.compile(r"trecho\s+parcia(?:l|is)", _re.IGNORECASE),
    _re.compile(r"quantidade\s+(?:\w+\s+){0,2}parcia(?:l|is)", _re.IGNORECASE),
    _re.compile(r"medi[çc][ãa]o\s+parcia(?:l|is)", _re.IGNORECASE),
    # "1 ocorrência listada: 9,71 m². Parcial — existem +229 pares NÃO LISTADOS"
    _re.compile(r"n[ãa]o\s+list", _re.IGNORECASE),
    _re.compile(r"sem\s+list(?:ar|agem)", _re.IGNORECASE),
)


def numero_declarado_parcial(observacao):
    """A observação admite que a quantidade entregue cobre só PARTE do item?

    Duas famílias, ambas escritas pelo próprio motor:
      · "Valor provavelmente parcial", "trecho parcial" → mediu um pedaço;
      · "+229 pares não listados"                       → somou o que coube.

    🚫 NÃO casa "planta parcial" nem "comprimentos parciais em cm": a primeira
    fala do desenho, a segunda das peças de uma tabela. Nenhuma das duas é
    confissão sobre o número entregue.
    """
    obs = str(observacao or "")
    if not obs:
        return False
    return any(rx.search(obs) for rx in _FRASES_DE_VALOR_PARCIAL)


# ── O AVISO DE LEITURA CORTADA (uma frase só) ──────────────────────────────

def aviso_de_leitura_cortada(nome_prancha, n_itens_lidos=None):
    """A frase ÚNICA pra "a resposta da IA foi cortada no teto".

    🩸 09/09/2026 — POR QUE ISTO VIROU FUNÇÃO. A mesma decisão tinha DUAS
    cópias vivas e só uma foi consertada:

        DXF/DWG (consertada em 24/08) → "Reprocessar normalmente NÃO resolve…"
        PDF     (esquecida)           → "Reprocessar pode completar."

    🚨 O conselho velho CUSTA DINHEIRO ao cliente: ele gasta o reprocesso à toa,
    porque o corte vem da DENSIDADE da prancha, não de uma falha passageira —
    reprocessar corta no mesmo lugar. Foi por isso que a frase foi aposentada em
    24/08; ela só não foi aposentada nos dois lugares.

    🪤 E as DUAS redes de segurança erraram pelo MESMO motivo: procuravam a
    variante LONGA ("Reprocessar pode completar **a planilha**.") enquanto o
    caminho do PDF produzia a CURTA. O saneador do merge não casava, e o guarda
    ancorava no texto do DXF — verde desde sempre com o defeito aberto.

    🔑 Agora os dois caminhos CHAMAM daqui. Divergir exige apagar a chamada, e
    há guarda pra isso.
    """
    nome = str(nome_prancha or "esta prancha").strip() or "esta prancha"
    if n_itens_lidos:
        _quanto = (" (li %d itens; os que vieram estão certos, mas faltam "
                   "itens do final)" % int(n_itens_lidos))
    else:
        _quanto = " (os itens que vieram estão certos, mas pode faltar item do final)"
    return (
        "A leitura da prancha '%s' ficou INCOMPLETA: ela tem itens demais para "
        "uma leitura só, e a IA foi cortada no meio da lista%s. Reprocessar "
        "normalmente NÃO resolve — o corte vem da densidade da prancha, não de "
        "uma falha passageira. Para ter a prancha inteira, exporte-a em partes "
        "(por exemplo um pavimento ou uma disciplina por arquivo) e reenvie, ou "
        "fale com a gente que a gente divide aqui." % (nome, _quanto))


# ── A MESCLAGEM DO `project_data` QUE A IA DEVOLVE (uma só) ────────────────

def departamentos_no_formato_do_modelo(bruto):
    """A lista de departamentos no formato que `ProjectData` declara.

    🩸 19/09/2026 — a planilha de um cliente MORREU por causa disto. O motor
    tinha acabado de ler 2 pranchas, 139 itens, 16 medidos, 25 minutos de
    máquina; ao escrever a CAPA, `dept.get('name')` estourou
    `AttributeError: 'str' object has no attribute 'get'`, o job virou `error`
    e o cliente recebeu um e-mail pedindo pra TROCAR O ARQUIVO — por um defeito
    que era nosso. Nada disso tinha a ver com o desenho dele.

    A causa: `models.py` declara `departments: list[dict]`, o prompt pede
    objetos com `name`/`positions`, e a mesclagem copiava o que a IA mandasse.
    Naquele job a IA devolveu uma lista de STRINGS. O tipo declarado não é
    contrato enquanto ninguém o aplica na porta de entrada.

    🔑 Aqui é a porta: o que entra sai no formato do modelo, e o resto do
    sistema pode confiar. Cada item vira `{"name": ..., "positions": int}`;
    string vira o nome; o que não dá pra entender é descartado em vez de
    virar uma linha `None` na capa.
    """
    if isinstance(bruto, (str, bytes)) or not isinstance(bruto, (list, tuple)):
        bruto = [bruto]
    saida = []
    for item in bruto:
        if isinstance(item, dict):
            nome = str(item.get("name") or item.get("nome") or "").strip()
            # Sinônimos porque a IA já devolveu cada um deles: o prompt pede
            # `positions`, e normalizar sem aceitá-los jogaria fora o número
            # que ela mandou — o oposto do que esta função existe pra fazer.
            _p = next((item[k] for k in ("positions", "posicoes", "n", "qtd",
                                         "quantidade") if item.get(k) is not None), 0)
            try:
                postos = int(float(_p))
            except (TypeError, ValueError):
                postos = 0
        else:
            nome, postos = str(item or "").strip(), 0
        if nome:
            saida.append({"name": nome, "positions": postos})
    return saida


def mesclar_project_data(destino, pd, area_readings=None, reg_area=None,
                         origem="ia", sf=None):
    """Junta o `project_data` que a IA devolveu de UMA prancha no acumulado.

    🩸 09/09/2026 — POR QUE ISTO VIROU FUNÇÃO. A mesma mesclagem existia em
    DOIS laços vivos do `main.py` (DXF/DWG e PDF) e eles DIVERGIRAM:

        campo                        DXF      PDF
        áreas, name, new_rooms...    colhe    colhe
        workstations, departments    DESCARTA colhe
        warnings                     DESCARTA DESCARTA

    🚨 O `warnings` é o que doía. A IA DETECTA que falta a planta baixa pro
    quadro de especificações e escreve o aviso pedindo o arquivo que falta —
    e os dois laços jogavam fora. Quem colhia era a `analyze_all_sheets`, que
    era MORTA e foi apagada. O cliente recebia itens com "status não
    identificável" e NENHUMA linha dizendo o que enviar pra resolver.
    🪤 E o aparato inteiro existia dos dois lados: o prompt PEDE o aviso, o
    `models.py` tem o campo, o `spreadsheet.py` tem o bloco "⚠ AVISOS DO MOTOR"
    na capa, e o painel acende "precisa de complemento". Só o meio faltava.

    🪤 `workstations`/`departments`: o prompt do DXF PEDE os dois
    (main.py ~10180), o laço descartava, e a capa da planilha tem campo pra
    eles. O MESMO projeto saía com em PDF e sem em DWG.

    🔑 Uma função, os dois chamam. Divergir agora exige apagar a chamada, e há
    guarda pra isso.
    """
    if not isinstance(pd, dict):
        return destino
    _sf = sf or (lambda v: float(v or 0))

    if area_readings is not None:
        for campo in ("total_area", "layout_area", "no_intervention_area"):
            v = pd.get(campo)
            if not v:
                continue
            try:
                vf = _sf(v)
            except Exception:
                continue
            if vf and vf > 0:
                area_readings.setdefault(campo, []).append(vf)
                if reg_area:
                    try:
                        reg_area(origem, campo)
                    except Exception:
                        pass

    # texto que só vale se ainda não temos (o primeiro que vier manda)
    for campo in ("name", "address", "architect"):
        if pd.get(campo) and not getattr(destino, campo, ""):
            setattr(destino, campo, pd[campo])

    # listas: acumulam de todas as pranchas
    for campo in ("demolition_notes", "new_rooms", "kept_elements", "warnings"):
        v = pd.get(campo)
        if not v:
            continue
        atual = list(getattr(destino, campo, None) or [])
        try:
            atual.extend(v if isinstance(v, (list, tuple)) else [v])
        except TypeError:
            continue
        setattr(destino, campo, atual)

    if pd.get("workstations"):
        try:
            destino.workstations = int(float(
                str(pd["workstations"]).replace("un", "").strip()))
        except (TypeError, ValueError):
            pass
    if pd.get("departments"):
        destino.departments = departamentos_no_formato_do_modelo(pd["departments"])
    return destino


# ══════════════════════════════════════════════════════════════════════════
#  O QUE MEDIMOS NO PDF — dito ao cliente, sem atribuir a item nenhum
# ══════════════════════════════════════════════════════════════════════════
# 🩸 17/09/2026. Medido na janela 19/07–16/09: **34 de 34** projetos só-PDF
# saíram sem UMA linha marcada como medida (31 clientes). O cliente conclui
# "esse produto não mede o meu arquivo" — e em 19 desses 34 a gente MEDIU a
# geometria e provou a escala contra as cotas do próprio desenho.
#
# 🚫 A tentativa óbvia — marcar a linha como medida — foi REPROVADA em revisão
# adversarial no mesmo dia, e pelo mesmo furo que aposentou o promotor
# automático em 15/07: a prova disponível é "o número desta linha é igual ao
# total desta prancha", e como só existe UM total de área por prancha, QUALQUER
# linha que cite esse número casa. Demolição pegaria a área do piso novo.
#
# 🔑 A saída é dizer a verdade no nível em que ela é defensável: a PRANCHA.
# "Medimos 22 ambientes, 90,9 m²" é um fato sobre o desenho e não afirma nada
# sobre linha nenhuma da planilha. Impossível virar falso-medido, porque não
# rotula item.
#
# 🪤 O comprimento de parede fica FORA de propósito. Medido em 45 dias, o
# `walls_m` chega a 84× o perímetro mínimo da área (3.213 m num imóvel de
# 90 m²): é a soma de todo traço classificado como parede, as duas faces e
# provavelmente hachura. Mostrar isso ao cliente seria impressionar com um
# número que a gente sabe que está errado.

#: De onde veio a escala NÃO conferida por cota, pela `scale_src` da medição.
#: 🪤 As MESMAS palavras da 1ª coluna de `main._FONTE_DA_ESCALA` — aquela vai pro
#: prompt e pra observação da linha, esta pro e-mail. O guarda
#: `test_a_procedencia_do_email_e_a_mesma_do_motor` reprova se as duas divergirem
#: — fonte nova no motor sem frase aqui também reprova.
FONTE_DA_ESCALA_SEM_PROVA = {
    "carimbo": "do carimbo da prancha",
    "viewport": "da caixa de recorte do PDF",
    "cotas": "das cotas escritas na prancha (por votação)",
    "vista": "do rótulo escrito ao lado do próprio desenho",
}


def o_que_medimos_na_prancha(por_prancha, project_type: str = "") -> str:
    """Frase honesta sobre a medição do PDF, pro cliente. "" quando não há o que dizer.

    Entra só o que se defende: quantos ambientes e quantos m². A escala é dita
    com a PROCEDÊNCIA dela — conferida contra cota, ou lida de onde veio (a
    `scale_src`) sem conferência — porque as duas coisas valem coisas diferentes.

    🩸 22/09/2026 — jobs ee801b82 e f8d8e6d8 (os mesmos 7 PDFs de estrutura).
    Os dois e-mails abriram com "DE-X: 32 ambiente(s), 892,0 m², na escala 1:125
    lida do carimbo da prancha". Duas mentiras numa linha:
      · "ambiente" numa prancha ESTRUTURAL é qualquer face fechada que o leitor
        vetorial achou (tampa, abertura, contorno de laje) — o número não
        descreve nada que a cliente reconheça, e a planilha dela não usava;
      · a escala tinha vindo do RÓTULO da vista (`scale_src="vista"`), e esta
        frase dizia "carimbo" pra toda escala não conferida, sem olhar a fonte.
    🔑 Em projeto de estrutura o bloco não lista ambientes/m²; em qualquer
    projeto a procedência sai da `scale_src`. Fonte desconhecida é dita como
    desconhecida — nunca emprestada do carimbo.
    """
    if str(project_type or "").strip().lower() == "estrutura":
        return ""
    linhas = []
    for _k, r in sorted((por_prancha or {}).items(),
                        key=lambda kv: -(float((kv[1] or {}).get("rooms_m2") or 0))):
        try:
            m2 = float(r.get("rooms_m2") or 0)
            n = int(r.get("n_rooms") or 0)
        except (TypeError, ValueError):
            continue
        if m2 <= 0 or n <= 0:
            continue
        nome = str(r.get("arquivo") or "").strip() or "prancha"
        esc = r.get("scale")
        cotas = int(r.get("cotas_batem") or 0)
        if r.get("escala_validada") and cotas > 0 and esc:
            # 🪤 "bate com N cotas" é uma AFIRMAÇÃO DE CONCORDÂNCIA, não uma
            # garantia: a validação exige 2 pares e não confere o eixo. Dizer o
            # que foi conferido deixa o cliente julgar; dizer "escala provada"
            # prometeria mais do que a régua entrega.
            comoescala = (f"na escala 1:{esc}, que bate com {cotas} cota(s) "
                          f"escritas no próprio desenho")
        elif esc:
            _src = str(r.get("scale_src") or "").strip().lower()
            _fonte = FONTE_DA_ESCALA_SEM_PROVA.get(_src)
            if _src == "cotas":
                # "sem conferência contra cota" negaria a própria fonte: a
                # votação ACHOU a escala nas cotas; o que faltou foi o par
                # cota×elemento na vista principal.
                comoescala = (f"na escala 1:{esc} lida {_fonte}, sem par "
                              f"cota×elemento que a confirmasse")
            elif _fonte:
                comoescala = (f"na escala 1:{esc} lida {_fonte} "
                              f"(sem conferência contra cota)")
            else:
                comoescala = (f"na escala 1:{esc}, de origem não identificada "
                              f"(sem conferência contra cota)")
        else:
            comoescala = "sem escala confirmada"
        linhas.append(f"{nome}: {n} ambiente(s), {m2:.1f} m², {comoescala}.")
    if not linhas:
        return ""
    return "\n".join(linhas)


def porque_nada_saiu_medido_no_pdf() -> str:
    """A segunda metade da verdade: por que a medição acima não vira selo.

    🔑 Sem esta frase a primeira engana ao contrário — o cliente leria "mediram
    90 m²" e perguntaria por que a planilha está toda laranja.
    """
    return ("Nenhuma linha da planilha saiu marcada como MEDIDA. O motivo é "
            "honesto: a gente mede a geometria da prancha inteira, mas não "
            "consegue afirmar com segurança qual linha da planilha corresponde "
            "a qual pedaço dessa medição — e marcar por semelhança de número já "
            "nos fez atribuir a área do piso novo a uma linha de demolição. "
            "Enquanto não der pra provar a correspondência, a quantidade fica "
            "como estimativa pra você conferir. Com o desenho em DWG ou DXF a "
            "medição sai por item, com selo.")


def area_informada_mudaria_a_planilha(items, pdfvec_m2: float = 0.0) -> bool:
    """Se o cliente informar a área total no envio, ela vira número em alguma linha?

    🩸 22/09/2026 — job ee801b82. O e-mail disse "Se só existe o PDF, me diga a
    área total no upload" a quem tinha 1.116,3 m² de medição vetorial no job —
    e com medição a área digitada não entra em linha NENHUMA. Conselho que a
    própria régua recusa (a doença de 08/09, de novo, agora no e-mail).
    🔑 As mesmas duas travas de `_area_informada_alcancaria` (dentro de
    `_apply_area_honesty`): só piso/forro/laje em m², e só sem medição vetorial.
    Aquela fica local de propósito (fatia executada por testes); esta é a que o
    e-mail consulta. O aviso de projeto aplica as duas em lugares diferentes:
    a de superfície no próprio `_alcanca` (o guarda de 09/09 lê aquela
    expressão pela AST) e a da medição no `if _alcanca and _pv_alc <= 0`.
    🪤 São três cópias da mesma pergunta: o guarda
    `test_as_tres_reguas_da_area_informada_concordam` roda as três nos mesmos
    itens e reprova se uma responder diferente.
    """
    try:
        if float(pdfvec_m2 or 0) > 0:
            return False
    except (TypeError, ValueError):
        return False
    return any(
        (_campo_do_item(it, "unit", "") or "") in FLOOR_M2_UNITS
        and is_floor_surface_para_criar(_campo_do_item(it, "description", "") or "")
        for it in (items or []))


# O quadro de aço que o projetista pôs na prancha, como a IA o cita na
# observação. Mais largo que `_QUADRO_DE_ACO` (que absolve SELO e é estreito de
# propósito): aqui só se pergunta "a prancha trouxe o resumo?", pra texto.
_RX_RESUMO_DE_ACO = _re.compile(
    r"resumos?\s+(?:de\s+)?(?:a[çc]o|tela)"
    r"|quadros?\s*(?:/\s*resumos?\s*)?\s+de\s+(?:a[çc]o|ferr(?:o|os|agem|agens))"
    r"|listas?\s+de\s+ferros?",
    _re.IGNORECASE)
# "Não há quadro/resumo de aço nesta prancha" — a IA escreve isso em linha de
# aço por TAXA. Negação no mesmo trecho da frase, colada antes da citação
# (ancorada no fim: um "sem" solto lá atrás na frase não nega o quadro).
_RX_NEGA_O_RESUMO = _re.compile(
    r"(?:n[ãa]o\s+(?:h[áa]|tem|existe|consta|aparece|foi|veio|apresenta|traz"
    r"|possui|cont[ée]m|inclui|mostra)\b[^.;|]{0,24}"
    r"|\bsem\s+(?:o\s+|a\s+|um\s+|uma\s+)?"
    r"|\baus[êe]ncia\s+d[eoa]s?\s+|\bfalta(?:m)?\s+(?:o\s+|a\s+)?)$",
    _re.IGNORECASE)
# "Quadro de aço não encontrado nesta prancha" — a negação vem DEPOIS.
_RX_NEGA_DEPOIS = _re.compile(
    r"^[^.;|]{0,30}?(?:\bn[ãa]o\s+(?:foi\s+|est[áa]\s+|é\s+|era\s+)?"
    r"(?:encontrad|localizad|dispon[íi]ve|vis[íi]ve|leg[íi]ve|enviad|identificad"
    r"|inclu[íi]d|apresentad|lid|consta|h[áa])|\bausente|\binexistente)",
    _re.IGNORECASE)
# 🩸 22/09/2026 (revisão) — quem AFIRMA que o número saiu do quadro, no mesmo
# trecho da frase: "lido do", "copiado do", "extraído do", "fonte:",
# "confirmado no", "declarado no", "total explícito no", "a partir do",
# "conforme", "soma das". Citar o quadro não basta: "Verificar projeto
# estrutural e quadro de ferragens" é recomendação, não procedência.
_RX_RESUMO_AFIRMADO_ANTES = _re.compile(
    r"(?:\bfonte\b[^:.;|]{0,25}:"
    r"|\b(?:lid|copiad|extra[íi]d|transcrit|confirmad|declarad|expl[íi]cit|tirad"
    r"|obtid|retirad|derivad|basead)[oa]s?\b"
    r"|\ba\s+partir\s+d[oa]s?\b|\bconforme\b|\bde\s+acordo\s+com\b"
    r"|\bcom\s+base\s+n[oa]s?\b|\bsegundo\b|\bsoma\w*\s+d[oa]s?\b)"
    r"[^.;|]{0,60}$",
    _re.IGNORECASE)
_RX_RESUMO_AFIRMADO_DEPOIS = _re.compile(
    r"^[^.;|]{0,25}?\b(?:lid|copiad|extra[íi]d|transcrit)[oa]s?\b|^[^.;|]{0,25}?\btotaliza",
    _re.IGNORECASE)
# Peso que SAIU de uma taxa (regra nº3): nesse trecho o quadro citado não é a
# fonte do número, mesmo com "conforme" ao lado.
_RX_PESO_DA_TAXA_NO_TRECHO = _re.compile(
    r"\btaxa\b[^.;|]{0,60}?\b(?:adotad|aplicad|t[íi]pic)"
    r"|\bconsumo\s+t[íi]pic|\bpor\s+taxa\b"
    r"|\bestimad[oa]s?\s+(?:\w+\s+){0,2}?(?:por|pela)\s+taxa",
    _re.IGNORECASE)


def _citacao_do_resumo_afirma_a_fonte(obs: str, m) -> bool:
    """A citação `m` do quadro diz que o número VEIO dele (e não o nega)?"""
    _ini = max(0, m.start() - 90)
    antes = _re.split(r"[.;|]", obs[_ini:m.start()])[-1]
    depois = _re.split(r"[.;|]", obs[m.end():m.end() + 90])[0]
    if _RX_NEGA_O_RESUMO.search(antes) or _RX_NEGA_DEPOIS.search(depois):
        return False
    if _RX_PESO_DA_TAXA_NO_TRECHO.search(antes + m.group(0) + depois):
        return False
    return bool(_RX_RESUMO_AFIRMADO_ANTES.search(antes)
                or _RX_RESUMO_AFIRMADO_DEPOIS.search(depois))


def linhas_de_aco_do_resumo(items) -> int:
    """Quantas linhas de aço (kg, com número) a IA tirou do resumo de aço da prancha.

    🩸 22/09/2026 — job ee801b82 (estrutura, 7 PDFs). O aviso de topo disse
    "O peso de aço depende do quadro de ferros, que é outra prancha (ARM)" — e
    três das pranchas ENVIADAS traziam o RESUMO DE AÇO, lido em 7 linhas
    (582, 784,45, 1,27, 306, 432,2, 54,6 e 199 kg). A frase afirmava sobre o
    arquivo dela sem olhar o que a leitura achou.

    🪤 Conta só `quantity > 0`: a linha "o peso das sapatas está no RESUMO DE
    AÇO" com 0 kg cita o quadro e não tirou número dele. E a citação negada
    ("Não há quadro/resumo de aço") não conta — é a frase das linhas por taxa.

    🩸 22/09/2026 (revisão adversária) — a 1ª versão contava QUALQUER citação
    não negada. No job 08ba5752 (PDF lido como estrutura, zero quadro de aço)
    as 7 linhas diziam "Não há quadro de aço nestas pranchas. Taxa 100 kg/m³
    adotada [...]. Verificar projeto estrutural e quadro de ferragens": a 1ª
    citação era negada, a 2ª não — e 6 linhas de TAXA viravam "aço lido do
    resumo", trocando a frase verdadeira do ARM por uma falsa.
    🔑 Agora a citação só conta se o mesmo trecho da frase AFIRMA a
    procedência ("lido do", "fonte:", "extraído do", "confirmado no"...), não
    a nega antes nem depois, e não é trecho de peso por taxa.
    📏 Medido (90 d, sem avaliação, now() de testemunha 22/09 15:37): 148
    linhas kg > 0 citam quadro/resumo/lista, em 15 jobs. A régua antiga
    contava 130; esta conta 119. Saem 12 linhas: as 6 do 08ba5752 e as 2 do
    62c49fe6 (taxa, "não há quadro [...] verificar/revisar com quadro de
    ferragens"), a do 7f7ef56a ("conferir com quadro de ferragens quando
    disponível"), a estimativa por comprimento × massa do f8d8e6d8, e 3
    linhas de soma/diagnóstico em jobs que seguem com dezenas lidas do
    quadro. Entram 3: o PLURAL "Soma confirmada dos quadros de ferragens"
    do 7f7ef56a, que a régua antiga (só singular) não via.
    🪤 Por JOB, zeram só os dois que não tinham quadro nenhum (08ba5752 6→0,
    62c49fe6 2→0). 7f7ef56a vai de 1 pra 3 — a régua antiga contava ali a
    linha ERRADA (a recomendação) e perdia as três certas. Os outros 12
    seguem contando (42c354a1 63→60, 6e9649a7 11→10, f8d8e6d8 5→4,
    ee801b82 5→5).
    🩸 A 1ª medição desta revisão disse "130→116, e os TRÊS zeram": ela
    peneirou o acervo com a regex ANTIGA (sem plural), então mediu o alcance
    da régua nova pelo corte da velha e perdeu 3 linhas do 7f7ef56a.
    """
    n = 0
    for it in (items or []):
        try:
            if str(_campo_do_item(it, "unit", "") or "").strip().lower() != "kg":
                continue
            if float(_campo_do_item(it, "quantity", 0) or 0) <= 0:
                continue
            obs = str(_campo_do_item(it, "observations", "") or "")
            if any(_citacao_do_resumo_afirma_a_fonte(obs, m)
                   for m in _RX_RESUMO_DE_ACO.finditer(obs)):
                n += 1
        except (TypeError, ValueError):
            continue
    return n


# ─────────────────────────────────────────────────────────────────────────────
# 🩸 18/09/2026 — O E-MAIL SE CONTRADIZIA EM DUAS LINHAS
#
# O e-mail de "planilha pronta" imprime o placar exato logo acima:
#     "✓ 7 medido(s) direto do CAD e ⚠ 30 pra você confirmar"
# e a frase seguinte dizia, para QUALQUER job de CAD com `medidos > 0`:
#     "medimos boa parte direto da geometria do desenho"
#
# A condição olhava só se havia ALGUM medido; o texto afirmava PROPORÇÃO.
# Medido no acervo em 18/09 (jobs de cliente concluídos com DWG/DXF que
# recebem a frase): 72 entregas, e em **63 delas menos da metade das linhas
# está medida** — 32 com menos de um quarto. A frase só é verdadeira em 9.
#
# 🔑 Regra dura nº1 é sobre não vender estimativa como medição. Dizer "boa
# parte" com 6,7% medido é a mesma mentira, em prosa, no canal que o cliente
# mais lê — e ainda por cima desmentida pelo número duas linhas acima.
#
# A régua mora aqui, fora do `main.py`, porque guarda tem que EXECUTAR a
# decisão, não ler o fonte dela.
# ─────────────────────────────────────────────────────────────────────────────

#: "Maior parte" quer dizer MAIS DA METADE — o corte não é gosto meu, é o
#: significado da palavra. Em metade exata a frase não ganha adjetivo: sai só
#: o número, que é verdadeiro em qualquer proporção.
_PISO_MAIOR_PARTE = 0.5


def frase_do_quanto_mediu(medidos, total):
    """Como dizer ao cliente o quanto foi medido, sem afirmar proporção falsa.

    Devolve o trecho de frase (texto puro, sem HTML) que descreve a medição.
    Sempre carrega os DOIS números — é o que torna a frase conferível contra o
    placar do próprio e-mail.

    🪤 Nunca chama de "maior parte" o que não PASSA de metade. Em metade exata,
    e abaixo dela, a frase não ganha adjetivo nenhum: diz o número e para.
    🪤 `total` zero ou inválido devolve texto vazio — quem chama decide o que
    fazer, e ninguém afirma nada sobre uma planilha que não existe.
    🪤 NÃO existe ramo para "mediu tudo". Cheguei a escrever um ("medimos todas
    as N") e fui medir antes de defendê-lo: em 101 jobs de CAD de cliente,
    **zero** saíram 100% medidos, e o máximo já visto foi 86,3%. Ramo que a
    produção nunca alcança é código morto com guarda decorativo em cima — o
    erro que a revisão de 18/09 já tinha me mostrado uma vez no mesmo dia.
    ⏭️ Se um dia isso acontecer, o placar do e-mail vai dizer "⚠ 0 pra você
    confirmar (em laranja)", que é a mesma contradição pelo avesso.
    """
    try:
        _m, _t = int(medidos), int(total)
    except (TypeError, ValueError):
        return ""
    if _t <= 0 or _m < 0:
        return ""
    _m = min(_m, _t)
    if _m == 0:
        return ""
    if (_m / float(_t)) > _PISO_MAIOR_PARTE:
        return (f"medimos a maior parte direto da geometria do desenho "
                f"({_m} de {_t} linhas, as em branco)")
    return (f"medimos {_m} de {_t} linhas direto da geometria do desenho "
            f"(as em branco)")


# ─────────────────────────────────────────────────────────────────────────────
#  O nome da prancha como o CLIENTE a enviou
# ─────────────────────────────────────────────────────────────────────────────
_SUFIXO_DO_CONVERSOR = _re.compile(r"_libredwg\.dxf(?=$|\s*\()", _re.IGNORECASE)


def nome_que_o_cliente_enviou(ref_sheet) -> str:
    """"planta_libredwg.dxf" → "planta.dwg": o nome que o cliente reconhece.

    🩸 18/09/2026. Quando o ODA recusa um .dwg, o plano B (libredwg) gera
    "<nome>_libredwg.dxf" e o motor gravava ESSE nome em `ref_sheet`. Medido
    no banco: **2.818 linhas de 43 contas** (26,7% das linhas de cliente) com
    um nome de arquivo que ninguém enviou — e o cliente que se cadastrou hoje
    tinha 77 de 77 assim. Pior: o aviso "você já mandou esse caderno" compara
    o nome ENVIADO com o gravado, e por isso era cego pra todos eles.

    🔑 A volta é DETERMINÍSTICA: só o nosso conversor cola "_libredwg", e só
    em DXF gerado a partir de um DWG. Então "X_libredwg.dxf" veio de "X.dwg",
    sempre. Conferido antes de escrever: das 5.010 linhas com o sufixo, 5.010
    o têm exatamente no fim do nome, 0 antes do "(hint da IA)", 0 com
    "_libredwg_min". Por isso a regex ancora no fim ou no " (".

    🔑 POR QUE LIMPAR NA SAÍDA e não no que se grava: `ref_sheet` é também a
    CHAVE que a tela manda de volta em `/api/sheet?ref=` e que o checkpoint
    usa; a busca já compara radicais (`_stem_da_prancha`), mas as 2.818 linhas
    gravadas só se consertam se a limpeza acontecer na exibição. Uma regra,
    aplicada onde o nome CHEGA ao cliente (planilha, tela, chat) e onde ele é
    COMPARADO (caderno repetido). Nada muda no banco.

    🚫 O que esta regra NÃO sabe: um .dwg que o ODA converteu SEM sufixo sai
    como "X.dxf", indistinguível de um DXF enviado pelo cliente — medido em
    18/09: 9 linhas, 1 job, 1 conta. Fica documentado, não consertado.

    🪤 A extensão volta em minúsculas ("planta.dwg") mesmo se o cliente mandou
    "PLANTA.DWG": o conversor preserva o radical, não a caixa da extensão.
    """
    s = str(ref_sheet or "")
    if not s:
        return ""
    return _SUFIXO_DO_CONVERSOR.sub(".dwg", s)


# ─────────────────────────────────────────────────────────────────────────────
#  O QUADRO DE QUANTITATIVOS IMPRESSO NA PRANCHA (22/09/2026)
# ─────────────────────────────────────────────────────────────────────────────
# 🩸 22/09/2026 — jobs ee801b82 e f8d8e6d8 (os mesmos 7 PDFs de estrutura,
# dois dias seguidos). A 1ª prancha traz um QUADRO DE QUANTITATIVOS impresso
# pelo projetista: concreto 4,90/3,80/13,20/3,90/1,00 m³ e fôrma
# 37,20/31,20/82,70/28,10/4,00 m². Duas leituras independentes da IA deram os
# mesmos dez números — e a honestidade de área zerou os dez nos dois dias,
# porque trata todo m²/m³ de PDF como chute. A planilha saiu com 0 m³ de
# concreto num projeto que DECLARA 26,8 m³.
# 🔑 O número do quadro não é medição nossa, e nunca vira branco/medido. Mas
# também não é chute: é a conta do projetista, copiada. Só que "a observação
# diz que copiou do quadro" é a PALAVRA da IA — ela escreve isso até em número
# que inventou. Por isso a preservação exige uma prova que não saia da mesma
# boca: o número escrito no TEXTO do PDF daquela prancha, ou a soma das linhas
# do quadro batendo com uma linha de TOTAL que a leitura diz ter LIDO (não
# somado).
#: Verbo de TRANSCRIÇÃO + "quadro/tabela de quantitativos" (ou "de
#: quantidades", "de volumes"). "Quadro de áreas" fica de fora de propósito: é
#: outra doença (a área do imóvel colada num item), com régua própria.
#: 📏 Medido em 22/09 (90 dias, sem avaliação, m²/m³/m fora do CAD): 30 linhas
#: em 5 jobs casam, 28 delas zeradas; fora deste caso, 8 zeradas em 2 jobs, e as
#: respostas da IA nesses jobs mostram quadros de verdade (memória de cálculo,
#: tabela de termo de referência, quadro de paginação de piso).
_RE_TRANSCRICAO_DE_QUADRO = _re.compile(
    r"\b(?:lid[oa]s?|extra[ií]d[oa]s?|transcrit[oa]s?|copiad[oa]s?|retirad[oa]s?"
    r"|obtid[oa]s?|conforme)\b[^.|;]{0,40}?"
    r"\b(?:quadros?|tabelas?)\s+(?:de\s+)?(?:resumo\s+de\s+)?"
    r"(?:quantitativ\w*|quantidades\b|volumes\b)",
    _re.IGNORECASE)
#: "não foi lido do quadro de quantitativos" é o CONTRÁRIO da afirmação.
_RE_NEGA_A_TRANSCRICAO = _re.compile(r"\bn[ãa]o\b[^.|;]{0,20}$", _re.IGNORECASE)
_RE_LINHA_DE_TOTAL = _re.compile(r"\b(?:sub)?tota(?:l|is)\b", _re.IGNORECASE)
_RE_TOKEN_NUMERICO = _re.compile(r"\d+(?:[.,]\d+)+")


def afirma_quadro_de_quantitativos(texto) -> bool:
    """A observação AFIRMA que o número foi copiado de um quadro de quantitativos?

    É a condição (a) — necessária, nunca suficiente: sozinha ela não preserva
    número nenhum (ver `veredito_do_quadro_impresso`)."""
    t = str(texto or "")
    for m in _RE_TRANSCRICAO_DE_QUADRO.finditer(t):
        if _RE_NEGA_A_TRANSCRICAO.search(t[max(0, m.start() - 25):m.start()]):
            continue
        return True
    return False


def e_linha_de_total(descricao) -> bool:
    """A linha se apresenta como TOTAL ("TOTAL GERAL", "— total", "subtotal")?"""
    return bool(_RE_LINHA_DE_TOTAL.search(str(descricao or "")))


def _decimal_do_token(tok):
    """'1.234,56' → 1234.56 · '4,90' → 4.9 · '37.20' → 37.2 · o resto → None.

    🪤 Só número COM parte decimal escrita. Inteiro ("4", "215") aparece aos
    montes numa prancha (cota, número de barra, nível) e casaria por acaso; e
    "1.234" com três casas é ambíguo (milhar pt-BR ou decimal) — fica de fora.
    """
    if "," in tok:
        if tok.count(",") != 1:
            return None
        inteiro, dec = tok.split(",")
        if "." in inteiro and not _re.fullmatch(r"\d{1,3}(?:\.\d{3})+", inteiro):
            return None
        try:
            return float(inteiro.replace(".", "") + "." + dec)
        except ValueError:
            return None
    if tok.count(".") == 1 and len(tok.split(".")[1]) != 3:
        try:
            return float(tok)
        except ValueError:
            return None
    return None


def numeros_decimais_do_texto(texto) -> frozenset:
    """Os números decimais escritos no texto de uma prancha, em CENTÉSIMOS.

    Centésimo inteiro, e não float, pra "4,90" e 4.9 serem a mesma coisa sem
    comparação de ponto flutuante. É o que viaja do laço de páginas (onde o
    texto existe) até a honestidade de área (onde o texto já foi apagado)."""
    out = set()
    for tok in _RE_TOKEN_NUMERICO.findall(str(texto or "")):
        v = _decimal_do_token(tok)
        if v is not None and v > 0:
            out.add(int(round(v * 100)))
    return frozenset(out)


def _familia_da_unidade(u):
    u = (u or "").strip().lower()
    if u in ("m³", "m3"):
        return "m3"
    if u in FLOOR_M2_UNITS:
        return "m2"
    if u in ("m", "ml", "mts"):
        return "m"
    return u


def veredito_do_quadro_impresso(linhas, numeros_por_prancha=None):
    """Decide, linha a linha, o que fazer com número de quadro de quantitativos.

    `linhas`: lista de dicts com `arquivo` (nome minúsculo, chave da prancha),
    `pagina` (int ou None), `prancha` (nome pra frase), `unidade`,
    `quantidade`, `texto` (observação) e `descricao`.
    `numeros_por_prancha`: {(arquivo, pagina): frozenset de centésimos} — o que
    `numeros_decimais_do_texto` achou no texto do PDF de cada prancha.

    Devolve uma lista do mesmo tamanho, com `None` (linha fora da régua) ou
    `(tipo, info)`:
      · "texto"     — (a) + o número está no texto do PDF da prancha: preserva;
      · "total"     — (a) + as linhas do quadro somam um TOTAL LIDO (±1%): preserva;
      · "sem_prova" — (a) sem prova: continua zerada, e a frase diz o número;
      · "e_o_total" — a linha É o total das outras: zerada, pra não contar em dobro.
        `info` traz `soma`, `parcelas`, `bate`, `parcelas_com_numero` (quantas
        das linhas que ele resume ficaram com número) e, quando só o NÚMERO
        diz que é total (a descrição não diz), `pela_soma`.

    🪤 Duas travas contra o acaso, porque prancha tem número pra todo lado:
      1. prova por texto só vale se o quadro APARECE no texto — pelo menos dois
         números distintos das linhas (a) daquela prancha estão lá. Um "1,00"
         solto casa em qualquer desenho;
      2. o TOTAL só prova as parcelas quando a própria linha do total diz que
         foi LIDO do quadro e não é uma soma. No ee801b82 o "TOTAL GERAL" era a
         conta da própria IA ("Soma dos valores do quadro: 4,90 + 3,80 + …") —
         conta de chegada, prova nenhuma.
    """
    # a chave do item sai do `ref_sheet` em minúsculas; a do mapa também tem que sair
    nums = {(str(a or "").strip().lower(), p): v
            for (a, p), v in dict(numeros_por_prancha or {}).items()}
    n = len(linhas)
    out = [None] * n

    def _q(l):
        try:
            return float(l.get("quantidade") or 0)
        except (TypeError, ValueError):
            return 0.0

    def _nums_da(l):
        arq = l.get("arquivo") or ""
        if not arq:
            return None
        pg = l.get("pagina")
        if pg is not None:
            return nums.get((arq, int(pg)))
        # sem página no `ref_sheet`: só vale se o arquivo tem UMA página lida
        cands = [v for (a, _p), v in nums.items() if a == arq]
        return cands[0] if len(cands) == 1 else None

    chave = [((l.get("arquivo") or ""), l.get("pagina")) for l in linhas]
    fam = [_familia_da_unidade(l.get("unidade")) for l in linhas]
    qs = [_q(l) for l in linhas]
    afirma = [afirma_quadro_de_quantitativos(l.get("texto"))
              or afirma_quadro_de_quantitativos(l.get("descricao")) for l in linhas]
    total = [e_linha_de_total(l.get("descricao")) for l in linhas]

    # ── o TOTAL: a linha que resume as outras linhas (a) do mesmo quadro ──
    # 🪤 Erra PRA MENOS, de propósito. Linha que se diz total/subtotal, com
    # parcelas no quadro, NUNCA fica com número (bata a soma ou não); e linha
    # que é igual à soma de TODAS as outras do quadro também é total, diga o
    # que disser — senão parcelas descritas como "volume total da estrutura 3"
    # esconderiam o TOTAL GERAL e a planilha contaria em dobro.
    e_o_total = {}
    #: quem cada TOTAL resume — pra dizer, no fim, se alguma parcela ficou com número
    resume = {}
    provada_pelo_total = {}
    grupos = {}
    for i in range(n):
        if (afirma[i] or total[i]) and qs[i] > 0 and chave[i][0]:
            grupos.setdefault((chave[i], fam[i]), []).append(i)
    for membros in grupos.values():
        for i in membros:
            outras = [j for j in membros if j != i and afirma[j]]
            parc = [j for j in outras if not total[j]]
            if total[i] and len(parc) >= 2:
                soma = sum(qs[j] for j in parc)
                bate = abs(soma - qs[i]) <= 0.01 * qs[i]
                e_o_total[i] = {"soma": soma, "parcelas": len(parc), "bate": bate}
                resume[i] = parc
                if (bate and afirma[i]
                        and not a_fonte_declarada_e_uma_soma(linhas[i].get("texto"))):
                    for j in parc:
                        provada_pelo_total[j] = qs[i]
            elif (total[i] and len(parc) == 1
                  and abs(qs[parc[0]] - qs[i]) <= 0.01 * qs[i]):
                # total de UMA linha só é a mesma linha duas vezes — e não prova
                # nada (é o mesmo número)
                e_o_total[i] = {"soma": qs[parc[0]], "parcelas": 1, "bate": True}
                resume[i] = parc
            elif len(outras) >= 2:
                soma = sum(qs[j] for j in outras)
                if abs(soma - qs[i]) <= 0.01 * qs[i]:
                    # 🪤 22/09 (revisão): aqui a linha NÃO se diz total — é o
                    # NÚMERO que manda. Uma parcela legítima igual à soma das
                    # outras cai aqui também, então a frase tem que perguntar,
                    # não afirmar (`pela_soma`).
                    e_o_total[i] = {"soma": soma, "parcelas": len(outras), "bate": True,
                                    "pela_soma": True}
                    resume[i] = outras

    # ── o quadro aparece no texto do PDF? (trava 1) ──
    achados = {}
    for i in range(n):
        if not afirma[i] or qs[i] <= 0:
            continue
        _ns = _nums_da(linhas[i])
        if _ns and int(round(qs[i] * 100)) in _ns:
            achados.setdefault(chave[i], set()).add(int(round(qs[i] * 100)))

    for i in range(n):
        if i in e_o_total:
            out[i] = ("e_o_total", e_o_total[i])
            continue
        if not afirma[i] or qs[i] <= 0:
            continue
        _ns = _nums_da(linhas[i])
        _c = int(round(qs[i] * 100))
        if _ns and _c in _ns and len(achados.get(chave[i], ())) >= 2:
            out[i] = ("texto", {})
        elif i in provada_pelo_total:
            out[i] = ("total", {"total": provada_pelo_total[i]})
        else:
            out[i] = ("sem_prova", {})
    # 🩸 22/09 (revisão): sem prova, as parcelas ficam em branco JUNTO com o
    # total — e aí "fica em branco pra não contar duas vezes" era falso: não
    # conta nem uma. A frase do total precisa saber se alguma parcela ficou.
    for i, parc in resume.items():
        e_o_total[i]["parcelas_com_numero"] = sum(
            1 for j in parc if out[j] and out[j][0] in ("texto", "total"))
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  AÇO POR TAXA não vira número (22/09/2026)
# ─────────────────────────────────────────────────────────────────────────────
# 🩸 22/09/2026 — job ee801b82: 294 + 215 + 485 + 751 = 1.745 kg de aço
# "estimado por taxa de consumo típica de 100 kg/m³" numa prancha SEM quadro de
# ferros — o mesmo aço que as listas das outras pranchas já traziam (e 100×
# um volume que o próprio motor zerou). No f8d8e6d8, mais 2.114 kg assim.
# kg não passa pela honestidade de área, então nada tocava nessas linhas.
# 🔑 Regra nº3: razão típica ALERTA, nunca vira número. Peso por taxa não é o
# aço do projeto do cliente — é um índice de livro multiplicado por um volume.
# 📏 Medido em 22/09 (90 dias, sem avaliação, kg > 0 fora do CAD e da revisão
# do cliente), rodando esta função nas 48 linhas que citam taxa/índice/
# consumo/kg por m: 25 linhas em 8 jobs falam de taxa, índice ou consumo; a
# régua pega 24 em 7 jobs (92.146 kg), 16 delas fora deste caso. A 25ª é aço
# de LISTA com a taxa de conferência — fica.
# 🩸 22/09 (revisão): a 1ª versão não via "ÍNDICE", que é a mesma conta com
# outro nome ("Estimativa por índice: 310,38 m² × 25 kg/m² (índice típico
# residencial)"): 3 linhas, 11.710 kg, num job de 18/08 ficavam com número.
# 🪤 A menção à taxa NÃO basta: "Soma dos quadros de ferragens … Taxa média
# ponderada ≈ 141,71 kg/m³" é aço de LISTA com a taxa como conferência. O que
# decide é o peso ter SAÍDO da taxa (multiplicação encostada nela, ou "adotada",
# "estimado por taxa/índice", "consumo típico", "índice típico").
# 🪤 "adotada/aplicada N kg/m" só vale com m³/m²: kg/m SEM expoente é massa
# LINEAR nominal (0,395 kg/m do ø8), que é a conta certa do aço de lista.
# 🪤 "calculado pelo índice/pela taxa DE PERDAS" é o +10% da lista, não taxa de
# consumo: fica de fora.
_RE_PESO_DA_TAXA = _re.compile(
    r"kg\s*/\s*m\s*[³3²2][^.|;]{0,40}?[×x*]\s*\(?\s*\d"
    r"|m\s*[³3²2]\s*\)?\s*[×x*]\s*(?:taxa\s*(?:de\s*)?)?\d+(?:[.,]\d+)?\s*kg\s*/\s*m"
    r"|\b(?:estimad[oa]s?|estimativa|calculad[oa]s?)\s+(?:\w+\s+){0,2}?"
    r"(?:por|pel[oa]|com\s+[oa])\s+(?:taxa|[íi]ndice)(?!\s+de\s+perdas?\b)"
    r"|\btaxa\b[^.|;]{0,60}?\b(?:adotad[oa]|aplicad[oa])"
    r"|\b(?:adotad[oa]|aplicad[oa])\b[^.|;]{0,15}?\d+(?:[.,]\d+)?\s*kg\s*/\s*m\s*[³3²2]"
    r"|\bconsumo\s+t[íi]pico|\btaxa\s+(?:de\s+\w+\s+)?t[íi]pica"
    r"|\b[íi]ndices?\s+(?:de\s+\w+\s+)?t[íi]picos?"
    r"|\bestimativa\s+param[ée]trica",
    _re.IGNORECASE)
#: Prova de que o peso veio de LISTA/QUADRO de ferros — aí a taxa é conferência.
_RE_PESO_DE_LISTA = _re.compile(
    r"\b(?:lid[oa]s?|extra[ií]d[oa]s?|copiad[oa]s?|transcrit[oa]s?|conforme"
    r"|soma\w*(?:\s+confirmad[oa])?\s+d[oa]s?)\b[^.|;]{0,40}?"
    r"\b(?:quadros?|resumos?|listas?|tabelas?|rela[çc][ãa]o)\s+(?:de\s+|do\s+|da\s+)?"
    r"(?:a[çc]o|ferros?|ferragens?|armadura|arma[çc][ãa]o)"
    r"|\b[cp]\.?\s*tot",
    _re.IGNORECASE)


def peso_por_taxa(obs) -> bool:
    """O peso desta linha foi CALCULADO com uma taxa (kg/m³, kg/m²)?"""
    t = str(obs or "")
    if not _RE_PESO_DA_TAXA.search(t):
        return False
    return not _RE_PESO_DE_LISTA.search(t)


#: Aço de ARMADURA (o que uma lista de ferros traz) — não perfil metálico A36.
_RE_ACO_DE_ARMADURA = _re.compile(
    r"\bCA[\s-]?(?:50|60)\b|\barmadura|\barma[çc][ãa]o|\bferr(?:o|os|agem|agens)\b"
    r"|\btela\s+soldada|\bvergalh|[øØ⌀Φφ]\s*\d",
    _re.IGNORECASE)


def e_linha_de_armadura(descricao) -> bool:
    """A descrição é de aço de armadura (CA-50/60, ferros, tela, ø)?

    Serve pra frase do peso por taxa dizer "somaria com o aço das outras
    linhas" só quando essas linhas existem (22/09, revisão)."""
    return bool(_RE_ACO_DE_ARMADURA.search(str(descricao or "")))


# ─────────────────────────────────────────────────────────────────────────────
#  O PESO DE AÇO CONTRA A MASSA NOMINAL (22/09/2026)
# ─────────────────────────────────────────────────────────────────────────────
# 🩸 22/09/2026 — job f8d8e6d8, 3ª prancha: a observação traz "CTot = 1473,3 m"
# de ø8 e "PTot … parcialmente cortado na imagem (lido como '58')", e a linha
# saiu com 58 kg. 1.473,3 × 0,395 = 582 kg — o mesmo arquivo, lido no dia
# anterior, deu 582. Erro de 10× com a conta certa escrita na própria linha.
# 🔑 A conferência já existia, mas só no caminho do CAD
# (`structural_extractor`, faixa 0,70–1,70). No PDF ninguém fazia a conta.
# 📏 Medido em 22/09 (90 dias, kg fora do CAD com comprimento total e bitola na
# observação): 1 linha com erro de potência de dez (esta); outras ~9 em 4 jobs
# divergem sem ser dígito perdido — leituras de quadro que a própria IA já
# marcou como inconsistentes (tela soldada?, dois quadros somados?).
# 🚫 Por isso "diverge > 20% → troca pelo calculado" NÃO é a régua: nesses 9
# casos não se sabe se errou o peso ou o comprimento, e trocar seria inventar
# qual dos dois está certo. Só o DÍGITO PERDIDO (razão ≈ 10ⁿ) vira troca; o
# resto ganha um ALERTA com a conta (regra nº3: razão alerta, não decide).
_RE_BITOLA_ACO = _re.compile(
    r"(?:[øØ⌀Φφ]|\bbitola\s*(?:de\s*)?)\s*(\d{1,2}(?:[.,]\d)?)(?!\d)",
    _re.IGNORECASE)
_RE_COMPRIMENTO_TOTAL_ACO = _re.compile(
    r"(?:\bc\.?\s*tot(?:al)?\b|\bcomprimento\s+total\b)(?:\s*\([^)]{0,20}\))?"
    r"[^\d|;]{0,30}?(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)\s*m\b",
    _re.IGNORECASE)
#: Faixa em que peso e comprimento × massa nominal CONCORDAM — a mesma do
#: `structural_extractor` (inclui o acréscimo de 10% de perdas dos quadros).
FAIXA_PESO_NOMINAL = (0.70, 1.70)
#: Quão perto de 10ⁿ a razão tem que ficar pra ser dígito perdido. 📏 Medido:
#: o caso dá 0,997; o vizinho mais próximo no acervo que NÃO é dígito perdido
#: dá 0,856 (tela soldada lida como ø5). Cabe o +10% de perdas (1,10).
FAIXA_DIGITO_PERDIDO = (0.90, 1.20)


def conferencia_do_peso_de_aco(descricao, obs, quantidade):
    """Confere o peso de UMA linha de aço contra comprimento × massa nominal.

    Devolve None (sem o que conferir, ou concorda) ou um dict com `acao`
    ("corrige" | "alerta"), `calculado`, `comprimento_m`, `bitola_mm`,
    `massa_kg_m` e `razao` (peso da linha / calculado).
    Só confere com UMA bitola e UM comprimento total na linha: linha de total
    geral com várias bitolas não tem a quem aplicar a massa.
    """
    from structural_extractor import BITOLAS_MM, massa_linear_kg_m
    import math
    try:
        q = float(quantidade or 0)
    except (TypeError, ValueError):
        return None
    if q <= 0:
        return None
    txt = "%s | %s" % (descricao or "", obs or "")
    bitolas = set()
    for m in _RE_BITOLA_ACO.finditer(txt):
        try:
            b = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        for ok in BITOLAS_MM:
            if abs(b - ok) < 0.05:
                bitolas.add(ok)
    comprimentos = set()
    for m in _RE_COMPRIMENTO_TOTAL_ACO.finditer(str(obs or "")):
        v = num_br_para_float(m.group(1))
        if v:
            comprimentos.add(round(v, 2))
    if len(bitolas) != 1 or len(comprimentos) != 1:
        return None
    b = next(iter(bitolas))
    c = next(iter(comprimentos))
    massa = massa_linear_kg_m(b)
    calc = c * massa
    if calc <= 0:
        return None
    r = q / calc
    info = {"calculado": calc, "comprimento_m": c, "bitola_mm": b,
            "massa_kg_m": massa, "razao": r}
    if FAIXA_PESO_NOMINAL[0] <= r <= FAIXA_PESO_NOMINAL[1]:
        return None
    k = round(math.log10(r))
    if k != 0 and FAIXA_DIGITO_PERDIDO[0] <= r / (10 ** k) <= FAIXA_DIGITO_PERDIDO[1]:
        info["acao"] = "corrige"
    else:
        info["acao"] = "alerta"
    return info
