# -*- coding: utf-8 -*-
"""Quem entrou por CONVITE do Escritório não leva a esteira de e-mail de cliente.

24/09/2026 — achado nº12 do parecer jurídico: a pessoa que veio trabalhar no
projeto de outra (a equipe convidada) cairia no "boas-vindas" e no "suba a sua
1ª prancha", que falam do quantitativo — outro produto pra ela. O Pedro pediu no
lugar um e-mail próprio: "além de convidado de um projeto, você tem a sua área".

O que estes guardas provam, rodando a varredura DE VERDADE (dry=1) com o banco falso:
  • convidado com 3+ dias de aceite e sem projeto próprio → `convidado_area_propria`;
    nunca `boas_vindas` nem `nudge_onboarding`;
  • convidado com 1 dia de aceite → nada ainda;
  • quem é admin de um projeto próprio no Escritório NÃO é tratado como convidado;
  • 🪤 não conseguir ler quem é convidado ≠ "ninguém é convidado": as regras de
    cliente-novo esperam o próximo tick (na dúvida, não envia).
🧪 Controle positivo: o cliente comum, no mesmo tick, CONTINUA levando o boas-vindas.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

AGORA = datetime.now(timezone.utc)
ha = lambda **k: (AGORA - timedelta(**k)).isoformat()  # noqa: E731


def _user(uid, email, dias):
    return {"id": uid, "email": email, "created_at": ha(days=dias),
            "email_confirmed_at": ha(days=dias), "user_metadata": {"full_name": "Pessoa Exemplo"}}


@pytest.fixture
def varredura(monkeypatch):
    estado = {"users": [], "membros": [], "falha_membros": False}

    def tudo(path, params=None, **k):
        if path == "profiles":
            return 200, [{"user_id": u["id"], "email": u["email"]} for u in estado["users"]]
        if path == "email_sent_log":
            return 200, []
        if path == "projects":
            return 200, []
        if path == "escritorio_membros":
            return (500, None) if estado["falha_membros"] else (200, estado["membros"])
        if path == "escritorio_projetos":
            return 200, [{"id": "proj-1", "nome": "Projeto Exemplo"}, {"id": "proj-2", "nome": "Outro"}]
        raise AssertionError("tabela inesperada: " + path)

    monkeypatch.setattr(main, "_require_tick_secret", lambda *a, **k: None)
    monkeypatch.setattr(main, "_auth_admin_list_users", lambda *a, **k: estado["users"])
    monkeypatch.setattr(main, "_supa_rest_tudo", tudo)
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (200, []))
    monkeypatch.setattr(main, "_email_auto_ja_enviado", lambda *a, **k: False)
    monkeypatch.setattr(main, "_email_auto_recente", lambda *a, **k: False)
    monkeypatch.setattr(main, "_alertas_de_cadastro_ao_pedro", lambda *a, **k: {"status": "teste"})
    monkeypatch.setattr(main, "_email_eh_interno", lambda e: False)

    def rodar():
        r = main.emails_auto_tick(request=None, dry=1)
        assert r.get("status") == "dry", r
        return r["por_tipo"]
    estado["rodar"] = rodar
    return estado


def _membro(uid, papel, projeto, aceito_dias):
    return {"user_id": uid, "papel": papel, "status": "ativo", "aceito_em": ha(days=aceito_dias),
            "nome": "Admin Exemplo" if papel == "dono" else None, "projeto_id": projeto}


def test_convidado_leva_o_email_proprio_e_nao_a_esteira_de_cliente(varredura):
    varredura["users"] = [_user("u-conv", "equipe@exemplo.com", 4), _user("u-adm", "admin@exemplo.com", 60)]
    varredura["membros"] = [_membro("u-adm", "dono", "proj-1", 60), _membro("u-conv", "freela", "proj-1", 4)]
    tipos = varredura["rodar"]()
    assert tipos.get("convidado_area_propria") == 1, tipos
    assert "boas_vindas" not in tipos and "nudge_onboarding" not in tipos, tipos


def test_controle_cliente_comum_continua_levando_o_boas_vindas(varredura):
    varredura["users"] = [_user("u-cli", "cliente@exemplo.com", 2), _user("u-conv", "equipe@exemplo.com", 4)]
    varredura["membros"] = [_membro("u-conv", "freela", "proj-1", 4)]
    tipos = varredura["rodar"]()
    assert tipos.get("boas_vindas") == 1 and tipos.get("convidado_area_propria") == 1, tipos


def test_convidado_recente_ainda_nao_recebe_nada(varredura):
    varredura["users"] = [_user("u-conv", "equipe@exemplo.com", 1)]
    varredura["membros"] = [_membro("u-conv", "freela", "proj-1", 1)]
    assert varredura["rodar"]() == {}


def test_quem_tem_projeto_proprio_no_escritorio_nao_e_convidado(varredura):
    varredura["users"] = [_user("u-x", "pessoa@exemplo.com", 4)]
    varredura["membros"] = [_membro("u-x", "freela", "proj-1", 4), _membro("u-x", "dono", "proj-2", 4)]
    tipos = varredura["rodar"]()
    assert "convidado_area_propria" not in tipos and tipos.get("boas_vindas") == 1, tipos


def test_sem_saber_quem_e_convidado_as_regras_de_cliente_novo_esperam(varredura):
    varredura["users"] = [_user("u-cli", "cliente@exemplo.com", 2), _user("u-conv", "equipe@exemplo.com", 4)]
    varredura["falha_membros"] = True
    tipos = varredura["rodar"]()
    assert "boas_vindas" not in tipos and "nudge_onboarding" not in tipos and "convidado_area_propria" not in tipos, tipos


def test_o_email_proprio_segue_o_padrao_da_casa():
    assunto, html = main._build_convidado_area_propria_email("Pessoa", "Projeto Exemplo", "Admin Exemplo")
    assert len(assunto) <= 52
    assert "convidado-area.png" in html and "Abrir minha área" in html
    assert os.path.exists(os.path.join(os.path.dirname(_BACKEND), "assets", "email", "convidado-area.png"))
    # o convite e o e-mail novo têm ficha na Central de E-mails
    chaves = {c["key"] for c in main._EMAIL_CATALOG}
    assert {"escritorio_convite", "convidado_area_propria"} <= chaves


def test_a_porta_do_primeiro_acesso_tambem_pula_o_convidado():
    import inspect
    fonte = inspect.getsource(main.notify_welcome)
    assert "_convidados_do_escritorio()" in fonte and "convidado_do_escritorio" in fonte
