/* Botão flutuante de WhatsApp — "Fale com a gente" (Fase 0 do plano WhatsApp, 21/07).
   Link wa.me (zero API, zero Meta). Acessível: verde + ÍCONE + TEXTO (daltonismo é
   regra dura — verde sozinho não basta). Dispensável (× lembra no localStorage).
   Fica bottom-RIGHT (posição nobre; o chat-widget de lead foi removido em 21/07).
   🔧 Pra trocar de número, muda só a constante NUMERO abaixo (E.164 sem '+'). */
(function () {
  'use strict';
  var NUMERO = '551151968034';                 // (11) 5196-8034 — número que VOCÊ responde no celular
  if (!NUMERO || /X/.test(NUMERO)) return;      // não renderiza sem número real
  try { if (localStorage.getItem('aiarq_wa_btn_hidden') === '1') return; } catch (e) {}
  if (document.getElementById('aiarq-wa-fab')) return;

  var msg = 'Olá! Vim do site do AI.arq. Tenho uma dúvida:';
  var href = 'https://wa.me/' + NUMERO + '?text=' + encodeURIComponent(msg);

  function mount() {
    if (document.getElementById('aiarq-wa-fab')) return;
    var wrap = document.createElement('div');
    wrap.id = 'aiarq-wa-fab';
    wrap.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:9998;display:flex;align-items:center;gap:6px;font-family:Inter,Arial,sans-serif;';

    var a = document.createElement('a');
    a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.setAttribute('aria-label', 'Falar com o AI.arq no WhatsApp');
    a.style.cssText = 'display:inline-flex;align-items:center;gap:8px;background:#25D366;color:#fff;text-decoration:none;padding:12px 16px;border-radius:9999px;box-shadow:0 6px 20px rgba(0,0,0,.18);font-size:14px;font-weight:600;transition:transform .15s ease,box-shadow .15s ease;';
    a.onmouseover = function () { a.style.transform = 'translateY(-2px)'; a.style.boxShadow = '0 10px 26px rgba(0,0,0,.24)'; };
    a.onmouseout = function () { a.style.transform = ''; a.style.boxShadow = '0 6px 20px rgba(0,0,0,.18)'; };
    a.innerHTML =
      '<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
      '<path d="M17.47 14.38c-.29-.15-1.7-.84-1.96-.94-.26-.1-.45-.15-.64.15-.19.29-.74.94-.91 1.13-.17.19-.34.22-.62.07-.29-.15-1.22-.45-2.32-1.43-.86-.77-1.44-1.72-1.61-2-.17-.29-.02-.44.13-.59.13-.13.29-.34.44-.51.15-.17.19-.29.29-.48.1-.19.05-.36-.02-.51-.07-.15-.64-1.55-.88-2.12-.23-.55-.47-.48-.64-.49l-.55-.01c-.19 0-.5.07-.76.36-.26.29-1 .98-1 2.38 0 1.4 1.02 2.76 1.17 2.95.15.19 2.01 3.07 4.87 4.3.68.29 1.21.47 1.62.6.68.22 1.3.19 1.79.11.55-.08 1.7-.69 1.94-1.36.24-.67.24-1.24.17-1.36-.07-.12-.26-.19-.55-.34z' +
      'M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38c1.45.79 3.08 1.21 4.79 1.21h.01c5.46 0 9.91-4.45 9.91-9.91C21.95 6.45 17.5 2 12.04 2z"/></svg>' +
      '<span>Fale com a gente</span>';

    var close = document.createElement('button');
    close.type = 'button';
    close.setAttribute('aria-label', 'Esconder o botão do WhatsApp');
    close.textContent = '×';
    close.style.cssText = 'background:#fff;color:#555;border:1px solid #e5e7eb;width:22px;height:22px;border-radius:9999px;font-size:15px;line-height:1;cursor:pointer;box-shadow:0 2px 6px rgba(0,0,0,.12);padding:0;';
    close.onclick = function () { try { localStorage.setItem('aiarq_wa_btn_hidden', '1'); } catch (e) {} wrap.remove(); };

    wrap.appendChild(a);
    wrap.appendChild(close);
    (document.body || document.documentElement).appendChild(wrap);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
