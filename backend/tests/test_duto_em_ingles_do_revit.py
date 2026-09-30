# -*- coding: utf-8 -*-
"""Duto do Revit ("M-HVAC-DUCT") desenhado pelas duas faces mede pelo EIXO.

🩸 30/09/2026 — H34 do estudo do acervo. O Revit exporta o duto de
climatização num layer em INGLÊS, "M-HVAC-DUCT", com as duas faces. A correção
de linha dupla (`_corrigir_duto_linha_dupla`) só entrava em layer com "duto",
"ducto" (espanhol), "leito", "eletrocalha" ou "bandeja" — o inglês ficava de
fora e o layer somava as DUAS bordas (acervo: 1.423 m de face → 903 m de eixo).

Guardas:
- M-HVAC-DUCT com duas faces paralelas sai pelo eixo (metade);
- "conduct"/"product"/"CONDUCTOR" não viram duto (a trava de letra antes);
- P-PIPE continua como está (o tubo tem regra própria, com o diâmetro).
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dwg_extractor as dx  # noqa: E402


class W:
    """O mínimo que a correção consome: `length` em METRO, start/end crus."""

    def __init__(self, layer, start, end, uf=1.0):
        self.layer = layer
        self.start = start
        self.end = end
        self.curvo = False
        self.pontos = ()
        self.peso = 1.0
        self.length = math.dist(start, end) * uf


def _duas_faces(layer, comp=10.0, sep=0.4):
    return [W(layer, (0, 0), (comp, 0)), W(layer, (0, sep), (comp, sep))]


def _total(walls, layer):
    return sum(w.length for w in walls if w.layer == layer)


@pytest.mark.parametrize("layer", ["M-HVAC-DUCT", "M-HVAC-DUCT-SUPPLY", "DUCT", "Duct Return"])
def test_duto_em_ingles_sai_pelo_eixo(layer):
    corr, relato, _ = dx._corrigir_duto_linha_dupla(_duas_faces(layer))
    assert _total(corr, layer) == pytest.approx(10.0, rel=0.02), (relato, _total(corr, layer))


@pytest.mark.parametrize("layer", ["CONDUCTOR", "E-CONDUCT", "PRODUCT-DATA", "P-PIPE"])
def test_CONTROLE_nao_e_duto(layer):
    corr, _r, _ = dx._corrigir_duto_linha_dupla(_duas_faces(layer))
    assert _total(corr, layer) == pytest.approx(20.0), layer


def test_CONTROLE_duto_em_portugues_continua():
    corr, _r, _ = dx._corrigir_duto_linha_dupla(_duas_faces("DUTO-INSUFLAMENTO"))
    assert _total(corr, "DUTO-INSUFLAMENTO") == pytest.approx(10.0, rel=0.02)
