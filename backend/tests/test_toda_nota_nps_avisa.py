# -*- coding: utf-8 -*-
"""Toda nota NPS avisa o Pedro na hora — nao so o detrator (31/08/2026).

O BURACO: a rota fazia `if category == "detractor": _alerta_detrator(row)`.
Promotor e neutro gravavam calados. Em 24/08 o cliente-13 deu **9 com o
comentario "Gostei muito do resultado"** e o Pedro descobriu em **31/08**,
sete dias depois, olhando o painel por acaso.

Por que isso e grave e nao cosmetico: existem **5 respostas NPS em toda a
historia do produto** (2 delas de casa). Perder uma e perder 20% do sinal. E
promotor com comentario e a materia-prima da pagina de cases, que esta parada
esperando depoimento desde sempre.

Estes testes CHAMAM a rota (asyncio.run) em vez de ler o fonte — licao do
apagao de 29h do /api/track, e da recaida de hoje de manha no registro de
exclusao, em que 4 testes liam a string certa num codigo que nao executava.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class _Req:
    headers = {"cf-connecting-ip": "198.51.100.9"}
    client = None


def _chamar(score, monkeypatch, comentario="", detalhado=False):
    """Roda a rota de NPS com tudo dublado; devolve (resposta, alertas)."""
    alertas = []
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda *a, **k: {"id": "u-1", "email": "cliente@exemplo.com"})
    monkeypatch.setattr(main, "_supabase_insert", lambda tabela, linha: True)
    monkeypatch.setattr(main, "_alerta_nps",
                        lambda linha, categoria="?": alertas.append((linha, categoria)))
    if detalhado:
        monkeypatch.setattr(main, "_name_from_auth", lambda uid: "Cliente Teste")
        p = main.NPSDetailedPayload(
            recommend=score, job_id="job-x", comment=comentario,
            stage_ratings={k: 4 for k in main._NPS_STAGES})
        resp = asyncio.run(main.submit_nps_detailed(p, _Req()))
    else:
        p = main.NPSPayload(user_id="u-1", score=score, comment=comentario,
                            context="after_download", job_id="job-x")
        resp = asyncio.run(main.submit_nps(p, _Req()))
    return resp, alertas


def test_promotor_AVISA(monkeypatch):
    """O caso cliente-13: nota 9 com elogio ficou 7 dias invisivel."""
    resp, alertas = _chamar(9, monkeypatch, comentario="Gostei muito do resultado")
    assert resp["category"] == "promoter"
    assert len(alertas) == 1, "nota 9 nao avisou ninguem — foi exatamente o caso cliente-13"
    linha, cat = alertas[0]
    assert cat == "promoter"
    assert linha["comment"] == "Gostei muito do resultado"


def test_nota_10_AVISA(monkeypatch):
    _, alertas = _chamar(10, monkeypatch)
    assert len(alertas) == 1 and alertas[0][1] == "promoter"


def test_neutro_AVISA(monkeypatch):
    """Neutro e quem quase gostou — o que faltou vira a proxima melhoria."""
    resp, alertas = _chamar(7, monkeypatch, comentario="Faltou o forro")
    assert resp["category"] == "passive"
    assert len(alertas) == 1 and alertas[0][1] == "passive"


def test_detrator_CONTINUA_avisando(monkeypatch):
    """CONTROLE: o comportamento que ja existia nao pode ter sido perdido
    (caso cliente-20, 16/08 — nota 2 as 19:18, janela de resgate de horas)."""
    resp, alertas = _chamar(2, monkeypatch)
    assert resp["category"] == "detractor"
    assert len(alertas) == 1 and alertas[0][1] == "detractor"


def test_feedback_detalhado_TAMBEM_avisa_promotor(monkeypatch):
    """A 2a porta: /api/nps/detailed tinha a MESMA trava. E o feedback mais
    rico que existe (nota por etapa) — perder um promotor dali e pior."""
    resp, alertas = _chamar(9, monkeypatch, comentario="Muito bom", detalhado=True)
    assert resp["category"] == "promoter"
    assert len(alertas) == 1 and alertas[0][1] == "promoter"


def test_TODA_faixa_de_0_a_10_avisa(monkeypatch):
    """Varredura: nenhuma nota pode passar calada."""
    faltaram = []
    for n in range(0, 11):
        _, alertas = _chamar(n, monkeypatch)
        if len(alertas) != 1:
            faltaram.append(n)
    assert not faltaram, f"notas que nao avisaram: {faltaram}"


def test_o_alerta_MONTA_email_diferente_por_faixa(monkeypatch):
    """Executa `_alerta_nps` de verdade (com o e-mail dublado) e confere que
    promotor e detrator nao chegam com o mesmo texto — senao o alerta novo vira
    ruido e o Pedro para de abrir."""
    import threading
    vistos, pronto = [], threading.Event()

    def _fake_notify(assunto, corpo):
        vistos.append((assunto, corpo))
        if len(vistos) >= 2:
            pronto.set()
        return True

    monkeypatch.setattr(main, "_notify_admin", _fake_notify)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rows", lambda *a, **k: [])
    base = {"score": 9, "user_email": "a@b.com", "user_name": "cliente-13",
            "comment": "Gostei muito", "job_id": ""}
    main._alerta_nps(dict(base), "promoter")
    main._alerta_nps(dict(base, score=2, comment=""), "detractor")
    assert pronto.wait(10), f"o alerta nao chegou a mandar e-mail: {vistos}"
    assuntos = " | ".join(a for a, _ in vistos)
    assert "promotor" in assuntos and "detrator" in assuntos, assuntos
    corpos = [c for _, c in vistos]
    assert any("DEPOIMENTO" in c.upper() for c in corpos), \
        "promotor tem que puxar pra pedir depoimento (pagina de cases parada)"
