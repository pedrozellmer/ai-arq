# -*- coding: utf-8 -*-
"""A conta seção × pé-direito × contagem de pilar é POR PRANCHA.

🩸 26/09/2026 — job 32a27efc (muro de arrimo, 7 DXF): a derivação juntava os
pilares contados em TODAS as pranchas (32 + 26 + 16 + 33 + 2 = "109 pilares",
num muro de P1 a P44 — cada prancha conta os pilares que MOSTRA, e as faixas se
sobrepõem) e escrevia o MESMO total em toda linha-alvo zerada, de qualquer
prancha: 46,99 m³ e 791 m² de fôrma, duas vezes (pranchas 0002 e 0003).

🪤 As descrições aqui são NEUTRAS de propósito: estes testes são do POR
PRANCHA. Com "muro de arrimo" na descrição a conta nem roda — contenção
não usa o pé-direito como altura de pilar (ver
test_o_pe_direito_nao_e_altura_de_pilar_de_muro.py).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_deriva = main._derive_estrutura_pe_direito


class _It:
    def __init__(self, descricao, unidade, qtd, folha):
        self.description = descricao
        self.unit = unidade
        self.quantity = qtd
        self.confidence = "estimado"
        self.observations = ""
        self.discipline = "Estrutura"
        self.origem = None
        self.ref_sheet = folha


def _pilar(n, folha, sec="19×30"):
    return _It("Pilar de concreto armado — seção %s cm" % sec, "un", n, folha)


def _conc(folha, q=0):
    return _It("Concreto armado — pilares", "m³", q, folha)


def _forma(folha, q=0):
    return _It("Fôrma de madeira — pilares", "m²", q, folha)


# 19×30 cm × 7,32 m: 0,057 m² × 7,32 = 0,41724 m³ por pilar; perímetro 0,98 m
def test_o_caso_cada_alvo_usa_os_pilares_da_propria_prancha():
    a, c = _conc("0004"), _forma("0003")
    itens = [_pilar(32, "0004"), _pilar(26, "0005"), _pilar(33, "0007"), a, c]
    _deriva(itens, 7.32)
    assert a.quantity == round(0.057 * 7.32 * 32, 2), a.quantity          # 13,35 — nunca a soma (38,38)
    assert "(32 pilares)" in a.observations
    assert c.quantity == 0, "prancha sem pilar contado não pode receber conta de outra"
    assert c.observations == ""


def test_duas_pranchas_com_alvo_cada_uma_com_a_sua_conta():
    a1, a2 = _forma("0005"), _forma("0007")
    _deriva([_pilar(26, "0005"), _pilar(33, "0007"), a1, a2], 7.32)
    assert a1.quantity == round(0.98 * 7.32 * 26, 2), a1.quantity
    assert a2.quantity == round(0.98 * 7.32 * 33, 2), a2.quantity
    assert a1.quantity != a2.quantity, "o MESMO número nas duas pranchas é a soma espalhada"


def test_a_conferencia_da_linha_ja_preenchida_e_da_propria_prancha():
    ja = _conc("0005", q=10.85)
    _deriva([_pilar(26, "0005"), _pilar(33, "0007"), ja], 7.32)
    assert ja.quantity == 10.85
    assert "Conferência por seção×PD: %g m³" % round(0.057 * 7.32 * 26, 2) in ja.observations, ja.observations


def test_o_motivo_mostra_a_prancha_com_mais_pilares_e_nao_a_soma():
    _deriva([_pilar(32, "0004"), _pilar(26, "0005"), _pilar(33, "0007")], 7.32)
    m = _deriva.ultimo_motivo
    assert "33 pilares" in m and "91 pilares" not in m, m
    assert "3 prancha(s)" in m, m


def test_CONTROLE_mesma_prancha_duas_secoes_somam():
    """Dentro da MESMA prancha as seções diferentes somam (não é repetição)."""
    a = _conc("0004")
    _deriva([_pilar(32, "0004"), _pilar(2, "0004", sec="40×40"), a], 7.32)
    assert a.quantity == round(0.057 * 7.32 * 32 + 0.16 * 7.32 * 2, 2), a.quantity
