# -*- coding: utf-8 -*-
"""A cota fica no MESMO espaço das paredes e salas — com a folha fora da origem.

📏 28/09/2026 (estudo de leitura, D7c). PDF de CAD com a folha centrada na
origem (a62f7ae3: MediaBox em −1417, −650): a posição da cota vinha do
pypdfium2 no espaço bruto; parede e sala vêm do pdfminer, que desconta a
origem e aplica a rotação. Nenhuma cota caía perto de parede nenhuma — 0
casamentos em qualquer escala, e a prova de escala nunca rodava.
"""
import os
import sys

import pdfplumber
import pikepdf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import pdfvec_cotas as pc  # noqa: E402
from pdfvec_rooms import _collect_raw_segments_rapido  # noqa: E402

DEN = 50.0
L_PT = 2.00 / (pc.PT_TO_M * DEN)         # parede de 2,00 m a 1:50


def _pdf(tmp_path, mediabox, rotate=0, ox=0.0, oy=0.0):
    """Uma parede horizontal e a cota "200" logo acima dela, desenhadas em
    (ox, oy) + posição fixa, no espaço bruto da página."""
    pdf = pikepdf.new()
    x0, y0 = ox + 100.0, oy + 100.0
    conteudo = (f"1 w {x0:.2f} {y0:.2f} m {x0 + L_PT:.2f} {y0:.2f} l S "
                f"BT /F1 8 Tf {x0 + L_PT / 2 - 6:.2f} {y0 + 6:.2f} Td (200) Tj ET")
    fonte = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                               BaseFont=pikepdf.Name.Helvetica)
    pag = pikepdf.Dictionary(
        Type=pikepdf.Name.Page, MediaBox=pikepdf.Array(mediabox),
        Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=fonte)),
        Contents=pdf.make_stream(conteudo.encode("latin-1")))
    if rotate:
        pag.Rotate = rotate
    pdf.pages.append(pikepdf.Page(pag))
    p = str(tmp_path / f"folha_{rotate}_{int(ox)}.pdf")
    pdf.save(p)
    return p


def _parede_e_cota(p):
    with pdfplumber.open(p) as doc:
        segs = _collect_raw_segments_rapido(doc.pages[0])
    (ax, ay), (bx, by) = max(segs, key=lambda s: abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1]))
    toks = pc.extract_cota_tokens(p, 0)
    assert len(toks) == 1, toks
    return ((ax + bx) / 2, (ay + by) / 2), toks[0]["center"], (ax, ay, bx, by)


@pytest.mark.parametrize("mediabox,rotate,ox,oy", [
    ([-1000, -500, 1000, 500], 0, -1000.0, -500.0),   # folha centrada na origem
    ([-1000, -500, 1000, 500], 90, -1000.0, -500.0),  # ...e girada
    ([0, 0, 2000, 1000], 0, 0.0, 0.0),                # CONTROLE: origem em (0, 0)
])
def test_a_cota_cai_junto_da_parede_que_ela_mede(tmp_path, mediabox, rotate, ox, oy):
    meio, cota, _ = _parede_e_cota(_pdf(tmp_path, mediabox, rotate, ox, oy))
    assert abs(cota[0] - meio[0]) + abs(cota[1] - meio[1]) < 20, (meio, cota)


def test_o_recorte_da_vista_segue_no_espaco_bruto(tmp_path):
    # a caixa da vista vem do /BBox da viewport, no espaço BRUTO da página: o
    # recorte acontece antes de a cota ir pro espaço da geometria
    p = _pdf(tmp_path, [-1000, -500, 1000, 500], 0, -1000.0, -500.0)
    vista_bruta = (-950.0, -450.0, -700.0, -350.0)      # envolve a parede e a cota
    assert len(pc.extract_cota_tokens(p, 0, vista_bruta)) == 1


def test_a_cota_da_folha_fora_da_origem_casa_com_a_parede(tmp_path):
    _, _, (ax, ay, bx, by) = _parede_e_cota(_pdf(tmp_path, [-1000, -500, 1000, 500], 0, -1000.0, -500.0))
    parede = {"kind": "parede", "length_m": 2.0, "axis": "h",
              "span_pt": (min(ax, bx), max(ax, bx)), "p_pt": ay}
    assert len(pc.match_cotas(pc.extract_cota_tokens(_pdf(tmp_path, [-1000, -500, 1000, 500], 0,
                                                          -1000.0, -500.0), 0), [parede])) == 1
