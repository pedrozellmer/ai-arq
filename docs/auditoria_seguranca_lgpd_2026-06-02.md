# Auditoria de Segurança + LGPD AI.arq — 2026-06-02

Auditoria do frontend (`index.html`, `cadastro.html`, `login.html`, `dashboard.html`, `projeto.html`, `revisao.html`, `cronograma.html`, `faq.html`, `termos.html`, `privacidade.html`, `admin.html`, `visualizar-prancha.html`, `meus-projetos.html`, `precos.html`, `chat-widget.js`, `contact-modal.js`, `toast.js`, `onboarding-tour.js`) + headers HTTP da `https://ai.arq.br` + textos legais. Backend fora de escopo (auditado em `b5ddd07`).

---

## Resumo executivo

Risco geral: **Médio**. A higiene de secrets está perfeita (zero credencial sensível no código público), os textos legais (`privacidade.html`, `termos.html`) são detalhados e citam corretamente LGPD/Marco Civil/CDC, e a maioria das injeções de HTML passa por `esc()`/`escapeHtml()`. As lacunas concentram-se em **headers HTTP zero** (sem CSP, HSTS, X-Frame-Options — GitHub Pages não envia nada), **gate admin client-side** (depende inteiramente do RLS do Supabase), **CNPJ/razão social ausente nos termos** (Marco Civil exige identificar o fornecedor), **DPO genérico** (apenas `contato@ai.arq.br`), **senha mínima de 6 caracteres** e **0 verificação de idade** apesar da política exigir 18+.

| Eixo | Risco |
|---|---|
| Secrets / credenciais | 🟢 Baixo |
| XSS / injeção | 🟡 Médio |
| Headers HTTP | 🔴 Alto |
| LGPD — política | 🟢 Baixo |
| LGPD — consentimento na prática | 🟡 Médio |
| Conformidade jurídica BR | 🟡 Médio |
| Autorização (gates admin) | 🟡 Médio |

---

## 🟢 5 acertos (mantenha)

1. **Zero secret no frontend.** Grep amplo (`service_role`, `sk_live`, `pk_live`, `whsec_`, `REPLICATE_API`, `META_ACCESS`, `STRIPE_SECRET`, `ghp_`, `AKIA`, `eyJ...`) só achou a Supabase anon key (decoded: `role:anon`, exp 2036) — exatamente como deveria. Hook `.claude/hooks/scan_secrets.py` é a guarda. Zero `console.log` vazando email/cpf/token (única ocorrência: `dashboard.html:1241` é mensagem de erro estruturada).
2. **`privacidade.html` é completíssima.** Cita LGPD art. 5 (controlador/operador), art. 7 (4 bases legais visualmente separadas — execução de contrato, consentimento, legítimo interesse, obrigação legal), art. 12 (anonimização), art. 18 (6 direitos do titular com prazo de 15 dias úteis), art. 33 (transferência internacional — Anthropic, Supabase, Render, Stripe). Seção 1-A separa explicitamente cliente final = controlador, AI.arq = operador. Retenção declarada por tipo de dado (90 dias para arquivos, indefinido para heurísticas anonimizadas, 5 anos para eventos contábeis de cashback). Cookies declarados como apenas essenciais — o que tecnicamente dispensa banner sob LGPD/CONAR.
3. **`termos.html` cobre o que importa pra BR.** Foro RJ explícito (art. 15), Marco Civil/LGPD/CDC citados, limitação de responsabilidade clara, seções específicas pra upload de planilhas de fornecedor (2-A, com declaração de autorização), dados do cliente final (2-B, com papéis LGPD), logo do escritório (2-C, com licença não-exclusiva revogável), disclaimer "AI.arq NÃO substitui engenheiro de custos" em vermelho e em caixa-alta (seção 3).
4. **`esc()` / `escapeHtml()` é a regra em código que renderiza dado de DB.** `admin.html` (campo `m.message` de contato público), `dashboard.html` (cards de projeto via `escProj`/`escapeH` em todas as 9 ocorrências de `${p.project_name}`), `revisao.html` (`section header`), `chat-widget.js` (mensagens da IA — escapa antes de transformar markdown, regex de URL só aceita `https?://` ou `ai.arq.br/` — bloqueia `javascript:`). Zero uso de `eval()` ou `new Function()` no projeto.
5. **CPF é coletado tarde, com flow correto.** `cadastro.html:88-94` deixa o campo opcional ("só pedimos antes do 1º pagamento"). `dashboard.html:1232-1290` (`ensureCpfBeforeCheckout`) abre `#modal-cpf` antes do checkout Stripe se `profile.cpf_cnpj` estiver vazio. Decisão de 2026-05-24 honrada no código. `privacidade.html:122` reflete a regra. Minimização de dados pessoais sensíveis — princípio LGPD art. 6, III.

---

## 🔴 Críticos (P0)

### 1. Headers HTTP zero — `https://ai.arq.br` não envia nada
`curl -sI https://ai.arq.br` retorna só Cache/CORS/Server/ETag. **Faltam todos**: `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`. GitHub Pages não permite headers customizados via repo. Consequências: site pode ser embedado em iframe num phishing, MIME-sniffing pode interpretar `.txt` como `.html`, sem HSTS o primeiro acesso aceita downgrade pra HTTP. Não existe `<meta http-equiv="Content-Security-Policy">` em nenhum HTML — busquei.

**Fix sugerido:** adicionar em todos os HTMLs um conjunto mínimo via `<meta>`:
```html
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com; font-src https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://ai-arq.onrender.com https://kqjabzwgbfuivzlcfvvu.supabase.co; frame-ancestors 'none';">
<meta http-equiv="X-Content-Type-Options" content="nosniff">
<meta name="referrer" content="strict-origin-when-cross-origin">
```
HSTS via `<meta>` não funciona (precisa de header HTTP real). Solução estrutural: migrar o frontend pra Cloudflare Pages ou pôr o Cloudflare como proxy da `ai.arq.br` (gratuito, adiciona headers via Page Rule). Já é caminho recomendado pelo MCP do Cloudflare conectado.

### 2. Gate admin é client-side puro — depende 100% do RLS Supabase
`admin.html:866-900` compara `session.user.email !== 'zarelalopes@gmail.com'` no JS. Sem RLS bem configurado, qualquer usuário logado pode:
1. Chamar diretamente `sbClient.from('contact_messages').select('*')` via DevTools.
2. Ler todos os perfis (`profiles`), códigos beta (`beta_codes`), mensagens públicas com email/whatsapp de quem usou o formulário de contato (incluindo dados sensíveis dos leads do chat-widget).

Linhas 960, 1090, 1516, 1556, 1891 fazem `sbClient.from(...)` direto, sem `authFetch` (que vai pro backend). O backend fica entre o frontend e o DB **apenas** nos endpoints `/api/admin/*` (linha 854 — `authFetch` envia Bearer JWT). Tudo o que vai direto pro Supabase via JS depende exclusivamente das policies RLS.

**Fix:** auditar RLS de `contact_messages`, `profiles`, `beta_codes`, `chat_leads`, `nps_responses`, `rejected_items`, `inline_edits` no Supabase para garantir que SELECT/UPDATE/DELETE estejam restritos via `auth.jwt()->>'email' = 'zarelalopes@gmail.com'` ou via tabela `admins`. Pode rodar via MCP do Supabase. Backend já foi auditado mas RLS do admin.html não estava no escopo de `b5ddd07` (era backend Python, não cliente SDK). Recomendo um `auditoria_rls_2026-06-02.md` complementar.

### 3. Cadastro recolhe marketing opt-in junto, mas o checkbox de termos é "amarrado" — LGPD art. 8 exige consentimento granular
`cadastro.html:170-181`: dois checkboxes separados (marketing + termos). Termos amarra **dois consentimentos num só**: aceite dos Termos de Uso **e** da Política de Privacidade. Sob interpretação rigorosa do art. 8 §4 LGPD, consentimento precisa ser **destacado por finalidade**. Hoje o usuário não consegue, p. ex., aceitar os termos comerciais mas recusar uma cláusula específica de tratamento de dados — eles vão juntos.

Não é um bloqueador imediato (a prática do mercado é amarrar Termos+Privacidade desde sempre — Stripe, Notion, Supabase fazem igual), mas a ANPD vem se posicionando contra. Pra reforçar conformidade, separar:
- Checkbox 1 (obrigatório): "Li e aceito os Termos de Uso."
- Checkbox 2 (obrigatório): "Concordo com o tratamento dos meus dados conforme descrito na Política de Privacidade."
- Checkbox 3 (opcional): "Aceito receber novidades por e-mail e WhatsApp." ← já tá separado, ok.

---

## 🟡 Médios (P1)

### 4. Razão social / CNPJ / endereço da AI.arq não aparecem em `termos.html` nem `privacidade.html`
Marco Civil (art. 5, II) e CDC obrigam o fornecedor a ser identificável. Hoje os documentos só dizem "AI.arq". Falta:
- Razão social (provavelmente vai usar Fami Capital até criar PJ própria, conforme CLAUDE.md).
- CNPJ.
- Endereço comercial (ainda que seja o do Pedro).
- Nome do encarregado (DPO) — LGPD art. 41 exige identificar o encarregado pelo nome, e-mail e telefone. Hoje só tem `contato@ai.arq.br` genérico.

Decisão dependente do Pedro: aceita expor a Fami Capital como controladora oficial nessa fase, ou prefere registrar uma PJ AI.arq antes de formalizar?

### 5. Política de privacidade declara 18+ mas o cadastro não pergunta nem valida
`privacidade.html:670-676`: "destinado exclusivamente a usuários com 18 anos ou mais". `cadastro.html` não tem checkbox "declaro ser maior de 18", nem campo de data de nascimento. Caso um menor cadastre, formalmente o AI.arq vai dizer "não coletamos intencionalmente", mas em fiscalização ANPD a ausência de mecanismo de verificação é apontada como falha de diligência. Acréscimo simples:
```html
<label class="flex items-start gap-3 cursor-pointer">
  <input type="checkbox" id="declara_maioridade" name="declara_maioridade" required>
  <span class="text-sm text-gray-600">Declaro ser maior de 18 anos.</span>
</label>
```

### 6. XSS via `proj-title` → `aiArqContactOpen` (escape ausente em 1 caminho específico)
`projeto.html:791-804`: o nome do projeto é lido com `.textContent` (seguro), concatenado em uma string que contém HTML (`<strong>...</strong> · ${projName}`) e passado pra `aiArqContactOpen` como `contextDetails`. Esse valor cai em `contact-modal.js:277` (`contextText.innerHTML = html`).

Se o usuário batizar o projeto como `<img src=x onerror=alert(document.cookie)>` (campo livre, sem `maxlength` em `dashboard.html` na criação), ele vê o XSS no próprio modal de "Reportar problema" do seu projeto. Não escala (RLS isola por user_id), mas é vetor real de auto-XSS — e em caso de bug de RLS, fica explorável.

**Fix mínimo:** escapar `projName` antes de concatenar:
```js
const escName = projName.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const contextDetails = `Código: <strong>${jobId}</strong>${escName ? ' · ' + escName : ''}`;
```

### 7. Senha mínima de 6 caracteres em `login.html:211`
NIST SP 800-63B e OWASP recomendam mínimo de 8. Supabase Auth por default já aceita 6, mas é configurável. Aumentar pra 8 e ideal: validar contra a [Have I Been Pwned API](https://haveibeenpwned.com/API/v3#PwnedPasswords) no signup (k-anonymity, não envia senha).

### 8. `chat-widget.js` coleta lead pré-conversa sem checkbox de marketing
Linha 256-289 da `chat-widget.js`: usuário público fornece nome + e-mail + whatsapp pra começar a conversa, com texto "Ao continuar, você concorda com os Termos e a Política". O texto descreve a coleta como "se fizer sentido, e o time comercial recebe sua dúvida" — caracteriza uso comercial. Sob LGPD art. 7, I (consentimento) + art. 8 §4 (granularidade), seria mais seguro:
- Checkbox visível "Posso receber contato comercial sobre o AI.arq" (opt-in explícito, default unchecked).
- Manter o aviso de Termos como nota de rodapé.

### 9. `revisao.html:608, 619, 850, 878, 882, 924, 952, 1389, 1431, 1440, 1478, 1486, 1492` — `innerHTML` com SVG/HTML estático (OK), mas linhas que misturam dados (`document.getElementById('marcos-legais').innerHTML = html`) renderizam string concatenada com itens do projeto. Verifiquei `revisao.html:349-388` — escapa via `escapeHtml(sec)` e `escapeHtml(...).replace(/'/g,'&#39;')` no onclick. Mas o `renderItem(it, i)` (linha 385) não é mostrado nesse trecho — recomendo conferir se `it.description`, `it.observacao`, `it.section` passam por escape antes de virar HTML.

### 10. Página `admin.html` tem `tbody.innerHTML = leads.map(l => ... ${escapeH(l.first_question)} ...).join('')` — escape OK, mas o `title=` attribute em `<td title="${escapeH(l.first_question)}">` aceita as mesmas entidades. Verificado: linha 1144, o `escapeH` interno escapa aspas. OK. Mas linha 1142: `${escapeH(l.source_page || '—')}` no `<td>` — `source_page` vem de `window.location.pathname` (controlado pelo navegador do lead). Não vejo vetor de injeção real, mas vale registrar.

### 11. localStorage guardando dados pessoais
`cadastro.html:362, 371` salva rascunho com nome, whatsapp, cpf_cnpj, empresa em `localStorage` (`aiarq_cadastro_draft`). Se o usuário estiver em PC compartilhado e fechar a aba sem submeter, esses dados ficam visíveis pra próxima pessoa em DevTools. Solução: limpar o draft também em `beforeunload` se a aba for fechada por mais de X minutos, ou pelo menos avisar no rascunho ("estes dados ficam neste navegador, limpe se for um PC compartilhado").

`chat-widget.js:17` (`LEAD_KEY = 'aiarq_chat_lead'`) — guarda nome+email+phone do lead público. Mesma observação: dado pessoal em localStorage de PC potencialmente compartilhado.

### 12. `dashboard.html:2972` — botão de download executa `window.aiArqDownloadProtected(\`${API_BASE}/api/download/${escProj(p.job_id)}\`, ...)` — `escProj` escapa pra HTML mas o resultado vai pra dentro de uma string JS aspeada. Se `escProj` deixar passar uma `'` mal escapada, quebra o JS. Verifiquei `escProj` (linha 3054): tem o escape padrão de `&<>"'`. OK.

---

## ⚪ Baixos (P2)

### 13. Vários `target="_blank"` sem `rel="noopener noreferrer"`
Cerca de 18+ ocorrências. Navegadores modernos (Chrome 88+, Firefox 79+, Safari 12.1+) já aplicam `noopener` por padrão, mas explicitar é boa prática.

### 14. `visualizar-prancha.html` não checa sessão Supabase
Linha 50-68: trusta `?job_id=...&ref=...` e chama backend direto. Se backend protege bem, OK; mas a falta de check client-side significa que o usuário sem sessão vê uma página em branco com erro do backend, em vez de redirect pra login. Cosmético + leve perda de UX.

### 15. CSS Tailwind via CDN em produção
Todos os HTMLs usam `<script src="https://cdn.tailwindcss.com">`. Documentado no CLAUDE.md como conhecido. Risco: indisponibilidade da CDN trava o layout. Risco de supply-chain é baixíssimo (Tailwind é mantida pela Tailwind Labs, não vejo histórico de comprometimento).

### 16. `cronograma.html:352` constrói `login.html?redirect=cronograma.html?job=${jobId}` mas `login.html` não lê `?redirect`. Código morto, sem efeito prático — vale limpar.

### 17. Dashboard não enforça `maxlength` em `project_name`, `client_name`, `obs`. Backend deve validar (não auditei). Risco: payload gigante consumindo storage.

### 18. Texto de fonte da imagem OG (`og:image`) é `/og-image.png` — fina; nada sensível vaza.

### 19. Política não menciona `idade mínima` no formulário em si — só no documento. Bom redundar no checkbox do cadastro (ver P1 #5).

---

## ⚖️ Conformidade LGPD — checklist

| Item LGPD | Status | Onde / observação |
|---|---|---|
| **Art. 5 — Papéis** (controlador / operador) | ✓ | `privacidade.html` seção 1-A, `termos.html` seção 2-B citam art. 5, VI e VII com clareza. Usuário=controlador do cliente final; AI.arq=operador. |
| **Art. 6 — Princípios** (finalidade, necessidade, transparência) | ✓ | Privacidade lista 8 finalidades específicas (seção 2). CPF é coletado apenas no checkout (minimização). |
| **Art. 7 — Bases legais** | ✓ | Privacidade seção 2 fim: bloco visual com 4 bases — execução de contrato (V), consentimento (I), legítimo interesse (IX), obrigação legal (II). |
| **Art. 8 — Consentimento** (livre, informado, inequívoco, específico) | ⚠ | Checkbox amarra Termos + Privacidade num só (P0 #3). Marketing está corretamente separado. Chat-widget não tem checkbox explícito de comercial (P1 #8). |
| **Art. 9 — Acesso facilitado** | ✓ | Política linkada no rodapé de todas as páginas; cadastro mostra link inline. |
| **Art. 11 — Dados sensíveis** | ✓ | AI.arq não coleta dados sensíveis (raça, saúde, biometria). CPF é dado pessoal "regular", não sensível. |
| **Art. 12 — Anonimização** | ✓ | Privacidade seção 7 + 1-A explicam: valores absolutos R$ nunca vazam; heurísticas usam métricas adimensionais; nome de cliente/fornecedor nunca cruza projetos. |
| **Art. 14 — Tratamento de menores** | ⚠ | Política diz 18+, mas cadastro não valida nem pergunta (P1 #5). |
| **Art. 18 — Direitos do titular** | ✓ | Política seção 6 lista os 6 direitos com prazo de 15 dias úteis. Canal: `contato@ai.arq.br`. |
| **Art. 33 — Transferência internacional** | ✓ | Política seção 7-A: Anthropic, Supabase, Render, Stripe (todos EUA), com base legal art. 33 V e VIII. |
| **Art. 37 — Registro das operações de tratamento** | ⚠ | Não vi documento interno (RIPD/RAT). Pode existir mas não está público; recomendo manter um doc interno simples. |
| **Art. 41 — Encarregado (DPO)** | ⚠ | Política diz "DPO" mas não nomeia. Pra empresa pequena pode ser o próprio Pedro, mas o nome e canal direto precisam aparecer (Decreto 11.137/2022). |
| **Art. 46 — Segurança técnica/admin** | ✓/⚠ | HTTPS ✓, hash de senha ✓, RLS Supabase (depende de configuração — P0 #2), headers HTTP zero (P0 #1). |
| **Art. 48 — Comunicação de incidente** | ✗ | Não existe procedimento documentado de resposta a vazamento. Pra 8 usuários é baixo risco prático, mas formalmente faltante. |
| **Cookies — banner de consentimento** | ✓* | Política declara apenas cookies essenciais (sessão Supabase). Tecnicamente dispensa banner. Não há tracking pixel (Google Analytics, Meta Pixel, Hotjar — busquei, zero ocorrências). *Se algum dia entrar GA/Meta, banner vira obrigatório imediatamente. |

---

## 🛠️ Top 10 fixes prioritários (Claude executa)

| # | Fix | Arquivo | Esforço |
|---|---|---|---|
| 1 | Adicionar `<meta>` CSP + nosniff + referrer em todos os HTMLs | 14 HTMLs raiz | 30min |
| 2 | Separar checkbox de Termos e Privacidade em `cadastro.html` | `cadastro.html:170-181` | 10min |
| 3 | Adicionar checkbox "declaro ser maior de 18 anos" no cadastro | `cadastro.html:170-181` | 5min |
| 4 | Escapar `projName` antes de concatenar em `contextDetails` | `projeto.html:792-794` | 5min |
| 5 | Aumentar senha mínima pra 8 caracteres + mensagem | `login.html:211` | 5min |
| 6 | Adicionar checkbox de aceite comercial no chat-widget lead form | `chat-widget.js:256-289` | 15min |
| 7 | Limpar código morto do `?redirect` em `cronograma.html` | `cronograma.html:352` | 2min |
| 8 | Adicionar `rel="noopener noreferrer"` em todos `target="_blank"` externos | grep -l + sed | 20min |
| 9 | `aiarq_cadastro_draft` no localStorage — adicionar aviso "PC compartilhado? Limpe os dados" + auto-expire em 24h | `cadastro.html:399-413` | 20min |
| 10 | Auditar RLS do Supabase via MCP — gerar `auditoria_rls_2026-06-02.md` com SELECT/UPDATE/DELETE por tabela do admin | Supabase MCP | 1h |

Posso aplicar 1-9 num único commit "seguranca: hardening LGPD + headers + senha mínima" se Pedro autorizar. O #10 requer rodar SQL no Supabase pra confirmar policies; é separado.

---

## ❓ Decisão pra Pedro

1. **Razão social / CNPJ / endereço** — Termos exige identificar o fornecedor (Marco Civil + CDC). Quer expor Fami Capital como controladora oficial até abrir PJ AI.arq, ou prefere segurar a abertura formal e arriscar com "AI.arq" sem CNPJ explícito? (Sugestão prática: usar Fami Capital, CNPJ Y, endereço Z. Você já tem.)

2. **DPO nomeado** — LGPD art. 41 + Decreto 11.137/2022 exigem nome + canal direto. Você quer aparecer como DPO oficial (nome + e-mail próprio `pedro@ai.arq.br` quando Zoho ativar), ou contratar um DPO terceirizado? Pra ~8 usuários, ser DPO próprio é viável e mais barato.

3. **Banner de cookies** — hoje você não tem (Política diz "apenas cookies essenciais", tecnicamente OK). Mas no minuto que entrar Google Analytics / Meta Pixel pra rastrear conversão de IG, banner vira obrigatório. Quer já preparar infra de banner (consent-mode v2) preventivamente, ou esperar?

4. **Procedimento de incidente (art. 48)** — não tem documento interno. Pra 8 usuários é baixo risco; mas se um deles for governo/CAU, postura proativa pesa. Quer eu escrever um `politicas/resposta_incidente.md` mínimo (10 passos, lista de contatos, prazo de 72h pra ANPD)?

5. **RLS audit do Supabase** — é a maior vulnerabilidade exposta. Quer que eu rode o audit usando o MCP Supabase agora (read-only, lista policies) e gere o relatório?

---

**Auditor:** security-reviewer (PT-BR, foco SaaS BR)
**Próximo passo recomendado:** aprovar o pacote de fixes 1-9 (~2h de trabalho, commit único) e separadamente decidir sobre #10 (RLS).
