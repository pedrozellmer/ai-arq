# -*- coding: utf-8 -*-
"""O que o cliente digita não pode virar HTML no painel do Pedro.

🚨 08/09/2026, auditoria de segurança — XSS ARMAZENADO NO ADMIN.

`unidade` está na lista do que o CLIENTE pode editar pela revisão
(`allowed = {description, unit, quantity, discipline, observations}` em
main.py) e é gravada VERBATIM: sem sanitização, sem teto de tamanho, coluna
`text` sem limite. A única regra sobre ela é "não pode ficar vazia".

Daí ela vinha CRUA pro `innerHTML` de dois painéis do admin. A vítima é o
Pedro — a sessão dele é a que manda no sistema — e o gatilho é ele abrir o
painel. Não precisa de nada além de um cliente digitar a unidade certa.

🪤 A descrição já tinha `.replace(/</g,'&lt;')`: escape pela METADE, que não
cobre `"` nem `&`. Meio escape é pior que nenhum, porque ensina que está
escapado.

🔑 UMA função, içada. Existiam TRÊS cópias locais de `esc` no arquivo, todas
definidas DEPOIS destes dois pontos e invisíveis ali. Três cópias da mesma
régua é como as coisas se separam — foi o mesmo defeito da frase da escala e do
parser de área, hoje.
"""
import io
import os
import re

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)
_ADMIN = os.path.join(_RAIZ, "admin.html")
_MAIN = os.path.join(_BACKEND, "main.py")


def _admin():
    return io.open(_ADMIN, encoding="utf-8", errors="replace").read()


def _escapador():
    """Executa o `_escHtml` REAL do admin.html num duktape."""
    import sys
    if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _bancada_js import Pagina
    src = _admin()
    i = src.index("function _escHtml(s) {")
    j = src.index("\n}", i) + 2
    p = Pagina(arquivos=(), prelude_extra="1;")
    p.eval(src[i:j] + "\n;1;")
    return p


# ══════════════════════════════════════════════════════════════════════════
#  A função escapa de verdade — inclusive o que o meio-escape deixava passar
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("bruto,proibido", [
    ('<img src=x onerror=alert(1)>', '<img'),
    ('</span><script>alert(1)</script>', '<script'),
    ('" onmouseover="alert(1)', '" onmouseover'),
    ("' onfocus='alert(1)", "' onfocus"),
    ('&lt;script&gt;', '&lt;s'),          # & tem que virar &amp;
])
def test_o_escapador_neutraliza(bruto, proibido):
    p = _escapador()
    import json
    saiu = p.eval("_escHtml(%s)" % json.dumps(bruto))
    assert proibido not in saiu, "passou %r: %r" % (proibido, saiu)
    assert "<" not in saiu and ">" not in saiu, saiu


def test_CONTROLE_texto_normal_continua_legivel():
    """Escapar tudo é fácil e deixaria o painel ilegível."""
    p = _escapador()
    assert p.eval('_escHtml("m²")') == "m²"
    assert p.eval('_escHtml("Alvenaria de bloco 14cm")') == "Alvenaria de bloco 14cm"
    assert p.eval("_escHtml(null)") == ""
    assert p.eval("_escHtml(undefined)") == ""


def test_o_meio_escape_do_menor_que_NAO_bastava():
    """🧪 Prova que o conserto era necessário: a forma antiga (só `<`) deixava
    passar o atributo com aspas, que é XSS igual."""
    antigo = lambda s: s.replace("<", "&lt;")          # noqa: E731
    ataque = '" onmouseover="alert(1)'
    assert '" onmouseover' in antigo(ataque), "o controle não reproduz o defeito"
    p = _escapador()
    import json
    assert '" onmouseover' not in p.eval("_escHtml(%s)" % json.dumps(ataque))


# ══════════════════════════════════════════════════════════════════════════
#  Os dois sinks usam a função — e o campo continua editável pelo cliente
# ══════════════════════════════════════════════════════════════════════════
def test_os_dois_sinks_passam_pelo_escapador():
    src = _admin()
    crus = []
    for m in re.finditer(r"\$\{([^}]*e\.(?:unidade|descricao|marca|codigo|cor)[^}]*)\}", src):
        trecho = m.group(1)
        if "_escHtml" not in trecho:
            crus.append(trecho.strip()[:70])
    assert not crus, (
        "campo editável pelo cliente indo cru pro innerHTML do admin: %s" % crus)


def test_o_campo_unidade_CONTINUA_editavel_pelo_cliente():
    """🔑 O guarda só faz sentido enquanto o campo for do cliente. Se um dia
    `unit` sair da lista, este teste avisa que a premissa mudou — em vez de o
    guarda virar enfeite silencioso."""
    src = io.open(_MAIN, encoding="utf-8", errors="replace").read()
    assert re.search(r"allowed\s*=\s*\{[^}]*['\"]unit['\"]", src), (
        "`unit` saiu da lista de campos editáveis pelo cliente — reveja se este "
        "guarda ainda descreve a realidade")


def test_o_escapador_e_UM_SO_e_alcanca_os_sinks():
    """🪤 Existiam 3 cópias locais de `esc`, todas invisíveis nos dois sinks.
    A função nova é `function` (içada) de propósito: `const` só existe depois
    da linha em que é declarado, e foi por isso que as três não serviam."""
    src = _admin()
    assert "function _escHtml(s)" in src, (
        "o escapador virou `const` ou sumiu — se for const, ele deixa de "
        "existir nos sinks que vêm antes dele no arquivo")
    i_def = src.index("function _escHtml(s)")
    i_uso = src.index("_escHtml(e.descricao)")
    assert i_def < i_uso, "a definição tem que vir antes do uso, por clareza"
