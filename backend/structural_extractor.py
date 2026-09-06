# -*- coding: utf-8 -*-
"""Medição ESTRUTURAL determinística a partir dos dados extraídos do DXF.

Por que existe: o roteamento estrutural v1 (27/06) lia aço/concreto via prompt,
mas quase tudo saía qty=0 ou estimado — a tabela de aço chegava pra IA como um
SET de textos embaralhados (célula por célula, ordenado alfabeticamente) e
pilares desenhados como retângulos fechados viravam só "perímetro somado" no
layer. Este módulo mede DE VERDADE, por código, o que dá pra medir com
honestidade — e nada além disso.

REGRA Nº1 DO PRODUTO (inegociável): "confirmado" (medido) SÓ quando a
quantidade veio de GEOMETRIA/TEXTO REAL do CAD. Aqui isso significa:

  MEDIDO (pode nascer 'confirmado'):
    - peso de aço por bitola LIDO do quadro/resumo de aço (texto real da
      prancha), com validação: total × soma das bitolas e/ou massa linear
      NBR 7480 quando o comprimento também está na tabela;
    - contagem de pilares (retângulos/círculos fechados em layer de PILAR,
      ou blocos INSERT em layer de PILAR) — a seção (ex.: 19x40 cm) vem da
      própria geometria do retângulo;
    - área de laje (polilinha FECHADA em layer de LAJE) — área, nunca volume.

  ESTIMADO (número de referência, NUNCA confirmado):
    - comprimento de vigas por soma das linhas do layer (viga desenhada pelas
      2 faces dobra o eixo — não dá pra distinguir por código);
    - QUALQUER volume de concreto (m³) ou área de fôrma (m²): exigem altura /
      pé-direito, que NÃO está medido no CAD 2D.

  Na dúvida, não emite (ou emite explicitamente como estimado).

REGRA DE DEPENDÊNCIA: só stdlib (re, math, statistics). NUNCA importar
ezdxf/anthropic/supabase aqui — é o que deixa o módulo testável isolado e
rápido (tests/test_estrutural.py). A parte que precisa de ezdxf (coleta dos
retângulos de pilar) vive em dwg_extractor.extract_dxf, que preenche
DXFExtraction.struct_rects e chama este módulo em to_structured_prompt().
"""
import math
import re
from dataclasses import dataclass, field
from statistics import median

# ---------------------------------------------------------------------------
# Constantes de norma (NBR 7480:2007) — usadas SÓ pra VALIDAR leitura, nunca
# pra fabricar peso "medido" (peso calculado por tabela é derivação → estimado,
# e derivação fica a cargo da IA, marcada como estimado).
# ---------------------------------------------------------------------------

BITOLAS_MM = (3.4, 4.2, 5.0, 6.3, 8.0, 10.0, 12.5, 16.0, 20.0, 25.0, 32.0, 40.0)


def massa_linear_kg_m(bitola_mm: float) -> float:
    """Massa linear aproximada (kg/m) de vergalhão CA-50/CA-60.
    Fórmula geral kg/m = d² × 0,00617 (d em mm) — ex.: 6.3 → 0,245; 8.0 → 0,395;
    10.0 → 0,617; 12.5 → 0,964; 16.0 → 1,579; 20.0 → 2,468; 25.0 → 3,856."""
    return bitola_mm * bitola_mm * 0.00617


# ---------------------------------------------------------------------------
# Retângulo/círculo de pilar coletado da geometria (preenchido pelo
# dwg_extractor com ezdxf; aqui só a estrutura de dados, stdlib pura).
# Coordenadas cx/cy e w_raw/h_raw em UNIDADES DO DESENHO (pra casar com a
# posição dos TEXTOs, que também é crua); w_m/h_m já em metros.
# ---------------------------------------------------------------------------

@dataclass
class StructRect:
    layer: str
    w_m: float
    h_m: float
    w_raw: float
    h_raw: float
    cx: float
    cy: float
    circular: bool = False


# ---------------------------------------------------------------------------
# Normalização numérica PT-BR (espelha analyzer._normalize_br_number — não dá
# pra importar analyzer aqui: ele puxa anthropic no topo).
# ---------------------------------------------------------------------------

_NUMERIC_RE = re.compile(r"-?[\d.,]+")


def _num(s) -> float | None:
    """Converte célula de tabela em float respeitando vírgula decimal BR.
    '184,50'→184.5 · '1.354,00'→1354.0 · '1,354.00'→1354.0 · 'Ø 6.3'→None
    (célula não-numérica). Retorna None quando não é um número puro."""
    if s is None:
        return None
    s = str(s).strip().replace(" ", " ").replace(" ", "")
    # 🚨 29/08/2026 — "685 kgf" virava None e o TOTAL do quadro sumia.
    # No quadro da cliente-20 o valor vem com a unidade colada ("131 kgf",
    # "685 kgf"). Aceitar sufixo de UNIDADE é diferente de aceitar texto livre:
    # continua exigindo número puro, só tolera a unidade no fim.
    # 🪤 A lista é fechada de propósito. `_num_in_text` (que pega o 1º número de
    # qualquer texto) existe pro caso solto — usá-lo aqui faria "Viga 3" virar 3
    # e encher a tabela de lixo.
    s = re.sub(r"\s*(kgf|kg|mm|cm|m|un)\.?$", "", s, flags=re.IGNORECASE).strip()
    if not s or not re.fullmatch(r"-?[\d.,]+", s):
        return None
    last_dot = s.rfind(".")
    last_com = s.rfind(",")
    if last_com > last_dot:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _num_in_text(s) -> float | None:
    """Extrai o primeiro número de um texto livre ('385,20 kg' → 385.2)."""
    if not s:
        return None
    m = _NUMERIC_RE.search(str(s))
    return _num(m.group(0)) if m else None


# ---------------------------------------------------------------------------
# Tokens de layer (mesma regra de token do dwg_extractor: split em -_ ./\|: e
# match por EQUALS ou STARTSWITH, case-insensitive).
# ---------------------------------------------------------------------------

_SPLIT_RE = re.compile(r"[-_\s./\\|:]+")

# 🏗️ 01/09/2026 — "COLS" é o padrão AIA/CAD para pilar estrutural (`S-COLS` =
# Structural Columns), e não casava: `_has_token` quebra "S-COLS" em ["S","COLS"]
# e "COLS" não começa com "COLUMN". Apareceu no arquivo do cliente-23 (RACIONAL),
# onde os 54 pilares vivem no layer `S-COLS`.
# 🪤 "COLUNA" foi TESTADO e RECUSADO: o Tiago (METAL-AR) tem o layer
# `AC-Indicação coluna Frigorígenas` — coluna frigorígena de ar-condicionado, e
# não pilar. Casaria como falso positivo em toda prancha de climatização.
# ⚠️ HONESTIDADE SOBRE O ALCANCE: isto sozinho NÃO destrava o caso do cliente-23.
# O detector de pilar só olha polilinha FECHADA, e o arquivo dele não tem
# nenhuma (2.158 LINE, 448 HATCH, 0 LWPOLYLINE) — os pilares são hachura.
# Medido em 01/09: 210 de 213 pranchas da base saem com `pilares=0`, e o
# comentário de 09/08 em dwg_extractor.py já registrava que "polilinha fechada
# quase não existe nos projetos reais". Contar pilar por HACHURA é o conserto
# que vale, e o protótipo erra 24% sem separar as vistas do desenho (67 contra
# 54 reais, porque os CORTES também desenham pilar). Fica pra quando houver
# mais de um arquivo pra validar.
_PILAR_TOKENS = ("PILAR", "COLUMN", "COLS")
_VIGA_TOKENS = ("VIGA", "BEAM")
_LAJE_TOKENS = ("LAJE", "SLAB")
_EIXO_TOKENS = ("EIXO", "AXIS")


def _has_token(name: str, tokens) -> bool:
    toks = [t.upper() for t in _SPLIT_RE.split(name or "") if t]
    for tok in toks:
        for kw in tokens:
            if tok == kw or tok.startswith(kw):
                return True
    return False


def layer_is_pilar(layer_name: str) -> bool:
    """True se o layer é claramente de PILAR (usado pelo dwg_extractor pra
    decidir quais polilinhas fechadas viram candidatos a pilar)."""
    return _has_token(layer_name, _PILAR_TOKENS)


# ---------------------------------------------------------------------------
# (a) TABELA/QUADRO/RESUMO DE AÇO — leitura de texto REAL do CAD
# ---------------------------------------------------------------------------
# No DXF cada célula da tabela costuma ser um TEXT separado. Reconstruímos a
# tabela por posição: agrupa textos por linha (Y ~igual), acha o cabeçalho com
# "PESO", mapeia colunas pelo X do cabeçalho e lê o kg de cada bitola.

_DIA_RE = re.compile(r"(?:ø|Ø|φ|Φ|%%[cC]|\bfi\b)\s*(\d{1,2}(?:[.,]\d{1,2})?)", re.IGNORECASE)
_PESO_HDR_RE = re.compile(r"\bpeso\b", re.IGNORECASE)
_COMP_HDR_RE = re.compile(r"\bcomp|c\.?\s*total|comprimento", re.IGNORECASE)
# 🚨 29/08/2026 — "BIT" NÃO CASAVA, E ISSO SOZINHO ZERAVA A PLANILHA.
# Caso cliente-20 (job 42c354a1): a coluna do quadro dela se chama "BIT",
# abreviada. Sem casar, `bitola_x` fica None, TODA linha de dados é pulada, o
# quadro sai vazio e `parse_steel_table` devolve None — o quadro nunca chega ao
# prompt e a planilha inteira sai laranja. Seis linhas perfeitas (conferidas
# uma a uma contra a NBR 7480) perdidas por três letras.
# 🪤 `\bbit\b` com borda de palavra: sem a borda, "arbitrário" e "bitmap"
# passariam a casar e qualquer texto viraria cabeçalho de bitola.
_BITOLA_HDR_RE = re.compile(r"bitola|\bbit\b|di[âa]m\.?|\bø\b|\bfi\b|gauge",
                            re.IGNORECASE)
_TOTAL_ROW_RE = re.compile(r"^\s*(?:peso\s+)?tota[l]\b", re.IGNORECASE)
_CA_RE = re.compile(r"\bCA[-\s]?\.?\s?(25|50|60)\b", re.IGNORECASE)
_KG_PER_M_RE = re.compile(r"kg\s*/\s*m", re.IGNORECASE)


def _match_bitola(value: float | None) -> float | None:
    """Casa um valor numérico com uma bitola comercial (±0,11 mm)."""
    if value is None:
        return None
    for b in BITOLAS_MM:
        if abs(value - b) <= 0.11:
            return b
    return None


def _cluster_rows(cells: list) -> list:
    """Agrupa células (text, x, y, h) em linhas por proximidade de Y.
    Tolerância relativa à altura mediana dos textos → independe da unidade."""
    if not cells:
        return []
    hs = [c[3] for c in cells if c[3] and c[3] > 0]
    if hs:
        tol = max(median(hs) * 0.75, 1e-9)
    else:
        ys = [c[2] for c in cells]
        span = max(ys) - min(ys) if len(ys) > 1 else 0
        tol = span / 200.0 if span > 0 else 1.0
    rows: list[dict] = []
    for c in sorted(cells, key=lambda c: -c[2]):
        placed = False
        for r in rows:
            if abs(r["y"] - c[2]) <= tol:
                r["cells"].append(c)
                placed = True
                break
        if not placed:
            rows.append({"y": c[2], "cells": [c]})
    for r in rows:
        r["cells"].sort(key=lambda c: c[1])
    return rows


def parse_steel_table(texts) -> dict | None:
    """Lê quadro/resumo de aço dos TEXTOs do CAD. Retorna None se a prancha
    não tem tabela de aço reconhecível (NUNCA inventa).

    Formato do retorno:
      {"por_bitola": [{"bitola_mm", "kg", "comp_m", "aco"}],
       "total_kg": float|None, "confiavel": bool, "avisos": [str], "n_quadros": int}

    "confiavel" False ⇒ a leitura tem inconsistência (soma ≠ total declarado,
    linha reprovada na massa linear) e NADA daqui pode virar 'confirmado'.
    """
    cells = []
    for t in texts or []:
        txt = (getattr(t, "text", "") or "").strip()
        if not txt:
            continue
        pos = getattr(t, "position", (0, 0)) or (0, 0)
        h = getattr(t, "height", 0) or 0
        cells.append((txt, float(pos[0]), float(pos[1]), float(h)))
    if not cells:
        return None

    rows = _cluster_rows(cells)

    # classe de aço presente na prancha (default quando a linha não indica)
    classes = set()
    for txt, *_ in cells:
        for m in _CA_RE.finditer(txt):
            classes.add(f"CA-{m.group(1)}")
    default_class = classes.pop() if len(classes) == 1 else ""
    if default_class:
        classes.add(default_class)

    avisos: list[str] = []
    entries: list[dict] = []   # linhas lidas {bitola_mm, kg, comp_m, aco}
    totals: list[tuple] = []   # (kg, indice_do_quadro | None)
    n_quadros = 0
    consumed_cells: set = set()  # ids de células já usadas pelo modo-tabela

    # ---- modo TABELA (célula por célula, reconstruída por posição) --------
    header_idxs = []
    for i, r in enumerate(rows):
        for c in r["cells"]:
            # 🚨 29/08/2026 — "PESO TOTAL" É LINHA DE TOTAL, NÃO CABEÇALHO.
            #
            # Caso cliente-20 (job 42c354a1). O rodapé do quadro dela é
            # "Peso Total 50 = 685 kgf" — e como contém a palavra *peso*, virava
            # um CABEÇALHO de quadro novo. Dois estragos de uma vez:
            #
            #  1. o TOTAL declarado nunca era lido (tinha virado cabeçalho), e a
            #     conferência soma-vs-total ficava sem termo de comparação;
            #  2. pior: esse "quadro" fantasma era o ÚLTIMO da prancha, e o
            #     último não tem limite embaixo — então suas "linhas de dados"
            #     varriam o desenho INTEIRO. Medido no arquivo dela: 1.728
            #     textos abaixo, 118 deles marcações de ferro (`%%c 5`,
            #     `2 %%c 12.5`) espalhadas pela planta. Cada uma virava linha da
            #     tabela, reprovava na massa linear, era descartada — e uma
            #     descartada marca o quadro inteiro como não-confiável.
            #
            # 🩸 Seis linhas perfeitas dela viraram laranja por causa disto.
            if (_PESO_HDR_RE.search(c[0]) and not _KG_PER_M_RE.search(c[0])
                    and not _TOTAL_ROW_RE.match(c[0])):
                header_idxs.append(i)
                break

    for hi_pos, hi in enumerate(header_idxs):
        n_quadros += 1
        hdr = rows[hi]["cells"]
        peso_x = comp_x = bitola_x = None
        outros: list = []  # colunas reconhecidas mas NÃO usadas (kg/m, qtd...) —
        #                    viram âncora "outro" pra ABSORVER os números da própria
        #                    coluna (senão massa linear 0,395 vazava pro peso)
        for c in hdr:
            if _PESO_HDR_RE.search(c[0]):
                if _KG_PER_M_RE.search(c[0]):
                    outros.append(("outro", c[1]))  # PESO (kg/m) = massa linear, não é peso
                elif peso_x is None or "total" in c[0].lower():
                    peso_x = c[1]
                else:
                    outros.append(("outro", c[1]))
            elif _COMP_HDR_RE.search(c[0]):
                comp_x = c[1]
            elif _BITOLA_HDR_RE.search(c[0]):
                bitola_x = c[1]
            else:
                outros.append(("outro", c[1]))
        if peso_x is None:
            continue
        anchors = [("peso", peso_x)]
        if comp_x is not None:
            anchors.append(("comp", comp_x))
        if bitola_x is not None:
            anchors.append(("bitola", bitola_x))
        anchors.extend(outros)

        # 🚨 29/08/2026 — O QUADRO NÃO TINHA BORDA E ENGOLIA A PRANCHA INTEIRA.
        #
        # Caso cliente-20 (job 42c354a1, prancha 0653-KZ-EST-PE-1052). O quadro dela
        # é PERFEITO — conferi as 6 linhas contra a NBR 7480, uma por uma:
        #     Ø5,0   852 m × 0,154 = 131,2   quadro diz 131   ✓
        #     Ø6,3   206 m × 0,245 =  50,5   quadro diz  50   ✓
        #     Ø8,0   157 m × 0,395 =  62,0   quadro diz  62   ✓
        #     Ø10    123 m × 0,617 =  75,9   quadro diz  76   ✓
        #     Ø12,5  409 m × 0,963 = 393,9   quadro diz 394   ✓
        #     Ø16     65 m × 1,578 = 102,6   quadro diz 103   ✓
        # E mesmo assim a planilha dela saiu com ZERO medido.
        #
        # 🔑 A CAUSA: o último cabeçalho da prancha usava `y_min = -infinito`, ou
        # seja, as "linhas de dados" do quadro iam até o fim do desenho. Medido
        # nessa prancha: o desenho vai de y=82 a y=-227, o quadro fica em y≈60, e
        # abaixo dele havia **1.728 textos**, com **118 marcações de ferro**
        # (`%%c 5`, `2 %%c 12.5`) espalhadas pela planta — a até 94 unidades de
        # distância horizontal do quadro.
        #
        # Cada marcação dessas virava candidata a linha da tabela. E a escolha de
        # coluna era `min(anchors, key=distância)` SEM TETO: um ferro desenhado no
        # meio da planta sempre "pertencia" a alguma coluna, por mais longe que
        # estivesse. Os números dele entravam como peso e comprimento, a
        # conferência de massa linear reprovava, a linha era descartada — e uma
        # linha descartada marca o QUADRO INTEIRO como não-confiável.
        #
        # 🩸 Seis linhas certas indo pro laranja por causa de um ferro desenhado
        # a 94 unidades de distância.
        #
        # 🔧 A BORDA: a tabela tem a largura das colunas dela. `passo` é o vão
        # típico entre colunas; sobra um passo de folga de cada lado pra caber
        # célula desalinhada do próprio quadro, e só. Fora disso não é linha
        # desta tabela — é desenho.
        _axs = sorted(ax for _n, ax in anchors)
        if len(_axs) >= 2:
            _vaos = [b - a for a, b in zip(_axs, _axs[1:]) if b > a]
            _passo = median(_vaos) if _vaos else (_axs[-1] - _axs[0])
        else:
            _passo = 0.0
        _passo = max(_passo, 1e-9)
        _x_ini, _x_fim = _axs[0] - _passo, _axs[-1] + _passo

        def _dentro_do_quadro(cells):
            """A linha pertence a ESTA tabela? Julga pela célula mais próxima."""
            return any(_x_ini <= c[1] <= _x_fim for c in cells)

        # linhas de dados deste quadro: abaixo do cabeçalho, até o próximo
        y_min = rows[header_idxs[hi_pos + 1]]["y"] if hi_pos + 1 < len(header_idxs) else -math.inf
        # 🪤 Parada vertical: depois do quadro vem o desenho. Sem isto, o último
        # cabeçalho da prancha continuaria varrendo até o fim do papel — só que
        # agora filtrando por x, o que ainda deixaria passar o que estivesse
        # alinhado com as colunas por coincidência.
        _fora_seguidas = 0
        for r in rows[hi + 1:]:
            if r["y"] <= y_min:
                break
            if not _dentro_do_quadro(r["cells"]):
                _fora_seguidas += 1
                if _fora_seguidas >= 3:
                    break
                continue
            _fora_seguidas = 0
            row_cells = [c for c in r["cells"] if _x_ini <= c[1] <= _x_fim]
            row_text = " ".join(c[0] for c in row_cells)
            # bitola da linha: prefixo ø explícito, ou número puro na coluna BITOLA
            bitola = None
            bitola_cell = None
            for c in row_cells:
                m = _DIA_RE.search(c[0])
                if m:
                    bitola = _match_bitola(_num(m.group(1)))
                    bitola_cell = c
                    break
            if bitola is None and bitola_x is not None:
                for c in row_cells:
                    v = _num(c[0])
                    if v is None:
                        continue
                    if _match_bitola(v) is not None and abs(c[1] - bitola_x) == min(
                            abs(c[1] - ax) for _, ax in anchors):
                        bitola = _match_bitola(v)
                        bitola_cell = c
                        break
            is_total = any(_TOTAL_ROW_RE.match(c[0]) for c in row_cells)
            if bitola is None and not is_total:
                continue

            # células numéricas → âncora de coluna mais próxima
            kg = comp = None
            for c in row_cells:
                if c is bitola_cell:
                    continue
                v = _num(c[0])
                if v is None:
                    continue
                kind = min(anchors, key=lambda a: abs(c[1] - a[1]))[0]
                if kind == "peso" and kg is None:
                    kg = v
                elif kind == "comp" and comp is None:
                    comp = v

            # linha inteira num TEXT só ("Ø 8.0  245,60  97,00"): mapeia por ordem
            if kg is None and bitola_cell is not None:
                tail = _DIA_RE.sub(" ", bitola_cell[0], count=1)
                nums = [_num(x) for x in _NUMERIC_RE.findall(tail)]
                nums = [x for x in nums if x is not None]
                if len(nums) == 2 and comp_x is not None and comp_x < peso_x:
                    comp, kg = nums[0], nums[1]
                elif len(nums) == 1 and re.search(r"\bkg\b", bitola_cell[0], re.IGNORECASE):
                    kg = nums[0]

            if is_total:
                if kg is not None and kg > 0:
                    totals.append((kg, hi_pos))
                continue
            if kg is None or not (0 < kg <= 200000):
                continue
            mrow = _CA_RE.search(row_text)
            aco = f"CA-{mrow.group(1)}" if mrow else default_class
            # validação por massa linear quando o comprimento também foi lido
            if comp is not None and comp > 0:
                esperado = comp * massa_linear_kg_m(bitola)
                if esperado > 0 and not (0.70 <= kg / esperado <= 1.70):
                    avisos.append(
                        f"Ø {bitola} mm: peso lido ({kg:.2f} kg) não bate com "
                        f"comprimento × massa linear ({esperado:.2f} kg) — linha descartada")
                    continue
            entries.append({"bitola_mm": bitola, "kg": kg, "comp_m": comp,
                            "aco": aco, "quadro": hi_pos})
            for c in row_cells:
                consumed_cells.add(id(c))

    # ---- modo LINHA (texto único com 'kg' explícito) ----------------------
    for c in cells:
        if id(c) in consumed_cells:
            continue
        txt = c[0]
        mt = re.search(r"(?:peso\s+)?total\D{0,15}?(\d(?:[\d.,\s]*\d)?)\s*kg\b(?!\s*/)",
                       txt, re.IGNORECASE)
        if mt:
            v = _num(mt.group(1).replace(" ", ""))
            if v and v > 0:
                totals.append((v, None))
            continue
        md = _DIA_RE.search(txt)
        if not md:
            continue
        bitola = _match_bitola(_num(md.group(1)))
        if bitola is None:
            continue
        mkg = re.search(r"(\d(?:[\d.,\s]*\d)?)\s*kg\b(?!\s*/)", txt[md.end():], re.IGNORECASE)
        if not mkg:
            continue
        kg = _num(mkg.group(1).replace(" ", ""))
        if kg is None or not (0 < kg <= 200000):
            continue
        mrow = _CA_RE.search(txt)
        aco = f"CA-{mrow.group(1)}" if mrow else default_class
        entries.append({"bitola_mm": bitola, "kg": kg, "comp_m": None,
                        "aco": aco, "quadro": None})

    if not entries and not totals:
        return None

    # ---- consolidação + consistência --------------------------------------
    #
    # 🚨 28/08/2026 — O RESUMO GERAL ERA SOMADO COMO SE FOSSE MAIS UM QUADRO.
    #
    # Prancha estrutural costuma trazer um quadro por elemento (vigas, lajes,
    # pilares) E um RESUMO GERAL que repete tudo junto. O código antigo somava
    # os três, então lia o DOBRO do aço da obra. Daí saíam dois estragos:
    #
    #   (a) se os quadros individuais NÃO tinham linha TOTAL, a soma dobrava e
    #       o total não: a checagem de 5% reprovava e TUDO virava 'estimado'.
    #       Medido no banco: 127 itens, 105 TONELADAS de aço rebaixadas assim —
    #       o motor tinha lido o número certo da prancha e desconfiou de si.
    #   (b) se os quadros TINHAM linha TOTAL, os dois lados dobravam junto,
    #       batiam entre si, e o item saía CONFIRMADO com o dobro do peso.
    #       Isso é pior: é a regra dura nº1 quebrada, com número inventado
    #       carimbado de MEDIDO. Provado em experimento controlado; ainda não
    #       observado em cliente (só 5 itens de aço confirmados no banco, todos
    #       de prancha com quadro único).
    #
    # 🔑 O SINAL QUE SEPARA OS DOIS CASOS: um resumo geral é, por definição, a
    # SOMA dos outros quadros — e por isso é ESTRITAMENTE MAIOR que cada um
    # deles. Dois quadros legítimos de mesmo peso (250 + 250) não têm ninguém
    # estritamente maior, então não são confundidos com resumo.
    #
    # 🪤 Quando não dá pra decidir (exatamente dois valores iguais: pode ser
    # "vigas 250 + lajes 250" ou "quadro 250 + resumo 250"), a saída é dizer
    # que NÃO SABE e marcar estimado. Chutar aqui é escolher entre entregar
    # metade ou o dobro do aço — os dois erram feio, e um deles erra carimbado
    # de medido.

    def _indice_do_resumo(valores, tol=0.02):
        """Índice do valor que é a soma dos demais (o resumo geral), ou None."""
        if len(valores) < 2:
            return None
        for i, v in enumerate(valores):
            resto = [x for j, x in enumerate(valores) if j != i]
            s = sum(resto)
            if s <= 0 or abs(v - s) / s > tol:
                continue
            # estritamente maior que CADA um dos outros — é o que descarta o
            # falso positivo do 250+250
            if all(v > x * (1 + tol) for x in resto):
                return i
            return None
        return None

    ambiguo = False

    # ── 1. o TOTAL declarado ────────────────────────────────────────────────
    total_kg = None
    if totals:
        vals = [kg for kg, _q in totals]
        i_res = _indice_do_resumo(vals)
        if i_res is not None:
            total_kg = round(vals[i_res], 2)
            avisos.append(
                f"a prancha traz {len(vals)} totais e um deles ({total_kg:.2f} kg) é a "
                f"soma dos outros — tratei como RESUMO GERAL, não somei em cima")
        elif len(vals) == 2 and abs(vals[0] - vals[1]) <= 0.02 * max(vals):
            ambiguo = True
            total_kg = round(sum(vals), 2)
            avisos.append(
                f"dois totais iguais ({vals[0]:.2f} kg) — pode ser dois quadros de mesmo "
                f"peso OU um quadro e seu resumo; não dá pra decidir pela prancha")
        else:
            total_kg = round(sum(vals), 2)

    # ── 2. as linhas por bitola ─────────────────────────────────────────────
    # Se um QUADRO inteiro é o resumo dos outros, ele sozinho já é a leitura
    # completa: usar só ele evita a soma em dobro e mantém o detalhe por bitola.
    quadros = {}
    for e in entries:
        quadros.setdefault(e.get("quadro"), []).append(e)
    usadas = entries
    if len(quadros) > 1:
        chaves = sorted(quadros, key=lambda k: (k is None, k))
        somas = [sum(x["kg"] for x in quadros[k]) for k in chaves]
        i_res = _indice_do_resumo(somas)
        if i_res is not None:
            usadas = quadros[chaves[i_res]]
            avisos.append(
                f"{len(chaves)} quadros de aço na prancha e um deles ({somas[i_res]:.2f} kg) "
                f"é a soma dos demais — usei só o RESUMO GERAL, sem somar em dobro")
        elif len(chaves) == 2 and abs(somas[0] - somas[1]) <= 0.02 * max(somas):
            ambiguo = True
            avisos.append(
                f"dois quadros de peso igual ({somas[0]:.2f} kg cada) — pode ser dois "
                f"elementos OU um quadro e seu resumo; não dá pra decidir pela prancha")

    by_bitola: dict[float, dict] = {}
    # 🔑 Marca se ALGUMA bitola veio de mais de um quadro. É o sinal de que a
    # soma pode ser leitura em dobro — e a conferência por massa linear é cega
    # pra isso, porque kg e comprimento dobram juntos.
    _repetiu_bitola = False
    for e in usadas:
        b = e["bitola_mm"]
        if b in by_bitola:
            _repetiu_bitola = True
            by_bitola[b]["kg"] += e["kg"]
            if e["comp_m"]:
                by_bitola[b]["comp_m"] = (by_bitola[b]["comp_m"] or 0) + e["comp_m"]
            if "somei" not in " ".join(avisos):
                avisos.append("mesma bitola em mais de um quadro — somei os pesos; "
                              "confira se não é resumo geral duplicado")
        else:
            by_bitola[b] = dict(e)
    por_bitola = [by_bitola[b] for b in sorted(by_bitola)]

    confiavel = True
    soma = sum(e["kg"] for e in por_bitola)
    if total_kg is not None and por_bitola:
        if total_kg > 0 and abs(soma - total_kg) / total_kg > 0.05:
            confiavel = False
            avisos.append(
                f"soma das bitolas ({soma:.2f} kg) difere do TOTAL declarado na prancha "
                f"({total_kg:.2f} kg) — leitura possivelmente incompleta; tratar como ESTIMADO")

    # 🚨 29/08/2026 — O BURACO QUE DEIXAVA AÇO EM DOBRO SAIR COMO "MEDIDO".
    #
    # Achado por cético adversarial, depois de eu declarar o conserto bom. Eu
    # tinha "conferido" os 38 itens da cliente-20 recalculando comprimento × massa
    # linear e comparando com o peso. Passaram 37 de 38 dentro de 1,3%.
    #
    # 🩸 A conferência era uma TAUTOLOGIA. Quando a mesma bitola cai em mais de
    # um quadro, a consolidação acima soma o `kg` E o `comp_m` JUNTOS — então a
    # razão kg/comp continua exatamente a massa linear da norma. Reproduzido com
    # o quadro real da cliente-20 duplicado sob o mesmo cabeçalho:
    #
    #     soma lida 1632 kg   (a verdade é 816)   confiavel=True
    #     Ø5,0   262 kg / 1704 m  → NBR 262,8   desvio -0,32%
    #     Ø12,5  788 kg /  818 m  → NBR 788,6   desvio -0,08%
    #
    # Seis de seis passando com folga, e a obra recebendo o DOBRO do aço com
    # selo de MEDIDO. Eu conferi o motor com a régua do próprio motor.
    #
    # 🔑 POR QUE O CONSERTO DE 28/08 NÃO PEGA ESTE CASO: `_indice_do_resumo` só
    # enxerga resumo geral quando os quadros têm CABEÇALHOS SEPARADOS. Resumo
    # colado embaixo do mesmo cabeçalho vira um quadro só, e a duplicação
    # emitia apenas um AVISO — que não rebaixava nada.
    #
    # 🔒 A REGRA AGORA: bitola repetida entre quadros só pode virar MEDIDO se
    # houver um TOTAL declarado pra conferir contra. Sem essa âncora, a soma é
    # indistinguível do dobro, e a resposta honesta é "não sei" → estimado.
    # 🪤 Não rebaixa quando HÁ total: aí a soma tem verificação independente, e
    # foi o que salvou 5 das 6 pranchas da cliente-20.
    if _repetiu_bitola and total_kg is None:
        confiavel = False
        avisos.append(
            "a mesma bitola aparece em mais de um quadro e a prancha NÃO declara "
            "um peso total pra conferir — a soma fica indistinguível de uma "
            "leitura em dobro. Tratando como ESTIMADO: confira o quadro impresso")

    if ambiguo:
        confiavel = False
    if any("descartada" in a for a in avisos):
        confiavel = False

    return {
        "por_bitola": [
            {"bitola_mm": e["bitola_mm"], "kg": round(e["kg"], 2),
             "comp_m": round(e["comp_m"], 2) if e.get("comp_m") else None,
             "aco": e.get("aco") or ""}
            for e in por_bitola
        ],
        "total_kg": total_kg,
        "confiavel": confiavel,
        "avisos": avisos,
        "n_quadros": max(n_quadros, 1 if entries or totals else 0),
    }


# ---------------------------------------------------------------------------
# (b) PILARES — contagem geométrica (retângulos/círculos fechados + blocos)
# ---------------------------------------------------------------------------

_PNAME_RE = re.compile(r"^\s*P\s?\d{1,3}\s*$", re.IGNORECASE)


def count_pillars(extraction) -> dict | None:
    """Conta pilares medidos na geometria. Fontes (sem dupla contagem — blocos
    são INSERTs, retângulos são polilinhas do modelspace):
      1. struct_rects: retângulos/círculos FECHADOS em layer de PILAR (coletados
         pelo dwg_extractor), deduplicados por centro (contorno duplo = 1 pilar);
      2. blocos INSERT em layer de PILAR ou com 'PILAR' no nome.
    Nomes P1/P2... vêm de TEXTOs próximos ao centro do retângulo (só rótulo —
    a QUANTIDADE é sempre a contagem geométrica). Retorna None se nada achou."""
    rects = list(getattr(extraction, "struct_rects", None) or [])
    _rects_todos = rects
    rects = [r for r in rects if layer_is_pilar(getattr(r, "layer", ""))]

    # 🪤 DESENHO QUE NUMERA OS LAYERS (Isabelle, 05/08/2026). A planta de fôrma
    # de um prédio de 7 pavimentos entregou 1 item medido porque os layers dela
    # se chamam '02', '4', '5', '100' — layer_is_pilar não casa com nada e a
    # geometria inteira era descartada aqui em cima, antes de qualquer medição.
    # Numerar layer é convenção comum em estrutural; não é defeito do desenho.
    #
    # Quando NENHUM retângulo passa pelo nome do layer, o RÓTULO vira o filtro:
    # retângulo com um texto "P12" DENTRO dele é pilar. O mecanismo de rótulo já
    # existia logo abaixo (labels por proximidade) — só rodava tarde demais.
    #
    # 🔒 Critério apertado de propósito: o texto tem que cair DENTRO do
    # retângulo, não "perto". Porta, mobiliário e moldura não têm P12 no meio.
    rotulo_foi_o_filtro = False
    if not rects and _rects_todos:
        _txts = []
        for _t in (getattr(extraction, "texts", None) or []):
            _s = (getattr(_t, "text", "") or "").strip()
            _p = getattr(_t, "position", None)
            if _p and _PNAME_RE.match(_s):
                _txts.append((_s, _p))
        if _txts:
            _achados = []
            for _r in _rects_todos:
                # 🔒 Sanidade de seção. Sem isso, QUADRO DE ESQUADRIAS vira
                # pilar: as células dele são retângulos com "P1", "P2" escritos
                # dentro, exatamente o padrão que este atalho procura. Pilar de
                # concreto tem lado entre 10 cm e 2,5 m — célula de tabela e
                # moldura de prancha caem fora.
                _menor, _maior = sorted((_r.w_m, _r.h_m))
                if not (0.10 <= _menor <= 2.50 and _maior <= 3.00):
                    continue
                _hw, _hh = _r.w_raw / 2.0, _r.h_raw / 2.0
                for _s, _p in _txts:
                    if abs(_p[0] - _r.cx) <= _hw and abs(_p[1] - _r.cy) <= _hh:
                        _achados.append(_r)
                        break
            # 2 é o mínimo pra não transformar um acaso em medição.
            if len(_achados) >= 2:
                rects = _achados
                rotulo_foi_o_filtro = True

    # dedupe por centro: contorno duplo/repetido do mesmo pilar conta 1
    kept: list = []
    for r in sorted(rects, key=lambda r: -(r.w_m * r.h_m)):
        dup = False
        for k in kept:
            lim = 0.6 * max(min(k.w_raw, k.h_raw), min(r.w_raw, r.h_raw))
            if math.hypot(r.cx - k.cx, r.cy - k.cy) < lim:
                dup = True
                break
        if not dup:
            kept.append(r)

    # rótulos P1/P2... por proximidade (1 texto rotula só o retângulo mais perto)
    labels: dict[int, str] = {}
    if kept:
        for t in getattr(extraction, "texts", None) or []:
            txt = (getattr(t, "text", "") or "").strip()
            if not _PNAME_RE.match(txt):
                continue
            pos = getattr(t, "position", None)
            if not pos:
                continue
            best, best_d = None, math.inf
            for idx, r in enumerate(kept):
                d = math.hypot(pos[0] - r.cx, pos[1] - r.cy)
                if d < best_d:
                    best, best_d = idx, d
            if best is not None and best_d <= 4.0 * max(kept[best].w_raw, kept[best].h_raw):
                labels.setdefault(best, txt.replace(" ", "").upper())

    por_secao: dict[str, dict] = {}
    for idx, r in enumerate(kept):
        if r.circular:
            key = f"Ø{round(r.w_m * 100)} cm"
        else:
            a, b = sorted((round(r.w_m * 100), round(r.h_m * 100)))
            key = f"{a}x{b} cm"
        d = por_secao.setdefault(key, {"secao_cm": key, "qtd": 0, "nomes": []})
        d["qtd"] += 1
        if idx in labels:
            d["nomes"].append(labels[idx])
    for d in por_secao.values():
        d["nomes"] = sorted(set(d["nomes"]))

    # Blocos que TÊM 'pilar' no nome/layer mas NÃO são o pilar de concreto:
    # eixos, hachura (rayado), cota, texto, tabela, símbolo. Contá-los inflava
    # o total (caso Luciano: 'Eixos do pilar'=136 + 'RAYADO Pxx' → 184 falsos).
    _BLOCO_NAO_PILAR = (
        "EIXO", "RAYADO", "HACH", "HATCH", "COTA", "TEXTO", "TABELA", "QUADRO",
        "TITULO", "TÍTULO", "LEGENDA", "SIMBOLO", "SÍMBOLO", "CARIMBO", "NORTE",
        "SETA", "NIVEL", "NÍVEL", "ETIQUETA",
    )
    blocos = []
    for b in getattr(extraction, "blocks", None) or []:
        bname = getattr(b, "name", "") or ""
        blayer = getattr(b, "layer", "") or ""
        _bn_up = bname.upper()
        if any(tok in _bn_up for tok in _BLOCO_NAO_PILAR):
            continue  # eixo / hachura / anotação — não é pilar de concreto medido
        if _has_token(blayer, _PILAR_TOKENS) or "PILAR" in _bn_up:
            blocos.append({"nome": bname, "qtd": int(getattr(b, "count", 0) or 0)})

    total = len(kept) + sum(x["qtd"] for x in blocos)
    if total <= 0:
        return None
    return {
        "total": total,
        "rects_qtd": len(kept),
        "layers": sorted({r.layer for r in kept}),
        "por_secao": sorted(por_secao.values(), key=lambda d: -d["qtd"]),
        "blocos": blocos,
        # Quem monta o texto pro modelo precisa saber que a identificação veio
        # do rótulo, não do nome do layer — a contagem é geométrica igual, mas
        # a procedência muda e o cliente tem direito de saber.
        "por_rotulo": rotulo_foi_o_filtro,
    }


# ---------------------------------------------------------------------------
# (c) VIGAS (referência, estimado) e LAJES (área medida)
# ---------------------------------------------------------------------------

def measure_beams(extraction) -> dict | None:
    """Soma comprimento das linhas/polilinhas em layer de VIGA. HONESTIDADE:
    viga desenhada pelas 2 faces soma o dobro do eixo — por isso o valor é
    REFERÊNCIA (estimado), exceto layer de EIXO (aí é o eixo de fato)."""
    per_layer: dict[str, float] = {}
    for w in getattr(extraction, "walls", None) or []:
        ly = getattr(w, "layer", "") or ""
        if _has_token(ly, _VIGA_TOKENS):
            per_layer[ly] = per_layer.get(ly, 0.0) + (getattr(w, "length", 0) or 0)
    out = [{"layer": ly, "m": round(v, 2), "eixo": _has_token(ly, _EIXO_TOKENS)}
           for ly, v in sorted(per_layer.items()) if v >= 0.5]
    return {"por_layer": out} if out else None


def measure_slabs(extraction) -> dict | None:
    """Área de laje por polilinha FECHADA em layer de LAJE (m² medido; o
    dedupe de contornos aninhados já aconteceu no dwg_extractor). Área, nunca
    volume — a espessura NÃO está medida no CAD 2D."""
    sums: dict[str, dict] = {}
    for p in getattr(extraction, "polygon_areas", None) or []:
        ly = getattr(p, "layer", "") or ""
        if _has_token(ly, _LAJE_TOKENS):
            d = sums.setdefault(ly, {"layer": ly, "m2": 0.0, "contornos": 0})
            d["m2"] += (getattr(p, "area", 0) or 0)
            d["contornos"] += 1
    out = [{"layer": d["layer"], "m2": round(d["m2"], 2), "contornos": d["contornos"]}
           for d in sums.values() if d["m2"] > 0]
    return {"por_layer": sorted(out, key=lambda d: -d["m2"])} if out else None


# ---------------------------------------------------------------------------
# Orquestração + seção de prompt
# ---------------------------------------------------------------------------

def extract_structural_measurements(extraction) -> dict:
    """Roda as medições estruturais determinísticas sobre uma DXFExtraction
    (duck-typed). Cada frente se auto-limita (só emite quando o dado REAL
    existe) — numa prancha de arquitetura sem tabela de aço nem layers
    PILAR/VIGA/LAJE o retorno é {} e NADA muda no fluxo. Nunca lança."""
    result: dict = {}
    try:
        aco = parse_steel_table(getattr(extraction, "texts", None) or [])
        if aco:
            result["aco"] = aco
    except Exception:
        pass
    try:
        pil = count_pillars(extraction)
        if pil:
            result["pilares"] = pil
    except Exception:
        pass
    try:
        vig = measure_beams(extraction)
        if vig:
            result["vigas"] = vig
    except Exception:
        pass
    try:
        laj = measure_slabs(extraction)
        if laj:
            result["lajes"] = laj
    except Exception:
        pass
    return result


def structural_prompt_section(struct: dict) -> str:
    """Renderiza o bloco de MEDIÇÕES ESTRUTURAIS pro prompt do caminho DXF.
    Linhas [MEDIDO] podem virar item 'confirmado' (quantidade literal);
    [REFERÊNCIA] entra como 'estimado'. Volume/fôrma: sempre estimado."""
    if not struct:
        return ""
    L: list[str] = []
    L.append("════════════════════════════════════════════════════════")
    L.append("MEDIÇÕES ESTRUTURAIS DETERMINÍSTICAS (o código leu DIRETO do CAD)")
    L.append("════════════════════════════════════════════════════════")
    L.append("As linhas abaixo são EXTRAÇÕES OBJETIVAS do arquivo (texto/geometria real),")
    L.append("no mesmo nível de 'CONTAGEM DE BLOCOS' e 'ÁREAS HACHURADAS':")
    L.append("- Linha marcada [MEDIDO]: gere o item copiando a quantidade LITERAL e marque")
    L.append("  confidence=\"confirmado\".")
    L.append("- Linha marcada [REFERÊNCIA]: use o número como base, mas confidence=\"estimado\".")
    L.append("- VOLUME de concreto (m³) e área de FÔRMA (m²) NÃO foram medidos (não há")
    L.append("  altura/pé-direito medido no CAD 2D) — se gerar esses itens, marque SEMPRE")
    L.append("  \"estimado\" e diga na observação que foi derivado.")
    L.append("")

    aco = struct.get("aco")
    if aco:
        tag = "[MEDIDO]" if aco.get("confiavel") else "[REFERÊNCIA]"
        L.append("QUADRO/RESUMO DE AÇO (lido dos textos da prancha):")
        for e in aco.get("por_bitola", []):
            comp = f" (comprimento total {e['comp_m']:.2f} m)" if e.get("comp_m") else ""
            cls = f" {e['aco']}" if e.get("aco") else ""
            L.append(f"  {tag} Aço{cls} Ø {e['bitola_mm']} mm: {e['kg']:.2f} kg{comp}")
        if aco.get("total_kg") is not None:
            L.append(f"  {tag} PESO TOTAL declarado na prancha: {aco['total_kg']:.2f} kg")
        for a in aco.get("avisos", []):
            L.append(f"  ⚠ {a}")
        if aco.get("confiavel"):
            L.append("  → Gere UM item por bitola (unidade kg, quantidade literal, confirmado).")
            L.append("    NÃO gere item separado com o TOTAL — seria dupla contagem; o total")
            L.append("    serve só de conferência." if aco.get("por_bitola") else
                     "    Sem detalhe por bitola: gere um único item com o peso total (kg, confirmado).")
        else:
            L.append("  → Leitura com inconsistência: use como base mas marque TUDO 'estimado'.")
        L.append("")

    pil = struct.get("pilares")
    if pil:
        if pil.get("rects_qtd"):
            lyr = ", ".join(pil.get("layers", []))
            L.append(f"PILARES (contagem geométrica — retângulos/círculos fechados no layer {lyr}):")
            L.append(f"  [MEDIDO] {pil['rects_qtd']} pilares contados")
            for s in pil.get("por_secao", []):
                nomes = f" ({', '.join(s['nomes'])})" if s.get("nomes") else ""
                L.append(f"  [MEDIDO] seção {s['secao_cm']}: {s['qtd']} un{nomes}")
            L.append("  → Gere um item por seção: \"Pilar de concreto — seção <s>\", unidade un,")
            L.append("    quantidade literal, confirmado. A seção veio da geometria (medida).")
            L.append("  → O comprimento do layer de pilar em 'COMPRIMENTOS POR LAYER' é o PERÍMETRO")
            L.append("    desses retângulos — NÃO vire item.")
            L.append("  → Volume desses pilares NÃO está medido (sem altura) — se listar concreto/fôrma,")
            L.append("    marque \"estimado\".")
        for b in pil.get("blocos", []):
            L.append(f"  [MEDIDO] bloco '{b['nome']}': {b['qtd']} un (INSERT em layer de pilar)")
        L.append("")

    vig = struct.get("vigas")
    if vig:
        L.append("VIGAS (comprimento somado das linhas do layer):")
        for v in vig.get("por_layer", []):
            if v.get("eixo"):
                L.append(f"  [MEDIDO] layer '{v['layer']}': {v['m']:.2f} m (eixo de viga)")
            else:
                L.append(f"  [REFERÊNCIA] layer '{v['layer']}': {v['m']:.2f} m — soma de TODAS as")
                L.append("    linhas do layer; viga desenhada pelas 2 faces dobra o eixo real.")
        L.append("  → Item de viga em metros: [MEDIDO]=confirmado; [REFERÊNCIA]=estimado.")
        L.append("    NUNCA converta pra m³ como confirmado (altura não medida).")
        L.append("")

    laj = struct.get("lajes")
    if laj:
        L.append("LAJES (área de polilinha fechada no layer):")
        for s in laj.get("por_layer", []):
            L.append(f"  [MEDIDO] layer '{s['layer']}': {s['m2']:.2f} m² "
                     f"({s['contornos']} contorno(s))")
        L.append("  → Item de laje em m² com a área literal, confirmado. Volume (m³) da laje")
        L.append("    NÃO está medido (sem espessura confirmada) — se listar, \"estimado\".")
        L.append("")

    return "\n".join(L).rstrip()
