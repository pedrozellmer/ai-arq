# -*- coding: utf-8 -*-
"""Folhas empilhadas no modelo não zeram a prancha.

🩸 30/09/2026 — H57 do estudo do acervo. Um prédio residencial com 7 folhas A1
EMPILHADAS no modelo, as molduras se tocando: a geometria virou UM bloco (a
coluna inteira, 42% da área, abaixo do teto de 60%), e 11 títulos — detalhes,
cortes, elevações — pegaram a MESMA caixa. Cada um tirava a coluna toda da
soma: 2.705 m → 0,19 m, com as plantas dentro.
"""
import os
import sys

import ezdxf

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402

_TITULOS = ["DETALHE 01 - MURO", "CORTE AA", "ELEVAÇÃO FRONTAL"]


def _modelo(colado=True):
    """3 folhas 100 × 50 empilhadas (x 0–100, y 0–150), cada uma com um desenho
    e o título embaixo; e a SITUAÇÃO solta ao lado (x 150–250)."""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    for k, tit in enumerate(_TITULOS):
        y = 50.0 * k
        for a, b in (((0, y), (100, y)), ((100, y), (100, y + 50)),
                     ((100, y + 50), (0, y + 50)), ((0, y + 50), (0, y))):
            msp.add_line(a, b)                                   # a moldura da folha
        x0, x1 = (0.0, 100.0) if colado else (20.0, 80.0)        # o desenho encosta na moldura?
        for a, b in (((x0, y + 20), (x1, y + 20)), ((x1, y + 20), (x1, y + 40)),
                     ((x1, y + 40), (x0, y + 40)), ((x0, y + 40), (x0, y + 20))):
            msp.add_line(a, b)
        msp.add_text(tit, dxfattribs={"height": 3, "insert": (30, y + 15)})
    for a, b in (((150, 100), (250, 100)), ((250, 100), (250, 140)),
                 ((250, 140), (150, 140)), ((150, 140), (150, 100))):
        msp.add_line(a, b)
    msp.add_text("SITUAÇÃO", dxfattribs={"height": 3, "insert": (160, 95)})
    return msp


def test_o_caso_a_mesma_caixa_pega_por_varios_titulos_nao_vale():
    regs = dx._desenhos_no_modelo(_modelo())
    assert [r["titulo"] for r in regs] == ["SITUAÇÃO"], regs


def test_CONTROLE_cada_desenho_com_a_sua_caixa_segue_valendo():
    # sem encostar na moldura, cada título acha o SEU desenho
    regs = dx._desenhos_no_modelo(_modelo(colado=False))
    tits = sorted(r["titulo"] for r in regs)
    assert tits == sorted(_TITULOS + ["SITUAÇÃO"]), regs
    assert len({r["caixa"] for r in regs}) == 4, regs
