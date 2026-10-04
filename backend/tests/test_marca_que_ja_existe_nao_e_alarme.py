# -*- coding: utf-8 -*-
"""Marca que já existe não dispara o alarme de "gravação falhou".

🩸 04/10/2026 — o alarme `supabase:gravacao-falhou` (item 7 da telemetria, 27/09) apitou 6 vezes em 6 dias e todas
eram MARCA que já existia: 5× a trava `fim_de_job` da raiz regravada pelo `_email_auto_registrar` depois do e-mail de
complemento/reprocesso, 1× o descadastro da newsletter clicado duas vezes. Nenhum e-mail saiu repetido. Pedro: "pode
consertar o alarme".

🔑 Em `email_auto_log` e `newsletter_optout`, 409 com 23505 = o estado pedido já está no banco: não conta. O retorno
continua False (a linha não foi inserida agora). Qualquer outra tabela, outro código ou outro erro segue contando.
Os testes rodam o `_supabase_insert` de verdade, com a rede encenada.
"""
import io
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


@pytest.fixture
def log(tmp_path, monkeypatch):
    p = tmp_path / "supa.txt"
    monkeypatch.setattr(main, "_SUPA_LOG_PATH", str(p))
    monkeypatch.setattr(main, "_FALHAS_DE_GRAVACAO", {})
    return p


def _rede(monkeypatch, codigo, corpo):
    """Todo POST responde `codigo` com `corpo`; devolve as tabelas pedidas (o alarme é um POST no error_log)."""
    pedidas = []

    def _abre(req, timeout=None):
        pedidas.append(req.full_url.split("/rest/v1/")[-1].split("?")[0])
        raise urllib.error.HTTPError(req.full_url, codigo, "erro", {}, io.BytesIO(corpo))
    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", _abre)
    return pedidas


_DUPLICADA = (b'{"code":"23505","details":"Key (email, kind, ref)=(cliente@exemplo.com, fim_de_job, abc12345) '
              b'already exists.","hint":null,"message":"duplicate key value violates unique constraint"}')
_FK = b'{"code":"23503","details":"Key is not present in table","message":"violates foreign key constraint"}'


def test_a_trava_de_email_regravada_nao_dispara_o_alarme(log, monkeypatch):
    pedidas = _rede(monkeypatch, 409, _DUPLICADA)
    main._email_auto_registrar("cliente@exemplo.com", "fim_de_job", ref="abc12345")    # o caminho de verdade
    assert pedidas == ["email_auto_log"], "foi pro error_log: %r" % pedidas
    assert main._FALHAS_DE_GRAVACAO == {}
    txt = log.read_text(encoding="utf-8")
    assert "INSERT email_auto_log já existia (409/23505)" in txt and "@" not in txt, txt


def test_descadastro_clicado_duas_vezes_nao_dispara_o_alarme(log, monkeypatch):
    pedidas = _rede(monkeypatch, 409, _DUPLICADA)
    assert main._supabase_insert("newsletter_optout", {"email": "cliente@exemplo.com", "source": "link"}) is False
    assert pedidas == ["newsletter_optout"] and main._FALHAS_DE_GRAVACAO == {}


def test_a_rota_de_descadastro_segue_dizendo_pronto(log, monkeypatch):
    from fastapi.testclient import TestClient
    _rede(monkeypatch, 409, _DUPLICADA)
    email = "cliente@exemplo.com"
    r = TestClient(main.app).get("/api/newsletter/unsub", params={"e": email, "t": main._newsletter_token(email)})
    assert r.status_code == 200 and "saiu da lista" in r.text
    assert main._FALHAS_DE_GRAVACAO == {}


def test_a_marca_repetida_devolve_False_pra_quem_usar_insert_como_trava(log, monkeypatch):
    """"Já existia" não é "consegui agora": quem um dia travar envio num insert não pode ouvir True."""
    _rede(monkeypatch, 409, _DUPLICADA)
    assert main._supabase_insert("email_auto_log", {"email": "x@exemplo.com", "kind": "k", "ref": "r"}) is False


# ─── controles: o alarme continua vivo pra tudo que não é marca repetida ─────────────────────────
def test_CONTROLE_duplicada_em_outra_tabela_ainda_dispara(log, monkeypatch):
    pedidas = _rede(monkeypatch, 409, _DUPLICADA)
    assert main._supabase_insert("email_sent_log", {"kind": "boas_vindas", "email": "x@exemplo.com"}) is False
    assert main._FALHAS_DE_GRAVACAO["email_sent_log"]["n"] == 1
    assert pedidas == ["email_sent_log", "error_log"], pedidas


def test_CONTROLE_409_de_outro_codigo_na_tabela_de_marca_ainda_dispara(log, monkeypatch):
    pedidas = _rede(monkeypatch, 409, _FK)
    main._email_auto_registrar("cliente@exemplo.com", "fim_de_job", ref="abc12345")
    assert main._FALHAS_DE_GRAVACAO["email_auto_log"]["n"] == 1 and pedidas[-1] == "error_log"


def test_CONTROLE_so_o_409_conta_como_ja_existia(log, monkeypatch):
    """🪤 Sabotagem de 04/10: trocar `== 409` por `>= 400` passou verde — nenhum controle tinha OUTRO status com
    o 23505 no corpo. Um 400/500 que ecoa o código não é "a linha já está lá"."""
    pedidas = _rede(monkeypatch, 400, _DUPLICADA)
    main._email_auto_registrar("cliente@exemplo.com", "fim_de_job", ref="abc12345")
    assert main._FALHAS_DE_GRAVACAO["email_auto_log"]["n"] == 1 and pedidas[-1] == "error_log"


def test_CONTROLE_banco_fora_do_ar_na_tabela_de_marca_ainda_dispara(log, monkeypatch):
    pedidas = _rede(monkeypatch, 500, b'{"message":"internal"}')
    main._email_auto_registrar("cliente@exemplo.com", "fim_de_job", ref="abc12345")
    assert main._FALHAS_DE_GRAVACAO["email_auto_log"]["n"] == 1 and pedidas[-1] == "error_log"
