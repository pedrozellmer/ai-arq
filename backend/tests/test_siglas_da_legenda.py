# -*- coding: utf-8 -*-
"""SIGLA → NOME lido da legenda da própria prancha e entregue à IA.

🩸 25/09/2026 — job `53f0483f`: a tabela de acessórios dizia TH-90º = TÊ
HORIZONTAL, CH-90º = CURVA HORIZONTAL, CZ-90º = CRUZETA; a IA, lendo os textos
soltos, trocou os três em quatro releituras. 🪤 Medido no acervo: "PD=255cm",
"A=4,20m²" são medida, e "RALO"/"BACIA" ao lado de um texto são rótulo.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from dwg_extractor import DXFExtraction, TextAnnotation  # noqa: E402

H = 100.0


def _T(texto, x, y, h=H):
    return TextAnnotation(layer="LEGENDA", text=texto, position=(x, y), height=h)


def _tabela():
    """A tabela de acessórios real (job 53f0483f, folha 2/4): duas colunas de 3.
    🪤 "JA", curta, sai 1,9 letra fora do prumo das outras siglas — o nome não."""
    return [
        _T("CH-90º", 24368, 4189), _T("CURVA HORIZONTAL 90°", 25583, 4192),
        _T("CVE-90°", 24313, 3932), _T("CURVA VERTICAL EXTERNA 90°", 25586, 3935),
        _T("CVI-90°", 24349, 3680), _T("CURVA VERTICAL INTERNA 90°", 25596, 3682),
        _T("TH-90º", 28625, 4189), _T("TÊ HORIZONTAL 90°", 29853, 4188),
        _T("JA", 28813, 3920), _T("JUNÇÃO ARTICULADA", 29853, 3921),
        _T("CZ-90º", 28622, 3675), _T("CRUZETA HORIZONTAL 90°", 29853, 3673),
        _T("L = LEITO PARA CABOS", 27435, 5544),
    ]


def test_a_tabela_da_legenda_vira_dicionario():
    s = dx.siglas_da_legenda(_tabela())
    assert s["TH-90º"] == "TÊ HORIZONTAL 90°"
    assert s["CH-90º"] == "CURVA HORIZONTAL 90°"
    assert s["CZ-90º"] == "CRUZETA HORIZONTAL 90°"
    assert s["JA"] == "JUNÇÃO ARTICULADA", "a sigla fora do prumo vale pelo nome alinhado"
    assert s["L"] == "LEITO PARA CABOS"


# ── 26/09: par solto no meio da planta é anotação, não definição ───────────────
def _planta_luminotecnica(h=0.1):
    """Job befab5aa: C01…C03 são número de CIRCUITO, espalhados pela planta; UM
    C01 tem à direita, na mesma linha, o rótulo da luminária que ele acende."""
    t = [_T("C01", 3.0 * k, 1.7 * k, h) for k in range(6)]
    t += [_T("C02", 2.2 * k + 0.9, 4.1 * k, h) for k in range(4)]
    t += [_T("C03", 5.3 * k + 1.3, 0.7 * k + 9.0, h) for k in range(3)]
    t += [_T("C01", 73.5, -31.1, h), _T("PERFIL DE LED DE EMBUTIR - 2,00m", 73.71, -31.1, h)]
    return t


def test_o_caso_numero_de_circuito_ao_lado_de_um_rotulo_nao_vira_sigla():
    """🩸 Virou "C01 = PERFIL DE LED…" e a planilha trouxe 39 × 2 m = 78 ml."""
    assert "C01" not in dx.siglas_da_legenda(_planta_luminotecnica())


_ROTULADO = [_T("C01", 73.5, -31.1, 0.1), _T("PERFIL DE LED DE EMBUTIR - 2,00m", 73.71, -31.1, 0.1)]


@pytest.mark.parametrize("vizinhos", [
    [_T("C01", 73.52, -31.6, 0.1), _T("C01", 73.49, -32.2, 0.1)],    # o MESMO circuito em fila
    [_T("C02", 74.8, -31.5, 0.1), _T("C03", 72.0, -30.6, 0.1)],      # perto, mas fora do prumo
    [_T("C02", 73.5, -45.0, 0.1), _T("C03", 73.52, -60.0, 0.1)],     # no prumo, mas longe
], ids=["mesmo-codigo-em-fila", "fora-do-prumo", "longe-demais"])
def test_CONTROLE_etiquetas_de_planta_nao_formam_tabela(vizinhos):
    """Três jeitos de a planta parecer coluna sem ser: a mesma etiqueta repetida
    (não são 3 siglas DISTINTAS), etiquetas vizinhas fora do prumo, e etiquetas
    no prumo ao longo de uma parede comprida."""
    assert "C01" not in dx.siglas_da_legenda(_ROTULADO + vizinhos)


def test_coluna_de_codigos_com_um_nome_na_linha_vale():
    """Forro do acervo: os códigos da tabela empilhados na coluna do símbolo e só
    o R6 tem o nome na mesma linha — é tabela, vale."""
    ts = [_T(c, x, y, 15) for c, x, y in (
        ("D3", -4828, -1236), ("D8", -4828, -1291), ("R4", -4815, -1325), ("P5", -4815, -1391),
        ("P6", -4830, -1517), ("R6", -4816, -1696), ("A3", -4823, -1769), ("A1", -4852, -1869),
        ("A2", -4852, -1929))] + [_T("LUMINI FIT S1 T5R-T5D", -4749, -1694, 20)]
    assert dx.siglas_da_legenda(ts).get("R6") == "LUMINI FIT S1 T5R-T5D"


def test_CONTROLE_tabela_de_duas_linhas_nao_basta():
    """Escolha medida no acervo (26/09): 2 pares não provam tabela — o preço é
    perder uma legenda de 2 itens (mobiliário MB-01/MB-02), que fica sem nome
    (a IA lê os textos como antes); o ganho é nunca afirmar um nome falso."""
    s = dx.siglas_da_legenda([_T("MB-01", 0, 0), _T("MESA REDONDA", 300, 0),
                              _T("MB-02", 0, -300), _T("MESA DE CHÁ", 300, -300)])
    assert s == {}


def test_o_igual_vale_sozinho():
    assert dx.siglas_da_legenda([_T("L = LEITO PARA CABOS", 0, 0)]) == {"L": "LEITO PARA CABOS"}


def test_a_ia_recebe_o_dicionario():
    ex = DXFExtraction(filename="x.dxf", blocks=[], walls=[], hatches=[], texts=_tabela(),
                       layers=[], dimensions=[], metadata={})
    txt = ex.to_structured_prompt()
    assert "SIGLAS DA LEGENDA DESTA PRANCHA" in txt and "TH-90º = TÊ HORIZONTAL 90°" in txt


@pytest.mark.parametrize("textos, sigla", [
    ([_T("PD=255cm", 0, 0)], "PD"),                                    # medida no formato "="
    ([_T("A=4,20m²", 0, 0)], "A"),
    ([_T("H=70cm ABAIXO DA BORDA DA PISCINA", 0, 0)], "H"),          # medida + frase (acervo)
    ([_T("RALO", 0, 0), _T("- EXISTENTE NO LOCAL", 300, 0)], "RALO"),  # rótulo, não sigla
    ([_T("T1", 0, 0), _T("h 1,10 2,20 3,30", 300, 0)], "T1"),          # "nome" que é número
    ([_T("CH-90º", 0, 0), _T("CURVA HORIZONTAL 90°", 300, 800)], "CH-90º"),   # outra linha
    ([_T("CH-90º", 0, 0), _T("CURVA HORIZONTAL 90°", 5000, 0)], "CH-90º"),    # longe demais
])
def test_CONTROLE_o_que_nao_e_sigla_com_nome(textos, sigla):
    assert sigla not in dx.siglas_da_legenda(textos)


def test_vale_o_nome_mais_perto():
    s = dx.siglas_da_legenda(_tabela() + [_T("NOTA DE OUTRA COLUNA", 26400, 4189)])
    assert s["CH-90º"] == "CURVA HORIZONTAL 90°"


def test_CONTROLE_sem_legenda_sem_secao():
    ex = DXFExtraction(filename="x.dxf", blocks=[], walls=[], hatches=[],
                       texts=[_T("PLANTA BAIXA", 0, 0)], layers=[], dimensions=[], metadata={})
    assert "SIGLAS DA LEGENDA" not in ex.to_structured_prompt()
