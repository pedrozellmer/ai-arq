# -*- coding: utf-8 -*-
"""Juntar N verbas iguais dá UMA verba — a consolidação não soma 'vb'.

🩸 28/09/2026 (estudo de leitura, achado 30): "LIMPEZA FINAL (várias
variantes) 26 vb", "Circuito de iluminação 30 vb" — as passadas 1 (réplica) e
3 (família) somavam sem olhar a unidade. 185 linhas assim em 51 projetos de
cliente em 60 dias. Prazo em mês repetido por prancha é o mesmo prazo: vale o
maior. Peça (un, m, m²) continua somando.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402


def _it(desc, unit, qtd, k=0, disc="Serviços Preliminares"):
    return BudgetItem(item_num=str(k + 1), description=desc, unit=unit, quantity=qtd,
                      ref_sheet="prancha-%d.pdf" % k, confidence=Confidence("estimado"),
                      discipline=disc)


def test_a_regua():
    assert main._quantidade_de_grupo("vb", [1, 1, 1])[0] == 1.0
    assert main._quantidade_de_grupo("vb", [0, 0])[0] == 0.0
    assert main._quantidade_de_grupo("mês", [1.5, 1.5, 1.0])[0] == 1.5
    assert main._quantidade_de_grupo("un", [1, 1, 1])[0] == 3.0


def test_replicas_de_verba_viram_uma_verba():
    out = main._consolidate_items([_it("Limpeza final de obra", "vb", 1.0, k) for k in range(26)])
    lim = [i for i in out if "impeza" in i.description]
    assert len(lim) == 1 and lim[0].quantity == 1.0, [(i.description, i.quantity) for i in lim]
    assert "verba única — não soma" in lim[0].observations, lim[0].observations


def test_familia_de_verbas_vira_uma_verba():
    descs = ("Limpeza final da obra", "Limpeza de obra e remoção de entulho", "Limpeza grossa pós-obra")
    out = main._consolidate_items([_it(d, "vb", 1.0, k) for k, d in enumerate(descs)])
    lim = [i for i in out if "impeza" in i.description]
    assert len(lim) == 1 and lim[0].quantity == 1.0, [(i.description, i.quantity) for i in lim]


def test_prazo_repetido_vale_o_maior():
    out = main._consolidate_items([_it("Locação de andaime", "mês", 1.5, k) for k in range(4)])
    anda = [i for i in out if "andaime" in i.description]
    assert len(anda) == 1 and anda[0].quantity == 1.5, [(i.description, i.quantity) for i in anda]


def test_CONTROLE_peca_continua_somando():
    out = main._consolidate_items([_it("Ponto de tomada baixa", "un", 1.0, k, disc="Instalações Elétricas")
                                   for k in range(4)])
    tom = [i for i in out if "tomada" in i.description]
    assert len(tom) == 1 and tom[0].quantity == 4.0, [(i.description, i.quantity) for i in tom]
