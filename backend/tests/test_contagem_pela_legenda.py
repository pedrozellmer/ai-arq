# -*- coding: utf-8 -*-
"""CONT.SE da tabela da legenda: o símbolo desenhado na tabela, contado na
planta onde aparece o MESMO desenho, no mesmo tamanho.

🩸 25/09/2026 — job `73c6f0ed` (orçamentista, projeto luminotécnico): a
tabela SÍMBOLO | QTD ("00") | DESCRIÇÃO deixava a quantidade pra quem orça;
os símbolos eram desenho solto, não bloco, e as luminárias saíram ZERADAS. O
cliente contou à mão. O motor agora acha jardim 11 e AR111 6 — os números
dele — e NÃO chuta as linhas cujo símbolo na planta foi redesenhado diferente
(🪤 com escala livre achava 32 no lugar de 11).
"""
import math
import os
import sys

import ezdxf

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from dwg_extractor import DXFExtraction  # noqa: E402

H = 0.1
PLANTA = (0.0, 0.0, 30.0, 30.0)


def _jardim(msp, x, y, k=1.0):
    msp.add_circle((x, y), 0.035 * k, dxfattribs={"layer": "LUM"})
    msp.add_circle((x, y), 0.056 * k, dxfattribs={"layer": "LUM"})


def _doc(com_cabecalho=True):
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    # a tabela, DENTRO da janela da planta (acontece: a legenda no modelo)
    if com_cabecalho:
        msp.add_text("SÍMBOLO", dxfattribs={"height": H, "insert": (20.0, 28.0)})
    msp.add_text("QTD", dxfattribs={"height": H, "insert": (20.8, 28.0)})
    msp.add_text("DESCRIÇÃO - LUMINÁRIA", dxfattribs={"height": H, "insert": (21.3, 28.0)})
    msp.add_text("LUM. EXTERNA JARDIM", dxfattribs={"height": H, "insert": (21.3, 27.5)})
    _jardim(msp, 20.2, 27.53)
    msp.add_text("PLAFON QUADRADO", dxfattribs={"height": H, "insert": (21.3, 27.0)})
    msp.add_lwpolyline([(20.1, 26.95), (20.3, 26.95), (20.3, 27.15), (20.1, 27.15)], close=True,
                       dxfattribs={"layer": "LUM"})
    msp.add_circle((20.2, 27.05), 0.05, dxfattribs={"layer": "LUM"})
    msp.add_text("PERFIL LED", dxfattribs={"height": H, "insert": (21.3, 26.5)})
    msp.add_line((20.05, 26.53), (20.4, 26.53), dxfattribs={"layer": "LUM"})     # 1 peça só
    # a planta: 3 jardins iguais + 1 girado (círculos: igual) + 1 em escala 0,8
    for x in (2.0, 5.0, 8.0, 11.0):
        _jardim(msp, x, 5.0)
    _jardim(msp, 14.0, 5.0, k=0.8)
    # quase iguais (outro símbolo): uma peça no tamanho certo, a outra não
    msp.add_circle((17.0, 5.0), 0.035, dxfattribs={"layer": "LUM"})
    msp.add_circle((17.0, 5.0), 0.080, dxfattribs={"layer": "LUM"})
    msp.add_circle((20.0, 5.0), 0.020, dxfattribs={"layer": "LUM"})
    msp.add_circle((20.0, 5.0), 0.056, dxfattribs={"layer": "LUM"})
    _jardim(msp, 40.0, 5.0)                                   # fora da planta
    # plafon como BLOCO, 2×, girado 90°
    b = doc.blocks.new("PLAF")
    b.add_lwpolyline([(-0.1, -0.1), (0.1, -0.1), (0.1, 0.1), (-0.1, 0.1)], close=True, dxfattribs={"layer": "LUM"})
    b.add_circle((0, 0), 0.05, dxfattribs={"layer": "LUM"})
    for x in (3.0, 6.0):
        msp.add_blockref("PLAF", (x, 10.0), dxfattribs={"rotation": 90})
    # o traço do perfil repetido na planta (não pode virar contagem)
    for x in (2.0, 4.0, 6.0):
        msp.add_line((x, 15.0), (x + 0.35, 15.0), dxfattribs={"layer": "LUM"})
    return doc


def _mapa(com_planta=True):
    return {"folhas": [{"tipo": "planta", "titulo": "PLANTA TÉRREO", "caixa": PLANTA}] if com_planta else []}


def _r(doc, mapa):
    return {x["descricao"]: x["n"] for x in dx.contagem_pela_legenda(doc, mapa)}


def test_conta_o_mesmo_desenho_na_planta():
    r = _r(_doc(), _mapa())
    assert r.get("LUM. EXTERNA JARDIM") == 4, r      # 4 iguais; escala 0,8, quase iguais e o de fora não


def test_conta_o_simbolo_desenhado_como_bloco_e_girado():
    r = _r(_doc(), _mapa())
    assert r.get("PLAFON QUADRADO") == 2, r


def test_CONTROLE_simbolo_de_uma_peca_nao_conta():
    assert "PERFIL LED" not in _r(_doc(), _mapa())


def test_CONTROLE_sem_janela_de_planta_nao_conta():
    assert dx.contagem_pela_legenda(_doc(), _mapa(com_planta=False)) == []


def test_CONTROLE_sem_tabela_nao_conta():
    assert dx.contagem_pela_legenda(_doc(com_cabecalho=False), _mapa()) == []


def test_a_ia_recebe_a_contagem():
    ex = DXFExtraction(filename="x.dxf", blocks=[], walls=[], hatches=[], texts=[], layers=[],
                       dimensions=[], metadata={})
    ex.folhas = {"legenda_contagem": [{"descricao": "LUM. EXTERNA JARDIM", "n": 4,
                                        "por_planta": {"PLANTA TÉRREO": 4}}]}
    txt = ex.to_structured_prompt()
    assert "CONTAGEM PELO SÍMBOLO DA LEGENDA" in txt and "LUM. EXTERNA JARDIM = 4" in txt


def test_cabecalho_da_tabela_nao_vira_sigla():
    T = dx.TextAnnotation
    s = dx.siglas_da_legenda([T(layer="0", text="QTD", position=(0, 0), height=0.1),
                              T(layer="0", text="DESCRIÇÃO - LUMINÁRIA", position=(0.5, 0), height=0.1)])
    assert "QTD" not in s


def test_distancia_nao_depende_de_rotacao():
    """Guarda da premissa: a assinatura usa DISTÂNCIA, que não muda ao girar."""
    a, c = (0.0, 0.0), (0.1, 0.0)
    ang = math.radians(90)
    c2 = (c[0] * math.cos(ang) - c[1] * math.sin(ang), c[0] * math.sin(ang) + c[1] * math.cos(ang))
    assert math.isclose(math.dist(a, c), math.dist(a, c2))
