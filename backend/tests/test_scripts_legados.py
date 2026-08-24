# -*- coding: utf-8 -*-
"""Roda, em subprocesso, cada arquivo da bancada escrito como SCRIPT.

Ver `conftest.py` para o porquê. Sem isto, `pytest tests/` deixava 13 arquivos
de fora — inclusive os que guardam consolidação de bitola, cotas do DXF,
engine_rules e a trava de jobs concorrentes.
"""
import io
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
    # 🚨 24/08: "saiu 0" não prova que rodou. Um arquivo que só DEFINE coisas
    # (teste em classe, helper) importa, não executa nada e sai 0 — e a bancada
    # contava isso como teste aprovado. Todo script da bancada imprime o
    # resultado ("RESULTADO: N passaram", "todos OK", "=== TODOS OK ==="), então
    # saída vazia é o sinal de que nada aconteceu.
    assert (r.stdout or "").strip(), (
        f"{nome} saiu com 0 mas não imprimiu NADA — provavelmente não executou "
        f"teste nenhum (arquivo só define funções/classes?). Verde sem prova de "
        f"execução é o bug que este assert existe pra impedir.")


def test_a_bancada_reprova_teste_em_CLASSE_que_falha():
    """🚨 Controle positivo (24/08, 2ª validação).

    O conftest classificava por `"\ndef test_" not in src` — e num teste em
    CLASSE o `def test_` está indentado, então nunca casava. O arquivo virava
    "script legado", o pytest não colhia, o subprocesso só importava (a classe é
    definida, nada executa), saía 0, e a suíte contava como APROVADO. Medido:
    um arquivo afirmando `assert 1 == 2` deixou a suíte em `143 passed`.

    Este teste prova que a classificação mudou de lado.
    """
    import conftest
    veneno = os.path.join(_AQUI, "test_zzz_controle_classe.py")
    io.open(veneno, "w", encoding="utf-8").write(
        "class TestControle:\n"
        "    def test_deve_falhar(self):\n"
        "        assert 1 == 2\n")
    try:
        assert not conftest._e_script("test_zzz_controle_classe.py"), (
            "teste em classe foi classificado como script legado — o pytest não "
            "vai colhê-lo e ele passa por aprovado sem nunca rodar")
    finally:
        os.remove(veneno)


def test_a_bancada_ainda_reconhece_script_de_verdade():
    """Controle negativo: quem executa no import continua sendo script."""
    import conftest
    alvo = os.path.join(_AQUI, "test_zzz_controle_script.py")
    io.open(alvo, "w", encoding="utf-8").write(
        "import sys\nprint('RESULTADO: 1 ok')\nsys.exit(0)\n")
    try:
        assert conftest._e_script("test_zzz_controle_script.py"), (
            "script com sys.exit no import foi mandado pra coleção — ele aborta "
            "a suíte inteira")
    finally:
        os.remove(alvo)


def test_todo_script_da_bancada_imprime_o_resultado():
    """A prova de execução só vale se os scripts realmente falam. Se algum
    parar de imprimir, é melhor descobrir aqui do que num verde falso."""
    mudos = []
    for nome in _SCRIPTS:
        src = io.open(os.path.join(_AQUI, nome), encoding="utf-8").read()
        if "print(" not in src:
            mudos.append(nome)
    assert not mudos, (
        "scripts sem nenhum print — o assert de saída não-vazia vai reprová-los "
        "por engano, ou pior, eles nunca executaram nada: %s" % mudos)
