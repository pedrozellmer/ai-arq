# -*- coding: utf-8 -*-
"""A medida em MILÍMETRO separa dois itens, como a medida em centímetro já separava.

🩸 14/10/2026 (fc14a25f): prancha de modulação de divisórias, persianas entre
vidros com a medida escrita na planta — "03 (TRÊS) PERSIANAS DE 1398MM X
2882MM". A régua de dimensão (`atributos_distintivos`, que o `pode_fundir`
e o `motivo_para_nao_fundir` perguntam) lia "30x90" e "0,90 x 2,10", não
"1398mm × 2882mm" (4 dígitos, "mm" colado). Saiu assim:
- passada 2: 1398, 1468 e 1638 mm, 3 un cada, viraram UMA linha de 3 un — seis
  persianas sumiram;
- passada 3: 1964, 955, 1534 e 1534 mm viraram "1964mm × 2882mm — 4 variantes
  consolidadas", 6 un — o total ficou, as larguras de compra não.

No banco (90 dias de cliente): fusão com medida de 4 dígitos em mm, só esta.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
import main  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

_P = "Persiana entre vidros — %s painéis de %smm × 2882mm — módulo M4-J — %s"


def _it(desc, qtd, k=0, unit="un", disc="Arquitetura", prancha="modulacao.pdf (p1 · Planta)"):
    return BudgetItem(item_num=str(k + 1), description=desc, unit=unit, quantity=qtd,
                      ref_sheet=prancha, confidence=Confidence("estimado"), discipline=disc)


def _persianas(out):
    return sorted((i.description, i.quantity) for i in out if "Persiana" in i.description)


_DO_CASO = (
    ("03 (três)", "1398", "Sala 01 / Sala 02", 3),
    ("03 (três)", "1468", "Sala 03", 3),
    ("03 (três)", "1638", "Jurídico", 3),
    ("02 (dois)", "1964", "Sala 03 / região superior da planta", 2),
    ("02 (dois)", "955", "Sala 04 (lateral)", 2),
    ("01 (uma)", "1534", "Reunião Rápida", 1),
    ("01 (uma)", "1534", "região lateral direita da planta", 1),
)


def test_o_caso_as_persianas_da_prancha_nao_somem():
    out = main._consolidate_items([_it(_P % (n, mm, sala), q, k) for k, (n, mm, sala, q) in enumerate(_DO_CASO)])
    ps = _persianas(out)
    # cada largura continua com a sua quantidade, numa linha que diz a SUA largura
    por_largura = {}
    for d, q in ps:
        larguras = [mm for _n, mm, _s, _q in _DO_CASO if "de %smm" % mm in d]
        assert len(set(larguras)) == 1, d
        por_largura[larguras[0]] = por_largura.get(larguras[0], 0) + q
    assert {k: v for k, v in por_largura.items() if k != "1534"} == {
        "1398": 3, "1468": 3, "1638": 3, "1964": 2, "955": 2}, ps
    assert not any("variantes consolidadas" in d for d, _q in ps), ps
    # 🪤 as duas de 1534 mm (1 un cada, "Reunião Rápida" × "região lateral
    # direita") têm a mesma largura: quem decide é a regra da linha repetida
    # da passada 1 — que já as juntava sozinhas, com a nota pedindo conferência.
    _1534 = [(d, q) for d, q in ps if "1534mm" in d]
    assert _1534 and (sum(q for _d, q in _1534) == 2 or any(
        "Confira se era o mesmo item" in (i.observations or "") for i in out if "1534mm" in i.description)), ps


def test_a_mesma_quantidade_com_larguras_diferentes_nao_funde():
    a, b = _P % ("03 (três)", "1398", "Sala A"), _P % ("03 (três)", "1638", "Sala B")
    assert er.motivo_para_nao_fundir(er.perfil_de_fusao(a, "un"), er.perfil_de_fusao(b, "un"))
    assert not er.pode_fundir(a, b)


@pytest.mark.parametrize("a,b", [
    ("Porta de vidro 900mm × 2100mm", "Porta de vidro 800mm × 2100mm"),
    ("Porta de vidro 900 × 2100 mm", "Porta de vidro 800 × 2100 mm"),
    ("Painel 1160×1110 mm", "Painel 1200×1110 mm"),
])
def test_as_grafias_em_milimetro(a, b):
    assert not er.pode_fundir(a, b), (a, b)
    assert er.motivo_para_nao_fundir(a, b), (a, b)


@pytest.mark.parametrize("a,b", [
    # a mesma medida escrita de outro jeito é a mesma peça
    ("Porta P1 — 2700×1000mm — porta de entrada", "Porta P1 — PORTA-P1 2700×1000 mm — porta de entrada"),
    ("Persiana entre vidros de 1398mm × 2882mm", "Persiana entre vidros de 1398 x 2882 mm"),
    ("Porcelanato 800×800mm", "Porcelanato 800×800"),
])
def test_CONTROLE_a_mesma_medida_continua_juntando(a, b):
    assert er.pode_fundir(a, b), (a, b)
    assert not er.motivo_para_nao_fundir(a, b), er.motivo_para_nao_fundir(a, b)


def test_o_x_e_o_sinal_de_vezes_sao_a_mesma_dimensao():
    # sem isso, "800×800mm" (lida agora) bloquearia "800×800" (lida antes)
    assert er.atributos_distintivos("Porcelanato 60×60")["dimensao"] == "60x60"
    assert er.pode_fundir("Porcelanato 60x60", "Porcelanato 60×60")


def test_CONTROLE_a_linha_repetida_continua_juntando():
    d = _P % ("03 (três)", "1398", "Sala 01")
    out = main._consolidate_items([_it(d, 3, 0), _it(d, 3, 1)])
    assert _persianas(out) == [(d, 3)], _persianas(out)


def test_CONTROLE_a_medida_de_um_lado_so_nao_bloqueia():
    assert er.pode_fundir("Persiana entre vidros de 1398mm × 2882mm", "Persiana entre vidros")


def test_CONTROLE_o_que_ja_se_lia_le_igual():
    # a dimensão curta: o valor de sempre
    assert er.atributos_distintivos("Pilar 30x90")["dimensao"] == "30x90"
    assert er.atributos_distintivos("Porta 0,90 x 2,10 m")["dimensao"] == ".90x2.10"


def test_CONTROLE_ponto_de_milhar_nao_vira_pedaco_do_numero():
    # sem a trava, "1.398mm × 2.882mm" seria "398x2" e bloquearia a mesma peça
    # escrita "1398mm × 2882mm" (o "só o número difere" é outra régua)
    assert "dimensao" not in er.atributos_distintivos("Persiana de 1.398mm × 2.882mm")
    assert er.pode_fundir("Persiana de 1.398mm × 2.882mm", "Persiana de 1398mm × 2882mm")


def test_a_dimensao_em_milimetro():
    for d in ("Persiana 1398mm × 2882mm", "Persiana 1398 x 2882 mm", "Persiana 1398MM X 2882MM"):
        assert er.atributos_distintivos(d)["dimensao"] == "1398x2882", d
