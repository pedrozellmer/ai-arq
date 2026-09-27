# -*- coding: utf-8 -*-
"""Peça contada por área × densidade típica não entra como número.

🩸 27/09/2026 — triagem de 20–27/09: "Estimativa: ~1.323 m² ÷ 11 m²/luminária
(densidade típica hospitalar)" = 120 luminárias; "1 detector a cada ~30 m²";
"Estimativa por boa prática". É a conta do aço por taxa (22/09) em peça contada:
índice de livro, não a contagem do projeto do cliente (regras nº1 e nº3).
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from engine_rules import contagem_por_densidade  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

_DENSIDADE = [
    "Estimativa: ~1.323 m² ÷ 11 m²/luminária (densidade típica hospitalar).",
    "Estimativa por área: 744,5 m² ÷ ~9 m² por luminária ≈ 83 luminárias.",
    "Estimativa: ~65m² de showroom ÷ ~30m²/equipamento = ~2 equipamentos.",
    "Estimativa por boa prática: 1 detector a cada ~30m² para loja de ~80m².",
    "Estimativa: 1 por ambiente = 3 unidades.",
    "Estimativa por boa prática para loja com 1 balcão.",
    # uma frase que só casa UM padrão (a sabotagem mostrou que as de cima
    # cobriam dois de uma vez)
    "Estimativa: 900 m² ÷ 10 m² = 90 luminárias.",
    "1 detector a cada 30 m² de área.",
]
_NAO_E = [
    "Contagem visual estimada: 12 luminárias na planta de forro.",
    "Fonte: 12 INSERTs do bloco 'LUM-01' na planta de forro.",
    "Conforme legenda: 18 un.",
    "Tubulação 1 a cada 3 m de apoio.",
]


def test_a_conta_de_densidade_e_reconhecida_em_peca():
    for t in _DENSIDADE:
        assert contagem_por_densidade("un", t), t


def test_CONTROLE_contagem_lida_e_outra_unidade_nao_sao_densidade():
    for t in _NAO_E:
        assert not contagem_por_densidade("un", t), t
    # verba "por boa prática" é decisão do Pedro, não entra aqui
    assert not contagem_por_densidade("vb", "Canteiro estimado por boa prática.")
    assert not contagem_por_densidade("m²", _DENSIDADE[0])


def _item(obs, origem="vision_pdf", unit="un", q=120):
    return BudgetItem(item_num="1", description="Luminária de embutir LED", unit=unit,
                      quantity=q, observations=obs, ref_sheet="p.pdf",
                      confidence=Confidence("estimado"), origem=origem)


def test_o_caso_a_linha_fica_em_branco_e_diz_a_conta():
    it = _item(_DENSIDADE[0])
    assert main._zera_contagem_por_densidade([it]) == 1
    assert it.quantity == 0
    assert it.observations.startswith("Em branco: contagem por DENSIDADE"), it.observations
    assert "dava 120." in it.observations, it.observations
    assert "÷ 11 m²/luminária" in it.observations, "a conta da leitura sumiu"


def test_CONTROLE_cad_revisao_do_cliente_e_verba_nao_mexem():
    for it in (_item(_DENSIDADE[0], origem="dxf_geom"),
               _item(_DENSIDADE[0], origem="revisao_cliente"),
               _item("Canteiro estimado por boa prática.", unit="vb", q=1),
               _item(_NAO_E[1])):
        q0 = it.quantity
        assert main._zera_contagem_por_densidade([it]) == 0
        assert it.quantity == q0


def test_o_process_job_chama_a_trava():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "main.py"), encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "process_job")
    chamadas = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "_zera_contagem_por_densidade"]
    assert len(chamadas) == 1, "a trava não é chamada (ou é chamada 2×) no process_job"
