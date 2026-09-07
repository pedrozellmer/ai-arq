# -*- coding: utf-8 -*-
"""Bancada de JS: roda o JS do site DE VERDADE, num duktape com navegador de mentira.

🪤 Guarda que lê o texto do .js prova que a linha existe; só executar prova que
ela FAZ o que diz. Aqui `aiarq-utils.js` (e, quando pedido, os `<script>` de um
HTML) rodam num interpretador real; `setTimeout`, `setInterval`, `fetch`,
`confirm` e `scrollIntoView` são de mentira e REGISTRAM o que foi pedido em
`window.__ev`, pra o teste perguntar depois.

Reconstruído em 07/09/2026 pela bancada cética: o módulo não veio junto da
conversão que dependia dele.
"""
import io
import os
import re

import dukpy

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))

_PRELUDIO = r"""
var window = this;
window.window = window;
window.__ev = [];
window.__t = 0;

function _reg(tipo, extra) {
  var e = { tipo: tipo };
  for (var k in extra) { e[k] = extra[k]; }
  window.__ev.push(e);
  return e;
}

window.setTimeout = function (fn, ms) {
  _reg('setTimeout', { ms: ms || 0 });
  return ++window.__t;
};
window.setInterval = function (fn, ms) {
  _reg('setInterval', { ms: ms || 0 });
  return ++window.__t;
};
window.clearTimeout = function (id) { _reg('clearTimeout', { id: id }); };
window.clearInterval = function (id) { _reg('clearInterval', { id: id }); };

window.console = {
  log: function () {}, info: function () {},
  warn: function () {}, error: function () {}, debug: function () {}
};

window.localStorage = (function () {
  var m = {};
  return {
    getItem: function (k) { return (k in m) ? m[k] : null; },
    setItem: function (k, v) { m[k] = String(v); },
    removeItem: function (k) { delete m[k]; }
  };
})();

function _elemento(id) {
  var el = {
    id: id, innerHTML: '', textContent: '', value: '', hidden: false,
    style: {}, dataset: {}, children: [],
    classList: { add: function () {}, remove: function () {}, toggle: function () {},
                 contains: function () { return false; } },
    setAttribute: function () {}, getAttribute: function () { return null; },
    appendChild: function (c) { this.children.push(c); return c; },
    removeChild: function () {}, remove: function () {},
    addEventListener: function () {}, click: function () {},
    focus: function () {}, querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    scrollIntoView: function (o) { _reg('scroll', { id: id, opt: JSON.stringify(o || {}) }); },
    insertAdjacentHTML: function () {}
  };
  return el;
}
window.__els = {};
window.document = {
  referrer: '',
  body: _elemento('body'),
  addEventListener: function () {},
  createElement: function (t) { return _elemento('<' + t + '>'); },
  getElementById: function (id) {
    if (!window.__els[id]) { window.__els[id] = _elemento(id); }
    return window.__els[id];
  },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; }
};
window.addEventListener = function () {};
window.location = { href: 'https://ai.arq.br/admin.html', hostname: 'ai.arq.br',
                    search: '', hash: '', origin: 'https://ai.arq.br' };
window.navigator = { userAgent: 'bancada', language: 'pt-BR' };
window.screen = { width: 1440, height: 900 };
window.confirm = function (msg) { _reg('confirm', { msg: String(msg) }); return true; };
window.alert = function (msg) { _reg('alert', { msg: String(msg) }); };
window.open = function (u) { _reg('open', { url: String(u) }); return null; };

window.AbortController = function () {
  this.signal = { aborted: false };
  this.abort = function () { this.signal.aborted = true; _reg('abort', {}); };
};

window.__pedidos = [];
window.fetch = function (url, init) {
  _reg('fetch', { url: String(url) });
  return Promise.resolve(window.__RESPOSTA_PADRAO());
};
window.__RESPOSTA_PADRAO = function () {
  return { ok: true, status: 200, json: function () { return Promise.resolve({}); } };
};

window.notify = { warn: function () {}, ok: function () {}, err: function () {},
                  info: function () {} };
window.aiArqNotify = window.notify;

window.supabase = {
  createClient: function () {
    return {
      auth: {
        getSession: function () {
          return Promise.resolve({ data: { session: { access_token: 'jwt-de-mentira' } } });
        },
        getUser: function () {
          return Promise.resolve({ data: { user: { id: 'u1', email: 'admin@example.com' } } });
        }
      },
      from: function () {
        return { select: function () { return Promise.resolve({ data: [], error: null }); } };
      }
    };
  }
};
window.URL = function (u) { this.hostname = 'ai.arq.br'; this.href = String(u); };
1;
"""


class Pagina(object):
    """Um duktape com o navegador de mentira e os arquivos pedidos carregados."""

    def __init__(self, arquivos=(), prelude_extra=""):
        self.i = dukpy.JSInterpreter()
        self.i.evaljs(_PRELUDIO)
        if prelude_extra:
            self.i.evaljs(prelude_extra)
        for a in arquivos:
            self.i.evaljs(self._fonte(a))
        self.pump()

    @staticmethod
    def _fonte(arquivo):
        caminho = os.path.join(_RAIZ, arquivo)
        src = io.open(caminho, encoding="utf-8").read()
        if arquivo.endswith(".html"):
            blocos = re.findall(r"<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>",
                                src, re.S)
            src = "\n;\n".join(blocos)
        return src

    def eval(self, js):
        return self.i.evaljs(js)

    def pump(self, n=6):
        """Drena os `await` pendentes (cada evaljs roda a fila de microtasks)."""
        for _ in range(n):
            self.i.evaljs("1;")

    def chama(self, js):
        r = self.i.evaljs(js)
        self.pump()
        return r

    def eventos(self):
        import json as _j
        return _j.loads(self.i.evaljs("JSON.stringify(window.__ev)"))

    def limpa_eventos(self):
        self.i.evaljs("window.__ev = []; 1;")
