# -*- coding: utf-8 -*-
"""O metro de layer de CONEXÃO que é o contorno das peças não sai medido.

🩸 01/10/2026 — H76 do estudo do acervo. O motor mede a linha de dentro dos
blocos nos layers de infra linear, e a peça (condulete, conexão, luva, caixa)
mora em layer com nome de eletroduto: o metro desses layers é o CONTORNO das
peças somado. Um job de iluminação entregou "conexões para eletroduto
376,8 ml ✓" (988 conduletes de 0,38 m de contorno), com as mesmas peças em un.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import layers_que_nao_provam, selo_apos_contorno_de_peca  # noqa: E402


def _ler(tmp_path, layer, n=30, lado=0.1, solta_m=0.0, nome_bloco="PECA"):
    """`n` inserções de um bloco quadrado de lado `lado` (contorno 4×lado) no
    `layer`, mais `solta_m` metros de linha solta no mesmo layer."""
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = 6
    blk = d.blocks.new(name=nome_bloco)
    pts = [(0, 0), (lado, 0), (lado, lado), (0, lado), (0, 0)]
    for a, b in zip(pts, pts[1:]):
        blk.add_line(a, b, dxfattribs={"layer": layer})
    msp = d.modelspace()
    for i in range(n):
        msp.add_blockref(nome_bloco, (i * 2.0, 0), dxfattribs={"layer": layer})
    if solta_m:
        msp.add_line((0, 50), (solta_m, 50), dxfattribs={"layer": layer})
    p = str(tmp_path / "pecas.dxf")
    d.saveas(p)
    return dx.extract_dxf(p)


@pytest.mark.parametrize("layer", ["Condulete com Rosca BSP", "E-ELETRODUTOCONEXAO",
                                   "Conexões do conduite"])
def test_o_caso_layer_de_conexao_e_contorno_de_peca(tmp_path, layer):
    ex = _ler(tmp_path, layer)
    ct = ex.metadata.get("layers_contorno_de_peca") or {}
    assert layer in ct, sorted(ex.metadata)
    assert ct[layer]["insercoes"] == 30 and ct[layer]["m_por_insercao"] == pytest.approx(0.4), ct
    assert layer.upper() in layers_que_nao_provam(ex.metadata)
    assert "CONTORNO DE PEÇA" in ex.to_structured_prompt()


def test_a_linha_confirmada_em_metro_cai():
    conf, obs, rebaixou = selo_apos_contorno_de_peca(
        "confirmado", "Fonte: layer E-ELETRODUTOCONEXAO", "ml", ["E-ELETRODUTOCONEXAO"],
        {"E-ELETRODUTOCONEXAO": {}})
    assert rebaixou and conf == "estimado" and "CONTORNO DE PEÇA" in obs


def test_CONTROLE_a_contagem_em_un_nao_e_tocada():
    conf, _obs, rebaixou = selo_apos_contorno_de_peca(
        "confirmado", "988 conduletes", "un", ["E-ELETRODUTOCONEXAO"], {"E-ELETRODUTOCONEXAO": {}})
    assert not rebaixou and conf == "confirmado"


def test_o_laco_de_producao_rebaixa_a_linha():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Conexões para eletroduto",
            "unit": "ml", "quantity": 376.8, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'E-ELETRODUTOCONEXAO' = 376.8 m."}
    itens, _esc, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"E-ELETRODUTOCONEXAO": 376.8},
        extra={"_ctp_ly": {"E-ELETRODUTOCONEXAO"}})
    assert itens[0].confidence.value == "estimado", itens[0].observations
    assert "CONTORNO DE PEÇA" in itens[0].observations


def test_CONTROLE_o_laco_sem_contorno_nao_mexe():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Conexões para eletroduto",
            "unit": "ml", "quantity": 37.0, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'E-ELETRODUTOCONEXAO' = 37.0 m."}
    itens, _esc, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"E-ELETRODUTOCONEXAO": 37.0}, extra={"_ctp_ly": set()})
    assert "CONTORNO DE PEÇA" not in itens[0].observations


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_layer_de_eletroduto_com_trecho_em_bloco(tmp_path):
    """O Revit põe trecho de eletroduto em bloco: o nome não é de peça."""
    ex = _ler(tmp_path, "ELETRODUTO")
    assert not ex.metadata.get("layers_contorno_de_peca")


def test_CONTROLE_poucas_insercoes(tmp_path):
    ex = _ler(tmp_path, "Condulete com Rosca BSP", n=10)
    assert not ex.metadata.get("layers_contorno_de_peca")


def test_CONTROLE_bloco_grande_e_trecho_nao_peca(tmp_path):
    """30 inserções de 8 m de contorno cada: é trecho desenhado em bloco."""
    ex = _ler(tmp_path, "Condulete com Rosca BSP", lado=2.0)
    assert not ex.metadata.get("layers_contorno_de_peca")


def test_CONTROLE_layer_quase_todo_em_linha_solta(tmp_path):
    """12 m de contorno de peça + 30 m de linha solta: o layer é rede."""
    ex = _ler(tmp_path, "Condulete com Rosca BSP", solta_m=30.0)
    assert not ex.metadata.get("layers_contorno_de_peca")
