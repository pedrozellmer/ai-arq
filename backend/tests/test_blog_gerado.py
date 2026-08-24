# -*- coding: utf-8 -*-
"""O HTML do blog no repo tem que ser o que o gerador produz.

🚨 24/08/2026: em 23/08 eu "consertei" a divergência de estatística do post que
ranqueia editando o HTML à mão — a nota "Atualizado em 23/08". Commitei, o CI
ficou verde, e eu disse ao Pedro que estava resolvido.

Nunca foi pro ar. O workflow de deploy roda `python blog/generate.py`, que
reescreve `blog/posts/<slug>.html` do zero a partir de `blog/posts.json`. A
minha edição foi apagada no próprio deploy que deveria publicá-la. Medido:
no repo a nota existia, na fonte não existia, no ar não aparecia.

Este teste fecha a porta: se alguém editar o HTML gerado em vez da fonte, ou
esquecer de rodar o gerador depois de mexer no posts.json, a bancada reprova
ANTES do push — em vez de o deploy desfazer em silêncio.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BLOG = os.path.join(_RAIZ, "blog")

# O gerador carimba a data/hora da geração em alguns lugares; comparar isso
# daria falso vermelho todo dia. Some com o que é volátil de propósito.
_VOLATIL = [
    re.compile(r"\?v=[0-9a-f]{6,}"),
    re.compile(r"<lastmod>[^<]*</lastmod>"),
    re.compile(r'"dateModified"\s*:\s*"[^"]*"'),
]


def _estavel(txt):
    for rx in _VOLATIL:
        txt = rx.sub("", txt)
    return txt.strip()


@pytest.fixture(scope="module")
def gerado():
    """Roda o gerador numa CÓPIA — nunca no repo — e devolve a pasta."""
    if not os.path.isdir(_BLOG):
        pytest.skip("pasta blog/ não encontrada")
    tmp = tempfile.mkdtemp(prefix="blog_gen_")
    dest = os.path.join(tmp, "blog")
    shutil.copytree(_BLOG, dest)
    r = subprocess.run([sys.executable, "generate.py"], cwd=dest,
                       capture_output=True, text=True, timeout=300,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        pytest.fail("blog/generate.py falhou:\n" + (r.stdout or "") + (r.stderr or ""))
    yield dest
    shutil.rmtree(tmp, ignore_errors=True)


def _posts():
    d = os.path.join(_BLOG, "posts")
    if not os.path.isdir(d):
        return []
    return sorted(n for n in os.listdir(d) if n.endswith(".html"))


@pytest.mark.parametrize("nome", _posts())
def test_post_commitado_e_igual_ao_gerado(nome, gerado):
    """Se estes dois divergem, o que está no ar é o GERADO — a edição no repo
    é ilusão de conserto."""
    no_repo = io.open(os.path.join(_BLOG, "posts", nome), encoding="utf-8").read()
    novo = os.path.join(gerado, "posts", nome)
    assert os.path.exists(novo), (
        "%s existe no repo mas o gerador não produz — post órfão, some no "
        "próximo deploy" % nome)
    assert _estavel(no_repo) == _estavel(io.open(novo, encoding="utf-8").read()), (
        "%s no repo difere do que blog/generate.py produz.\n"
        "O deploy roda o gerador, então quem vale é a FONTE (blog/posts.json).\n"
        "Se você editou o HTML à mão, mova a mudança pro posts.json e rode "
        "`python blog/generate.py`." % nome)


def test_a_nota_de_atualizacao_mora_na_fonte():
    """Controle do caso concreto que originou este arquivo."""
    fonte = io.open(os.path.join(_BLOG, "posts.json"), encoding="utf-8").read()
    assert "update_note" in fonte, (
        "o campo update_note sumiu do posts.json — a nota datada do post de "
        "DWG × PDF volta a existir só no HTML e some no próximo deploy")
    html = io.open(os.path.join(_BLOG, "posts",
                                "dwg-ou-pdf-quantitativo-o-que-os-dados-mostram.html"),
                   encoding="utf-8").read()
    assert "Atualizado em 23/08/2026" in html
    assert "4,6" in html and "21,6%" in html, (
        "a nota tem que carregar o número novo, senão não resolve a divergência "
        "com a home")


def test_o_gerador_ignora_update_note_ausente():
    """Controle negativo: post sem a nota não pode ganhar caixa vazia."""
    import json
    d = json.loads(io.open(os.path.join(_BLOG, "posts.json"), encoding="utf-8").read())
    posts = d if isinstance(d, list) else d["posts"]
    sem = [x for x in posts if not (x.get("update_note") or "").strip()]
    assert sem, "esperava posts sem update_note pra usar como controle"
    alvo = os.path.join(_BLOG, "posts", sem[0]["slug"] + ".html")
    if not os.path.exists(alvo):
        pytest.skip("post de controle ainda não gerado (data futura)")
    html = io.open(alvo, encoding="utf-8").read()
    assert "bg-indigo-50 px-4 py-3 text-sm text-indigo-900" not in html, (
        "post sem nota ganhou a tarja de atualização vazia")
