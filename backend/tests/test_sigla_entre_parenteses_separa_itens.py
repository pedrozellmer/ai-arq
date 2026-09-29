# -*- coding: utf-8 -*-
"""Siglas diferentes entre parênteses são itens diferentes — a fusão não junta.

🩸 28/09/2026 (caso 18c57c3c): a prancha tinha 9 blocos "DJIII" (disjuntor
tripolar) e 9 blocos "DJKI" (disjuntor DR 40A/30mA). A IA escreveu as duas
linhas certas; a passada 2 da consolidação juntou as duas porque têm a MESMA
quantidade e o `_RX_CODIGO` só reconhece código com número. O log
`motor:fusao-calada` até marcou "pranchas=1 🚩MEDIDA" — e a planilha saiu com
9 disjuntores tripolares a menos.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
import main  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

_TRIPOLAR = ("Disjuntor tripolar (DJIII) — fornecimento e instalação — corrente nominal "
             "conforme diagrama")
_DR = ("Disjuntor (DJKI) — fornecimento e instalação — corrente nominal conforme diagrama; "
       "atributo: 40A/30mA (diferencial residual)")


def _it(desc, qtd=9.0, k=0):
    return BudgetItem(item_num=str(k + 1), description=desc, unit="un", quantity=qtd,
                      ref_sheet="prancha-eletrica.dxf", confidence=Confidence("confirmado"),
                      discipline="Instalações Elétricas")


def test_a_regua():
    assert er.motivo_para_nao_fundir(_TRIPOLAR, _DR).startswith("sigla")
    assert er._siglas_fusao(_TRIPOLAR) == {"DJIII"}


def test_a_consolidacao_mantem_os_dois_disjuntores():
    out = main._consolidate_items([_it(_TRIPOLAR, k=0), _it(_DR, k=1)])
    dj = sorted((i.description[:22], i.quantity) for i in out if "isjuntor" in i.description)
    assert len(dj) == 2, dj
    assert sum(q for _d, q in dj) == 18, dj


def test_CONTROLE_a_mesma_sigla_continua_juntando():
    """Réplica de verdade ("(PD)" × "(PD)" no acervo) — a regra não pode separar."""
    a = "Disjuntor DR (DJKI) — fornecimento e instalação — corrente nominal conforme diagrama"
    out = main._consolidate_items([_it(a, k=0), _it(_DR, k=1)])
    dj = [i for i in out if "isjuntor" in i.description]
    assert len(dj) == 1 and dj[0].quantity == 9, [(i.description, i.quantity) for i in dj]


def test_CONTROLE_sigla_de_um_lado_so_nao_bloqueia():
    """A leitura vaga não diz a sigla: isso não é prova de que são dois itens."""
    vago = "Disjuntor — fornecimento e instalação — corrente nominal conforme diagrama"
    assert er.motivo_para_nao_fundir(vago, _DR) == ""
    out = main._consolidate_items([_it(vago, k=0), _it(_DR, k=1)])
    assert len([i for i in out if "isjuntor" in i.description]) == 1


def test_sigla_de_material_ou_norma_nao_conta():
    assert er._siglas_fusao("Eletroduto rígido (PVC) — 25 mm") == frozenset()
    assert er._siglas_fusao("Luminária (LED) — conforme legenda") == frozenset()
