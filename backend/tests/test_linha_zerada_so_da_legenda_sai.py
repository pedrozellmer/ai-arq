# -*- coding: utf-8 -*-
"""Linha com quantidade zero de item que o desenho só mostra na LEGENDA sai da planilha.

🩸 29/09/2026 (caso 18c57c3c): 18 linhas "0 un" — tomada de forro, pontos de
telefonia, central de alarme e sensores — todas símbolos da legenda que a planta
não usa. Linha zerada é do produto (o que não conseguimos medir, o cliente
completa); item que o desenho só mostra na legenda não é lacuna, é fora da prancha.
"""
import ast
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import engine_rules as er  # noqa: E402
from _corpo import fonte  # noqa: E402

_OBS = ("Bloco 'TOM. FORRO 127V': 2 INSERTs, dos quais ao menos 2 são símbolo de "
        "legenda gráfica — quantidade real na planta não identificada.")


def test_a_linha_zero_do_item_so_da_legenda_sai():
    assert er.linha_zerada_so_de_legenda(_OBS, 0, "un", {"TOM. FORRO 127V": (2, 2)}) == "TOM. FORRO 127V"


@pytest.mark.parametrize("obs,qtd,unid,amostras", [
    (_OBS, 0, "un", {"TOM. FORRO 127V": (3, 2)}),        # uma inserção fora da legenda: fica
    (_OBS, 1, "un", {"TOM. FORRO 127V": (2, 2)}),        # tem quantidade: fica
    (_OBS, 0, "m", {"TOM. FORRO 127V": (2, 2)}),         # não é contagem de bloco
    ("Tomada de forro — quantidade a confirmar", 0, "un", {"TOM. FORRO 127V": (2, 2)}),
    ("Bloco 'PONTO LOGICA 30CM': 1 INSERT", 0, "un", {"PONTO LOGICA 30": (1, 1)}),  # outro nome
    (_OBS, 0, "un", {}),
])
def test_CONTROLE_o_resto_fica(obs, qtd, unid, amostras):
    assert er.linha_zerada_so_de_legenda(obs, qtd, unid, amostras) == ""


def test_a_regra_esta_no_laco_dos_itens_e_tira_a_linha():
    """A decisão mora em engine_rules; no `process_job` é uma chamada seguida de
    `continue`, DEPOIS do selo da legenda e ANTES de o item ir pra lista."""
    arv = ast.parse(fonte("main.py"))
    pj = [n for n in ast.walk(arv) if isinstance(n, ast.FunctionDef) and n.name == "process_job"][0]
    chamada = [n for n in ast.walk(pj) if isinstance(n, ast.Call)
               and getattr(n.func, "id", "") == "_so_legenda"]
    assert len(chamada) == 1, "a regra da linha só-de-legenda sumiu (ou duplicou) do laço"
    ifs = [n for n in ast.walk(pj) if isinstance(n, ast.If)
           and getattr(n.test, "id", "") == "_bl_leg"]
    assert len(ifs) == 1 and any(isinstance(s, ast.Continue) for s in ifs[0].body), (
        "a linha que casa tem que SAIR (continue), não só ser marcada")
    regra_amostra = [n.lineno for n in ast.walk(pj) if isinstance(n, ast.Call)
                     and getattr(n.func, "id", "") == "_regra_amostra"]
    append = [n.lineno for n in ast.walk(pj) if isinstance(n, ast.Call)
              and getattr(n.func, "attr", "") == "append"
              and getattr(n.func.value, "id", "") == "dxf_items"]
    assert regra_amostra and append
    assert regra_amostra[0] < chamada[0].lineno < min(a for a in append if a > chamada[0].lineno)
