# -*- coding: utf-8 -*-
"""De onde chegou TODO mundo — o Web Analytics do Cloudflare, sem cookie.

27/09/2026 — Pedro escolheu "visitas por origem" pra decidir onde pôr esforço de marketing.
A origem que o painel já tinha (`origem_30d`) só vê quem ACEITOU o cookie; esta vê toda
visita que chega de fora (o "beacon" do Cloudflare, com a referência do navegador).

🩸 A 1ª versão (d8cc455) pedia `clientRefererHost` ao httpRequestsAdaptiveGroups e o
Cloudflare recusou no ar ("zone … does not have access to the field") — a coleta tratou
como "não medi" sem estragar o dia, mas a recusa só apareceu porque fui procurar: o erro
ficava num print. Agora ele sobe pro error_log, e este guarda cobra isso.

O que o guarda cobra, EXECUTANDO o código (coletor com Cloudflare de mentira, a rotina
diária, a rota, e o JavaScript do painel no dukpy):
- navegação de uma página nossa pra outra (0 visita, referência ai.arq.br) não é chegada;
- a volta do login (Google/Microsoft) tem rótulo próprio — não é "veio do Google";
- "linkedin" dentro de outro nome NÃO é LinkedIn (casa por domínio inteiro);
- a consulta que FALHA vira "não medi" (None) com o MOTIVO, nunca lista vazia — não derruba
  o dia, e o motivo chega ao error_log sem ir junto pro banco como coluna;
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

_GOOGLE = "Google (busca e IA do Google)"
_LOGIN = "volta do login (Google/Microsoft)"


def _grupo(host, visitas, pagina="/", pais="BR", amostra=None):
    # 27/09 (item 4): a visita sem referência vai pro balde da PÁGINA e do PAÍS —
    # o padrão aqui é página pública do Brasil, que é o "direto ou app" de verdade
    g = {"sum": {"visits": visitas},
         "dimensions": {"refererHost": host, "requestPath": pagina, "countryName": pais}}
    if amostra is not None:
        g["avg"] = {"sampleInterval": amostra}
    return g


def _resposta(grupos):
    return {"data": {"viewer": {"accounts": [{"rumPageloadEventsAdaptiveGroups": grupos}]}}}


# ── a classificação da referência ──────────────────────────────────────────────

@pytest.mark.parametrize("host,canal", [
    ("www.google.com", _GOOGLE),
    ("www.google.com.br", _GOOGLE),
    ("google.com", _GOOGLE),
    ("com.google.android.googlequicksearchbox", _GOOGLE),
    ("accounts.google.com", _LOGIN),                   # voltou do "Entrar com Google": não é aquisição
    ("login.live.com", _LOGIN),
    ("gemini.google.com", "Gemini"),
    ("mail.google.com", "E-mail"),
    ("com.google.android.gm", "E-mail"),
    ("chatgpt.com", "ChatGPT"),
    ("www.perplexity.ai", "Perplexity"),
    ("br.search.yahoo.com", "Yahoo"),
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

def test_soma_as_visitas_por_canal_e_ignora_a_navegacao_interna(monkeypatch):
    # os números de 26/09 lidos no ar, + um segundo domínio do Google e um ChatGPT
    grupos = [
        _grupo("", 37), _grupo("www.google.com", 10), _grupo("www.google.com.br", 2),
        _grupo("accounts.google.com", 4), _grupo("chatgpt.com", 3),
        _grupo("www.bing.com", 0),            # linha sem visita: não entra
        _grupo("ai.arq.br", 0),               # clique interno
        _grupo("www.ai.arq.br", 2),           # outro endereço NOSSO conta "visita" no beacon: não é chegada
    ]
    monkeypatch.setattr(ms, "_graphql", lambda q, timeout=25: _resposta(grupos))
    lista, truncada, erro, _amostra = ms.origens_do_dia("a", "b", limite=1000)
    assert erro is None and truncada is False
    por = {x["origem"]: x for x in lista}
    assert por[_GOOGLE]["visitas"] == 12, lista
    assert set(por[_GOOGLE]["hosts"]) == {"www.google.com", "www.google.com.br"}
    assert por[ms.SEM_REFERENCIA]["visitas"] == 37 and por["ChatGPT"]["visitas"] == 3
    assert por[_LOGIN]["visitas"] == 4, "a volta do login virou 'veio do Google'"
    assert "Bing" not in por and not any("ai.arq.br" in k or k == "interno" for k in por), lista
    assert sum(x["visitas"] for x in lista) == 56, "entrou visita que não é chegada de fora: %r" % lista
    assert [x["origem"] for x in lista][:2] == [ms.SEM_REFERENCIA, _GOOGLE], "a lista não veio do maior pro menor"


def test_a_pergunta_e_a_do_web_analytics_do_site(monkeypatch):
    vistas = []

    def _fake(q, timeout=25):
        vistas.append(q)
        return _resposta([])
    monkeypatch.setattr(ms, "_graphql", _fake)
    ms.origens_do_dia("2026-09-26T03:00:00Z", "2026-09-27T02:59:59Z")
    q = vistas[0]
    assert "rumPageloadEventsAdaptiveGroups" in q and ms._SITE_RUM in q and ms._CONTA in q
    assert "2026-09-26T03:00:00Z" in q, "o dia não é o de Brasília"
    assert "clientRefererHost" not in q, "voltou a pedir o campo que o plano da zona não tem"


def test_bateu_no_limite_diz_que_truncou(monkeypatch):
    grupos = [_grupo("site%d.com" % i, 1) for i in range(5)]
    monkeypatch.setattr(ms, "_graphql", lambda q, timeout=25: _resposta(grupos))
    assert ms.origens_do_dia("a", "b", limite=5)[1] is True


@pytest.mark.parametrize("resposta,trecho", [
    ({"errors": [{"message": "does not have access to the field"}]}, "does not have access"),
    ({"data": {"viewer": {"accounts": []}}}, "sem os grupos"),
    ({"data": {"viewer": {"accounts": [{}]}}}, "sem os grupos"),
])
def test_consulta_que_falha_vira_NAO_MEDI_com_o_MOTIVO(monkeypatch, resposta, trecho):
    monkeypatch.setattr(ms, "_graphql", lambda q, timeout=25: resposta)
    lista, truncada, erro, _amostra = ms.origens_do_dia("a", "b")
    assert lista is None and truncada is None, "falha virou lista (vazia = 'ninguém veio', é mentira)"
    assert erro and trecho in erro, erro


def test_excecao_tambem_vira_NAO_MEDI_com_o_motivo(monkeypatch):
    def _explode(q, timeout=25):
        raise TimeoutError("cloudflare lento")
    monkeypatch.setattr(ms, "_graphql", _explode)
    lista, _, erro, _amostra = ms.origens_do_dia("a", "b")
    assert lista is None and "cloudflare lento" in erro


def _principal():
    return {"data": {"viewer": {"zones": [{"httpRequestsAdaptiveGroups": [
        {"count": 3, "dimensions": {"clientIP": "9.9.9.9", "userAgentBrowser": "Chrome", "clientRequestPath": "/",
                                    "edgeResponseStatus": 200, "edgeResponseContentTypeName": "html"}}]}]}}}


def test_a_falha_das_origens_NAO_derruba_o_dia_e_leva_o_motivo(monkeypatch):
    def _fake(q, timeout=25):
        if "rumPageloadEventsAdaptiveGroups" in q:
            return {"errors": [{"message": "sem permissão de Account Analytics"}]}
        if "httpRequests1dGroups" in q:
            return {"data": {"viewer": {"zones": [{"httpRequests1dGroups": []}]}}}
        return _principal()
    monkeypatch.setattr(ms, "_graphql", _fake)
    monkeypatch.setattr(ms, "_teto_lembrado", 1000)
    linha = ms.coletar(date(2026, 9, 27), ips_da_casa=set())
    assert linha["grupos_recebidos"] == 1 and linha["req_gente"] == 3, linha
    assert linha["top_origens"] is None and linha["origens_truncada"] is None, linha
    assert "Account Analytics" in (linha.get("_erro_origens") or ""), linha


def test_a_linha_do_dia_leva_as_origens(monkeypatch):
    def _fake(q, timeout=25):
        if "rumPageloadEventsAdaptiveGroups" in q:
            return _resposta([_grupo("lnkd.in", 2)])
        if "httpRequests1dGroups" in q:
            return {"data": {"viewer": {"zones": [{"httpRequests1dGroups": []}]}}}
        return _principal()
    monkeypatch.setattr(ms, "_graphql", _fake)
    monkeypatch.setattr(ms, "_teto_lembrado", 1000)
    linha = ms.coletar(date(2026, 9, 27), ips_da_casa=set())
    assert linha["top_origens"] == [{"origem": "LinkedIn", "visitas": 2, "hosts": ["lnkd.in"]}]
    assert linha["origens_truncada"] is False and linha["_erro_origens"] is None


# ── a rotina diária: o motivo vai pro log e NÃO vai pro banco ──────────────────

@pytest.mark.parametrize("erro", ["Cloudflare recusou: sem permissão", None])
def test_o_tick_tira_o_motivo_da_linha_e_so_loga_quando_ha(monkeypatch, erro):
    import main as _m
    gravado, logs = [], []
    monkeypatch.setattr(_m, "_require_tick_secret", lambda r: None)
    monkeypatch.setattr(_m, "_ips_da_casa", lambda: set())
    monkeypatch.setattr(_m, "_contar_do_dia", lambda tabela, dia: None)
    monkeypatch.setattr(ms, "token", lambda: "x")      # a rotina importa metricas_site por dentro
    monkeypatch.setattr(ms, "coletar", lambda dia, ips_da_casa=None: {
        "dia": str(dia), "grupos_recebidos": 5, "top_origens": None, "origens_truncada": None, "_erro_origens": erro})
    monkeypatch.setattr(_m, "_supa_rest_service", lambda *a, **k: gravado.append(k.get("body")) or (201, None))
    monkeypatch.setattr(_m, "_log_error", lambda stage, msg, *a, **k: logs.append((stage, msg)))
    r = _m.metricas_tick(request=None, dias=1)
    assert gravado and all("_erro_origens" not in b for b in gravado), "a chave interna foi pro banco como coluna"
    assert r["gravados"], r
    if erro:
        assert any(s == "metricas:origens" and "sem permissão" in m for s, m in logs), logs
        assert r["origens_sem_medida"], r
    else:
        assert not any(s == "metricas:origens" for s, _ in logs), "logou erro que não houve"


# ── a soma da semana (rota do painel) ──────────────────────────────────────────

def test_a_semana_soma_so_dia_medido_e_inteiro_e_DIZ_quantos_ficaram_fora():
    import main as _m
    dias = [
        {"top_origens": None},                                                             # antigo
        {"top_origens": [{"origem": "LinkedIn", "visitas": 9}], "origens_truncada": True},    # truncado
        {"top_origens": [{"origem": _GOOGLE, "visitas": 4, "hosts": ["www.google.com"]},
                         {"origem": "ChatGPT", "visitas": 1}], "origens_truncada": False},
        {"top_origens": [{"origem": _GOOGLE, "visitas": 3, "hosts": ["www.google.com.br"]}],
         "origens_truncada": False},
    ]
    r = _m._origens_7d(dias)
    assert r["dias_somados"] == 2 and r["dias_fora"] == 2, r
    por = {x["origem"]: x for x in r["origens"]}
    assert por[_GOOGLE]["visitas"] == 7
    assert "LinkedIn" not in por, "o dia truncado entrou na soma"
    assert por[_GOOGLE]["hosts"] == ["www.google.com", "www.google.com.br"]
    assert r["origens"][0]["origem"] == _GOOGLE


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


def test_a_caixa_mostra_o_canal_as_visitas_e_a_nota_honesta():
    js = _js()
    r = js.evaljs("htmlOrigensDoSite(%s)" % json.dumps(
        {"origens": [{"origem": "ChatGPT", "visitas": 5, "hosts": ["chatgpt.com"]}], "dias_somados": 4, "dias_fora": 3}))
    assert "ChatGPT" in r["html"] and ">5<" in r["html"]
    assert "4 dia(s)" in r["nota"] and "3 fora" in r["nota"] and "sem cookie" in r["nota"]
    assert "conta a gente" in r["nota"], "a nota esconde que as nossas visitas diretas entram"


def test_o_nome_do_site_de_origem_sai_ESCAPADO():
    js = _js()
    mal = '<img src=x onerror=alert(1)>'
    r = js.evaljs("htmlOrigensDoSite(%s)" % json.dumps(
        {"origens": [{"origem": mal, "visitas": 1, "hosts": ['x" onmouseover="alert(1)']}], "dias_somados": 1, "dias_fora": 0}))
    assert "<img" not in r["html"] and "&lt;img" in r["html"], r["html"]
    assert 'x" onmouseover' not in r["html"], r["html"]
