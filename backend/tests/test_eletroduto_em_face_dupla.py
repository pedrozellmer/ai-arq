# -*- coding: utf-8 -*-
"""Eletroduto do Revit desenhado pelas duas paredes não sai medido.

🩸 01/10/2026 — H75 do estudo do acervo. O Revit exporta o eletroduto como o
tubo: as duas paredes (às vezes 2 a 4 linhas), sem ø escrito — a régua do tubo
(H34) exige o rótulo e não marcava. Um job de iluminação entregou "1.798,8 ml
✓": 80 % do layer com uma parceira a 25 mm; pelo eixo, ~1.070 m.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import layers_que_nao_provam, selo_apos_tubo_em_face_dupla  # noqa: E402


def _ler(tmp_path, desenha, insunits=6):
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = insunits
    desenha(d.modelspace())
    p = str(tmp_path / "ele.dxf")
    d.saveas(p)
    return dx.extract_dxf(p)


def _trechos(msp, layer, ys, n=12, k=1.0, comp=8.0, passo=3.0):
    """n trechos paralelos ao x, cada um com as linhas em `ys` (m)."""
    for i in range(n):
        y0 = i * passo
        for y in ys:
            msp.add_line((0, (y0 + y) * k), (comp * k, (y0 + y) * k), dxfattribs={"layer": layer})


@pytest.mark.parametrize("layer", ["E-ELETRODUTO-ILUM", "Conduites", "CONDUIT-POWER"])
def test_o_caso_eletroduto_pelas_duas_paredes(tmp_path, layer):
    ex = _ler(tmp_path, lambda m: _trechos(m, layer, (0, 0.025)))
    fd = ex.metadata.get("tubos_em_face_dupla") or {}
    assert layer in fd and fd[layer]["fracao"] >= 0.9 and fd[layer]["eletroduto"], fd
    assert fd[layer]["diametros_mm"][0] == 25, fd[layer]
    assert layer.upper() in layers_que_nao_provam(ex.metadata)
    assert "ELETRODUTO EM FACE DUPLA" in ex.to_structured_prompt()


def test_multi_linha_com_a_parede_do_tubo(tmp_path):
    """4 linhas por eletroduto (as duas paredes, cada uma com a espessura)."""
    ex = _ler(tmp_path, lambda m: _trechos(m, "Conduites", (0, 0.004, 0.033, 0.037)))
    assert "Conduites" in (ex.metadata.get("tubos_em_face_dupla") or {})


def test_desenho_em_milimetro(tmp_path):
    ex = _ler(tmp_path, lambda m: _trechos(m, "ELETRODUTO", (0, 0.025), k=1000.0), insunits=4)
    assert "ELETRODUTO" in (ex.metadata.get("tubos_em_face_dupla") or {})


def test_a_linha_confirmada_que_usa_o_layer_cai():
    conf, obs, rebaixou = selo_apos_tubo_em_face_dupla(
        "confirmado", "Fonte: layer E-ELETRODUTO-ILUM", "ml", ["E-ELETRODUTO-ILUM"],
        {"E-ELETRODUTO-ILUM": {"eletroduto": True}})
    assert rebaixou and conf == "estimado"


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_eletroduto_de_linha_unica(tmp_path):
    ex = _ler(tmp_path, lambda m: _trechos(m, "ELETRODUTO", (0,)))
    assert not ex.metadata.get("tubos_em_face_dupla")


def test_CONTROLE_dois_eletrodutos_de_linha_unica_a_30_cm(tmp_path):
    ex = _ler(tmp_path, lambda m: _trechos(m, "ELETRODUTO", (0, 0.30)))
    assert not ex.metadata.get("tubos_em_face_dupla")


def test_CONTROLE_menos_de_60_por_cento_em_par(tmp_path):
    """Metade do layer em par a 25 mm, metade linha única: a convenção do layer
    é linha única, o par é coincidência."""
    def d(m):
        _trechos(m, "ELETRODUTO", (0, 0.025), n=5)
        for i in range(14):
            m.add_line((20, i * 3.0), (28, i * 3.0), dxfattribs={"layer": "ELETRODUTO"})
    ex = _ler(tmp_path, d)
    assert not ex.metadata.get("tubos_em_face_dupla")


@pytest.mark.parametrize("layer", ["Conexões do conduite", "Condulete com Rosca BSP",
                                   "ELETRODUTO-CAIXAS", "PAREDE", "FIACAO"])
def test_CONTROLE_layer_que_nao_e_eletroduto(tmp_path, layer):
    ex = _ler(tmp_path, lambda m: _trechos(m, layer, (0, 0.025)))
    fd = ex.metadata.get("tubos_em_face_dupla") or {}
    assert layer not in fd, (layer, fd)


def test_CONTROLE_tubo_continua_com_a_regua_do_h34(tmp_path):
    """P-PIPE sem ø escrito: o H34 não marca, e esta régua não é dele."""
    ex = _ler(tmp_path, lambda m: _trechos(m, "P-PIPE", (0, 0.025)))
    assert "P-PIPE" not in (ex.metadata.get("tubos_em_face_dupla") or {})
