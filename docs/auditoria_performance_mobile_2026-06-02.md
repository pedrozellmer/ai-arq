# Auditoria de Performance & Mobile — AI.arq
**Data:** 2026-06-02 · **Auditor:** Claude (Performance Engineer) · **Escopo:** site público (`ai.arq.br`) + área logada

---

## Resumo executivo

Site funciona, mas leva no peito **3 freios duros**: (1) Tailwind CDN baixa ~120KB gzip / ~400KB descompactado em TODA página antes do primeiro paint; (2) 14 HTMLs têm `<meta http-equiv="Cache-Control" content="no-cache, no-store">` que mata cache do browser e faz repeat visit baixar tudo de novo; (3) dashboard/projeto/revisao/cronograma carregam `supabase-js` síncrono no `<head>` bloqueando render. Mobile tem touch targets pequenos (108 usos de `text-xs`/`h-6`/`py-1`) e backend Render free dorme — primeira request demora 30-60s. Bom: lazy loading nas 13 `<img>`, gzip ativo do GitHub Pages, preconnect já existe nas páginas principais (mas falta no blog).

**Nota Lighthouse estimada (mobile):**
- Performance: **55-65** (LCP alto por causa do Tailwind CDN sem critical CSS + script bloqueante)
- Accessibility: **85-90** (já melhorou na Onda B, ainda tem touch targets pequenos)
- Best Practices: **80-85** (Cache-Control problemático, sem CSP)
- SEO: **95+** (canonical, sitemap, schema.org já estão)

---

## 🟢 5 acertos

1. **Preconnect já configurado** nas páginas principais (fonts.googleapis.com, fonts.gstatic.com, cdn.jsdelivr.net, cdn.tailwindcss.com) — economiza ~100-200ms de handshake TLS por origem.
2. **`font-display=swap`** no Google Fonts — texto aparece com fallback enquanto Inter carrega, evitando FOIT (flash of invisible text).
3. **`loading="lazy"` em todas as 13 `<img>`** — incluindo os 6 ícones de bandeira de cartão na index.html que ficam below-the-fold.
4. **Gzip ativo no GitHub Pages** — `index.html` baixa 52KB raw → 12KB gzip; `dashboard.html` 176KB → 43KB gzip. Boa compressão.
5. **`defer` nos JS de widget** (`chat-widget.js`, `contact-modal.js`, `onboarding-tour.js`, `toast.js`) — não bloqueiam parsing do HTML.

---

## 🟡 Problemas (15)

### 🔴 Críticos (LCP / FCP)

1. **Tailwind via CDN em runtime** `<script src="https://cdn.tailwindcss.com">` — baixa 120KB gzip + executa JS pra gerar CSS no client. **Impacto: +800-1500ms no LCP em 3G.** Está em todas 33 HTMLs. Console mostra warning "should not be used in production".

2. **`<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">` em 14 páginas** — força revalidação a cada visita, anula o `max-age=600` que o GitHub Pages serve. Repeat visit = baixa tudo de novo. **Impacto: +2-5s em visitas subsequentes.** Comentário diz que foi pra "testadores não ficarem presos em versão antiga" — solução muito agressiva.

3. **`supabase-js` síncrono no `<head>`** em `dashboard.html` (linha 20), `projeto.html` (15), `revisao.html` (15), `cronograma.html` (13), `login.html` (21). Baixa 50KB gzip bloqueando o render. **Impacto: +200-500ms no FCP.** Na `index.html` está no fim do body (correto).

4. **Sem critical CSS inline** — depende totalmente do Tailwind CDN carregar pra qualquer estilo aparecer. Hero da landing fica sem estilo até CDN executar.

### 🟠 Médios

5. **Blog `/blog/index.html` e 19 posts não têm `<link rel="preconnect">`** pra fonts.gstatic.com e cdn.tailwindcss.com — perdem 100-200ms por origem em cold connection. Blog é onde tráfego SEO chega primeiro!

6. **`<script src="chat-widget.js" defer>` carrega em quase toda página pública** — 18KB raw + injeta CSS + faz fetch pra `/api/public/chat`. Não precisaria em página de termos/privacidade/login/cadastro.

7. **Backend cold-start (Render free) sem UX explícito de espera** — código em `projeto.html:711` reconhece que cold-start "demora 30-60s e o usuário fica olhando botão morto", mas NÃO há ping pre-emptivo na landing/login pra acordar o backend antes do upload. Quando usuário sobe DWG, vai esperar 30-60s sem feedback.

8. **`backdrop-blur-md` no `<nav>` sticky** (index, blog, dashboard, login) — em mobile médio (Android baixo/médio), backdrop-filter custa frames de scroll. Cada scroll vira jank.

9. **Inter com 5 pesos no blog `<link>`** (`@wght@400;500;600;700;800;900`) — 6 pesos! Mais que dobra peso da fonte vs 4 pesos da landing (400;500;600;700). 800 e 900 nunca são usados — só pra `font-extrabold` que aparece em 1 título.

10. **CSS duplicado entre as 33 HTMLs** — `gradient-main`, `gradient-text`, `shadow-gradient` redefinidos em cada página dentro de `<style>` inline. Bom pra critical CSS, mas se já houvesse arquivo CSS compartilhado seria cacheável.

11. **`dashboard.html` tem 180KB raw (3478 linhas)** — todo HTML, todas as 7 tabs renderizam de uma vez (só com `display: hidden`). Mobile parseia tudo mesmo escondido.

12. **Sem `<link rel="dns-prefetch">` pra ai-arq.onrender.com** — primeira chamada à API gasta ~100ms só de resolução DNS.

### 🟡 Pequenos

13. **`og-image.png` é PNG 22KB** — poderia ser JPG/WebP de ~8KB. Quase nada, mas é fácil ganho.

14. **Console warning constante "Tailwind should not be used in production"** — não afeta performance mas mostra pro Pedro um botão vermelho no DevTools toda hora.

15. **Sem `<link rel="manifest">` / Service Worker** — segunda visita ainda baixa tudo do zero. PWA não foi feito (decisão consciente listada no CLAUDE.md como "NÃO fazer agora — exagero pra 3 usuários"), mas vale revisar agora que tem 8+ usuários e blog atraindo tráfego repetido.

---

## 📱 Top 5 problemas mobile-específicos

1. **Touch targets abaixo de 44×44 em vários botões** — dashboard tem 108 ocorrências de `text-xs`/`h-6`/`py-1`/`px-2 py-1`. O dropdown do avatar usa `px-2 py-1.5` (~30px de altura). WCAG 2.5.5 e Material recomendam 44px mínimo. Daniela e Yuri (usuários ativos mobile) podem errar o tap.

2. **`overflow-x-auto` em 3 elementos do cronograma** (Gantt, Curva S, Matriz) + tabela de pagamentos no dashboard com `min-w-[640px]` — usuário mobile precisa fazer scroll horizontal. Funciona, mas sem indicador visual de "tem mais à direita". Vai parecer que falta dado.

3. **`backdrop-blur-md` em nav sticky** — jank em scroll mobile baixo/médio. iOS Safari renderiza bem, Android budget telefone (Moto G, Galaxy A) trava.

4. **Tailwind CDN executando em mobile 3G** — gera bottleneck na main thread por 1-2s antes do primeiro paint. Pedro testa em desktop fibra, mas usuário em campo (canteiro, deslocamento) usa 4G ruim.

5. **`min-w-[640px]` em tabela de pagamentos** força scroll horizontal antes mesmo de ter dados — em mobile 360px, o usuário vê só uma parte. Falta um modo "card stack" pra mobile (cada linha vira um cartão empilhado).

---

## ⏱️ Top 5 quick wins de performance

| # | Quick win | Ganho estimado | Esforço |
|---|---|---|---|
| 1 | Remover `<meta http-equiv="Cache-Control" content="no-cache, no-store">` das 14 páginas + adicionar `<meta name="version" content="0.5.0">` pra debug | **-2000 a -5000ms** em repeat visit | Patch 5min |
| 2 | Mover `<script src="supabase-js@2">` do `<head>` pro fim do `<body>` em dashboard/projeto/revisao/cronograma/login | **-300 a -500ms** no FCP | Patch 5min |
| 3 | Adicionar `<link rel="preconnect">` pra fonts.gstatic.com + cdn.tailwindcss.com no blog/index e 19 posts | **-150 a -250ms** no LCP mobile | Patch 10min |
| 4 | Adicionar `<link rel="dns-prefetch" href="//ai-arq.onrender.com">` em login/cadastro/dashboard + fazer "ping de aquecimento" assíncrono (`fetch('/api/health')`) na index.html quando usuário clica em "Comece Grátis" | **-2000 a -25000ms** percebidos quando usuário sobe primeira prancha (backend já acordado) | 15min |
| 5 | Trocar `font-family@wght@400;500;600;700;800;900` por `@wght@400;700` no blog | **-50 a -100KB** na fonte; **-80-150ms** | Patch 5min |

**Ganho composto estimado:** primeira visita ~500-800ms mais rápida, repeat visit ~3-5s mais rápida.

---

## 🛠️ Top 10 patches automáticos que eu aplico

Estes eu posso fazer agora sem decisão estratégica:

1. **Remover meta `Cache-Control: no-cache` das 14 páginas** — substituir por comentário "GitHub Pages serve max-age=600, browser revalida".
2. **Mover `<script src="...supabase-js@2">` do `<head>` pro fim do `<body>`** em dashboard.html, projeto.html, revisao.html, cronograma.html, login.html (e qualquer outra que precise).
3. **Adicionar `<link rel="preconnect">` no `<head>` do blog** (index + 19 posts via `blog/generate.py`).
4. **Adicionar `<link rel="dns-prefetch" href="//ai-arq.onrender.com">`** nas páginas que falam com backend.
5. **Reduzir pesos Inter** no blog de `400;500;600;700;800;900` pra `400;500;600;700` (alinha com resto do site).
6. **Adicionar ping de aquecimento** `fetch('https://ai-arq.onrender.com/health', {mode: 'no-cors'}).catch(()=>{})` na landing quando user clica em "Comece Grátis" → quando ele cadastra, backend já tá acordado.
7. **Adicionar `aria-label`** nos botões de touch só com SVG (ainda tem alguns no dashboard menu).
8. **Aumentar touch target do dropdown do avatar** de `py-1.5` pra `py-2.5` em mobile (`md:py-1.5` mantém densidade no desktop).
9. **Adicionar `loading="eager"` + `fetchpriority="high"`** no logo do nav (não tem hoje porque é div com texto, então N/A — mas vale notar) e no avatar do nav (que tem `loading="lazy"`).
10. **Inlinear hint visual de scroll horizontal** nas tabelas do cronograma + pagamentos: gradiente fade na direita só em mobile (`<640px`), avisando "tem mais →".

---

## ❓ Decisão pra Pedro

### Big picture: migrar Tailwind CDN pra build de uma vez?

**Hoje:** Tailwind CDN baixa 120KB gzip e executa JS pra gerar CSS toda vez que alguém abre uma página. É o maior freio de performance do site.

**Opções:**

#### A) Manter Tailwind CDN (status quo)
- ✅ Pedro não precisa de build pipeline (não é dev)
- ✅ Claude continua editando direto
- ❌ Performance ruim (perdendo ~1s no LCP mobile)
- ❌ Console warning permanente

#### B) Pré-compilar Tailwind via GitHub Actions
- ✅ CSS final ~10-20KB gzip (10× menor que CDN)
- ✅ Sem JS rodando pra gerar estilo (sumiu o bottleneck)
- ✅ Pedro continua editando HTML direto — só `class="..."` muda
- ⚠️ Precisa workflow `.yml` que roda `tailwindcss -i input.css -o tailwind.min.css` no push e commita o resultado, OU Pedro nunca olha pro CSS gerado
- ⚠️ Se Claude inventar classe nova, precisa estar no `tailwind.config.js` (raro hoje, todas as classes são padrão)

**Custo de migração:** ~3-4h de Claude criando workflow + ajustando os 33 HTMLs pra referenciar `tailwind.min.css` local. Reversível em 1 commit.

**Recomendação:** **Fazer B agora, antes do tráfego SEO subir.** A maioria dos 19 posts do blog ainda não foi publicada (cronograma vai até 12/07/2026). Se o blog viralizar e cada visitante perder 1s a mais por causa do Tailwind CDN, isso vira **bounce rate** ruim que prejudica ranqueamento Google. Custo é baixo, benefício composto cresce com tráfego.

### Decisão secundária: virar PWA?

**Hoje:** Service Worker = não. Manifest = não. Repeat visit baixa tudo do zero (agravado pelos meta `no-cache`).

**Pra fazer:**
- Manifest com ícones + cor primária — 30min de Claude
- Service Worker com cache de Tailwind + Inter + JS estático — 1-2h
- Banner "Instalar app" só pra usuários logados que já tiveram projeto entregue — 1h

**Benefício real:** repeat visit em 200ms (vs 2-3s), botão "AI.arq" no homescreen do celular do arquiteto vai pro canteiro.

**Recomendação:** **Adiar até pós-Indique-e-ganhe** (top priority do roadmap). PWA não fecha venda nova, só polish em quem já voltou. Indique-e-ganhe traz usuário novo.

---

## Próximos passos sugeridos

**Hoje (Claude aplica em ~30min total):**
- Patches 1-5 da lista de "Top 10 patches automáticos"
- Commit único: `perf: remove no-cache headers + move supabase-js to body + reduce font weights`

**Esta semana:**
- Decisão Pedro sobre migrar Tailwind CDN pra build (opção B acima)
- Se sim, Claude monta workflow + PR

**Mês:**
- Service Worker básico pra usuários logados (cache de assets estáticos)
- Modo card-stack pra tabelas em mobile <640px (tabela pagamentos, ranking comparativo)

---

## Apêndice — números crus

### Peso dos HTMLs (raw / gzipped)

| Página | Raw | Gzipped | Linhas |
|---|---|---|---|
| `index.html` | 53 KB | **12 KB** | 640 |
| `dashboard.html` | 180 KB | **43 KB** | 3478 |
| `projeto.html` | 83 KB | **21 KB** | 1579 |
| `revisao.html` | 49 KB | **13 KB** | 917 |
| `cronograma.html` | 71 KB | **20 KB** | 1510 |
| `blog/index.html` | 30 KB | **6 KB** | 359 |
| `login.html` | 15 KB | **5 KB** | 250 |
| `faq.html` | 94 KB | n/m | 1060 |
| `admin.html` | 120 KB | n/m | n/m |
| 19 posts blog | 21-39 KB cada | n/m | n/m |

### Recursos externos (por página da landing)

- **fonts.googleapis.com** + **fonts.gstatic.com** — Inter (4-6 pesos) com `display=swap` ✅
- **cdn.tailwindcss.com** — ~120 KB gzip / ~400 KB raw ⚠️
- **cdn.jsdelivr.net/npm/@supabase/supabase-js@2** — ~50 KB gzip / cache 7d ✅
- **cdn.jsdelivr.net/gh/aaronfagan/svg-credit-card-payment-icons** — 6 SVGs de bandeira, ~3KB cada
- **ai-arq.onrender.com** — só quando logado (chat widget faz call public)

### Imagens

Total no repo: ~200 KB.
- `logos/*.png` — 6 PNGs entre 12-30 KB
- `og-image.png` — 23 KB
- `apple-touch-icon.png` — 18 KB
- `favicon.ico` — 0.6 KB

Não tem imagem pesada no site. Bom.

### Cache headers servidos (GitHub Pages)

- HTML: `Cache-Control: max-age=600` ✅ (mas anulado pelos meta tags `no-cache` em 14 páginas ❌)
- Imagens: `Cache-Control: max-age=600` ✅
- JS estático local (chat-widget.js etc): `Cache-Control: max-age=600` ✅
- Tailwind CDN: `Cache-Control: max-age=14400` (4h) — bom
- Supabase JS CDN: `Cache-Control: max-age=604800` (7d) — ótimo

### Backend latência

`curl https://ai-arq.onrender.com/` quando acordado: **272ms** (HTTPS handshake + first byte).
Quando dormindo: 30-60s no primeiro request, depois <300ms.

---

*Auditoria conduzida lendo source local + curl + Read/Grep. Sem Lighthouse rodado — nota é estimativa fundamentada nos achados. Pra confirmar, basta rodar PageSpeed Insights em `https://ai.arq.br` quando quiser número oficial.*
