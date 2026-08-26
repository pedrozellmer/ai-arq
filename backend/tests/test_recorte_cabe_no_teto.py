# -*- coding: utf-8 -*-
"""A resolucao do recorte e o teto que o analyzer DESCARTA sao um par.

🚨 26/08/2026. Duas constantes moravam longe uma da outra e ninguem sabia que
estavam ligadas:

  processor.render_crops(max_side=...)  -> quao grande o JPEG sai
  analyzer: `if file_size > 500_000`    -> acima disso o crop e PULADO

Pular o crop nao da erro: a IA simplesmente recebe a prancha SEM imagem e
ninguem fica sabendo. Subir a resolucao sem olhar o teto deixa o produto PIOR
que antes, em silencio.

Medido em 8 pranchas reais (A0 e A1) antes de subir o padrao de 1000 pra 1600:

    1600px -> pior recorte 362 KB  (28% de folga)   <- escolhido
    1800px -> pior recorte 441 KB  (12% de folga)
    2000px -> pior recorte 565 KB  ESTOURA o teto

Por que 1600 e nao mais: os tokens de imagem TRAVAM em 1.560 de 1400 px pra
cima (teto do proprio modelo), entao acima disso nao se ganha leitura, so
bytes. E o ganho de leitura medido foi grande: numa A1, a IA acerta 4 de 22
ambientes (nome+area) a 1000px e 13 de 22 a 1600px, com o pico de RAM subindo
so de 161 pra 171 MB.

🪤 Este guarda RODA a renderizacao. Ler o fonte nao pegaria o caso: o problema
nao e o numero escrito, e o BYTE que sai.

🪤 E a 1a versao dele usava PyMuPDF pra montar o PDF de teste. Fitz NAO esta no
requirements: no CI o arquivo inteiro morria no import, sumia da colheita, e o
guarda "todo arquivo de teste realmente EXECUTA" derrubou a bancada -- com
razao. Teste que so roda na minha maquina nao guarda nada. Agora o PDF sai de
bytes puros (stdlib), entao roda em qualquer lugar.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import analyzer                                     # noqa: E402
from processor import render_crops, SheetType       # noqa: E402

_NL = chr(10)


def _pdf_denso(destino, larg=2384, alt=1684, passo=7):
    """Uma A1 cheia de linha fina e texto miudo -- o pior caso pro JPEG."""
    ops = ["0.3 w"]
    x = 40
    while x < larg - 40:
        ops.append("%d 40 m %d %d l S" % (x, x, alt - 40))
        x += passo
    y = 40
    while y < alt - 40:
        ops.append("40 %d m %d %d l S" % (y, larg - 40, y))
        y += passo * 3
    ops.append("BT /F1 5 Tf")
    y = 60
    while y < alt - 60:
        ops.append("1 0 0 1 60 %d Tm (sala 12.3m2 PD=255cm  ) Tj" % y)
        y += 40
    ops.append("ET")
    fluxo = _NL.join(ops).encode("latin-1")

    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        ("<</Type/Page/Parent 2 0 R/MediaBox[0 0 %d %d]"
         "/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>" % (larg, alt)).encode(),
        b"",   # o objeto 4 e montado logo abaixo (precisa do fluxo pronto)
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    nl = _NL.encode()
    objs[3] = (b"<</Length " + str(len(fluxo)).encode() + b">>" + nl
               + b"stream" + nl + fluxo + nl + b"endstream")

    saida = bytearray(b"%PDF-1.4" + nl)
    posicoes = []
    for i, corpo in enumerate(objs, start=1):
        posicoes.append(len(saida))
        saida += str(i).encode() + b" 0 obj" + nl + corpo + nl + b"endobj" + nl
    inicio = len(saida)
    saida += b"xref" + nl + b"0 " + str(len(objs) + 1).encode() + nl
    saida += b"0000000000 65535 f " + nl
    for p in posicoes:
        saida += (b"%010d 00000 n " % p) + nl
    saida += (b"trailer" + nl + b"<</Size " + str(len(objs) + 1).encode()
              + b"/Root 1 0 R>>" + nl + b"startxref" + nl
              + str(inicio).encode() + nl + b"%%EOF" + nl)
    open(destino, "wb").write(bytes(saida))
    return destino


@pytest.fixture
def prancha_densa(tmp_path):
    return _pdf_denso(str(tmp_path / "densa.pdf"))


def test_o_padrao_da_resolucao_e_o_que_foi_medido():
    import inspect
    padrao = inspect.signature(render_crops).parameters["max_side"].default
    assert padrao == 1600, (
        "max_side saiu de 1600 pra %r. Se foi de proposito, REMEDIR o JPEG "
        "contra analyzer.MAX_CROP_BYTES antes -- a 2000px o recorte estoura o "
        "teto e o crop e descartado calado." % padrao)


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

    Refaz o que o codigo fazia ANTES: renderiza no mesmo tamanho e salva direto
    em qualidade 80, sem o laco que encolhe ate caber. Se isso NAO estourar o
    teto, a prancha de teste e facil demais e o teste de cima nao mede nada.
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

    🪤 Guarda que so olha a constante nao veria o CALL SITE -- e o call site e
    onde o crop e descartado. Por isso olha o corpo da funcao, com os
    comentarios removidos (comentario ja me enganou 3 vezes num dia so).
    """
    import inspect
    linhas = [l for l in inspect.getsource(analyzer.analyze_sheet).split(_NL)
              if not l.strip().startswith("#")]
    corpo = _NL.join(linhas)
    assert "MAX_CROP_BYTES" in corpo, (
        "o analyzer voltou a comparar com um numero solto em vez da constante")
    assert "500_000" not in corpo and "500000" not in corpo, (
        "sobrou numero magico no lugar da constante")
