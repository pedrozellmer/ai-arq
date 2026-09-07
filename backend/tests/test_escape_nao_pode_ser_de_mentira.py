# -*- coding: utf-8 -*-
"""Função chamada `esc` tem que ESCAPAR — executando, não pelo nome.

🩸 07/09/2026. `admin.html:2802`, dentro de `renderMotorHealth`:

    const esc = s => String(s==null?'':s);

Não escapava nada. Só convertia para string. As outras três `esc` do mesmo
arquivo sempre fizeram o `.replace()`; só essa era de mentira — e ela
**sombreava o nome** dentro de 252 linhas, servindo **36 chamadas**, entre elas
`r.descricao`, que o cliente EDITA na tela de revisão.

🔑 É o pior tipo de defeito: parece proteção, tem nome de proteção, e quem lê
`esc(...)` ali dentro acha que está coberto. Nenhum guarda pegava, porque todos
os guardas de escape desta casa conferiam que a CHAMADA se chama `esc` — nunca
o que `esc` FAZ. Um cético já tinha anotado a lacuna; quem achou a função real
foi um agente que conferia outra coisa.

🪤 Medido antes de chamar de incêndio: 29 descrições na base têm `<` ou `>`
(coisas como "≤ 10mm") e ZERO têm `script`, `img`, `svg` ou `on…=`. Buraco
vazio — mas buraco.

🔑 POR QUE ESTE GUARDA EXECUTA. Ler o fonte diria "existe um replace na linha".
Só rodar prova que o `<` não sai do outro lado, e o Duktape roda o mesmo
JavaScript que o navegador roda.
"""
import html as _html
import io
import os
import re

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))

#: 🚨 Import DURO de propósito. Com `importorskip`, a falta do dukpy viraria
#: skip silencioso e este arquivo ficaria verde sem testar nada — que é
#: exatamente a doença que ele existe pra pegar.
import dukpy  # noqa: E402

#: Conteúdo hostil de verdade.
#: 🪤 O julgamento é "sobrou caractere CRU?", e `&` NÃO entra nessa lista: a
#: saída correta de `Reforma & Cia` é `Reforma &amp; Cia`, que contém um `&`.
#: A 1ª versão deste guarda procurava `&` na saída e acusou as três funções
#: CERTAS do admin.html. Guarda que acusa o certo acaba desligado — e eu
#: escrevi um enquanto consertava outro.
_HOSTIS = [
    "<script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "Reforma & Cia <b>negrito</b>",
    'aspas "duplas" aqui',
]

#: Os que não podem sobreviver crus dentro de um innerHTML.
_CRUS_PROIBIDOS = ("<", ">", '"')

#: 🪤 Duktape não é navegador: não tem `window` nem `document`. Uma `esc` que os
#: mencione estoura em ReferenceError, e o guarda leria isso como "não escapa",
#: acusando código que pode estar certo. Este esqueleto mudo existe só pra a
#: função conseguir RODAR.
_ESQUELETO = (
    "var window = (typeof window !== 'undefined') ? window : {};"
    "var document = (typeof document !== 'undefined') ? document :"
    " {getElementById: function(){ return null; }};"
    "var location = (typeof location !== 'undefined') ? location : {href: ''};"
)


def _paginas():
    for nome in sorted(os.listdir(_RAIZ)):
        if nome.endswith(".html"):
            yield nome, io.open(os.path.join(_RAIZ, nome),
                                encoding="utf-8", errors="replace").read()


def _declaracoes_de_esc(src):
    """Toda `const esc = …`, com o corpo até o `;` da própria declaração.

    🪤 Recorte pelo fim da declaração, nunca por tamanho fixo — janela fixa
    mede o vizinho, e esta casa já tem 17 casos disso documentados.
    """
    fora = []
    for m in re.finditer(r"\bconst\s+(esc|escapeH|escapeHtml)\s*=\s*", src):
        i = m.end()
        prof, j = 0, i
        while j < len(src):
            c = src[j]
            if c in "({[":
                prof += 1
            elif c in ")}]":
                prof -= 1
            elif c == ";" and prof <= 0:
                break
            j += 1
        corpo = src[i:j].strip()
        if not _e_escape_de_html(corpo):
            continue
        fora.append((m.group(1), corpo, src[:m.start()].count("\n") + 1))
    return fora


def _e_escape_de_html(corpo):
    """Isto é uma função de escape de HTML, ou outra coisa com o mesmo nome?

    🩸 07/09 — a 1ª versão deste guarda julgava tudo que se chamasse `esc` e
    acusou DOIS trechos corretos:
      · `admin.html:5669` — escape de **CSV** (dobra aspas, envolve o campo).
        Correto pro que faz, e a saída CONTÉM `"` de propósito.
      · `projeto.html:1571` — `const esc = document.getElementById(...)`, um
        ELEMENTO chamado esc (escotilha). Nem função é.

    🔑 O filtro é por FATO, não por nome: precisa SER função, e não pode ter a
    assinatura de CSV (testar `,`/`;`/quebra e dobrar aspas). Guarda que acusa
    o certo acaba desligado — e eu escrevi um enquanto consertava outro.
    """
    if "=>" not in corpo and "function" not in corpo:
        return False                      # não é função: é elemento, valor, etc.
    csv = ('""' in corpo) and re.search(r"/\[[^]]*[,;][^]]*\]/", corpo)
    return not csv


def _roda(corpo, entrada):
    """Executa a função no Duktape. Devolve (ok, saida, erro)."""
    try:
        js = dukpy.JSInterpreter()
        out = js.evaljs("%s var _f = %s; _f(dukpy['x']);" % (_ESQUELETO, corpo),
                        x=entrada)
        return True, str(out), ""
    except Exception as e:
        return False, "", str(e)


def test_toda_funcao_de_escape_REALMENTE_escapa():
    """🚨 Executa cada `esc` de cada HTML da raiz com conteúdo hostil."""
    falhas = []
    for nome, src in _paginas():
        for como_chama, corpo, linha in _declaracoes_de_esc(src):
            for entrada in _HOSTIS:
                ok, saida, erro = _roda(corpo, entrada)
                if not ok:
                    falhas.append("%s:%d (%s) nao executou: %s"
                                  % (nome, linha, como_chama, erro[:90]))
                    break
                cru = [c for c in _CRUS_PROIBIDOS if c in saida]
                if cru:
                    falhas.append(
                        "%s:%d - `%s` devolveu %r com %s CRU. E passagem direta "
                        "com nome de escape: quem le `%s(...)` acha que esta "
                        "protegido." % (nome, linha, como_chama, saida[:70],
                                        cru, como_chama))
                    break
                if _html.unescape(saida) != entrada:
                    falhas.append("%s:%d - `%s` nao volta ao original: %r -> %r"
                                  % (nome, linha, como_chama, entrada, saida[:70]))
                    break
    assert not falhas, "escape de mentira:" + chr(10) + "  " + (chr(10) + "  ").join(falhas)


def test_CONTROLE_o_guarda_ACHA_o_escape_de_mentira():
    """🧪 A função exata que estava em produção até hoje."""
    _ok, saida, _e = _roda("s => String(s==null?'':s)", "<script>alert(1)</script>")
    assert "<" in saida, (
        "o controle parou de reproduzir o defeito — a funcao de mentira passou "
        "a escapar sozinha?")


def test_CONTROLE_o_guarda_ABSOLVE_o_escape_de_verdade():
    """O outro lado: guarda que acusa o certo acaba desligado."""
    de_verdade = ("s => String(s==null?'':s).replace(/[<>&\"]/g, "
                  "c => ({'<':'&lt;','>':'&gt;','&':'&amp;','\"':'&quot;'}[c]))")
    for entrada in _HOSTIS:
        ok, saida, erro = _roda(de_verdade, entrada)
        assert ok, erro
        assert not [c for c in _CRUS_PROIBIDOS if c in saida], (entrada, saida)
        assert _html.unescape(saida) == entrada, (entrada, saida)


def test_CONTROLE_o_detector_ACHA_as_declaracoes():
    """Se `_declaracoes_de_esc` devolvesse vazio, o teste principal passaria
    sem olhar nada — verde vazio."""
    achadas = [(n, l) for n, s in _paginas() for _c, _b, l in _declaracoes_de_esc(s)]
    assert len(achadas) >= 4, (
        "o detector achou so %d declaracoes de escape no site — em 07/09 eram "
        "pelo menos 4 so no admin.html" % len(achadas))
    assert any(n == "admin.html" for n, _l in achadas)


@pytest.mark.parametrize("entrada", _HOSTIS)
def test_CONTROLE_cada_conteudo_hostil_e_de_fato_hostil(entrada):
    """🪤 Se um caso de teste não tivesse caractere que precisa de escape, ele
    passaria sempre e daria sensação falsa de cobertura."""
    assert [c for c in _CRUS_PROIBIDOS + ("&",) if c in entrada], entrada
