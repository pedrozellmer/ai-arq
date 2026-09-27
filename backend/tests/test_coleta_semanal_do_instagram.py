# -*- coding: utf-8 -*-
"""A coleta semanal dos números do Instagram tem porta própria pro pg_cron — e
a porta do admin continua fechada pra quem não é admin.

🩸 26/09/2026. A última coleta de alcance/salvamentos foi em 16/08: a única
porta era `/api/instagram/insights/sync`, atrás do login de admin, e a grade
dizia "adicionar ao pg_cron" — ninguém adicionou (o cron não tem login). O plano
de outubro ia ser feito sem um número de setembro.

Conserto: `/api/instagram/insights/tick`, com o MESMO portão dos outros ticks
(X-Tick-Secret), chamando a mesma rotina de coleta que o admin usa.
"""
import asyncio
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import instagram_webhook as iw  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _req(headers=None):
    return type("R", (), {"headers": dict(headers or {})})()


@pytest.fixture
def coleta(monkeypatch):
    """Troca a coleta de verdade (Graph API + banco) por um contador."""
    chamadas = []

    def falsa():
        chamadas.append(1)
        return {"ok": True, "synced": 3,
                "errors": [{"slot": "s%d" % i, "error": "x"} for i in range(14)]}

    monkeypatch.setattr(iw, "_sincronizar_insights", falsa)
    return chamadas


def test_tick_sem_o_segredo_e_recusado_e_nao_coleta(monkeypatch, coleta):
    monkeypatch.setenv("TICK_SECRET", "s3gredo")
    with pytest.raises(HTTPException) as e:
        iw.insights_tick(_req())
    assert e.value.status_code == 401
    assert coleta == [], "coletou sem o segredo — qualquer um gastaria a cota da Graph API"


def test_tick_com_segredo_errado_e_recusado(monkeypatch, coleta):
    monkeypatch.setenv("TICK_SECRET", "s3gredo")
    with pytest.raises(HTTPException) as e:
        iw.insights_tick(_req({"X-Tick-Secret": "chute"}))
    assert e.value.status_code == 401
    assert coleta == []


def test_tick_com_o_segredo_coleta_uma_vez_e_responde_curto(monkeypatch, coleta):
    monkeypatch.setenv("TICK_SECRET", "s3gredo")
    r = iw.insights_tick(_req({"X-Tick-Secret": "s3gredo"}))
    assert coleta == [1]
    assert r["ok"] is True and r["synced"] == 3
    assert r["n_errors"] == 14 and len(r["errors"]) == 10, (
        "o pg_net guarda o corpo de cada chamada — a resposta do cron é curta")
    assert "insights" not in r


def test_sync_do_admin_continua_exigindo_admin(monkeypatch, coleta):
    def barra(_request):
        raise HTTPException(403, "admin only")

    monkeypatch.setattr(iw, "_admin", barra)
    with pytest.raises(HTTPException) as e:
        asyncio.run(iw.insights_sync(_req(), force=True))
    assert e.value.status_code == 403
    assert coleta == [], "a refatoração abriu a porta do admin"


def test_sync_do_admin_coleta_e_devolve_a_lista(monkeypatch, coleta):
    monkeypatch.setattr(iw, "_admin", lambda _request: None)
    monkeypatch.setattr(iw, "_supa_select", lambda tabela, query: [{"media_id": "m1"}])
    r = asyncio.run(iw.insights_sync(_req(), force=True))
    assert coleta == [1]
    assert r["insights"] == [{"media_id": "m1"}], "o painel do admin perdeu a lista"
    assert len(r["errors"]) == 14, "o admin continua vendo TODOS os erros"
