# -*- coding: utf-8 -*-
"""A copy pública não chama o selo de "conferido", não fala "motor" e não promete o que a base não mostra.

🩸 27/09/2026 — O estudo de posicionamento listou frases que o produto não sustenta, espalhadas pela home,
FAQ, /dados, /sobre, preços, llms.txt e posts do blog:
  • "o que você pode usar SEM CONFERIR", "já vem conferida", "certificada", "usar sem reconferir" — o selo
    diz de onde veio o número, não que ele foi conferido (nunca foi comparado com gabarito);
  • "o motor mede / o motor lê" — palavra de dentro de casa;
  • "os melhores / mais avançados modelos de IA do mundo" — o estudo acadêmico mediu os modelos que TESTOU;
  • "suas correções afinam o motor / seus próximos quantitativos saem medindo melhor" — a base de
    comparação por tipo de obra tem 2 projetos, de um tipo só.
Pedro liberou a limpeza em todos esses lugares. O guarda cobra o texto de cada página pública e das fontes
que geram texto público (blog/posts.json → blog/posts/*.html; blog/gerar_llms.py → llms.txt).

27/09, mais tarde: Pedro liberou também a ÁREA LOGADA (painel, projeto, revisão, agradecimento e a ajuda de
erro do aiarq-utils.js) — "Avisos do motor", "Reprocessar com motor atualizado", "ajude a calibrar o motor",
"sua revisão afina o motor — os próximos projetos saem melhores". Ali o guarda lê o arquivo SEM comentário
de código (comentário não aparece pro cliente) e com os escapes \\uXXXX do JS já decodificados.
Fora, de propósito: o recado que só o admin vê ("Pra testar o motor…") e os e-mails do servidor.
"""
import glob
import html
import io
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAGINAS = ["index.html", "faq.html", "dados.html", "sobre.html", "precos.html", "exemplo.html", "llms.txt",
           "blog/index.html", "blog/posts.json", "blog/gerar_llms.py"]

PROIBIDAS = [
    (r"usar\s+sem\s+(re)?conferir", "selo não é conferência"),
    (r"vem\s+conferid", "selo não é conferência"),
    (r"certificad[ao]\s+como\s+medid|sai\s+certificad", "selo não é certificado"),
    (r"\bo\s+motor\s+(mede|l[êe])\b", "jargão da casa"),
    (r"afina[m]?\s+(o\s+motor|a\s+IA|a\s+calibra)", "promessa que a base não sustenta"),
    (r"saem\s+medindo\s+melhor", "promessa que a base não sustenta"),
    (r"(melhores|mais\s+avan[çc]ados)\s+(modelos\s+de\s+IA\s+)?do\s+mundo", "o estudo mediu os modelos testados"),
]


def _texto(caminho):
    t = io.open(caminho, encoding="utf-8").read()
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    return html.unescape(t)


def problemas(textos):
    """textos: {nome: texto}. Devolve a lista do que está proibido (vazia = certo)."""
    achados = []
    for nome, t in textos.items():
        for pad, porque in PROIBIDAS:
            for m in re.finditer(pad, t, re.I):
                achados.append("%s: %r (%s)" % (nome, t[max(0, m.start() - 30):m.end() + 20], porque))
    return achados


def _todas():
    nomes = PAGINAS + [os.path.relpath(p, RAIZ) for p in glob.glob(os.path.join(RAIZ, "blog", "posts", "*.html"))]
    return {n: _texto(os.path.join(RAIZ, n)) for n in nomes}


def test_a_copy_publica_nao_promete_mais_que_a_base():
    achados = problemas(_todas())
    assert not achados, "a copy pública voltou a prometer demais:\n  " + "\n  ".join(achados[:15])


def test_CONTROLE_o_guarda_REPROVA_as_frases_que_estavam_no_ar():
    """🧪 Uma frase de cada, como estava no ar até 27/09."""
    velhas = {
        "faq": "A diferença maior está no que você pode usar SEM CONFERIR: em CAD, 25,0%",
        "home": "Em CAD, 1 em cada 4 linhas já vem conferida",
        "post": "contagem sai certificada em 41,7% dos casos; “linha certificada como medida”",
        "dados": "PDF vetorial também é lido — o motor mede a geometria quando dá",
        "faq2": "O motor lê o CAD de qualquer lugar",
        "precos": "Planilha revisada e cotações de fornecedor afinam o motor — seus próximos quantitativos saem medindo melhor.",
        "faq3": "Mesmo os modelos de IA mais avançados do mundo, quando contam itens",
    }
    achados = problemas(velhas)
    for nome in velhas:
        assert any(a.startswith(nome + ":") for a in achados), (nome, achados)


def test_CONTROLE_o_guarda_nao_morde_uso_legitimo():
    """"sem conferir" é português comum — só a promessa de usar o número sem conferir é proibida."""
    ok = {"post-manual": "tratar estimativa como medição é como assinar um cheque sem conferir o saldo",
          "post-duto": "Supor a mais fina sem conferir erra o peso",
          "cert": "PDF assinado com certificado digital ICP-Brasil",
          "motor": "persiana motorizada"}
    assert problemas(ok) == []


AREA_LOGADA = ["dashboard.html", "projeto.html", "revisao.html", "obrigado.html", "aiarq-utils.js"]

PROIBIDAS_LOGADA = PROIBIDAS + [
    (r"afinar?\s+o\s+motor|calibrar\s+o\s+motor|ensina\s+o\s+motor|calibra[çc][ãa]o\s+do\s+motor",
     "promessa que a base não sustenta"),
    (r"sa[ie]m\s+(medindo\s+)?melhor|mais\s+afiados", "promessa que a base não sustenta"),
    (r"avisos\s+do\s+motor|motor\s+atualizado|vers[ãa]o(\s+mais\s+nova|\s+[úu]ltima)?\s+do\s+motor"
     r"|[úu]ltima\s+vers[ãa]o\s+do\s+motor|conserto\s+de\s+motor|o\s+motor\s+procura|corrigir\s+o\s+motor",
     "jargão da casa"),
]


def _sem_comentario_de_codigo(t):
    """O que o cliente pode ver: sem <!-- -->, sem /* */ e sem linha de // (url com // fica)."""
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"/\*.*?\*/", " ", t, flags=re.S)
    t = re.sub(r"(?m)^\s*//.*$", " ", t)
    t = re.sub(r"(?<![:\"'`])//[^\n\"'`]*$", " ", t, flags=re.M)
    t = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)
    return html.unescape(t)


def problemas_logada(textos):
    achados = []
    for nome, t in textos.items():
        for pad, porque in PROIBIDAS_LOGADA:
            for m in re.finditer(pad, t, re.I):
                achados.append("%s: %r (%s)" % (nome, t[max(0, m.start() - 30):m.end() + 20], porque))
    return achados


def test_a_area_logada_nao_promete_mais_que_a_base():
    textos = {n: _sem_comentario_de_codigo(io.open(os.path.join(RAIZ, n), encoding="utf-8").read())
              for n in AREA_LOGADA}
    achados = problemas_logada(textos)
    assert not achados, "a área logada voltou a prometer demais:\n  " + "\n  ".join(achados[:15])


def test_CONTROLE_o_guarda_da_area_logada_REPROVA_o_que_estava_no_ar_e_poupa_comentario():
    velhas = {
        "dash": "msg += '\\u2705 Sua revis\\u00e3o afina o motor \\u2014 os pr\\u00f3ximos projetos saem melhores';",
        "proj": '<h3 class="font-semibold">Avisos do motor</h3><p>Reprocessar com motor atualizado</p>',
        "proj2": "⭐ Ajude a calibrar o motor — e faz seus próximos projetos saírem mais afiados",
        "rev": "é recado pra gente conferir e corrigir o motor.",
        "obr": "'O que faltou nessa planilha? Isso vira conserto de motor'",
    }
    achados = problemas_logada({n: _sem_comentario_de_codigo(t) for n, t in velhas.items()})
    for nome in velhas:
        assert any(a.startswith(nome + ":") for a in achados), (nome, achados)
    comentario = "  // a planilha revisada é o que CALIBRA o motor — afina o motor\n<!-- Avisos do motor -->"
    assert problemas_logada({"c": _sem_comentario_de_codigo(comentario)}) == []
    assert "https://ai.arq.br" in _sem_comentario_de_codigo("x = 'https://ai.arq.br';")


def test_CONTROLE_o_guarda_le_as_paginas_de_verdade():
    textos = _todas()
    assert len([n for n in textos if n.startswith(os.path.join("blog", "posts"))]) >= 20, "não achei os posts"
    for n in ("index.html", "faq.html", "llms.txt"):
        assert len(textos[n]) > 2000, "%s veio vazio — o guarda não está lendo" % n
