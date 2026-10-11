# -*- coding: utf-8 -*-
"""A seção AMBIENTE ↔ ÁREA ESCRITA deixa uma linha no log, por arquivo.

🔑 11/10/2026 — a seção entrou medida no acervo (88 arquivos de 59 jobs). Sem a
linha `motor:ambiente-area`, o que ela faz em PRODUÇÃO só se saberia baixando o
arquivo do cliente: quantas etiquetas foram lidas, quantas ganharam nome,
quantas são total, quantas estão fora das pranchas, e se a lista foi cortada.
"""
import io
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


class _Ex:
    def __init__(self, amb):
        self.metadata = {"ambientes_area_escrita": amb} if amb is not None else {}


_AMB = {
    "por_desenho": True, "etiquetas": 12, "pares": 9, "sem_nome": 3, "janelas_nao_usadas": 1,
    "grupos": [
        {"desenho": "PLANTA BAIXA", "desenhos": 1, "tipo": "planta", "fora": False,
         "ambientes": [["SALA", 12.3, 1], ["WC", 2.4, 2]], "totais": [["TOTAL", 90.0, 1]], "sem_nome": [5.0]},
        {"desenho": "", "desenhos": 0, "tipo": "", "fora": True,
         "ambientes": [["SALA", 12.3, 1], ["DEPOSITO", 90.0, 3]], "totais": [["TOTAL", 90.0, 1]],
         "sem_nome": [5.0, 6.0]},
    ],
}


def test_a_linha_traz_os_numeros_da_secao():
    assert main._ambientes_resumo(_Ex(_AMB)) == (
        "etiquetas=12 com_nome=9 sem_nome=3 totais=2 grupos=2 por_desenho=sim "
        "fora_das_pranchas=7 pares_distintos=4 nao_listados=0 janelas_nao_usadas=1")


def test_a_lista_cortada_no_teto_aparece():
    import dwg_extractor as dx
    muitos = dict(_AMB, grupos=[{"fora": False, "totais": [], "sem_nome": [],
                                 "ambientes": [["SALA %d" % i, 10.0, 1] for i in range(dx._AMB_LISTA_MAX + 7)]}],
                  por_desenho=False)
    linha = main._ambientes_resumo(_Ex(muitos))
    assert "pares_distintos=%d nao_listados=7" % (dx._AMB_LISTA_MAX + 7) in linha and "por_desenho=nao" in linha


def test_CONTROLE_arquivo_sem_etiqueta_nao_gera_linha():
    assert main._ambientes_resumo(_Ex(None)) == ""
    assert main._ambientes_resumo(_Ex({})) == ""
    assert main._ambientes_resumo(_Ex({"grupos": []})) == ""
    assert main._ambientes_resumo(object()) == ""


def test_a_etapa_e_diagnostico_e_o_processamento_grava():
    """🪤 Etapa fora de `_STAGES_DIAGNOSTICO` entra no painel de ERROS do motor."""
    assert "motor:ambiente-area" in main._STAGES_DIAGNOSTICO
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert fonte.count('_log_error("motor:ambiente-area"') == 1
    i = fonte.index("_ab = _ambientes_resumo(extraction)")
    trecho = fonte[i:i + 400]
    assert "if _ab:" in trecho and '_log_error("motor:ambiente-area"' in trecho
    assert 'severity="info"' in trecho


def test_o_resumo_bate_com_o_registro_de_verdade(tmp_path):
    """Do arquivo até a linha: o registro que o extrator grava é o que o resumo lê."""
    import ezdxf
    import dwg_extractor as dx
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    msp.add_text("SALA DE ESTAR", dxfattribs={"height": 100, "insert": (0, 300)})
    msp.add_text("A = 12,30 m²", dxfattribs={"height": 100, "insert": (0, 0)})
    msp.add_text("COZINHA A=8,50m²", dxfattribs={"height": 100, "insert": (5000, 0)})
    msp.add_text("A = 3,10 m²", dxfattribs={"height": 100, "insert": (20000, 9000)})
    p = str(tmp_path / "amb.dxf")
    doc.saveas(p)
    ex = dx.extract_dxf(p)
    amb = ex.metadata.get("ambientes_area_escrita")
    assert amb and amb["etiquetas"] == 3, amb
    linha = main._ambientes_resumo(ex)
    assert linha.startswith("etiquetas=3 com_nome=2 sem_nome=1 totais=0 grupos=1 por_desenho=nao"), linha
