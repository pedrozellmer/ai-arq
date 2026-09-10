# -*- coding: utf-8 -*-
"""A parede em diagonal DESCENDENTE não sai espelhada na coleta das salas.

🩸 10/09/2026 — A/B do leitor rápido contra a coleta de hoje, no corpus de teste:
todas as diferenças de segmento eram diagonais, e cada diagonal do leitor rápido
tinha a sua CAIXA no conjunto do pdfminer. A coleta das salas usava `x0,y0,x1,y1`
da linha do pdfplumber — a caixa (mínimos e máximos) — e toda diagonal que desce
virava a outra diagonal da mesma caixa. Isso bastou pra mudar as salas.

Estes guardas CHAMAM `_collect_raw_segments` e `detect_rooms` num PDF sintético.
"""
import math
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import pdfvec_rooms  # noqa: E402


def _pdf(tmp_path, conteudo, tamanho=(842, 595)):
    pikepdf = pytest.importorskip("pikepdf")
    p = tmp_path / "linhas.pdf"
    pdf = pikepdf.Pdf.new()
    pagina = pdf.add_blank_page(page_size=tamanho)
    pagina.Contents = pdf.make_stream(conteudo)
    pdf.save(str(p))
    return str(p)


def _segmentos(pdf):
    import pdfplumber
    with pdfplumber.open(pdf) as d:
        return pdfvec_rooms._collect_raw_segments(d.pages[0])


def _como_par(seg):
    """Segmento sem direção, arredondado: {(x, y), (x, y)}."""
    (ax, ay), (bx, by) = seg
    return frozenset({(round(ax, 1), round(ay, 1)), (round(bx, 1), round(by, 1))})


def test_a_diagonal_DESCENDENTE_sai_com_os_pontos_de_verdade(tmp_path):
    pdf = _pdf(tmp_path, b"1 w 50 250 m 150 50 l S")
    pares = {_como_par(s) for s in _segmentos(pdf)}
    assert frozenset({(50.0, 250.0), (150.0, 50.0)}) in pares, pares
    assert frozenset({(50.0, 50.0), (150.0, 250.0)}) not in pares, (
        "a diagonal saiu ESPELHADA — é a caixa da linha, não a linha")


def test_CONTROLE_diagonal_subindo_e_linhas_em_eixo_nao_mudam(tmp_path):
    pdf = _pdf(tmp_path, b"1 w 200 50 m 300 250 l S 100 400 m 500 400 l S 600 100 m 600 400 l S")
    pares = {_como_par(s) for s in _segmentos(pdf)}
    assert frozenset({(200.0, 50.0), (300.0, 250.0)}) in pares, pares
    assert frozenset({(100.0, 400.0), (500.0, 400.0)}) in pares, pares
    assert frozenset({(600.0, 100.0), (600.0, 400.0)}) in pares, pares


def test_a_sala_com_parede_inclinada_FECHA(tmp_path):
    """Trapézio com o lado esquerdo descendo de (100,300) a (200,100), cada lado
    uma linha separada (como o CAD exporta). Área = (300+200)/2 × 200 = 50.000 pt²,
    que a 1:100 dá ~62,2 m². Com a diagonal espelhada o contorno não fecha."""
    pdf = _pdf(tmp_path, b"1 w 100 300 m 400 300 l S 400 300 m 400 100 l S "
                         b"400 100 m 200 100 l S 200 100 m 100 300 l S")
    esperado = 50000 * (0.0254 / 72.0 * 100.0) ** 2
    salas = pdfvec_rooms.detect_rooms(pdf, 0, 100.0, None)
    areas = [r["area_m2"] for r in salas]
    assert any(math.isclose(a, esperado, rel_tol=0.02) for a in areas), (
        "a sala do trapézio (%.1f m²) não fechou: %r" % (esperado, areas))


def test_CONTROLE_linha_sem_pts_cai_na_caixa_como_antes():
    """Objeto de linha sem `pts` (versão antiga do pdfplumber) não pode quebrar
    a coleta: usa a caixa, como sempre fez."""
    class _Pagina:
        height = 300.0
        lines = [{"x0": 10.0, "y0": 20.0, "x1": 110.0, "y1": 20.0, "top": 280.0, "bottom": 280.0}]
        rects = []
        curves = []
    segs = pdfvec_rooms._collect_raw_segments(_Pagina())
    assert [_como_par(s) for s in segs] == [frozenset({(10.0, 20.0), (110.0, 20.0)})], segs
