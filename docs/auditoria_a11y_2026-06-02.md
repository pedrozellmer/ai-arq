# Auditoria de Acessibilidade AI.arq — 2026-06-02

Auditoria WCAG 2.2 Level AA sobre `index.html`, `cadastro.html`, `login.html`, `dashboard.html`, `projeto.html`, `revisao.html`, `cronograma.html`, `faq.html`, `termos.html`, `privacidade.html`, `contact-modal.js`, `toast.js`, `chat-widget.js`, `onboarding-tour.js`.

---

## Resumo executivo

Conformidade WCAG 2.2 AA aproximada: **~70%**. A Onda B (selos cor+ícone+texto, role=alert, aria-modal, focus trap em `revisao.html`, toast.js acessível, `<label for>` em formulários, `aria-label` em ícones-só) cobriu o essencial em revisão/cadastro/modais. Daltonismo está bem endereçado nos itens de status já tocados. As lacunas restantes são sistêmicas: ausência de skip link em todas as páginas, contrastes finos (`text-gray-300`, `text-amber-600` sobre `bg-amber-50`, gradient-text usado em texto pequeno), o widget `chat-widget.js` e o `onboarding-tour.js` não têm semântica de diálogo, e o Gantt do `cronograma.html` não tem alternativa de teclado para reordenar.

**Risco mais alto:** o cronograma tem fluxo de reordenar fases via botões `<button class="btn-up"/.btn-down">` (bom), mas falta `aria-live` anunciando "fase movida pra posição X" — usuário cego não percebe que algo mudou. O `chat-widget.js` é um diálogo modal que nem `role="dialog"` tem.

---

## 🟢 5 acertos (mantenha)

1. **`revisao.html:127, 169, 187`** — modais `role="dialog"` com `aria-modal="true"` + `aria-labelledby`. Focus trap implementado em `revisao.html:476-509` (`trapFocus`/`openModalA11y`/`closeModalA11y`), Esc fecha (linha 749), foco volta pra origem.
2. **`revisao.html:399-404`** — chips de estado de item levam cor + ícone (`✓ ✎ ✗`) + texto ("aprovado", "editado", "removido"). Regra do daltonismo cumprida com elegância. Mesmo padrão replicado em `dashboard.html:2935-2942` (badges de status do projeto: ✓ Pronto, ✗ Erro, ⏳ Na fila, ⚙ Processando).
3. **`toast.js:99-105`** — Toasts atribuem `role="status"` (sucesso/info) ou `role="alert"` (warn/erro), cada tipo com cor + ícone + borda esquerda + texto. Honra `prefers-reduced-motion` na linha 75. Substitui `alert()` em todo o app.
4. **`login.html:78,83` + `faq.html:171`** — uso correto de `sr-only` em labels de campos onde o placeholder já comunica o propósito, mas screen reader ainda lê o rótulo semântico. `autocomplete="email"`/`"current-password"` em `login.html:79,84` (único arquivo do app que faz isso — bom).
5. **`revisao.html:741-784`** — atalhos de teclado completos pra revisão (J/K/↑/↓/A/D/E/C/V/M/Esc/?) com modal `#modal-help` documentando todos. Ignora `keydown` quando dentro de `input/textarea/select` (linha 744) — não interfere com digitação.

---

## 🟡 Problemas (24 itens, P0 = bloqueador, P1 = corrigir logo, P2 = melhoria)

### 1. Falta skip link em todas as páginas (P1)
**WCAG 2.4.1 Bypass Blocks** · arquivos: `index.html`, `dashboard.html`, `cadastro.html`, `login.html`, `revisao.html`, `cronograma.html`, `projeto.html`, `faq.html`, `termos.html`, `privacidade.html`
Nenhum HTML do app tem `<a href="#main" class="skip-link">Pular pra conteúdo</a>`. Usuário de teclado precisa tabular através de toda a navbar/avatar dropdown em cada página.
**Fix:** adicionar logo após `<body>`:
```html
<a href="#main" class="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-indigo-600 focus:text-white focus:rounded-lg">Pular pra conteúdo principal</a>
```
e marcar `<main id="main">` em todas as páginas.

### 2. Contraste insuficiente — `text-gray-300` em fundo claro (P0)
**WCAG 1.4.3 Contrast (Minimum)** · `index.html:608`, `precos.html:477`, `cadastro.html:215`, `dashboard.html:359, 994`, `faq.html:173`
`text-gray-300` (#D1D5DB) sobre `bg-white`/`bg-gray-50` dá contraste ~1.6:1 — abaixo de 4.5:1 (texto normal) e 3:1 (UI). Aparece em copyright do footer ("v0.5.0 · Beta"), placeholder ("PDF, DWG ou DXF — sem limite de arquivos") e botão "limpar busca" no FAQ.
**Fix:** trocar `text-gray-300` por `text-gray-500` (#6B7280, ~5:1) ou `text-gray-600` em todas as ocorrências.

### 3. `gradient-text` aplicado a métricas pequenas (P1)
**WCAG 1.4.3 Contrast** · `index.html:111, 115, 119, 123` (números "18", "~5min", "XLSX", "SINAPI")
O gradient indigo-cyan tem contraste variável; nas extremidades cyan claro (#06b6d4) sobre fundo `bg-gradient-to-br from-indigo-50/50 to-cyan-50/50` cai abaixo de 4.5:1. Não é texto puramente decorativo (transmite informação numérica).
**Fix:** trocar `gradient-text` por `text-indigo-700` puro em `.text-3xl font-bold` quando o valor for informativo. Manter gradient só em títulos `<h1>/<h2>` grandes (3.1 ainda passa pra "large").

### 4. Botões com texto branco em `bg-amber-500` quase abaixo do limite (P2)
**WCAG 1.4.3** · `index.html:201` (passo 5 — "amber-500" #F59E0B com `text-white` dá ~2.4:1)
A bolinha do passo "5" e a do "PPT com sua marca" usam `bg-amber-500` com SVG branco — contraste ~2.4:1. Ícone passa por 1.4.11 (UI ≥ 3:1)? Não.
**Fix:** trocar pra `bg-amber-600` (#D97706, ~3.1:1) ou `bg-amber-700` (#B45309, ~4.5:1). Mesmo problema em `dashboard.html` várias caixas de cashback.

### 5. Footer "v0.5.0 · Beta" ilegível (P1)
**WCAG 1.4.3** · `index.html:608`, `precos.html:477`
`text-xs text-gray-300` — texto minúsculo (12px) ainda mais cinza-claro. Combo péssimo. Mesmo se a info for "secundária", a regra continua valendo.
**Fix:** `text-xs text-gray-500` ou esconder de assistive tech com `aria-hidden="true"` se realmente for só ornamento.

### 6. Drop zone só funciona por mouse/touch (P0)
**WCAG 2.1.1 Keyboard, 2.5.7 Dragging Movements** · `dashboard.html:353-361` (`#drop-zone`), `dashboard.html:675-682` (`#cashback-drop-zone`)
`<div id="drop-zone" class="drop-zone... cursor-pointer">` não é focusable, não tem `role="button"`, não responde a Enter/Espaço. O `<input type="file" id="file-input" class="hidden">` existe mas não tem `<label for="file-input">` visível conectado ao drop zone.
**Fix:**
```html
<label for="file-input" id="drop-zone" tabindex="0" role="button" aria-label="Clique ou arraste arquivos pra upload">
  ...
</label>
```
Drop por drag-and-drop continua funcionando (já tem fallback de clique), mas teclado passa a navegar via Tab → Enter abre o picker nativo.

### 7. Chat widget é diálogo modal sem semântica (P0)
**WCAG 4.1.2 Name, Role, Value** · `chat-widget.js:237-306`
O `#aiarq-chat-panel` aparece como overlay, captura input, mas:
- não tem `role="dialog"` nem `aria-modal="true"`
- não tem `aria-labelledby` (não diz "AI.arq · Suporte" pra screen reader)
- não trapa foco (Tab escapa pro conteúdo de baixo)
- não devolve foco pro botão `#aiarq-chat-btn` ao fechar
- `id="aiarq-chat-messages"` deveria ser `aria-live="polite"` pra anunciar mensagens novas
**Fix:** adicionar atributos no `panel` (linha 237), implementar focus trap igual ao do `revisao.html`, marcar `aiarq-chat-messages` com `aria-live="polite" aria-atomic="false"`.

### 8. Tour de onboarding sem semântica de diálogo (P1)
**WCAG 4.1.2** · `onboarding-tour.js:129-148`
`.aiqt-overlay` é modal de boas-vindas (cobre a tela, bloqueia conteúdo) mas não tem `role="dialog"`, `aria-modal`, focus trap, nem aria-labelledby pra `#aiqt-title`. Esc não fecha. Botão "Pular tour" perdido visualmente (cor `#94a3b8` sobre branco — 3.4:1, OK; mas o foco visual?).
**Fix:** `overlay.setAttribute('role','dialog'); overlay.setAttribute('aria-modal','true'); overlay.setAttribute('aria-labelledby','aiqt-title');` + listener de Escape que chama `aiArqTourSkip`, + focus trap entre `btn-skip`/`btn-back`/`btn-next`.

### 9. Reordenar fases no Gantt não anuncia mudança (P1)
**WCAG 4.1.3 Status Messages, 2.5.7 Dragging** · `cronograma.html:540-545, 670-684`
Os botões `.btn-up` / `.btn-down` (cronograma) têm `aria-label="Mover fase pra cima/baixo"` (bom), mas o reorder só dá feedback visual (flash de `ring-2 ring-indigo-300`). Usuário de leitor de tela não fica sabendo "fase X agora está na posição Y de N".
**Fix:** adicionar `<div id="reorder-announcer" class="sr-only" aria-live="polite"></div>` e em `moverRow`:
```js
document.getElementById('reorder-announcer').textContent =
  `Fase "${label}" movida pra posição ${novoIdx + 1} de ${rows.length}`;
```

### 10. `<input type="color">` sem label acessível no editor de fases (P1)
**WCAG 1.3.1, 3.3.2 Labels** · `cronograma.html:547`
`<input type="color" value="..." class="fase-cor ..." title="Cor" aria-label="Cor da fase" />` — `aria-label` está bom, mas o `title="Cor"` redundante. Mais importante: pra daltônico, escolher cor sem nome verbal é difícil. Mostre o hex code ao lado: `<span aria-hidden="true">#64748B</span>`. Já existe a info, só não tá renderizada.

### 11. Tab navegação em `dashboard.html` sem `role="tablist"` (P2)
**WCAG 1.3.1** · `projeto.html:408-419` (sub-tabs "Cotações"/"Revisada")
`<button onclick="switchUploadTab('cotacoes')">` sem `role="tab"`, `aria-selected`, `aria-controls`. Sub-tabs visualmente, mas semanticamente botões soltos.
**Fix:**
```html
<div role="tablist" aria-label="Tipo de upload">
  <button role="tab" id="tab-btn-cotacoes" aria-selected="true" aria-controls="tab-cotacoes">...</button>
  <button role="tab" id="tab-btn-revisada" aria-selected="false" aria-controls="tab-revisada">...</button>
</div>
<div id="tab-cotacoes" role="tabpanel" aria-labelledby="tab-btn-cotacoes">...</div>
```

### 12. Avatar dropdown sem `aria-expanded` (P1)
**WCAG 4.1.2** · `dashboard.html:112-156`
`<button onclick="toggleAvatarMenu()">` abre `#avatar-menu` mas não tem `aria-haspopup="menu"` nem `aria-expanded` (alterna `true`/`false`). Backdrop `#avatar-backdrop` (linha 87) usa `onclick="closeAvatarMenu()"` — funcional, mas não é focusable e não tem `aria-hidden`.

### 13. `<select>` com chevron custom via background-image (P2)
**WCAG 1.4.5 Images of Text** · `cadastro.html:108-117, 124-134, 141-151`
Selects com chevron via `style="background-image: url('data:image/svg+xml...')"` quebra em modo "Forced Colors" (Windows High Contrast). Setinha some.
**Fix:** usar pseudo `::after` via classe Tailwind ou um wrapper `<div>` com SVG `<svg aria-hidden="true">` posicionado absoluto.

### 14. Botão "limpar busca" no FAQ tem contraste fraco e ícone só (P1)
**WCAG 1.4.11 Non-text Contrast** · `faq.html:173-175`
`text-gray-300 hover:text-gray-500` no ícone "X" — 1.6:1 em rest. Só vira visível no hover. Usuário de teclado vê foco mas o ícone "some" no estado normal.
**Fix:** `text-gray-500 hover:text-gray-700`.

### 15. `target="_blank"` sem `rel="noopener"` na maioria dos casos (P2)
**WCAG 3.2.5 Change on Request (boa prática)** · 48 ocorrências de `target="_blank"`, apenas 11 com `rel="noopener"`
Exemplos: `dashboard.html` botões de download `target="_blank"`, `cadastro.html:179` link "Termos de Uso", `projeto.html` botões PDF/PPT. Fora `_blank` sem aviso prévio também viola 3.2.5 — adicionar `rel="noopener"` + texto "(abre em nova aba)" no `aria-label`.

### 16. Imagens decorativas com `alt=""` ausente (P1)
**WCAG 1.1.1 Non-text Content** · `index.html:73`, `dashboard.html:113`
`<img id="nav-avatar" src="" alt="" ...>` está OK (alt vazio = decorativo), MAS quando o avatar carrega `<img id="user-avatar" alt="Avatar">` (`dashboard.html:113`) — alt genérico "Avatar" não descreve. Se o usuário tem foto de perfil, deveria ser alt do nome: `alt="Avatar de Pedro Zellmer"` ou `alt=""` (puramente decorativo, já que o nome aparece ao lado).
**Fix:** `<img id="user-avatar" alt="" role="presentation">` — o nome adjacente já cumpre a função.

### 17. Pagamento icons em `index.html` com alt redundante (P2)
**WCAG 1.1.1** · `index.html:559-564`
`<img src="...visa.svg" alt="Visa">` — Visa é só o nome da bandeira, faz sentido manter. OK na verdade. Pra os ícones SVG `aria-hidden="true"` que JÁ estão no `<svg>` da maioria dos lugares (`index.html:97, 220`), as poucas que faltam:
**Fix:** auditar `<svg class="...">` sem `aria-hidden="true"` em botões que já têm texto. Procurar com Grep `<svg [^>]*>(?!.*aria-hidden)`.

### 18. Modal de contato (`contact-modal.js`) sem `aria-describedby` (P2)
**WCAG 1.3.1** · `contact-modal.js:99-200`
Tem `role="dialog"`, `aria-modal="true"`, `aria-labelledby="aicm-title-h"` (bom). Mas o subtítulo `#aicm-subtitle-p` ("Dúvida, sugestão, reclamação, parceria — todas chegam aqui.") não é exposto via `aria-describedby`. Screen reader anuncia só o título.
**Fix:** `modal.setAttribute('aria-describedby', 'aicm-subtitle-p');`. Mesmo no `aiArqContactClose`, foco volta pra origem — bom.

### 19. Drag-over CSS depende só de cor pra indicar drop válido (P1)
**WCAG 1.4.1 Use of Color** · `dashboard.html:32-36` (`.drop-zone.drag-over { border-color:#4f46e5; background-color:#eef2ff; }`)
Hover/drag-over altera só cor. Daltônico pode não notar a mudança. Adicionar ícone que muda, ou texto "Solte o arquivo aqui" via JS quando entra no estado drag-over.
**Fix:** em `dragover`, trocar texto interno: `dropZone.querySelector('p').textContent = 'Solte aqui pra adicionar';`. Em `dragleave`, volta pro texto original.

### 20. `kbd` styling de atalhos não conta com Windows High Contrast (P2)
**WCAG 1.4.11** · `revisao.html:29-33`
`kbd` usa `background:#f3f4f6; border:1px solid #d1d5db;` — em High Contrast Mode some o fundo. Texto fica em fundo branco do sistema, borda some. Usuário ainda lê o atalho, então é P2.
**Fix:** adicionar `border-color: currentColor;` no estilo do `kbd`.

### 21. `<dialog>` nativo não usado (P2)
**WCAG 4.1.2** · `revisao.html`, `cronograma.html`, `contact-modal.js`
Modais são `<div role="dialog">` em vez de `<dialog>` nativo (HTML5). `<dialog>` traz focus trap, Esc fecha, e backdrop grátis. Não é violação direta, mas é a melhor prática 2024+.
**Fix (longo prazo):** migrar pra `<dialog>` quando refatorar.

### 22. Estado focused do item revisado usa só outline + bg (P2)
**WCAG 2.4.7 Focus Visible** · `revisao.html:28` (`.item-row.focused { outline: 2px solid #4f46e5; outline-offset: -2px; background-color: #eef2ff; }`)
Tecnicamente OK (3:1 contra adjacent), mas `outline-offset:-2px` faz o outline ficar dentro do item — em telas pequenas pode ser sutil. `tabindex="-1"` no `.item-row` (linha 407) é correto pq foco é gerenciado por JS.

### 23. Páginas extensas sem `<h1>` único + hierarquia (P1)
**WCAG 1.3.1, 2.4.6 Headings and Labels** · `dashboard.html`
Cada tab tem seu próprio `<h1 class="text-2xl">` (`dashboard.html:185, 283, 547, 599...`). Quando tab está oculta (`hidden`), o `<h1>` ainda existe no DOM — screen reader pode pular pra ele mesmo invisível, dependendo da implementação. Visualmente OK. Melhor: o `<h1>` principal da página (statickly visível em todas tabs) seria o nome do app, e cada tab pode usar `<h2>`. Mas isso é refator. P1 mas tolerável.
**Fix:** considerar atributos `aria-hidden="true"` nas tabs ocultas pra blindar.

### 24. Animações sem opt-out via `prefers-reduced-motion` (P2)
**WCAG 2.3.3 Animation from Interactions** · `dashboard.html:43-81` (`@keyframes pulse-bar`, `spin-slow`, `bounce-house`, `menuFadeIn`), `chat-widget.js:62-65`, `onboarding-tour.js:65-67, 81-86`, `contact-modal.js:35`
Só `toast.js:75-77` honra `prefers-reduced-motion`. Resto continua animando — bug pra quem tem vestibular issues / enxaqueca.
**Fix:** adicionar em cada `<style>`:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

---

## 🔴 Bloqueadores duros

1. **Contraste `text-gray-300` (1.6:1)** em 6+ páginas — falha WCAG 1.4.3 AA. Aparece em copyrights e em placeholder "PDF, DWG ou DXF" do drop zone. **Risco real:** usuário com baixa visão (não só daltônico) não enxerga.
2. **Drop zone não opera por teclado** (`dashboard.html:353`) — `cursor-pointer` num `<div>` sem `tabindex` nem `role`. Usuário cego/teclado-only não consegue subir CAD. É o fluxo central do produto. **Risco real:** zero acessibilidade pro feature mais importante.
3. **Chat widget sem `role="dialog"` + focus trap** (`chat-widget.js`) — modal que captura input mas teclado escapa, leitores de tela não anunciam abertura. Aparece em todas as páginas públicas.
4. **Tour de onboarding bloqueia conteúdo sem semântica de modal** (`onboarding-tour.js`) — primeira impressão pra novo usuário. Se ele for teclado-only ou usar leitor de tela, fica preso.

---

## ♿ Top 10 fixes prioritários (em ordem)

1. **Skip link em todas as páginas** — 1 linha em cada HTML, ganho enorme pra teclado.
2. **Trocar todo `text-gray-300` por `text-gray-500`** — 11 ocorrências, fix de busca-e-substitui.
3. **`#drop-zone` virar `<label for="file-input">` com `tabindex="0"` e `role="button"`** — 2 lugares no `dashboard.html`. Habilita teclado no fluxo principal.
4. **`chat-widget.js`: adicionar `role="dialog"` + `aria-modal` + focus trap + Esc + `aria-live` em messages** — fix self-contained no JS.
5. **`onboarding-tour.js`: idem chat widget** — fix self-contained.
6. **`gradient-text` em números pequenos → `text-indigo-700`** — `index.html:111-123` (4 lugares).
7. **`@media (prefers-reduced-motion: reduce)` global** — copy/paste em cada `<style>` ou centralizar num CSS comum.
8. **Cronograma: aria-live announcer pra reordenar fases** — 1 div sr-only + 1 update no `moverRow`.
9. **Avatar dropdown: `aria-haspopup` + `aria-expanded` toggle** — 1 linha em `toggleAvatarMenu()`.
10. **Drop zone: feedback de drag-over não-só-cor** — trocar texto interno via JS.

---

## 🛠️ Lista de patches automáticos que posso aplicar agora

Sem decisão humana necessária:

1. **Substituir `text-gray-300` → `text-gray-500`** em 11 lugares (`cadastro.html:215`, `faq.html:173`, `dashboard.html:167, 359, 994, 1970, 1975`, `index.html:608`, `precos.html:477`, `visualizar-prancha.html:29, 36`). Único risco: o `text-gray-300` em `visualizar-prancha.html` está num botão SOBRE fundo escuro (`bg-slate-900` no header) — aí o cinza claro tem contraste OK e NÃO mexer. Validar antes de mudar.
2. **Adicionar skip link** logo após `<body>` em todas as páginas: bloco de ~3 linhas + `<main id="main">` se ainda não tiver `id`.
3. **`@media (prefers-reduced-motion: reduce)` global** dentro de cada `<style>` existente.
4. **`rel="noopener"` em todos os `target="_blank"`** sem rel — 37 ocorrências a corrigir.
5. **`<svg aria-hidden="true">`** em todos os SVGs decorativos dentro de botões com texto. Critério: se já tem texto irmão no mesmo `<button>`/`<a>`, marca o SVG como `aria-hidden="true"`. Cerca de 50+ lugares.
6. **Avatar dropdown `aria-expanded` toggle** — patchar `toggleAvatarMenu()` no `dashboard.html`.
7. **`role="dialog"` + `aria-modal` + `aria-labelledby` + `aria-live` em chat-widget.js** — patch isolado.
8. **`role="dialog"` + `aria-modal` + `aria-labelledby` em onboarding-tour.js** + listener de Escape.
9. **`<input type="color">` mostrar hex code ao lado** no editor do cronograma — 1 linha.
10. **`aria-live="polite"` announcer pro `moverRow` do cronograma** — div sr-only + 1 update.
11. **Drop zone (`#drop-zone` no `dashboard.html`) virar `<label for="file-input">` com `tabindex="0"` e `role="button"`** — também aplicar em `#cashback-drop-zone`.

Pode autorizar a aplicação dos 11 patches num único PR de acessibilidade. Estimativa: ~150 linhas alteradas, zero mudança de comportamento visual em uso normal.
