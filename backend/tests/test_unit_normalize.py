# -*- coding: utf-8 -*-
"""Regressão de _normalize_unit_for_item.

A unidade é decidida pela IDENTIDADE do item (o NOME), não pelo contexto entre
parênteses. Caso Roberta (23/07/2026): uma TV numa "planta de forro" virava m²
porque a palavra "forro" aparecia na descrição (era localização, não o tipo).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import _normalize_unit_for_item as norm  # noqa: E402


def test_tv_em_planta_de_forro_nao_vira_m2():
    # "forro" está no CONTEXTO (parênteses) = localização, não o tipo do item.
    assert norm('MONITOR/TV 42" (televisores fixados no teto - visíveis na '
                'planta de forro)', "un") == ("un", False)


def test_tv_marcada_m2_corrige_para_un():
    assert norm('MONITOR/TV 42"', "m²") == ("un", True)
    assert norm("Televisores LED", "m²") == ("un", True)
    assert norm("Monitor de vídeo", "m²") == ("un", True)


def test_forro_e_piso_de_verdade_seguem_m2():
    assert norm("FORRO DE GESSO ACARTONADO COM PINTURA", "un") == ("m²", True)
    assert norm("PISO VINÍLICO EM MANTA", "ml") == ("m²", True)


def test_linear_segue_ml():
    assert norm("RODAPÉ DE MADEIRA", "un") == ("ml", True)


def test_contexto_entre_parenteses_nao_forca_unidade():
    # "piso" no contexto NÃO deve forçar m² numa bancada.
    assert norm("BANCADA DE GRANITO (assentada sobre o piso)", "un") == ("un", False)


def test_contavel_classico_intacto():
    assert norm("Luminária de embutir", "m²") == ("un", True)
    assert norm("Porta de madeira", "m²") == ("un", True)


if __name__ == "__main__":
    _fails = 0
    for _n, _fn in list(globals().items()):
        if _n.startswith("test_") and callable(_fn):
            try:
                _fn()
                print("OK", _n)
            except AssertionError as e:
                _fails += 1
                print("FALHOU", _n, e)
    print("todos passaram" if not _fails else f"{_fails} falharam")
    sys.exit(1 if _fails else 0)
