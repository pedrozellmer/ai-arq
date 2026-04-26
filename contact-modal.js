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

  var API = (window.AIARQ_API_BASE || 'https://ai-arq.onrender.com');

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
  `;
  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  // ── HTML do modal ─────────────────────────────────────────────────
  var modal = document.createElement('div');
  modal.className = 'aicm-overlay';
  modal.id = 'aicm-overlay';
  modal.innerHTML = `
    <div class="aicm-modal" onclick="event.stopPropagation()">
      <div class="aicm-header">
        <div>
          <h2 class="aicm-title">Fale com a gente</h2>
          <p class="aicm-subtitle">Dúvida, sugestão, reclamação, parceria — todas chegam aqui.</p>
        </div>
        <button class="aicm-close" onclick="aiArqContactClose()" aria-label="Fechar">
          <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>
      <div class="aicm-body" id="aicm-body">
        <form id="aicm-form" onsubmit="return aiArqContactSubmit(event)">
          <div id="aicm-error" class="aicm-error" style="display:none"></div>
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
          <div class="aicm-field">
            <label class="aicm-label" for="aicm-subject">Assunto (opcional)</label>
            <input class="aicm-input" type="text" id="aicm-subject" name="subject" maxlength="300" placeholder="Ex: Dúvida sobre o cashback">
          </div>
          <div class="aicm-field">
            <label class="aicm-label" for="aicm-message">Sua mensagem *</label>
            <textarea class="aicm-textarea" id="aicm-message" name="message" required maxlength="5000" placeholder="Conta pra gente o que tá acontecendo..."></textarea>
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

  // ── API global ────────────────────────────────────────────────────
  window.aiArqContactOpen = function (preselectType) {
    modal.classList.add('open');
    if (preselectType) {
      var sel = document.getElementById('aicm-type');
      if (sel) sel.value = preselectType;
    }
    setTimeout(function () { document.getElementById('aicm-name').focus(); }, 100);
  };

  window.aiArqContactClose = function () {
    modal.classList.remove('open');
    var err = document.getElementById('aicm-error');
    if (err) err.style.display = 'none';
  };

  window.aiArqContactSubmit = function (event) {
    event.preventDefault();
    var btn = document.getElementById('aicm-submit-btn');
    var errorEl = document.getElementById('aicm-error');
    errorEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Enviando...';

    var data = {
      name: document.getElementById('aicm-name').value.trim(),
      email: document.getElementById('aicm-email').value.trim(),
      phone: document.getElementById('aicm-phone').value.trim(),
      type: document.getElementById('aicm-type').value,
      subject: document.getElementById('aicm-subject').value.trim(),
      message: document.getElementById('aicm-message').value.trim(),
    };

    fetch(API + '/api/contact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok) {
          errorEl.textContent = res.error || 'Erro ao enviar. Tenta de novo.';
          errorEl.style.display = 'block';
          btn.disabled = false;
          btn.textContent = 'Enviar mensagem';
          return;
        }
        // Sucesso
        document.getElementById('aicm-body').innerHTML = `
          <div class="aicm-success">
            <div class="aicm-success-icon">✓</div>
            <div class="aicm-success-title">Mensagem enviada!</div>
            <div class="aicm-success-msg">A gente recebeu sua mensagem e responde em até 24h úteis no email <strong>${data.email}</strong>.</div>
            <button class="aicm-submit" onclick="aiArqContactClose()" style="max-width:200px;margin:0 auto;">Fechar</button>
          </div>
        `;
        // Reset depois de fechar
        setTimeout(function () {
          var b = document.getElementById('aicm-body');
          if (b && !modal.classList.contains('open')) {
            location.reload();  // reset simples — recarrega o modal
          }
        }, 5000);
      })
      .catch(function () {
        errorEl.textContent = 'Erro de conexão. Tenta de novo em alguns segundos.';
        errorEl.style.display = 'block';
        btn.disabled = false;
        btn.textContent = 'Enviar mensagem';
      });

    return false;
  };

  // ── ESC fecha ─────────────────────────────────────────────────────
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && modal.classList.contains('open')) {
      aiArqContactClose();
    }
  });
})();
