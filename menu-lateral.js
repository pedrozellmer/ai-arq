/* ══════════════════════════════════════════════════════════════════════════
   MENU LATERAL COMPARTILHADO — AI.arq — 04/08/2026

   Nasceu porque o menu vivia DENTRO do dashboard.html: qualquer link que saía
   dele (Dúvidas frequentes, abrir um projeto, cronograma) caía numa tela sem
   menu nenhum, e o cliente ficava sem saída. Agora é um componente só, usado
   em dashboard, projeto, revisao, cronograma, memorial e faq.

   🪤 ARMADILHAS DESTE REPO QUE ESTE ARQUIVO PRECISA RESPEITAR:

   1. O /tailwind.min.css é um build ESTÁTICO gerado à mão, e o tailwindcss.exe
      NÃO está no repositório — ninguém consegue regerar. Classe que não existe
      lá é INERTE: não dá erro, não aparece no console, só não pinta. Por isso
      este componente traz TODO o CSS de que precisa, em classes próprias.

   2. As páginas declaram `const API_BASE` e `const sbClient` no topo de um
      <script> clássico. Script novo que redeclare qualquer um dos dois lança
      "Identifier already declared" e mata o bloco inteiro. Aqui dentro tudo
      vive numa IIFE e o acesso é sempre via window.

   3. O botão do WhatsApp é z-index 9998 inline no body. Gaveta com z-index
      menor passa por baixo dele no celular. Por isso 10000/9999.

   4. O <header> das páginas é sticky COM z-index, então cria contexto de
      empilhamento: a gaveta é filha DIRETA do <body>, nunca do header.
   ══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  if (window.__aiarqMenuLateral) return;          // idempotente
  window.__aiarqMenuLateral = true;

  // ══════════════════════════════════════════════════════════════════════
  //  PÁGINA VELHA SE RECARREGA SOZINHA
  // ══════════════════════════════════════════════════════════════════════
  // O HTML é cacheado 10 min e os .js/.css 4 horas. Depois de um deploy, o
  // cliente pode ficar rodando uma página antiga sem saber — e foi isso que
  // aconteceu em 04/08: o Pedro via "não funciona" em coisa que já estava no
  // ar, três vezes seguidas, e a única saída era ele saber apertar
  // Ctrl+Shift+R. Ninguém deveria precisar saber disso.
  //
  // O deploy grava /version.txt com o SHA e carimba o mesmo SHA na URL deste
  // arquivo. Se o que está no ar for diferente do que este HTML carregou, a
  // página está velha: recarrega UMA vez.
  //
  // 🪤 Recarga automática é perigosa — laço de reload deixa o site inutilizável.
  // Por isso: marca em sessionStorage ANTES de recarregar, e só tenta uma vez
  // por aba. Qualquer falha (offline, 404, versão vazia) não faz nada.
  (function conferirVersao() {
    try {
      var meu = '';
      var tags = document.querySelectorAll('script[src*="menu-lateral.js"]');
      for (var i = 0; i < tags.length; i++) {
        var m = /[?&]v=([^&"']+)/.exec(tags[i].getAttribute('src') || '');
        if (m) { meu = m[1]; break; }
      }
      if (!meu) return;                       // sem carimbo: nada a comparar

      fetch('/version.txt?t=' + Date.now(), { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.text() : null; })
        .then(function (t) {
          if (!t) return;
          var noAr = String(t).trim();
          if (!noAr || noAr === meu) return;   // já estamos na versão do ar

          // 🚨 A TRAVA COMPARA COM `noAr`, NÃO COM `meu`.
          // Com `meu` ela não travaria NADA: depois da recarga a página velha
          // volta com o mesmo `meu`, a marca guardada seria diferente, e o
          // código recarregaria de novo — laço infinito, site inutilizável.
          // Guardando o ALVO, a segunda tentativa reconhece "já tentei chegar
          // nesta versão e não consegui" e desiste em silêncio.
          if (sessionStorage.getItem('aiarq_alvo') === noAr) return;
          sessionStorage.setItem('aiarq_alvo', noAr);

          // Recarga simples pode servir do cache de novo (o HTML tem 10 min de
          // validade). Mudar a URL força busca nova; o parâmetro é limpo
          // logo abaixo, então o cliente não fica com sujeira no endereço.
          var u = location.href.split('#')[0];
          u += (u.indexOf('?') > -1 ? '&' : '?') + '_v=' + encodeURIComponent(noAr);
          location.replace(u + (location.hash || ''));
        })
        .catch(function () {});
    } catch (_) {}
  })();

  // Limpa o ?_v= da barra de endereço depois que a recarga cumpriu o papel.
  try {
    if (/[?&]_v=/.test(location.search)) {
      var limpa = location.search.replace(/[?&]_v=[^&]*/, '').replace(/^&/, '?');
      if (limpa === '?') limpa = '';
      history.replaceState(null, '', location.pathname + limpa + (location.hash || ''));
    }
  } catch (_) {}

  var ARQ = (location.pathname.split('/').pop() || 'index.html').toLowerCase();

  // 🪤 NÃO decida comportamento por nome de arquivo. A pergunta certa não é
  // "estou no dashboard?", é "esta página sabe trocar de aba sozinha?". Quem
  // sabe tem window.switchTab e as <div class="tab-content">. Assim o
  // componente funciona em qualquer página que ganhe abas no futuro — e dá pra
  // testar fora do dashboard, coisa que a 1ª versão não permitia.
  function sabeTrocarAba(aba) {
    return typeof window.switchTab === 'function'
      && !!document.getElementById('tab-' + aba);
  }
  // Só pra decidir se o menu nasce: o painel exige login de qualquer jeito.
  var EH_PAINEL = ARQ === 'dashboard.html' || ARQ === ''
    || !!document.querySelector('.tab-content');

  // ── Quem vê o menu ──────────────────────────────────────────────────────
  // O dashboard já exige login, então lá o menu nasce sempre. Nas outras, só
  // se houver sessão — o FAQ é público e não pode mostrar menu pra visitante.
  // A checagem é SÍNCRONA (localStorage) de propósito: o botão Sair carrega
  // id="btn-logout" e precisa existir no DOM antes do script da página rodar.
  function pareceLogado() {
    if (EH_PAINEL) return true;
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (k && /^sb-.*-auth-token$/.test(k) && localStorage.getItem(k)) return true;
      }
    } catch (_) {}
    return false;
  }

  // 🪤 O palpite no localStorage NÃO pode ser a palavra final. O nome da chave
  // (`sb-<ref>-auth-token`) é detalhe interno do Supabase: se mudar de versão,
  // ou se a sessão ainda não tiver sido gravada, o cliente logado ficaria sem
  // menu — foi exatamente o que apareceu no FAQ. Então são DUAS passadas:
  //   1. o palpite síncrono monta na hora (sem piscar pra quem já está logado
  //      e com o #btn-logout no DOM antes do script da página rodar);
  //   2. o getSession() assíncrono é a verdade — monta se o palpite errou, e
  //      desmonta se acertou pra menos.
  // Quem manda é a resposta do Supabase, nunca o palpite.
  function confirmarComSupabase() {
    if (EH_PAINEL) return;                       // painel exige login de qualquer jeito
    if (!window.sbClient || !window.sbClient.auth) return;
    window.sbClient.auth.getSession().then(function (r) {
      var logado = !!(r && r.data && r.data.session);
      var existe = !!document.getElementById('aiarq-side');
      // Só ACRESCENTA. Nunca tira.
      if (logado && !existe) { subir(); preencherUsuario(); atualizarSelo(); }
      // 🚨 A versão anterior desmontava o menu quando o getSession não
      // confirmava — e o Pedro viu o menu aparecer e SUMIR depois de um
      // segundo. A sessão pode demorar a ser restaurada, o cliente pode estar
      // offline, a chamada pode falhar: em todos esses casos o menu evaporava
      // na cara de quem está logado. Menu que some é muito pior que menu a
      // mais numa página pública, e quem realmente barra o acesso e' a guarda
      // de sessão de cada página, não o desenho do menu.
      // Só chegamos aqui com menu na tela se o localStorage tinha token —
      // então a aposta certa e' manter.
    }).catch(function () {});
  }

  function desmontar() {
    ['aiarq-side', 'aiarq-scrim', 'aiarq-burger', 'aiarq-menu-css'].forEach(function (id) {
      var e = document.getElementById(id);
      if (e && e.parentNode) e.parentNode.removeChild(e);
    });
    document.body.style.overflow = '';
  }

  // ── Itens ───────────────────────────────────────────────────────────────
  // `aba` = destino no dashboard. No próprio dashboard vira switchTab (sem
  // recarregar); nas outras páginas vira link pra dashboard.html#aba.
  var ICONE = {
    painel: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    pasta: '<path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h4l2 2.5h7A1.5 1.5 0 0 1 19 10v7.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 3 17.5z"/>',
    revisao: '<path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 13.5l2 2 4-4.5"/>',
    planilha: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10M3 15h18"/>',
    cronograma: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/><path d="M7 14h5M10 17.5h6"/>',
    memorial: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M8.5 13h7M8.5 16.5h4.5"/>',
    comparativo: '<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
    download: '<path d="M12 3v11M8 10.5l4 4 4-4M4 18.5h16"/>',
    pessoa: '<circle cx="12" cy="8" r="3.6"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
    presente: '<path d="M4 11h16v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 20z"/><rect x="3" y="7" width="18" height="4" rx="1"/><path d="M12 7v14M12 7S10.5 3 8.4 3a2.2 2.2 0 0 0 0 4.4M12 7s1.5-4 3.6-4a2.2 2.2 0 0 1 0 4.4"/>',
    cartao: '<rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M2.5 10h19M6.5 14.8h3"/>',
    duvida: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.7"/><path d="M12 17.2h.01"/>',
    sair: '<path d="M15 17l5-5-5-5M20 12H9M12 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h6"/>',
    engrenagem: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'
  };

  // ── O projeto FIXADO ────────────────────────────────────────────────────
  // 🔑 A fixação mora na URL (?job_id=), nunca guardada no navegador. Decisão
  // do Pedro em 04/08: fechar a página e voltar depois abre o painel LIMPO.
  // Guardado, um link de e-mail abriria mostrando o menu de OUTRO projeto —
  // e o endereço deixaria de ser compartilhável.
  var JOB = (function () {
    try {
      var q = new URLSearchParams(location.search);
      // 🪤 O cronograma nasceu com ?job= e as outras com ?job_id=. Lendo só um
      // nome, o menu não fixava numa das telas e a pessoa perdia o contexto no
      // meio do caminho. Lê os dois, e a página do cronograma também.
      return q.get('job_id') || q.get('job') || '';
    } catch (_) { return ''; }
  })();
  var FIXADO = !!JOB;

  function url(pagina) { return pagina + '?job_id=' + encodeURIComponent(JOB); }

  // Menu da CONTA — quando ninguém está fixado.
  var GRUPOS_CONTA = [
    { titulo: '', itens: [
      { aba: 'home',            rotulo: 'Painel',          ic: 'painel' },
      { aba: 'meus-projetos',   rotulo: 'Meus projetos',   ic: 'pasta' },
      { aba: 'revisao',         rotulo: 'Revisão',         ic: 'revisao', selo: 'selo-revisao' },
      { aba: 'downloads',       rotulo: 'Downloads',       ic: 'download' }
    ]},
    { titulo: 'Conta', itens: [
      { aba: 'meu-cadastro',    rotulo: 'Meu cadastro',    ic: 'pessoa' },
      // 🚫 'Contribuições' saiu do menu em 05/08. Era formulário DUPLICADO —
      // o envio da planilha revisada e das cotações já vive dentro do
      // projeto, com o contexto aberto. E o contador mostrava 0 pra todo
      // mundo: em 102 projetos prontos, ZERO planilha revisada e ZERO
      // cotação enviadas. Entrada permanente de menu pra uma tela que nunca
      // teve conteúdo. A aba continua existindo pra link antigo não morrer.
      { aba: 'meus-pagamentos', rotulo: 'Meus pagamentos', ic: 'cartao' }
    ]},
    { titulo: 'Ajuda', itens: [
      { aba: 'como-funciona',   rotulo: 'Como funciona',   ic: 'duvida' },
      { href: 'faq.html',       rotulo: 'Dúvidas frequentes', ic: 'duvida' }
    ]}
  ];

  // Menu do PROJETO — os mesmos nomes, agora falando de UM projeto.
  // As páginas já existem; o menu só aponta pra elas com o job_id.
  function gruposProjeto() {
    return [
      // 🔑 A página do projeto virou 4 VISTAS (visao/quantitativo/cotacoes/
      // dados) em vez de 17 blocos empilhados na mesma rolagem. As que moram
      // lá dentro trocam SEM recarregar; revisão, cronograma e memorial
      // continuam sendo páginas próprias.
      // 🚨 SÓ O PROJETO. Nada de item de conta aqui.
      // A 1ª versão tinha um grupo "Sua conta" com Downloads e Meu cadastro, e
      // o Pedro apontou o problema na hora: "dentro do projeto tem download e
      // volta pro menu de fora, não dá isso, confunde". Clicar num item de
      // conta desfixava o projeto SEM avisar — o menu inteiro trocava debaixo
      // da pessoa. Menu de contexto fala do contexto; a ponte pra sair é o
      // "← Todos os projetos", que está lá em cima e é explícito.
      { titulo: '', itens: [
        { href: url('projeto.html') + '#visao',        rotulo: 'Visão geral',  ic: 'painel' },
        { href: url('projeto.html') + '#quantitativo', rotulo: 'Quantitativo', ic: 'planilha',    chave: 'quantitativo' },
        { href: url('revisao.html'),                   rotulo: 'Revisão',      ic: 'revisao',     chave: 'revisao' },
        { href: url('cronograma.html'),                rotulo: 'Cronograma',   ic: 'cronograma',  chave: 'cronograma' },
        { href: url('memorial.html'),                  rotulo: 'Memorial',     ic: 'memorial',    chave: 'memorial' },
        { href: url('projeto.html') + '#cotacoes',     rotulo: 'Comparativo',  ic: 'comparativo', chave: 'comparativo' },
        // 🪤 A vista se chama 'processamento'. Ela já se chamou 'dados', e o
        // menu ficou apontando pro nome velho: o item caía calado na visão
        // geral. Nome de vista e link nascem no mesmo lugar, de propósito.
        { href: url('projeto.html') + '#processamento', rotulo: 'Processamento', ic: 'duvida' }
      ]},
      // Próximas entregas do ciclo, já no roadmap. Não são links: item de menu
      // que não leva a lugar nenhum vira reclamação. Aqui está escrito que
      // ainda não existe, e é só isso que ele promete.
      { titulo: 'Em breve', embreve: true, itens: [
        { rotulo: 'Caderno de acabamentos', nota: 'FF&E', ic: 'memorial' },
        { rotulo: 'BDI Helper',             ic: 'planilha' }
      ]}
    ];
  }

  var GRUPOS = FIXADO ? gruposProjeto() : GRUPOS_CONTA;

  // ── CSS próprio ─────────────────────────────────────────────────────────
  var CSS = [
    '#aiarq-side{position:fixed;top:0;left:0;height:100%;width:248px;background:#fff;',
    'border-right:1px solid #E2E8F0;display:flex;flex-direction:column;padding:14px 12px;',
    'overflow-y:auto;overscroll-behavior:contain;transform:translateX(-100%);',
    'transition:transform .28s ease;z-index:10000;font-family:Inter,sans-serif}',
    '#aiarq-side.aberto{transform:translateX(0)}',
    '#aiarq-scrim{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(15,23,42,.45);',
    'z-index:9999;opacity:0;pointer-events:none;transition:opacity .28s ease}',
    '#aiarq-scrim.aberto{opacity:1;pointer-events:auto}',
    '.aiarq-topo{display:flex;align-items:center;justify-content:space-between;padding:2px 8px 14px;',
    'border-bottom:1px solid #E2E8F0;margin-bottom:14px}',
    '.aiarq-marca{display:flex;align-items:center;gap:9px;text-decoration:none}',
    '.aiarq-logo{width:32px;height:32px;border-radius:9px;background:linear-gradient(135deg,#4F46E5,#22D3EE);',
    'color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px}',
    '.aiarq-nome{font-weight:700;font-size:16px;color:#0F172A;letter-spacing:-.01em}',
    '.side-grp{margin-bottom:14px}',
    '.side-grp-t{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:#94A3B8;',
    'font-weight:700;padding:0 10px;margin-bottom:5px}',
    '.side-it{display:flex;align-items:center;gap:11px;width:100%;padding:8px 10px;border-radius:9px;',
    'font-size:14px;color:#334155;text-align:left;cursor:pointer;text-decoration:none;border:0;',
    'background:transparent;transition:background .15s,color .15s;font-family:inherit}',
    '.side-it:hover{background:#F1F5F9}',
    '.side-it.on{background:#EEF2FF;color:#4F46E5;font-weight:600}',
    // 🚨 Sem esta regra o link de admin aparece pra TODO cliente logado: a
    // .hidden do Tailwind e a .side-it têm a mesma especificidade, e quem vem
    // depois ganha. .side-it.hidden é (0,2,0) e vence as duas.
    '.side-it.hidden{display:none}',
    '.side-it svg{width:19px;height:19px;flex:none;stroke:currentColor;fill:none;stroke-width:1.75;',
    'stroke-linecap:round;stroke-linejoin:round;color:#94A3B8}',
    '.side-it:hover svg{color:#64748B}.side-it.on svg{color:#4F46E5}',
    '.side-badge{margin-left:auto;font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:99px;',
    'background:#FEF3C7;color:#92400E}',
    '.side-cta{display:flex;align-items:center;justify-content:center;gap:8px;margin:0 2px 16px;',
    'background:#4F46E5;color:#fff;font-weight:600;font-size:14px;padding:10px;border-radius:10px;',
    'border:0;cursor:pointer;width:calc(100% - 4px);text-decoration:none;font-family:inherit;',
    'box-shadow:0 6px 16px -6px rgba(79,70,229,.55)}',
    '.side-cta:hover{background:#4338CA}',
    // ── projeto fixado ──
    '.aiarq-sair-proj{display:flex;align-items:center;gap:7px;font-size:12px;color:#64748B;',
    'text-decoration:none;padding:7px 9px;border-radius:8px;margin-bottom:10px}',
    '.aiarq-sair-proj:hover{background:#F1F5F9;color:#334155}',
    '.aiarq-sair-proj svg{width:15px;height:15px;flex:none}',
    '.aiarq-fixado{background:linear-gradient(180deg,#F5F7FF,#fff);border:1.5px solid #4F46E5;',
    'border-radius:11px;padding:10px 11px;margin:0 2px 14px}',
    '.aiarq-fixado .tag{font-size:9.5px;font-weight:700;letter-spacing:.07em;',
    'text-transform:uppercase;color:#4F46E5}',
    '.aiarq-fixado b{display:block;font-size:13.5px;font-weight:700;margin-top:4px;',
    'line-height:1.3;color:#0F172A}',
    '.aiarq-fixado span#aiarq-proj-sub{font-size:11.5px;color:#64748B}',
    // estado de cada entregavel, ao lado do item
    '.side-est{margin-left:auto;font-size:10px;font-weight:700;padding:1px 6px;',
    'border-radius:99px;white-space:nowrap}',
    '.side-est.ok{background:#ECFDF5;color:#065F46}',
    '.side-est.velho{background:#FEF3C7;color:#92400E}',
    '.side-est.nao{background:#F1F5F9;color:#475569}',
    '.side-est.pend{background:#FEF3C7;color:#92400E}',
    // "Em breve": visivelmente inerte, pra ninguem tentar clicar
    '.side-embreve{color:#64748B;cursor:default}',
    '.side-embreve:hover{background:transparent}',
    '.side-embreve svg{color:#CBD5E1}',
    '.side-nota{margin-left:auto;font-size:10px;font-weight:700;padding:1px 6px;',
    'border-radius:99px;background:#F1F5F9;color:#94A3B8}',
    '.aiarq-rodape{margin-top:auto;border-top:1px solid #E2E8F0;padding-top:12px}',
    '.aiarq-beta{background:#ECFDF5;border-radius:9px;padding:9px 11px}',
    '.aiarq-beta b{display:block;font-size:12px;color:#065F46}',
    '.aiarq-beta span{font-size:11px;color:#047857}',
    '.aiarq-eu{display:flex;align-items:center;gap:9px;padding:11px 6px 6px}',
    '.aiarq-ini{width:30px;height:30px;border-radius:50%;background:#EEF2FF;color:#4F46E5;display:flex;',
    'align-items:center;justify-content:center;font-weight:600;font-size:11px;flex:none}',
    '#side-user-name{font-size:13px;font-weight:500;color:#334155;overflow:hidden;',
    'text-overflow:ellipsis;white-space:nowrap;min-width:0}',
    '#aiarq-burger,#aiarq-fechar{display:inline-flex;align-items:center;justify-content:center;',
    'background:transparent;border:0;cursor:pointer;padding:6px;border-radius:8px}',
    '#aiarq-burger:hover,#aiarq-fechar:hover{background:#F1F5F9}',
    // A partir de 1024px o menu vira fixo e o conteúdo anda pro lado. O
    // deslocamento é padding no <body> porque cada página tem uma estrutura
    // diferente — não dá pra contar com um wrapper comum.
    '@media (min-width:1024px){',
    '#aiarq-side{transform:translateX(0)}',
    '#aiarq-scrim{display:none}',
    '#aiarq-burger,#aiarq-fechar{display:none}',
    'body{padding-left:248px}',
    '}',

    // ── O "deslizar" entre as features ──────────────────────────────────
    // Quantitativo, cronograma, memorial e revisão são PÁGINAS separadas, então
    // clicar num item recarrega tudo — o menu piscava junto e a troca parecia
    // um solavanco. Refazer as quatro como painéis de uma página só seria o
    // caminho "certo" e é caro; isto entrega a mesma sensação de graça:
    //   @view-transition liga a transição entre documentos do mesmo site, e
    //   dar um nome próprio ao menu o EXCLUI da animação — ele fica parado
    //   enquanto só o conteúdo desliza.
    // Navegador que não suporta simplesmente navega como antes. Nada quebra.
    '@view-transition{navigation:auto}',
    '#aiarq-side{view-transition-name:aiarq-menu}',
    '::view-transition-old(root){animation:aiarq-sai .16s ease both}',
    '::view-transition-new(root){animation:aiarq-entra .22s ease both}',
    '@keyframes aiarq-entra{from{opacity:0;transform:translateX(16px)}}',
    '@keyframes aiarq-sai{to{opacity:0;transform:translateX(-10px)}}',
    // Quem pediu menos movimento no sistema não ganha movimento nenhum.
    '@media (prefers-reduced-motion:reduce){',
    '::view-transition-old(root),::view-transition-new(root){animation:none}',
    '}'
  ].join('');

  function svg(nome) {
    return '<svg viewBox="0 0 24 24">' + (ICONE[nome] || '') + '</svg>';
  }

  function montarItens() {
    var out = '';
    GRUPOS.forEach(function (g) {
      out += '<div class="side-grp">'
           + (g.titulo ? '<p class="side-grp-t">' + g.titulo + '</p>' : '');
      g.itens.forEach(function (it) {
        // "Em breve": não é link. Item de menu que não leva a lugar nenhum
        // vira reclamação; aqui está escrito que ainda não existe.
        if (g.embreve) {
          out += '<div class="side-it side-embreve">' + svg(it.ic) + it.rotulo
               + (it.nota ? '<span class="side-nota">' + it.nota + '</span>' : '')
               + '</div>';
          return;
        }
        var selo = it.selo
          ? '<span id="' + it.selo + '" class="side-badge" style="display:none"></span>' : '';
        // No menu do projeto cada item carrega o ESTADO do entregável, e é isso
        // que faz a regra nº7 virar navegação: dá pra ver o que está velho
        // antes de clicar. Preenchido depois, quando os dados chegam.
        if (it.chave) selo = '<span class="side-est" data-est="' + it.chave + '"></span>';
        if (it.href) {
          out += '<a class="side-it" href="' + it.href + '" data-arq="' + it.href + '"'
               + (it.chave ? ' data-chave="' + it.chave + '"' : '') + '>'
               + svg(it.ic) + it.rotulo + selo + '</a>';
        } else {
          // Sempre <a>: o link e o comportamento base e funciona sem JS. Se a
          // pagina souber trocar a aba sozinha, o clique intercepta.
          out += '<a class="side-it" href="dashboard.html#' + it.aba + '" data-tab="' + it.aba + '">'
               + svg(it.ic) + it.rotulo + selo + '</a>';
        }
      });
      out += '</div>';
    });
    return out;
  }

  function montar() {
    var st = document.createElement('style');
    st.id = 'aiarq-menu-css';
    st.textContent = CSS;
    document.head.appendChild(st);

    var scrim = document.createElement('div');
    scrim.id = 'aiarq-scrim';
    scrim.addEventListener('click', fechar);

    var side = document.createElement('aside');
    side.id = 'aiarq-side';
    // role=navigation: pra leitor de tela um <aside> e "conteudo lateral", nao
    // "menu". Com o papel certo, da pra pular direto pra navegacao.
    side.setAttribute('role', 'navigation');
    side.setAttribute('aria-label', 'Menu principal');
    side.innerHTML =
      '<div class="aiarq-topo">'
      + '<a class="aiarq-marca" href="index.html" title="Ir pra página inicial do site">'
      + '<span class="aiarq-logo">AI</span><span class="aiarq-nome">AI.arq</span></a>'
      + '<button id="aiarq-fechar" aria-label="Fechar menu">'
      + '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="#64748B" stroke-width="1.9" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>'
      + '</button></div>'
      + (FIXADO
          // 🚨 A SAÍDA VEM PRIMEIRO, não escondida no fim. Cliente preso dentro
          // de um projeto sem achar como voltar é pior que o problema que isto
          // resolve.
          ? '<a class="aiarq-sair-proj" href="dashboard.html#meus-projetos">'
            + '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>'
            + 'Todos os projetos</a>'
            + '<div class="aiarq-fixado">'
            + '<span class="tag">📌 Trabalhando em</span>'
            + '<b id="aiarq-proj-nome">Carregando…</b>'
            + '<span id="aiarq-proj-sub"></span></div>'
          : '<a class="side-cta" href="dashboard.html#novo-projeto" data-tab="novo-projeto">'
            + '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>'
            + 'Novo projeto</a>')
      + montarItens()
      + '<div class="side-grp">'
      + '<a id="btn-admin" class="side-it hidden" href="admin.html" style="color:#DC2626">'
      + svg('engrenagem') + 'Painel Admin</a></div>'
      + '<div class="aiarq-rodape">'
      + '<div class="aiarq-beta"><b>Beta gratuito</b><span>Projetos ilimitados, sem cartão</span></div>'
      + '<div class="aiarq-eu"><span id="side-user-initials" class="aiarq-ini">·</span>'
      + '<span id="side-user-name"></span></div>'
      + '<button id="btn-logout" class="side-it" style="color:#DC2626">'
      + svg('sair') + 'Sair</button></div>';

    document.body.appendChild(scrim);
    document.body.appendChild(side);

    side.querySelector('#aiarq-fechar').addEventListener('click', fechar);
    // Troca de VISTA dentro da própria página, sem recarregar. É o que faz a
    // navegação entre as partes do projeto ser instantânea — e o menu nem
    // pisca, porque a página nunca é descartada.
    side.addEventListener('click', function (ev) {
      var link = ev.target.closest('a[data-arq]');
      if (!link) return;
      var dArq = link.getAttribute('data-arq') || '';
      var arq = dArq.split('?')[0].split('#')[0];
      if (arq !== ARQ) return;                       // outra página: deixa navegar
      if (typeof window.mostrarVista !== 'function') return;
      ev.preventDefault();
      var h = dArq.indexOf('#') > -1 ? dArq.split('#')[1] : 'visao';
      // 🪤 Clicar no item da vista em que já se está empilhava uma entrada nova
      // no histórico. Tocar 5 vezes em "Quantitativo" enterrava a página
      // anterior sob 5 entradas iguais — e o Voltar do navegador virava um
      // botão que "não faz nada", cinco vezes, antes de finalmente sair.
      var atual = (location.hash || '').replace(/^#/, '');
      if (atual === h) { fechar(); return; }     // já estamos aqui
      // O hash na URL mantém o endereço compartilhável e o voltar do
      // navegador funcionando (há um listener de hashchange na página).
      try { history.pushState(null, '', '#' + h); } catch (_) {}
      window.mostrarVista(h);
      // 🪤 `fechar()`, NÃO `fecharMenuLateral()`. A função do componente chama-se
      // fechar; fecharMenuLateral só existe como global no dashboard.html. Aqui
      // dentro, o nome errado resolvia pro global NO DASHBOARD (funcionava por
      // acidente) e estourava ReferenceError em projeto.html — onde este
      // handler é justamente o que mais roda. No celular a gaveta ficava aberta
      // cobrindo a tela depois de escolher a vista.
      fechar();
    });

    side.addEventListener('click', function (ev) {
      var alvo = ev.target.closest('[data-tab]');
      if (!alvo) return;
      var aba = alvo.getAttribute('data-tab');
      if (sabeTrocarAba(aba)) {
        ev.preventDefault();
        window.switchTab(aba);      // troca de aba sem recarregar
      }
      // Se a pagina nao tem essa aba, o <a href> leva pro painel. Sem JS
      // tambem funciona: o link e o comportamento base.
    });
  }

  // ── Botão de três traços, dentro do cabeçalho da página ─────────────────
  // Cada página tem um header diferente, mas todas seguem
  // <header|nav ...><div class="... flex ...">. Encaixar ali evita botão
  // flutuante sobrepondo conteúdo.
  function plantarBurger() {
    var b = document.createElement('button');
    b.id = 'aiarq-burger';
    b.setAttribute('aria-label', 'Abrir menu');
    b.setAttribute('aria-expanded', 'false');
    b.setAttribute('aria-controls', 'aiarq-side');
    b.innerHTML = '<svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="#334155" stroke-width="1.9" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
    b.addEventListener('click', abrir);
    var casa = document.querySelector('header > div, nav > div');
    if (casa) {
      // 🪤 Entrar como PRIMEIRO FILHO de um flex justify-between faz o botão
      // virar um "item" da distribuição e empurra a logo/título pro centro em
      // 4 das 6 telas. Entrar DENTRO do primeiro filho (que costuma ser o
      // grupo da logo) mantém o cabeçalho como estava.
      var primeiroFilho = casa.firstElementChild;
      var ehGrupo = primeiroFilho &&
        /flex|items-center/.test(primeiroFilho.className || '') &&
        primeiroFilho.children.length > 0;
      if (ehGrupo) primeiroFilho.insertBefore(b, primeiroFilho.firstChild);
      else { casa.insertBefore(b, casa.firstChild); b.style.marginRight = 'auto'; }
    }
    else {
      b.style.position = 'fixed';
      b.style.top = '10px';
      b.style.left = '10px';
      b.style.zIndex = '9997';
      b.style.background = '#fff';
      b.style.boxShadow = '0 2px 10px rgba(15,23,42,.15)';
      document.body.appendChild(b);
    }
  }

  // ── Abrir / fechar ──────────────────────────────────────────────────────
  var ehDesktop = function () { return window.matchMedia('(min-width: 1024px)').matches; };

  // Gaveta fechada continua no DOM, só deslocada — e continuaria no caminho do
  // teclado. `inert` tira do foco, do clique e do leitor de tela.
  function sincronizarInerte() {
    var s = document.getElementById('aiarq-side');
    if (!s) return;
    if (!ehDesktop() && !s.classList.contains('aberto')) {
      s.setAttribute('inert', ''); s.setAttribute('aria-hidden', 'true');
    } else {
      s.removeAttribute('inert'); s.removeAttribute('aria-hidden');
    }
  }

  function abrir() {
    var s = document.getElementById('aiarq-side');
    var c = document.getElementById('aiarq-scrim');
    if (s) s.classList.add('aberto');
    if (c) c.classList.add('aberto');
    document.body.style.overflow = 'hidden';
    sincronizarInerte();
    // Guarda de onde o foco veio, pra devolver ao fechar. Sem isso o foco
    // ficava perdido no começo da página e quem navega por teclado tinha que
    // percorrer tudo de novo pra voltar ao botão.
    _focoAntes = document.activeElement;
    var burg0 = document.getElementById('aiarq-burger');
    if (burg0) { burg0.setAttribute('aria-expanded', 'true'); burg0.setAttribute('aria-label', 'Fechar menu'); }
    var primeiro = s && s.querySelector('.side-cta, .side-it');
    if (primeiro) { try { primeiro.focus({ preventScroll: true }); } catch (_) {} }
    document.addEventListener('keydown', _prenderTab, true);
  }

  var _focoAntes = null;

  // Enquanto a gaveta está aberta no celular, o Tab não pode passear pela
  // página atrás dela: quem usa teclado ou leitor de tela sai do menu sem
  // perceber e fica navegando um conteúdo que está coberto.
  function _prenderTab(ev) {
    if (ev.key !== 'Tab') return;
    var s = document.getElementById('aiarq-side');
    if (!s || !s.classList.contains('aberto') || ehDesktop()) return;
    var focaveis = s.querySelectorAll('a[href], button:not([disabled])');
    if (!focaveis.length) return;
    var primeiro = focaveis[0], ultimo = focaveis[focaveis.length - 1];
    if (ev.shiftKey && document.activeElement === primeiro) {
      ev.preventDefault(); ultimo.focus();
    } else if (!ev.shiftKey && document.activeElement === ultimo) {
      ev.preventDefault(); primeiro.focus();
    }
  }

  function fechar() {
    var s = document.getElementById('aiarq-side');
    var c = document.getElementById('aiarq-scrim');
    if (s) s.classList.remove('aberto');
    if (c) c.classList.remove('aberto');
    document.body.style.overflow = '';
    document.removeEventListener('keydown', _prenderTab, true);
    var burg1 = document.getElementById('aiarq-burger');
    if (burg1) { burg1.setAttribute('aria-expanded', 'false'); burg1.setAttribute('aria-label', 'Abrir menu'); }
    // Devolve o foco ANTES de marcar inerte: com o inert já aplicado o
    // navegador recusa o foco e ele cai no começo da página.
    if (_focoAntes && document.contains(_focoAntes)) {
      try { _focoAntes.focus({ preventScroll: true }); } catch (_) {}
    } else {
      var burg = document.getElementById('aiarq-burger');
      if (burg) { try { burg.focus({ preventScroll: true }); } catch (_) {} }
    }
    _focoAntes = null;
    sincronizarInerte();
  }

  function marcarAtivo(aba) {
    var alvo = aba || (EH_PAINEL
      ? ((location.hash || '#home').replace(/^#/, '') || 'home')
      : null);
    var itens = document.querySelectorAll('#aiarq-side .side-it');
    var hash = (location.hash || '').replace(/^#/, '');
    // 🪤 Numa página de vistas, chegar SEM hash é estar na visão geral. Sem
    // esta linha, abrir o projeto direto (sem #) não acendia item nenhum: o
    // cliente via o menu inteiro apagado sem entender onde estava.
    if (!hash && document.querySelector('.vista')) hash = 'visao';
    for (var i = 0; i < itens.length; i++) {
      var e = itens[i];
      var porAba = alvo && e.getAttribute('data-tab') === alvo;
      // 🪤 No menu do projeto o data-arq carrega a query
      // (projeto.html?job_id=...), então comparar com o nome do arquivo cru
      // nunca casaria e NENHUM item acenderia. Compara só o arquivo — e o
      // hash desempata Quantitativo × Comparativo, que moram na mesma página.
      var dArq = e.getAttribute('data-arq') || '';
      var arqDoItem = dArq.split('?')[0].split('#')[0];
      var hashDoItem = dArq.indexOf('#') > -1 ? dArq.split('#')[1] : '';
      var porArq = arqDoItem === ARQ && (hashDoItem ? hashDoItem === hash : !hash || !dArq);
      e.classList.toggle('on', !!(porAba || porArq));
    }
  }

  // ── Identidade e selo ───────────────────────────────────────────────────
  function preencherUsuario() {
    if (!window.sbClient || !window.sbClient.auth) return;
    window.sbClient.auth.getUser().then(function (r) {
      var u = r && r.data && r.data.user;
      if (!u) return;
      var m = u.user_metadata || {};
      var nome = m.full_name || m.name || u.email || '';
      var n = document.getElementById('side-user-name');
      if (n) n.textContent = nome;
      var ini = document.getElementById('side-user-initials');
      if (ini) {
        ini.textContent = (nome || '?').trim().split(/\s+/).slice(0, 2)
          .map(function (p) { return p[0]; }).join('').toUpperCase() || '?';
      }
      // Botão admin: quem autoriza de verdade é o backend. Isto é só a UI.
      if (window.aiarqEmailMatches) {
        window.aiarqEmailMatches(u.email, '97bda6eb7aa5b5426da844969ef4d756a77595bc18d12e5a49240598e89b74c2')
          .then(function (bate) {
            var ba = document.getElementById('btn-admin');
            if (bate && ba) ba.classList.remove('hidden');
          }).catch(function () {});
      }
    }).catch(function () {});
  }

  function ligarSair() {
    var b = document.getElementById('btn-logout');
    // No dashboard quem liga o clique é o script da própria página (ele limpa
    // outras coisas antes). Fora dele, o componente resolve.
    if (!b || EH_PAINEL) return;
    b.addEventListener('click', function () {
      try { localStorage.removeItem('aiarq_profile_complete'); } catch (_) {}
      if (window.sbClient && window.sbClient.auth) {
        window.sbClient.auth.signOut().finally(function () {
          window.location.href = 'login.html';
        });
      } else { window.location.href = 'login.html'; }
    });
  }

  // Uma chamada só alimenta o contador do menu da conta E o bloco do projeto
  // fixado com o estado de cada entregável. Acessório: falhou, não mostra nada.
  function atualizarSelo() {
    var base = window.API_BASE;
    if (!base || !window.authFetch) return;
    window.authFetch(base + '/api/meus-entregaveis')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        var lista = d.projetos || [];

        // contador global (menu da conta)
        var el = document.getElementById('selo-revisao');
        if (el) {
          var n = lista.filter(function (p) {
            return !p.arquivado && p.a_revisar > 0;
          }).length;
          if (n > 0) { el.textContent = n; el.style.display = ''; }
          else { el.style.display = 'none'; }
        }

        if (!FIXADO) return;
        var p = null;
        for (var i = 0; i < lista.length; i++) {
          if (lista[i].job_id === JOB) { p = lista[i]; break; }
        }
        if (!p) {
          // O projeto da URL não é deste usuário (ou não existe). Não invente
          // nome: diga o que se sabe e deixe a saída à mão.
          var nx = document.getElementById('aiarq-proj-nome');
          if (nx) nx.textContent = 'Projeto não encontrado';
          return;
        }
        var nm = document.getElementById('aiarq-proj-nome');
        // Vitrine: primeira letra maiúscula. O dado no banco não muda.
        if (nm) nm.textContent = (window.tituloProjeto || String)(p.nome);
        var sb = document.getElementById('aiarq-proj-sub');
        if (sb) {
          sb.textContent = [p.tipologia, (p.itens || 0) + ' itens']
            .filter(Boolean).join(' · ');
        }

        // estado de cada entregável ao lado do item
        function pinta(chave, texto, classe) {
          var e = document.querySelector('.side-est[data-est="' + chave + '"]');
          if (!e) return;
          e.textContent = texto;
          e.className = 'side-est ' + classe;
        }
        var ent = p.entregaveis || {};
        pinta('quantitativo', p.medido + ' medidos', p.medido > 0 ? 'ok' : 'nao');
        // 🚨 "ok" verde é uma AFIRMAÇÃO: quer dizer "está conferido". Projeto
        // que falhou no processamento ou que não tem item nenhum não conferiu
        // coisa alguma — dizer "ok" ali é dar por resolvido o que nunca
        // aconteceu. Nesse caso o certo é o traço: não há o que revisar.
        if (p.status !== 'done' || !(p.itens > 0)) pinta('revisao', '—', 'nao');
        else if (p.a_revisar > 0) pinta('revisao', String(p.a_revisar), 'pend');
        else pinta('revisao', 'ok', 'ok');
        ['cronograma', 'memorial', 'comparativo'].forEach(function (k) {
          var e = ent[k] || {};
          if (!e.disponivel) pinta(k, '—', 'nao');
          else if (e.desatualizado) pinta(k, 'velho', 'velho');
          else pinta(k, 'ok', 'ok');
        });
      })
      .catch(function () {});
  }

  // ── Sobe ────────────────────────────────────────────────────────────────
  // 🪤 O componente NÃO pode exigir estar dentro do <body>. No faq.html os
  // scripts moram no <head>, então document.body ainda é null quando este
  // arquivo roda — appendChild estourava e o menu simplesmente não nascia, sem
  // nada na tela explicando. Nas outras 5 páginas o script fica no body e
  // monta na hora. Quem decide não é a página: é aqui.
  function subir() {
    if (document.getElementById('aiarq-side')) return;   // já está de pé
    montar();
    plantarBurger();
    marcarAtivo();
    sincronizarInerte();
    ligarSair();
  }

  function arrancar() {
    if (pareceLogado()) subir();
    // A confirmação roda SEMPRE: ela corrige o palpite nos dois sentidos.
    confirmarComSupabase();
  }
  if (document.body) arrancar();
  else document.addEventListener('DOMContentLoaded', arrancar);

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') fechar();
  });

  // 🪤 Girar o celular (ou arrastar a janela) com a gaveta ABERTA deixava
  // body.overflow travado em 'hidden': acima de 1024px o fundo escuro some por
  // CSS e não sobra nada pra clicar — a página inteira ficava sem rolagem, sem
  // causa visível.
  try {
    var mq = window.matchMedia('(min-width: 1024px)');
    var aoCruzar = function () { fechar(); sincronizarInerte(); };
    if (mq.addEventListener) mq.addEventListener('change', aoCruzar);
    else if (mq.addListener) mq.addListener(aoCruzar);
  } catch (_) {}

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      if (document.getElementById('aiarq-side')) { preencherUsuario(); atualizarSelo(); }
    });
  } else if (document.getElementById('aiarq-side')) {
    // So chama o backend se o menu existe. Visitante anonimo no FAQ estava
    // acordando o Render com uma chamada autenticada que nunca ia servir pra
    // nada -- e o Render dorme; a primeira chamada custa 30 a 60 segundos.
    preencherUsuario(); atualizarSelo();
  }

  // API pública, usada pelo dashboard (switchTab chama marcarAtivo/fechar).
  window.aiarqMenu = {
    abrir: abrir, fechar: fechar, marcarAtivo: marcarAtivo,
    atualizarSelo: atualizarSelo
  };
})();
