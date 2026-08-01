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
    """
    import pypdfium2 as pdfium

    tokens: list[dict] = []
    doc = pdfium.PdfDocument(pdf_path)
    try:
        if page_index >= len(doc):
            return []
        page = doc[page_index]
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
    Cota de ambiente costuma medir exatamente o vão interno (largura/fundo)."""
    out: list[dict] = []
    for room in rooms or []:
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
                        "p_pt": float(p)})
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
    máximo UM elemento (e vice-versa) — independência de verdade.
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
    matches: list[dict] = []
    for rel_err, ti, ei in cands:
        if ti in used_t or ei in used_e:
            continue
        used_t.add(ti)
        used_e.add(ei)
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
      validada  : n_matches >= 2 ("escala_validada_por_cota")
      exemplos  : até 5 pares (transparência no log)

    NÃO promove nada — evidência pra outra etapa decidir.
    """
    tokens = extract_cota_tokens(pdf_path, page_index, region_bbox)
    m_per_pt = PT_TO_M * float(scale_denominator)
    elements = _elements_from_walls(walls) + _elements_from_rooms(rooms, m_per_pt)
    elements = elements[:MAX_ELEMS]
    matches = match_cotas(tokens, elements) if tokens and elements else []
    return {
        "n_cotas": len(tokens),
        "n_matches": len(matches),
        "validada": len(matches) >= 2,
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
    ok = n_melhor >= MIN_VOTOS_ESCALA and n_melhor >= DOMINANCIA * max(segundo, 1)
    return {
        "scale": float(melhor) if ok else None,
        "votos": n_melhor,
        "segundo_lugar": segundo,
        "total_pares": pares,
        "n_cotas": len(tokens),
        "confianca": round(n_melhor / max(sum(votos.values()), 1), 2),
        "candidatas": [{"escala": k, "votos": v} for k, v in ranking[:4]],
    }


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
