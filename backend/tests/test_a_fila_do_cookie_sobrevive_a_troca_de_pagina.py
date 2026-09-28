# -*- coding: utf-8 -*-
"""A fila de antes do "sim" ao cookie sobrevive à troca de página — e só sai com o "sim".

🔑 28/09/2026 — Pedro (decisões da auditoria de telemetria): "guardar no
sessionStorage". A fila vivia em memória e morria na troca de página: quem
aceitava o cookie já no cadastro ou no painel perdia a home e o cadastro aberto
(o signup_done faltava em 1 de cada 3 fichas, 30/08–27/09). Agora ela vive no
sessionStorage DA ABA, nada é enviado sem o "sim", recusou = apagada, e cada
item leva a PÁGINA onde aconteceu.

Os testes RODAM o código do aiarq-utils.js no dukpy, com duas "páginas"
dividindo o mesmo sessionStorage (é o que a aba faz).
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _jsbancada import _do_marcador_ate_fechar, fonte_html, funcao_js, motor, rodar  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _trecho_track():
    src = fonte_html("aiarq-utils.js")
    marca = "window.trackEvent = function (event, meta, _paginaDaFila) "
    i = src.index(marca)
    return "window.trackEvent = function (event, meta, _paginaDaFila) " + \
        _do_marcador_ate_fechar(src, i + len(marca), "trackEvent")


def _pagina(caminho, sessao, consentimento=None):
    """Uma página nova da MESMA aba: mesmo sessionStorage (`sessao`), fila relida."""
    js = motor(
        "var __ss = %s, __ls = %s, __envios = [];"
        "var sessionStorage = { getItem: function (k) { return k in __ss ? __ss[k] : null; },"
        "  setItem: function (k, v) { __ss[k] = String(v); }, removeItem: function (k) { delete __ss[k]; } };"
        "var localStorage = { getItem: function (k) { return k in __ls ? __ls[k] : null; },"
        "  setItem: function (k, v) { __ls[k] = String(v); } };"
        "var location = { pathname: %s };"
        "var API_BASE = 'https://api.teste';"
        "var window = { addEventListener: function () {} };"
        "function fetch(url, o) { __envios.push(JSON.parse(o.body)); return Promise.resolve({}); }"
        "var _FILA_KEY = 'aiarq_fila_pre_sim'; null;"
        % (json.dumps(sessao), json.dumps({"aiarq_cookie_consent": json.dumps(consentimento)} if consentimento else {}),
           json.dumps(caminho)))
    for f in ("_filaLer", "_filaGravar", "_filaDescarrega"):
        js.evaljs(funcao_js(f, "aiarq-utils.js"))
    js.evaljs("var _trackFila = _filaLer(); %s; null;" % _trecho_track())
    return js


def _ler(js, expr):
    return json.loads(js.evaljs("JSON.stringify(%s)" % expr))


def test_o_evento_da_home_sai_quando_a_pessoa_aceita_no_cadastro():
    # página 1: a home, sem resposta ao banner
    home = _pagina("/", {})
    rodar(home, "(function(){ window.trackEvent('view_landing', {}); return 1; })()")
    sessao = _ler(home, "__ss")
    assert _ler(home, "__envios") == [], "enviou antes do sim"
    # página 2: o cadastro, na mesma aba — aceita
    cad = _pagina("/cadastro.html", sessao)
    rodar(cad, "(function(){ window.trackEvent('view_cadastro', {}); return 1; })()")
    cad.evaljs("__ls['aiarq_cookie_consent'] = JSON.stringify({analytics: true}); null;")
    rodar(cad, "(function(){ _filaDescarrega(true); return 1; })()")
    envios = _ler(cad, "__envios")
    assert [(e["event"], e["path"]) for e in envios] == [("view_landing", "/"), ("view_cadastro", "/cadastro.html")], envios
    assert "aiarq_fila_pre_sim" not in _ler(cad, "__ss"), "a fila ficou guardada depois de enviada"


def test_CONTROLE_sem_a_fila_guardada_a_home_se_perdia():
    """O de antes: a página nova começava com a fila VAZIA (memória)."""
    cad = _pagina("/cadastro.html", {})           # nada guardado da home
    cad.evaljs("__ls['aiarq_cookie_consent'] = JSON.stringify({analytics: true}); null;")
    rodar(cad, "(function(){ _filaDescarrega(true); return 1; })()")
    assert _ler(cad, "__envios") == []


def test_recusou_apaga_a_fila_e_nao_envia_nada():
    home = _pagina("/", {})
    rodar(home, "(function(){ window.trackEvent('view_landing', {}); return 1; })()")
    cad = _pagina("/cadastro.html", _ler(home, "__ss"))
    rodar(cad, "(function(){ _filaDescarrega(false); return 1; })()")
    assert _ler(cad, "__envios") == [] and "aiarq_fila_pre_sim" not in _ler(cad, "__ss")


def test_a_fila_nao_passa_de_20():
    home = _pagina("/", {})
    rodar(home, "(function(){ for (var i = 0; i < 30; i++) window.trackEvent('e' + i, {}); return 1; })()")
    assert len(json.loads(_ler(home, "__ss")["aiarq_fila_pre_sim"])) == 20


def test_com_consentimento_ja_dado_nao_guarda_nada_na_fila():
    home = _pagina("/", {}, consentimento={"analytics": True})
    rodar(home, "(function(){ window.trackEvent('view_landing', {}); return 1; })()")
    assert "aiarq_fila_pre_sim" not in _ler(home, "__ss")
    assert [e["path"] for e in _ler(home, "__envios")] == ["/"]


def test_a_politica_conta_o_que_o_codigo_faz():
    """A Política de Privacidade descreve a fila no sessionStorage, o beacon do
    Cloudflare (sem cookie), o cookie de segurança e a origem que vai pra conta."""
    pol = io.open(os.path.join(_RAIZ, "privacidade.html"), encoding="utf-8").read()
    for trecho in ("sessionStorage", "Cloudflare Web Analytics", "cf_clearance",
                   "origem da sua primeira visita", "não usa cookie nem localStorage"):
        assert trecho in pol, trecho
