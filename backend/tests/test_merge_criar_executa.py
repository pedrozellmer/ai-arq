# -*- coding: utf-8 -*-
"""O merge, RODANDO: `admin_merge_criar` chamado de verdade.

Conversao de `test_merge_email_cliente.py::test_a_linha_do_merge_carrega_a_leitura_de_origem`,
que lia o fonte. Aqui as linhas conferidas sao as que o endpoint REALMENTE
mandou pro POST /project_items.
"""
import os
import sys
import types

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main as _m  # noqa: E402
from engine_rules import merge_plano as _merge_plano  # noqa: E402

_PAI_CRIADO_EM = "2026-08-20T19:37:00+00:00"      # -> 20/08 16h37 (Brasilia)
_FILHO_CRIADO_EM = "2026-08-24T22:31:00+00:00"    # -> 24/08 19h31


class _Req:
    def __init__(self):
        self.headers = {"Authorization": "Bearer jwt"}
        self.query_params = {}
        self.state = types.SimpleNamespace()


def _it(desc, prancha, n=1, conf="confirmado", q=1.0, unit="un", obs=""):
    return {"description": desc, "unit": unit, "quantity": q,
            "confidence": conf, "observations": obs, "ref_sheet": prancha,
            "discipline": "Eletrica", "section": "Instalacoes",
            "sort_order": n, "origem": "dxf_geom"}


@pytest.fixture
def criar(monkeypatch):
    """Roda `admin_merge_criar` DE VERDADE e devolve o que foi gravado."""
    gravado = {"projects": [], "itens": []}

    def _svc(method, path, body=None, params=None, prefer=None, timeout=15):
        if method == "POST" and path == "projects":
            gravado["projects"].append(dict(body or {}))
            return 201, None
        if method == "POST" and path == "project_items":
            gravado["itens"].extend(list(body or []))
            return 201, None
        return 200, []

    monkeypatch.setattr(_m, "_require_admin", lambda r: None)
    monkeypatch.setattr(_m, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(_m, "_supa_rows", lambda *a, **k: [])
    monkeypatch.setattr(_m, "_supa_rest_service", _svc)

    def _roda(itens_pai, itens_filho):
        pai = {"job_id": "aa11bb22", "user_id": "u-cliente-01",
               "user_email": "cliente-01@example.com", "user_name": "Cliente Um",
               "project_name": "Obra do cliente-01", "created_at": _PAI_CRIADO_EM,
               "typology": "office", "project_type": "arquitetura",
               "files_count": 2, "file_types": "dxf", "warnings": []}
        filho = {"job_id": "ev000001", "parent_job_id": "aa11bb22",
                 "is_eval": True, "status": "done", "user_id": "eval",
                 "created_at": _FILHO_CRIADO_EM, "warnings": []}
        plano = _merge_plano(itens_pai, itens_filho)
        monkeypatch.setattr(
            _m, "_merge_montar",
            lambda job, com_juiza=True: (pai, filho, itens_pai, itens_filho,
                                         plano, 0))
        r = _m.admin_merge_criar("ev000001", _Req())
        return {"resp": r, "itens": gravado["itens"],
                "projects": gravado["projects"]}

    return {"roda": _roda, "gravado": gravado}


_CARIMBO = "Veio da leitura de "

# A procedencia que o motor JA escreve em quase toda linha de producao. A
# fixture nascia com `observations` vazia — forma que praticamente nao ocorre no
# banco — entao o ramo `(_obs + " | " if _obs else "")` nunca era exercitado.
_OBS_DE_PRODUCAO = ("Contagem de blocos ELET-LUM na prancha; confira antes de "
                    "orcar.")


@pytest.mark.parametrize("obs_de_origem", ["", _OBS_DE_PRODUCAO])
def test_a_linha_do_merge_carrega_a_leitura_de_origem(criar, obs_de_origem):
    """Pedro, 24/08: "sempre coloca a fonte na planilha". Numa planilha
    COMBINADA a fonte tem uma camada a mais: de QUAL leitura a linha veio.

    🪤 06/09/2026 — O CENARIO ERA UM SO, E ERA O QUE NAO EXISTE. Com
    `observations` vazia em toda a fixture, o guarda so via o ramo do `else`:
    uma condicao que dependesse do texto ja gravado (ou que o SOBRESCREVESSE em
    vez de concatenar) derrubava o carimbo — ou a procedencia do motor — em 100%
    das linhas reais, com a bancada verde. Agora os DOIS ramos entram, e a
    afirmacao e sobre a ORDEM: a anotacao que ja existia fica, o carimbo entra
    DEPOIS dela, separados por " | ".
    """
    pai = [_it("Luminaria LM1", "4366-EL-E", n=1, obs=obs_de_origem),
           _it("Luminaria LM2", "4366-EL-E", n=2, obs=obs_de_origem)]
    filho = [_it("Tomada 2P+T", "3073-AQ-E", n=1, obs=obs_de_origem)]
    g = criar["roda"](pai, filho)

    obs = [str(l.get("observations") or "") for l in g["itens"]]
    assert len(g["itens"]) == 3, "nao gravou as 3 linhas: %d" % len(g["itens"])
    assert all(_CARIMBO in o for o in obs), (
        "linha combinada gravada SEM o carimbo de procedencia: %s" % obs)
    do_pai = [l for l in g["itens"] if l["ref_sheet"] == "4366-EL-E"]
    do_filho = [l for l in g["itens"] if l["ref_sheet"] == "3073-AQ-E"]
    for linha, data in ((do_pai[0], "20/08 16h37"), (do_filho[0], "24/08 19h31")):
        o = str(linha["observations"])
        assert o.endswith(_CARIMBO + data), (
            "o carimbo da leitura de origem nao fecha a observacao: %r" % o)
        if obs_de_origem:
            # 🔒 o que o motor ja tinha escrito NAO pode ser apagado (regra n7)
            assert obs_de_origem in o, (
                "o carimbo comeu a procedencia que o motor tinha escrito: %r" % o)
            assert (obs_de_origem + " | " + _CARIMBO + data) in o, (
                "carimbo e procedencia deixaram de ficar na ordem certa, ou o "
                "separador ' | ' sumiu: %r" % o)
        else:
            assert o == _CARIMBO + data, (
                "linha sem anotacao anterior saiu com separador orfao ou lixo "
                "grudado: %r" % o)
