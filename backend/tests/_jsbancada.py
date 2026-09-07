# -*- coding: utf-8 -*-
"""Roda o JavaScript das telas DE VERDADE, num motor JS — não lê o fonte.

🚨 06/09/2026. Uma varredura por MUTAÇÃO provou cegos os guardas de
`revisao.html` e `admin.html`: todos eles procuravam TEXTO no arquivo. Três
mutações passaram verdes:

  • um `_salvarRapido(url, opts)` que devolve a resposta sem conferir `r.ok`,
    usado no lugar do `_salvar` — a chamada tem a MESMA forma, então o
    regex do guarda continuava achando "salvamento que não é authFetch";
  • `if (r.ok || r.status >= 500) return r;` — "r.ok" e "throw" seguem no
    corpo, que era tudo que o guarda cobrava;
  • restaurar o estado da tela só `if (e.name === 'TimeoutError')` — as
    contagens de `Object.assign(...)` exigidas ficaram idênticas.

🔑 Nenhuma dessas some quando o código RODA: com 502 na mão, ou a tela desfaz
e avisa, ou ela mente. Este módulo é o que permite perguntar isso.

🪤 `corpo_js` do `_corpo.py` ancora em `function <nome>(` e por isso perde o
`async` da declaração — o recorte não compila. Aqui o recorte começa no
`async`.

🪤 dukpy (duktape) NÃO é o navegador do cliente: não há DOM, e o que a tela
faz com `document` tem que ser encenado pelo teste. O que ele executa de
verdade é a LÓGICA — status da resposta, o que é lançado, o que é restaurado,
o que a função devolve como HTML. É exatamente onde os guardas cegos estavam.

🪤 `import dukpy` é DURO de propósito: `pytest.importorskip` transformaria
"a ferramenta não está instalada" em teste pulado, e teste pulado dá a mesma
paz falsa que os guardas que este arquivo veio substituir. Ele está no
`pip install` da bancada (.github/workflows/bancada.yml).
"""
import io
import os

import dukpy  # noqa: F401  (ver docstring: a falta dele tem que ser ERRO, não skip)

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)


def fonte_html(arquivo: str) -> str:
    return io.open(os.path.join(_RAIZ, arquivo), encoding="utf-8").read()


def _do_marcador_ate_fechar(src: str, i: int, oque: str) -> str:
    """Do índice `i` até a chave que fecha a PRIMEIRA aberta depois dele.

    🪤 Balanço de chaves não entende chave dentro de string/regex. Quando isso
    acontecer o recorte sai truncado — e o motor JS recusa com SyntaxError na
    hora de carregar, que é o controle desta função (um recorte errado não
    passa despercebido como passaria numa janela de texto).
    """
    k = src.find("{", i)
    if k < 0:
        raise AssertionError("não achei corpo pra %s" % oque)
    prof = 0
    while k < len(src):
        if src[k] == "{":
            prof += 1
        elif src[k] == "}":
            prof -= 1
            if prof == 0:
                return src[i:k + 1]
        k += 1
    raise AssertionError("chaves desbalanceadas em %s" % oque)


def funcao_js(nome: str, arquivo: str, src: str = None) -> str:
    """A declaração INTEIRA da função, com o `async` quando ele existe."""
    src = fonte_html(arquivo) if src is None else src
    i = src.find("function %s(" % nome)
    if i < 0:
        raise AssertionError("não achei function %s() em %s" % (nome, arquivo))
    if src[max(0, i - 6):i] == "async ":
        i -= 6
    return _do_marcador_ate_fechar(src, i, "%s (%s)" % (nome, arquivo))


def handler_js(nome_novo: str, marcador: str, arquivo: str, src: str = None) -> str:
    """O handler ANÔNIMO de um addEventListener, virando função com nome.

    O submit do formulário de edição — o pior dos quatro salvamentos, porque
    troca o número do item na tela ANTES de gravar — não tem nome nenhum:
    é uma arrow passada direto pro `addEventListener`. `marcador` é o trecho
    exato que precede a arrow no fonte; o corpo dela sai daqui inteiro e sem
    uma vírgula alterada.
    """
    src = fonte_html(arquivo) if src is None else src
    i = src.find(marcador)
    if i < 0:
        raise AssertionError("não achei %r em %s" % (marcador[:60], arquivo))
    j = i + len(marcador)
    corpo = _do_marcador_ate_fechar(src, j, "handler %s (%s)" % (nome_novo, arquivo))
    return "var %s = %s;" % (nome_novo, corpo)


def motor(preludio: str = "") -> "dukpy.JSInterpreter":
    """Um motor JS com o prelúdio já carregado.

    🪤 O motor só drena a fila de promessas ao FIM de um `evaljs`. Por isso
    quem chama uma função async tem que ler o resultado num `evaljs`
    SEGUINTE — `rodar()` faz isso.
    """
    js = dukpy.JSInterpreter()
    if preludio:
        js.evaljs(preludio)
    return js


def rodar(js, chamada: str, guarda: str = "__R") -> dict:
    """Executa uma chamada async e devolve {'ok':..} ou {'erro': mensagem}.

    A leitura do resultado sai num `evaljs` separado — é o que faz duktape
    rodar a fila de microtarefas e a promessa realmente terminar.
    """
    js.evaljs("var %s = {pendente:true};" % guarda)
    js.evaljs(
        "Promise.resolve().then(function(){ return %s; })"
        ".then(function(v){ %s = {ok:true, valor:v===undefined?null:v}; },"
        " function(e){ %s = {erro: String((e && e.message) || e)}; });"
        % (chamada, guarda, guarda))
    bruto = js.evaljs("JSON.stringify(%s)" % guarda)
    import json as _json
    fora = _json.loads(bruto)
    assert not fora.get("pendente"), (
        "a promessa de %s não terminou — o motor não drenou a fila" % chamada)
    return fora
