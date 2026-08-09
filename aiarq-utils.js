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
  // API geral passa pelo Cloudflare (proxy laranja em api.ai.arq.br → protege,
  // esconde origem, permite rate-limit). 23/07.
  const API_BASE          = 'https://api.ai.arq.br';
  // 🪤 UPLOAD DE CAD vai DIRETO pro Render, FORA do Cloudflare: o backend aceita
  // até 450 MB (main.py:5970, projetos grandes), mas o Cloudflare Free CORTA em
  // 100 MB — passar upload grande pelo proxy daria 413 antes de chegar no backend.
  // Use API_UPLOAD_BASE em /api/process e /api/project/{id}/add-file. Só esses.
  const API_UPLOAD_BASE   = 'https://ai-arq.onrender.com';

  window.SUPABASE_URL      = SUPABASE_URL;
  window.SUPABASE_ANON_KEY = SUPABASE_ANON_KEY;
  window.API_BASE          = API_BASE;
  window.API_UPLOAD_BASE   = API_UPLOAD_BASE;

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

  // ─── Impressão digital de e-mail ─────────────────────────────
  // 28/07: o repositório é PÚBLICO. Antes, e-mails de pessoas reais
  // (admin e testadores) ficavam em texto claro nos HTMLs — qualquer um
  // lia. Agora comparamos pelo hash SHA-256.
  //
  // ⚠️ Isto NÃO é controle de segurança: hash de e-mail é conferível por
  // quem já conhece o endereço. Serve pra não EXPOR o dado pessoal.
  // A autorização de verdade é sempre no backend (`_require_admin`).
  window.aiarqEmailHash = async function (email) {
    const norm = String(email == null ? '' : email).trim().toLowerCase();
    if (!norm || !window.crypto || !crypto.subtle) return '';
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(norm));
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
  };

  // Confere se o e-mail bate com um hash ou com uma lista de hashes.
  window.aiarqEmailMatches = async function (email, hashes) {
    const h = await window.aiarqEmailHash(email);
    if (!h) return false;
    return (Array.isArray(hashes) ? hashes : [hashes]).includes(h);
  };

  // ─── escapeHtml ──────────────────────────────────────────────
  // Versão mais defensiva (de revisao.html): aceita null/undefined
  // sem explodir (o `|| ''` na coerção).
  window.escapeHtml = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
    );
  };

  // ─── Nome do projeto pra exibir ──────────────────────────────
  // O cliente digita "teste 22/07" e a tela mostrava assim, minúsculo, em
  // título, no menu e no cartão. Fica feio.
  //
  // 🚨 SÓ NA EXIBIÇÃO. Nunca grave isto de volta: o nome é dado DELE, e
  // reescrever o que ele digitou é mexer no dado do cliente. Aqui é maquiagem
  // de vitrine, e some se ele renomear.
  //
  // 🪤 Sobe só a PRIMEIRA letra e não encosta no resto. Nada de Title Case:
  // "ConfortAr — Expansão HSM" viraria "Confortar — Expansão Hsm", e "HSM",
  // "FF&E", "AVAC" são siglas que o cliente escreveu de propósito.
  // Nome que começa com número ("22/07 teste") não tem o que capitalizar.
  window.tituloProjeto = function (nome) {
    var s = String(nome == null ? '' : nome).trim();
    if (!s) return 'Projeto sem nome';
    // Acha a primeira letra de verdade (pula aspas, hífen, número, emoji).
    var i = s.search(/[a-zA-ZÀ-ÿ]/);
    if (i === -1) return s;
    var c = s[i];
    if (c === c.toUpperCase()) return s;      // já está maiúscula: não mexe
    return s.slice(0, i) + c.toUpperCase() + s.slice(i + 1);
  };

  // ─── Datas/horas em horário de Brasília ──────────────────────
  // Postgres/Supabase guardam TUDO em UTC (timestamptz). Se a gente formatar
  // com toLocaleString SEM fixar o fuso, ele usa o RELÓGIO DO NAVEGADOR — muda
  // de máquina pra máquina e, dependendo da config, mostra UTC (+3h) em vez de
  // Brasília. Aqui fixamos America/Sao_Paulo pra TODO horário do sistema bater
  // com o de Brasília, em qualquer navegador (o do Pedro, de um cliente, etc).
  //   fmtBR(iso)                       → "16/07 15:32"
  //   fmtBR(iso, { year:'numeric' })   → acrescenta o ano
  //   fmtDataBR(iso)                   → só a data "16/07/2026"
  // O timeZone é aplicado POR ÚLTIMO de propósito: o caller escolhe o formato,
  // mas nunca troca o fuso — sistema inteiro em Brasília, sem exceção.
  const _TZ_BR = 'America/Sao_Paulo';
  window.fmtBR = function (iso, opts) {
    if (iso == null || iso === '') return '';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso);   // data inválida → devolve cru, nunca "Invalid Date"
      const o = Object.assign(
        { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' },
        opts || {}, { timeZone: _TZ_BR });
      return d.toLocaleString('pt-BR', o);
    } catch (e) { return String(iso); }
  };
  window.fmtDataBR = function (iso, opts) {
    if (iso == null || iso === '') return '';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso);
      const o = Object.assign({}, opts || {}, { timeZone: _TZ_BR });
      return d.toLocaleDateString('pt-BR', o);
    } catch (e) { return String(iso); }
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
    if (/ai\.arq\.br/.test(host)) return 'direto';   // navegação interna → 'direto' (antes voltava '' e o fallback gravava 'ai.arq.br' como origem)
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
        // 🚨 Manda o token quando há sessão (09/08). O backend passou a IGNORAR
        // user_id/user_email do corpo e só aceitar identidade que o token prove
        // — sem este header, todo evento de quem está logado viraria anônimo e
        // o painel de Atividade esvaziaria. Deslogado segue sem header, que é o
        // caso normal aqui: a rota é aberta de propósito.
        const _h = { 'Content-Type': 'application/json' };
        if (session && session.access_token) {
          _h['Authorization'] = 'Bearer ' + session.access_token;
        }
        // keepalive: o evento sobrevive mesmo se a página for fechada logo
        // após (ex.: clicou em baixar e saiu). Erro engolido de propósito.
        fetch(API_BASE + '/api/track', {
          method: 'POST',
          headers: _h,
          body: body,
          keepalive: true,
        }).catch(() => {});
      }).catch(() => {});
    } catch (e) { /* telemetria nunca quebra nada */ }
  };
})();
