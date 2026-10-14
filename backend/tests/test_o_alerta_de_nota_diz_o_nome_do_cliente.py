# -*- coding: utf-8 -*-
"""O alerta de nota diz o NOME do cliente, mesmo quando a página não manda.

🩸 13/10/2026: dois alertas no mesmo dia chegaram ao Pedro com "Cliente: ?" —
a carinha da página do projeto grava `user_name` vazio, e os dois perfis
tinham nome. O alerta busca o nome no cadastro (`_resolve_client_name`),
dentro da thread, pra não segurar a resposta da nota.
"""
import os
import sys
import threading

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402


class _ThreadNaHora(object):
    def __init__(self, target=None, daemon=None, **k):
        self._t = target

    def start(self):
        self._t()


def _alerta(monkeypatch, row, nome_no_cadastro="Fulano de Tal"):
    enviados, pedidos = [], []

    def _resolve(email="", user_id="", hint=""):
        pedidos.append((email, user_id))
        return nome_no_cadastro

    monkeypatch.setattr(threading, "Thread", _ThreadNaHora)
    monkeypatch.setattr(main, "_resolve_client_name", _resolve)
    monkeypatch.setattr(main, "_notify_admin", lambda assunto, html: enviados.append(html) or True)
    monkeypatch.setattr(main, "_supa_rows", lambda *a, **k: [])
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._alerta_nps(row, "detractor")
    assert len(enviados) == 1, enviados
    return enviados[0], pedidos


_ROW = {"user_id": "u-1", "user_email": "cliente@exemplo.com", "user_name": "",
        "score": 2, "comment": "", "context": "after_project", "job_id": ""}


def test_o_caso_nome_vazio_na_linha_vem_do_cadastro(monkeypatch):
    html, pedidos = _alerta(monkeypatch, dict(_ROW))
    assert "<b>Cliente:</b> Fulano de Tal (cliente@exemplo.com)" in html, html
    assert pedidos == [("cliente@exemplo.com", "u-1")]


def test_CONTROLE_nome_na_linha_nao_busca(monkeypatch):
    html, pedidos = _alerta(monkeypatch, dict(_ROW, user_name="Beltrana"))
    assert "<b>Cliente:</b> Beltrana (" in html and pedidos == [], (html, pedidos)


def test_CONTROLE_sem_nome_em_lugar_nenhum_continua_interrogacao(monkeypatch):
    html, _p = _alerta(monkeypatch, dict(_ROW), nome_no_cadastro="")
    assert "<b>Cliente:</b> ? (cliente@exemplo.com)" in html, html


def test_a_busca_que_falha_nao_derruba_o_alerta(monkeypatch):
    def _quebra(*a, **k):
        raise RuntimeError("cadastro fora do ar (dublê)")
    enviados = []
    monkeypatch.setattr(threading, "Thread", _ThreadNaHora)
    monkeypatch.setattr(main, "_resolve_client_name", _quebra)
    monkeypatch.setattr(main, "_notify_admin", lambda assunto, html: enviados.append(html) or True)
    monkeypatch.setattr(main, "_supa_rows", lambda *a, **k: [])
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._alerta_nps(dict(_ROW), "detractor")
    assert len(enviados) == 1 and "<b>Cliente:</b> ? (" in enviados[0], enviados
