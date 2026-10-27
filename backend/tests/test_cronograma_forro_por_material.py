# -*- coding: utf-8 -*-
"""Forros: cada forro na taxa do material que o nome diz.

🩸 27/10/2026 — nos 27 cronogramas da base, a fase de Forros punha tudo na
taxa de forro de placas de gesso (1,437 Hh/m²): septo forro/laje, estrutura
metálica auxiliar (a área do forro contada de novo), pintura de forro e o
drywall, que é 1,091. 6.446 Hh → ~2.830.

🔑 Decisão do Pedro: forro "tipo a definir" SEGUE na taxa de placas, como era.
Frases reescritas a partir do acervo, sem nome de cliente.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from cronograma_produtividade import REFS_POR_FASE, _ref_do_item, esforco_por_fase  # noqa: E402
from cronograma import _mapear_fase  # noqa: E402


def _codigo(desc):
    r = _ref_do_item(REFS_POR_FASE["Forros"]["m2"], desc)
    return r[0] if r else None


@pytest.mark.parametrize("desc,codigo", [
    ("Forro de drywall (chapa de gesso acartonado ST — padrão) em pé-direito duplo", "96110"),
    ("Forro em gesso acartonado com massa corrida e pintura PVA cor branca", "96110"),
    ("Forro em gesso acartonado ou gesso liso em ambientes internos", "96110"),
    ("Forro em réguas de PVC branco — banheiros", "96111"),
    ("Forro em fibra mineral 625×625 — área de escritório", "104757"),
    ("Forro metálico em lambri de alumínio — varanda", "97557"),
    ("Forro de madeira pinus — área gourmet", "96112"),
    ("Forro em gesso — ambiente gourmet, conforme planta", "96109"),
    # 🔑 sem material dito: segue na de placas, como era (decisão do Pedro)
    ("Forro — tipo a confirmar com projeto executivo (gesso acartonado, PVC ou mineral)", "96109"),
    ("Forro da sala / cozinha — tipo a definir", "96109"),
])
def test_cada_forro_na_taxa_do_seu_material(desc, codigo):
    assert _codigo(desc) == codigo, (desc, _codigo(desc))


@pytest.mark.parametrize("desc", [
    "Septo forro/laje — execução de septo divisório entre forro e laje",
    "Estrutura auxiliar metálica (perfil de aço galvanizado) para sustentação do forro",
    "Pintura de forro — tinta látex PVA ou acrílica",
    "Pintura sobre forro de alumínio anodizado tipo lambri existente",
    "Forro de tela ondulada em arame galvanizado, cor natural",
    "Tabica metálica — acabamento do forro junto à parede",
    "Sanca de gesso — iluminação indireta",
])
def test_CONTROLE_o_que_nao_e_forro_sai_da_conta(desc):
    assert _codigo(desc) is None, (desc, _codigo(desc))


def test_septo_e_estrutura_nao_somam_por_cima_do_forro():
    """🩸 O forro, o septo e a estrutura DO MESMO forro eram 3 forros na conta."""
    itens = [{"discipline": "Forros", "description": "Forro de drywall — escritório", "unit": "m²", "quantity": 420},
             {"discipline": "Forros", "description": "Estrutura auxiliar metálica para o forro", "unit": "m²", "quantity": 420},
             {"discipline": "Forros", "description": "Septo forro/laje — divisório", "unit": "m²", "quantity": 100}]
    f = esforco_por_fase(itens, lambda d: (_mapear_fase(d) or [None])[0])["Forros"]
    assert f["qtd_total"] == 420, f
    assert "96110" in f["detalhe"] and "96109" not in f["detalhe"], f["detalhe"]
    # a TAXA do drywall, não só o código: 420 × 1,091 = 458,2 Hh
    assert f["esforco_hh"] == round(420 * 1.091, 1), f["esforco_hh"]
