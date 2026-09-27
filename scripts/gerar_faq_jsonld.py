# -*- coding: utf-8 -*-
"""Gera o JSON-LD (FAQPage) do faq.html a partir do texto VISÍVEL da página.

O texto que a pessoa lê é a fonte única. O bloco
<script type="application/ld+json"> é derivado dele: é o que Google, Bing e
os leitores de IA consomem, e em 26/09/2026 ele dizia outra coisa em 15 das
53 respostas (9 com mais de 20% das palavras faltando). Pior: numa delas era
a página que tinha ficado para trás — a rodada de coerência corrigiu o preço
só no JSON-LD. Editar em dois lugares não se sustenta.

Uso:
    python scripts/gerar_faq_jsonld.py            # reescreve o bloco no faq.html
    python scripts/gerar_faq_jsonld.py --conferir # sai 1 se o bloco commitado divergir

A guarda backend/tests/test_faq_jsonld.py chama `divergencias()` daqui: mudou
uma resposta no HTML e esqueceu de rodar o gerador, o CI fica vermelho.

Regras da conversão (as mesmas que 38 das 53 respostas já seguiam à mão):
- pergunta = texto do botão .faq-toggle; resposta = texto de .faq-answer;
- tag de bloco (p, li, div, ul...) vira espaço; <br> vira espaço;
- svg, script e style não entram; link entra só com o texto;
- entidades decodificadas e espaços colapsados.
"""
import io
import json
import os
import re
import sys
from html.parser import HTMLParser

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAQ = os.path.join(RAIZ, "faq.html")

_BLOCO = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S)


class _Itens(HTMLParser):
    _VAZIAS = {"br", "img", "hr", "input", "meta", "link", "source", "wbr",
               "path", "circle", "rect", "line", "polyline", "polygon"}
    _QUEBRA_ABRE = {"p", "li", "div", "tr", "h3", "h4", "ul", "ol", "table"}
    _QUEBRA_FECHA = {"p", "li", "div", "td", "th"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pilha = []
        self.itens = []

    def _papel(self):
        papeis = [p for _, p in self.pilha if p]
        if "mudo" in papeis:
            return None
        for p in reversed(papeis):
            if p in ("q", "a"):
                return p
        return None

    def _add(self, texto):
        papel = self._papel()
        if papel and self.itens:
            self.itens[-1][papel] += texto

    def handle_starttag(self, tag, attrs):
        if tag in self._VAZIAS:
            if tag == "br":
                self._add(" ")
            return
        classes = (dict(attrs).get("class") or "").split()
        papel = None
        if "faq-item" in classes:
            self.itens.append({"q": "", "a": ""})
            papel = "item"
        elif "faq-toggle" in classes:
            papel = "q"
        elif "faq-answer" in classes:
            papel = "a"
        elif tag in ("svg", "script", "style"):
            papel = "mudo"
        self.pilha.append((tag, papel))
        if tag in self._QUEBRA_ABRE:
            self._add(" ")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self._add(" ")

    def handle_endtag(self, tag):
        if tag in self._VAZIAS:
            return
        while self.pilha:
            aberta, _ = self.pilha.pop()
            if aberta == tag:
                break
        if tag in self._QUEBRA_FECHA:
            self._add(" ")

    def handle_data(self, dado):
        self._add(dado)


def _limpa(texto):
    # as entidades já chegam decodificadas (convert_charrefs=True); decodificar
    # de novo transformaria um "&amp;mdash;" escrito de propósito em "—"
    return re.sub(r"\s+", " ", texto).strip()


def perguntas_visiveis(src):
    """[(pergunta, resposta)] na ordem da página, como a pessoa lê."""
    p = _Itens()
    p.feed(src)
    p.close()
    return [(_limpa(i["q"]), _limpa(i["a"])) for i in p.itens]


def jsonld_esperado(src):
    """O FAQPage que corresponde ao texto visível de `src`."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in perguntas_visiveis(src)
        ],
    }


def jsonld_commitado(src):
    m = _BLOCO.search(src)
    if not m:
        raise ValueError("faq.html sem bloco application/ld+json")
    return json.loads(m.group(2))


def divergencias(src):
    """Lista legível do que o JSON-LD commitado diz diferente da página.
    Vazia = os dois dizem a mesma coisa."""
    esperado = jsonld_esperado(src)
    atual = jsonld_commitado(src)
    fora = []
    if {k: v for k, v in atual.items() if k != "mainEntity"} != \
            {k: v for k, v in esperado.items() if k != "mainEntity"}:
        fora.append("cabeçalho do FAQPage (@context/@type) diferente")
    exp = [(q["name"], q["acceptedAnswer"]["text"]) for q in esperado["mainEntity"]]
    atu = [((q or {}).get("name"), ((q or {}).get("acceptedAnswer") or {}).get("text"))
           for q in atual.get("mainEntity") or []]
    nomes_exp = [q for q, _ in exp]
    nomes_atu = [q for q, _ in atu]
    for q in nomes_exp:
        if q not in nomes_atu:
            fora.append("pergunta na página e fora do JSON-LD: %r" % q)
    for q in nomes_atu:
        if q not in nomes_exp:
            fora.append("pergunta no JSON-LD e fora da página: %r" % q)
    d_atu = dict(atu)
    for q, texto in exp:
        if q in d_atu and d_atu[q] != texto:
            fora.append("resposta diferente em %r" % q)
    if not fora and nomes_exp != nomes_atu:
        fora.append("mesmas perguntas, ordem diferente da página")
    return fora


def gerar(src):
    """`src` com o bloco JSON-LD reescrito a partir do texto visível."""
    nl = "\r\n" if "\r\n" in src else "\n"
    corpo = json.dumps(jsonld_esperado(src), ensure_ascii=False, indent=2)
    corpo = nl + corpo.replace("\n", nl) + nl
    return _BLOCO.sub(lambda m: m.group(1) + corpo + m.group(3), src, count=1)


def main(argv):
    src = io.open(FAQ, encoding="utf-8", newline="").read()
    if "--conferir" in argv:
        fora = divergencias(src)
        for linha in fora:
            print(linha)
        print("faq.html: %s" % ("JSON-LD bate com a página" if not fora
                                else "%d divergência(s)" % len(fora)))
        return 1 if fora else 0
    novo = gerar(src)
    if novo == src:
        print("faq.html: JSON-LD já batia com a página")
        return 0
    tmp = FAQ + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(novo)
    os.replace(tmp, FAQ)
    print("faq.html: JSON-LD regerado (%d perguntas)"
          % len(jsonld_esperado(novo)["mainEntity"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
