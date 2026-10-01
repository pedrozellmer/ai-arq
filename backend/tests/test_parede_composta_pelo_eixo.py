# -*- coding: utf-8 -*-
"""Parede COMPOSTA (face, reboco, bloco, reboco, face) mede pelo eixo.

🩸 01/10/2026 — H73 do estudo do acervo. O Revit exporta a parede composta em
4 linhas: o reboco fica a 2–5 cm da face, abaixo da separação mínima do par.
Só as duas linhas do meio pareavam e as faces entravam inteiras (3 de 4
linhas), ou o layer caía na zona cinza e somava as 4. Numa escola o
pavimento superior tem ~363 m de parede, e a entrega de 23/09 disse
"Alvenaria 1.419,73 ml ✓" (3,9×). A linha a até 5 cm da vizinha é a MESMA face.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _ler(tmp_path, desenha, insunits=6):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = insunits
    desenha(doc.modelspace())
    p = str(tmp_path / "parede.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


def _linhas(msp, layer, x0, x1, ys, k=1.0):
    for y in ys:
        msp.add_line((x0 * k, y * k), (x1 * k, y * k), dxfattribs={"layer": layer})


# ── o caso ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ys,motivo", [
    ((0, 0.025, 0.165, 0.19), "reboco de 2,5 cm dos dois lados"),
    ((0, 0.05, 0.20, 0.25), "reboco de 5 cm: no limite, ainda é a face"),
    ((0, 0.02, 0.17), "reboco de um lado só (3 linhas)"),
])
def test_o_caso_parede_composta_mede_o_eixo(tmp_path, ys, motivo):
    ex = _ler(tmp_path, lambda m: _linhas(m, "A-WALL", 0, 10, ys))
    assert ex.get_walls_by_layer()["A-WALL"] == pytest.approx(10.0, abs=0.05), motivo


def test_parede_grossa_a_face_de_fora_passa_dos_40_cm_da_outra(tmp_path):
    """Alvenaria de 38 cm com reboco de 3 cm por fora: a face de fora fica a
    41 cm da de dentro — longe demais pra parear sozinha. É a mesma face do
    reboco, então entra pelo reboco."""
    ex = _ler(tmp_path, lambda m: _linhas(m, "PAREDE", 0, 10, (0, 0.03, 0.41)))
    assert ex.get_walls_by_layer()["PAREDE"] == pytest.approx(10.0, abs=0.05)


def test_parede_composta_em_milimetro(tmp_path):
    ex = _ler(tmp_path, lambda m: _linhas(m, "PAREDE", 0, 10, (0, 0.025, 0.165, 0.19), k=1000.0),
              insunits=4)
    assert ex.get_walls_by_layer()["PAREDE"] == pytest.approx(10.0, abs=0.05)


def test_a_composta_sai_da_zona_cinza(tmp_path):
    """Composta + uma parede de linha única: antes 2 das 4 linhas em par (43% do
    layer) → zona cinza, somava tudo (46 m) e ficava sem selo. Agora as 4 são
    face de um par: 10 m pelo eixo + 6 m da linha única."""
    def d(m):
        _linhas(m, "PAREDE", 0, 10, (0, 0.025, 0.165, 0.19))
        _linhas(m, "PAREDE", 0, 6, (5,))
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["PAREDE"] == pytest.approx(16.0, abs=0.05)
    assert "PAREDE" not in (ex.metadata.get("parede_zona_cinza") or {})


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_parede_de_duas_faces_igual(tmp_path):
    ex = _ler(tmp_path, lambda m: _linhas(m, "PAREDE", 0, 10, (0, 0.15)))
    assert ex.get_walls_by_layer()["PAREDE"] == pytest.approx(10.0, abs=0.05)


def test_CONTROLE_duas_paredes_vizinhas_continuam_duas(tmp_path):
    """Duas paredes de 15 cm com 10 cm de vão entre elas: 4 linhas, nenhuma a
    ≤ 5 cm da outra. São DUAS paredes — a régua do feixe largo juntaria."""
    ex = _ler(tmp_path, lambda m: _linhas(m, "PAREDE", 0, 10, (0, 0.15, 0.25, 0.40)))
    assert ex.get_walls_by_layer()["PAREDE"] == pytest.approx(20.0, abs=0.05)


def test_CONTROLE_linha_fina_sem_par_nao_e_tocada(tmp_path):
    """Duas linhas a 3 cm, sem parceira: não há par, então não há face a juntar
    — fica como era (as duas contam). Só a parede de duas faces vira eixo."""
    def d(m):
        _linhas(m, "PAREDE", 0, 10, (0, 0.15))
        _linhas(m, "PAREDE", 0, 5, (5, 5.03))
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["PAREDE"] == pytest.approx(20.0, abs=0.05)


def test_CONTROLE_linha_que_so_encosta_na_ponta_nao_e_reboco(tmp_path):
    """Uma linha a 2 cm da face que só cruza o último metro da parede (segue
    outro elemento até x=20): não corre junto com a face — não é reboco, conta
    inteira. Parede 10 m pelo eixo + a linha de 11 m."""
    def d(m):
        _linhas(m, "PAREDE", 0, 10, (0, 0.15))
        _linhas(m, "PAREDE", 9, 20, (0.02,))
    ex = _ler(tmp_path, d)
    assert ex.get_walls_by_layer()["PAREDE"] == pytest.approx(21.0, abs=0.05)


def test_CONTROLE_duto_nao_junta_face_fina():
    """A junção é só da PAREDE. O duto continua com a régua dele (isolamento a
    2 cm não vira face)."""
    from types import SimpleNamespace as NS
    ys = (0, 0.02, 0.32, 0.34)
    walls = [NS(layer="DUTO AR", start=(0.0, y), end=(10.0, y), length=10.0, pontos=(),
                curvo=False) for y in ys]
    novos, _, _ = dx._corrigir_duto_linha_dupla(walls, 1.0)
    assert sum(w.length for w in novos) == pytest.approx(30.0, abs=0.05)
    novos_j, _, _ = dx._corrigir_duto_linha_dupla(walls, 1.0, junta_face_fina=True)
    assert sum(w.length for w in novos_j) == pytest.approx(10.0, abs=0.05)
