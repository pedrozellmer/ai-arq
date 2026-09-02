# -*- coding: utf-8 -*-
"""Quando o ADMIN reprocessa o projeto de um CLIENTE, fica rastro no banco.

🩸 02/09/2026. 23 projetos com reprocess_count = 1 e nenhuma forma de saber se
algum foi gasto pelo Pedro "de visita" (`projeto.html?adm=1`): a rota
/reprocess só confere que quem chamou é dono OU admin, e não escreve quem foi.
A tela ganhou uma segunda confirmação pra esse caso; isto aqui é o rastro no
servidor (error_log, stage `admin:reprocessou-projeto-de-cliente`).

🪤 O guarda CHAMA a rota de verdade (`reprocess_project`) com as dependências
trocadas: o dono é um cliente, quem chama é o admin, e o freio de ritmo diz
"não" — assim a execução para no 429 logo DEPOIS do rastro, sem tocar Storage
nem banco. Se o rastro vier antes do 429 e com o job certo, passou.
"""
import asyncio
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class _Req:
    headers = {}


def _roda(monkeypatch, quem, dono="uid-do-cliente", job="abc12345"):
    registros = []
    monkeypatch.setattr(main, "_require_project_owner", lambda req, jid: dono)
    monkeypatch.setattr(main, "_get_user_from_request", lambda req, tolerante=False: quem)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, message, job_id=None, severity="error":
                        registros.append((stage, job_id, severity)))
    # Freio de ritmo "fechado": a rota levanta 429 logo depois do ponto do rastro.
    monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: False)
    with pytest.raises(HTTPException) as ex:
        asyncio.run(main.reprocess_project(job, _Req()))
    assert ex.value.status_code == 429, "não chegou no freio — a rota parou antes do ponto do rastro?"
    return [r for r in registros if r[0] == "admin:reprocessou-projeto-de-cliente"]


def test_admin_no_projeto_do_cliente_deixa_rastro(monkeypatch):
    achados = _roda(monkeypatch, {"id": "uid-admin", "email": main.ADMIN_EMAIL.upper()})
    assert achados == [("admin:reprocessou-projeto-de-cliente", "abc12345", "warning")], achados


def test_CONTROLE_o_proprio_cliente_nao_deixa_rastro_de_admin(monkeypatch):
    assert _roda(monkeypatch, {"id": "uid-do-cliente", "email": "cliente@x.com"}) == []


def test_CONTROLE_admin_no_proprio_projeto_nao_deixa_rastro(monkeypatch):
    assert _roda(monkeypatch, {"id": "uid-admin", "email": main.ADMIN_EMAIL}, dono="uid-admin") == []


def test_CONTROLE_falha_na_sessao_nao_derruba_o_reprocesso(monkeypatch):
    """`_get_user_from_request(tolerante=True)` devolve None em falha de rede — o
    rastro é best-effort e o reprocesso segue (aqui: até o 429 do freio)."""
    assert _roda(monkeypatch, None) == []
