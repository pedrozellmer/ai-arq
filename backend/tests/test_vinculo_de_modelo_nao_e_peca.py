# -*- coding: utf-8 -*-
"""Vínculo de modelo (outro arquivo do Revit/IFC colado como bloco) não é peça.

🩸 27/09/2026 (estudo de leitura, item 4): "módulo de fachada 51 un ✓" vindo do
bloco 'LUC-ARQ-001-MOD-TIP_rvt'; "cozinha padrão 1 un ✓" de
'PDRAO-FS60_80-R01_rvt-1-LAJE'. É o contêiner do modelo de outra disciplina.
Pelo SUFIXO: 'IFC-Corrimão-Contorno' (prefixo) é elemento importado de IFC.
"""
import os
import sys
import textwrap

import ezdxf

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import MARCA_VINCULO_DE_MODELO, e_vinculo_de_modelo  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402


def test_o_sufixo_de_vinculo_e_reconhecido():
    for n in ("LUC-ARQ-001-MOD-TIP_rvt", "CENTRAL_rvt-1-PLANTA", "_vinculo__rvt-5-TORRE",
              "PDRAO-FS60_80-R01_rvt-1-LAJE", "bloco 'MOD-EMB_rvt-1-Elevação'", "X_ifc-2-CORTE"):
        assert e_vinculo_de_modelo(n), n
    for n in ("IFC-Corrimão-Contorno", "OMA-ELE-LO-0001-IFC-R01", "rvtmesa",
              "HTB - PORTA VENEZIANA - 0_70x2_10-2314776", "Mesa LerHamn 2"):
        assert not e_vinculo_de_modelo(n), n


def test_a_ia_e_avisada_na_contagem_de_blocos(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    for nm in ("LUC-ARQ-001-MOD-TIP_rvt", "PORTA-P1"):
        doc.blocks.new(nm).add_circle((0, 0), 0.3)
    for k in range(3):
        msp.add_blockref("LUC-ARQ-001-MOD-TIP_rvt", (5 * k, 0))
        msp.add_blockref("PORTA-P1", (5 * k, 10))
    p = str(tmp_path / "vinc.dxf")
    doc.saveas(p)
    txt = dx.extract_dxf(p).to_structured_prompt()
    vinc = [l for l in txt.splitlines() if "MOD-TIP" in l and " un" in l]
    porta = [l for l in txt.splitlines() if "PORTA-P1" in l and " un" in l]
    assert vinc and "VÍNCULO DE MODELO" in vinc[0], vinc
    assert porta and "VÍNCULO" not in porta[0], porta


def test_vinculo_com_tracinho_no_nome_e_conteudo_tambem_e_marcado(tmp_path, monkeypatch):
    """🩸 30/09 (H60): "FAMÍLIA - TORRE _vinculo__rvt-N-VISTA" — a raiz cortava no
    " - " e o vínculo COM conteúdo saía "FAMÍLIA (tipo N): 1 un" sem a marca; só
    o VAZIO (sem assinatura) era marcado."""
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    for k in (1, 2):
        b = doc.blocks.new("CONDOMINIO X - TORRE _vinculo__rvt-%d-TORRE B" % k)
        b.add_line((0, 0), (10 * k, 0))
        b.add_circle((0, 0), k)
        msp.add_blockref(b.name, (50 * k, 0))
    doc.blocks.new("CONDOMINIO X - TORRE _vinculo__rvt-7-TORRE B")        # vazio
    msp.add_blockref("CONDOMINIO X - TORRE _vinculo__rvt-7-TORRE B", (500, 0))
    p = str(tmp_path / "vinc2.dxf")
    doc.saveas(p)
    txt = dx.extract_dxf(p).to_structured_prompt()
    linhas = [l for l in txt.splitlines() if "CONDOMINIO X" in l and " un" in l]
    assert len(linhas) == 3 and all("VÍNCULO DE MODELO" in l for l in linhas), linhas
    assert not any("(tipo" in l for l in linhas), linhas


def _fatia_da_trava():
    src = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    a = src.index("            from engine_rules import (marca_de_rebaixamento as _marca_reb,")
    ini = src.rindex("        try:\n", 0, a)
    fim = src.index("        # 🚨 AQUI é o fim da fila de quem rebaixa selo", a)
    return textwrap.dedent(src[ini:fim])


def test_a_linha_do_vinculo_perde_o_selo_e_diz_por_que():
    vinc = BudgetItem(item_num="1", description="Módulo de fachada — pavimento tipo", unit="un",
                      quantity=51, observations="Fonte: bloco 'LUC-ARQ-001-MOD-TIP_rvt' = 51 un",
                      ref_sheet="a.dxf", confidence=Confidence("confirmado"), origem="dxf_geom")
    ifc = BudgetItem(item_num="2", description="Corrimão", unit="ml", quantity=32.69,
                     observations="Fonte: layer 'IFC-Corrimão-Contorno' = 32,69 m", ref_sheet="a.dxf",
                     confidence=Confidence("confirmado"), origem="dxf_geom")
    ns = {"all_items": [vinc, ifc], "job_id": "t", "_log_error": lambda *a, **k: None}
    exec(compile(_fatia_da_trava(), "trava", "exec"), ns)
    assert vinc.confidence == Confidence("estimado") and vinc.quantity == 51
    assert vinc.observations.startswith(MARCA_VINCULO_DE_MODELO), vinc.observations
    assert ifc.confidence == Confidence("confirmado"), "CONTROLE: elemento IFC fica"
