// ═══════════════════════════════════════════════════════════════════
// aiarq-utils.js — utilitários compartilhados entre HTMLs do AI.arq
// ═══════════════════════════════════════════════════════════════════
//
// Antes desse arquivo, cada HTML duplicava: SUPABASE_URL, anon key,
// API_BASE, cliente Supabase, authFetch, downloadProtected, escapeHtml.
// Risco: variável com nome diferente (sb vs sbClient — armadilha #6 do
// CLAUDE.md), fix-em-um-lugar-só, drift de implementação.
//
// Este arquivo expõe TUDO em `window.*` pra não dar conflito:
//   - window.sbClient (cliente Supabase oficial)
//   - window.sb       (alias compat — alguns HTMLs usam esse nome)
//   - window.API_BASE
//   - window.SUPABASE_URL
//   - window.SUPABASE_ANON_KEY
//   - window.authFetch(url, opts)
//   - window.downloadProtected(url, filename)
//   - window.openPdfProtected(url)   ← abre PDF em nova aba (não força download)
//   - window.escapeHtml(s)
//   - window.aiArqNotify              ← shim toast/alert
//
// Como usar nos HTMLs:
//   <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2" defer></script>
//   <script src="aiarq-utils.js" defer></script>
//
// IMPORTANTE: ambos com `defer` pra ordem ser preservada e rodarem só
// depois do DOM. Scripts que dependem de sbClient/authFetch também
// precisam usar `defer` ou ficar inline no fim do <body>.

(function () {
  'use strict';

  // ─── Constantes ───────────────────────────────────────────────
  // Supabase anon key é PÚBLICA por design — RLS protege o resto.
  // Source of truth: este arquivo. NÃO duplicar nos HTMLs.
  const SUPABASE_URL      = 'https://kqjabzwgbfuivzlcfvvu.supabase.co';
  const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI';
  const API_BASE          = 'https://ai-arq.onrender.com';

  window.SUPABASE_URL      = SUPABASE_URL;
  window.SUPABASE_ANON_KEY = SUPABASE_ANON_KEY;
  window.API_BASE          = API_BASE;

  // ─── Cliente Supabase ─────────────────────────────────────────
  // Defensivo: se o <script> do supabase-js não carregou (rede ruim,
  // CDN fora do ar), avisa no console em vez de quebrar tudo silenciosamente.
  if (!window.supabase || typeof window.supabase.createClient !== 'function') {
    console.error('[aiarq-utils] supabase-js não foi carregado antes deste script. ' +
                  'Inclua <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2" defer></script> ANTES de aiarq-utils.js.');
    return;
  }

  const _sbClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  // Expor com os DOIS nomes pra evitar armadilha #6: alguns HTMLs
  // historicamente chamam de `sb`, outros de `sbClient`. Mantém ambos
  // apontando pro mesmo cliente — refactor é zero-diff de comportamento.
  window.sbClient = _sbClient;
  window.sb       = _sbClient;

  // ─── Notificação (toast com fallback alert) ──────────────────
  // toast.js carrega via defer — se ainda não montou window.toast,
  // cai pro alert nativo. Bug Daniela 2026-05-18 mostrou que silenciar
  // erro de download é pior que feio.
  const notify = {
    warn:  (m) => (window.toast ? window.toast.warn(m)    : alert(m)),
    error: (m) => (window.toast ? window.toast.error(m)   : alert(m)),
    info:  (m) => (window.toast ? window.toast.info(m)    : alert(m)),
    ok:    (m) => (window.toast ? window.toast.success(m) : alert(m)),
  };
  window.aiArqNotify = notify;

  // ─── escapeHtml ──────────────────────────────────────────────
  // Versão mais defensiva (de revisao.html): aceita null/undefined
  // sem explodir (o `|| ''` na coerção).
  window.escapeHtml = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
    );
  };

  // ─── authFetch ───────────────────────────────────────────────
  // Fetch com Bearer do Supabase. Backend exige JWT em endpoints
  // com ownership check (/api/items, /api/projects, /api/admin/*, etc).
  window.authFetch = async function (url, options) {
    options = options || {};
    const { data: { session } } = await _sbClient.auth.getSession();
    const headers = Object.assign({}, options.headers || {});
    if (session && session.access_token) {
      headers['Authorization'] = 'Bearer ' + session.access_token;
    }
    return fetch(url, Object.assign({}, options, { headers }));
  };

  // ─── downloadProtected ───────────────────────────────────────
  // Baixa endpoint protegido enviando Authorization header. Armadilha #9
  // do CLAUDE.md: <a href>, window.open() e window.location.href NÃO
  // enviam header customizado → backend retorna 401 mesmo com sessão
  // válida (bug Daniela 2026-05-18). Solução: fetch com Bearer → blob →
  // <a> programático → cleanup do object URL.
  window.downloadProtected = async function (url, filename) {
    const { data: { session } } = await _sbClient.auth.getSession();
    if (!session) {
      notify.warn('Sua sessão expirou. Faça login de novo pra baixar.');
      window.location.href = 'login.html';
      return;
    }
    try {
      const resp = await fetch(url, {
        headers: { 'Authorization': 'Bearer ' + session.access_token }
      });
      if (!resp.ok) {
        let detail = 'HTTP ' + resp.status;
        try { const j = await resp.json(); detail = j.detail || detail; } catch (_) {}
        notify.error('Não consegui baixar o arquivo: ' + detail);
        return;
      }
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = filename || 'arquivo';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Pequeno delay pro browser começar o download antes do GC.
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    } catch (e) {
      notify.error('Erro de rede ao baixar: ' + (e && e.message ? e.message : e));
    }
  };
  // Alias usado em templates inline com onclick (dashboard.html).
  window.aiArqDownloadProtected = window.downloadProtected;

  // ─── openPdfProtected ────────────────────────────────────────
  // Abre PDF protegido em nova aba (em vez de forçar download).
  // Bug 2026-06-02: mesmo problema do downloadProtected — endpoint
  // protegido não pode ser aberto via <a href>/target="_blank". Solução:
  // fetch com Bearer → blob URL → window.open na blob URL.
  window.openPdfProtected = async function (url) {
    const { data: { session } } = await _sbClient.auth.getSession();
    if (!session) {
      notify.warn('Sua sessão expirou. Faça login de novo pra abrir.');
      window.location.href = 'login.html';
      return;
    }
    try {
      const resp = await fetch(url, {
        headers: { 'Authorization': 'Bearer ' + session.access_token }
      });
      if (!resp.ok) {
        let detail = 'HTTP ' + resp.status;
        try { const j = await resp.json(); detail = j.detail || detail; } catch (_) {}
        notify.error('Não consegui abrir o PDF: ' + detail);
        return;
      }
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      window.open(blobUrl, '_blank', 'noopener');
      // 60s pra dar tempo do browser carregar o PDF antes de revogar.
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    } catch (e) {
      notify.error('Erro de rede ao abrir: ' + (e && e.message ? e.message : e));
    }
  };

  // ─── Origem (first-touch attribution) ────────────────────────
  // Guarda UMA VEZ de onde o visitante chegou (referrer + UTM/?origem=).
  // First-party (só localStorage, zero 3rd-party). Usado no cadastro pra
  // atribuir a conta e, com consentimento, no funil. NÃO sobrescreve — o
  // PRIMEIRO toque é o que conta (a pessoa pode navegar antes de cadastrar).
  function _classifyRef(host) {
    if (!host) return '';
    host = host.toLowerCase();
    if (/instagram|l\.instagram|ig\./.test(host)) return 'instagram';
    if (/wa\.me|whatsapp/.test(host)) return 'whatsapp';
    if (/t\.me|telegram/.test(host)) return 'telegram';
    if (/google\./.test(host)) return 'google';
    if (/bing\.|duckduckgo|search\.yahoo/.test(host)) return 'busca';
    if (/facebook|fb\.me|\bfb\./.test(host)) return 'facebook';
    if (/linkedin|lnkd\.in/.test(host)) return 'linkedin';
    if (/youtube|youtu\.be/.test(host)) return 'youtube';
    if (/ai\.arq\.br/.test(host)) return '';   // navegação interna, ignora
    return host.replace(/^www\./, '');
  }
  (function _captureSource() {
    try {
      if (localStorage.getItem('aiarq_src')) return;   // first-touch: não sobrescreve
      var params = new URLSearchParams(location.search || '');
      var utm_source = (params.get('utm_source') || params.get('origem') || '').slice(0, 40);
      var utm_medium = (params.get('utm_medium') || '').slice(0, 40);
      var utm_campaign = (params.get('utm_campaign') || params.get('campanha') || '').slice(0, 60);
      var refHost = '';
      try { if (document.referrer) refHost = new URL(document.referrer).hostname; } catch (e) {}
      var label = utm_source || _classifyRef(refHost) || (refHost ? refHost.replace(/^www\./, '') : 'direto');
      localStorage.setItem('aiarq_src', JSON.stringify({
        label: String(label).slice(0, 40),
        utm_source: utm_source, utm_medium: utm_medium, utm_campaign: utm_campaign,
        ref: refHost.slice(0, 80), landing: (location.pathname || '').slice(0, 80),
      }));
    } catch (e) { /* nunca quebra nada */ }
  })();
  window.aiArqSource = function () {
    try { return JSON.parse(localStorage.getItem('aiarq_src') || 'null'); } catch (e) { return null; }
  };

  // ─── trackEvent ──────────────────────────────────────────────
  // Telemetria leve de uso (Painel de Atividade no admin). Fire-and-forget:
  // nunca bloqueia a UI, nunca lança. POST /api/track → grava em usage_events
  // (RLS on, só o backend lê). Sem ferramenta de 3rd-party (LGPD tranquilo).
  //   trackEvent('open_project', { job_id: '...' })
  window.trackEvent = function (event, meta) {
    try {
      if (!event) return;
      // LGPD (opt-in do banner de cookies): SÓ rastreia se o usuário consentiu
      // com analytics. Sem consentimento — declinado OU ainda não respondido —
      // não grava nada. Honra a promessa "telemetria só com seu sim".
      try {
        var _consent = JSON.parse(localStorage.getItem('aiarq_cookie_consent') || 'null');
        if (!_consent || _consent.analytics !== true) return;
      } catch (e) { return; }
      // cid = id anônimo do navegador (localStorage) → dá pra contar VISITANTE
      // único e seguir o funil (visita → cadastro) mesmo sem login.
      let _cid = '';
      try {
        _cid = localStorage.getItem('aiarq_cid') || '';
        if (!_cid) { _cid = 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10); localStorage.setItem('aiarq_cid', _cid); }
      } catch (e) { /* localStorage indisponível */ }
      // src = origem first-touch (de onde o visitante chegou) — pra atribuir o funil
      let _src = '';
      try { var _s0 = JSON.parse(localStorage.getItem('aiarq_src') || 'null'); _src = (_s0 && _s0.label) ? String(_s0.label).slice(0, 40) : ''; } catch (e) {}
      _sbClient.auth.getSession().then(({ data: { session } }) => {
        const u = (session && session.user) ? session.user : null;
        const body = JSON.stringify({
          event: String(event).slice(0, 60),
          user_id: u ? u.id : '',
          user_email: u ? (u.email || '') : '',
          job_id: (meta && meta.job_id) ? String(meta.job_id) : '',
          path: (location.pathname || '').slice(0, 200),
          meta: Object.assign({ cid: _cid, src: _src }, meta || {}),
        });
        // keepalive: o evento sobrevive mesmo se a página for fechada logo
        // após (ex.: clicou em baixar e saiu). Erro engolido de propósito.
        fetch(API_BASE + '/api/track', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: body,
          keepalive: true,
        }).catch(() => {});
      }).catch(() => {});
    } catch (e) { /* telemetria nunca quebra nada */ }
  };
})();

// ═══════════════════════════════════════════════════════════════════
// 🌙 MODO ESCURO — sistema único pra TODAS as páginas (todas carregam este arquivo).
// Remapeia as cores base do Tailwind via CSS com seletores de atributo
// [class~="..."] (não precisa de dark: em cada elemento) + botão flutuante +
// memória da preferência (localStorage 'aiarq_theme' / prefers-color-scheme).
// Badges/gradientes/botões coloridos ficam vibrantes; só as superfícies
// brancas/cinzas e o texto viram escuros. Pedro é daltônico → contraste alto.
// ═══════════════════════════════════════════════════════════════════
(function () {
  'use strict';
  // Paleta: cor → [texto claro no escuro, rgb pra fundos translúcidos]
  var C = {
    indigo:['#a5b4fc','99,102,241'], blue:['#93c5fd','59,130,246'], sky:['#7dd3fc','56,189,248'],
    cyan:['#67e8f9','34,211,238'], teal:['#5eead4','20,184,166'], emerald:['#6ee7b7','16,185,129'],
    green:['#86efac','34,197,94'], lime:['#bef264','132,204,22'], amber:['#fcd34d','245,158,11'],
    orange:['#fdba74','249,115,22'], yellow:['#fde68a','234,179,8'], red:['#fca5a5','239,68,68'],
    rose:['#fda4af','244,63,94'], pink:['#f9a8d4','236,72,153'], purple:['#d8b4fe','168,85,247'],
    violet:['#c4b5fd','139,92,246'], fuchsia:['#f0abfc','217,70,239']
  };
  var R = [
    'html.dark{color-scheme:dark;}',
    'html.dark body{background-color:#0f0f12;color:#e5e7eb;}',
    // superfícies brancas (+ opacidade) → escuro
    'html.dark [class~="bg-white"],html.dark [class~="bg-white/95"],html.dark [class~="bg-white/90"],html.dark [class~="bg-white/80"]{background-color:#1a1a1e !important;}',
    'html.dark [class~="bg-white/70"],html.dark [class~="bg-white/60"],html.dark [class~="bg-white/50"]{background-color:rgba(26,26,30,.6) !important;}',
    // cinzas de fundo → escuro; chip cinza-200 → tom médio distinto
    'html.dark [class~="bg-gray-50"],html.dark [class~="bg-gray-100"],html.dark [class~="bg-gray-50/40"],html.dark [class~="bg-gray-50/50"],html.dark [class~="bg-gray-50/60"],html.dark [class~="bg-slate-50"],html.dark [class~="bg-slate-100"]{background-color:#131316 !important;}',
    'html.dark [class~="bg-gray-200"],html.dark [class~="bg-slate-200"]{background-color:#33333a !important;}',
    // texto cinza → claro
    'html.dark [class~="text-gray-900"],html.dark [class~="text-slate-900"]{color:#f3f4f6 !important;}',
    'html.dark [class~="text-gray-800"],html.dark [class~="text-slate-800"]{color:#e5e7eb !important;}',
    'html.dark [class~="text-gray-700"],html.dark [class~="text-slate-700"]{color:#d1d5db !important;}',
    'html.dark [class~="text-gray-600"],html.dark [class~="text-slate-600"]{color:#b8c2d0 !important;}',
    'html.dark [class~="text-gray-500"],html.dark [class~="text-slate-500"]{color:#9aa6b5 !important;}',
    'html.dark [class~="text-gray-400"],html.dark [class~="text-slate-400"]{color:#7f8b9b !important;}',
    // bordas cinza
    'html.dark [class~="border"],html.dark [class~="border-2"],html.dark [class~="border-gray-100"],html.dark [class~="border-gray-200"],html.dark [class~="border-gray-300"],html.dark [class~="border-slate-100"],html.dark [class~="border-slate-200"],html.dark [class~="border-b"],html.dark [class~="border-t"]{border-color:#2b2b31 !important;}',
    'html.dark [class~="divide-y"]>*,html.dark [class~="divide-gray-100"]>*,html.dark [class~="divide-gray-200"]>*,html.dark [class~="divide-indigo-100"]>*{border-color:#2b2b31 !important;}',
    // inputs + hovers
    'html.dark input,html.dark textarea,html.dark select{background-color:#131316 !important;color:#e5e7eb !important;border-color:#33333a !important;}',
    'html.dark input::placeholder,html.dark textarea::placeholder{color:#64748b !important;}',
    'html.dark [class~="hover:bg-gray-50"]:hover,html.dark [class~="hover:bg-gray-100"]:hover{background-color:#26262c !important;}',
    // gradientes pra branco → escuro
    'html.dark [class~="to-white"]{--tw-gradient-to:#1a1a1e !important;}',
    'html.dark [class~="from-white"]{--tw-gradient-from:#1a1a1e !important;--tw-gradient-stops:var(--tw-gradient-from),var(--tw-gradient-to) !important;}',
    'html.dark [class~="gradient-hero"]{background:linear-gradient(180deg,#131316 0%,#0f0f12 100%) !important;}',
    // card destacado da precos (borda gradiente via style inline com fill branco)
    'html.dark [style*="linear-gradient(white, white)"],html.dark [style*="linear-gradient(white,white)"]{background-image:linear-gradient(#1a1a1e,#1a1a1e),linear-gradient(135deg,#4f46e5,#06b6d4) !important;}',
    // botão do toggle
    '#aiarq-theme-toggle{position:fixed;left:16px;bottom:16px;z-index:60;width:44px;height:44px;border-radius:9999px;display:flex;align-items:center;justify-content:center;border:1px solid #d1d5db;background:#fff;color:#374151;box-shadow:0 4px 14px rgba(0,0,0,.15);cursor:pointer;font-size:20px;line-height:1;transition:transform .15s,background .2s;}',
    '#aiarq-theme-toggle:hover{transform:scale(1.08);}',
    'html.dark #aiarq-theme-toggle{background:#26262c !important;color:#fbbf24 !important;border-color:#33333a !important;}'
  ];
  // Gera por cor: fundos/chips tingidos → escuro translúcido; texto colorido →
  // claro (legível no escuro E nos chips escurecidos); gradientes e bordas.
  Object.keys(C).forEach(function (k) {
    var lt = C[k][0], rgb = C[k][1];
    R.push('html.dark [class~="bg-' + k + '-50"],html.dark [class~="bg-' + k + '-100"],html.dark [class~="bg-' + k + '-50/40"],html.dark [class~="bg-' + k + '-50/50"],html.dark [class~="bg-' + k + '-50/60"],html.dark [class~="bg-' + k + '-100/50"]{background-color:rgba(' + rgb + ',.16) !important;}');
    R.push('html.dark [class~="text-' + k + '-600"],html.dark [class~="text-' + k + '-700"],html.dark [class~="text-' + k + '-800"],html.dark [class~="text-' + k + '-900"]{color:' + lt + ' !important;}');
    R.push('html.dark [class~="from-' + k + '-50"],html.dark [class~="from-' + k + '-50/50"]{--tw-gradient-from:rgba(' + rgb + ',.14) !important;--tw-gradient-stops:var(--tw-gradient-from),var(--tw-gradient-to) !important;}');
    R.push('html.dark [class~="to-' + k + '-50"],html.dark [class~="to-' + k + '-50/50"]{--tw-gradient-to:rgba(' + rgb + ',.14) !important;}');
    R.push('html.dark [class~="border-' + k + '-100"],html.dark [class~="border-' + k + '-200"],html.dark [class~="border-' + k + '-300"]{border-color:rgba(' + rgb + ',.35) !important;}');
  });
  var CSS = R.join('\n');

  try {
    var st = document.createElement('style');
    st.id = 'aiarq-theme-css';
    st.textContent = CSS;
    (document.head || document.documentElement).appendChild(st);
  } catch (e) { return; }

  function saved() { try { return localStorage.getItem('aiarq_theme'); } catch (e) { return null; } }
  function prefersDark() { try { return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches; } catch (e) { return false; } }
  function apply(mode) {
    var dark = mode === 'dark';
    document.documentElement.classList.toggle('dark', dark);
    var b = document.getElementById('aiarq-theme-toggle');
    if (b) {
      b.textContent = dark ? '☀️' : '🌙';
      b.setAttribute('aria-label', dark ? 'Mudar para o modo claro' : 'Mudar para o modo escuro');
      b.title = dark ? 'Modo claro' : 'Modo escuro';
    }
  }
  apply(saved() || (prefersDark() ? 'dark' : 'light'));

  function mount() {
    if (document.getElementById('aiarq-theme-toggle') || !document.body) return;
    var btn = document.createElement('button');
    btn.id = 'aiarq-theme-toggle';
    btn.type = 'button';
    btn.addEventListener('click', function () {
      var next = document.documentElement.classList.contains('dark') ? 'light' : 'dark';
      try { localStorage.setItem('aiarq_theme', next); } catch (e) {}
      apply(next);
    });
    document.body.appendChild(btn);
    apply(document.documentElement.classList.contains('dark') ? 'dark' : 'light');
  }
  if (document.body) mount();
  else document.addEventListener('DOMContentLoaded', mount);
})();
