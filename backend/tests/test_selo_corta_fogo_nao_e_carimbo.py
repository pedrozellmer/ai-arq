# -*- coding: utf-8 -*-
"""SELO corta-fogo é peça da obra, não o carimbo da prancha.

🩸 27/09/2026 — o layer 'PAT-DW-SELO CORTA-FOGO' (drywall de shaft) virou
"⚠ FONTE = CARIMBO DA PRANCHA" em 3 linhas de 3 envios do mesmo cliente, porque
"SELO" é também o nome do carimbo. Numa delas a chave do selo ainda pôs
"✓ MEDIDO" na frente: a linha dizia as duas coisas.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine_rules import layer_is_carimbo, prova_da_geometria  # noqa: E402


def test_selo_da_obra_nao_e_carimbo():
    for ly in ("PAT-DW-SELO CORTA-FOGO", "SELO CORTAFOGO", "A-SELO-ACUSTICO",
               "SELO_VEDACAO", "selo acústico"):
        assert not layer_is_carimbo(ly), ly


def test_CONTROLE_o_carimbo_continua_carimbo():
    for ly in ("SELO", "A-SELO", "SELO PRANCHA", "Fundo Logotipo", "CARIMBO-SELO",
               "Muldura", "MARGEM"):
        assert layer_is_carimbo(ly), ly


_IDX = {"area": [("Fundo Logotipo", 12.5), ("PAT-FORRO", 230.71),
                 ("PAT-DW-SELO CORTA-FOGO", 0.44)]}


def test_a_chave_nao_prova_numero_medido_no_carimbo():
    obs = "Fonte: área hachurada do layer 'Fundo Logotipo' = 12,5 m²."
    assert prova_da_geometria(12.5, "m²", obs, _IDX) == ""


def test_CONTROLE_a_chave_continua_provando_layer_da_obra():
    assert prova_da_geometria(230.71, "m²", "layer 'PAT-FORRO' = 230,71", _IDX)
    assert prova_da_geometria(0.44, "m²", "layer 'PAT-DW-SELO CORTA-FOGO' = 0,44", _IDX)
