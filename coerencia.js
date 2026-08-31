/* ─────────────────────────────────────────────────────────────
   AVISO DE ENTREGÁVEL DESATUALIZADO  —  AI.arq, 02/08/2026

   Regra do projeto: planilha, cronograma, memorial e comparativo de
   fornecedores saem do MESMO levantamento. Mexeu num item, os outros
   envelheceram. Este script pergunta ao backend o que ficou velho e mostra
   o aviso na tela.

   Ele NUNCA refaz nada sozinho — cronograma e memorial têm edição manual
   do cliente dentro, e sobrescrever o trabalho dele sem pedir seria pior
   do que o número velho. O botão é dele. Planilha e comparativo são 100%
   derivados (nada escrito à mão), então nesses dois o botão age direto.

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
      // Com valor informado, o que envelheceu não é só a data: o rateio do
      // desembolso sai das durações, então o dinheiro por mês também está
      // velho. Dizer isso é o ponto todo da regra nº7 — o cliente não pode
      // mandar pro banco um desembolso que não vale mais.
      var temFin = !!cron.tem_financeiro;
      return {
        titulo: temFin
          ? 'Este cronograma físico-financeiro está desatualizado'
          : 'Este cronograma está desatualizado',
        corpo: 'Você mexeu no quantitativo depois que ele foi gerado (' +
               motivo(cron) + '). As durações das fases ainda vêm dos números ' +
               'antigos, e é esse cronograma velho que sai no PDF, no PPT e na planilha. ' +
               (temFin
                 ? '<strong>Atenção: o desembolso por mês também mudou</strong> — ele é ' +
                   'distribuído pelas durações, então o valor de cada mês saiu do lugar. ' +
                   'Os valores que você digitou por etapa continuam salvos; só o rateio ' +
                   'pelos meses precisa ser refeito. '
                 : '') +
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
        acoes: '<button type="button" data-coer="memorial" ' +
               'class="inline-block rounded-lg px-3 py-1.5 text-xs font-bold ' +
               'bg-amber-600 text-white">Atualizar com os números de agora</button>'
      };
    }

    // Página do projeto: o painel geral de todos os entregáveis.
    var pl = d.planilha || {}, comp = d.comparativo || {};
    var velhos = [];
    if (pl.desatualizado)  velhos.push({ artigo: 'a', nome: 'planilha',   info: pl  });
    if (cronVelho)         velhos.push({ artigo: 'o', nome: 'cronograma', info: cron });
    if (memVelho)          velhos.push({ artigo: 'o', nome: 'memorial',   info: mem });
    if (comp.desatualizado) velhos.push({ artigo: 'o', nome: 'comparativo de fornecedores',
                                          chave: 'comparativo', info: comp });

    var nomes = velhos.map(function (v) { return v.artigo + ' ' + v.nome; });
    var alvo = nomes.length > 2
      ? nomes.slice(0, -1).join(', ') + ' e ' + nomes[nomes.length - 1]
      : nomes.join(' e ');

    var acoes = '';
    var primeiro = true;
    velhos.forEach(function (v) {
      if (v.nome === 'planilha') {
        acoes += '<button type="button" data-coer="planilha" ' +
                 'class="inline-block rounded-lg px-3 py-1.5 text-xs font-bold ' +
                 'bg-amber-600 text-white">Atualizar planilha agora</button> ';
      } else if (v.chave === 'comparativo') {
        // Também 100% derivado: refazer só reprocessa as cotações que já estão
        // no projeto contra os itens de agora. Nada escrito à mão se perde.
        acoes += '<button type="button" data-coer="comparativo" ' +
                 'class="inline-block rounded-lg px-3 py-1.5 text-xs font-bold ' +
                 'bg-amber-600 text-white">Refazer comparativo</button> ';
      } else {
        // job_id nos dois: e o nome que projeto/revisao/memorial usam. As duas
        // paginas aceitam os dois, mas link novo nasce no padrao certo.
        var pag = v.nome === 'cronograma' ? 'cronograma.html?job_id=' : 'memorial.html?job_id=';
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
      // 🩸 31/08: a frase saía redundante e ninguém entendia — nem o Pedro.
      // Quando o backend não sabe dizer O QUE mudou, `motivo()` devolve
      // "o quantitativo mudou" e o texto virava "Você ajustou o quantitativo
      // depois (o quantitativo mudou)". Agora a frase específica ENTRA no
      // lugar do genérico, e sem frase o texto é direto.
      corpo: (so.info && so.info.frase
                ? 'Depois que ' + alvo + ' ' + plural(velhos.length, 'foi gerada', 'foram gerados') +
                  ', você ' + so.info.frase + '. '
                : 'O quantitativo mudou depois que ' + alvo + ' ' +
                  plural(velhos.length, 'foi gerada', 'foram gerados') + '. ') +
             (velhos.length === 1 ? 'Ela ainda usa' : 'Eles ainda usam') +
             ' os números antigos — vale atualizar antes de mandar pra obra, ' +
             'pro cliente ou pro banco.',
      acoes: acoes
    };
  }

  // Pinta TODAS as caixas de aviso da página, não só a primeira: com a
  // página do projeto dividida em vistas, o alerta precisa aparecer tanto
  // na Visão geral quanto ao lado dos botões de baixar.
  function render(caixa, txt) {
    var html =
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
    _todasAsCaixas().forEach(function (c) {
      c.innerHTML = html;
      c.classList.remove('hidden');
      c.setAttribute('role', 'status');
    });
  }

  function _todasAsCaixas() {
    return [].slice.call(document.querySelectorAll(
      '#aviso-coerencia, .aviso-coerencia'));
  }

  // Refazer a planilha é seguro: ela é 100% derivada dos itens, não tem nada
  // escrito à mão dentro. Por isso aqui tem botão direto, sem confirmação —
  // ao contrário do memorial e do cronograma.
  // Liga o MESMO clique em todos os botões daquele tipo — o aviso aparece em
  // mais de uma caixa e cada uma tem o seu. E, quando um é clicado, os dois
  // mudam de estado juntos: ver "Atualizar" ainda ativo do outro lado enquanto
  // a coisa já está rodando faz a pessoa clicar de novo.
  function ligarTodos(tipo, aoClicar) {
    var btns = [].slice.call(document.querySelectorAll('[data-coer="' + tipo + '"]'));
    if (!btns.length) return null;
    var estado = function (texto, travado) {
      btns.forEach(function (b) {
        if (texto != null) b.textContent = texto;
        b.disabled = !!travado;
      });
    };
    btns.forEach(function (b) {
      b.addEventListener('click', function () { aoClicar(estado); });
    });
    return estado;
  }

  function wirePlanilha(jobId, contexto) {
    // 🪤 querySelectorAll, nao getElementById: o aviso agora aparece em
    // DUAS caixas (Visao geral e Sua planilha) e o id so pegaria a
    // primeira -- o botao da segunda ficaria bonito e morto.
    ligarTodos('planilha', async function (estado) {
      estado('Atualizando…', true);
      try {
        var r = await window.authFetch(
          window.API_BASE + '/api/items/' + jobId + '/finalize', { method: 'POST' });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        window.toast && window.toast.success
          ? window.toast.success('Planilha atualizada com os números de agora')
          : null;
        aiArqCoerencia(jobId, contexto);   // recarrega o aviso já sem a planilha
      } catch (e) {
        estado('Atualizar planilha agora', false);
        var msg = 'Não consegui atualizar a planilha agora: ' + e.message;
        window.toast ? window.toast.error(msg) : alert(msg);
      }
    });
  }

  // Refazer o comparativo é seguro pelo mesmo motivo da planilha: ele só
  // reprocessa as cotações já enviadas contra os itens atuais. Prefere chamar
  // a função da própria página do projeto, que já sabe desenhar o resultado
  // (ranking, quem esqueceu o quê); só cai no endpoint cru se não existir.
  function wireComparativo(jobId, contexto) {
    ligarTodos('comparativo', async function (estado) {
      estado('Refazendo…', true);
      try {
        if (typeof window.generateComparison === 'function') {
          await window.generateComparison();
        } else {
          var r = await window.authFetch(
            window.API_BASE + '/api/projects/' + jobId + '/quotes/compare');
          if (!r.ok) throw new Error('HTTP ' + r.status);
          var d = await r.json();
          if (d && d.error) throw new Error(d.error);
        }
        aiArqCoerencia(jobId, contexto);
      } catch (e) {
        estado('Refazer comparativo', false);
        var msg = 'Não consegui refazer o comparativo agora: ' + e.message;
        window.toast ? window.toast.error(msg) : alert(msg);
      }
    });
  }

  async function aiArqCoerencia(jobId, contexto) {
    // 🚨 REGRA DURA nº7 — o aviso tem que estar ONDE O CLIENTE BAIXA.
    // A página do projeto virou 4 vistas em 04/08 e este aviso ficou só na
    // "Visão geral", enquanto os botões de baixar foram pra "Sua planilha".
    // O cliente entrava direto no Quantitativo, baixava um arquivo velho e
    // mandava pro cliente dele sem nunca ver o alerta. Agora todo elemento
    // marcado como caixa de aviso recebe o mesmo conteúdo — quem põe uma na
    // página só precisa dar a classe, sem tocar neste arquivo.
    var caixas = [].slice.call(document.querySelectorAll(
      '#aviso-coerencia, .aviso-coerencia'));
    var caixa = caixas[0];
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
      if (!mostra) {
        _todasAsCaixas().forEach(function (c) {
          c.classList.add('hidden'); c.innerHTML = '';
        });
        return d;
      }

      render(caixa, montarTexto(contexto, d));
      wirePlanilha(jobId, contexto);
      wireComparativo(jobId, contexto);
      return d;
    } catch (e) {
      // Aviso é acessório: falhou, a página segue sem ele.
      console.warn('coerencia:', e);
      return null;
    }
  }

  window.aiArqCoerencia = aiArqCoerencia;
})();
