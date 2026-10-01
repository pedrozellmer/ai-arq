# -*- coding: utf-8 -*-
"""Unidade imperial num desenho em coordenada UTM: é metro.

🩸 01/10/2026 — H63 do estudo do acervo. Um loteamento declarava PÉS, sem
cota, e a letra cabia nas duas unidades. O desenho estava em UTM (leste ~245
mil, norte ~8,98 milhões) — UTM é metro. A entrega saiu 3,3× menor no
comprimento e 10,8× na área.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import aviso_unidade_imperial  # noqa: E402


def _doc(x0, y0, insunits=2, n=600, lado=800.0):
    """Uma malha de ruas: 2n pontos em volta de (x0, y0), letra de 1,3 un."""
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = insunits
    msp = d.modelspace()
    for i in range(n):
        x = x0 + lado * i / n
        msp.add_line((x, y0), (x + lado / 50.0, y0 + lado / 2.0), dxfattribs={"layer": "MEIO-FIO"})
    for i in range(40):
        msp.add_text("RUA %d" % i, dxfattribs={"height": 1.3,
                                               "insert": (x0 + lado * i / 40, y0 + lado / 4)})
    return d


@pytest.mark.parametrize("uf,nome", [(0.3048, "pés"), (0.0254, "polegadas")])
def test_o_caso_imperial_em_utm_vira_metro(uf, nome):
    r = dx._unidade_pela_coordenada_utm(_doc(244_847, 8_982_516), uf)
    assert r["status"] == "corrigida_plausibilidade" and r["fator_corrigido"] == 1.0, r
    assert nome in r["mensagem"] and "UTM" in r["mensagem"] and "NÃO é prova" in r["mensagem"]
    assert "8.982." in r["mensagem"], r["mensagem"]


def test_a_cascata_da_plausibilidade_chama_o_utm():
    r = dx._unidade_por_plausibilidade(_doc(244_847, 8_982_516), 0.3048)
    assert r["status"] == "corrigida_plausibilidade" and r["fator_corrigido"] == 1.0, r


@pytest.mark.parametrize("x0,y0,uf,motivo", [
    (0, 0, 0.3048, "pés em coordenada local: nada a dizer"),
    (244_847, 8_982_516, 1.0, "metro declarado: a régua é só pra imperial"),
    (244_847, 8_982_516, 0.001, "mm declarado: idem"),
    (500_000, 300_000, 0.3048, "norte de 300 km: hemisfério norte confunde, fica de fora"),
    (1_500_000, 8_982_516, 0.3048, "leste fora da faixa UTM"),
    (244_847, 5_000_000, 0.3048, "norte abaixo do sul do Brasil"),
])
def test_CONTROLE_nao_corrige(x0, y0, uf, motivo):
    r = dx._unidade_pela_coordenada_utm(_doc(x0, y0), uf)
    assert r["status"] is None, (motivo, r)


def test_CONTROLE_poucos_pontos():
    r = dx._unidade_pela_coordenada_utm(_doc(244_847, 8_982_516, n=100), 0.3048)
    assert r["status"] is None, r


def test_CONTROLE_so_parte_do_desenho_em_utm():
    """Metade do núcleo perto da origem: não é desenho georreferenciado."""
    d = _doc(244_847, 8_982_516, n=300)
    for i in range(400):
        d.modelspace().add_line((i, 0), (i + 1, 1))
    assert dx._unidade_pela_coordenada_utm(d, 0.3048)["status"] is None


def test_de_ponta_a_ponta_o_loteamento_sai_em_metro(tmp_path):
    p = str(tmp_path / "lote.dxf")
    _doc(244_847, 8_982_516).saveas(p)
    md = dx.extract_dxf(p).metadata
    assert float(md["fator_para_metros"]) == 1.0, md.get("fator_para_metros")
    assert "UTM" in (md.get("unidade_corrigida_por_plausibilidade") or ""), sorted(md)
    assert aviso_unidade_imperial(1, md.get("regua_cotas_status")) is None
