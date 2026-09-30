# -*- coding: utf-8 -*-
"""Bloco de 1–3 traços inserido em layer de TUBULAÇÃO/sprinkler é PEÇA, não marca.

🩸 30/09/2026 — varredura do estudo do acervo (127 DXF) sobre a regra da
SIGLA de 29/09 (`nota_de_bloco_de_anotacao`: 1–3 LINE + nome sem palavra de
≥ 4 letras). Ela marcava como "não conte" as conexões de um sprinkler:
X1 (104), X2 (88) e X3 (85) no layer SPK — o tê e o cotovelo de cada bico
(X1 + X2 = 192 ≈ 201 bicos) — e IF/IP1/IC2, acessórios atravessados no tubo
(HPLU100, PVC, HAF). Tudo o que a regra marcou em layer de tubulação era peça;
nenhuma marca de verdade do acervo mora lá: a de fiação fica em layer de
ELÉTRICA, a cruz do eixo em PILAR_EIXOS, o _H0 do TQS no "224".

A decisão é pela MAIORIA das inserções (≥ 80%): o X3 tem 3 de 85 no pilar, e
o `layer` da contagem é o da PRIMEIRA inserção — podia ser a do pilar.
"""
import ast
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402
from _corpo import fonte  # noqa: E402


@pytest.mark.parametrize("nome,assin,camadas", [
    ("X1", "LINE:1|bb:0.1x0.1", {"SPK": 103, "VISTA": 1}),
    ("X2", "LINE:2|bb:0.1x0.1", {"SPK": 87, "VISTA": 1}),
    ("X3", "LINE:3|bb:0.1x0.1", {"SPK": 82, "0-PILAR": 3}),
    ("IF", "LINE:1|bb:0.1x0.1", {"HPLU100": 151, "PVC": 79, "HAF": 51}),
    ("IC2", "LINE:1|bb:0.1x0.1", {"PVC": 3, "HAF": 1}),
    ("fase", "LINE:1|bb:0.1x0.1", {"ESGOTO": 10}),       # vale pro condutor também
])
def test_em_layer_de_tubulacao_e_peca(nome, assin, camadas):
    assert er.nota_de_bloco_de_anotacao(nome, assin, camadas) == ""


@pytest.mark.parametrize("nome,assin,camadas", [
    ("WN", "LINE:2|bb:0.1x0.1", {"ELE-FIACAO": 23}),
    ("A$C31C73CB7", "LINE:2|bb:5.6x5.6", {"PILAR_EIXOS": 2}),
    ("T-RAB", "LINE:1|bb:0.1x0.1", {"ELE-TEXTOS": 5}),
    ("_H0", "LINE:1|bb:0.1x0.1", {"224": 9}),
    ("E-TEB", "LINE:3|bb:0.1x0.1", {"ELE-EQUIPTOS": 13}),
    ("NEUTRO", "LINE:2|bb:0.1x0.1", {"SDAI-INCENDIO": 12}),  # alarme é elétrica
    ("WN", "LINE:2|bb:0.1x0.1", None),                        # sem camadas: como antes
])
def test_CONTROLE_marca_de_verdade_continua_marca(nome, assin, camadas):
    assert "MARCA DE ANOTAÇÃO" in er.nota_de_bloco_de_anotacao(nome, assin, camadas)


def test_a_fronteira_dos_80_por_cento():
    assert er.insercoes_em_tubulacao({"SPK": 8, "ELE": 2})
    assert not er.insercoes_em_tubulacao({"SPK": 7, "ELE": 3})
    assert not er.insercoes_em_tubulacao({})
    assert not er.insercoes_em_tubulacao(None)


def test_de_ponta_a_ponta_a_contagem_por_layer_chega_a_regua(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    x3 = doc.blocks.new("X3")
    for k in range(3):
        x3.add_line((k * 0.05, 0), (k * 0.05 + 0.05, 0.1))
    wn = doc.blocks.new("WN")
    wn.add_line((0, 0), (0.1, 0.1))
    wn.add_line((0.05, 0), (0.15, 0.1))
    msp = doc.modelspace()
    # a 1ª inserção do X3 é no pilar — o `layer` da contagem seria esse
    msp.add_blockref("X3", (0, 0), dxfattribs={"layer": "0-PILAR"})
    for i in range(9):
        msp.add_blockref("X3", (i * 2 + 2, 0), dxfattribs={"layer": "SPK"})
    for i in range(5):
        msp.add_blockref("WN", (i * 2, 5), dxfattribs={"layer": "ELE-FIACAO"})
    msp.add_line((0, -5), (20, -5))
    p = str(tmp_path / "spk.dxf")
    doc.saveas(p)
    ex = dx.extract_from_file(p)
    b = {bb.name: bb for bb in ex.blocks}
    assert b["X3"].camadas == {"0-PILAR": 1, "SPK": 9}, b["X3"].camadas
    assert b["X3"].layer == "0-PILAR"          # por isso a régua não usa `layer`
    txt = ex.to_structured_prompt()
    linhas = {l.split(":")[0].strip(): l for l in txt.splitlines() if l.startswith("  ") and " un" in l}
    assert "⚠" not in linhas.get("X3", "x"), linhas
    assert "MARCA DE ANOTAÇÃO" in linhas.get("WN", ""), linhas


def test_o_laco_do_main_passa_as_camadas_pra_regua():
    arv = ast.parse(fonte("main.py"))
    pj = [n for n in ast.walk(arv) if isinstance(n, ast.FunctionDef) and n.name == "process_job"][0]
    chamadas = [n for n in ast.walk(pj) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "_nota_anot"]
    assert chamadas, "a régua sumiu do laço"
    assert all(len(c.args) == 3 for c in chamadas), "o laço não passa `camadas`"
