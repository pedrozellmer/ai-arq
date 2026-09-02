# -*- coding: utf-8 -*-
"""Os guardas dos planos de 02/09/2026 que vieram sem teste escrito.

🎯 "Bora, tudo" (Pedro): 18 itens do painel admin em 10 planos. Cinco planos
(navegação, cliente único, dados de projeto, movimento do site, fuso) descreveram
o guarda mas não trouxeram o código dele. Este arquivo é esse código.

🔑 Regra da casa que já me pegou TRÊS vezes só hoje: guarda que procura palavra
no fonte passa cego se a palavra estiver num comentário, e reprova o código
certo quando a função muda de lugar. Por isso aqui a maioria CHAMA a função ou
INTERCEPTA a chamada ao banco. Os poucos que leem fonte estão marcados como
fracos e dizem por quê.
"""
import io
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)

import main as _m           # noqa: E402
import metricas_site as ms  # noqa: E402


def _admin_html():
    return io.open(os.path.join(_RAIZ, "admin.html"), encoding="utf-8").read()


def _js_do_admin():
    h = _admin_html()
    return "\n".join(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", h, re.S))


class _Resp:
    def __init__(self, obj):
        self._b = json.dumps(obj).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ═══════════════════ FUSO: o dia é o de Brasília ═══════════════════════════

def test_a_coleta_pede_ao_cloudflare_o_dia_de_BRASILIA(monkeypatch):
    """🚨 O dia da série era o de Greenwich: virava às 21h de Brasília. Agora
    a consulta pede de 03:00Z a 02:59:59Z do dia seguinte, e a linha diz em
    que relógio foi contada."""
    vistas = []

    def _fake(q, timeout=25):
        vistas.append(q)
        return {"data": {"viewer": {"zones": [{"httpRequestsAdaptiveGroups": [],
                                               "httpRequests1dGroups": []}]}}}
    monkeypatch.setattr(ms, "_graphql", _fake)
    linha = ms.coletar(date(2026, 9, 1), ips_da_casa=set())
    com_janela = [q for q in vistas if "datetime_geq" in q]
    assert com_janela, "a coleta parou de pedir janela de data ao Cloudflare"
    for q in com_janela:
        assert '2026-09-01T03:00:00Z' in q, "a borda de INÍCIO do dia não é 00h de Brasília: %s" % q[:200]
        assert ('2026-09-02T02:59:59Z' in q) or ('2026-09-02T03:00:00Z' in q), (
            "a borda de FIM do dia não é 23:59 de Brasília: %s" % q[:200])
        assert 'T00:00:00Z' not in q and 'T23:59:59Z' not in q, (
            "voltou a pedir o dia de Greenwich: %s" % q[:200])
    assert linha.get("fuso") == "America/Sao_Paulo", (
        "a linha gravada não diz em que relógio o dia foi contado — o histórico "
        "UTC e o novo BRT ficariam indistinguíveis na tela")


def test_a_contagem_do_dia_corta_as_03h_UTC_que_e_meia_noite_em_brasilia(monkeypatch):
    """🚨 `_contar_do_dia` cortava em T00:00:00Z: cadastro das 22h de Brasília
    caía no dia seguinte. Medido: 24/08 dava 2 em UTC e 3 em Brasília."""
    pedidos = {}

    def _espiao(metodo, tabela, params=None, **k):
        pedidos[tabela] = params or {}
        return 200, []
    monkeypatch.setattr(_m, "_supa_rest_service", _espiao)
    for t in ("projects", "profiles"):
        _m._contar_do_dia(t, date(2026, 9, 1))
        faixa = pedidos[t].get("and", "")
        assert "created_at.gte.2026-09-01T03:00:00Z" in faixa, (
            "%s: o início do dia não é 00h de Brasília: %s" % (t, faixa))
        assert "created_at.lt.2026-09-02T03:00:00Z" in faixa, (
            "%s: o fim do dia não é 00h de Brasília do dia seguinte: %s" % (t, faixa))


def test_a_saude_da_coleta_NAO_alarma_as_22h_de_brasilia(monkeypatch):
    """🚨 Com `date.today()` (UTC no Render) entre 21h e meia-noite de Brasília
    "hoje" já era amanhã, e a caixa "A coleta PAROU" acendia TODA noite sem a
    coleta ter parado. Relógio falsificado, não a env (no Windows TZ não move
    date.today())."""
    from datetime import datetime as _dt
    monkeypatch.setattr(_m, "_agora_br_fn", lambda: _dt(2026, 9, 1, 22, 0))
    r = _m._saude_da_coleta([{"dia": "2026-08-31"}], True)
    assert r["aviso"] is None and r["atraso_dias"] == 1, (
        "alarme falso: série de ontem (estado saudável) com aviso %r" % r["aviso"])
    # 🪤 01:00 da madrugada: o cron das 06:00 ainda não rodou, então a série
    # terminar ANTEONTEM é normal. Sem olhar a hora, alarme falso toda noite.
    monkeypatch.setattr(_m, "_agora_br_fn", lambda: _dt(2026, 9, 3, 1, 0))
    r = _m._saude_da_coleta([{"dia": "2026-09-01"}], True)
    assert r["aviso"] is None, "alarme falso na madrugada, antes do cron: %r" % r["aviso"]


def test_CONTROLE_a_saude_da_coleta_AINDA_alarma_quando_parou_de_verdade(monkeypatch):
    """🧪 O outro lado: com o relógio em 03/09 e a série parada em 31/08, tem
    que gritar. Sem isto, um `return None` sempre passaria no teste de cima."""
    from datetime import datetime as _dt
    monkeypatch.setattr(_m, "_agora_br_fn", lambda: _dt(2026, 9, 3, 8, 0))
    r = _m._saude_da_coleta([{"dia": "2026-08-31"}], True)
    assert r["aviso"] and "PAROU" in r["aviso"], "coleta parada há 3 dias e nenhum aviso"
    # e às 08:00 com a série em 01/09: o tick das 06:00 de hoje faltou → grita
    r = _m._saude_da_coleta([{"dia": "2026-09-01"}], True)
    assert r["aviso"] and "PAROU" in r["aviso"], "o tick de hoje faltou e nenhum aviso"


def test_o_quando_da_revisao_inline_chega_INTEIRO_e_nao_cortado_em_UTC():
    """🪤 Lê fonte (fraco, admitido): o servidor cortava `reviewed_at[:10]`, que
    é a DATA em UTC — às 22h de Brasília já era amanhã. Agora manda o timestamp
    inteiro e a tela formata em Brasília. Um guarda de comportamento exigiria
    montar a rota inteira; este pelo menos reprova se o `[:10]` voltar."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.find("def admin_revision_feedback")
    assert i > 0, "sumiu a rota admin_revision_feedback"
    corpo = src[i:src.find("\n@app.", i + 10)]
    assert '(r.get("reviewed_at") or "")[:10]' not in corpo, (
        "o `quando` da revisão voltou a ser cortado em 10 chars — data de UTC")
    assert 'r.get("reviewed_at")' in corpo, "o `quando` da revisão sumiu da resposta"


# ═══════════════════ MOVIMENTO DO SITE ══════════════════════════════════════

def test_o_ranking_de_paginas_NAO_lista_area_logada_e_MANTEM_a_entrada():
    """🚨 O ranking "páginas que trouxeram gente" só tirava /admin: dashboard,
    login, projeto e revisão entravam no top 8 e empurravam página de entrada
    de verdade. Casa por SEGMENTO, pra não tirar /memorial-descritivo.html."""
    for p in ("/dashboard.html", "/login.html", "/projeto.html", "/revisao.html",
              "/admin.html", "/admin/x", "/cronograma.html"):
        assert _m._e_pagina_de_area_logada(p), "%s é área logada e passou" % p
    for p in ("/", "/index.html", "/faq.html", "/cadastro.html",
              "/blog/posts/memorial-descritivo.html", "/memorial-descritivo.html"):
        assert not _m._e_pagina_de_area_logada(p), "%s é entrada e foi cortada" % p


def test_a_origem_que_FALHA_vira_None_e_nao_zeros(monkeypatch):
    """🪤 A RPC falhar não é "ninguém veio". None, nunca {'pessoas': 0}."""
    chamadas = []

    def _falha(metodo, tabela, body=None, **k):
        chamadas.append((metodo, tabela, body))
        return 500, None
    monkeypatch.setattr(_m, "_supa_rest_service", _falha)
    assert _m._origem_das_visitas(30) is None
    assert chamadas and chamadas[0][1] == "rpc/admin_origem_visitas", chamadas
    assert (chamadas[0][2] or {}).get("p_dias") == 30, "a janela pedida não é 30 dias"

    def _explode(*a, **k):
        raise RuntimeError("rede")
    monkeypatch.setattr(_m, "_supa_rest_service", _explode)
    assert _m._origem_das_visitas(30) is None

    ok = {"janela_dias": 30, "pessoas": 83, "pessoas_com_origem": 77,
          "pessoas_na_home": 60, "origens": [{"origem": "google", "pessoas": 62}]}
    monkeypatch.setattr(_m, "_supa_rest_service", lambda *a, **k: (200, ok))
    assert _m._origem_das_visitas(30) == ok


def test_a_inflacao_deixa_dia_sem_medida_FORA_da_conta(monkeypatch):
    """🚨 O contador de "únicos" do Cloudflare infla de 2× a 6× e fez o Pedro
    perder a manhã duas vezes. Agora o fator é dito — e dia em que um dos dois
    lados não foi medido fica FORA e é contado como 'sem medida', nunca zero
    (zero mudaria o fator calado)."""
    serie = []
    unicos = [200, 220, 180, 250, 227, 250]   # soma 1327
    gente = [60, 70, 55, 80, 68, 70]          # soma 403
    for i in range(6):
        serie.append({"dia": "2026-08-2%d" % (i + 4), "ips_gente": gente[i],
                      "unicos_cloudflare": unicos[i], "cadastros": 1, "projetos": 1,
                      "top_paginas": [{"pagina": "/", "enderecos": 10},
                                      {"pagina": "/dashboard.html", "enderecos": 9}]})
    serie.append({"dia": "2026-08-30", "ips_gente": 50, "unicos_cloudflare": None,
                  "cadastros": 1, "projetos": 1,
                  "top_paginas": [{"pagina": "/faq.html", "enderecos": 3}]})

    def _fake(metodo, tabela, params=None, body=None, **k):
        if tabela == "metricas_diarias":
            return 200, serie
        if tabela == "rpc/admin_origem_visitas":
            return 200, {"janela_dias": 30, "pessoas": 1, "pessoas_com_origem": 1,
                         "pessoas_na_home": 1, "origens": []}
        return 404, None
    monkeypatch.setattr(_m, "_supa_rest_service", _fake)
    monkeypatch.setattr(_m, "_require_admin", lambda *a, **k: {"email": "x"})
    r = _m.admin_metricas(request=object(), dias=45)
    infl = r["inflacao_7d"]
    assert infl["dias_medidos"] == 6 and infl["dias_sem_medida"] == 1, infl
    assert infl["unicos_cloudflare"] == 1327 and infl["ips_gente"] == 403, infl
    assert infl["fator"] == 3.3, infl
    paginas = [p["pagina"] for p in r["top_paginas_7d"]]
    assert "/" in paginas and "/faq.html" in paginas, paginas
    assert "/dashboard.html" not in paginas, "área logada voltou pro ranking"
    assert r["origem_30d"]["pessoas"] == 1


def test_CONTROLE_sem_nenhum_dia_medido_o_fator_e_None(monkeypatch):
    serie = [{"dia": "2026-08-3%d" % i, "ips_gente": 10, "unicos_cloudflare": None,
              "top_paginas": []} for i in range(2)]
    monkeypatch.setattr(_m, "_supa_rest_service",
                        lambda m, t, **k: (200, serie) if t == "metricas_diarias" else (500, None))
    monkeypatch.setattr(_m, "_require_admin", lambda *a, **k: {"email": "x"})
    r = _m.admin_metricas(request=object(), dias=45)
    assert r["inflacao_7d"]["fator"] is None and r["inflacao_7d"]["dias_medidos"] == 0
    assert r["origem_30d"] is None


def test_a_tela_tem_os_campos_novos_do_movimento_e_alguem_preenche():
    """🪤 Lê fonte (fraco, admitido): campo no HTML sem ninguém preencher é
    número que nunca aparece — que era a doença original."""
    h = _admin_html()
    js = _js_do_admin()
    for campo in ("mov-origem", "mov-inflacao"):
        assert 'id="%s"' % campo in h, "#%s sumiu do HTML" % campo
        assert "'%s'" % campo in js, "#%s existe e ninguém preenche" % campo


# ═══════════════════ PROJETOS: formato, revisão, retorno ════════════════════

def test_por_formato_NAO_inventa_zero_quando_nao_tem_projeto_atras():
    r = _m.frase_por_formato({"formato": "DXF", "total": 21, "mediu": 16})
    assert r == {"formato": "DXF", "mediu": 16, "finalizados": 21, "pct": 76}, r
    assert _m.frase_por_formato({"formato": "PDF", "total": 0, "mediu": 0}) is None, (
        "0 de 0 virou 0% — é 'sem medição', não zero")
    assert _m.frase_por_formato({"formato": "PDF", "total": 5}) is None, (
        "RPC antiga sem o campo `mediu` virou número")
    assert _m.frase_por_formato(None) is None


def test_retorno_separa_as_tres_perguntas_e_chave_ausente_vira_None():
    """🔑 "2+ projetos" (54%) é USO no mesmo dia, não retorno. As três perguntas
    saem com nome, e RPC antiga (sem a chave nova) dá None, nunca {'n': 0}."""
    R = {"clientes": 74, "voltaram_outro_dia": 8, "voltaram_outra_sem": 5,
         "dois_ou_mais_projetos": 40, "so_um_projeto": 34}
    f = _m.faixas_de_retorno(R)
    assert f["voltou_outro_dia"] == {"n": 8, "pct": 11}, f
    assert f["voltou_outra_semana"] == {"n": 5, "pct": 7}, f
    assert f["dois_ou_mais_projetos"] == {"n": 40, "pct": 54}, f
    antiga = {"clientes": 74, "voltaram_outra_sem": 5, "so_um_projeto": 34}
    f2 = _m.faixas_de_retorno(antiga)
    assert f2["voltou_outro_dia"] is None, (
        "chave que a RPC não mandou virou zero — 'ninguém voltou' é afirmação")
    assert _m.faixas_de_retorno({"clientes": 0}) is None


def test_era_zerada_le_o_ANTES_da_revisao_e_nao_a_quantidade_ja_corrigida():
    """🩸 A versão antiga lia `project_items.quantity`, que a revisão JÁ tinha
    sobrescrito — a tela subestimava 3,5× o achado que mais importa (preencher
    linha zerada)."""
    ez = _m.era_linha_zerada
    assert ez({"edits": {"quantity": 135, "_antes": {"quantity": 0}}}, {"quantity": 135}) is True
    assert ez({"edits": {"quantity": 135, "_antes": {"quantity": 42.72}}}, {"quantity": 135}) is False
    assert ez({"edits": {"quantity": 135}}, {"quantity": 0}) is True, "sem _antes cai na quantidade atual"
    assert ez({"edits": {"quantity": 135}}, {}) is None, "sem nada é 'não sei', não False"


def test_o_endpoint_qualidade_semanal_NAO_quebra_com_a_RPC_antiga(monkeypatch):
    """🪤 Ordem de deploy: se o backend subir antes da RPC nova, a resposta vem
    sem `por_formato_90d`. O endpoint tem que continuar respondendo."""
    import urllib.request as _ur
    antiga = {"semanas": [], "por_formato": [], "retencao": {"clientes": 1}, "gerado_em": "x"}
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=20: _Resp(antiga))
    monkeypatch.setattr(_m, "_require_admin", lambda *a, **k: {"email": "x"})
    r = _m.admin_qualidade_semanal(request=object())
    assert isinstance(r, dict) and "semanas" in r
    nova = dict(antiga, por_formato_90d=[{"formato": "DXF", "total": 21, "mediu": 16, "concluiu": 20, "erro": 1}],
                janela_formato_90d={"dias": 90})
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=20: _Resp(nova))
    r2 = _m.admin_qualidade_semanal(request=object())
    assert isinstance(r2, dict) and r2.get("por_formato_90d"), r2.keys()


def test_o_painel_tem_onde_pintar_formato_e_retorno():
    """🪤 Lê fonte (fraco, admitido): o lugar existe e a função que pinta existe."""
    h = _admin_html()
    i = h.find('id="stat-success-evo"')
    assert i > 0 and 'id="stat-success-formato"' in h[i - 1500:i + 1500], (
        "o cartão Entrega perdeu o lugar da linha por formato")
    assert 'panel-clients-volta' in h and "function pintarRetornoNoQuadroDeClientes" in h
    assert "function pintarFormato90d" in h


# ═══════════════════ CLIENTE ÚNICO ══════════════════════════════════════════

def test_o_backend_NAO_manda_lista_de_emails_pro_funil(monkeypatch):
    """🔑 A regra "quem é cliente" mora no banco (view projetos_de_cliente). O
    backend tinha uma lista de 4 e-mails na mão — a terceira definição."""
    chamadas = []

    def _espiao(metodo, tabela, body=None, **k):
        chamadas.append((metodo, tabela, body))
        return 200, []
    monkeypatch.setattr(_m, "_supa_rest_service", _espiao)
    monkeypatch.setattr(_m, "_require_admin", lambda *a, **k: {"email": "x"})
    fn = getattr(_m, "admin_funil_revisao", None)
    assert fn is not None, "sumiu a rota do funil"
    try:
        fn(request=object())
    except TypeError:
        fn(object())
    funil = [c for c in chamadas if c[1] == "rpc/funil_revisao"]
    assert funil, "o funil parou de chamar a RPC: %r" % chamadas
    corpo = json.dumps(funil[0][2] or {})
    assert "@" not in corpo, "o backend voltou a mandar e-mails da casa na mão: %s" % corpo


def test_o_painel_le_a_VIEW_e_nao_tem_lista_propria_de_contas():
    """🪤 Lê fonte (fraco, admitido — o plano pedia AST; o texto basta pra
    pegar a regressão óbvia)."""
    js = _js_do_admin()
    n_view = len(re.findall(r"\.from\('projetos_de_cliente'\)", js))
    assert n_view >= 4, "o dashboard parou de ler a view projetos_de_cliente (%d usos)" % n_view
    assert "_CONTAS_TESTE" not in js, "voltou a lista própria de contas de teste no JS"
    assert "conta_da_casa" in js, "a retenção não lê mais o campo conta_da_casa da RPC"
    assert "conta(s) de teste fora" in js, "o painel parou de DIZER que tirou contas"


# ═══════════════════ NAVEGAÇÃO ══════════════════════════════════════════════

def test_toda_aba_tem_botao_no_menu_e_todo_botao_tem_aba():
    """🚨 Pagamentos e Insights existiam como div e não tinham botão — trabalho
    pronto invisível (Insights) e HTML morto (Pagamentos)."""
    h = _admin_html()
    botoes = set(re.findall(r'data-tab="([a-z_-]+)"', h))
    abas = set(re.findall(r'id="tab-([a-z_-]+)"[^>]*class="tab-content', h))
    assert botoes and abas
    assert abas - botoes == set(), "aba sem botão no menu: %s" % sorted(abas - botoes)
    assert botoes - abas == set(), "botão sem aba: %s" % sorted(botoes - abas)
    assert "insights" in botoes, "a aba de revisões do cliente voltou a ficar sem botão"


def test_o_cartao_do_dashboard_carrega_a_lista_UMA_vez():
    """🪤 Lê fonte (fraco, admitido — não há Chrome no CI). irParaProjetos
    chamava switchTab (que carrega) e depois setProjectsFilter (que carregava
    de novo). Agora marca o filtro SEM carregar e deixa a troca de aba carregar."""
    js = _js_do_admin()
    i = js.find("function irParaProjetos()")
    corpo = js[i:i + 300]
    assert "setProjectsFilter('tudo', true)" in corpo, "irParaProjetos voltou a carregar duas vezes"
    j = js.find("function setProjectsFilter(")
    assert "if (!soMarcar) loadProjects();" in js[j:j + 900], (
        "setProjectsFilter voltou a carregar sempre — o clique no cartão carrega 2×")


def test_a_bolinha_de_mensagens_e_contada_no_boot_sem_abrir_a_aba():
    """🚨 O badge de mensagens só era contado quando a aba Mensagens abria."""
    js = _js_do_admin()
    i = js.find("async function carregarBadgeMensagens()")
    assert i > 0, "sumiu carregarBadgeMensagens"
    corpo = js[i:i + 800]
    assert "count: 'exact'" in corpo and "head: true" in corpo, "a contagem virou lista inteira"
    assert ".eq('status', 'new')" in corpo, "conta tudo em vez de só as sem resposta"
    assert len(re.findall(r"carregarBadgeMensagens\(\)", js)) >= 2, (
        "carregarBadgeMensagens existe e ninguém chama no boot")


# ═══════════════════ O BUG QUE NENHUMA AUDITORIA VIU ════════════════════════

def test_renderOps_NAO_usa_variavel_de_outra_funcao():
    """🩸 `return inlineHtml + html` dentro de renderOps — `inlineHtml` só existe
    em renderRevisionFeedback. ReferenceError: o bloco inteiro de falhas/avisos/
    PDFs da aba Motor não renderizava, e ninguém viu porque ninguém EXECUTAVA a
    função. Recorte da função inteira, não janela fixa (renderOps cresce)."""
    js = _js_do_admin()
    i = js.find("function renderOps(d){")
    assert i > 0, "sumiu renderOps"
    fim = js.find(chr(10) + "}", i)
    # 🪤 A 1ª versão deste guarda reprovou o CÓDIGO CERTO: o comentário que
    # explica o bug cita `inlineHtml`, e o guarda leu o comentário. Quarta vez
    # hoje. Comentário fora; só o que executa conta.
    corpo = chr(10).join(l for l in js[i:fim].split(chr(10)) if not l.strip().startswith("//"))
    assert "inlineHtml" not in corpo, (
        "renderOps voltou a usar `inlineHtml`, que é de outra função — "
        "ReferenceError e a aba Motor mostra 'Não consegui carregar'")
    assert "return html;" in corpo


def test_o_divisor_do_custo_tira_FILHOTE_do_lado_do_cliente(monkeypatch):
    """🪤 Filhote (reprocesso liberado) é o MESMO projeto contado de novo: 3 dos
    57 (medido). Só do lado do cliente — avaliação é 100% filhote por natureza."""
    pedidos = []
    monkeypatch.setattr(_m, "_supa_rest_service",
                        lambda m, t, params=None, **k: (pedidos.append(dict(params or {})), (200, []))[1])
    _m._projetos_para_custo_30d()
    cli = [p for p in pedidos if p.get("is_eval") == "not.is.true"]
    ava = [p for p in pedidos if p.get("is_eval") == "is.true"]
    assert cli and ava, pedidos
    assert cli[0].get("parent_job_id") == "is.null", "filhote voltou a contar no divisor"
    assert "parent_job_id" not in ava[0], "a contagem de avaliacoes perdeu os filhotes (que sao todas)"
