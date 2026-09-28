# -*- coding: utf-8 -*-
"""O comentário do NPS não se perde — e a nota escolhida também não.

🩸 27/09/2026 — auditoria de telemetria, item 6. De 30/08 a 27/09: 9 notas de
fora e 0 comentário. Dois caminhos jogavam o dado fora:

  · projeto.html: a nota sai 6 s depois do clique. Quem começava a escrever
    DEPOIS disso apertava "Enviar comentário", `_fbFlush` devolvia false (a nota
    "já tinha ido") e a tela dizia "Não consegui salvar sua avaliação" — com a
    nota GRAVADA e o comentário no lixo.
  · dashboard.html: o "Pular" só aparece depois de escolher a nota (é o pular
    do COMENTÁRIO) e fechava o widget sem gravar nada.

🔑 O comentário atrasado entra na MESMA linha (`/api/nps/comentario`, UPDATE da
última nota desta conta — do token — pra este projeto, nas últimas 24 h). O
"Pular" grava a nota sem comentário. Sem promessa: que isso explica os 0
comentários é hipótese (plano, item 6).
"""
import json
import os
import sys
import threading

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402
from _jsbancada import fonte_html, funcao_js, motor, rodar  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
#  1. A rota do comentário atrasado
# ══════════════════════════════════════════════════════════════════════════
def _rota(monkeypatch, linhas=None, patch=(200, [{"id": "n1"}]), usuario=True, comentario="faltou o forro"):
    chamadas, alertas = [], []
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda req: ({"id": "u-token", "email": "c@x.com"} if usuario else None))

    def _rest(metodo, caminho, body=None, params=None, prefer=None, **k):
        chamadas.append({"metodo": metodo, "caminho": caminho, "body": body, "params": params})
        if metodo == "GET":
            return 200, (linhas if linhas is not None else
                         [{"id": "n1", "score": 7, "context": "after_project", "job_id": "j1",
                           "user_email": "c@x.com", "user_name": ""}])
        return patch
    monkeypatch.setattr(main, "_supa_rest_service", _rest)
    monkeypatch.setattr(main, "_alerta_nps", lambda row, cat="detractor", **k: alertas.append((row, cat, k)))
    r = main.nps_comentario(main.NPSComentarioPayload(job_id="j1", comment=comentario), request=None)
    return r, chamadas, alertas


def test_o_comentario_atrasado_entra_na_MESMA_linha(monkeypatch):
    r, chamadas, alertas = _rota(monkeypatch)
    assert r == {"status": "ok"}, r
    get, patch = chamadas
    assert get["params"]["user_id"] == "eq.u-token", "a linha tem que ser DA CONTA do token, não do corpo"
    assert get["params"]["job_id"] == "eq.j1" and get["params"]["context"] == "eq.after_project"
    assert get["params"]["created_at"].startswith("gte."), "sem janela: editaria nota antiga"
    assert patch["metodo"] == "PATCH" and patch["params"] == {"id": "eq.n1"}
    assert patch["body"] == {"comment": "faltou o forro"}, "o UPDATE mexeu em mais que o comentário"
    assert alertas and alertas[0][1] == "passive" and alertas[0][2] == {"comentario_depois": True}
    assert alertas[0][0]["comment"] == "faltou o forro"


def test_sem_sessao_e_401(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _rota(monkeypatch, usuario=False)
    assert e.value.status_code == 401


def test_comentario_vazio_nao_toca_o_banco(monkeypatch):
    r, chamadas, _ = _rota(monkeypatch, comentario="   ")
    assert r.get("vazio") and chamadas == []


def test_sem_nota_pra_atualizar_e_erro_dito_e_nada_gravado(monkeypatch):
    r, chamadas, alertas = _rota(monkeypatch, linhas=[])
    assert r["status"] == "error" and [c["metodo"] for c in chamadas] == ["GET"] and not alertas


def test_update_que_nao_pegou_linha_nenhuma_e_erro(monkeypatch):
    r, _, alertas = _rota(monkeypatch, patch=(200, []))
    assert r["status"] == "error" and not alertas


def test_o_alerta_diz_que_e_o_comentario_que_chegou_depois(monkeypatch):
    vistos, pronto = [], threading.Event()

    def _fake(assunto, corpo):
        vistos.append(assunto)
        pronto.set()
        return True
    monkeypatch.setattr(main, "_notify_admin", _fake)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rows", lambda *a, **k: [])
    main._alerta_nps({"score": 9, "user_email": "a@b.com", "comment": "ótimo", "job_id": ""},
                     "promoter", comentario_depois=True)
    assert pronto.wait(10), vistos
    assert vistos[0].startswith("💬 Comentário que chegou depois da nota"), vistos


# ══════════════════════════════════════════════════════════════════════════
#  2. O cartão do projeto, rodando o JavaScript da página
# ══════════════════════════════════════════════════════════════════════════
_DOM = r"""
var __els = {}, __req = [];
function __el(id) {
  if (!__els[id]) {
    var e = { id: id, value: '', hidden: true, html: '' };
    e.classList = { add: function (c) { if (c === 'hidden') e.hidden = true; },
                    remove: function (c) { if (c === 'hidden') e.hidden = false; } };
    e.insertAdjacentHTML = function (p, h) { e.html += h; };
    __els[id] = e;
  }
  return __els[id];
}
var document = { getElementById: __el };
var localStorage = { setItem: function () {}, getItem: function () { return null; } };
var API_BASE = 'https://api.teste', jobId = 'j1';
function __resposta() { return Promise.resolve({ ok: true, status: 200,
  json: function () { return Promise.resolve({ status: 'ok' }); } }); }
function authFetch(url, o) { __req.push({ url: url, body: JSON.parse(o.body) }); return __resposta(); }
function fetch(url, o) { __req.push({ url: url, keepalive: !!o.keepalive, body: JSON.parse(o.body) }); return __resposta(); }
var sbClient = { auth: { getSession: function () { return Promise.resolve({ data: { session:
  { user: { id: 'u1', email: 'a@b.c' }, access_token: 't' } } }); } } };
function setTimeout() { return 1; } function clearTimeout() {}
var _fbScore = null, _fbTimer = null, _fbPosted = false, _fbToken = null, _fbMandado = '', _fbEnvio = null;
null;
"""

_NOVAS = ("_fbTexto", "_fbComentarioDepois", "_fbTick", "_fbFlush", "_fbArm", "postNps",
          "sendFeedbackComment", "_fbSalvaAntesDeSair")

# Como era até 27/09 — só pro controle
_ANTES = r"""
async function _fbFlush() {
  if (_fbPosted || _fbScore === null) return false;
  _fbPosted = true;
  const ok = await postNps(_fbScore, (document.getElementById('fb-comment').value || '').trim());
  if (!ok) _fbPosted = false;
  return ok;
}
async function sendFeedbackComment() {
  clearTimeout(_fbTimer);
  const ok = await _fbFlush();
  document.getElementById('fb-comment-wrap').classList.add('hidden');
  if (ok) {
    document.getElementById('fb-thanks').classList.remove('hidden');
  } else {
    const c = document.getElementById('feedback-card');
    if (c) c.insertAdjacentHTML('beforeend', '<p role="alert">Não consegui salvar sua avaliação agora.</p>');
    document.getElementById('fb-comment-wrap').classList.remove('hidden');
  }
}
"""


def _cartao(antes=False):
    js = motor(_DOM)
    js.evaljs(funcao_js("postNps", "projeto.html"))
    if antes:
        js.evaljs(_ANTES + " null;")
    else:
        for f in _NOVAS:
            js.evaljs(funcao_js(f, "projeto.html"))
    return js


# o caso: clicou a nota, os 6 s passaram SEM texto, escreveu depois, apertou Enviar
_CASO = ("(async function () { _fbScore = 7; await _fbFlush();"
         " __el('fb-comment').value = 'faltou o forro';"
         " await sendFeedbackComment(); return 1; })()")


def _ler(js, expr):
    return json.loads(js.evaljs("JSON.stringify(%s)" % expr))


def test_o_comentario_escrito_DEPOIS_dos_6s_vai_pra_mesma_linha_e_agradece():
    js = _cartao()
    assert "erro" not in rodar(js, _CASO)
    req = _ler(js, "__req")
    assert [r["url"] for r in req] == ["https://api.teste/api/nps", "https://api.teste/api/nps/comentario"], req
    assert req[0]["body"]["comment"] == "" and req[0]["body"]["score"] == 7
    assert req[1]["body"] == {"comment": "faltou o forro", "context": "after_project", "job_id": "j1"}
    assert _ler(js, "__el('fb-thanks').hidden") is False, "não agradeceu"
    assert "Não consegui" not in _ler(js, "__el('feedback-card').html"), "acusou falha com a nota gravada"


def test_CONTROLE_o_codigo_de_ANTES_perdia_o_comentario_e_acusava_falha():
    js = _cartao(antes=True)
    assert "erro" not in rodar(js, _CASO)
    req = _ler(js, "__req")
    assert [r["url"] for r in req] == ["https://api.teste/api/nps"], "o de antes nem mandava o comentário"
    assert "Não consegui" in _ler(js, "__el('feedback-card').html")


def test_comentario_escrito_ANTES_dos_6s_vai_junto_com_a_nota_e_nao_duplica():
    js = _cartao()
    rodar(js, "(async function () { _fbScore = 9; __el('fb-comment').value = 'ótimo';"
              " await _fbFlush(); await sendFeedbackComment(); return 1; })()")
    req = _ler(js, "__req")
    assert [r["url"] for r in req] == ["https://api.teste/api/nps"], req
    assert req[0]["body"]["comment"] == "ótimo"
    assert _ler(js, "__el('fb-thanks').hidden") is False


def test_fechar_a_aba_com_comentario_novo_manda_o_comentario_com_keepalive():
    js = _cartao()
    rodar(js, "(async function () { _fbScore = 2; await _fbFlush();"
              " __el('fb-comment').value = 'não achou as paredes'; _fbSalvaAntesDeSair(); return 1; })()")
    req = _ler(js, "__req")
    assert req[-1]["url"] == "https://api.teste/api/nps/comentario" and req[-1]["keepalive"] is True, req
    assert req[-1]["body"]["comment"] == "não achou as paredes"


def test_fechar_a_aba_sem_texto_novo_nao_manda_nada_a_mais():
    js = _cartao()
    rodar(js, "(async function () { _fbScore = 2; await _fbFlush(); _fbSalvaAntesDeSair(); return 1; })()")
    assert len(_ler(js, "__req")) == 1


def test_o_timer_depois_da_nota_manda_o_comentario_e_nao_a_nota_de_novo():
    """O `oninput` rearma o timer; com a nota já gravada, o timer tem que mandar
    o COMENTÁRIO — `/api/nps` é INSERT puro, 2º POST seria linha duplicada."""
    js = _cartao()
    rodar(js, "(async function () { _fbScore = 7; await _fbFlush();"
              " __el('fb-comment').value = 'x'; await _fbTick(); return 1; })()")
    urls = [r["url"] for r in _ler(js, "__req")]
    assert urls == ["https://api.teste/api/nps", "https://api.teste/api/nps/comentario"], urls


# ══════════════════════════════════════════════════════════════════════════
#  3. O "Pular" do widget do painel grava a nota
# ══════════════════════════════════════════════════════════════════════════
def test_o_pular_do_painel_grava_a_nota_sem_comentario():
    js = motor("var __envios = 0; var __c = { value: 'rascunho' };"
               "var document = { getElementById: function (id) { return id === 'nps-comment' ? __c : null; } };"
               "function submitNPS() { __envios += 1; return 1; } null;")
    js.evaljs(funcao_js("pularComentarioNPS", "dashboard.html"))
    js.evaljs("pularComentarioNPS(); null;")
    assert js.evaljs("__envios") == 1, "o Pular não gravou a nota"
    assert js.evaljs("__c.value") == "", "o Pular mandou o rascunho como comentário"


def test_o_botao_pular_esta_ligado_a_gravacao_e_nao_so_fecha():
    src = fonte_html("dashboard.html")
    i = src.index('id="nps-pular"')
    tag = src[src.rindex("<button", 0, i):src.index(">", i)]
    assert "Pular" in src[i:i + 200] and "remove()" not in tag, "o Pular voltou a só fechar: %r" % tag
    assert src.index('id="nps-comment-area"') < i, "o Pular saiu da área do comentário"
    assert "getElementById('nps-pular').addEventListener('click', pularComentarioNPS)" in src
