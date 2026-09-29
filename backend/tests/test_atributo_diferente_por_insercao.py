# -*- coding: utf-8 -*-
"""O mesmo bloco com ATRIBUTO diferente por inserção: a contagem diz quantas de cada.

🩸 29/09/2026 (caso 18c57c3c): 4 disjuntores 'DISJ-3F' — 2 com 63A=63A e 2
com 63A=D-32A. A lista de atributos do prompt junta as linhas iguais sem dizer
quantas; a IA viu duas linhas soltas e a planilha saiu "63A" nos 4 (noutra
rodada, "×1" cada). A quebra vai na linha da CONTAGEM da peça — não na lista
de atributos, onde a mesma etiqueta de área escrita 2× viraria área dobrada.
📏 Acervo de 76 DXF: 48 tinham linha de atributo repetida engolida sem contagem.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _ext(blocos, atributos):
    return dx.DXFExtraction(
        filename="eletrico.dxf",
        blocks=[dx.BlockCount(name=n, count=c, layer="ELE", assinatura="LINE:3|bb:0.2x0.1")
                for n, c in blocos],
        walls=[], hatches=[], texts=[], layers=["ELE"], dimensions=[],
        block_attributes=[{"bloco": b, "layer": "ELE", "campos": dict(c)} for b, c in atributos])


def _linha_da_contagem(p, nome):
    ls = [l for l in p.splitlines() if l.strip().startswith(nome + ":")]
    assert ls, "a contagem de %s sumiu do prompt:\n%s" % (nome, p[:1500])
    return ls[0]


_3F = [("DISJ-3F", [("63A", "63A"), ("III", "III")])] * 2 + \
      [("DISJ-3F", [("63A", "D-32A"), ("III", "III")])] * 2


def test_o_caso_o_3F_diz_2_de_63A_e_2_de_D32A():
    l = _linha_da_contagem(_ext([("DISJ-3F", 4)], _3F).to_structured_prompt(), "DISJ-3F")
    assert "4 un" in l and "63A=63A; III=III ×2" in l and "63A=D-32A; III=III ×2" in l, l
    assert "separe por valor" in l, l


def test_CONTROLE_um_valor_so_nao_ganha_quebra():
    attrs = [("TOI", [("C", "1")])] * 5
    l = _linha_da_contagem(_ext([("TOI", 5)], attrs).to_structured_prompt(), "TOI")
    assert "atributo por inserção" not in l, l


def test_CONTROLE_quebra_que_nao_soma_a_contagem_fica_de_fora():
    """Depois das vistas, 11 inserções viram 7 peças: a quebra das 11 mentiria."""
    attrs = [("QUADRO", [("N", "A")])] * 6 + [("QUADRO", [("N", "B")])] * 5
    l = _linha_da_contagem(_ext([("QUADRO", 7)], attrs).to_structured_prompt(), "QUADRO")
    assert "atributo por inserção" not in l, l


def test_a_lista_de_atributos_continua_sem_multiplicar():
    """Etiqueta de área repetida não ganha ×N na lista dos atributos."""
    attrs = [("AREA3", [("AMBIENTE", "sala"), ("XX,XX", "7.7")])] * 2
    p = _ext([("DISJ-3F", 4)], _3F + attrs).to_structured_prompt()
    area = [l for l in p.splitlines() if l.strip().startswith("[AREA3]")]
    assert len(area) == 1 and "×" not in area[0], area


def test_mais_de_4_valores_resume():
    attrs = [("ESQ", [("T", "P%d" % k)]) for k in range(6) for _ in range(2)]
    l = _linha_da_contagem(_ext([("ESQ", 12)], attrs).to_structured_prompt(), "ESQ")
    assert l.count("×2") == 4 and "+2 valor(es)" in l, l


def test_CONTROLE_etiqueta_de_area_nao_e_tipo_de_peca():
    """Cada inserção uma sala (valor único): 'separe por valor' viraria 1 linha por sala."""
    attrs = [("area", [("XX,XX", "%d.5" % k), ("AMBIENTE", "SALA %d" % k)]) for k in range(5)]
    l = _linha_da_contagem(_ext([("area", 5)], attrs).to_structured_prompt(), "area")
    assert "atributo por inserção" not in l, l


def test_CONTROLE_etiqueta_so_com_nome_tambem_nao():
    """Sem número nenhum: a trava é a REPETIÇÃO (cada inserção um nome único)."""
    attrs = [("TAG_AMB", [("NOME", "SALA %s" % c)]) for c in "ABCDE"]
    l = _linha_da_contagem(_ext([("TAG_AMB", 5)], attrs).to_structured_prompt(), "TAG_AMB")
    assert "atributo por inserção" not in l, l


def test_CONTROLE_marca_de_nivel_e_medida_nao_tipo():
    """Cotas de nível se repetem, mas são MEDIDA (decimal), não tipo de peça."""
    attrs = [("COTAV", [("COTA", "+13.90")])] * 6 + [("COTAV", [("COTA", "+19.50")])] * 4
    l = _linha_da_contagem(_ext([("COTAV", 10)], attrs).to_structured_prompt(), "COTAV")
    assert "atributo por inserção" not in l, l
