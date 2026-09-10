# -*- coding: utf-8 -*-
"""A passada 3 do consolidador não soma o que as outras passadas mantiveram separado.

🩸 10/09/2026 — primeiro projeto de um cliente novo (orçamentista). A planilha
entregou "Caixilho de alumínio AL004 — esquadria 250 × 241 cm ( — 2 variantes
consolidadas" com 4 un, enquanto a linha de pintura do MESMO projeto descontava
"AL004 (2 un × 4,03 m²)". Eram duas linhas de caixilho com 2 un cada: a passada 2
não as juntou porque as MEDIDAS eram diferentes (guarda de atributo), e a passada
3 somou as duas porque ambas diziam "por definir conforme memorial". A outra
janela sumiu dentro da AL004 — regra dura nº4. Os pilares do mesmo projeto: 4
seções numa linha "31 × 150 cm — 4 variantes consolidadas".
🪤 A linha consumida não foi gravada; o 2º caixilho aqui é um reprodutor com
medida diferente, que é o único caso em que a passada 2 recusa.

Estes guardas CHAMAM `_consolidate_items`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import BudgetItem, Confidence  # noqa: E402
from main import _consolidate_items  # noqa: E402

_DISC = "Divisórias e Vidros"


def mk(desc, qty, unit="un", disc=_DISC, num=""):
    return BudgetItem(item_num=num, description=desc, unit=unit, quantity=qty,
                      observations="", ref_sheet="planta.dxf",
                      confidence=Confidence("estimado"), discipline=disc)


def _com(out, trecho):
    return [it for it in out if trecho in (it.description or "")]


def _mesma_medida():
    """Dois caixilhos de MESMA medida que chegam à passada 3.

    🪤 Quantidades DIFERENTES de propósito: com a mesma quantidade a passada 1
    trata as duas como a mesma linha repetida e fica com uma só — e o controle
    nem chegaria à passada 3 (a 1ª versão deste teste caiu nisso).
    """
    return [
        mk("Caixilho de alumínio — esquadria 250 × 241 cm (especificação de perfil por definir "
           "conforme memorial)", 1, num="1"),
        mk("Caixilho de alumínio — janela 250 × 241 cm (por definir conforme memorial)", 2, num="2"),
    ]


def test_dois_caixilhos_de_MEDIDAS_diferentes_nao_viram_uma_linha():
    out = _consolidate_items([
        mk("Caixilho de alumínio AL004 — esquadria 250 × 241 cm (especificação de perfil, "
           "cor e vidro por definir conforme memorial)", 2, num="10"),
        mk("Caixilho de alumínio AL005 — esquadria 160 × 120 cm (especificação de perfil, "
           "cor e vidro por definir conforme memorial)", 2, num="11"),
    ])
    caixilhos = [it for it in out if "Caixilho" in (it.description or "")]
    assert len(caixilhos) == 2, [(i.description, i.quantity) for i in caixilhos]
    assert not any("variantes consolidadas" in i.description for i in caixilhos), caixilhos
    assert [i.quantity for i in _com(out, "250 × 241")] == [2], "a AL004 tem que continuar com 2 un"
    assert [i.quantity for i in _com(out, "160 × 120")] == [2], "a outra janela não pode sumir"


def test_item_SEM_medida_no_comeco_nao_libera_duas_medidas_diferentes():
    """Comparar só com o 1º do grupo deixaria passar: ele não tem dimensão."""
    out = _consolidate_items([
        mk("Pilar de concreto armado (conforme projeto estrutural)", 1, disc="Complementares", num="24"),
        mk("Pilar de concreto armado — seção 31 × 150 cm (conforme projeto estrutural)", 2,
           disc="Complementares", num="25"),
        mk("Pilar de concreto armado — seção 25 × 60 cm (conforme projeto estrutural)", 2,
           disc="Complementares", num="26"),
    ])
    pilares = [it for it in out if "Pilar" in (it.description or "")]
    assert not any("variantes consolidadas" in i.description for i in pilares), \
        [(i.description, i.quantity) for i in pilares]
    assert [i.quantity for i in _com(out, "31 × 150")] == [2]
    assert [i.quantity for i in _com(out, "25 × 60")] == [2]


def test_CONTROLE_variantes_de_legenda_SEM_medida_continuam_fundindo():
    out = _consolidate_items([
        mk("Porta de madeira conforme especificação 08", 1, disc="Portas e Ferragens", num="1"),
        mk("Porta de madeira conforme especificação 09", 1, disc="Portas e Ferragens", num="2"),
        mk("Porta de madeira conforme especificação 10", 1, disc="Portas e Ferragens", num="3"),
    ])
    assert len(out) == 1 and out[0].quantity == 3, [(i.description, i.quantity) for i in out]
    assert "variantes consolidadas" in out[0].description


def test_CONTROLE_mesma_medida_continua_fundindo_e_diz_de_onde_veio():
    out = _consolidate_items(_mesma_medida())
    assert len(out) == 1 and out[0].quantity == 3, [(i.description, i.quantity) for i in out]
    assert "variantes consolidadas" in out[0].description, out[0].description
    obs = out[0].observations or ""
    assert "Veio de:" in obs, obs
    assert "esquadria 250 × 241" in obs and "janela 250 × 241" in obs, obs


def test_a_descricao_fundida_nao_fica_com_PARENTESE_ABERTO():
    out = _consolidate_items(_mesma_medida())
    assert len(out) == 1, [(i.description, i.quantity) for i in out]
    desc = out[0].description
    assert "( —" not in desc and "(—" not in desc, desc
    assert desc.endswith("— 2 variantes consolidadas"), desc
    assert "250 × 241 cm — 2 variantes" in desc, desc
