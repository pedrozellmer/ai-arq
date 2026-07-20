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

E das melhorias de 19/07 (tarde) — dedupe + malha + validação por cota:
  6. faces aninhadas/sobrepostas (IoU > 0.8) são dedupadas pra UMA — vence o
     contorno com menos ponte; duplicatas idênticas viram uma;
  7. salas legítimas adjacentes (banda de parede no meio) NÃO são fundidas
     nem dedupadas;
  8. malha de anotação (4+ células dividindo a MESMA linha) é descartada,
     sem derrubar as salas reais da mesma prancha;
  9. cota perto de parede com valor batendo (±2%) valida a escala (>= 2
     independentes); cota LONGE ou com valor errado não valida.
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

# ─────────────── melhorias 19/07 (tarde): dedupe + malha + cotas ───────────────
from shapely.geometry import Polygon  # noqa: E402

from pdfvec_rooms import _dedupe_rooms, _drop_lattice  # noqa: E402
from pdfvec_cotas import match_cotas, parse_cota_value  # noqa: E402

print("== 6. faces aninhadas/sobrepostas são dedupadas pra UMA ==")


def _box_poly(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


L = LADO_10M_PT
# duas faces da MESMA sala, deslocadas meia parede (banda): IoU ~0.95
a_out = _box_poly(0.0, 0.0, L, L)                     # anel externo (com parede)
a_in = _box_poly(4.0, 4.0, L - 4.0, L - 4.0)          # anel interno (piso real)
dup_in = [(100.0, a_out, 0.10), (97.2, a_in, 0.0)]    # (m2, shell, fracao_ponte)
kept, n_dup = _dedupe_rooms(dup_in)
check("par aninhado vira 1 sala", len(kept) == 1 and n_dup == 1,
      f"-> {len(kept)} kept, {n_dup} dup")
if len(kept) == 1:
    check("vence o contorno mais honesto (menos ponte = anel interno)",
          abs(kept[0][0] - 97.2) < 0.01, f"-> área {kept[0][0]}")
# duplicata idêntica (mesma face duas vezes) => uma
kept, n_dup = _dedupe_rooms([(100.0, a_out, 0.0), (100.0, _box_poly(0, 0, L, L), 0.0)])
check("duplicata idêntica vira uma", len(kept) == 1 and n_dup == 1)
# sobreposição fraca (IoU ~0.45) NÃO é duplicata
b_shift = _box_poly(L * 0.38, 0.0, L * 1.38, L)
kept, n_dup = _dedupe_rooms([(100.0, a_out, 0.0), (100.0, b_shift, 0.0)])
check("sobreposição fraca não dedupa", len(kept) == 2 and n_dup == 0)

print("== 7. salas legítimas adjacentes (banda de parede) não são fundidas ==")
# duas salas de 4x4 m separadas por parede de 15 cm (cada sala tem a própria
# linha de face — nunca a MESMA linha)
S4 = 4.0 / M_PER_PT_100
B15 = 0.15 / M_PER_PT_100
segs = _snap_endpoints(_square(0.0, 0.0, S4) + _square(S4 + B15, 0.0, S4))
r = _rooms(segs)
check("2 salas (não fundidas, não dedupadas)", len(r) == 2, f"-> {len(r)}")
if len(r) == 2:
    check("áreas ~16 m² preservadas",
          all(abs(x["area_m2"] - 16.0) < 0.5 for x in r),
          f"-> {[x['area_m2'] for x in r]}")

print("== 8. malha de anotação (células coladas) cai; salas reais ficam ==")
# 6 células de 4x4 m dividindo as MESMAS linhas (grade de eixos/cotas sobre
# papel vazio) + as 2 salas reais do teste 7 (cada uma com contorno próprio)
grid = []
gy0, gy1 = 30.0 / M_PER_PT_100, 38.0 / M_PER_PT_100
gym = (gy0 + gy1) / 2.0
for k in range(4):                                   # verticais x=0,4,8,12 m
    x = k * S4
    grid.append(LineString([(x, gy0), (x, gy1)]))
for yy in (gy0, gym, gy1):                           # horizontais y=30,34,38 m
    grid.append(LineString([(0.0, yy), (3 * S4, yy)]))
segs = _snap_endpoints(grid + _square(0.0, 0.0, S4) + _square(S4 + B15, 0.0, S4))
r = _rooms(segs)
check("células da malha descartadas, 2 salas reais ficam", len(r) == 2,
      f"-> {len(r)} salas: {[x['area_m2'] for x in r]}")
if r:
    check("nenhuma sala veio da região da malha (y>30m)",
          all(x["centroid"][1] < gy0 for x in r))
# salvaguarda: prancha SÓ com malha não zera (abstém de abster)
r = _rooms(_snap_endpoints(list(grid)))
check("prancha só-malha: filtro se abstém (não zera)", len(r) == 6,
      f"-> {len(r)}")

print("== 9. cota valida parede; cota longe/errada não valida ==")
check("parse '350' -> 3,50 m (>=20 sem separador = cm)",
      parse_cota_value("350") == 3.5)
check("parse '1,20' -> 1,20 m", parse_cota_value("1,20") == 1.2)
check("parse '3.50' -> 3,50 m", parse_cota_value("3.50") == 3.5)
check("parse '120' -> 1,20 m", parse_cota_value("120") == 1.2)
check("parse '0,98m' -> 0,98 m (unidade explícita vence)",
      parse_cota_value("0,98m") == 0.98)
check("parse '35cm' -> 0,35 m", parse_cota_value("35cm") == 0.35)
check("parse '08' ambíguo -> None (número de item, não cota)",
      parse_cota_value("08") is None)
check("parse '1:50' não é cota", parse_cota_value("1:50") is None)

# parede horizontal de 3,50 m em 1:100 (99,2 pt), texto da cota 12 pt acima
W35 = 3.5 / M_PER_PT_100
paredes = [
    {"kind": "parede", "length_m": 3.5, "axis": "h",
     "span_pt": (0.0, W35), "p_pt": 100.0},
    {"kind": "parede", "length_m": 1.2, "axis": "v",
     "span_pt": (200.0, 200.0 + 1.2 / M_PER_PT_100), "p_pt": 300.0},
]
tok_ok = [
    {"text": "350", "value_m": 3.5, "center": (W35 / 2, 112.0)},
    {"text": "1,20", "value_m": 1.2, "center": (285.0, 217.0)},
]
m = match_cotas(tok_ok, paredes)
check("2 cotas perto batendo -> 2 matches (escala validada)", len(m) == 2,
      f"-> {m}")
# mesma cota, mas LONGE (200 pt acima da parede): não valida
tok_far = [{"text": "350", "value_m": 3.5, "center": (W35 / 2, 300.0)}]
check("cota longe não valida", len(match_cotas(tok_far, paredes)) == 0)
# valor fora dos ±2% não valida (3,70 numa parede de 3,50)
tok_bad = [{"text": "370", "value_m": 3.7, "center": (W35 / 2, 112.0)}]
check("valor fora de ±2% não valida", len(match_cotas(tok_bad, paredes)) == 0)
# 1 cota só = 1 match (a regra >=2 fica no validate_scale)
m = match_cotas(tok_ok[:1], paredes)
check("1 cota -> 1 match (>=2 exigidos pra validar ficam no validate_scale)",
      len(m) == 1)
# independência: 2 tokens iguais no MESMO lugar não podem validar 2x a mesma parede
tok_dup = [
    {"text": "350", "value_m": 3.5, "center": (W35 / 2, 112.0)},
    {"text": "350", "value_m": 3.5, "center": (W35 / 2, 112.0)},
]
m = match_cotas(tok_dup, [paredes[0]])
check("pareamento 1-pra-1: 2 tokens x 1 parede = 1 match", len(m) == 1)

print(f"\nRESULTADO: {_passed} passaram, {_failed} falharam")
sys.exit(1 if _failed else 0)
