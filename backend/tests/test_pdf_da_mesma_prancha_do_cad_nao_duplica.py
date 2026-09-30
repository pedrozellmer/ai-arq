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


# ══════════════════════════════════════════════════════════════════════════
#  29/09 (Pedro): prancha de TABELA fica mesmo com o CAD lido
# ══════════════════════════════════════════════════════════════════════════
# 🩸 job 6437838e: o quadro de cargas, o unifilar e o rack em PDF traziam os
# totais do projetista (69 luminárias de teto alto, 14 tomadas de elevacar…),
# disjuntores e cabos; a leitura do DWG das mesmas folhas não trouxe — o texto
# estava dentro de bloco. (Trechos de texto reescritos, com a forma dos reais.)
@pytest.mark.parametrize("texto, esperado", [
    ("01-QUADRO DE DISTRIBUIÇÃO … QUADRO DE CARGAS  TOTAIS 22 69", "QUADRO DE CARGA"),
    ("DIAGRAMA\nUNIFILAR  QGBT  disjuntor 3P", "DIAGRAMA UNIFILAR"),
    ("DIAGRAMA DE LIGAÇÃO UNIFILAR PARA DADOS  RACK 18U", "LIGACAO UNIFILAR"),
    ("RESUMO DO AÇO  AÇO DIAM (MM) C.TOTAL (M) PESO + 10% (KG)", "RESUMO DO ACO"),
    ("PLANTA CIVIL  TABELA DE ESQUADRIAS DE ALUMÍNIO  CX. ALTURA LARGURA", "TABELA DE ESQUADRIA"),
    ("QUADRO DE QUANTITATIVOS  CONCRETO 4,90 m³", "QUANTITATIVO"),
])
def test_a_tabela_de_quantidade_no_texto(texto, esperado):
    assert er.tabela_de_quantidade_no_texto(texto) == esperado


@pytest.mark.parametrize("texto", [
    "ATUALIZAÇÃO DA TABELA DE REVESTIMENTOS CONFORME NOVA TABELA",   # nota de revisão
    "OS ESFORÇOS INDICADOS NESTA TABELA SÃO OS VALORES MÁXIMOS",
    "PLANTA BAIXA ESCALA 1/100  CIRCUITO 1.4  DISJUNTOR 20A  TOMADA",
    "", None,
])
def test_CONTROLE_planta_e_nota_nao_sao_tabela(texto):
    assert er.tabela_de_quantidade_no_texto(texto) == ""


def test_a_prancha_de_tabela_fica_e_a_de_planta_sai():
    tab = "/j/OBR-ELE-004-CARGA-R01.pdf"
    planta = "/j/OBR-ELE-001-ILUM-R01.pdf"
    refs = ["OBR-ELE-004-CARGA-R01.dxf", "OBR-ELE-001-ILUM-R01.dxf"]
    textos = {tab: "QUADRO DE CARGAS  TOTAIS", planta: "PLANTA BAIXA 1/100"}
    ficam = []
    sai = er.pdfs_da_prancha_ja_lida_no_cad([tab, planta], refs,
                                           texto_do_pdf=textos.get, ficam_por_tabela=ficam)
    assert sai == [planta]
    assert ficam == [(tab, "QUADRO DE CARGA")]


def test_CONTROLE_leitor_que_falha_vale_a_regra_sem_a_excecao():
    def _quebra(p):
        raise OSError("pdf ilegível")
    assert er.pdfs_da_prancha_ja_lida_no_cad([PDF_006], ["OBR.FR.EX.HT.006.3PAVXXXXXX-R01.dxf"],
                                             texto_do_pdf=_quebra) == [PDF_006]


def test_o_motor_le_o_texto_com_o_leitor_da_producao():
    """🪤 `fitz` (PyMuPDF) NÃO está no requirements — a 1ª versão da escala por
    texto importava ele, o import falhava em produção e o except engolia."""
    fn = next(n for n in ast.walk(ast.parse(io.open(os.path.join(os.path.dirname(_AQUI), "main.py"),
                                                    encoding="utf-8").read()))
              if isinstance(n, ast.FunctionDef) and n.name == "_texto_das_folhas_do_pdf")
    importados = {a.name for n in ast.walk(fn) if isinstance(n, ast.Import) for a in n.names}
    assert "pypdfium2" in importados and "fitz" not in importados, importados


def test_o_leitor_nao_levanta():
    import main
    assert main._texto_das_folhas_do_pdf("/nao/existe.pdf") == ""


def test_o_motor_passa_o_leitor_e_registra_quem_ficou():
    fn = _process_job()
    ch = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
          and getattr(n.func, "id", "") == "_pdfs_irmaos"]
    kw = {k.arg: getattr(k.value, "id", None) for k in ch[0].keywords}
    assert kw.get("texto_do_pdf") == "_texto_das_folhas_do_pdf", kw
    assert kw.get("ficam_por_tabela") == "_tabelas_ficam", kw
