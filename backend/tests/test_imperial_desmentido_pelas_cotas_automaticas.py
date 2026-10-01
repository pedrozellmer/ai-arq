# -*- coding: utf-8 -*-
"""Unidade imperial que as cotas automáticas desmentem vira plausibilidade.

🩸 01/10/2026 — H74 do estudo do acervo. Um refeitório declara POLEGADA, sem
cota digitada, com 109 cotas automáticas medindo 0,8–2,0 (vãos e portas em
METRO): lido em polegada, sairia 39× menor. Fora do imperial o mesmo sinal erra
(folha de detalhe com furação de 40 cm qualifica metro) — daí as travas.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import aviso_unidade_imperial  # noqa: E402


def _doc(insunits=1, n=40, base=0.9, passo=0.03):
    """`n` cotas automáticas de base+passo·i unidades, numa planta de 100 × 60."""
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = insunits
    msp = d.modelspace()
    for x0, y0, x1, y1 in ((0, 0, 100, 0), (100, 0, 100, 60), (100, 60, 0, 60), (0, 60, 0, 0)):
        msp.add_line((x0, y0), (x1, y1))
    for i in range(n):
        x, y = (i % 10) * 9.0, (i // 10) * 12.0 + 2.0
        L = base + passo * i
        msp.add_linear_dim(base=(x, y + 1.0), p1=(x, y), p2=(x + L, y)).render()
    return d


def test_o_caso_polegada_com_cotas_de_vao_em_metro():
    d = _doc()
    reg = dx._validate_unit_by_dimensions(d, 0.0254)
    r = dx._unidade_pelas_cotas_automaticas(reg, 0.0254)
    assert r["status"] == "corrigida_plausibilidade" and r["fator_corrigido"] == 1.0, (reg, r)
    assert "polegadas" in r["mensagem"] and "NÃO é prova" in r["mensagem"]


def test_a_cascata_chama_a_regua_das_cotas():
    d = _doc()
    reg = dx._validate_unit_by_dimensions(d, 0.0254)
    r = dx._unidade_por_plausibilidade(d, 0.0254, cotas=reg)
    assert r["status"] == "corrigida_plausibilidade" and r["fator_corrigido"] == 1.0, r


def test_de_ponta_a_ponta_o_refeitorio_sai_em_metro(tmp_path):
    p = str(tmp_path / "refeitorio.dxf")
    _doc().saveas(p)
    md = dx.extract_dxf(p).metadata
    assert float(md["fator_para_metros"]) == 1.0, md.get("fator_para_metros")
    assert "cotas automáticas" in (md.get("unidade_corrigida_por_plausibilidade") or ""), sorted(md)
    assert aviso_unidade_imperial(1, md.get("regua_cotas_status")) is None


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("insunits,uf,motivo", [
    (6, 1.0, "metro declarado: a régua é só do imperial"),
    (4, 0.001, "mm declarado: idem"),
])
def test_CONTROLE_unidade_metrica_nao_entra(insunits, uf, motivo):
    d = _doc(insunits=insunits)
    reg = dx._validate_unit_by_dimensions(d, uf)
    assert dx._unidade_pelas_cotas_automaticas(reg, uf)["status"] is None, motivo


def test_CONTROLE_poucas_cotas():
    d = _doc(n=20)
    reg = dx._validate_unit_by_dimensions(d, 0.0254)
    assert dx._unidade_pelas_cotas_automaticas(reg, 0.0254)["status"] is None


def test_CONTROLE_folha_de_detalhe_com_mediana_de_40():
    """Furação de 40 unidades: em metro daria 40 m de mediana — é detalhe em cm,
    não vão. Não decide."""
    d = _doc(base=38.0, passo=0.1)
    reg = dx._validate_unit_by_dimensions(d, 0.0254)
    assert dx._unidade_pelas_cotas_automaticas(reg, 0.0254)["status"] is None, reg


@pytest.mark.parametrize("quals", [
    [],
    [{"fator": 1.0, "n": 40, "mediana_m": 1.4}, {"fator": 0.01, "n": 40, "mediana_m": 0.9}],
])
def test_CONTROLE_nenhum_ou_dois_fatores_nao_decide(quals):
    r = dx._unidade_pelas_cotas_automaticas({"qualificados": quals}, 0.0254)
    assert r["status"] is None, r


def test_CONTROLE_sem_regua_de_cotas():
    assert dx._unidade_pelas_cotas_automaticas(None, 0.3048)["status"] is None
