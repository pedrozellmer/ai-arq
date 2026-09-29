# -*- coding: utf-8 -*-
"""O alerta "Novo projeto recebido" traz o nome do dono, mesmo sem nome no login.

🩸 29/09/2026: desde 25/09 o nome vem só do LOGIN; quem se cadastrou por e-mail
e senha não tem nome lá (mora em profiles.full_name) e o alerta saía
"Usuário: —".
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402


def _cena(monkeypatch, nome_no_perfil="Pessoa Exemplo"):
    enviados, gravados, perguntas = [], [], []
    monkeypatch.setattr(main, "_notify_admin", lambda assunto, corpo: enviados.append((assunto, corpo)))
    monkeypatch.setattr(main, "_projeto_patch", lambda job, patch: gravados.append((job, patch)))

    def _resolve(email="", user_id="", hint=""):
        perguntas.append((email, user_id))
        return nome_no_perfil
    monkeypatch.setattr(main, "_resolve_client_name", _resolve)
    return enviados, gravados, perguntas


def test_sem_nome_no_login_o_alerta_busca_no_perfil_e_grava(monkeypatch):
    enviados, gravados, perguntas = _cena(monkeypatch)
    main._alerta_de_projeto_novo("job00001", "", "cliente@exemplo.com", "u-1", "Projeto X", 1, "1 DWG")
    assert perguntas == [("cliente@exemplo.com", "u-1")]
    assert "Pessoa Exemplo" in enviados[0][1] and "—" not in enviados[0][1], enviados
    assert gravados == [("job00001", {"user_name": "Pessoa Exemplo"})]


def test_CONTROLE_com_nome_no_login_nao_pergunta_nem_grava(monkeypatch):
    enviados, gravados, perguntas = _cena(monkeypatch)
    main._alerta_de_projeto_novo("job00002", "Nome do Login", "c@exemplo.com", "u-2", "P", 2, "2 PDF")
    assert perguntas == [] and gravados == []
    assert "Nome do Login" in enviados[0][1]


def test_sem_nome_em_lugar_nenhum_sai_como_antes(monkeypatch):
    enviados, gravados, _p = _cena(monkeypatch, nome_no_perfil="")
    main._alerta_de_projeto_novo("job00003", "", "c@exemplo.com", "u-3", "P", 1, "1 PDF")
    assert "Usuário:</b> —" in enviados[0][1] and gravados == []


def test_a_busca_que_falha_nao_derruba_o_alerta(monkeypatch):
    enviados, gravados, _p = _cena(monkeypatch)

    def _explode(*a, **k):
        raise RuntimeError("banco fora")
    monkeypatch.setattr(main, "_resolve_client_name", _explode)
    main._alerta_de_projeto_novo("job00004", "", "c@exemplo.com", "u-4", "P", 1, "1 PDF")
    assert enviados and "—" in enviados[0][1]
