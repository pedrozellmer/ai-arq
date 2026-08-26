# -*- coding: utf-8 -*-
"""A resolucao do recorte e o teto que o analyzer DESCARTA sao um par.

🚨 26/08/2026. Duas constantes moravam longe uma da outra e ninguem sabia
que estavam ligadas:

  processor.render_crops(max_side=...)   -> quao grande o JPEG sai
  analyzer: `if file_size > 500_000`     -> acima disso o crop e PULADO

Pular o crop nao da erro: a IA simplesmente recebe a prancha SEM imagem e
ninguem fica sabendo. Ou seja, subir a resolucao sem olhar o teto deixa o
produto PIOR que antes, em silencio.

Medido em 8 pranchas reais (A0 e A1) antes de subir o padrao de 1000 pra 1600:

    1600px -> pior recorte 362 KB  (28% de folga)   <- escolhido
    1800px -> pior recorte 441 KB  (12% de folga)
    2000px -> pior recorte 565 KB  ESTOURA o teto

Por que 1600 e nao mais: os tokens de imagem TRAVAM em 1.560 de 1400 pra cima
(teto do proprio modelo), entao acima disso nao se ganha leitura -- so bytes.
E o ganho de leitura medido foi grande: numa A1, a IA acerta 4 de 22 ambientes
(nome+area) a 1000px e 13 de 22 a 1600px, com o pico de RAM subindo so de
161 pra 171 MB.

🩤 Este guarda RODA a renderizacao num PDF gerado na hora, dificil de
proposito (muito vetor fino, que e o que faz JPEG crescer). Ler o fonte nao
pegaria o caso: o problema nao e o numero escrito, e o BYTE que sai.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import analyzer                                     # noqa: E402
from processor import render_crops, SheetType       # noqa: E402

fitz = pytest.importorskip("fitz")


@pytest.fixture
def prancha_densa(tmp_path):
    """Uma A1 cheia de linha fina e texto miudo -- o pior caso pro JPEG."""
    doc = fitz.open()
    pg = doc.new_page(width=2384, height=1684)          # A1 em pontos
    for x in range(40, 2340, 7):                        # hachura fina
        pg.draw_line(fitz.Point(x, 40), fitz.Point(x, 1640), width=0.3)
    for y in range(40, 1640, 23):
        pg.draw_line(fitz.Point(40, y), fitz.Point(2340, y), width=0.3)
    for y in range(60, 1600, 40):                       # texto miudo
        pg.insert_text(fitz.Point(60, y), "sala 12.3m2 PD=255cm " * 6, fontsize=5)
    p = str(tmp_path / "densa.pdf")
    doc.save(p)
    doc.close()
    return p


def test_o_padrao_da_resolucao_e_o_que_foi_medido():
    import inspect
    padrao = inspect.signature(render_crops).parameters["max_side"].default
    assert padrao == 1600, (
        "max_side saiu de 1600 pra %r. Se foi de proposito, REMEDIR o JPEG "
        "contra analyzer.MAX_CROP_BYTES antes -- a 2000px o recorte estoura "
        "o teto e o crop e descartado calado." % padrao)


def test_recorte_no_padrao_cabe_no_teto_do_analyzer(prancha_densa, tmp_path):
    """O que importa nao e o numero da constante: e o byte que sai."""
    saida = tmp_path / "crops"
    saida.mkdir()
    crops = render_crops(prancha_densa, SheetType.LAYOUT_NOVO, str(saida))
    assert crops, "nao renderizou nada"
    maior = max(os.path.getsize(c) for c in crops)
    assert maior <= analyzer.MAX_CROP_BYTES, (
        "recorte de %d KB passa do teto de %d KB: o analyzer vai PULAR a imagem "
        "e a IA recebe a prancha sem desenho nenhum."
        % (maior // 1024, analyzer.MAX_CROP_BYTES // 1024))


def test_controle_positivo_SEM_o_encolhimento_estouraria(prancha_densa, tmp_path):
    """Prova que o guarda de cima nao passa verde de graca.

    Refaz o que o codigo fazia ANTES: renderiza no mesmo tamanho e salva
    direto em qualidade 80, sem o laco que encolhe ate caber. Se isso NAO
    estourar o teto, entao a prancha de teste e facil demais e o teste de
    cima nao esta medindo nada.
    """
    import pypdfium2 as pdfium
    from PIL import Image

    pdf = pdfium.PdfDocument(prancha_densa)
    img = pdf[0].render(scale=120 / 72).to_pil()
    w, h = img.size
    crop = img.crop((int(w * 0.02), int(h * 0.02), int(w * 0.58), int(h * 0.95)))
    lado = max(crop.size)
    if lado > 1600:
        r = 1600 / lado
        crop = crop.resize((int(crop.width * r), int(crop.height * r)), Image.LANCZOS)
    velho = str(tmp_path / "sem_encolher.jpg")
    crop.save(velho, "JPEG", quality=80)      # <- o comportamento antigo, cru
    pdf.close()

    assert os.path.getsize(velho) > analyzer.MAX_CROP_BYTES, (
        "controle positivo furado: nem sem o encolhimento a prancha de teste "
        "passa do teto (%d KB) -- o guarda de cima passaria verde com qualquer "
        "coisa." % (os.path.getsize(velho) // 1024))


def test_o_teto_e_o_MESMO_numero_que_o_analyzer_usa():
    """Amarra os dois: se alguem trocar o 500_000 solto, isto acusa.

    🩤 Guarda que so olha a constante nao veria o CALL SITE -- e o call
    site e onde o crop e descartado. Por isso olha o corpo da funcao, com os
    comentarios removidos (comentario ja me enganou 3 vezes num dia so).
    """
    import inspect
    linhas = [l for l in inspect.getsource(analyzer.analyze_sheet).split(chr(10))
              if not l.strip().startswith("#")]
    corpo = chr(10).join(linhas)
    assert "MAX_CROP_BYTES" in corpo, (
        "o analyzer voltou a comparar com um numero solto em vez da constante")
    assert "500_000" not in corpo and "500000" not in corpo, (
        "sobrou numero magico no lugar da constante")
