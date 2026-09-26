# -*- coding: utf-8 -*-
"""A posição do bloco é onde ele APARECE, quando o desenho está longe da base.

🩸 25/09/2026 — job `73c6f0ed` (projeto elétrico exportado do Revit): tomada,
ponto de ar e luminária eram INSERIDOS a até 2 km da casa; a definição do
bloco trazia o desenho deslocado e ele caía no lugar certo só depois de
escalar e girar. O motor situava pelo ponto de inserção: todos "fora de
qualquer desenho". Medido no acervo: 3 de 34 arquivos mudam — as conexões e
setas das vistas 3D do Revit saem (475 → 340 blocos) e duas portas de alçapão
de um DETALHE saem; comprimento e área, nenhum.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import test_desenho_no_modelo as tdm  # noqa: E402


def _folha(tmp_path, onde_desenha):
    """A folha do guarda vizinho (planta em cima, DETALHE D embaixo, caixa
    (4,6)-(12,12)) + o bloco LUZ desenhado 500 m longe da base, inserido de
    modo que APARECE em `onde_desenha`; + o bloco TOMADA normal, na planta."""
    p = tdm._folha(tmp_path)
    doc = ezdxf.readfile(p)
    luz = doc.blocks.new("LUZ")
    luz.add_circle((500, 500), 0.1)
    tom = doc.blocks.new("TOMADA")
    tom.add_circle((0, 0), 0.1)
    msp = doc.modelspace()
    for dx_ in (0.0, 0.5):
        x, y = onde_desenha
        msp.add_blockref("LUZ", (x + dx_ - 500, y - 500))
    msp.add_blockref("TOMADA", (10, 24))
    doc.saveas(p)
    return p


@pytest.fixture(autouse=True)
def _folha_ligada(monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)


def _conta(ex, nome):
    return sum(b.count for b in ex.blocks if b.name == nome)


def test_bloco_que_desenha_no_detalhe_sai_mesmo_inserido_longe(tmp_path):
    ex = dx.extract_dxf(_folha(tmp_path, (8, 9)))        # aparece DENTRO do detalhe
    assert _conta(ex, "LUZ") == 0, "é do detalhe: sai, como sairia se fosse inserido lá"
    assert ex.metadata.get("blocos_pelo_desenho") == 2


def test_bloco_que_desenha_na_planta_continua_contado(tmp_path):
    ex = dx.extract_dxf(_folha(tmp_path, (10, 23)))      # aparece na planta
    assert _conta(ex, "LUZ") == 2


def test_a_posicao_e_a_do_desenho(tmp_path):
    ex = dx.extract_dxf(_folha(tmp_path, (10, 23)))
    ps = next(b.positions for b in ex.blocks if b.name == "LUZ")
    assert all(abs(x - 10.25) < 0.5 and abs(y - 23) < 0.5 for x, y in ps), ps


def test_CONTROLE_bloco_normal_fica_no_ponto_de_insercao(tmp_path):
    ex = dx.extract_dxf(_folha(tmp_path, (10, 23)))
    assert next(b.positions for b in ex.blocks if b.name == "TOMADA") == [(10.0, 24.0)]
    assert _conta(ex, "TOMADA") == 1
