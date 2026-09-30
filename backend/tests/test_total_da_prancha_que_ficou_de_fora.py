# -*- coding: utf-8 -*-
"""Total de peso declarado na prancha que a leitura NÃO usou = quadro de aço não
lido → a leitura não sai confiável.

🩸 30/09/2026 — antes/depois do H37 no acervo (estrutura de vigas, 13 quadros,
20 linhas "Peso Total 50A/60A"). A leitura somou 11.670 kg, o total que ela
mesma leu dava 11.152 — bateu nos 5% e saiu CONFIÁVEL. A prancha declara
12.221 kg: faltavam ~551 kg de CA-50, de um quadro cujas linhas E cujo total
ficaram de fora juntos. Soma parcial conferida contra total parcial.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

from dwg_extractor import TextAnnotation as T  # noqa: E402
import structural_extractor as se  # noqa: E402
from test_borda_do_cabecalho_de_aco import _EBERICK  # noqa: E402

H = 2.5


def _t(txt, x, y, h=H):
    return T("0", txt, (x, y), h)


def _quadro_lido(total=("PESO TOTAL 50A =", "211,1 kgf")):
    """BITOLA | COMPR | PESO, 3 linhas que batem na NBR 7480, e o total."""
    ts = [_t("BITOLA", 10, 10), _t("COMPR (m)", 40, 10), _t("PESO (kg)", 70, 10)]
    for i, (b, comp, kg) in enumerate((("8", 100, 39.5), ("10", 200, 123.4), ("12.5", 50, 48.2))):
        y = 5 - 4 * i
        ts += [_t(b, 10, y), _t("%g" % comp, 40, y), _t("%g" % kg, 70, y)]
    if total:
        ts += [_t(total[0], 10, -9), _t(total[1], 70, -9)]
    return ts


def _quadro_que_nao_e_lido(x0=300, total=("Peso Total 50A =", "900 kgf")):
    """Um quadro de outro formato, que o leitor não reconhece — sobra o total dele."""
    ts = [_t("POS", x0, 10), _t("QUANT", x0 + 30, 10), _t("KG", x0 + 60, 10),
          _t("N1", x0, 5), _t("12", x0 + 30, 5), _t("900", x0 + 60, 5)]
    if total:
        ts += [_t(total[0], x0, -9), _t(total[1], x0 + 40, -9)]
    return ts


# ── o caso ─────────────────────────────────────────────────────────────────────
def test_o_caso_quadro_nao_lido_com_total_declarado_derruba_o_confiavel():
    r = se.parse_steel_table(_quadro_lido() + _quadro_que_nao_e_lido())
    assert r["confiavel"] is False, r
    assert any("900" in a and "ficou de fora" in a for a in r["avisos"]), r["avisos"]


@pytest.mark.parametrize("total", [("Peso Total 50A = 900 kgf", ""), ("Peso Total 50A = 900", ""),
                                   ("PESO TOTAL:", "900"), ("TOTAL", "900 kgf")])
def test_os_formatos_do_total_que_sobrou(total):
    extra = [_t(total[0], 300, -9)] + ([_t(total[1], 340, -9)] if total[1] else [])
    r = se.parse_steel_table(_quadro_lido() + extra)
    assert r["confiavel"] is False, (total, r["avisos"])


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_tudo_lido_segue_confiavel():
    r = se.parse_steel_table(_quadro_lido())
    assert r["confiavel"] is True and r["total_kg"] == pytest.approx(211.1), r
    assert not any("ficou de fora" in a for a in r["avisos"]), r["avisos"]


def test_CONTROLE_eberick_segue_confiavel():
    r = se.parse_steel_table([T(lay, txt, (x, y), h) for lay, txt, x, y, h in _EBERICK])
    assert r["confiavel"] is True and r["total_kg"] == 18252.0, r


def test_CONTROLE_total_geral_do_quadro_e_a_soma_das_classes():
    # "Peso Total 50A" e "60B" lidos; o "PESO TOTAL = soma" do mesmo quadro não sobra
    r = se.parse_steel_table(_quadro_lido() + [_t("PESO TOTAL GERAL =", 0, -30), _t("211,1 kgf", 40, -30)])
    assert not any("ficou de fora" in a for a in r["avisos"]), r["avisos"]


@pytest.mark.parametrize("total", [
    ("TOTAL", "24"),                    # tabela de quantidades: sem "peso" e sem kg
    ("PESO TOTAL CA 50", ""),           # rótulo com a classe, sem valor
    ("PESO TOTAL", "350"),              # linha TOTAL de tabela: o número à direita pode ser o comprimento
    ("TOTAL =", "24"),                  # "=" mas nada diz que é peso
])
def test_CONTROLE_o_que_nao_e_total_de_peso_declarado(total):
    extra = [_t(total[0], 300, -9)] + ([_t(total[1], 340, -9)] if total[1] else [])
    r = se.parse_steel_table(_quadro_lido() + extra)
    assert r["confiavel"] is True, (total, r["avisos"])
