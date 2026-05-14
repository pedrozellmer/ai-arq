/**
 * Widget de chat público do AI.arq.
 *
 * Bolinha flutuante no canto inferior direito que abre um painel
 * de conversa com a IA (sem login). Integra com /api/public/chat.
 *
 * Uso em qualquer página pública:
 *   <script src="chat-widget.js" defer></script>
 *
 * O script se injeta sozinho — não precisa configurar nada.
 */
(function() {
  'use strict';

  const API_BASE = 'https://ai-arq.onrender.com';
  const STORAGE_KEY = 'aiarq_chat_history';
  const LEAD_KEY = 'aiarq_chat_lead';
  const MAX_STORED_MSGS = 10;

  // Histórico em memória (também persiste em localStorage pra manter entre páginas)
  let messages = [];
  let lead = null;
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) messages = JSON.parse(saved).slice(-MAX_STORED_MSGS);
    const savedLead = localStorage.getItem(LEAD_KEY);
    if (savedLead) lead = JSON.parse(savedLead);
  } catch (_) {}

  // ═══ CSS injetado ═══
  const style = document.createElement('style');
  style.textContent = `
    #aiarq-chat-btn {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%);
      color: white;
      border: none;
      cursor: pointer;
      box-shadow: 0 8px 30px -8px rgba(79,70,229,0.5);
      z-index: 9998;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
      font-family: 'Inter', -apple-system, sans-serif;
    }
    #aiarq-chat-btn:hover {
      transform: scale(1.05);
      box-shadow: 0 12px 40px -8px rgba(79,70,229,0.6);
    }
    #aiarq-chat-btn .pulse {
      position: absolute;
      inset: 0;
      border-radius: 50%;
      background: rgba(79,70,229,0.4);
      animation: aiarq-pulse 2s ease-out infinite;
    }
    @keyframes aiarq-pulse {
      0% { transform: scale(1); opacity: 0.7; }
      100% { transform: scale(1.6); opacity: 0; }
    }
    #aiarq-chat-panel {
      position: fixed;
      bottom: 100px;
      right: 24px;
      width: 380px;
      max-width: calc(100vw - 32px);
      height: 560px;
      max-height: calc(100vh - 140px);
      background: white;
      border-radius: 16px;
      box-shadow: 0 24px 60px -10px rgba(0,0,0,0.25);
      z-index: 9999;
      display: none;
      flex-direction: column;
      overflow: hidden;
      font-family: 'Inter', -apple-system, sans-serif;
    }
    #aiarq-chat-panel.open { display: flex; animation: aiarq-slideup 0.25s ease-out; }
    @keyframes aiarq-slideup {
      from { opacity: 0; transform: translateY(16px); }
      to { opacity: 1; transform: translateY(0); }
    }
    #aiarq-chat-header {
      background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%);
      color: white;
      padding: 16px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    #aiarq-chat-header .title {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    #aiarq-chat-header .avatar {
      width: 36px; height: 36px; border-radius: 10px;
      background: rgba(255,255,255,0.25);
      display: flex; align-items: center; justify-content: center;
      font-weight: 700; font-size: 13px;
    }
    #aiarq-chat-header .status {
      font-size: 11px; opacity: 0.85;
      display: flex; align-items: center; gap: 4px;
    }
    #aiarq-chat-header .status::before {
      content: ''; width: 6px; height: 6px; border-radius: 50%;
      background: #4ade80;
    }
    #aiarq-chat-close {
      background: rgba(255,255,255,0.15);
      border: none; cursor: pointer; color: white;
      width: 30px; height: 30px; border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
      transition: background 0.15s;
    }
    #aiarq-chat-close:hover { background: rgba(255,255,255,0.25); }
    #aiarq-chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      background: #f9fafb;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .aiarq-msg {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 13.5px;
      line-height: 1.5;
      word-wrap: break-word;
    }
    .aiarq-msg.user {
      align-self: flex-end;
      background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%);
      color: white;
      border-bottom-right-radius: 4px;
    }
    .aiarq-msg.assistant {
      align-self: flex-start;
      background: white;
      color: #1f2937;
      border: 1px solid #e5e7eb;
      border-bottom-left-radius: 4px;
    }
    .aiarq-msg.assistant strong { font-weight: 600; }
    .aiarq-msg.assistant a { color: #4f46e5; text-decoration: underline; }
    .aiarq-typing {
      align-self: flex-start;
      padding: 12px 16px;
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 14px;
      border-bottom-left-radius: 4px;
      display: flex;
      gap: 4px;
    }
    .aiarq-typing span {
      width: 7px; height: 7px; border-radius: 50%; background: #9ca3af;
      animation: aiarq-bounce 1.2s infinite;
    }
    .aiarq-typing span:nth-child(2) { animation-delay: 0.15s; }
    .aiarq-typing span:nth-child(3) { animation-delay: 0.3s; }
    @keyframes aiarq-bounce {
      0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
      30% { transform: translateY(-6px); opacity: 1; }
    }
    #aiarq-chat-input-wrap {
      border-top: 1px solid #e5e7eb;
      padding: 12px;
      background: white;
      display: flex;
      gap: 8px;
    }
    #aiarq-chat-input {
      flex: 1;
      border: 1px solid #d1d5db;
      border-radius: 10px;
      padding: 10px 14px;
      font-size: 13.5px;
      resize: none;
      outline: none;
      font-family: inherit;
      max-height: 80px;
    }
    #aiarq-chat-input:focus { border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.1); }
    #aiarq-chat-send {
      background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%);
      color: white;
      border: none;
      border-radius: 10px;
      padding: 0 16px;
      cursor: pointer;
      font-weight: 600;
      font-size: 13px;
      transition: opacity 0.15s;
    }
    #aiarq-chat-send:disabled { opacity: 0.5; cursor: not-allowed; }
    #aiarq-chat-footer {
      padding: 6px 12px;
      text-align: center;
      font-size: 10px;
      color: #9ca3af;
      background: white;
      border-top: 1px solid #f3f4f6;
    }
    @media (max-width: 480px) {
      #aiarq-chat-panel {
        width: calc(100vw - 16px);
        right: 8px;
        bottom: 90px;
      }
      #aiarq-chat-btn { bottom: 16px; right: 16px; }
    }
  `;
  document.head.appendChild(style);

  // ═══ HTML do widget ═══
  const btn = document.createElement('button');
  btn.id = 'aiarq-chat-btn';
  btn.title = 'Fale com a IA do AI.arq';
  btn.innerHTML = `
    <span class="pulse"></span>
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path stroke-linecap="round" stroke-linejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/>
    </svg>
  `;

  const panel = document.createElement('div');
  panel.id = 'aiarq-chat-panel';
  panel.innerHTML = `
    <div id="aiarq-chat-header">
      <div class="title">
        <div class="avatar">AI</div>
        <div>
          <div style="font-weight:600;font-size:14px">AI.arq · Suporte</div>
          <div class="status">online agora</div>
        </div>
      </div>
      <button id="aiarq-chat-close" aria-label="Fechar">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M18 6L6 18M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <!-- FORM DE LEAD (mostrado ANTES do chat na 1ª vez) -->
    <div id="aiarq-chat-lead-form" style="padding:20px;background:#f9fafb;flex:1;overflow-y:auto;">
      <p style="font-size:13.5px;color:#1f2937;margin:0 0 4px 0;font-weight:600;">
        Antes de começar, me conta quem você é 👋
      </p>
      <p style="font-size:12px;color:#6b7280;margin:0 0 16px 0;line-height:1.5;">
        Assim consigo entrar em contato depois, se fizer sentido, e o time comercial recebe sua dúvida.
      </p>
      <div style="display:flex;flex-direction:column;gap:10px;">
        <div>
          <label style="font-size:11px;color:#6b7280;font-weight:500;display:block;margin-bottom:4px;">Nome *</label>
          <input id="aiarq-lead-name" type="text" placeholder="Seu nome completo"
            style="width:100%;padding:10px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;outline:none;box-sizing:border-box;font-family:inherit;" required/>
        </div>
        <div>
          <label style="font-size:11px;color:#6b7280;font-weight:500;display:block;margin-bottom:4px;">E-mail *</label>
          <input id="aiarq-lead-email" type="email" placeholder="seu@email.com"
            style="width:100%;padding:10px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;outline:none;box-sizing:border-box;font-family:inherit;" required/>
        </div>
        <div>
          <label style="font-size:11px;color:#6b7280;font-weight:500;display:block;margin-bottom:4px;">WhatsApp <span style="color:#9ca3af;font-weight:400;">(opcional)</span></label>
          <input id="aiarq-lead-phone" type="tel" placeholder="(00) 0 0000-0000"
            style="width:100%;padding:10px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;outline:none;box-sizing:border-box;font-family:inherit;"/>
        </div>
        <button id="aiarq-lead-submit"
          style="margin-top:6px;background:linear-gradient(135deg,#4f46e5 0%,#06b6d4 100%);color:white;border:none;border-radius:10px;padding:11px;font-weight:600;font-size:13px;cursor:pointer;font-family:inherit;">
          Começar conversa →
        </button>
        <p id="aiarq-lead-error" style="font-size:11px;color:#dc2626;margin:0;display:none;"></p>
        <p style="font-size:10px;color:#9ca3af;text-align:center;margin:8px 0 0 0;line-height:1.5;">
          Ao continuar, você concorda com os
          <a href="/termos.html" target="_blank" style="color:#6b7280;text-decoration:underline;">Termos</a>
          e a
          <a href="/privacidade.html" target="_blank" style="color:#6b7280;text-decoration:underline;">Política de Privacidade</a>.
        </p>
      </div>
    </div>

    <!-- CHAT (mostrado só DEPOIS do lead ser capturado) -->
    <div id="aiarq-chat-messages" style="display:none;"></div>
    <div id="aiarq-chat-input-wrap" style="display:none;">
      <textarea id="aiarq-chat-input" rows="1" placeholder="Digite sua dúvida..."></textarea>
      <button id="aiarq-chat-send" aria-label="Enviar">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
        </svg>
      </button>
    </div>
    <div id="aiarq-chat-footer" style="display:none;">
      Respostas por IA · use para dúvidas rápidas, não aconselhamento técnico
    </div>
  `;

  document.body.appendChild(btn);
  document.body.appendChild(panel);

  // ═══ Render messages ═══
  const msgsEl = document.getElementById('aiarq-chat-messages');
  function renderMessages() {
    msgsEl.innerHTML = messages.map(m => {
      // Converte links markdown/url simples e **bold**
      let html = escapeHtml(m.content)
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/(https?:\/\/\S+|ai\.arq\.br\/\S+)/g, '<a href="$1" target="_blank">$1</a>')
        .replace(/\n/g, '<br>');
      return `<div class="aiarq-msg ${m.role}">${html}</div>`;
    }).join('');

    // Se vazio, mostra mensagem de boas-vindas
    if (!messages.length) {
      msgsEl.innerHTML = `
        <div class="aiarq-msg assistant">
          Oi! 👋 Sou o assistente do <strong>AI.arq</strong>. Posso tirar dúvidas sobre o produto, preços, como funciona ou LGPD.<br><br>
          Algumas perguntas que os visitantes fazem:<br>
          • "Quanto custa?"<br>
          • "Que tipo de arquivo vocês aceitam?"<br>
          • "Vocês fazem orçamento ou só quantitativo?"<br>
          • "Como funciona o comparativo de fornecedores?"
        </div>
      `;
    }
    msgsEl.scrollTop = msgsEl.scrollHeight;
  }

  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function showTyping(on) {
    const existing = msgsEl.querySelector('.aiarq-typing');
    if (existing) existing.remove();
    if (on) {
      const el = document.createElement('div');
      el.className = 'aiarq-typing';
      el.innerHTML = '<span></span><span></span><span></span>';
      msgsEl.appendChild(el);
      msgsEl.scrollTop = msgsEl.scrollHeight;
    }
  }

  // ═══ Send ═══
  async function sendMessage() {
    const input = document.getElementById('aiarq-chat-input');
    const sendBtn = document.getElementById('aiarq-chat-send');
    const text = input.value.trim();
    if (!text) return;

    messages.push({ role: 'user', content: text });
    input.value = '';
    input.style.height = 'auto';
    renderMessages();
    showTyping(true);
    sendBtn.disabled = true;

    // Atualiza o lead com essa nova mensagem (best-effort)
    if (lead && lead.email) {
      fetch(`${API_BASE}/api/public/chat/lead`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          name: lead.name,
          email: lead.email,
          phone: lead.phone || '',
          source_page: window.location.pathname.split('/').pop() || 'index.html',
          first_question: messages[0]?.content || text,
        }),
      }).catch(() => {});
    }

    try {
      const res = await fetch(`${API_BASE}/api/public/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: messages.slice(-10),
          lead: lead ? { name: lead.name, email: lead.email } : null,
        }),
      });
      const data = await res.json();
      showTyping(false);

      if (data.error) {
        messages.push({
          role: 'assistant',
          content: data.message || 'Desculpe, deu erro. Tenta de novo ou manda e-mail pra contato@ai.arq.br',
        });
      } else {
        messages.push({ role: 'assistant', content: data.reply });
      }

      // Persiste
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-MAX_STORED_MSGS)));
      } catch (_) {}
      renderMessages();
    } catch (e) {
      showTyping(false);
      messages.push({
        role: 'assistant',
        content: 'Sem conexão no momento. Tenta de novo em instantes ou manda e-mail pra contato@ai.arq.br',
      });
      renderMessages();
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  // ═══ Exibe chat vs form de lead conforme estado ═══
  function showChatUI() {
    document.getElementById('aiarq-chat-lead-form').style.display = 'none';
    document.getElementById('aiarq-chat-messages').style.display = 'flex';
    document.getElementById('aiarq-chat-input-wrap').style.display = 'flex';
    document.getElementById('aiarq-chat-footer').style.display = 'block';
    renderMessages();
    setTimeout(() => document.getElementById('aiarq-chat-input').focus(), 100);
  }

  function showLeadForm() {
    document.getElementById('aiarq-chat-lead-form').style.display = 'block';
    document.getElementById('aiarq-chat-messages').style.display = 'none';
    document.getElementById('aiarq-chat-input-wrap').style.display = 'none';
    document.getElementById('aiarq-chat-footer').style.display = 'none';
    setTimeout(() => document.getElementById('aiarq-lead-name').focus(), 100);
  }

  // ═══ Submit do form de lead ═══
  async function submitLead() {
    const name = document.getElementById('aiarq-lead-name').value.trim();
    const email = document.getElementById('aiarq-lead-email').value.trim();
    const phone = document.getElementById('aiarq-lead-phone').value.trim();
    const err = document.getElementById('aiarq-lead-error');
    const btnSub = document.getElementById('aiarq-lead-submit');

    err.style.display = 'none';
    if (!name || name.length < 2) { err.textContent = 'Digite seu nome.'; err.style.display = 'block'; return; }
    if (!email || !email.includes('@') || !email.includes('.')) { err.textContent = 'Digite um e-mail válido.'; err.style.display = 'block'; return; }

    btnSub.disabled = true;
    btnSub.textContent = 'Salvando...';

    // Salva no backend (não bloqueia UX se der erro)
    try {
      await fetch(`${API_BASE}/api/public/chat/lead`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          name, email, phone,
          source_page: window.location.pathname.split('/').pop() || 'index.html',
          first_question: '',
        }),
      }).catch(() => {});
    } catch (_) {}

    lead = { name, email, phone };
    try { localStorage.setItem(LEAD_KEY, JSON.stringify(lead)); } catch (_) {}

    btnSub.disabled = false;
    btnSub.textContent = 'Começar conversa →';
    showChatUI();
  }

  // ═══ Event wiring ═══
  btn.addEventListener('click', () => {
    panel.classList.add('open');
    btn.style.display = 'none';
    if (lead) showChatUI();  // já tem lead, vai direto pro chat
    else showLeadForm();
  });

  document.getElementById('aiarq-chat-close').addEventListener('click', () => {
    panel.classList.remove('open');
    btn.style.display = 'flex';
  });

  document.getElementById('aiarq-lead-submit').addEventListener('click', submitLead);

  // Enter nos campos do form submete
  ['aiarq-lead-name', 'aiarq-lead-email', 'aiarq-lead-phone'].forEach(id => {
    document.getElementById(id).addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); submitLead(); }
    });
  });

  document.getElementById('aiarq-chat-send').addEventListener('click', sendMessage);

  const input = document.getElementById('aiarq-chat-input');
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 80) + 'px';
  });
})();
