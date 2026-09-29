# -*- coding: utf-8 -*-
"""Marca de fiação e nuvem de revisão são ANOTAÇÃO do desenho — não viram peça.

🩸 29/09/2026 (caso 18c57c3c): "Dispositivo elétrico tipo WN — 23 un", "W-FFF —
23 un" (as marcas de neutro e fases do diagrama) e "Caixa de revisão elétrica
(C-REV) — 2 un ✓" (a etiqueta de revisão "01") foram pra planilha do cliente.
📏 No acervo, "só 1–3 traços" pegaria VIGA_3_1, GUARDA-CORPO e "CONDU. C" — peças
de verdade. Os controles abaixo são esses nomes.
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


@pytest.mark.parametrize("nome,assin", [
    ("WN", "LINE:2|bb:0.1x0.1"),
    ("W-FFF", "LINE:3|bb:0.1x0.1"),
])
def test_marca_de_fiacao(nome, assin):
    assert "MARCA DE ANOTAÇÃO" in er.nota_de_bloco_de_anotacao(nome, assin)


@pytest.mark.parametrize("nome", ["C-REV", "REV_01", "Nuvem de revisão", "REVISAO"])
def test_etiqueta_de_revisao(nome):
    assert "REVISÃO" in er.nota_de_bloco_de_anotacao(nome, "ATTDEF:1|LINE:16|bb:1x1")


@pytest.mark.parametrize("nome,assin", [
    ("Viga_3_1", "LINE:3|bb:5x0.2"),                 # peça de verdade, 3 traços
    ("Guarda-corpo - Guarda-corpo", "LINE:2|bb:3x0.1"),
    ("CONDU. C", "LINE:3|bb:0.2x0.2"),
    ("*U197", "LINE:2|bb:1x1"),                      # anônimo: o nome não diz nada
    ("WN", "LINE:4|bb:0.1x0.1"),                     # mais de 3 traços
    ("WN", "CIRCLE:1|LINE:2|bb:0.1x0.1"),            # tem círculo: é símbolo
    ("Revestimento cerâmico", "HATCH:1|bb:1x1"),     # "REV" dentro de palavra
    ("TOM. BAIXA 127V", "CIRCLE:2|HATCH:1|bb:0.2x0.2"),
])
def test_CONTROLE_peca_de_verdade_fica(nome, assin):
    assert er.nota_de_bloco_de_anotacao(nome, assin) == ""


def test_a_ia_recebe_o_aviso_na_linha_do_bloco(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    wn = doc.blocks.new("WN")
    wn.add_line((0, 0), (0.1, 0.1))
    wn.add_line((0.05, 0), (0.15, 0.1))
    rev = doc.blocks.new("C-REV")
    rev.add_attdef("A", (0, 0), dxfattribs={"height": 0.2})
    for k in range(4):
        rev.add_line((k * 0.1, 0), ((k + 1) * 0.1, 0.1))
    tom = doc.blocks.new("TOMADA")
    tom.add_circle((0, 0), 0.1)
    msp = doc.modelspace()
    for i in range(5):
        msp.add_blockref("WN", (i * 2, 0))
        msp.add_blockref("TOMADA", (i * 2, 5))
    for i in range(2):
        msp.add_blockref("C-REV", (i * 3, 10))
    msp.add_line((0, -5), (20, -5))
    p = str(tmp_path / "anot.dxf")
    doc.saveas(p)
    txt = dx.extract_from_file(p).to_structured_prompt()
    linhas = {l.split(":")[0].strip(): l for l in txt.splitlines() if l.startswith("  ") and " un" in l}
    assert "MARCA DE ANOTAÇÃO" in linhas.get("WN", ""), linhas
    assert "REVISÃO" in linhas.get("C-REV", ""), linhas
    assert "⚠" not in linhas.get("TOMADA", "x"), linhas


def test_a_linha_que_e_a_contagem_da_anotacao_sai_do_laco():
    arv = ast.parse(fonte("main.py"))
    pj = [n for n in ast.walk(arv) if isinstance(n, ast.FunctionDef) and n.name == "process_job"][0]
    chamadas = [n for n in ast.walk(pj) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "_contagem_de_bloco_citada"
                and any(getattr(a, "id", "") == "_blocos_anotacao" for a in n.args)]
    assert len(chamadas) == 1, "a saída da linha de anotação sumiu do laço"
    ifs = [n for n in ast.walk(pj) if isinstance(n, ast.If) and getattr(n.test, "id", "") == "_bl_anot"]
    assert len(ifs) == 1 and any(isinstance(s, ast.Continue) for s in ifs[0].body)
