/**
 * Sistema de toast acessível pro AI.arq.
 *
 * Substitui alert()/confirm() — alert bloqueia thread, não é estilizável,
 * não tem fallback aria. Toast aparece flutuante no canto, anuncia via
 * aria-live, fecha sozinho (sucesso/info) ou via botão (erro).
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
  @keyframes toast-in {
    from { transform: translateX(120%); opacity: 0; }
    to   { transform: translateX(0);    opacity: 1; }
  }
  @media (prefers-reduced-motion: reduce) {
    .toast-item { animation: none; }
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
      const region = ensureRegion();
      const item = document.createElement('div');
      item.className = 'toast-item toast-warn';
      item.setAttribute('role', 'alertdialog');
      item.setAttribute('aria-modal', 'false');

      const okLabel = (opts && opts.ok) || 'Confirmar';
      const cancelLabel = (opts && opts.cancel) || 'Cancelar';
      const safeMsg = String(message || '').replace(/<[^>]*>/g, '');

      item.innerHTML = `
        <span class="toast-icon" aria-hidden="true">⚠</span>
        <div class="toast-body">
          <div class="toast-msg"></div>
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

      const finish = (val) => {
        if (item.parentNode) item.parentNode.removeChild(item);
        resolve(val);
      };
      okBtn.addEventListener('click', () => finish(true));
      cancelBtn.addEventListener('click', () => finish(false));

      region.appendChild(item);
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
