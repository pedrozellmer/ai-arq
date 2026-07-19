# -*- coding: utf-8 -*-
"""Rede de segurança — fechamento de ambientes do motor vetorial de PDF
(pdfvec_rooms.py), com geometria SINTÉTICA (zero PDF, zero IA, roda em <1s):
`python tests/test_pdfvec_rooms.py`.

Trava os comportamentos das melhorias de 19/07:
  1. snap de pontas fecha micro-gap de plotagem (o unary_union sozinho não);
  2. ponte de vão de porta fecha o contorno SEM inflar a área além do honesto;
  3. guarda BRIDGE_PERIM_FRAC: "sala" que só existe por causa das pontes é
     descartada (regra nº 1 do produto: na dúvida, abster);
  4. pontas do MESMO segmento nunca se auto-ligam (leader não vira laço).
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from shapely.geometry import LineString  # noqa: E402

from pdfvec_rooms import (  # noqa: E402
    PT_TO_M,
    _bridge_dangling,
    _middle_layer,
    _polygonize_faces,
    _snap_endpoints,
)

_passed = 0
_failed = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global _passed, _failed
    if ok:
        _passed += 1
        print(f"  ok  {name}")
    else:
        _failed += 1
        print(f"FALHOU {name} {extra}")


M_PER_PT_100 = PT_TO_M * 100.0   # escala 1:100


def _rooms(segs, bridge_pt=0.0, min_m2=1.5, max_m2=500.0):
    faces, bridges = _polygonize_faces(segs, bridge_gaps_pt=bridge_pt)
    return _middle_layer(faces, M_PER_PT_100, min_m2, max_m2, bridges=bridges)


def _square(x0, y0, lado_pt, gap_pt=0.0):
    """Quadrado como 4 segmentos; gap_pt abre um vão no meio do lado de baixo."""
    x1, y1 = x0 + lado_pt, y0 + lado_pt
    segs = [
        LineString([(x1, y0), (x1, y1)]),
        LineString([(x1, y1), (x0, y1)]),
        LineString([(x0, y1), (x0, y0)]),
    ]
    if gap_pt > 0:
        meio = (x0 + x1) / 2.0
        segs.append(LineString([(x0, y0), (meio - gap_pt / 2.0, y0)]))
        segs.append(LineString([(meio + gap_pt / 2.0, y0), (x1, y0)]))
    else:
        segs.append(LineString([(x0, y0), (x1, y0)]))
    return segs


# Quadrado de 10 m reais em 1:100 = 283,5 pt de lado (~100 m²).
LADO_10M_PT = 10.0 / M_PER_PT_100          # 283,46 pt
PORTA_09M_PT = 0.9 / M_PER_PT_100          # 25,5 pt
PONTE_12M_PT = 1.2 / M_PER_PT_100          # 34,0 pt

print("== 1. snap + micro-ponte fecham micro-gap de plotagem ==")
# Vão de 0,3 pt num canto: arredondamento CAD->PDF típico. Sem snap/micro o
# polygonize não fecha nada (comportamento antigo = 0 salas com escala boa).
L = LADO_10M_PT
segs = [
    LineString([(0.0, 0.3), (0.0, L)]),   # começa 0,3pt acima do canto
    LineString([(0.0, L), (L, L)]),
    LineString([(L, L), (L, 0.0)]),
    LineString([(L, 0.0), (0.0, 0.0)]),
]
faces_old, _ = ( [], [] )
from shapely.ops import polygonize as _pz, unary_union as _uu  # noqa: E402
from shapely.geometry import MultiLineString as _MLS  # noqa: E402
faces_old = list(_pz(_uu(_MLS([list(s.coords) for s in segs]))))
check("sem snap/micro: polygonize não fecha nada (comportamento antigo)",
      len(faces_old) == 0)
r = _rooms(_snap_endpoints(segs))
check("com snap+micro: fecha 1 sala", len(r) == 1, f"-> {r}")
if r:
    check("área ~100 m² (erro <1%)", abs(r[0]["area_m2"] - 100.0) < 1.0,
          f"-> {r[0]['area_m2']}")

print("== 2. ponte de porta fecha vão de 0,9 m sem inflar área ==")
# Vão de 0,9 m (25,5 pt) no lado de baixo. Puro (só micro-ponte de 1pt):
# aberto. Com ponte de porta (1,2 m = 34 pt): fecha, e a área inclui o vão
# (o piso passa por baixo da porta).
segs = _snap_endpoints(_square(0.0, 0.0, LADO_10M_PT, gap_pt=PORTA_09M_PT))
check("puro: vão de porta deixa 0 salas", len(_rooms(segs)) == 0)
r = _rooms(segs, bridge_pt=PONTE_12M_PT)
check("ponteado: fecha 1 sala", len(r) == 1, f"-> {r}")
if r:
    check("área segue ~100 m² (ponte não inventa área)",
          abs(r[0]["area_m2"] - 100.0) < 2.0, f"-> {r[0]['area_m2']}")

print("== 3. guarda de honestidade: lado inteiro faltando != sala ==")
# Retângulo 12x3 m SEM o lado de baixo: a ponte teria que fabricar 40% do
# perímetro. _bridge_dangling até liga, mas a guarda descarta a "sala".
W12, H3 = 12.0 / M_PER_PT_100, 3.0 / M_PER_PT_100
segs = _snap_endpoints([
    LineString([(0.0, 0.0), (0.0, H3)]),
    LineString([(0.0, H3), (W12, H3)]),
    LineString([(W12, H3), (W12, 0.0)]),
])
r = _rooms(segs, bridge_pt=W12 + 10.0)
check("sala fabricada por ponte é descartada (abstém)", len(r) == 0, f"-> {r}")

print("== 4. leader isolado não vira laço (auto-ponte proibida) ==")
bridges = _bridge_dangling(_snap_endpoints([LineString([(0.0, 0.0), (30.0, 0.0)])]), 50.0)
check("segmento sozinho: 0 pontes", len(bridges) == 0, f"-> {bridges}")

print("== 5. sala já fechada não muda com ponte disponível ==")
segs = _snap_endpoints(_square(0.0, 0.0, LADO_10M_PT))
r_puro = _rooms(segs)
r_ponte = _rooms(segs, bridge_pt=PONTE_12M_PT)
check("mesma contagem", len(r_puro) == len(r_ponte) == 1)
if r_puro and r_ponte:
    check("mesma área", abs(r_puro[0]["area_m2"] - r_ponte[0]["area_m2"]) < 0.01)

print(f"\nRESULTADO: {_passed} passaram, {_failed} falharam")
sys.exit(1 if _failed else 0)
