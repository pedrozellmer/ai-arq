/**
 * Sistema de toast acessível pro AI.arq.
 *
 * Substitui alert()/confirm() — alert bloqueia thread, não é estilizável,
 * não tem fallback aria. Toast aparece flutuante no canto, anuncia via
 * aria-live, fecha sozinho (sucesso/info) ou via botão (erro).
 * A pergunta (confirm) é diferente: abre no CENTRO, com a tela escurecida
 * atrás (07/11/2026, ver .toast-overlay).
 *
 * Pedro é daltônico — cada toast leva cor + ícone + texto. Verde + ✓,
 * vermelho + ✗, âmbar + ⚠, azul + ℹ.
 *
 * Uso:
 *   toast.success('Salvo!');
 *   toast.error('Não consegui baixar: HTTP 401');
 *   toast.warn('Sessão prestes a expirar');
 *   toast.info('Reprocessamento iniciado. Vou recarregar em 5s.');
 *   await toast.confirm('Excluir projeto?', { ok: 'Excluir', cancel: 'Não' });
 *   // → resolve true/false
 *
 * NÃO é dependência externa. Vanilla JS, sem build. Inclui CSS inline.
 */
(function (window) {
  'use strict';

  // ── CSS injetado uma vez ─────────────────────────────────────────────
  const CSS = `
  .toast-region {
    position: fixed; top: 16px; right: 16px; z-index: 9999;
    display: flex; flex-direction: column; gap: 8px;
    max-width: min(420px, calc(100vw - 32px));
    pointer-events: none;
  }
  .toast-item {
    pointer-events: auto;
    display: flex; align-items: flex-start; gap: 10px;
    padding: 12px 14px; border-radius: 12px;
    background: #fff; color: #111827;
    box-shadow: 0 10px 25px rgba(0,0,0,0.10), 0 4px 6px rgba(0,0,0,0.05);
    border-left: 6px solid #6366f1;
    font: 500 14px/1.4 'Inter', -apple-system, sans-serif;
    animation: toast-in 200ms ease-out;
  }
  .toast-item.toast-success { border-left-color: #10b981; }
  .toast-item.toast-error   { border-left-color: #ef4444; }
  .toast-item.toast-warn    { border-left-color: #f59e0b; }
  .toast-item.toast-info    { border-left-color: #3b82f6; }
  .toast-check { display: flex; align-items: flex-start; gap: 8px;
                 margin: 8px 0 0; font-weight: 400; cursor: pointer; }
  .toast-check input { margin-top: 3px; }
  /* 08/10/2026 — o display: flex acima VENCE o atributo hidden (a regra do
     navegador pra [hidden] perde pra qualquer display do autor). Desde 23/09
     todo diálogo SEM caixa de ciência mostrava uma caixinha vazia, sem rótulo e
     sem função: "Informar agora / Enviar assim mesmo", o anexo ao projeto
     anterior, todos. Visto na prévia da pergunta do tipo antes do envio.
     🪤 Este CSS mora numa template string do JS: crase aqui dentro fecha a
     string e derruba o toast do site inteiro (aconteceu na 1ª versão disto). */
  .toast-check[hidden] { display: none; }
  .toast-actions button[disabled] { opacity: .5; cursor: not-allowed; }
  .toast-icon {
    flex-shrink: 0; font-size: 18px; line-height: 1; padding-top: 1px;
    width: 22px; text-align: center;
  }
  .toast-success .toast-icon { color: #059669; }
  .toast-error   .toast-icon { color: #dc2626; }
  .toast-warn    .toast-icon { color: #d97706; }
  .toast-info    .toast-icon { color: #2563eb; }
  .toast-body { flex: 1; min-width: 0; word-wrap: break-word; }
  .toast-close {
    flex-shrink: 0; background: none; border: 0; cursor: pointer;
    color: #6b7280; font-size: 20px; line-height: 1; padding: 0 4px;
  }
  .toast-close:hover { color: #111827; }
  .toast-actions {
    display: flex; gap: 8px; margin-top: 8px;
  }
  .toast-actions button {
    padding: 6px 12px; border-radius: 8px; border: 1px solid #d1d5db;
    background: #fff; cursor: pointer; font: 500 13px/1 'Inter', sans-serif;
  }
  .toast-actions button.toast-primary {
    background: #4f46e5; color: #fff; border-color: #4f46e5;
  }
  .toast-actions button:hover { filter: brightness(0.95); }
  /* 07/11/2026 — A PERGUNTA VAI PRO CENTRO. Ela abria no canto, igual a um
     aviso, e quem não via clicava Processar de novo: em 30 dias, 10 pessoas
     levaram o "seu envio já começou", e uma desistiu sem enviar. Agora toda
     pergunta de sim ou não abre no centro, com a tela escurecida atrás; os
     avisos simples continuam no canto. Maquete aprovada pelo Pedro em 07/11.
     Guarda: test_a_pergunta_abre_no_centro. */
  .toast-overlay {
    position: fixed; inset: 0; z-index: 10000;
    display: flex; align-items: center; justify-content: center;
    padding: 16px; background: rgba(15, 23, 42, 0.55);
  }
  .toast-item.toast-dialog {
    width: min(520px, 100%); box-sizing: border-box;
    padding: 24px; gap: 14px; border-left: 0; border-radius: 16px;
    box-shadow: 0 25px 50px rgba(15, 23, 42, 0.25);
    font-size: 15px; line-height: 1.55;
    animation: toast-dialog-in 150ms ease-out;
  }
  @keyframes toast-dialog-in {
    from { transform: scale(0.96); opacity: 0; }
    to   { transform: scale(1);    opacity: 1; }
  }
  .toast-dialog .toast-icon {
    width: 40px; height: 40px; border-radius: 999px; padding: 0;
    background: #fef3c7; color: #b45309;
    display: flex; align-items: center; justify-content: center;
  }
  .toast-dialog .toast-msg { color: #374151; }
  .toast-dialog .toast-actions {
    justify-content: flex-end; flex-wrap: wrap; gap: 12px; margin-top: 16px;
  }
  .toast-dialog .toast-actions button {
    min-height: 44px; padding: 10px 18px; border-radius: 10px; font-size: 15px;
  }
  @keyframes toast-in {
    from { transform: translateX(120%); opacity: 0; }
    to   { transform: translateX(0);    opacity: 1; }
  }
  @media (prefers-reduced-motion: reduce) {
    .toast-item, .toast-item.toast-dialog { animation: none; }
  }
  `;

  function ensureRegion() {
    let region = document.getElementById('toast-region');
    if (region) return region;
    if (!document.getElementById('toast-style')) {
      const style = document.createElement('style');
      style.id = 'toast-style';
      style.textContent = CSS;
      document.head.appendChild(style);
    }
    region = document.createElement('div');
    region.id = 'toast-region';
    region.className = 'toast-region';
    region.setAttribute('aria-live', 'polite');
    region.setAttribute('aria-atomic', 'false');
    document.body.appendChild(region);
    return region;
  }

  const ICONS = { success: '✓', error: '✗', warn: '⚠', info: 'ℹ' };
  const ROLES = { success: 'status', info: 'status', warn: 'alert', error: 'alert' };

  function show(type, message, opts) {
    const region = ensureRegion();
    const item = document.createElement('div');
    item.className = `toast-item toast-${type}`;
    item.setAttribute('role', ROLES[type] || 'status');

    // Strip HTML tags do message — sempre tratado como texto.
    const safeMsg = String(message || '').replace(/<[^>]*>/g, '');

    item.innerHTML = `
      <span class="toast-icon" aria-hidden="true">${ICONS[type] || 'ℹ'}</span>
      <div class="toast-body"></div>
      <button class="toast-close" aria-label="Fechar aviso">×</button>
    `;
    item.querySelector('.toast-body').textContent = safeMsg;

    const close = () => {
      if (item.parentNode) item.parentNode.removeChild(item);
    };
    item.querySelector('.toast-close').addEventListener('click', close);

    region.appendChild(item);

    // Auto-fechamento — erros ficam até o usuário fechar; resto some.
    const duration = opts && opts.duration != null
      ? opts.duration
      : (type === 'error' ? 0 : 5000);
    if (duration > 0) setTimeout(close, duration);

    return { close };
  }

  function confirmToast(message, opts) {
    return new Promise((resolve) => {
      ensureRegion();                       // o CSS da casa vem junto com a região
      // 🩸 07/11/2026: no CENTRO, com a tela escurecida (ver .toast-overlay).
      // O fundo segura o clique de fora: a pergunta só fecha num dos botões,
      // como antes, ou no Esc, que vale como o botão de recusa.
      const overlay = document.createElement('div');
      overlay.className = 'toast-overlay';
      const item = document.createElement('div');
      item.className = 'toast-item toast-warn toast-dialog';
      item.setAttribute('role', 'alertdialog');
      item.setAttribute('aria-modal', 'true');

      const okLabel = (opts && opts.ok) || 'Confirmar';
      const cancelLabel = (opts && opts.cancel) || 'Cancelar';
      const safeMsg = String(message || '').replace(/<[^>]*>/g, '');
      // 23/09/2026 — `checkbox: 'texto'` põe uma caixa de ciência e SEGURA o
      // botão principal até ela ser marcada. Serve pra aviso que a pessoa
      // precisa ter LIDO (não é pergunta de sim/não). Aditivo: quem chama sem
      // a opção continua com o diálogo de antes, byte a byte.
      const checkLabel = (opts && opts.checkbox) || '';

      item.innerHTML = `
        <span class="toast-icon" aria-hidden="true">⚠</span>
        <div class="toast-body">
          <div class="toast-msg"></div>
          <label class="toast-check" hidden>
            <input type="checkbox"> <span></span>
          </label>
          <div class="toast-actions">
            <button class="toast-primary" type="button"></button>
            <button type="button"></button>
          </div>
        </div>
      `;
      item.querySelector('.toast-msg').textContent = safeMsg;
      const [okBtn, cancelBtn] = item.querySelectorAll('.toast-actions button');
      okBtn.textContent = okLabel;
      cancelBtn.textContent = cancelLabel;
      const wrap = item.querySelector('.toast-check');
      const box = wrap.querySelector('input');
      if (checkLabel) {
        wrap.hidden = false;
        // 🔒 textContent, nunca innerHTML: o rótulo pode vir de qualquer tela.
        wrap.querySelector('span').textContent = String(checkLabel);
        okBtn.disabled = true;
        box.addEventListener('change', () => { okBtn.disabled = !box.checked; });
      }

      const finish = (val) => {
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
        resolve(val);
      };
      okBtn.addEventListener('click', () => {
        // 🪤 O `disabled` é a porta; isto é a tranca. Um clique programático
        // (ou CSS quebrado) não pode passar por cima da ciência da pessoa.
        if (checkLabel && !box.checked) return;
        finish(true);
      });
      cancelBtn.addEventListener('click', () => finish(false));
      overlay.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape') finish(false);
      });

      overlay.appendChild(item);
      document.body.appendChild(overlay);
      okBtn.focus();
    });
  }

  window.toast = {
    success: (m, o) => show('success', m, o),
    error:   (m, o) => show('error',   m, o),
    warn:    (m, o) => show('warn',    m, o),
    info:    (m, o) => show('info',    m, o),
    confirm: confirmToast,
  };
})(window);
