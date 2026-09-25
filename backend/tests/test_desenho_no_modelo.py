# -*- coding: utf-8 -*-
"""Folha inteira desenhada no MODELO: os desenhos se acham pelo título.

🩸 25/09/2026 — job `53f0483f` (elétrica industrial, 3 DWG). Cada arquivo era
uma folha A1 INTEIRA no modelspace — moldura, carimbo, planta, cortes e
detalhes lado a lado — e UMA janela mostrando tudo. Sem janela por desenho, a
leitura por folha só achava o título do carimbo e dizia "nenhum desenho com
título". O DETALHE típico entrou na soma como percurso: 99,5 m de "eletroduto"
e os leitos dos níveis 3 e 4, tudo "✓ MEDIDO". E os títulos vinham
`%%UDETALHE "D"` — o código de sublinhado do AutoCAD na frente.

Regras que os guardas prendem:
- título = começa pelo tipo + letra GRANDE (a bolha "DETALHE D" da planta não é);
- o desenho é o bloco de geometria logo ACIMA do título; moldura não conta;
- 'fora' sai da soma; do corte ('vista') sai o COMPRIMENTO (25/09 — a decisão
  de 24/09 de deixar o corte na soma caiu neste mesmo caso: o leito visto de
  lado somava ~1,4 km); o peso da vista continua indo pro log;
- 'planta' só protege: bloco que é de detalhe E de planta fica com peso 1;
- só entra quando nenhuma janela disse o que mostra; sem janela, nada muda.
Medido: acervo local (27 DXF) sem nenhuma mudança; só o caso de origem muda.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import parece_titulo_de_desenho, tipo_do_desenho  # noqa: E402

GRANDE, PEQUENA = 0.175, 0.10


def _texto(msp, t, x, y, h=GRANDE):
    msp.add_text(t, dxfattribs={"height": h, "insert": (x, y)})


def _folha(tmp_path, titulo_detalhe='%%UDETALHE "D"', titulo_planta="PORÃO DE CABOS - PLANTA",
           janela=True, titulo_na_janela=None, grudado=False, moldura_picotada=False,
           cola_tudo=False, linha_longa=False):
    """Folha A1 de 42 × 29,7 m no modelo (metros): planta em cima (15 m de
    tubo), detalhe embaixo (8 m de tubo), bolha pequena "DETALHE D" dentro da
    planta, e UMA janela mostrando a folha inteira."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    # moldura (atravessa a folha: não pode colar os desenhos)
    cantos = [(0, 0), (42, 0), (42, 29.7), (0, 29.7), (0, 0)]
    if moldura_picotada:
        for (ax, ay), (bx, by) in zip(cantos, cantos[1:]):
            n = int(max(abs(bx - ax), abs(by - ay)))
            for k in range(n):
                msp.add_line((ax + (bx - ax) * k / n, ay + (by - ay) * k / n),
                             (ax + (bx - ax) * (k + 1) / n, ay + (by - ay) * (k + 1) / n),
                             dxfattribs={"layer": "MOLDURA"})
    else:
        for a, b in zip(cantos, cantos[1:]):
            msp.add_line(a, b, dxfattribs={"layer": "MOLDURA"})
    # PLANTA: contorno + 15 m de tubo; título embaixo
    for a, b in [((4, 19), (22, 19)), ((22, 19), (22, 27)), ((22, 27), (4, 27)), ((4, 27), (4, 19))]:
        msp.add_line(a, b, dxfattribs={"layer": "CONTORNO"})
    msp.add_line((5, 22), (20, 22), dxfattribs={"layer": "TUBO"})
    if titulo_planta:
        _texto(msp, titulo_planta, 12, 18)
    # bolha de chamada, letra pequena, logo ABAIXO do tubo da planta — se ela
    # valesse como título, o tubo seria "o desenho acima dela"
    _texto(msp, "DETALHE D", 15, 20.5, PEQUENA)
    # DETALHE: moldura própria + 8 m de tubo; título embaixo
    for a, b in [((4, 6), (12, 6)), ((12, 6), (12, 12)), ((12, 12), (4, 12)), ((4, 12), (4, 6))]:
        msp.add_line(a, b, dxfattribs={"layer": "CONTORNO"})
    msp.add_line((5, 8), (11, 8), dxfattribs={"layer": "TUBO"})
    msp.add_line((5, 8), (5, 10), dxfattribs={"layer": "TUBO"})
    if titulo_detalhe:
        _texto(msp, titulo_detalhe, 8, 5)
    if grudado:                                          # detalhe emendado na planta
        msp.add_line((4, 12), (4, 19), dxfattribs={"layer": "CONTORNO"})
    if linha_longa:                                      # margem que atravessa a folha rente aos dois
        msp.add_line((4.3, 0), (4.3, 29.7), dxfattribs={"layer": "MARGEM"})
    if cola_tudo:                                        # malha de traços curtos na folha toda
        for y in (1.0, 3.5, 6.0, 9.0, 12.0, 15.0, 18.0, 21.0, 24.0, 27.0, 29.0):
            for x in range(1, 41):
                msp.add_line((x, y), (x + 1, y), dxfattribs={"layer": "MALHA"})
        for x in (1.0, 13.0, 25.0, 37.0, 41.0):
            for y in range(1, 29):
                msp.add_line((x, y), (x, y + 1), dxfattribs={"layer": "MALHA"})
    # CARIMBO com o atributo TITULO da folha, como no arquivo real: diz o
    # assunto ("DISTRIBUIÇÃO DE FORÇA…"), não o que cada desenho é
    b = doc.blocks.new("CARIMBO")
    b.add_attdef("TITULO", (0, 0), dxfattribs={"height": 0.3})
    msp.add_blockref("CARIMBO", (36, 2)).add_attrib(
        "TITULO", titulo_na_janela or "DISTRIBUIÇÃO DE FORÇA, CONTROLE E REDE", (36, 2))
    if janela:
        lay = doc.layouts.new("FOLHA")
        vp = lay.add_viewport(center=(420, 297), size=(840, 594),
                              view_center_point=(21, 14.85), view_height=29.7)
        vp.dxf.view_target_point = (0, 0, 0)
    p = str(tmp_path / "folha.dxf")
    doc.saveas(p)
    return p


def _tubo(tmp_path, monkeypatch, liga=True, **kw):
    if liga:
        monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    else:
        monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    ex = dx.extract_dxf(_folha(tmp_path, **kw))
    return ex.get_walls_by_layer().get("TUBO"), ex


# ── o caso ─────────────────────────────────────────────────────────────────────
def test_o_detalhe_desenhado_no_modelo_sai_da_soma(tmp_path, monkeypatch):
    tubo, ex = _tubo(tmp_path, monkeypatch)
    assert tubo == pytest.approx(15.0), "só a planta; os 8 m do detalhe não são percurso"
    assert ex.folhas.get("origem") == "modelo"
    assert {"titulo": 'DETALHE "D"', "tipo": "fora"}.items() <= next(
        d for d in ex.folhas["desenhos_lista"] if d["tipo"] == "fora").items()


def test_CONTROLE_a_chave_desliga_e_volta_como_era(tmp_path, monkeypatch):
    tubo, _ = _tubo(tmp_path, monkeypatch, liga=False)
    assert tubo == pytest.approx(23.0)


def test_a_ia_fica_sabendo_que_o_detalhe_ja_saiu(tmp_path, monkeypatch):
    _, ex = _tubo(tmp_path, monkeypatch)
    txt = ex.to_structured_prompt()
    assert 'DETALHE "D"' in txt and "FORA das medidas" in txt


# ── o que NÃO pode acontecer ──────────────────────────────────────────────────
def test_CONTROLE_bolha_de_chamada_na_planta_nao_vira_titulo(tmp_path, monkeypatch):
    """Sem o título grande do detalhe, sobra a bolha 'DETALHE D' (letra pequena)
    DENTRO da planta. Se ela valesse, a planta inteira sairia da soma."""
    tubo, ex = _tubo(tmp_path, monkeypatch, titulo_detalhe=None, titulo_planta="PORÃO DE CABOS")
    assert tubo == pytest.approx(23.0)
    assert ex.folhas.get("origem") != "modelo"


def test_detalhe_emendado_na_planta_nao_apaga_a_planta(tmp_path, monkeypatch):
    """Uma linha emenda o detalhe na planta: a caixa do detalhe estica por cima
    da planta. Cruzou a caixa da planta → o detalhe não vale; fica como era."""
    tubo, _ = _tubo(tmp_path, monkeypatch, grudado=True)
    assert tubo == pytest.approx(23.0), "na dúvida fica como era — nunca some a planta"


def test_bloco_que_e_a_folha_inteira_nao_e_um_desenho(tmp_path, monkeypatch):
    """Uma malha de traços curtos cola tudo num bloco só; 'o desenho' seria a
    folha toda — recusado, mesmo sem título de planta pra proteger."""
    tubo, _ = _tubo(tmp_path, monkeypatch, cola_tudo=True, titulo_planta="PORÃO DE CABOS")
    assert tubo == pytest.approx(23.0)


def test_linha_que_atravessa_a_folha_nao_cola_os_desenhos(tmp_path, monkeypatch):
    """Margem/divisa do carimbo passando rente à planta e ao detalhe: é moldura,
    não desenho — não pode transformar os dois num bloco só."""
    tubo, _ = _tubo(tmp_path, monkeypatch, linha_longa=True)
    assert tubo == pytest.approx(15.0)


@pytest.mark.parametrize("picotada", [False, True], ids=["inteira", "picotada"])
def test_CONTROLE_a_moldura_nao_atrapalha(tmp_path, monkeypatch, picotada):
    tubo, _ = _tubo(tmp_path, monkeypatch, titulo_planta="PORÃO DE CABOS",
                    moldura_picotada=picotada)
    assert tubo == pytest.approx(15.0)


def test_CONTROLE_janela_que_ja_diz_o_que_mostra_nao_procura_no_modelo(tmp_path, monkeypatch):
    tubo, ex = _tubo(tmp_path, monkeypatch, titulo_na_janela="PLANTA BAIXA TÉRREO")
    assert tubo == pytest.approx(23.0)
    assert ex.folhas.get("origem") != "modelo"


def test_CONTROLE_sem_janela_nenhuma_nada_muda(tmp_path, monkeypatch):
    """Contrato de 24/09: arquivo sem janela fica como está."""
    tubo, _ = _tubo(tmp_path, monkeypatch, janela=False)
    assert tubo == pytest.approx(23.0)


def test_corte_no_modelo_tira_o_comprimento_e_o_peso_vai_pro_log(tmp_path, monkeypatch):
    """25/09: o comprimento visto de lado sai (ver `aplicar_leitura_por_folha`)."""
    tubo, ex = _tubo(tmp_path, monkeypatch, titulo_detalhe='%%UCORTE "A-A"')
    assert tubo == pytest.approx(15.0), "o tubo do corte é o da planta visto de lado"
    # o peso da vista é TODA a geometria do corte: contorno 28 m + tubo 8 m
    assert ex.folhas["medida"]["vista"]["m"] == pytest.approx(36.0)
    # e o que a regra da vista tirou, pro log
    assert ex.folhas["vista"]["m"] == pytest.approx(36.0)


# ── o código de sublinhado do AutoCAD ─────────────────────────────────────────
def test_titulo_sublinhado_e_titulo():
    assert parece_titulo_de_desenho('%%UCORTE "A-A"')
    assert parece_titulo_de_desenho("%%uDETALHE 3")


def test_CONTROLE_sublinhado_no_meio_nao_inventa_titulo():
    assert not parece_titulo_de_desenho("SIGLA %%UDE AMPLIAÇÃO")


@pytest.mark.parametrize("cru, lido", [
    ('%%UCORTE "A-A"', 'CORTE "A-A"'),
    ("ELETRODUTO %%c50", "ELETRODUTO Ø50"),
    ("ÂNGULO 90%%d", "ÂNGULO 90°"),
])
def test_o_texto_chega_como_se_le_na_folha(cru, lido):
    t = ezdxf.new().modelspace().add_text(cru)
    assert dx._texto_do_text(t) == lido
    assert tipo_do_desenho(dx._texto_do_text(t)) == tipo_do_desenho(lido)


def test_a_ia_recebe_o_texto_limpo(tmp_path, monkeypatch):
    _, ex = _tubo(tmp_path, monkeypatch)
    assert any(t.text == 'DETALHE "D"' for t in ex.texts)
    assert not any("%%" in t.text for t in ex.texts)


def test_o_log_diz_que_veio_do_modelo(tmp_path, monkeypatch):
    import main
    _, ex = _tubo(tmp_path, monkeypatch)
    linha = main._leitura_por_folha_resumo(ex)
    assert "aplicada=sim origem=modelo" in linha and "fora=1" in linha
