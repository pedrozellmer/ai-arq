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
def _serie(valores, truncado_no_ultimo=None, truncado_em=(), sem_marca=False):
    """Sábados consecutivos; `valores[-1]` é o dia julgado.

    🪤 22/09/2026: o padrão passou a ser `coleta_truncada=False` — "medido
    inteiro, com a régua nova". Antes era a AUSÊNCIA da chave, e a ausência
    deixou de significar "dia normal": significa "medido com o teto de 400", que
    saía cortado. Quem quer o dia velho pede `sem_marca=True`.
    """
    base = date(2026, 8, 1)          # 01/08/2026 é um sábado
    fora = []
    for i, v in enumerate(valores):
        d = {"dia": (base + timedelta(days=7 * i)).isoformat(), "ips_gente": v}
        if not sem_marca:
            d["coleta_truncada"] = i in truncado_em
        elif i in truncado_em:
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


def test_dia_SEM_a_informacao_nao_e_comparado_com_os_dias_da_REGUA_NOVA():
    """🚨 22/09/2026 — ESTE GUARDA DIZIA O CONTRÁRIO, e estava certo até hoje.

    Enquanto todos os dias eram medidos com o mesmo teto de 400, o erro era
    igual em todo mundo e comparar ainda dizia alguma coisa; o guarda antigo
    protegia isso ("dia sem a informação continua sendo julgado").

    📏 O teto virou perguntado à zona e os mesmos dias mudaram de tamanho:
    19, 20 e 21/09 foram de 19→65, 34→72 e 13→120 endereços ao serem
    recoletados. Dia velho contra dia novo virou comparação entre réguas
    diferentes — e o painel diria "disparou" por causa da nossa medição.

    🔑 Agora sem marca é "medido com a régua velha", que é um estado de
    instrumento, não um veredito sobre o público.
    """
    s = _serie([63, 55, 48, 29, 19], sem_marca=True)   # ninguém tem a chave
    v = ms.veredito(s)
    assert v["status"] == "regua_antiga", (
        "dia medido com o teto antigo voltou a ser comparado com os novos: %r" % v)
    assert "Vale olhar" not in v["frase"], v["frase"]
    assert "22/09" in v["frase"], (
        "a frase não diz QUANDO a régua mudou — sem isso o aviso não ensina "
        "nada a quem lê: %r" % v["frase"])


def test_dia_da_REGUA_VELHA_nao_serve_de_regua_pros_novos():
    """🔑 A outra ponta, a que engana de verdade: hoje está medido inteiro
    (120), e os sábados do histórico foram medidos cortados (63, 55, 48). Se
    eles entrarem como faixa, o painel anuncia "acima do mais cheio que já vi"
    — uma alta que é só a régua tendo mudado."""
    s = _serie([63, 55, 48, 120], truncado_no_ultimo=False, sem_marca=True)
    v = ms.veredito(s)
    assert v["status"] == "nao_sei", (
        "os dias da régua velha entraram na faixa e inventaram uma alta: %r" % v)
    assert v["regua_velha"] == 3, v
    assert "22/09" in v["frase"] and "cortados" in v["frase"], (
        "o painel se calou sem dizer por quê — painel que parece quebrado não "
        "é lido: %r" % v["frase"])


def test_a_frase_da_REGUA_VELHA_concorda_em_GENERO():
    """🪤 A primeira versão saiu "3 segundas-feiras ficaram de fora: foram
    MEDIDOS". Este texto o Pedro lê todo dia, e frase torta faz o painel
    parecer descuidado — painel descuidado não é lido. Mesma lição das outras
    frases deste módulo: escrever as duas versões, nunca colar letras."""
    # segundas: feminino
    segundas = [{"dia": d, "ips_gente": n} for d, n in
                [("2026-08-03", 60), ("2026-08-10", 55), ("2026-08-17", 48)]]
    segundas.append({"dia": "2026-08-24", "ips_gente": 120,
                     "coleta_truncada": False})
    f = ms.veredito(segundas)["frase"]
    assert "foram medidas" in f and "cortadas" in f, (
        "concordância errada no feminino: %r" % f)
    # sábados: masculino
    sabados = _serie([63, 55, 48, 120], truncado_no_ultimo=False, sem_marca=True)
    g = ms.veredito(sabados)["frase"]
    assert "foram medidos" in g and "cortados" in g, (
        "concordância errada no masculino: %r" % g)


def test_CONTROLE_tres_dias_da_REGUA_NOVA_voltam_a_dar_veredito():
    """🧪 Sem isto, uma régua que recusasse tudo passaria nos dois testes
    acima e o painel ficaria mudo para sempre — que é exatamente a doença que
    este conserto veio curar."""
    s = _serie([63, 55, 48, 29])              # padrão: todos com a régua nova
    v = ms.veredito(s)
    assert v["status"] == "abaixo", v
    assert "Vale olhar" in v["frase"], v["frase"]


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
    guarda em silêncio (3× em setembro).

    `teto` é o que o Cloudflare responde quando perguntam o `maxPageSize` da
    zona; `None` finge uma zona que não sabe responder.
    """

    def __init__(self, n_grupos, teto=None):
        self.n = n_grupos
        self.teto = teto

    def __call__(self, query, *a, **k):
        if "maxPageSize" in query:               # a pergunta do teto da zona
            if self.teto is None:
                return {"errors": [{"message": "sem settings"}]}
            return {"data": {"viewer": {"zones": [{"settings": {
                "httpRequestsAdaptiveGroups": {"maxPageSize": self.teto}}}]}}}
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
    # 🪤 O teto é lembrado por PROCESSO. Sem zerar, o primeiro teste que rodar
    # escolhe o teto de todos os outros e os guardas passam a medir o cache.
    monkeypatch.setattr(ms, "_teto_lembrado", None)
    return monkeypatch


def test_a_coleta_avisa_quando_bate_no_teto(sem_rede):
    sem_rede.setattr(ms, "_graphql", _Cloudflare(1000, teto=1000))
    out = ms.coletar(date(2026, 9, 19))
    assert out["coleta_truncada"] is True, out
    assert out["grupos_recebidos"] == 1000, out


def test_CONTROLE_coleta_folgada_NAO_e_marcada(sem_rede):
    """🧪 Sem isto, um marcador que dissesse sempre True passaria no teste
    acima e o painel pararia de opinar para sempre."""
    sem_rede.setattr(ms, "_graphql", _Cloudflare(12, teto=1000))
    out = ms.coletar(date(2026, 9, 19))
    assert out["coleta_truncada"] is False, out
    assert out["grupos_recebidos"] == 12, out
    assert out["ips_gente"] == 12, out


def test_o_teto_vem_do_CLOUDFLARE_e_nao_do_numero_que_eu_ESCOLHI(sem_rede):
    """🚨 22/09/2026 — os 400 batiam TODO DIA (3 de 3 dias medidos, inclusive
    um com o robô calmo), e a trava do truncamento virava mordaça permanente.

    🪤 Este guarda reprova quem voltar a cravar o número na consulta: com a
    zona respondendo 10.000, pedir 400 é recusar 96% do dia de graça."""
    vistas = []

    def _espia(query, *a, **k):
        vistas.append(query)
        return _Cloudflare(500, teto=10000)(query)

    sem_rede.setattr(ms, "_graphql", _espia)
    out = ms.coletar(date(2026, 9, 19))
    dos_grupos = [q for q in vistas if "httpRequestsAdaptiveGroups" in q
                  and "maxPageSize" not in q]
    assert "limit: 10000" in dos_grupos[0], (
        "a consulta não usou o teto que a zona respondeu: %r" % dos_grupos[0][:200])
    assert out["coleta_truncada"] is False, (
        "500 grupos com teto de 10.000 é coleta FOLGADA: %r" % out)


def test_se_o_CLOUDFLARE_nao_disser_o_teto_a_coleta_usa_o_PADRAO(sem_rede):
    """🧪 O outro lado, executado. Chutar alto sem confirmação faz o GraphQL
    recusar a consulta inteira — e dia recusado não volta, porque o detalhe
    morre em ~7 dias. Sem resposta, vale o número que comprovadamente passa."""
    vistas = []

    def _espia(query, *a, **k):
        vistas.append(query)
        return _Cloudflare(3, teto=None)(query)

    sem_rede.setattr(ms, "_graphql", _espia)
    ms.coletar(date(2026, 9, 19))
    dos_grupos = [q for q in vistas if "httpRequestsAdaptiveGroups" in q
                  and "maxPageSize" not in q]
    assert "limit: %d" % ms.TETO_PADRAO_DE_GRUPOS in dos_grupos[0], (
        "sem resposta da zona a coleta tem que cair no padrão: %r"
        % dos_grupos[0][:200])


def test_o_teto_da_ZONA_nao_passa_do_que_esta_maquina_aguenta(sem_rede):
    """🪤 Teto de fora não vira ordem de dentro. Se a zona oferecer um número
    gigante, pedir tudo é uma resposta de tamanho imprevisível dentro de uma
    consulta com timeout — e coleta que estoura o tempo não deixa nem o dado
    truncado, deixa buraco."""
    vistas = []

    def _espia(query, *a, **k):
        vistas.append(query)
        return _Cloudflare(3, teto=999999)(query)

    sem_rede.setattr(ms, "_graphql", _espia)
    ms.coletar(date(2026, 9, 19))
    dos_grupos = [q for q in vistas if "httpRequestsAdaptiveGroups" in q
                  and "maxPageSize" not in q]
    assert "limit: %d" % ms._MAXIMO_QUE_AGUENTAMOS in dos_grupos[0], (
        "a coleta aceitou o número da zona sem olhar o que aguenta: %r"
        % dos_grupos[0][:200])


def test_a_pergunta_do_teto_nao_se_repete_a_cada_DIA(sem_rede):
    """🪤 O tick reescreve 3 dias por rodada. Perguntar o teto uma vez por dia
    coletado triplica a chamada à toa — e o limite do GraphQL é por janela de
    5 minutos."""
    contou = {"n": 0}

    def _espia(query, *a, **k):
        if "maxPageSize" in query:
            contou["n"] += 1
        return _Cloudflare(3, teto=5000)(query)

    sem_rede.setattr(ms, "_graphql", _espia)
    for atras in (1, 2, 3):
        ms.coletar(date(2026, 9, 19) - timedelta(days=atras))
    assert contou["n"] == 1, (
        "o teto foi perguntado %d vezes para 3 dias" % contou["n"])


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
        return _Cloudflare(777, teto=777)(query)

    sem_rede.setattr(ms, "_graphql", _espia)
    out = ms.coletar(date(2026, 9, 19))
    dos_grupos = [q for q in vistas if "httpRequestsAdaptiveGroups" in q
                  and "maxPageSize" not in q]
    assert dos_grupos, "a consulta dos grupos sumiu: %r" % [q[:60] for q in vistas]
    assert "limit: 777" in dos_grupos[0], (
        "o teto da consulta não é o mesmo que o marcador usa — duas cópias do "
        "número divergem em silêncio e nada é marcado como truncado: %r"
        % dos_grupos[0][:200])
    assert out["coleta_truncada"] is True, (
        "vieram 777 grupos para um teto de 777 e ninguém marcou: %r" % out)


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


# ══════════════════════════════════════════════════════════════════════════
#  🔧 CURAR A SÉRIE: recoletar o que o Cloudflare ainda guarda
# ══════════════════════════════════════════════════════════════════════════
# 🚨 22/09/2026. Quando a régua muda, os dias velhos não se consertam sozinhos
# — e o detalhe (IP, navegador) morre em ~7 dias. Ou se recolhe dentro da
# janela, ou aquele pedaço da série fica cortado PARA SEMPRE.
def _tick(monkeypatch, coletados, **kw):
    """Roda `/api/metricas/tick` de verdade, com Cloudflare e banco de mentira.

    `coletados` é um dict {dias_atras: linha} — o que a coleta devolveria.
    Devolve (resposta, gravados_no_banco).
    """
    import main
    import metricas_site as _ms
    from datetime import date as _d

    hoje = _d(2026, 9, 22)
    gravado = []

    def _coletar(dia, **k):
        atras = (hoje - dia).days
        if atras not in coletados:
            raise RuntimeError("o dublê não tem o dia %s" % dia)
        linha = dict(coletados[atras])
        linha["dia"] = dia.isoformat()
        return linha

    def _rest(metodo, caminho, *a, **k):
        if caminho == "metricas_diarias" and metodo == "POST":
            gravado.append(dict(k.get("body") or {}))
        return 200, []

    monkeypatch.setattr(main, "_require_tick_secret", lambda *a, **k: None)
    monkeypatch.setattr(main, "_hoje_br", lambda: hoje)
    monkeypatch.setattr(main, "_ips_da_casa", lambda *a, **k: set())
    monkeypatch.setattr(main, "_contar_do_dia", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_service", _rest)
    monkeypatch.setattr(_ms, "token", lambda: "fingindo")
    monkeypatch.setattr(_ms, "coletar", _coletar)
    return main.metricas_tick(request=None, **kw), gravado


def _linha(grupos, ips):
    return {"grupos_recebidos": grupos, "coleta_truncada": False,
            "ips_gente": ips, "req_total": 900}


def test_o_tick_RECOLHE_mais_dias_quando_pedido(monkeypatch):
    """🔑 Sem isto, curar a série exigiria esperar o tick passar por cima de 3
    dias por rodada — e o Cloudflare apaga o detalhe antes disso."""
    out, gravado = _tick(monkeypatch,
                         {i: _linha(800, 60) for i in range(1, 9)}, dias=7)
    dias = sorted(l["dia"] for l in gravado)
    assert len(gravado) == 7, (out, dias)
    assert dias[0] == "2026-09-15" and dias[-1] == "2026-09-21", dias


def test_CONTROLE_sem_pedir_nada_o_tick_continua_nos_3_dias(monkeypatch):
    """🧪 O padrão é o do pg_cron. Se `dias` tivesse virado obrigatório ou
    mudado o default, o cron passaria a reescrever a série inteira toda noite
    — sete vezes mais consulta ao Cloudflare por nada."""
    out, gravado = _tick(monkeypatch, {i: _linha(800, 60) for i in range(1, 9)})
    assert len(gravado) == 3, (out, [l["dia"] for l in gravado])


def test_o_tick_NAO_sobrescreve_dia_gravado_com_coleta_VAZIA(monkeypatch):
    """🚨 Fora da janela de ~7 dias o Cloudflare responde 200 com ZERO grupos:
    "não tenho mais esse dia", não "não houve movimento". Gravar isso apagaria
    a medida boa com zeros — e zero, no gráfico, tem a mesma cara de um dia
    fraco de verdade.

    🪤 É o irmão exato da lição de que evidência não sobrevive calada: a perda
    aconteceria dentro de uma rodada que responde "ok"."""
    out, gravado = _tick(monkeypatch,
                         {1: _linha(800, 60), 2: _linha(0, 0), 3: _linha(0, 0)},
                         dias=3)
    dias = [l["dia"] for l in gravado]
    assert dias == ["2026-09-21"], (
        "dia vazio foi gravado por cima do que já estava medido: %r" % dias)
    assert any("0 grupos" in f for f in out.get("motivos") or []), (
        "a rodada engoliu a recusa: quem lê a resposta não fica sabendo que "
        "dois dias não foram atualizados: %r" % out)


def test_a_BARRA_do_dia_da_REGUA_VELHA_avisa_no_hover():
    """🔑 O número continua (apagar metade do gráfico esconderia o histórico),
    mas quem passa o mouse tem que saber que aquele 63 não se compara com o
    120 de agora."""
    html = _barras([_dia("2026-09-16", 63),
                    _dia("2026-09-21", 120, coleta_truncada=False)])
    assert "63 endere" in html and "120 endere" in html, html[-400:]
    assert "teto antigo de 400" in html, (
        "a barra do dia velho não avisa que o número saiu cortado: %r" % html[-400:])
    assert html.count("teto antigo de 400") == 1, (
        "o aviso vazou para o dia medido com a régua nova: %r" % html[-400:])
    assert "opacity:.4" in html, "o dia da régua velha não ficou esmaecido"
