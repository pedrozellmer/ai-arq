# -*- coding: utf-8 -*-
"""Duas linhas que citam BLOCOS DIFERENTES do desenho como fonte não se fundem.

🩸 29/09/2026 (caso 18c57c3c, 2ª vez): "Disjuntor (tipo DJIII)" e "Disjuntor (tipo
DJKI)", 9 un cada, fundiram de novo — a sigla veio com "tipo" dentro do parêntese e a
trava da sigla depende da redação da IA. A observação de cada linha cita o bloco de
onde veio a contagem; blocos diferentes = dois símbolos = dois itens.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
import main  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402


def _it(desc, obs, qtd=9.0, k=0, ref="eletrica.dxf", disc="Instalações Elétricas"):
    return BudgetItem(item_num=str(k + 1), description=desc, unit="un", quantity=qtd,
                      observations=obs, ref_sheet=ref, confidence=Confidence("confirmado"),
                      discipline=disc)


@pytest.mark.parametrize("obs,esperado", [
    ("Fonte: 9 INSERTs do bloco 'DJIII'. Confirmar polo", {"djiii"}),
    ('Fonte: 9 INSERTs do bloco "DJKI".', {"djki"}),
    ("Fonte: blocos 'TOM. BAIXA 127V' e 'x'", {"tom. baixa 127v"}),
    ("Fonte: texto do layer 'ELE-TEXTOS'", set()),
    ("", set()),
])
def test_os_blocos_que_a_observacao_cita(obs, esperado):
    assert er.blocos_citados(obs) == frozenset(esperado)


def test_djiii_e_djki_ficam_separados_mesmo_com_tipo_no_parentese():
    out = main._consolidate_items([
        _it("Disjuntor (tipo DJIII) — fornecimento e instalação em quadro de distribuição",
            "Fonte: 9 INSERTs do bloco 'DJIII'. Confirmar polo.", k=0),
        _it("Disjuntor (tipo DJKI) — fornecimento e instalação em quadro de distribuição",
            "Fonte: 9 INSERTs do bloco 'DJKI'. Confirmar sensibilidade.", k=1),
    ])
    dj = [i for i in out if "isjuntor" in i.description]
    assert len(dj) == 2 and sum(i.quantity for i in dj) == 18, [(i.description, i.quantity) for i in dj]


def test_na_passada_3_tambem():
    """Três linhas pequenas de mesma abertura (a passada 3 juntaria) de três blocos."""
    out = main._consolidate_items([
        _it("Dispositivo elétrico de campo — tipo %s — fornecimento e instalação" % n,
            "Fonte: 1 INSERT do bloco '%s'." % n, qtd=1.0, k=k)
        for k, n in enumerate(("SP", "SI", "SX"))])
    disp = [i for i in out if "ispositivo" in i.description]
    assert len(disp) == 3, [(i.description, i.quantity) for i in disp]


def test_CONTROLE_o_mesmo_bloco_em_duas_pranchas_continua_juntando():
    """Réplica de verdade: a mesma linha, o mesmo bloco, lida em duas pranchas."""
    out = main._consolidate_items([
        _it("Tomada baixa 2P+T 10A — fornecimento e instalação",
            "Fonte: 12 INSERTs do bloco 'TOM. BAIXA'.", qtd=12, k=0, ref="a.dxf"),
        _it("Tomada baixa 2P+T 10A — fornecimento e instalação",
            "Fonte: 12 INSERTs do bloco 'TOM. BAIXA'.", qtd=12, k=1, ref="b.dxf"),
    ])
    tom = [i for i in out if "Tomada" in i.description]
    assert len(tom) == 1, [(i.description, i.quantity) for i in tom]


def test_CONTROLE_sem_bloco_citado_de_um_lado_nao_decide():
    a = er.perfil_de_fusao("Disjuntor — fornecimento", "un", "", "Fonte: 9 INSERTs do bloco 'DJIII'.")
    b = er.perfil_de_fusao("Disjuntor — fornecimento", "un", "", "Quantidade do texto do quadro.")
    assert not er.motivo_para_nao_fundir(a, b).startswith("blocos")
