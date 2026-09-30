# -*- coding: utf-8 -*-
"""Nota da prancha com a palavra "PESO" não é cabeçalho de quadro de aço.

🩸 30/09/2026 — planta de fôrma do TQS, sem quadro de aço. A nota "PARA AS
ÁREAS REBAIXADAS (PESO < 150 kgf/m2)" virou cabeçalho, "205", "DET.2" e
"1084.5" da mesma altura viraram colunas do tamanho da folha, um Ø10 solto
virou linha e o NÍVEL da laje (803,07) virou "Aço Ø10: 803,07 kg", confiável.

Regras que os guardas prendem:
- célula longa (frase de nota) com "peso" não abre quadro;
- cabeçalho curto de verdade ("PESO + 10% PERDAS (kg)") continua abrindo;
- na linha de cabeçalho, a coluna de peso é a do cabeçalho curto — uma nota
  longa com "PESO TOTAL" ao lado não rouba a coluna.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from dwg_extractor import TextAnnotation as T  # noqa: E402
import structural_extractor as se  # noqa: E402

H = 2.5


def _folha_de_forma():
    """Sem quadro: nota com PESO + números soltos na mesma altura; embaixo, um
    Ø10 de furo e o nível da laje ao lado do rótulo dela."""
    return [T("225", "205", (100, 0), H), T("225", "DET.2", (300, 0), H), T("225", "1084.5", (500, 0), H),
            T("224", "PARA AS ÁREAS REBAIXADAS (PESO < 150 kgf/m2)", (800, 0), H),
            T("213", "%%c10", (150, -10), H), T("237", "803.07", (780, -10), H),
            T("228", "h=12", (790, -20), H), T("218", "L5", (760, -20), H)]


def test_nota_com_peso_nao_abre_quadro_e_o_nivel_nao_vira_kg():
    r = se.parse_steel_table(_folha_de_forma())
    assert r is None, r


def _quadro(cabecalho_peso, nota=None):
    txts = [T("0", "BITOLA", (100, 0), H), T("0", cabecalho_peso, (300, 0), H),
            T("0", "%%c8", (100, -10), H), T("0", "20.5", (300, -10), H),
            T("0", "%%c10", (100, -20), H), T("0", "12.5", (300, -20), H)]
    if nota:
        txts.append(T("0", nota, (800, 0), H))
    return txts


def test_CONTROLE_cabecalho_curto_de_verdade_continua_abrindo():
    r = se.parse_steel_table(_quadro("PESO + 10% PERDAS (kg)"))
    assert r and sorted((b["bitola_mm"], b["kg"]) for b in r["por_bitola"]) == [(8.0, 20.5), (10.0, 12.5)], r


def test_nota_longa_ao_lado_do_cabecalho_nao_rouba_a_coluna_de_peso():
    r = se.parse_steel_table(_quadro("PESO (kg)", nota="PESO TOTAL DAS BARRAS JÁ COM 10% DE PERDAS"))
    assert r and sorted((b["bitola_mm"], b["kg"]) for b in r["por_bitola"]) == [(8.0, 20.5), (10.0, 12.5)], r


def test_nota_com_peso_no_meio_do_quadro_nao_corta_o_quadro():
    # a nota fica na altura ENTRE duas linhas do quadro, do outro lado da folha:
    # se ela contasse como cabeçalho, seria o "próximo quadro" e cortaria o Ø10
    txts = _quadro("PESO (kg)")
    txts.append(T("0", "PARA AS ÁREAS REBAIXADAS (PESO < 150 kgf/m2)", (800, -15), H))
    r = se.parse_steel_table(txts)
    assert r and sorted((b["bitola_mm"], b["kg"]) for b in r["por_bitola"]) == [(8.0, 20.5), (10.0, 12.5)], r


def test_o_teto_do_cabecalho():
    assert se._e_cabecalho_de_peso("PESO (kg)")
    assert se._e_cabecalho_de_peso("PESO + 10% PERDAS (kg)")
    assert not se._e_cabecalho_de_peso("PARA AS ÁREAS REBAIXADAS (PESO < 150 kgf/m2)")
