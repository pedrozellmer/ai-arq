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

# 28/09 (Pedro): "deixa o gráfico de clientes por semana também no dash" → dash-cadastros-semana
_RESUMO = ("mov-farol", "mov-frase", "mov-saude", "mov-cadastros", "mov-projetos", "mov-alerta",
           "dash-cadastros-semana", "dash-clientes-voltaram")   # 04/10: quem voltou também
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
    for f in ("loadDashboardStats", "loadCadastrosPorSemana", "loadClientesQueVoltaram", "loadOrigem", "loadFilhotes", "carregarBadgeMensagens", "loadActivity",
              "loadBuscaOrganica",
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
    # 04/10: + a busca orgânica (Search Console e Bing)
    assert set(_ler(js, "__chamou")) == {"carregarMovimentoDoSite", "loadOrigem", "loadBuscaOrganica", "loadActivity"}
    assert _ler(js, "__visivel") == ["tab-telemetria"]


def test_o_dashboard_nao_carrega_mais_a_origem():
    js = _painel("#dashboard")
    js.evaljs("switchTab('dashboard', true); null;")
    chamou = _ler(js, "__chamou")
    assert "loadDashboardStats" in chamou and "loadOrigem" not in chamou, chamou
    assert "loadCadastrosPorSemana" in chamou, "o gráfico de cadastros por semana saiu do dash"
    assert "loadClientesQueVoltaram" in chamou, "o card de quem voltou saiu do dash"


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
    ramo = "  if (tabName === 'telemetria') { carregarMovimentoDoSite(); loadOrigem(); loadBuscaOrganica(); loadActivity(); }"
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
    assert "loadCadastrosPorSemana()" in ramo and "loadClientesQueVoltaram()" in ramo, ramo


# ─── o gráfico de cadastros por semana (no dash) desenha de verdade ────────────────────────────
def _grafico(users, agora):
    js = motor()
    js.evaljs(funcao_js("htmlCadastrosPorSemana", _ADMIN) + "; null;")
    return js.evaljs("htmlCadastrosPorSemana(%s, Date.parse(%s))" % (json.dumps(users), json.dumps(agora)))


def test_o_grafico_de_cadastros_por_semana_conta_semana_fixa_e_tira_a_em_curso_da_media():
    # datas sem fuso = hora local (vale igual no Windows e no CI); meio-dia, longe da virada
    users = [{"auth_created_at": d} for d in ("2026-09-15T12:00:00", "2026-09-16T12:00:00",
                                               "2026-09-22T12:00:00", "2026-09-29T12:00:00")]
    h = _grafico(users, "2026-09-30T12:00:00")                 # quarta-feira
    assert "Cadastros por semana" in h
    assert "4 cadastros em 3 semanas, desde 14/09" in h, h[:600]
    assert "m&eacute;dia <b>1.5</b>/semana nas 2 semanas fechadas" in h     # (2 + 1) / 2, sem a em curso
    assert "(1 em 3 de 7 dias)" in h and "em curso" in h


def test_com_mais_de_26_semanas_o_numero_continua_em_cima_de_cada_barra():
    """🩸 06/10/2026 — print do Pedro: os números sumiram. O desenho tinha TODAS as semanas desde o 1º cadastro
    e o número só sai com até 26 colunas; a 27ª começou em 05/10. Agora o desenho fica nas últimas 26 e o
    texto de cima segue contando a história inteira."""
    import datetime as _dt
    agora = _dt.datetime(2026, 10, 7, 12, 0, 0)                          # quarta-feira
    users = []
    for semana in range(30):                                            # 30 semanas, de 1 a 3 cadastros cada
        d = agora - _dt.timedelta(weeks=semana)
        users += [{"auth_created_at": d.strftime("%Y-%m-%dT12:00:00")}] * (1 + semana % 3)
    h = _grafico(users, agora.strftime("%Y-%m-%dT12:00:00"))
    assert h.count("cadastros em 30 semanas") == 1, "o texto de cima tem que contar a história inteira"
    assert "o gr&aacute;fico mostra as &uacute;ltimas 26" in h
    barras = h.count('cadastro">') + h.count('cadastros">')            # o title de cada coluna termina assim
    numeros = h.count("font-variant-numeric:tabular-nums;color:")     # só o número em cima da barra usa
    assert barras == 26 and numeros == 26, (barras, numeros)


def test_CONTROLE_o_grafico_mudaria_com_outra_contagem():
    users = [{"auth_created_at": "2026-09-15T12:00:00"}, {"auth_created_at": "2026-09-29T12:00:00"}]
    h = _grafico(users, "2026-09-30T12:00:00")
    assert "4 cadastros" not in h and "2 cadastros em 3 semanas" in h


def test_o_grafico_saiu_da_origem_e_nao_aparece_duas_vezes():
    html = fonte_html(_ADMIN)
    assert "Cadastros por semana" not in funcao_js("loadOrigem", _ADMIN)
    assert html.count('<h3 class="font-semibold text-gray-900">Cadastros por semana</h3>') == 1


def test_o_ao_vivo_da_atividade_olha_a_aba_nova():
    """O recarregamento de 12 s só roda com a aba visível — e a aba agora é a Telemetria."""
    html = fonte_html(_ADMIN)
    corpo = funcao_js("startActivityAutoRefresh", _ADMIN)
    assert "getElementById('tab-telemetria')" in corpo and "tab-atividade" not in corpo
    assert "tab-atividade" not in html


# ─── "Clientes que voltaram" (de volta no dash em 04/10) desenha de verdade ────────────────────
def _voltaram(users):
    js = motor("function esc(s) { return String(s == null ? '' : s); }")
    js.evaljs(funcao_js("htmlClientesQueVoltaram", _ADMIN) + "; null;")
    return js.evaljs("htmlClientesQueVoltaram(%s)" % json.dumps(users))


_CLIENTES = [
    {"full_name": "Pessoa Exemplo A", "num_projects": 3, "dias_com_projeto": 2,
     "primeiro_projeto": "2026-09-01T12:00:00", "ultimo_projeto": "2026-09-10T12:00:00"},
    {"full_name": "Pessoa Exemplo B", "num_projects": 2, "dias_com_projeto": 1},
    {"full_name": "Pessoa Exemplo C", "num_projects": 1, "dias_com_projeto": 1},
    {"full_name": "Conta da Casa", "num_projects": 5, "dias_com_projeto": 4, "conta_da_casa": True,
     "primeiro_projeto": "2026-08-01T12:00:00", "ultimo_projeto": "2026-09-20T12:00:00"},
]


def test_quem_voltou_e_outro_dia_e_a_casa_fica_fora():
    h = _voltaram(_CLIENTES)
    assert "Clientes que voltaram" in h
    assert "voltaram (33.3% de 3 que usaram)" in h, h[:900]        # só A voltou; B tem 2 projetos no MESMO dia
    assert "Pessoa Exemplo A" in h and "9 dias depois" in h
    assert "Conta da Casa" not in h and "1 conta(s) de teste fora" in h


def test_CONTROLE_sem_tirar_a_casa_a_retencao_infla():
    sem_marca = [dict(u, conta_da_casa=False) for u in _CLIENTES]
    assert "voltaram (50% de 4 que usaram)" in _voltaram(sem_marca)


def test_quem_voltou_saiu_da_origem_e_nao_aparece_duas_vezes():
    html = fonte_html(_ADMIN)
    assert "Clientes que voltaram" not in funcao_js("loadOrigem", _ADMIN)
    assert html.count('<h3 class="font-semibold text-gray-900">Clientes que voltaram</h3>') == 1
