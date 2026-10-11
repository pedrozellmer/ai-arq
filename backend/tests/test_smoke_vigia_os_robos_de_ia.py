# -*- coding: utf-8 -*-
"""O smoke diário confere que os rastreadores de IA continuam entrando no site.

🔎 11/10/2026 — estudo de SEO: em 30 dias, 41 cadastros disseram ter vindo por IA contra 39 da busca comum.
A regra da casa (nunca bloquear rastreador de IA) vivia de conferência à mão; um botão no Cloudflare ("Block AI
bots" ou o robots.txt gerenciado) desligaria o canal sem ninguém ver. Pedro: "segue com o 2, o 4 e o 6".

Duas medidas: o robots.txt QUE ESTÁ NO AR não barra nenhum robô, e cada robô leva 200 nas páginas.
🪤 O runner do GitHub é IP de datacenter e o Cloudflare às vezes barra todo mundo que vem dele: robô barrado COM
o navegador barrado junto = não medido (inconclusivo), nunca falha. Os testes rodam o script de verdade com a
rede encenada.
"""
import io
import os
import types

import pytest

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPT = os.path.join(_RAIZ, ".github", "scripts", "smoke_test_production.py")

_NOSSO = io.open(os.path.join(_RAIZ, "robots.txt"), encoding="utf-8").read()
_CF = {"Server": "cloudflare", "CF-RAY": "abc-GRU"}


@pytest.fixture
def smoke():
    mod = types.ModuleType("smoke_prod_ia")
    mod.__dict__["__name__"] = "smoke_prod_ia"
    exec(compile(io.open(_SCRIPT, encoding="utf-8").read(), _SCRIPT, "exec"), mod.__dict__)
    return mod


# ─── o robots.txt ───────────────────────────────────────────────────────────────────────────
def test_o_nosso_robots_nao_barra_nenhum_robo(smoke):
    assert smoke.robos_barrados_no_robots(_NOSSO) == []


def test_robots_gerenciado_que_barra_ia_e_pego(smoke):
    """O formato que o Cloudflare põe por cima quando o bloqueio de IA é ligado."""
    gerenciado = ("User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n\n"
                  "User-agent: Google-Extended\nDisallow: /\n\n" + _NOSSO)
    assert smoke.robos_barrados_no_robots(gerenciado) == ["GPTBot", "ClaudeBot", "Google-Extended"]


def test_disallow_geral_pega_todo_mundo_e_o_parcial_nao_conta(smoke):
    assert set(smoke.robos_barrados_no_robots("User-agent: *\nDisallow: /\n")) == set(smoke.ROBOS_NO_ROBOTS)
    assert smoke.robos_barrados_no_robots("User-agent: *\nDisallow: /backend/\nDisallow: /_*\n") == []
    # grupo próprio liberado vale mais que o geral barrado
    assert "GPTBot" not in smoke.robos_barrados_no_robots(
        "User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /\n")


# ─── a decisão por robô ─────────────────────────────────────────────────────────────────────
def test_o_veredito_separa_bloqueio_do_robo_de_bloqueio_do_runner(smoke):
    assert smoke.veredito_do_robo(200, 200, False) == "ok"
    assert smoke.veredito_do_robo(200, 403, True) == "falha"            # navegador entra, robô não
    assert smoke.veredito_do_robo(403, 403, True) == "inconclusivo"     # o IP do runner barrado pra todos
    assert smoke.veredito_do_robo(200, 404, False) == "falha"           # página sumiu só pro robô
    assert smoke.veredito_do_robo(403, 403, False) == "falha"           # 403 que NÃO é do Cloudflare


def _rede(smoke, monkeypatch, responde):
    pedidos = []

    def _get(url, headers=None, timeout=60, tentativas=3):
        ua = (headers or {}).get("User-Agent", "navegador")
        pedidos.append((url.replace(smoke.SITE_BASE, ""), ua.split("compatible; ")[-1].split("/")[0]))
        return responde(url.replace(smoke.SITE_BASE, ""), ua)
    monkeypatch.setattr(smoke, "_get", _get)
    monkeypatch.setattr(smoke, "failures", [])
    monkeypatch.setattr(smoke, "passes", [])
    monkeypatch.setattr(smoke, "inconclusivos", [])
    return pedidos


def test_tudo_liberado_passa_e_cada_robo_pede_as_tres_paginas(smoke, monkeypatch):
    pedidos = _rede(smoke, monkeypatch, lambda caminho, ua: (
        200, _NOSSO.encode("utf-8") if caminho == "/robots.txt" else b"<html>", {}))
    smoke._check_robos_de_ia()
    assert smoke.failures == [] and smoke.inconclusivos == []
    assert len(smoke.passes) == 1 + len(smoke.ROBOS_DE_IA)
    for robo in smoke.ROBOS_DE_IA:
        assert {p for p, quem in pedidos if quem == robo} == set(smoke.PAGINAS_DOS_ROBOS), robo


def test_robo_barrado_com_o_navegador_passando_e_FALHA(smoke, monkeypatch):
    def responde(caminho, ua):
        if caminho == "/robots.txt":
            return 200, _NOSSO.encode("utf-8"), {}
        if "ClaudeBot" in ua:
            return 403, b"", _CF
        return 200, b"<html>", {}
    _rede(smoke, monkeypatch, responde)
    smoke._check_robos_de_ia()
    assert len(smoke.failures) == 1 and smoke.failures[0].startswith("ClaudeBot recebe o site")
    assert "AI Crawl Control" in smoke.failures[0] and smoke.inconclusivos == []


def test_CONTROLE_runner_barrado_pra_todo_mundo_nao_vira_falha(smoke, monkeypatch):
    """O caso de 25/08: o Cloudflare barra o IP do GitHub, navegador incluído. Não é o robô."""
    _rede(smoke, monkeypatch, lambda caminho, ua: (403, b"", _CF))
    smoke._check_robos_de_ia()
    assert smoke.failures == [], smoke.failures
    assert len(smoke.inconclusivos) == 1 + len(smoke.ROBOS_DE_IA) and smoke.passes == []


def test_robots_no_ar_barrando_ia_e_FALHA_mesmo_com_as_paginas_abrindo(smoke, monkeypatch):
    barrado = "User-agent: GPTBot\nDisallow: /\n\n" + _NOSSO
    _rede(smoke, monkeypatch, lambda caminho, ua: (
        200, barrado.encode("utf-8") if caminho == "/robots.txt" else b"<html>", {}))
    smoke._check_robos_de_ia()
    assert len(smoke.failures) == 1 and "GPTBot" in smoke.failures[0]


def test_o_nivel_1_chama_o_vigia(smoke, monkeypatch):
    chamou = []
    monkeypatch.setattr(smoke, "_get", lambda *a, **k: (200, b"AI.arq API <html <urlset <title>", {}))
    monkeypatch.setattr(smoke, "_check_robos_de_ia", lambda: chamou.append(1))
    monkeypatch.setattr(smoke, "failures", [])
    monkeypatch.setattr(smoke, "passes", [])
    monkeypatch.setattr(smoke, "inconclusivos", [])
    smoke.nivel_1()
    assert chamou == [1]
