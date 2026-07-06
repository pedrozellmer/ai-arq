# -*- coding: utf-8 -*-
"""Medicao Vetorial de PDF v1 - deteccao de AMBIENTES (areas de piso).

Le a geometria vetorial de uma prancha CAD plotada em PDF (pdfplumber) e fecha
os poligonos de ambientes com shapely (unary_union para nodar a sopa de linhas
+ polygonize). Deterministico: zero IA, zero rede.

O problema que a sonda original nao resolvia: poligonos ANINHADOS.
polygonize devolve tres camadas misturadas:
  1. envoltorias (contorno do pavimento / faixa de parede) que CONTEM ambientes;
  2. os ambientes de verdade (a "camada do meio");
  3. mobiliario/bancadas dentro dos ambientes.
Estrategia: ordenar por area desc; um candidato cujo interior e' majoritariamente
preenchido por outros candidatos e' envoltoria (descarta); um candidato dentro de
um ambiente ja aceito e' mobiliario (descarta). Fica a camada do meio.

Sistema de coordenadas: pontos PDF com y crescendo PARA CIMA (convencao de
page.lines y0/y1 do pdfplumber). `region_bbox` e as saidas centroid/bbox usam
esse mesmo sistema. Conversao p/ metros: pts * PT_TO_M * scale_denominator.

Limitacoes conhecidas (v1):
  - Sem deteccao de views: prancha com varias vistas (cortes, ampliacoes 1:25)
    mede TUDO na escala passada — inflaciona. Mitigacao: region_bbox.
  - Piso de custo: o parse do pdfplumber/pdfminer e' ~40s em prancha de forro
    densa (85k linhas + 75k curvas de hachura); nao ha' knob p/ acelerar isso.
  - Corredores/faixas de parede na faixa 1.5-500 m2 podem passar como ambiente.

Uso:
    from pdfvec_rooms import detect_rooms
    rooms = detect_rooms(path, page_index=0, scale_denominator=100)
    # -> [{"area_m2": 9.6, "centroid": (x, y), "bbox": (x0, y0, x1, y1)}, ...]
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from typing import Optional, Sequence

import pdfplumber
from shapely.geometry import LineString, MultiLineString, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

PT_TO_M: float = 0.0254 / 72.0     # metros por ponto PDF em escala 1:1
MIN_ROOM_M2: float = 1.5           # abaixo disso = mobiliario/shaft
MAX_ROOM_M2: float = 500.0         # acima disso = envoltoria/pavimento
STAMP_FRACTION: float = 0.15       # carimbo tipico: faixa direita da prancha
MAX_SEGS: int = 45_000             # teto de seguranca p/ o union ficar <40s
LEN_THRESHOLDS: Sequence[float] = (3.0, 5.0, 8.0, 12.0, 20.0)  # pt
ENVELOPE_FILL: float = 0.55        # filhos cobrindo >55% do pai => envoltoria


def _curve_pts_bottom_up(curve: dict, page_height: float) -> list[tuple[float, float]]:
    """Pontos de uma curva na convencao y-para-cima.

    pdfplumber entrega curve['pts'] ora top-down ora bottom-up dependendo da
    versao; detecta comparando com o bbox declarado (y0/y1, sempre bottom-up).
    """
    pts = [(float(x), float(y)) for x, y in curve["pts"]]
    ys = [y for _, y in pts]
    y0, y1 = float(curve["y0"]), float(curve["y1"])
    direct_err = abs(min(ys) - y0) + abs(max(ys) - y1)
    flip_err = abs((page_height - max(ys)) - y0) + abs((page_height - min(ys)) - y1)
    if flip_err < direct_err:
        pts = [(x, page_height - y) for x, y in pts]
    return pts


def _collect_raw_segments(page: "pdfplumber.page.Page") -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Extrai segmentos brutos (linhas, bordas de rects, lados de curvas).

    Filtro de micro-segmentos (<MIN_SEG_PT) e dedupe acontecem AQUI, inline,
    porque pranchas de forro/hachura chegam a >1M de sub-segmentos e materializar
    tudo custava ~12s so' em Python.
    """
    min_len = LEN_THRESHOLDS[0]
    seen: set[tuple[float, float, float, float]] = set()
    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []

    def push(ax: float, ay: float, bx: float, by: float) -> None:
        if abs(bx - ax) < min_len and abs(by - ay) < min_len:
            return
        key = (round(ax, 2), round(ay, 2), round(bx, 2), round(by, 2))
        if key[:2] > key[2:]:  # canonico: dedupa tambem o segmento invertido
            key = (key[2], key[3], key[0], key[1])
        if key in seen:
            return
        seen.add(key)
        segs.append(((ax, ay), (bx, by)))

    for l in page.lines:
        push(float(l["x0"]), float(l["y0"]), float(l["x1"]), float(l["y1"]))
    for r in page.rects:
        x0, y0, x1, y1 = float(r["x0"]), float(r["y0"]), float(r["x1"]), float(r["y1"])
        push(x0, y0, x1, y0)
        push(x1, y0, x1, y1)
        push(x1, y1, x0, y1)
        push(x0, y1, x0, y0)
    h = float(page.height)
    for c in page.curves:
        # curva com bbox minusculo (hachura/simbolo) nunca fecha ambiente
        if float(c["x1"]) - float(c["x0"]) < min_len and float(c["y1"]) - float(c["y0"]) < min_len:
            continue
        pts = _curve_pts_bottom_up(c, h)
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            push(ax, ay, bx, by)
    return segs


def _seg_len(seg: tuple[tuple[float, float], tuple[float, float]]) -> float:
    (ax, ay), (bx, by) = seg
    return max(abs(bx - ax), abs(by - ay))  # Chebyshev basta p/ filtro


def _filter_segments(
    raw: list[tuple[tuple[float, float], tuple[float, float]]],
    page_width: float,
    page_height: float,
    region_bbox: Optional[tuple[float, float, float, float]],
) -> list[LineString]:
    """Filtra por comprimento adaptativo, recorta regiao e aplica teto de custo.

    (dedupe e corte <3pt ja aconteceram inline na coleta)
    """
    uniq = raw
    # micro-segmentos (hachura/seta/texto explodido) sobem o custo e nao fecham sala
    min_len = LEN_THRESHOLDS[0]
    for thr in LEN_THRESHOLDS:
        min_len = thr
        if sum(1 for s in uniq if _seg_len(s) >= thr) <= MAX_SEGS:
            break
    kept = [s for s in uniq if _seg_len(s) >= min_len]
    if len(kept) > MAX_SEGS:  # ainda acima do teto: fica com os maiores
        kept.sort(key=_seg_len, reverse=True)
        kept = kept[:MAX_SEGS]

    if region_bbox is not None:
        clip = box(*region_bbox)
        out: list[LineString] = []
        for a, b in kept:
            ls = LineString([a, b])
            inter = ls.intersection(clip)
            if inter.is_empty or inter.length < min_len:
                continue
            if inter.geom_type == "LineString":
                out.append(inter)
            elif inter.geom_type == "MultiLineString":
                out.extend(g for g in inter.geoms if g.length >= min_len)
        return out

    # default: exclui segmentos INTEIRAMENTE dentro da faixa do carimbo (direita)
    stamp_x = page_width * (1.0 - STAMP_FRACTION)
    return [
        LineString([a, b])
        for a, b in kept
        if not (a[0] >= stamp_x and b[0] >= stamp_x)
    ]


def _bridge_dangling(segments: list[LineString], max_gap_pt: float) -> list[LineString]:
    """Fecha o anel: liga PONTAS SOLTAS próximas (vãos de porta abrem o contorno).

    Ponta solta = endpoint que aparece uma única vez na sopa (grau 1, com
    arredondamento de 0.5pt). Pares de pontas soltas a até max_gap_pt viram
    segmentos-ponte (greedy, cada ponta casa 1x). Em 1:100, 12pt ≈ 1,2 m —
    cobre porta de 0,8-1,1 m sem engolir corredor (~1,5 m+).
    """
    from collections import defaultdict
    occ: dict[tuple[float, float], int] = defaultdict(int)
    def key(p):
        return (round(p[0] * 2) / 2, round(p[1] * 2) / 2)
    for s in segments:
        c = list(s.coords)
        occ[key(c[0])] += 1
        occ[key(c[-1])] += 1
    dang = [k for k, n in occ.items() if n == 1]
    if len(dang) < 2:
        return []
    # pareamento guloso por distância (n pequeno: pontas soltas são poucas)
    used = set()
    bridges: list[LineString] = []
    import math
    for i, a in enumerate(dang):
        if i in used:
            continue
        best_j, best_d = None, max_gap_pt
        for j in range(i + 1, len(dang)):
            if j in used:
                continue
            b = dang[j]
            d = math.hypot(a[0] - b[0], a[1] - b[1])
            if d <= best_d:
                best_j, best_d = j, d
        if best_j is not None and best_d > 0.6:
            used.add(i); used.add(best_j)
            bridges.append(LineString([a, dang[best_j]]))
    return bridges


def _polygonize_faces(segments: list[LineString], bridge_gaps_pt: float = 0.0) -> list[Polygon]:
    """Noda a sopa de linhas (unary_union) e fecha as faces (polygonize)."""
    if not segments:
        return []
    if bridge_gaps_pt > 0:
        segments = segments + _bridge_dangling(segments, bridge_gaps_pt)
    merged = unary_union(MultiLineString([list(s.coords) for s in segments]))
    return list(polygonize(merged))


def _middle_layer(
    faces: list[Polygon],
    m_per_pt: float,
    min_m2: float,
    max_m2: float,
) -> list[dict]:
    """Resolve o aninhamento: descarta envoltorias e mobiliario, fica o ambiente.

    Trabalha com o anel externo (shell) de cada face para que buracos criados
    pelo polygonize nao mascarem o teste de continencia. Area reportada = area
    do shell (inclui piso sob mobiliario, que continua sendo piso).
    """
    sq = m_per_pt * m_per_pt
    cands: list[tuple[float, Polygon, Polygon]] = []  # (area_m2_shell, shell, face)
    for f in faces:
        try:
            shell = Polygon(f.exterior)
        except Exception:
            continue
        a = shell.area * sq
        if min_m2 <= a <= max_m2:
            cands.append((a, shell, f))
    if not cands:
        return []

    cands.sort(key=lambda t: t[0], reverse=True)
    shells = [c[1] for c in cands]
    reps = [s.representative_point() for s in shells]
    tree = STRtree(reps)

    # filhos estritos de cada candidato (ponto-representante dentro do shell,
    # com area menor — faces do polygonize nao se sobrepoem em interior)
    children: list[list[int]] = [[] for _ in cands]
    for i, (a_i, shell_i, _f) in enumerate(cands):
        for j in tree.query(shell_i, predicate="contains"):
            j = int(j)
            if j != i and cands[j][0] < a_i * 0.98:
                children[i].append(j)

    accepted: list[int] = []
    accepted_shells: list[Polygon] = []
    for i, (a_i, shell_i, _f) in enumerate(cands):
        # mobiliario: dentro de um ambiente ja aceito (aceitos vem antes, sao maiores)
        rep = reps[i]
        if any(s.contains(rep) for s in accepted_shells):
            continue
        # envoltoria: os filhos-candidatos preenchem a maior parte do interior
        if children[i]:
            fill = sum(cands[j][0] for j in children[i])
            if fill > ENVELOPE_FILL * a_i:
                continue
        accepted.append(i)
        accepted_shells.append(shell_i)

    rooms: list[dict] = []
    for i in accepted:
        a, shell, _f = cands[i]
        cx, cy = shell.centroid.x, shell.centroid.y
        x0, y0, x1, y1 = shell.bounds
        rooms.append({
            "area_m2": round(a, 2),
            "centroid": (round(cx, 1), round(cy, 1)),
            "bbox": (round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)),
        })
    rooms.sort(key=lambda r: r["area_m2"], reverse=True)
    return rooms


def detect_rooms(
    pdf_path: str,
    page_index: int = 0,
    scale_denominator: float = 100.0,
    region_bbox: Optional[tuple[float, float, float, float]] = None,
    min_m2: float = MIN_ROOM_M2,
    max_m2: float = MAX_ROOM_M2,
    bridge_gaps_pt: float = 0.0,
) -> list[dict]:
    """Detecta ambientes (areas de piso) numa prancha CAD vetorial em PDF.

    Args:
        pdf_path: caminho do PDF.
        page_index: pagina (0-based).
        scale_denominator: denominador da escala de plotagem (100 => 1:100).
            O integrador deriva isso das cotas (ver escala_pdf2.py) e passa aqui.
        region_bbox: (x0, y0, x1, y1) em pontos PDF, y crescendo para cima,
            para medir so a view principal. Se None, mede a pagina toda menos
            a faixa tipica do carimbo (15% da direita).
        min_m2 / max_m2: faixa plausivel de ambiente na escala dada.

    Returns:
        Lista de dicts {"area_m2", "centroid", "bbox"} (coords em pontos PDF,
        y para cima), ordenada por area decrescente.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_index]
        raw = _collect_raw_segments(page)
        w, h = float(page.width), float(page.height)
    segs = _filter_segments(raw, w, h, region_bbox)
    faces = _polygonize_faces(segs, bridge_gaps_pt=bridge_gaps_pt)
    m_per_pt = PT_TO_M * float(scale_denominator)
    return _middle_layer(faces, m_per_pt, min_m2, max_m2)


# ─────────────────────────── auto-teste no corpus ───────────────────────────

_CORPUS = [
    (r"C:\Users\admin\Desktop\arq\0326.CGR.14.500.PONTOS.02-A1.pdf", 100),
    (r"C:\Users\admin\Desktop\arq\0326.CGR.14.400.ARQUITETURA.02-A1.pdf", 100),
    (r"C:\Users\admin\Desktop\arq\0326.CGR.14.200.LAYOUT.02-A1.pdf", 100),
    (r"C:\Users\admin\Desktop\arq\0326.CGR.14.100.DEMOLIR.02-A1.pdf", 100),
    (r"C:\Users\admin\Desktop\arq\0326.CGR.14.600.PISO.02-a1.pdf", 100),
    (r"C:\Users\admin\Desktop\arq\0326.CGR.14.700.FORRO.02-A1.pdf", 100),
    (r"C:\Users\admin\Desktop\arq\0326.CGR.14.301.MARCENARIA.00-A0.pdf", 100),
    (r"C:\Users\admin\Desktop\arq\LAYOUT ATENDAS rev 01.pdf", 100),
]


def _selftest() -> None:
    for path, scale in _CORPUS:
        name = path.rsplit("\\", 1)[-1]
        t0 = time.monotonic()
        try:
            rooms = detect_rooms(path, 0, scale)
        except Exception as e:  # noqa: BLE001 - relatorio de teste
            print(f"{name}: ERRO {type(e).__name__}: {e}")
            continue
        dt = time.monotonic() - t0
        total = sum(r["area_m2"] for r in rooms)
        top = [r["area_m2"] for r in rooms[:12]]
        rep = Counter(round(r["area_m2"], 1) for r in rooms)
        repeats = {a: n for a, n in rep.most_common(5) if n >= 2}
        flag = " <<< LENTO" if dt > 40 else ""
        print(f"{name}: {len(rooms)} ambientes | {total:.0f} m2 | {dt:.1f}s{flag}")
        print(f"   top: {top}")
        if repeats:
            print(f"   areas repetidas (bom sinal): {repeats}")


if __name__ == "__main__":
    _selftest()
    sys.exit(0)
