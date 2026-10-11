# -*- coding: utf-8 -*-
"""Frases públicas que contradiziam o próprio site, e a ponte do memorial colada no download.

🔎 11/10/2026 — estudo de SEO, itens 5 e 7 (Pedro: "segue com o 5 e o 7"; textos aprovados por ele).
  · O botão do fim de todo post dizia que o quantitativo era de verdade, e a página de destino se declara
    "EXEMPLO — projeto fictício".
  · O post SINAPI × TCPO prometia na introdução que o AI.arq "integra as três" bases, e o corpo diz que não
    entrega TCPO nem SICRO.
  · A home tinha o subtítulo "Pague por projeto, sem mensalidade" com tudo grátis no beta.
  · O llms.txt tratava o produto no feminino; o resto do site, no masculino.
  · Memorial: desde 26/09, 43 pessoas viram o post, 34 baixaram o modelo e 0 clicaram na ponte pro produto
    (eventos de quem aceitou cookie). A ponte ficava num parágrafo longe do botão; agora está na nota do download.
"""
import io
import json
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ler(*partes):
    return io.open(os.path.join(_RAIZ, *partes), encoding="utf-8").read()


def _posts():
    return {p["slug"]: p for p in json.loads(_ler("blog", "posts.json"))["posts"]}


_LINK_EXEMPLO = re.compile(r'<a href="/exemplo\.html"[^>]*>([^<]*)', re.S)


def _links_pro_exemplo_que_dizem_real(texto):
    return [t.strip() for t in _LINK_EXEMPLO.findall(texto) if "quantitativo real" in t.lower()]


def test_nenhum_link_pro_exemplo_diz_que_ele_e_real():
    """A página de destino diz "projeto fictício". (A expressão solta tem uso legítimo — "o quantitativo real
    da sua obra" —, por isso o que se cobra é o TEXTO DO LINK.)"""
    assert "projeto fictício" in _ler("exemplo.html").lower() or "projeto fict&iacute;cio" in _ler("exemplo.html").lower()
    pasta = os.path.join(_RAIZ, "blog", "posts")
    for nome in sorted(os.listdir(pasta)):
        if nome.endswith(".html"):
            assert _links_pro_exemplo_que_dizem_real(_ler("blog", "posts", nome)) == [], nome
    assert _links_pro_exemplo_que_dizem_real(_ler("blog", "generate.py")) == []


def test_CONTROLE_o_botao_antigo_reprova():
    antigo = '<a href="/exemplo.html" data-track="blog-cta-exemplo" class="x">\n        Ver um quantitativo real →\n      </a>'
    assert _links_pro_exemplo_que_dizem_real(antigo) == ["Ver um quantitativo real →"]


def test_o_post_das_bases_nao_promete_o_que_o_corpo_nega():
    p = _posts()["sinapi-vs-tcpo-qual-usar"]
    assert "integra as três" not in p["intro"]
    corpo = " ".join(s["body"] for s in p["sections"])
    assert "não entrega composição TCPO nem SICRO" in corpo, "o corpo mudou — releia a introdução junto"


def test_o_subtitulo_de_preco_da_home_diz_que_hoje_e_gratis():
    h2 = [re.sub(r"<[^>]+>", "", m).strip() for m in re.findall(r"<h2.*?</h2>", _ler("index.html"), re.S)]
    de_preco = [t for t in h2 if "mensalidade" in t]
    assert de_preco and all(t.startswith("Grátis no beta") for t in de_preco), de_preco


def test_o_llms_txt_trata_o_produto_como_o_resto_do_site():
    assert re.findall(r"\b[Aa] AI\.arq\b|\bda AI\.arq\b", _ler("llms.txt")) == []
    assert "O AI.arq lê a prancha" in _ler("llms.txt")


def test_post_agendado_nao_leva_norma_cancelada_nas_palavras_chave():
    kw = _posts()["memorial-a-partir-do-quantitativo-caminho-inverso"]["keywords"]
    assert "NBR 13531" not in kw and "NBR 13532" not in kw


# ─── a ponte do memorial ──────────────────────────────────────────────────────────────────────
def test_a_ponte_do_memorial_esta_colada_no_download():
    p = _posts()["memorial-descritivo-de-obra-modelo-pdf-docx"]
    nota = p["download_nota"]
    assert 'href="/exemplo.html" data-track="memorial-nota-exemplo"' in nota
    assert 'href="/login.html?novo=1" data-track="memorial-nota-cadastro"' in nota
    html = _ler("blog", "posts", "memorial-descritivo-de-obra-modelo-pdf-docx.html")
    # 🪤 âncora na CAIXA do download (o <div>), não no nome da classe: "aiarq-dl-btn" aparece antes, no CSS
    i_caixa = html.index('<div class="aiarq-downloads')
    i_ponte = html.index("memorial-nota-exemplo")
    assert 0 < i_ponte - i_caixa < 4000, "a ponte tem que vir colada aos botões de download"
    # e antes do parágrafo comprido de baixo
    assert i_ponte < html.index("memorial-ponte-exemplo")


def test_no_paragrafo_os_links_vem_antes_da_explicacao():
    corpo = _posts()["memorial-descritivo-de-obra-modelo-pdf-docx"]["sections"][0]["body"]
    i = corpo.index("**E o memorial do seu projeto?**")
    assert corpo.index("memorial-ponte-cadastro", i) < corpo.index("Primeiro sai a planilha", i)


def test_CONTROLE_a_nota_de_antes_nao_tinha_link():
    antiga = ("Do seu CAD, o AI.arq gera um rascunho de memorial organizado por disciplina, com a origem de cada "
              "quantidade — não este modelo de 10 seções, que é pra preencher à mão.")
    assert "data-track" not in antiga and "<a " not in antiga
