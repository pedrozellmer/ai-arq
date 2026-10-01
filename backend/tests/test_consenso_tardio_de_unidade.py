# -*- coding: utf-8 -*-
"""A prancha que prova a escala DENTRO do laço vale pras seguintes.

🩸 01/10/2026 — o pré-passe do consenso de unidade pula prancha > 60 MB, e a
única que provava a escala do projeto era a de arquitetura (163 MB; emagrecida
pra 21 MB e validada por 1.062 cotas dentro do laço). O elétrico, lido depois,
não soube: a plausibilidade escolheu decímetro e tudo saiu 10× menor.
"""
import ast
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

from dwg_extractor import escala_provada_pela_prancha  # noqa: E402


@pytest.mark.parametrize("md,esperado", [
    ({"regua_cotas_status": "validada", "fator_para_metros": 1.0}, 1.0),
    ({"regua_cotas_status": "corrigida", "fator_para_metros": 0.01}, 0.01),
])
def test_a_prancha_provada_por_cota_da_o_fator(md, esperado):
    assert escala_provada_pela_prancha(md) == esperado


@pytest.mark.parametrize("md,motivo", [
    ({"regua_cotas_status": "corrigida_plausibilidade", "fator_para_metros": 0.1},
     "plausibilidade não é prova — foi ela que errou o elétrico"),
    ({"regua_cotas_status": "corrigida_lfac", "fator_para_metros": 1.0},
     "DIMLFAC: o pré-passe também não usa"),
    ({"regua_cotas_status": "nao-decidiu", "fator_para_metros": 0.001}, "sem prova"),
    ({"regua_cotas_status": "validada", "fator_para_metros": 0}, "fator zerado"),
    ({"regua_cotas_status": "validada", "fator_para_metros": "x"}, "fator ilegível"),
    ({}, "metadata vazia"),
    (None, "sem metadata"),
])
def test_CONTROLE_sem_prova_por_cota_nao_da_fator(md, motivo):
    assert escala_provada_pela_prancha(md) is None, motivo


def _process_job():
    fonte = open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    return next(n for n in ast.walk(ast.parse(fonte))
                if isinstance(n, ast.FunctionDef) and n.name == "process_job")


def test_o_laco_das_pranchas_alimenta_o_consenso():
    """No MESMO `for` que chama `_extract_dxf_isolated`: um `if _unit_consensus
    is None` que atribui `_unit_consensus` a partir de `escala_provada_pela_prancha`."""
    fn = _process_job()
    lacos = [n for n in ast.walk(fn) if isinstance(n, ast.For)
             and any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_extract_dxf_isolated"
                     for c in ast.walk(n))]
    assert lacos, "não achei o laço das pranchas"
    laco = min(lacos, key=lambda n: n.end_lineno - n.lineno)

    def _guarda(n):
        if not isinstance(n, ast.If):
            return False
        t = n.test
        return (isinstance(t, ast.Compare)
                and getattr(t.left, "id", "") == "_unit_consensus"
                and isinstance(t.ops[0], ast.Is))

    ifs = [n for n in ast.walk(laco) if _guarda(n)]
    assert ifs, "o laço não preenche o consenso"
    corpo = ifs[0]
    chama = any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "escala_provada_pela_prancha"
                for c in ast.walk(corpo))
    atribui = any(isinstance(a, ast.Assign) and any(getattr(t, "id", "") == "_unit_consensus"
                                                    for t in a.targets)
                  for a in ast.walk(corpo))
    assert chama and atribui, (chama, atribui)
    # e depois da extração da prancha (a régua lê o que ELA gravou)
    ext = min(c.lineno for c in ast.walk(laco) if isinstance(c, ast.Call)
              and getattr(c.func, "id", "") == "_extract_dxf_isolated")
    assert corpo.lineno > ext
