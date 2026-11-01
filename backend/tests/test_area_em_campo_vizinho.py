# -*- coding: utf-8 -*-
"""A área construída que a IA leu com outro nome de campo não pode se perder.

🩸 31/10/2026 (jobs a33ec785 e 3cc39837): o prompt não diz o nome do campo.
A leitura trazia `area_total_construida: 447.61`, o motor só olhava `total_area`
e o cliente lia "não encontramos a área", com as linhas em m² vazias.

🔑 AREA_EM_CAMPO_VIZINHO=1 aproveita a leitura; com 0 só conta. O risco é pegar
terreno ou a nossa própria medição como se fosse área construída.
"""
import ast
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engine_rules  # noqa: E402
import main  # noqa: E402
from engine_rules import area_em_campo_vizinho  # noqa: E402


@pytest.mark.parametrize("campo", engine_rules._AREA_CONSTRUIDA_EM_OUTRO_NOME)
def test_cada_nome_da_lista_e_resgatado(campo):
    assert area_em_campo_vizinho({campo: 152.04}) == (campo, 152.04)


@pytest.mark.parametrize("campo", [
    "area_terreno", "total_area_terreno", "total_area_terrain", "lot_area",
    "total_land_area", "area_livre", "total_area_free", "area_projecao_ortogonal",
    "area_total_cobertura", "total_coverage_area", "area_solo_permeavel",
    "total_area_measured", "area_total_medida", "area", "area_m2"])
def test_outra_area_nao_vira_area_construida(campo):
    assert area_em_campo_vizinho({campo: 900}) is None


def test_total_area_preenchido_manda():
    assert area_em_campo_vizinho({"total_area": 100, "area_construida": 90}) is None


@pytest.mark.parametrize("valor", [None, 0, "", "sem cota"])
def test_valor_vazio_ou_sem_numero_nao_vale(valor):
    assert area_em_campo_vizinho({"area_construida": valor}) is None


def test_um_valor_ruim_nao_esconde_o_seguinte():
    assert area_em_campo_vizinho({"area_total_construida": "sem cota",
                                  "built_area": 80}) == ("built_area", 80.0)


def test_pd_que_nao_e_dicionario_nao_quebra():
    assert area_em_campo_vizinho(["x"]) is None


def _colhe(monkeypatch, valor_da_chave, pd):
    logs, regs, leituras = [], [], {"total_area": []}
    monkeypatch.setattr(main, "_chave_do_job", lambda j, n, p="0": valor_da_chave)
    monkeypatch.setattr(main, "_log_error",
                        lambda st, msg, j=None, severity="error": logs.append((st, msg, severity)))
    main._colhe_area_em_campo_vizinho("job-1", pd, leituras,
                                      lambda o, c: regs.append((o, c)), "ia-pdf", float)
    return leituras, regs, logs


def test_com_a_chave_em_0_so_registra(monkeypatch):
    leituras, regs, logs = _colhe(monkeypatch, "0", {"area_construida": 447.61})
    assert leituras == {"total_area": []} and regs == []
    assert logs == [("motor:area-em-campo-vizinho",
                     "campo=area_construida valor=447.61 liga=0", "info")]


def test_com_a_chave_em_1_entra_como_leitura(monkeypatch):
    leituras, regs, logs = _colhe(monkeypatch, "1", {"area_construida": 447.61})
    assert leituras == {"total_area": [447.61]}
    assert regs == [("ia-pdf", "total_area")]
    assert logs[0][1].endswith("liga=1")


def test_sem_campo_vizinho_nao_registra_nada(monkeypatch):
    leituras, regs, logs = _colhe(monkeypatch, "1", {"name": "x"})
    assert leituras == {"total_area": []} and regs == [] and logs == []


def test_falha_nao_derruba_a_leitura(monkeypatch):
    logs = []
    monkeypatch.setattr(main, "_log_error",
                        lambda st, msg, j=None, severity="error": logs.append(msg))
    def _quebra(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(main, "_chave_do_job", _quebra)
    main._colhe_area_em_campo_vizinho("j", {"built_area": 9}, {}, None, "ia-pdf", float)
    assert logs == ["FALHOU: boom"]


def test_a_chave_nasce_em_0_e_e_avaliavel():
    assert "AREA_EM_CAMPO_VIZINHO" in main._CHAVES_AVALIAVEIS
    assert "motor:area-em-campo-vizinho" in main._STAGES_DIAGNOSTICO
    assert main._chave_do_job("job-sem-avaliacao", "AREA_EM_CAMPO_VIZINHO") == "0"


@pytest.mark.parametrize("origem", ["ia-pdf", "ia-dxf"])
def test_os_dois_lacos_chamam_a_colheita(origem):
    with open(os.path.join(os.path.dirname(__file__), "..", "main.py"), encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    achou = [n for n in ast.walk(arvore) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_colhe_area_em_campo_vizinho"
             and any(isinstance(a, ast.Constant) and a.value == origem for a in n.args)]
    assert len(achou) == 1, "o laço %s não colhe a área de campo vizinho" % origem
