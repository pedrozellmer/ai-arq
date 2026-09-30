# -*- coding: utf-8 -*-
"""Os símbolos do TQS não são peça.

🩸 30/09/2026 — H16 do estudo do acervo. 14 plantas de fôrma do TQS de um
cliente: "indicação de desnível 16–85 un" e "AVCR 19 un" saíram com selo, 10+
linhas. O que cada bloco desenha, sem texto nenhum: `_DESNIV` = círculo + 2
linhas; `_CORTEA` = a marca do corte; `AVCR` = círculo com cruz colado aos
"a", "b", "a×b" de um detalhe que se repete em todo andar; `SN` = círculo + 3
linhas ao lado de cotas. E `_VAONER…` é o VÃO da laje nervurada — a cubeta,
peça de verdade (2.719 num pavimento).
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402

_CUBETA = "_VAONER065250652500550005500"


def _bloco(doc, nome):
    # desenho diferente por nome: a assinatura do bloco não junta dois nomes
    b = doc.blocks.new(nome)
    b.add_circle((0, 0), 0.02 + 0.003 * len(nome))
    for i in range(2 + len(nome) % 3):
        b.add_line((-0.05, 0.01 * i), (0.05 + 0.001 * len(nome), 0.01 * i))


def _ler(tmp_path, nomes, n=6):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for nome in nomes:
        if nome == _CUBETA:
            b = doc.blocks.new(nome)
            b.add_lwpolyline([(0, 0), (0.68, 0), (0.68, 0.68), (0, 0.68)], close=True)
        else:
            _bloco(doc, nome)
        for i in range(n):
            msp.add_blockref(nome, (3.0 * i, 5.0 * len(nome)))
    p = str(tmp_path / "forma.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


def _contados(ex):
    return {b.name for b in ex.blocks}


@pytest.mark.parametrize("nome", ["_DESNIV", "AVCR", "_CORTEA", "_CORTEB", "_CORTE"])
def test_simbolo_do_tqs_sai_da_contagem(tmp_path, nome):
    ex = _ler(tmp_path, [nome, _CUBETA])
    assert nome not in _contados(ex), _contados(ex)
    assert ex.blocos_descartados.get("anotacao", 0) >= 6, ex.blocos_descartados


def test_sn_no_arquivo_do_tqs_e_simbolo(tmp_path):
    ex = _ler(tmp_path, ["SN", "AVCR"])
    assert "SN" not in _contados(ex), _contados(ex)


@pytest.mark.parametrize("marca", ["_DESNIV", "_CORTEA", _CUBETA])
def test_qualquer_marca_do_tqs_basta_pro_sn(tmp_path, marca):
    ex = _ler(tmp_path, ["SN", marca])
    assert "SN" not in _contados(ex), (marca, _contados(ex))


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_a_cubeta_da_laje_nervurada_continua_peca(tmp_path):
    ex = _ler(tmp_path, [_CUBETA, "_DESNIV"])
    assert _CUBETA in _contados(ex), _contados(ex)


def test_CONTROLE_sn_fora_do_tqs_continua_peca(tmp_path):
    ex = _ler(tmp_path, ["SN", "TOMADA"])
    assert "SN" in _contados(ex), _contados(ex)


@pytest.mark.parametrize("nome", ["_DESNIVEL_PISO", "AVCR2", "SNX", "_CORTEAB"])
def test_CONTROLE_so_o_nome_exato(tmp_path, nome):
    ex = _ler(tmp_path, [nome, "_DESNIV"])
    assert nome in _contados(ex), (nome, _contados(ex))
