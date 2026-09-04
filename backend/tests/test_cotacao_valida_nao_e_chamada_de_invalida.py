# -*- coding: utf-8 -*-
"""Planilha de cotação VÁLIDA era recusada como "não é um .xlsx válido".

🩸 04/09/2026, achado por mim enquanto media o custo do parse pra tirar a rota
do laço de eventos — o meu próprio arquivo de teste caiu no defeito.

Os três lugares que procuram o cabeçalho faziam `min(25, ws.max_row + 1)`. Em
`read_only=True`, o openpyxl só sabe o tamanho da planilha se o .xlsx trouxer o
registro `<dimension>` — e **arquivo perfeitamente válido pode não trazer**: o
próprio openpyxl, no modo `write_only`, gera assim, e exportador de ERP também.
Aí `max_row` é `None` e a conta estoura:

    TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'

O `except Exception` da rota engolia e o cliente lia:

    "Não consegui abrir esse arquivo como planilha Excel.
     Confira se é um .xlsx válido e tente de novo."

🔑 Ele ia procurar defeito num arquivo que não tem nenhum. Culpar o arquivo do
cliente por bug nosso é a doença que a gente passou 03/09 inteiro caçando —
aqui em forma de um `+ 1`.

🪤 Conferido antes de escolher o conserto: `ws.cell()` FUNCIONA em read_only sem
dimensão (é só `calculate_dimension()` que exige `force=True`), e ler além do
fim devolve `None` em vez de levantar — medido, 24×19 células além do fim de uma
planilha de 2 linhas custam 0,11 s. Então varrer até o próprio teto, quando não
dá pra saber onde acaba, é exatamente o comportamento pretendido.
"""
import os
import tempfile

import pytest

from supplier_quote_parser import _ate, parse_supplier_quote

openpyxl = pytest.importorskip("openpyxl")


def _planilha_sem_dimensao(linhas=30):
    """Um .xlsx VÁLIDO que não declara `<dimension>` — como o write_only gera."""
    d = tempfile.mkdtemp()
    p = os.path.join(d, "cotacao_sem_dimensao.xlsx")
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("Cotacao")
    ws.append(["ITEM", "ESPECIFICAÇÃO", "UN", "QTD",
               "VALOR UNITÁRIO", "VALOR TOTAL"])
    for i in range(linhas):
        ws.append([i + 1, "Alvenaria bloco ceramico 14x19x39", "m2",
                   12.5, 89.9, 1123.75])
    wb.save(p)
    return p


# ══════════════════════════════════════════════════════════════════════════
#  O que o cliente vive: manda a planilha e ela é lida
# ══════════════════════════════════════════════════════════════════════════
def test_a_planilha_sem_dimensao_e_LIDA():
    """🩸 O caso. Antes: TypeError → "confira se é um .xlsx válido"."""
    r = parse_supplier_quote(_planilha_sem_dimensao(), "Fornecedor", mode="auto")
    assert not r.get("error"), (
        "planilha VÁLIDA voltou com erro: %r — o cliente vai procurar defeito "
        "num arquivo que não tem nenhum" % r.get("error"))
    assert r["n_items_quoted"] == 30, (
        "leu %s itens de 30 — a varredura até o teto não está alcançando as "
        "linhas" % r.get("n_items_quoted"))
    assert r["total_bruto"] > 0, "leu os itens mas não leu os preços"


def test_a_planilha_NORMAL_continua_sendo_lida():
    """CONTROLE: consertar o caso raro não pode quebrar o comum."""
    d = tempfile.mkdtemp()
    p = os.path.join(d, "normal.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ITEM", "ESPECIFICAÇÃO", "UN", "QTD",
               "VALOR UNITÁRIO", "VALOR TOTAL"])
    for i in range(10):
        ws.append([i + 1, "Piso ceramico 60x60", "m2", 8.0, 45.0, 360.0])
    wb.save(p)
    r = parse_supplier_quote(p, "Fornecedor", mode="auto")
    assert not r.get("error"), r.get("error")
    assert r["n_items_quoted"] == 10


# ══════════════════════════════════════════════════════════════════════════
#  A conta, isolada
# ══════════════════════════════════════════════════════════════════════════
def test_o_limite_aguenta_o_None():
    assert _ate(None, 25) == 25, (
        "voltou a estourar (ou a devolver coisa errada) quando o openpyxl não "
        "sabe o tamanho da planilha")


def test_o_limite_continua_cortando_quando_SABE_o_tamanho():
    """🪤 Se ele passar a devolver sempre o teto, a varredura fica mais lenta
    à toa em toda planilha curta — e o guarda de cima não perceberia."""
    assert _ate(3, 25) == 4, "planilha de 3 linhas tem que varrer só até a 3"
    assert _ate(900, 25) == 25, "o teto continua sendo teto"
    assert _ate(0, 25) == 1


def test_o_limite_nao_quebra_com_lixo():
    for entrada in ("", "abc", [], {}):
        assert _ate(entrada, 15) == 15, (
            "entrada inesperada %r derrubou o cálculo" % (entrada,))


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — a conta de ANTES, no MESMO insumo
# ══════════════════════════════════════════════════════════════════════════
def _ate_ANTIGO(tamanho, teto):
    """Como era escrito nos três lugares: `min(teto, ws.max_row + 1)`."""
    return min(teto, tamanho + 1)


def test_CONTROLE_a_conta_ANTIGA_estoura_no_mesmo_insumo():
    assert _ate_ANTIGO(3, 25) == 4, (
        "o controle está errado: com tamanho conhecido as duas contas têm que "
        "dar o mesmo resultado, senão o conserto mudou o comportamento normal")
    with pytest.raises(TypeError):
        _ate_ANTIGO(None, 25)
    # e a de hoje aguenta o mesmo insumo
    assert _ate(None, 25) == 25


def test_CONTROLE_nenhum_sitio_voltou_a_somar_direto():
    """Os três lugares tinham a mesma conta; consertar dois é não consertar."""
    import io
    fonte = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "supplier_quote_parser.py"),
        encoding="utf-8").read()
    codigo = "\n".join(l for l in fonte.splitlines()
                       if not l.strip().startswith("#"))
    # 🪤 sem os comentários: a docstring do `_ate` CITA a conta antiga pra
    # explicar por que ela saiu — acusar isso é acusar a própria lápide.
    for proibido in ("ws.max_row + 1", "ws.max_column + 1"):
        assert codigo.count(proibido) <= 1, (
            "a conta que estoura com None voltou em algum sítio: %r" % proibido)
    assert codigo.count("_ate(ws.max_row") == 2
    assert codigo.count("_ate(ws.max_column") == 1
