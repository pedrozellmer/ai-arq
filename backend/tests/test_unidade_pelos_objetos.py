# -*- coding: utf-8 -*-
"""Sem unidade no cabeçalho, quando cm E metro cabem na largura, os OBJETOS
do desenho desempatam — e, sem cota que prove, m/m²/m³ saem estimados.

🩸 29/09/2026 (job 6437838e). DWG elétrico sem $INSUNITS, 1.584 unidades de
largura (8 pranchas lado a lado no modelo). cm dava 15,8 m, metro 1,58 km —
os dois "plausíveis" — e a regra ficava com o menor: cm. Estava em METROS (a
mesa "CONJ MESA 1.40M" mede 1,400; a vaga, 5,0 × 3,7; a bacia, 0,62): todo
comprimento saiu 100× pequeno e o detector de planta repetida, que trabalha
em metros, não enxergou as 5 cópias da planta.
📏 Acervo local (90 DXF): onde o voto decidiu entre cm e m, acertou todos os
que declaravam cm ou m e os 2 que declaravam mm mas eram metro. Em 90 dias de
produção, 2 desenhos caíram na faixa ambígua — os 2 eram metro.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402

#: tamanhos de objeto em METROS (tomada, luminária, bacia, pia, cadeira, mesa,
#: porta, vaga, carro, elevador)
OBJETOS_M = [0.23, 0.26, 0.62, 0.48, 0.58, 1.40, 0.90, 5.0, 4.6, 2.8]


def _doc(insunits, largura, objetos=None, escala=1.0, n_linhas=600):
    d = ezdxf.new("R2010")
    d.header["$INSUNITS"] = insunits
    msp = d.modelspace()
    passo = largura / n_linhas
    for i in range(n_linhas):
        msp.add_line((i * passo, 0), ((i + 1) * passo, 1))
    for k, t in enumerate(objetos or []):
        lado = t * escala
        blk = d.blocks.new(name="OBJ%02d" % k)
        blk.add_lwpolyline([(0, 0), (lado, 0), (lado, lado * 0.6), (0, lado * 0.6)], close=True)
        for j in range(3):
            msp.add_blockref("OBJ%02d" % k, (10 + k * 7 + j, 20 + j))
    d.header["$EXTMIN"] = (0.0, 0.0, 0.0)
    d.header["$EXTMAX"] = (largura, largura * 0.3, 0.0)
    # 🪤 o `saveas` do ezdxf regrava o cabeçalho com a extensão do MODELO
    msp.dxf.extmin = (0.0, 0.0, 0.0)
    msp.dxf.extmax = (largura, largura * 0.3, 0.0)
    return d


# ══════════════════════════════════════════════════════════════════════════
#  1. A faixa ambígua: os objetos decidem
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_objetos_em_metro_decidem_metro():
    d = _doc(0, 1584, OBJETOS_M)
    assert dx._detect_unit_factor(d) == 1.0


def test_objetos_em_centimetro_decidem_centimetro():
    d = _doc(0, 1584, OBJETOS_M, escala=100.0)
    assert dx._detect_unit_factor(d) == 0.01


def test_o_voto_vai_pro_log_do_cabecalho():
    diag = dx._diag_unidade_cabecalho(_doc(0, 1584, OBJETOS_M))
    assert diag.get("objetos", {}).get("escolha") == 1.0, diag
    assert diag["objetos"]["tipos"] == len(OBJETOS_M)


@pytest.mark.parametrize("objetos, escala", [
    (OBJETOS_M[:7], 1.0),                                   # < 8 tipos: não é evidência
    (OBJETOS_M[:5] + [t * 100 for t in OBJETOS_M[5:]], 1.0),  # meio a meio: sem margem
])
def test_CONTROLE_sem_voto_claro_fica_o_menor_como_antes(objetos, escala):
    assert dx._detect_unit_factor(_doc(0, 1584, objetos, escala)) == 0.01


def test_CONTROLE_sem_bloco_nenhum_fica_o_menor_como_antes():
    assert dx._detect_unit_factor(_doc(0, 1200)) == 0.01


# ══════════════════════════════════════════════════════════════════════════
#  2. Fora da faixa ambígua nada muda
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("insunits, largura, esperado", [
    (0, 500, 1.0),          # só metro cabe: não vota
    (0, 20000, 0.001),      # mm plausível: não encosta
    (4, 1584, 0.001),       # declarado mm
    (5, 1584, 0.01),        # declarado cm
    (6, 1584, 1.0),         # declarado m
])
def test_CONTROLE_fora_da_duvida_os_objetos_nao_votam(insunits, largura, esperado):
    # objetos em CENTÍMETRO: se votassem, puxariam pra 0,01
    d = _doc(insunits, largura, OBJETOS_M, escala=100.0)
    assert dx._detect_unit_factor(d) == esperado


# ══════════════════════════════════════════════════════════════════════════
#  3. A ressalva: sem cota que prove, metro não sai medido
# ══════════════════════════════════════════════════════════════════════════
def test_a_ressalva_do_desempate():
    voto = ((0.01, 1.0), (1.0, {"tipos": 75, "fracoes": {"0.01": 0.13, "1.0": 0.96}}))
    txt = dx.ressalva_da_unidade_por_desempate(voto, "nao-decidiu")
    assert "metro" in txt and "96%" in txt, txt
    md = {"unidade_por_desempate": txt}
    assert er.extraction_has_quality_caveat(md) is True
    assert er.caveat_atinge_unidade(md, "m") is True
    assert er.caveat_atinge_unidade(md, "un") is False


def test_a_ressalva_sem_voto_diz_que_ficou_em_centimetro():
    voto = ((0.01, 1.0), (None, {"tipos": 3}))
    assert "centímetro" in dx.ressalva_da_unidade_por_desempate(voto, "nao-decidiu")


@pytest.mark.parametrize("voto, status", [
    (((0.01, 1.0), (1.0, {"fracoes": {"1.0": 0.9}})), "validada"),   # as cotas provaram
    (((0.01, 1.0), (1.0, {"fracoes": {"1.0": 0.9}})), "corrigida"),
    (None, "nao-decidiu"),                                             # não houve desempate
])
def test_CONTROLE_cota_que_prova_ou_sem_desempate_nao_ha_ressalva(voto, status):
    assert dx.ressalva_da_unidade_por_desempate(voto, status) == ""


def test_de_ponta_a_ponta_a_extracao_marca_a_ressalva(tmp_path):
    p = str(tmp_path / "planta.dxf")
    _doc(0, 1584, OBJETOS_M).saveas(p)
    md = dx.extract_dxf(p).metadata
    assert float(md.get("fator_para_metros")) == 1.0, md.get("fator_para_metros")
    assert md.get("unidade_por_desempate"), sorted(md)
    assert er.caveat_atinge_unidade(md, "m") is True
    assert er.caveat_atinge_unidade(md, "un") is False


def test_CONTROLE_de_ponta_a_ponta_unidade_declarada_nao_ganha_ressalva(tmp_path):
    p = str(tmp_path / "planta.dxf")
    _doc(6, 1584, OBJETOS_M).saveas(p)
    md = dx.extract_dxf(p).metadata
    assert not md.get("unidade_por_desempate"), md.get("unidade_por_desempate")
