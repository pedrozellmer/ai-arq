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
import json
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


def _data_da_copia_commitada(sitemap_path=None, posts_path=None):
    """A data editorial em que a cópia COMMITADA foi gerada: o maior
    `publish_date` entre os posts que o sitemap commitado já publica.

    🩸 04/10/2026: o teste regenerava com a data REAL. No dia em que um post
    agendado entrava, o gerador o publicava (sai do noindex, entra no sitemap,
    no llms.txt e nos cards de relacionados) e a cópia commitada ficava "velha"
    — 20 falhas no CI, com o site certo (o deploy regenera). Regenerando na
    data da cópia, a comparação volta a medir o que importa: HTML editado à mão
    ou posts.json mexido sem rodar o gerador."""
    sitemap_path = sitemap_path or os.path.join(_RAIZ, "sitemap.xml")
    posts_path = posts_path or os.path.join(_BLOG, "posts.json")
    if not (os.path.exists(sitemap_path) and os.path.exists(posts_path)):
        return None
    slugs = set(re.findall(r"/blog/posts/([^/<\"]+)\.html",
                           io.open(sitemap_path, encoding="utf-8").read()))
    d = json.load(io.open(posts_path, encoding="utf-8"))
    posts = d if isinstance(d, list) else d.get("posts", [])
    datas = [p["publish_date"] for p in posts if p.get("slug") in slugs]
    return max(datas) if datas else None


def _hoje_real():
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=3)).date().isoformat()


@pytest.fixture(scope="module")
def gerado():
    """Roda o gerador numa CÓPIA — nunca no repo — na data editorial da cópia
    commitada (`_data_da_copia_commitada`), e devolve a pasta."""
    if not os.path.isdir(_BLOG):
        pytest.skip("pasta blog/ não encontrada")
    tmp = tempfile.mkdtemp(prefix="blog_gen_")
    dest = os.path.join(tmp, "blog")
    shutil.copytree(_BLOG, dest)
    env = dict(os.environ)
    data = _data_da_copia_commitada()
    if data:
        env["BLOG_HOJE"] = data
    r = subprocess.run([sys.executable, "generate.py"], cwd=dest, env=env,
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


def test_o_gerador_escreve_o_llms_txt_igual_ao_do_repo(gerado):
    """27/09/2026: o llms.txt passou a sair do generate.py (ver
    test_llms_txt_e_gerado.py). Se a chamada sumir do main(), o deploy serve o
    arquivo velho do repo e post novo nunca mais entra — sem teste reclamar."""
    escrito = os.path.join(os.path.dirname(gerado), "llms.txt")
    assert os.path.exists(escrito), "blog/generate.py rodou e não escreveu o llms.txt"
    no_repo = io.open(os.path.join(_RAIZ, "llms.txt"), encoding="utf-8").read()
    assert _estavel(no_repo) == _estavel(io.open(escrito, encoding="utf-8").read()), (
        "llms.txt do repo difere do que blog/generate.py escreve — rode o gerador")


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


# ── 04/10/2026: a data editorial da cópia commitada ──────────────────────────
def _sitemap_e_posts(tmp_path, publicados, todos):
    sm = tmp_path / "sitemap.xml"
    sm.write_text("<urlset>" + "".join(
        "<url><loc>https://ai.arq.br/blog/posts/%s.html</loc></url>" % s for s in publicados)
        + "</urlset>", encoding="utf-8")
    pj = tmp_path / "posts.json"
    pj.write_text(json.dumps([{"slug": s, "publish_date": d} for s, d in todos]), encoding="utf-8")
    return str(sm), str(pj)


def test_a_data_da_copia_e_o_ultimo_post_que_o_sitemap_publica(tmp_path):
    sm, pj = _sitemap_e_posts(tmp_path, ["a", "b"],
                              [("a", "2026-09-20"), ("b", "2026-09-27"), ("c", "2026-10-04")])
    assert _data_da_copia_commitada(sm, pj) == "2026-09-27"


def test_CONTROLE_sem_post_no_sitemap_nao_fixa_data(tmp_path):
    sm, pj = _sitemap_e_posts(tmp_path, [], [("c", "2026-10-04")])
    assert _data_da_copia_commitada(sm, pj) is None


def test_a_copia_commitada_nao_publica_post_do_futuro():
    """O outro lado da porta: se alguém gerar o blog com a data adiantada e
    commitar, um post agendado iria pro sitemap antes da hora."""
    data = _data_da_copia_commitada()
    assert data is not None, "o sitemap commitado não publica nenhum post do blog"
    assert data <= _hoje_real(), (
        "a cópia commitada publica post de %s, depois de hoje (%s)" % (data, _hoje_real()))


def test_o_gerador_aceita_a_data_fixa():
    """`BLOG_HOJE` é o que o teste usa pra regenerar na data da cópia."""
    env = dict(os.environ, BLOG_HOJE="2026-01-02")
    r = subprocess.run([sys.executable, "-B", "-c", "import generate; print(generate.hoje_editorial())"],
                       cwd=_BLOG, env=env, capture_output=True, text=True, timeout=60,
                       encoding="utf-8", errors="replace")
    assert r.stdout.strip() == "2026-01-02", r.stdout + r.stderr
