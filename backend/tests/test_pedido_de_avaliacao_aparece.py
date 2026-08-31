# -*- coding: utf-8 -*-
"""O pedido de avaliacao esta na vista em que a pagina ABRE (31/08/2026).

O BURACO, achado medindo por que so existem 5 avaliacoes em toda a historia do
produto (3 de fora de casa, com 67 clientes que ja concluiram projeto):

    #feedback-card ("Essa planilha te ajudou?") morava DENTRO de
    <div class="vista" data-vista="quantitativo" hidden>

e projeto.html abre na vista "visao". `maybeShowFeedback()` tirava o `hidden`
do proprio cartao — e o ancestral continuava fechado. O pedido de avaliacao de
MAIOR alcance do produto (dispara pra todo projeto com itens) estava apagado a
menos que a pessoa clicasse em "Quantitativo" no menu lateral.

Este guarda le a ARVORE do HTML, nao o texto. A primeira versao da minha
propria checagem procurou a string `data-vista="quantitativo"` e casou com o
COMENTARIO que eu tinha acabado de escrever explicando o conserto — deu
"errado" com o codigo certo. Ver feedback_guarda_que_le_fonte: guarda que
casa string ve o que esta escrito, nao o que o navegador monta.
"""
import io
import os
from html.parser import HTMLParser

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGINA = os.path.join(RAIZ, "projeto.html")


class _Arvore(HTMLParser):
    """Guarda, pra cada id que interessa, a pilha de ancestrais no momento em
    que a tag abriu. So conta tags de verdade — comentario nao passa por aqui."""

    VAZIAS = {"br", "hr", "img", "input", "meta", "link", "source", "path",
              "circle", "rect", "line", "polygon", "polyline", "ellipse", "use",
              "col", "area", "base", "embed", "track", "wbr", "stop"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pilha = []
        self.ancestrais = {}

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag not in self.VAZIAS:
            self.pilha.append((tag, d))
        if d.get("id"):
            self.ancestrais[d["id"]] = list(self.pilha)

    def handle_startendtag(self, tag, attrs):
        d = dict(attrs)
        if d.get("id"):
            self.ancestrais[d["id"]] = list(self.pilha) + [(tag, d)]

    def handle_endtag(self, tag):
        for i in range(len(self.pilha) - 1, -1, -1):
            if self.pilha[i][0] == tag:
                del self.pilha[i:]
                break


def _arvore():
    p = _Arvore()
    p.feed(io.open(PAGINA, encoding="utf-8").read())
    return p


def _vista_de(anc):
    """Qual vista (data-vista) envolve o elemento, e se ela nasce hidden."""
    for tag, at in anc:
        if at.get("data-vista"):
            return at["data-vista"], ("hidden" in at)
    return None, False


def test_o_cartao_de_avaliacao_existe():
    a = _arvore().ancestrais
    assert "feedback-card" in a, "sumiu o #feedback-card de projeto.html"


def test_o_cartao_NAO_esta_numa_vista_que_nasce_fechada():
    """O bug em uma linha: o cartao estava numa vista `hidden`."""
    anc = _arvore().ancestrais["feedback-card"]
    vista, escondida = _vista_de(anc)
    assert not escondida, (
        "o pedido de avaliacao voltou pra dentro da vista '%s', que nasce "
        "hidden — ninguem ve, e foi assim que ficamos com 5 avaliacoes em "
        "toda a historia do produto" % vista)


def test_o_cartao_esta_na_vista_QUE_A_PAGINA_ABRE():
    anc = _arvore().ancestrais["feedback-card"]
    vista, _ = _vista_de(anc)
    assert vista == "visao", (
        "o cartao esta na vista '%s'; a pagina abre na 'visao'" % vista)


def test_CONTROLE_o_guarda_SABE_reprovar():
    """Controle positivo: o mesmo HTML com o cartao dentro de uma vista hidden
    tem que ser reprovado. Sem isto, os testes acima podem estar so passando
    porque o parser nao acha nada."""
    html = ('<div class="vista" data-vista="quantitativo" hidden>'
            '<div id="feedback-card"></div></div>')
    p = _Arvore()
    p.feed(html)
    vista, escondida = _vista_de(p.ancestrais["feedback-card"])
    assert vista == "quantitativo" and escondida is True, (vista, escondida)


def test_CONTROLE_comentario_nao_engana_o_guarda():
    """A minha 1a checagem casou com a string `data-vista="quantitativo"` que
    estava dentro do COMENTARIO explicando o conserto, e acusou erro num codigo
    certo. O parser tem que ignorar comentario."""
    html = ('<div class="vista" data-vista="visao">'
            '<!-- antes ele ficava em <div class="vista" data-vista="quantitativo" hidden> -->'
            '<div id="feedback-card"></div></div>')
    p = _Arvore()
    p.feed(html)
    vista, escondida = _vista_de(p.ancestrais["feedback-card"])
    assert vista == "visao" and escondida is False, (vista, escondida)


def test_a_vista_visao_realmente_abre_sem_hidden():
    """Premissa do teste acima: 'visao' e a unica vista que nao nasce hidden."""
    txt = io.open(PAGINA, encoding="utf-8").read()
    p = _Arvore()
    p.feed(txt)
    # revarre as tags coletando todas as vistas
    class _V(HTMLParser):
        def __init__(self):
            super().__init__()
            self.vistas = []

        def handle_starttag(self, tag, attrs):
            d = dict(attrs)
            if d.get("data-vista"):
                self.vistas.append((d["data-vista"], "hidden" in d))
    v = _V()
    v.feed(txt)
    abertas = [n for n, h in v.vistas if not h]
    assert abertas == ["visao"], (
        "mudou a vista que abre por padrao: %s. O cartao de avaliacao precisa "
        "acompanhar." % abertas)
