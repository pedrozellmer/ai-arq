# Auditoria de regressão frontend — 2026-06-09

Escopo: ~10 commits desde 02/06 (e9363fb SEO+a11y, 8ac2392 IDOR+cookies+utils,
48ed35a/7a260cc/98d268b RLS, a8c989b aviso PDF). Foco no risco de quebra do
`aiarq-utils.js` (extração de helpers), `cookie-consent.js` (banner novo) e do
aviso de PDF vetorial no dashboard.

---

## Resumo

Auditei ordem de scripts, nomes de variáveis (`sb`/`sbClient`), funções órfãs,
`createClient` duplicado, z-index/foco/ESC do cookie-consent, e a robustez do
pdf.js no dashboard. A extração pra `aiarq-utils.js` está **sólida**: ordem de
carregamento correta em todas as páginas, ambos os nomes (`sb` e `sbClient`)
expostos, zero `createClient` duplicado, zero função órfã, zero URL hardcoded
remanescente. Os dois arquivos novos estão no ar (HTTP 200) e o deploy bate byte
a byte com o repo. O único ponto real é cosmético: o banner de cookies (z-index
9999) cobre o botão flutuante do chat (z-index 9998) nas páginas públicas até o
usuário escolher uma opção.

**Veredicto: Tudo OK — nenhuma regressão funcional. 1 colisão visual leve + 2 riscos a confirmar no browser.**

---

## 🔴 Regressões CONFIRMADAS

Nenhuma regressão funcional (que quebre fluxo). Há **uma colisão visual leve**:

### 1. Banner de cookies cobre o botão flutuante do chat (cosmético)
- **Onde:** as 5 páginas públicas que carregam os dois ao mesmo tempo —
  `index.html`, `precos.html`, `faq.html`, `termos.html`, `privacidade.html`.
  (`login.html` e `cadastro.html` carregam cookie-consent mas o chat-widget
  também — mesmo efeito.)
- **O que acontece:** `cookie-consent.js:80` usa `z-index:9999`, `position:fixed`,
  `bottom:0`, faixa de largura total com ~80–110px de altura. O launcher do chat
  (`chat-widget.js:34-45`) é `fixed; bottom:24px; right:24px; 60px; z-index:9998`.
  Como o banner tem z-index maior e ocupa a faixa de 0–~110px do rodapé, ele
  **fica por cima do botão do chat** (que vive em 24–84px). O botão só reaparece
  depois que o usuário aceita/recusa cookies (a maioria faz na hora).
- **Gravidade:** baixa. Não quebra nada — é uma sobreposição temporária. O chat
  volta a aparecer assim que o banner some.
- **Fix sugerido:** dar ao banner um z-index maior que o chat (ele já tem) **mas**
  empurrar o botão do chat pra cima enquanto o banner existe, OU deixar o banner
  como faixa que não chega na lateral direita. Opção mais simples: no
  `cookie-consent.js`, ao abrir, adicionar `document.body.classList.add('aiarq-cc-open')`
  e no `chat-widget.js` subir o `bottom` do botão quando essa classe existe
  (ex.: `body.aiarq-cc-open #aiarq-chat-btn { bottom: 130px; }`). Alternativa
  ainda mais barata: reduzir o banner pra não cobrir os ~80px da direita
  (`right: 96px` no desktop) — mas quebra no mobile. Recomendo a classe no body.

---

## 🟡 Riscos não confirmados (testar no browser)

### A. ESC do cookie-consent intercepta ESC de outros componentes
- **Arquivo:** `cookie-consent.js:275` (listener em **capture phase**) +
  `cookie-consent.js:291-298` (`onKeydown` faz `stopPropagation()` + `preventDefault()`).
- **Risco:** enquanto o banner está aberto, qualquer ESC na página é capturado
  ANTES de chegar a outros handlers e fecha o banner como "Só essenciais". Em
  `login.html`/`cadastro.html`, se o usuário apertar ESC esperando limpar um
  campo ou fechar um modal de contato, o banner some no lugar. Como o banner é a
  primeira coisa que aparece e some no primeiro ESC, na prática o conflito é
  efêmero — mas vale confirmar que o modal de contato (`contact-modal.js`) e o
  chat não dependem de ESC enquanto o banner ainda está visível.
- **Como testar:** abrir `precos.html` em aba anônima (sem consentimento salvo),
  abrir o modal de contato, apertar ESC → confirmar que fecha o que o usuário
  espera, não o banner por baixo.

### B. Foco move pro botão "Aceitar todos" ao abrir o banner
- **Arquivo:** `cookie-consent.js:274` (`focusFirstButton('aiarq-cc-accept-all')`
  com timeout de 50ms).
- **Risco:** em páginas onde o usuário começa a digitar imediatamente
  (`login.html`, `cadastro.html`), o foco pode pular pro botão do banner 50ms
  após o load, tirando o cursor do primeiro campo. Não é trap (aria-modal=false,
  não há loop de foco — isso está correto), é só um "roubo" único de foco.
- **Como testar:** abrir `login.html` em aba anônima e ver se o foco inicial fica
  no campo de email ou pula pro banner. Se incomodar, trocar o foco automático
  por um foco só quando o usuário tab-ar pra dentro do banner.

### C. Render free tier dormindo no primeiro `authFetch`/`downloadProtected`
- Não é regressão desta leva, mas como o `aiarq-utils.js` centralizou os fetches,
  vale lembrar: a primeira chamada após 15min acorda o Render (30–60s). O
  `downloadProtected` tem try/catch e mostra toast de erro de rede — confirmar
  que o usuário entende a demora (não é bug do refactor).

---

## 🟢 Verificado OK

1. **Ordem de scripts — correta em TODAS as páginas.** O padrão é sempre
   `supabase-js` → `aiarq-utils.js` → `<script>` inline, os três **sem `defer`**
   (execução síncrona em ordem de documento). Verificado em:
   `dashboard.html:1009-1011`, `login.html:128-132`, `cadastro.html:18-19/218`,
   `index.html:622-624`, `projeto.html:536-538`, `revisao.html:220-222`,
   `cronograma.html:268-270`, `admin.html:19-20/844`, `precos.html:483-485`,
   `faq.html:98-99/960`, `termos.html:28-29/633`, `privacidade.html:28-29/766`,
   `visualizar-prancha.html:13-14/46`.
   Observação: o comentário interno do `aiarq-utils.js:23-28` recomenda `defer`,
   mas na prática os HTMLs carregam SEM defer — o que também é seguro (síncrono
   preserva ordem). Sem regressão.

2. **`sb` vs `sbClient` (armadilha #6) — mitigada.** `aiarq-utils.js:57-58`
   expõe `window.sbClient` E `window.sb` apontando pro MESMO cliente. Cada página
   usa o nome que declarou: dashboard/login/cadastro/index/termos/privacidade/
   precos/faq/cronograma/visualizar-prancha usam `const sbClient = window.sbClient`;
   projeto e revisao usam `const sb = window.sb`. Nenhuma página usa um nome que
   não existe. Confirmado que dashboard usa só `sbClient.*` e projeto/revisao usam
   só `sb.*` (sem cruzar). `admin.html` usa `sbClient` como global (sem reimportar).

3. **`const sb` em `revisao.html:303` NÃO é conflito.** É uma variável local
   string dentro de um callback `.sort((a,b)=>{...})` — escopo de função
   separado do `const sb = window.sb` do topo (`revisao.html:226`). Shadowing
   inofensivo, sem SyntaxError. Nome confuso, mas funcional.

4. **`createClient` duplicado — 0 ocorrências.** `grep supabase.createClient` em
   `*.html` = nenhum match. O único `createClient` vive em `aiarq-utils.js:53`.
   Check passou.

5. **Funções órfãs — nenhuma.** Todas as páginas que chamam
   `downloadProtected`/`authFetch`/`openPdfProtected`/`escapeHtml`/`API_BASE`
   (dashboard, cronograma, revisao, projeto, admin, visualizar-prancha) carregam
   `aiarq-utils.js`. Os 25 posts de blog + `index` do blog NÃO usam nenhum helper
   (só carregam cookie-consent.js, que é self-contained). Sem chamada pendurada.

6. **Sem redefinição local divergente dos helpers.** Nenhuma página declara
   `function escapeHtml`/`authFetch`/`downloadProtected` própria — todas usam os
   globals do aiarq-utils. Só `notify`/`API_BASE`/`sb`/`sbClient` são reimportados
   como `const` local (apontando pro `window.*`), o que é seguro.

7. **API_BASE — centralizado, sem hardcode divergente.** `grep` por
   `ai-arq.onrender.com` e `kqjabzwgbfuivzlcfvvu.supabase.co` em `*.html` = 0
   ocorrências. Tudo vem de `aiarq-utils.js:36-42`. Sem drift.

8. **pdf.js no dashboard — totalmente defensivo.** `dashboard.html:1822-1838`:
   o arquivo é adicionado a `selectedFiles` PRIMEIRO, depois
   `checkPdfTextAndWarn(f)` é disparado como promise solta com `.catch()`
   (`dashboard.html:1832`). pdf.js carrega sob demanda
   (`loadPdfJs`, `dashboard.html:1853-1870`) e `checkPdfTextAndWarn`
   (`:1872-1902`) envolve tudo em try/catch — se a CDN falhar, cai no
   `console.warn` e o `addFiles` segue normal com `renderFiles()`. Upload NÃO
   quebra se pdf.js estiver offline. Check #6 do briefing passou.

9. **cookie-consent — acessibilidade OK (exceto colisão do item 🔴).**
   `aria-modal=false` (não bloqueia interação — `cookie-consent.js:72`),
   **não prende foco** (sem loop de focusin — correto pra banner sticky),
   ESC fecha como "Só essenciais" (`:291-298`), restaura foco anterior ao
   fechar (`:285-287`), daltônico-safe (cor + ícone + texto em cada estado:
   ICON_LOCK + "Sempre ativo", ICON_CHECK etc.), respeita
   `prefers-reduced-motion` (`:261`). Persiste escolha em localStorage e
   **não reabre** depois de escolhido (`:318-321`).

10. **cookie-consent NÃO aparece em página logada.** Carrega só em 7 páginas
    públicas (index, precos, faq, termos, privacidade, login, cadastro). NÃO
    está em dashboard, projeto, revisao, cronograma, admin nem
    visualizar-prancha. Requisito "não aparece logado" atendido por inclusão
    seletiva.

11. **Arquivos novos no ar e deploy atual (não stale).**
    `aiarq-utils.js` HTTP 200, 8576 bytes, `application/javascript`;
    `cookie-consent.js` HTTP 200, 14855 bytes. Ambos batem byte a byte com o
    repo local, e os marcadores (`window.openPdfProtected`, `aiarqCookieConsent`)
    estão presentes na versão deployada. `toast.js` também 200.

12. **Remoção do meta no-cache — sem impacto funcional.** Confirmado que sobrou
    só em `admin.html:9-10` (intencional — admin nunca deve cachear). As outras
    14 páginas tiveram a meta removida; é puramente cache, não quebra
    comportamento.

---

## 🛠️ Fixes prioritários

1. **(P2 — cosmético) Empurrar botão do chat pra cima enquanto o banner de
   cookies está aberto.** No `cookie-consent.js`, ao abrir/fechar, alternar
   `document.body.classList.toggle('aiarq-cc-open', true/false)`; no
   `chat-widget.js` adicionar CSS `body.aiarq-cc-open #aiarq-chat-btn { bottom: 130px; }`.
   Resolve a única sobreposição confirmada nas 5 páginas públicas.

2. **(P3 — verificar) Testar ESC e foco inicial em `login.html`/`cadastro.html`
   em aba anônima.** Se o ESC do banner ou o roubo de foco incomodar, trocar o
   `stopPropagation()` no `onKeydown` por uma versão que só age se o foco estiver
   dentro do banner, e adiar o `focusFirstButton` pra quando o usuário tab-ar
   pra dentro.

3. **(P4 — limpeza opcional) Renomear o `const sb` local em `revisao.html:303`**
   pra `numB`/`itemNumB` — elimina o shadowing confuso do cliente Supabase
   homônimo. Zero impacto funcional, só clareza.

Nenhum fix é bloqueante. O site está funcional. NÃO commitei nada (auditoria).
