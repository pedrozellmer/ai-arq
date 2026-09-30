# -*- coding: utf-8 -*-
"""A POLILINHA "pesada" (2D/3D, com VERTEX) também entra pelos lados.

🩸 30/09/2026 — H52 do estudo do acervo. Num projeto de cliente, o layer de
alvenaria tinha 129 LINE + 10 LWPOLYLINE (218 m) e 5 POLYLINE (239 m): a maior,
uma parede desenhada pelo contorno — vai 71 m e volta a 15 cm. A LWPOLYLINE
guarda os lados (`pontos`) desde 25/09; a POLYLINE não: virava UMA reta do 1º
ao último vértice (15 cm). Nem o eixo da parede, nem o tubo em face dupla, nem a
régua da espessura viam as faces — os 239 m entraram como as duas faces somadas.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402

_CONTORNO = [(0, 0), (71, 0), (71, 0.15), (0, 0.15)]          # vai 71 m e volta a 15 cm


def _ler(tmp_path, desenha, insunits=6, doc=None):
    d = doc or ezdxf.new("R2018")
    d.header["$INSUNITS"] = insunits
    desenha(d.modelspace())
    p = str(tmp_path / "planta.dxf")
    d.saveas(p)
    return dx.extract_dxf(p)


def _do_layer(ex, layer):
    return [w for w in ex.walls if w.layer == layer]


# ── o caso ─────────────────────────────────────────────────────────────────────
def test_o_caso_contorno_da_parede_em_polilinha_2d_mede_o_eixo(tmp_path):
    ex = _ler(tmp_path, lambda m: m.add_polyline2d(_CONTORNO, dxfattribs={"layer": "08 - ALVENARIA 1"}))
    assert ex.get_walls_by_layer()["08 - ALVENARIA 1"] == pytest.approx(71.0, abs=0.1), \
        "nunca 142 (as duas faces)"
    assert "08 - ALVENARIA 1" in (ex.metadata.get("parede_linha_dupla") or "")


def test_mesma_coisa_que_a_lwpolyline(tmp_path):
    lw = _ler(tmp_path, lambda m: m.add_lwpolyline(_CONTORNO, dxfattribs={"layer": "ALVENARIA"}))
    pl = _ler(tmp_path, lambda m: m.add_polyline2d(_CONTORNO, dxfattribs={"layer": "ALVENARIA"}))
    assert pl.get_walls_by_layer()["ALVENARIA"] == pytest.approx(lw.get_walls_by_layer()["ALVENARIA"])


def test_polilinha_3d_com_z_lixo_vai_no_plano(tmp_path):
    pts = [(x, y, z) for (x, y), z in zip(_CONTORNO, (16.6, -7.1, 3.0, 0.0))]
    ex = _ler(tmp_path, lambda m: m.add_polyline3d(pts, dxfattribs={"layer": "ALVENARIA"}))
    assert ex.get_walls_by_layer()["ALVENARIA"] == pytest.approx(71.0, abs=0.1)
    (w,) = _do_layer(ex, "ALVENARIA")
    assert all(len(p) == 3 and p[2] == 0.0 for p in w.pontos), w.pontos   # (x, y, sem arco)


def test_polilinha_fechada_repete_o_primeiro_vertice(tmp_path):
    q = [(0, 0), (10, 0), (10, 0.15), (0, 0.15)]
    ex = _ler(tmp_path, lambda m: m.add_polyline2d(q, close=True, dxfattribs={"layer": "A-WALL"}))
    (w,) = _do_layer(ex, "A-WALL")
    assert len(w.pontos) == 5 and w.pontos[0][:2] == w.pontos[-1][:2], w.pontos
    assert ex.get_walls_by_layer()["A-WALL"] == pytest.approx(10.0, abs=0.05)


def test_o_tubo_do_revit_em_polilinha_tambem_e_face_dupla(tmp_path):
    def d(m):
        m.add_polyline2d([(0, 0), (20000, 0), (20000, 150), (0, 150)], dxfattribs={"layer": "P-PIPE"})
        m.add_text("ø150", dxfattribs={"height": 100, "insert": (5000, 400)})
    ex = _ler(tmp_path, d, insunits=4)
    assert "P-PIPE" in (ex.metadata.get("tubos_em_face_dupla") or {}), ex.metadata.get("tubos_em_face_dupla")


def test_o_duto_em_polilinha_tambem_mede_o_eixo(tmp_path):
    ex = _ler(tmp_path, lambda m: m.add_polyline2d([(0, 0), (10, 0), (10, 0.5), (0, 0.5)],
                                                   dxfattribs={"layer": "DUTO AR"}))
    assert ex.get_walls_by_layer()["DUTO AR"] == pytest.approx(10.0, abs=0.1)


def test_o_layer_que_a_legenda_aponta_tambem(tmp_path):
    from test_corte_e_leito_pela_legenda import _doc, _legenda
    doc, msp = _doc()
    _legenda(msp)                                         # "K-04" = leito, pela legenda
    ex = _ler(tmp_path, lambda m: m.add_polyline2d([(2, 2), (12, 2), (12, 2.3), (2, 2.3)],
                                                   dxfattribs={"layer": "K-04"}), doc=doc)
    assert any(len(w.pontos) == 4 for w in _do_layer(ex, "K-04")), [w.pontos for w in _do_layer(ex, "K-04")]


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_layer_que_nao_e_candidato_fica_sem_lados(tmp_path):
    ex = _ler(tmp_path, lambda m: m.add_polyline2d(_CONTORNO, dxfattribs={"layer": "MOBILIARIO"}))
    (w,) = _do_layer(ex, "MOBILIARIO")
    assert w.pontos == ()
    assert ex.get_walls_by_layer()["MOBILIARIO"] == pytest.approx(142.15, abs=0.01)


def test_CONTROLE_lado_em_arco_nao_pareia(tmp_path):
    # o lado de volta é um ARCO (bulge): não é face paralela, não pareia
    def d(m):
        m.add_polyline2d([(0, 0, 0, 0, 0), (10, 0, 0, 0, 0), (10, 0.15, 0, 0, 0.2), (0, 0.15, 0, 0, 0)],
                         format="xyseb", dxfattribs={"layer": "ALVENARIA"})
    ex = _ler(tmp_path, d)
    (w,) = _do_layer(ex, "ALVENARIA")
    assert w.pontos[2][2] == pytest.approx(0.2), w.pontos
    assert not ex.metadata.get("parede_linha_dupla"), ex.metadata.get("parede_linha_dupla")


def test_CONTROLE_malha_nao_e_caminho(tmp_path):
    def d(m):
        pf = m.add_polyface(dxfattribs={"layer": "ALVENARIA"})
        pf.append_face([(0, 0, 0), (71, 0, 0), (71, 0.15, 0), (0, 0.15, 0)])
    ex = _ler(tmp_path, d)
    assert all(w.pontos == () for w in _do_layer(ex, "ALVENARIA"))
