/* Botão flutuante de WhatsApp — "Fale com a gente" (Fase 0 do plano WhatsApp, 21/07).
   Cara do WhatsApp: círculo verde com o LOGO branco (a cara clássica) + etiqueta de
   texto do lado (daltonismo é regra dura — logo/cor sozinhos não bastam).
   Link wa.me (zero API). Dispensável (× lembra no localStorage). Bottom-RIGHT.
   🔧 Pra trocar de número, muda só a constante NUMERO abaixo (E.164 sem '+'). */
(function () {
  'use strict';
  var NUMERO = '551151968034';                 // (11) 5196-8034 — número que VOCÊ responde no celular
  if (!NUMERO || /X/.test(NUMERO)) return;      // não renderiza sem número real
  try { if (localStorage.getItem('aiarq_wa_btn_hidden') === '1') return; } catch (e) {}

  var msg = 'Olá! Vim do site do AI.arq. Tenho uma dúvida:';
  var href = 'https://wa.me/' + NUMERO + '?text=' + encodeURIComponent(msg);

  var WA_LOGO = '<svg width="34" height="34" viewBox="0 0 32 32" fill="#fff" aria-hidden="true">' +
    '<path d="M16.003 3C9.373 3 3.99 8.383 3.99 15.013c0 2.12.555 4.19 1.61 6.017L3 29l8.15-2.137a12.06 12.06 0 004.85 1.01h.004c6.63 0 12.013-5.383 12.013-12.013C28.017 8.383 22.633 3 16.003 3zm0 21.9h-.003a9.9 9.9 0 01-5.043-1.382l-.362-.215-4.836 1.268 1.29-4.714-.236-.377a9.86 9.86 0 01-1.51-5.27c0-5.463 4.446-9.91 9.913-9.91 2.648 0 5.137 1.032 7.008 2.905a9.84 9.84 0 012.902 7.012c0 5.463-4.446 9.91-9.836 9.91zm5.43-7.42c-.297-.15-1.758-.868-2.03-.967-.272-.099-.47-.148-.669.15-.198.297-.767.966-.94 1.164-.173.198-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.76-1.653-2.058-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.52.149-.174.198-.298.297-.496.099-.198.05-.372-.025-.52-.074-.15-.669-1.612-.916-2.207-.241-.579-.486-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.478 1.065 2.875 1.213 3.073c.149.198 2.096 3.2 5.076 4.487.71.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.247-.694.247-1.29.173-1.414-.074-.124-.272-.198-.57-.347z"/></svg>';

  function mount() {
    if (document.getElementById('aiarq-wa-fab')) return;

    var wrap = document.createElement('div');
    wrap.id = 'aiarq-wa-fab';
    wrap.style.cssText = 'position:fixed;right:18px;bottom:18px;z-index:9998;font-family:Inter,Arial,sans-serif;';

    var a = document.createElement('a');
    a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.setAttribute('aria-label', 'Falar com o AI.arq no WhatsApp');
    a.style.cssText = 'display:flex;align-items:center;gap:10px;text-decoration:none;';

    // Etiqueta de texto (branca) — o daltonismo exige texto, não só verde/logo.
    var label = document.createElement('span');
    label.textContent = 'Fale com a gente';
    label.style.cssText = 'background:#fff;color:#111827;font-size:13px;font-weight:600;padding:9px 14px;border-radius:9999px;box-shadow:0 4px 14px rgba(0,0,0,.14);white-space:nowrap;';

    // FAB redondo verde com o LOGO do WhatsApp — a cara clássica.
    var fab = document.createElement('span');
    fab.style.cssText = 'display:inline-flex;align-items:center;justify-content:center;width:58px;height:58px;border-radius:9999px;background:#25D366;box-shadow:0 6px 20px rgba(37,211,102,.45);transition:transform .15s ease,box-shadow .15s ease;';
    fab.innerHTML = WA_LOGO;

    a.appendChild(label);
    a.appendChild(fab);
    a.onmouseover = function () { fab.style.transform = 'translateY(-2px) scale(1.05)'; fab.style.boxShadow = '0 10px 28px rgba(37,211,102,.55)'; };
    a.onmouseout = function () { fab.style.transform = ''; fab.style.boxShadow = '0 6px 20px rgba(37,211,102,.45)'; };

    // Dismiss × — canto superior direito do FAB.
    var close = document.createElement('button');
    close.type = 'button';
    close.setAttribute('aria-label', 'Esconder o botão do WhatsApp');
    close.textContent = '×';
    close.style.cssText = 'position:absolute;top:-8px;right:-8px;background:#fff;color:#6b7280;border:1px solid #e5e7eb;width:20px;height:20px;border-radius:9999px;font-size:13px;line-height:1;cursor:pointer;box-shadow:0 2px 6px rgba(0,0,0,.15);padding:0;';
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
