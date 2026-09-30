# -*- coding: utf-8 -*-
"""Tubo desenhado pelas DUAS paredes (Revit P-PIPE) não sai medido.

🩸 30/09/2026 — H34 do estudo do acervo. O Revit exporta o tubo pelas duas
paredes: duas linhas paralelas à distância do diâmetro externo, sem eixo. A
soma do layer é o dobro do tubo. Um projeto de cliente saiu "tubulação
hidrossanitária 1.056 ml CONFIRMADO" (≈ 530 m de tubo) e o cliente aprovou.

v1 (segura): DETECTA o layer em face dupla — ≥ 80% do comprimento com uma
parceira paralela a um diâmetro ROTULADO no próprio desenho (ø150, %%c100) —,
AVISA no prompt e TIRA o selo da linha em metro que usa o layer. Não divide:
num feixe de tubos lado a lado o vão até o vizinho é menor que o diâmetro, e
"a parceira mais perto" seria o tubo errado.
"""
import math
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402


class W:
    def __init__(self, layer, a, b, uf=1.0, curvo=False, pontos=()):
        self.layer, self.start, self.end = layer, a, b
        self.curvo, self.pontos, self.peso = curvo, pontos, 1.0
        self.length = math.dist(a, b) * uf


class T:
    def __init__(self, text):
        self.text = text


def _feixe(layer="P-PIPE", n=3, d=0.150, vao=0.133, comp=10.0, uf=1.0):
    """n tubos lado a lado, cada um pelas 2 paredes a `d`; vão `vao` entre eles."""
    ws, y = [], 0.0
    for _ in range(n):
        ws.append(W(layer, (0, y / uf), (comp / uf, y / uf), uf))
        ws.append(W(layer, (0, (y + d) / uf), (comp / uf, (y + d) / uf), uf))
        y += d + vao
    return ws


def test_o_caso_real_feixe_de_tubos_em_face_dupla():
    fd = dx.tubos_em_face_dupla(_feixe(), [T("ø150"), T("PVC-ø75")])
    assert "P-PIPE" in fd and fd["P-PIPE"]["fracao"] >= 0.8, fd
    # os que PAREARAM, por metros — o ø75 foi rotulado mas não tem par (30/09:
    # o aviso listava os 5 menores rotulados e escondia o ø150 que dominava)
    assert fd["P-PIPE"]["diametros_mm"] == [150]


def test_os_diametros_do_aviso_vao_pelos_metros_em_par():
    ws = _feixe(n=1, d=0.075, comp=2.0) + _feixe(n=3, d=0.150, comp=10.0)
    for w in ws[2:]:
        w.start = (w.start[0], w.start[1] + 5)
        w.end = (w.end[0], w.end[1] + 5)
    fd = dx.tubos_em_face_dupla(ws, [T("ø25"), T("ø75"), T("ø150")])
    assert fd["P-PIPE"]["diametros_mm"] == [150, 75], fd


def test_layer_acima_do_teto_e_amostrado_e_nao_pulado(monkeypatch):
    """17d6e1f2/788d0270/4b2db70b: 23 a 41 mil trechos no P-PIPE. Pular o
    layer grande pulava justo os maiores danos."""
    monkeypatch.setattr(dx, "_TUBO_MAX_SEG", 4)
    ws = _feixe(n=3) + [W("P-PIPE", (0, 20 + k), (0.5, 20 + k)) for k in range(6)]
    fd = dx.tubos_em_face_dupla(ws, [T("ø150")])
    assert "P-PIPE" in fd and fd["P-PIPE"]["fracao"] >= 0.8, fd


def test_desenho_em_milimetro_tambem():
    fd = dx.tubos_em_face_dupla(_feixe(uf=0.001), [T("%%c150")], unit_factor=0.001)
    assert "P-PIPE" in fd, fd


def test_polilinha_de_tubo_pelos_lados():
    # as duas paredes como UMA polilinha em U: ida numa, volta na outra
    pts = ((0, 0, 0), (10, 0, 0), (10, 0.15, 0), (0, 0.15, 0))
    w = W("P-PIPE", (0, 0), (0, 0.15), pontos=pts)
    w.length = 20.15
    fd = dx.tubos_em_face_dupla([w], [T("ø150")])
    assert "P-PIPE" in fd, fd


@pytest.mark.parametrize("walls,textos", [
    (_feixe(), []),                                         # sem diâmetro rotulado: não decide
    (_feixe(d=0.40, vao=0.40), [T("ø150")]),                # linhas a 0,40: não é a parede
    (_feixe(layer="ELETRODUTO"), [T("ø150")]),               # eletroduto é linha única
    (_feixe(layer="ELETROTUBO"), [T("ø150")]),               # "tubo" dentro de palavra
    (_feixe(d=0.20, vao=0.50), [T("ø150")]),                 # par a 0,20: 33% fora do ø150
    (_feixe(layer="AGUA FRIA"), [T("ø150")]),                # nome não é de tubo
    (_feixe(comp=1.0, n=1), [T("ø150")]),                    # layer pequeno (2 m)
])
def test_CONTROLE_nao_e_face_dupla(walls, textos):
    assert dx.tubos_em_face_dupla(walls, textos) == {}


def test_CONTROLE_so_metade_do_layer_em_par_nao_basta():
    ws = _feixe(n=2) + [W("P-PIPE", (0, 5 + k), (10, 5 + k)) for k in range(4)]
    assert dx.tubos_em_face_dupla(ws, [T("ø150")]) == {}


def test_CONTROLE_tubo_em_linha_unica_com_vizinhos_longe():
    ws = [W("P-PIPE", (0, k * 0.6), (10, k * 0.6)) for k in range(6)]
    assert dx.tubos_em_face_dupla(ws, [T("ø150"), T("ø100")]) == {}


def test_os_rotulos_de_diametro():
    ds = dx._diametros_rotulados([T("ø150"), T("Ø 100"), T("%%c75"), T("ø35-CPVC"),
                                  T("ø3/4\""), T("ø1500"), T("Ø8 c/15")])
    assert ds == [35, 75, 100, 150], ds


def test_o_selo_sai_da_linha_do_tubo_em_face_dupla():
    conf, obs, reb = er.selo_apos_tubo_em_face_dupla(
        "confirmado", "Fonte: comprimento do layer 'P-PIPE' = 1056.04 m.", "ml",
        ["P-PIPE"], {"P-PIPE"})
    assert reb and conf == "estimado"
    assert obs.startswith(er.MARCA_TUBO_FACE_DUPLA) and "METADE" in obs
    assert er.MARCA_TUBO_FACE_DUPLA in er.MARCAS_DE_REBAIXAMENTO


@pytest.mark.parametrize("conf,unit,citados,fd", [
    ("estimado", "ml", ["P-PIPE"], {"P-PIPE"}),     # já estimado
    ("confirmado", "un", ["P-PIPE"], {"P-PIPE"}),   # contagem não é comprimento
    ("confirmado", "ml", ["P-PIPE-IDEN"], {"P-PIPE"}),
    ("confirmado", "ml", ["P-PIPE"], set()),
])
def test_CONTROLE_o_selo_fica(conf, unit, citados, fd):
    c, _o, reb = er.selo_apos_tubo_em_face_dupla(conf, "obs", unit, citados, fd)
    assert not reb and c == conf


def test_o_layer_em_face_dupla_nao_prova_quantidade():
    assert "P-PIPE" in er.layers_que_nao_provam({"tubos_em_face_dupla": {"P-PIPE": {}}})


def test_o_laco_de_producao_rebaixa_a_linha():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Tubulação hidrossanitária PVC",
            "unit": "ml", "quantity": 1056.04, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'P-PIPE' = 1056.04 m."}
    itens, _esc, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"P-PIPE": 1056.04}, extra={"_fd_ly": {"P-PIPE"}})
    assert itens[0].confidence.value == "estimado", itens[0].observations
    assert "TUBO EM FACE DUPLA" in itens[0].observations


def test_CONTROLE_o_laco_sem_face_dupla_nao_mexe():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Tubulação hidrossanitária PVC",
            "unit": "ml", "quantity": 50.0, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'P-PIPE' = 50.00 m."}
    itens, _esc, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"P-PIPE": 50.0}, extra={"_fd_ly": set()})
    assert "TUBO EM FACE DUPLA" not in itens[0].observations


def test_de_ponta_a_ponta_a_extracao_marca_e_o_prompt_avisa(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    y = 0.0
    for _ in range(3):
        msp.add_line((0, y), (10, y), dxfattribs={"layer": "P-PIPE"})
        msp.add_line((0, y + 0.15), (10, y + 0.15), dxfattribs={"layer": "P-PIPE"})
        y += 0.283
    msp.add_lwpolyline([(20, 0), (30, 0), (30, 0.1), (20, 0.1)], dxfattribs={"layer": "P-PIPE"})
    msp.add_text("ø150", dxfattribs={"layer": "P-PIPE-IDEN", "height": 0.2}).set_placement((5, 2))
    msp.add_text("ø100", dxfattribs={"layer": "P-PIPE-IDEN", "height": 0.2}).set_placement((25, 2))
    msp.add_line((0, -5), (8, -5), dxfattribs={"layer": "PAREDE"})
    p = str(tmp_path / "tubo.dxf")
    doc.saveas(p)
    ex = dx.extract_from_file(p)
    assert "P-PIPE" in (ex.metadata.get("tubos_em_face_dupla") or {}), ex.metadata
    txt = ex.to_structured_prompt()
    linha = next((l for l in txt.splitlines() if l.strip().startswith("P-PIPE:")), "")
    assert "TUBO EM FACE DUPLA" in linha and "METADE" in linha, linha
    assert "tubos_em_face_dupla" not in txt
