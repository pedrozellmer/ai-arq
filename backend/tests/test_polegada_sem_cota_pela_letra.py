# -*- coding: utf-8 -*-
"""Polegada declarada sem cota que prove: a altura da letra decide a unidade.

🩸 01/10/2026 — H56 do estudo do acervo, liberado pelo Pedro. Em 120 dias, 5
pranchas declararam polegada, erradas nas DUAS direções: um ar-condicionado
desenhado em mm saiu 25× maior (duto de 22.332 m, real ~879 m — a avaliação
NOTA 1 de 01/09) e uma estrutura em metro saiu 39× menor. A letra entrega:
4 m em polegada é 16 cm em mm; 2,5 mm em polegada é 10 cm em metro.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import aviso_unidade_imperial  # noqa: E402


def _doc(altura, n=40, insunits=1, largura=20000.0):
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = insunits
    msp = d.modelspace()
    for i in range(60):
        x = largura * i / 60.0
        msp.add_line((x, 0), (x + largura / 70.0, largura / 2.0))
    for i in range(n):
        msp.add_text("AMB %d" % i, dxfattribs={"height": altura,
                                                "insert": (largura * i / n, largura / 4.0)})
    return d


@pytest.mark.parametrize("altura,fator,uf,nome", [
    (158.0, 0.001, 0.0254, "polegadas"),   # o ar-condicionado: 4 m em polegada → 16 cm em mm
    (0.1, 1.0, 0.0254, "polegadas"),       # a estrutura: 2,5 mm em polegada → 10 cm em metro
    (150.0, 0.001, 0.3048, "pés"),         # 45,7 m em pé → 15 cm em mm
])
def test_o_caso_unidade_imperial_com_letra_impossivel(altura, fator, uf, nome):
    r = dx._unidade_pela_altura_do_texto(_doc(altura), uf)
    assert r["status"] == "corrigida_plausibilidade" and r["fator_corrigido"] == fator, r
    assert nome in r["mensagem"] and "NÃO é prova" in r["mensagem"], r


@pytest.mark.parametrize("altura,uf,motivo", [
    (4.0, 0.0254, "letra de 10 cm em polegada: possível"),
    (0.5, 0.3048, "letra de 15 cm em pé: possível"),
    (50.0, 0.0254, "1,27 m em polegada; em mm 5 cm e em cm 50 cm: duas unidades, não decide"),
    (5000.0, 1.0, "metro declarado: implantação 1:2000 tem letra de 5 m de verdade"),
    (5000.0, 0.001, "milímetro declarado: a régua imperial não vale"),
])
def test_CONTROLE_nao_corrige(altura, uf, motivo):
    r = dx._unidade_pela_altura_do_texto(_doc(altura), uf)
    assert r["status"] is None, (motivo, r)


def test_CONTROLE_poucos_textos():
    assert dx._unidade_pela_altura_do_texto(_doc(158.0, n=29), 0.0254)["status"] is None


def test_de_ponta_a_ponta_o_ar_condicionado_vira_milimetro(tmp_path):
    p = str(tmp_path / "ac.dxf")
    _doc(158.0).saveas(p)
    md = dx.extract_dxf(p).metadata
    assert float(md["fator_para_metros"]) == 0.001, md.get("fator_para_metros")
    assert "polegadas" in (md.get("unidade_corrigida_por_plausibilidade") or ""), sorted(md)
    assert "25×" not in str(md.get("alerta_unidade") or ""), md.get("alerta_unidade")


def test_CONTROLE_de_ponta_a_ponta_polegada_com_letra_possivel_so_avisa(tmp_path):
    p = str(tmp_path / "pol.dxf")
    _doc(4.0, largura=2000.0).saveas(p)
    md = dx.extract_dxf(p).metadata
    assert float(md["fator_para_metros"]) == 0.0254, md.get("fator_para_metros")
    assert "25×" in str(md.get("alerta_unidade") or md.get("unidade_suspeita") or ""), sorted(md)


@pytest.mark.parametrize("status", ["corrigida_plausibilidade", "corrigida_lfac"])
def test_corrigida_o_aviso_de_polegada_cala(status):
    assert aviso_unidade_imperial(1, status) is None


def test_CONTROLE_sem_correcao_o_aviso_continua():
    assert "25×" in (aviso_unidade_imperial(1, None) or "")
