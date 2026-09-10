# -*- coding: utf-8 -*-
"""A ponte de vão de porta escolhe a MAIS CURTA, em qualquer ordem dos traços.

🩸 10/09/2026 — A/B do leitor rápido contra a coleta do pdfminer, no corpus de
teste: com o MESMO conjunto de segmentos as salas e a envoltória saíam
diferentes (envoltória 828,6 × 850,4 m² numa prancha). Os segmentos de uma
coleta na ORDEM da outra davam exatamente o resultado da outra. Causa:
`_bridge_dangling` só procurava vizinhas entre as pontas que vinham DEPOIS na
lista, então a ordem (e o sentido) em que o arquivo guarda os traços decidia
quais pontes existiam — e uma sala com porta podia não fechar. O docstring
sempre prometeu "a ponte mais curta ganha" com "K vizinhas por ponta".
📏 Planta sintética com gabarito (60 plantas, 663 salas): embaralhar mudava as
salas em 105 de 240 casos; com K vizinhas de verdade, em 0 — e as salas certas
foram de 94 para 101.

Estes guardas CHAMAM `_bridge_dangling` e `detect_rooms`.
"""
import math
import os
import random
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import pdfvec_rooms  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

W, H = 842.0, 595.0

# Sala de 200 × 150 pt (37,3 m² em 1:100) com vão de porta de 10 pt no topo,
# entre b=(190,250) e a=(200,250). Logo acima de b, 4 traços soltos em 2 pares a
# 1,5 pt: as 4 pontas de baixo ficam MAIS perto de b do que `a`. Na ordem
# [b, traços, a], a ponte que só olhava pra frente dava a b as 4 pontas dos
# traços como vizinhas, e a `a` nenhuma: a porta não fechava.
_TOPO_ESQ = ((100.0, 250.0), (190.0, 250.0))
_TRACOS = [((186.0, 256.0), (186.0, 290.0)), ((187.5, 256.0), (187.5, 290.0)),
           ((192.5, 256.0), (192.5, 290.0)), ((194.0, 256.0), (194.0, 290.0))]
_TOPO_DIR = ((200.0, 250.0), (300.0, 250.0))
_PAREDES = [((100.0, 100.0), (100.0, 250.0)), ((100.0, 100.0), (300.0, 100.0)),
            ((300.0, 100.0), (300.0, 250.0))]
_ORDEM_QUE_FALHAVA = [_TOPO_ESQ] + _TRACOS + [_TOPO_DIR] + _PAREDES
_AREA_DA_SALA = 200 * 150 * (pdfvec_rooms.PT_TO_M * 100.0) ** 2


def _areas(segs):
    rooms = pdfvec_rooms.detect_rooms("", 0, 100.0, None, bridge_gaps_m=1.2,
                                      _segments=(segs, W, H))
    return sorted(r["area_m2"] for r in rooms)


@pytest.mark.parametrize("como", ["ordem que falhava", "ordem invertida", "sentido invertido"])
def test_a_sala_com_porta_FECHA_em_qualquer_ordem_e_sentido(como):
    segs = {"ordem que falhava": _ORDEM_QUE_FALHAVA,
            "ordem invertida": _ORDEM_QUE_FALHAVA[::-1],
            "sentido invertido": [(s[1], s[0]) for s in _ORDEM_QUE_FALHAVA]}[como]
    areas = _areas(segs)
    assert len(areas) == 1 and math.isclose(areas[0], _AREA_DA_SALA, rel_tol=0.01), (
        "a sala de %.1f m² não fechou: %r" % (_AREA_DA_SALA, areas))


# 🪤 A 1ª versão deste guarda deixou passar "só pra frente numa ordem de
# COORDENADA" (a mutação pegou): não depende da ordem do arquivo, mas ainda não
# acha a parceira de verdade. No caso de cima `a` caía entre as 4 vizinhas de b
# por acaso. Aqui os 4 traços (x de 191 a 197) ficam ENTRE b e `a`, todos a menos
# de 10 pt de b: olhando só pra frente, b fica com os 4 traços e `a` não enxerga
# b — a porta não fecha.
_TRACOS_ENTRE = [((191.0, 256.0), (191.0, 296.0)), ((192.5, 256.0), (192.5, 296.0)),
                 ((195.5, 256.0), (195.5, 296.0)), ((197.0, 256.0), (197.0, 296.0))]
_TRACOS_ENTRE_AS_PONTAS = [_TOPO_ESQ] + _TRACOS_ENTRE + [_TOPO_DIR] + _PAREDES


@pytest.mark.parametrize("como", ["como o arquivo guarda", "ordem invertida", "sentido invertido"])
def test_a_porta_FECHA_quando_os_tracos_ficam_ENTRE_as_duas_pontas(como):
    segs = {"como o arquivo guarda": _TRACOS_ENTRE_AS_PONTAS,
            "ordem invertida": _TRACOS_ENTRE_AS_PONTAS[::-1],
            "sentido invertido": [(s[1], s[0]) for s in _TRACOS_ENTRE_AS_PONTAS]}[como]
    areas = _areas(segs)
    assert len(areas) == 1 and math.isclose(areas[0], _AREA_DA_SALA, rel_tol=0.01), (
        "a sala de %.1f m² não fechou: %r" % (_AREA_DA_SALA, areas))


def _pontes(segs, gap):
    linhas = pdfvec_rooms._snap_endpoints([LineString(s) for s in segs])
    return {frozenset(b.coords) for b in pdfvec_rooms._bridge_dangling(linhas, gap)}


def test_as_pontes_sao_as_MESMAS_em_qualquer_ordem_e_sentido():
    base = _pontes(_ORDEM_QUE_FALHAVA, 34.0)
    assert frozenset({(190.0, 250.0), (200.0, 250.0)}) in base, base
    rng = random.Random(7)
    for _ in range(6):
        outra = list(_ORDEM_QUE_FALHAVA)
        rng.shuffle(outra)
        outra = [(s[1], s[0]) if rng.random() < 0.5 else s for s in outra]
        assert _pontes(outra, 34.0) == base, outra


def test_EMPATE_de_distancia_decide_pela_GEOMETRIA_e_nao_pela_lista():
    """Ponta p a 10 pt de q1 e de q2: quem ganha a ponte não depende da ordem."""
    p = ((100.0, 100.0), (100.0, 40.0))
    q1 = ((90.0, 100.0), (30.0, 100.0))
    q2 = ((110.0, 100.0), (170.0, 100.0))
    base = _pontes([p, q1, q2], 12.0)
    assert len(base) == 1, base
    for ordem in ([q2, p, q1], [q1, q2, p], [p, q2, q1], [q2, q1, p]):
        assert _pontes(ordem, 12.0) == base, ordem


def _planta_com_portas(seed):
    """Grade de ambientes com parede de linha única, vão de porta em ~45% das
    paredes, pontas com a imprecisão da plotagem (±0,3 pt) e mobiliário solto."""
    rng = random.Random(seed)
    cols, rows = rng.randint(3, 5), rng.randint(2, 4)
    cw, rh = rng.uniform(90, 140), rng.uniform(80, 120)
    x0, y0 = 40.0, 40.0
    segs = []

    def jit(v):
        return v + rng.uniform(-0.3, 0.3)

    def parede(ax, ay, bx, by):
        if rng.random() < 0.45:
            gap = rng.uniform(18, 33)
            mx, my = (ax + bx) / 2, (ay + by) / 2
            L = max(abs(bx - ax), abs(by - ay))
            ux, uy = (bx - ax) / L, (by - ay) / L
            segs.append(((jit(ax), jit(ay)), (jit(mx - ux * gap / 2), jit(my - uy * gap / 2))))
            segs.append(((jit(mx + ux * gap / 2), jit(my + uy * gap / 2)), (jit(bx), jit(by))))
        else:
            segs.append(((jit(ax), jit(ay)), (jit(bx), jit(by))))

    for r in range(rows + 1):
        for c in range(cols):
            parede(x0 + c * cw, y0 + r * rh, x0 + (c + 1) * cw, y0 + r * rh)
    for r in range(rows):
        for c in range(cols + 1):
            parede(x0 + c * cw, y0 + r * rh, x0 + c * cw, y0 + (r + 1) * rh)
    for _ in range(rng.randint(20, 80)):
        cx, cy = rng.uniform(x0, x0 + cols * cw), rng.uniform(y0, y0 + rows * rh)
        L, ang = rng.uniform(6, 30), rng.choice([0.0, 1.5708, 0.7854])
        segs.append(((cx, cy), (cx + L * math.cos(ang), cy + L * math.sin(ang))))
    return segs


# Sementes em que a ponte de ANTES errava: 0 e 7 em 4 de 4 embaralhamentos
# (ponte de vão de porta); 4 em 3 de 4 (só a micro-ponte).
_SEMENTES = (0, 4, 7)


@pytest.mark.parametrize("seed", _SEMENTES)
def test_planta_com_portas_da_as_MESMAS_salas_em_qualquer_ordem_e_sentido(seed):
    segs = _planta_com_portas(seed)
    base = _areas(segs)
    for k in range(4):
        rng = random.Random(1000 + 10 * seed + k)
        outra = list(segs)
        rng.shuffle(outra)
        outra = [(s[1], s[0]) if rng.random() < 0.5 else s for s in outra]
        got = _areas(outra)
        assert got == base, "embaralhamento %d: %r != %r" % (k, got, base)


def test_CONTROLE_a_planta_passa_pela_PONTE():
    """Sem ponte a ordem não pesaria e o guarda de cima ficaria cego."""
    estagios = []
    for seed in _SEMENTES:
        rooms, meta = pdfvec_rooms.detect_rooms(
            "", 0, 100.0, None, bridge_gaps_m=1.2, return_meta=True,
            _segments=(_planta_com_portas(seed), W, H))
        assert rooms, seed
        assert meta["n_bridges"] > 0, (seed, meta)
        estagios.append(meta["stage"])
    assert "ponte_porta" in estagios, estagios
