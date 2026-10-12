# -*- coding: utf-8 -*-
"""A soma que a IA escreve na observação tem de fechar com a quantidade da linha.

🩸 12/10/2026 — numa avaliação a IA fez UMA linha de piso com a soma de 20
ambientes, listou as 20 parcelas e escreveu "= 377,36 m²". As parcelas somam
367,36. No banco (60 dias de cliente): em 123 linhas cuja quantidade é o total
de uma soma escrita, 5 não fecham — sempre soma longa.

A régua só AVISA e tira o selo; não troca a quantidade. E só julga a conta que
lê com certeza.
"""
import io
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from engine_rules import (MARCA_CONTA_NAO_FECHA, MARCAS_DE_REBAIXAMENTO,  # noqa: E402
                          marca_de_rebaixamento, selo_apos_soma_que_nao_fecha,
                          soma_escrita_que_nao_fecha)

# a observação da avaliação, com os nomes trocados (só a forma): 20 parcelas
_VINTE = ("Fonte: soma das áreas dos ambientes exceto WC (folha PLANTA BAIXA, Layout1): "
          "SALA A 16.16 + SALA B 8.73 + SALA C 29.86 + CORREDOR 26.20+30.50 + SALA D 11.00 + "
          "COPA 14.45 + DML 4.63 + GABINETE01 8.37 + GABINETE02 8.37 + GABINETE03 8.37 + "
          "GABINETE04 10.70 + GABINETE05 8.88 + GABINETE06 10.58 + ESTUDO GRAD 23.67 + "
          "ESTUDO PÓS 23.67 + RECEPÇÃO 55.92 + REUNIÃO 12.56 + SALA TÉCNICA 4.92 + "
          "ÁREA LIVRE 49.82 = %s m². Material de piso não especificado.")


# ── a conta que NÃO fecha ────────────────────────────────────────────────────
@pytest.mark.parametrize("obs, q, soma, n", [
    (_VINTE % "377.36", 377.36, 367.36, 20),
    ("106+74+32+32+13+10+10+7+5+2+2+1+1+1+1+1+1+1+1+1+1+1 = 303", 303, 304.0, 22),
    ("7+6+4+4+2+2+2+2+1+1+1+1+1+1+1+1+1+1+1+1+1 = 41 un", 41, 42.0, 21),
    ("5,41+1,93+4,67+2,69+14,68+4,87+2,23+0,53+1,58+2,76+2,64+1,80+2,54+1,11+2,64+1,80+0,60 = 53,48",
     53.48, 54.48, 17),
    ("WC FEM 2,40 + WC MASC 2,60 + WC PNE 5,87 = 12,87 m²", 12.87, 10.87, 3),
    ("etiquetas 'CORREDOR = 26,20 m²' + 'CORREDOR = 30,50 m²' = 58,70 m²", 58.70, 56.70, 2),
    ("'GABINETE 01=8,37 + GABINETE 02=8,37 + GABINETE 03=8,37' = 26,11 m²", 26.11, 25.11, 3),
    ("1.019,30 + 59,10 + 462,00 = 1.640,40", 1640.40, 1540.40, 3),
    # número grande que é QUANTIDADE (não ID) continua julgado: o total também é grande
    ("12000 + 15000 + 11000 = 39000 un", 39000, 38000.0, 3),
    ("tipo1=2 + tipo2=2 + tipo3=1 + tipo4=1 = 4", 4, 6.0, 4),      # o total era o nº de TIPOS
])
def test_a_conta_que_nao_fecha(obs, q, soma, n):
    assert soma_escrita_que_nao_fecha(obs, q) == (soma, q, n)


# ── a conta que fecha ────────────────────────────────────────────────────────
@pytest.mark.parametrize("obs, q", [
    (_VINTE % "367.36", 367.36),
    ("WC FEM 2.40+8.30 + WC MASC 2.60+8.30 + WC PNE 5.87 = 27.47 m².", 27.47),
    ("etiquetas 'CORREDOR = 26,20 m²' + 'CORREDOR = 30,50 m²' = 56,70 m²", 56.70),
    ("'GABINETE 01=8,37 + GABINETE 02=8,37 + GABINETE 03=8,37' = 25,11 m²", 25.11),
    ("5,10 + 5,20 = 10,30", 10.30),
    ("6,83 m² + 6,82 m² + 6,30 m² = 19,95", 19.95),
    ("1.019,30 + 59,10 + 462,00 + 1.051,20 + 1.583,30 + 1.445,00 + 67,90 = 5.687,80", 5687.80),
    ("40.5782 + 40.5782 = 81.16", 81.16),                       # arredondamento do total
    ("3,333 + 3,333 + 3,333 = 10,00", 10.0),                    # idem, 3 parcelas
])
def test_CONTROLE_a_conta_que_fecha_nao_e_julgada(obs, q):
    assert soma_escrita_que_nao_fecha(obs, q) is None


# ── o que a régua NÃO julga (não lê com certeza) ─────────────────────────────
@pytest.mark.parametrize("obs, q, porque", [
    ("57,16 + 55,49 + 62,70 + 60,87 = 236,22", 100, "o total escrito não é a quantidade da linha"),
    ("57,16 + 55,49 = 200,00", 100, "idem, e a conta nem fecha: é de outra coisa"),
    ("REUNIÃO 10 lugares + COPA 5,00 = 99,00", 99.0, "número seguido de palavra não é a parcela"),
    ("2×23,70 + 5,16 = 99,00", 99.0, "parcela com multiplicação"),
    ("WC (2,40+8,30) + COPA 5,00 = 99,00", 99.0, "parcela entre parênteses"),
    ("2,40+8,30 e 2,60+8,30 = 10,90", 10.90, "duas contas na mesma frase, sem pontuação"),
    ("1 + 2 = 3 e 4 + 5 = 9", 9, "o = de outra conta no meio da cadeia"),
    ("WC FEM 2.40+8.30; WC MASC 2.60+8.30 = 10.90", 10.90, "fim de frase no meio da cadeia"),
    ("Tipo A 5 + Tipo B 3. Tipo C 2 + Tipo D 4 = 6", 6, "fim de frase com rótulo numérico antes"),
    ("SALA 5,00 + (COPA) 3,00 + DML 1,00 = 99,00", 99.0, "parêntese no meio da cadeia"),
    ("'SALA 1=8,37 + SALA 2=8,37'", 8.37, "o = é o de dentro da última parcela"),
    ("tomada 2P+T = 12 un", 12, "não há número nas parcelas"),
    ("Luminária de embutir: IDs 500123 + 1300456 = 2", 2, "as parcelas são IDs de elemento; o total é quantos são"),
    ("elementos 1800594 + 1800595 + 1800596 = 3 un", 3, "idem, três IDs"),
    ("100 - 20 + 5 = 99", 99, "subtração"),
    ("área 10,00 + 5,00 ≈ 99 m²", 99, "aproximação não é igual"),
    ("12 + 7", 19, "sem total escrito"),
    ("12 + 7 = 99", 0, "linha zerada"),
    ("12 + 7 = 99", None, "sem quantidade"),
    ("", 10, "sem observação"),
    (None, 10, "sem observação"),
])
def test_CONTROLE_o_que_a_regua_nao_julga(obs, q, porque):
    assert soma_escrita_que_nao_fecha(obs, q) is None, porque


def test_o_nome_abreviado_com_ponto_nao_quebra_a_cadeia():
    """🪤 "Vest. Fem 23,70" tem ponto e espaço e é nome de ambiente, não fim de frase:
    cortar a cadeia ali faria a soma de uma parcela só — e o aviso falso."""
    certa = "Vest. Fem 23,70 + Vest. Mas 21,46 + Desp. Alimentos 5,13 = 50,29"
    assert soma_escrita_que_nao_fecha(certa, 50.29) is None


# ── o aviso ──────────────────────────────────────────────────────────────────
def test_o_aviso_diz_os_dois_numeros_e_nao_mexe_na_quantidade():
    obs = _VINTE % "377.36"
    conf, nova, avisou = selo_apos_soma_que_nao_fecha("estimado", obs, 377.36)
    assert avisou and conf == "estimado"
    assert nova.startswith(MARCA_CONTA_NAO_FECHA) and nova.endswith(obs)
    assert "20 parcelas" in nova and "367,36" in nova and "377,36" in nova


def test_a_linha_com_selo_perde_o_selo():
    conf, nova, avisou = selo_apos_soma_que_nao_fecha(
        "confirmado", "Fonte: CONTAGEM DE BLOCOS — 7+6+4+4+2+2+2+2+1+1+1+1+1+1+1+1+1+1+1+1+1 = 41 un", 41)
    assert (conf, avisou) == ("estimado", True)
    assert MARCA_CONTA_NAO_FECHA in MARCAS_DE_REBAIXAMENTO, "senão a chave do selo promove de novo"
    assert marca_de_rebaixamento(nova) == MARCA_CONTA_NAO_FECHA


def test_o_aviso_nao_se_repete():
    obs = "12 + 7 + 3 = 99"
    _c, uma, _a = selo_apos_soma_que_nao_fecha("estimado", obs, 99)
    conf, duas, avisou = selo_apos_soma_que_nao_fecha("estimado", uma, 99)
    assert not avisou and duas == uma and uma.count(MARCA_CONTA_NAO_FECHA) == 1


@pytest.mark.parametrize("conf", ["confirmado", "estimado"])
def test_CONTROLE_conta_que_fecha_fica_como_esta(conf):
    obs = "WC FEM 2,40 + WC MASC 2,60 + WC PNE 5,87 = 10,87 m²"
    assert selo_apos_soma_que_nao_fecha(conf, obs, 10.87) == (conf, obs, False)


# ── onde roda ────────────────────────────────────────────────────────────────
def test_roda_sobre_todas_as_linhas_antes_da_trava_final():
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    regua = fonte.index("selo_apos_soma_que_nao_fecha as _regra_conta")
    trava = fonte.index("marca_de_rebaixamento as _marca_reb")
    assert regua < trava, "a trava final é quem tira o selo de quem carrega a marca"
    trecho = fonte[regua:trava]
    assert "for _it in all_items:" in trecho and "_it.observations = _ob_s" in trecho
    assert "_it.quantity =" not in trecho, "a régua não troca a quantidade"
