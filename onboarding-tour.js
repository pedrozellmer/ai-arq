/**
 * Tour de boas-vindas AI.arq.
 *
 * Mostra automaticamente no primeiro acesso ao dashboard, baseado em
 * user_metadata.onboarded. Pode ser rechamado a qualquer momento via
 * window.aiArqTourStart().
 *
 * Não usa biblioteca externa — overlay próprio com 5 cards educativos.
 */
(function () {
  if (window.aiArqTourInjected) return;
  window.aiArqTourInjected = true;

  // Steps do tour — focados em explicar o fluxo, não dependem de
  // elementos específicos da página estarem visíveis (mais resiliente)
  var STEPS = [
    {
      icon: '👋',
      title: 'Bem-vindo ao AI.arq!',
      body: 'Em 30 segundos te mostro como tirar a planilha de quantitativos do seu primeiro projeto. <strong>Promessa: nada chato.</strong>',
      cta: 'Começar',
    },
    {
      icon: '📤',
      title: '1 · Suba seu CAD',
      body: 'No menu (avatar no canto superior direito) → <strong>Novo projeto</strong>. Aceita PDF, DWG ou DXF. Pode ser uma prancha ou várias num zip.',
      cta: 'Próximo',
    },
    {
      icon: '⏱️',
      title: '2 · Aguarde ~5 minutos',
      body: 'A IA lê todas as pranchas, identifica 18 disciplinas e monta a planilha. Você pode fechar a aba — quando voltar, vai estar pronta.',
      cta: 'Próximo',
    },
    {
      icon: '✏️',
      title: '3 · Revise e baixe',
      body: 'Itens em <strong style="color:#16a34a">VERDE</strong> foram medidos do CAD (confiável). Itens em <strong style="color:#ea580c">LARANJA</strong> foram estimados (revisar antes de usar). Cada item validado vira <strong>R$ 0,10 de cashback</strong> (até R$ 20).',
      cta: 'Próximo',
    },
    {
      icon: '🎁',
      title: 'Lembrete importante',
      body: 'Seu <strong>1º projeto é 100% grátis</strong>. Sem cartão, sem mensalidade. Se gostar, paga só pelos próximos. Bora?',
      cta: 'Subir meu CAD agora',
      ctaAction: 'goToUpload',
    },
  ];

  // ── CSS ──────────────────────────────────────────────────────
  var css = `
    .aiqt-overlay {
      position: fixed; inset: 0; background: rgba(15, 23, 42, 0.78);
      z-index: 99996; display: none; align-items: center; justify-content: center;
      padding: 16px; backdrop-filter: blur(6px);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .aiqt-overlay.open { display: flex; }
    .aiqt-card {
      background: #fff; border-radius: 24px; max-width: 440px; width: 100%;
      box-shadow: 0 25px 80px rgba(0,0,0,0.4);
      animation: aiqtSlideUp 0.35s cubic-bezier(0.16, 1, 0.3, 1);
      overflow: hidden;
    }
    @keyframes aiqtSlideUp {
      from { opacity: 0; transform: translateY(30px) scale(0.96); }
      to   { opacity: 1; transform: translateY(0) scale(1); }
    }
    .aiqt-progress {
      height: 4px; background: #e2e8f0; position: relative;
    }
    .aiqt-progress-bar {
      position: absolute; top: 0; left: 0; height: 100%;
      background: linear-gradient(90deg, #4f46e5, #06b6d4);
      transition: width 0.3s ease;
    }
    .aiqt-body { padding: 36px 32px 28px; text-align: center; }
    .aiqt-icon {
      font-size: 56px; line-height: 1; margin-bottom: 16px;
      animation: aiqtBounce 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
    }
    @keyframes aiqtBounce {
      0% { transform: scale(0); }
      60% { transform: scale(1.15); }
      100% { transform: scale(1); }
    }
    .aiqt-title {
      font-size: 22px; font-weight: 700; color: #0f172a; margin: 0 0 12px;
      line-height: 1.25;
    }
    .aiqt-body-text {
      font-size: 15px; color: #475569; line-height: 1.6; margin: 0 0 28px;
    }
    .aiqt-body-text strong { color: #0f172a; font-weight: 600; }
    .aiqt-actions {
      display: flex; gap: 10px; align-items: center; justify-content: space-between;
    }
    .aiqt-btn-skip {
      background: none; border: none; color: #94a3b8; font-size: 13px;
      cursor: pointer; padding: 8px 12px; transition: color 0.2s;
      font-family: inherit;
    }
    .aiqt-btn-skip:hover { color: #475569; }
    .aiqt-btn-nav {
      background: #f1f5f9; border: none; color: #475569; font-size: 13px;
      cursor: pointer; padding: 10px 16px; border-radius: 10px;
      font-weight: 500; transition: all 0.2s; font-family: inherit;
    }
    .aiqt-btn-nav:hover { background: #e2e8f0; }
    .aiqt-btn-next {
      background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%);
      color: #fff; border: none; font-size: 14px; font-weight: 600;
      cursor: pointer; padding: 12px 24px; border-radius: 12px;
      transition: opacity 0.2s; flex: 1; font-family: inherit;
      box-shadow: 0 8px 24px -8px rgba(79, 70, 229, 0.5);
    }
    .aiqt-btn-next:hover { opacity: 0.92; }
    .aiqt-step-counter {
      display: inline-block; font-size: 11px; color: #94a3b8;
      letter-spacing: 0.05em; text-transform: uppercase; font-weight: 600;
      margin-bottom: 12px;
    }
  `;
  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  // ── HTML do overlay ──────────────────────────────────────────
  var overlay = document.createElement('div');
  overlay.className = 'aiqt-overlay';
  overlay.id = 'aiqt-overlay';
  overlay.innerHTML = `
    <div class="aiqt-card" onclick="event.stopPropagation()">
      <div class="aiqt-progress"><div class="aiqt-progress-bar" id="aiqt-progress-bar" style="width:0%"></div></div>
      <div class="aiqt-body">
        <span class="aiqt-step-counter" id="aiqt-step-counter">1 de ${STEPS.length}</span>
        <div class="aiqt-icon" id="aiqt-icon">👋</div>
        <h2 class="aiqt-title" id="aiqt-title">...</h2>
        <p class="aiqt-body-text" id="aiqt-body-text">...</p>
        <div class="aiqt-actions">
          <button class="aiqt-btn-skip" id="aiqt-btn-skip" onclick="aiArqTourSkip()">Pular tour</button>
          <button class="aiqt-btn-nav" id="aiqt-btn-back" onclick="aiArqTourBack()" style="display:none">← Voltar</button>
          <button class="aiqt-btn-next" id="aiqt-btn-next" onclick="aiArqTourNext()">Começar →</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  var currentStep = 0;

  function render() {
    var step = STEPS[currentStep];
    var counter = document.getElementById('aiqt-step-counter');
    var icon    = document.getElementById('aiqt-icon');
    var title   = document.getElementById('aiqt-title');
    var body    = document.getElementById('aiqt-body-text');
    var btnNext = document.getElementById('aiqt-btn-next');
    var btnBack = document.getElementById('aiqt-btn-back');
    var bar     = document.getElementById('aiqt-progress-bar');

    counter.textContent = (currentStep + 1) + ' de ' + STEPS.length;
    icon.textContent = step.icon;
    title.textContent = step.title;
    body.innerHTML = step.body;
    btnNext.textContent = step.cta + (currentStep < STEPS.length - 1 ? ' →' : '');
    btnBack.style.display = currentStep > 0 ? '' : 'none';
    bar.style.width = ((currentStep + 1) / STEPS.length * 100) + '%';

    // Re-anima ícone
    icon.style.animation = 'none';
    void icon.offsetHeight;
    icon.style.animation = 'aiqtBounce 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)';
  }

  // ── API global ───────────────────────────────────────────────
  window.aiArqTourStart = function () {
    currentStep = 0;
    overlay.classList.add('open');
    render();
  };

  window.aiArqTourNext = function () {
    var step = STEPS[currentStep];
    // Última etapa pode ter ação especial
    if (currentStep === STEPS.length - 1) {
      markOnboarded();
      overlay.classList.remove('open');
      if (step.ctaAction === 'goToUpload') {
        // Tenta ir pra aba "Novo projeto" se estiver no dashboard
        if (typeof window.switchTab === 'function') {
          window.switchTab('novo-projeto');
        } else {
          window.location.href = '/dashboard.html#novo-projeto';
        }
      }
      return;
    }
    currentStep++;
    render();
  };

  window.aiArqTourBack = function () {
    if (currentStep > 0) {
      currentStep--;
      render();
    }
  };

  window.aiArqTourSkip = function () {
    markOnboarded();
    overlay.classList.remove('open');
  };

  // Salva no Supabase Auth metadata que o usuário já fez o onboarding
  function markOnboarded() {
    try {
      if (window.sb && window.sb.auth && typeof window.sb.auth.updateUser === 'function') {
        window.sb.auth.updateUser({ data: { onboarded: true } }).catch(function () {});
      } else if (window.sbClient && window.sbClient.auth && typeof window.sbClient.auth.updateUser === 'function') {
        window.sbClient.auth.updateUser({ data: { onboarded: true } }).catch(function () {});
      }
    } catch (e) { /* silenciar */ }
  }

  // ── Auto-trigger no primeiro acesso ──────────────────────────
  // Espera a sessão Supabase carregar e checa se é primeira vez
  function tryAutoStart(attempts) {
    attempts = attempts || 0;
    var sb = window.sb || window.sbClient;
    if (!sb || !sb.auth) {
      if (attempts < 30) {
        setTimeout(function () { tryAutoStart(attempts + 1); }, 200);
      }
      return;
    }
    sb.auth.getSession().then(function (res) {
      var session = res && res.data && res.data.session;
      if (!session) return;  // não autenticado, sai
      var meta = session.user.user_metadata || {};
      // Se já fez onboarding, não mostra de novo
      if (meta.onboarded === true) return;
      // Não mostra se a URL tem hash específica (ex: usuário clicou em link de aba)
      if (window.location.hash && window.location.hash !== '#home') return;
      // Espera 800ms pra dashboard carregar visualmente
      setTimeout(function () {
        window.aiArqTourStart();
      }, 800);
    }).catch(function () {});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { tryAutoStart(); });
  } else {
    tryAutoStart();
  }
})();
