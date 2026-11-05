# -*- coding: utf-8 -*-
"""O aviso de fonte = anotação só diz "o comprimento foi medido" em linha de metro.

🩸 05/11/2026: "Fornecimento e instalação de split — 1 un" com "o comprimento foi
medido, mas do desenho da anotação" — a fonte era a nota "split a instalar".
📏 30 dias de cliente: 869 linhas em 56 projetos fora do metro.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine_rules as er  # noqa: E402

_SRC = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "main.py"), encoding="utf-8").read()


@pytest.mark.parametrize("u", ["m", "ml", "ML", " m "])
def test_em_metro_a_frase_segue_a_de_antes(u):
    f = er.frase_da_fonte_anotacao(u)
    assert f.startswith(er.MARCA_FONTE_ANOTACAO)
    assert "o comprimento foi medido, mas do desenho da anotação" in f


@pytest.mark.parametrize("u", ["un", "m²", "m2", "vb", "m³", "kg", "", None])
def test_fora_do_metro_nao_diz_que_mediu(u):
    f = er.frase_da_fonte_anotacao(u)
    assert f.startswith(er.MARCA_FONTE_ANOTACAO), "o prefixo é o que a revisão mostra"
    assert "medido" not in f and "comprimento" not in f
    assert "não de medição" in f and "Confirme o serviço e a quantidade." in f


def test_a_frase_nova_nao_vira_nome_de_layer():
    """A observação é relida por `_layers_da_obs`: o aviso não pode ganhar layer."""
    import main as m
    for u in ("un", "m"):
        obs = er.frase_da_fonte_anotacao(u) + " Fonte: texto 'split a instalar' no layer COTA."
        assert m._layers_da_obs(obs) == ["COTA"], m._layers_da_obs(obs)


def test_o_motor_usa_a_funcao_com_a_unidade_normalizada():
    assert "_fr_anot(normalized_unit)" in _SRC
    assert "foi medido, mas do desenho da anotação. Confirme o \"" not in _SRC
