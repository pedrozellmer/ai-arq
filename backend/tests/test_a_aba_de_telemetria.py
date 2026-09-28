# -*- coding: utf-8 -*-
"""A telemetria tem aba própria; o dashboard fica só com o resumo.

📊 28/09/2026 — Pedro: "vale uma aba pra telemetria no admin, deixa só um resumo no dash" e "tudo numa aba só".
O dashboard respondia duas perguntas na mesma tela ("está tudo normal?" e "de onde vem e o que faz a visita?"),
e as três réguas de origem (quem aceitou o cookie, o Cloudflare, o declarado no cadastro) ficavam espalhadas.
Agora: dashboard = farol, site no ar, cadastros e projetos (7d), o alarme de coleta desligada e o link; a aba
Telemetria = tráfego, as três origens juntas e o uso do produto (a antiga aba Atividade).

Os testes de comportamento RODAM o `switchTab` e o `_abaDoHash` do admin.html no dukpy.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _jsbancada import fonte_html, funcao_js, motor  # noqa: E402

_ADMIN = "admin.html"

_RESUMO = ("mov-farol", "mov-frase", "mov-saude", "mov-cadastros", "mov-projetos", "mov-alerta")
_MUDARAM = ("mov-barras", "mov-inflacao", "mov-funil", "mov-paginas", "mov-origem", "mov-origem-nota",
            "mov-referencia", "mov-referencia-nota", "origem-box")
_ATIVIDADE = ("act-auto-refresh", "act-live-dot", "act-days", "act-cards", "act-funnel-body", "act-by-event",
              "act-by-user", "act-recent")


def _aba(html, nome):
    """O bloco da aba: do `<div id="tab-<nome>"` até a próxima aba."""
    i = html.index('<div id="tab-%s"' % nome)
    j = html.find('<div id="tab-', i + 10)
    return html[i:j if j > 0 else len(html)]


def _fora_do_lugar(html):
    """Ids que estão na aba errada (ou sumiram). Vazio = o layout está como o Pedro pediu."""
    dash, tele = _aba(html, "dashboard"), _aba(html, "telemetria")
    ruins = []
    for i in _RESUMO:
        if ('id="%s"' % i) not in dash:
            ruins.append("resumo sem #%s" % i)
    for i in _MUDARAM + _ATIVIDADE:
        if ('id="%s"' % i) in dash:
            ruins.append("#%s ainda no dashboard" % i)
        if ('id="%s"' % i) not in tele:
            ruins.append("#%s fora da Telemetria" % i)
    return ruins


def test_o_dashboard_fica_so_com_o_resumo_e_a_telemetria_com_o_resto():
    html = fonte_html(_ADMIN)
    assert _fora_do_lugar(html) == []
    assert "switchTab('telemetria')" in _aba(html, "dashboard"), "o resumo perdeu o link pra aba"


def test_CONTROLE_barras_de_volta_no_dashboard_reprova():
    html = fonte_html(_ADMIN)
    i = html.index('<div id="tab-dashboard"')
    fim = html.index(">", i) + 1
    ruim = html[:fim] + '<div id="mov-barras"></div>' + html[fim:]
    assert "#mov-barras ainda no dashboard" in _fora_do_lugar(ruim)


def test_a_telemetria_tem_as_tres_secoes_e_nenhum_link_de_ancora():
    tele = _aba(fonte_html(_ADMIN), "telemetria")
    for sec in ("tele-trafego", "tele-origem", "tele-produto"):
        assert ('id="%s"' % sec) in tele and ("irParaSecaoDaTelemetria('%s')" % sec) in tele, sec
    # 🪤 a aba mora no hash: um <a href="#tele-origem"> mandaria o painel pro dashboard
    assert 'href="#' not in tele


def test_o_menu_leva_pra_telemetria_e_a_atividade_nao_tem_mais_aba():
    html = fonte_html(_ADMIN)
    assert 'data-tab="telemetria"' in html and "<span>Telemetria</span>" in html
    assert 'data-tab="atividade"' not in html and 'id="tab-atividade"' not in html


# ─── comportamento: o switchTab e o _abaDoHash de verdade ───────────────────────────────────
def _painel(hash_inicial="", switch_src=None):
    js = motor(
        "var __chamou = [], __visivel = [], __hash = %s;"
        "var location = { get hash() { return __hash; }, set hash(v) { __hash = '#' + v; } };"
        "function _el(id) { return { id: id, classList: {"
        "  add: function (c) { if (c === 'hidden') __visivel = __visivel.filter(function (x) { return x !== id; }); },"
        "  remove: function (c) { if (c === 'hidden') __visivel.push(id); } } }; }"
        "var __abas = ['tab-dashboard', 'tab-telemetria', 'tab-projetos'];"
        "var document = {"
        "  getElementById: function (id) { return __abas.indexOf(id) >= 0 ? _el(id) : null; },"
        "  querySelectorAll: function () { return []; },"
        "  querySelector: function () { return null; } };"
        "function closeSidebar() {}"
        % json.dumps(hash_inicial))
    for f in ("loadDashboardStats", "loadOrigem", "loadFilhotes", "carregarBadgeMensagens", "loadActivity",
              "carregarMovimentoDoSite", "loadUsers", "_filtroPadraoAoEntrar", "loadProjects",
              "loadCalibrationFactors", "loadAgentData", "loadNPSData", "loadEmailCatalog", "loadInsights",
              "loadMessages", "loadNewsletterPreview", "loadNewsletterScheduled", "loadInstagramPosts",
              "loadLinkedinPosts", "loadCalendario", "loadOndeErra", "loadQualidadeSemanal", "loadMotorHealth",
              "loadOps", "loadFunilRevisao", "loadVozCliente", "loadRevisionFeedback", "loadCosts"):
        js.evaljs("function %s() { __chamou.push(%s); }" % (f, json.dumps(f)))
    js.evaljs((switch_src or funcao_js("switchTab", _ADMIN)) + "; null;")
    js.evaljs(funcao_js("_abaDoHash", _ADMIN) + "; null;")
    return js


def _ler(js, expr):
    return json.loads(js.evaljs("JSON.stringify(%s)" % expr))


def test_abrir_a_telemetria_carrega_trafego_origem_e_uso_do_produto():
    js = _painel("#telemetria")
    js.evaljs("switchTab('telemetria', true); null;")
    assert set(_ler(js, "__chamou")) == {"carregarMovimentoDoSite", "loadOrigem", "loadActivity"}
    assert _ler(js, "__visivel") == ["tab-telemetria"]


def test_o_dashboard_nao_carrega_mais_a_origem():
    js = _painel("#dashboard")
    js.evaljs("switchTab('dashboard', true); null;")
    chamou = _ler(js, "__chamou")
    assert "loadDashboardStats" in chamou and "loadOrigem" not in chamou, chamou


def test_link_e_favorito_velhos_da_atividade_abrem_a_telemetria():
    js = _painel("#atividade")
    assert js.evaljs("_abaDoHash()") == "telemetria"       # favorito / recarregar a página
    js.evaljs("switchTab('atividade'); null;")              # clique vindo de código velho
    assert js.evaljs("__hash") == "#telemetria"
    js.evaljs("switchTab('atividade', true); null;")
    assert _ler(js, "__visivel") == ["tab-telemetria"] and "loadActivity" in _ler(js, "__chamou")


def test_CONTROLE_sem_o_apelido_o_favorito_velho_caia_no_dashboard():
    src = funcao_js("_abaDoHash", _ADMIN)
    apelido = "  if (h === 'atividade') h = 'telemetria';"
    assert apelido in src
    js = _painel("#atividade")
    js.evaljs(src.replace(apelido, "") + "; null;")
    assert js.evaljs("_abaDoHash()") == "dashboard"


def test_CONTROLE_sem_o_ramo_da_telemetria_a_aba_abre_vazia():
    src = funcao_js("switchTab", _ADMIN)
    ramo = "  if (tabName === 'telemetria') { carregarMovimentoDoSite(); loadOrigem(); loadActivity(); }"
    assert ramo in src
    js = _painel("#telemetria", switch_src=src.replace(ramo, ""))
    js.evaljs("switchTab('telemetria', true); null;")
    assert _ler(js, "__chamou") == []


def test_o_boot_do_dashboard_nao_chama_a_origem():
    html = fonte_html(_ADMIN)
    i = html.index("(async function init()")
    boot = html[i:html.index("})();", i)]
    ramo = boot[boot.index("if (aba === 'dashboard')"):boot.index("} else {")]
    assert "loadDashboardStats()" in ramo and not re.search(r"loadOrigem\(\)", ramo), ramo


def test_o_ao_vivo_da_atividade_olha_a_aba_nova():
    """O recarregamento de 12 s só roda com a aba visível — e a aba agora é a Telemetria."""
    html = fonte_html(_ADMIN)
    corpo = funcao_js("startActivityAutoRefresh", _ADMIN)
    assert "getElementById('tab-telemetria')" in corpo and "tab-atividade" not in corpo
    assert "tab-atividade" not in html
