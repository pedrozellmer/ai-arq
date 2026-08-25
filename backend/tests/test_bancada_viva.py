# -*- coding: utf-8 -*-
"""A bancada não pode ENCOLHER sem ninguém notar.

🚨 23/08/2026: `pytest tests/` colhia 6 testes de UM arquivo e abortava. O job
passava VERDE, porque os 6 passaram. 17 arquivos nunca rodavam, e ninguém viu.

🚨 25/08 (auditoria do dia): o `bancada.yml` conferia o verde do pytest e NÃO o
número. O lado dos scripts legados já tinha essa checagem; o lado do pytest,
não — o mesmo buraco de 23/08 seguia aberto do lado que mais importa.

Piso, não alvo: só acusa QUEDA. Teste novo sobe o número e não quebra nada.
"""
import io
import os
import re
import subprocess
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)
_CI = os.path.join(_RAIZ, ".github", "workflows", "bancada.yml")


def _ci():
    if not os.path.exists(_CI):
        pytest.skip("bancada.yml não está nesta cópia")
    return io.open(_CI, encoding="utf-8").read()


def _saida_colheita():
    """O que o pytest COLHE, sem rodar. Uma chamada só, reusada."""
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "--collect-only"],
                       cwd=_BACKEND, capture_output=True, text=True, timeout=300)
    return r.stdout


def test_o_CI_confere_o_NUMERO_de_testes_colhidos():
    ci = _ci()
    assert "--collect-only" in ci, (
        "o CI voltou a conferir só o verde. Em 23/08 o pytest colhia 6 de 70 e "
        "passava — verde não prova que a bancada rodou inteira")
    assert "PISO" in ci


def test_o_piso_do_CI_faz_sentido_contra_a_realidade():
    """Piso acima da realidade quebra o CI toda vez e ensina a ignorá-lo; piso
    baixo demais deixa passar uma queda grande."""
    m = re.search(r"PISO:\s*(\d+)", _ci())
    assert m, "não achei o piso no bancada.yml"
    piso = int(m.group(1))
    aqui = len([l for l in _saida_colheita().splitlines() if "::" in l])
    assert aqui > 0, "não consegui contar a colheita"
    assert piso <= aqui, "o piso (%d) está acima do que a bancada colhe (%d)" % (piso, aqui)
    assert piso >= aqui * 0.75, (
        "o piso (%d) está muito abaixo dos %d testes de hoje — perderia uma "
        "queda grande sem reclamar" % (piso, aqui))


def test_todo_arquivo_de_teste_realmente_EXECUTA():
    """🪤 Arquivo que existe e não é colhido some em silêncio — foi assim que 17
    ficaram invisíveis por semanas. Quem é script legado roda pelo
    test_scripts_legados; o resto tem que aparecer na colheita."""
    colhidos = _saida_colheita()
    caminho_legado = os.path.join(_BACKEND, "tests", "test_scripts_legados.py")
    legado = (io.open(caminho_legado, encoding="utf-8").read()
              if os.path.exists(caminho_legado) else "")
    conftest = os.path.join(_BACKEND, "tests", "conftest.py")
    ignorados = (io.open(conftest, encoding="utf-8").read()
                 if os.path.exists(conftest) else "")

    orfaos = []
    for f in sorted(os.listdir(os.path.join(_BACKEND, "tests"))):
        if not (f.startswith("test_") and f.endswith(".py")):
            continue
        if f in colhidos or f in legado or f in ignorados:
            continue
        orfaos.append(f)
    assert not orfaos, (
        "estes arquivos de teste não são colhidos, não rodam como script legado "
        "e não estão declarados no conftest — existem e nunca executam: %s" % orfaos)


def test_nenhum_teste_tem_corpo_vazio():
    """🪤 25/08: eu tinha um `def test_...(): pass` com um comentário dizendo que
    outro arquivo cobria. Teste que não faz nada mas tem nome de quem confere é
    PIOR que teste nenhum: infla a contagem e se lê como cobertura."""
    import ast
    vazios = []
    for f in sorted(os.listdir(os.path.join(_BACKEND, "tests"))):
        if not (f.startswith("test_") and f.endswith(".py")):
            continue
        try:
            arvore = ast.parse(io.open(os.path.join(_BACKEND, "tests", f),
                                       encoding="utf-8").read())
        except SyntaxError:
            continue
        for n in ast.walk(arvore):
            if not (isinstance(n, ast.FunctionDef) and n.name.startswith("test_")):
                continue
            # tira a docstring antes de julgar
            corpo = [x for x in n.body
                     if not (isinstance(x, ast.Expr)
                             and isinstance(getattr(x, "value", None), ast.Constant))]
            if not corpo or all(isinstance(x, ast.Pass) for x in corpo):
                vazios.append("%s::%s" % (f, n.name))
    assert not vazios, "testes que não medem nada: %s" % vazios
