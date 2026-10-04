# -*- coding: utf-8 -*-
"""O layer genérico "ARQUITETURA" entra na régua da espessura do H51 (H95, 04/10/2026).

🩸 Num projeto do acervo, desenhado em CENTÍMETRO e declarado MILÍMETRO, as
paredes estavam em "4 - ARQUITETURA 01..06" (layers de espessura de pena, não
de andar). O H51 (a parede de 1,5 cm desmente a unidade) só olhava layer com
NOME de parede e não viu nada: 6 linhas de alvenaria saíram ✓ com a unidade
errada (de 0,05× a ~6× por linha). Antes × depois do extract nos 342 DXF do
acervo: com o layer genérico na régua, muda só esse desenho; nenhuma soma muda e
não há alarme falso (o par a 1,5–2 cm de reboco/revestimento em mm de verdade é
vetado pela letra plausível).
Só REBAIXA: é a mesma ressalva de escala do H51; nenhuma quantidade muda.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402
from test_parede_desmente_a_unidade import _faces, _textos  # noqa: E402


def _md(tmp_path, faces, layer, insunits=4, extra=None):
    d = ezdxf.new("R2010")
    d.header["$INSUNITS"] = insunits
    msp = d.modelspace()
    for a, b in faces:
        msp.add_line(a, b, dxfattribs={"layer": layer})
    if extra:
        extra(msp)
    p = str(tmp_path / "planta.dxf")
    d.saveas(p)
    return dx.extract_dxf(p).metadata


# ══════════════════════════════════════════════════════════════════════════
#  1. O nome
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("nome", ["4 - ARQUITETURA 01", "ARQUITETURA", "ARQ_ARQUITETURA", "Arquitetura - Térreo"])
def test_layer_generico_de_arquitetura_entra(nome):
    assert er.layer_de_arquitetura(nome)


@pytest.mark.parametrize("nome", ["arquiteturapaisagismo", "ARQUITETURA - MOBILIARIO", "ARQUITETURA_LAYOUT",
                                  "ARQUITETURA PISO", "ARQUITETURA REVESTIMENTO", "ARQUITETURA COTAS",
                                  "Arquitetura - Paisagismo", "ARQUITETURA EQUIPAMENTOS", "4 - ESTRUTURA 01", ""])
def test_o_que_nao_e_parede_no_layer_de_arquitetura_fica_fora(nome):
    assert not er.layer_de_arquitetura(nome)


def test_so_a_regua_da_espessura_ve_o_layer_de_arquitetura():
    """O layer de arquitetura NÃO vira parede no resto do motor."""
    assert not er.layer_e_parede("4 - ARQUITETURA 01")


# ══════════════════════════════════════════════════════════════════════════
#  2. De ponta a ponta (extract_dxf)
# ══════════════════════════════════════════════════════════════════════════
def test_parede_em_cm_declarada_mm_no_layer_de_arquitetura_dispara(tmp_path):
    md = _md(tmp_path, _faces(), "4 - ARQUITETURA 01")
    assert "1,5 cm" in (md.get("unidade_contradita_pela_parede") or ""), sorted(md)
    assert er.extraction_has_quality_caveat(md)


@pytest.mark.parametrize("layer", ["ARQUITETURA - MOBILIARIO", "arquiteturapaisagismo", "ARQUITETURA PISO",
                                   "4 - ESTRUTURA 01"])
def test_CONTROLE_o_mesmo_desenho_em_layer_que_nao_conta_nao_dispara(tmp_path, layer):
    md = _md(tmp_path, _faces(), layer)
    assert not md.get("unidade_contradita_pela_parede"), md.get("unidade_contradita_pela_parede")


def test_reboco_a_1_5_cm_em_mm_de_verdade_com_letra_plausivel_e_vetado(tmp_path):
    """O par a 1,5 cm de reboco/revestimento num desenho em mm certo: a letra de 15 cm veta."""
    md = _md(tmp_path, _faces(u=10.0, esp=1.5), "ARQUITETURA", extra=_textos(150.0))
    assert not md.get("unidade_contradita_pela_parede"), md.get("unidade_contradita_pela_parede")


def test_CONTROLE_sem_a_letra_o_mesmo_reboco_disparava(tmp_path):
    """É o veto da letra que segura o caso acima (sem texto, a régua sozinha dispararia)."""
    md = _md(tmp_path, _faces(u=10.0, esp=1.5), "ARQUITETURA")
    assert md.get("unidade_contradita_pela_parede"), sorted(md)


def test_layer_de_arquitetura_em_metro_certo_nao_dispara(tmp_path):
    md = _md(tmp_path, _faces(u=0.01), "4 - ARQUITETURA 01", insunits=6)
    assert not md.get("unidade_contradita_pela_parede"), md.get("unidade_contradita_pela_parede")


def test_o_layer_de_parede_de_hoje_continua_igual(tmp_path):
    md = _md(tmp_path, _faces(), "PAREDE")
    assert "1,5 cm" in (md.get("unidade_contradita_pela_parede") or ""), sorted(md)
