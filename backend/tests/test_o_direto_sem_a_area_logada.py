# -*- coding: utf-8 -*-
"""O "direto ou app" não conta mais a nossa área logada nem o de fora do país.

🩸 27/09/2026 — auditoria de telemetria, item 4. De 20 a 26/09 o painel dizia
"direto ou app: 220" e a leitura do dia foi feita em cima disso ("a IA
autodeclarada some em direto"). Recontado dia a dia, com a página e o país:
132 eram página LOGADA (114 só no /admin.html), 9 login/cadastro, 35 página
pública vinda de fora do Brasil e só 44 página pública do Brasil — com a
equipe dentro (o beacon não tem IP). Total de visitas de fora: 424, igual.

🔑 Visita SEM referência vai pro balde da página e do país; COM referência o
canal manda. O dia grava o `sampleInterval` (o Cloudflare amostra: a semana
pedida de uma vez veio 1 em 10). E o tick ganha `?so_origens=1`, que recolhe só
essas colunas — a linha inteira, perto do fim dos ~7 dias, viria pela metade.
"""
import glob
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metricas_site as ms  # noqa: E402
from _jsbancada import funcao_js, motor  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _g(host, visitas, pagina="/", pais="BR", amostra=1):
    return {"sum": {"visits": visitas}, "avg": {"sampleInterval": amostra},
            "dimensions": {"refererHost": host, "requestPath": pagina, "countryName": pais}}


def _resp(grupos):
    return {"data": {"viewer": {"accounts": [{"rumPageloadEventsAdaptiveGroups": grupos}]}}}


def _por(lista):
    return {x["origem"]: x["visitas"] for x in lista}


# ══════════════════════════════════════════════════════════════════════════
#  1. O balde da visita sem referência
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("pagina,pais,balde", [
    ("/admin.html", "BR", ms.AREA_LOGADA),
    ("/dashboard.html", "US", ms.AREA_LOGADA),          # logada ganha do país
    ("/dashboard", "BR", ms.AREA_LOGADA),               # sem .html é a mesma página
    ("/projeto.html?job_id=x", "BR", ms.AREA_LOGADA),
    ("/cadastro.html", "BR", ms.ENTRADA),
    ("/convite.html", "PT", ms.ENTRADA),
    ("/", "IN", ms.FORA_DO_BRASIL),
    ("/blog/posts/x.html", "", ms.FORA_DO_BRASIL),      # país desconhecido não é Brasil
    ("/", "BR", ms.SEM_REFERENCIA),
    ("/blog/posts/x.html", "br", ms.SEM_REFERENCIA),
])
def test_cada_visita_sem_referencia_cai_no_balde_certo(pagina, pais, balde):
    assert ms.balde_sem_referencia(pagina, pais) == balde


def test_com_referencia_o_canal_manda_mesmo_em_pagina_logada(monkeypatch):
    """Google no /dashboard.html é gente que clicou num resultado: aquisição."""
    monkeypatch.setattr(ms, "_graphql", lambda q, timeout=25: _resp(
        [_g("www.google.com", 3, "/dashboard.html", "US")]))
    lista = ms.origens_do_dia("a", "b")[0]
    assert _por(lista) == {"Google (busca e IA do Google)": 3}, lista


def test_a_semana_de_20_a_26_09_fecha_nos_numeros_medidos(monkeypatch):
    """Os baldes medidos no ar, dia a dia: 132 + 9 + 35 + 44 = 220 sem
    referência, e o total de visitas de fora continua 424."""
    grupos = [
        _g("", 114, "/admin.html"), _g("", 18, "/dashboard.html"),
        _g("", 9, "/login.html"),
        _g("", 19, "/blog/posts/um-post.html", "IN"), _g("", 16, "/", "US"),
        _g("", 30, "/"), _g("", 14, "/blog/posts/outro.html"),
        _g("www.google.com", 91), _g("www.bing.com", 55), _g("accounts.google.com", 38, "/cadastro.html"),
        _g("search.yahoo.com", 9), _g("chatgpt.com", 3), _g("gemini.google.com", 3),
        _g("ai.arq.br", 50, "/faq.html"),                                    # navegação interna
        _g("www.facebook.com", 2), _g("www.linkedin.com", 1), _g("l.instagram.com", 1), _g("mail.google.com", 1),
    ]
    monkeypatch.setattr(ms, "_graphql", lambda q, timeout=25: _resp(grupos))
    lista, truncada, erro, amostra = ms.origens_do_dia("a", "b")
    por = _por(lista)
    assert erro is None and truncada is False and amostra == 1
    assert por[ms.AREA_LOGADA] == 132 and por[ms.ENTRADA] == 9
    assert por[ms.FORA_DO_BRASIL] == 35
    assert por[ms.SEM_REFERENCIA] == 44, "o 'direto ou app' voltou a carregar área logada ou estrangeiro"
    assert sum(por.values()) == 424, "o total de visitas de fora deixou de fechar: %r" % por


def test_CONTROLE_sem_os_baldes_o_direto_daria_220():
    assert 114 + 18 + 9 + 19 + 16 + 30 + 14 == 220


def test_a_pergunta_pede_pagina_pais_e_amostra(monkeypatch):
    vistas = []
    monkeypatch.setattr(ms, "_graphql", lambda q, timeout=25: vistas.append(q) or _resp([]))
    ms.origens_do_dia("a", "b")
    for campo in ("requestPath", "countryName", "sampleInterval", "refererHost"):
        assert campo in vistas[0], campo


def test_a_amostra_do_dia_e_a_MAIOR_e_nula_quando_nao_vem(monkeypatch):
    # o maior NO MEIO: "fica com o último" ou "fica com o primeiro" reprovam
    monkeypatch.setattr(ms, "_graphql", lambda q, timeout=25: _resp(
        [_g("", 13, "/admin.html", amostra=1.083), _g("www.google.com", 6, amostra=2),
         _g("www.bing.com", 2, amostra=1)]))
    assert ms.origens_do_dia("a", "b")[3] == 2
    sem = {"sum": {"visits": 1}, "dimensions": {"refererHost": ""}}
    monkeypatch.setattr(ms, "_graphql", lambda q, timeout=25: _resp([sem]))
    assert ms.origens_do_dia("a", "b")[3] is None, "amostra inventada onde não veio"


def test_toda_pagina_da_raiz_esta_numa_classe():
    """Página nova sem classe cairia calada em "direto ou app" — o defeito que
    esta separação desfaz. Classificar é decidir: logada, entrada ou pública."""
    todas = ms.PAGINAS_DA_AREA_LOGADA | ms.PAGINAS_DE_ENTRADA | ms.PAGINAS_PUBLICAS
    soltas = sorted("/" + os.path.basename(p) for p in glob.glob(os.path.join(_RAIZ, "*.html"))
                    if "/" + os.path.basename(p) not in todas)
    assert not soltas, "página sem classe no balde do 'direto': %r" % soltas
    assert not (ms.PAGINAS_DA_AREA_LOGADA & ms.PAGINAS_DE_ENTRADA)
    assert not (ms.PAGINAS_PUBLICAS & (ms.PAGINAS_DA_AREA_LOGADA | ms.PAGINAS_DE_ENTRADA))


# ══════════════════════════════════════════════════════════════════════════
#  2. A recoleta só das origens
# ══════════════════════════════════════════════════════════════════════════
def _tick(monkeypatch, origens, resposta_patch=(200, [{"dia": "x"}])):
    import main as _m
    chamadas, logs = [], []
    monkeypatch.setattr(_m, "_require_tick_secret", lambda r: None)
    monkeypatch.setattr(ms, "token", lambda: "x")
    monkeypatch.setattr(ms, "origens_do_dia", lambda ini, fim, limite=1000: origens)
    monkeypatch.setattr(ms, "coletar", lambda *a, **k: pytest.fail("recoleta de origens coletou a linha inteira"))

    def _rest(metodo, caminho, body=None, params=None, prefer=None, **k):
        chamadas.append({"metodo": metodo, "caminho": caminho, "body": body, "params": params})
        return resposta_patch
    monkeypatch.setattr(_m, "_supa_rest_service", _rest)
    monkeypatch.setattr(_m, "_log_error", lambda stage, msg, *a, **k: logs.append((stage, msg)))
    r = _m.metricas_tick(request=None, dias=2, so_origens=1)
    return r, chamadas, logs


def test_so_origens_mexe_SO_nas_colunas_de_origem_e_so_em_linha_que_existe(monkeypatch):
    lista = [{"origem": ms.SEM_REFERENCIA, "visitas": 5, "hosts": []}]
    r, chamadas, _ = _tick(monkeypatch, (lista, False, None, 1.2))
    assert r["modo"] == "so_origens" and len(r["gravados"]) == 2, r
    for c in chamadas:
        assert c["metodo"] == "PATCH", "virou upsert — dia sem linha nasceria com fuso UTC"
        assert set(c["body"]) == {"top_origens", "origens_truncada", "origens_amostra"}, c["body"]
        assert c["params"]["dia"].startswith("eq.")


def test_so_origens_NAO_sobrescreve_com_lista_vazia_nem_com_falha(monkeypatch):
    r, chamadas, logs = _tick(monkeypatch, ([], False, None, 1))
    assert chamadas == [] and not r["gravados"] and len(r["falhas"]) == 2, r
    assert any(s == "metricas:origens" for s, _ in logs), "a falha não chegou a ninguém"
    r2, chamadas2, _ = _tick(monkeypatch, (None, None, "Cloudflare recusou", None))
    assert chamadas2 == [] and "Cloudflare recusou" in " ".join(r2["falhas"])


def test_so_origens_dia_sem_linha_e_FALHA_dita(monkeypatch):
    lista = [{"origem": ms.SEM_REFERENCIA, "visitas": 5, "hosts": []}]
    r, _, _ = _tick(monkeypatch, (lista, False, None, 1), resposta_patch=(200, []))
    assert not r["gravados"] and len(r["falhas"]) == 2, r


def test_CONTROLE_sem_so_origens_o_tick_coleta_a_linha_inteira(monkeypatch):
    import main as _m
    coletados = []
    monkeypatch.setattr(_m, "_require_tick_secret", lambda r: None)
    monkeypatch.setattr(_m, "_ips_da_casa", lambda: set())
    monkeypatch.setattr(_m, "_contar_do_dia", lambda tabela, dia: None)
    monkeypatch.setattr(ms, "token", lambda: "x")
    monkeypatch.setattr(ms, "coletar", lambda dia, ips_da_casa=None: coletados.append(dia) or {
        "dia": str(dia), "grupos_recebidos": 5, "top_origens": None, "origens_truncada": None,
        "_erro_origens": None})
    monkeypatch.setattr(_m, "_supa_rest_service", lambda *a, **k: (201, None))
    monkeypatch.setattr(_m, "_log_error", lambda *a, **k: None)
    _m.metricas_tick(request=None, dias=1)
    assert len(coletados) == 1


# ══════════════════════════════════════════════════════════════════════════
#  3. A semana e a caixa do painel
# ══════════════════════════════════════════════════════════════════════════
def test_a_semana_diz_a_maior_amostra_dos_dias_somados():
    import main as _m
    dias = [{"top_origens": [{"origem": "ChatGPT", "visitas": 1}], "origens_truncada": False, "origens_amostra": 1.3},
            {"top_origens": [{"origem": "ChatGPT", "visitas": 1}], "origens_truncada": False, "origens_amostra": 2},
            {"top_origens": [{"origem": "ChatGPT", "visitas": 1}], "origens_truncada": True, "origens_amostra": 10}]
    assert _m._origens_7d(dias)["amostra_max"] == 2, "entrou a amostra de dia que ficou fora da soma"
    assert _m._origens_7d([{"top_origens": [], "origens_truncada": False}])["amostra_max"] is None


def _caixa(o):
    js = motor("true;")
    js.evaljs(funcao_js("esc", "admin.html"))
    js.evaljs(funcao_js("htmlOrigensDoSite", "admin.html"))
    return js.evaljs("htmlOrigensDoSite(%s)" % json.dumps(o))


def test_a_caixa_diz_que_e_estimativa_quando_ha_amostra():
    base = {"origens": [{"origem": "ChatGPT", "visitas": 5}], "dias_somados": 3, "dias_fora": 0}
    com = _caixa(dict(base, amostra_max=2))["nota"]
    assert "estimativa" in com and "1 em 2" in com, com
    for sem in (dict(base, amostra_max=1), dict(base, amostra_max=None), base):
        assert "estimativa" not in _caixa(sem)["nota"]


def test_a_caixa_explica_os_baldes_e_segue_dizendo_que_conta_a_gente():
    nota = _caixa({"origens": [{"origem": "ChatGPT", "visitas": 5}], "dias_somados": 3, "dias_fora": 0})["nota"]
    assert "área logada" in nota and "fora do Brasil" in nota and "página pública do Brasil" in nota
    assert "conta a gente" in nota
