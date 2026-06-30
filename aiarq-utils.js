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

  // ─── trackEvent ──────────────────────────────────────────────
  // Telemetria leve de uso (Painel de Atividade no admin). Fire-and-forget:
  // nunca bloqueia a UI, nunca lança. POST /api/track → grava em usage_events
  // (RLS on, só o backend lê). Sem ferramenta de 3rd-party (LGPD tranquilo).
  //   trackEvent('open_project', { job_id: '...' })
  window.trackEvent = function (event, meta) {
    try {
      if (!event) return;
      _sbClient.auth.getSession().then(({ data: { session } }) => {
        const u = (session && session.user) ? session.user : null;
        const body = JSON.stringify({
          event: String(event).slice(0, 60),
          user_id: u ? u.id : '',
          user_email: u ? (u.email || '') : '',
          job_id: (meta && meta.job_id) ? String(meta.job_id) : '',
          path: (location.pathname || '').slice(0, 200),
          meta: meta || {},
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
