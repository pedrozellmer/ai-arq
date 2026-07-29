/* Botão flutuante de WhatsApp — a cara do app: QUADRADINHO verde com cantos
   arredondados e o LOGO oficial branco. Balança de leve pra chamar atenção.
   Link wa.me (zero API). Bottom-RIGHT.
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

  // Logo OFICIAL do WhatsApp (simple-icons), viewBox 24x24 — centralizado e simétrico.
  var WA_LOGO = '<svg width="40" height="40" viewBox="0 0 24 24" fill="#fff" aria-hidden="true">' +
    '<path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.885-9.885 9.885M20.52 3.449C18.24 1.245 15.24 0 12.045 0 5.463 0 .104 5.359.101 11.892c0 2.096.549 4.14 1.595 5.945L0 24l6.335-1.652a11.916 11.916 0 005.71 1.454h.006c6.585 0 11.946-5.359 11.949-11.893a11.821 11.821 0 00-3.495-8.411z"/></svg>';

  function injectStyle() {
    if (document.getElementById('aiarq-wa-style')) return;
    var st = document.createElement('style');
    st.id = 'aiarq-wa-style';
    // Balancinho periódico (mexe ~1,4s a cada 4s) pra chamar atenção sem cansar.
    st.textContent =
      '@keyframes aiarq-wa-wiggle{' +
      '0%,64%,100%{transform:rotate(0)}' +
      '70%{transform:rotate(-9deg)}' +
      '76%{transform:rotate(7deg)}' +
      '82%{transform:rotate(-5deg)}' +
      '88%{transform:rotate(4deg)}' +
      '94%{transform:rotate(-2deg)}}';
    document.head.appendChild(st);
  }

  function mount() {
    if (document.getElementById('aiarq-wa-fab')) return;
    injectStyle();

    var wrap = document.createElement('div');
    wrap.id = 'aiarq-wa-fab';
    wrap.style.cssText = 'position:fixed;right:22px;bottom:22px;z-index:9998;';

    var a = document.createElement('a');
    a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.setAttribute('aria-label', 'Falar com o AI.arq no WhatsApp');
    a.title = 'Fale com a gente no WhatsApp';
    a.style.cssText = 'display:inline-flex;align-items:center;justify-content:center;width:68px;height:68px;border-radius:18px;background:#25D366;box-shadow:0 8px 26px rgba(37,211,102,.55);transition:transform .15s ease,box-shadow .15s ease;animation:aiarq-wa-wiggle 4s ease-in-out infinite;transform-origin:center;';
    a.innerHTML = WA_LOGO;
    a.onmouseover = function () { a.style.animationPlayState = 'paused'; a.style.transform = 'translateY(-2px) scale(1.06)'; a.style.boxShadow = '0 14px 34px rgba(37,211,102,.65)'; };
    a.onmouseout = function () { a.style.transform = ''; a.style.boxShadow = '0 8px 26px rgba(37,211,102,.55)'; a.style.animationPlayState = 'running'; };

    var close = document.createElement('button');
    close.type = 'button';
    close.setAttribute('aria-label', 'Esconder o botão do WhatsApp nesta página');
    close.title = 'Esconder aqui (volta ao trocar de página)';
    close.textContent = '×';
    // 28/07/2026: era 22px colado no botão de 68px — no celular o dedo acertava
    // o WhatsApp quando queria fechar. Agora 32px (mínimo confortável de toque)
    // e afastado, pra não disparar a ação errada.
    close.style.cssText = 'position:absolute;top:-10px;right:-10px;background:#fff;color:#4b5563;border:1px solid #d1d5db;width:32px;height:32px;border-radius:9999px;font-size:18px;line-height:1;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.18);padding:0;z-index:2;display:flex;align-items:center;justify-content:center;';
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
