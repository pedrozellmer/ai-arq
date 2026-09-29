# -*- coding: utf-8 -*-
"""Desenho em METRO que declara milímetro: a altura do texto denuncia.

🩸 29/09/2026 (caso 18c57c3c): sem cota, o núcleo lido em mm dava 0,99 × 0,11 m
(a régua do núcleo exige os dois lados < 0,5 m) e todo comprimento saiu 1000×
menor. O texto mediano tinha 0,135 unidade — em mm, letra de 0,14 mm.
📏 No acervo, só três arquivos disparam (os três declarando mm com texto de
0,1–0,25) e nos outros dois a produção já tinha provado metro por outro caminho.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _desenho(pasta, altura_texto, n_textos=40, insunits=4, largura=1000.0, altura=100.0):
    """Faixa larga (4 vistas lado a lado) com texto de altura fixa, SEM cota."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()
    for k in range(60):
        x = largura * k / 60.0
        msp.add_line((x, 0), (x, altura), dxfattribs={"layer": "PAREDE"})
        msp.add_line((x, 0), (x + largura / 60.0, 0), dxfattribs={"layer": "PAREDE"})
    for k in range(n_textos):
        msp.add_text("SALA %d" % k, dxfattribs={"height": altura_texto}).set_placement(
            (largura * k / n_textos, altura / 2))
    p = os.path.join(str(pasta), "t.dxf")
    doc.saveas(p)
    return p


def test_texto_de_0_135_em_mm_vira_metro(tmp_path):
    doc = ezdxf.readfile(_desenho(tmp_path, 0.135))
    r = dx._unidade_por_plausibilidade(doc, 0.001)
    assert r.get("status") == "corrigida_plausibilidade" and r["fator_corrigido"] == 1.0, r
    assert "altura do texto" in r["mensagem"] and "NÃO é prova" in r["mensagem"]


def test_a_extracao_mede_em_metro(tmp_path):
    e = dx.extract_from_file(_desenho(tmp_path, 0.135))
    assert float(e.metadata.get("fator_para_metros")) == 1.0, e.metadata.get("fator_para_metros")
    assert max(w.length for w in e.walls) == pytest.approx(100.0), "a parede de 100 un tem que medir 100 m"
    assert "altura do texto" in (e.metadata.get("unidade_corrigida_por_plausibilidade") or ""), e.metadata


@pytest.mark.parametrize("h,motivo", [
    (2.0, "possível"),       # mm com texto de 2 mm (escala de papel): fica
    (150.0, "possível"),     # mm de verdade: texto de 15 cm
    (0.9, "sem unidade"),    # 0,9: metro (90 cm) ou decímetro (9 cm) — ambíguo, fica
])
def test_CONTROLE_nao_corrige(tmp_path, h, motivo):
    doc = ezdxf.readfile(_desenho(tmp_path, h))
    r = dx._unidade_pela_altura_do_texto(doc, 0.001)
    assert r.get("status") is None and motivo in r.get("motivo", ""), r


def test_CONTROLE_poucos_textos_nao_julga(tmp_path):
    doc = ezdxf.readfile(_desenho(tmp_path, 0.135, n_textos=10))
    r = dx._unidade_pela_altura_do_texto(doc, 0.001)
    assert r.get("status") is None and "textos" in r.get("motivo", ""), r


def test_o_nucleo_continua_decidindo_primeiro(tmp_path, monkeypatch):
    """Quando o núcleo resolve, o texto nem é consultado."""
    monkeypatch.setattr(dx, "_unidade_pelo_nucleo",
                        lambda doc, f: {"status": "corrigida_plausibilidade", "fator_corrigido": 0.01,
                                        "mensagem": "núcleo"})
    monkeypatch.setattr(dx, "_unidade_pela_altura_do_texto",
                        lambda doc, f: pytest.fail("o texto não pode passar na frente do núcleo"))
    r = dx._unidade_por_plausibilidade(None, 0.001)
    assert r["fator_corrigido"] == 0.01
