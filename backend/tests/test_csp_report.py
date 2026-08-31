# -*- coding: utf-8 -*-
"""A coleta de violações de CSP funciona de verdade (30/08/2026).

🔒 O CSP vai entrar em Report-Only apontando pra /api/csp-report: é assim que
a gente mede, em cliente REAL e logado, o que o teste de load não alcança (os
2 defeitos que os céticos acharam eram exatamente desse tipo). Se este
endpoint nascer morto, ligamos o CSP no escuro.

Estes testes CHAMAM a rota (asyncio.run), como manda a lição do apagão de 29h
do /api/track: guarda que lê o FONTE não pega argumento faltando.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class _Req:
    def __init__(self, corpo, headers=None):
        self._c = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.headers = headers or {"cf-connecting-ip": "198.51.100.77"}
        self.client = None

    async def body(self):
        return self._c


def _chamar(req, monkeypatch):
    """Roda a rota com o gravador dublado; devolve (resposta, linhas_gravadas)."""
    gravadas = []
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job=None, severity="error":
                        gravadas.append((stage, msg, severity)))
    monkeypatch.setattr(main, "_RATE_BUCKETS", {})
    resp = asyncio.run(main.csp_report(req))
    return resp, gravadas


def test_formato_classico_csp_report(monkeypatch):
    corpo = {"csp-report": {
        "document-uri": "https://ai.arq.br/visualizar-prancha.html",
        "effective-directive": "frame-src",
        "blocked-uri": "blob"}}
    resp, grav = _chamar(_Req(corpo), monkeypatch)
    assert resp["status"] == "ok"
    assert len(grav) == 1, grav
    stage, msg, sev = grav[0]
    assert stage == "csp:violacao" and sev == "info"
    assert "frame-src" in msg and "visualizar-prancha" in msg


def test_formato_reporting_api(monkeypatch):
    """Chrome moderno manda lista de {type, body} — tem que entender os dois."""
    corpo = [{"type": "csp-violation", "body": {
        "documentURL": "https://ai.arq.br/dashboard.html",
        "effectiveDirective": "img-src",
        "blockedURL": "https://lh3.googleusercontent.com/a/x"}}]
    resp, grav = _chamar(_Req(corpo), monkeypatch)
    assert resp["status"] == "ok" and len(grav) == 1
    assert "img-src" in grav[0][1] and "googleusercontent" in grav[0][1]


def test_RUIDO_de_extensao_e_descartado(monkeypatch):
    """🪤 Quase todo relatório de CSP do mundo real é extensão do navegador.
    Sem este filtro o error_log vira lixo e o painel fica ilegível."""
    corpo = {"csp-report": {"document-uri": "https://ai.arq.br/",
                            "effective-directive": "script-src",
                            "blocked-uri": "chrome-extension://abcdef/inject.js"}}
    resp, grav = _chamar(_Req(corpo), monkeypatch)
    assert resp["status"] == "ok"
    assert grav == [], "ruído de extensão foi gravado"


def test_corpo_lixo_nao_derruba(monkeypatch):
    resp, grav = _chamar(_Req("nao eh json".encode()), monkeypatch)
    assert resp["status"] == "ignorado" and grav == []


def test_teto_por_IP_fecha(monkeypatch):
    """Endpoint público = mesma trava do /api/contact (que só funciona desde
    hoje, com CF-Connecting-IP)."""
    gravadas = []
    monkeypatch.setattr(main, "_log_error",
                        lambda *a, **k: gravadas.append(a))
    monkeypatch.setattr(main, "_RATE_BUCKETS", {})
    corpo = {"csp-report": {"document-uri": "https://ai.arq.br/",
                            "effective-directive": "img-src",
                            "blocked-uri": "https://x.example"}}
    oks = sum(1 for _ in range(40)
              if asyncio.run(main.csp_report(_Req(corpo)))["status"] == "ok")
    assert oks == 30, f"passou {oks} (teto é 30)"


def test_CONTROLE_um_relatorio_REAL_de_violacao_grava(monkeypatch):
    """🧪 Controle positivo: o formato que o Chrome manda de verdade quando o
    iframe blob: é bloqueado — o defeito nº1 que os céticos acharam."""
    corpo = {"csp-report": {
        "document-uri": "https://ai.arq.br/visualizar-prancha.html?job_id=x",
        "referrer": "", "violated-directive": "frame-src 'self'",
        "effective-directive": "frame-src", "original-policy": "default-src 'self'; ...",
        "disposition": "report", "blocked-uri": "blob", "status-code": 200}}
    resp, grav = _chamar(_Req(corpo), monkeypatch)
    assert len(grav) == 1 and "frame-src" in grav[0][1]
