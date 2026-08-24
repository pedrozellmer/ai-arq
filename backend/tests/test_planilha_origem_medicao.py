# -*- coding: utf-8 -*-
"""A planilha tem que dizer DE ONDE veio cada número.

Pedro, 24/08/2026: *"e sempre coloca a fonte na planilha, dizendo qual a origem
da medição"*.

O motor já registrava a procedência — 96% dos itens MEDIDOS do acervo (1.370 de
1.432) têm um "Fonte: ..." escrito: 972 por contagem de bloco, 109 por
comprimento de layer, 68 por área de hachura. Só que estava enterrada no meio da
coluna OBSERVAÇÕES, junto do selo e de outros recados. Agora é coluna própria.

🚨 Este teste ABRE o .xlsx gerado. Escrever no código não é escrever na planilha
— errei isso 4 vezes dizendo "consertado" olhando a fonte em vez do resultado.

🪤 O deslocamento de coluna quase quebrou outra aba: `for c in range(1, 10)`
aparece 7 vezes, e 3 são da aba "Referências SINAPI", que tem colunas próprias.
Trocar as 7 de uma vez teria estragado uma aba que ninguém estava olhando.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

openpyxl = pytest.importorskip("openpyxl")


def _gerar(tmp_path, itens):
    from models import ProjectData
    from spreadsheet import generate_spreadsheet
    proj = ProjectData(name="Teste de procedência", total_area=100.0)
    caminho = str(tmp_path / "q.xlsx")
    generate_spreadsheet(proj, itens, caminho, typology="office")
    return caminho


def _item(desc, obs, conf, num="1", unit="un", qtd=1.0):
    from models import BudgetItem, Confidence
    return BudgetItem(
        item_num=num, description=desc, unit=unit, quantity=qtd,
        observations=obs, ref_sheet="PRANCHA-01.dxf",
        confidence=Confidence.CONFIRMADO if conf else Confidence.ESTIMADO,
        discipline="Arquitetura")


@pytest.fixture
def planilha(tmp_path):
    itens = [
        _item("Porta P80E", "Fonte: 23 INSERTs do bloco 'P80E'. Confirmar ferragens.",
              True, num="1", qtd=23),
        _item("Eletroduto", "Fonte: comprimento do layer -TETOMELE = 49,44 m | 💡 nota",
              True, num="2", unit="ml", qtd=49.44),
        _item("Piso porcelanato", "Fonte: área hachurada do layer 'A-FLOR' = 69.03 m².",
              True, num="3", unit="m²", qtd=69.03),
        _item("Item sem procedência", "", True, num="4"),
        _item("Bancada a definir", "", False, num="5"),
    ]
    caminho = _gerar(tmp_path, itens)
    wb = openpyxl.load_workbook(caminho)
    return wb["Orçamento"]


def _linha_do(ws, texto):
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=2).value
        if v and texto in str(v):
            return r
    raise AssertionError("não achei a linha de %r na planilha" % texto)


def test_a_coluna_existe_com_o_nome_certo(planilha):
    ws = planilha
    for r in range(1, 30):
        if ws.cell(row=r, column=1).value == "ITEM":
            assert ws.cell(row=r, column=9).value == "ORIGEM DA MEDIÇÃO"
            assert ws.cell(row=r, column=10).value == "REF."
            return
    raise AssertionError("não achei o cabeçalho da planilha")


def test_bloco_vira_procedencia_legivel(planilha):
    ws = planilha
    r = _linha_do(ws, "Porta P80E")
    assert ws.cell(row=r, column=9).value == "23 INSERTs do bloco 'P80E'"


def test_layer_vira_procedencia_e_o_separador_corta_certo(planilha):
    """O motor usa ' | ' pra emendar recado extra — não pode entrar na coluna."""
    ws = planilha
    r = _linha_do(ws, "Eletroduto")
    assert ws.cell(row=r, column=9).value == "comprimento do layer -TETOMELE = 49,44 m"


def test_o_ponto_do_decimal_nao_corta_a_frase(planilha):
    """🪤 '69.03 m²' tem ponto. Se o corte fosse no ponto e não no '. ', a
    procedência sairia mutilada em 'área hachurada do layer A-FLOR = 69'."""
    ws = planilha
    r = _linha_do(ws, "Piso porcelanato")
    assert ws.cell(row=r, column=9).value == "área hachurada do layer 'A-FLOR' = 69.03 m²"


def test_medido_SEM_procedencia_e_denunciado_nao_deixado_em_branco(planilha):
    """🚨 Regra dura nº1: selo de MEDIDO sem dizer de onde veio é o defeito.
    Célula vazia em planilha lê-se como 'não se aplica' — esconderia."""
    ws = planilha
    r = _linha_do(ws, "Item sem procedência")
    v = str(ws.cell(row=r, column=9).value or "")
    assert "sem procedência registrada" in v, (
        "item MEDIDO sem fonte saiu com célula %r" % v)


def test_estimado_sem_fonte_explica_em_vez_de_ficar_vazio(planilha):
    ws = planilha
    r = _linha_do(ws, "Bancada a definir")
    v = str(ws.cell(row=r, column=9).value or "")
    assert "não medido" in v and "quantidade é sua" in v


def test_a_coluna_REF_continua_funcionando_no_lugar_novo(planilha):
    ws = planilha
    r = _linha_do(ws, "Porta P80E")
    assert "PRANCHA-01" in str(ws.cell(row=r, column=10).value or "")


def test_o_selo_continua_na_coluna_de_observacoes(planilha):
    """Contrapeso: a coluna nova não pode ter roubado o selo da nº1."""
    ws = planilha
    r = _linha_do(ws, "Porta P80E")
    assert "MEDIDO do CAD" in str(ws.cell(row=r, column=8).value or "")
    r2 = _linha_do(ws, "Bancada a definir")
    assert "ESTIMADO" in str(ws.cell(row=r2, column=8).value or "")


def test_a_aba_de_referencias_sinapi_nao_foi_deslocada_junto(tmp_path):
    """🪤 Ela tem colunas PRÓPRIAS. Três dos sete `range(1, 10)` do arquivo eram
    dela — deslocar os sete de uma vez estragaria uma aba fora do meu olhar."""
    import io as _io
    src = _io.open(os.path.join(_BACKEND, "spreadsheet.py"), encoding="utf-8").read()
    i = src.index("wsm = wb.create_sheet('Referências SINAPI')")
    trecho = src[i:]
    assert "range(1, 11):" not in trecho, (
        "a aba Referências SINAPI foi deslocada junto e não devia")
    assert "end_column=10)" not in trecho
