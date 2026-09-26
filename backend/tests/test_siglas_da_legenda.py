# -*- coding: utf-8 -*-
"""SIGLA → NOME lido da legenda da própria prancha e entregue à IA.

🩸 25/09/2026 — job `53f0483f`: a tabela de acessórios dizia TH-90º = TÊ
HORIZONTAL, CH-90º = CURVA HORIZONTAL, CZ-90º = CRUZETA; a IA, lendo os textos
soltos, trocou os três em quatro releituras. 🪤 Medido no acervo: "PD=255cm",
"A=4,20m²" são medida, e "RALO"/"BACIA" ao lado de um texto são rótulo.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from dwg_extractor import DXFExtraction, TextAnnotation  # noqa: E402

H = 100.0


def _T(texto, x, y, h=H):
    return TextAnnotation(layer="LEGENDA", text=texto, position=(x, y), height=h)


def _tabela():
    return [
        _T("CH-90º", 24368, 4189), _T("CURVA HORIZONTAL 90°", 25584, 4192),
        _T("TH-90º", 28625, 4189), _T("TÊ HORIZONTAL 90°", 29853, 4188),
        _T("CZ-90º", 28622, 3675), _T("CRUZETA HORIZONTAL 90°", 29853, 3673),
        _T("L = LEITO PARA CABOS", 27435, 5544),
    ]


def test_a_tabela_da_legenda_vira_dicionario():
    s = dx.siglas_da_legenda(_tabela())
    assert s["TH-90º"] == "TÊ HORIZONTAL 90°"
    assert s["CH-90º"] == "CURVA HORIZONTAL 90°"
    assert s["CZ-90º"] == "CRUZETA HORIZONTAL 90°"
    assert s["L"] == "LEITO PARA CABOS"


def test_a_ia_recebe_o_dicionario():
    ex = DXFExtraction(filename="x.dxf", blocks=[], walls=[], hatches=[], texts=_tabela(),
                       layers=[], dimensions=[], metadata={})
    txt = ex.to_structured_prompt()
    assert "SIGLAS DA LEGENDA DESTA PRANCHA" in txt and "TH-90º = TÊ HORIZONTAL 90°" in txt


@pytest.mark.parametrize("textos, sigla", [
    ([_T("PD=255cm", 0, 0)], "PD"),                                    # medida no formato "="
    ([_T("A=4,20m²", 0, 0)], "A"),
    ([_T("H=70cm ABAIXO DA BORDA DA PISCINA", 0, 0)], "H"),          # medida + frase (acervo)
    ([_T("RALO", 0, 0), _T("- EXISTENTE NO LOCAL", 300, 0)], "RALO"),  # rótulo, não sigla
    ([_T("T1", 0, 0), _T("h 1,10 2,20 3,30", 300, 0)], "T1"),          # "nome" que é número
    ([_T("CH-90º", 0, 0), _T("CURVA HORIZONTAL 90°", 300, 800)], "CH-90º"),   # outra linha
    ([_T("CH-90º", 0, 0), _T("CURVA HORIZONTAL 90°", 5000, 0)], "CH-90º"),    # longe demais
])
def test_CONTROLE_o_que_nao_e_sigla_com_nome(textos, sigla):
    assert sigla not in dx.siglas_da_legenda(textos)


def test_vale_o_nome_mais_perto():
    s = dx.siglas_da_legenda([_T("CH-90º", 0, 0), _T("CURVA HORIZONTAL 90°", 1200, 0),
                              _T("NOTA DE OUTRA COLUNA", 2000, 0)])
    assert s["CH-90º"] == "CURVA HORIZONTAL 90°"


def test_CONTROLE_sem_legenda_sem_secao():
    ex = DXFExtraction(filename="x.dxf", blocks=[], walls=[], hatches=[],
                       texts=[_T("PLANTA BAIXA", 0, 0)], layers=[], dimensions=[], metadata={})
    assert "SIGLAS DA LEGENDA" not in ex.to_structured_prompt()
