# -*- coding: utf-8 -*-
"""O envio da newsletter não prende o servidor e não manda a mesma edição duas vezes.

🩸 30/09/2026 — `admin_newsletter_send` é `async def` e chamava o envio (SMTP síncrono, ~2,5 s por
e-mail) direto no laço de eventos. Com 140 destinatários o laço ficou preso por minutos, o /health
do Render não respondeu, a instância foi reiniciada às 10:03:57 e o envio parou em 50 — e um job de
cliente que rodava junto caiu. Reenviar sem filtro mandaria a edição de novo pros 50.

Agora: (1) o envio de verdade roda numa thread e a rota responde na hora; (2) um envio por vez;
(3) quem já recebeu ESTA edição (email_sent_log, mesmo assunto, 7 dias) é pulado, e se o log não
puder ser lido NINGUÉM recebe (falha fechada); (4) o teste pro admin não pula.
"""
import asyncio
import io
import json
import threading
import time
import urllib.request

import pytest

import main


class _Req:
    headers = {}

    def __init__(self, corpo):
        self._corpo = corpo

    async def json(self):
        return self._corpo


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setattr(main, "_require_admin", lambda r: {"email": main.ADMIN_EMAIL})
    # a trava é global: garante que cada teste comece com ela solta
    if main._NEWSLETTER_TRAVA.locked():
        main._NEWSLETTER_TRAVA.release()
    yield
    if main._NEWSLETTER_TRAVA.locked():
        main._NEWSLETTER_TRAVA.release()


def _espera(cond, teto=5.0):
    t0 = time.time()
    while time.time() - t0 < teto:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_o_envio_de_verdade_nao_prende_a_rota(monkeypatch):
    base = [("a@x.com", "A"), ("b@x.com", "B"), ("c@x.com", "C")]
    monkeypatch.setattr(main, "_newsletter_recipients", lambda tipo: list(base))
    chamadas = []

    def blast_lento(subject, html, recipients, pular_quem_ja_recebeu=True):
        chamadas.append((threading.current_thread().name, len(recipients), pular_quem_ja_recebeu))
        time.sleep(0.6)                      # o SMTP de verdade: segundos
        return len(recipients), 0

    monkeypatch.setattr(main, "_newsletter_blast", blast_lento)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: True)
    t0 = time.time()
    r = asyncio.run(main.admin_newsletter_send(_Req({"tipo": "servico"})))
    gasto = time.time() - t0
    assert r["status"] == "enviando" and r["background"] is True and r["recipients"] == 3, r
    assert gasto < 0.4, "a rota esperou o envio (%.2f s) — o laço de eventos fica preso" % gasto
    assert _espera(lambda: chamadas), "o envio em segundo plano não começou"
    nome, n, pula = chamadas[0]
    assert nome != threading.main_thread().name and n == 3 and pula is True, chamadas
    assert _espera(lambda: not main._NEWSLETTER_TRAVA.locked()), "a trava não foi solta no fim"


def test_um_envio_por_vez(monkeypatch):
    monkeypatch.setattr(main, "_newsletter_recipients", lambda tipo: [("a@x.com", "A")])
    solta = threading.Event()

    def blast_preso(subject, html, recipients, pular_quem_ja_recebeu=True):
        solta.wait(3)
        return 1, 0

    monkeypatch.setattr(main, "_newsletter_blast", blast_preso)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: True)
    asyncio.run(main.admin_newsletter_send(_Req({"tipo": "campanha"})))
    with pytest.raises(main.HTTPException) as ex:
        asyncio.run(main.admin_newsletter_send(_Req({"tipo": "campanha"})))
    assert ex.value.status_code == 409
    solta.set()
    assert _espera(lambda: not main._NEWSLETTER_TRAVA.locked())


def test_o_teste_pro_admin_responde_na_hora_e_NAO_pula(monkeypatch):
    visto = {}

    def blast(subject, html, recipients, pular_quem_ja_recebeu=True):
        visto.update(n=len(recipients), pula=pular_quem_ja_recebeu, quem=recipients[0][0])
        return 1, 0

    monkeypatch.setattr(main, "_newsletter_blast", blast)
    r = asyncio.run(main.admin_newsletter_send(_Req({"test_only": True})))
    assert r["test_only"] is True and r["sent"] == 1, r
    assert visto == {"n": 1, "pula": False, "quem": main.ADMIN_EMAIL}, visto


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_quem_ja_recebeu_esta_edicao_e_pulado(monkeypatch):
    urls = []

    def urlopen(req, timeout=None):
        urls.append(req.full_url)
        return _Resp(json.dumps([{"email": "A@x.com"}, {"email": "c@x.com"}]).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    base = [("a@x.com", "A"), ("b@x.com", "B"), ("c@x.com", "C")]
    fica = main._tirar_quem_ja_recebeu("Quantas vezes a mesma parede entra na sua conta?", base)
    assert fica == [("b@x.com", "B")], fica
    assert "kind=eq.newsletter" in urls[0] and "subject=eq.Quantas%20vezes" in urls[0], urls[0]
    assert "%3F" in urls[0], "o '?' do assunto tem que ir escapado"


def test_FALHA_FECHADA_sem_ler_o_log_ninguem_recebe(monkeypatch):
    def urlopen(req, timeout=None):
        raise OSError("sem rede")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    enviados = []
    monkeypatch.setattr(main, "_send_email_smtp", lambda *a, **k: enviados.append(a[0]) or True)
    assert main._tirar_quem_ja_recebeu("x", [("a@x.com", "A")]) is None
    assert main._newsletter_blast("x", "<p>{{SAUDACAO}}</p>", [("a@x.com", "A")]) == (0, 0)
    assert enviados == [], "mandou sem saber quem já tinha recebido"


def test_CONTROLE_sem_o_filtro_quem_ja_recebeu_receberia_de_novo(monkeypatch):
    """Prova que é o filtro que evita o dobro: com ele desligado, os 3 recebem."""
    enviados = []
    monkeypatch.setattr(main, "_send_email_smtp", lambda *a, **k: enviados.append(a[0]) or True)
    base = [("a@x.com", "A"), ("b@x.com", "B"), ("c@x.com", "C")]
    assert main._newsletter_blast("x", "<p>{{SAUDACAO}}</p>", base, pular_quem_ja_recebeu=False) == (3, 0)
    assert enviados == ["a@x.com", "b@x.com", "c@x.com"]


def test_CONTROLE_o_jeito_antigo_prenderia_a_rota():
    """🧪 O que o guarda de tempo mede: uma rota que chama o envio direto espera ele inteiro."""
    async def rota_antiga():
        time.sleep(0.5)                       # o envio síncrono no laço
        return {"status": "ok"}

    t0 = time.time()
    asyncio.run(rota_antiga())
    assert time.time() - t0 >= 0.4, "o controle não reproduz o bloqueio"
