# -*- coding: utf-8 -*-
"""A marca de corte desenhada NA planta não é o título da planta.

🩸 30/09/2026 — H54 do estudo do acervo. Na planta do Revit, as marcas
"CORTE 1" / "CORTE 2" são a maior letra da região e viravam o título dela →
'vista': 84,86 m² do piso da casa saíram como "superfície vista de lado, NÃO é
piso". Noutra casa, a marca "ELEVAÇÃO" fez o mesmo com a planta do térreo.
Contraexemplos que o estudo mediu e que NÃO podem mudar: o esquema de prumada
com 30 nomes de ambiente (título descritivo), os cortes estruturais com rótulos
P/V/L e os cortes do Revit com etiqueta de ambiente.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
from engine_rules import tipo_do_desenho  # noqa: E402
from test_a_leitura_por_folha import _viewport  # noqa: E402


def _regiao(msp, x0, titulos, ambientes, h_tit=0.3, h_amb=0.2):
    for i, t in enumerate(titulos):
        msp.add_text(t, dxfattribs={"height": h_tit, "insert": (x0 + 2 + 6 * i, 2)})
    for i, a in enumerate(ambientes):
        msp.add_text(a, dxfattribs={"height": h_amb, "insert": (x0 + 2 + 4 * (i % 4), 6 + 3 * (i // 4))})
    msp.add_line((x0 + 1, 1), (x0 + 18, 1))


def _mapa(regioes, papel_abaixo=None):
    """regioes: [(titulos, ambientes)], uma folha e uma janela por região."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for k, (tits, ambs) in enumerate(regioes):
        x0 = 40.0 * k
        _regiao(msp, x0, tits, ambs)
        lay = doc.layouts.new("F%d" % k)
        _viewport(lay, (x0, 0, x0 + 20, 15))
        if papel_abaixo:
            # texto no PAPEL logo abaixo da janela (centro 200,150; 200 × 150 de papel)
            lay.add_text(papel_abaixo, dxfattribs={"height": 5, "insert": (105, 70)})
    m = dx.mapa_de_folhas(doc)
    return sorted(m["folhas"], key=lambda f: f["caixa"][0])


_CASA = ["QUARTO", "SALA", "COZINHA", "BANHEIRO"]


@pytest.mark.parametrize("marcas", [["CORTE 1", "CORTE 2"], ["ELEVAÇÃO"], ["CORTE A-A"], ["Corte 1"]])
def test_o_caso_marca_de_corte_na_planta_nao_vira_vista(marcas):
    (f,) = _mapa([(marcas, _CASA)])
    assert f["tipo"] != "vista" and f["tipo"] == "", f
    assert "4 ambientes" in f.get("marca_na_planta", ""), f


@pytest.mark.parametrize("ambs", [["ESTAR/JANTAR/COZINHA A= 26,13 m²", "DORMITÓRIO 9,15", "SUÍTE 9,76",
                                   "GARAGEM 10,10", "I.S."],
                                  ["SALA / COZINHA 52 m2", "DORMITORIO 33 m2", "ÁREA DE SERVIÇO"]])
def test_os_nomes_de_ambiente_dos_casos(ambs):
    (f,) = _mapa([(["ELEVAÇÃO"], ambs)])
    assert f["tipo"] == "" and f.get("marca_na_planta"), f


def test_o_papel_de_baixo_tambem_nao_decide_a_planta_com_marca():
    (f,) = _mapa([(["CORTE 1"], _CASA)], papel_abaixo="CORTE 3")
    assert f["tipo"] == "", f


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_corte_de_verdade_segue_vista():
    (f,) = _mapa([(["CORTE AA"], [])])
    assert f["tipo"] == "vista", f


def test_CONTROLE_menos_de_3_ambientes_segue_vista():
    (f,) = _mapa([(["ELEVAÇÃO"], ["QUARTO", "SALA"])])
    assert f["tipo"] == "vista", f


def test_CONTROLE_titulo_descritivo_com_muitos_ambientes_nao_muda():
    # o esquema de prumada: 30 nomes de ambiente, mas o título DIZ o que é
    ambs = ["QUARTO %d" % i for i in range(1, 11)] + ["SALA %d" % i for i in range(1, 11)]
    (f,) = _mapa([(["ESQUEMA VERTICAL DE ÁGUA FRIA"], ambs)])
    assert tipo_do_desenho("ESQUEMA VERTICAL DE ÁGUA FRIA") == "fora"
    assert f["tipo"] == "fora" and not f.get("marca_na_planta"), f


def test_CONTROLE_marca_junto_de_titulo_descritivo_nao_muda():
    (f,) = _mapa([(["CORTE 1", "CORTE LONGITUDINAL DO GALPÃO"], _CASA)])
    assert not f.get("marca_na_planta"), f


@pytest.mark.parametrize("texto", ["ESTARTER", "SALAMANDRA", "COPAIBA", "HALLS"])
def test_CONTROLE_palavra_que_so_comeca_com_ambiente_nao_conta(texto):
    assert not dx._RE_NOME_DE_AMBIENTE.match(texto)
