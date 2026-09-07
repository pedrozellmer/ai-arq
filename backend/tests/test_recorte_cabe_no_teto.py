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
import base64
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


def _imagens_que_a_IA_recebeu(monkeypatch, crops, tipo=SheetType.LAYOUT_NOVO):
    """RODA `analyzer.analyze_sheet` e devolve os blocos de imagem que ele
    montou pra chamada da IA.

    🚨 06/09/2026 — o guarda que morava aqui lia `inspect.getsource` e conferia
    se a string "MAX_CROP_BYTES" aparecia no corpo. Isso prova redacao, nao
    comportamento: qualquer `continue` a mais, um `[:0]`, ou uma comparacao
    invertida deixavam o texto intacto e a IA recebia a prancha SEM desenho --
    calada, que e exatamente o modo de falha que este arquivo existe pra pegar.
    Agora a chamada da IA e espionada e o que se afirma sao os BYTES que
    chegaram.
    """
    from models import SheetInfo

    capturado = {}

    class _Bloco:
        text = '{"items": []}'

    class _Resp:
        content = [_Bloco()]
        stop_reason = "end_turn"

    def _espiao(client, **kw):
        capturado["content"] = kw["messages"][0]["content"]
        return _Resp()

    monkeypatch.setattr(analyzer, "call_with_retry_stream", _espiao)
    analyzer.analyze_sheet(None, SheetInfo(filename="prancha.pdf",
                                           sheet_type=tipo,
                                           text_content="",
                                           crops=list(crops)))
    assert "content" in capturado, (
        "analyze_sheet nem chegou a chamar a IA -- o guarda nao mediu nada")
    return [c for c in capturado["content"] if c.get("type") == "image"]


def _arquivo_de(caminho, tamanho):
    with open(caminho, "wb") as f:
        f.write(b"\xff\xd8" + b"J" * (tamanho - 2))
    assert os.path.getsize(caminho) == tamanho
    return caminho


def test_o_teto_e_o_MESMO_numero_que_o_analyzer_usa(prancha_densa, tmp_path,
                                                    monkeypatch):
    """Amarra os dois pela BORDA: um recorte com exatamente
    `MAX_CROP_BYTES` bytes tem que chegar na IA, e um com UM byte a mais tem
    que ser descartado. Trocar o teto por qualquer outro numero move a borda e
    reprova -- sem ler uma linha de fonte.

    🔑 E confere o CONTEUDO, nao a presenca: `len(imgs)` sozinho so provava que
    "um bloco de imagem foi anexado". O que interessa e se a imagem CHEGOU --
    `media_type` certo e os bytes do recorte, byte a byte.
    """
    teto = analyzer.MAX_CROP_BYTES

    saida = tmp_path / "crops"
    saida.mkdir()
    crops = render_crops(prancha_densa, SheetType.LAYOUT_NOVO, str(saida))
    assert crops, "nao renderizou nada"
    real = min(crops, key=os.path.getsize)          # recorte de VERDADE
    assert os.path.getsize(real) < teto

    no_limite = _arquivo_de(str(tmp_path / "no_limite.jpg"), teto)
    passou = _arquivo_de(str(tmp_path / "passou_um_byte.jpg"), teto + 1)

    imgs = _imagens_que_a_IA_recebeu(monkeypatch, [real, no_limite, passou])

    chegou = {}
    for b in imgs:
        assert b["source"]["type"] == "base64", b["source"].get("type")
        chegou[len(base64.b64decode(b["source"]["data"]))] = (
            b["source"]["media_type"], base64.b64decode(b["source"]["data"]))

    assert len(imgs) == 2, (
        "esperava 2 imagens (o recorte real e o que tem exatamente %d bytes) e "
        "vieram %d. Se veio 3, o teto parou de descartar e a memoria estoura; "
        "se veio menos, o analyzer esta jogando fora recorte que CABE e a IA "
        "recebe a prancha sem desenho." % (teto, len(imgs)))
    assert teto + 1 not in chegou, (
        "o recorte de %d bytes (UM acima do teto) passou -- o call site nao "
        "esta mais comparando com MAX_CROP_BYTES" % (teto + 1))

    # o de borda chegou INTEIRO e como JPEG
    assert teto in chegou, (
        "o recorte com exatamente %d bytes foi descartado: a comparacao virou "
        ">= em vez de >, ou o teto mudou de numero" % teto)
    media_borda, bytes_borda = chegou[teto]
    assert media_borda == "image/jpeg", media_borda
    assert bytes_borda == open(no_limite, "rb").read(), (
        "o recorte de borda chegou CORROMPIDO na chamada da IA")

    # e o recorte de verdade tambem, byte a byte
    n_real = os.path.getsize(real)
    assert n_real in chegou, (n_real, sorted(chegou))
    media_real, bytes_real = chegou[n_real]
    assert media_real == "image/jpeg", media_real
    assert bytes_real == open(real, "rb").read(), (
        "os bytes do recorte renderizado nao sao os que a IA recebeu -- "
        "'anexou um bloco de imagem' nao e o mesmo que 'a imagem chegou'")


def test_o_media_type_acompanha_a_extensao(tmp_path, monkeypatch):
    """🧪 Controle da OUTRA metade do ternario: `.png` nao pode ir carimbado
    como jpeg. Media_type errado faz a API recusar a imagem inteira -- e o
    fixture antigo so tinha `.jpg`."""
    png = _arquivo_de(str(tmp_path / "recorte.png"), 4096)
    imgs = _imagens_que_a_IA_recebeu(monkeypatch, [png])
    assert len(imgs) == 1, len(imgs)
    assert imgs[0]["source"]["media_type"] == "image/png", (
        "recorte .png foi anexado como %r" % imgs[0]["source"]["media_type"])
    assert base64.b64decode(imgs[0]["source"]["data"]) == open(png, "rb").read()
