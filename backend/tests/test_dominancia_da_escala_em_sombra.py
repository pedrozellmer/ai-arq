# -*- coding: utf-8 -*-
"""A dominância da escala é MEDIDA em sombra — e a prova segue a de sempre.

📏 28/09/2026 (estudo de leitura, D7b). ">= 2 casamentos" não separa a
escala certa da errada (na a3366fbb_11 as erradas juntavam 2 a 4). A
declarada passa a ser comparada com as escalas padrão nos mesmos elementos,
e o resultado vai pro log. Não decide: nas páginas locais a dominância
derrubou uma escala certa (a3366fbb_10) e não pegou nenhuma errada.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import pdfvec_cotas as pc  # noqa: E402


def _cenario(monkeypatch, certas, coincid, declarada):
    """`certas` paredes cuja cota bate a 1:100; `coincid` cuja cota bate a
    1:50. Tudo em pontos; `length_m` na escala DECLARADA (como a produção)."""
    walls, toks = [], []
    for k in range(certas + coincid):
        comp_pt = 60.0 + 17.0 * k
        esc_da_cota = 100.0 if k < certas else 50.0
        y = 100.0 * k
        walls.append({"length_m": comp_pt * pc.PT_TO_M * declarada, "axis": "h",
                      "span_pt": (0.0, comp_pt), "p_pt": y})
        toks.append({"text": "x", "value_m": round(comp_pt * pc.PT_TO_M * esc_da_cota, 4),
                     "center": (comp_pt / 2, y + 8.0)})
    monkeypatch.setattr(pc, "extract_cota_tokens", lambda *a, **k: toks)
    return pc.validate_scale("x.pdf", 0, declarada, walls=walls, rooms=[])


def test_a_certa_com_folga_domina(monkeypatch):
    r = _cenario(monkeypatch, certas=6, coincid=2, declarada=100.0)
    assert r["n_matches"] == 6 and r["segunda"] == [50, 2] and r["dominante"], r


def test_a_errada_com_2_casamentos_nao_domina(monkeypatch):
    # declarada 1:50: bate 2 por coincidência, mas 1:100 bate 6
    r = _cenario(monkeypatch, certas=6, coincid=2, declarada=50.0)
    assert r["n_matches"] == 2 and r["segunda"] == [100, 6] and not r["dominante"], r


def test_em_sombra_a_prova_segue_a_de_sempre(monkeypatch):
    # a mesma errada acima: não domina, mas a prova continua sendo ">= 2"
    assert _cenario(monkeypatch, certas=6, coincid=2, declarada=50.0)["validada"]


def test_o_dobro_exato_domina_e_menos_nao(monkeypatch):
    assert _cenario(monkeypatch, certas=4, coincid=2, declarada=100.0)["dominante"]
    assert not _cenario(monkeypatch, certas=3, coincid=2, declarada=100.0)["dominante"]


def test_CONTROLE_sem_outra_escala_basta_2(monkeypatch):
    r = _cenario(monkeypatch, certas=2, coincid=0, declarada=100.0)
    assert r["segunda"] is None and r["dominante"] and r["validada"], r


def test_CONTROLE_com_1_casamento_nem_compara(monkeypatch):
    r = _cenario(monkeypatch, certas=1, coincid=0, declarada=100.0)
    assert r["segunda"] is None and not r["dominante"] and not r["validada"], r
