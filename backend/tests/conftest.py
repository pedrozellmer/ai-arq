# -*- coding: utf-8 -*-
"""Faz `pytest tests/` rodar a bancada INTEIRA.

🚨 23/08/2026 (auditoria): `pytest tests/` colhia 6 testes de UM arquivo e
abortava com `ValueError: I/O operation on closed file`. Os outros 17 arquivos
— consolidação, cotas, engine_rules, estrutural, jobs_lock, revision_feedback —
NUNCA rodavam junto. A rede de segurança existia e estava apagada.

Causa: 13 dos 18 arquivos `test_*.py` são SCRIPTS, não módulos de pytest: eles
executam no import, trocam `sys.stdout` por um TextIOWrapper (que o pytest
depois tenta ler fechado) e terminam em `sys.exit()`.

Reescrever os 13 seria caro e arriscado — eles são a bancada que segurou o motor
o ano inteiro. Em vez disso: o pytest ignora esses arquivos na coleção normal
(`collect_ignore`) e `test_scripts_legados.py` roda cada um em SUBPROCESSO,
conferindo o código de saída. Ninguém fica de fora, e quem escrever teste novo
no formato pytest é colhido normalmente.
"""
import io
import os
import re

_AQUI = os.path.dirname(os.path.abspath(__file__))


def _e_script(nome: str) -> bool:
    """True se o arquivo EXECUTA NO IMPORT (formato script), e só isso.

    🚨 24/08/2026 (2ª validação): a versão anterior devolvia True sempre que
    `"\ndef test_" not in src` — e num teste escrito em CLASSE o `def test_`
    está indentado, então nunca casava. Efeito medido com controle positivo:
    um arquivo com `class TestX: def test_deve_falhar(self): assert 1 == 2`
    era classificado como "script legado", o pytest não colhia, o subprocesso
    só importava o módulo (a classe é definida, nada executa), saía 0 — e a
    suíte contava **143 passed**. Um teste que afirma 1 == 2 passou por
    aprovado. Era a armadilha de 23/08 de novo: verde não é o mesmo que
    "rodou".
    """
    try:
        src = io.open(os.path.join(_AQUI, nome), encoding="utf-8").read()
    except Exception:
        return False
    # Tem teste no formato pytest? Função OU CLASSE, em qualquer indentação —
    # era a classe que escapava antes.
    tem_pytest = re.search(r"^[ \t]*(def test_|class Test)", src, re.M) is not None
    # Quebra a coleção do pytest? (`sys.exit` no import aborta a suíte inteira,
    # e trocar o sys.stdout faz o pytest ler um arquivo já fechado.)
    _nl = chr(10)
    quebra_colecao = (_nl + "sys.exit(") in src or (_nl + "sys.stdout = ") in src
    if quebra_colecao:
        return True
    return not tem_pytest


def scripts_legados():
    return sorted(n for n in os.listdir(_AQUI)
                  if n.startswith("test_") and n.endswith(".py")
                  and n != "test_scripts_legados.py" and _e_script(n))


collect_ignore = scripts_legados()
