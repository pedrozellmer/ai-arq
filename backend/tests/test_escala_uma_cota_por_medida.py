# -*- coding: utf-8 -*-
"""A prova de escala do PDF conta UMA vez cada medida da sala.

📏 28/09/2026 (estudo de leitura, D7a). A sala vira 4 arestas, e as duas
paralelas têm o mesmo comprimento. A cota da largura escrita dos dois lados
("2.15" em cima e embaixo da sala de 2,178, na a3366fbb_11 a 1:25) valia 2
casamentos "independentes" — e 2 casamentos carimbam a escala como PROVADA.
Escalas erradas passavam assim.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import pdfvec_cotas as pc  # noqa: E402

M_PT = pc.PT_TO_M * 100.0          # 1:100
LARG, FUNDO = 2.178, 3.40          # m
W, D = LARG / M_PT, FUNDO / M_PT   # pt


def _sala(x0=0.0, y0=0.0):
    return {"bbox": (x0, y0, x0 + W, y0 + D)}


def _cota(valor, x, y):
    return {"text": f"{valor:.2f}", "value_m": valor, "center": (x, y)}


def test_a_largura_escrita_dos_dois_lados_conta_uma_vez():
    els = pc._elements_from_rooms([_sala()], M_PT)
    toks = [_cota(2.18, W / 2, -10.0), _cota(2.18, W / 2, D + 10.0)]
    assert len(pc.match_cotas(toks, els)) == 1


def test_CONTROLE_largura_e_fundo_da_mesma_sala_sao_duas_medidas():
    els = pc._elements_from_rooms([_sala()], M_PT)
    toks = [_cota(2.18, W / 2, -10.0), _cota(3.40, -10.0, D / 2)]
    assert len(pc.match_cotas(toks, els)) == 2


def test_CONTROLE_duas_salas_iguais_sao_duas_medidas():
    els = pc._elements_from_rooms([_sala(), _sala(x0=W + 200.0)], M_PT)
    toks = [_cota(2.18, W / 2, -10.0), _cota(2.18, W + 200.0 + W / 2, -10.0)]
    assert len(pc.match_cotas(toks, els)) == 2


def test_CONTROLE_parede_nao_tem_grupo():
    # duas paredes diferentes do mesmo comprimento, cada uma com a sua cota
    L = 3.5 / M_PT
    paredes = [{"kind": "parede", "length_m": 3.5, "axis": "h", "span_pt": (0.0, L), "p_pt": 100.0},
               {"kind": "parede", "length_m": 3.5, "axis": "h", "span_pt": (0.0, L), "p_pt": 400.0}]
    toks = [_cota(3.5, L / 2, 112.0), _cota(3.5, L / 2, 412.0)]
    assert len(pc.match_cotas(toks, paredes)) == 2
