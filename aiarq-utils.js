// ═══════════════════════════════════════════════════════════════════
// aiarq-utils.js — utilitários compartilhados entre HTMLs do AI.arq
// ═══════════════════════════════════════════════════════════════════
//
// Antes desse arquivo, cada HTML duplicava: SUPABASE_URL, anon key,
// API_BASE, cliente Supabase, authFetch, downloadProtected, escapeHtml.
// Risco: variável com nome diferente (sb vs sbClient — armadilha #6 do
// CLAUDE.md), fix-em-um-lugar-só, drift de implementação.
//
// Este arquivo expõe TUDO em `window.*` pra não dar conflito:
//   - window.sbClient (cliente Supabase oficial)
//   - window.sb       (alias compat — alguns HTMLs usam esse nome)
//   - window.API_BASE
//   - window.SUPABASE_URL
//   - window.SUPABASE_ANON_KEY
//   - window.authFetch(url, opts)
//   - window.downloadProtected(url, filename)
//   - window.openPdfProtected(url)   ← abre PDF em nova aba (não força download)
//   - window.escapeHtml(s)
//   - window.aiArqNotify              ← shim toast/alert
//
// Como usar nos HTMLs:
//   <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2" defer></script>
//   <script src="aiarq-utils.js" defer></script>
//
// IMPORTANTE: ambos com `defer` pra ordem ser preservada e rodarem só
// depois do DOM. Scripts que dependem de sbClient/authFetch também
// precisam usar `defer` ou ficar inline no fim do <body>.

(function () {
  'use strict';

  // ─── Constantes ───────────────────────────────────────────────
  // Supabase anon key é PÚBLICA por design — RLS protege o resto.
  // Source of truth: este arquivo. NÃO duplicar nos HTMLs.
  const SUPABASE_URL      = 'https://kqjabzwgbfuivzlcfvvu.supabase.co';
  const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI';
  // API geral passa pelo Cloudflare (proxy laranja em api.ai.arq.br → protege,
  // esconde origem, permite rate-limit). 23/07.
  const API_BASE          = 'https://api.ai.arq.br';
  // 🪤 UPLOAD DE CAD vai DIRETO pro Render, FORA do Cloudflare: o backend aceita
  // até 450 MB (main.py:5970, projetos grandes), mas o Cloudflare Free CORTA em
  // 100 MB — passar upload grande pelo proxy daria 413 antes de chegar no backend.
  // Use API_UPLOAD_BASE em /api/process, /api/project/{id}/add-file e
  // /api/estimate-price (29/08 — estimativa acima de 100 MB morria no CF). Só esses.
  const API_UPLOAD_BASE   = 'https://ai-arq.onrender.com';

  window.SUPABASE_URL      = SUPABASE_URL;
  window.SUPABASE_ANON_KEY = SUPABASE_ANON_KEY;
  window.API_BASE          = API_BASE;
  window.API_UPLOAD_BASE   = API_UPLOAD_BASE;


  // ═══════════════════════════════════════════════════════════════
  //  TELEMETRIA — FICA ANTES DO GUARDA DO SUPABASE, DE PROPÓSITO
  // ═══════════════════════════════════════════════════════════════
  // 🚨 28/08/2026. O blog é a MAIOR porta de entrada do produto — no dia
  // 28/08, das páginas que gente de verdade abriu, TODAS eram post de blog
  // (zero na home, zero no cadastro). E os 26 posts não tinham telemetria
  // nenhuma: todo número de funil que a gente olhava ignorava a principal
  // fonte de visita.
  //
  // 🪤 Não bastava incluir este arquivo no blog. O guarda do supabase-js
  // logo abaixo faz `return` quando o SDK não está carregado — e o blog é
  // página estática, sem SDK. O arquivo entrava e saía antes de definir o
  // `trackEvent`. A alternativa seria carregar o SDK inteiro do Supabase em
  // 26 páginas estáticas só pra registrar uma visita: troca ruim.
  //
  // 🔑 Telemetria não depende de banco: ela só faz POST /api/track. Então
  // sobe pra cá e passa a existir com ou sem SDK. Tudo daqui pra baixo
  // continua exigindo o Supabase, como antes.
  // 🔒 LGPD intacta: o `trackEvent` continua checando consentimento, e o
  // blog já carrega o `cookie-consent.js`.


  // ─── trackEvent ──────────────────────────────────────────────
  // Telemetria leve de uso (Painel de Atividade no admin). Fire-and-forget:
  // nunca bloqueia a UI, nunca lança. POST /api/track → grava em usage_events
  // (RLS on, só o backend lê). Sem ferramenta de 3rd-party (LGPD tranquilo).
  //   trackEvent('open_project', { job_id: '...' })
  // 23/08/2026 (board): na PRIMEIRA visita o consentimento ainda é nulo, então
  // view_landing/view_login/view_cadastro eram descartados — e depois do "aceitar"
  // ninguém reenviava. Agora: sem resposta → fila (máx. 20); aceitou → a fila
  // sai; recusou → a fila morre. Nada grava sem o "sim" (LGPD intacta).
  var _trackFila = [];
  window.addEventListener('aiarq:consent-changed', function (ev) {
    try {
      var d = ev && ev.detail;
      var fila = _trackFila; _trackFila = [];
      if (d && d.analytics === true) fila.forEach(function (q) { window.trackEvent(q.event, q.meta); });
    } catch (e) {}
  });
  window.trackEvent = function (event, meta) {
    try {
      if (!event) return;
      // LGPD (opt-in do banner de cookies): SÓ rastreia se o usuário consentiu
      // com analytics. Sem consentimento — declinado OU ainda não respondido —
      // não grava nada. Honra a promessa "telemetria só com seu sim".
      try {
        var _consent = JSON.parse(localStorage.getItem('aiarq_cookie_consent') || 'null');
        if (!_consent) { if (_trackFila.length < 20) _trackFila.push({ event: event, meta: meta }); return; }
        if (_consent.analytics !== true) return;
      } catch (e) { return; }
      // cid = id anônimo do navegador (localStorage) → dá pra contar VISITANTE
      // único e seguir o funil (visita → cadastro) mesmo sem login.
      let _cid = '';
      try {
        _cid = localStorage.getItem('aiarq_cid') || '';
        if (!_cid) { _cid = 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10); localStorage.setItem('aiarq_cid', _cid); }
      } catch (e) { /* localStorage indisponível */ }
      // src = origem first-touch (de onde o visitante chegou) — pra atribuir o funil
      let _src = '';
      try { var _s0 = JSON.parse(localStorage.getItem('aiarq_src') || 'null'); _src = (_s0 && _s0.label) ? String(_s0.label).slice(0, 40) : ''; } catch (e) {}
      // 🚨 28/08/2026 — ESTA LINHA MATAVA A TELEMETRIA NO BLOG, EM SILÊNCIO.
      // Era `_sbClient.auth.getSession()` direto. Em página estática (o blog)
      // o `_sbClient` NÃO existe — o guarda lá em cima retorna antes de criar
      // — e a chamada estourava. Morria calada porque o corpo inteiro desta
      // função está num `try/catch` com o comentário "telemetria nunca quebra
      // nada": ela nunca quebrou a página, e nunca mandou nada também.
      //
      // 🪤 O QUE ME ENGANOU: mover o bloco pra antes do guarda fez o
      // `trackEvent` EXISTIR no blog. Conferi no DOM vivo — função presente,
      // zero erro no console, consentimento concedido. Parecia pronto. Só que
      // o evento não chegava ao banco. "Existe" não é "funciona".
      //
      // 🔑 Sessão é OPCIONAL: serve pra atribuir o evento a quem está logado.
      // Leitor de blog não está logado. Sem cliente, manda anônimo — que é o
      // certo pra essa página.
      // 🪤 USA `window.sbClient`, NÃO `_sbClient`. O `_sbClient` é `const`
      // declarado DEPOIS deste bloco: em página onde o guarda retorna, ele
      // nunca é inicializado e fica na zona morta temporal — e `typeof` NÃO
      // protege contra TDZ em `let`/`const`, estoura `ReferenceError` igual.
      // Morreria calado do mesmo jeito. `window.sbClient` é propriedade comum:
      // simplesmente `undefined` quando não existe.
      var _sb = (typeof window !== 'undefined') ? window.sbClient : null;
      var _sessao = (_sb && _sb.auth)
        ? _sb.auth.getSession()
        : Promise.resolve({ data: { session: null } });
      _sessao.then(({ data: { session } }) => {
        const u = (session && session.user) ? session.user : null;
        const body = JSON.stringify({
          event: String(event).slice(0, 60),
          user_id: u ? u.id : '',
          user_email: u ? (u.email || '') : '',
          job_id: (meta && meta.job_id) ? String(meta.job_id) : '',
          path: (location.pathname || '').slice(0, 200),
          meta: Object.assign({ cid: _cid, src: _src }, meta || {}),
        });
        // 🚨 Manda o token quando há sessão (09/08). O backend passou a IGNORAR
        // user_id/user_email do corpo e só aceitar identidade que o token prove
        // — sem este header, todo evento de quem está logado viraria anônimo e
        // o painel de Atividade esvaziaria. Deslogado segue sem header, que é o
        // caso normal aqui: a rota é aberta de propósito.
        const _h = { 'Content-Type': 'application/json' };
        if (session && session.access_token) {
          _h['Authorization'] = 'Bearer ' + session.access_token;
        }
        // keepalive: o evento sobrevive mesmo se a página for fechada logo
        // após (ex.: clicou em baixar e saiu). Erro engolido de propósito.
        fetch(API_BASE + '/api/track', {
          method: 'POST',
          headers: _h,
          body: body,
          keepalive: true,
        }).catch(() => {});
      }).catch(() => {});
    } catch (e) { /* telemetria nunca quebra nada */ }
  };

  // ─── clique marcado: data-track ──────────────────────────────
  // Um ouvinte SÓ, delegado no documento. Elemento com `data-track="nome"`
  // (ou dentro de um) vira evento `clique:nome`.
  //
  // 🚨 POR QUE MARCADO E NÃO "TUDO" (11/08/2026): capturar todo clique gera
  // milhares de eventos de <div> sem nome — muito dado e nenhuma resposta — e
  // aumenta a superfície de dado pessoal sem necessidade. Marcamos só os pontos
  // que respondem uma dúvida MEDIDA. Hoje são duas:
  //   1) a janela de 2 minutos: 39 de 39 clientes que subiram projeto em 60
  //      dias fizeram isso em menos de 30 min, mediana 2 min. Ninguém voltou
  //      depois. Queremos saber onde os 17% que nunca sobem param.
  //   2) o funil da revisão: `revision_feedback` tem 0 linhas desde sempre.
  //
  // 🪤 O DENOMINADOR É 37%. `trackEvent` só dispara pra quem aceitou cookie de
  // análise — medido em 11/08: 19 de 51 clientes. Serve pra COMPARAR (o botão A
  // é mais clicado que o B), NÃO pra número absoluto ("42% dos clientes
  // clicam"). Ver o aviso no painel de Atividade.
  document.addEventListener('click', function (ev) {
    try {
      var alvo = ev.target && ev.target.closest ? ev.target.closest('[data-track]') : null;
      if (!alvo) return;
      var nome = (alvo.getAttribute('data-track') || '').trim();
      if (!nome) return;
      var meta = {};
      // rótulo visível ajuda a ler o painel sem abrir o HTML
      var _t = (alvo.getAttribute('aria-label') || alvo.textContent || '').replace(/\s+/g, ' ').trim();
      if (_t) meta.rotulo = _t.slice(0, 60);
      // 🪤 NÃO dá pra registrar clique em botão desabilitado: por especificação
      // o navegador não dispara evento nenhum em `<button disabled>`. Cheguei a
      // escrever `if (alvo.disabled) meta.desabilitado = true` e o teste no DOM
      // provou que era código morto. Se um dia quisermos medir "tentou clicar
      // sem poder", tem que ser um envelope clicável em volta do botão.
      var _job = new URLSearchParams(location.search).get('job_id');
      if (_job) meta.job_id = _job;
      window.trackEvent('clique:' + nome.slice(0, 40), meta);
    } catch (e) { /* nunca quebra o clique do cliente */ }
  }, true);   // captura: pega mesmo se o handler do elemento parar a propagação
  // 🩸 31/08/2026 — ESTE BLOCO ESTAVA DEPOIS DO `return` DO GUARDA ABAIXO.
  // No BLOG (página estática, sem supabase-js) o arquivo saía no return e a
  // captura de origem NUNCA rodava: visitante novo registrava view_blog_post
  // SEM `src` e, se depois se cadastrasse, o first-touch já estava perdido —
  // o referrer vira ai.arq.br e ele é carimbado como "direto".
  // 🪤 Na 1ª tentativa deste conserto eu recortei o bloco por índice de string
  // e deixei o `};` final pra trás: a função ficou ABERTA e engoliu o resto do
  // arquivo, incluindo `window.sbClient = _sbClient`. Sintaxe VÁLIDA, login
  // MORTO em produção por 12 min. Recorte de código se faz por LINHA e se
  // confere pelo comportamento (sbClient existe?), não pela ausência de erro.
  // ─── Origem (first-touch attribution) ────────────────────────
  // Guarda UMA VEZ de onde o visitante chegou (referrer + UTM/?origem=).
  // First-party (só localStorage, zero 3rd-party). Usado no cadastro pra
  // atribuir a conta e, com consentimento, no funil. NÃO sobrescreve — o
  // PRIMEIRO toque é o que conta (a pessoa pode navegar antes de cadastrar).
  function _classifyRef(host) {
    if (!host) return '';
    host = host.toLowerCase();
    if (/instagram|l\.instagram|ig\./.test(host)) return 'instagram';
    if (/wa\.me|whatsapp/.test(host)) return 'whatsapp';
    if (/t\.me|telegram/.test(host)) return 'telegram';
    if (/google\./.test(host)) return 'google';
    if (/bing\.|duckduckgo|search\.yahoo/.test(host)) return 'busca';
    if (/facebook|fb\.me|\bfb\./.test(host)) return 'facebook';
    if (/linkedin|lnkd\.in/.test(host)) return 'linkedin';
    if (/youtube|youtu\.be/.test(host)) return 'youtube';
    if (/ai\.arq\.br/.test(host)) return 'direto';   // navegação interna → 'direto' (antes voltava '' e o fallback gravava 'ai.arq.br' como origem)
    return host.replace(/^www\./, '');
  }
  (function _captureSource() {
    try {
      if (localStorage.getItem('aiarq_src')) return;   // first-touch: não sobrescreve
      var params = new URLSearchParams(location.search || '');
      var utm_source = (params.get('utm_source') || params.get('origem') || '').slice(0, 40);
      var utm_medium = (params.get('utm_medium') || '').slice(0, 40);
      var utm_campaign = (params.get('utm_campaign') || params.get('campanha') || '').slice(0, 60);
      var refHost = '';
      try { if (document.referrer) refHost = new URL(document.referrer).hostname; } catch (e) {}
      var label = utm_source || _classifyRef(refHost) || (refHost ? refHost.replace(/^www\./, '') : 'direto');
      localStorage.setItem('aiarq_src', JSON.stringify({
        label: String(label).slice(0, 40),
        utm_source: utm_source, utm_medium: utm_medium, utm_campaign: utm_campaign,
        ref: refHost.slice(0, 80), landing: (location.pathname || '').slice(0, 80),
      }));
    } catch (e) { /* nunca quebra nada */ }
  })();
  window.aiArqSource = function () {
    try { return JSON.parse(localStorage.getItem('aiarq_src') || 'null'); } catch (e) { return null; }
  };

  // ─── Cliente Supabase ─────────────────────────────────────────
  // Defensivo: se o <script> do supabase-js não carregou (rede ruim,
  // CDN fora do ar), avisa no console em vez de quebrar tudo silenciosamente.
  if (!window.supabase || typeof window.supabase.createClient !== 'function') {
    // 🪤 28/08/2026: era `console.error` e a mensagem dizia que tudo quebrava.
    // Desde que a telemetria subiu pra ANTES deste guarda, isso deixou de ser
    // verdade: numa página estática (o blog) o `trackEvent` funciona e só o
    // que depende de banco fica de fora. Erro vermelho pra situação esperada
    // treina todo mundo a ignorar o console — e aí o erro real passa batido.
    console.info('[aiarq-utils] sem supabase-js nesta página: telemetria ATIVA, ' +
                  'recursos de banco (login, projetos) indisponíveis. Se esta ' +
                  'página PRECISA de banco, inclua o supabase-js ANTES deste arquivo.');
    return;
  }

  const _sbClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  // Expor com os DOIS nomes pra evitar armadilha #6: alguns HTMLs
  // historicamente chamam de `sb`, outros de `sbClient`. Mantém ambos
  // apontando pro mesmo cliente — refactor é zero-diff de comportamento.
  window.sbClient = _sbClient;
  window.sb       = _sbClient;

  // ─── Notificação (toast com fallback alert) ──────────────────
  // toast.js carrega via defer — se ainda não montou window.toast,
  // cai pro alert nativo. Bug Daniela 2026-05-18 mostrou que silenciar
  // erro de download é pior que feio.
  const notify = {
    warn:  (m) => (window.toast ? window.toast.warn(m)    : alert(m)),
    error: (m) => (window.toast ? window.toast.error(m)   : alert(m)),
    info:  (m) => (window.toast ? window.toast.info(m)    : alert(m)),
    ok:    (m) => (window.toast ? window.toast.success(m) : alert(m)),
  };
  window.aiArqNotify = notify;

  // ─── Impressão digital de e-mail ─────────────────────────────
  // 28/07: o repositório é PÚBLICO. Antes, e-mails de pessoas reais
  // (admin e testadores) ficavam em texto claro nos HTMLs — qualquer um
  // lia. Agora comparamos pelo hash SHA-256.
  //
  // ⚠️ Isto NÃO é controle de segurança: hash de e-mail é conferível por
  // quem já conhece o endereço. Serve pra não EXPOR o dado pessoal.
  // A autorização de verdade é sempre no backend (`_require_admin`).
  window.aiarqEmailHash = async function (email) {
    const norm = String(email == null ? '' : email).trim().toLowerCase();
    if (!norm || !window.crypto || !crypto.subtle) return '';
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(norm));
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
  };

  // Confere se o e-mail bate com um hash ou com uma lista de hashes.
  window.aiarqEmailMatches = async function (email, hashes) {
    const h = await window.aiarqEmailHash(email);
    if (!h) return false;
    return (Array.isArray(hashes) ? hashes : [hashes]).includes(h);
  };

  // ─── escapeHtml ──────────────────────────────────────────────
  // Versão mais defensiva (de revisao.html): aceita null/undefined
  // sem explodir (o `|| ''` na coerção).
  window.escapeHtml = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
    );
  };

  // ─── Nome do projeto pra exibir ──────────────────────────────
  // O cliente digita "teste 22/07" e a tela mostrava assim, minúsculo, em
  // título, no menu e no cartão. Fica feio.
  //
  // 🚨 SÓ NA EXIBIÇÃO. Nunca grave isto de volta: o nome é dado DELE, e
  // reescrever o que ele digitou é mexer no dado do cliente. Aqui é maquiagem
  // de vitrine, e some se ele renomear.
  //
  // 🪤 Sobe só a PRIMEIRA letra e não encosta no resto. Nada de Title Case:
  // "ConfortAr — Expansão HSM" viraria "Confortar — Expansão Hsm", e "HSM",
  // "FF&E", "AVAC" são siglas que o cliente escreveu de propósito.
  // Nome que começa com número ("22/07 teste") não tem o que capitalizar.
  window.tituloProjeto = function (nome) {
    var s = String(nome == null ? '' : nome).trim();
    if (!s) return 'Projeto sem nome';
    // Acha a primeira letra de verdade (pula aspas, hífen, número, emoji).
    var i = s.search(/[a-zA-ZÀ-ÿ]/);
    if (i === -1) return s;
    var c = s[i];
    if (c === c.toUpperCase()) return s;      // já está maiúscula: não mexe
    return s.slice(0, i) + c.toUpperCase() + s.slice(i + 1);
  };

  // ─── Datas/horas em horário de Brasília ──────────────────────
  // Postgres/Supabase guardam TUDO em UTC (timestamptz). Se a gente formatar
  // com toLocaleString SEM fixar o fuso, ele usa o RELÓGIO DO NAVEGADOR — muda
  // de máquina pra máquina e, dependendo da config, mostra UTC (+3h) em vez de
  // Brasília. Aqui fixamos America/Sao_Paulo pra TODO horário do sistema bater
  // com o de Brasília, em qualquer navegador (o do Pedro, de um cliente, etc).
  //   fmtBR(iso)                       → "16/07 15:32"
  //   fmtBR(iso, { year:'numeric' })   → acrescenta o ano
  //   fmtDataBR(iso)                   → só a data "16/07/2026"
  // O timeZone é aplicado POR ÚLTIMO de propósito: o caller escolhe o formato,
  // mas nunca troca o fuso — sistema inteiro em Brasília, sem exceção.
  const _TZ_BR = 'America/Sao_Paulo';
  window.fmtBR = function (iso, opts) {
    if (iso == null || iso === '') return '';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso);   // data inválida → devolve cru, nunca "Invalid Date"
      const o = Object.assign(
        { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' },
        opts || {}, { timeZone: _TZ_BR });
      return d.toLocaleString('pt-BR', o);
    } catch (e) { return String(iso); }
  };
  window.fmtDataBR = function (iso, opts) {
    if (iso == null || iso === '') return '';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso);
      const o = Object.assign({}, opts || {}, { timeZone: _TZ_BR });
      return d.toLocaleDateString('pt-BR', o);
    } catch (e) { return String(iso); }
  };

  // ─── Receitas de erro (compartilhadas: projeto.html e dashboard.html) ──
  // 23/08/2026 (board): a receita por família de erro existia só na página do
  // projeto; o dashboard mostrava o texto cru do banco na hora do upload.
  window.AIARQ_RECEITAS_ERRO = [
  {
    // Reenvio duplicado: não existe nada pra fazer. Pedir arquivo aqui é
    // pedir trabalho à toa — o botão de upload some.
    quando: /reenvio duplicado/i,
    semMotivo: true,
    semUpload: true,
    acao: 'Não precisa fazer nada aqui: este projeto foi reenviado e a versão boa é a mais recente, que está no seu painel.',
  },
  {
    // 🪤 53 dos 74 erros do banco são ESTE — o servidor reiniciou no meio do
    // processamento. O desenho do cliente não tem defeito nenhum, e mandar
    // ele converter pra DXF é jogar a nossa falha no colo dele.
    quando: /rein[íi]cio do servidor|redeploy do backend|interrompido por reinicializa/i,
    semMotivo: true,
    botao: 'Enviar o arquivo de novo',
    acao: 'Não foi o seu desenho: o nosso servidor reiniciou no meio do processamento. É só enviar o mesmo arquivo de novo no botão abaixo.',
  },
  {
    quando: /servidores de IA estavam sobrecarregados|sobrecarga tempor[áa]ria do servidor/i,
    botao: 'Enviar o arquivo de novo',
    acao: 'Não foi o seu desenho, e não precisa mexer nele: espere alguns minutos e envie o mesmo arquivo de novo no botão abaixo.',
  },
  {
    // Arquivo maior que o teto de processamento.
    // 🩸 03/09/2026 — ESTA RECEITA SOBREPUNHA A MENSAGEM DO MOTOR. No caso do
    // RAFAEL LIMA (job 28f140ef) o backend foi consertado pra parar de mandar
    // "divida / mande vários" pra quem mandou UMA prancha — e a tela devolvia
    // exatamente isso, porque os passos e a linha em negrito saem DAQUI, não do
    // texto do banco (projeto.html:1842-1858). Consertar a copy do motor e
    // deixar esta parada é consertar onde o cliente não olha.
    // 🔑 O front não sabe quantos arquivos vieram, então o conselho tem que ser
    // verdadeiro nos dois casos — e o que serve pra UMA prancha pesada é PURGE.
    quando: /grande demais|limite \d+ ?MB|excede o limite/i,
    titulo: 'Como resolver',
    passos: [
      'No CAD, rode <b>PURGE</b> no desenho — tira camadas e blocos que não são usados, e costuma cortar boa parte do peso',
      'Se o arquivo tem várias pranchas, exporte <b>só a que você quer medir</b>',
      'Envie de novo aqui',
    ],
    acao: 'Reexportar em DXF não resolve: DXF é texto puro e nasce de 30 a 50 vezes maior que o DWG. O que pesa é a quantidade de desenho, não o formato.',
  },
  {
    // DWG do AutoCAD Architecture/MEP com objetos "inteligentes" (proxy).
    // O passo a passo existe no motor desde sempre, mas nunca chegou ao
    // cliente: a mensagem era cortada em 500 caracteres no banco e morria
    // exatamente em "1. Abra o arqui".
    quando: /AEC|proxy|objetos? (inteligentes|especiais)|MEP ?\/ ?Architecture|Architecture ?\/ ?MEP/i,
    titulo: 'Como resolver, em 3 passos',
    passos: [
      'No AutoCAD, com o arquivo aberto, digite <b>EXPORTTOAUTOCAD</b> e Enter',
      'Escolha a versão <b>2013</b> e confirme — ele cria um arquivo novo, e o seu original não é alterado',
      'Abra esse arquivo novo, salve como <b>DXF</b> e envie aqui',
    ],
    botao: 'Enviar o DXF',
    acao: 'É esse DXF que a gente consegue medir — o "Salvar como DXF" direto não resolve neste caso.',
  },
  {
    quando: /chegou incompleto|truncado|corrompido/i,
    titulo: 'Como resolver',
    passos: [
      'Abra o arquivo no seu CAD e confira se ele abre inteiro',
      'Salve de novo (Salvar Como), de preferência em <b>DXF</b>',
      'Envie o arquivo novo aqui',
    ],
    acao: 'Se ele também não abrir no seu CAD, procure a última versão salva ou o backup automático (.bak).',
  },
  {
    // 🪤 Falha declaradamente NOSSA. Caía no texto padrão e virava "converta o
    // seu arquivo pra DXF" — cobrando do cliente uma conta que é da casa.
    quando: /problema t[ée]cnico do nosso lado|problema t[ée]cnico ao processar|instabilidade moment[âa]nea no servidor/i,
    semMotivo: true,
    botao: 'Enviar o arquivo de novo',
    acao: 'Não foi o seu desenho — foi um problema nosso. É só enviar o mesmo arquivo de novo no botão abaixo.',
  },
  {
    // Estouro de memória: o caminho é DIVIDIR. Mandar converter pra DXF piora,
    // porque DXF é bem maior que o DWG equivalente.
    quando: /estourou a mem[óo]ria|muito pesado|pesado demais/i,
    titulo: 'Como resolver',
    passos: [
      'Abra o arquivo no seu CAD',
      'Exporte <b>uma prancha por vez</b> (ou só as que você quer medir)',
      'Envie as pranchas separadas aqui — pode mandar várias de uma vez',
    ],
    acao: 'Separado, cada prancha mede igual — o que estoura é o arquivo inteiro de uma vez. Não adianta converter pra DXF: o DXF fica ainda maior.',
  },
  {
    // PDF escaneado/fotografado: as cotas viraram pixel. Não existe "salvar
    // como DXF" que resolva — é preciso o arquivo original.
    quando: /nenhum item quantific[áa]vel|imagem escaneada|escaneado ou fotografado/i,
    titulo: 'Como resolver',
    passos: [
      'Procure o arquivo <b>original</b> do projeto (o CAD, não o PDF escaneado)',
      'Salve em <b>DXF</b> — ou, se só tiver PDF, exporte um PDF direto do CAD (não digitalizado)',
      'Envie esse arquivo aqui',
    ],
    acao: 'Num PDF escaneado as cotas viraram imagem, e imagem não tem medida pra ler. Só o arquivo que saiu do CAD tem.',
  },
  {
    quando: /vers[ãa]o (muito )?recente|n[ãa]o conseguimos abrir automaticamente/i,
    titulo: 'Como resolver',
    passos: [
      'Abra o arquivo no seu CAD',
      'Salve como <b>DXF</b> (Salvar Como → DXF), versão 2013 ou mais antiga',
      'Envie o DXF aqui',
    ],
    botao: 'Enviar o DXF',
    acao: 'DXF é o formato que a gente lê melhor — nele a medição sai do desenho, não de estimativa.',
  },
];
  window.aiArqReceitaPara = function (txt) {
    try {
      var t = String(txt || '');
      for (var i = 0; i < window.AIARQ_RECEITAS_ERRO.length; i++) {
        if (window.AIARQ_RECEITAS_ERRO[i].quando.test(t)) return window.AIARQ_RECEITAS_ERRO[i];
      }
    } catch (e) {}
    return null;
  };
  // Texto simples (sem HTML) pra elementos com white-space: pre-line.
  window.aiArqErroComReceita = function (txt) {
    var r = window.aiArqReceitaPara(txt);
    if (!r) return String(txt || '');
    var semTag = function (s) { return String(s).replace(/<[^>]+>/g, ''); };
    var partes = [];
    if (!r.semMotivo && txt) partes.push(String(txt).replace(/\n?\s*Detalhe t[ée]cnico:[\s\S]*$/i, '').trim());
    if (r.passos && r.passos.length) partes.push((r.titulo || 'Como resolver') + ':\n' + r.passos.map(function (p, k) { return (k + 1) + '. ' + semTag(p); }).join('\n'));
    if (r.acao) partes.push(semTag(r.acao));
    return partes.join('\n\n');
  };

  // ─── authFetch ───────────────────────────────────────────────
  // Fetch com Bearer do Supabase. Backend exige JWT em endpoints
  // com ownership check (/api/items, /api/projects, /api/admin/*, etc).
  // 23/08/2026 (board): sem timeout, servidor pendurado virava "Carregando…"
  // eterno; 401 virava "Erro ao salvar: …" técnico. Agora: 45 s de teto (a não
  // ser que quem chamou passe o próprio signal) e aviso único de sessão expirada.
  var _avisouSessao = false;
  window.authFetch = async function (url, options) {
    options = options || {};
    const { data: { session } } = await _sbClient.auth.getSession();
    const headers = Object.assign({}, options.headers || {});
    if (session && session.access_token) {
      headers['Authorization'] = 'Bearer ' + session.access_token;
    }
    // 23/08 (auditoria): 45 s corta rotas que demoram DE PROPÓSITO — chat com IA
    // (backend espera 60 s), memorial "escrever com IA", reprocesso, upload de
    // planilha revisada. O cliente via erro e o servidor seguia trabalhando (e
    // cobrando o reprocesso). Essas rotas ganham teto próprio; o resto fica em 45 s.
    var _lentas = /\/api\/(agent|projeto\/[^/]+\/chat|memorial|cronograma)\b|\/(reprocess|add-file|upload|finalize)\b/i;
    var _teto = options.timeoutMs || (_lentas.test(String(url)) ? 180000 : 45000);
    var ctrl = null, timer = null;
    var init = Object.assign({}, options, { headers });
    delete init.timeoutMs;   // não vaza pro fetch
    if (!init.signal && typeof AbortController !== 'undefined') {
      ctrl = new AbortController(); init.signal = ctrl.signal;
      timer = setTimeout(function () { try { ctrl.abort(); } catch (e) {} }, _teto);
    }
    try {
      var resp = await fetch(url, init);
      if (resp.status === 401 && !_avisouSessao) {
        // 23/08 (auditoria): o toast escapa HTML, então o <a> saía como texto
        // cru e o cliente ficava sem caminho. Agora é frase simples + reset em
        // 60 s (se foi falha transitória do login, o aviso volta a poder sair).
        _avisouSessao = true;
        setTimeout(function () { _avisouSessao = false; }, 60000);
        try {
          notify.warn('Sua sessão expirou ou não deu pra confirmar seu login. Recarregue a página e entre de novo.');
        } catch (e) {}
      }
      return resp;
    } catch (err) {
      if (err && err.name === 'AbortError' && ctrl) {
        throw new Error('o servidor demorou mais de ' + Math.round(_teto / 1000) + ' s pra responder — tente de novo em instantes');
      }
      throw err;
    } finally {
      if (timer) clearTimeout(timer);
    }
  };

  // ─── downloadProtected ───────────────────────────────────────
  // Baixa endpoint protegido enviando Authorization header. Armadilha #9
  // do CLAUDE.md: <a href>, window.open() e window.location.href NÃO
  // enviam header customizado → backend retorna 401 mesmo com sessão
  // válida (bug Daniela 2026-05-18). Solução: fetch com Bearer → blob →
  // <a> programático → cleanup do object URL.
  // Devolve true quando o arquivo chegou na mão do cliente, false quando não — quem chama
  // decide o que fazer (o financeiro só registra o evento de export no true, 05/09/2026).
  window.downloadProtected = async function (url, filename) {
    const { data: { session } } = await _sbClient.auth.getSession();
    if (!session) {
      notify.warn('Sua sessão expirou. Faça login de novo pra baixar.');
      window.location.href = 'login.html';
      return false;
    }
    try {
      const resp = await fetch(url, {
        headers: { 'Authorization': 'Bearer ' + session.access_token }
      });
      if (!resp.ok) {
        let detail = 'HTTP ' + resp.status;
        try { const j = await resp.json(); detail = j.detail || detail; } catch (_) {}
        notify.error('Não consegui baixar o arquivo: ' + detail);
        return false;
      }
      const blob = await resp.blob();
      // Nome do arquivo: o que o servidor mandou no Content-Disposition (ex.: financeiro_obra_Casa_X.pdf),
      // com o `filename` da tela de reserva. O header só chega porque o CORS do backend o expõe.
      let nome = filename || 'arquivo';
      try {
        const cd = resp.headers.get('Content-Disposition') || '';
        const mUtf = /filename\*=(?:UTF-8|utf-8)''([^;]+)/.exec(cd);
        const mSimples = /filename="?([^";]+)"?/.exec(cd);
        if (mUtf && mUtf[1]) nome = decodeURIComponent(mUtf[1].trim());
        else if (mSimples && mSimples[1]) nome = mSimples[1].trim();
      } catch (_) {}
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = nome;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Pequeno delay pro browser começar o download antes do GC.
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
      return true;
    } catch (e) {
      // "Failed to fetch" / "The user aborted a request" não dizem nada a quem está esperando o arquivo
      var msg = (e && e.message) || String(e);
      if (/failed to fetch|networkerror|load failed/i.test(msg)) msg = 'sem conexão com o servidor';
      else if (/abort|timeout/i.test(msg)) msg = 'o servidor demorou demais pra responder';
      notify.error('Não consegui baixar o arquivo: ' + msg + '. Tente de novo em instantes.');
      return false;
    }
  };
  // Alias usado em templates inline com onclick (dashboard.html).
  window.aiArqDownloadProtected = window.downloadProtected;

  // ─── openPdfProtected ────────────────────────────────────────
  // Abre PDF protegido em nova aba (em vez de forçar download).
  // Bug 2026-06-02: mesmo problema do downloadProtected — endpoint
  // protegido não pode ser aberto via <a href>/target="_blank". Solução:
  // fetch com Bearer → blob URL → window.open na blob URL.
  window.openPdfProtected = async function (url) {
    const { data: { session } } = await _sbClient.auth.getSession();
    if (!session) {
      notify.warn('Sua sessão expirou. Faça login de novo pra abrir.');
      window.location.href = 'login.html';
      return;
    }
    try {
      const resp = await fetch(url, {
        headers: { 'Authorization': 'Bearer ' + session.access_token }
      });
      if (!resp.ok) {
        let detail = 'HTTP ' + resp.status;
        try { const j = await resp.json(); detail = j.detail || detail; } catch (_) {}
        notify.error('Não consegui abrir o PDF: ' + detail);
        return;
      }
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      window.open(blobUrl, '_blank', 'noopener');
      // 60s pra dar tempo do browser carregar o PDF antes de revogar.
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    } catch (e) {
      notify.error('Erro de rede ao abrir: ' + (e && e.message ? e.message : e));
    }
  };

})();
