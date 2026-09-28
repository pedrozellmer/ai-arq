# -*- coding: utf-8 -*-
"""A hachura da SEÇÃO da parede cortada não é superfície e não prova m².

🩸 27/09/2026 (estudo de leitura, item 1): em layer de parede, a hachura que
preenche a ESPESSURA da parede na planta virava "m² de drywall" com ✓ MEDIDO —
shaft 0,18 m² ✓ (real ~2,5 m²), drywall 1,44 m² ✓ (uma parede de ~23 m).
Faixa fina = some numa erosão de 12 cm e tem ≥ 0,6 m de comprimento.
"""
import os
import sys

import ezdxf

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import layer_de_hachura_de_parede  # noqa: E402


def _hachura(msp, layer, x0, y0, w, h):
    ha = msp.add_hatch(dxfattribs={"layer": layer})
    ha.paths.add_polyline_path([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)], is_closed=True)


def _arquivo(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6                      # metros
    msp = doc.modelspace()
    _hachura(msp, "PAT-DW-SHAFT RU-48", 0, 0, 5.0, 0.15)       # faixa: seção
    _hachura(msp, "PAT-DW-SHAFT RU-48", 0, 2, 3.0, 0.12)       # outra faixa
    _hachura(msp, "PAT-ALV-QUADRADO", 10, 0, 1.0, 1.0)         # parede, mas não é faixa
    _hachura(msp, "PAT-FORRO", 20, 0, 4.3, 0.14)               # faixa, mas não é parede
    _hachura(msp, "PAT-DW-SELO CORTA-FOGO", 30, 0, 3.7, 0.13)  # selo: peça, não seção
    _hachura(msp, "PAT-DW-CURTO", 40, 0, 0.4, 0.15)            # faixa curta demais
    p = str(tmp_path / "secao.dxf")
    # 🪤 tamanhos todos diferentes: hachuras IGUAIS em layers diferentes
    # viram "amostra de legenda" e saem antes de chegar aqui
    doc.saveas(p)
    return p


def _extrai(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    return dx.extract_dxf(_arquivo(tmp_path))


def test_a_faixa_fina_em_layer_de_parede_e_secao(tmp_path, monkeypatch):
    ex = _extrai(tmp_path, monkeypatch)
    assert ex.get_layers_secao_de_parede() == {"PAT-DW-SHAFT RU-48"}


def test_o_rotulo_pra_ia_diz_que_nao_e_superficie(tmp_path, monkeypatch):
    txt = _extrai(tmp_path, monkeypatch).to_structured_prompt()
    linha = next(l for l in txt.splitlines() if l.strip().startswith("PAT-DW-SHAFT RU-48:"))
    assert "SEÇÃO DE PAREDE CORTADA" in linha and "NÃO é" in linha, linha
    outra = next(l for l in txt.splitlines() if l.strip().startswith("PAT-ALV-QUADRADO:"))
    assert "SEÇÃO DE PAREDE" not in outra, outra


def test_CONTROLE_o_que_nao_e_secao(tmp_path, monkeypatch):
    sec = {h.layer: h.secao_de_parede for h in _extrai(tmp_path, monkeypatch).hatches}
    assert sec["PAT-ALV-QUADRADO"] is False, "1×1 m não some na erosão"
    assert sec["PAT-FORRO"] is False, "forro não é parede"
    assert sec["PAT-DW-SELO CORTA-FOGO"] is False, "selo corta-fogo é peça do shaft"
    assert sec["PAT-DW-CURTO"] is False, "faixa de 0,4 m não é parede"


def test_layer_de_hachura_de_parede():
    for n in ("PAT-DW-SHAFT RU-48 40cm", "PAT-DW-ST-70-ST 40cm LÃ", "PAT-ALV1", "PAT-TIJOLO 9",
              "A-WALL-PATT", "ALVENARIA"):
        assert layer_de_hachura_de_parede(n), n
    for n in ("PAT-DW-SELO CORTA-FOGO", "PAT-FORRO", "PAT-HACHURAS", "PISO", "PAT-PILAR"):
        assert not layer_de_hachura_de_parede(n), n


def test_a_chave_do_selo_nao_prova_m2_com_a_secao():
    """O cofre da chave (`_indice_geom["area"]`) pula os layers de seção."""
    src = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    i = src.index('for _lyr, _a in (extraction.get_areas_by_layer() or {}).items():')
    trecho = src[i - 400:i + 300]
    assert "_secoes_ig = extraction.get_layers_secao_de_parede()" in trecho
    assert "if _lyr in _secoes_ig:\n                                    continue" in trecho
