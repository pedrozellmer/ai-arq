# -*- coding: utf-8 -*-
"""O título no PAPEL, do lado da convenção da folha, vence o texto do MODELO
quando os dois discordam — o corte do Revit não é somado como planta.

🩸 30/09/2026 — H54, o erro inverso. No corte do Revit, os níveis escritos no
desenho ("TÉRREO", "COBERTURA", "TELHADO") eram a maior letra da região e
viravam o título → 'planta' (somado); o título de verdade, "CORTE AA", estava no
papel logo abaixo da janela. Tabela do estudo (12 janelas com título no modelo
e no papel): o papel do lado da convenção acerta 8, erra 0; o papel do lado
CONTRÁRIO errou 1 (um esquema de rede com "Planta Baixa" escrito em cima).
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
from test_a_leitura_por_folha import _viewport  # noqa: E402


def _folha(janelas, ab=None, ac=None):
    """janelas: [textos_do_modelo]; ab/ac: {índice: título no papel abaixo/acima}."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    lay = doc.layouts.new("CORTES")
    for k, tits in enumerate(janelas):
        x0 = 40.0 * k
        for i, t in enumerate(tits):
            msp.add_text(t, dxfattribs={"height": 0.3, "insert": (x0 + 2 + 6 * i, 2)})
        msp.add_line((x0 + 1, 1), (x0 + 18, 1))
        cx = 150 + 250 * k                       # papel: 200 × 150 por janela
        _viewport(lay, (x0, 0, x0 + 20, 15), centro_papel=(cx, 150))
        if ab and k in ab:
            lay.add_text(ab[k], dxfattribs={"height": 5, "insert": (cx - 95, 65)})
        if ac and k in ac:
            lay.add_text(ac[k], dxfattribs={"height": 5, "insert": (cx - 95, 235)})
    return sorted(dx.mapa_de_folhas(doc)["folhas"], key=lambda f: f["caixa"][0])


_NIVEIS = ["TÉRREO", "COBERTURA"]


def test_o_caso_corte_com_niveis_e_titulo_no_papel_abaixo_nao_e_planta():
    fs = _folha([_NIVEIS, _NIVEIS, _NIVEIS, []],
                ab={0: "CORTE AA", 1: "CORTE BB", 2: "CORTE CC", 3: "PLANTA BAIXA TÉRREO"})
    for f in fs[:3]:
        assert f["tipo"] == "vista" and f.get("papel_venceu_modelo") == "TÉRREO | COBERTURA", f
    assert fs[3]["tipo"] == "planta", fs[3]


def test_o_numero_da_vista_do_revit_nao_e_o_titulo():
    # o bloco de título do Revit: o número da vista em letra MAIOR que o nome
    pap = (100, 75, 300, 225)
    tx = [("6", 106, 66, 4.0), ("CORTE AA", 112, 66, 3.5), ("1 : 50", 112, 60, 2.5)]
    assert dx._titulo_no_papel(pap, tx) == "CORTE AA"
    assert dx._titulo_no_papel(pap, [("6", 106, 66, 4.0)]) == ""


def test_o_caso_do_revit_com_numero_da_vista_tambem_decide_a_convencao():
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    lay = doc.layouts.new("FOLHA REVIT")
    nomes = ["CORTE AA", "CORTE BB", "CORTE CC", "PLANTA BAIXA TÉRREO"]
    for k, nome in enumerate(nomes):
        x0 = 40.0 * k
        if k < 3:                                # os cortes: os níveis viram o título do modelo
            for i, t in enumerate(_NIVEIS):
                msp.add_text(t, dxfattribs={"height": 0.3, "insert": (x0 + 2 + 6 * i, 2)})
        msp.add_line((x0 + 1, 1), (x0 + 18, 1))
        cx = 150 + 250 * k
        _viewport(lay, (x0, 0, x0 + 20, 15), centro_papel=(cx, 150))
        lay.add_text(str(k + 5), dxfattribs={"height": 6, "insert": (cx - 98, 65)})   # o número, maior
        lay.add_text(nome, dxfattribs={"height": 5, "insert": (cx - 90, 65)})
    m = dx.mapa_de_folhas(doc)
    fs = sorted(m["folhas"], key=lambda f: f["caixa"][0])
    assert m.get("convencao") == {"FOLHA REVIT": "abaixo"}, m.get("convencao")
    assert [f["tipo"] for f in fs] == ["vista", "vista", "vista", "planta"], fs


def test_a_convencao_sai_no_mapa():
    doc = ezdxf.new("R2018")
    lay = doc.layouts.new("CORTES")
    for k in range(3):
        doc.modelspace().add_line((40.0 * k + 1, 1), (40.0 * k + 18, 1))
        _viewport(lay, (40.0 * k, 0, 40.0 * k + 20, 15), centro_papel=(150 + 250 * k, 150))
        lay.add_text("CORTE %d" % k, dxfattribs={"height": 5, "insert": (150 + 250 * k - 95, 65)})
    assert dx.mapa_de_folhas(doc).get("convencao") == {"CORTES": "abaixo"}


def test_convencao_de_5_contra_3_ainda_decide():
    # a casa do Revit: 5 títulos abaixo × 3 acima
    fs = _folha([["TELHADO"], [], [], [], []],
                ab={0: "CORTE 1", 1: "CORTE 2", 2: "TÉRREO - LAYOUT", 3: "COBERTURA", 4: "CORTE 3"},
                ac={1: "PLANTA BAIXA TÉRREO", 2: "CORTE 4", 3: "CORTE 5"})
    assert fs[0]["tipo"] == "vista" and fs[0].get("papel_venceu_modelo") == "TELHADO", fs[0]


def test_folha_que_escreve_em_cima_procura_em_cima():
    fs = _folha([[], [], [], _NIVEIS],
                ac={0: "PLANTA BAIXA TÉRREO", 1: "CORTE AA", 2: "CORTE BB", 3: "CORTE CC"},
                ab={1: "CORTE ZZ"})
    assert [f["tipo"] for f in fs] == ["planta", "vista", "vista", "vista"], fs
    assert fs[3].get("papel_venceu_modelo"), fs[3]


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_papel_que_concorda_nao_mexe():
    fs = _folha([_NIVEIS, [], [], []],
                ab={0: "PLANTA DE COBERTURA", 1: "CORTE AA", 2: "CORTE BB", 3: "CORTE CC"})
    assert fs[0]["tipo"] == "planta" and not fs[0].get("papel_venceu_modelo"), fs[0]


def test_CONTROLE_papel_do_lado_contrario_a_convencao_nao_vale():
    # o esquema de rede com "Planta Baixa" escrito EM CIMA, numa folha de títulos embaixo
    fs = _folha([["ESQUEMA LÓGICO"], [], [], []],
                ab={1: "CORTE AA", 2: "CORTE BB", 3: "CORTE CC"},
                ac={0: "Planta Baixa Escala 1/100"})
    assert fs[0]["tipo"] == "fora" and not fs[0].get("papel_venceu_modelo"), fs[0]


@pytest.mark.parametrize("ab,ac", [
    ({0: "CORTE AA", 1: "CORTE BB"}, {}),                              # só 2 janelas: não decide
    ({0: "CORTE AA", 1: "CORTE BB", 2: "CORTE CC"}, {1: "CORTE X", 2: "CORTE Y", 3: "CORTE Z"}),  # 3 × 3
])
def test_CONTROLE_convencao_fraca_fica_como_hoje(ab, ac):
    fs = _folha([_NIVEIS, [], [], []], ab=ab, ac=ac)
    assert fs[0]["tipo"] == "planta" and not fs[0].get("papel_venceu_modelo"), fs[0]


def test_CONTROLE_texto_do_papel_que_nao_e_titulo_nao_faz_convencao():
    # embaixo das outras janelas há texto, mas é nota — não diz o que o desenho é
    fs = _folha([_NIVEIS, [], [], []],
                ab={0: "CORTE AA", 1: "NOTA GERAL", 2: "COTAS EM CM", 3: "REV 02"})
    assert fs[0]["tipo"] == "planta" and not fs[0].get("papel_venceu_modelo"), fs[0]


def test_CONTROLE_sem_titulo_no_modelo_segue_pegando_o_papel_de_baixo():
    fs = _folha([[], [], []], ab={0: "CORTE AA"})
    assert fs[0]["tipo"] == "vista" and fs[0].get("titulo_no_papel"), fs[0]


def test_CONTROLE_marca_na_planta_continua_sem_tipo_mesmo_com_convencao():
    # a (b'): marca "CORTE 1" + 3 ambientes = a planta; nem o papel decide
    fs = _folha([["CORTE 1", "QUARTO", "SALA", "COZINHA"], [], [], []],
                ab={0: "PLANTA BAIXA TÉRREO", 1: "CORTE AA", 2: "CORTE BB", 3: "CORTE CC"})
    assert fs[0]["tipo"] == "" and fs[0].get("marca_na_planta"), fs[0]
    assert not fs[0].get("papel_venceu_modelo"), fs[0]
