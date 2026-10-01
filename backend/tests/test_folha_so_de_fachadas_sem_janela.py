# -*- coding: utf-8 -*-
"""Arquivo SEM janela, só de fachadas: lido por desenho, o comprimento da
elevação sai da soma.

🩸 30/09/2026 — H61 do estudo do acervo. Sem janela, o arquivo nunca era lido
por desenho: uma folha só de fachadas entregou "guarda-corpo de fachada
1.247,45 ml ✓" — o layer inteiro na elevação (horizontais, verticais e as
diagonais), em fachadas que somam 178,5 m de largura. Ligar geral NÃO: sem
janela, a caixa "logo acima do título" falhava mais (planta 0 × 0, detalhe de
120 m) — só a folha de VISTAS, inequívoca.
"""
import os
import sys

import ezdxf

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _desenho(msp, x0, titulo, ambientes=()):
    """Uma elevação em x0..x0+40: o guarda-corpo (com as diagonais) e o título embaixo."""
    gc = {"layer": "GUARDA-CORPO"}
    msp.add_line((x0, 10), (x0 + 40, 10), dxfattribs=gc)
    msp.add_line((x0, 11), (x0 + 40, 11), dxfattribs=gc)
    for k in range(9):
        msp.add_line((x0 + 5 * k, 10), (x0 + 5 * k + 5, 11), dxfattribs=gc)
    # a fachada: base, paredes até o guarda-corpo e o telhado em diagonal
    # (🪤 linha que ocupa a altura TODA do desenho é tratada como moldura)
    msp.add_line((x0, 0), (x0 + 40, 0))
    msp.add_line((x0, 0), (x0, 12))
    msp.add_line((x0 + 40, 0), (x0 + 40, 12))
    msp.add_line((x0, 12), (x0 + 40, 20))
    for i, a in enumerate(ambientes):
        msp.add_text(a, dxfattribs={"height": 0.5, "insert": (x0 + 5 + 8 * i, 15)})
    msp.add_text(titulo, dxfattribs={"height": 1.5, "insert": (x0 + 10, -3)})
    msp.add_text("ESC. 1:100", dxfattribs={"height": 0.8, "insert": (x0 + 10, -5)})


def _doc(titulos, ambientes=None):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for k, t in enumerate(titulos):
        _desenho(msp, 100.0 * k, t, (ambientes or {}).get(k, ()))
    return doc


def test_o_caso_folha_so_de_fachadas_sem_janela_e_lida_por_desenho():
    m = dx.mapa_de_folhas(_doc(["FACHADA A", "FACHADA B"]))
    assert m.get("origem") == "modelo sem janela", m
    assert sorted(f["titulo"] for f in m["folhas"]) == ["FACHADA A", "FACHADA B"], m
    assert all(f["tipo"] == "vista" for f in m["folhas"]), m


def test_o_comprimento_da_elevacao_sai_da_soma(tmp_path):
    p = str(tmp_path / "fachadas.dxf")
    _doc(["FACHADA A", "FACHADA B"]).saveas(p)
    ex = dx.extract_dxf(p)
    assert ex.get_walls_by_layer().get("GUARDA-CORPO", 0.0) < 1.0, ex.get_walls_by_layer()


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_com_planta_nao_mexe():
    assert not dx.mapa_de_folhas(_doc(["PLANTA BAIXA", "FACHADA A"])).get("folhas")


def test_CONTROLE_com_detalhe_nao_mexe():
    # detalhe é o que engolia os vizinhos no acervo (caixa de 120 m)
    assert not dx.mapa_de_folhas(_doc(["DETALHE 01", "FACHADA A"])).get("folhas")


def test_CONTROLE_uma_fachada_so_nao_mexe():
    assert not dx.mapa_de_folhas(_doc(["FACHADA A"])).get("folhas")


def test_CONTROLE_regiao_com_cara_de_planta_nao_mexe():
    m = dx.mapa_de_folhas(_doc(["FACHADA A", "FACHADA B"],
                               ambientes={1: ["SALA", "QUARTO", "COZINHA"]}))
    assert not m.get("folhas"), m


def test_CONTROLE_com_janela_segue_o_caminho_de_antes(tmp_path):
    # com janela útil, quem decide é a janela (este caminho não muda)
    doc = _doc(["FACHADA A", "FACHADA B"])
    lay = doc.layouts.new("F1")
    lay.add_viewport(center=(100, 100), size=(100, 50), view_center_point=(20, 10), view_height=25)
    assert dx.mapa_de_folhas(doc).get("origem") != "modelo sem janela"
