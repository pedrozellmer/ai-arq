# -*- coding: utf-8 -*-
"""O dado estruturado do FAQ tem que dizer a MESMA coisa que a página mostra.

🚨 23/08/2026 (auditoria): o commit que reescreveu "Como a IA calcula as
quantidades?" mexeu só no HTML visível. O JSON-LD ficou com uma frase única —
"Quando a legenda informa a quantidade, ela é usada diretamente." — que promete
só a leitura de legenda e some com toda a parte de honestidade (selo
medido/estimado, o que NÃO fazemos).

Dois estragos: quem chega pelo rich result do Google lê a versão pobre, e o
Google exige que o dado estruturado bata com o conteúdo visível — divergência
grande tira o FAQ rich result da página, que é o canal que mais trouxe gente.

🚨 26/09/2026: a comparação por termos centrais deixou passar 15 de 53
respostas diferentes (9 com mais de 20% das palavras faltando) — e numa delas
quem estava velha era a PÁGINA (o preço no presente, corrigido só no JSON-LD).
Desde então o JSON-LD é GERADO do texto visível por
scripts/gerar_faq_jsonld.py, e a guarda de baixo exige igualdade exata.
Mexeu numa resposta? Rode `python scripts/gerar_faq_jsonld.py`.
"""
import io
import json
import os
import re
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FAQ = os.path.join(_RAIZ, "faq.html")
sys.path.insert(0, os.path.join(_RAIZ, "scripts"))
import gerar_faq_jsonld as gerador  # noqa: E402


def _faq():
    return io.open(_FAQ, encoding="utf-8").read()


def _perguntas_do_jsonld(src):
    fora = {}
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', src, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception as e:
            raise AssertionError("JSON-LD do faq.html não é JSON válido: %s" % e)
        blocos = d if isinstance(d, list) else [d]
        for b in blocos:
            for q in (b or {}).get("mainEntity") or []:
                nome = (q or {}).get("name") or ""
                txt = (((q or {}).get("acceptedAnswer") or {}).get("text")) or ""
                if nome:
                    fora[nome] = txt
    return fora


def test_todo_jsonld_do_faq_e_json_valido():
    assert _perguntas_do_jsonld(_faq()), "não achei nenhuma Question no FAQPage"


def test_nenhuma_resposta_do_jsonld_e_um_toco():
    """Resposta de uma frase é o sintoma de "mexeram no HTML e esqueceram aqui"."""
    curtas = {n: t for n, t in _perguntas_do_jsonld(_faq()).items() if len(t) < 150}
    assert not curtas, (
        "respostas do JSON-LD curtas demais pra bater com a página visível "
        "(mexeu no HTML, sincronize aqui): " + "; ".join(
            "%s -> %r" % (n, t[:80]) for n, t in curtas.items()))


def test_a_resposta_de_como_calcula_carrega_a_honestidade():
    """O ponto todo dessa resposta é o selo. Sem ele, a promessa fica maior que
    o produto — que é exatamente o que a auditoria achou."""
    d = _perguntas_do_jsonld(_faq())
    alvo = [t for n, t in d.items() if "como a ia calcula" in n.lower()]
    assert alvo, "sumiu a pergunta 'Como a IA calcula as quantidades?' do JSON-LD"
    txt = alvo[0].lower()
    for termo in ("medido", "estimado", "geometria"):
        assert termo in txt, (
            "a resposta do JSON-LD não menciona %r — o selo medido/estimado é o "
            "que impede a página de prometer mais do que o motor entrega" % termo)


def test_nao_promete_medir_area_de_hachura_sem_ressalva():
    """🚨 O motor rebaixa DE PROPÓSITO a área que é soma de várias hachuras
    (main.py, rede de segurança sempre ligada). Medido em 555 itens: forro 0%,
    revestimento 1%, piso 2% de área medida. Prometer 'medimos área de hachura'
    sem a ressalva é o caso cliente-20 (NPS 2) esperando pra acontecer."""
    src = _faq()
    if "hachura" not in src.lower():
        return
    # em toda a página, "hachura" tem que vir acompanhado da condição
    assert re.search(r"uma hachura s[oó]", src, re.I), (
        "faq.html fala de hachura sem dizer que só a camada com UMA hachura "
        "vira medido — camada com várias sai como estimado")


# ── Fonte única: o JSON-LD é o texto visível, gerado ──────────────────────────

def _corpo(src):
    """Só o HTML depois do bloco JSON-LD — onde mora o texto que a pessoa lê."""
    fim = src.index("</script>", src.index('<script type="application/ld+json">'))
    return fim + len("</script>")


def _muda_so_na_pagina(src, velho, novo):
    corte = _corpo(src)
    assert src[corte:].count(velho) == 1, "âncora do controle sumiu: %r" % velho
    return src[:corte] + src[corte:].replace(velho, novo)


def test_o_jsonld_e_exatamente_o_texto_visivel():
    fora = gerador.divergencias(_faq())
    assert not fora, (
        "o JSON-LD do faq.html não diz o mesmo que a página — rode "
        "`python scripts/gerar_faq_jsonld.py` e commite:\n  " + "\n  ".join(fora))


def test_CONTROLE_resposta_mudada_so_na_pagina_reprova():
    src = _muda_so_na_pagina(_faq(), "4 cores por tipo de item", "3 cores por tipo de item")
    fora = gerador.divergencias(src)
    assert any("O que a planilha gerada contém?" in f for f in fora), fora


def test_CONTROLE_resposta_mudada_so_no_jsonld_reprova():
    src = _faq()
    velho = '"text": "Não. O modelo previsto é por projeto processado'
    assert src.count(velho) == 1, "âncora do controle sumiu"
    fora = gerador.divergencias(src.replace(velho, '"text": "Sim. O modelo previsto é por projeto processado'))
    assert any("Tem mensalidade ou assinatura?" in f for f in fora), fora


def test_CONTROLE_pergunta_nova_so_na_pagina_reprova():
    src = _muda_so_na_pagina(
        _faq(), "Tem mensalidade ou assinatura?</span>",
        "Tem mensalidade, assinatura ou fidelidade?</span>")
    fora = gerador.divergencias(src)
    assert any("pergunta na página e fora do JSON-LD" in f for f in fora), fora
    assert any("pergunta no JSON-LD e fora da página" in f for f in fora), fora


def test_o_leitor_acha_todas_as_perguntas_da_pagina():
    """O gerador só é fonte única se não pular item: cada `faq-item` do HTML
    vira uma pergunta, com pergunta e resposta não vazias e sem repetição."""
    src = _faq()
    itens = gerador.perguntas_visiveis(src)
    no_html = len(re.findall(r'class="faq-item[\s"]', src))
    assert len(itens) == no_html, "%d faq-item no HTML, %d lidos" % (no_html, len(itens))
    assert len(itens) >= 50, "piso: o FAQ tinha 53 perguntas em 26/09; leu %d" % len(itens)
    assert all(q and a for q, a in itens), [q for q, a in itens if not (q and a)]
    nomes = [q for q, _ in itens]
    assert len(nomes) == len(set(nomes)), "pergunta repetida no FAQ"


def test_a_conversao_segue_o_que_a_pessoa_le():
    html_ = ('<div class="faq-item"><button class="faq-toggle"><span>P&eacute;?</span>'
             '<svg><path d="M1"/></svg></button><div class="faq-answer"><div>'
             '<p>A <strong>b</strong> &mdash; <a href="x">link</a></p>'
             '<ul><li><span>&bull;</span> c</li><li>d</li></ul><p>x<br>y</p>'
             '</div></div></div>')
    assert gerador.perguntas_visiveis(html_) == [("Pé?", "A b — link • c d x y")]


def test_a_pagina_nao_mostra_aspas_escapadas():
    """26/09: a resposta "O AI.arq erra?" mostrava \\"itens por m²\\" na tela —
    texto copiado do JSON sem desfazer o escape."""
    ruins = [q for q, a in gerador.perguntas_visiveis(_faq()) if '\\"' in a or "\\'" in a]
    assert not ruins, "aspas com barra invertida no texto visível: %s" % ruins


def test_CONTROLE_aspas_escapadas_reprovam():
    src = _muda_so_na_pagina(_faq(), '(do tipo "itens por m²")', '(do tipo \\"itens por m²\\")')
    ruins = [q for q, a in gerador.perguntas_visiveis(src) if '\\"' in a]
    assert ruins == ["O AI.arq erra? E quando erra, o que eu faço?"], ruins


def test_o_gerador_e_idempotente():
    src = _faq()
    assert gerador.gerar(src) == src, "rodar o gerador no faq.html commitado mudaria o arquivo"
