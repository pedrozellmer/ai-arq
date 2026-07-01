/**
 * AI.arq — Banner de consentimento de cookies LGPD
 *
 * Mostra banner sticky no rodapé enquanto o usuário não escolher.
 * Persiste a escolha em localStorage["aiarq_cookie_consent"].
 *
 * Categorias:
 *   - Essenciais: sempre ON, não editável (Supabase auth, preferências locais)
 *   - Analytics/Telemetria: opt-in
 *
 * Acessibilidade:
 *   - role=dialog, aria-modal=false (não bloqueia interação, é sticky no rodapé)
 *   - aria-labelledby e aria-describedby
 *   - foco inicial no botão primário "Aceitar todos"
 *   - ESC fecha como "Só essenciais"
 *   - Daltônico-safe: cor + ícone + texto em cada estado
 *
 * Pode ser reaberto: window.aiarqCookieConsent.open()
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'aiarq_cookie_consent';
  var POLICY_URL = '/privacidade.html';

  // -----------------------------------------------------------------------
  // Estado
  // -----------------------------------------------------------------------

  function readConsent() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var data = JSON.parse(raw);
      if (!data || typeof data !== 'object') return null;
      return data;
    } catch (err) {
      return null;
    }
  }

  function saveConsent(prefs) {
    try {
      var payload = {
        essenciais: true, // sempre on (mantém sessão)
        analytics: !!prefs.analytics,
        timestamp: new Date().toISOString(),
        version: 1
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
      // Dispara evento pro resto do site reagir (ex: ativar/desativar telemetria depois)
      try {
        window.dispatchEvent(new CustomEvent('aiarq:consent-changed', { detail: payload }));
      } catch (err) { /* IE/Edge antigos */ }
      return payload;
    } catch (err) {
      return null;
    }
  }

  // -----------------------------------------------------------------------
  // UI
  // -----------------------------------------------------------------------

  var bannerEl = null;
  var lastFocusedBeforeOpen = null;

  function buildBanner() {
    var wrap = document.createElement('div');
    wrap.id = 'aiarq-cookie-consent';
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-modal', 'false');
    wrap.setAttribute('aria-labelledby', 'aiarq-cc-title');
    wrap.setAttribute('aria-describedby', 'aiarq-cc-desc');
    wrap.style.cssText = [
      'position:fixed',
      'left:0',
      'right:0',
      'bottom:0',
      'z-index:9999',
      'background:#f8fafc', // slate-50
      'border-top:1px solid #cbd5e1', // slate-300
      'box-shadow:0 -8px 30px -10px rgba(15,23,42,0.18)',
      'font-family:Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif',
      'color:#0f172a', // slate-900
      'padding:16px',
      'animation:aiarqCcSlide 240ms ease-out'
    ].join(';');

    wrap.innerHTML = renderModeSimples();
    return wrap;
  }

  // ícone cookie SVG (sem depender de cor pra significar coisa)
  var ICON_COOKIE = '<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a10 10 0 1 0 10 10 4 4 0 0 1-5-5 4 4 0 0 1-5-5"/><path d="M8.5 8.5h.01"/><path d="M15.5 9.5h.01"/><path d="M10.5 14.5h.01"/><path d="M15 14.5h.01"/><path d="M11 11.5h.01"/></svg>';
  var ICON_SHIELD = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
  var ICON_CHART = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>';
  var ICON_CHECK = '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
  var ICON_LOCK = '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';

  function renderModeSimples() {
    return [
      '<div style="max-width:1100px;margin:0 auto;display:flex;flex-wrap:wrap;align-items:center;gap:16px;">',
        '<div style="display:flex;align-items:flex-start;gap:12px;flex:1 1 320px;min-width:240px;">',
          '<div style="color:#475569;flex-shrink:0;margin-top:2px;">', ICON_COOKIE, '</div>',
          '<div>',
            '<p id="aiarq-cc-title" style="margin:0 0 4px;font-size:14px;font-weight:600;color:#0f172a;">Cookies e telemetria</p>',
            '<p id="aiarq-cc-desc" style="margin:0;font-size:13px;line-height:1.5;color:#475569;">',
              'Usamos cookies <strong>essenciais</strong> pra manter sua sessão (login Supabase). ',
              'Com seu sim, coletamos <strong>telemetria de uso</strong> pra melhorar a plataforma — anônima nas páginas públicas e vinculada à sua conta quando você está logado. ',
              '<a href="', POLICY_URL, '" style="color:#4f46e5;text-decoration:underline;font-weight:500;">Política de Privacidade</a>.',
            '</p>',
          '</div>',
        '</div>',
        '<div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;flex:0 0 auto;">',
          btn('Personalizar', 'aiarq-cc-customize', 'secondary'),
          btn('Só essenciais', 'aiarq-cc-essentials', 'secondary'),
          btn('Aceitar todos', 'aiarq-cc-accept-all', 'primary'),
        '</div>',
      '</div>'
    ].join('');
  }

  function renderModePersonalizar() {
    return [
      '<div style="max-width:1100px;margin:0 auto;">',
        '<div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:12px;">',
          '<div style="color:#475569;flex-shrink:0;margin-top:2px;">', ICON_COOKIE, '</div>',
          '<div style="flex:1;">',
            '<p id="aiarq-cc-title" style="margin:0 0 4px;font-size:14px;font-weight:600;color:#0f172a;">Personalizar consentimento</p>',
            '<p id="aiarq-cc-desc" style="margin:0;font-size:13px;line-height:1.5;color:#475569;">',
              'Escolha quais categorias autorizar. Mais detalhes na ',
              '<a href="', POLICY_URL, '" style="color:#4f46e5;text-decoration:underline;font-weight:500;">Política de Privacidade</a>.',
            '</p>',
          '</div>',
        '</div>',

        // Categoria: Essenciais (sempre on, não editável)
        '<div style="border:1px solid #e2e8f0;background:#ffffff;border-radius:8px;padding:12px 14px;margin-bottom:8px;display:flex;align-items:flex-start;gap:12px;">',
          '<div style="color:#0f766e;flex-shrink:0;margin-top:2px;">', ICON_SHIELD, '</div>',
          '<div style="flex:1;">',
            '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">',
              '<p style="margin:0;font-size:13px;font-weight:600;color:#0f172a;">Essenciais</p>',
              // Indicador de estado: cor + ícone + texto
              '<span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:600;color:#0f766e;background:#ccfbf1;padding:2px 8px;border-radius:999px;">',
                ICON_LOCK, ' Sempre ativo',
              '</span>',
            '</div>',
            '<p style="margin:4px 0 0;font-size:12px;line-height:1.5;color:#64748b;">Cookies de autenticação Supabase e preferências locais (idioma, tour de onboarding). Sem esses, o login não funciona.</p>',
          '</div>',
        '</div>',

        // Categoria: Analytics (opt-in)
        '<label for="aiarq-cc-analytics" style="display:flex;align-items:flex-start;gap:12px;border:1px solid #e2e8f0;background:#ffffff;border-radius:8px;padding:12px 14px;margin-bottom:12px;cursor:pointer;">',
          '<div style="color:#475569;flex-shrink:0;margin-top:2px;">', ICON_CHART, '</div>',
          '<div style="flex:1;">',
            '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">',
              '<p style="margin:0;font-size:13px;font-weight:600;color:#0f172a;">Analytics / Telemetria</p>',
              '<input id="aiarq-cc-analytics" type="checkbox" style="width:18px;height:18px;accent-color:#4f46e5;cursor:pointer;" aria-describedby="aiarq-cc-analytics-desc">',
            '</div>',
            '<p id="aiarq-cc-analytics-desc" style="margin:4px 0 0;font-size:12px;line-height:1.5;color:#64748b;">Métricas de uso (páginas visitadas, cliques). Anônimas nas páginas públicas; quando você está logado, ficam vinculadas à sua conta pra melhorar o produto.</p>',
          '</div>',
        '</label>',

        '<div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;">',
          btn('Voltar', 'aiarq-cc-back', 'ghost'),
          btn('Salvar escolha', 'aiarq-cc-save', 'primary'),
        '</div>',
      '</div>'
    ].join('');
  }

  function btn(label, id, variant) {
    var styles = {
      primary: 'background:#4f46e5;color:#ffffff;border:1px solid #4f46e5;',
      secondary: 'background:#ffffff;color:#334155;border:1px solid #cbd5e1;',
      ghost: 'background:transparent;color:#475569;border:1px solid transparent;'
    };
    var base = 'font-family:inherit;font-size:13px;font-weight:600;padding:8px 14px;border-radius:6px;cursor:pointer;transition:filter 120ms ease,box-shadow 120ms ease;line-height:1.2;';
    return '<button type="button" id="' + id + '" style="' + base + styles[variant] + '">' + label + '</button>';
  }

  // -----------------------------------------------------------------------
  // Handlers
  // -----------------------------------------------------------------------

  function applyModeSimples() {
    bannerEl.innerHTML = renderModeSimples();
    wireSimples();
    focusFirstButton('aiarq-cc-accept-all');
  }

  function applyModePersonalizar() {
    bannerEl.innerHTML = renderModePersonalizar();
    // Pré-marca conforme escolha anterior, se houver
    var prev = readConsent();
    var cb = document.getElementById('aiarq-cc-analytics');
    if (cb && prev) cb.checked = !!prev.analytics;
    wirePersonalizar();
    // Foco no checkbox (primeira coisa interativa que ele veio mudar)
    if (cb) cb.focus();
  }

  function wireSimples() {
    var $accept = document.getElementById('aiarq-cc-accept-all');
    var $only = document.getElementById('aiarq-cc-essentials');
    var $custom = document.getElementById('aiarq-cc-customize');

    if ($accept) $accept.addEventListener('click', function () { decide({ analytics: true }); });
    if ($only) $only.addEventListener('click', function () { decide({ analytics: false }); });
    if ($custom) $custom.addEventListener('click', applyModePersonalizar);

    addHoverFx([$accept, $only, $custom]);
  }

  function wirePersonalizar() {
    var $save = document.getElementById('aiarq-cc-save');
    var $back = document.getElementById('aiarq-cc-back');
    var $analytics = document.getElementById('aiarq-cc-analytics');

    if ($save) $save.addEventListener('click', function () {
      decide({ analytics: $analytics && $analytics.checked });
    });
    if ($back) $back.addEventListener('click', applyModeSimples);

    addHoverFx([$save, $back]);
  }

  function addHoverFx(els) {
    els.forEach(function (el) {
      if (!el) return;
      el.addEventListener('mouseenter', function () { el.style.filter = 'brightness(0.95)'; });
      el.addEventListener('mouseleave', function () { el.style.filter = ''; });
      el.addEventListener('focus', function () { el.style.boxShadow = '0 0 0 3px rgba(79,70,229,0.35)'; });
      el.addEventListener('blur', function () { el.style.boxShadow = ''; });
    });
  }

  function decide(prefs) {
    saveConsent(prefs);
    close();
  }

  function focusFirstButton(id) {
    setTimeout(function () {
      var el = document.getElementById(id);
      if (el && typeof el.focus === 'function') el.focus();
    }, 50);
  }

  // -----------------------------------------------------------------------
  // Abrir / fechar
  // -----------------------------------------------------------------------

  function injectStyles() {
    if (document.getElementById('aiarq-cc-style')) return;
    var st = document.createElement('style');
    st.id = 'aiarq-cc-style';
    st.textContent = [
      '@keyframes aiarqCcSlide { from { transform: translateY(100%); opacity: 0; } to { transform: translateY(0); opacity: 1; } }',
      '@media (prefers-reduced-motion: reduce) { #aiarq-cookie-consent { animation: none !important; } }',
      '#aiarq-cookie-consent *:focus-visible { outline: 2px solid #4f46e5; outline-offset: 2px; }'
    ].join('\n');
    document.head.appendChild(st);
  }

  function open() {
    if (bannerEl) return; // já aberto
    injectStyles();
    lastFocusedBeforeOpen = document.activeElement;
    bannerEl = buildBanner();
    document.body.appendChild(bannerEl);
    wireSimples();
    focusFirstButton('aiarq-cc-accept-all');
    document.addEventListener('keydown', onKeydown, true);
  }

  function close() {
    document.removeEventListener('keydown', onKeydown, true);
    if (bannerEl && bannerEl.parentNode) {
      bannerEl.parentNode.removeChild(bannerEl);
    }
    bannerEl = null;
    // Restaura foco anterior pra leitor de tela
    if (lastFocusedBeforeOpen && typeof lastFocusedBeforeOpen.focus === 'function') {
      try { lastFocusedBeforeOpen.focus(); } catch (err) { /* noop */ }
    }
    lastFocusedBeforeOpen = null;
  }

  function onKeydown(ev) {
    if (ev.key === 'Escape' || ev.keyCode === 27) {
      ev.stopPropagation();
      ev.preventDefault();
      // ESC = "Só essenciais" (mais conservador, default LGPD)
      decide({ analytics: false });
    }
  }

  // -----------------------------------------------------------------------
  // API pública
  // -----------------------------------------------------------------------

  window.aiarqCookieConsent = {
    open: function () { open(); },
    close: close,
    get: readConsent,
    reset: function () {
      try { localStorage.removeItem(STORAGE_KEY); } catch (err) { /* noop */ }
      open();
    }
  };

  // -----------------------------------------------------------------------
  // Auto-init
  // -----------------------------------------------------------------------

  function maybeAutoOpen() {
    if (readConsent()) return; // já escolheu
    open();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', maybeAutoOpen);
  } else {
    maybeAutoOpen();
  }
})();
