# -*- coding: utf-8 -*-
"""O relato do eixo e a área da vista falam do que FICOU na soma.

🩸 25/09/2026 — releitura do job `53f0483f` com o conserto dos cortes no ar:
a soma por layer dava ZERO de leito nas pranchas que eram só corte, mas o
relato do eixo — feito ANTES da leitura por folha — dizia "431 m de face ->
230,5 m de eixo", e a IA entregou 212,5 m de leito BRANCO e o cabo de cobre
"ao longo do leito" com o mesmo número. E a área cheia que ficou dentro do
corte saiu branca como "piso de equipamentos 11,46 m²".

Regras:
- depois da folha, o relato traz só o número que está na soma (ou diz que
  nada do layer entrou); número de antes não aparece;
- área que fica dentro de corte/elevação vai marcada como vista DE LADO.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import test_desenho_no_modelo as tdm  # noqa: E402


def _quadrado(msp, lay, x0, y0, x1, y1):
    h = msp.add_hatch(color=1, dxfattribs={"layer": lay})
    h.paths.add_polyline_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], is_closed=True)


def _folha(tmp_path, com_planta=True):
    """A folha do guarda vizinho (planta em cima, CORTE embaixo) + um leito em
    2 linhas no corte, outro na planta, e uma área cheia dentro do corte."""
    p = tdm._folha(tmp_path, titulo_detalhe='%%UCORTE "A-A"')
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()
    if com_planta:
        for y in (24.0, 24.6):
            msp.add_line((5, y), (15, y), dxfattribs={"layer": "EL-LEITO"})
    for y in (10.0, 10.6):
        msp.add_line((5, y), (11, y), dxfattribs={"layer": "EL-LEITO"})
    _quadrado(msp, "CONCRETO", 6, 7, 9, 9.5)
    _quadrado(msp, "PISO", 16, 20, 19, 23)
    doc.saveas(p)
    return p


def test_o_relato_so_fala_do_eixo_que_ficou_na_soma(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_folha(tmp_path))
    rel = ex.metadata["duto_linha_dupla"]
    assert "EL-LEITO: 10.0m na soma" in rel, rel
    assert "de face" not in rel, "número de antes da folha vira quantidade na mão da IA"
    assert ex.get_walls_by_layer()["EL-LEITO"] == pytest.approx(10.0)


def test_layer_todo_em_corte_diz_que_nada_entrou(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_folha(tmp_path, com_planta=False))
    rel = ex.metadata["duto_linha_dupla"]
    assert "NADA deste layer entra" in rel and "m na soma" not in rel, rel


def test_CONTROLE_sem_leitura_por_folha_o_relato_fica_como_era(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    ex = dx.extract_dxf(_folha(tmp_path))
    assert "de face" in ex.metadata["duto_linha_dupla"]


def test_area_que_ficou_no_corte_vai_marcada(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    txt = dx.extract_dxf(_folha(tmp_path)).to_structured_prompt()
    linha = next(l for l in txt.splitlines() if l.strip().startswith("CONCRETO:"))
    assert "vista DE LADO" in linha and "NÃO é piso" in linha, linha
    # 🩸 3ª releitura: "só vale como revestimento" virou revestimento de concreto
    assert "IGNORE" in linha and "só vale como revestimento" not in linha, linha


def test_CONTROLE_area_da_planta_nao_leva_a_marca(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    txt = dx.extract_dxf(_folha(tmp_path)).to_structured_prompt()
    linha = next(l for l in txt.splitlines() if l.strip().startswith("PISO:"))
    assert "vista DE LADO" not in linha, linha


def test_o_relato_estranho_passa_intacto():
    assert dx._relato_do_eixo_na_soma("texto fora do formato", []) == "texto fora do formato"
