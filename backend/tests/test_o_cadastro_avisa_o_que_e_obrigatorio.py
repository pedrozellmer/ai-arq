# -*- coding: utf-8 -*-
"""Campo obrigatório do cadastro avisa que é obrigatório.

🩸 17/09/2026. Dois campos do formulário eram `required` e a tela não dizia:
"Área de atuação" e "Como nos conheceu?". O cliente preenchia, clicava em
"Criar conta", e o navegador barrava sem ele entender o que faltava.

📏 Medido em `usage_events` antes de mexer (evento `signup_bloqueado`, que
existe desde 06/09):

    motivo=area      14 bloqueios, 10 pessoas
    motivo=origem    10 bloqueios,  8 pessoas
    motivo=whatsapp   3 bloqueios,  2 pessoas   <- este JÁ tinha o asterisco

**12 de 51 pessoas** que começaram o formulário esbarraram (23,5%). Um cliente
clicou em "Criar conta" 5 vezes em 17 segundos até descobrir sozinho.
🍀 Ninguém desistiu — os 12 completaram. Era atrito, não vazamento.

🔑 O FATO que este guarda prende não é "tem asterisco". É a coerência:
**todo campo `required` carrega marca visível**. Marcar dois e esquecer o
terceiro recria o defeito com outra cara — e foi exatamente assim que ele
nasceu (o formulário já sabia marcar o WhatsApp e escrever "(opcional)" no
CPF e no Cargo; só estes ficaram de fora).

🪤 O parser é o `html.parser` do Python, não regex: a tag do `<select>` tem um
SVG embutido no `style`, com `>` dentro. Meu primeiro guarda usou regex, parou
no `>` errado e disse que NENHUM campo era obrigatório — teria passado verde
com o defeito no ar.
"""
import io
import os
import re
from html.parser import HTMLParser

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: campos que são `required` mas cujo rótulo é o próprio texto de consentimento
#: (caixas de "li e aceito"), onde asterisco não faz sentido.
_ACEITES = {"aceita_termos", "aceita_idade"}


class _Form(HTMLParser):
    """Campos com `required` e o texto de cada <label for=...>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.obrigatorios = {}      # id -> tag
        self.rotulos = {}           # for -> texto
        self._label_atual = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("input", "select", "textarea"):
            if "required" in a and a.get("id"):
                self.obrigatorios[a["id"]] = tag
        elif tag == "label" and a.get("for"):
            self._label_atual = a["for"]
            self._buf = []

    def handle_data(self, data):
        if self._label_atual:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "label" and self._label_atual:
            self.rotulos[self._label_atual] = "".join(self._buf).strip()
            self._label_atual = None


def _ler(arquivo="cadastro.html"):
    p = _Form()
    p.feed(io.open(os.path.join(_RAIZ, arquivo), encoding="utf-8").read())
    return p


def _tem_marca(texto):
    """A marca pode ser o asterisco OU a palavra — o que importa é avisar."""
    t = (texto or "").lower()
    return ("*" in texto) or ("obrigat" in t)


def test_todo_campo_obrigatorio_AVISA_que_e_obrigatorio():
    f = _ler()
    assert f.obrigatorios, "o parser não achou campo `required` nenhum — ele quebrou"
    mudos = []
    for cid in f.obrigatorios:
        if cid in _ACEITES:
            continue
        rot = f.rotulos.get(cid)
        if rot is None:
            mudos.append("%s (sem <label for=>)" % cid)
        elif not _tem_marca(rot):
            mudos.append("%s -> %r" % (cid, rot[:40]))
    assert not mudos, (
        "campo obrigatório sem marca na tela — o cliente clica em Criar conta "
        "e é barrado sem saber o quê: %s" % mudos)


def test_CONTROLE_o_guarda_REPROVA_um_campo_mudo():
    """Prova que o guarda reprova de verdade, com o HTML do defeito real."""
    p = _Form()
    p.feed('<label for="area">Área de atuação</label>'
           '<select id="area" name="area" required><option>x</option></select>')
    assert p.obrigatorios == {"area": "select"}, p.obrigatorios
    assert not _tem_marca(p.rotulos.get("area", "")), (
        "o guarda aceitaria o rótulo mudo que causou 14 bloqueios")


def test_CONTROLE_o_guarda_ACEITA_o_campo_marcado():
    p = _Form()
    p.feed('<label for="area">Área de atuação <span class="text-red-500">*</span></label>'
           '<select id="area" name="area" required><option>x</option></select>')
    assert _tem_marca(p.rotulos.get("area", "")), p.rotulos


def test_o_parser_atravessa_o_SVG_embutido_no_style():
    """🪤 O guarda anterior era regex e morria aqui: a tag do `<select>` carrega
    um SVG no `style`, e o `>` do SVG fechava a tag cedo. Resultado: o regex
    dizia que NENHUM campo era obrigatório, e o guarda passava verde com o
    defeito no ar."""
    f = _ler()
    # o campo que tem o SVG no style é `required` e TEM que ser visto
    assert "area" in f.obrigatorios, (
        "o parser perdeu o campo que tem SVG embutido — é o mesmo buraco do "
        "guarda de regex: %r" % sorted(f.obrigatorios))
    src = io.open(os.path.join(_RAIZ, "cadastro.html"), encoding="utf-8").read()
    assert "svg+xml" in src, "o caso que o parser precisa atravessar sumiu do arquivo"


def test_o_que_NAO_e_obrigatorio_nao_ganha_marca_a_toa():
    """Contrapeso: marcar tudo é o mesmo que não marcar nada. O que é opcional
    tem que continuar dizendo que é opcional."""
    f = _ler()
    for cid in ("cpf_cnpj", "cargo"):
        assert cid not in f.obrigatorios, "%s virou obrigatório sem decisão" % cid
        rot = f.rotulos.get(cid, "")
        assert "opcional" in rot.lower(), (
            "%s é opcional e a tela parou de dizer isso: %r" % (cid, rot[:60]))
        assert "*" not in rot, "%s ganhou asterisco sendo opcional: %r" % (cid, rot[:60])
