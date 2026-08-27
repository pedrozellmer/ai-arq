# -*- coding: utf-8 -*-
"""A régua dizia "não avaliada" depois de avaliar 1.104 cotas.

🔍 27/08/2026. Em 26/08 eu consertei o `cotas=-` do log de unidade, que juntava
CINCO desfechos opostos num traço só. Menos de 24 horas depois, o próprio
instrumento novo me mostrou o sexto — e esse mente de um jeito pior:

    motor:unidade — regua=nao-decidiu utilizaveis=1104 porque=nao-avaliada

**Mil e cento e quatro cotas lidas, e o log afirmando que a régua não rodou.**

🔑 A causa: `out["motivo"]` nasce como `"nao-avaliada"` e é sobrescrito em cada
saída conhecida. A saída FINAL — cair fora do `if detected is not None and
len(proven) == 1 and n_digitadas >= _DIM_MIN_COTAS` — devolve `out` sem tocar no
motivo, então o valor inicial vaza pro log como se fosse diagnóstico.

E o `except` devolvia um dicionário SEM a chave `motivo`, o que fazia falha de
código virar indistinguível de "o desenho não tem cota".

🪤 A diferença é acionável: "não avaliada" é beco sem saída; "avaliou, 1 fator
qualificou, 0 cotas com número digitado" aponta exatamente qual condição travou
a correção.

📌 Visto no job `evaa4391` — avaliação isolada da prancha estrutural do Evandro,
rodada pra investigar `pilares=0`. O instrumento de ontem achou o buraco do
instrumento de ontem.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ezdxf  # noqa: E402

from dwg_extractor import _validate_unit_by_dimensions  # noqa: E402


def _desenho_com_cotas(n=40, comprimento=7.3):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for i in range(n):
        d = msp.add_linear_dim(base=(0, i * 3 + 2), p1=(0, i * 3),
                               p2=(comprimento, i * 3))
        d.render()
    return doc


def test_NAO_diz_nao_avaliada_quando_avaliou():
    """🚨 O conserto. Se sobrou cota utilizável, a régua avaliou — e o motivo
    tem que refletir isso."""
    r = _validate_unit_by_dimensions(_desenho_com_cotas(), 0.001)
    uteis = r.get("cotas_utilizaveis") or 0
    assert uteis > 0, "o controle não gerou cota utilizável — teste inútil"
    assert r.get("motivo") != "nao-avaliada", (
        "avaliou %d cotas e o log ainda diz 'nao-avaliada'" % uteis)


def test_o_motivo_DIZ_o_que_travou():
    """Diagnóstico serve pra decidir o próximo passo. "não avaliada" não decide
    nada; "1 fator qualificou, 0 com número digitado" decide."""
    r = _validate_unit_by_dimensions(_desenho_com_cotas(), 0.001)
    m = (r.get("motivo") or "").lower()
    assert "utiliz" in m, m
    assert "digitado" in m, (
        "o motivo não diz quantas cotas tinham número digitado — é essa "
        "condição que trava a correção: %s" % m)
    assert "qualific" in m, (
        "o motivo não diz quantos fatores qualificaram: %s" % m)


def test_desenho_SEM_cota_continua_com_o_motivo_dele():
    """🧪 Controle negativo: o conserto não pode ter atropelado os motivos que
    já existiam desde 26/08."""
    doc = ezdxf.new("R2010")
    doc.modelspace().add_line((0, 0), (10, 0))
    r = _validate_unit_by_dimensions(doc, 0.001)
    m = (r.get("motivo") or "").lower()
    assert "nenhuma cota" in m or "utiliz" in m, (
        "desenho sem cota perdeu o motivo específico: %r" % m)
    assert "avaliada e sem prova" not in m, (
        "desenho sem cota recebeu o motivo da saída final — os dois casos "
        "viraram um só de novo")


def test_a_FALHA_da_regua_tambem_deixa_rastro():
    """🪤 O `except` devolvia dicionário sem `motivo`, então falha de código
    ficava indistinguível de "o desenho não tem cota". A régua não pode
    derrubar a extração — mas também não pode sumir sem dizer que quebrou."""
    import io
    _b = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = io.open(os.path.join(_b, "dwg_extractor.py"), encoding="utf-8").read()
    i = src.find("defensivo: a régua NUNCA derruba a extração")
    assert i > 0, "não achei o except defensivo da régua"
    trecho = src[i:i + 600]
    assert '"motivo"' in trecho, (
        "o except voltou a devolver sem motivo — falha de código vira "
        "'não tinha cota' no log")


def test_o_motivo_INICIAL_continua_existindo():
    """Ele ainda é útil como sentinela: se aparecer no log com 0 cotas
    utilizáveis, é porque a régua realmente não chegou a rodar."""
    import io
    _b = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = io.open(os.path.join(_b, "dwg_extractor.py"), encoding="utf-8").read()
    assert '"motivo": "nao-avaliada"' in src, (
        "o valor inicial sumiu — some também a sentinela de 'nem rodou'")
