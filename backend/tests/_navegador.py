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
import io
import json
import os
import re

import dukpy   # noqa: F401  — falta dele é ERRO, nunca skip: verde vazio mente

_AQUI_NAV = os.path.dirname(os.path.abspath(__file__))
_RAIZ_NAV = os.path.dirname(os.path.dirname(_AQUI_NAV))

# ── O CSS COMPILADO, que é quem decide se a classe esconde ───────────────
# 🪤 06/09 (cético): `_visivel` modelava DUAS formas de sumir — a classe
# `hidden` e o `display:none` inline — de uma boa meia dúzia. `opacity-0`,
# `sr-only`, `h-0 overflow-hidden` e PAI escondido passavam batido.
# 🔑 A lista de classes que escondem NÃO é escrita à mão aqui: ela sai do
# `tailwind.min.css` que a produção serve. É a única fonte que sabe a verdade,
# porque o build do Tailwind é ESTÁTICO: `invisible`, por exemplo, NÃO está no
# CSS compilado — quem escrevesse `class="invisible"` na tag não esconderia
# nada, e um guarda com lista fixa acusaria um defeito que não existe.
_REGRA_CSS = re.compile(r"([^{}@]+)\{([^{}]*)\}")
_CLASSE_SIMPLES = re.compile(r"^\.([A-Za-z0-9_-]+)$")
_CSS_CACHE = {}


def css_declaracoes():
    """{classe: {propriedade: valor}} do CSS COMPILADO que o site serve.

    Só seletor de UMA classe simples: variantes responsivas e de estado
    (as que o Tailwind escreve com dois-pontos escapado) valem sob condição e
    não servem pra decidir "o cliente vê?".
    """
    if not _CSS_CACHE:
        css = io.open(os.path.join(_RAIZ_NAV, "tailwind.min.css"),
                      encoding="utf-8").read()
        fora = {}
        for sel, corpo in _REGRA_CSS.findall(css):
            decl = {}
            for par in corpo.split(";"):
                if ":" in par:
                    k, v = par.split(":", 1)
                    decl[k.strip().lower()] = v.strip().lower()
            if not decl:
                continue
            for parte in sel.split(","):
                m = _CLASSE_SIMPLES.match(parte.strip())
                if m:
                    fora.setdefault(m.group(1), {}).update(decl)
        # 🧪 controle do próprio instrumento: se o build deixar de trazer
        # `.hidden{display:none}`, TUDO aqui passaria a dizer "visível".
        assert fora.get("hidden", {}).get("display") == "none", (
            "o tailwind.min.css compilado não define .hidden{display:none} — "
            "o navegador da bancada perdeu a régua de visibilidade")
        _CSS_CACHE.update(fora)
    return _CSS_CACHE


# ── A ÁRVORE: pai escondido esconde o filho ───────────────────────────
_VAZIAS = {"AREA", "BASE", "BR", "COL", "EMBED", "HR", "IMG", "INPUT", "LINK",
           "META", "PARAM", "SOURCE", "TRACK", "WBR", "PATH", "CIRCLE", "RECT",
           "LINE", "POLYGON", "POLYLINE", "ELLIPSE", "USE", "STOP"}
_TAG_QUALQUER = re.compile(
    r"<(/?)([a-zA-Z][\w:-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*?)(/?)>")


def _sem_ruido(html):
    """Comentário, <script> e <style> viram espaço (as POSIÇÕES não mudam).

    🪤 O JS da tela escreve `'<div ...>'` dentro de string; sem apagar o
    script, a pilha de tags sairia torta.
    """
    for padrao in (r"<!--.*?-->",
                   r"<script\b[^>]*>.*?</script>",
                   r"<style\b[^>]*>.*?</style>"):
        html = re.sub(padrao, lambda m: " " * len(m.group(0)), html,
                      flags=re.S | re.I)
    return html


def ancestrais(html, pos):
    """As tags ABERTAS naquela posição, da mais externa pra mais interna."""
    pilha = []
    for m in _TAG_QUALQUER.finditer(_sem_ruido(html)):
        if m.start() >= pos:
            break
        fecha, nome = m.group(1), m.group(2).upper()
        if fecha:
            for k in range(len(pilha) - 1, -1, -1):
                if pilha[k][0] == nome:
                    del pilha[k:]
                    break
            continue
        if m.group(4) or nome in _VAZIAS:
            continue
        pilha.append((nome, dict(re.findall(r'([\w:-]+)="([^"]*)"', m.group(3))),
                      m.start()))
    return pilha


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
    """Os elementos pedidos + os ANCESTRAIS deles, na ordem do documento.

    🪤 06/09 (cético): sem a árvore, `<main class="hidden">` em volta da
    caixa deixava todo guarda de visibilidade verde. Cada spec ganha `pai`.
    """
    achados = []
    for i in ids:
        a = atributos(html, i)
        assert a is not None, (
            "o id %r não existe no HTML — o JS escreve nele e morre calado no "
            "catch (getElementById devolve null)" % i)
        a["id"] = i
        achados.append(a)
    achados = sorted(achados, key=lambda a: a["pos"])
    return _com_ancestrais(html, achados)


def _com_ancestrais(html, achados):
    por_pos = {a["pos"]: a for a in achados}
    extras = {}
    for a in achados:
        pai = None
        for nome, attrs, pos in ancestrais(html, a["pos"]):
            spec = por_pos.get(pos) or extras.get(pos)
            if spec is None:
                spec = {"tag": nome, "attrs": attrs, "pos": pos, "html": "",
                        "id": attrs.get("id") or ("__anc%d" % pos)}
                extras[pos] = spec
            spec["pai"] = pai
            pai = spec["id"]
        a["pai"] = pai
    return sorted(list(extras.values()) + achados, key=lambda x: x["pos"])


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
  this.style = { display: '', visibility: '', opacity: '' };
  var _st = this._attrs['style'] || '';
  /* nao so `display`: `visibility:hidden` e `opacity:0` somem igual */
  var _RXST = [['display', /(?:^|;)\s*display\s*:\s*([^;]+)/],
               ['visibility', /(?:^|;)\s*visibility\s*:\s*([^;]+)/],
               ['opacity', /(?:^|;)\s*opacity\s*:\s*([^;]+)/]];
  for (var _p = 0; _p < _RXST.length; _p++) {
    var _m = _RXST[_p][1].exec(_st);
    if (_m) this.style[_RXST[_p][0]] = _m[1].replace(/\s+$/, '');
  }
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
  var criados = [];
  for (var i = 0; i < specs.length; i++) {
    var el = new _El(specs[i]);
    if (!el.id) el.id = '__auto' + i;      // tag sem id ainda ocupa o documento
    __els[el.id] = el;
    __ordem.push(el);
    criados.push(el);
  }
  /* a ARVORE: pai escondido esconde o filho */
  for (var j = 0; j < specs.length; j++) {
    var pai = specs[j].pai;
    if (pai && __els[pai]) criados[j].parentNode = __els[pai];
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
/* O que o cliente VE. Junta, pra cada tag, as declaracoes das CLASSES (vindas
   do tailwind.min.css compilado, em __CSS) com o style inline, e responde. */
function _decl(el) {
  var fora = {}, cs = String(el.className || '').split(/\s+/), i, k;
  for (i = 0; i < cs.length; i++) {
    var d = cs[i] && __CSS[cs[i]];
    if (d) { for (k in d) fora[k] = d[k]; }
  }
  if (el.style.display) fora['display'] = String(el.style.display).toLowerCase();
  if (el.style.visibility) fora['visibility'] = String(el.style.visibility).toLowerCase();
  if (el.style.opacity !== '') fora['opacity'] = String(el.style.opacity).toLowerCase();
  return fora;
}
function _oculta(el) {
  if (!el) return false;
  var d = _decl(el);
  if (d['display'] === 'none') return true;                       /* .hidden */
  if (d['visibility'] === 'hidden' || d['visibility'] === 'collapse') return true;
  if (d['opacity'] === '0') return true;                          /* .opacity-0 */
  if (String(d['clip'] || '').replace(/\s+/g, '') === 'rect(0,0,0,0)') return true; /* .sr-only */
  var zero = function (v) { return v === '0' || v === '0px'; };
  if (String(d['overflow'] || '') === 'hidden'
      && (zero(d['height']) || zero(d['max-height'])
          || zero(d['width']) || zero(d['max-width']))) return true;
  return false;
}
function _visivel(id) {
  var el = __els[id];
  if (!el) return false;
  var no = el;
  while (no) {                        /* pai escondido esconde o filho */
    if (_oculta(no)) return false;
    no = no.parentNode;
  }
  return true;
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
    """O JS que constrói o documento a partir do que o HTML REAL declara.

    Vai junto o `__CSS`: as declarações do tailwind.min.css COMPILADO, que é
    quem sabe se uma classe esconde de verdade.
    """
    return (("var __CSS = %s;" + chr(10) + "_montar(%s);")
            % (json.dumps(css_declaracoes(), ensure_ascii=False),
               json.dumps(elementos_, ensure_ascii=False)))
