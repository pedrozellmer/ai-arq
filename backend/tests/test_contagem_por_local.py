# -*- coding: utf-8 -*-
"""Peça contada por "N por local" não é contagem do desenho.

🩸 30/10/2026 (27b39a2d): "Estimativa: ~3 tomadas por bancada (2 bancadas) = 6
tomadas", com a própria linha dizendo que a prancha não tem ponto elétrico. A régua
da densidade (27/09) cobre "por banheiro/sala/quarto"; bancada, WC, cozinha,
vestiário e espaço escapavam. 📏 Desde 28/09: 16 linhas em 5 jobs, todas de PDF.
🔑 CONTAGEM_POR_LOCAL_EM_BRANCO=1 deixa em branco; com 0 o motor só conta.
Os textos abaixo são os do banco (cortados).
"""
import os
import sys
import textwrap

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
import pytest  # noqa: E402
import main  # noqa: E402
from engine_rules import contagem_por_local  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

_PEGA = [
    "Estimativa: ~3 luminárias por espaço churrasqueira (16,84 m² cada) = 6 unidades.",
    "Estimativa: 2 tomadas por bancada (uso geral), totalizando 4 unidades para os 2 espaços.",
    "Estimativa: ~3 tomadas por bancada (2 bancadas) = 6 tomadas.",
    "Quantidade estimada: 1 un por vestiário (feminino + masculino = 2 un).",
    "Quantidade estimada: 1 bacia por lavabo PNE (feminino + masculino = 2 ambientes).",
    "Estimativa: ~4 pontos por WC (lavatório, vaso, chuveiro, torneira de limpeza) × 4 WC identificados",
    "Estimativa: ~2 pontos por cozinha (pia, máquina de lavar/lava-louça) × 6 cozinhas",
    "Estimativa: 1 ponto por área de serviço × 8 unidades.",
    "Estimativa: 1 torneira por pia × 3 pias.",
    "Estimativa: 1 dispenser por copa × 2 copas.",
]

_NAO_PEGA = [
    # a linha não se diz estimativa: pode ser leitura do desenho
    "Cuba de embutir, 1 por bancada, indicada na planta.",
    # fonte objetiva
    "Estimativa de consumo. Fonte: 4 INSERTs do bloco 'cuba': 1 por bancada.",
    "Estimada conforme quadro de louças: 1 por WC.",
    # outro local
    "Estimativa: 8 un por pavimento.",
    # sem número na frente
    "Estimativa por bancada, a definir.",
    # palavra que só começa igual
    "Estimativa: 2 un por copas-bar.x",
]


@pytest.mark.parametrize("obs", _PEGA)
def test_a_regra_de_bolso_e_reconhecida(obs):
    assert contagem_por_local("un", obs), obs


@pytest.mark.parametrize("obs", _NAO_PEGA[:-1])
def test_CONTROLE_o_que_nao_e_regra_de_bolso(obs):
    assert not contagem_por_local("un", obs), obs


@pytest.mark.parametrize("unidade", ["m²", "ml", "vb", "kg"])
def test_CONTROLE_so_peca_contada(unidade):
    assert not contagem_por_local(unidade, _PEGA[0])


@pytest.mark.parametrize("unidade", ["un", "UN", "pç", "ponto", "pontos", "cj"])
def test_toda_unidade_de_contagem(unidade):
    assert contagem_por_local(unidade, _PEGA[0])


def _it(q=6, obs=_PEGA[2], unit="un", origem="vision_pdf"):
    return BudgetItem(item_num="1", description="Tomada de bancada", unit=unit, quantity=q,
                      observations=obs, ref_sheet="a.pdf", confidence=Confidence("estimado"),
                      discipline="Elétrica", origem=origem)


def test_so_conta_nao_mexe_na_linha():
    it = _it()
    assert main._zera_contagem_por_densidade([it], regua=contagem_por_local, so_conta=True) == 1
    assert it.quantity == 6 and it.observations == _PEGA[2]


def test_ligada_deixa_em_branco_com_a_conta_escrita():
    it = _it()
    assert main._zera_contagem_por_densidade([it], regua=contagem_por_local) == 1
    assert it.quantity == 0 and "A conta da leitura dava 6" in it.observations
    assert it.observations.endswith(_PEGA[2])


@pytest.mark.parametrize("origem", ["dxf_geom", "revisao_cliente"])
def test_CONTROLE_cad_e_revisao_do_cliente_nao_entram(origem):
    assert main._zera_contagem_por_densidade([_it(origem=origem)], regua=contagem_por_local) == 0


def test_CONTROLE_sem_regua_segue_a_densidade():
    # "por bancada" não é da régua de 27/09
    it = _it()
    assert main._zera_contagem_por_densidade([it]) == 0 and it.quantity == 6


# ── o bloco do process_job, executado de verdade ──
_INICIO = "        # 🩸 30/10 — a irmã da irmã:"
_FIM = "motor:contagem-por-local\", f\"FALHOU: {_ecl}\", job_id,\n                       severity=\"warning\")\n"


def _bloco():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read().replace("\r\n", "\n")
    i = src.index(_INICIO)
    return src[i:src.index(_FIM, i) + len(_FIM)]


def _rodar(liga, monkeypatch):
    logs = []
    monkeypatch.setenv("CONTAGEM_POR_LOCAL_EM_BRANCO", "1" if liga else "0")
    it = _it()
    ns = {"all_items": [it], "job_id": "t1",
          "_zera_contagem_por_local": main._zera_contagem_por_local,
          "_log_error": lambda st, msg, job=None, severity="error": logs.append((st, msg))}
    exec(textwrap.dedent(_bloco()), ns)
    return it, logs


def test_com_a_chave_em_0_so_registra(monkeypatch):
    it, logs = _rodar(False, monkeypatch)
    assert it.quantity == 6
    assert logs == [("motor:contagem-por-local", "linhas=1 em_branco=0 liga=0")]


def test_com_a_chave_em_1_fica_em_branco(monkeypatch):
    it, logs = _rodar(True, monkeypatch)
    assert it.quantity == 0
    assert logs == [("motor:contagem-por-local", "linhas=1 em_branco=1 liga=1")]


def test_a_chave_e_avaliavel_e_o_log_e_diagnostico():
    assert "CONTAGEM_POR_LOCAL_EM_BRANCO" in main._CHAVES_AVALIAVEIS
    assert "motor:contagem-por-local" in main._STAGES_DIAGNOSTICO
