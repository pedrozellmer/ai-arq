# -*- coding: utf-8 -*-
"""Com a pergunta do envio aberta, o 2º clique em "Processar" não vira 2º projeto.

🩸 19/10/2026 — uma conta escolheu 1 DWG e clicou "Processar" às 15:03:28 e
às 15:03:42. O 1º clique abriu a pergunta "anexar ao projeto anterior?", um
toast NÃO modal no canto da tela, que só fecha num dos dois botões. A trava de
3 s do clique deixou o 2º passar, e ele rodou um SEGUNDO `startProcessing`:

    15:03:54  start_project → projeto A
    15:05:36  anexo_recusado (409: o arquivo já estava no projeto anterior)
    15:05:45  start_project → projeto B   (o mesmo arquivo, processado de novo)

📏 Banco + rastro de eventos (90 dias): o mesmo desenho aparece em 3 casos
confirmados (27/09, 05/10 com 30 DWG, 19/10). Em dois deles a pergunta
ANTIGA, respondida depois que o outro fluxo já tinha enviado, devolveu a tela
ao formulário, e o clique seguinte virou o 2º projeto.

🔑 `_umEnvioPorVez`: um `startProcessing` por vez, solto no `finally`. O 2º
clique avisa onde está a pergunta e deixa rastro (`processar_bloqueado`,
motivo `envio-em-curso`).

Roda o `startProcessing` REAL na bancada JS (mesma encenação de
`test_o_anexo_recusado_nao_vira_projeto_sozinho`).
"""
import json
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

from _jsbancada import fonte_html, funcao_js, motor, rodar  # noqa: E402
import test_o_anexo_recusado_nao_vira_projeto_sozinho as _anexo  # noqa: E402

_TRAVA = "    if (_envioJaEmCurso()) return false;\n"

#: a pergunta fica ABERTA: guarda quem a resolveria, sem resolver
_PERGUNTA_PENDURADA = r"""
var __pendentes = [];
window.toast.confirm = function (msg, o) {
  __dialogos.push({ msg: String(msg), ok: (o || {}).ok, cancel: (o || {}).cancel });
  return new Promise(function (res) { __pendentes.push(res); });
};
1;
"""


def _fonte_da_trava(sem_trava=False):
    site = fonte_html("dashboard.html").replace("\r\n", "\n")
    js = "\n;\n".join(funcao_js(n, "dashboard.html", site)
                      for n in ("_envioJaEmCurso", "_umEnvioPorVez"))
    if sem_trava:
        assert js.count(_TRAVA) == 1, "a âncora do controle mudou"
        js = js.replace(_TRAVA, "", 1)
    return js


def _cena(sem_trava=False):
    """1 DWG, sem pé-direito nem área: o envio PERGUNTA antes de subir."""
    _site, fonte = _anexo._fonte_das_funcoes()
    js = motor(_anexo._PRELUDIO)
    js.evaljs(fonte + "\n;1;")
    js.evaljs(_fonte_da_trava(sem_trava) + "\n;1;")
    js.evaljs("_soPdfNoEnvio = function () { return false; };"
              "var selectedFiles = [{ name: 'prancha-001.dwg', size: 1000, lastModified: 1 }];"
              "__candidatos = []; __els['project-pe-direito'].value = '';"
              "__els['project-area'].value = ''; 1;")
    js.evaljs(_PERGUNTA_PENDURADA)
    return js


def _clique_sem_esperar(js, n):
    js.evaljs("var __c%d = {pendente: true};"
              "_umEnvioPorVez(startProcessing).then(function (v) { __c%d = {ok: true, valor: v}; },"
              " function (e) { __c%d = {erro: String(e)}; }); 1;" % (n, n, n))
    js.evaljs("1;")      # drena a fila: o fluxo anda até a pergunta


def _estado(js):
    return json.loads(js.evaljs(
        "JSON.stringify({dialogos: __dialogos.length, pendentes: __pendentes.length,"
        " processos: __xhr.filter(function (x) { return x.url.indexOf('/api/process') >= 0; }).length,"
        " ev: __ev, toasts: __toasts, em_curso: !!_umEnvioPorVez.emCurso})"))


def _responde(js, i, valor):
    js.evaljs("__pendentes[%d](%s); 1;" % (i, "true" if valor else "false"))
    js.evaljs("1;")
    js.evaljs("1;")


def test_o_caso_o_segundo_clique_com_a_pergunta_aberta_nao_envia():
    js = _cena()
    _clique_sem_esperar(js, 1)
    e = _estado(js)
    assert e["dialogos"] == 1 and e["processos"] == 0, e
    assert e["em_curso"], "o 1º envio, esperando a resposta, não segurou a vez"

    r = rodar(js, "_umEnvioPorVez(startProcessing)")
    assert r.get("ok") and r.get("valor") is False, r
    e = _estado(js)
    assert e["dialogos"] == 1, "o 2º clique abriu OUTRA pergunta: %r" % e
    assert e["processos"] == 0, e
    assert ["processar_bloqueado", {"motivo": "envio-em-curso"}] in e["ev"], (
        "o 2º clique não deixou rastro: %r" % e["ev"])
    assert any(t[0] == "warn" and "pergunta" in t[1] for t in e["toasts"]), (
        "o 2º clique não disse onde está a pergunta: %r" % e["toasts"])

    _responde(js, 0, False)          # "Enviar assim mesmo"
    e = _estado(js)
    assert e["processos"] == 1, "a resposta não gerou UM envio: %r" % e
    assert not e["em_curso"], "a vez não foi devolvida depois do envio"


def test_CONTROLE_sem_a_trava_o_mesmo_arquivo_vira_dois_envios():
    js = _cena(sem_trava=True)
    _clique_sem_esperar(js, 1)
    _clique_sem_esperar(js, 2)
    e = _estado(js)
    assert e["dialogos"] == 2, "a mutação não empilhou as perguntas: %r" % e
    _responde(js, 0, False)
    _responde(js, 1, False)
    assert _estado(js)["processos"] == 2, (
        "sem a trava não saíram 2 envios — o controle não reproduz o caso")


def test_depois_de_informar_agora_o_botao_volta_a_funcionar():
    """🪤 O medo do comentário da trava de 3 s: flag que não se solta deixa o
    botão morto. "Informar agora" devolve ao formulário SEM enviar."""
    js = _cena()
    _clique_sem_esperar(js, 1)
    _responde(js, 0, True)           # "Informar agora"
    e = _estado(js)
    assert e["processos"] == 0 and not e["em_curso"], e
    _clique_sem_esperar(js, 2)
    assert _estado(js)["dialogos"] == 2, "o clique depois de 'Informar agora' foi recusado"


def test_envio_que_falha_tambem_devolve_a_vez():
    js = _cena()
    r = rodar(js, "_umEnvioPorVez(function () { return Promise.reject(new Error('rede')); })"
                  ".then(null, function () { return 'falhou'; })")
    assert r.get("valor") == "falhou", r
    assert not _estado(js)["em_curso"], "erro no envio deixou o botão morto"


def test_o_clique_usa_a_trava_nos_dois_caminhos():
    """Os dois ramos do clique (grátis e beta) chamam o envio pela trava, e o
    topo do clique confere a vez ANTES do aviso de beta."""
    site = fonte_html("dashboard.html").replace("\r\n", "\n")
    i = site.index("btnProcess.addEventListener('click', async () => {")
    j = site.index("ensureCpfBeforeCheckout()", i)
    corpo = site[i:j]
    assert corpo.count("_umEnvioPorVez(startProcessing);") == 2, (
        "um dos caminhos do clique voltou a chamar startProcessing direto")
    assert not re.search(r"(?<![\w(])startProcessing\(\);", corpo), (
        "sobrou chamada direta de startProcessing no clique")
    k_vez = corpo.index("if (_envioJaEmCurso()) return;")
    assert k_vez < corpo.index("_ultimoEnvioMs = Date.now();") < corpo.index("notify.ok("), (
        "a conferência da vez saiu do topo do clique")
