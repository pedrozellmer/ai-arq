# -*- coding: utf-8 -*-
"""Peça que se chama "bloco" não é bloco do CAD sem identidade.

🩸 31/10/2026 (73e07b47): "Bloco autônomo de sinalização de saída", num projeto só de
PDF, saiu com "não sabemos o que é este elemento: o nome do bloco no CAD não diz".
📏 60 dias: 43 linhas em 13 jobs de cliente, 33 de CAD. Bloco autônomo é luminária de emergência,
bloco de coroamento é peça de concreto.
🔑 BLOCO_QUE_E_PECA_NAO_REBAIXA=1 poupa a linha; com 0 o motor só conta.
As descrições abaixo são as do banco (cortadas).
"""
import os
import sys
import textwrap

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
import pytest  # noqa: E402
import main  # noqa: E402
from engine_rules import (bloco_e_nome_de_peca, contar_bloco_que_e_peca,  # noqa: E402
                          item_e_bloco_sem_identidade)
from models import BudgetItem, Confidence  # noqa: E402

_PECAS = [
    "Bloco autônomo de sinalização de saída (placa de rota de fuga) com LEDs",
    "Bloco autônomo para aclaramento — com lâmpada compacta de 9W",
    "Bloco autonomo para balizamento",
    "Bloco de coroamento de estaca — altura H.B. = 0,80 m",
    "Bloco de coroamento tipo B02E400 — 2 estacas Ø400 mm",
    "Blocos de coroamento sobre estacas",
    "Bloco de fundação B3",
    "Blocos de fundação — tipo B1",
    "Bloco sobre estacas tipo B2",
    "Blocos de enchimento de laje",
    "Bloco cerâmico 19×39 cm para alvenaria de fachada",
    "Bloco de concreto 14×19×39",
]

_NAO_SAO = [
    "Bloco não identificado — 'CP525_p' — verificar com projetista",
    "Bloco de equipamento — verificar com projetista",
    "Bloco de ponto elétrico sem nome",
    "Bloco estrutural — elemento a identificar",
    "Bloco A3 — elemento a identificar na prancha",
    "Bloco de coroamento não identificado — bloco 'X1'",
    "Bloco autônomo _DOT",
    "Elemento de marcenaria",
    "Porta com bloco de concreto",
    "Bloco autonomia",
    # nome de bloco do CAD que só começa igual
    "Bloco de concreto_01",
]


@pytest.mark.parametrize("d", _PECAS)
def test_a_peca_e_reconhecida(d):
    assert bloco_e_nome_de_peca(d), d


@pytest.mark.parametrize("d", _NAO_SAO)
def test_CONTROLE_o_que_nao_e_peca(d):
    assert not bloco_e_nome_de_peca(d), d


def _it(d=_PECAS[0], cf="confirmado", unit="un", obs="Contagem do desenho."):
    return BudgetItem(item_num="1", description=d, unit=unit, quantity=8, observations=obs,
                      ref_sheet="a.dxf", confidence=Confidence(cf), discipline="Elétrica",
                      origem="dxf_geom")


def test_chave_em_0_nada_muda():
    it = _it()
    assert item_e_bloco_sem_identidade(it.description, it.unit)
    assert main.rebaixar_itens_sem_identidade([it]) == 1
    assert it.confidence == Confidence.ESTIMADO
    assert "não sabemos o que é" in it.observations


def test_chave_em_1_a_peca_fica_como_estava():
    it = _it()
    assert main.rebaixar_itens_sem_identidade([it], poupa_peca=True) == 0
    assert it.confidence == Confidence("confirmado")
    assert it.observations == "Contagem do desenho."


def test_CONTROLE_chave_em_1_quem_nao_tem_identidade_segue_rebaixado():
    it = _it(_NAO_SAO[0])
    assert main.rebaixar_itens_sem_identidade([it], poupa_peca=True) == 1
    assert "não sabemos o que é" in it.observations


def test_chave_em_1_o_palpite_pelo_nome_do_bloco_segue_valendo():
    it = _it(_PECAS[3], obs="Bloco 'B7'. Nome do bloco sugere marco de controle topográfico.")
    assert main.rebaixar_itens_sem_identidade([it], poupa_peca=True) == 1
    assert it.confidence == Confidence.ESTIMADO


def test_a_contagem_so_ve_quem_o_guarda_pegaria():
    itens = [_it(), _it(_PECAS[3]), _it(_NAO_SAO[0]), _it("Porta de abrir"), _it(unit="ml")]
    assert contar_bloco_que_e_peca(itens) == 2
    assert contar_bloco_que_e_peca([]) == 0


# ── o bloco do process_job, executado de verdade ──
_INICIO = "        # 🩸 31/10: \"Bloco autônomo\" e \"Bloco de coroamento\" são peças"
_FIM = "motor:bloco-que-e-peca\", f\"FALHOU: {_ebp}\", job_id,\n                       severity=\"warning\")\n"


def _bloco():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read().replace("\r\n", "\n")
    i = src.index(_INICIO)
    return src[i:src.index(_FIM, i) + len(_FIM)]


def _rodar(liga, monkeypatch):
    logs = []
    monkeypatch.setenv("BLOCO_QUE_E_PECA_NAO_REBAIXA", "1" if liga else "0")
    ns = {"all_items": [_it()], "job_id": "t1",
          "_log_error": lambda st, msg, job=None, severity="error": logs.append((st, msg))}
    exec(textwrap.dedent(_bloco()), ns)
    return ns["_bloco_peca_liga"], logs


def test_a_chave_em_0_so_registra(monkeypatch):
    assert _rodar(False, monkeypatch) == (False, [("motor:bloco-que-e-peca", "linhas=1 liga=0")])


def test_a_chave_em_1_liga(monkeypatch):
    assert _rodar(True, monkeypatch) == (True, [("motor:bloco-que-e-peca", "linhas=1 liga=1")])


@pytest.mark.parametrize("valor,liga", [("1", True), ("0", False)])
def test_a_chave_vem_do_job(valor, liga):
    # é o caminho de produção: a avaliação isolada liga a chave só naquele job
    ns = {"all_items": [], "job_id": "t1", "_chave_do_job": lambda job, chave: valor,
          "_log_error": lambda *a, **k: None}
    exec(textwrap.dedent(_bloco()), ns)
    assert ns["_bloco_peca_liga"] is liga


def test_o_process_job_passa_a_chave_pro_guarda():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        assert "rebaixar_itens_sem_identidade(all_items, poupa_peca=_bloco_peca_liga)" in f.read()


def test_a_chave_e_avaliavel_e_o_log_e_diagnostico():
    assert "BLOCO_QUE_E_PECA_NAO_REBAIXA" in main._CHAVES_AVALIAVEIS
    assert "motor:bloco-que-e-peca" in main._STAGES_DIAGNOSTICO
