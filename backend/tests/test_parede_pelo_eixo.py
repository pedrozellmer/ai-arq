# -*- coding: utf-8 -*-
"""Parede desenhada pelas DUAS FACES mede pelo EIXO.

🩸 26/09/2026 — job befab5aa (interiores): a planilha trouxe "pintura
1.977 m²" = "659 m × 3 m de pé-direito, por face". Os 659 m eram a SOMA DAS
LINHAS do layer PAREDE — 79% delas em pares de face (5–30 cm): pelo eixo, a
mesma versão tinha ~383 m. Toda "parede (ml) ✓" de DWG com parede em duas faces
saía 1,5–2× maior; a soma × pé-direito era ≈ as duas faces, não uma.
Mesma máquina do leito/duto (`_corrigir_duto_linha_dupla`), em layer de parede.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import layer_e_parede  # noqa: E402


def _ler(tmp_path, desenha, insunits=6, monkeypatch=None):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = insunits
    desenha(doc.modelspace())
    p = str(tmp_path / "parede.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


def _par(msp, layer, x0, x1, y, esp, k=1.0):
    msp.add_line((x0 * k, y * k), (x1 * k, y * k), dxfattribs={"layer": layer})
    msp.add_line((x0 * k, (y + esp) * k), (x1 * k, (y + esp) * k), dxfattribs={"layer": layer})


# ── o caso ─────────────────────────────────────────────────────────────────────
def test_o_caso_parede_de_duas_faces_mede_o_eixo(tmp_path):
    ex = _ler(tmp_path, lambda m: _par(m, "PAREDE", 0, 10, 0, 0.15))
    assert ex.get_walls_by_layer()["PAREDE"] == pytest.approx(10.0, abs=0.05), "nunca 20 (as duas faces)"


def test_parede_em_polilinha_fechada_mede_o_eixo(tmp_path):
    """O contorno da parede (10 m × 15 cm) — os lados longos pareiam, as pontas
    são tampa. 🪤 Sem os lados da polilinha ela entrava como UMA reta."""
    def d(m):
        m.add_lwpolyline([(0, 0), (10, 0), (10, 0.15), (0, 0.15)], close=True, dxfattribs={"layer": "A-WALL"})
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["A-WALL"] == pytest.approx(10.0, abs=0.05)


def test_desenho_em_milimetro_tambem(tmp_path):
    """🪤 A armadilha do duto (04/08): separação em bruto × comprimento em metro."""
    ex = _ler(tmp_path, lambda m: _par(m, "ALVENARIA", 0, 10, 0, 0.15, k=1000.0), insunits=4)
    assert ex.get_walls_by_layer()["ALVENARIA"] == pytest.approx(10.0, abs=0.05)


def test_a_ia_fica_sabendo_que_a_parede_ja_e_o_eixo(tmp_path):
    ex = _ler(tmp_path, lambda m: _par(m, "PAREDE", 0, 10, 0, 0.15))
    assert "PAREDE" in (ex.metadata.get("parede_linha_dupla") or "")
    assert "eixo" in ex.to_structured_prompt().lower()


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_parede_de_linha_unica_fica(tmp_path):
    def d(m):
        m.add_line((0, 0), (10, 0), dxfattribs={"layer": "PAREDE"})
        m.add_line((0, 3), (6, 3), dxfattribs={"layer": "PAREDE"})
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["PAREDE"] == pytest.approx(16.0)
    assert not ex.metadata.get("parede_linha_dupla")


def test_CONTROLE_layer_de_linha_unica_com_duas_paredes_vizinhas_fica(tmp_path):
    """Drywall desenhado em linha ÚNICA (a convenção do layer): duas paredes que
    correm a 20 cm uma da outra são DUAS — o par é coincidência. Menos da metade
    do layer em par → não mexe."""
    def d(m):
        _par(m, "parede drywall", 0, 5, 0, 0.20)                   # 10 m em "par"
        for k in range(4):
            m.add_line((0, 3 + 2 * k), (8, 3 + 2 * k), dxfattribs={"layer": "parede drywall"})  # 32 m sozinhos
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["parede drywall"] == pytest.approx(42.0)


def test_layer_de_linha_dupla_com_trecho_sozinho_corrige_o_par(tmp_path):
    """A outra ponta: layer em linha DUPLA (mais da metade em par) com um trecho
    sozinho — o par vira eixo, o trecho sozinho fica."""
    def d(m):
        _par(m, "PAREDE", 0, 10, 0, 0.15)                          # 20 m em par
        m.add_line((0, 5), (4, 5), dxfattribs={"layer": "PAREDE"})   # 4 m sozinho
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["PAREDE"] == pytest.approx(14.0, abs=0.05)


def test_CONTROLE_paredes_a_60_cm_sao_duas(tmp_path):
    """Acima de 40 cm não é a espessura de UMA parede: são duas."""
    ex = _ler(tmp_path, lambda m: _par(m, "PAREDE", 0, 10, 0, 0.60))
    assert ex.get_walls_by_layer()["PAREDE"] == pytest.approx(20.0)


@pytest.mark.parametrize("layer", ["ELETRODUTO PAREDE", "PAREDE-HACHURA", "LAYOUT", "COTAS"])
def test_CONTROLE_layer_que_nao_e_o_traco_da_parede_nao_pareia(tmp_path, layer):
    """Eletroduto é linha ÚNICA (dois paralelos são dois tubos); hachura, layout e
    cota não são parede — parear cortaria pela metade uma medição certa."""
    ex = _ler(tmp_path, lambda m: _par(m, layer, 0, 10, 0, 0.20))
    assert ex.get_walls_by_layer()[layer] == pytest.approx(20.0)


def test_CONTROLE_duto_continua_como_era(tmp_path):
    ex = _ler(tmp_path, lambda m: _par(m, "DUTO INSUFLAMENTO", 0, 10, 0, 0.80))
    assert ex.get_walls_by_layer()["DUTO INSUFLAMENTO"] == pytest.approx(10.0, abs=0.05)


@pytest.mark.parametrize("nome, e", [
    ("PAREDE", True), ("Paredes", True), ("A-WALL", True), ("ARQ - ALV", True),
    ("00_PAREDE", True), ("parede drywall", True), ("PAREDE A DEMOLIR", True),
    ("A-WALL-PATT", False), ("A-WALL-FNSH", False), ("PAREDE-HACHURA", False),
    ("ELETRODUTO PAREDE", False), ("HIDR-PAREDE", False), ("Revestimento parede", False),
    ("LUMINOTECNICO PAREDE", False), ("TOMADAS PAREDE", False), ("ELETRICA PAREDE", False),
    ("LEITO PAREDE", False),
    ("WALLPAPER", False), ("LAYOUT", False),
])
def test_o_nome_do_layer_de_parede(nome, e):
    assert layer_e_parede(nome) is e
