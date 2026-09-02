# -*- coding: utf-8 -*-
"""O admin "de visita" na tela do cliente não pode gastar o reprocesso dele sem saber.

🩸 02/09/2026. Desde 01/09 todos os links de projeto do painel abrem
`projeto.html?adm=1&job_id=…` — a tela do CLIENTE, com uma barra "voltar ao
painel". Nessa tela existe o botão Reprocessar, que chama
`POST /api/project/{job_id}/reprocess` e incrementa `reprocess_count` do
projeto. É 1 por projeto (REPROCESS_FREE_LIMIT = 1); depois a rota responde
402 e não volta nunca. O backend deixa o admin passar (`_require_project_owner`
libera ADMIN_EMAIL) e NÃO distingue quem clicou.

No banco (02/09): 288 projetos, 23 com reprocess_count = 1, nenhum com 2. O
admin abriu projeto de outra pessoa 96 vezes (47 projetos distintos, 33 nos
últimos 7 dias) — ou seja, a exposição é diária. Quantos dos 23 foram gastos
pelo Pedro de visita? SEM MEDIÇÃO: não havia rastro (o backend não sabe).

O conserto: quando `adm=1` E a sessão é do admin (a MESMA checagem que mostra a
barra, agora exposta em `window.__adminDeVisita`), o clique pede uma segunda
confirmação que diz de QUEM é o reprocesso e aponta o caminho seguro
("Avaliar (isolado)" no painel). Recusar não gasta nada e devolve o foco à barra.

🪤 Este guarda lê a ÁRVORE do JS (esprima), não o texto: um comentário com as
palavras certas não passa; a string tem que estar no argumento do confirm, e o
confirm tem que estar dentro do `if` que olha `_deVisita`, ANTES do fetch.
Hoje (29/08 e 02/09, 2×) guardas que procuravam palavra no fonte passaram
cegos com a palavra num comentário.
"""
import io
import os
import re

import pytest

esprima = pytest.importorskip("esprima")

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PAGINA = os.path.join(_RAIZ, "projeto.html")
_SCRIPT_INLINE = re.compile(r"(<script(?![^>]*\bsrc=)[^>]*>)(.*?)</script>", re.S | re.I)


def _normaliza(js):
    """Mesma normalização de test_js_paginas (esprima é ES2017)."""
    js = js.replace("?.(", ".__oc__(").replace("?.[", ".__oi__[").replace("?.", ".")
    js = re.sub(r"\bcatch\s*\{", "catch (_e) {", js)
    return js.replace("??=", "=").replace("??", "||")


def _fonte(caminho=None):
    return io.open(caminho or _PAGINA, encoding="utf-8").read()


def _arvores(src):
    fora = []
    for m in _SCRIPT_INLINE.finditer(src):
        tipo = re.search(r'type="([^"]+)"', m.group(1))
        if tipo and "javascript" not in tipo.group(1) and "module" not in tipo.group(1):
            continue
        if m.group(2).strip():
            fora.append(esprima.parseScript(_normaliza(m.group(2)), {"range": True}))
    return fora


def _anda(no):
    """Todos os nós da árvore, em ordem de fonte."""
    if no is None or not hasattr(no, "type"):
        return
    yield no
    for campo in dir(no):
        if campo.startswith("_") or campo in ("type", "range", "loc"):
            continue
        try:
            v = getattr(no, campo)
        except Exception:
            continue
        if isinstance(v, list):
            for x in v:
                if hasattr(x, "type"):
                    for y in _anda(x):
                        yield y
        elif hasattr(v, "type"):
            for y in _anda(v):
                yield y


def _tem_ident(no, nome):
    return any(n.type == "Identifier" and n.name == nome for n in _anda(no))


def _tem_membro(no, obj, prop):
    for n in _anda(no):
        if (n.type == "MemberExpression" and getattr(n.object, "type", "") == "Identifier"
                and n.object.name == obj and getattr(n.property, "name", "") == prop):
            return True
    return False


def _literais(no):
    """Todas as strings literais dentro de um nó, concatenadas na ordem."""
    return "".join(n.value for n in _anda(no) if n.type == "Literal" and isinstance(n.value, str))


def _e_confirm(no):
    if no.type != "CallExpression":
        return False
    c = no.callee
    if c.type == "Identifier" and c.name == "confirm":
        return True
    return c.type == "MemberExpression" and getattr(c.property, "name", "") == "confirm"


def _handler_do_reprocessar(src):
    for ast in _arvores(src):
        for n in _anda(ast):
            if (n.type == "CallExpression" and n.callee.type == "MemberExpression"
                    and getattr(n.callee.property, "name", "") == "addEventListener"
                    and getattr(n.callee.object, "name", "") == "btnReprocess"
                    and n.arguments and getattr(n.arguments[0], "value", "") == "click"):
                return n.arguments[1]
    pytest.fail("não achei btnReprocess.addEventListener('click', …) em %s" % _PAGINA)


def _if_do_admin(handler):
    """O `if` do clique que olha `_deVisita` e, dentro dele, o confirm com `_avisoAdmin`."""
    for n in _anda(handler):
        if n.type == "IfStatement" and _tem_ident(n.test, "_deVisita"):
            for c in _anda(n.consequent):
                if _e_confirm(c) and c.arguments and getattr(c.arguments[0], "name", "") == "_avisoAdmin":
                    return n, c
    pytest.fail("o clique em Reprocessar não tem `if (_deVisita …) { … confirm(_avisoAdmin …) }` — "
                "o admin de visita reprocessa o projeto do cliente sem segunda pergunta")


def _declaracao(no, nome):
    for n in _anda(no):
        if n.type == "VariableDeclarator" and getattr(n.id, "name", "") == nome:
            return n
    return None


# ── o conserto ──────────────────────────────────────────────────────────────
def test_o_clique_pergunta_de_novo_quando_e_o_admin_de_visita():
    handler = _handler_do_reprocessar(_fonte())
    _if_do_admin(handler)
    d = _declaracao(handler, "_deVisita")
    assert d is not None and _tem_membro(d.init, "window", "__adminDeVisita"), (
        "`_deVisita` tem que vir de `window.__adminDeVisita` — a MESMA checagem da barra "
        "(adm=1 E sessão do admin). Outra fonte é outra regra.")


def test_o_aviso_diz_de_quem_e_o_reprocesso_e_o_caminho_seguro():
    handler = _handler_do_reprocessar(_fonte())
    no_if, _ = _if_do_admin(handler)
    d = _declaracao(no_if.consequent, "_avisoAdmin")
    assert d is not None, "`_avisoAdmin` não é declarado dentro do if do admin"
    texto = _literais(d.init)
    assert "reprocesso grátis DESTE CLIENTE" in texto, (
        "o aviso não diz de QUEM é o reprocesso que vai ser gasto")
    assert "Avaliar (isolado)" in texto, (
        "o aviso não aponta o caminho que NÃO encosta no cliente")


def test_recusar_nao_chega_no_fetch():
    """O `return` tem que depender da resposta, e o confirm tem que vir ANTES
    do POST /reprocess — confirm depois do fetch é enfeite."""
    handler = _handler_do_reprocessar(_fonte())
    no_if, chamada = _if_do_admin(handler)
    d = _declaracao(no_if.consequent, "okAdmin")
    assert d is not None and any(c is chamada for c in _anda(d.init)), (
        "`okAdmin` não recebe a resposta do confirm")
    saidas = [n for n in _anda(no_if.consequent)
              if n.type == "IfStatement" and n.test.type == "UnaryExpression"
              and n.test.operator == "!" and getattr(n.test.argument, "name", "") == "okAdmin"
              and any(r.type == "ReturnStatement" for r in _anda(n.consequent))]
    assert saidas, "recusar (`!okAdmin`) não dá `return` — o reprocesso segue mesmo dizendo não"
    fetches = [n for n in _anda(handler)
               if n.type == "CallExpression" and getattr(n.callee, "name", "") == "authFetch"
               and n.arguments and "reprocess" in "".join(
                   q.value.cooked for q in getattr(n.arguments[0], "quasis", []) or [])]
    assert fetches, "não achei o authFetch(…/reprocess) dentro do clique"
    assert chamada.range[0] < fetches[0].range[0], "o confirm do admin vem DEPOIS do fetch"


def test_a_barra_responde_se_e_admin_e_falha_fechando():
    """`window.__adminDeVisita` é a Promise da barra: `true` só quando a
    sessão bate com o hash do admin; qualquer outro caminho devolve `false`."""
    fn = None
    for ast in _arvores(_fonte()):
        for n in _anda(ast):
            if (n.type == "AssignmentExpression" and _tem_membro(n.left, "window", "__adminDeVisita")
                    and n.right.type == "CallExpression"
                    and getattr(getattr(n.right.callee, "id", None), "name", "") == "mostrarBarraDoAdmin"):
                fn = n.right.callee
    assert fn is not None, "`window.__adminDeVisita` não recebe a Promise de mostrarBarraDoAdmin()"
    assert _tem_ident(fn, "aiarqEmailMatches") and _tem_ident(fn, "getSession"), (
        "a checagem deixou de olhar a sessão / o hash do admin")
    retornos = [n for n in _anda(fn) if n.type == "ReturnStatement"]
    verdadeiro = [r for r in retornos if r.argument is not None and r.argument.type == "BinaryExpression"
                  and r.argument.operator == "===" and getattr(r.argument.left, "name", "") == "ok"]
    assert verdadeiro, "nenhum `return ok === true` — a Promise nunca diz que é o admin"
    outros = [r for r in retornos if r not in verdadeiro]
    assert outros and all(r.argument is not None and r.argument.type == "Literal" and r.argument.value is False
                          for r in outros), (
        "todo caminho que não confirmou o admin tem que devolver `false` (sem adm=1, sem sessão, erro)")


# ── controles ───────────────────────────────────────────────────────────────
def test_CONTROLE_o_cliente_nao_le_palavra_de_admin():
    """O aviso que o CLIENTE vê (`_aviso`) não pode ganhar as palavras do admin —
    'Avaliar (isolado)' não existe pra ele e 'DESTE CLIENTE' seria vexatório."""
    handler = _handler_do_reprocessar(_fonte())
    d = _declaracao(handler, "_aviso")
    assert d is not None
    texto = _literais(d.init)
    assert "DESTE CLIENTE" not in texto and "Avaliar (isolado)" not in texto


def test_CONTROLE_o_guarda_reprova_quando_o_confirm_e_o_do_cliente():
    """Prova que o guarda REPROVA: trocando `_avisoAdmin` por `_aviso` no confirm
    (texto certo declarado, mas não é ele que aparece), o achado tem que sumir."""
    src = _fonte()
    sab = src.replace("window.toast.confirm(_avisoAdmin,", "window.toast.confirm(_aviso,")
    sab = sab.replace(": confirm(_avisoAdmin);", ": confirm(_aviso);")
    assert sab != src, "a sabotagem não pegou — o fonte mudou de forma?"
    with pytest.raises(BaseException):
        _if_do_admin(_handler_do_reprocessar(sab))


def test_CONTROLE_o_guarda_reprova_texto_so_em_comentario():
    """A palavra em COMENTÁRIO não conta (foi assim que 2 guardas passaram cegos hoje)."""
    src = _fonte()
    sab = src.replace("'Reprocessar daqui gasta o único reprocesso grátis DESTE CLIENTE (1 por projeto) ' +",
                      "// reprocesso grátis DESTE CLIENTE\n            '' +")
    assert sab != src
    handler = _handler_do_reprocessar(sab)
    no_if, _ = _if_do_admin(handler)
    assert "DESTE CLIENTE" not in _literais(_declaracao(no_if.consequent, "_avisoAdmin").init)
