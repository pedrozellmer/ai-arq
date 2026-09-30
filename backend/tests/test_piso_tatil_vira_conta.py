# -*- coding: utf-8 -*-
"""Piso tátil contado em placa e orçado em m² vira CONTA (estimada), não branco.

🩸 30/09/2026 — H4 do estudo do acervo. A régua de 14/09
(`quantidade_apos_troca_de_unidade`) não deixa o número atravessar troca de
grandeza: "185 un" de piso tátil orçado em m² saía EM BRANCO — 41 de 50
linhas de piso tátil em m² de clientes em 90 dias. Quando a descrição diz o
tamanho da placa ("placa 40×40 cm", "módulo 25×25cm", "20×20"), contagem ×
área da placa é conta com dado do próprio projeto: sai ESTIMADA, com a conta
escrita na frente. Sem o tamanho, continua em branco.
"""
import ast
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import engine_rules as er  # noqa: E402
from _corpo import fonte  # noqa: E402


@pytest.mark.parametrize("q,desc,m2,placa", [
    (185, "Piso tátil de alerta/direcional — placa 40×40 cm — PRK", 29.60, "40 × 40"),
    (51, "Piso tátil direcional — módulo 25×25cm (conforme NBR 9050)", 3.19, "25 × 25"),
    (15, "Piso tátil direcional — placa 35×10 cm — ABNT NBR 9050", 0.53, "35 × 10"),
    (7, "Piso tátil de alerta 20×20 cm (Podotatil 20×20 Alerta)", 0.28, "20 × 20"),
    (12, "Piso podotátil de alerta 25x25 amarelo", 0.75, "25 × 25"),
])
def test_placa_na_descricao_vira_conta(q, desc, m2, placa):
    qtd, nota = er.quantidade_apos_troca_de_unidade(q, "un", "m²", descricao=desc)
    assert qtd == pytest.approx(m2), (qtd, nota)
    assert nota.startswith("⚠ CONTA, não medida") and placa in nota, nota


@pytest.mark.parametrize("q,de,para,desc", [
    (511, "un", "m²", "Piso tátil direcional — placa podotátil — fornecimento"),  # sem tamanho
    (35, "ml", "m²", "Piso tátil direcional 40x40"),                            # metro → m²
    (20, "un", "m²", "Porcelanato 60x60 cm"),                                   # não é piso tátil
    (10, "un", "m²", "Piso tátil 2,50x2,50 m"),                                 # não é placa em cm
    (10, "un", "m²", "Piso tátil 400x400"),                                     # fora da faixa
    (10, "un", "ml", "Piso tátil 40x40"),                                       # un → ml
    (2.5, "un", "m²", "Piso tátil 40x40"),                                      # contagem quebrada
])
def test_CONTROLE_continua_em_branco(q, de, para, desc):
    qtd, nota = er.quantidade_apos_troca_de_unidade(q, de, para, descricao=desc)
    assert qtd == 0 and "EM BRANCO DE PROPÓSITO" in nota, (qtd, nota)


def test_CONTROLE_sem_descricao_e_como_antes():
    qtd, nota = er.quantidade_apos_troca_de_unidade(185, "un", "m²")
    assert qtd == 0 and "EM BRANCO DE PROPÓSITO" in nota


def test_CONTROLE_mesma_grandeza_passa_intacta():
    assert er.quantidade_apos_troca_de_unidade(185, "un", "pç", descricao="Piso tátil 40x40") == (185, "")


def test_os_dois_pontos_do_main_passam_a_descricao():
    arv = ast.parse(fonte("main.py"))
    chamadas = [n for n in ast.walk(arv) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") in ("_qtd_troca", "_qtd_troca2")]
    assert len(chamadas) == 2, len(chamadas)
    for c in chamadas:
        kw = {k.arg: getattr(k.value, "id", None) for k in c.keywords}
        assert kw.get("descricao") == "desc", ast.dump(c)
