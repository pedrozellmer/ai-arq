# -*- coding: utf-8 -*-
"""Parede em PARTE desenhada em duas linhas: o eixo não roda e a soma não prova.

🩸 27/09/2026 (estudo de leitura, item 2): o eixo de 26/09 só corrige o layer
com ≥ 50% do traçado em pares de face. Abaixo disso a soma fica inteira — e
pode contar as duas faces: "PAT-ALV2 131,26 ml ✓" contra 73,7 m pelo eixo (a
pintura por face vira 354 m²). Entre 15% e 50% em par (a ZONA CINZA) o layer
fica anotado: a chave do selo não prova comprimento com ele e a IA é avisada.
Nenhum número muda.
"""
import os
import sys

import ezdxf

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _arquivo(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6                      # metros
    msp = doc.modelspace()
    # ALV-CINZA: 4 m em par (2 linhas de 2 m a 15 cm) + 10 m de linha única → ~29%
    msp.add_line((0, 0), (2, 0), dxfattribs={"layer": "ALV-CINZA"})
    msp.add_line((0, 0.15), (2, 0.15), dxfattribs={"layer": "ALV-CINZA"})
    for k in range(5):
        msp.add_line((10 + 3 * k, 5), (10 + 3 * k, 7), dxfattribs={"layer": "ALV-CINZA"})
    # ALV-DUPLA: tudo em par → o eixo roda (fica fora da zona cinza)
    for y in (20, 20.15):
        msp.add_line((0, y), (6, y), dxfattribs={"layer": "ALV-DUPLA"})
    # ALV-UNICA: nada em par → linha única de verdade (fora da zona cinza)
    for k in range(4):
        msp.add_line((40 + 3 * k, 0), (40 + 3 * k, 3), dxfattribs={"layer": "ALV-UNICA"})
    # ALV-POUCO: 2 m em par + 20 m únicos → ~9%: par por acaso, abaixo dos 15%
    msp.add_line((0, 60), (1, 60), dxfattribs={"layer": "ALV-POUCO"})
    msp.add_line((0, 60.15), (1, 60.15), dxfattribs={"layer": "ALV-POUCO"})
    for k in range(5):
        msp.add_line((20 + 3 * k, 60), (20 + 3 * k, 64), dxfattribs={"layer": "ALV-POUCO"})
    p = str(tmp_path / "zona_cinza.dxf")
    doc.saveas(p)
    return p


def _extrai(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    return dx.extract_dxf(_arquivo(tmp_path))


def test_so_a_parede_meio_dupla_entra_na_zona_cinza(tmp_path, monkeypatch):
    ex = _extrai(tmp_path, monkeypatch)
    zc = (ex.metadata or {}).get("parede_zona_cinza") or {}
    assert set(zc) == {"ALV-CINZA"}, zc
    assert 0.2 <= zc["ALV-CINZA"] <= 0.4, zc


def test_o_numero_nao_muda(tmp_path, monkeypatch):
    wl = _extrai(tmp_path, monkeypatch).get_walls_by_layer()
    assert abs(wl["ALV-CINZA"] - 14.0) < 0.01, "a zona cinza não mexe na soma"


def test_a_ia_e_avisada(tmp_path, monkeypatch):
    txt = _extrai(tmp_path, monkeypatch).to_structured_prompt()
    linha = next(l for l in txt.splitlines() if l.strip().startswith("ALV-CINZA:"))
    assert "PAREDE EM PARTE EM DUAS LINHAS" in linha and "ESTIMADO" in linha, linha
    outra = next(l for l in txt.splitlines() if l.strip().startswith("ALV-UNICA:"))
    assert "DUAS LINHAS" not in outra, outra


def test_a_chave_do_selo_nao_prova_com_a_zona_cinza():
    src = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    i = src.index('for _lyr, _c in (extraction.get_walls_by_layer() or {}).items():')
    trecho = src[i - 500:i + 300]
    assert '_cinza_ig = (extraction.metadata or {}).get("parede_zona_cinza") or {}' in trecho
    assert "if _lyr in _cinza_ig:\n                                    continue" in trecho
