# -*- coding: utf-8 -*-
"""O aviso "parece projeto ESTRUTURAL" reconhece o CÓDIGO "EST" da prancha.

🩸 25/09/2026 — job `e9b9a8a0` (incorporação): 4 DWG "…-AP-EST-LOCFUN-R01",
"…-EST-FORTER-…", "…-EST-FORSUP-…", "…-EST-FORCOB-…" enviados como
ARQUITETURA, e o aviso calado — a regra só via a palavra ("estrutural",
"fundação", "armação"…), e em prancha codificada a disciplina é o código.
Saíram 118 linhas, NENHUMA medida, os pilares em "Complementares".
📏 Medido no Storage: 27 projetos com "EST" maiúsculo entre separadores —
todos estrutura; 3 foram enviados como arquitetura (um deles reenviado
depois como estrutura). Nenhum falso positivo.

🪤 Este aviso tem histórico de disparo ERRADO ("SEM ESTRUTURAL", "cabeamento
ESTRUTURADO"). Por isso o código só vale MAIÚSCULO e entre separadores.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest  # noqa: E402
import main as _m  # noqa: E402


@pytest.mark.parametrize("nome", [
    "192501-OBRA-AP-EST-LOCFUN-R01.dwg",
    "LIB2-EST-LO-101-2SUB-R03.DXF",
    "A5-09801-DE-EST-FUN-001-R00.dwg",
    "0653-KZ-EST-PE-1052-ARM-TOR-VTE-R01.DXF",
    "OBRA EST P2-P7 (A1).pdf",
    "EST-CA-CLINICA-VT-VS.pdf",
    "RES_EST_61_FOR.DWG",
])
def test_o_codigo_EST_da_prancha_avisa(nome):
    assert _m._nome_parece_estrutural(nome), nome


@pytest.mark.parametrize("nome", [
    "BLOCO-LESTE.dwg",           # EST dentro de palavra
    "ZONA OESTE.pdf",
    "ESTUDO PRELIMINAR.pdf",     # começa com EST mas é outra palavra
    "PLANTA_ESTAR-R01.dwg",
    "REST-AREA.dwg",
    "casa-est-01.dwg",           # minúsculo: pode ser qualquer coisa
    "ARQ_SEM_EST_R01.pdf",       # a negação que já existia continua valendo
    "0653-ARQ-PE-001-R01.dwg",
])
def test_CONTROLE_o_que_nao_e_o_codigo_nao_avisa(nome):
    assert not _m._nome_parece_estrutural(nome), nome


def test_CONTROLE_a_palavra_continua_valendo_sozinha():
    assert _m._nome_parece_estrutural("PROJETO ESTRUTURAL - FUNDACOES.pdf")
