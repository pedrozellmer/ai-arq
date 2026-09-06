/**
 * Modal de contato AI.arq — abre de qualquer página.
 *
 * Uso:
 *   <a onclick="aiArqContactOpen()">Contato</a>
 *   <button onclick="aiArqContactOpen('reclamacao')">Reclamar</button>
 *
 * O modal:
 * - Aparece em overlay sobre qualquer página
 * - Captura: nome, email, whatsapp opcional, tipo, assunto, mensagem
 * - POSTa em /api/contact (backend salva no Supabase)
 * - Mostra confirmação ao enviar
 * - Não interfere com chat-widget (são coisas diferentes)
 */
(function () {
  if (window.aiArqContactInjected) return;
  window.aiArqContactInjected = true;

  var API = (window.AIARQ_API_BASE || 'https://api.ai.arq.br');  // via Cloudflare (anexo é capado em 10 MB, cabe no limite)

  // ── CSS isolado ───────────────────────────────────────────────────
  var css = `
    .aicm-overlay {
      position: fixed; inset: 0; background: rgba(15, 23, 42, 0.7);
      z-index: 99998; display: none; align-items: center; justify-content: center;
      padding: 16px; backdrop-filter: blur(4px);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .aicm-overlay.open { display: flex; }
    .aicm-modal {
      background: #fff; border-radius: 20px; max-width: 520px; width: 100%;
      max-height: 90vh; overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
      animation: aicmSlideUp 0.3s ease;
    }
    @keyframes aicmSlideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    .aicm-header {
      padding: 24px 24px 0 24px; display: flex; align-items: flex-start;
      justify-content: space-between; gap: 12px;
    }
    .aicm-title { font-size: 20px; font-weight: 700; color: #0f172a; margin: 0; }
    .aicm-subtitle { font-size: 13px; color: #64748b; margin-top: 4px; }
    .aicm-close {
      background: none; border: none; cursor: pointer; padding: 4px;
      color: #94a3b8; transition: color 0.2s;
    }
    .aicm-close:hover { color: #0f172a; }
    .aicm-body { padding: 20px 24px 24px 24px; }
    .aicm-field { margin-bottom: 14px; }
    .aicm-label { display: block; font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 6px; }
    .aicm-input, .aicm-select, .aicm-textarea {
      width: 100%; padding: 10px 12px; border: 1.5px solid #e2e8f0;
      border-radius: 10px; font-size: 14px; color: #0f172a;
      transition: border-color 0.2s; box-sizing: border-box;
      font-family: inherit;
    }
    .aicm-input:focus, .aicm-select:focus, .aicm-textarea:focus {
      outline: none; border-color: #4f46e5;
    }
    .aicm-textarea { min-height: 100px; resize: vertical; }
    .aicm-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    @media (max-width: 480px) { .aicm-row { grid-template-columns: 1fr; } }
    .aicm-submit {
      width: 100%; padding: 12px 16px; background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%);
      color: #fff; border: none; border-radius: 12px; font-weight: 600; font-size: 15px;
      cursor: pointer; transition: opacity 0.2s; margin-top: 4px;
    }
    .aicm-submit:hover { opacity: 0.9; }
    .aicm-submit:disabled { opacity: 0.5; cursor: not-allowed; }
    .aicm-disclaimer { font-size: 11px; color: #94a3b8; text-align: center; margin-top: 12px; }
    .aicm-success {
      text-align: center; padding: 32px 16px;
    }
    .aicm-success-icon {
      width: 56px; height: 56px; border-radius: 50%; background: #dcfce7;
      color: #16a34a; display: flex; align-items: center; justify-content: center;
      margin: 0 auto 16px; font-size: 28px;
    }
    .aicm-success-title { font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 8px; }
    .aicm-success-msg { font-size: 14px; color: #64748b; margin-bottom: 20px; }
    .aicm-error {
      background: #fef2f2; border: 1px solid #fecaca; color: #991b1b;
      padding: 10px 12px; border-radius: 8px; font-size: 13px; margin-bottom: 12px;
    }
    .aicm-context-box {
      display: flex; gap: 12px; align-items: flex-start;
      background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 10px;
      padding: 12px 14px; margin-bottom: 16px;
    }
    .aicm-context-icon { font-size: 20px; line-height: 1; }
    .aicm-context-text { font-size: 13px; color: #1e1b4b; line-height: 1.5; }
    .aicm-context-text strong { color: #4f46e5; }
    .aicm-file-info { font-size: 11px; color: #16a34a; margin-top: 4px; }
  `;
  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  // ── HTML do modal ─────────────────────────────────────────────────
  var modal = document.createElement('div');
  modal.className = 'aicm-overlay';
  modal.id = 'aicm-overlay';
  // Semântica de diálogo modal — aria-modal + role + labelledby
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('aria-labelledby', 'aicm-title-h');
  modal.innerHTML = `
    <div class="aicm-modal" onclick="event.stopPropagation()">
      <div class="aicm-header">
        <div>
          <h2 class="aicm-title" id="aicm-title-h">Fale com a gente</h2>
          <p class="aicm-subtitle" id="aicm-subtitle-p">Dúvida, sugestão, reclamação, parceria — todas chegam aqui.</p>
        </div>
        <button class="aicm-close" onclick="aiArqContactClose()" aria-label="Fechar">
          <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>
      <div class="aicm-body" id="aicm-body">
        <form id="aicm-form" onsubmit="return aiArqContactSubmit(event)" enctype="multipart/form-data">
          <div id="aicm-error" class="aicm-error" style="display:none"></div>

          <!-- Box informativo (só aparece em modo ticket de projeto) -->
          <div id="aicm-context-box" class="aicm-context-box" style="display:none">
            <div class="aicm-context-icon">📋</div>
            <div class="aicm-context-text" id="aicm-context-text"></div>
          </div>

          <!-- Campos de identificação (escondidos em modo ticket) -->
          <div id="aicm-identity-fields">
            <div class="aicm-row">
              <div class="aicm-field">
                <label class="aicm-label" for="aicm-name">Seu nome *</label>
                <input class="aicm-input" type="text" id="aicm-name" name="name" required maxlength="200">
              </div>
              <div class="aicm-field">
                <label class="aicm-label" for="aicm-email">Seu email *</label>
                <input class="aicm-input" type="email" id="aicm-email" name="email" required maxlength="200">
              </div>
            </div>
            <div class="aicm-row">
              <div class="aicm-field">
                <label class="aicm-label" for="aicm-phone">WhatsApp (opcional)</label>
                <input class="aicm-input" type="tel" id="aicm-phone" name="phone" maxlength="50" placeholder="(21) 9 9999-9999">
              </div>
              <div class="aicm-field">
                <label class="aicm-label" for="aicm-type">Tipo *</label>
                <select class="aicm-select" id="aicm-type" name="type" required>
                  <option value="duvida">Dúvida</option>
                  <option value="sugestao">Sugestão</option>
                  <option value="reclamacao">Reclamação</option>
                  <option value="parceria">Parceria</option>
                  <option value="elogio">Elogio</option>
                  <option value="outro">Outro</option>
                </select>
              </div>
            </div>
          </div>

          <!-- Subject livre (modo geral) -->
          <div id="aicm-subject-free-wrap" class="aicm-field">
            <label class="aicm-label" for="aicm-subject">Assunto (opcional)</label>
            <input class="aicm-input" type="text" id="aicm-subject" name="subject" maxlength="300" placeholder="Ex: Dúvida sobre a planilha">
          </div>

          <!-- Subject pré-definido (modo ticket) -->
          <div id="aicm-subject-preset-wrap" class="aicm-field" style="display:none">
            <label class="aicm-label" for="aicm-subject-preset">Sobre o que é? *</label>
            <select class="aicm-select" id="aicm-subject-preset" name="subject_preset">
              <option value="item-errado">Item errado ou faltando na planilha</option>
              <option value="quantidade-incorreta">Quantidade não bate com o projeto</option>
              <option value="disciplina-nao-detectada">Disciplina não foi detectada</option>
              <option value="cor-classificacao">Classificação de cor (BRANCO/LARANJA) errada</option>
              <option value="erro-processamento">Erro durante o processamento</option>
              <option value="planilha-nao-baixa">Planilha XLSX não baixa</option>
              <option value="reprocessar">Pedir reprocessamento manual</option>
              <option value="outro">Outro assunto</option>
            </select>
          </div>

          <div class="aicm-field">
            <label class="aicm-label" for="aicm-message">Sua mensagem *</label>
            <textarea class="aicm-textarea" id="aicm-message" name="message" required maxlength="5000" placeholder="Conta pra gente o que tá acontecendo..."></textarea>
          </div>

          <!-- Upload de arquivo (sempre disponível, opcional) -->
          <div class="aicm-field">
            <label class="aicm-label" for="aicm-file">Anexo (opcional) <span style="font-weight:400;color:#94a3b8">— print, planilha, doc até 10MB</span></label>
            <input class="aicm-input" type="file" id="aicm-file" name="file" accept="image/*,.pdf,.xlsx,.xls,.csv,.doc,.docx,.txt" style="padding:6px 12px">
            <p id="aicm-file-info" class="aicm-file-info" style="display:none"></p>
          </div>

          <button type="submit" class="aicm-submit" id="aicm-submit-btn">Enviar mensagem</button>
          <p class="aicm-disclaimer">Resposta em até 24h úteis. Seus dados não são compartilhados.</p>
        </form>
      </div>
    </div>
  `;
  modal.addEventListener('click', function (e) {
    if (e.target === modal) aiArqContactClose();
  });
  document.body.appendChild(modal);

  // Guarda o HTML original do corpo do modal (o form completo). Depois de um
  // envio OK a tela de sucesso SUBSTITUI esse HTML (form destruído); sem
  // restaurar, reabrir o modal dava TypeError (campos sumiram) e travava na
  // tela de sucesso antiga — só um F5 resolvia. Bug pego na revisão 16/07.
  // O listener de change do arquivo é delegado no document (linha ~433) e o
  // onsubmit é inline, então ambos sobrevivem à restauração do innerHTML.
  var _aicmOriginalBody = (function () {
    var b = document.getElementById('aicm-body');
    return b ? b.innerHTML : null;
  })();
  var _aicmSent = false;
  function _aicmResetBody() {
    if (_aicmSent && _aicmOriginalBody != null) {
      var b = document.getElementById('aicm-body');
      if (b) b.innerHTML = _aicmOriginalBody;   // form volta zerado e habilitado
    }
    _aicmSent = false;
  }

  // ── API global ────────────────────────────────────────────────────
  // Modos:
  //   - geral (default): form completo, pessoa preenche tudo
  //   - ticket: esconde nome/email/whatsapp/tipo (já temos via session) e mostra
  //             dropdown de assuntos pré-definidos. Usado dentro de área autenticada
  //             tipo projeto.html. Usa: opts.mode='ticket', opts.contextLabel,
  //             opts.contextDetails, opts.name, opts.email, opts.type
  // Guarda quem tinha foco antes de abrir, pra devolver no close.
  var _aicmRestoreFocus = null;
  // Handler de Escape pra fechar o modal — registrado só enquanto aberto.
  var _aicmEscHandler = function (e) {
    if (e.key === 'Escape') aiArqContactClose();
  };
  window.aiArqContactOpen = function (opts) {
    // 06/09: o contato e a unica porta de fala do visitante que nao passa pelo chat, e abrir o
    // modal nao deixava rastro — so dava pra ver quem chegou ate o FIM (a mensagem no banco).
    try {
      if (window.trackEvent) {
        var _t = (typeof opts === 'string') ? opts : ((opts && opts.type) || 'geral');
        window.trackEvent('contato_abriu', { type: String(_t).slice(0, 20) });
      }
    } catch (_) {}
    _aicmRestoreFocus = document.activeElement;
    modal.classList.add('open');
    document.addEventListener('keydown', _aicmEscHandler);

    if (typeof opts === 'string') opts = { type: opts };
    opts = opts || {};

    _aicmResetBody();   // se o último uso terminou na tela de sucesso, restaura o form antes de mexer nos campos

    var isTicket = opts.mode === 'ticket';

    // Pré-preenche campos hidden (sempre, ainda que escondidos)
    if (opts.type) {
      var sel = document.getElementById('aicm-type');
      if (sel) sel.value = opts.type;
    }
    if (opts.name) {
      var n = document.getElementById('aicm-name');
      if (n) n.value = opts.name;
    }
    if (opts.email) {
      var e = document.getElementById('aicm-email');
      if (e) e.value = opts.email;
    }
    if (opts.phone) {
      var p = document.getElementById('aicm-phone');
      if (p) p.value = opts.phone;
    }
    if (opts.subject) {
      var subj = document.getElementById('aicm-subject');
      if (subj) subj.value = opts.subject;
    }
    if (opts.message) {
      var msg = document.getElementById('aicm-message');
      if (msg) msg.value = opts.message;
    }

    // Modo ticket: simplifica drasticamente o form
    var identity = document.getElementById('aicm-identity-fields');
    var subjectFreeWrap = document.getElementById('aicm-subject-free-wrap');
    var subjectPresetWrap = document.getElementById('aicm-subject-preset-wrap');
    var contextBox = document.getElementById('aicm-context-box');
    var contextText = document.getElementById('aicm-context-text');
    var titleH = document.getElementById('aicm-title-h');
    var subtitleP = document.getElementById('aicm-subtitle-p');

    if (isTicket) {
      // Esconde campos de identificação (já temos via session)
      identity.style.display = 'none';
      // Esconde subject livre, mostra dropdown
      subjectFreeWrap.style.display = 'none';
      subjectPresetWrap.style.display = '';
      // Pré-seleciona subject preset se passado
      if (opts.subjectPreset) {
        var presetSel = document.getElementById('aicm-subject-preset');
        if (presetSel) presetSel.value = opts.subjectPreset;
      }
      // Mostra context box com info do projeto
      if (opts.contextLabel || opts.contextDetails) {
        contextBox.style.display = 'flex';
        var html = '';
        if (opts.contextLabel) html += '<strong>' + (window.escapeHtml ? window.escapeHtml(opts.contextLabel) : opts.contextLabel) + '</strong><br>';
        if (opts.contextDetails) html += opts.contextDetails;  // contém <strong> do chamador; o CHAMADOR deve escapar dados dinâmicos
        contextText.innerHTML = html;
      }
      // Customiza title
      titleH.textContent = opts.titleOverride || 'Abrir chamado';
      subtitleP.textContent = opts.subtitleOverride || 'Conta o que aconteceu — a gente responde rapidinho.';
      // Limpa a mensagem se foi preenchida com template feio
      // (o modo ticket é mais limpo, usuário escreve o que quiser)
      if (opts.clearMessageInTicket !== false) {
        var msgEl = document.getElementById('aicm-message');
        if (msgEl) msgEl.value = '';
      }
    } else {
      // Modo geral: tudo visível
      identity.style.display = '';
      subjectFreeWrap.style.display = '';
      subjectPresetWrap.style.display = 'none';
      contextBox.style.display = 'none';
      titleH.textContent = 'Fale com a gente';
      subtitleP.textContent = 'Dúvida, sugestão, reclamação, parceria — todas chegam aqui.';
    }

    // Reset file input (pode ter ficado de envio anterior)
    var fileEl = document.getElementById('aicm-file');
    if (fileEl) {
      fileEl.value = '';
      var info = document.getElementById('aicm-file-info');
      if (info) info.style.display = 'none';
    }

    // Foco: pra ticket vai direto pra mensagem
    setTimeout(function () {
      var focusEl = isTicket
        ? document.getElementById('aicm-message')
        : (opts.name && opts.email)
          ? document.getElementById('aicm-message')
          : document.getElementById('aicm-name');
      if (focusEl) focusEl.focus();
    }, 100);
  };

  window.aiArqContactClose = function () {
    modal.classList.remove('open');
    document.removeEventListener('keydown', _aicmEscHandler);
    _aicmResetBody();   // fechou após enviar → restaura o form pra próxima abertura
    var err = document.getElementById('aicm-error');
    if (err) err.style.display = 'none';
    // Devolve foco pra origem (botão que abriu).
    if (_aicmRestoreFocus) {
      try { _aicmRestoreFocus.focus(); } catch (_) {}
      _aicmRestoreFocus = null;
    }
  };

  // Mapa de subjects pré-definidos -> texto humano
  var SUBJECT_PRESETS = {
    'item-errado':              'Item errado ou faltando na planilha',
    'quantidade-incorreta':     'Quantidade não bate com o projeto',
    'disciplina-nao-detectada': 'Disciplina não foi detectada',
    'cor-classificacao':        'Classificação de cor (BRANCO/LARANJA) errada',
    'erro-processamento':       'Erro durante o processamento',
    'planilha-nao-baixa':       'Planilha XLSX não baixa',
    'reprocessar':              'Pedir reprocessamento manual',
    'outro':                    'Outro assunto',
  };

  window.aiArqContactSubmit = function (event) {
    event.preventDefault();
    var btn = document.getElementById('aicm-submit-btn');
    var errorEl = document.getElementById('aicm-error');
    errorEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Enviando...';

    // Detecta se está em modo ticket (subject preset visível)
    var subjectPresetWrap = document.getElementById('aicm-subject-preset-wrap');
    var isTicket = subjectPresetWrap && subjectPresetWrap.style.display !== 'none';

    // Monta subject final
    var subject = '';
    if (isTicket) {
      var presetVal = document.getElementById('aicm-subject-preset').value;
      var presetLabel = SUBJECT_PRESETS[presetVal] || presetVal;
      // Anexa subject pre-preenchido (ex: "Projeto XYZ — ...") se existir
      var existing = document.getElementById('aicm-subject').value.trim();
      subject = existing ? '[' + presetLabel + '] ' + existing : presetLabel;
    } else {
      subject = document.getElementById('aicm-subject').value.trim();
    }

    // Usa FormData pra suportar upload de arquivo
    var fd = new FormData();
    fd.append('name',    document.getElementById('aicm-name').value.trim());
    fd.append('email',   document.getElementById('aicm-email').value.trim());
    fd.append('phone',   document.getElementById('aicm-phone').value.trim());
    fd.append('type',    document.getElementById('aicm-type').value);
    fd.append('subject', subject);
    fd.append('message', document.getElementById('aicm-message').value.trim());

    var fileEl = document.getElementById('aicm-file');
    var fileName = '';
    if (fileEl && fileEl.files && fileEl.files[0]) {
      var f = fileEl.files[0];
      if (f.size > 10 * 1024 * 1024) {
        errorEl.textContent = 'Arquivo grande demais (máx 10MB).';
        errorEl.style.display = 'block';
        btn.disabled = false;
        btn.textContent = 'Enviar mensagem';
        return false;
      }
      fd.append('file', f, f.name);
      fileName = f.name;
    }

    var sentEmail = document.getElementById('aicm-email').value.trim();

    fetch(API + '/api/contact', {
      method: 'POST',
      body: fd,  // sem Content-Type — browser seta multipart com boundary
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok) {
          try { if (window.trackEvent) window.trackEvent('contato_falhou', { motivo: 'servidor' }); } catch (_) {}
          errorEl.textContent = res.error || 'Erro ao enviar. Tenta de novo.';
          errorEl.style.display = 'block';
          btn.disabled = false;
          btn.textContent = 'Enviar mensagem';
          return;
        }
        // Sucesso — marca que o corpo virou tela de sucesso pra restaurar o form
        // ao reabrir/fechar (antes só um location.reload aos 5s, e só se o modal
        // já estivesse fechado — senão o form ficava destruído e travava).
        _aicmSent = true;
        // 🔒 so o tipo do assunto (slug NOSSO) — nunca o texto, o e-mail ou o anexo
        try { if (window.trackEvent) window.trackEvent('contato_enviado', {}); } catch (_) {}
        var _emEsc = (window.escapeHtml ? window.escapeHtml(sentEmail) : sentEmail);
        var emailHtml = sentEmail
          ? 'A gente responde em até 24h úteis no email <strong>' + _emEsc + '</strong>.'
          : 'A gente responde em até 24h úteis.';
        document.getElementById('aicm-body').innerHTML =
          '<div class="aicm-success">' +
          '<div class="aicm-success-icon">✓</div>' +
          '<div class="aicm-success-title">Mensagem enviada!</div>' +
          '<div class="aicm-success-msg">' + emailHtml + '</div>' +
          '<button class="aicm-submit" onclick="aiArqContactClose()" style="max-width:200px;margin:0 auto;">Fechar</button>' +
          '</div>';
      })
      .catch(function () {
        try { if (window.trackEvent) window.trackEvent('contato_falhou', { motivo: 'rede' }); } catch (_) {}
        errorEl.textContent = 'Erro de conexão. Tenta de novo em alguns segundos.';
        errorEl.style.display = 'block';
        btn.disabled = false;
        btn.textContent = 'Enviar mensagem';
      });

    return false;
  };

  // Mostra info do arquivo selecionado
  document.addEventListener('change', function (ev) {
    if (ev.target && ev.target.id === 'aicm-file') {
      var info = document.getElementById('aicm-file-info');
      if (!info) return;
      var f = ev.target.files && ev.target.files[0];
      if (f) {
        var sizeKB = Math.round(f.size / 1024);
        var sizeStr = sizeKB > 1024 ? (sizeKB / 1024).toFixed(1) + ' MB' : sizeKB + ' KB';
        info.textContent = '✓ ' + f.name + ' (' + sizeStr + ')';
        info.style.display = 'block';
      } else {
        info.style.display = 'none';
      }
    }
  });

  // ── ESC fecha ─────────────────────────────────────────────────────
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && modal.classList.contains('open')) {
      aiArqContactClose();
    }
  });
})();
