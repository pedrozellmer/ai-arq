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


def test_a_linha_do_merge_carrega_a_leitura_de_origem(criar):
    """Pedro, 24/08: "sempre coloca a fonte na planilha". Numa planilha
    COMBINADA a fonte tem uma camada a mais: de QUAL leitura a linha veio."""
    pai = [_it("Luminaria LM1", "4366-EL-E", n=1),
           _it("Luminaria LM2", "4366-EL-E", n=2)]
    filho = [_it("Tomada 2P+T", "3073-AQ-E", n=1)]
    g = criar["roda"](pai, filho)

    obs = [str(l.get("observations") or "") for l in g["itens"]]
    assert len(g["itens"]) == 3, "nao gravou as 3 linhas: %d" % len(g["itens"])
    assert all("Veio da leitura de " in o for o in obs), (
        "linha combinada gravada SEM o carimbo de procedencia: %s" % obs)
    do_pai = [l for l in g["itens"] if l["ref_sheet"] == "4366-EL-E"]
    do_filho = [l for l in g["itens"] if l["ref_sheet"] == "3073-AQ-E"]
    assert "20/08 16h37" in do_pai[0]["observations"], do_pai[0]["observations"]
    assert "24/08 19h31" in do_filho[0]["observations"], do_filho[0]["observations"]
