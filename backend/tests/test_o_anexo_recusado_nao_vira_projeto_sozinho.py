# -*- coding: utf-8 -*-
"""Anexo recusado pelo servidor não pode virar projeto novo sem o clique da pessoa.

🩸 22/09/2026 — jobs ee801b82 → f8d8e6d8. Cliente de 1 dia. Ontem ela mandou
7 PDFs de estrutura (ee801b82). Hoje escolheu os MESMOS 7 no painel; a tela
reconheceu os nomes e sugeriu anexar ao projeto de ontem, e ela clicou
"Anexar ao projeto". O servidor recusou com 409 — mesmo sha256, a barreira de
16/09 — e um recado dizendo por quê. O `startProcessing` só olhava
`status === 'ok'`: jogou o recado fora, mostrou "Não consegui anexar… vou
criar um projeto novo" e CRIOU o f8d8e6d8 sozinho, 0,33 s depois, no tipo
padrão do formulário (arquitetura — o de ontem era estrutura). Saíram um 2º
projeto idêntico, no tipo errado, e um 2º e-mail de "sem quantidade". NPS 2.

📏 Alcance medido (error_log × projects do mesmo user_id, 2 min): as 2 recusas
por arquivo repetido que passaram pelo painel (a barreira nasceu em 16/09)
viraram projeto novo em 2,2 s e 5,1 s. Em 90 dias, PELO MENOS 4 anexos por esse
caminho deram certo — o `usage_events` só grava quem aceitou a telemetria no
banner (113 de 207 projetos de cliente tinham o `start_project` ao lado), então
4 é piso e o "2 de 6" que sai daí é teto. 409 de outro motivo, 5xx e rede não
deixavam rastro nenhum; o `anexo_recusado` passa a mostrar uma AMOSTRA deles.

O que este arquivo cobra, RODANDO a tela no motor JS (nunca procurando palavra):
  · o `startProcessing` real, com a sugestão real (`_acharProjetoIrmao`,
    `_perguntarAnexo`) e a resposta REAL da rota `/add-file` para os 7 arquivos
    repetidos — o corpo que o navegador recebeu às 07:46;
  · o recado do servidor chega à pessoa, e o `/api/process` só é chamado
    DEPOIS do clique dela no botão que diz o tipo;
  · o tipo oferecido é o do projeto irmão, a não ser que ela tenha escolhido
    outro À MÃO no formulário — com o `change` disparado no listener que o
    painel REGISTRA (o registro sai do dashboard e roda aqui);
  · rede, 5xx sem recado, diálogo que falha, erro depois do anexo (que volta
    ao formulário) e o confirm nativo sem o toast.js também não criam nada
    sozinhos;
  · e CONTROLES: o harness enxerga o `/api/process` quando ele acontece, e cada
    conserto desfeito (decidir sem perguntar, esquecer o tipo do irmão, perder
    o recado, o `catch` que segue pro projeto novo) faz o defeito voltar.
"""
import io
import json
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

from _jsbancada import fonte_html, funcao_js, motor, rodar  # noqa: E402

_JOB = "ee801b82"
_NOME_IRMAO = "Projeto 21/09/2026"
_NOMES = ["prancha-%s.pdf" % l for l in "ABCDEFG"]

_FUNCOES = ("startProcessing", "_acharProjetoIrmao", "_assinaturaLocalDXF",
            "_baseLocal", "_perguntarAnexo", "_anexarAoIrmao",
            "_tipoDoProjetoNovoAposAnexo", "_textoDoAnexoRecusado",
            "_escolhaAposAnexoRecusado", "_marcarTipoEscolhidoAMao")


def _padrao_do_select(site):
    """O valor que o <select id="project-type"> REAL abre (1ª opção, sem
    `selected`) — é o tipo que o projeto sai quando ninguém mexe."""
    m = re.search(r'<select id="project-type"[^>]*>(.*?)</select>', site, re.S)
    assert m, "o <select id=\"project-type\"> sumiu do dashboard"
    sel = re.search(r'<option value="([^"]+)"[^>]*\sselected', m.group(1))
    return sel.group(1) if sel else re.search(r'<option value="([^"]+)"', m.group(1)).group(1)


_PRELUDIO = r"""
var window = this;
window.window = window;
var console = { log: function () {}, info: function () {}, warn: function () {},
                error: function () {}, debug: function () {} };
var __xhr = [], __dialogos = [], __estados = [], __ev = [], __toasts = [];
var __respostas = [];      // o que a pessoa clica em cada diálogo, em ordem
var __respAnexo = null;    // {status, texto} ou {rede: true}
var __respProcess = { status: 200, texto: '{"job_id": "novo0001"}' };
var __candidatos = [];
var __quebrarVoltaAoFormulario = 0;
var __aoPerguntar = null;  // o que a pessoa faz na tela ENQUANTO o diálogo está aberto
var location = { href: '', search: '' };
window.location = location;
window.API_UPLOAD_BASE = 'https://envio.exemplo';
var API_BASE = 'https://api.exemplo';
window.fmtDataBR = function () { return '21/09/2026'; };
function trackEvent(nome, meta) { __ev.push([nome, meta || {}]); }
window.trackEvent = trackEvent;
window.toast = {
  confirm: function (msg, o) {
    __dialogos.push({ msg: String(msg), ok: (o || {}).ok, cancel: (o || {}).cancel });
    if (__aoPerguntar) __aoPerguntar(__dialogos.length);
    var r = __respostas.shift();
    if (r === 'rejeita') return Promise.reject(new Error('diálogo fechou'));
    return Promise.resolve(!!r);
  },
  info: function (m) { __toasts.push(['info', String(m)]); },
  warn: function (m) { __toasts.push(['warn', String(m)]); },
  error: function (m) { __toasts.push(['error', String(m)]); },
  success: function (m) { __toasts.push(['success', String(m)]); }
};
function alert(m) { __toasts.push(['alert', String(m)]); }
function confirm(m) { __dialogos.push({ msg: String(m), nativo: true }); return !!__respostas.shift(); }
function FormData() { this.itens = []; this.append = function (k) { this.itens.push(k); }; }
function XMLHttpRequest() {
  var x = this;
  this.upload = {};
  this.setRequestHeader = function () {};
  this.open = function (m, u) {
    x._u = String(u);
    __xhr.push({ metodo: m, url: String(u), dialogosAntes: __dialogos.length });
  };
  this.send = function () {
    var r = (x._u.indexOf('/add-file') >= 0) ? __respAnexo : __respProcess;
    if (r.rede) { x.onerror(); return; }
    x.status = r.status; x.responseText = r.texto; x.onload();
  };
}
function URLSearchParams(o) {
  this.toString = function () {
    return Object.keys(o).map(function (k) {
      return encodeURIComponent(k) + '=' + encodeURIComponent(o[k]); }).join('&');
  };
}
function fetch(url) {
  if (String(url).indexOf('candidatos-anexo') >= 0) {
    return Promise.resolve({ ok: true, json: function () {
      return Promise.resolve({ projetos: __candidatos }); } });
  }
  return Promise.resolve({ ok: false, json: function () { return Promise.resolve({}); } });
}
var __els = {};
function _el(id) {
  return { id: id, value: '', textContent: '', innerHTML: '', style: {}, dataset: {},
           _ouvintes: {},
           addEventListener: function (ev, fn) {
             (this._ouvintes[ev] = this._ouvintes[ev] || []).push(fn); },
           classList: { add: function () {}, remove: function () {},
                        contains: function () { return false; } } };
}
// O gesto da pessoa: o navegador troca o valor e dispara o evento nos
// ouvintes que a PÁGINA registrou. `sel.value = ...` do código não dispara nada.
function __disparar(id, ev) {
  var el = __els[id];
  (el._ouvintes[ev] || []).forEach(function (fn) { fn.call(el, { type: ev, target: el }); });
  return (el._ouvintes[ev] || []).length;
}
['project-name', 'project-typology', 'project-type', 'project-area',
 'project-pe-direito'].forEach(function (i) { __els[i] = _el(i); });
__els['project-typology'].value = 'office';
var document = {
  getElementById: function (id) { return __els[id] || null; },
  querySelectorAll: function () { return []; }
};
var stateUpload = { id: 'upload' }, stateProcessing = { id: 'processing' },
    stateDone = { id: 'done' }, stateError = { id: 'error' };
function showState(s) {
  if (s === stateUpload && __quebrarVoltaAoFormulario > 0) {
    __quebrarVoltaAoFormulario--; throw new Error('a tela quebrou');
  }
  __estados.push(s.id);
}
var processingStep = { textContent: '' }, progressBar = { style: {} },
    progressPercent = { textContent: '' }, timeEstimate = { textContent: '' },
    errorMessage = { textContent: '' };
function renderFileProgress() {}
function startPolling() { __estados.push('polling'); }
function _botaoDoErro() {}
function mostrarAvisoAec() {}
function _limparAvisosDoEnvio() {}
function requestNotificationPermission() {}
function aplicarTextoDoPeDireito() {}
var sbClient = { auth: { getSession: function () {
  return Promise.resolve({ data: { session: { access_token: 'jwt-de-teste' } } }); } } };
var currentUser = { id: 'u-teste' }, accessToken = 'jwt-de-teste', currentJobId = null;
var userCreditsCents = 0;
1;
"""


def _fonte_das_funcoes(mutacoes=()):
    site = fonte_html("dashboard.html")
    partes = [funcao_js(n, "dashboard.html", site) for n in _FUNCOES]
    m = re.search(r"const _ROTULO_DO_TIPO = \{[^}]*\};", site)
    assert m, "o `_ROTULO_DO_TIPO` sumiu do dashboard"
    partes.append(m.group(0))
    js = "\n;\n".join(partes)
    for velho, novo in mutacoes:
        # 🧪 a âncora do controle é a instrução INTEIRA, e única
        assert js.count(velho) == 1, ("âncora do controle achada %d vezes: %r"
                                      % (js.count(velho), velho[:80]))
        js = js.replace(velho, novo, 1)
    return site, js


def _registros_do_tipo_a_mao(site):
    """Os `addEventListener` que o painel faz com `_marcarTipoEscolhidoAMao`,
    como estão no fonte — rodam aqui como rodam no carregamento da página.

    🪤 Chamar `_marcarTipoEscolhidoAMao()` direto deixava o REGISTRO fora da
    bancada: apagado (ou trocado de evento), a escolha feita à mão passava a
    ser atropelada pelo tipo do irmão e tudo seguia verde.
    """
    regs = [m.group(0) for m in re.finditer(
        r"document\.getElementById\('project-type'\)\s*\??\.addEventListener\([^;]*?\);",
        site) if "_marcarTipoEscolhidoAMao" in m.group(0)]
    assert regs, ("o painel não registra mais `_marcarTipoEscolhidoAMao` no "
                  "<select id=\"project-type\">: sem o registro, a escolha feita "
                  "à mão é atropelada pelo tipo do irmão")
    return "\n;\n".join(regs)


def _o_409_de_verdade(monkeypatch):
    """A rota `/add-file` REAL com os 7 PDFs que já estão no projeto.

    Devolve (status, corpo) — o que o navegador recebeu às 07:46:11. Dublês
    só na borda (dono, Storage, banco); a conferência por sha256 e o recado
    são os de produção.
    """
    import main
    from fastapi.testclient import TestClient

    conteudos = {n: (("%%PDF-1.4 %s " % n) * 40).encode("ascii") for n in _NOMES}
    disparos, subidas = [], []
    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: "dono-1")
    monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: True)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_storage_upload_prancha",
                        lambda *a, **k: subidas.append(a) or True)
    monkeypatch.setattr(main, "_process_job_throttled",
                        lambda *a, **k: disparos.append(a))
    monkeypatch.setattr(main, "_pranchas_com_tamanho",
                        lambda job, *a, **k: [("%s/%s" % (job, n), len(b))
                                              for n, b in conteudos.items()])
    monkeypatch.setattr(main, "_supabase_storage_download_prancha",
                        lambda job, nome, *a, **k: conteudos.get(nome))

    class _Resp(object):
        def read(self_):
            return json.dumps([{"typology": "office", "project_type": "estrutura",
                                "status": "done", "user_total_area": 0,
                                "user_pe_direito": 0}]).encode("utf-8")

    monkeypatch.setattr(main.urllib.request, "urlopen", lambda *a, **k: _Resp())
    r = TestClient(main.app, raise_server_exceptions=False).post(
        "/api/project/%s/add-file" % _JOB,
        files=[("files", (n, io.BytesIO(b), "application/pdf"))
               for n, b in conteudos.items()])
    assert r.status_code == 409, (r.status_code, r.text[:300])
    assert disparos == [] and subidas == [], "a rota refez o projeto: o cenário não é o do caso"
    return r.status_code, r.text


def _cena(anexo, cliques, tipo_irmao="estrutura", a_mao=None, mutacoes=(),
          quebrar_volta=0, durante_o_dialogo="", registrar=True, sem_toast=False):
    site, fonte = _fonte_das_funcoes(mutacoes)
    js = motor(_PRELUDIO)
    js.evaljs(fonte + "\n;1;")
    if registrar:
        # o que a página faz ao carregar: registra o ouvinte do <select>
        js.evaljs(_registros_do_tipo_a_mao(site) + "\n;1;")
    if sem_toast:
        # o toast.js carrega com `defer`; sem ele sobra o confirm nativo
        js.evaljs("window.toast = undefined; 1;")
    js.evaljs("document.getElementById('project-type').value = %s; 1;"
              % json.dumps(_padrao_do_select(site)))
    js.evaljs("var selectedFiles = %s.map(function (n) { return { name: n }; });"
              "__respAnexo = %s; __respostas = %s; __quebrarVoltaAoFormulario = %d;"
              "__candidatos = [{ job_id: %s, project_name: %s, project_type: %s,"
              " created_at: '2026-09-21T20:07:00Z', items_count: 63,"
              " bases: selectedFiles.map(function (f) { return _baseLocal(f.name); }) }];"
              "1;"
              % (json.dumps(_NOMES), json.dumps(anexo), json.dumps(cliques),
                 quebrar_volta, json.dumps(_JOB), json.dumps(_NOME_IRMAO),
                 json.dumps(tipo_irmao)))
    if a_mao:
        # a pessoa mexeu no <select>: o valor muda e o navegador dispara o
        # `change` nos ouvintes que a página registrou — nenhum atalho daqui
        js.evaljs("document.getElementById('project-type').value = %s;"
                  " __disparar('project-type', 'change'); 1;" % json.dumps(a_mao))
    if durante_o_dialogo:
        js.evaljs("__aoPerguntar = function (n) { %s }; 1;" % durante_o_dialogo)
    r = rodar(js, "startProcessing()")
    assert "ok" in r, "o startProcessing LANÇOU: %r" % r
    return json.loads(js.evaljs(
        "JSON.stringify({xhr: __xhr, dialogos: __dialogos, estados: __estados,"
        " ev: __ev, toasts: __toasts, href: location.href,"
        " tipo: document.getElementById('project-type').value})"))


def _processos(c):
    return [x for x in c["xhr"] if "/api/process" in x["url"]]


def _anexos(c):
    return [x for x in c["xhr"] if "/add-file" in x["url"]]


def _recusa_409(monkeypatch):
    st, corpo = _o_409_de_verdade(monkeypatch)
    return {"status": st, "texto": corpo}, json.loads(corpo)["detail"]


# ── o caso ─────────────────────────────────────────────────────────────────
def test_o_409_mostra_o_recado_do_servidor_e_nao_cria_projeto_sozinho(monkeypatch):
    anexo, recado = _recusa_409(monkeypatch)
    assert "prancha-A.pdf" in recado and "prancha-G.pdf" in recado, recado
    # o recado que agora CHEGA à pessoa fala dos 7, não de "Esse arquivo"
    # (o texto em si é cobrado em test_anexo_repetido_nao_refaz_o_projeto)
    assert recado.startswith("Esses 7 arquivos já estão no projeto"), recado[:120]
    c = _cena(anexo, [True, True])            # "Anexar", depois "Abrir o projeto"
    assert len(_anexos(c)) == 1, "o anexo nem saiu: a cena não é a do caso"
    assert _processos(c) == [], (
        "o anexo foi recusado e a tela criou projeto novo SOZINHA — o que "
        "gerou o f8d8e6d8: %r" % c["xhr"])
    assert len(c["dialogos"]) == 2, "a recusa não virou pergunta: %r" % c["dialogos"]
    assert recado in c["dialogos"][1]["msg"], (
        "o recado do servidor não chegou à pessoa: %r" % c["dialogos"][1]["msg"][:300])
    assert "vou criar um projeto novo" not in json.dumps(c, ensure_ascii=False), (
        "a tela ainda anuncia que VAI criar o projeto")
    assert c["href"] == "projeto.html?job_id=%s" % _JOB, c["href"]
    assert "start_project" not in [e[0] for e in c["ev"]], c["ev"]
    assert ["anexo_recusado", {"job_id": _JOB, "type": "409"}] in c["ev"], c["ev"]


def test_projeto_novo_so_com_o_clique_dela_e_no_tipo_do_irmao(monkeypatch):
    """🔑 Ela pediu 'Anexar' a um projeto de ESTRUTURA. Se, depois da recusa,
    quiser mesmo um projeto novo, ele sai como estrutura — não no padrão do
    formulário — e o botão diz isso antes do clique."""
    anexo, recado = _recusa_409(monkeypatch)
    c = _cena(anexo, [True, False])           # "Anexar", depois "Criar projeto novo"
    assert c["dialogos"][1]["cancel"] == "Criar projeto novo (Estrutura)", c["dialogos"][1]
    assert "sai como Estrutura, o mesmo tipo do projeto" in c["dialogos"][1]["msg"], (
        c["dialogos"][1]["msg"])
    procs = _processos(c)
    assert len(procs) == 1, c["xhr"]
    assert procs[0]["dialogosAntes"] == 2, (
        "o projeto novo saiu ANTES do clique da pessoa: %r" % procs[0])
    assert "project_type=estrutura" in procs[0]["url"], procs[0]["url"]
    assert ["start_project", {"type": "estrutura"}] in c["ev"], c["ev"]
    assert c["tipo"] == "estrutura", "o formulário não mostra o tipo que vai sair"
    assert "processing" in c["estados"] and c["estados"][-1] == "polling", c["estados"]


def test_o_tipo_escolhido_A_MAO_vence_o_do_irmao(monkeypatch):
    """Escolha dela no formulário é escolha; o padrão do <select> não é."""
    anexo, _ = _recusa_409(monkeypatch)
    c = _cena(anexo, [True, False], a_mao="arquitetura")
    assert c["dialogos"][1]["cancel"] == "Criar projeto novo (Arquitetura)", c["dialogos"][1]
    assert ('o projeto "%s" é Estrutura' % _NOME_IRMAO) in c["dialogos"][1]["msg"], (
        "o tipo dela difere do irmão e a mensagem não conta: %r" % c["dialogos"][1]["msg"])
    procs = _processos(c)
    assert len(procs) == 1 and "project_type=arquitetura" in procs[0]["url"], c["xhr"]


def test_o_tipo_que_vale_e_o_que_o_BOTAO_disse(monkeypatch):
    """O diálogo não trava o formulário atrás dele. Se o <select> mudar com o
    diálogo aberto, o clique foi em "Criar projeto novo (Estrutura)" — é esse
    o contrato, e o projeto não pode sair com outro tipo."""
    anexo, _ = _recusa_409(monkeypatch)
    c = _cena(anexo, [True, False], durante_o_dialogo=(
        "if (n === 2) document.getElementById('project-type').value = 'arquitetura';"))
    assert c["dialogos"][1]["cancel"] == "Criar projeto novo (Estrutura)", c["dialogos"][1]
    assert "project_type=estrutura" in _processos(c)[0]["url"], _processos(c)


def test_irmao_sem_tipo_conhecido_fica_no_que_o_formulario_mostra(monkeypatch):
    """Backend antigo (sem `project_type` no candidato): nada é inventado."""
    anexo, _ = _recusa_409(monkeypatch)
    c = _cena(anexo, [True, False], tipo_irmao="")
    assert c["dialogos"][1]["cancel"] == "Criar projeto novo (Arquitetura)", c["dialogos"][1]
    assert "project_type=arquitetura" in _processos(c)[0]["url"]


# ── as outras falhas do anexo ──────────────────────────────────────────────
def test_falha_de_REDE_tambem_nao_cria_projeto_sozinho():
    c = _cena({"rede": True}, [True, True])
    assert _processos(c) == [], c["xhr"]
    msg = c["dialogos"][1]["msg"]
    assert "Não recebi a resposta" in msg and "Pode ser que ele tenha chegado" in msg, msg
    assert ["anexo_recusado", {"job_id": _JOB, "type": "rede"}] in c["ev"], c["ev"]
    assert c["href"] == "projeto.html?job_id=%s" % _JOB


def test_5xx_SEM_recado_diz_o_que_sabe_e_nao_cria():
    """Um 502 do proxy chega com HTML: o motor pode ter recebido o anexo."""
    c = _cena({"status": 502, "texto": "<html>Bad gateway</html>"}, [True, True])
    assert _processos(c) == [], c["xhr"]
    msg = c["dialogos"][1]["msg"]
    assert "código 502" in msg and "Pode ser que ele tenha chegado" in msg, msg


def test_5xx_COM_recado_mostra_o_recado():
    """Vários recados da rota dizem 'os arquivos ficaram guardados no
    projeto' — criar outro projeto por cima dobraria o trabalho."""
    rec = "Não consegui confirmar o início do processamento. Os arquivos ficaram guardados."
    c = _cena({"status": 503, "texto": json.dumps({"detail": rec})}, [True, True])
    assert rec in c["dialogos"][1]["msg"], c["dialogos"][1]["msg"]
    assert _processos(c) == []


def test_dialogo_que_FALHA_nao_cria_nada():
    c = _cena({"status": 409, "texto": json.dumps({"detail": "x"})}, [True, "rejeita"])
    assert _processos(c) == [], c["xhr"]
    assert c["href"] == "", "navegou sem a pessoa pedir"
    assert c["estados"][-1] == "upload", c["estados"]


def test_erro_DEPOIS_do_anexo_nao_cai_no_projeto_novo():
    """🪤 O `catch` do bloco do anexo seguia pro projeto novo em QUALQUER erro.
    Antes de o anexo sair, certo (a sugestão é acessório); depois, não."""
    c = _cena({"status": 409, "texto": json.dumps({"detail": "x"})}, [True, True],
              quebrar_volta=1)
    assert _processos(c) == [], c["xhr"]
    assert any(t[0] == "error" and "não criei projeto novo" in t[1]
               for t in c["toasts"]), c["toasts"]
    # e a pessoa volta ao formulário — sem isto ela fica presa na tela de
    # processamento, em "Anexando ao projeto…", só com o toast
    assert c["estados"][-1] == "upload", c["estados"]


def test_sem_o_toast_Cancelar_do_confirm_nativo_nao_cria_nada(monkeypatch):
    """O toast.js carrega com `defer`; sem ele, o confirm nativo só tem
    OK/Cancelar e a pergunta vira "criar?". Cancelar não pode criar."""
    anexo, recado = _recusa_409(monkeypatch)
    c = _cena(anexo, [True, False], sem_toast=True)   # "OK" (anexar), "Cancelar"
    assert len(c["dialogos"]) == 2 and c["dialogos"][1].get("nativo"), (
        "a cena não passou pelo confirm nativo: %r" % c["dialogos"])
    assert recado in c["dialogos"][1]["msg"], c["dialogos"][1]["msg"][:300]
    assert "Cancelar não cria nada" in c["dialogos"][1]["msg"], c["dialogos"][1]["msg"]
    assert _processos(c) == [], "Cancelar no confirm nativo criou projeto: %r" % c["xhr"]
    assert c["href"] == "", "navegou sem a pessoa pedir"
    assert c["estados"][-1] == "upload", c["estados"]


# ── controles: o harness enxerga, e cada conserto desfeito reprova ─────────
def test_CONTROLE_anexo_que_DA_CERTO_navega_sem_segunda_pergunta():
    c = _cena({"status": 200, "texto": json.dumps({"status": "ok", "job_id": _JOB})}, [True])
    assert len(c["dialogos"]) == 1 and _processos(c) == [], c
    assert c["href"] == "projeto.html?job_id=%s" % _JOB
    assert ["anexou_ao_projeto", {"job_id": _JOB}] in c["ev"], c["ev"]


def test_CONTROLE_quem_recusa_a_sugestao_segue_pro_projeto_novo():
    """Sem este, 'nenhum /api/process' passaria verde por um harness cego."""
    c = _cena({"status": 409, "texto": "{}"}, [False])
    assert _anexos(c) == [], c["xhr"]
    assert len(_processos(c)) == 1, c["xhr"]


def test_CONTROLE_decidir_sem_perguntar_volta_o_defeito(monkeypatch):
    anexo, _ = _recusa_409(monkeypatch)
    c = _cena(anexo, [True, True], mutacoes=[(
        "const escolha = await _escolhaAposAnexoRecusado(",
        "const escolha = 'criar'; void (")])
    procs = _processos(c)
    assert len(procs) == 1 and procs[0]["dialogosAntes"] == 1, (
        "com a decisão tirada da pessoa, o guarda devia ver o projeto novo "
        "nascer sem o 2º clique: %r" % c["xhr"])


def test_CONTROLE_esquecer_o_tipo_do_irmao_volta_a_arquitetura(monkeypatch):
    anexo, _ = _recusa_409(monkeypatch)
    c = _cena(anexo, [True, False], mutacoes=[("sel.value = doIrmao;", "void 0;")])
    assert "project_type=arquitetura" in _processos(c)[0]["url"], (
        "sem o tipo do irmão o projeto devia sair no padrão do formulário")


def test_CONTROLE_perder_o_recado_some_com_ele_da_tela(monkeypatch):
    anexo, recado = _recusa_409(monkeypatch)
    c = _cena(anexo, [True, True], mutacoes=[(
        "const recado = (corpo && typeof corpo.detail === 'string') ? corpo.detail.trim() : '';",
        "const recado = '';")])
    assert recado not in c["dialogos"][1]["msg"]


def test_CONTROLE_o_catch_que_segue_cria_o_projeto():
    c = _cena({"status": 409, "texto": json.dumps({"detail": "x"})}, [True, True],
              quebrar_volta=1, mutacoes=[("if (_anexoSaiu) {", "if (false) {")])
    assert len(_processos(c)) == 1, c["xhr"]


def test_CONTROLE_sem_o_registro_do_change_o_irmao_atropela_a_escolha(monkeypatch):
    """Sem este, 'o tipo à mão vence' passaria verde com um harness que nem
    registra o ouvinte — que é como ele estava antes de 22/09."""
    anexo, _ = _recusa_409(monkeypatch)
    c = _cena(anexo, [True, False], a_mao="arquitetura", registrar=False)
    assert c["dialogos"][1]["cancel"] == "Criar projeto novo (Estrutura)", c["dialogos"][1]
    assert "project_type=estrutura" in _processos(c)[0]["url"], _processos(c)


def test_CONTROLE_o_OK_do_confirm_nativo_cria_depois_do_clique(monkeypatch):
    """Sem este, 'Cancelar não cria' passaria verde por um harness que nunca
    chegasse ao confirm nativo, ou que não enxergasse o projeto nascer por ele."""
    anexo, _ = _recusa_409(monkeypatch)
    c = _cena(anexo, [True, True], sem_toast=True)    # "OK" (anexar), "OK" (criar)
    procs = _processos(c)
    assert len(procs) == 1 and procs[0]["dialogosAntes"] == 2, c["xhr"]
    assert "project_type=estrutura" in procs[0]["url"], procs[0]["url"]
