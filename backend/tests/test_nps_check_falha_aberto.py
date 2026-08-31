# -*- coding: utf-8 -*-
"""Quando nao da pra saber se a pessoa ja respondeu, PERGUNTA (31/08/2026).

O BURACO: `should_show_nps` tinha `except Exception: return {"should_show":
False}`. O dashboard chama essa rota antes de mostrar o widget e tem, no
codigo, o comentario "fail-safe: mostra se API falhar" — so que a API **nunca
falhava**: respondia HTTP 200 dizendo "nao mostre". Do lado do navegador isso e
indistinguivel de "essa pessoa ja respondeu", e nada era gravado no error_log.
Rede de seguranca morta, do jeito mais silencioso possivel.

Mesma familia do `/api/track` (29h de 500 calados) e do cron que dizia
`succeeded` com o erro no CORPO: HTTP 200 nao prova nada.

Com 5 respostas de NPS em toda a historia do produto, o erro caro e deixar de
perguntar. O cooldown de 60 dias continua valendo em todo caminho que CONSEGUE
ler a data — o que muda e so o caminho do "nao sei".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class _Req:
    headers = {}
    client = None


def _prep(monkeypatch, urlopen):
    logs = []
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda *a, **k: {"id": "u-1", "email": "c@ex.com"})
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job=None, severity="error":
                        logs.append((stage, severity)))
    monkeypatch.setattr(main.urllib.request, "urlopen", urlopen)
    return logs


class _Resp:
    def __init__(self, corpo):
        self._c = corpo.encode("utf-8")

    def read(self):
        return self._c

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_banco_fora_do_ar_PERGUNTA(monkeypatch):
    """Era aqui que morria: excecao virava 'nao mostre', calada."""
    def _explode(*a, **k):
        raise OSError("connection refused")
    logs = _prep(monkeypatch, _explode)
    r = main.should_show_nps("u-1", _Req())
    assert r["should_show"] is True, "falha do banco virou 'nao pergunte' de novo"
    assert r.get("indeterminado") is True
    assert logs and logs[0][0] == "nps:check-falhou", \
        "a falha tem que deixar rastro no error_log — antes era muda"


def test_data_ilegivel_PERGUNTA(monkeypatch):
    """2o caminho fechado: created_at que o parser nao entende."""
    logs = _prep(monkeypatch, lambda *a, **k: _Resp('[{"created_at": "ontem"}]'))
    r = main.should_show_nps("u-1", _Req())
    assert r["should_show"] is True
    assert logs and logs[0][0] == "nps:check-data-ilegivel"


def test_CONTROLE_quem_respondeu_ONTEM_nao_e_incomodado(monkeypatch):
    """O cooldown de 60 dias continua de pe — este teste e o que impede o
    conserto de virar 'pergunta sempre'."""
    from datetime import timedelta
    ontem = (main.datetime.utcnow() - timedelta(days=1)).isoformat() + "+00:00"
    _prep(monkeypatch, lambda *a, **k: _Resp('[{"created_at": "%s"}]' % ontem))
    r = main.should_show_nps("u-1", _Req())
    assert r["should_show"] is False, "cooldown de 60 dias foi perdido no conserto"


def test_CONTROLE_quem_respondeu_ha_muito_tempo_e_perguntado(monkeypatch):
    from datetime import timedelta
    velho = (main.datetime.utcnow() - timedelta(days=200)).isoformat() + "+00:00"
    _prep(monkeypatch, lambda *a, **k: _Resp('[{"created_at": "%s"}]' % velho))
    r = main.should_show_nps("u-1", _Req())
    assert r["should_show"] is True and r["days_since"] >= 60


def test_quem_nunca_respondeu_e_perguntado(monkeypatch):
    _prep(monkeypatch, lambda *a, **k: _Resp("[]"))
    r = main.should_show_nps("u-1", _Req())
    assert r["should_show"] is True and r["last_answered"] is None
