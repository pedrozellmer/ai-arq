# -*- coding: utf-8 -*-
"""Roda, em subprocesso, cada arquivo da bancada escrito como SCRIPT.

Ver `conftest.py` para o porquê. Sem isto, `pytest tests/` deixava 13 arquivos
de fora — inclusive os que guardam consolidação de bitola, cotas do DXF,
engine_rules e a trava de jobs concorrentes.
"""
import os
import subprocess
import sys

import pytest

from conftest import scripts_legados

_AQUI = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = scripts_legados()


def test_a_lista_nao_esvaziou():
    """Se alguém quebrar a detecção, o silêncio não pode passar por sucesso."""
    assert len(_SCRIPTS) >= 10, (
        "esperava pelo menos 10 scripts legados na bancada, achei "
        f"{len(_SCRIPTS)}: {_SCRIPTS}")


@pytest.mark.parametrize("nome", _SCRIPTS)
def test_script_legado(nome):
    r = subprocess.run([sys.executable, os.path.join(_AQUI, nome)],
                       capture_output=True, text=True, timeout=300,
                       encoding="utf-8", errors="replace")
    saida = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, f"{nome} saiu com {r.returncode}:\n{saida[-3000:]}"
