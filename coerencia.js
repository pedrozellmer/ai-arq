/* ─────────────────────────────────────────────────────────────
   AVISO DE ENTREGÁVEL DESATUALIZADO  —  AI.arq, 02/08/2026

   Regra do projeto: quantitativo, cronograma e memorial saem do MESMO
   levantamento. Mexeu num item, os outros dois envelheceram. Este script
   pergunta ao backend o que ficou velho e mostra o aviso na tela.

   Ele NUNCA refaz nada sozinho — cronograma e memorial têm edição manual
   do cliente dentro, e sobrescrever o trabalho dele sem pedir seria pior
   do que o número velho. O botão é dele.

   Uso: coloque <div id="aviso-coerencia" class="hidden"></div> na página e
   chame aiArqCoerencia(jobId, 'projeto' | 'cronograma' | 'memorial').
   ───────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  function plural(n, um, muitos) { return n === 1 ? um : muitos; }

  // "3 itens corrigidos e 1 item excluído" → frase pronta, vinda do backend.
  function motivo(info) {
    var f = (info && info.frase) || '';
    return f ? f : 'o quantitativo mudou';
  }

  function botao(href, texto, primario) {
    var base = 'inline-block rounded-lg px-3 py-1.5 text-xs font-bold ';
    var cor = primario
      ? 'bg-amber-600 text-white'
      : 'bg-white text-amber-800 border border-amber-300';
    return '<a href="' + href + '" class="' + base + cor + '">' + texto + '</a>';
  }

  function montarTexto(ctx, d) {
    var cron = d.cronograma || {}, mem = d.memorial || {};
    var cronVelho = !!cron.desatualizado, memVelho = !!mem.desatualizado;

    if (ctx === 'cronograma') {
      return {
        titulo: 'Este cronograma está desatualizado',
        corpo: 'Você mexeu no quantitativo depois que ele foi gerado (' +
               motivo(cron) + '). As durações das fases ainda vêm dos números ' +
               'antigos, e é esse cronograma velho que sai no PDF e no PPT. ' +
               'Pra corrigir: <strong>Regerar</strong> e depois <strong>Salvar</strong>' +
               ' — atenção, regerar substitui os ajustes que você tenha feito à ' +
               'mão nas fases.',
        acoes: ''
      };
    }

    if (ctx === 'memorial') {
      return {
        titulo: 'Este memorial está desatualizado',
        corpo: 'Você mexeu no quantitativo depois que ele foi salvo (' +
               motivo(mem) + '). As quantidades escritas aqui ainda são as ' +
               'antigas. Você pode atualizar o texto com os números de agora — ' +
               'o que você escreveu à mão será substituído, e nada é salvo até ' +
               'você clicar em Salvar.',
        acoes: '<button type="button" id="coer-refazer-memorial" ' +
               'class="inline-block rounded-lg px-3 py-1.5 text-xs font-bold ' +
               'bg-amber-600 text-white">Atualizar com os números de agora</button>'
      };
    }

    // Página do projeto: o painel geral dos três entregáveis.
    var pl = d.planilha || {};
    var velhos = [];
    if (pl.desatualizado)  velhos.push({ artigo: 'a', nome: 'planilha',   info: pl  });
    if (cronVelho)         velhos.push({ artigo: 'o', nome: 'cronograma', info: cron });
    if (memVelho)          velhos.push({ artigo: 'o', nome: 'memorial',   info: mem });

    var nomes = velhos.map(function (v) { return v.artigo + ' ' + v.nome; });
    var alvo = nomes.length > 2
      ? nomes.slice(0, -1).join(', ') + ' e ' + nomes[nomes.length - 1]
      : nomes.join(' e ');

    var acoes = '';
    var primeiro = true;
    velhos.forEach(function (v) {
      if (v.nome === 'planilha') {
        acoes += '<button type="button" id="coer-refazer-planilha" ' +
                 'class="inline-block rounded-lg px-3 py-1.5 text-xs font-bold ' +
                 'bg-amber-600 text-white">Atualizar planilha agora</button> ';
      } else {
        var pag = v.nome === 'cronograma' ? 'cronograma.html?job=' : 'memorial.html?job=';
        acoes += botao(pag + d._jobId, 'Abrir ' + v.nome, primeiro) + ' ';
      }
      primeiro = false;
    });

    var so = velhos[0];
    return {
      titulo: velhos.length === 1
        ? (so.artigo === 'a' ? 'Sua ' : 'Seu ') + so.nome + ' ficou desatualizad' +
          (so.artigo === 'a' ? 'a' : 'o')
        : 'Estes arquivos ficaram desatualizados: ' + alvo,
      corpo: 'Você ajustou o quantitativo depois (' + motivo(so.info) + '), então ' +
             alvo + ' ainda ' + plural(velhos.length, 'usa', 'usam') + ' os números ' +
             'antigos. Vale atualizar antes de mandar pra obra, pro cliente ou pro banco.',
      acoes: acoes
    };
  }

  function render(caixa, txt) {
    caixa.innerHTML =
      '<div class="rounded-xl border-2 border-amber-300 bg-amber-50 px-4 py-3">' +
        '<div class="flex items-start gap-3">' +
          '<span class="text-amber-700 font-bold" aria-hidden="true">⚠</span>' +
          '<div>' +
            '<p class="text-sm font-bold text-amber-900">' + txt.titulo + '</p>' +
            '<p class="text-xs text-amber-800 leading-snug mt-1">' + txt.corpo + '</p>' +
            (txt.acoes ? '<div class="flex flex-wrap gap-2 mt-2">' + txt.acoes + '</div>' : '') +
          '</div>' +
        '</div>' +
      '</div>';
    caixa.classList.remove('hidden');
    caixa.setAttribute('role', 'status');
  }

  // Refazer a planilha é seguro: ela é 100% derivada dos itens, não tem nada
  // escrito à mão dentro. Por isso aqui tem botão direto, sem confirmação —
  // ao contrário do memorial e do cronograma.
  function wirePlanilha(jobId, contexto) {
    var btn = document.getElementById('coer-refazer-planilha');
    if (!btn) return;
    btn.addEventListener('click', async function () {
      btn.disabled = true;
      btn.textContent = 'Atualizando…';
      try {
        var r = await window.authFetch(
          window.API_BASE + '/api/items/' + jobId + '/finalize', { method: 'POST' });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        window.toast && window.toast.success
          ? window.toast.success('Planilha atualizada com os números de agora')
          : null;
        aiArqCoerencia(jobId, contexto);   // recarrega o aviso já sem a planilha
      } catch (e) {
        btn.disabled = false;
        btn.textContent = 'Atualizar planilha agora';
        var msg = 'Não consegui atualizar a planilha agora: ' + e.message;
        window.toast ? window.toast.error(msg) : alert(msg);
      }
    });
  }

  async function aiArqCoerencia(jobId, contexto) {
    var caixa = document.getElementById('aviso-coerencia');
    if (!caixa || !jobId) return null;
    try {
      var r = await window.authFetch(window.API_BASE + '/api/projeto/' + jobId + '/coerencia');
      if (!r.ok) return null;
      var d = await r.json();
      d._jobId = jobId;

      // Cada tela só fala do que é dela. O hub fala dos dois.
      var mostra = contexto === 'cronograma' ? (d.cronograma || {}).desatualizado
                 : contexto === 'memorial'   ? (d.memorial || {}).desatualizado
                 : !d.tudo_em_dia;
      if (!mostra) { caixa.classList.add('hidden'); caixa.innerHTML = ''; return d; }

      render(caixa, montarTexto(contexto, d));
      wirePlanilha(jobId, contexto);
      return d;
    } catch (e) {
      // Aviso é acessório: falhou, a página segue sem ele.
      console.warn('coerencia:', e);
      return null;
    }
  }

  window.aiArqCoerencia = aiArqCoerencia;
})();
