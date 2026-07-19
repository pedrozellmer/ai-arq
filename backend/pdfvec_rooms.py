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

Fechamento de ambientes (melhorias 19/07, A/B em 28 pranchas reais):
  - snap de pontas (SNAP_GRID_PT) + micro-ponte (MICRO_GAP_PT): fecham vaos de
    arredondamento da plotagem que deixavam prancha inteira com 0 salas;
  - ponte de vao de porta (bridge_gaps_m, 2 estagios): so' dispara quando a
    leitura pura mede quase nada, e so' e' adotada se medir MAIS;
  - guarda BRIDGE_PERIM_FRAC: sala que depende de ponte em >25% do perimetro
    e' descartada — fechamento honesto ou nada (regra nº 1).

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

# ── fechamento de ambientes (melhorias 19/07) ────────────────────────────────
# Snap de pontas: meio ponto PDF (~0,18 mm no papel). Plotagem CAD->PDF
# arredonda coordenadas e deixa vaos de centesimos de ponto que o unary_union
# NAO fecha (ele noda cruzamentos, nunca encosta pontas). Em 1:100 o snap move
# cada ponta no maximo ~2,5 cm reais — irrelevante p/ area de sala, mas fecha
# o anel. NAO e' invencao de medida: so cola o que ja estava colado no papel.
SNAP_GRID_PT: float = 0.5
# Ponta solta demais = sopa quebrada (PDF rasterizado/explodido). Pontear isso
# seria fabricar geometria — melhor se abster (regra nº 1 do produto).
MAX_DANGLING: int = 20_000
# Micro-ponte SEMPRE ligada (ate' 1 pt): o snap de grid nao fecha gap montado
# na FRONTEIRA da celula (0,3 pt pode virar 0,5 pt). 1 pt = 3,5 cm reais em
# 1:100 — ordem do arredondamento de pena/plotagem, longe de qualquer vao
# real. Nao e' invencao de medida; e' tolerancia de fabricacao do PDF.
MICRO_GAP_PT: float = 1.0
# Cada ponta solta considera no maximo K vizinhas no pareamento (custo linear).
BRIDGE_KNN: int = 4
# Sala cujo perimetro depende de ponte alem desta fracao e' descartada: um
# ambiente real tem contorno de parede; pontes sao so' os vaos de porta.
# Sala 3x3 m com 2 portas de 1,2 m = 20% do perimetro => passa; "sala" que so'
# existe porque as pontes fecharam metade do contorno => abstem.
BRIDGE_PERIM_FRAC: float = 0.25
# Total de salas abaixo disso = contorno provavelmente aberto (ate' um
# apartamento pequeno tem >=30 m² de ambientes; 20 m² fechados numa planta
# inteira e' sinal de que so' os banheiros fecharam). Dispara o estagio de
# ponte — que so' e' ADOTADO se medir MAIS que a leitura pura (medido no A/B
# 19/07: ponte em prancha que ja fecha bem DERRUBA a medicao, ex. 21->17
# salas na 225.AFS.201 — por isso nunca pontear incondicionalmente).
UNDERDETECT_M2: float = 20.0


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


def _snap_endpoints(segments: list[LineString],
                    grid: float = SNAP_GRID_PT) -> list[LineString]:
    """Snap-rounding das pontas pro grid de SNAP_GRID_PT (fecha micro-gaps).

    O unary_union noda cruzamentos, mas duas pontas a 0,2 pt uma da outra
    continuam separadas — e o ambiente fica aberto sem nenhuma ponta "solta"
    detectável (os buckets de grau podem até coincidir). Quantizar TODAS as
    coordenadas pro mesmo grid cola pontas a até ~0,7 pt (diagonal da célula)
    de forma determinística. Deslocamento máximo por ponta: 0,35 pt ≈ 3,5 cm
    reais em 1:100 — erro de área <0,5% na menor sala aceita (1,5 m²).
    Vértices que colapsam no mesmo ponto são deduplicados; segmento que virou
    ponto cai fora (era menor que o grid — nunca fecharia sala).
    """
    out: list[LineString] = []
    for s in segments:
        coords = [(round(x / grid) * grid, round(y / grid) * grid)
                  for x, y in s.coords]
        ded = [coords[0]]
        for p in coords[1:]:
            if p != ded[-1]:
                ded.append(p)
        if len(ded) >= 2:
            out.append(LineString(ded))
    return out


def _bridge_dangling(segments: list[LineString], max_gap_pt: float) -> list[LineString]:
    """Fecha o anel: liga PONTAS SOLTAS próximas (vãos de porta abrem o contorno).

    Ponta solta = endpoint que aparece uma única vez na sopa (grau 1, no grid
    de SNAP_GRID_PT — os segmentos já chegam snapados). Pares de pontas soltas
    a até max_gap_pt viram segmentos-ponte; pareamento guloso global por
    distância (a ponte mais curta ganha), cada ponta casa no máximo 1x.
    O chamador escolhe max_gap_pt PROPORCIONAL À ESCALA (ex.: 1,2 m reais)
    pra cobrir vão de porta de 60-120 cm sem engolir corredor (>=1,5 m).

    Salvaguardas:
      - as duas pontas do MESMO segmento nunca se ligam (leader/cota isolada
        viraria um laço de área zero — ruído);
      - mais de MAX_DANGLING pontas soltas = sopa quebrada demais; pontear
        seria fabricar geometria => devolve nada (se abstém);
      - busca por grade espacial (célula = max_gap) com K vizinhas por ponta —
        custo ~linear mesmo em prancha densa (o antigo O(n²) explodia).
    """
    from collections import defaultdict
    import math

    occ: dict[tuple[float, float], int] = defaultdict(int)
    owner: dict[tuple[float, float], int] = {}

    def key(p):
        return (round(p[0] * 2) / 2, round(p[1] * 2) / 2)

    for si, s in enumerate(segments):
        c = s.coords
        for p in (c[0], c[-1]):
            k = key(p)
            occ[k] += 1
            owner[k] = si
    dang = [k for k, n in occ.items() if n == 1]
    if len(dang) < 2 or len(dang) > MAX_DANGLING:
        return []

    cell = max(max_gap_pt, 1.0)
    grid_map: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, k in enumerate(dang):
        grid_map[(int(k[0] // cell), int(k[1] // cell))].append(idx)

    cands: list[tuple[float, int, int]] = []
    for idx, a in enumerate(dang):
        cx, cy = int(a[0] // cell), int(a[1] // cell)
        near: list[tuple[float, int]] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for jdx in grid_map.get((cx + dx, cy + dy), ()):
                    if jdx <= idx:
                        continue
                    b = dang[jdx]
                    d = math.hypot(a[0] - b[0], a[1] - b[1])
                    if 1e-9 < d <= max_gap_pt and owner[a] != owner[b]:
                        near.append((d, jdx))
        near.sort()
        cands.extend((d, idx, j) for d, j in near[:BRIDGE_KNN])

    cands.sort()
    used: set[int] = set()
    bridges: list[LineString] = []
    for _d, i, j in cands:
        if i in used or j in used:
            continue
        used.add(i)
        used.add(j)
        bridges.append(LineString([dang[i], dang[j]]))
    return bridges


def _polygonize_faces(
    segments: list[LineString], bridge_gaps_pt: float = 0.0
) -> tuple[list[Polygon], list[LineString]]:
    """Noda a sopa de linhas (unary_union) e fecha as faces (polygonize).

    Retorna (faces, pontes usadas) — as pontes alimentam a guarda de
    honestidade do _middle_layer (sala não pode depender de ponte demais).

    Mesmo com bridge_gaps_pt=0 a MICRO-ponte (MICRO_GAP_PT) roda: sela só
    resíduo de arredondamento da plotagem, nunca vão de porta.
    """
    if not segments:
        return [], []
    bridges = _bridge_dangling(segments, max(bridge_gaps_pt, MICRO_GAP_PT))
    merged = unary_union(MultiLineString(
        [list(s.coords) for s in segments + bridges]))
    return list(polygonize(merged)), bridges


def _middle_layer(
    faces: list[Polygon],
    m_per_pt: float,
    min_m2: float,
    max_m2: float,
    bridges: Optional[list[LineString]] = None,
) -> list[dict]:
    """Resolve o aninhamento: descarta envoltorias e mobiliario, fica o ambiente.

    Trabalha com o anel externo (shell) de cada face para que buracos criados
    pelo polygonize nao mascarem o teste de continencia. Area reportada = area
    do shell (inclui piso sob mobiliario, que continua sendo piso).

    Guarda de honestidade (regra nº 1): quando a sopa recebeu PONTES
    (_bridge_dangling), uma face cujo perimetro depende de ponte alem de
    BRIDGE_PERIM_FRAC nao e' ambiente — e' um buraco que so' "fechou" porque
    inventamos lados demais. Essa face e' descartada (melhor 0 salas honesto
    que 1 sala fabricada).
    """
    sq = m_per_pt * m_per_pt
    bridge_tree: Optional[STRtree] = None
    if bridges:
        bridge_tree = STRtree(bridges)
    cands: list[tuple[float, Polygon, Polygon]] = []  # (area_m2_shell, shell, face)
    for f in faces:
        try:
            shell = Polygon(f.exterior)
        except Exception:
            continue
        a = shell.area * sq
        if not (min_m2 <= a <= max_m2):
            continue
        if bridge_tree is not None:
            ring = shell.exterior
            # faixa fina em volta do anel: mede quanto do contorno é ponte
            band = ring.buffer(0.1)
            blen = 0.0
            for bi in bridge_tree.query(ring):
                try:
                    blen += bridges[int(bi)].intersection(band).length
                except Exception:
                    continue
            if blen > BRIDGE_PERIM_FRAC * ring.length:
                continue  # "sala" feita de ponte => abstém
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
    bridge_gaps_m: float = 0.0,
    return_meta: bool = False,
):
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
        bridge_gaps_pt: ponte de pontas soltas SEMPRE ligada, medida em pontos
            (comportamento legado — usado pela envoltoria). 0 = sem ponte.
        bridge_gaps_m: ponte em METROS REAIS (convertida pela escala), aplicada
            de forma CONSERVADORA em 2 estagios: 1º tenta sem ponte nenhuma
            (geometria pura); SO' se o total fechado ficar abaixo de
            UNDERDETECT_M2, refaz com ponte de ate' bridge_gaps_m — cobre vao
            de porta (60-120 cm) que abre o contorno, sem engolir corredor
            (>=1,5 m) — e adota o resultado apenas se ele medir MAIS. Sala que
            depender de ponte alem de BRIDGE_PERIM_FRAC do perimetro e'
            descartada.
        return_meta: True => retorna (rooms, meta) com o estagio usado e o
            nº de pontes — transparencia pro log do shadow.

    Returns:
        Lista de dicts {"area_m2", "centroid", "bbox"} (coords em pontos PDF,
        y para cima), ordenada por area decrescente. Com return_meta=True,
        tupla (rooms, meta).
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_index]
        raw = _collect_raw_segments(page)
        w, h = float(page.width), float(page.height)
    segs = _filter_segments(raw, w, h, region_bbox)
    # snap de pontas SEMPRE: fecha micro-gaps de arredondamento da plotagem
    # sem inventar geometria (deslocamento maximo ~0,35 pt por ponta).
    segs = _snap_endpoints(segs)
    m_per_pt = PT_TO_M * float(scale_denominator)

    faces, bridges = _polygonize_faces(segs, bridge_gaps_pt=bridge_gaps_pt)
    rooms = _middle_layer(faces, m_per_pt, min_m2, max_m2, bridges=bridges)
    meta = {"stage": "ponte_fixa" if bridge_gaps_pt > 0 else "puro",
            "n_bridges": len(bridges)}

    # 2º estagio (conservador): SO' quando a leitura pura mediu quase nada
    # (< UNDERDETECT_M2 — contorno aberto). Vao de porta abre o ambiente; a
    # ponte proporcional a escala fecha ate' bridge_gaps_m reais. O resultado
    # ponteado so' e' ADOTADO se medir MAIS que o puro (ponte em prancha boa
    # DERRUBA a medicao — visto no A/B). Quem garante honestidade por sala e'
    # a guarda BRIDGE_PERIM_FRAC no _middle_layer: sem folga honesta, sem sala.
    total_puro = sum(r["area_m2"] for r in rooms)
    if total_puro < UNDERDETECT_M2 and bridge_gaps_m > 0 and bridge_gaps_pt <= 0:
        gap_pt = bridge_gaps_m / m_per_pt
        faces2, bridges2 = _polygonize_faces(segs, bridge_gaps_pt=gap_pt)
        rooms2 = _middle_layer(faces2, m_per_pt, min_m2, max_m2, bridges=bridges2)
        if sum(r["area_m2"] for r in rooms2) > total_puro:
            rooms = rooms2
            meta = {"stage": "ponte_porta", "n_bridges": len(bridges2),
                    "gap_pt": round(gap_pt, 1)}

    if return_meta:
        return rooms, meta
    return rooms


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
