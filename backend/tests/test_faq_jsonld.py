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

Este teste não compara palavra por palavra (o JSON-LD é um resumo em texto
puro): ele exige que cada resposta do JSON-LD tenha corpo e que os TERMOS
centrais da resposta visível apareçam nela.
"""
import io
import json
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FAQ = os.path.join(_RAIZ, "faq.html")


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
