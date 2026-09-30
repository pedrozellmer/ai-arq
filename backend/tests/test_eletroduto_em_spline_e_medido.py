# -*- coding: utf-8 -*-
"""Eletroduto desenhado em SPLINE entra no comprimento do layer.

🩸 30/09/2026 — H10 do estudo do acervo, job 73c6f0ed (25/09). Eletroduto de
piso (108 m), de gesso (55 m) e o circuito de telefone (65 m) desenhados em
SPLINE: ≥ 99% dos layers. O motor somava só LINE/POLYLINE/ARC/CIRCLE, e o
único traço reto de cada layer era a AMOSTRA DA LEGENDA. Saíram "✓ MEDIDO
0,59 m", "0,62 m", "0,60 m" — planilha entregue.

E o emagrecedor de DXF grande (> 60 MB) descartava SPLINE como "lastro que o
motor não mede": medir sem manter lá perderia o eletroduto justo nos grandes.

O que os guardas prendem:
- a SPLINE do modelo entra no comprimento do layer (curva achatada);
- dentro de bloco de INFRA linear também; em bloco de móvel, não;
- o registro vai pro metadado e NÃO cru pro prompt;
- SPLINE degenerada não derruba; o teto de quantidade vale;
- o filtro textual do emagrecedor mantém a SPLINE.
"""
import math
import os
import sys

import ezdxf
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dwg_extractor as dx  # noqa: E402
import dxf_slim  # noqa: E402

R = 10.0
QUARTO = math.pi * R / 2          # 15,708 m — o quarto de círculo


def _quarto_de_circulo(cx=0.0, cy=0.0):
    return [(cx + R * math.cos(a), cy + R * math.sin(a))
            for a in [i * (math.pi / 2) / 8 for i in range(9)]]


def _doc():
    d = ezdxf.new("R2010")
    d.header["$INSUNITS"] = 6          # metros — o teste é da curva, não da escala
    return d


def _por_layer(ex):
    tot = {}
    for w in ex.walls:
        tot[w.layer] = tot.get(w.layer, 0.0) + w.length * getattr(w, "peso", 1.0)
    return tot


def _extrai(tmp_path, d, nome="t.dxf"):
    p = str(tmp_path / nome)
    d.saveas(p)
    return dx.extract_dxf(p)


def test_o_caso_real_a_curva_entra_e_a_amostra_nao_e_o_total(tmp_path):
    d = _doc()
    msp = d.modelspace()
    msp.add_spline(_quarto_de_circulo(), dxfattribs={"layer": "Ele piso"})
    msp.add_spline(_quarto_de_circulo(100, 0), dxfattribs={"layer": "Ele piso"})
    # a amostra reta da legenda: antes era TUDO o que o layer tinha
    msp.add_line((500, 0), (500.6, 0), dxfattribs={"layer": "Ele piso"})
    ex = _extrai(tmp_path, d)
    total = _por_layer(ex).get("Ele piso", 0.0)
    assert total == pytest.approx(2 * QUARTO + 0.6, rel=0.01), total
    # como o ARC: comprimento é da curva, start/end são as pontas (o pareamento
    # de faces de duto precisa saber que não é reta)
    assert sum(1 for w in ex.walls if w.layer == "Ele piso" and w.curvo) == 2


def test_o_prompt_mostra_o_comprimento_com_a_curva(tmp_path):
    d = _doc()
    msp = d.modelspace()
    msp.add_spline(_quarto_de_circulo(), dxfattribs={"layer": "Ele piso"})
    msp.add_line((500, 0), (500.6, 0), dxfattribs={"layer": "Ele piso"})
    p = _extrai(tmp_path, d).to_structured_prompt()
    linha = next((l for l in p.splitlines() if "Ele piso" in l and " m" in l), "")
    assert "16.3" in linha or "16,3" in linha, linha


def test_o_registro_vai_pro_metadado_e_nao_cru_pro_prompt(tmp_path):
    d = _doc()
    d.modelspace().add_spline(_quarto_de_circulo(), dxfattribs={"layer": "Ele piso"})
    ex = _extrai(tmp_path, d)
    reg = ex.metadata.get("splines_medidas", "")
    assert reg.startswith("1 SPLINE") and "Ele piso" in reg, reg
    assert "splines_medidas" not in ex.to_structured_prompt()


def test_dentro_de_bloco_de_INFRA_a_curva_entra_uma_vez_por_insercao(tmp_path):
    d = _doc()
    b = d.blocks.new("TRECHO")
    b.add_spline(_quarto_de_circulo(), dxfattribs={"layer": "ELETRODUTO"})
    msp = d.modelspace()
    msp.add_blockref("TRECHO", (0, 0))
    msp.add_blockref("TRECHO", (200, 0))
    total = _por_layer(_extrai(tmp_path, d)).get("ELETRODUTO", 0.0)
    assert total == pytest.approx(2 * QUARTO, rel=0.01), total


def test_CONTROLE_curva_de_movel_dentro_de_bloco_nao_entra(tmp_path):
    d = _doc()
    b = d.blocks.new("POLTRONA")
    b.add_spline(_quarto_de_circulo(), dxfattribs={"layer": "MOVEIS"})
    d.modelspace().add_blockref("POLTRONA", (0, 0))
    assert _por_layer(_extrai(tmp_path, d)).get("MOVEIS", 0.0) == 0.0


def test_curva_de_SIMBOLO_no_modelo_nao_soma_metro(tmp_path):
    """dd52081b: CARROS 649 → 1.000 m com a curva dos carros; LAYOUT (móveis)."""
    d = _doc()
    msp = d.modelspace()
    for lay in ("CARROS", "CARROS-LF", "LAY-OUT-LF", "LAYOUT", "VEGETACAO", "MOBILIARIO"):
        msp.add_spline(_quarto_de_circulo(), dxfattribs={"layer": lay})
    msp.add_line((0, 0), (4, 0), dxfattribs={"layer": "CARROS"})     # a linha reta fica
    ex = _extrai(tmp_path, d)
    tot = _por_layer(ex)
    assert tot.get("CARROS") == pytest.approx(4.0), tot
    for lay in ("CARROS-LF", "LAY-OUT-LF", "LAYOUT", "VEGETACAO", "MOBILIARIO"):
        assert tot.get(lay, 0.0) == 0.0, (lay, tot)
    assert "fora (símbolo/anotação): 6" in ex.metadata.get("splines_medidas", ""), ex.metadata


def test_CONTROLE_os_layers_de_eletroduto_do_caso_nao_casam_com_simbolo():
    for lay in ("Ele piso", "TELEFONE", "Eletroduto gesso", "ALARME", "TVCABO", "INTERFONE",
                "EL-Condutos (Teto)", "CARRETEL", "ELE-CARREGADOR VEICULAR"):
        assert not dx._RE_LAYER_SIMBOLO_EM_CURVA.search(lay), lay


def test_curva_em_layer_de_ANOTACAO_nao_soma_metro(tmp_path):
    d = _doc()
    d.modelspace().add_spline(_quarto_de_circulo(), dxfattribs={"layer": "COTAS"})
    assert _por_layer(_extrai(tmp_path, d)).get("COTAS", 0.0) == 0.0


def test_CONTROLE_sem_spline_nada_muda(tmp_path):
    d = _doc()
    d.modelspace().add_line((0, 0), (5, 0), dxfattribs={"layer": "PAREDE"})
    ex = _extrai(tmp_path, d)
    assert "splines_medidas" not in ex.metadata
    assert _por_layer(ex) == {"PAREDE": pytest.approx(5.0)}


def test_spline_degenerada_nao_derruba(tmp_path):
    d = _doc()
    msp = d.modelspace()
    s = msp.add_spline([(1, 1), (1, 1)], dxfattribs={"layer": "Ele piso"})
    assert s is not None
    msp.add_line((0, 0), (2, 0), dxfattribs={"layer": "PAREDE"})
    ex = _extrai(tmp_path, d)
    assert _por_layer(ex).get("PAREDE") == pytest.approx(2.0)


def test_o_teto_de_quantidade(tmp_path, monkeypatch):
    monkeypatch.setattr(dx, "_MAX_SPLINES", 2)
    d = _doc()
    msp = d.modelspace()
    for k in range(5):
        msp.add_spline(_quarto_de_circulo(100 * k, 0), dxfattribs={"layer": "Ele piso"})
    ex = _extrai(tmp_path, d)
    assert _por_layer(ex).get("Ele piso", 0.0) == pytest.approx(2 * QUARTO, rel=0.01)
    assert ex.metadata["splines_medidas"].startswith("2 SPLINE")


def test_o_comprimento_de_uma_spline_reta_e_exato():
    d = _doc()
    s = d.modelspace().add_open_spline([(0, 0), (5, 0), (10, 0), (20, 0)], degree=3)
    assert dx._spline_length(s) == pytest.approx(20.0, abs=1e-6)


def test_o_emagrecedor_mantem_a_spline(tmp_path):
    assert "SPLINE" in dxf_slim._KEEP
    d = _doc()
    msp = d.modelspace()
    msp.add_spline(_quarto_de_circulo(), dxfattribs={"layer": "Ele piso"})
    msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "PAREDE"})
    src, out = str(tmp_path / "g.dxf"), str(tmp_path / "g.slim.dxf")
    d.saveas(src)
    dxf_slim.emagrecer_por_texto(src, out)
    tipos = [e.dxftype() for e in ezdxf.readfile(out).modelspace()]
    assert "SPLINE" in tipos and "LINE" in tipos, tipos
