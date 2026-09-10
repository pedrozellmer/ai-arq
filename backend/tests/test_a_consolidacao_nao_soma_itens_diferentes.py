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

🩸 E a revisão adversarial do próprio conserto achou o efeito colateral: com 1 un
cada, a recusa devolvia as linhas pra PASSADA 5, que troca 2+ itens "a definir" de
qty ≤ 1 por UMA linha "Itens de ... a especificar em projeto executivo" de 1 vb.
Antes do conserto a soma escapava desse corte; depois, janela, box e quantidade
sumiam. Os testes da passada 5 abaixo reprovam no primeiro commit do conserto.

Estes guardas CHAMAM `_consolidate_items`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import BudgetItem, Confidence  # noqa: E402
from main import _consolidate_items  # noqa: E402

_DISC = "Divisórias e Vidros"
_VAGO = "(especificação de perfil, cor e vidro por definir conforme memorial)"


def mk(desc, qty, unit="un", disc=_DISC, num="", obs=""):
    return BudgetItem(item_num=num, description=desc, unit=unit, quantity=qty,
                      observations=obs, ref_sheet="planta.dxf",
                      confidence=Confidence("estimado"), discipline=disc)


def _com(out, trecho):
    return [it for it in out if trecho in (it.description or "")]


def _sem_verba_generica(out):
    return not any("a especificar em projeto executivo" in (i.description or "") for i in out)


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
    # 🪤 Este caso reprova só pela DIMENSÃO: a régua `pode_fundir` não reconhece
    # código de esquadria como AL004 (achado separado, com medição pendente).
    out = _consolidate_items([
        mk("Caixilho de alumínio AL004 — esquadria 250 × 241 cm " + _VAGO, 2, num="10"),
        mk("Caixilho de alumínio AL005 — esquadria 160 × 120 cm " + _VAGO, 2, num="11"),
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


def test_a_passada_5_NAO_apaga_o_par_que_a_passada_3_recusou():
    out = _consolidate_items([
        mk("Caixilho de alumínio AL004 — esquadria 250 × 241 cm " + _VAGO, 1, num="10"),
        mk("Caixilho de alumínio AL005 — esquadria 160 × 120 cm " + _VAGO, 1, num="11"),
        mk("Box de vidro temperado — dimensão por definir", 1, num="12"),
    ])
    linhas = [(i.description, i.quantity, i.unit) for i in out]
    assert _sem_verba_generica(out), linhas
    assert sum(i.quantity for i in out) == 3, linhas
    assert [i.quantity for i in _com(out, "250 × 241")] == [1], linhas
    assert [i.quantity for i in _com(out, "160 × 120")] == [1], linhas
    assert _com(out, "Box de vidro"), "o box vizinho sumiu junto: %r" % linhas


def test_marcador_vago_so_na_OBSERVACAO_tambem_nao_apaga_o_que_foi_recusado():
    out = _consolidate_items([
        mk("Pilar de concreto armado — seção 31 × 150 cm (conforme projeto estrutural)", 1,
           disc="Complementares", num="1", obs="armadura a definir"),
        mk("Pilar de concreto armado — seção 25 × 60 cm (conforme projeto estrutural)", 1,
           disc="Complementares", num="2", obs="armadura a definir"),
    ])
    linhas = [(i.description, i.quantity, i.unit) for i in out]
    assert _sem_verba_generica(out), linhas
    assert [i.quantity for i in _com(out, "31 × 150")] == [1], linhas
    assert [i.quantity for i in _com(out, "25 × 60")] == [1], linhas


def test_seis_janelas_a_definir_continuam_seis_linhas_com_8_un():
    janelas = [("J01", "120 × 100 cm", 1), ("J02", "150 × 120 cm", 1), ("J03", "60 × 60 cm", 2),
               ("J04", "200 × 120 cm", 1), ("J05", "80 × 60 cm", 2), ("J06", "100 × 100 cm", 1)]
    out = _consolidate_items([mk("Janela %s — %s (modelo a definir)" % (c, m), q, num=c)
                              for c, m, q in janelas])
    linhas = [(i.description, i.quantity, i.unit) for i in out]
    assert _sem_verba_generica(out), linhas
    assert sum(i.quantity for i in out) == 8, linhas
    for codigo, _m, q in janelas:
        assert [i.quantity for i in _com(out, codigo)] == [q], (codigo, linhas)


def test_CONTROLE_itens_genericos_a_definir_continuam_virando_uma_verba():
    ele = "Instalações Elétricas e Dados"
    out = _consolidate_items([
        mk("Tomada de uso geral — modelo a definir", 1, disc=ele, num="1"),
        mk("Interruptor simples — modelo a definir", 1, disc=ele, num="2"),
        mk("Ponto de luz no teto — modelo a definir", 1, disc=ele, num="3"),
    ])
    assert len(out) == 1, [(i.description, i.quantity) for i in out]
    assert "a especificar em projeto executivo" in out[0].description and out[0].unit == "vb", out[0]


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


def test_a_descricao_fundida_nao_fica_com_TRAVESSAO_SOLTO():
    """Cortar em "conforme especificação" deixava "Porta de madeira — — 2 variantes".

    🪤 Quantidades DIFERENTES de propósito: a chave da passada 1 corta tudo depois
    do " — " ("madeira porta" pras duas), e com a mesma quantidade ela fica com uma
    linha só — o caso nem chegaria à passada 3 (a 1ª versão deste teste caiu nisso).
    """
    out = _consolidate_items([
        mk("Porta de madeira — conforme especificação 08", 1, disc="Portas e Ferragens", num="1"),
        mk("Porta de madeira — conforme especificação 09", 2, disc="Portas e Ferragens", num="2"),
    ])
    assert len(out) == 1 and out[0].quantity == 3, [(i.description, i.quantity) for i in out]
    assert out[0].description == "Porta de madeira — 2 variantes consolidadas", out[0].description
