# -*- coding: utf-8 -*-
"""O /api/health não vaza inteligência de negócio/infra pra anônimo (30/08).

🔒 A auditoria do site achou que a rota expunha a QUALQUER UM: nº de usuários e
projetos, RAM/disco/CPU do container, o modelo de IA em uso, a temperatura e se
as chaves estão configuradas. Agora o payload sensível exige login de admin; o
público fica só com o mínimo que a sonda de vida e a trava de deploy precisam.
"""
import asyncio
import inspect
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


class _FakeReq:
    def __init__(self):
        self.headers = {}
        self.client = None


def _chamar(fn, *a):
    r = fn(*a)
    return asyncio.run(r) if inspect.isawaitable(r) else r


_SENSIVEL = ("stats", "system", "memoria_container",
             "api_key_configured", "stripe_configured")


def test_anonimo_NAO_ve_stats_nem_infra(monkeypatch):
    monkeypatch.setattr(main, "_get_user_from_request", lambda *a, **k: None)
    r = _chamar(main.health, _FakeReq())
    for campo in _SENSIVEL:
        assert campo not in r, f"VAZOU pra anônimo: {campo}"
    # o modelo de IA e a temperatura não podem sair no features público
    assert "dxf_extract_model" not in r.get("features", {})
    assert "dxf_temperature" not in r.get("features", {})
    assert "libredwg_ligado" not in r.get("features", {})


def test_anonimo_AINDA_ve_o_que_a_trava_de_deploy_precisa(monkeypatch):
    """guard_deploy.py lê jobs_em_curso/uploads_em_curso sem credencial —
    não pode ter quebrado."""
    monkeypatch.setattr(main, "_get_user_from_request", lambda *a, **k: None)
    r = _chamar(main.health, _FakeReq())
    assert r["status"] == "healthy"
    assert "jobs_em_curso" in r and "uploads_em_curso" in r
    assert r["features"]["pdf"] is True and r["features"]["dxf"] is True


def test_CONTROLE_admin_VE_tudo(monkeypatch):
    """🧪 Se o admin também não visse, o guarda de cima passaria por uma rota
    que simplesmente removeu os campos de todo mundo — inútil."""
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda *a, **k: {"id": "x", "email": main.ADMIN_EMAIL})
    r = _chamar(main.health, _FakeReq())
    assert "stats" in r and "system" in r
    assert "dxf_extract_model" in r["features"]


def test_CONTROLE_email_qualquer_NAO_e_admin(monkeypatch):
    """🧪 Só o ADMIN_EMAIL destrava — um usuário logado comum continua no
    payload público."""
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda *a, **k: {"id": "y", "email": "cliente@qualquer.com"})
    r = _chamar(main.health, _FakeReq())
    assert "stats" not in r and "system" not in r
