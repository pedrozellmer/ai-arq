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

_AQUI = os.path.dirname(os.path.abspath(__file__))


def _e_script(nome: str) -> bool:
    """True se o arquivo roda no import / termina em sys.exit (formato script)."""
    try:
        src = io.open(os.path.join(_AQUI, nome), encoding="utf-8").read()
    except Exception:
        return False
    if "\nsys.exit(" in src or "\nsys.stdout = " in src:
        return True
    return "\ndef test_" not in src


def scripts_legados():
    return sorted(n for n in os.listdir(_AQUI)
                  if n.startswith("test_") and n.endswith(".py")
                  and n != "test_scripts_legados.py" and _e_script(n))


collect_ignore = scripts_legados()
