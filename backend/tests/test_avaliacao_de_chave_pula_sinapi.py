# -*- coding: utf-8 -*-
"""Avaliação que compara chaves não paga o SINAPI por padrão.

💸 04/11/2026: 43 de 63 avaliações em 30 dias pagaram o SINAPI (US$ 25,15) e
nenhuma foi liberada ao cliente. Quem passa `?chaves=` está medindo uma regra do
motor; o botão "Avaliar (isolado)" (sem chaves) segue completo pra poder liberar.
"""
import ast
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


@pytest.mark.parametrize("sem,chaves,com,pula", [
    (None, None, None, False),             # botão do admin: pipeline inteiro
    (None, "", None, False),
    (None, "   ", None, False),
    (None, "X=1", None, True),             # A/B de chave: pula por padrão
    (None, "X=1", "1", False),             # pediu o SINAPI
    ("1", None, None, True),               # pediu pra pular
    ("0", "X=1", None, False),             # pediu explicitamente pra NÃO pular
    ("1", "X=1", "1", False),              # com_sinapi vence
    ("sim", None, "nao", True),
    (None, "X=1", "true", False),
])
def test_quem_decide(sem, chaves, com, pula):
    assert main._pula_sinapi_na_avaliacao(sem, chaves, com) is pula


def test_a_rota_usa_a_regra_e_aceita_com_sinapi():
    with open(main.__file__, encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    rota = next(n for n in ast.walk(arvore)
                if isinstance(n, ast.FunctionDef) and n.name == "admin_eval_reprocess")
    assert "com_sinapi" in [a.arg for a in rota.args.args]
    chamadas = [n for n in ast.walk(rota) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "_pula_sinapi_na_avaliacao"]
    assert len(chamadas) == 1
    assert [a.id for a in chamadas[0].args] == ["sem_sinapi", "chaves", "com_sinapi"]
    assert not [n for n in ast.walk(rota) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "_pediu_sem_sinapi"]
