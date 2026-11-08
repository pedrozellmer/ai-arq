# -*- coding: utf-8 -*-
"""Linha em verba não sai com o selo "✓ MEDIDO do CAD".

🩸 07/11/2026 (a8688985, elétrica de garagem): "Alimentador elétrico QDNTPA =
1 vb" saiu em BRANCO porque a fonte citava "1 INSERT do bloco '0. ALIM.
QDNTPA'". Contar a etiqueta do alimentador não mede o cabo, e verba vale 1 por
definição: não há o que medir. Cinco linhas assim no job, duas repetidas.
📏 90 dias: só esse job desde 24/08; antes, 5 linhas em agosto.
🔑 VERBA_NUNCA_BRANCA=1 rebaixa; com 0 o motor só conta (`motor:verba-branca`).
As descrições abaixo são as do banco (cortadas).
"""
import os
import sys
import textwrap

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
import pytest  # noqa: E402
import main  # noqa: E402
from engine_rules import verbas_brancas  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402


def _it(desc="Alimentador elétrico — QDNTPA — fornecimento e instalação de ramal",
        unit="vb", conf=Confidence.CONFIRMADO, obs="Fonte: 1 INSERT do bloco '0. ALIM. QDNTPA'"):
    return BudgetItem(item_num="1", description=desc, unit=unit, quantity=1.0,
                      confidence=conf, observations=obs)


@pytest.mark.parametrize("un", ["vb", "VB", "vb.", "verba", "gl", "global", " Vb "])
def test_verba_branca_e_achada(un):
    assert [a["indice"] for a in verbas_brancas([_it(unit=un)])] == [0]


@pytest.mark.parametrize("it", [
    _it(conf=Confidence.ESTIMADO),                       # já é laranja
    _it(unit="un", desc="Quadro de distribuição QDNTPA"),  # contagem de bloco
    _it(unit="cj", desc="Conjunto de ferragens para porta 0,80 m"),
    _it(unit="ml", desc="Eletroduto rígido Ø32 mm"),
])
def test_CONTROLE_o_que_nao_e_verba_branca(it):
    assert verbas_brancas([it]) == []


def test_aceita_dict_como_o_banco_devolve():
    linha = {"description": "Alimentador QDNTPB", "unit": "vb", "confidence": "confirmado"}
    assert len(verbas_brancas([linha, {**linha, "confidence": "estimado"}])) == 1


# ── o bloco do process_job, executado de verdade ──
_INICIO = "        # 🩸 08/11: VERBA não se mede do desenho (`verbas_brancas`)."
_FIM = "motor:verba-branca\", f\"FALHOU: {_evb}\", job_id,\n                       severity=\"warning\")\n"


def _bloco():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read().replace("\r\n", "\n")
    i = src.index(_INICIO)
    return src[i:src.index(_FIM, i) + len(_FIM)]


def _rodar(valor):
    logs = []
    itens = [_it(), _it(unit="un", desc="Quadro QDNTPA")]
    ns = {"all_items": itens, "job_id": "t1",
          "_chave_do_job": lambda job, chave: valor if chave == "VERBA_NUNCA_BRANCA" else "0",
          "_observacao_que_cabe": main._observacao_que_cabe,
          "_log_error": lambda st, msg, job=None, severity="error": logs.append(
              (st, msg.split(" | ")[0]))}
    exec(textwrap.dedent(_bloco()), ns)
    return itens, logs


def test_a_chave_em_0_so_registra():
    itens, logs = _rodar("0")
    assert itens[0].confidence == Confidence.CONFIRMADO
    assert not itens[0].observations.startswith("⚠ VERBA")
    assert logs == [("motor:verba-branca", "linhas=1 liga=0")]


def test_a_chave_em_1_rebaixa_so_a_verba():
    itens, logs = _rodar("1")
    assert itens[0].confidence == Confidence.ESTIMADO
    assert itens[0].observations.startswith("⚠ VERBA: não é medida do desenho")
    assert "INSERT" in itens[0].observations, "a fonte original sumiu da observação"
    assert itens[1].confidence == Confidence.CONFIRMADO, "a contagem em un perdeu o selo"
    assert logs == [("motor:verba-branca", "linhas=1 liga=1")]


def test_nasce_desligada_e_avaliavel():
    assert main._chave_do_job("job-qualquer", "VERBA_NUNCA_BRANCA") in ("0", os.environ.get("VERBA_NUNCA_BRANCA", "0"))
    assert "VERBA_NUNCA_BRANCA" in main._CHAVES_AVALIAVEIS
    assert "motor:verba-branca" in main._STAGES_DIAGNOSTICO


def test_o_bloco_roda_antes_da_planilha():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read()
    i = src.index("        # 🩸 08/11: VERBA não se mede do desenho")
    assert i < src.index("generate_spreadsheet(project_data, all_items, output_path, typology=typology)", i), (
        "o rebaixamento saiu de antes da planilha: o arquivo sairia com o selo velho")
