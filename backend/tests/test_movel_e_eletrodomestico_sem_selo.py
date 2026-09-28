# -*- coding: utf-8 -*-
"""Móvel e eletrodoméstico saem sem selo, com o aviso de escopo.

📏 28/09/2026 (estudo de leitura, P1a): em 120 dias, linhas de "Mobiliário"
COM selo que clientes revisaram: 71 rejeitadas × 4 aprovadas. A contagem está
certa; o que o cliente recusa é o escopo. O número fica, o selo sai.
"""
import os
import sys
import textwrap

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from engine_rules import MARCA_ESCOPO_MOBILIARIO, e_mobiliario_ou_equipamento  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402


def test_a_regua():
    assert e_mobiliario_ou_equipamento("Mobiliário", "Cadeira Breuer — fornecimento")
    assert e_mobiliario_ou_equipamento("Complementares", "Cooktop — Brastemp, fornecimento e instalação")
    assert not e_mobiliario_ou_equipamento("Instalações Elétricas", "Ponto de tomada para geladeira")
    assert not e_mobiliario_ou_equipamento("Complementares", "Instalação de cooktop — ponto de gás")
    assert not e_mobiliario_ou_equipamento("Instalações Hidráulicas", "Cuba de aço inox para cozinha")
    assert not e_mobiliario_ou_equipamento("Marcenaria", "Armário planejado em MDF")


def _fatia():
    src = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    a = src.index("# 📏 MÓVEL E ELETRODOMÉSTICO SEM SELO")
    ini = src.index("        try:\n", a)
    fim = src.index("        # 🚨 AQUI é o fim da fila de quem rebaixa selo", a)
    return textwrap.dedent(src[ini:fim])


def _item(desc, disc, qtd=4, conf="confirmado"):
    return BudgetItem(item_num="1", description=desc, unit="un", quantity=qtd, discipline=disc,
                      observations="Fonte: 4 INSERTs do bloco 'X' (CONTAGEM DE BLOCOS).",
                      ref_sheet="a.dxf", confidence=Confidence(conf), origem="dxf_geom")


def _roda(itens):
    ns = {"all_items": itens, "job_id": "t", "os": os, "_log_error": lambda *a, **k: None,
          "_unidades_do_quadro": {}}
    exec(compile(_fatia(), "mobiliario", "exec"), ns)
    return itens


def test_movel_e_eletrodomestico_perdem_o_selo_e_o_numero_fica():
    cad, cook, tomada, vaso = _roda([
        _item("Cadeira Breuer — fornecimento", "Mobiliário", 12),
        _item("Cooktop — Brastemp, fornecimento e instalação", "Complementares", 2),
        _item("Ponto de tomada para geladeira", "Instalações Elétricas", 6),
        _item("Vaso sanitário — louça branca", "Instalações Hidráulicas", 8),
    ])
    for it, qtd in ((cad, 12), (cook, 2)):
        assert it.confidence == Confidence("estimado") and it.quantity == qtd, it
        assert it.observations.startswith(MARCA_ESCOPO_MOBILIARIO), it.observations
    for it in (tomada, vaso):
        assert it.confidence == Confidence("confirmado") and MARCA_ESCOPO_MOBILIARIO not in it.observations


def test_rodar_de_novo_nao_repete_o_aviso():
    itens = [_item("Mesa redonda", "Mobiliário")]
    _roda(itens)
    _roda(itens)
    assert itens[0].observations.count(MARCA_ESCOPO_MOBILIARIO) == 1
