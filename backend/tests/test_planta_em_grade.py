# -*- coding: utf-8 -*-
"""PLANTA_EM_GRADE: o PDF vai pra IA como prancha inteira + grade 3x2.

📏 15/11/2026. Medido em duas pranchas A1 do acervo de teste (verdade no DXF),
mesmo modelo e mesmo prompt curto: com a planta inteira num recorte a leitura
acertou 18 de 26 e 21-22 de 24 ambientes (nome + area); em grade, 24 e 24. O
modelo gasta o mesmo punhado de tokens por imagem, entao a planta inteira num
recorte chega com o digito da etiqueta borrado.

🪤 A grade sozinha DUPLICA a etiqueta da emenda (40 linhas para 26 ambientes).
Com a prancha inteira na frente e a nota dizendo o que e cada imagem, voltou a
25-26. Por isso este arquivo guarda as duas coisas juntas: a visao geral e a
primeira imagem, e a nota vem antes dela.

🛑 Nasce desligada. Sem recorte de grade na prancha, o que vai pra IA e
exatamente o de antes -- e ha um teste so pra isso.

Tudo sintetico: PDF montado de bytes puros (sem PyMuPDF, que nao esta no
requirements) e nomes genericos.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import analyzer                                               # noqa: E402
import processor                                              # noqa: E402
from models import SheetInfo, SheetType                       # noqa: E402

_NL = chr(10)


def _pdf_a1(destino, larg=2384, alt=1684):
    """Uma A1 com uma malha de linhas -- o bastante pra ter o que renderizar."""
    ops = ["0.5 w"]
    for x in range(40, larg - 40, 60):
        ops.append("%d 40 m %d %d l S" % (x, x, alt - 40))
    for y in range(40, alt - 40, 60):
        ops.append("40 %d m %d %d l S" % (y, larg - 40, y))
    fluxo = _NL.join(ops).encode("latin-1")
    nl = _NL.encode()
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        ("<</Type/Page/Parent 2 0 R/MediaBox[0 0 %d %d]/Contents 4 0 R>>" % (larg, alt)).encode(),
        b"<</Length " + str(len(fluxo)).encode() + b">>" + nl + b"stream" + nl + fluxo + nl + b"endstream",
    ]
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
              + b"/Root 1 0 R>>" + nl + b"startxref" + nl + str(inicio).encode() + nl + b"%%EOF" + nl)
    with open(destino, "wb") as f:
        f.write(bytes(saida))
    return destino


@pytest.fixture
def grade(tmp_path):
    pdf = _pdf_a1(str(tmp_path / "prancha generica.pdf"))
    saida = tmp_path / "crops"
    saida.mkdir()
    return processor.render_grade(pdf, str(saida), out_stem="prancha_p1")


# ── o que `render_grade` entrega ────────────────────────────────────────────

def test_a_grade_tem_a_visao_geral_na_frente_e_seis_pedacos(grade):
    assert len(grade) == 1 + processor.GRADE_LINHAS * processor.GRADE_COLUNAS == 7
    assert os.path.basename(grade[0]) == "prancha_p1_grade_visao.jpg"
    assert [os.path.basename(c) for c in grade[1:]] == [
        "prancha_p1_grade_l%dc%d.jpg" % (lin, col) for lin in range(2) for col in range(3)]
    assert all(os.path.exists(c) for c in grade)


def test_cada_imagem_da_grade_cabe_no_teto_que_o_analyzer_descarta(grade):
    maior = max(os.path.getsize(c) for c in grade)
    assert maior <= analyzer.MAX_CROP_BYTES, (
        "imagem da grade com %d KB: o analyzer PULA o que passa do teto" % (maior // 1024))


def test_os_pedacos_repetem_uma_faixa_do_vizinho(grade):
    """Sem a faixa repetida, a etiqueta que cai na emenda sai cortada dos dois
    lados. O pedaco do MEIO repete dos dois lados, entao e mais largo que o da
    ponta -- e os dois sao mais largos que um terco seco da pagina."""
    from PIL import Image
    larg_pagina = int(2384 * 120 / 72)
    with Image.open(grade[1]) as ponta, Image.open(grade[2]) as meio:
        # os dois foram reduzidos ao mesmo teto de lado; compara a PROPORCAO
        prop_ponta = ponta.width / ponta.height
        prop_meio = meio.width / meio.height
    assert prop_meio > prop_ponta, "o pedaco do meio nao repete faixa dos dois lados"
    terco = larg_pagina / 3
    lado_ponta = larg_pagina * (1 / 3 + processor.GRADE_SOBREPOSICAO)
    assert lado_ponta > terco * 1.1, "a sobreposicao ficou pequena demais pra uma etiqueta"


def test_controle_positivo_sem_sobreposicao_os_pedacos_teriam_a_mesma_proporcao(tmp_path, monkeypatch):
    """Prova que o teste de cima reprova: com a faixa em zero, ponta e meio saem
    com a mesma proporcao."""
    from PIL import Image
    monkeypatch.setattr(processor, "GRADE_SOBREPOSICAO", 0.0)
    pdf = _pdf_a1(str(tmp_path / "p.pdf"))
    saida = tmp_path / "c"
    saida.mkdir()
    g = processor.render_grade(pdf, str(saida), out_stem="p")
    with Image.open(g[1]) as ponta, Image.open(g[2]) as meio:
        assert abs(ponta.width / ponta.height - meio.width / meio.height) < 0.01


def test_pdf_que_nao_abre_devolve_lista_vazia(tmp_path):
    ruim = tmp_path / "ruim.pdf"
    ruim.write_bytes(b"isto nao e um pdf")
    assert processor.render_grade(str(ruim), str(tmp_path)) == []


# ── quem e recorte de grade ─────────────────────────────────────────────────

@pytest.mark.parametrize("nome,esperado", [
    ("prancha_p1_grade_visao.jpg", True),
    ("prancha_p1_grade_l0c2.jpg", True),
    ("prancha_p1_planta.jpg", False),
    ("prancha_p1_legenda.jpg", False),
    # o nome do PDF pode trazer a palavra: quem decide e o SUFIXO
    ("estudo grade_visao revisado_planta.jpg", False),
    ("", False),
])
def test_recorte_de_grade_se_reconhece_pelo_sufixo(nome, esperado):
    assert processor.e_recorte_de_grade(nome) is esperado


# ── o que vai pra IA ────────────────────────────────────────────────────────

_DE_SEMPRE = ["x_legenda_fechamentos.jpg", "x_legenda_revestimentos.jpg", "x_legenda_portas.jpg",
              "x_legenda_divisorias.jpg", "x_planta_esquerda.jpg", "x_planta_centro.jpg"]


def test_DESLIGADA_sem_recorte_de_grade_a_lista_e_a_de_antes():
    antes = analyzer._crops_por_importancia(_DE_SEMPRE)[:analyzer.MAX_IMGS_POR_PRANCHA]
    assert analyzer._recortes_que_vao_pra_ia(_DE_SEMPRE) == antes
    assert len(antes) == 4 and antes[0] == "x_planta_esquerda.jpg"


def test_com_grade_vao_as_sete_e_so_elas_a_visao_geral_primeiro():
    grade_fora_de_ordem = ["x_grade_l0c0.jpg", "x_grade_l0c1.jpg", "x_grade_visao.jpg",
                           "x_grade_l0c2.jpg", "x_grade_l1c0.jpg", "x_grade_l1c1.jpg", "x_grade_l1c2.jpg"]
    vai = analyzer._recortes_que_vao_pra_ia(_DE_SEMPRE + grade_fora_de_ordem)
    assert len(vai) == 7 > analyzer.MAX_IMGS_POR_PRANCHA, "o teto de 4 cortaria a grade no meio"
    assert vai[0] == "x_grade_visao.jpg"
    assert vai[1:] == ["x_grade_l0c0.jpg", "x_grade_l0c1.jpg", "x_grade_l0c2.jpg",
                       "x_grade_l1c0.jpg", "x_grade_l1c1.jpg", "x_grade_l1c2.jpg"]
    assert not any("legenda" in c or "planta" in c for c in vai)


class _Bloco:
    type = "text"
    text = '{"items": []}'


class _Resp:
    stop_reason = "end_turn"
    content = [_Bloco()]


def _conteudo_que_iria_pra_ia(monkeypatch, crops):
    """Roda `analyze_sheet` com a chamada de IA trocada por um capturador e
    devolve o `content` da mensagem. Nada sai pra rede."""
    visto = {}

    def _captura(client, **kw):
        visto.update(kw)
        return _Resp()

    monkeypatch.setattr(analyzer, "call_with_retry_stream", _captura)
    sheet = SheetInfo(filename="prancha generica.pdf", sheet_type=SheetType.LAYOUT_NOVO,
                      text_content="", crops=list(crops))
    analyzer.analyze_sheet(object(), sheet, usa_cache=False)
    assert visto, "o capturador nao foi chamado: o teste nao mediu nada"
    return visto["messages"][0]["content"]


def test_a_nota_vem_antes_da_primeira_imagem_quando_ha_grade(grade, monkeypatch):
    content = _conteudo_que_iria_pra_ia(monkeypatch, grade)
    tipos = [c["type"] for c in content]
    assert tipos.count("image") == 7
    i_nota = next(i for i, c in enumerate(content)
                  if c["type"] == "text" and c["text"] == analyzer.NOTA_DA_GRADE)
    assert i_nota < tipos.index("image"), "a nota tem que ser lida ANTES das imagens"
    assert content[-1]["type"] == "text" and content[-1]["text"] != analyzer.NOTA_DA_GRADE


def test_DESLIGADA_sem_grade_a_nota_nao_aparece(tmp_path, monkeypatch):
    pdf = _pdf_a1(str(tmp_path / "p.pdf"))
    saida = tmp_path / "c"
    saida.mkdir()
    de_sempre = processor.render_crops(pdf, SheetType.LAYOUT_NOVO, str(saida))
    content = _conteudo_que_iria_pra_ia(monkeypatch, de_sempre)
    assert [c["type"] for c in content].count("image") == len(de_sempre) == 2
    assert not any(c["type"] == "text" and "SOBRE AS IMAGENS" in c["text"] for c in content)


def test_a_nota_nao_pede_item_so_explica_as_imagens():
    nota = analyzer.NOTA_DA_GRADE.lower()
    assert "primeira" in nota and "conte uma vez" in nota
    for proibida in ("item", "quantidade", "estime", "m²"):
        assert proibida not in nota, "a nota explica a imagem; o que extrair e do prompt do tipo"


# ── a chave ─────────────────────────────────────────────────────────────────

def test_a_avaliacao_pode_ligar_a_chave_e_o_padrao_e_zero(monkeypatch):
    import main
    assert "PLANTA_EM_GRADE" in main._CHAVES_AVALIAVEIS
    monkeypatch.delenv("PLANTA_EM_GRADE", raising=False)
    assert main._chave_do_job("job-qualquer", "PLANTA_EM_GRADE") == "0"
    assert main._chaves_pedidas("PLANTA_EM_GRADE=1") == {"PLANTA_EM_GRADE": "1"}
