# -*- coding: utf-8 -*-
"""Um NAVEGADOR mínimo pra bancada: roda o JavaScript do site de verdade.

🩸 06/09/2026 — por que isto existe. Metade dos guardas de tela desta casa
procurava string dentro do `.html`, e a varredura por mutação mostrou o preço:

  · `<div id="convite-area" class="hidden ...">` ganhou um
    `style="display:none"` — o `id` continuava lá, o guarda continuava verde,
    e a caixa nunca mais apareceria pro cliente;
  · `maybeShowConviteArea();` virou `if (false) maybeShowConviteArea();` —
    a chamada continuava no arquivo;
  · `'/api/project/${jobId}/inform-area'` virou `.../inform-area-v2` — o
    trecho procurado continuava sendo um prefixo do texto novo.

Nenhuma dessas três é detectável lendo o arquivo. Todas as três são óbvias
quando a função RODA: a caixa não aparece, o evento não sai, a rota chamada é
outra.

🪤 O motor é o `dukpy` (Duktape embutido). Ele não tem `window`, `document` nem
laço de eventos — este arquivo monta o mínimo, e o mínimo é de propósito: DOM
grande esconde defeito em vez de mostrar. O que existe aqui é o que os guardas
precisam ver — classe, `style.display`, texto, valor, ordem no documento,
`data-*` e o ouvinte de clique.

🪤 `await` não roda no Duktape: não há fila de microtarefas pra drenar. Por isso
`sem_await()` tira o `async`/`await` do trecho ANTES de rodar — a sequência de
comandos e os valores continuam os mesmos, só sem o adiamento. Quem depende
disso passa dublês SÍNCRONOS (ver `submitConviteArea` nos guardas).
"""
import json
import re

import dukpy   # noqa: F401  — falta dele é ERRO, nunca skip: verde vazio mente


def atributos(html, elem_id):
    """A tag REAL do arquivo: nome, atributos, posição e conteúdo interno."""
    m = re.search(r'<(\w+)([^>]*\sid="%s"[^>]*)>' % re.escape(elem_id), html)
    if not m:
        return None
    tag, resto = m.group(1), m.group(2)
    attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', resto))
    fim = html.find("</%s>" % tag, m.end())
    return {"tag": tag.upper(), "attrs": attrs, "pos": m.start(),
            "html": html[m.end():fim] if fim > m.end() else ""}


def elementos(html, ids):
    """Os elementos pedidos, JÁ na ordem em que aparecem no documento."""
    achados = []
    for i in ids:
        a = atributos(html, i)
        assert a is not None, (
            "o id %r não existe no HTML — o JS escreve nele e morre calado no "
            "catch (getElementById devolve null)" % i)
        a["id"] = i
        achados.append(a)
    return sorted(achados, key=lambda a: a["pos"])


_TAG = re.compile(r"<(\w+)((?:[^>\"]|\"[^\"]*\")*)>")


def todas_as_tags(html):
    """Toda tag de abertura do arquivo, com os atributos que ela declara."""
    for m in _TAG.finditer(html):
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', m.group(2)))
        fim = html.find("</%s>" % m.group(1), m.end())
        yield {"tag": m.group(1).upper(), "attrs": attrs, "pos": m.start(),
               "id": attrs.get("id", ""),
               "html": html[m.end():fim] if 0 < fim - m.end() < 4000 else ""}


def tags_com(html, atributo=None, classe=None):
    """As tags que declaram um atributo, ou que têm uma classe. Em ordem."""
    saida = []
    for t in todas_as_tags(html):
        if atributo and atributo in t["attrs"]:
            saida.append(t)
        elif classe and classe in (t["attrs"].get("class") or "").split():
            saida.append(t)
    return saida


_DOM = r"""
var __els = {}, __ordem = [], __ouvintes = {};

function _El(spec) {
  var self = this;
  this.id = spec.id;
  this.tagName = spec.tag || 'DIV';
  this._attrs = spec.attrs || {};
  this.className = this._attrs['class'] || '';
  this.innerHTML = spec.html || '';
  this.textContent = String(spec.html || '').replace(/<[^>]*>/g, '');
  this.value = this._attrs['value'] || '';
  this.disabled = false;
  this.style = { display: '' };
  var _st = this._attrs['style'] || '';
  var _m = /display\s*:\s*([^;]+)/.exec(_st);
  if (_m) this.style.display = _m[1].replace(/\s+$/, '');
  this.classList = {
    contains: function (c) { return (' ' + self.className + ' ').indexOf(' ' + c + ' ') >= 0; },
    add: function (c) { if (!this.contains(c)) self.className = (self.className + ' ' + c).replace(/^\s+/, ''); },
    remove: function (c) {
      self.className = self.className.split(/\s+/).filter(function (x) { return x && x !== c; }).join(' ');
    },
    toggle: function (c, forcar) {
      var tem = this.contains(c);
      var quer = (arguments.length > 1) ? !!forcar : !tem;
      if (quer) this.add(c); else this.remove(c);
      return quer;
    }
  };
  this.getAttribute = function (n) {
    return Object.prototype.hasOwnProperty.call(self._attrs, n) ? self._attrs[n] : null;
  };
  this.setAttribute = function (n, v) { self._attrs[n] = v; };
  this.closest = function (sel) {
    var mm = /^\[([\w-]+)\]$/.exec(sel);
    var no = self;
    while (no) {
      if (mm && no.getAttribute && no.getAttribute(mm[1]) !== null) return no;
      no = no.parentNode;
    }
    return null;
  };
  this.after = function (outro) {
    var de = __ordem.indexOf(outro);
    if (de >= 0) __ordem.splice(de, 1);
    __ordem.splice(__ordem.indexOf(self) + 1, 0, outro);
  };
  this.appendChild = function (outro) { outro.parentNode = self; return outro; };
  this.addEventListener = function (t, f) { (__ouvintes[t] = __ouvintes[t] || []).push(f); };
}

function _montar(specs) {
  __els = {}; __ordem = [];
  for (var i = 0; i < specs.length; i++) {
    var el = new _El(specs[i]);
    if (!el.id) el.id = '__auto' + i;      // tag sem id ainda ocupa o documento
    __els[el.id] = el;
    __ordem.push(el);
  }
}

/* seletor de pobre: `.classe`, `[attr]` e `[attr="valor"]`. É o que os
   guardas desta casa precisam — seletor rico esconde defeito. */
function _casa(el, sel) {
  sel = String(sel).trim();
  var m = /^\.([\w-]+)$/.exec(sel);
  if (m) return el.classList.contains(m[1]);
  m = /^\[([\w-]+)(?:=["']?([^\]"']*)["']?)?\]$/.exec(sel);
  if (m) {
    var v = el.getAttribute(m[1]);
    if (v === null) return false;
    return m[2] === undefined || v === m[2];
  }
  return false;
}

var document = {
  getElementById: function (id) { return __els[id] || null; },
  addEventListener: function (t, f) { (__ouvintes[t] = __ouvintes[t] || []).push(f); },
  querySelectorAll: function (sel) {
    return __ordem.filter(function (el) { return _casa(el, sel); });
  },
  querySelector: function (sel) {
    var r = this.querySelectorAll(sel);
    return r.length ? r[0] : null;
  },
  body: null
};
var window = { trackEvent: null };
window.addEventListener = function (t, f) { (__ouvintes[t] = __ouvintes[t] || []).push(f); };
var console = {
  log: function () {}, warn: function () {}, error: function () {}, info: function () {}
};
var localStorage = {
  _d: {}, getItem: function (k) { return this._d[k] === undefined ? null : this._d[k]; },
  setItem: function (k, v) { this._d[k] = String(v); },
  removeItem: function (k) { delete this._d[k]; }
};
/* 🔑 `location.hash` DISPARA o hashchange, como no navegador de verdade: sem
   isso a navegação por aba do admin (que escreve o hash e volta pelo evento)
   não roda, e o guarda mediria meia navegação. */
var __hash = '';
var location = { search: '', href: '' };
Object.defineProperty(location, 'hash', {
  get: function () { return __hash; },
  set: function (v) {
    v = String(v);
    __hash = (v && v.charAt(0) !== '#') ? '#' + v : v;
    var fs = __ouvintes['hashchange'] || [];
    for (var i = 0; i < fs.length; i++) fs[i]({ type: 'hashchange' });
  }
});
window.location = location;
function URLSearchParams(s) {
  this._s = String(s || '');
  this.get = function (k) {
    var m = new RegExp('[?&]' + k + '=([^&]*)').exec(this._s);
    return m ? m[1] : null;
  };
}

/* o que os guardas perguntam ao DOM */
function _visivel(id) {
  var el = __els[id];
  if (!el) return false;
  return !el.classList.contains('hidden') && el.style.display !== 'none';
}
function _posicao(id) {
  for (var i = 0; i < __ordem.length; i++) if (__ordem[i].id === id) return i;
  return -1;
}
function _disparar(tipo, alvo) {
  var fs = __ouvintes[tipo] || [];
  for (var i = 0; i < fs.length; i++) fs[i]({ target: alvo, type: tipo });
  return fs.length;
}

/* diário da telemetria: o que o site MANDOU registrar */
var __eventos = [];
function _ligarTelemetria() {
  window.trackEvent = function (nome, meta) { __eventos.push([nome, meta || {}]); };
  trackEvent = window.trackEvent;
}
var trackEvent = null;
"""


def bloco_a_partir_de(src, marcador, arquivo="(js)", fecho=");"):
    """Do marcador até a chave que fecha o primeiro `{` — o bloco inteiro.

    Serve pro que não é `function nome(...)`: um `document.addEventListener`,
    por exemplo. O fim é o balanço de chaves, nunca um número de caracteres.
    """
    i = src.find(marcador)
    assert i >= 0, "não achei %r em %s" % (marcador, arquivo)
    k = src.find("{", i)
    assert k > 0, "bloco sem corpo: %r" % marcador
    prof = 0
    while k < len(src):
        if src[k] == "{":
            prof += 1
        elif src[k] == "}":
            prof -= 1
            if prof == 0:
                return src[i:k + 1] + fecho
        k += 1
    raise AssertionError("chaves desbalanceadas depois de %r" % marcador)


def sem_await(js):
    """Tira o adiamento, mantém a sequência. Ver a docstring do módulo."""
    js = re.sub(r"\basync\s+function\b", "function", js)
    js = re.sub(r"\bawait\s+", "", js)
    return js


def rodar(pedacos, expressao):
    """Monta o DOM, roda os pedaços de JS e devolve o valor da expressão."""
    return dukpy.evaljs([_DOM] + list(pedacos) + [expressao])


def montar(elementos_):
    """O JS que constrói o documento a partir do que o HTML REAL declara."""
    return "_montar(%s);" % json.dumps(elementos_, ensure_ascii=False)
