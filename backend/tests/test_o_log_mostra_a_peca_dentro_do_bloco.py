# -*- coding: utf-8 -*-
"""O log mostra a peça que está DENTRO de um bloco com nome — e não conta.

📏 28/09/2026 (estudo de leitura, item 5 — aninhados): o bloco "banheiro tipo
1" contava 3 e os 12 vasos de dentro dele sumiam da contagem (job dd52081b).
Antes de mexer na contagem, o log diz quanto isso pesa.
"""
import os
import sys

import ezdxf

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _arquivo(tmp_path):
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    doc.layers.add("BASE-CONGELADA").freeze()
    for n in ("VASO", "CHUVEIRO", "RALO"):
        doc.blocks.new(n).add_circle((0, 0), 0.2)
    ban = doc.blocks.new("BANHEIRO-T1")
    ban.add_blockref("VASO", (0, 0))
    ban.add_blockref("VASO", (2, 0))
    ban.add_blockref("CHUVEIRO", (1, 1))
    ban.add_blockref("RALO", (1, 2), dxfattribs={"layer": "BASE-CONGELADA"})
    mod = doc.blocks.new("TORRE_rvt-1-PLANTA")
    mod.add_blockref("VASO", (0, 0))
    for k in range(3):
        msp.add_blockref("BANHEIRO-T1", (10 * k, 0))
    msp.add_blockref("TORRE_rvt-1-PLANTA", (0, 50))
    msp.add_blockref("VASO", (0, 80))
    p = str(tmp_path / "aninhados.dxf")
    doc.saveas(p)
    return p


def test_os_filhos_aparecem_multiplicados_pelo_pai(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    ex = dx.extract_dxf(_arquivo(tmp_path))
    an = ex.metadata["procedencia_blocos"]["aninhados"]
    assert an["BANHEIRO-T1"] == {"VASO": 6, "CHUVEIRO": 3, "RALO (desl)": 3}, an
    assert "TORRE_rvt-1-PLANTA (vínculo)" in an, an


def test_so_registra_a_contagem_nao_muda(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert ex.get_block_summary().get("VASO") == 1      # só o solto, como antes


def test_a_linha_do_log_leva_os_aninhados():
    import main as m

    class _Ex:
        metadata = {"procedencia_blocos": {"aninhados": {"BANHEIRO-T1": {"VASO": 6, "CHUVEIRO": 3}}}}
    assert "aninhados=[BANHEIRO-T1>VASO=6,CHUVEIRO=3]" in m._procedencia_dos_blocos(_Ex())
