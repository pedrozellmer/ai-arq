# -*- coding: utf-8 -*-
"""A coluna ESPECIFICACAO na planilha: marca, codigo e cor.

Pedro, 24/08/2026: *"podiamos ter uma planilha completa, ne, sku, revisao, qtd,
tudo"*, dentro do desenho do Caderno de acabamentos — *"ele revisa a qtd em
quantitativos, e depois no caderno vai especificando a marca, modelo, o sku,
justamente pra mandar pra orcar"*.

UMA coluna, nao tres: 95% dos itens nao tem especificacao nenhuma, e triplicar a
largura por causa de 5% piora a leitura de todo mundo. No BANCO os tres campos
ficam separados (pro caderno editar); na planilha saem juntos e legiveis.

🚨 Este teste ABRE o .xlsx gerado. Escrever no codigo nao e escrever na planilha.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

openpyxl = pytest.importorskip("openpyxl")


def _item(desc, marca="", codigo="", cor="", num="1"):
    from models import BudgetItem, Confidence
    return BudgetItem(item_num=num, description=desc, unit="un", quantity=1,
                      observations="Fonte: 1 INSERT do bloco 'X'.",
                      ref_sheet="PRANCHA-01.dxf",
                      confidence=Confidence.CONFIRMADO, discipline="Arquitetura",
                      marca=marca, codigo_fabricante=codigo, cor=cor,
                      spec_origem="lido" if (marca or codigo) else "")


@pytest.fixture
def aba(tmp_path):
    from models import ProjectData
    from spreadsheet import generate_spreadsheet
    itens = [
        _item("Papeleira cromada Quadratta", "Deca", "2020.CB3", num="1"),
        _item("Pintura acrilica", "Suvinil", "", "Branco Neve", num="2"),
        _item("Alvenaria em bloco ceramico", num="3"),
    ]
    caminho = str(tmp_path / "q.xlsx")
    generate_spreadsheet(ProjectData(name="Teste", total_area=100.0), itens,
                         caminho, typology="office")
    return openpyxl.load_workbook(caminho)["Orçamento"]


def _linha(ws, texto):
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=2).value
        if v and texto in str(v):
            return r
    raise AssertionError("nao achei %r" % texto)


def test_a_coluna_existe_no_lugar_certo(aba):
    """🪤 25/08 (auditoria): este teste tinha corpo `pass`, com um comentario
    dizendo que outro arquivo cobria. Teste que nao faz nada mas tem nome de
    quem confere e PIOR que teste nenhum: infla a contagem e se le como
    cobertura. Ou ele mede algo, ou sai."""
    for r in range(1, 30):
        if aba.cell(row=r, column=1).value == "ITEM":
            assert aba.cell(row=r, column=10).value == "ESPECIFICAÇÃO"
            assert aba.cell(row=r, column=9).value == "ORIGEM DA MEDIÇÃO"
            assert aba.cell(row=r, column=11).value == "REF."
            return
    raise AssertionError("não achei o cabeçalho da planilha")


def test_marca_codigo_e_cor_saem_juntos_e_legiveis(aba):
    r = _linha(aba, "Papeleira")
    assert aba.cell(row=r, column=10).value == "Deca \u00b7 2020.CB3"


def test_sai_o_que_existe_sem_separador_sobrando(aba):
    """Item com marca e cor, sem codigo, nao pode sair 'Suvinil · · Branco'."""
    r = _linha(aba, "Pintura")
    assert aba.cell(row=r, column=10).value == "Suvinil \u00b7 Branco Neve"


def test_item_sem_especificacao_fica_VAZIO(aba):
    """🚫 Nada de 'a definir' ou '-': campo vazio e honesto, texto inventado nao.
    Diferente da ORIGEM DA MEDICAO, onde o vazio esconderia violacao da regra
    n1 — aqui nao ter especificacao e o estado normal da maioria."""
    r = _linha(aba, "Alvenaria")
    assert not (aba.cell(row=r, column=10).value or "")


def test_a_observacao_e_a_origem_da_medicao_continuam_intactas(aba):
    """Contrapeso: a coluna nova nao pode ter roubado nada das vizinhas."""
    r = _linha(aba, "Papeleira")
    assert "MEDIDO do CAD" in str(aba.cell(row=r, column=8).value or "")
    assert "INSERT do bloco" in str(aba.cell(row=r, column=9).value or "")
    assert "PRANCHA-01" in str(aba.cell(row=r, column=11).value or "")


def test_a_aba_de_referencias_sinapi_nao_foi_deslocada():
    """🪤 Segunda vez no mesmo dia que mexo nas colunas. `range(1, 11)` e
    `end_column=10` tambem existem na aba Referencias SINAPI, que tem colunas
    PROPRIAS."""
    import io as _io
    src = _io.open(os.path.join(_BACKEND, "spreadsheet.py"), encoding="utf-8").read()
    i = src.index("wsm = wb.create_sheet('Referências SINAPI')")
    trecho = src[i:]
    assert "range(1, 12):" not in trecho
    assert "end_column=11)" not in trecho
    assert "column=11," not in trecho
