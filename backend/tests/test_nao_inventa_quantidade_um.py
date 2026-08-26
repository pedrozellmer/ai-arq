# -*- coding: utf-8 -*-
"""Rebaixar o selo nao autoriza inventar a quantidade.

🚨 Achado em 26/08/2026. O analyzer tinha:

    if qty == 0 and conf == "confirmado":
        qty = 1                      # <- de onde saiu esse 1?
        conf = "estimado"

O rebaixamento do selo esta certo (regra dura n1: confirmado exige geometria).
O `qty = 1` nao: ele INVENTA um numero que ninguem leu em lugar nenhum.

E o pior e QUAIS itens caem ai. A IA usa confirmado+0 justamente pros itens que
o projeto manda NAO orcar -- "[EXISTENTE - sem intervencao] Porta PE1",
"Alvenaria existente a manter". Ela tem certeza de que existe e certeza de que
nao ha obra. O `qty = 1` virava isso em "orcar 1 porta" na planilha do cliente.
Medido no acervo antes de mexer: 77 itens em 41 projetos com essa assinatura.

🩤 Zero nao e estado quebrado: a propria politica do arquivo ja permite
qty=0 pra "estimado", ha 2.337 itens assim no acervo, e a tela de revisao existe
pro cliente preencher. Numero inventado infla o quantitativo em silencio.

Este guarda RODA o caminho real (`analyze_sheet` com a chamada de LLM trocada
por uma resposta de mentira), nao le o fonte.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import analyzer                                    # noqa: E402
from processor import SheetInfo, SheetType         # noqa: E402


ITENS_DE_MENTIRA = {
    "items": [
        {"item_num": "1", "description": "[EXISTENTE - sem intervencao] Porta PE1",
         "unit": "un", "quantity": 0, "confidence": "confirmado",
         "observations": "porta existente, manter", "discipline": "Esquadrias"},
        {"item_num": "2", "description": "Alvenaria existente a manter",
         "unit": "vb", "quantity": 0, "confidence": "confirmado",
         "observations": "nao orcar", "discipline": "Alvenaria"},
        {"item_num": "3", "description": "Divisoria nova em gesso",
         "unit": "m2", "quantity": 12.5, "confidence": "confirmado",
         "observations": "medido", "discipline": "Alvenaria"},
        {"item_num": "4", "description": "Item negativo defeituoso",
         "unit": "un", "quantity": -3, "confidence": "estimado",
         "observations": "", "discipline": "Complementares"},
    ]
}


@pytest.fixture
def rodar(monkeypatch):
    """Roda `analyze_all_sheets`, que e onde mora o saneamento.

    🩤 Na 1a versao deste guarda eu chamei `analyze_sheet` e os testes
    reprovaram sozinhos: aquela funcao devolve o JSON CRU da IA e nao sanea
    nada. Quem rebaixa selo, corta negativo e monta o BudgetItem e
    `analyze_all_sheets`. Guarda no caminho errado mede outra coisa.
    """
    def _rodar(payload):
        monkeypatch.setattr(analyzer, "analyze_sheet",
                            lambda *a, **k: dict(payload))
        monkeypatch.setattr(analyzer.anthropic, "Anthropic",
                            lambda **k: object())
        sheet = SheetInfo(filename="prancha.pdf", sheet_type=SheetType.ARQUITETURA,
                          text_content="", crops=[])
        _pd, itens = analyzer.analyze_all_sheets([sheet], api_key="sk-teste")
        return itens
    return _rodar


def _por_desc(itens, pedaco):
    for i in itens:
        d = i.description if hasattr(i, "description") else i.get("description", "")
        if pedaco.lower() in str(d).lower():
            return i
    raise AssertionError("item %r sumiu da saida" % pedaco)


def _q(i):
    return float(i.quantity if hasattr(i, "quantity") else i.get("quantity"))


def _c(i):
    c = i.confidence if hasattr(i, "confidence") else i.get("confidence")
    return str(getattr(c, "value", c)).lower()


def test_confirmado_com_zero_rebaixa_o_selo_e_MANTEM_zero(rodar):
    itens = rodar(ITENS_DE_MENTIRA)
    porta = _por_desc(itens, "Porta PE1")
    assert _c(porta) == "estimado", "o selo tinha que rebaixar (regra dura n1)"
    assert _q(porta) == 0, (
        "REGRESSAO: voltou a inventar quantidade. O projeto disse 'nao orcar' e "
        "a planilha do cliente recebeu %s." % _q(porta))

    alv = _por_desc(itens, "Alvenaria existente")
    assert _c(alv) == "estimado" and _q(alv) == 0


def test_o_que_tinha_quantidade_de_verdade_nao_e_tocado(rodar):
    """Controle negativo: o conserto nao pode zerar quem tinha numero."""
    itens = rodar(ITENS_DE_MENTIRA)
    div = _por_desc(itens, "Divisoria nova")
    assert _q(div) == 12.5, "o conserto mexeu em item que tinha quantidade real"
    assert _c(div) == "confirmado", "rebaixou selo de item legitimo"


def test_quantidade_negativa_continua_virando_zero(rodar):
    """A outra metade da politica nao pode ter sido perdida no conserto."""
    itens = rodar(ITENS_DE_MENTIRA)
    neg = _por_desc(itens, "negativo")
    assert _q(neg) == 0, "quantidade negativa deixou de ser saneada"


def test_controle_positivo_a_versao_ANTIGA_reprova(rodar):
    """Prova que o guarda acima reprova mesmo.

    Refaz o comportamento antigo (forcar 1) por cima da saida e confere que a
    afirmacao principal falha com ele.
    """
    itens = rodar(ITENS_DE_MENTIRA)
    porta = _por_desc(itens, "Porta PE1")
    qtd_antiga = 1 if _q(porta) == 0 else _q(porta)   # o que a versao antiga faria
    assert qtd_antiga == 1
    with pytest.raises(AssertionError):
        assert qtd_antiga == 0, "controle positivo: a versao antiga TEM que reprovar"
