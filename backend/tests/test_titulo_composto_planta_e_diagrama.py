# -*- coding: utf-8 -*-
"""Folha "PLANTA BAIXA - DIAGRAMAS": a planta continua na soma.

🩸 30/09/2026 (estudo do acervo, elétrico de uma casa de ~50 m²). A folha
inteira era UMA janela com esse título: a planta com os eletrodutos num canto,
quadro de cargas e unifilar no resto. "diagrama" é testado antes de "planta",
a folha foi pra 'fora' e o comprimento caiu de 4.061 para 51 m.

Regras que os guardas prendem:
- título COMPOSTO (com separador) com uma parte "planta" e o resto só diagrama
  elétrico → 'planta';
- esquema, isométrico, detalhe, ampliação, 3D e planta-chave continuam 'fora'
  (redesenham o mesmo objeto) — e o composto sem a palavra "planta" também;
- o log da leitura por folha passa a dizer o TÍTULO do que saiu.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import tipo_do_desenho  # noqa: E402


@pytest.mark.parametrize("titulo", [
    "PLANTA BAIXA - DIAGRAMAS",
    "Planta Baixa / Diagrama Unifilar",
    "PLANTA BAIXA E DIAGRAMA TRIFILAR",
    "PLANTA BAIXA ELÉTRICA - QUADRO DE CARGAS - DIAGRAMA UNIFILAR",
])
def test_planta_e_diagrama_na_mesma_folha_e_planta(titulo):
    assert tipo_do_desenho(titulo) == "planta"


@pytest.mark.parametrize("titulo", [
    "DIAGRAMA UNIFILAR SIMPLIFICADO",            # só diagrama
    "DETALHE PLANTA BAIXA TÍPICA DO PI",         # sem separador: detalhe ganha
    "PLANTA BAIXA - DETALHE BANHEIRO",           # detalhe redesenha a planta
    "PLANTA BAIXA E ESQUEMA VERTICAL",           # esquema = o mesmo tubo de novo
    "PLANTA BAIXA - ISOMÉTRICO ÁGUA FRIA",
    "3D - Térreo - Banho",                       # sem a palavra planta
    "PLANTA CHAVE - DIAGRAMA",                   # a "planta" é a planta-chave
    "PLANTA-CHAVE / DIAGRAMA",                   # hífen colado não separa
    "PLANTA DE SITUAÇÃO / DIAGRAMA",             # a parte planta também é fora
    "DIAGRAMA - PLANTA AMPLIADA",
    "DIAGRAMA DA PLANTA - UNIFILAR",             # "planta" dentro de uma parte diagrama
])
def test_CONTROLE_o_resto_de_fora_continua_fora(titulo):
    assert tipo_do_desenho(titulo) == "fora"


# ── de ponta a ponta: uma folha, uma janela, título no papel ──────────────────
def _arquivo(tmp_path, titulo):
    """Modelo: 20 m de eletroduto (planta) e 5 m de linha de diagrama, tudo
    dentro de UMA janela; o título escrito no papel logo abaixo dela."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((1, 2), (11, 2), dxfattribs={"layer": "EL-CONDUTO"})
    msp.add_line((1, 4), (11, 4), dxfattribs={"layer": "EL-CONDUTO"})
    msp.add_line((20, 2), (25, 2), dxfattribs={"layer": "DI-DIAGRAMA"})
    lay = doc.layouts.new("FOLHA 01")
    x0, y0, x1, y1, esc = 0, 0, 30, 10, 10.0
    vp = lay.add_viewport(center=(200, 150), size=((x1 - x0) * esc, (y1 - y0) * esc),
                          view_center_point=((x0 + x1) / 2, (y0 + y1) / 2), view_height=(y1 - y0))
    vp.dxf.view_target_point = (0, 0, 0)
    px0, py0 = 200 - (x1 - x0) * esc / 2, 150 - (y1 - y0) * esc / 2
    lay.add_text(titulo, dxfattribs={"height": 3.0, "insert": (px0 + 2, py0 - 3.0)})
    lay.add_text(" 1 : 100", dxfattribs={"height": 2.2, "insert": (px0 + 2, py0 - 6.0)})
    p = str(tmp_path / "eletrico.dxf")
    doc.saveas(p)
    return p


def test_a_planta_eletrica_da_folha_com_diagrama_fica_na_soma(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, "PLANTA BAIXA - DIAGRAMAS"))
    assert ex.get_walls_by_layer().get("EL-CONDUTO") == pytest.approx(20.0)


def test_CONTROLE_a_folha_so_de_diagrama_continua_fora(tmp_path, monkeypatch):
    # prova que o arquivo de teste É lido pela folha: com título de diagrama
    # a janela inteira sai — e o eletroduto some junto
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, "DIAGRAMA UNIFILAR"))
    assert not ex.get_walls_by_layer().get("EL-CONDUTO"), ex.get_walls_by_layer()
    fora = [d for d in ex.folhas["desenhos_lista"] if d["tipo"] == "fora"]
    assert fora and fora[0]["titulo"] == "DIAGRAMA UNIFILAR"


def test_o_log_diz_o_titulo_do_que_saiu(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    import main
    ex = dx.extract_dxf(_arquivo(tmp_path, "DIAGRAMA UNIFILAR"))
    linha = main._leitura_por_folha_resumo(ex)
    assert "fora=1 fora_titulos=[DIAGRAMA UNIFILAR]" in linha, linha
