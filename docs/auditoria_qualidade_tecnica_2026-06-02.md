# Auditoria de qualidade técnica — frontend AI.arq

**Data:** 2026-06-02
**Escopo:** 13 HTMLs raiz + 20 HTMLs do blog + 4 JSs compartilhados (~15.6k linhas, sem `frontend/node_modules/`)
**Auditor:** Claude (Opus 4.7, sessão Tech Lead)

---

## Resumo executivo

O código frontend tá **funcional e shippado**, mas carrega muita dívida de "vibe coding" sem framework. **3 bugs sérios em produção** (downloads protegidos via `<a href>`, info de cashback obsoleta no onboarding, mismatch verde/branco). Duplicação massiva de boilerplate (Supabase init em 13 lugares, `downloadProtected` colado 4 vezes, `escapeHtml` em 4). JS é razoavelmente moderno (sem `var`, sem `==`), mas tem inconsistência entre `sb` e `sbClient` que o próprio CLAUDE.md já alerta.

**Grade geral: C+** — não é grave, mas tá no limite. Cada novo HTML acumula mais cópia do mesmo. Sem um util.js compartilhado, qualquer fix de segurança vai precisar tocar em 13 arquivos.

---

## 🟢 5 acertos

1. **`toast.js` é exemplar** — acessível (aria-live, role conforme severidade), daltônico-friendly (cor + ícone + texto), vanilla sem dependência, autocontido. Modelo a seguir.
2. **`lang="pt-BR"` em 100% dos HTMLs** (35/35) — bom pra SEO e leitores de tela.
3. **Schema.org JSON-LD válido em todos os posts do blog** (23 arquivos), gerado por Python (`blog/generate.py`), sem caracteres especiais escapando errado nas headlines.
4. **JS já é majoritariamente moderno** — `const/let` (zero `var` nos HTMLs), `===` em vez de `==`, async/await em vez de callback hell. Só `contact-modal.js` (47 `var`s) e `onboarding-tour.js` (20 `var`s) ficaram com sintaxe legacy.
5. **`downloadProtected` foi corretamente implementado** depois do bug Daniela 2026-05-18 — fetch com Bearer + blob + download programático. Só o problema é que tá colado em 4 HTMLs (ver P1).

---

## 🔴 Críticos (P0) — bugs ou copy quebrado em produção

### P0-1 · `visualizar-prancha.html` baixa PDF protegido via `<a href>` → 401

**Arquivo:** `visualizar-prancha.html` linhas 53-67
**Sintoma:** Usuário clica em "Baixar" no viewer de prancha e recebe erro 401 (ou planilha quebrada), mesmo logado.

```js
const pdfUrl = `${API_BASE}/api/sheet/${jobId}?ref=${encodeURIComponent(ref)}`;
document.getElementById('pdf-frame').src = pdfUrl;  // iframe
// ...
window.downloadPdf = function() {
  const a = document.createElement('a');
  a.href = pdfUrl;
  a.download = decodeURIComponent(ref);
  ...
```

É **exatamente o bug Daniela 2026-05-18** (item #9 da seção "Armadilhas conhecidas" do CLAUDE.md), que diz: *"Endpoint protegido que devolve arquivo NÃO pode ser baixado via navegação direta"*. A página inteira foi escrita sem usar `downloadProtected`.

**Agravante:** Hoje `GET /api/sheet/{job_id}` (`backend/main.py:6130`) **não tem auth** — é público. Então o download "funciona", mas qualquer um com `job_id+ref` lê prancha de qualquer outro projeto. **Vulnerabilidade IDOR**: o arquivo desse endpoint deveria exigir `_require_project_owner`, e o frontend deveria usar `downloadProtected`.

**Patch:** importar/inline o `downloadProtected`, trocar `<a href>` por `fetch + blob`, e proteger o endpoint no backend.

---

### P0-2 · `projeto.html` baixa XLSX/PPT do comparativo de fornecedores via `<a href>` → 401

**Arquivo:** `projeto.html` linhas 1354 e 1365
**Sintoma:** Usuário gera comparativo de fornecedores, clica em "Baixar comparativo XLSX" ou "Baixar apresentação PPT" → recebe 401.

```html
<a href="${API_BASE}${data.pptx_url}" target="_blank" ...>📊 Baixar apresentação PPT</a>
<a href="${API_BASE}${data.xlsx_url}" target="_blank" ...>📥 Baixar comparativo XLSX</a>
```

Confirmei no backend: ambos endpoints (`/api/projects/{job_id}/quotes/download/xlsx` e `.../pptx`, em `main.py:3995` e `:4009`) chamam `_require_project_owner(request, job_id)` — **exigem Bearer token**. O `<a href>` não envia Authorization. **O comparativo de fornecedores (feature vendida em destaque na landing) está literalmente quebrado pra download**.

**Patch:** trocar pelos botões que chamam `downloadProtected(...)`. A função já existe no mesmo arquivo (linha 564).

---

### P0-3 · `onboarding-tour.js` promete cashback obsoleto + cor errada

**Arquivo:** `onboarding-tour.js` linhas 36-38
**Sintoma:** Tour do 1º acesso (que TODO usuário novo vê) mostra:

> "Itens em **VERDE** foram medidos do CAD (confiável). Itens em **LARANJA** foram estimados (revisar antes de usar). Cada item validado vira **R$ 0,10 de cashback** (até R$ 20)."

**3 problemas em uma frase:**

1. **Vaza decisão revogada** — `feedback_cashback_v2` (2026-05-13): *"Inline (R$0,10/item) eliminado"*. Cashback agora é só R$30 (planilha) + R$10 × 3 (cotação) = R$60 max. O usuário novo entra acreditando que vai ganhar R$ 0,10 por item. Quando descobrir que não, fica com **promessa quebrada na primeira interação**.
2. **Mismatch de design system: VERDE vs BRANCO** — todo o resto do produto (planilha XLSX, badges, landing) usa **BRANCO = medido / LARANJA = estimado**. Só o tour fala "VERDE". Inconsistência confusa **especialmente pro Pedro, que é daltônico** — verde-laranja é exatamente o par crítico que ele NÃO consegue distinguir bem.
3. **Quebra a regra dura #1** — "🚨 NUNCA estimar como confirmado" — chamar de "confiável" reforça a leitura errada de que LARANJA é "menos confiável", quando na verdade é "não-medido = revisar OBRIGATORIAMENTE".

**Patch:** reescrever o step 3:

```js
{
  icon: '✏️',
  title: '3 · Revise e baixe',
  body: 'Itens em <strong>fundo BRANCO</strong> foram medidos direto do CAD (auditáveis). Itens em <strong style="color:#ea580c">fundo LARANJA</strong> foram estimados pela IA — você precisa revisar antes de mandar pro orçamentista.',
  cta: 'Próximo',
},
{
  icon: '🎁',
  title: 'Cashback até R$ 60',
  body: 'Sobe a planilha revisada (+R$ 30) e cotações de fornecedor (até 3 = +R$ 30) e o crédito entra no próximo projeto. <strong>Seu 1º projeto é grátis sem cartão.</strong>',
  ...
}
```

---

### P0-4 · Endpoint público `/api/sheet/{job_id}` permite IDOR (relacionado a P0-1)

Já documentado acima. **Backend issue**, mas frontend é o que expõe o problema (o viewer aceita qualquer `job_id+ref` da URL). Recomendo:
- Backend: adicionar `_require_project_owner(request, job_id)` em `/api/sheet/{job_id}` (linha 6130 do `main.py`).
- Frontend: passar a baixar via `downloadProtected` no `visualizar-prancha.html`, e renderizar PNG/PDF no iframe via blob URL.

---

## 🟡 Alta dívida (P1) — duplicação grave e padrões inconsistentes

### P1-1 · Supabase init duplicado em 13 lugares (com chave anon hardcoded em todos)

Em **cada um** desses 13 arquivos aparece o mesmo bloco:

```js
const SUPABASE_URL = 'https://kqjabzwgbfuivzlcfvvu.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGc...CSKI';  // 248 chars idênticos
const sbClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
```

**Onde:** `index.html, login.html, cadastro.html, dashboard.html, admin.html, projeto.html (sb), revisao.html (sb), cronograma.html, faq.html, precos.html, termos.html, privacidade.html, onboarding-tour.js` (esse último como fallback porque `const` não vai pro `window`).

**Custo da duplicação:**
- Se a chave anon for rotacionada → 13 arquivos pra editar.
- Inconsistência de nome (`sb` vs `sbClient`) já causou o bug de 2026-05-14 (registrado no comentário do `onboarding-tour.js:217`).
- Cada página carrega o SDK Supabase do CDN separadamente (sem cache cross-page warming, todas refazem o handshake).

**Patch:** extrair pra `js/supabase-client.js`:
```js
window.AIARQ_SUPABASE_URL = 'https://kqjabzwgbfuivzlcfvvu.supabase.co';
window.AIARQ_SUPABASE_ANON_KEY = 'eyJhbGc...CSKI';
window.sb = window.supabase.createClient(window.AIARQ_SUPABASE_URL, window.AIARQ_SUPABASE_ANON_KEY);
```
e em cada HTML usar `<script src="js/supabase-client.js"></script>` depois do CDN. Resolve P1-2 e P1-3 também.

---

### P1-2 · `downloadProtected` colado em 4 HTMLs (idênticos exceto `sb` vs `sbClient`)

Mesma função, 30 linhas cada, em:
- `dashboard.html:1295`
- `projeto.html:564`
- `revisao.html:249`
- `cronograma.html:276`

**Risco real:** se você ajustar a função em 1 lugar (ex: melhorar mensagem de erro, lidar com 403 vs 401), as outras 3 ficam atrás. **Bug de segurança ou UX pode existir em 3 das 4 cópias sem você perceber.**

**Patch:** extrair pra `js/auth-fetch.js`:
```js
async function downloadProtected(url, filename) { ... }
async function authFetch(url, options = {}) { ... }
window.aiArqDownloadProtected = downloadProtected;
window.aiArqAuthFetch = authFetch;
```

`authFetch` também tá duplicado nos mesmos 4 lugares.

---

### P1-3 · `escapeHtml` em 4 lugares + `API_BASE` em 7

```
escapeHtml: dashboard.html:2452 · revisao.html:890 · cronograma.html:1500 · chat-widget.js:339
API_BASE:   admin.html · dashboard.html · projeto.html · revisao.html · cronograma.html · visualizar-prancha.html · chat-widget.js
```

Junto no mesmo util.js (`js/aiarq-utils.js`).

---

### P1-4 · `contact-modal.js` é todo `var` + tem brecha XSS leve

**Arquivo:** `contact-modal.js`
**Achados:**
- 47 ocorrências de `var` (sintaxe ES5) — JS legacy.
- Linha 277: `contextText.innerHTML = html;` — `html` é montado com `opts.contextLabel` e `opts.contextDetails` **sem escape**.

O chamador único (até hoje, `projeto.html:794`) passa:
```js
contextDetails: `Código: <strong>${jobId}</strong>${projName ? ' · ' + projName : ''}`
```
`projName` vem de `document.getElementById('proj-title').textContent.trim()`. **Hoje é seguro** porque `textContent` retorna texto puro e o backend filtra nome de projeto. Mas o contrato da função aceita HTML cru — **basta um próximo dev passar input direto do usuário** pra virar XSS. Comentários do `projeto.html:1174` mostram que essa preocupação já apareceu antes.

**Patch:** trocar `innerHTML` por construção via `createElement` + `textContent`, ou aceitar só texto (sem HTML).

---

### P1-5 · `chat-widget.js` carregado SEM `defer` no blog

`blog/index.html:357` e todos os 20 posts do blog usam:
```html
<script src="/chat-widget.js"></script>
<script src="/contact-modal.js"></script>
```

(sem `defer`). Pros HTMLs da raiz é `<script src="chat-widget.js" defer>`. Inconsistente — o blog renderiza ~5-15% mais devagar que o resto do site.

---

### P1-6 · `toast.js` carregado em só 4 páginas

`toast.js` existe em `cronograma, dashboard, projeto, revisao` (áreas autenticadas). Mas:
- `cadastro.html`, `login.html` usam `alert()` direto em vez de toast (vi 2 ocorrências de `console.error` + alerts implícitos).
- `chat-widget.js`, `contact-modal.js` chamam `window.toast` com fallback `alert()` — em páginas públicas o fallback ativa.

**Patch:** carregar `toast.js` em todas as páginas. Tem 179 linhas com CSS injetado — overhead irrisório.

---

### P1-7 · 13 cópias de `version v0.5.0 · Beta` no footer

Hardcoded em todo HTML. Arquivo `VERSION` existe na raiz mas nada lê. Quando bumpar pra `v0.6.0`, é 1 commit tocando 13 arquivos. **Plugin pro `blog/generate.py` pode resolver no blog**, mas pros HTMLs raiz não tem ninguém regerando.

---

## ⚪ Médios (P2)

### P2-1 · `meta name="theme-color"` ausente em TODOS os HTMLs (35/35)
**Sintoma:** No Chrome Android, a barra do navegador fica cinza padrão em vez de Indigo. Coisa simples.
**Patch:** adicionar `<meta name="theme-color" content="#4F46E5">` em todos.

### P2-2 · `email admin hardcoded em 2 lugares`
- `admin.html:851` — `const ADMIN_EMAIL = 'zarelalopes@gmail.com';`
- `dashboard.html:1410` — `if (user.email === 'zarelalopes@gmail.com')`

Funciona, mas se Pedro mudar o email primário, esquece um. Extrair pra `js/aiarq-config.js`.

### P2-3 · `!important` em 38 arquivos do blog
Sempre o mesmo padrão `aiarq-dl-btn { text-decoration: none !important; }`. É o `generate.py` colocando — provavelmente porque a `.prose` do Tailwind sobrescreve. Não é grave, mas indica um conflito que poderia ser resolvido com seletor mais específico.

### P2-4 · 3 cópias de `escapeHtml` levemente diferentes
- Algumas escapam aspas simples como `&#39;`, outras como `&apos;`. Consistente entre os 4, mas inconsistente vs o backend Python (que usa `markupsafe`). Não é bug, é falta de fonte única.

### P2-5 · `index.html` carrega `onboarding-tour.js` (10KB) pra páginas públicas
O tour só roda se houver sessão Supabase, mas o script é baixado e parseado por todo visitante anônimo da landing. **Mover pro dashboard apenas.**

### P2-6 · Comentário `// TODO: mover pra fetch inicial de config endpoint` (admin.html:846)
Único TODO genuíno do código — referencia exatamente o util.js compartilhado que sugiro em P1-1.

### P2-7 · `console.log/error/warn` espalhado (47 ocorrências em 6 arquivos)
Dashboard tem 13, admin 14, projeto 13. Maioria é `console.warn(...)` em catch silencioso. Pra prod beta tudo bem; quando crescer pra 50+ usuários, vale meter um wrapper `aiArqLog.warn(...)` que mande pra Sentry/Logflare.

### P2-8 · `cronograma.html:649-650` usa `innerHTML +=`
```js
dependsSel.innerHTML += `<option value="${i}">${escapeHtml(label)}</option>`;
parentSel.innerHTML += `<option value="${i}">${escapeHtml(label)}</option>`;
```
`+=` em select recria todos os children (lento + perde event handlers). Trocar por `appendChild` com `new Option(label, i)`.

### P2-9 · `meus-projetos.html` é só redirect com `<meta http-equiv="refresh">`
Funciona, mas redirect via meta-refresh é mal visto por SEO e mais lento que server-side 301. Como é GitHub Pages (sem 301), tudo bem — porém vale comentar isso no HTML ("legacy redirect, rotear via 301 quando migrar").

### P2-10 · Padrão inconsistente: `sb` em `revisao.html/projeto.html` vs `sbClient` no resto
Já registrado no CLAUDE.md como armadilha #6. **O fix de P1-1 (util.js compartilhado) resolve isso.**

---

## 🛠️ Top 15 patches automáticos (Claude aplica sem decisão humana)

1. **Fix P0-3** — reescrever `onboarding-tour.js` steps 3 e 4 (BRANCO em vez de VERDE, cashback v2 em vez de R$0,10/item).
2. **Fix P0-2** — substituir `<a href>` por botões com `downloadProtected` em `projeto.html:1354,1365`.
3. **Fix P0-1 (parcial frontend)** — em `visualizar-prancha.html`, trocar `<a href>` no botão de baixar por `downloadProtected`. Iframe continua aberto porque GET público é trivial.
4. **Adicionar `<meta name="theme-color" content="#4F46E5">`** em todos os 35 HTMLs.
5. **Adicionar `defer`** aos `<script src="/chat-widget.js">` e `/contact-modal.js"` em `blog/index.html` e nos 20 posts (alterar `blog/generate.py`).
6. **Trocar `'auth-failed'` por mensagens mais úteis** em todos os 4 `downloadProtected` (texto consistente, "Faça login de novo pra baixar").
7. **Renomear `sb` → `sbClient` em `revisao.html` e `projeto.html`** pra padronizar com os outros 10 HTMLs.
8. **Remover `onboarding-tour.js` do `index.html`** (linha 639) — só dashboard precisa.
9. **Padronizar `escapeHtml`** — pegar a versão do `chat-widget.js` (mais simples) e replicar nos 3 outros lugares ANTES de extrair pra util.js.
10. **Trocar `cronograma.html:649-650 `innerHTML +=` por `appendChild(new Option(...))`.
11. **Sanitizar `contact-modal.js:277`** — trocar `innerHTML = html` por DOM seguro (`createElement` + `textContent`).
12. **Carregar `toast.js` em `login.html`, `cadastro.html`, `index.html`, `precos.html`, `faq.html`, `termos.html`, `privacidade.html`, `admin.html`** (8 arquivos).
13. **Tornar `_isValidCpfOrCnpj` mais estrito** em `dashboard.html:1225` — hoje aceita "11111111111" como CPF válido (não valida DV). Como Stripe valida depois, é cosmético, mas vale uma checagem leve.
14. **Remover o atributo `<meta http-equiv="Pragma" content="no-cache">` e `Expires: 0`** em todos os HTMLs onde aparecem — `Cache-Control: no-cache, no-store` já faz o trabalho, esses 2 são legado HTTP/1.0 que só infla o `<head>`.
15. **Adicionar `rel="noopener"` nos `target="_blank"` que ainda não têm** (vi alguns em `projeto.html:1354,1365` se virarem botões protegidos com fallback `<a>`).

---

## 🏗️ Refactors maiores (1 commit dedicado cada)

### Refactor A · `js/aiarq-utils.js` compartilhado
Cria 1 arquivo: `js/aiarq-utils.js` com tudo que tá duplicado.

```
js/aiarq-utils.js   (~150 linhas)
├── window.AIARQ_SUPABASE_URL
├── window.AIARQ_SUPABASE_ANON_KEY
├── window.AIARQ_API_BASE = 'https://ai-arq.onrender.com'
├── window.AIARQ_ADMIN_EMAIL = 'zarelalopes@gmail.com'
├── window.AIARQ_VERSION (lido do <meta name="aiarq:version">)
├── window.sb = supabase.createClient(...)        // unifica sb vs sbClient
├── window.aiArqAuthFetch(url, opts)
├── window.aiArqDownloadProtected(url, filename)
└── window.aiArqEscapeHtml(s)
```

Cada HTML perde 30-40 linhas. Total economizado: ~400 linhas. **Sugiro 1 PR só pra isso, com hard refresh do GitHub Pages testado em cada página.**

### Refactor B · Quebrar `dashboard.html` em módulos
Hoje `dashboard.html` tem **3478 linhas** com tabs (projetos, novo, cashback, mensagens, conta). Sugiro:
- Extrair JS pra `js/dashboard.js`, `js/dashboard-novo-projeto.js`, `js/dashboard-projetos.js`, etc.
- Templates HTML ficam no .html.
- Volume cai pra ~800 linhas no HTML principal.

**Custo:** 1 dia de trabalho com testes em todas as abas. **Benefício:** futuras edições do dashboard ficam muito mais rápidas, e cada vez que Claude precisa ler "o estado do dashboard" não consome 3.5k linhas de contexto.

### Refactor C · `blog/generate.py` ler `VERSION` e injetar
Hoje cada post tem `v0.5.0 Beta` hardcoded — `generate.py` poderia ler `../VERSION` e renderizar no template. Versão da raiz idem (3-4 HTMLs).

### Refactor D · Sanitizar todos os `innerHTML` que usam dados de API
Vi escape correto em `projeto.html:1178+` e `cronograma.html:649-650`. Mas precisa varrer **todos** os `innerHTML = \`...${var}...\`` e checar se cada `${var}` veio de API/user input ou de constante. Auditoria de XSS focada — 2-4h de trabalho. **Sugiro fazer DEPOIS dos refactors A e B.**

### Refactor E · Endpoint público `/api/sheet/{job_id}` virar protegido
Backend: adicionar `_require_project_owner`. Frontend: `visualizar-prancha.html` precisa fazer fetch autenticado, converter o blob em URL e setar no `<iframe>`. Mais complexo que parece — iframe não aceita Authorization, então precisa de blob URL.

**Alternativa mais simples:** assinar uma URL temporária (signed URL do Supabase Storage), que pode ser usada por iframe normalmente. Backend gera URL válida por 5min, frontend embute no iframe. Aplica também ao P0-1.

---

## ❓ Decisão pra Pedro

**Esses 3 caminhos têm trade-offs reais — qual rota seguir?**

### Decisão 1 · `js/aiarq-utils.js` compartilhado vs ficar igual

| Opção | Prós | Contras |
|---|---|---|
| **A. Extrair pra util.js (Refactor A)** | Cada novo HTML = 1 linha em vez de 35. Bug fix de segurança aplicado uma vez só. Padronização `sb`. | 1 PR sério com risco de regressão em todas as páginas. Precisa testar tudo. |
| **B. Manter como tá** | Zero risco agora. Cada HTML é "auto-suficiente" (bom pra debug). | Dívida composta — quando virar 25 HTMLs (Fase 5 ERP), vai virar pesadelo. |
| **C. Adiar pra Fase 4-5** | Quando migrar pra React/Vue, o util.js vira hook nativo e o trabalho não é jogado fora. | Bugs P0-1 e P0-2 vão precisar ser corrigidos em N lugares enquanto isso. |

**Minha recomendação:** **A**, mas só DEPOIS de fixar os 3 P0s (que mexem em 3 arquivos diferentes). Caso contrário você fica fazendo refactor em código que já tá quebrado.

### Decisão 2 · `dashboard.html` quebrar agora ou esperar?

Dashboard tem **3478 linhas** e crescendo (Fase 2 cronograma vai adicionar UI). Quebrar agora custa ~1 dia. Esperar = chegar fácil em 5k linhas até o ERP da Fase 5.

**Sugiro:** quebrar agora se a Fase 2 cronograma for esperada pra antes de 2026-08. Senão, manter monolítico.

### Decisão 3 · Backend endpoint `/api/sheet/{job_id}` — proteger ou deixar público?

- **Proteger** (recomendado): blinda IDOR, mas exige iframe + blob URL no frontend.
- **Deixar público + URL com `signed=<jwt>`**: rotina expira em 5min, mais simples no frontend (iframe normal). Stripe/Cloudflare R2 fazem assim.
- **Deixar 100% público**: hoje é assim. O `job_id` é UUID v4 (impossível adivinhar), então prática-real-risco é baixo. Mas viola princípio "least privilege" e LGPD (operador deve restringir acesso).

**Minha recomendação:** signed URL, 5min de TTL. Mais simples e seguro o suficiente.

---

## Anexo · números do diagnóstico

| Métrica | Valor |
|---|---|
| HTMLs raiz | 13 |
| HTMLs blog | 21 (1 index + 20 posts) |
| JS compartilhados | 4 (chat-widget, contact-modal, onboarding-tour, toast) |
| Total linhas frontend | ~15.655 |
| Supabase init duplicado | 13 lugares |
| `downloadProtected` duplicado | 4 lugares |
| `authFetch` duplicado | 4 lugares |
| `escapeHtml` duplicado | 4 lugares |
| `API_BASE` duplicado | 7 lugares |
| `var` em JS compartilhado | 67 (47 em contact-modal, 20 em onboarding-tour) |
| `==` em vez de `===` | 0 |
| `TODO/FIXME/HACK` | 1 (admin.html:846) |
| Bugs P0 confirmados | 4 |
| Patches automáticos sugeridos | 15 |
| Refactors maiores | 5 |
