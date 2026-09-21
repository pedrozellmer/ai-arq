# -*- coding: utf-8 -*-
"""Dia com a coleta truncada não vira veredito sobre o público.

🚨 20/09/2026. O painel disse ao Pedro: "19/09 (sábado) teve 19 endereços, e o
mais fraco que já vi teve 29. Vale olhar." Ele respondeu o que importava:
**"quase todo dia tá isso 'vale olhar'"**.

🩸 E o número estava TRUNCADO. `coletar()` pede ao Cloudflare os grupos com MAIS
requisições (`orderBy: count_DESC`, teto de 400) e só depois separa robô de
gente, aqui no Python. Desde 17/09 o site levou uma onda de robôs — de ~80 para
14.000 requisições por dia, 93% do tráfego — e eles ocuparam os 400 lugares. As
pessoas ficaram fora da janela.

📏 A prova de que não foi o público que sumiu: as REQUISIÇÕES de gente subiram
(738 → 1.147) enquanto os ENDEREÇOS distintos caíam de 63 para 19. E a página
mais vista passou de 16 endereços para 3.

🔑 O defeito não era o teto: era o painel não saber que bateu nele. Ele mostrava
19 com a mesma cara de quando mostra 63, e mandava olhar o público quando o que
tinha quebrado era a régua. Três dias seguidos assim e o aviso virou ruído —
que é como um alarme morre.

🪤 NULL não é "não truncado". Os dias coletados antes desta medida existir não
sabem responder, e não-sei não pode virar acusação: falta de estado não é
neutra (a mesma lição do e-mail de falha que acusava o cliente, em 19/09).
"""
import os
import sys
from datetime import date, timedelta

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import metricas_site as ms  # noqa: E402


# ── uma série de sábados, o formato que o veredito recebe ───────────────────
def _serie(valores, truncado_no_ultimo=None, truncado_em=()):
    """Sábados consecutivos; `valores[-1]` é o dia julgado."""
    base = date(2026, 8, 1)          # 01/08/2026 é um sábado
    fora = []
    for i, v in enumerate(valores):
        d = {"dia": (base + timedelta(days=7 * i)).isoformat(), "ips_gente": v}
        if i in truncado_em:
            d["coleta_truncada"] = True
        fora.append(d)
    if truncado_no_ultimo is not None:
        fora[-1]["coleta_truncada"] = truncado_no_ultimo
    return fora


def test_dia_truncado_NAO_manda_olhar_o_publico():
    """🧪 CONTROLE POSITIVO da regra: sem ela, este é exatamente o caso que
    produziu o 'vale olhar' de 19/09."""
    s = _serie([63, 55, 48, 29, 19], truncado_no_ultimo=True)
    s[-1]["grupos_recebidos"] = 400
    v = ms.veredito(s)

    assert v["status"] == "coleta_truncada", v
    assert "Vale olhar" not in v["frase"], (
        "o painel ainda manda olhar o público num dia em que a contagem veio "
        "pela metade: %r" % v["frase"])
    assert "incompleto" in v["frase"].lower(), v["frase"]
    assert "400" in v["frase"], (
        "a frase não diz em que teto a coleta bateu — sem isso ninguém sabe o "
        "que consertar: %r" % v["frase"])


def test_CONTROLE_dia_limpo_e_baixo_CONTINUA_alarmando():
    """🧪 O conserto não pode virar mordaça: queda de verdade, com coleta
    inteira, tem que continuar aparecendo."""
    s = _serie([63, 55, 48, 29, 19], truncado_no_ultimo=False)
    v = ms.veredito(s)
    assert v["status"] == "abaixo", v
    assert "Vale olhar" in v["frase"], v["frase"]


def test_dia_SEM_a_informacao_nao_e_tratado_como_limpo_nem_como_truncado():
    """🪤 Os dias antigos não têm a chave. `None` é "não sei" — e o código
    decide com `is True`, não com verdade/falsidade solta."""
    s = _serie([63, 55, 48, 29, 19])          # ninguém tem a chave
    v = ms.veredito(s)
    assert v["status"] == "abaixo", (
        "dia sem a informação deixou de ser julgado — isso apagaria o alarme "
        "de todo o histórico: %r" % v)


def test_dia_truncado_nao_serve_de_REGUA_pros_outros():
    """🔑 O estrago tem duas pontas. Um sábado truncado com 19 endereços vira
    o 'pior sábado que já vi' e puxa o piso para baixo — aí todo sábado normal
    passa a parecer bom, e a régua fica envenenada por semanas."""
    # três sábados bons, um truncado baixíssimo, e hoje um sábado fraco de verdade
    s = _serie([63, 55, 48, 5, 29], truncado_em=(3,))
    v = ms.veredito(s)
    assert v["status"] == "abaixo", (
        "o sábado truncado (5) entrou como piso e absolveu um dia que era "
        "para ser acusado: %r" % v)
    assert v["faixa"][0] == 48, (
        "o piso saiu de um dia truncado: %r" % (v["faixa"],))


# ── a coleta marca o truncamento ────────────────────────────────────────────
class _Cloudflare:
    """Dublê do GraphQL. 🪤 **k na assinatura: dublê com a cara exata desarma
    guarda em silêncio (3× em setembro)."""

    def __init__(self, n_grupos):
        self.n = n_grupos

    def __call__(self, query, *a, **k):
        if "httpRequests1dGroups" in query:      # a consulta do número cru
            return {"data": {"viewer": {"zones": [{"httpRequests1dGroups": []}]}}}
        grupos = [{"count": 1,
                   "dimensions": {"clientIP": "203.0.113.%d" % (i % 250),
                                  "userAgentBrowser": "Chrome",
                                  "clientRequestPath": "/",
                                  "edgeResponseStatus": "200",
                                  "edgeResponseContentTypeName": "html"}}
                  for i in range(self.n)]
        return {"data": {"viewer": {"zones": [
            {"httpRequestsAdaptiveGroups": grupos}]}}}


@pytest.fixture
def sem_rede(monkeypatch):
    monkeypatch.setattr(ms, "erros_5xx_do_dia", lambda *a, **k: 0)
    return monkeypatch


def test_a_coleta_avisa_quando_bate_no_teto(sem_rede):
    sem_rede.setattr(ms, "_graphql", _Cloudflare(ms.TETO_DE_GRUPOS))
    out = ms.coletar(date(2026, 9, 19))
    assert out["coleta_truncada"] is True, out
    assert out["grupos_recebidos"] == ms.TETO_DE_GRUPOS, out


def test_CONTROLE_coleta_folgada_NAO_e_marcada(sem_rede):
    """🧪 Sem isto, um marcador que dissesse sempre True passaria no teste
    acima e o painel pararia de opinar para sempre."""
    sem_rede.setattr(ms, "_graphql", _Cloudflare(12))
    out = ms.coletar(date(2026, 9, 19))
    assert out["coleta_truncada"] is False, out
    assert out["grupos_recebidos"] == 12, out
    assert out["ips_gente"] == 12, out


def test_o_teto_da_consulta_e_o_MESMO_que_o_marcador_usa(sem_rede):
    """🪤 Duas cópias do 400 — uma na string da consulta, outra na comparação —
    divergiriam em silêncio: a consulta traria 400 e o marcador esperaria outro
    número, então nada seria marcado nunca."""
    # 🪤 `coletar` faz MAIS DE UMA consulta (a dos grupos e a do número cru do
    # painel). Guardar só a última olharia a query errada — foi o que esta
    # versão fez na primeira execução.
    vistas = []

    def _espia(query, *a, **k):
        vistas.append(query)
        return _Cloudflare(3)(query)

    sem_rede.setattr(ms, "_graphql", _espia)
    ms.coletar(date(2026, 9, 19))
    dos_grupos = [q for q in vistas if "httpRequestsAdaptiveGroups" in q]
    assert dos_grupos, "a consulta dos grupos sumiu: %r" % [q[:60] for q in vistas]
    assert "limit: %d" % ms.TETO_DE_GRUPOS in dos_grupos[0], (
        "o teto da consulta não vem da constante — duas cópias do número "
        "divergem em silêncio e nada é marcado como truncado: %r"
        % dos_grupos[0][:200])


def test_a_tela_do_admin_sabe_pintar_o_status_novo():
    """🪤 Status que a tela não conhece cai no default por ACIDENTE. Aqui o
    acidente até acerta a cor, mas ninguém escreveu que acerta — e o próximo a
    mexer no mapa não tem como saber que `coleta_truncada` depende dele.

    🔑 E precisa ser CINZA, não âmbar: dia truncado não é veredito ruim sobre
    o público, é ausência de veredito.
    """
    import io
    raiz = os.path.dirname(_BACKEND)
    painel = io.open(os.path.join(raiz, "admin.html"), encoding="utf-8").read()
    i = painel.find("nao_sei: 'bg-gray-300'")
    assert i > 0, "o mapa de cores do farol sumiu do admin.html"
    trecho = painel[i - 200:i + 260]
    assert "coleta_truncada:" in trecho, (
        "o status novo não está no mapa de cores — depende do default: %r"
        % trecho[-260:])
    assert "coleta_truncada: 'bg-gray-300'" in trecho, (
        "dia truncado ficou com cor de alarme; ele não é veredito sobre o "
        "público: %r" % trecho[-260:])


# ══════════════════════════════════════════════════════════════════════════
#  🩸 O QUE A REVISÃO ADVERSARIAL DERRUBOU: a frase calava, o DESENHO mentia
# ══════════════════════════════════════════════════════════════════════════
# O veredito passou a recusar julgamento, mas as barras do MESMO cartão
# continuavam desenhando 63 → 38 → 19 em cor de dia medido, com "19 endereços"
# no hover, três centímetros abaixo da frase que diz "não dá pra comparar".
# O que se lê primeiro é o desenho — e foi o gráfico, não a frase, que o Pedro
# mandou no print.
def _barras(serie):
    from _jsbancada import funcao_js, motor, rodar
    js = motor(funcao_js("barrasDoMovimento", "admin.html"))
    out = rodar(js, "barrasDoMovimento(%s)" % _json(serie))
    assert out.get("ok"), out
    return out["valor"]


def _json(o):
    import json
    return json.dumps(o)


def _dia(iso, ips, **extra):
    d = {"dia": iso, "ips_gente": ips, "fuso": "America/Sao_Paulo",
         "req_total": 900, "req_robo": 80, "req_nosso": 20, "req_gente": 800}
    d.update(extra)
    return d


def test_a_BARRA_do_dia_truncado_nao_desenha_o_numero_cortado():
    html = _barras([_dia("2026-09-16", 63),
                    _dia("2026-09-19", 19, coleta_truncada=True,
                         grupos_recebidos=400)])
    assert "contagem incompleta" in html, (
        "a barra do dia truncado ainda anuncia o número cortado: %r" % html[-400:])
    assert "19 endere" not in html, (
        "o hover continua dizendo '19 endereços' num dia em que a contagem "
        "veio pela metade: %r" % html[-400:])
    assert "400 grupos" in html, (
        "a barra não diz onde a coleta bateu: %r" % html[-400:])
    assert html.count("bg-gray-200") == 1, (
        "o dia truncado não ficou cinza (ou pintou o dia bom junto): %r" % html)


def test_CONTROLE_a_barra_do_dia_LIMPO_continua_mostrando_o_numero():
    """🧪 Sem isto, apagar todas as barras passaria nos dois testes acima."""
    html = _barras([_dia("2026-09-16", 63), _dia("2026-09-15", 53)])
    assert "63 endere" in html and "53 endere" in html, html[-300:]
    assert "bg-gray-200" not in html, (
        "dia medido saiu com cor de 'sem medição': %r" % html[-300:])
    assert "contagem incompleta" not in html, html[-300:]


def test_o_dia_truncado_sai_da_ESCALA_das_barras_boas():
    """🔑 O estrago tem duas pontas. Se o dia truncado continua no cálculo do
    teto, ele comprime a escala das barras boas com um número que não é
    medida — e um dia truncado ALTO achataria o gráfico inteiro."""
    so_bons = _barras([_dia("2026-09-16", 60), _dia("2026-09-15", 30)])
    com_truncado = _barras([_dia("2026-09-16", 60), _dia("2026-09-15", 30),
                            _dia("2026-09-19", 600, coleta_truncada=True,
                                 grupos_recebidos=400)])
    import re as _re

    def alturas(h):
        # 🪤 Cada dia desenha DUAS alturas: a barra e a faixa fixa de 6px da
        # separação gente/robô/nós. Comparar a lista crua mistura as duas.
        return [a for a in _re.findall(r"height:(\d+)px", h) if a != "6"]

    assert alturas(so_bons) == alturas(com_truncado)[:2], (
        "o dia truncado entrou na escala e esmagou as barras boas: %s vs %s"
        % (alturas(so_bons), alturas(com_truncado)))
    assert alturas(com_truncado)[2] == "3", (
        "o dia truncado não virou toco: %s" % alturas(com_truncado))


def test_dia_SEM_a_coluna_desenha_normal():
    """🪤 NULL é 'não sei' — dia antigo continua com barra e número."""
    html = _barras([_dia("2026-08-01", 44)])
    assert "44 endere" in html and "bg-gray-200" not in html, html[-300:]


# ══════════════════════════════════════════════════════════════════════════
#  E OS OUTROS CARTÕES DO MESMO PAINEL
# ══════════════════════════════════════════════════════════════════════════
# 🩸 A revisão achou o irmão do problema: calar o veredito não basta se
# "Páginas que trouxeram gente" e a inflação do Cloudflare seguem somando o
# dia truncado. O `top_paginas` de um dia cortado só tem o que sobrou dentro
# dos grupos que passaram — em 17–19/09 a página mais vista caiu de 16
# endereços para 3, por truncamento. Publicar isso convida à conclusão errada
# ("o blog morreu") no mesmo painel em que a frase de cima diz que o dia não
# presta.
def _rota_metricas(monkeypatch, serie):
    """Roda `/api/admin/metricas` de verdade, com o banco de mentira."""
    import main

    def _rest(metodo, caminho, *a, **k):
        if caminho == "metricas_diarias":
            return 200, list(serie)
        return 200, []

    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_service", _rest)
    monkeypatch.setattr(main, "_origem_das_visitas", lambda *a, **k: None)
    monkeypatch.setattr(main, "_funil_do_site", lambda *a, **k: {})
    return main.admin_metricas(request=None, dias=30)


def _d(iso, ips, paginas, **extra):
    d = {"dia": iso, "ips_gente": ips, "unicos_cloudflare": ips * 3,
         "fuso": "America/Sao_Paulo",
         "top_paginas": [{"pagina": p, "enderecos": n} for p, n in paginas]}
    d.update(extra)
    return d


def test_as_PAGINAS_nao_somam_o_dia_truncado(monkeypatch):
    """🧪 CONTROLE POSITIVO: sem o filtro, o /blog/ aparece com 3 a menos e a
    lista publica uma queda que é da nossa coleta."""
    out = _rota_metricas(monkeypatch, [
        _d("2026-09-16", 63, [("/blog/", 16), ("/faq.html", 4)]),
        _d("2026-09-19", 19, [("/blog/", 3)], coleta_truncada=True,
           grupos_recebidos=400),
    ])
    topo = {p["pagina"]: p["enderecos"] for p in out["top_paginas_7d"]}
    assert topo.get("/blog/") == 16, (
        "o dia truncado entrou na soma das páginas: %r" % topo)
    assert out["top_paginas_7d_meta"]["dias_truncados_fora"] == 1, out["top_paginas_7d_meta"]
    assert out["top_paginas_7d_meta"]["dias_somados"] == 1, out["top_paginas_7d_meta"]


def test_a_INFLACAO_nao_usa_o_dia_truncado(monkeypatch):
    """🔑 O fator divide únicos do Cloudflare (que conta robô e explode na
    onda) por um `ips_gente` cortado. Em 19/09 daria 10,5× contra os ~3× dos
    dias limpos — o painel publicaria como piora da inflação uma piora que é
    da nossa coleta."""
    out = _rota_metricas(monkeypatch, [
        _d("2026-09-16", 60, [("/", 5)]),                       # 180/60 = 3,0
        _d("2026-09-19", 19, [("/", 1)], unicos_cloudflare=200,
           coleta_truncada=True, grupos_recebidos=400),         # 200/19 = 10,5
    ])
    infl = out["inflacao_7d"]
    assert infl["fator"] == 3.0, (
        "o dia truncado entrou no fator de inflação: %r" % infl)
    assert infl["dias_truncados_fora"] == 1, infl


def test_CONTROLE_sem_dia_truncado_tudo_continua_somando(monkeypatch):
    """🧪 Sem isto, um filtro que jogasse tudo fora passaria nos dois acima e
    os cartões ficariam vazios para sempre."""
    out = _rota_metricas(monkeypatch, [
        _d("2026-09-16", 60, [("/blog/", 10)]),
        _d("2026-09-15", 40, [("/blog/", 6)]),
    ])
    topo = {p["pagina"]: p["enderecos"] for p in out["top_paginas_7d"]}
    assert topo.get("/blog/") == 16, topo
    assert out["top_paginas_7d_meta"] == {"dias_somados": 2,
                                          "dias_truncados_fora": 0}, out["top_paginas_7d_meta"]
    assert out["inflacao_7d"]["fator"] == 3.0, out["inflacao_7d"]


def test_dia_SEM_a_coluna_continua_somando_nas_paginas(monkeypatch):
    """🪤 NULL é "não sei". Tirar esses dias esvaziaria o cartão inteiro por
    causa de uma coluna que nasceu hoje."""
    out = _rota_metricas(monkeypatch, [_d("2026-08-01", 44, [("/faq.html", 9)])])
    topo = {p["pagina"]: p["enderecos"] for p in out["top_paginas_7d"]}
    assert topo.get("/faq.html") == 9, topo
    assert out["top_paginas_7d_meta"]["dias_truncados_fora"] == 0
