# -*- coding: utf-8 -*-
"""Bloco espelhado no eixo Z fica onde aparece, não no x com sinal trocado.

🩸 27/09/2026 (estudo de leitura, item 8): o ponto de inserção do INSERT está
no OCS da peça. Com a extrusão (0,0,-1), o x do OCS é o do desenho com o sinal
trocado — no R17, IC e CG (8 + 8) caíam em −76 m em vez de +76 m, fora de
qualquer folha, e a leitura por folha os tratava como peça solta.
"""
import os
import sys

import ezdxf

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _arquivo(tmp_path, pecas):
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    doc.blocks.new("IC").add_circle((0, 0), 0.2)
    for x_ocs, y, extr in pecas:
        msp.add_blockref("IC", (x_ocs, y), dxfattribs={"extrusion": extr})
    p = str(tmp_path / "espelho.dxf")
    doc.saveas(p)
    return p


def test_a_posicao_do_bloco_espelhado_e_a_do_desenho(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    # no OCS de extrusão (0,0,-1) o x = -76,2 aparece no desenho em +76,2
    p = _arquivo(tmp_path, [(-76.2, 13.0, (0, 0, -1)), (40.0, 13.0, (0, 0, 1))])
    ic = next(b for b in dx.extract_dxf(p).blocks if b.name == "IC")
    assert sorted(ic.positions) == [(40.0, 13.0), (76.2, 13.0)], ic.positions


def test_CONTROLE_espelhada_no_mesmo_lugar_e_outra_peca(tmp_path, monkeypatch):
    """A cópia idêntica no mesmo ponto conta 1 (3ad7d38). Uma espelhada e uma
    normal no MESMO ponto do desenho são duas peças: o lado virado entra na
    chave junto com a posição."""
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    p = _arquivo(tmp_path, [(-5.0, 5.0, (0, 0, -1)), (5.0, 5.0, (0, 0, 1))])
    ic = next(b for b in dx.extract_dxf(p).blocks if b.name == "IC")
    assert ic.count == 2, ic.positions
