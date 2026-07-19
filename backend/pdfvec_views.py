# -*- coding: utf-8 -*-
"""pdfvec_views — Medição Vetorial de PDF v1: SEGMENTAÇÃO DE VIEWS.

Uma prancha CAD plotada em PDF quase sempre tem VÁRIAS vistas na mesma folha:
a planta principal + cortes, ampliações, legendas, tabelas. Medir a folha
inteira numa escala só INFLA o quantitativo (ARQUITETURA/DEMOLIR/PISO deste
corpus). Este módulo separa as vistas de forma DETERMINÍSTICA (zero IA/rede):

  1. extrai os segmentos de geometria (reusa pdfvec_rooms._collect_raw_segments);
  2. exclui a faixa do carimbo (direita, 15% da largura) e as linhas de
     MOLDURA da folha (quase do tamanho da página, coladas na borda) — a
     moldura tocaria todas as vistas e fundiria tudo num cluster só;
  3. rasteriza cada segmento numa GRADE (célula = gap_pt) e roda componentes
     conexos 8-vizinhos sobre as células ocupadas: geometria a menos de
     ~gap_pt de distância pertence à mesma vista;
  4. REFINO HIERÁRQUICO do cluster principal: cadeias de cota/símbolos fazem
     ponte entre a planta e a coluna de detalhes (no corpus, ARQUITETURA e
     DEMOLIR fundiam tudo em qualquer gap>=8). O maior cluster é re-clusterizado
     com gap/2; se o maior sub-cluster mantém a maioria dos segmentos num bbox
     bem menor, ele vira a main view e o resto vira vista própria;
  5. clusters com >=1% dos segmentos viram "views"; a MAIN VIEW é o cluster
     que maximiza contagem_de_segmentos x área_do_bbox (legendas/tabelas de
     texto explodido têm muitos segmentos mas área pequena; sobras de moldura
     têm área grande mas pouquíssimos segmentos — o produto isola a planta).

Sistema de coordenadas: pontos PDF com y crescendo PARA CIMA (a mesma
convenção de pdfvec_rooms/pdfvec_walls). O bbox devolvido pode ser passado
direto como `region_bbox` de detect_rooms/detect_walls.

Calibração no corpus (8 pranchas reais, A1/A0):
  gap 8pt separa vistas sem fragmentar a planta; gap>=12 funde tudo;
  gap<=5 estilhaça legendas. O refino gap/2 corta as pontes de cota.

Limitações (v1):
  * Vista COLADA na planta (tabela encostando a <4pt, caso DEMOLIR) permanece
    no cluster da planta — sem gap físico não há separação espacial possível.
  * O carimbo é assumido na faixa direita (15%); carimbo em outra borda entra
    nos clusters (mas dificilmente vira main view).
  * "Main view" é a maior vista da folha — em prancha SÓ de detalhes
    (ex.: marcenaria) a main view é apenas o maior detalhe, não uma planta.

Uso:
    from pdfvec_views import detect_views
    views = detect_views(path, page_index=0)
    main = next(v for v in views if v["is_main"])
    rooms = detect_rooms(path, region_bbox=main["bbox"], scale_denominator=100)
"""
from __future__ import annotations

import json
import sys
import time
from typing import Optional

import pdfplumber
from shapely.geometry import Polygon

from pdfvec_rooms import (  # mesma pasta; reusa extração e polígonos
    PT_TO_M,
    _collect_raw_segments,
    _filter_segments,
    _middle_layer,
    _polygonize_faces,
)

GAP_PT: float = 8.0           # células da grade; geometria a <~8-16pt = mesma view
STAMP_FRACTION: float = 0.15  # carimbo típico: faixa direita da prancha
MIN_VIEW_FRAC: float = 0.01   # cluster com <1% dos segmentos não é view
FRAME_LEN_FRAC: float = 0.70  # segmento >=70% da dimensão da página...
FRAME_BAND_FRAC: float = 0.06 # ...colado a <6% da borda = moldura (descarta)
PAD_PT: float = 6.0           # folga do bbox devolvido (não decepar parede)
REFINE_KEEP: float = 0.55     # refino: sub-cluster fica com >=55% dos segs...
REFINE_SHRINK: float = 0.85   # ...e bbox <=85% da área => vira a main view

RawSeg = tuple[tuple[float, float], tuple[float, float]]


# ───────────────────────── pré-filtros de segmento ──────────────────────────

def _drop_frame_and_stamp(
    raw: list[RawSeg], w: float, h: float, stamp_fraction: float
) -> list[RawSeg]:
    """Remove moldura da folha e faixa do carimbo antes de clusterizar."""
    stamp_x = w * (1.0 - stamp_fraction)
    bx0, bx1 = w * FRAME_BAND_FRAC, w * (1.0 - FRAME_BAND_FRAC)
    by0, by1 = h * FRAME_BAND_FRAC, h * (1.0 - FRAME_BAND_FRAC)
    out: list[RawSeg] = []
    for (ax, ay), (bx, by) in raw:
        if ax >= stamp_x and bx >= stamp_x:           # inteiro no carimbo
            continue
        dx, dy = abs(bx - ax), abs(by - ay)
        if dx >= FRAME_LEN_FRAC * w and dy < 2.0:     # h quase página inteira
            ym = (ay + by) / 2
            if ym <= by0 or ym >= by1:                # colada na borda = moldura
                continue
        if dy >= FRAME_LEN_FRAC * h and dx < 2.0:     # v quase página inteira
            xm = (ax + bx) / 2
            if xm <= bx0 or xm >= bx1:
                continue
        out.append(((ax, ay), (bx, by)))
    return out


# ───────────────────── grade + componentes conexos ──────────────────────────

def _cells_of(seg: RawSeg, cell: float) -> list[tuple[int, int]]:
    """Células da grade atravessadas pelo segmento (amostragem ao longo dele)."""
    (ax, ay), (bx, by) = seg
    n = int(max(abs(bx - ax), abs(by - ay)) / cell) + 1
    cells: list[tuple[int, int]] = []
    last: Optional[tuple[int, int]] = None
    for i in range(n + 1):
        t = i / n
        c = (int((ax + (bx - ax) * t) // cell), int((ay + (by - ay) * t) // cell))
        if c != last:
            cells.append(c)
            last = c
    return cells


class _DSU:
    """Union-find sobre células (chave = tupla int da grade)."""

    def __init__(self) -> None:
        self.parent: dict[tuple[int, int], tuple[int, int]] = {}

    def add(self, c: tuple[int, int]) -> None:
        if c not in self.parent:
            self.parent[c] = c

    def find(self, c: tuple[int, int]) -> tuple[int, int]:
        p = self.parent
        root = c
        while p[root] != root:
            root = p[root]
        while p[c] != root:      # compressão de caminho
            p[c], c = root, p[c]
        return root

    def union(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


# 4 vizinhos bastam p/ fechar as 8 direções varrendo todas as células
_NEIGH = ((1, 0), (0, 1), (1, 1), (1, -1))


def _cluster(segs: list[RawSeg], idxs: list[int], gap: float) -> list[dict]:
    """Componentes conexos espaciais dos segmentos `idxs` (grade célula=gap).

    Retorna clusters ordenados por contagem desc:
      {"idx": [índices em segs], "bbox": [x0,y0,x1,y1], "n": int}
    """
    dsu = _DSU()
    first_cell: list[tuple[int, int]] = []
    for i in idxs:
        cells = _cells_of(segs[i], gap)
        first_cell.append(cells[0])
        for c in cells:
            dsu.add(c)
        for a, b in zip(cells, cells[1:]):     # células do próprio segmento
            dsu.union(a, b)
    for c in list(dsu.parent):                 # vizinhança 8-conexa
        for dx, dy in _NEIGH:
            nb = (c[0] + dx, c[1] + dy)
            if nb in dsu.parent:
                dsu.union(c, nb)

    groups: dict[tuple[int, int], dict] = {}
    for i, c0 in zip(idxs, first_cell):
        root = dsu.find(c0)
        (ax, ay), (bx, by) = segs[i]
        x0, x1 = (ax, bx) if ax <= bx else (bx, ax)
        y0, y1 = (ay, by) if ay <= by else (by, ay)
        g = groups.get(root)
        if g is None:
            groups[root] = {"idx": [i], "bbox": [x0, y0, x1, y1], "n": 1}
        else:
            g["idx"].append(i)
            g["n"] += 1
            bb = g["bbox"]
            if x0 < bb[0]: bb[0] = x0
            if y0 < bb[1]: bb[1] = y0
            if x1 > bb[2]: bb[2] = x1
            if y1 > bb[3]: bb[3] = y1
    return sorted(groups.values(), key=lambda g: g["n"], reverse=True)


def _bbox_area(bb: list[float]) -> float:
    return max((bb[2] - bb[0]) * (bb[3] - bb[1]), 1.0)


def _score(g: dict) -> float:
    """Main view = muitos segmentos NUM bbox grande (produto isola a planta)."""
    return g["n"] * _bbox_area(g["bbox"])


def detect_views(
    pdf_path: str,
    page_index: int = 0,
    gap_pt: float = GAP_PT,
    stamp_fraction: float = STAMP_FRACTION,
    min_view_frac: float = MIN_VIEW_FRAC,
    _segments: Optional[tuple[list[RawSeg], float, float]] = None,
) -> list[dict]:
    """Segmenta as VIEWS (vistas) de uma prancha CAD vetorial em PDF.

    Args:
        pdf_path: caminho do PDF.
        page_index: página (0-based).
        gap_pt: gap espacial que separa vistas (célula da grade de clusters).
        stamp_fraction: fração da largura, à direita, tratada como carimbo.
        min_view_frac: fração mínima dos segmentos p/ um cluster virar view.
        _segments: (raw, width, height) pré-extraídos — atalho interno p/ não
            pagar o parse do PDF duas vezes quando o integrador também mede.

    Returns:
        Lista de dicts, ordenada por n_segments desc:
          bbox          (x0, y0, x1, y1) em pontos PDF, y PARA CIMA — pronto
                        p/ region_bbox de detect_rooms/detect_walls
          n_segments    segmentos de geometria do cluster
          frac_segments fração do total de segmentos úteis da folha
          is_main       True só no cluster eleito main view
    """
    if _segments is not None:
        raw, w, h = _segments
    else:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_index]
            raw = _collect_raw_segments(page)
            w, h = float(page.width), float(page.height)

    segs = _drop_frame_and_stamp(raw, w, h, stamp_fraction)
    if not segs:
        return []
    total = len(segs)

    clusters = _cluster(segs, list(range(total)), gap_pt)

    # refino hierárquico: pontes de cota/símbolo fundem planta+detalhes num
    # cluster só; re-clusteriza o maior com gap/2 e adota o sub-cluster
    # dominante se ele concentra os segmentos num bbox bem menor
    main_g = max(clusters, key=_score)
    sub = _cluster(segs, main_g["idx"], gap_pt / 2.0)
    if len(sub) > 1:
        cand = max(sub, key=_score)
        if (cand["n"] >= REFINE_KEEP * main_g["n"]
                and _bbox_area(cand["bbox"]) <= REFINE_SHRINK * _bbox_area(main_g["bbox"])):
            clusters.remove(main_g)
            clusters.extend(sub)          # sub-clusters relevantes viram views
            main_g = cand

    views: list[dict] = []
    for g in clusters:
        frac = g["n"] / total
        if frac < min_view_frac and g is not main_g:
            continue
        x0, y0, x1, y1 = g["bbox"]
        views.append({
            "bbox": (round(max(x0 - PAD_PT, 0.0), 1),
                     round(max(y0 - PAD_PT, 0.0), 1),
                     round(min(x1 + PAD_PT, w), 1),
                     round(min(y1 + PAD_PT, h), 1)),
            "n_segments": g["n"],
            "frac_segments": round(frac, 4),
            "is_main": g is main_g,
        })
    views.sort(key=lambda v: v["n_segments"], reverse=True)
    return views


# ───────────────── medição da main view (integração c/ rooms) ───────────────

def measure_main_view(
    pdf_path: str,
    page_index: int = 0,
    scale_denominator: float = 100.0,
    max_room_m2: float = 400.0,
) -> dict:
    """detect_views + detect_rooms SÓ na main view; parse do PDF uma vez só.

    Retorna {views, main_bbox, envelope_m2 (maior polígono da main view),
    rooms_m2 (soma dos ambientes <= max_room_m2), n_rooms}.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_index]
        raw = _collect_raw_segments(page)
        w, h = float(page.width), float(page.height)

    views = detect_views(pdf_path, page_index, _segments=(raw, w, h))
    out = {"views": views, "main_bbox": None, "envelope_m2": None,
           "rooms_m2": 0.0, "n_rooms": 0}
    main = next((v for v in views if v["is_main"]), None)
    if main is None:
        return out
    out["main_bbox"] = main["bbox"]

    segs = _filter_segments(raw, w, h, main["bbox"])
    faces, _bridges = _polygonize_faces(segs)
    m_per_pt = PT_TO_M * float(scale_denominator)
    sq = m_per_pt * m_per_pt

    env = 0.0
    for f in faces:
        try:
            a = Polygon(f.exterior).area * sq
        except Exception:
            continue
        if a > env:
            env = a
    out["envelope_m2"] = round(env, 1) if env > 0 else None

    rooms = _middle_layer(faces, m_per_pt, 1.5, max_room_m2)
    out["rooms_m2"] = round(sum(r["area_m2"] for r in rooms), 1)
    out["n_rooms"] = len(rooms)
    return out


# ─────────────────────────── auto-teste no corpus ───────────────────────────

_CORPUS = [
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.100.DEMOLIR.02-A1.pdf",
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.200.LAYOUT.02-A1.pdf",
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.301.MARCENARIA.00-A0.pdf",
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.400.ARQUITETURA.02-A1.pdf",
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.500.PONTOS.02-A1.pdf",
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.600.PISO.02-a1.pdf",
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.700.FORRO.02-A1.pdf",
    r"C:\Users\admin\Desktop\arq\LAYOUT ATENDAS rev 01.pdf",
]


def _selftest(paths: list[str]) -> None:
    results = []
    for path in paths:
        name = path.rsplit("\\", 1)[-1]
        t0 = time.monotonic()
        try:
            res = measure_main_view(path, 0, 100.0)
        except Exception as e:  # noqa: BLE001 — relatório de teste
            print(f"{name}: ERRO {type(e).__name__}: {e}")
            continue
        dt = time.monotonic() - t0
        views = res["views"]
        main = next((v for v in views if v["is_main"]), None)
        rec = {
            "sheet": name,
            "n_views": len(views),
            "main_view_envelope_m2": res["envelope_m2"],
            "main_view_rooms_m2": res["rooms_m2"],
            "n_rooms": res["n_rooms"],
            "main_bbox": main["bbox"] if main else None,
            "main_frac": main["frac_segments"] if main else None,
            "seconds": round(dt, 1),
        }
        results.append(rec)
        print(json.dumps(rec, ensure_ascii=False))
        top = [(v["n_segments"], v["bbox"]) for v in views[:6]]
        print(f"   top clusters (n_segs, bbox): {top}")
    print("== RESUMO ==")
    print(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    _selftest(sys.argv[1:] or _CORPUS)
