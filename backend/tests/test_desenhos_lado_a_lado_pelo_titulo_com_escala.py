# -*- coding: utf-8 -*-
"""Folha de detalhe com vários desenhos do MESMO ambiente lado a lado no modelo.

🩸 27/09/2026 — cliente que voltou (folha de detalhe de um banho semi-suíte):
a folha tem a PLANTA, a PAGINAÇÃO DE PISO e a PLANTA DE FORRO do mesmo banheiro
lado a lado, 4 elevações e o corte da bancada, e UMA janela de papel mostrando
tudo. O motor somava as três plantas: janela JA7 "4 ✓" (no desenho, 1), ralo
"4 ✓" (são 2). Três defeitos juntos:
- a letra maior da folha é do carimbo (60) e os títulos dos desenhos têm 7 —
  a régua "título é a letra grande" não achava nenhum desenho;
- "PAGINAÇÃO DE PISO" não era desenho nenhum (sem a palavra "planta");
- a janela estava inserida DUAS vezes no MESMO ponto.

Regras que os guardas prendem:
- título pequeno vale quando tem a ESCALA logo embaixo ("escala 1:25"); o
  título da folha no carimbo e o rótulo solto ("DET.03") não têm;
- paginação e layout são planta (temática: a base repetida conta uma vez);
- inserção do mesmo bloco no mesmo ponto, rotação, escala e atributos conta 1;
  com atributo diferente são duas peças.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import tipo_do_desenho  # noqa: E402

TITULOS = ("PLANTA BANHO SEMI-SUÍTE", "PAGINAÇÃO DE PISO", "PLANTA DE FORRO DE GESSO")


def _folha(tmp_path, com_escala=True, janela_dupla=True, nome="banho.dxf"):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for nm in ("RALO", "JANELA"):
        doc.blocks.new(nm).add_circle((0, 0), 0.2)
    # moldura e carimbo: a letra GRANDE da folha é daqui
    c = [(0, 0), (130, 0), (130, 45), (0, 45), (0, 0)]
    for a, b in zip(c, c[1:]):
        msp.add_line(a, b, dxfattribs={"layer": "MOLDURA"})
    msp.add_text("A052", dxfattribs={"height": 6.0, "insert": (112, 3)})
    msp.add_text("DETALHAMENTO BANHO SEMI-SUÍTE", dxfattribs={"height": 0.65, "insert": (100, 12)})
    # o campo de escala do carimbo fica ACIMA do título da folha: não o faz desenho
    msp.add_text("1:25", dxfattribs={"height": 0.5, "insert": (101, 13.5)})
    for k, t in enumerate(TITULOS):
        ox = 5 + 35.0 * k
        r = [(ox, 12), (ox + 20, 12), (ox + 20, 30), (ox, 30), (ox, 12)]
        for a, b in zip(r, r[1:]):
            msp.add_line(a, b, dxfattribs={"layer": "ALV"})
        if k < 2:                                  # planta e paginação têm as peças
            msp.add_blockref("RALO", (ox + 8, 16), dxfattribs={"layer": "HID"})
            msp.add_blockref("RALO", (ox + 12, 16), dxfattribs={"layer": "HID"})
            for _ in range(2 if janela_dupla else 1):
                msp.add_blockref("JANELA", (ox + 10, 29), dxfattribs={"layer": "ESQ"})
        msp.add_text(t, dxfattribs={"height": 0.7, "insert": (ox, 10)})
        if com_escala:
            msp.add_text("escala 1:25", dxfattribs={"height": 0.5, "insert": (ox, 9.2)})
    # uma elevação ao lado
    for a, b in [((110, 25), (125, 25)), ((125, 25), (125, 35)), ((125, 35), (110, 35)), ((110, 35), (110, 25))]:
        msp.add_line(a, b, dxfattribs={"layer": "ALV"})
    msp.add_text("ELEVAÇÃO 01", dxfattribs={"height": 0.7, "insert": (110, 23)})
    if com_escala:
        msp.add_text("escala 1:25", dxfattribs={"height": 0.5, "insert": (110, 22.2)})
    # UMA janela de papel mostrando a folha inteira (como no arquivo do cliente)
    lay = doc.layouts.new("F1")
    vp = lay.add_viewport(center=(200, 150), size=(1300, 450), view_center_point=(65, 22.5), view_height=45)
    vp.dxf.view_target_point = (0, 0, 0)
    p = str(tmp_path / nome)
    doc.saveas(p)
    return p


def _ler(p, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(p)
    return ex.get_block_summary(), ex.get_walls_by_layer(), ex


# ── o caso ─────────────────────────────────────────────────────────────────────
def test_as_tres_plantas_do_mesmo_banheiro_contam_uma_vez(tmp_path, monkeypatch):
    bs, wl, ex = _ler(_folha(tmp_path), monkeypatch)
    assert bs.get("RALO") == 2, "planta e paginação do MESMO banheiro: são 2 ralos"
    assert bs.get("JANELA") == 1, "uma janela, inserida 2× no mesmo ponto e repetida na paginação"
    assert ex.folhas.get("aplicada") is True and ex.folhas.get("repetidas")


def test_o_titulo_pequeno_com_escala_embaixo_e_achado(tmp_path):
    msp = ezdxf.readfile(_folha(tmp_path)).modelspace()
    ts = {f["titulo"]: f["tipo"] for f in dx._desenhos_no_modelo(msp)}
    assert ts.get("PAGINAÇÃO DE PISO") == "planta", ts
    assert ts.get("ELEVAÇÃO 01") == "vista", ts
    assert "DETALHAMENTO BANHO SEMI-SUÍTE" not in ts, "título do carimbo, sem escala: não é desenho"


def test_paginacao_e_layout_sao_planta():
    assert tipo_do_desenho("PAGINAÇÃO DE PISO") == "planta"
    assert tipo_do_desenho("LAYOUT - TÉRREO") == "planta"
    assert tipo_do_desenho("DETALHE DE PAGINAÇÃO") == "fora", "detalhe ganha de planta"


# ── controles ──────────────────────────────────────────────────────────────────
def test_CONTROLE_sem_escala_embaixo_o_titulo_pequeno_nao_vale(tmp_path, monkeypatch):
    """Sem a escala, nenhum título passa: fica como era (soma as plantas)."""
    bs, _, ex = _ler(_folha(tmp_path, com_escala=False), monkeypatch)
    assert bs.get("RALO") == 4
    assert not ex.folhas.get("aplicada")


def test_CONTROLE_a_janela_inserida_uma_vez_continua_uma(tmp_path, monkeypatch):
    bs, _, _ = _ler(_folha(tmp_path, com_escala=False, janela_dupla=False), monkeypatch)
    assert bs.get("JANELA") == 2, "uma por planta, sem leitura por folha: 2 (como antes)"


def test_a_insercao_repetida_no_mesmo_ponto_conta_uma(tmp_path, monkeypatch):
    bs, _, ex = _ler(_folha(tmp_path, com_escala=False), monkeypatch)
    assert bs.get("JANELA") == 2, "2 plantas × (2 inserções no mesmo ponto = 1)"
    assert ex.blocos_descartados.get("duplicado") == 2


def _com_pecas_soltas_longe(p, destino):
    """A folha + mobília miúda nas plantas (massa de desenho) + 6 peças soltas a
    quilômetros da folha, como os registros e tomadas perdidos no modelo."""
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()
    for k in range(3):
        ox = 5 + 35.0 * k
        for i in range(40):
            msp.add_line((ox + 1 + 0.4 * i, 13), (ox + 1 + 0.4 * i, 13.3), dxfattribs={"layer": "MOB"})
    for x, y in ((-4000, -3000), (-3900, -2900), (-4100, -3100), (6000, 5000), (6100, 5100), (5900, 4900)):
        msp.add_blockref("RALO", (x, y), dxfattribs={"layer": "SOLTO"})
    doc.saveas(destino)
    return destino


def test_peca_solta_longe_nao_estica_a_folha(tmp_path):
    """🩸 Sem o miolo, 6 peças a km da folha faziam a malha engolir a folha
    inteira e nenhum desenho era achado."""
    p = _com_pecas_soltas_longe(_folha(tmp_path), str(tmp_path / "solto.dxf"))
    ts = {f["titulo"]: f["tipo"] for f in dx._desenhos_no_modelo(ezdxf.readfile(p).modelspace())}
    assert ts.get("PAGINAÇÃO DE PISO") == "planta" and ts.get("ELEVAÇÃO 01") == "vista", ts


def test_CONTROLE_sem_ponto_longe_o_miolo_nao_corta_desenho_da_ponta(tmp_path):
    """🩸 Medido no acervo (elétrica industrial de 25/09): cortar o miolo
    SEMPRE encolhia as caixas dos cortes da ponta da folha e 100 m de corte
    voltavam pra soma. Aqui um corte com poucos pontos (3% da folha) fica na
    ponta, DENTRO da folha: tem que continuar sendo achado."""
    p = _com_pecas_soltas_longe(_folha(tmp_path), str(tmp_path / "base.dxf"))
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()
    for e in list(msp.query("INSERT")):
        if e.dxf.layer == "SOLTO":
            msp.delete_entity(e)                  # sem nenhum ponto longe
    for a, b in [((150, 30), (165, 30)), ((165, 30), (165, 38)), ((165, 38), (150, 38)), ((150, 38), (150, 30))]:
        msp.add_line(a, b, dxfattribs={"layer": "LEITO"})
    msp.add_text("CORTE A-A", dxfattribs={"height": 0.7, "insert": (150, 28)})
    msp.add_text("escala 1:50", dxfattribs={"height": 0.5, "insert": (150, 27.2)})
    ts = {f["titulo"]: f["tipo"] for f in dx._desenhos_no_modelo(msp)}
    assert ts.get("CORTE A-A") == "vista", ts


def _duas_etiquetas(tmp_path, cod_a, cod_b, rot_b=0.0, pos_b=(5, 5)):
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    blk = doc.blocks.new("ETIQ")
    blk.add_attdef("COD", (0, 0), dxfattribs={"height": 0.2})
    blk.add_circle((0, 0), 0.3)
    msp.add_blockref("ETIQ", (5, 5)).add_attrib("COD", cod_a, (5, 5))
    msp.add_blockref("ETIQ", pos_b, dxfattribs={"rotation": rot_b}).add_attrib("COD", cod_b, pos_b)
    p = str(tmp_path / "etiq.dxf")
    doc.saveas(p)
    return p


@pytest.mark.parametrize("cod_b,rot_b,pos_b,esperado", [
    ("A", 0.0, (5, 5), 1),          # a mesma peça duas vezes
    ("B", 0.0, (5, 5), 2),          # atributo diferente: duas peças
    ("A", 90.0, (5, 5), 2),         # girada: outra peça
    ("A", 0.0, (5.5, 5), 2),        # meio metro ao lado: outra peça
])
def test_CONTROLE_so_a_insercao_identica_e_duplicata(tmp_path, monkeypatch, cod_b, rot_b, pos_b, esperado):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    ex = dx.extract_dxf(_duas_etiquetas(tmp_path, "A", cod_b, rot_b, pos_b))
    assert ex.get_block_summary().get("ETIQ") == esperado
