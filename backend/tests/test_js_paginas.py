# -*- coding: utf-8 -*-
"""Sintaxe do JavaScript de TODAS as páginas — inclusive redeclaração léxica.

🚨 24/08/2026: `revisao.html` ficou MORTA em produção por ~3 horas. Eu declarei
`let ok = 0` dentro de uma função que já tinha `const ok` 37 linhas acima. Isso
é SyntaxError, e SyntaxError num <script> inline mata o bloco INTEIRO — não só
a função. loadItems, render e bulkReview nunca chegaram a existir; ninguém
conseguia revisar item nenhum.

🪤 E o meu validador tinha dado VERDE nas 12 páginas. `esprima.parseScript`
monta a árvore mas NÃO faz a checagem de escopo léxico, que é uma etapa
posterior da especificação (early errors). Guarda que não reprova é guarda que
aprova tudo — mesma lição do teste da tupla, no dia anterior.

Por isso este arquivo mora no repo e roda no CI, e não num script solto: a
checagem só vale se ela rodar sozinha, antes do push.
"""
import io
import os
import re

import pytest

esprima = pytest.importorskip("esprima")

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPT_INLINE = re.compile(r"(<script(?![^>]*\bsrc=)[^>]*>)(.*?)</script>", re.S | re.I)

# Cria escopo léxico próprio (um `let` aqui dentro não colide com o de fora)
_ABRE_ESCOPO = {
    "Program", "BlockStatement", "FunctionDeclaration", "FunctionExpression",
    "ArrowFunctionExpression", "ForStatement", "ForInStatement", "ForOfStatement",
    "SwitchStatement", "CatchClause", "ClassBody", "StaticBlock",
}


def _normaliza(js: str) -> str:
    """esprima aqui é ES2017: normaliza o que veio depois (optional chaining,
    catch sem binding, nullish). Não muda escopo, só faz o parse passar."""
    js = js.replace("?.(", ".__oc__(").replace("?.[", ".__oi__[").replace("?.", ".")
    js = re.sub(r"\bcatch\s*\{", "catch (_e) {", js)
    return js.replace("??=", "=").replace("??", "||")


def _nomes(alvo):
    """Nomes declarados por um padrão (id simples, desestruturação, rest)."""
    if alvo is None:
        return []
    t = getattr(alvo, "type", None)
    if t == "Identifier":
        return [alvo.name]
    if t == "ObjectPattern":
        fora = []
        for pr in (alvo.properties or []):
            fora += _nomes(getattr(pr, "value", None) or getattr(pr, "argument", None))
        return fora
    if t == "ArrayPattern":
        fora = []
        for el in (alvo.elements or []):
            fora += _nomes(el)
        return fora
    if t in ("RestElement", "AssignmentPattern"):
        return _nomes(getattr(alvo, "argument", None) or getattr(alvo, "left", None))
    return []


def _redeclaracoes(ast):
    """Nomes declarados 2× com let/const/class no MESMO escopo léxico."""
    achados = []

    def visita(no, escopo):
        if no is None or not hasattr(no, "type"):
            return
        t = no.type
        meu = {} if t in _ABRE_ESCOPO else escopo

        if t == "VariableDeclaration" and no.kind in ("let", "const"):
            for d in (no.declarations or []):
                for nome in _nomes(getattr(d, "id", None)):
                    if nome in escopo:
                        achados.append((nome, no.kind, escopo[nome]))
                    escopo[nome] = no.kind
        elif t == "ClassDeclaration" and getattr(no, "id", None) is not None:
            nome = no.id.name
            if nome in escopo:
                achados.append((nome, "class", escopo[nome]))
            escopo[nome] = "class"

        for campo in dir(no):
            if campo.startswith("_") or campo == "type":
                continue
            try:
                v = getattr(no, campo)
            except Exception:
                continue
            if isinstance(v, list):
                for x in v:
                    if hasattr(x, "type"):
                        visita(x, meu)
            elif hasattr(v, "type"):
                visita(v, meu)

    visita(ast, {})
    return achados


def _blocos(caminho):
    src = io.open(caminho, encoding="utf-8").read()
    if caminho.endswith(".js"):
        return [(1, src)]
    fora = []
    for m in _SCRIPT_INLINE.finditer(src):
        tipo = re.search(r'type="([^"]+)"', m.group(1))    # só na tag de abertura
        if tipo and "javascript" not in tipo.group(1) and "module" not in tipo.group(1):
            continue
        if m.group(2).strip():
            fora.append((src[:m.start()].count("\n") + 1, m.group(2)))
    return fora


def _paginas():
    fora = []
    for nome in sorted(os.listdir(_RAIZ)):
        if nome.endswith(".html") or (nome.endswith(".js") and not nome.endswith(".min.js")):
            fora.append(os.path.join(_RAIZ, nome))
    blog = os.path.join(_RAIZ, "blog", "posts")
    if os.path.isdir(blog):
        fora += [os.path.join(blog, n) for n in sorted(os.listdir(blog)) if n.endswith(".html")]
    return fora


_PAGINAS = _paginas()


def test_achei_as_paginas():
    assert len(_PAGINAS) >= 15, "esperava dezenas de páginas, achei %d" % len(_PAGINAS)


@pytest.mark.parametrize("caminho", _PAGINAS, ids=lambda c: os.path.basename(c))
def test_pagina_tem_javascript_valido(caminho):
    for linha, js in _blocos(caminho):
        try:
            ast = esprima.parseScript(_normaliza(js))
        except Exception as e:
            pytest.fail("%s (script da linha %d): %s" % (os.path.basename(caminho), linha, e))
        ruins = _redeclaracoes(ast)
        assert not ruins, (
            "%s (script da linha %d): redeclaração léxica no MESMO escopo — isto é "
            "SyntaxError e mata o <script> INTEIRO em produção:\n  %s"
            % (os.path.basename(caminho), linha,
               "\n  ".join("%s declarado como %s e de novo como %s" % (n, a, b)
                           for n, b, a in ruins)))


def test_o_guarda_reprova_o_bug_que_matou_a_revisao():
    """🚨 Controle positivo, sem o qual este arquivo não vale nada.

    Esta é a forma EXATA que derrubou revisao.html — e que o validador antigo,
    baseado só em `esprima.parseScript`, aprovava."""
    veneno = """
    async function bulkReview(section, action) {
      const ok = window.toast ? await window.toast.confirm('x') : confirm('x');
      if (!ok) return;
      const limit = 5;
      let ok = 0;
      return ok + limit;
    }
    """
    esprima.parseScript(veneno)          # o parser sozinho ACEITA: é essa a armadilha
    assert _redeclaracoes(esprima.parseScript(veneno)), (
        "o guarda não pega a redeclaração — foi exatamente assim que a tela de "
        "revisão passou batido e quebrou em produção")


def test_o_guarda_nao_reprova_codigo_sao():
    """Controle negativo: escopos DIFERENTES podem repetir o nome, e isso é
    normal em toda página nossa (vários `const ok` em funções distintas)."""
    sao = """
    function a() { const ok = 1; return ok; }
    function b() { const ok = 2; return ok; }
    function c() { if (true) { let x = 1; } else { let x = 2; } for (let x of [1]) { } }
    const f = () => { const ok = 3; return ok; };
    """
    assert not _redeclaracoes(esprima.parseScript(sao)), (
        "o guarda reprova código são — ia travar todo push por nada")
