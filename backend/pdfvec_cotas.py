# -*- coding: utf-8 -*-
"""pdfvec_cotas — Medição Vetorial de PDF: VALIDAÇÃO DA ESCALA POR COTA.

A prova que faltava pra promover a medição vetorial: se o que MEDIMOS na
geometria (paredes de detect_walls / arestas de sala de detect_rooms) bate com
o que o projetista ESCREVEU nas cotas da prancha, a escala está validada por
duas fontes independentes. Este módulo entrega a PROVA (campos de evidência);
a promoção pra planilha do cliente é decisão de outra etapa — aqui nada é
promovido (regra nº 1: nunca estimar como confirmado).

Como funciona
-------------
1. TEXTOS COM POSIÇÃO via pypdfium2 (textpage.count_rects/get_rect/
   get_text_bounded — mesma família de API que o pdfvec_carimbo usa pra
   renderizar). Cada "rect" é um trecho de texto contíguo com bbox em pontos
   PDF (y pra cima — mesmo espaço do resto do pipeline). Prancha em que a
   cota foi plotada como DESENHO (texto explodido em curvas) devolve 0 tokens
   — resultado honesto: sem texto, sem validação (nunca chuta).
2. TOKENS COM CARA DE COTA (formatos brasileiros):
     "350"  "120"        inteiro sem separador
     "1,20" "3.50"       decimal com vírgula OU ponto (1-2 casas)
     "0,98m" "35cm"      unidade colada (m/cm, maiúscula ou minúscula)
   Hipótese de unidade (documentada e conservadora):
     - unidade explícita ("m"/"cm") SEMPRE vence;
     - valor >= 20 (com ou sem separador) => CENTÍMETROS (350 -> 3,50 m;
       122.5 -> 1,225 m) — convenção dominante de cota BR em planta;
     - valor < 20 COM separador decimal => METROS (1,20 -> 1,20 m);
     - inteiro < 20 SEM separador => AMBÍGUO (número de item/revisão/detalhe)
       => descartado. Melhor perder uma cota do que validar com "08".
   Só tokens DENTRO do bbox da view principal contam (cota de outra viewport
   tem outra escala — ver multi-escala abaixo).
3. CASAMENTO cota × elemento medido:
     - elementos = paredes de detect_walls (com axis/span_pt/p_pt) e as 4
       arestas do bbox de cada sala de detect_rooms;
     - valor da cota bate com o comprimento medido em ±2% (TOL_REL);
     - posição da cota PERTO do elemento, proporcional ao tamanho dele em pt
       (texto de cota fica na linha de cota, offset da parede — a tolerância
       perpendicular cresce com o elemento, com piso e teto absolutos);
     - projeção axial do token dentro do vão do elemento (com folga de 15%).
4. INDEPENDÊNCIA: pareamento guloso 1-pra-1 (menor erro relativo primeiro);
   cada token valida no máximo UM elemento e vice-versa. >= 2 pares
   independentes => escala_validada_por_cota.

Multi-escala (risco nº 1 do spike de PDF vetorial): prancha com 2+ viewports
de escalas DISTINTAS. A validação usa apenas tokens dentro do bbox da view
que foi efetivamente medida — portanto "escala_validada" vale SÓ para a view
principal, nunca para a prancha inteira. O integrador (pdf_vector) marca
"cotas_escopo": "view_principal" quando há mais de uma escala na página.

Zero IA, zero rede, determinístico. Uso:
    from pdfvec_cotas import validate_scale
    res = validate_scale(path, 0, scale_denominator=50, region_bbox=bbox,
                         walls=walls_list, rooms=rooms_list)
    # -> {"n_cotas": 14, "n_matches": 3, "validada": True, ...}
"""
from __future__ import annotations

import re
from typing import Optional, Sequence

PT_TO_M: float = 0.0254 / 72.0   # metros por ponto PDF em escala 1:1

TOL_REL: float = 0.02            # cota bate com o medido em ±2%
PROX_FRAC: float = 0.25          # tolerância perpendicular ∝ tamanho do elemento
PROX_MIN_PT: float = 15.0        # piso: cota de elemento curto ainda é achável
PROX_MAX_PT: float = 90.0        # teto: cota a >90pt não é "deste" elemento
AXIAL_MARGIN_FRAC: float = 0.15  # folga da projeção axial além das pontas
MIN_ELEM_M: float = 0.40         # elemento menor que isso não é validável
MAX_COTA_M: float = 100.0        # cota acima disso não é dimensão de planta
MAX_RECTS: int = 6000            # teto de trechos de texto lidos por página
MAX_TOKENS: int = 2000           # teto de tokens numéricos considerados
MAX_ELEMS: int = 1200            # teto de elementos casáveis

# Derivação de escala por votação das cotas (ver derive_scale_from_cotas).
# Escalas usadas em prancha de arquitetura no Brasil — a votação só aceita
# uma dessas, o que já descarta sozinha a maior parte do ruído.
ESCALAS_PADRAO: tuple[float, ...] = (10, 15, 20, 25, 33.33, 50, 75, 100,
                                     125, 150, 200, 250, 500, 1000)
TOL_ESCALA_REL: float = 0.03     # par "vota" numa escala padrão se cair a ±3%
MIN_VOTOS_ESCALA: int = 4        # abaixo disso é coincidência, não evidência
DOMINANCIA: float = 2.0          # a 1ª tem que ter o dobro da 2ª colocada
MAX_PONTAS: int = 400            # teto de extremos por eixo (custo O(n) da cadeia)

# número BR com unidade opcional colada: "350", "1,20", "3.50", "0,98m", "35cm"
_COTA_RE = re.compile(r"^(\d{1,4})(?:[.,](\d{1,2}))?(CM|M)?$", re.IGNORECASE)


# ───────────────────────── parsing (puro, testável) ─────────────────────────

def parse_cota_value(text: str) -> Optional[float]:
    """Interpreta um token como cota e devolve o valor em METROS (ou None).

    Regras de unidade (ver docstring do módulo): unidade explícita vence;
    >= 20 => cm; decimal < 20 => metros; inteiro < 20 sem separador => None
    (ambíguo — número de item/revisão).
    """
    t = (text or "").strip().replace(" ", "")
    m = _COTA_RE.match(t)
    if not m:
        return None
    inteiro, frac, unit = m.group(1), m.group(2), m.group(3)
    value = float(f"{inteiro}.{frac}" if frac else inteiro)
    if value <= 0:
        return None
    unit = unit.lower() if unit else None
    if unit == "m":
        meters = value
    elif unit == "cm":
        meters = value / 100.0
    elif value >= 20.0:
        meters = value / 100.0          # convenção BR: cota de planta em cm
    elif frac is not None:
        meters = value                  # decimal pequeno: já está em metros
    else:
        return None                     # inteiro < 20 sem separador: ambíguo
    if not (0.05 <= meters <= MAX_COTA_M):
        return None
    return meters


def _split_rect_tokens(text: str, l: float, b: float, r: float,
                       t: float) -> list[dict]:
    """Divide o texto de um rect em tokens, com centro aproximado por
    interpolação proporcional ao longo do EIXO LONGO do rect (texto vertical
    de cota tem w pequeno e h grande)."""
    words = (text or "").split()
    if not words:
        return []
    total = sum(len(w) for w in words) + (len(words) - 1)
    out: list[dict] = []
    pos = 0
    horizontal = (r - l) >= (t - b)
    for w in words:
        frac0 = pos / max(total, 1)
        frac1 = (pos + len(w)) / max(total, 1)
        fmid = (frac0 + frac1) / 2.0
        if horizontal:
            cx = l + fmid * (r - l)
            cy = (b + t) / 2.0
        else:
            cx = (l + r) / 2.0
            cy = b + fmid * (t - b)
        out.append({"text": w, "center": (cx, cy),
                    "bbox": (l, b, r, t)})
        pos += len(w) + 1
    return out


# ───────────────────── extração de tokens (pypdfium2) ─────────────────────

def extract_cota_tokens(pdf_path: str, page_index: int = 0,
                        region_bbox: Optional[Sequence[float]] = None) -> list[dict]:
    """Extrai tokens numéricos com cara de cota e posição (pontos PDF, y pra
    cima). region_bbox (x0, y0, x1, y1) filtra pela view principal.

    Retorna [{"text", "value_m", "center": (x, y), "bbox"}]. PDF sem texto
    extraível (cota plotada como curva) devolve [] — honesto, sem chute.

    📏 28/09/2026 (estudo de leitura, D7c): o pypdfium2 dá a posição no
    espaço BRUTO da página; paredes e salas vêm no espaço do pdfminer, que
    desconta a origem da MediaBox e aplica a rotação (`_initial_ctm`). Em PDF
    de CAD com a folha centrada na origem (a62f7ae3: MediaBox em −1417, −650)
    nenhuma cota caía perto de parede nenhuma: 0 casamentos em qualquer
    escala. O recorte da vista (`region_bbox`, que vem do /BBox da viewport,
    também bruto) continua no espaço bruto; depois dele, a cota vai pro
    espaço da geometria pela MESMA transformação. Página com origem em (0, 0)
    e sem rotação — quase todas — não muda.
    """
    import pypdfium2 as pdfium
    from pdfvec_walls import _initial_ctm

    tokens: list[dict] = []
    doc = pdfium.PdfDocument(pdf_path)
    try:
        if page_index >= len(doc):
            return []
        page = doc[page_index]
        try:
            ca, cb, cc, cd, ce, cf = _initial_ctm(page.get_mediabox(), page.get_rotation())
        except Exception:
            ca, cb, cc, cd, ce, cf = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0

        def _geo(x, y):
            return (ca * x + cc * y + ce, cb * x + cd * y + cf)

        tp = page.get_textpage()
        try:
            n_rects = tp.count_rects(0, -1)
            for i in range(min(n_rects, MAX_RECTS)):
                l, b, r, t = tp.get_rect(i)
                try:
                    txt = tp.get_text_bounded(l, b, r, t)
                except Exception:
                    continue
                for tok in _split_rect_tokens(txt, l, b, r, t):
                    val = parse_cota_value(tok["text"])
                    if val is None:
                        continue
                    cx, cy = tok["center"]
                    if region_bbox is not None:
                        x0, y0, x1, y1 = region_bbox
                        if not (x0 <= cx <= x1 and y0 <= cy <= y1):
                            continue
                    tok["center"] = _geo(cx, cy)
                    (qx0, qy0), (qx1, qy1) = _geo(l, b), _geo(r, t)
                    tok["bbox"] = (min(qx0, qx1), min(qy0, qy1), max(qx0, qx1), max(qy0, qy1))
                    tok["value_m"] = val
                    tokens.append(tok)
                    if len(tokens) >= MAX_TOKENS:
                        return tokens
        finally:
            tp.close()
    finally:
        doc.close()
    return tokens


# ───────────────────── casamento cota × elemento (puro) ─────────────────────

def _elements_from_walls(walls: Optional[Sequence[dict]]) -> list[dict]:
    """Paredes de detect_walls -> elementos casáveis (precisam dos campos de
    posição axis/span_pt/p_pt que o detect_walls novo exporta)."""
    out: list[dict] = []
    for w in walls or []:
        try:
            a0, a1 = w["span_pt"]
            out.append({"kind": "parede", "length_m": float(w["length_m"]),
                        "axis": w["axis"], "span_pt": (float(a0), float(a1)),
                        "p_pt": float(w["p_pt"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _elements_from_rooms(rooms: Optional[Sequence[dict]],
                         m_per_pt: float) -> list[dict]:
    """Salas de detect_rooms -> 4 arestas do bbox como elementos casáveis.
    Cota de ambiente costuma medir exatamente o vão interno (largura/fundo).

    📏 28/09/2026 (estudo de leitura, D7a): as duas arestas paralelas da sala
    têm o MESMO comprimento — é uma medida só. A mesma cota escrita dos dois
    lados ("2.15" em cima e embaixo da sala de 2,178) contava como 2 provas
    independentes da escala. `grupo` = (sala, eixo): `match_cotas` aceita um
    casamento por grupo."""
    out: list[dict] = []
    for ri, room in enumerate(rooms or []):
        try:
            x0, y0, x1, y1 = room["bbox"]
        except (KeyError, TypeError, ValueError):
            continue
        wx, hy = float(x1) - float(x0), float(y1) - float(y0)
        for axis, span, p, ln_pt in (
            ("h", (x0, x1), y0, wx),   # aresta de baixo
            ("h", (x0, x1), y1, wx),   # aresta de cima
            ("v", (y0, y1), x0, hy),   # aresta esquerda
            ("v", (y0, y1), x1, hy),   # aresta direita
        ):
            if ln_pt <= 0:
                continue
            out.append({"kind": "sala", "length_m": ln_pt * m_per_pt,
                        "axis": axis,
                        "span_pt": (float(span[0]), float(span[1])),
                        "p_pt": float(p), "grupo": ("sala", ri, axis)})
    return out


def match_cotas(tokens: Sequence[dict], elements: Sequence[dict],
                tol_rel: float = TOL_REL) -> list[dict]:
    """Casa tokens de cota com elementos medidos. PURO (testável sem PDF).

    tokens:   [{"value_m", "center": (x, y), ...}]
    elements: [{"length_m", "axis" 'h'|'v', "span_pt": (a0, a1), "p_pt"}]

    Critérios: valor bate em ±tol_rel; centro do token dentro do vão axial do
    elemento (folga AXIAL_MARGIN_FRAC) e a distância perpendicular <=
    clamp(PROX_FRAC * comprimento_pt, PROX_MIN_PT, PROX_MAX_PT).
    Pareamento guloso 1-pra-1 por menor erro relativo: cada token valida no
    máximo UM elemento (e vice-versa) — independência de verdade. Elementos
    com o mesmo `grupo` (as duas arestas paralelas de uma sala) são UMA
    medida: casam uma vez só.
    """
    cands: list[tuple[float, int, int]] = []
    for ei, el in enumerate(elements):
        length = float(el.get("length_m") or 0.0)
        if length < MIN_ELEM_M:
            continue
        a0, a1 = el["span_pt"]
        if a1 < a0:
            a0, a1 = a1, a0
        elen_pt = a1 - a0
        if elen_pt <= 0:
            continue
        perp_tol = min(max(PROX_FRAC * elen_pt, PROX_MIN_PT), PROX_MAX_PT)
        margin = AXIAL_MARGIN_FRAC * elen_pt
        p = float(el["p_pt"])
        horizontal = el.get("axis") == "h"
        for ti, tk in enumerate(tokens):
            val = tk.get("value_m")
            if not val:
                continue
            err = abs(val - length)
            if err > tol_rel * length:
                continue
            cx, cy = tk["center"]
            axial, perp = (cx, cy) if horizontal else (cy, cx)
            if not (a0 - margin <= axial <= a1 + margin):
                continue
            if abs(perp - p) > perp_tol:
                continue
            cands.append((err / max(length, 1e-9), ti, ei))

    cands.sort()
    used_t: set[int] = set()
    used_e: set[int] = set()
    used_g: set = set()
    matches: list[dict] = []
    for rel_err, ti, ei in cands:
        if ti in used_t or ei in used_e:
            continue
        g = elements[ei].get("grupo")
        if g is not None and g in used_g:
            continue                    # a outra aresta da mesma medida
        used_t.add(ti)
        used_e.add(ei)
        if g is not None:
            used_g.add(g)
        el = elements[ei]
        matches.append({
            "cota": tokens[ti].get("text"),
            "valor_m": round(float(tokens[ti]["value_m"]), 3),
            "medido_m": round(float(el["length_m"]), 3),
            "erro_rel": round(rel_err, 4),
            "elemento": el.get("kind", "?"),
        })
    return matches


# ─────────────────────────────── API pública ───────────────────────────────

def validate_scale(pdf_path: str, page_index: int, scale_denominator: float,
                   region_bbox: Optional[Sequence[float]] = None,
                   walls: Optional[Sequence[dict]] = None,
                   rooms: Optional[Sequence[dict]] = None) -> dict:
    """Valida a escala da view principal cruzando cotas escritas × medido.

    Retorna:
      n_cotas   : tokens com cara de cota DENTRO da view principal
      n_matches : pares independentes cota×elemento batendo em ±2%
      segunda   : [escala, casamentos] da melhor OUTRA escala padrão, ou None
      dominante : n_matches >= 2 E >= DOMINANCIA × a segunda — SÓ SOMBRA
      validada  : n_matches >= 2 (a régua de sempre)
      exemplos  : até 5 pares (transparência no log)

    📏 28/09/2026 (estudo de leitura, D7b): ">= 2 casamentos" sozinho não
    separa a escala certa da errada. Na a3366fbb_11 (certa 1:100, 15
    casamentos) as erradas juntavam 2 a 4 por coincidência. A declarada é
    comparada com as escalas padrão, contando nos MESMOS elementos medidos
    (comprimentos reescalados, sem detectar de novo) — ~0,4 s na prancha mais
    pesada do acervo, e só quando já há >= 2 casamentos.
    🪤 EM SOMBRA, não decide: nas 38 páginas locais, pela leitura da produção,
    a dominância não pegou escala errada nenhuma e DERRUBOU uma certa — a
    a3366fbb_10 (1:100 com três fontes concordando) casa 2 a 1:100 e 5 a
    1:150 nos elementos reescalados. Com poucos casamentos a comparação nos
    mesmos elementos é frágil. O log grava a segunda pra calibrar com
    produção antes de ligar.

    NÃO promove nada — evidência pra outra etapa decidir.
    """
    tokens = extract_cota_tokens(pdf_path, page_index, region_bbox)
    den = float(scale_denominator)
    m_per_pt = PT_TO_M * den
    paredes = _elements_from_walls(walls)
    elements = (paredes + _elements_from_rooms(rooms, m_per_pt))[:MAX_ELEMS]
    matches = match_cotas(tokens, elements) if tokens and elements else []
    segunda = None
    if len(matches) >= 2:
        for esc in ESCALAS_PADRAO:
            if abs(esc - den) <= TOL_ESCALA_REL * den:
                continue                    # é a própria declarada
            f = esc / den
            alt = ([dict(e, length_m=e["length_m"] * f) for e in paredes]
                   + _elements_from_rooms(rooms, PT_TO_M * esc))[:MAX_ELEMS]
            n_alt = len(match_cotas(tokens, alt))
            if n_alt and (segunda is None or n_alt > segunda[1]):
                segunda = [esc, n_alt]
    n = len(matches)
    return {
        "n_cotas": len(tokens),
        "n_matches": n,
        "segunda": segunda,
        "dominante": n >= 2 and n >= DOMINANCIA * (segunda[1] if segunda else 0),
        "validada": n >= 2,
        "exemplos": matches[:5],
    }


def derive_scale_from_cotas(pdf_path: str, page_index: int = 0,
                            region_bbox: Optional[Sequence[float]] = None,
                            walls: Optional[Sequence[dict]] = None,
                            rooms_pt: Optional[Sequence[dict]] = None) -> dict:
    """DESCOBRE a escala a partir das cotas escritas. Não valida — deriva.

    Por que existe (medido em 01/08/2026 nas 30 pranchas da sombra):
    47% das pranchas eram puladas com "sem escala (viewport nem carimbo)" —
    a escala só podia vir dessas duas fontes. Mas a cota está desenhada ali:
    uma prancha trazia 122 cotas e mesmo assim foi descartada.

    A ideia: para cada par (cota, elemento próximo), a escala IMPLÍCITA é
    `valor_escrito / comprimento_em_pontos`. Não é preciso saber a qual
    elemento a cota se refere — pares errados espalham valores aleatórios,
    pares certos se acumulam todos no mesmo lugar. A escala verdadeira é a
    moda. É votação, não pareamento.

    Isso contorna o problema que trava o `match_cotas`: cota brasileira vem
    em CADEIA ("1,20 | 0,80 | 2,40"), medindo trechos entre linhas de chamada
    e não paredes inteiras — por isso 415 cotas produziram só 22 pares. Aqui
    a cadeia não atrapalha: basta que alguns pares caiam na escala certa.

    Retorna {"scale", "votos", "total_pares", "confianca", "candidatas"} ou
    {"scale": None, ...} quando não há acordo suficiente.
    """
    tokens = extract_cota_tokens(pdf_path, page_index, region_bbox)
    if not tokens:
        return {"scale": None, "motivo": "nenhuma cota lida"}

    # Elementos em PONTOS (não em metros — a escala é justamente a incógnita).
    elems: list[dict] = []
    for w in walls or []:
        try:
            a0, a1 = w["span_pt"]
            ln = abs(float(a1) - float(a0))
            if ln > 0:
                elems.append({"len_pt": ln, "axis": w["axis"],
                              "span_pt": (float(min(a0, a1)), float(max(a0, a1))),
                              "p_pt": float(w["p_pt"])})
        except (KeyError, TypeError, ValueError):
            continue
    for room in rooms_pt or []:
        try:
            x0, y0, x1, y1 = room["bbox"]
        except (KeyError, TypeError, ValueError):
            continue
        wx, hy = abs(float(x1) - float(x0)), abs(float(y1) - float(y0))
        for axis, span, p, ln in (("h", (x0, x1), y0, wx), ("h", (x0, x1), y1, wx),
                                  ("v", (y0, y1), x0, hy), ("v", (y0, y1), x1, hy)):
            if ln > 0:
                elems.append({"len_pt": ln, "axis": axis,
                              "span_pt": (float(min(span)), float(max(span))),
                              "p_pt": float(p)})
    elems = elems[:MAX_ELEMS]
    if not elems:
        return {"scale": None, "motivo": "nenhum elemento medível"}

    votos: dict[float, int] = {}
    # 🔬 07/09/2026 — SONDAGEM, NÃO DECISÃO. Nada aqui muda o resultado da
    # função: `votos` continua sendo o único que decide. Estes três só CONTAM,
    # pra o log dizer o que a gente hoje não sabe.
    #
    # 🩸 Por quê: esta função subiu em 01/08 e NUNCA produziu uma escala em
    # produção — 0 de 128 promoções (`pdfvec:promo`), 5 semanas, 143 jobs.
    # E o motivo mais provável, achado em 07/09 na prancha FORRO: o voto é
    # contado POR TOKEN, e o `break` elege o PRIMEIRO vão que casa. Quatro
    # cotas com o mesmo texto "80" casando o mesmo vão viram 4 "votos
    # independentes" — e derivaram 1:50 numa região que o PDF declara 1:100
    # (erro de 2× linear, 4× em ÁREA). A resposta certa estava na lista de
    # vãos, mais adiante, e o `break` nunca chegou nela.
    #
    # 🚨 O conserto NÃO entra hoje. Afrouxar ou mexer na régua sem medir anda
    # na direção do erro de 4×, e a regra dura nº1 diz que número errado com
    # cara de medido é muito pior que linha vazia. Primeiro estes números
    # aparecem no log das pranchas REAIS que morrem; depois a gente decide.
    votos_por_valor: dict[float, set] = {}   # escala -> {valores distintos que votaram}
    votos_por_par: dict[float, set] = {}     # escala -> {(valor, vão) distintos}
    _corte_eixo: dict[str, float] = {}       # eixo -> % do eixo descartada
    pares = 0
    for el in elems:
        ln_pt = el["len_pt"]
        perp_tol = min(max(PROX_FRAC * ln_pt, PROX_MIN_PT), PROX_MAX_PT)
        margin = AXIAL_MARGIN_FRAC * ln_pt
        a0, a1 = el["span_pt"]
        horizontal = el["axis"] == "h"
        for tk in tokens:
            val = tk.get("value_m")
            if not val:
                continue
            cx, cy = tk["center"]
            axial, perp = (cx, cy) if horizontal else (cy, cx)
            if not (a0 - margin <= axial <= a1 + margin):
                continue
            if abs(perp - el["p_pt"]) > perp_tol:
                continue
            pares += 1
            implicita = val / (ln_pt * PT_TO_M)      # denominador da escala
            for padrao in ESCALAS_PADRAO:
                if abs(implicita - padrao) <= TOL_ESCALA_REL * padrao:
                    votos[padrao] = votos.get(padrao, 0) + 1
                    votos_por_valor.setdefault(padrao, set()).add(round(val, 3))
                    votos_por_par.setdefault(padrao, set()).add(
                        (round(val, 3), round(ln_pt, 1)))
                    break

    # 2ª fonte de votos: CADEIA DE COTAS. Cota parcial não mede elemento
    # inteiro — mede o vão entre duas linhas de chamada, e essas linhas caem
    # sobre as PONTAS dos elementos (onde a parede é interrompida por porta,
    # janela ou encontro). Então o candidato certo é a distância entre dois
    # extremos vizinhos, não o comprimento de um elemento.
    # Sem isto, prancha muito cotada casa zero: a de 122 cotas casou 0 pares.
    for eixo in ("h", "v"):
        pontas = sorted({p for el in elems if el["axis"] == eixo
                         for p in el["span_pt"]})
        if len(pontas) < 3:
            continue
        # 🔬 SONDAGEM (07/09): quanto do EIXO este corte joga fora.
        # 🩸 `pontas` está ORDENADO POR COORDENADA, então `[:MAX_PONTAS]` não é
        # amostra — é recorte espacial: guarda os N pontos mais à esquerda/baixo
        # e descarta o resto da folha. Medido nos PDFs locais: prancha A0 perde
        # 39,8% da largura (596 pontas), A1 de arquitetura perde 38,1% (505).
        # E as COTAS não são cortadas: as do lado descartado seguem sendo
        # pareadas contra vãos calculados só na outra metade — pareamento
        # errado espalha voto, que é a assinatura do empate. Só CONTA por ora.
        if len(pontas) > MAX_PONTAS and pontas[-1] > pontas[0]:
            _faixa = pontas[-1] - pontas[0]
            _usada = pontas[MAX_PONTAS - 1] - pontas[0]
            _corte_eixo[eixo] = round(100.0 * (1 - _usada / _faixa), 1)
        pontas = pontas[:MAX_PONTAS]
        vaos: list[float] = []
        for i in range(len(pontas) - 1):
            # vãos entre pontas vizinhas e entre saltos de até 3 pontas —
            # cobre cota parcial e cota que agrupa dois trechos
            for j in range(i + 1, min(i + 4, len(pontas))):
                d = pontas[j] - pontas[i]
                if d > 0:
                    vaos.append(d)
        for tk in tokens:
            val = tk.get("value_m")
            if not val:
                continue
            for d_pt in vaos:
                implicita = val / (d_pt * PT_TO_M)
                for padrao in ESCALAS_PADRAO:
                    if abs(implicita - padrao) <= TOL_ESCALA_REL * padrao:
                        votos[padrao] = votos.get(padrao, 0) + 1
                        votos_por_valor.setdefault(padrao, set()).add(round(val, 3))
                        votos_por_par.setdefault(padrao, set()).add(
                            (round(val, 3), round(d_pt, 1)))
                        pares += 1
                        break
                else:
                    continue
                break   # um voto por cota por eixo, pra cadeia não inflar

    if not votos:
        return {"scale": None, "motivo": "nenhum par caiu em escala padrão",
                "total_pares": pares, "n_cotas": len(tokens)}

    ranking = sorted(votos.items(), key=lambda kv: -kv[1])
    melhor, n_melhor = ranking[0]
    segundo = ranking[1][1] if len(ranking) > 1 else 0
    # Só aceita com apoio real E dominância clara sobre a 2ª colocada:
    # escala errada não junta votos, espalha.
    # 🪤 07/09/2026 — MEDIDO: esta trava é INERTE justamente onde importa. Com
    # `segundo` em {0, 1, 2} o `max(segundo, 1)` faz a 2ª cláusula exigir
    # `n >= 2`, MENOR que o MIN_VOTOS de 4 — ou seja, ela nunca é a restrição
    # ativa em página esparsa, e a `confianca` reporta 1,00 exatamente porque
    # ninguém mais votou. Não mexo hoje: a função nunca produziu escala em
    # produção (0 de 128 promoções), então hoje ela não erra — só não acerta.
    # Mudar sem os números das pranchas REAIS anda pro lado do erro de 4×.
    ok = n_melhor >= MIN_VOTOS_ESCALA and n_melhor >= DOMINANCIA * max(segundo, 1)
    # 🔬 SONDAGEM — nada abaixo entra na decisão; só sai no log pra responder,
    # nas pranchas de produção que morrem sem escala, as perguntas que hoje a
    # gente não sabe responder:
    #   · o voto por VALOR DISTINTO (ou por par valor×vão) desempataria?
    #   · quantos valores diferentes de cota a prancha realmente tem?
    #   · o corte do MAX_PONTAS jogou fora parte da folha, e quanto?
    _rk_valor = sorted(((k, len(v)) for k, v in votos_por_valor.items()),
                       key=lambda kv: -kv[1])
    _rk_par = sorted(((k, len(v)) for k, v in votos_por_par.items()),
                     key=lambda kv: -kv[1])
    return {
        "scale": float(melhor) if ok else None,
        "votos": n_melhor,
        "segundo_lugar": segundo,
        "total_pares": pares,
        "n_cotas": len(tokens),
        "confianca": round(n_melhor / max(sum(votos.values()), 1), 2),
        "candidatas": [{"escala": k, "votos": v} for k, v in ranking[:4]],
        # ── sondagem ──
        "valores_distintos": len({round(t["value_m"], 3) for t in tokens
                                  if t.get("value_m")}),
        "por_valor": [{"escala": k, "n": v} for k, v in _rk_valor[:3]],
        "por_par": [{"escala": k, "n": v} for k, v in _rk_par[:3]],
        "corte_eixo_pct": _corte_eixo or None,
    }


# ──────────────── o juiz: cota × a PRÓPRIA linha de cota (H87) ────────────────
#
# 🩸 02/10/2026 — estudo do acervo (H87). Uma planta de casa em 1:40 (a própria
# folha escreve "1:40" numa das pranchas) saiu "escala 1:50 PROVADA por 3
# cota(s)" e "por 4 cota(s)": o `validate_scale` aceita 2 pares cota × parede a
# ±2 %, e com ~180 cotas e centenas de paredes a coincidência passa. Na mesma
# folha, cada cota medida contra a LINHA DE COTA que ela mede dá 1:40 em ~100
# valores distintos (e a cama de casal mede 1,65 × 1,93 m em 1:40; 2,06 × 2,41
# em 1:50).
# 📏 Mínimo de pares não separa: das 37 provas verdadeiras do acervo, 12 têm 2 a
# 4 pares (4 delas só 2) — subir o mínimo pra 5 derrubaria essas 12.
# 🔑 Então o juiz só DESMENTE: a prova cai quando, na MESMA região da
# validação, as linhas de cota sustentam com folga OUTRA escala. A escala não
# muda e nada é promovido — a prova vira declaração.
JUIZ_DIST_PT: float = 12.0        # o texto da cota fica a até isto da linha dela
JUIZ_FAMILIA_REL: float = 0.02    # valores a 2 % um do outro são a mesma cota
JUIZ_JANELA_REL: float = 0.03     # um grupo de escala implícita tem ±3 %
JUIZ_MIN_FAMILIAS: int = 10       # grupo forte: ≥ 10 famílias de valor…
JUIZ_MIN_AMPLITUDE: float = 3.0   # …e o maior valor ≥ 3× o menor
JUIZ_OUTRA_ESCALA: float = 0.15   # o grupo forte é OUTRA escala se a > 15 %
JUIZ_APOIO_REL: float = 0.10      # apoio da escala provada: pares a ±10 %
JUIZ_PROPORCAO: float = 3.0       # desmente se o grupo tem > 3× o apoio dela
JUIZ_MAX_PARES: int = 8000        # teto de pares (custo da varredura)


def pares_cota_linha(tokens: Sequence[dict], segs: Sequence) -> list[tuple[float, float]]:
    """(escala implícita, valor em m) de cada cota × traço reto paralelo a ela
    que passa SOB o centro do texto (a até JUIZ_DIST_PT).

    `tokens` = `extract_cota_tokens`; `segs` = a coleta crua da página
    (`[((x0, y0), (x1, y1)), ...]`, mesmo espaço). Texto mais largo que alto
    procura traço horizontal; mais alto que largo, vertical. Puro.
    """
    hor: dict[int, list] = {}
    ver: dict[int, list] = {}
    for (x0, y0), (x1, y1) in segs:
        if abs(y1 - y0) < 0.5 and abs(x1 - x0) > 2:
            y = (y0 + y1) / 2
            hor.setdefault(int(y // JUIZ_DIST_PT), []).append((min(x0, x1), max(x0, x1), y))
        elif abs(x1 - x0) < 0.5 and abs(y1 - y0) > 2:
            x = (x0 + x1) / 2
            ver.setdefault(int(x // JUIZ_DIST_PT), []).append((min(y0, y1), max(y0, y1), x))
    pares: list[tuple[float, float]] = []
    for t in tokens:
        val = t.get("value_m")
        if not val or val <= 0:
            continue
        bx0, by0, bx1, by1 = t["bbox"]
        cx, cy = t["center"]
        deitado = (bx1 - bx0) >= (by1 - by0)
        ao_longo, perp, idx = (cx, cy, hor) if deitado else (cy, cx, ver)
        k = int(perp // JUIZ_DIST_PT)
        for kk in (k - 1, k, k + 1):
            for a, b, c in idx.get(kk, ()):
                if a <= ao_longo <= b and abs(c - perp) <= JUIZ_DIST_PT:
                    pares.append((val / ((b - a) * PT_TO_M), val))
                    if len(pares) >= JUIZ_MAX_PARES:
                        return pares
    return pares


def _familias(valores) -> int:
    """Quantas cotas DIFERENTES: valores a JUIZ_FAMILIA_REL do 1º da família
    contam uma vez (os níveis "750,80 / 750,65 / 750,35" são uma só)."""
    n, ini = 0, None
    for v in sorted(valores):
        if ini is None or v > ini * (1 + JUIZ_FAMILIA_REL):
            n, ini = n + 1, v
    return n


def juiz_desmente(pares: Sequence[tuple[float, float]], den: float) -> Optional[dict]:
    """O grupo de escala que desmente a prova de `den`, ou None se ela fica.

    Desmente só com as três: (1) há um grupo de escala implícita com ≥
    JUIZ_MIN_FAMILIAS famílias de valor e amplitude ≥ JUIZ_MIN_AMPLITUDE;
    (2) ele está a mais de JUIZ_OUTRA_ESCALA de `den`; (3) o apoio de `den`
    (famílias a ±JUIZ_APOIO_REL) × JUIZ_PROPORCAO fica abaixo dele. Puro.
    """
    if not pares or not den or den <= 0:
        return None
    ps = sorted(pares)
    melhor = None                                   # (famílias, amplitude, escala)
    j = 0
    for i, (s, _) in enumerate(ps):
        if j < i:
            j = i
        while j < len(ps) and ps[j][0] <= s * (1 + 2 * JUIZ_JANELA_REL):
            j += 1
        if melhor and j - i <= melhor[0]:
            continue                                # não tem pares pra ganhar
        vals = [v for _, v in ps[i:j]]
        fam = _familias(vals)
        if melhor is None or fam > melhor[0]:
            melhor = (fam, max(vals) / min(vals), ps[(i + j - 1) // 2][0])
    if not melhor:
        return None
    fam, amp, esc = melhor
    if fam < JUIZ_MIN_FAMILIAS or amp < JUIZ_MIN_AMPLITUDE:
        return None
    if abs(esc - den) / den <= JUIZ_OUTRA_ESCALA:
        return None
    apoio = _familias([v for s, v in ps if abs(s - den) / den <= JUIZ_APOIO_REL])
    if apoio * JUIZ_PROPORCAO >= fam:
        return None
    return {"escala": round(esc, 1), "familias": fam, "amplitude": round(amp, 1), "apoio": apoio}


def prova_desmentida_pela_linha_de_cota(pdf_path: str, page_index: int, scale_denominator: float,
                                        region_bbox: Optional[Sequence[float]], segs: Sequence) -> Optional[dict]:
    """O juiz na MESMA região da validação (`region_bbox`, como o
    `validate_scale`): numa folha com implantação 1:200 e planta 1:75, as cotas
    da implantação não podem derrubar a prova da planta."""
    tokens = extract_cota_tokens(pdf_path, page_index, region_bbox)
    return juiz_desmente(pares_cota_linha(tokens, segs), float(scale_denominator))


# ─────────────────────────── auto-teste no corpus ───────────────────────────

if __name__ == "__main__":
    import json
    import sys as _sys

    _sys.path.insert(0, r"C:\Users\admin\Desktop\arq\projeto_arq\backend")
    from pdfvec_layers import scale_from_viewport

    paths = _sys.argv[1:] or [
        r"C:\Users\admin\Desktop\arq\arq\_cad_teste\225.AFS.201.LAYOUT- C. COTA_EX-A2.pdf",
        r"C:\Users\admin\Desktop\arq\arq\_cad_teste\0326.CGR.14.500.PONTOS-A1.pdf",
    ]
    for path in paths:
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        vp = scale_from_viewport(path, 0)
        den = vp.get("main_scale")
        if not den:
            print(f"{name}: sem escala de viewport — pulando")
            continue
        toks = extract_cota_tokens(path, 0, vp.get("main_bbox"))
        print(f"{name}: 1:{den} | {len(toks)} tokens-cota | "
              f"{json.dumps([t['text'] for t in toks[:12]], ensure_ascii=False)}")
