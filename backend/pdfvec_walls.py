# -*- coding: utf-8 -*-
"""pdfvec_walls — Medição Vetorial de PDF v1: COMPRIMENTO DE PAREDES/DIVISÓRIAS.

Parede em planta baixa = PAR DE LINHAS PARALELAS próximas (as duas faces da
parede), com espessura real entre ~8 e ~30 cm. Este módulo lê a geometria
vetorial do PDF (zero IA/rede) e:

  1. extrai segmentos do content stream — caminho RÁPIDO: tokenizador
     próprio do content stream (regex + get_data() do pdfminer, que já é o
     motor interno do pdfplumber); fallback: page.lines/page.rects do
     pdfplumber (mesmo espaço de coordenadas, só que ~10x mais lento em
     prancha densa);
  2. classifica horizontais/verticais dentro da região útil (exclui a faixa
     do carimbo) e funde colineares quase-encostados (linha de CAD quebrada);
  3. casa cada segmento com um paralelo à distância de espessura de parede
     (bucketing por coordenada perpendicular → nada de O(n²) cego);
  4. deduplica (cada segmento casa no máximo uma vez, guloso por maior
     sobreposição) e suprime hachuras (segmento com partners demais);
  5. converte para metros reais: metros = pontos * PT_TO_M * denominador.

Convenções de eixo: espaço device do pdfminer/pdfplumber para `lines`
(y cresce PARA CIMA). `region_bbox` segue a mesma convenção.

Limitações honestas (v1):
  * Só paredes ortogonais (H/V); diagonais/curvas ficam de fora.
  * Um lado de parede com várias aberturas casa só o maior trecho (par
    guloso 1-pra-1 subconta parede muito recortada).
  * Mobiliário/esquadria desenhado como par de paralelas de 8-30 cm entra
    como falso positivo; hachura densa é suprimida, esparsa não.
  * Prancha de detalhamento (forro/piso/marcenaria) infla o total: grades
    de forro e vistas de mobiliário parecem "paredes" para esta heurística.
  * A escala precisa vir de fora (derivada por cotas em outra etapa).
  * Carimbo assumido na faixa direita (15% da largura) quando region_bbox
    não é dado — em prancha com carimbo em outra borda, ajuste o bbox.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import Any, Iterable, Optional, Sequence

import pdfplumber
from pdfminer.pdftypes import resolve1  # pdfminer é o motor interno do pdfplumber

PT_TO_M: float = 0.0254 / 72.0  # metros por ponto PDF em escala 1:1

# Segmento cru: (x0, y0, x1, y1) em pontos, espaço device (y para cima).
RawSeg = tuple[float, float, float, float]
# Segmento em eixo: (a0, a1, p) — intervalo [a0, a1] ao longo do eixo,
# p = coordenada perpendicular (y para horizontais, x para verticais).
AxisSeg = tuple[float, float, float]

_TOKEN_RE = re.compile(
    rb"""
      <<|>>                          # delimitadores de dicionario
    | \((?:\\.|[^\\()])*\)           # string literal (com escapes)
    | <[0-9A-Fa-f\s]*>               # string hex
    | /[^\s/<>()\[\]{}%]*            # nome
    | [-+]?(?:\d+\.\d*|\.\d+|\d+)    # numero
    | [A-Za-z'"*]{1,4}               # operador
    | \[|\]
    """,
    re.X,
)
_INLINE_IMG_RE = re.compile(rb"(?<![A-Za-z0-9])BI(?![A-Za-z0-9])")
# imagem inline inteira (BI ... ID <binario> EI); cap de tamanho por seguranca
_INLINE_IMG_SPAN_RE = re.compile(
    rb"(?<![A-Za-z0-9])BI(?![A-Za-z0-9]).{0,4000}?(?<![A-Za-z0-9])EI(?![A-Za-z0-9])",
    re.S,
)
_PAINT_OPS = frozenset((b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"))
_CLOSE_PAINT_OPS = frozenset((b"s", b"b", b"b*"))
_MAX_FORM_DEPTH = 8


# ───────────────────────── extração de segmentos ─────────────────────────

def _initial_ctm(mediabox: Sequence[float], rotate: int) -> tuple[float, ...]:
    """Replica o CTM inicial do pdfminer (espaço device = o do pdfplumber)."""
    x0, y0, x1, y1 = (float(v) for v in mediabox)
    rotate = int(rotate or 0) % 360
    if rotate == 90:
        return (0.0, -1.0, 1.0, 0.0, -y0, x1)
    if rotate == 180:
        return (-1.0, 0.0, 0.0, -1.0, x1, y1)
    if rotate == 270:
        return (0.0, 1.0, -1.0, 0.0, y1, -x0)
    return (1.0, 0.0, 0.0, 1.0, -x0, -y0)


def _pdf_name(token: bytes) -> str:
    """Decodifica /Nome (com escapes #xx) para str."""
    body = token[1:]
    if b"#" in body:
        body = re.sub(rb"#([0-9A-Fa-f]{2})",
                      lambda m: bytes([int(m.group(1), 16)]), body)
    return body.decode("latin-1")


def _fast_stream_segments(
    data: bytes,
    ctm0: tuple[float, ...],
    xobjects: Optional[dict] = None,
    depth: int = 0,
    form_cache: Optional[dict[int, list[RawSeg]]] = None,
) -> list[RawSeg]:
    """Interpreta só o necessário do content stream: caminhos m/l/h/re + CTM.

    Curvas (c/v/y) só movem o ponto corrente (não viram parede). O caminho
    corrente é emitido nos operadores de pintura e descartado no `n` (clip).
    Form XObjects (blocos de CAD) são parseados UMA vez em espaço local
    (cache) e re-transformados a cada invocação `Do`. Imagens inline BI..EI
    são removidas antes da tokenização. ~10-50x mais rápido que montar os
    objetos de layout do pdfminer.
    """
    if form_cache is None:
        form_cache = {}
    if _INLINE_IMG_RE.search(data):
        data = _INLINE_IMG_SPAN_RE.sub(b" ", data)
        if _INLINE_IMG_RE.search(data):  # imagem inline maior que o cap
            raise ValueError("imagem inline grande demais para o caminho rapido")

    segs: list[RawSeg] = []
    stack: list[float] = []
    gstack: list[tuple[float, ...]] = []
    a, b, c, d, e, f = ctm0
    path: list[RawSeg] = []
    cur: Optional[tuple[float, float]] = None
    start: Optional[tuple[float, float]] = None
    last_name: Optional[str] = None

    for mt in _TOKEN_RE.finditer(data):
        t = mt.group()
        ch = t[0]
        if 48 <= ch <= 57 or ch in (43, 45, 46):  # número
            try:
                stack.append(float(t))
            except ValueError:
                stack.clear()
            continue
        if ch == 47:  # /Nome
            last_name = _pdf_name(t)
            stack.clear()
            continue
        if t == b"l":
            if cur is not None and len(stack) >= 2:
                x, y = stack[-2], stack[-1]
                p = (a * x + c * y + e, b * x + d * y + f)
                path.append((cur[0], cur[1], p[0], p[1]))
                cur = p
        elif t == b"m":
            if len(stack) >= 2:
                x, y = stack[-2], stack[-1]
                cur = (a * x + c * y + e, b * x + d * y + f)
                start = cur
        elif t == b"c":
            if cur is not None and len(stack) >= 6:
                x, y = stack[-2], stack[-1]
                cur = (a * x + c * y + e, b * x + d * y + f)
        elif t in (b"v", b"y"):
            if cur is not None and len(stack) >= 4:
                x, y = stack[-2], stack[-1]
                cur = (a * x + c * y + e, b * x + d * y + f)
        elif t == b"h":
            if cur is not None and start is not None:
                path.append((cur[0], cur[1], start[0], start[1]))
                cur = start
        elif t == b"re":
            if len(stack) >= 4:
                x, y, w, h = stack[-4:]
                p0 = (a * x + c * y + e, b * x + d * y + f)
                p1 = (a * (x + w) + c * y + e, b * (x + w) + d * y + f)
                p2 = (a * (x + w) + c * (y + h) + e, b * (x + w) + d * (y + h) + f)
                p3 = (a * x + c * (y + h) + e, b * x + d * (y + h) + f)
                path.extend((
                    (p0[0], p0[1], p1[0], p1[1]),
                    (p1[0], p1[1], p2[0], p2[1]),
                    (p2[0], p2[1], p3[0], p3[1]),
                    (p3[0], p3[1], p0[0], p0[1]),
                ))
                cur = start = p0
        elif t in _PAINT_OPS:
            if t in _CLOSE_PAINT_OPS and cur is not None and start is not None:
                path.append((cur[0], cur[1], start[0], start[1]))
            segs.extend(path)
            path = []
            cur = start = None
        elif t == b"n":  # fim de caminho sem pintar (clip)
            path = []
            cur = start = None
        elif t == b"cm":
            if len(stack) >= 6:
                na, nb, nc, nd, ne, nf = stack[-6:]
                a, b, c, d, e, f = (
                    na * a + nb * c, na * b + nb * d,
                    nc * a + nd * c, nc * b + nd * d,
                    ne * a + nf * c + e, ne * b + nf * d + f,
                )
        elif t == b"q":
            gstack.append((a, b, c, d, e, f))
        elif t == b"Q":
            if gstack:
                a, b, c, d, e, f = gstack.pop()
        elif t == b"Do":
            if xobjects and last_name in xobjects and depth < _MAX_FORM_DEPTH:
                local = _form_local_segments(
                    xobjects[last_name], depth, form_cache)
                segs.extend(
                    (a * x0 + c * y0 + e, b * x0 + d * y0 + f,
                     a * x1 + c * y1 + e, b * x1 + d * y1 + f)
                    for x0, y0, x1, y1 in local
                )
        stack.clear()
    return segs


def _form_local_segments(
    ref: object,
    depth: int,
    form_cache: dict[int, list[RawSeg]],
) -> list[RawSeg]:
    """Segmentos de um Form XObject no espaço LOCAL (já com a Matrix do form).

    Cacheado por objeto: bloco de CAD invocado N vezes é parseado 1 vez.
    Imagens (Subtype/Image) retornam vazio.
    """
    xo = resolve1(ref)
    key = id(xo)
    if key in form_cache:
        return form_cache[key]
    form_cache[key] = []  # quebra ciclo antes de recursar
    try:
        attrs = getattr(xo, "attrs", {}) or {}
        subtype = resolve1(attrs.get("Subtype"))
        if getattr(subtype, "name", str(subtype)) != "Form":
            return form_cache[key]
        matrix = tuple(float(v) for v in (resolve1(attrs.get("Matrix"))
                                          or (1, 0, 0, 1, 0, 0)))
        res = resolve1(attrs.get("Resources")) or {}
        nested = resolve1(res.get("XObject")) if res.get("XObject") else None
        segs = _fast_stream_segments(
            xo.get_data(), matrix, nested, depth + 1, form_cache)
        form_cache[key] = segs
    except Exception:
        pass  # form ilegível: contribui zero, resto da página segue
    return form_cache[key]


def _extract_raw_segments(page: "pdfplumber.page.Page") -> tuple[list[RawSeg], str]:
    """Extrai segmentos crus; caminho rápido com fallback pro pdfplumber."""
    try:
        page_obj = page.page_obj
        contents = page_obj.contents or []
        data = b" ".join(resolve1(s).get_data() for s in contents)
        if not data:
            raise ValueError("content stream vazio")
        res = resolve1(page_obj.resources) or {}
        xobjects = resolve1(res.get("XObject")) if res.get("XObject") else None
        ctm0 = _initial_ctm(page_obj.mediabox, page_obj.attrs.get("Rotate", 0))
        return _fast_stream_segments(data, ctm0, xobjects), "fast"
    except Exception:
        h = float(page.height)
        segs: list[RawSeg] = [
            (l["x0"], l["y0"], l["x1"], l["y1"]) for l in page.lines
        ]
        for r in page.rects:
            x0, y0, x1, y1 = r["x0"], r["y0"], r["x1"], r["y1"]
            segs.extend((
                (x0, y0, x1, y0), (x1, y0, x1, y1),
                (x1, y1, x0, y1), (x0, y1, x0, y0),
            ))
        for cv in page.curves:  # polilinhas viram sub-segmentos retos
            pts = cv.get("pts") or []
            for (px0, py0), (px1, py1) in zip(pts, pts[1:]):
                segs.append((px0, h - py0, px1, h - py1))
        return segs, "pdfplumber"


# ─────────────────── classificação, fusão e pareamento ───────────────────

def _axis_segments(
    raw: Iterable[RawSeg],
    bbox: tuple[float, float, float, float],
    min_len_pt: float,
    axis_tol_pt: float = 0.35,
) -> tuple[list[AxisSeg], list[AxisSeg]]:
    """Filtra H/V dentro do bbox; descarta diagonais e micro-segmentos."""
    bx0, by0, bx1, by1 = bbox
    horiz: list[AxisSeg] = []
    vert: list[AxisSeg] = []
    for x0, y0, x1, y1 in raw:
        if not (bx0 <= x0 <= bx1 and bx0 <= x1 <= bx1
                and by0 <= y0 <= by1 and by0 <= y1 <= by1):
            continue
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dy <= axis_tol_pt and dx >= min_len_pt:
            horiz.append((min(x0, x1), max(x0, x1), (y0 + y1) / 2.0))
        elif dx <= axis_tol_pt and dy >= min_len_pt:
            vert.append((min(y0, y1), max(y0, y1), (x0 + x1) / 2.0))
    return horiz, vert


def _merge_collinear(
    segs: list[AxisSeg],
    perp_tol_pt: float = 0.35,
    gap_pt: float = 1.0,
) -> list[AxisSeg]:
    """Funde segmentos na mesma reta (p ± tol) com gap pequeno.

    Junta linha de CAD quebrada em pedacinhos e elimina duplicata exata.
    NÃO atravessa abertura de porta (a 1:100, porta de 80 cm ≈ 28 pt >> gap).
    """
    if not segs:
        return []
    segs = sorted(segs, key=lambda s: s[2])
    out: list[AxisSeg] = []
    group: list[AxisSeg] = [segs[0]]
    for s in segs[1:]:
        if s[2] - group[-1][2] <= perp_tol_pt:
            group.append(s)
        else:
            out.extend(_merge_group(group, gap_pt))
            group = [s]
    out.extend(_merge_group(group, gap_pt))
    return out


def _merge_group(group: list[AxisSeg], gap_pt: float) -> list[AxisSeg]:
    p = sum(g[2] for g in group) / len(group)
    ivs = sorted((g[0], g[1]) for g in group)
    merged: list[AxisSeg] = []
    cur0, cur1 = ivs[0]
    for a0, a1 in ivs[1:]:
        if a0 - cur1 <= gap_pt:
            cur1 = max(cur1, a1)
        else:
            merged.append((cur0, cur1, p))
            cur0, cur1 = a0, a1
    merged.append((cur0, cur1, p))
    return merged


def _pair_walls(
    segs: list[AxisSeg],
    tmin_pt: float,
    tmax_pt: float,
    min_len_pt: float,
    min_overlap_frac: float = 0.6,
    max_partners: int = 6,
) -> list[tuple[float, float, float, float, float]]:
    """Casa pares paralelos à distância [tmin, tmax] com bucketing por p.

    Retorna lista de (comprimento_overlap_pt, espessura_pt, inicio_pt,
    fim_pt, p_meio_pt) — os 3 últimos localizam a parede no eixo (intervalo
    da sobreposição + coordenada perpendicular média), usados pela validação
    por cota (pdfvec_cotas). Guloso por maior overlap; cada segmento casa no
    máximo uma vez. Segmento com mais de `max_partners` candidatos =
    provável hachura/grade → descartado.
    """
    n = len(segs)
    if n < 2:
        return []
    cell = max(tmax_pt, 1.0)
    buckets: dict[int, list[int]] = defaultdict(list)
    for i, (_, _, p) in enumerate(segs):
        buckets[int(p // cell)].append(i)

    cands: list[tuple[float, float, int, int]] = []
    partners = [0] * n
    for i, (a0, a1, p) in enumerate(segs):
        k0 = int((p + tmin_pt) // cell) - 1
        k1 = int((p + tmax_pt) // cell) + 1
        for k in range(k0, k1 + 1):
            for j in buckets.get(k, ()):
                b0, b1, q = segs[j]
                d = q - p
                if d < tmin_pt or d > tmax_pt:
                    continue
                ov = min(a1, b1) - max(a0, b0)
                if ov < min_len_pt:
                    continue
                if ov < min_overlap_frac * min(a1 - a0, b1 - b0):
                    continue
                cands.append((ov, d, i, j))
                partners[i] += 1
                partners[j] += 1

    cands = [cd for cd in cands
             if partners[cd[2]] <= max_partners and partners[cd[3]] <= max_partners]
    cands.sort(key=lambda cd: (-cd[0], cd[1]))

    used: set[int] = set()
    walls: list[tuple[float, float, float, float, float]] = []
    for ov, d, i, j in cands:
        if i in used or j in used:
            continue
        used.add(i)
        used.add(j)
        a0, a1, p = segs[i]
        b0, b1, q = segs[j]
        walls.append((ov, d, max(a0, b0), min(a1, b1), (p + q) / 2.0))
    return walls


# ─────────────────────────────── API pública ───────────────────────────────

def detect_walls(
    pdf_path: str,
    page_index: int = 0,
    scale_denominator: int = 100,
    region_bbox: Optional[tuple[float, float, float, float]] = None,
    thickness_range_m: tuple[float, float] = (0.08, 0.30),
    min_wall_len_m: float = 0.30,
    min_overlap_frac: float = 0.6,
    max_segments: int = 60000,
) -> dict[str, Any]:
    """Mede comprimento de paredes/divisórias numa prancha vetorial.

    Args:
        pdf_path: caminho do PDF.
        page_index: página (0-based).
        scale_denominator: denominador da escala (100 para 1:100).
        region_bbox: (x0, y0, x1, y1) em pontos, y para cima; None = página
            inteira MENOS a faixa direita de 15% (carimbo típico).
        thickness_range_m: faixa de espessura real aceita como parede.
        min_wall_len_m: trecho mínimo de parede em metros reais.
        min_overlap_frac: sobreposição mínima de projeção entre as faces.
        max_segments: teto de segmentos por eixo (guarda de performance).

    Returns:
        {"total_length_m": float,
         "n_walls": int,
         "walls": [{"length_m": float, "thickness_cm": float,
                    "axis": "h"|"v", "span_pt": (ini, fim), "p_pt": float},
                   ...],   # axis/span_pt/p_pt localizam a parede no papel —
                           # consumidos pela validação por cota (pdfvec_cotas)
         "meta": {...diagnóstico: engine, contagens, tempo...}}
    """
    t0 = time.time()
    m_per_pt = PT_TO_M * scale_denominator
    min_len_pt = min_wall_len_m / m_per_pt
    tmin_pt = thickness_range_m[0] / m_per_pt
    tmax_pt = thickness_range_m[1] / m_per_pt

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_index]
        pw, ph = float(page.width), float(page.height)
        raw, engine = _extract_raw_segments(page)

    if region_bbox is None:
        region_bbox = (0.0, 0.0, pw * 0.85, ph)  # exclui carimbo à direita

    horiz, vert = _axis_segments(raw, region_bbox, min_len_pt)
    horiz = _merge_collinear(horiz)
    vert = _merge_collinear(vert)
    for seq in (horiz, vert):
        if len(seq) > max_segments:
            seq.sort(key=lambda s: s[1] - s[0], reverse=True)
            del seq[max_segments:]

    walls = []
    for axis, seq in (("h", horiz), ("v", vert)):
        for ov, d, lo, hi, p in _pair_walls(seq, tmin_pt, tmax_pt,
                                            min_len_pt, min_overlap_frac):
            walls.append({
                "length_m": round(ov * m_per_pt, 3),
                "thickness_cm": round(d * m_per_pt * 100.0, 1),
                # posição no eixo (pontos PDF, y pra cima) — consumida pela
                # validação por cota (pdfvec_cotas): "h" = parede horizontal
                # (span em x, p = y da linha média); "v" = vertical.
                "axis": axis,
                "span_pt": (round(lo, 1), round(hi, 1)),
                "p_pt": round(p, 1),
            })
    walls.sort(key=lambda w: -w["length_m"])
    total = sum(w["length_m"] for w in walls)

    return {
        "total_length_m": round(total, 2),
        "n_walls": len(walls),
        "walls": walls,
        "meta": {
            "pdf_path": pdf_path,
            "page_index": page_index,
            "engine": engine,
            "scale_denominator": scale_denominator,
            "page_size_pt": (round(pw, 1), round(ph, 1)),
            "region_bbox": tuple(round(v, 1) for v in region_bbox),
            "n_raw_segments": len(raw),
            "n_horiz_segs": len(horiz),
            "n_vert_segs": len(vert),
            "seconds": round(time.time() - t0, 2),
        },
    }


# ─────────────────────────────── auto-teste ───────────────────────────────

def _thickness_histogram(walls: list[dict[str, float]]) -> dict[str, float]:
    """Metros de parede por faixa de espessura (diagnóstico)."""
    hist: dict[str, float] = defaultdict(float)
    for w in walls:
        lo = min(int(w["thickness_cm"] // 5) * 5, 25)
        hist[f"{lo}-{lo + 5}cm"] += w["length_m"]
    return {k: round(v, 1)
            for k, v in sorted(hist.items(), key=lambda kv: int(kv[0].split("-")[0]))}


if __name__ == "__main__":
    import json
    import os

    CORPUS = [
        ("DEMOLIR", r"C:\Users\admin\Desktop\arq\0326.CGR.14.100.DEMOLIR.02-A1.pdf"),
        ("LAYOUT", r"C:\Users\admin\Desktop\arq\0326.CGR.14.200.LAYOUT.02-A1.pdf"),
        ("MARCENARIA", r"C:\Users\admin\Desktop\arq\0326.CGR.14.301.MARCENARIA.00-A0.pdf"),
        ("ARQUITETURA", r"C:\Users\admin\Desktop\arq\0326.CGR.14.400.ARQUITETURA.02-A1.pdf"),
        ("PONTOS", r"C:\Users\admin\Desktop\arq\0326.CGR.14.500.PONTOS.02-A1.pdf"),
        ("PISO", r"C:\Users\admin\Desktop\arq\0326.CGR.14.600.PISO.02-a1.pdf"),
        ("FORRO", r"C:\Users\admin\Desktop\arq\0326.CGR.14.700.FORRO.02-A1.pdf"),
        ("ATENDAS", r"C:\Users\admin\Desktop\arq\LAYOUT ATENDAS rev 01.pdf"),
    ]
    DEN = 100  # 1:100 validado por cotas na PONTOS; assumido para as irmãs

    results = {}
    for name, path in CORPUS:
        if not os.path.exists(path):
            print(f"[{name}] AUSENTE: {path}")
            continue
        r = detect_walls(path, scale_denominator=DEN)
        m = r["meta"]
        top = [(w["length_m"], w["thickness_cm"]) for w in r["walls"][:8]]
        print(f"[{name}] {r['total_length_m']:8.1f} m em {r['n_walls']:4d} trechos | "
              f"{m['seconds']:5.1f}s ({m['engine']}) | raw {m['n_raw_segments']} "
              f"-> H/V {m['n_horiz_segs']}/{m['n_vert_segs']}")
        print(f"          espessuras (m por faixa): {_thickness_histogram(r['walls'])}")
        print(f"          maiores trechos: {top}")
        results[name] = {"total_length_m": r["total_length_m"], "n_walls": r["n_walls"],
                         "seconds": m["seconds"], "engine": m["engine"]}
    print("\nJSON:", json.dumps(results, ensure_ascii=False))
