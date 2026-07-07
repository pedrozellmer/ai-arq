# -*- coding: utf-8 -*-
"""Extração de geometria de PDF POR LAYER do CAD (Optional Content Groups).

Descoberta 07/07: PDF exportado de CAD preserva os layers como OCG, e o
content stream marca cada objeto com /OC /BDC ... EMC. Rastreando a matriz de
transformação (q/Q/cm) + a pilha de OC, dá pra extrair a geometria de cada
layer em coordenadas reais de página. Isso separa parede (ARQ-ALV) de
mobiliário de texto, e permite CONTAR símbolos (IND-*, LUM-*) — impossível na
"sopa de linhas" indiferenciada.

Só pikepdf (MPL-2.0, já instalável) — NÃO PyMuPDF (AGPL, contamina licença).
"""
from __future__ import annotations

import re
from collections import defaultdict

import pikepdf
from pikepdf import parse_content_stream

# xref vira prefixo "0326.CGR.14.xref.06|ARQ-ALV" — normaliza pro nome do layer.
_XREF_RE = re.compile(r"^.*\|")


def _norm_layer(name: str) -> str:
    return _XREF_RE.sub("", str(name or "")).strip().upper()


def _compose(a, b):
    """Matriz afim A seguida de B (ponto-linha [x y 1] · M). 6-tupla (a,b,c,d,e,f)."""
    a1, b1, c1, d1, e1, f1 = a
    a2, b2, c2, d2, e2, f2 = b
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def _apply(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def extract_layers(pdf_path: str, page_index: int = 0) -> dict[str, list]:
    """Devolve {LAYER_NORMALIZADO: [segmentos]} em pontos de página (y-up).
    Segmento = ((x0,y0),(x1,y1)). Beziers reduzidos a corda; retângulos a 4 lados.
    Ignora XObjects (blocos/xrefs) nesta v1 — a geometria principal (paredes,
    pontos) está no stream da página."""
    pdf = pikepdf.open(pdf_path)
    page = pdf.pages[page_index]

    # mapa nome-local -> nome do OCG (via Resources/Properties)
    props = {}
    try:
        for k, v in dict(page.Resources.Properties).items():
            try:
                props[str(k)] = str(v.Name)
            except Exception:
                props[str(k)] = None
    except Exception:
        pass

    out: dict[str, list] = defaultdict(list)
    ctm = _IDENTITY
    ctm_stack: list = []
    oc_stack: list = []          # pilha de layers (BDC/EMC)
    cur = (0.0, 0.0)             # ponto corrente (raw, pré-CTM)
    start = (0.0, 0.0)

    def num(o):
        try:
            return float(o)
        except Exception:
            return 0.0

    def layer_now():
        for l in reversed(oc_stack):
            if l:
                return l
        return None

    def emit(x0, y0, x1, y1):
        lay = layer_now()
        if not lay:
            return
        p0 = _apply(ctm, x0, y0)
        p1 = _apply(ctm, x1, y1)
        out[lay].append((p0, p1))

    for instr in parse_content_stream(page):
        op = str(instr.operator)
        o = instr.operands
        if op == "q":
            ctm_stack.append(ctm)
        elif op == "Q":
            if ctm_stack:
                ctm = ctm_stack.pop()
        elif op == "cm" and len(o) >= 6:
            m = tuple(num(x) for x in o[:6])
            ctm = _compose(m, ctm)
        elif op == "BDC":
            lay = None
            if len(o) >= 2 and str(o[0]) == "/OC":
                tag = o[1]
                nm = props.get(str(tag)) or props.get(str(tag).lstrip("/"))
                if nm is None:
                    try:
                        nm = str(tag.Name)
                    except Exception:
                        nm = None
                lay = _norm_layer(nm) if nm else None
            oc_stack.append(lay)
        elif op == "BMC":
            oc_stack.append(None)
        elif op == "EMC":
            if oc_stack:
                oc_stack.pop()
        elif op == "m" and len(o) >= 2:
            cur = (num(o[0]), num(o[1]))
            start = cur
        elif op == "l" and len(o) >= 2:
            nxt = (num(o[0]), num(o[1]))
            emit(cur[0], cur[1], nxt[0], nxt[1])
            cur = nxt
        elif op in ("c", "v", "y"):
            # bezier -> corda (endpoint são os 2 últimos operandos)
            if len(o) >= 2:
                nxt = (num(o[-2]), num(o[-1]))
                emit(cur[0], cur[1], nxt[0], nxt[1])
                cur = nxt
        elif op == "re" and len(o) >= 4:
            x, y, w, h = (num(o[0]), num(o[1]), num(o[2]), num(o[3]))
            emit(x, y, x + w, y); emit(x + w, y, x + w, y + h)
            emit(x + w, y + h, x, y + h); emit(x, y + h, x, y)
            cur = (x, y); start = cur
        elif op == "h":
            emit(cur[0], cur[1], start[0], start[1])
            cur = start
    return dict(out)


import math as _math

PT_TO_M = 0.0254 / 72.0

# Layers que são PAREDE (alvenaria/divisória) vs SÍMBOLO contável vs TEXTO (ignorar).
_WALL_HINT = re.compile(r"ALV|PAR(?:ED)?|DIV(?:IS)?", re.I)
_TEXT_HINT = re.compile(r"TXT|TEXT|LEG|DIM|COTA|HACH|ANNO", re.I)
_SYMBOL_HINT = re.compile(r"^IND-|^LUM|^ELE|PTA|PTM|PTF|PTP|INT|TOM|LUMIN|ANTENA|WIFI|ACS", re.I)


def _seg_len_m(segs, mpp):
    return sum(_math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs) * mpp


def count_symbols(segs, mpp, tol=3.0, lo_cm=3.0, hi_cm=40.0):
    """Conta instâncias de símbolo por componentes conexos (endpoints compartilhados).
    Filtra por tamanho real (símbolo elétrico ~5-20cm) pra cortar leader/texto."""
    n = len(segs)
    if not n:
        return 0
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grid = defaultdict(list)

    def key(p):
        return (round(p[0] / tol), round(p[1] / tol))

    for i, (a, b) in enumerate(segs):
        for p in (a, b):
            kx, ky = key(p)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in grid[(kx + dx, ky + dy)]:
                        parent[find(i)] = find(j)
            grid[key(p)].append(i)
    comps = defaultdict(list)
    for i in range(n):
        comps[find(i)].append(i)
    cnt = 0
    for idxs in comps.values():
        xs = []
        ys = []
        for i in idxs:
            for p in segs[i]:
                xs.append(p[0])
                ys.append(p[1])
        d = max(max(xs) - min(xs), max(ys) - min(ys)) * mpp * 100
        if lo_cm <= d <= hi_cm:
            cnt += 1
    return cnt


def summarize_layers(pdf_path: str, page_index: int, scale_denominator: float,
                     region_bbox=None) -> dict:
    """Resumo por layer pra shadow: comprimento de parede (layers ALV/DIV) e
    contagem de símbolos (layers IND-*/LUM-*). region_bbox (x0,y0,x1,y1) filtra
    a view principal. Tudo determinístico, sem IA."""
    mpp = PT_TO_M * float(scale_denominator)
    layers = extract_layers(pdf_path, page_index)

    def in_region(seg):
        if region_bbox is None:
            return True
        (x0, y0, x1, y1) = region_bbox
        mx = (seg[0][0] + seg[1][0]) / 2
        my = (seg[0][1] + seg[1][1]) / 2
        return x0 <= mx <= x1 and y0 <= my <= y1

    walls = {}
    symbols = {}
    sym_inv = {}  # inventário BRUTO (seg count) dos layers de símbolo — sempre confiável
    for lay, segs in layers.items():
        if region_bbox is not None:
            segs = [s for s in segs if in_region(s)]
        if not segs:
            continue
        if _WALL_HINT.search(lay) and not _TEXT_HINT.search(lay):
            walls[lay] = round(_seg_len_m(segs, mpp), 1)
        elif _SYMBOL_HINT.search(lay) and not _TEXT_HINT.search(lay):
            sym_inv[lay] = len(segs)
            c = count_symbols(segs, mpp)
            if c:
                symbols[lay] = c

    wall_stroke = round(sum(walls.values()), 1)
    return {
        "n_layers": len(layers),
        "wall_layers": dict(sorted(walls.items(), key=lambda t: -t[1])[:6]),
        "wall_centerline_m": round(wall_stroke / 2, 1),  # ALV = 2 faces
        "symbols": dict(sorted(symbols.items(), key=lambda t: -t[1])[:10]),
        "symbol_layers": dict(sorted(sym_inv.items(), key=lambda t: -t[1])[:12]),
    }


# ── Escala EXATA embutida no PDF (descoberta 07/07, achado #2 do estudo) ──
# PDF exportado de CAD traz /VP (viewports) com /Measure /X /C = fator de
# conversão real por view. denom = C / (2.54/72). Resolve escala + multi-view
# + "INDICADAS" de forma DETERMINÍSTICA, sem Vision. Só pikepdf.
_CM_PER_PT = 2.54 / 72.0            # 0.0352778 — 1 ponto em escala 1:1
_STD_SCALES = [10, 20, 25, 33, 50, 75, 100, 125, 150, 200, 250, 500, 1000]


def _snap_scale(raw: float):
    """Aproxima pra escala padrão de arquitetura se estiver a ≤5%. C é cm/pt
    (padrão do /RL). NÃO tenta unidades alternativas — isso fazia a folha 1:1
    (raw≈1) casar errado com 1:10. Retorna (denom, snapped_bool) ou None."""
    if raw <= 0:
        return None
    for s in _STD_SCALES:
        if abs(raw - s) / s <= 0.05:
            return s, True
    if 5 <= raw <= 2000:
        return int(round(raw)), False
    return None


def scale_from_viewport(pdf_path: str, page_index: int = 0) -> dict:
    """Lê a escala exata de cada viewport do PDF. Retorna:
      {main_scale, main_bbox, snapped, viewports:[{bbox, scale, snapped}]}.
    main = maior viewport que não é a folha inteira. {} se não houver /VP."""
    try:
        pdf = pikepdf.open(pdf_path)
        page = pdf.pages[page_index]
        vps = page.get("/VP")
        if not vps:
            return {}
        pw = float(page.MediaBox[2]) - float(page.MediaBox[0])
        ph = float(page.MediaBox[3]) - float(page.MediaBox[1])
        page_area = pw * ph
        views = []
        for v in vps:
            try:
                meas = v.get("/Measure")
                bbox = [float(x) for x in v.get("/BBox")]
                c = float(meas.get("/X")[0].get("/C"))
            except Exception:
                continue
            snap = _snap_scale(c / _CM_PER_PT)
            if not snap:
                continue
            denom, snapped = snap
            area = abs(bbox[2] - bbox[0]) * abs(bbox[3] - bbox[1])
            # ignora a viewport da folha inteira (é o quadro do papel, não um
            # desenho) — sempre por ÁREA, nunca pelo denominador.
            if area >= 0.9 * page_area:
                continue
            views.append({"bbox": bbox, "scale": denom, "snapped": snapped, "area": area})
        if not views:
            return {}
        main = max(views, key=lambda x: x["area"])
        for x in views:
            x.pop("area", None)
        return {"main_scale": main["scale"], "main_bbox": main["bbox"],
                "snapped": main["snapped"], "viewports": views}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:100]}
