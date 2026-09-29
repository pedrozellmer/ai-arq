# -*- coding: utf-8 -*-
"""Reprocessar um reprocesso não dobra o "(reprocessado)" no nome.

🩸 29/09/2026 (caso 18c57c3c): o cliente recebeu "SHOPPE (reprocessado)
(reprocessado) — sua planilha está pronta" — o nome é o de antes + sufixo, e o
de antes já era reprocesso.
"""
import ast
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _corpo import fonte  # noqa: E402


@pytest.mark.parametrize("antes,depois", [
    ("SHOPPE", "SHOPPE (reprocessado)"),
    ("SHOPPE (reprocessado)", "SHOPPE (reprocessado)"),
    ("SHOPPE (reprocessado) (reprocessado)", "SHOPPE (reprocessado)"),
    ("  Casa 2  ", "Casa 2 (reprocessado)"),
    ("", "Projeto (reprocessado)"),
    (None, "Projeto (reprocessado)"),
])
def test_o_sufixo_entra_uma_vez(antes, depois):
    assert main._nome_do_reprocesso(antes) == depois


def test_a_rota_de_reprocesso_usa_a_regua():
    arv = ast.parse(fonte("main.py"))
    rota = [n for n in ast.walk(arv)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "reprocess_project"]
    assert len(rota) == 1
    valores = [v for n in ast.walk(rota[0]) if isinstance(n, ast.Dict)
               for k, v in zip(n.keys, n.values)
               if isinstance(k, ast.Constant) and k.value == "project_name"]
    assert valores, "a rota não grava mais project_name?"
    for v in valores:
        assert isinstance(v, ast.Call) and getattr(v.func, "id", "") == "_nome_do_reprocesso", (
            "o nome do reprocesso voltou a ser montado na mão: %s" % ast.unparse(v))
