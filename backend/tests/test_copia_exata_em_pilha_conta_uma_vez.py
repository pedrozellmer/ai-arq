# -*- coding: utf-8 -*-
"""Cópia exata em pilha (copiar-colar no mesmo lugar) conta uma vez.

🩸 01/10/2026 — H84 do estudo do acervo. A mesma treliça colada 16× no mesmo
lugar somava 1.099 m (é 68,7 m); difusores colados uns sobre os outros; a
rampa com as 40 linhas 2×. Só a cópia do MESMO tipo (LINE com as mesmas
pontas, polilinha ABERTA com os mesmos vértices) — o lado comum de figuras
FECHADAS vizinhas é legítimo e fica.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402

TRELICA = [(0, 0), (2.7, 1.5), (0, 3.0), (2.7, 4.5), (0, 6.0), (2.7, 7.5), (0, 9.0),
           (2.7, 10.5), (0, 12.0), (2.7, 14.0)]


def _ler(tmp_path, desenha, insunits=6):
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = insunits
    desenha(d.modelspace())
    p = str(tmp_path / "pilha.dxf")
    d.saveas(p)
    return dx.extract_dxf(p)


def _comp(pts):
    return sum(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(pts, pts[1:]))


def test_o_caso_a_trelica_colada_16_vezes(tmp_path):
    ex = _ler(tmp_path, lambda m: [m.add_lwpolyline(TRELICA, dxfattribs={"layer": "TRELICAS"})
                                   for _ in range(16)])
    assert ex.get_walls_by_layer()["TRELICAS"] == pytest.approx(_comp(TRELICA), rel=1e-6)
    assert ex.metadata["copias_exatas"]["TRELICAS"]["n"] == 15


def test_pilha_de_linhas_e_a_linha_ao_contrario(tmp_path):
    def d(m):
        for i in range(10):
            for _ in range(3):
                m.add_line((0, i), (5, i), dxfattribs={"layer": "AC-BOCAL"})
            m.add_line((5, i), (0, i), dxfattribs={"layer": "AC-BOCAL"})   # ao contrário
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["AC-BOCAL"] == pytest.approx(50.0)


def test_em_milimetro_a_tolerancia_e_de_1_mm_de_verdade(tmp_path):
    def d(m):
        m.add_line((0, 0), (5000, 0), dxfattribs={"layer": "RAMPA"})
        m.add_line((0.4, 0), (5000.4, 0), dxfattribs={"layer": "RAMPA"})   # 0,4 mm: a mesma
    ex = _ler(tmp_path, d, insunits=4)
    assert ex.get_walls_by_layer()["RAMPA"] == pytest.approx(5.0, rel=1e-3)


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_figuras_fechadas_vizinhas_dividem_o_lado(tmp_path):
    """Duas salas fechadas com uma parede em comum: o rodapé dos dois lados."""
    def d(m):
        m.add_lwpolyline([(0, 0), (4, 0), (4, 3), (0, 3)], close=True, dxfattribs={"layer": "RODAPE"})
        m.add_lwpolyline([(4, 0), (8, 0), (8, 3), (4, 3)], close=True, dxfattribs={"layer": "RODAPE"})
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["RODAPE"] == pytest.approx(28.0)


def test_CONTROLE_fechada_identica_tambem_fica(tmp_path):
    """Polilinha FECHADA não entra na régua, nem idêntica (pode ser rodapé e
    forro do mesmo ambiente no mesmo layer genérico)."""
    def d(m):
        for _ in range(2):
            m.add_lwpolyline([(0, 0), (4, 0), (4, 3), (0, 3)], close=True, dxfattribs={"layer": "AMB"})
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["AMB"] == pytest.approx(28.0)


def test_CONTROLE_linha_sobre_aresta_de_fechada_fica(tmp_path):
    def d(m):
        m.add_lwpolyline([(0, 0), (4, 0), (4, 3), (0, 3)], close=True, dxfattribs={"layer": "PORTAO"})
        m.add_line((0, 0), (4, 0), dxfattribs={"layer": "PORTAO"})
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["PORTAO"] == pytest.approx(18.0)


def test_CONTROLE_a_mesma_linha_em_dois_layers_conta_nos_dois(tmp_path):
    def d(m):
        m.add_line((0, 0), (5, 0), dxfattribs={"layer": "AGUA FRIA"})
        m.add_line((0, 0), (5, 0), dxfattribs={"layer": "AGUA QUENTE"})
    w = _ler(tmp_path, d).get_walls_by_layer()
    assert w["AGUA FRIA"] == pytest.approx(5.0) and w["AGUA QUENTE"] == pytest.approx(5.0)


def test_CONTROLE_linha_paralela_a_2_mm_e_outra(tmp_path):
    def d(m):
        m.add_line((0, 0), (5, 0), dxfattribs={"layer": "REDE"})
        m.add_line((0, 0.002), (5, 0.002), dxfattribs={"layer": "REDE"})
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["REDE"] == pytest.approx(10.0)
    assert not ex.metadata.get("copias_exatas")


def test_CONTROLE_polilinha_aberta_que_so_comeca_igual(tmp_path):
    def d(m):
        m.add_lwpolyline([(0, 0), (5, 0), (5, 5)], dxfattribs={"layer": "REDE"})
        m.add_lwpolyline([(0, 0), (5, 0), (9, 0)], dxfattribs={"layer": "REDE"})
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["REDE"] == pytest.approx(19.0)
