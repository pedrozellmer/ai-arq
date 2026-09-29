# -*- coding: utf-8 -*-
"""O PDF que é a MESMA prancha de um CAD lido não entra de novo na planilha.

🩸 29/09/2026 (job 1b96bd42): 8 DWG + o PDF de cada um, com o mesmo nome. O
envio inicial lia os dois: a prancha 006 saiu com 10 linhas do DWG e 30 do
PDF. Pedro: ler só o DWG. Sai o PDF cujo CAD RENDEU linha; o do CAD que falhou
fica — é o plano B (8b7a2b71: o DWG falhou 3 vezes e as 14 linhas vieram do
PDF de mesmo nome).
(Nomes de arquivo sintéticos, com a mesma FORMA dos reais.)
"""
import ast
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402

PDF_006 = "/tmp/j/OBR.FR.EX.HT.006.3PAVXXXXXX-R01.pdf"
PDF_108 = "/tmp/j/OBR.FU.EX.HT.108.PAVTOTIPOX-R01.pdf"


def test_o_caso_sai_so_o_pdf_da_prancha_que_o_dwg_leu():
    refs = ["OBR.FR.EX.HT.006.3PAVXXXXXX-R01.dxf"] * 10
    assert er.pdfs_da_prancha_ja_lida_no_cad([PDF_006, PDF_108], refs) == [PDF_006]


@pytest.mark.parametrize("ref", [
    "OBR.FR.EX.HT.006.3PAVXXXXXX-R01_libredwg.dxf",       # ODA recusou, plano B
    "OBR.FR.EX.HT.006.3PAVXXXXXX-R01_libredwg_min.dxf",   # o resgate enxuto
    "OBR.FR.EX.HT.006.3PAVXXXXXX-R01.slim.dxf",           # o DXF emagrecido
    "OBR.FR.EX.HT.006.3PAVXXXXXX-R01.dxf (Planta — 3º pavimento)",   # dica da leitura
    "obr.fr.ex.ht.006.3pavxxxxxx-r01.DXF",
    "C:\\obra\\OBR.FR.EX.HT.006.3PAVXXXXXX-R01.dwg",
])
def test_o_nome_do_cad_como_a_leitura_grava(ref):
    assert er.pdfs_da_prancha_ja_lida_no_cad([PDF_006], [ref]) == [PDF_006], ref


def test_acento_e_caixa_nao_separam_a_mesma_prancha():
    assert er.pdfs_da_prancha_ja_lida_no_cad(["/j/Planta Térreo.PDF"],
                                             ["planta terreo.dxf"]) == ["/j/Planta Térreo.PDF"]


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLES — o que continua como hoje
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_cad_que_nao_rendeu_linha_deixa_o_pdf():
    """O DWG não converteu / não deu nada: o PDF de mesmo nome é o plano B."""
    assert er.pdfs_da_prancha_ja_lida_no_cad([PDF_006, PDF_108], []) == []
    assert er.pdfs_da_prancha_ja_lida_no_cad([PDF_006], ["", None]) == []


@pytest.mark.parametrize("pdf, ref", [
    # um DWG com todas as folhas + um PDF por folha, nomes que não batem
    ("/j/1 - Iluminacao prancha 1-8.pdf", "02.PROJETO ELETRICO OBRA_REV 05.dxf"),
    # cópia baixada de novo: "(1)" é outro nome
    ("/j/prancha (1).pdf", "prancha.dxf"),
    ("/j/prancha 01.pdf", "prancha 1.dwg"),
    # revisões diferentes da mesma folha
    ("/j/OBR-ARQ-003-R02.pdf", "OBR-ARQ-003-R01.dwg"),
])
def test_CONTROLE_nome_diferente_fica(pdf, ref):
    assert er.pdfs_da_prancha_ja_lida_no_cad([pdf], [ref]) == []


def test_CONTROLE_parenteses_do_proprio_nome_nao_sao_dica():
    assert er.radical_da_prancha("/j/prancha (1).pdf") == "prancha (1)"
    assert er.radical_da_prancha("prancha.dxf (Planta baixa)") == "prancha"
    assert er.radical_da_prancha("") == ""
    assert er.radical_da_prancha(None) == ""


# ══════════════════════════════════════════════════════════════════════════
#  O MOTOR aplica, antes do laço dos PDFs e sem condição
# ══════════════════════════════════════════════════════════════════════════
def _process_job():
    arv = ast.parse(io.open(os.path.join(os.path.dirname(_AQUI), "main.py"),
                            encoding="utf-8").read())
    return next(n for n in ast.walk(arv)
                if isinstance(n, ast.FunctionDef) and n.name == "process_job")


def _lista_que_contem(fn, no):
    for pai in ast.walk(fn):
        for campo in ("body", "orelse", "finalbody"):
            lista = getattr(pai, campo, None)
            if isinstance(lista, list) and no in lista:
                return lista
    return None


def test_o_motor_tira_o_pdf_antes_de_ler_os_pdfs():
    fn = _process_job()
    chamada = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
               and isinstance(n.value, ast.Call)
               and getattr(n.value.func, "id", "") == "_pdfs_irmaos"]
    assert len(chamada) == 1, "a regra do PDF da mesma prancha sumiu de process_job"
    args = chamada[0].value.args
    assert getattr(args[0], "id", None) == "pdf_paths"
    assert "dxf_items" in {x.id for x in ast.walk(args[1]) if isinstance(x, ast.Name)}
    total = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
             and any(getattr(t, "id", "") == "total" for t in n.targets)
             and "pdf_paths" in {x.id for x in ast.walk(n.value) if isinstance(x, ast.Name)}]
    assert total, "sumiu o `total = len(pdf_paths)` que abre o laço dos PDFs"
    lista = _lista_que_contem(fn, chamada[0])
    assert lista is not None and total[0] in lista, "a regra ficou atrás de um `if`"
    assert lista.index(chamada[0]) < lista.index(total[0])
    ifs = [n for n in lista if isinstance(n, ast.If)
           and getattr(n.test, "id", "") == "_pdf_irmao"]
    assert ifs and any(isinstance(s, ast.Assign)
                       and any(getattr(t, "id", "") == "pdf_paths" for t in s.targets)
                       for s in ast.walk(ifs[0])), "o PDF não sai de pdf_paths"
