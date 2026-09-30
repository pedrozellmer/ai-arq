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


def _dois_quadros_com_classes():
    """Dois quadros; os totais por classe (50A + 60B) diferem das linhas em ~4%
    (dentro dos 5%): só a SOMA DOS TOTAIS LIDOS explica o total do quadro e o
    geral."""
    ts = []
    for y0, linhas, t50, t60 in ((10, (("8", 100, 39.5), ("10", 200, 123.4), ("12.5", 50, 48.2)), 120, 100),
                                 (-40, (("8", 200, 79.0), ("10", 100, 61.7), ("12.5", 100, 96.3)), 150, 97)):
        ts += [_t("BITOLA", 10, y0), _t("COMPR (m)", 40, y0), _t("PESO (kg)", 70, y0)]
        for i, (b, comp, kg) in enumerate(linhas):
            y = y0 - 5 - 4 * i
            ts += [_t(b, 10, y), _t("%g" % comp, 40, y), _t("%g" % kg, 70, y)]
        ts += [_t("PESO TOTAL 50A =", 10, y0 - 19), _t("%g kgf" % t50, 70, y0 - 19),
               _t("PESO TOTAL 60B =", 10, y0 - 23), _t("%g kgf" % t60, 70, y0 - 23)]
    return ts


def test_CONTROLE_os_dois_quadros_sem_nada_a_mais_sao_confiaveis():
    r = se.parse_steel_table(_dois_quadros_com_classes())
    assert r["confiavel"] is True and r["total_kg"] == pytest.approx(467.0), r


@pytest.mark.parametrize("extra", ["PESO TOTAL QUADRO 1 = 220 kgf",     # = 120 + 100 (um quadro)
                                   "PESO TOTAL GERAL = 467 kgf"])        # = os dois
def test_CONTROLE_total_que_e_soma_dos_totais_lidos_nao_sobra(extra):
    r = se.parse_steel_table(_dois_quadros_com_classes() + [_t(extra, 300, -80)])
    assert r["confiavel"] is True, (extra, r["avisos"])


def test_CONTROLE_arredondamento_de_1_kg_num_total_pequeno():
    # uma linha de 39,5 kg e o resumo "PESO TOTAL CA-50 = 40 kgf" fora do quadro
    ts = [_t("BITOLA", 10, 10), _t("COMPR (m)", 40, 10), _t("PESO (kg)", 70, 10),
          _t("8", 10, 5), _t("100", 40, 5), _t("39.5", 70, 5), _t("PESO TOTAL CA-50 = 40 kgf", 300, -80)]
    r = se.parse_steel_table(ts)
    assert r["confiavel"] is True, r["avisos"]


def test_o_aviso_traz_os_maiores_primeiro():
    extra = []
    for i, v in enumerate((2, 900, 7, 50, 1200)):
        extra += [_t("Peso Total 50A =", 300, -9 - 5 * i), _t("%g kgf" % v, 340, -9 - 5 * i)]
    r = se.parse_steel_table(_quadro_lido() + extra)
    av = next(a for a in r["avisos"] if "ficou de fora" in a)
    assert "os maiores: 1200, 900, 50, 7 kg e mais 1" in av, av


def test_o_detalhe_por_quadro_pra_medir():
    r = se.parse_steel_table(_dois_quadros_com_classes())
    pq = {q["quadro"]: q for q in r["por_quadro"]}
    assert (pq[0]["n_linhas"], pq[0]["linhas_kg"], pq[0]["total_lido_kg"]) == (3, 211.1, 220.0), pq
    assert (pq[1]["n_linhas"], pq[1]["linhas_kg"], pq[1]["total_lido_kg"]) == (3, 237.0, 247.0), pq
    assert pq[0]["cabecalho_xy"][1] == 10 and pq[1]["cabecalho_xy"][1] == -40, pq


def test_o_detalhe_por_quadro_nao_vai_pro_prompt():
    txt = se.structural_prompt_section({"aco": se.parse_steel_table(_dois_quadros_com_classes())})
    assert "por_quadro" not in txt and "cabecalho_xy" not in txt, txt


@pytest.mark.parametrize("texto", ["TOTAL = 24", "TOTAL: 24"])
def test_CONTROLE_total_sem_peso_nem_kg_no_proprio_texto(texto):
    r = se.parse_steel_table(_quadro_lido() + [_t(texto, 300, -9)])
    assert r["confiavel"] is True, (texto, r["avisos"])


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
