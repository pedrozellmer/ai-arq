# -*- coding: utf-8 -*-
"""Parede se reconhece pela CABEÇA do nome, não pela palavra em qualquer lugar.

🩸 24/09/2026 — job `0a999117`, projeto de GÁS de um prédio: a linha
"Tubulação de gás natural embutida em tubo MMC — … inclui suportes, fixações,
conexões e recomposição de ALVENARIA/reboco" (1.088,34 m) entrou como parede, e
`_derive_pintura_pe_direito` escreveu "Pintura látex sobre paredes internas —
6.530 m²" num projeto sem parede nenhuma. Foi a 1ª linha PD.1 da base inteira.
A mesma palavra pôs "📐 ÁREA COM O PÉ-DIREITO … 3.265 m² por face" no TUBO.

📊 Medido antes do conserto (120 dias, m/ml, qtd>0): palavra de parede só na
cauda = 36 linhas em 25 projetos, nenhuma parede interna (eletroduto até
2.200 m, rodapé, demolição, rufo, corrimão, "geometria de linhas" 3.852 m).
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402
from engine_rules import e_parede_pelo_nome  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

TUBO = ("Tubulação de gás natural embutida em tubo MMC (Multicamada Metálico "
        "Composto) — conforme indicação de layer ARQ-GÁS-EMBUTIDO — inclui "
        "suportes, fixações, conexões e recomposição de alvenaria/reboco")


def _it(desc, unit="m", q=100.0, obs=""):
    return BudgetItem(item_num="1", description=desc, unit=unit, quantity=q,
                      observations=obs, ref_sheet="p.dxf",
                      confidence=Confidence("estimado"), discipline="Arquitetura")


# Paredes de verdade, com o texto que a leitura escreve (tirados da base).
@pytest.mark.parametrize("desc", [
    "Alvenaria de vedação — bloco cerâmico ou de concreto — paredes internas",
    "Parede drywall tipo DRY 01 — espessura total 82,5 mm, montante 70 mm",
    "Comprimento total de paredes drywall — layer A-WALL (referência)",
    "Execução de paredes — alvenaria ou drywall conforme projeto",
    "Instalação de divisórias em gesso acartonado",
    "Divisória/parede interna — alvenaria de bloco cerâmico ou drywall",
    "Fechamento vertical / parede em cobertura — alvenaria ou drywall",
    "Meia parede de alvenaria — bloco cerâmico, altura parcial",
    "Meia-parede — alvenaria ou concreto — conforme projeto",
    "Mureta em alvenaria — conforme detalhamento, com reboco nas duas faces",
    "Muro de divisa/arrimo em alvenaria de tijolo cerâmico rebocado",
    "Divisórias internas / tabiques — execução de paredes internas",
    "Alvenaria/muros — execução de paredes externas e muros de divisa",
])
def test_parede_de_verdade_e_parede(desc):
    assert e_parede_pelo_nome(desc)


# A palavra está lá, a parede não.
@pytest.mark.parametrize("desc", [
    TUBO,
    "Demolição de alvenaria existente",
    "Demolição de paredes e/ou divisórias — conforme marcação em planta",
    "Eletroduto de PVC rígido embutido no piso ou parede, para lógica",
    "Eletroduto flexível corrugado Ø 1\" (25 mm) — embutido em laje/parede",
    "Fornecimento e instalação de eletroduto PVC Ø1\" — embutido em parede",
    "Perfis de drywall — montantes/guias",
    "Sanca em drywall (gesso acartonado) com perfilado metálico",
    "Soco de concreto/alvenaria H=0,10m — soco perimetral",
    "Rodapé — instalação em todo o perímetro de paredes internas",
    "Geometria de linhas de plantas arquitetônicas — contornos, paredes",
    "Muro de arrimo em concreto armado — desenvolvimento linear",
    "Mureta em concreto — delimitação de áreas externas",
    "Vedação de juntas com silicone — encontro com parede",
    "Rufo metálico galvanizado — vedação entre telha e platibanda/parede",
])
def test_CONTROLE_a_palavra_na_cauda_nao_faz_parede(desc):
    assert not e_parede_pelo_nome(desc)


def test_o_tubo_de_gas_nao_vira_pintura():
    itens = [_it(TUBO, q=1088.34)]
    n = main._derive_pintura_pe_direito(itens, 3.0, area_conhecida=720.0)
    assert n == 0, "o tubo de gás virou pintura de parede"
    assert not any("Pintura" in i.description for i in itens)
    assert main._derive_pintura_pe_direito.ultimo_motivo == "sem comprimento de parede"


def test_CONTROLE_parede_de_verdade_ainda_vira_pintura():
    itens = [_it(TUBO, q=1088.34),
             _it("Alvenaria de vedação — bloco cerâmico — paredes internas", q=100.0)]
    assert main._derive_pintura_pe_direito(itens, 3.0, area_conhecida=720.0) == 1
    pint = [i for i in itens if i.description.startswith("Pintura látex")]
    assert len(pint) == 1 and pint[0].quantity == 600.0, "só os 100 m de alvenaria contam"


def test_o_tubo_de_gas_nao_ganha_area_de_parede():
    tubo = _it(TUBO, q=1088.34, obs="✓ MEDIDO — layer ARQ-GÁS-EMBUTIDO = 1088,34")
    assert main._anotar_area_parede_pe_direito([tubo], 3.0) == 0
    assert "ÁREA COM O PÉ-DIREITO" not in tubo.observations


def test_CONTROLE_parede_ganha_area():
    par = _it("Parede de alvenaria — espessura a confirmar", q=50.0)
    assert main._anotar_area_parede_pe_direito([par], 3.0) == 1
    assert par.observations.startswith("📐 ÁREA COM O PÉ-DIREITO")


def test_a_previsao_de_reposicao_usa_a_mesma_regua():
    """`_derivacao_vai_repor` precisa concordar com a derivação: se disser que
    repõe e a derivação não repõe, a linha de pintura some."""
    so_tubo = [_it(TUBO, q=1088.34)]
    assert not main._derivacao_vai_repor(so_tubo, "Pintura látex em paredes", 3.0)
    com_parede = so_tubo + [_it("Alvenaria de vedação — paredes internas", q=80.0)]
    assert main._derivacao_vai_repor(com_parede, "Pintura látex em paredes", 3.0)
