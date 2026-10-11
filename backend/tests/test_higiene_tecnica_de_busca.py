# -*- coding: utf-8 -*-
"""Higiene técnica de busca e a origem técnica da visita.

🔎 11/10/2026 — plano de SEO, "fazer em seguida" 7 e 6 (Pedro: "segue com o 7 e o 6").

  · A home tinha dois endereços: "/" e "/index.html". O logo das páginas de login, cadastro, convite, painel e
    admin, e dois links do menu de preços, apontavam pro segundo. (O guarda de 26/09 só olhava páginas do
    sitemap e o texto exato `href="index.html"` — `index.html#recursos` passava.)
  · A data em que o TEXTO de um post mudou só aparecia no rodapé das fontes; o topo mostrava a de publicação.
  · A página "Sobre" apontava pra organização por `@id` sem repetir o nó — cada página é lida sozinha.
  · As 54 perguntas do FAQ não tinham endereço: não dava pra linkar UMA resposta.
  · `gemini.google.com` casava com a regra do Google e a visita do Gemini entrava como busca no Google; Bing,
    Yahoo e DuckDuckGo caíam juntos em "busca".

Deixado de fora de propósito: "não gerar post futuro". Os posts agendados são gerados com `noindex` e é a
rotina diária que tira a marca na data; mudar isso mexe no calendário de publicação por um ganho que o próprio
plano classifica como baixo.
"""
import glob
import io
import json
import os
import re

from _jsbancada import funcao_js, motor

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_RE_LD = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)


def _ler(*partes):
    return io.open(os.path.join(_RAIZ, *partes), encoding="utf-8").read()


# ── a home tem um endereço só ────────────────────────────────────────────────────────────────
def _links_pro_index_html(texto):
    return re.findall(r'href="(?:\./|/)?index\.html[^"]*"', texto)


def test_nenhuma_pagina_linka_index_html():
    arquivos = sorted(os.path.basename(p) for p in glob.glob(os.path.join(_RAIZ, "*.html"))) + ["menu-lateral.js"]
    assert len(arquivos) >= 20, arquivos
    ruins = ["%s: %s" % (a, _links_pro_index_html(_ler(a))) for a in arquivos if _links_pro_index_html(_ler(a))]
    assert not ruins, "link pra index.html (o endereço da home é /): " + " | ".join(ruins)


def test_CONTROLE_os_links_antigos_reprovam():
    assert _links_pro_index_html('<a href="index.html#recursos">Recursos</a>') == ['href="index.html#recursos"']
    assert _links_pro_index_html('<a class="aiarq-marca" href="index.html" title="x">') == ['href="index.html"']
    assert _links_pro_index_html('<a href="/#recursos">Recursos</a> <a href="/">AI.arq</a>') == []


# ── a data de atualização no topo do post ────────────────────────────────────────────────────
def _topo(html):
    i = html.index("<!-- Meta -->")
    return html[i:html.index("</div>", i)]


def _posts_publicados():
    sitemap = _ler("sitemap.xml")
    return [p for p in json.loads(_ler("blog", "posts.json"))["posts"]
            if "/blog/posts/%s.html" % p["slug"] in sitemap]


def test_post_atualizado_mostra_a_data_no_topo():
    mexidos = [p for p in _posts_publicados() if p.get("update_date") and p["update_date"] != p["publish_date"]]
    assert len(mexidos) >= 5, "esperava vários posts com update_date; achei %d" % len(mexidos)
    for p in mexidos:
        a, m, d = p["update_date"].split("-")
        topo = _topo(_ler("blog", "posts", p["slug"] + ".html"))
        assert "<span>Atualizado em %s/%s/%s</span>" % (d, m, a) in topo, p["slug"]


def test_CONTROLE_post_intocado_nao_ganha_data_de_atualizacao():
    intocados = [p for p in _posts_publicados() if not p.get("update_date") and not p.get("updated")]
    assert intocados, "esperava ao menos um post sem update_date pra servir de controle"
    for p in intocados:
        assert "Atualizado em" not in _topo(_ler("blog", "posts", p["slug"] + ".html")), p["slug"]


# ── a organização completa também na página "Sobre" ──────────────────────────────────────────
def test_a_pagina_sobre_repete_a_organizacao_da_home():
    home = json.loads(_RE_LD.findall(_ler("index.html"))[0])["publisher"]
    sobre = [json.loads(b) for b in _RE_LD.findall(_ler("sobre.html"))]
    pagina = [b for b in sobre if b.get("@type") == "AboutPage"]
    assert len(pagina) == 1, [b.get("@type") for b in sobre]
    assert pagina[0]["mainEntity"] == home, "o nó da organização no /sobre divergiu do da home"
    assert home.get("logo") and home.get("sameAs") and home.get("email"), home


# ── cada pergunta do FAQ tem endereço ────────────────────────────────────────────────────────
_RE_ITEM = re.compile(r'<div([^>]*)class="faq-item [^>]*>\s*<button data-track="faq-([a-z0-9-]+)"')


def _itens_do_faq(texto):
    """(id do item, slug do botão) de cada pergunta."""
    fora = []
    for m in _RE_ITEM.finditer(texto):
        i = re.search(r'\bid="([^"]*)"', m.group(1))
        fora.append((i.group(1) if i else None, m.group(2)))
    return fora


def test_toda_pergunta_do_faq_tem_id_proprio():
    faq = _ler("faq.html")
    itens = _itens_do_faq(faq)
    assert len(itens) == faq.count('class="faq-item ') and len(itens) >= 54, len(itens)
    assert all(i == slug for i, slug in itens), [x for x in itens if x[0] != x[1]][:3]
    ids = re.findall(r'\bid="([^"]+)"', faq)
    repetidos = sorted(set(i for i in ids if ids.count(i) > 1))
    assert not repetidos, "id repetido no FAQ: %s" % repetidos


def test_CONTROLE_pergunta_sem_id_e_pega():
    antigo = ('<div class="faq-item rounded-xl" data-keywords="x">\n'
              '  <button data-track="faq-o-que-e-o-ai-arq" class="faq-toggle">')
    assert _itens_do_faq(antigo) == [(None, "o-que-e-o-ai-arq")]


def _pergunta_do_endereco(hash_):
    """Roda a função do FAQ com uma página de mentira: uma pergunta e um elemento que não é pergunta."""
    js = motor(
        "var document = { getElementById: function (id) {"
        "  if (id === 'qual-formato') return { id: id, classList: { contains: function (c) { return c === 'faq-item'; } } };"
        "  if (id === 'faq-search') return { id: id, classList: { contains: function () { return false; } } };"
        "  return null; } };")
    js.evaljs(funcao_js("perguntaDoEndereco", "faq.html"))
    return js.evaljs("var __i = perguntaDoEndereco(%s); __i ? __i.id : null" % json.dumps(hash_))


def test_o_endereco_com_a_pergunta_acha_a_pergunta():
    assert _pergunta_do_endereco("#qual-formato") == "qual-formato"


def test_endereco_que_nao_e_pergunta_nao_abre_nada():
    assert _pergunta_do_endereco("") is None
    assert _pergunta_do_endereco("#nao-existe") is None
    assert _pergunta_do_endereco("#faq-search") is None, "campo de busca não é pergunta"
    assert _pergunta_do_endereco("#%E0%A4%A") is None, "endereço mal formado não pode quebrar a página"


def test_o_faq_abre_a_pergunta_do_endereco_e_escreve_o_endereco_ao_abrir():
    faq = _ler("faq.html")
    assert "abrirPerguntaDoEndereco();" in faq and "addEventListener('hashchange', abrirPerguntaDoEndereco)" in faq
    assert "history.replaceState(null, '', '#' + item.id)" in funcao_js("toggleFaq", "faq.html")


# ── a origem técnica: IA, Google e cada buscador ─────────────────────────────────────────────
def _classifica(host, fonte=None):
    js = motor()
    js.evaljs(fonte or funcao_js("_classifyRef", "aiarq-utils.js"))
    return js.evaljs("_classifyRef(%s)" % json.dumps(host))


_ORIGENS = [
    ("gemini.google.com", "gemini"), ("chatgpt.com", "chatgpt"), ("chat.openai.com", "chatgpt"),
    ("copilot.microsoft.com", "copilot"), ("www.perplexity.ai", "perplexity"), ("claude.ai", "claude"),
    ("www.google.com", "google"), ("www.google.com.br", "google"),
    ("www.bing.com", "bing"), ("duckduckgo.com", "duckduckgo"), ("br.search.yahoo.com", "yahoo"),
    ("l.instagram.com", "instagram"), ("ai.arq.br", "direto"), ("www.exemplo.com", "exemplo.com"),
]


def test_cada_origem_ganha_o_seu_rotulo():
    for host, esperado in _ORIGENS:
        assert _classifica(host) == esperado, host
    assert _classifica("") == ""


_REGRA_ANTIGA = r"""function _classifyRef(host) {
    if (!host) return '';
    host = host.toLowerCase();
    if (/google\./.test(host)) return 'google';
    if (/bing\.|duckduckgo|search\.yahoo/.test(host)) return 'busca';
    return host.replace(/^www\./, '');
  }"""


def test_CONTROLE_a_regra_antiga_confundia_o_gemini_com_o_google():
    assert _classifica("gemini.google.com", _REGRA_ANTIGA) == "google"
    assert _classifica("www.bing.com", _REGRA_ANTIGA) == "busca"


def _grupo(src):
    js = motor()
    js.evaljs(funcao_js("_grupoChegou", "admin.html"))
    return js.evaljs("_grupoChegou(%s)" % json.dumps(src))


def test_o_painel_agrupa_os_rotulos_novos_sem_quebrar_a_serie():
    assert [_grupo(s) for s in ("bing", "yahoo", "duckduckgo", "busca")] == ["outra busca"] * 4
    assert [_grupo(s) for s in ("gemini", "chatgpt", "copilot", "perplexity", "claude", "chatgpt.com")] == \
        ["IA (marca no link)"] * 6
    assert _grupo("google") == "Google" and _grupo("exemplo.com") == "outro site"
