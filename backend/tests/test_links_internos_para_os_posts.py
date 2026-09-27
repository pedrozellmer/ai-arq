# -*- coding: utf-8 -*-
"""Links internos que levam a gente aos posts — e nunca a um post que ainda não saiu.

🔗 27/09/2026 (auditoria de aquisição, item 6). Medido em 26/09 nos HTML
servidos: home, preços, FAQ e exemplo linkavam ZERO posts, e os 23 posts no ar
tinham ZERO links internos no corpo (fora download). Cada post recebia 3 a 6
links, todos do "Leia também" e do /blog/. O único caminho de um post pro
produto era o CTA do rodapé.

Agora: linha "Guias" no rodapé da home, FAQ e preços (nunca acima do CTA da
home, que é o que converte); 1–2 links no corpo dos posts com tráfego (a prova,
/exemplo.html, e o post irmão); o FAQ aponta pro post do mesmo assunto.
"""
import io
import json
import os
import re
from datetime import datetime, timedelta, timezone

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LINK_POST = re.compile(r'href="(?:https://ai\.arq\.br)?/blog/posts/([a-z0-9-]+)\.html"')

COM_TRAFEGO = [
    "extrair-quantitativo-do-dwg-automatico-sem-bim",
    "quantitativo-de-obra-com-ia",
    "quantitativo-arquitetura-sinapi-planilha-modelo",
    "quadro-de-areas-modelo-excel-nbr-12721",
    "cronograma-fisico-financeiro-obra-modelo",
    "memorial-descritivo-de-obra-modelo-pdf-docx",
]
GUIAS = [
    "extrair-quantitativo-do-dwg-automatico-sem-bim",
    "quantitativo-de-obra-com-ia",
    "dwg-ou-pdf-quantitativo-o-que-os-dados-mostram",
    "quantitativo-arquitetura-sinapi-planilha-modelo",
    "memorial-descritivo-de-obra-modelo-pdf-docx",
]


def _ler(rel):
    return io.open(os.path.join(_RAIZ, rel), encoding="utf-8").read()


def _posts():
    d = json.loads(_ler("blog/posts.json"))
    return {p["slug"]: p for p in (d if isinstance(d, list) else d["posts"])}


def _hoje():
    return (datetime.now(timezone.utc) - timedelta(hours=3)).date().isoformat()


def _corpo(post):
    return " ".join(str(s.get("body", "")) for s in post.get("sections", []))


def _links_para_o_futuro(posts):
    """Post que linka, no corpo, outro que publica DEPOIS dele (ou que não existe)."""
    ruins = []
    for slug, p in posts.items():
        for alvo in _LINK_POST.findall(_corpo(p)):
            if alvo not in posts:
                ruins.append("%s → %s (não existe)" % (slug, alvo))
            elif posts[alvo]["publish_date"] > p["publish_date"]:
                ruins.append("%s (%s) → %s (%s)" % (slug, p["publish_date"], alvo, posts[alvo]["publish_date"]))
    return ruins


def test_nenhum_post_linka_post_que_sai_depois_dele():
    """No dia em que o post publica, o alvo já tem que estar no ar — senão o
    leitor cai no guarda JS e volta pro /blog/, e o robô segue pra um noindex."""
    ruins = _links_para_o_futuro(_posts())
    assert not ruins, "link no corpo pra post que ainda não saiu: %s" % ruins


def test_os_posts_com_trafego_tem_link_interno_no_corpo():
    posts = _posts()
    sem = [s for s in COM_TRAFEGO
           if not re.search(r'href="/(exemplo\.html|blog/posts/[a-z0-9-]+\.html)"', _corpo(posts[s]))]
    assert not sem, "post com tráfego sem nenhum link interno no corpo: %s" % sem


def test_as_paginas_de_entrada_so_linkam_post_publicado():
    posts, hoje = _posts(), _hoje()
    for pag in ("index.html", "faq.html", "precos.html", "sobre.html", "exemplo.html"):
        for alvo in _LINK_POST.findall(_ler(pag)):
            assert alvo in posts, "%s linka post que não existe: %s" % (pag, alvo)
            assert posts[alvo]["publish_date"] <= hoje, "%s linka post agendado: %s" % (pag, alvo)


def test_o_rodape_de_home_faq_e_precos_tem_os_guias():
    for pag in ("index.html", "faq.html", "precos.html"):
        src = _ler(pag)
        m = re.search(r'<nav aria-label="Guias".*?</nav>', src, re.S)
        assert m, "%s perdeu a linha de Guias do rodapé" % pag
        assert _LINK_POST.findall(m.group(0)) == GUIAS, (pag, _LINK_POST.findall(m.group(0)))
        assert src.index(m.group(0)) > src.index("<footer"), "%s: os Guias saíram do rodapé" % pag


def _post_acima_do_rodape(src):
    corte = src.index("<footer")
    return _LINK_POST.findall(src[:corte])


def test_a_home_nao_poe_post_no_fluxo_acima_do_cta():
    """A home converte o que a auditoria mediu como a maior taxa do site; link
    pra post no meio do fluxo tira gente do caminho do cadastro."""
    assert not _post_acima_do_rodape(_ler("index.html"))


def test_os_data_track_novos_tem_nome_valido():
    """O evento `clique:<nome>` só é aceito com [a-z0-9-], até 40 caracteres."""
    nomes = set()
    for pag in ("index.html", "faq.html", "precos.html"):
        nomes |= set(re.findall(r'data-track="([^"]+)"', _ler(pag)))
    for p in _posts().values():
        nomes |= set(re.findall(r'data-track="([^"]+)"', _corpo(p)))
    ruins = [n for n in nomes if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", n)]
    assert not ruins, ruins


def _classes_sem_css(html_bloco, css):
    classes = set()
    for m in re.finditer(r'class="([^"]+)"', html_bloco):
        classes |= set(m.group(1).split())
    # no CSS, "hover:x" vira ".hover\:x" — a barra montada por chr(92), sem escape no fonte
    return sorted(c for c in classes if "." + c.replace(":", chr(92) + ":") not in css)


def test_a_linha_de_guias_so_usa_classe_que_existe_no_css():
    """🪤 27/09: o 1º rascunho usou `gap-x-5`, que o tailwind.min.css enxuto do
    site não tem — os links saíram colados ("BIMQuantitativo"), sem erro nenhum."""
    css = _ler("tailwind.min.css")
    for pag in ("index.html", "faq.html", "precos.html"):
        bloco = re.search(r'<nav aria-label="Guias".*?</nav>', _ler(pag), re.S).group(0)
        faltam = _classes_sem_css(bloco, css)
        assert not faltam, "%s: classe(s) sem CSS na linha de Guias: %s" % (pag, faltam)


# ── CONTROLES ────────────────────────────────────────────────────────────────

def test_CONTROLE_classe_inexistente_e_pega():
    assert _classes_sem_css('<nav class="gap-x-5 gap-x-6">', _ler("tailwind.min.css")) == ["gap-x-5"]



def test_CONTROLE_link_pra_post_do_futuro_e_pego():
    posts = {"a": {"publish_date": "2026-09-01", "sections": [{"body": '<a href="/blog/posts/b.html">b</a>'}]},
             "b": {"publish_date": "2026-10-01", "sections": [{"body": ""}]}}
    assert _links_para_o_futuro(posts) == ["a (2026-09-01) → b (2026-10-01)"]


def test_CONTROLE_post_no_meio_da_home_e_pego():
    src = '<main><a href="/blog/posts/x.html">x</a></main><footer></footer>'
    assert _post_acima_do_rodape(src) == ["x"]
