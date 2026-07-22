/* Botão flutuante de WhatsApp — a cara do app: QUADRADINHO verde com cantos
   arredondados e o LOGO branco. Link wa.me (zero API). Bottom-RIGHT.
   O × só esconde na página atual (em memória) — ao trocar de página, VOLTA sozinho.
   🔧 Pra trocar de número, muda só a constante NUMERO abaixo (E.164 sem '+'). */
(function () {
  'use strict';
  var NUMERO = '551151968034';                 // (11) 5196-8034 — número que VOCÊ responde no celular
  if (!NUMERO || /X/.test(NUMERO)) return;

  // Limpa a trava antiga que escondia o botão pra sempre (versões anteriores usavam localStorage).
  try { localStorage.removeItem('aiarq_wa_btn_hidden'); } catch (e) {}

  var msg = 'Olá! Vim do site do AI.arq. Tenho uma dúvida:';
  var href = 'https://wa.me/' + NUMERO + '?text=' + encodeURIComponent(msg);

  var WA_LOGO = '<svg width="42" height="42" viewBox="0 0 32 32" fill="#fff" aria-hidden="true">' +
    '<path d="M16.003 3C9.373 3 3.99 8.383 3.99 15.013c0 2.12.555 4.19 1.61 6.017L3 29l8.15-2.137a12.06 12.06 0 004.85 1.01h.004c6.63 0 12.013-5.383 12.013-12.013C28.017 8.383 22.633 3 16.003 3zm0 21.9h-.003a9.9 9.9 0 01-5.043-1.382l-.362-.215-4.836 1.268 1.29-4.714-.236-.377a9.86 9.86 0 01-1.51-5.27c0-5.463 4.446-9.91 9.913-9.91 2.648 0 5.137 1.032 7.008 2.905a9.84 9.84 0 012.902 7.012c0 5.463-4.446 9.91-9.836 9.91zm5.43-7.42c-.297-.15-1.758-.868-2.03-.967-.272-.099-.47-.148-.669.15-.198.297-.767.966-.94 1.164-.173.198-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.76-1.653-2.058-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.52.149-.174.198-.298.297-.496.099-.198.05-.372-.025-.52-.074-.15-.669-1.612-.916-2.207-.241-.579-.486-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.478 1.065 2.875 1.213 3.073c.149.198 2.096 3.2 5.076 4.487.71.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.247-.694.247-1.29.173-1.414-.074-.124-.272-.198-.57-.347z"/></svg>';

  function mount() {
    if (document.getElementById('aiarq-wa-fab')) return;

    var wrap = document.createElement('div');
    wrap.id = 'aiarq-wa-fab';
    wrap.style.cssText = 'position:fixed;right:22px;bottom:22px;z-index:9998;';

    var a = document.createElement('a');
    a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.setAttribute('aria-label', 'Falar com o AI.arq no WhatsApp');
    a.title = 'Fale com a gente no WhatsApp';
    a.style.cssText = 'display:inline-flex;align-items:center;justify-content:center;width:68px;height:68px;border-radius:18px;background:#25D366;box-shadow:0 8px 26px rgba(37,211,102,.55);transition:transform .15s ease,box-shadow .15s ease;';
    a.innerHTML = WA_LOGO;
    a.onmouseover = function () { a.style.transform = 'translateY(-2px) scale(1.06)'; a.style.boxShadow = '0 14px 34px rgba(37,211,102,.65)'; };
    a.onmouseout = function () { a.style.transform = ''; a.style.boxShadow = '0 8px 26px rgba(37,211,102,.55)'; };

    var close = document.createElement('button');
    close.type = 'button';
    close.setAttribute('aria-label', 'Esconder o botão do WhatsApp nesta página');
    close.title = 'Esconder aqui (volta ao trocar de página)';
    close.textContent = '×';
    close.style.cssText = 'position:absolute;top:-6px;right:-6px;background:#fff;color:#6b7280;border:1px solid #e5e7eb;width:22px;height:22px;border-radius:9999px;font-size:14px;line-height:1;cursor:pointer;box-shadow:0 2px 6px rgba(0,0,0,.15);padding:0;';
    // Só esconde nesta página (em memória) — não persiste. Ao navegar/recarregar, o botão volta.
    close.onclick = function () { wrap.remove(); };

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
