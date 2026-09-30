# -*- coding: utf-8 -*-
"""O "Ø n" do DESENHO não vira a coluna BITOLA do quadro de aço, nem a bitola
de uma linha dele.

🩸 30/09/2026 — H37 do estudo do acervo. Resumo de aço do Eberick (5 resumos
lado a lado na folha): na altura do cabeçalho caiu um "Ø 6.3" do desenho. Ele
casava o título de bitola (`\\bø\\b`) e, por ser o último, roubou a coluna do
"BIT" de verdade. A borda do quadro alargou, e na linha "50A 12.5 411 396" o
"Ø 10" da planta virou a bitola: Ø10 396 kg, que passa na massa linear
(396 / (411 × 0,617) = 1,56, dentro de 0,70–1,70).
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

from dwg_extractor import TextAnnotation as T  # noqa: E402
import structural_extractor as se  # noqa: E402
from test_borda_do_cabecalho_de_aco import _EBERICK  # noqa: E402

_CERTO = {8.0: 1202.0, 10.0: 1114.0, 12.5: 3781.0, 16.0: 11846.0, 20.0: 309.0}
_Y_CAB, _Y_12_5 = 41.906, 41.156


def _textos(linhas):
    return [T(lay, txt, (x, y), h) for lay, txt, x, y, h in linhas]


def _kg(r):
    out: dict = {}
    for b in r["por_bitola"]:
        out.setdefault(b["bitola_mm"], []).append(b["kg"])
    return out


def test_o_caso_o_o_do_desenho_no_cabecalho_nao_rouba_a_coluna():
    extra = [("1", "Ø 6.3", 9.0, _Y_CAB, 0.1),          # marcação do desenho, na altura do "BIT"
             ("1", "Ø 10", 8.5, _Y_12_5, 0.1)]          # e o "Ø 10" da planta na linha do Ø12,5
    r = se.parse_steel_table(_textos(_EBERICK + extra))
    assert r, r
    assert _kg(r) == {b: [kg] for b, kg in _CERTO.items()}, r
    assert r["total_kg"] == 18252.0 and r["confiavel"] is True, r


def test_o_o_do_desenho_dentro_da_borda_nao_vira_a_bitola_da_linha():
    # cabeçalho certo, mas o "Ø 10" da planta cai DENTRO da borda do quadro
    r = se.parse_steel_table(_textos(_EBERICK + [("1", "Ø 10", 7.5, _Y_12_5, 0.1)]))
    assert _kg(r) == {b: [kg] for b, kg in _CERTO.items()}, r


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def _quadro(cab_bitola, celulas_bitola, com_bitola_no_cab=True):
    """Quadro simples: BITOLA | COMPR (m) | PESO (kg), 3 linhas que batem na NBR 7480."""
    h = 2.5
    linhas = [("0", "QUADRO DE AÇO", 0, 20, h), ("0", "COMPR (m)", 40, 10, h), ("0", "PESO (kg)", 70, 10, h)]
    if com_bitola_no_cab:
        linhas.append(("0", cab_bitola, 10, 10, h))
    for i, (b, comp, kg) in enumerate(((celulas_bitola[0], 100.0, 39.5),
                                       (celulas_bitola[1], 200.0, 123.4),
                                       (celulas_bitola[2], 50.0, 48.2))):
        y = 5 - 4 * i
        linhas += [("0", b, 10, y, h), ("0", "%g" % comp, 40, y, h), ("0", "%g" % kg, 70, y, h)]
    return _textos(linhas)


@pytest.mark.parametrize("cab", ["BITOLA", "BIT", "Ø", "Ø (mm)", "BITOLA Ø", "DIÂM."])
def test_CONTROLE_titulo_de_bitola_continua_titulo(cab):
    r = se.parse_steel_table(_quadro(cab, ("8", "10", "12.5")))
    assert _kg(r) == {8.0: [39.5], 10.0: [123.4], 12.5: [48.2]}, r


def test_CONTROLE_celula_com_o_na_coluna_da_bitola_continua_lida():
    r = se.parse_steel_table(_quadro("BITOLA", ("Ø8", "Ø 10", "%%c12.5")))
    assert _kg(r) == {8.0: [39.5], 10.0: [123.4], 12.5: [48.2]}, r


def test_CONTROLE_sem_coluna_de_bitola_o_o_da_linha_ainda_vale():
    # sem título de bitola no cabeçalho: a linha só se lê pelo "Ø n" dela
    r = se.parse_steel_table(_quadro("", ("Ø8", "Ø 10", "Ø12.5"), com_bitola_no_cab=False))
    assert _kg(r) == {8.0: [39.5], 10.0: [123.4], 12.5: [48.2]}, r
