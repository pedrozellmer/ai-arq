# -*- coding: utf-8 -*-
"""O log de gravação não guarda dado pessoal, e a falha de gravação deixa rastro.

🔒🩸 27/09/2026 — auditoria de telemetria, item 7.
  · `_supa_log` guardava 200 caracteres de CADA insert que deu certo — o e-mail
    de usage_events, email_auto_log e email_sent_log — num arquivo servido por
    /api/debug/supa-log (só admin, mas sem prazo além do boot).
  · `_supabase_insert` não levanta: devolve False, e seis chamadores ignoram o
    retorno. A falha morria no print e nesse arquivo, que zera a cada boot.
  · Não havia alarme de "a telemetria parou".

🔑 Gravação que deu certo registra só os CAMPOS; e-mail que sobrar em qualquer
linha sai mascarado. Falha conta por tabela; a 1ª de cada hora vira linha no
error_log (a do próprio error_log só conta). O tick diário avisa quando ontem
teve projeto de cliente e zero evento.
"""
import io
import os
import sys
import urllib.error
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


@pytest.fixture
def log(tmp_path, monkeypatch):
    p = tmp_path / "supa.txt"
    monkeypatch.setattr(main, "_SUPA_LOG_PATH", str(p))
    monkeypatch.setattr(main, "_FALHAS_DE_GRAVACAO", {})
    return p


def _ler(p):
    return io.open(str(p), encoding="utf-8").read() if p.exists() else ""


class _Ok(object):
    def read(self, *a):
        return b""


def _insert(monkeypatch, comportamento):
    """Roda o `_supabase_insert` de verdade com a rede encenada; devolve as URLs pedidas."""
    pedidas = []

    def _abre(req, timeout=None):
        pedidas.append(req.full_url)
        return comportamento(req)
    import urllib.request as _ur   # o `_supabase_insert` importa por dentro e chama `urllib.request.urlopen`
    monkeypatch.setattr(_ur, "urlopen", _abre)
    return pedidas


def _http_500(req):
    raise urllib.error.HTTPError(req.full_url, 500, "erro", {}, io.BytesIO(
        b'{"message":"duplicate key (email)=(cliente@exemplo.com)"}'))


# ══════════════════════════════════════════════════════════════════════════
#  1. Sem dado pessoal no arquivo
# ══════════════════════════════════════════════════════════════════════════
def test_insert_que_deu_certo_guarda_so_os_campos(log, monkeypatch):
    _insert(monkeypatch, lambda req: _Ok())
    assert main._supabase_insert("email_sent_log", {"kind": "boas_vindas", "user_name": "Fulana Tal",
                                                     "email": "cliente@exemplo.com"}) is True
    txt = _ler(log)
    assert "INSERT email_sent_log OK" in txt and "user_name" in txt, txt
    # 🪤 o NOME é o que prova: a máscara de e-mail esconderia o e-mail mesmo com
    # o conteúdo de volta no arquivo — nome ela não pega
    assert "Fulana" not in txt and "@" not in txt, "o conteúdo do insert voltou pro arquivo: %r" % txt


def test_CONTROLE_do_jeito_de_antes_o_email_ia_pro_arquivo(log):
    """O formato de antes (`data=json.dumps(data)[:200]`) — com a máscara central
    o e-mail ainda sairia, mas o NOME também; e sem a máscara, o e-mail."""
    main._supa_log('INSERT usage_events OK  data={"user_email": "cliente@exemplo.com"}')
    txt = _ler(log)
    assert "cliente@exemplo.com" not in txt and "<e-mail>" in txt, txt


def test_a_mascara_pega_apelido_e_dominio_composto(log):
    main._supa_log("x zarela+smoke@gmail.com y a.b@c-d.com.br z")
    txt = _ler(log)
    assert "@" not in txt and txt.count("<e-mail>") == 2, txt


def test_a_falha_nao_leva_o_email_nem_no_corpo_de_erro_do_banco(log, monkeypatch):
    _insert(monkeypatch, _http_500)
    assert main._supabase_insert("email_auto_log", {"email": "cliente@exemplo.com"}) is False
    assert "@" not in _ler(log), _ler(log)


# ══════════════════════════════════════════════════════════════════════════
#  2. A falha de gravação deixa rastro
# ══════════════════════════════════════════════════════════════════════════
def test_a_1a_falha_da_hora_vai_pro_error_log_e_as_seguintes_so_contam(log, monkeypatch):
    urls = _insert(monkeypatch, _http_500)
    assert main._supabase_insert("usage_events", {"event": "a"}) is False
    assert main._supabase_insert("usage_events", {"event": "b"}) is False
    assert main._supabase_insert("usage_events", {"event": "c"}) is False
    c = main._FALHAS_DE_GRAVACAO["usage_events"]
    assert c["n"] == 3 and c["total"] == 3, c
    rastros = [u for u in urls if u.endswith("/error_log")]
    assert len(rastros) == 1, "a 1ª falha da hora não deixou rastro (ou deixou um por falha): %r" % urls


def test_falha_no_proprio_error_log_so_conta_sem_recursao(log, monkeypatch):
    urls = _insert(monkeypatch, _http_500)
    assert main._supabase_insert("error_log", {"stage": "x"}) is False
    assert urls == [urls[0]] and urls[0].endswith("/error_log"), urls
    assert main._FALHAS_DE_GRAVACAO["error_log"]["n"] == 1


def test_CONTROLE_insert_que_deu_certo_nao_conta_falha(log, monkeypatch):
    _insert(monkeypatch, lambda req: _Ok())
    main._supabase_insert("usage_events", {"event": "a"})
    assert main._FALHAS_DE_GRAVACAO == {}


def test_a_hora_nova_volta_a_deixar_rastro(log, monkeypatch):
    urls = _insert(monkeypatch, _http_500)
    main._FALHAS_DE_GRAVACAO["llm_uso"] = {"hora": "2000-01-01T00", "n": 7, "total": 7}
    main._supabase_insert("llm_uso", {"x": 1})
    assert [u for u in urls if u.endswith("/error_log")], "hora nova e nenhum rastro"
    assert main._FALHAS_DE_GRAVACAO["llm_uso"]["n"] == 1 and main._FALHAS_DE_GRAVACAO["llm_uso"]["total"] == 8


@pytest.mark.parametrize("com_arquivo", [True, False])
def test_o_diagnostico_mostra_as_falhas_por_tabela(log, monkeypatch, com_arquivo):
    import asyncio
    monkeypatch.setattr(main, "_require_admin", lambda r: None)
    if com_arquivo:
        main._supa_log("linha qualquer")
    main._FALHAS_DE_GRAVACAO["usage_events"] = {"hora": "2026-09-27T23", "n": 2, "total": 5}
    r = asyncio.run(main.debug_supa_log(request=None, tail=10))
    assert r["falhas_de_gravacao"]["usage_events"]["total"] == 5, r


# ══════════════════════════════════════════════════════════════════════════
#  3. O alarme de "a telemetria parou"
# ══════════════════════════════════════════════════════════════════════════
def _alarme(monkeypatch, projetos, eventos):
    logs, avisos = [], []
    monkeypatch.setattr(main, "_contar_do_dia", lambda o_que, dia: projetos)
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: eventos if isinstance(eventos, tuple) else (200, eventos))
    monkeypatch.setattr(main, "_log_error", lambda stage, msg, *a, **k: logs.append(stage))
    monkeypatch.setattr(main, "_notify_admin", lambda *a, **k: avisos.append(a[0]) or True)
    r = main._telemetria_parou(date(2026, 9, 26))
    return r, logs, avisos


def test_cliente_sem_nenhum_evento_no_dia_ALARMA(monkeypatch):
    r, logs, avisos = _alarme(monkeypatch, 5, [])
    assert r is True and logs == ["telemetria:parou"] and avisos, (r, logs, avisos)


@pytest.mark.parametrize("projetos,eventos,esperado", [
    (5, [{"id": 1}], False),         # teve evento: tudo normal
    (0, [], False),                  # dia sem cliente: silêncio é normal
    (None, [], None),                # não soube contar projeto: não sei
    (5, (500, None), None),          # não soube ler evento: não sei
])
def test_CONTROLE_o_alarme_so_toca_quando_deve(monkeypatch, projetos, eventos, esperado):
    r, logs, avisos = _alarme(monkeypatch, projetos, eventos)
    assert r is esperado and logs == [] and avisos == [], (r, logs, avisos)


def test_o_tick_diario_pergunta_pelo_dia_de_ontem(monkeypatch):
    vistos = []
    monkeypatch.setattr(main, "_require_tick_secret", lambda r: None)
    monkeypatch.setattr(main, "_ips_da_casa", lambda: set())
    import metricas_site as ms
    monkeypatch.setattr(ms, "token", lambda: "x")
    monkeypatch.setattr(ms, "coletar", lambda dia, ips_da_casa=None: {
        "dia": str(dia), "grupos_recebidos": 0, "_erro_origens": None})
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_telemetria_parou", lambda dia: vistos.append(dia) or False)
    r = main.metricas_tick(request=None, dias=1)
    assert vistos == [main._hoje_br() - __import__("datetime").timedelta(days=1)]
    assert r["telemetria_parou"] is False
