# -*- coding: utf-8 -*-
"""Em que posição da lista de candidatos estava o código SINAPI escolhido.

💸 20/11/2026 — a escolha do SINAPI é ~1/3 do gasto da API e o cache não ajuda
(~99% do pedido são os candidatos). Mandar MENOS candidatos só é seguro se o
escolhido mora no topo da lista. Isto só MEDE: nada muda na planilha.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import sinapi_matcher as sm  # noqa: E402


def _item(n):
    return {"description": "X", "unit": "un",
            "candidates": [{"codigo": "C%d" % k} for k in range(1, n + 1)]}


def test_faixas_da_posicao():
    items = [_item(60) for _ in range(7)]
    escolhas = {0: "C1", 1: "C5", 2: "C6", 3: "C20", 4: "C31", 5: "C60", 6: None}
    p = sm.posicoes_do_escolhido(items, escolhas)
    assert p["1-5"] == 2 and p["6-10"] == 1 and p["11-20"] == 1
    assert p["21-30"] == 0 and p["31-45"] == 1 and p["46+"] == 1
    assert p["nenhum"] == 1
    assert p["n_cands"] == "60-60"


def test_codigo_fora_da_lista_nao_conta_em_faixa():
    p = sm.posicoes_do_escolhido([_item(10)], {0: "INVENTADO"})
    assert sum(v for k, v in p.items() if k not in ("nenhum", "n_cands")) == 0


def test_indice_ruim_nao_derruba():
    p = sm.posicoes_do_escolhido([_item(3)], {0: "C2", 9: "C1"})
    assert p["1-5"] == 1


def test_mede_antes_de_reordenar(monkeypatch):
    """apply_llm_pick põe o escolhido em 1º — a medida tem que ver a ordem ANTES."""
    items = [_item(30)]
    monkeypatch.setattr(sm, "pick_best_batch", lambda its, job_id=None: {0: "C25"})
    visto = {}
    monkeypatch.setattr(sm, "_registrar_posicoes",
                        lambda its, esc, job_id: visto.update(sm.posicoes_do_escolhido(its, esc)))
    assert sm.apply_llm_pick(items) == 1
    assert visto["21-30"] == 1, visto
    assert items[0]["candidates"][0]["codigo"] == "C25"   # a planilha segue igual


def test_o_log_falhar_nao_derruba_a_planilha(monkeypatch):
    items = [_item(5)]
    monkeypatch.setattr(sm, "pick_best_batch", lambda its, job_id=None: {0: "C2"})
    monkeypatch.setattr(sm, "posicoes_do_escolhido",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert sm.apply_llm_pick(items) == 1


def test_o_estagio_esta_na_lista_do_diagnostico():
    import main
    assert "motor:sinapi-posicao" in main._STAGES_DIAGNOSTICO
