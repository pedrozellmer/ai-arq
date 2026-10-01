# -*- coding: utf-8 -*-
"""Layer de parede com 3.000 a 6.000 trechos também mede pelo eixo.

🩸 01/10/2026 — H73b do estudo do acervo. Acima do teto do duto (3.000
trechos) o layer era PULADO inteiro: o térreo de uma escola, com 3.070 trechos
de parede composta, saía 2.746 m (pelo eixo, 816). Só na parede o teto vai a
6.000; o duto segue no dele.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _paredes(layer, n_paredes, esp=0.15, comp=2.0):
    """n paredes de duas faces, lado a lado (2 trechos cada)."""
    ws = []
    for i in range(n_paredes):
        y = i * 1.0
        for dy in (0.0, esp):
            ws.append(dx.WallSegment(layer=layer, length=comp,
                                     start=(0.0, y + dy), end=(comp, y + dy)))
    return ws


def _soma(ws, layer):
    return sum(w.length for w in ws if w.layer == layer)


def test_o_caso_parede_com_3500_trechos_mede_pelo_eixo():
    ws = _paredes("A-WALL", 1750)                      # 3.500 trechos
    novos, _rel = dx._corrigir_parede_linha_dupla(ws, 1.0)
    assert _soma(novos, "A-WALL") == pytest.approx(1750 * 2.0, rel=0.01)


def test_CONTROLE_acima_de_6000_continua_pulado():
    ws = _paredes("A-WALL", 3100)                      # 6.200 trechos
    novos, _rel = dx._corrigir_parede_linha_dupla(ws, 1.0)
    assert _soma(novos, "A-WALL") == pytest.approx(3100 * 2 * 2.0)


def test_CONTROLE_o_duto_segue_no_teto_dele():
    ws = _paredes("DUTO AR", 1750, esp=0.30)           # 3.500 trechos de duto
    novos, _rel, _res = dx._corrigir_duto_linha_dupla(ws, 1.0)
    assert _soma(novos, "DUTO AR") == pytest.approx(1750 * 2 * 2.0)


def test_CONTROLE_abaixo_de_3000_igual_a_antes():
    ws = _paredes("A-WALL", 1000)
    novos, _rel = dx._corrigir_parede_linha_dupla(ws, 1.0)
    assert _soma(novos, "A-WALL") == pytest.approx(1000 * 2.0, rel=0.01)
