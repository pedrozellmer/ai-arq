# -*- coding: utf-8 -*-
"""De onde chegou TODO mundo — a referência do navegador, lida no Cloudflare, sem cookie.

27/09/2026 — Pedro escolheu "visitas por origem" pra decidir onde pôr esforço de marketing.
A origem que o painel já tinha (`origem_30d`) só vê quem ACEITOU o cookie; esta vê todo mundo.

O que o guarda cobra, EXECUTANDO o código (coletor com Cloudflare de mentira, rota, e o
JavaScript do painel no dukpy):
- robô e a nossa máquina não contam; clique de uma página nossa pra outra não é "chegada";
- o mesmo endereço vindo duas vezes do Google conta 1;
- "linkedin" dentro de outro nome NÃO é LinkedIn (casa por domínio inteiro);
- a consulta que FALHA vira "não medi" (None), nunca lista vazia — e não derruba o dia;
- dia não medido ou truncado fica FORA da soma da semana, e a soma DIZ quantos ficaram fora;
- o nome do site de origem vem de fora e sai ESCAPADO na tela.
"""
import json
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metricas_site as ms  # noqa: E402
from _jsbancada import funcao_js, motor  # noqa: E402

_NOSSO = "10.0.0.1"


def _grupo(ip, ref, nav="Chrome"):
    return {"count": 1, "dimensions": {"clientIP": ip, "clientRefererHost": ref, "userAgentBrowser": nav}}


def _resposta(grupos):
    return {"data": {"viewer": {"zones": [{"httpRequestsAdaptiveGroups": grupos}]}}}


# ── a classificação da referência ──────────────────────────────────────────────

@pytest.mark.parametrize("host,canal", [
    ("www.google.com", "Google (busca e IA do Google)"),
    ("www.google.com.br", "Google (busca e IA do Google)"),
    ("google.com", "Google (busca e IA do Google)"),
    ("com.google.android.googlequicksearchbox", "Google (busca e IA do Google)"),
    ("gemini.google.com", "Gemini"),
    ("mail.google.com", "E-mail"),
    ("com.google.android.gm", "E-mail"),
    ("chatgpt.com", "ChatGPT"),
    ("www.perplexity.ai", "Perplexity"),
    ("www.linkedin.com", "LinkedIn"),
    ("lnkd.in", "LinkedIn"),
    ("com.linkedin.android", "LinkedIn"),
    ("l.instagram.com", "Instagram"),
    ("", ms.SEM_REFERENCIA),
    (None, ms.SEM_REFERENCIA),
    ("notlinkedin.com", "notlinkedin.com"),          # pedaço de nome NÃO é o canal
    ("www.arquiteturabrasil.com.br", "www.arquiteturabrasil.com.br"),
])
def test_cada_referencia_cai_no_canal_certo(host, canal):
    assert ms.canal_da_referencia(host) == canal


@pytest.mark.parametrize("interno", ["ai.arq.br", "www.ai.arq.br", "AI.ARQ.BR"])
def test_navegacao_dentro_do_site_nao_e_chegada(interno):
    assert ms.canal_da_referencia(interno) is None


# ── a coleta do dia ────────────────────────────────────────────────────────────

def test_conta_enderecos_distintos_por_canal_sem_robo_sem_nos_sem_navegacao_interna(monkeypatch):
    grupos = [
        _grupo("1.1.1.1", "www.google.com"), _grupo("1.1.1.1", "www.google.com"),  # mesma pessoa, 2 páginas
        _grupo("2.2.2.2", "www.google.com.br"),
        _grupo("2.2.2.2", "www.google.com"),       # a MESMA pessoa por outro domínio do Google: conta 1
        _grupo("3.3.3.3", "chatgpt.com"),
        _grupo("4.4.4.4", ""),                                                   # direto ou app
        _grupo("1.1.1.1", "ai.arq.br"),                                          # clique interno
        _grupo("5.5.5.5", "www.google.com", nav="unknown"),                      # robô
        _grupo(_NOSSO, "www.google.com"),                                        # nós
    ]
    monkeypatch.setattr(ms, "_graphql", lambda q, timeout=25: _resposta(grupos))
    lista, truncada = ms.origens_do_dia("a", "b", {_NOSSO}, 1000)
    assert truncada is False
    por = {x["origem"]: x for x in lista}
    assert por["Google (busca e IA do Google)"]["enderecos"] == 2, lista
    assert set(por["Google (busca e IA do Google)"]["hosts"]) == {"www.google.com", "www.google.com.br"}
    assert por["ChatGPT"]["enderecos"] == 1 and por[ms.SEM_REFERENCIA]["enderecos"] == 1
    assert "ai.arq.br" not in por and len(lista) == 3, lista
    assert lista[0]["origem"].startswith("Google"), "a lista não veio do maior pro menor"


def test_bateu_no_teto_diz_que_truncou(monkeypatch):
    grupos = [_grupo("1.1.1.%d" % i, "www.google.com") for i in range(5)]
    monkeypatch.setattr(ms, "_graphql", lambda q, timeout=25: _resposta(grupos))
    assert ms.origens_do_dia("a", "b", set(), 5)[1] is True


@pytest.mark.parametrize("resposta", [
    {"errors": [{"message": "unknown field clientRefererHost"}]},   # o GraphQL falha com HTTP 200
    {"data": {"viewer": {"zones": []}}},
    {"data": {"viewer": {"zones": [{}]}}},
])
def test_consulta_que_falha_vira_NAO_MEDI_e_nao_lista_vazia(monkeypatch, resposta):
    monkeypatch.setattr(ms, "_graphql", lambda q, timeout=25: resposta)
    assert ms.origens_do_dia("a", "b", set(), 100) == (None, None)


def test_excecao_tambem_vira_NAO_MEDI(monkeypatch):
    def _explode(q, timeout=25):
        raise TimeoutError("cloudflare lento")
    monkeypatch.setattr(ms, "_graphql", _explode)
    assert ms.origens_do_dia("a", "b", set(), 100) == (None, None)


def test_a_falha_das_origens_NAO_derruba_o_dia(monkeypatch):
    """A série principal continua sendo gravada; só a coluna nova fica nula."""
    principal = [{"count": 3, "dimensions": {"clientIP": "9.9.9.9", "userAgentBrowser": "Chrome",
                                              "clientRequestPath": "/", "edgeResponseStatus": 200,
                                              "edgeResponseContentTypeName": "html"}}]

    def _fake(q, timeout=25):
        if "clientRefererHost" in q:
            return {"errors": [{"message": "campo desconhecido"}]}
        if "httpRequests1dGroups" in q:
            return {"data": {"viewer": {"zones": [{"httpRequests1dGroups": []}]}}}
        return _resposta(principal)
    monkeypatch.setattr(ms, "_graphql", _fake)
    monkeypatch.setattr(ms, "_teto_lembrado", 1000)
    linha = ms.coletar(date(2026, 9, 27), ips_da_casa=set())
    assert linha["grupos_recebidos"] == 1 and linha["req_gente"] == 3, linha
    assert linha["top_origens"] is None and linha["origens_truncada"] is None, linha


def test_a_linha_do_dia_leva_as_origens(monkeypatch):
    def _fake(q, timeout=25):
        if "clientRefererHost" in q:
            return _resposta([_grupo("1.1.1.1", "lnkd.in")])
        if "httpRequests1dGroups" in q:
            return {"data": {"viewer": {"zones": [{"httpRequests1dGroups": []}]}}}
        return _resposta([])
    monkeypatch.setattr(ms, "_graphql", _fake)
    monkeypatch.setattr(ms, "_teto_lembrado", 1000)
    linha = ms.coletar(date(2026, 9, 27), ips_da_casa=set())
    assert linha["top_origens"] == [{"origem": "LinkedIn", "enderecos": 1, "hosts": ["lnkd.in"]}]
    assert linha["origens_truncada"] is False


# ── a soma da semana (rota do painel) ──────────────────────────────────────────

def test_a_semana_soma_so_dia_medido_e_inteiro_e_DIZ_quantos_ficaram_fora():
    import main as _m
    dias = [
        {"top_origens": None},                                                             # antigo
        {"top_origens": [{"origem": "LinkedIn", "enderecos": 9}], "origens_truncada": True},  # truncado
        {"top_origens": [{"origem": "Google (busca e IA do Google)", "enderecos": 4, "hosts": ["www.google.com"]},
                         {"origem": "ChatGPT", "enderecos": 1}], "origens_truncada": False},
        {"top_origens": [{"origem": "Google (busca e IA do Google)", "enderecos": 3, "hosts": ["www.google.com.br"]}],
         "origens_truncada": False},
    ]
    r = _m._origens_7d(dias)
    assert r["dias_somados"] == 2 and r["dias_fora"] == 2, r
    por = {x["origem"]: x for x in r["origens"]}
    assert por["Google (busca e IA do Google)"]["enderecos"] == 7
    assert "LinkedIn" not in por, "o dia truncado entrou na soma"
    assert por["Google (busca e IA do Google)"]["hosts"] == ["www.google.com", "www.google.com.br"]
    assert r["origens"][0]["origem"].startswith("Google")


# ── a caixa do painel, rodando o JavaScript de verdade ─────────────────────────

def _js():
    js = motor("true;")
    js.evaljs(funcao_js("esc", "admin.html"))
    js.evaljs(funcao_js("htmlOrigensDoSite", "admin.html"))
    return js


def test_a_caixa_distingue_NAO_LI_de_AINDA_NAO_MEDI_de_NINGUEM_VEIO():
    js = _js()
    nao_li = js.evaljs("htmlOrigensDoSite(null)")["html"]
    ainda = js.evaljs("htmlOrigensDoSite({origens: [], dias_somados: 0, dias_fora: 7})")["html"]
    ninguem = js.evaljs("htmlOrigensDoSite({origens: [], dias_somados: 3, dias_fora: 0})")["html"]
    assert "não consegui ler" in nao_li
    assert "ainda sem dia medido" in ainda
    assert "ninguém chegou" in ninguem
    assert len({nao_li, ainda, ninguem}) == 3


def test_a_caixa_mostra_o_canal_o_numero_e_a_nota_honesta():
    js = _js()
    r = js.evaljs("htmlOrigensDoSite(%s)" % json.dumps(
        {"origens": [{"origem": "ChatGPT", "enderecos": 5, "hosts": ["chatgpt.com"]}], "dias_somados": 4, "dias_fora": 3}))
    assert "ChatGPT" in r["html"] and ">5<" in r["html"]
    assert "4 dia(s)" in r["nota"] and "3 fora" in r["nota"] and "sem cookie" in r["nota"]


def test_o_nome_do_site_de_origem_sai_ESCAPADO():
    js = _js()
    mal = '<img src=x onerror=alert(1)>'
    r = js.evaljs("htmlOrigensDoSite(%s)" % json.dumps(
        {"origens": [{"origem": mal, "enderecos": 1, "hosts": ['x" onmouseover="alert(1)']}], "dias_somados": 1, "dias_fora": 0}))
    assert "<img" not in r["html"] and "&lt;img" in r["html"], r["html"]
    assert 'x" onmouseover' not in r["html"], r["html"]
