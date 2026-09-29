# -*- coding: utf-8 -*-
"""Altura de instalação diferente é item diferente — também na passada 3.

🩸 29/09/2026 (caso 18c57c3c): os pontos de força da condensadora a h=3,00 m,
h=3,50 m e na fachada a h=0,80 m viraram "3 variantes consolidadas" com a
descrição de um deles. A passada 3 perguntava só ao `pode_fundir`, que não
conhecia altura.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
import main  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

_COND = [
    "Ponto de força para condensadora de ar-condicionado, altura h=3,00 m — fornecimento e instalação",
    "Ponto de força para condensadora de ar-condicionado, altura h=3,50 m — fornecimento e instalação",
    "Ponto de força para condensadora de ar-condicionado na fachada, h=0,80m da passarela — fornecimento e instalação",
]


def _it(desc, qtd=1.0, k=0, disc="Ar-Condicionado"):
    return BudgetItem(item_num=str(k + 1), description=desc, unit="un", quantity=qtd,
                      ref_sheet="eletrica.dxf", confidence=Confidence("estimado"), discipline=disc)


@pytest.mark.parametrize("a,b,difere", [
    (_COND[0], _COND[1], True),                              # 3,00 × 3,50
    (_COND[0], _COND[2], True),                              # 3,00 × 0,80
    ("Tomada h=1,10", "Tomada a 110 cm do piso", False),     # mesma altura, outra escrita
    ("Tomada h=1,10", "Tomada de uso geral", False),         # altura de um lado só
])
def test_a_regua_de_altura(a, b, difere):
    assert er.alturas_diferentes(a, b) is difere


def test_a_regua_rica_continua_com_o_motivo_de_sempre():
    assert er.motivo_para_nao_fundir("Tomada 2P+T 10A a 0,30 m do piso",
                                     "Tomada 2P+T 10A a 1,10 m do piso").startswith("altura")


def test_as_tres_condensadoras_ficam_separadas():
    out = main._consolidate_items([_it(d, k=k) for k, d in enumerate(_COND)])
    cond = [i for i in out if "condensadora" in i.description]
    assert len(cond) == 3 and all(i.quantity == 1 for i in cond), [(i.description, i.quantity) for i in cond]


def test_CONTROLE_o_ralo_repetido_continua_juntando():
    """O alvo da passada 3 ('Ralo sifonado' × 5 em pranchas diferentes) segue igual."""
    out = main._consolidate_items([_it("Ralo sifonado 100 mm — fornecimento e instalação", k=k,
                                       disc="Instalações Hidráulicas") for k in range(5)])
    ralo = [i for i in out if "Ralo" in i.description]
    assert len(ralo) == 1 and ralo[0].quantity == 5, [(i.description, i.quantity) for i in ralo]
