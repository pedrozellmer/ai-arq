# -*- coding: utf-8 -*-
"""O blog sabe fazer tabela, resposta curta e ponte pro produto no meio do post.

🔎 11/10/2026 — plano de SEO, "fazer em seguida" 2 e 3 (Pedro: "segue com o 2 e o 3"; textos aprovados).
  · Nenhum dos 32 posts tinha <table>: o que promete "tabela" no título entregava parágrafo + lista.
  · Nenhum post respondia a própria pergunta antes da 2ª tela (mediana de ~920 palavras até citar o produto).
  · 22 dos 26 publicados não tinham link de produto no corpo, só o bloco do fim.

O que este arquivo cobra: que o gerador QUEBRE em vez de publicar tabela torta ou ponte com evento que o
/api/track joga fora; que os três blocos apareçam onde foram prometidos; e que a tabela não tenha trocado
número nenhum no caminho.
"""
import importlib.util
import io
import json
import os
import re

import pytest

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("generate_sob_teste", os.path.join(_RAIZ, "blog", "generate.py"))
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)


def _ler(*partes):
    return io.open(os.path.join(_RAIZ, *partes), encoding="utf-8").read()


def _posts():
    return {p["slug"]: p for p in json.loads(_ler("blog", "posts.json"))["posts"]}


def _html(slug):
    return _ler("blog", "posts", slug + ".html")


def _publicado(slug):
    return "/blog/posts/%s.html" % slug in _ler("sitemap.xml")


# ── tabela ───────────────────────────────────────────────────────────────────────────────────
def test_a_tabela_sai_com_cabecalho_e_linhas():
    html = G.tabela_html(["| Base | Custo |", "|---|---|", "| SINAPI | grátis |", "| TCPO | **pago** |"])
    assert html.count("<th ") == 2 and html.count("<tr>") == 3 and html.count("<td>") == 4
    assert '<th scope="col">Base</th>' in html and "<td>SINAPI</td><td>grátis</td>" in html
    assert "<td><strong>pago</strong></td>" in html, "célula tem que aceitar negrito como o resto do post"
    assert "---" not in html


def test_tabela_torta_quebra_a_geracao():
    with pytest.raises(ValueError):
        G.tabela_html(["| a | b | c |", "| 1 | 2 |"])
    with pytest.raises(ValueError):
        G.tabela_html(["| só cabeçalho |", "|---|"])


def test_a_secao_reconhece_a_tabela_e_nao_confunde_com_lista():
    com = G.render_section({"h2": "X", "body": "Antes.\n\n| a | b |\n| 1 | 2 |\n\nDepois."})
    assert "<p>Antes.</p>" in com and "<table>" in com and "<p>Depois.</p>" in com
    assert com.index("<p>Antes.</p>") < com.index("<table>") < com.index("<p>Depois.</p>")


def test_CONTROLE_lista_continua_lista_e_barra_no_meio_nao_vira_tabela():
    lista = G.render_section({"h2": "X", "body": "- um\n- dois"})
    assert "<ul><li>um</li><li>dois</li></ul>" in lista and "<table>" not in lista
    texto = G.render_section({"h2": "X", "body": "DWG | DXF | PDF são formatos.\nSegue o texto."})
    assert "<table>" not in texto


def _celulas(slug):
    return re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", _html(slug), re.S)


def test_a_tabela_do_bdi_traz_as_doze_faixas_do_acordao():
    celulas = _celulas("bdi-arquiteto-br-2026-tabela")
    for n in ("20,34%", "22,12%", "25,00%", "19,60%", "20,97%", "24,23%", "20,76%", "24,18%", "26,44%",
              "11,10%", "14,02%", "16,80%"):
        assert celulas.count(n) == 1, n
    linha = celulas[celulas.index("Edificações (construção e reforma de prédios)"):][:4]
    assert linha[1:] == ["20,34%", "22,12%", "25,00%"], linha


def test_a_tabela_do_post_de_formatos_repete_a_pagina_de_dados():
    """A fonte do número é /dados.html — a tabela do post não pode dizer outra coisa."""
    dados = _ler("dados.html")
    celulas = _celulas("dwg-ou-pdf-quantitativo-o-que-os-dados-mostram")
    for n in ("165", "12.910", "69,4%", "75", "8.966", "51,6%", "70", "7 (10,0%)", "28", "1 (3,6%)"):
        assert n in celulas, n
        assert ">%s<" % n in dados, "%s está na tabela do post e não na página de dados" % n


def test_os_quatro_posts_ganharam_tabela():
    for slug in ("bdi-arquiteto-br-2026-tabela", "sinapi-vs-tcpo-qual-usar",
                 "quantitativo-manual-automatico-ou-bim-comparativo",
                 "dwg-ou-pdf-quantitativo-o-que-os-dados-mostram"):
        assert '<div class="aiarq-tabela"><table>' in _html(slug), slug


# ── resposta curta ───────────────────────────────────────────────────────────────────────────
def test_a_resposta_curta_fica_entre_o_titulo_e_a_introducao():
    com = [p for p in _posts().values() if p.get("resposta_curta")]
    assert len(com) >= 4
    for p in com:
        html = _html(p["slug"])
        i = html.index('class="aiarq-resposta"')
        assert html.index("<h1") < i < html.index("<!-- Intro destacada -->"), p["slug"]
        assert G._inline_md(p["resposta_curta"]) in html, p["slug"]


def test_a_resposta_curta_de_formatos_usa_o_numero_da_pagina_de_dados():
    resposta = _posts()["dwg-ou-pdf-quantitativo-o-que-os-dados-mostram"]["resposta_curta"]
    numeros = re.findall(r"\d+,\d%", resposta)
    assert numeros, "a resposta curta deixou de citar a parcela medida"
    for n in numeros:
        assert ">%s<" % n in _ler("dados.html"), "%s não está na página de dados" % n


def test_CONTROLE_post_sem_o_campo_nao_ganha_caixa_vazia():
    sem = [p for p in _posts().values() if not p.get("resposta_curta") and not p.get("ponte") and _publicado(p["slug"])]
    assert sem, "esperava post publicado sem resposta curta nem ponte pra servir de controle"
    for p in sem:
        html = _html(p["slug"])
        assert 'class="aiarq-resposta"' not in html and 'class="aiarq-ponte"' not in html, p["slug"]
    assert G.resposta_curta_html({"slug": "x"}) == "" and G.ponte_html({"slug": "x"}) == ""


# ── ponte no meio do post ────────────────────────────────────────────────────────────────────
def test_a_ponte_entra_depois_da_segunda_secao():
    com = [p for p in _posts().values() if p.get("ponte")]
    assert len(com) >= 7
    for p in com:
        html = _html(p["slug"])
        corpo = html[html.index('<div class="prose-aiarq">'):]
        h2 = [m.start() for m in re.finditer(r"<h2>", corpo)]
        i = corpo.index('<aside class="aiarq-ponte">')
        assert h2[1] < i < h2[2], "%s: a ponte tem que ficar entre a 2ª e a 3ª seção" % p["slug"]
        trecho = corpo[i:corpo.index("</aside>", i)]
        assert 'href="/exemplo.html" data-track="%s"' % p["ponte"]["track"] in trecho, p["slug"]
        assert "Ver um quantitativo de exemplo" in trecho


def test_o_evento_de_cada_ponte_e_unico_e_o_backend_aceita():
    import main as _m
    tracks = [p["ponte"]["track"] for p in _posts().values() if p.get("ponte")]
    assert len(tracks) == len(set(tracks)), "duas pontes com o mesmo evento não dá pra medir por post"
    for t in tracks:
        assert _m._track_evento_aceito("clique:" + t), "o /api/track descarta %r em silêncio" % t


@pytest.mark.parametrize("track", ["", "Ponte-Duto", "ponte duto", "ponte_duto", "p" * 41, "-ponte"])
def test_ponte_com_evento_que_o_backend_descartaria_quebra_a_geracao(track):
    with pytest.raises(ValueError):
        G.ponte_html({"slug": "x", "ponte": {"frase": "Frase.", "track": track}})


def test_CONTROLE_a_regra_do_gerador_e_a_do_backend():
    """O gerador valida o nome sem importar o backend; os dois têm de concordar."""
    import main as _m
    for t in ("ponte-duto", "a", "p" * 40, "Ponte", "ponte_x", "p" * 41, "-x", ""):
        assert bool(G._RE_TRACK_DA_PONTE.match(t)) == _m._track_evento_aceito("clique:" + t), t


# ── o post secundário aponta pro principal ───────────────────────────────────────────────────
@pytest.mark.parametrize("de,para", [
    ("5-erros-quantitativo-atraso-de-obra", "7-erros-comuns-levantamento-quantitativos"),
    ("bdi-arquiteto-br-2026-tabela", "bdi-em-obra-o-que-e-como-calcular"),
    ("quantitativo-arquitetura-sinapi-planilha-modelo", "como-fazer-planilha-de-quantitativos-de-obra"),
])
def test_o_secundario_linka_o_principal_na_primeira_secao(de, para):
    assert _publicado(para), "link pra post que ainda não publicou vira link morto"
    primeira = _posts()[de]["sections"][0]["body"]
    assert 'href="/blog/posts/%s.html"' % para in primeira, "%s não aponta pra %s" % (de, para)
