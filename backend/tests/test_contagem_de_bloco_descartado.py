# -*- coding: utf-8 -*-
"""A linha que repete a contagem de um bloco que o motor DESCARTOU não sai medida.

🩸 19/11/2026 — num prédio, o motor deixou fora as janelas dinâmicas (o bloco
era a FOLHA de janelas de 3 a 11 folhas; o quadro somava 29). A lista de
descartados vai pro prompt, e a IA escreveu "67 INSERTs do bloco dinâmico '…'
(CONTAGEM DE BLOCOS)" com selo de medido. No ar, com a chave do dinâmico em 0,
o mesmo caminho deu luminária 337 ✓ e condulete 115 ✓.

🔑 SÓ REBAIXA, e só com SELO_BLOCO_DESCARTADO_REBAIXA=1 — com 0, o log
`motor:contagem-de-descartado` diz o que faria. Dados sintéticos, na FORMA do caso.
"""
import inspect
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402
import main  # noqa: E402

_DESC = {"JANELA_FOLHA_X": 67, "PORTA_X": 15}
_OBS = "Fonte: 67 INSERTs do bloco dinâmico 'JANELA_FOLHA_X' (CONTAGEM DE BLOCOS)."


# ══════════════════════════════════════════════════════════════════════════
#  1. A regra
# ══════════════════════════════════════════════════════════════════════════
def test_linha_que_repete_o_descartado_perde_o_selo():
    conf, obs, rb = er.selo_apos_bloco_descartado("confirmado", _OBS, 67, "un", _DESC, {})
    assert rb is True
    assert conf == "estimado"
    assert obs.startswith(er.MARCA_BLOCO_DESCARTADO)
    assert "JANELA_FOLHA_X" in obs[:160]
    assert obs.endswith(_OBS)          # a procedência original fica


def test_bloco_contado_com_o_mesmo_nome_nao_e_tocado():
    """Com a chave do dinâmico, a peça contada de verdade sai da lista."""
    conf, obs, rb = er.selo_apos_bloco_descartado(
        "confirmado", _OBS, 67, "un", _DESC, {"JANELA_FOLHA_X": 67})
    assert (conf, obs, rb) == ("confirmado", _OBS, False)


@pytest.mark.parametrize("qtd", [66, 68, 29])
def test_outro_numero_nao_e_a_lista(qtd):
    conf, _o, rb = er.selo_apos_bloco_descartado("confirmado", _OBS, qtd, "un", _DESC, {})
    assert (conf, rb) == ("confirmado", False)


def test_linha_ja_estimada_nao_muda():
    conf, obs, rb = er.selo_apos_bloco_descartado("estimado", _OBS, 67, "un", _DESC, {})
    assert (conf, obs, rb) == ("estimado", _OBS, False)


def test_metro_nao_e_contagem():
    conf, _o, rb = er.selo_apos_bloco_descartado("confirmado", _OBS, 67, "m", _DESC, {})
    assert (conf, rb) == ("confirmado", False)


def test_sem_lista_nada_muda():
    assert er.selo_apos_bloco_descartado("confirmado", _OBS, 67, "un", {}, {}) == \
        ("confirmado", _OBS, False)


def test_bloco_citado_de_passagem_nao_decide():
    """A fonte é o bloco contado; o descartado só aparece como comparação."""
    obs = ("Fonte: 67 INSERTs do bloco 'JANELA_REAL' (CONTAGEM DE BLOCOS). "
           "Ver também bloco 'JANELA_FOLHA_X'.")
    conf, _o, rb = er.selo_apos_bloco_descartado(
        "confirmado", obs, 67, "un", _DESC, {"JANELA_REAL": 67})
    assert (conf, rb) == ("confirmado", False)


def test_a_marca_trava_a_promocao():
    assert er.MARCA_BLOCO_DESCARTADO in er.MARCAS_DE_REBAIXAMENTO


# ══════════════════════════════════════════════════════════════════════════
#  2. Do DXF à regra: a lista é a que a extração grava
# ══════════════════════════════════════════════════════════════════════════
def test_a_lista_da_extracao_alimenta_a_regra(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    doc.appids.new("AcDbBlockRepBTag")
    doc.blocks.new("JANELA_FOLHA_X").add_line((0, 0), (1, 0))
    u = doc.blocks.new_anonymous_block("U")
    u.add_line((0, 0), (1, 0))
    doc.block_records.get(u.name).set_xdata(
        "AcDbBlockRepBTag",
        [(1070, 1), (1005, doc.block_records.get("JANELA_FOLHA_X").dxf.handle)])
    for k in range(3):
        doc.modelspace().add_blockref(u.name, (k * 2, 0))
    p = str(tmp_path / "x.dxf")
    doc.saveas(p)
    ex = dx.extract_dxf(p)
    desc = ex.metadata["procedencia_blocos"]["dinamicos"]
    assert desc == {"JANELA_FOLHA_X": 3}
    obs = "Fonte: 3 INSERTs do bloco dinâmico 'JANELA_FOLHA_X' (CONTAGEM DE BLOCOS)."
    conf, _o, rb = er.selo_apos_bloco_descartado(
        "confirmado", obs, 3, "un", desc, ex.get_block_summary())
    assert (conf, rb) == ("estimado", True)


# ══════════════════════════════════════════════════════════════════════════
#  3. A chave e o log
# ══════════════════════════════════════════════════════════════════════════
def test_a_chave_e_avaliavel_e_nasce_0(monkeypatch):
    assert "SELO_BLOCO_DESCARTADO_REBAIXA" in main._CHAVES_AVALIAVEIS
    monkeypatch.delenv("SELO_BLOCO_DESCARTADO_REBAIXA", raising=False)
    assert main._chave_do_job("abc", "SELO_BLOCO_DESCARTADO_REBAIXA") == "0"


_INICIO = "                                if _blocos_descart:\n"
_FIM = "                                # 🩸 12/10/2026: o número ESCRITO num quadro do desenho"


def _rodar(liga, conf="confirmado", qty=67):
    """Roda o TRECHO real do main (o mesmo recorte do teste irmão)."""
    import textwrap
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read().replace("\r\n", "\n")
    i = src.index(_INICIO)
    ns = {"_blocos_descart": dict(_DESC), "_blocos_n": {}, "_liga_descart": liga,
          "_linhas_descart": [], "_rebaixado_pela_fonte": False,
          "conf": conf, "obs_raw": _OBS, "qty": qty, "normalized_unit": "un",
          "desc": "Janela 1 folha"}
    exec(textwrap.dedent(src[i:src.index(_FIM, i)]), ns)
    return ns


def test_com_a_chave_em_0_so_o_log():
    ns = _rodar(False)
    assert ns["conf"] == "confirmado" and ns["obs_raw"] == _OBS
    assert ns["_rebaixado_pela_fonte"] is False
    assert ns["_linhas_descart"] == ["Janela 1 folha=67"]


def test_com_a_chave_em_1_rebaixa_e_trava():
    ns = _rodar(True)
    assert ns["conf"] == "estimado"
    assert ns["obs_raw"].startswith(er.MARCA_BLOCO_DESCARTADO)
    assert ns["_rebaixado_pela_fonte"] is True, "sem a trava, o cross-check re-promoveria"
    assert ns["qty"] == 67, "não mexe no número"


def test_o_log_tem_estagio_proprio():
    assert "motor:contagem-de-descartado" in main._STAGES_DIAGNOSTICO
    assert "motor:contagem-de-descartado" in inspect.getsource(main)
