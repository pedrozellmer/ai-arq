# -*- coding: utf-8 -*-
"""'Planta repetida' com poucas peças num arquivo cheio de peças é FALSA.

🩸 01/10/2026 — H78 do estudo do acervo. Família do Revit, legenda e pilha de
fixação davam "planta repetida": a IA escrevia "o valor real pode ser ~metade"
em arruela/porca/parafuso que são peças iguais lado a lado. Medido nas 8
conhecidas: a cópia verdadeira põe ≥ 4,6 % das inserções do arquivo em cópia;
as falsas, ≤ 2,0 %.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

from dwg_extractor import BlockCount, copias_em_sombra  # noqa: E402
from test_copias_da_planta_em_sombra import _blocos  # noqa: E402


def _soltas(n):
    """`n` peças avulsas (um nome por peça, espalhadas): o resto do arquivo."""
    return [BlockCount(name="PECA-%d" % i, count=1, layer="0",
                       positions=[(200.0 + (i % 50) * 3.0, 200.0 + (i // 50) * 3.0)])
            for i in range(n)]


def test_o_caso_poucas_pecas_em_copia_num_arquivo_cheio():
    """16 peças em cópia num arquivo de 2.032 inserções (0,8 %): falsa."""
    assert copias_em_sombra(_blocos([(0, 0), (0, -60)]) + _soltas(2000), 1.0) == {}


def test_CONTROLE_a_mesma_copia_num_arquivo_pequeno_fica():
    """As mesmas 16 peças em 332 inserções (4,8 %): é cópia de planta."""
    c = copias_em_sombra(_blocos([(0, 0), (0, -60)]) + _soltas(300), 1.0)
    assert c and c["pecas"] == 16, c


def test_CONTROLE_sem_o_resto_do_arquivo_igual_a_antes():
    c = copias_em_sombra(_blocos([(0, 0), (0, -60)]), 1.0)
    assert c and c["pecas"] == 16, c
