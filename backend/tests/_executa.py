# -*- coding: utf-8 -*-
"""Executar um trecho REAL de `process_job` — em vez de ler o fonte dele.

🚨 06/09/2026. Uma varredura por mutação provou 23 guardas CEGOS: todos liam
`main.py` como texto (`assert "..." in src`). Mutação que reescreve a mesma
linha com outra grafia — `or []` virando `or list()`, `if x:` virando
`if not x:`, `endswith(suf)` virando `endswith(suf) and False` — passa por
todos eles VERDE.

O conserto certo é chamar a função e olhar a saída. Para o que mora em
`_build_reading_diagnostic`, `health` e `rebuild_planilha_from_review` isso é
direto: são funções de verdade, com colaboradores monkeypatcháveis.

🪤 Mas cinco dos defeitos moram DENTRO de `process_job` — 3.900 linhas, que lê
CAD, chama a IA e sobe arquivo. Nenhum teste desta casa jamais a executou, e
montar isso pra provar um `if` seria trocar um guarda cego por um guarda que
nunca roda.

🔑 A saída: recortar do PRÓPRIO `main.py`, pela ÁRVORE SINTÁTICA, o statement
que interessa, e EXECUTÁ-LO com um escopo montado à mão. O que roda é o código
de produção — não uma cópia dele no arquivo de teste. Se alguém mexer naquele
`if`, o statement recortado muda de comportamento e o guarda reprova.

🪤 A diferença que faz isso valer: recorte por AST tem FIM REAL (`end_lineno`),
não é janela de N caracteres — o mesmo motivo que fez `_corpo.corpo_de` existir.
E o que se afirma é o RESULTADO da execução, não a presença de um texto.
"""
import ast
import io
import os
import textwrap

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fonte(arquivo="main.py"):
    return io.open(os.path.join(_BACKEND, arquivo), encoding="utf-8").read()


def _funcao(nome, arquivo="main.py"):
    src = _fonte(arquivo)
    arv = ast.parse(src)
    for no in ast.walk(arv):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name == nome:
            return no, src
    raise AssertionError("não achei a função %s em %s" % (nome, arquivo))


def trecho(nome_funcao, marcador, tamanho=0, arquivo="main.py"):
    """Fonte do statement de `nome_funcao` que contém `marcador`, dedentado.

    `tamanho=0` devolve o MENOR statement que contém o marcador; 1 devolve o que
    o envolve; 2 o de fora dele, e assim por diante. O recorte vem da árvore
    sintática (`lineno`/`end_lineno`), então ele sempre acaba onde o statement
    acaba de verdade — nunca no meio de uma f-string de várias linhas.
    """
    no_fn, src = _funcao(nome_funcao, arquivo)
    linhas = src.splitlines(True)
    achados = []
    for no in ast.walk(no_fn):
        if not isinstance(no, ast.stmt):
            continue
        if getattr(no, "lineno", None) is None:
            continue
        bruto = "".join(linhas[no.lineno - 1:no.end_lineno])
        if marcador in bruto:
            achados.append((no.end_lineno - no.lineno, bruto))
    if not achados:
        raise AssertionError(
            "não achei nenhum statement com %r dentro de %s — o código que este "
            "guarda executa sumiu ou foi reescrito" % (marcador, nome_funcao))
    achados.sort(key=lambda t: t[0])
    if tamanho >= len(achados):
        raise AssertionError(
            "%s tem só %d statements aninhados com %r (pedi o de índice %d)"
            % (nome_funcao, len(achados), marcador, tamanho))
    return textwrap.dedent(achados[tamanho][1])


def roda(nome_funcao, marcador, escopo, tamanho=0, arquivo="main.py"):
    """Executa o statement real de `nome_funcao` com o escopo dado.

    Devolve o escopo depois da execução — é nele que se lê o RESULTADO.
    """
    fonte_trecho = trecho(nome_funcao, marcador, tamanho, arquivo)
    codigo = compile(fonte_trecho, "<%s:%s>" % (arquivo, nome_funcao), "exec")
    exec(codigo, escopo)
    return escopo
