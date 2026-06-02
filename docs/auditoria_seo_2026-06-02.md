# Auditoria SEO — ai.arq.br (2026-06-02)

Auditor: seo-auditor-br · Escopo: páginas públicas + blog + indexação · Beta v0.5

---

## Resumo executivo

Site tem base SEO sólida (canonical em 100% das públicas, schema.org em todas críticas, og-image 1200×630 correto, robots.txt bloqueando auth). Os dois problemas que mais sangram tráfego hoje são (a) **sitemap defasado** — só 5 dos 6 posts já publicados estão listados, e (b) **zero internal linking entre os 20 posts do blog**, o que joga fora a oportunidade de cluster topical em "quantitativo + SINAPI + BDI + memorial". Conserto dos dois leva ~3h e destrava o crescimento orgânico.

---

## 🟢 5 acertos

1. **Canonical em 100% das páginas públicas** (index, precos, faq, termos, privacidade, blog/, 20 posts) — sem risco de duplicate content.
2. **og-image PNG 1200×630 (22 KB)** — dimensão certa pro LinkedIn/Facebook/WhatsApp, peso ótimo.
3. **Schema.org bem distribuído** — `SoftwareApplication` no index, `Product`+`Offer` em precos.html, `FAQPage` em faq.html, `Article` com `Organization`/`publisher` em todos os 20 posts.
4. **Auth corretamente bloqueada no robots.txt** — `/login`, `/cadastro`, `/dashboard`, `/admin`, `/projeto`, `/revisao`, `/cronograma`, `/meus-projetos`, `/visualizar-prancha`, `/backend/` todos com `Disallow`. `noindex,follow` também presente em `login.html` e `cadastro.html`.
5. **Exatamente 1 H1 por página pública** — index (1), precos (1), faq (1), termos (1), privacidade (1), blog/ (1), todos os 20 posts (1 cada). Hierarquia limpa.

---

## 🟡 Lacunas (15)

### L1 · Sitemap defasado — falta 1 post já publicado · **P0**
- Arquivo: `sitemap.xml` (mtime 24/05/2026)
- O sitemap lista 5 posts, mas hoje (02/06) já são **6 publicados** conforme `publish_date` no `posts.json` (até 2026-05-31). O post `quanto-cobrar-planilha-quantitativos-2026.html` foi publicado 31/05 e não está no sitemap.
- Fix: rodar `python blog/generate.py` (o `render_sitemap()` já filtra por `publish_date <= today`) e commitar. Ideal: adicionar ao GitHub Actions um cron diário que regenere o sitemap.
- Bônus: dos 20 posts no JSON, 14 ainda são agendados (futuro) — o sitemap fica em 6/20 até 12/07, depois cresce semanalmente.

### L2 · Zero internal linking entre posts do blog · **P0**
- Arquivos: `blog/posts/*.html` (todos os 20)
- Cada post linka só pra navegação geral (`/`, `/blog/`, `/faq.html`, `/login.html`, `/#precos`) e fontes externas. Nenhum post linka pra outro post. Ex: `bdi-em-obra` não cita `bdi-arquiteto-br-2026-tabela`; `sinapi-vs-tcpo` não cita `quantitativo-arquitetura-sinapi-planilha-modelo`; `memorial-descritivo-de-obra-modelo-pdf-docx` não cita `memorial-descritivo-cau-prefeitura-sp-rj-bh` nem `memorial-a-partir-do-quantitativo-caminho-inverso`.
- Fix: adicionar ao final de cada post uma seção "Leia também" com 3 links pra posts irmãos do mesmo cluster (BDI, Memorial, Quantitativo, SINAPI). Ideal automatizar no `generate.py` por `category` + `keywords`.

### L3 · Páginas pós-login sem `<meta name="robots" content="noindex">` · **P1**
- Arquivos: `dashboard.html` (l.17), `admin.html` (l.15), `projeto.html` (l.13), `revisao.html` (l.13), `cronograma.html` (l.11), `visualizar-prancha.html` (l.11), `meus-projetos.html` (l.7)
- Bloqueio existe só via `robots.txt`. Se alguém colar o link em rede social ou e-mail, o crawler pode pegar antes do robots ser consultado (Google segue o Disallow, mas Bing/Yandex/agregadores nem sempre). `admin.html` tem 11 H1s — risco de indexar conteúdo cego é real.
- Fix: adicionar `<meta name="robots" content="noindex,nofollow">` em cada uma das 7 páginas, idêntico ao já feito em login.html/cadastro.html.

### L4 · `termos.html` e `privacidade.html` sem og:image nem twitter:card · **P2**
- Arquivos: `termos.html` (l.16-22), `privacidade.html` (l.16-22)
- Têm og:title, og:description, og:url, og:locale — mas falta `og:image` e o bloco `twitter:*` inteiro. Quando compartilhado no WhatsApp/LinkedIn fica sem thumbnail.
- Fix: copiar o bloco completo do `index.html` linhas 24, 28-32.

### L5 · `precos.html` e `blog/index.html` sem twitter:card · **P2**
- Arquivos: `precos.html` (só og, não twitter), `blog/index.html` (só og, não twitter)
- Twitter cards ausentes — quando compartilha no X/Twitter ou no app oficial cai pro modo "summary" sem imagem grande.
- Fix: adicionar 4 linhas `<meta name="twitter:card" content="summary_large_image">` + title/description/image.

### L6 · Falta `og:image:width` / `og:image:height` em todas as páginas · **P2**
- Arquivos: index.html, precos.html, faq.html, blog/index.html, 20 posts blog/posts/*.html
- Sem essas tags o crawler precisa baixar a imagem pra medir, atrasando o card preview.
- Fix: adicionar abaixo de cada og:image:
  ```html
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="AI.arq — quantitativo com IA">
  ```

### L7 · Falta schema `Organization` global e `BreadcrumbList` nos posts · **P1**
- Arquivos: `index.html` (só tem SoftwareApplication), todos os 20 posts (só tem Article)
- `Organization` no rodapé do index seria reaproveitada pelo Knowledge Graph (nome, logo, sameAs com Instagram). `BreadcrumbList` nos posts ajuda o Google a mostrar a hierarquia `Home > Blog > Post` nos resultados.
- Fix: adicionar `Organization` no index com `sameAs: ["https://instagram.com/ai.arq.br"]` e `logo`. Adicionar `BreadcrumbList` no `generate.py` pra incluir em todos os posts.

### L8 · `meta keywords` ainda usada (não tem peso há 10+ anos) · **P2**
- Arquivos: todos os 20 posts (l.9), `blog/index.html` (l.9)
- Google ignora desde 2009. Não atrapalha, mas pode passar info de cluster pra concorrente fazendo scraping. Pequeno ganho remover.
- Fix: remover `<meta name="keywords">` do `generate.py` ou manter só nas internas pra audit interno.

### L9 · Tailwind via CDN em produção · **P1**
- Arquivos: 100% das páginas usam `<script src="https://cdn.tailwindcss.com">`
- Conhecido pelo time (CLAUDE.md l.291). Custo SEO: o JIT compila no browser em tempo de runtime — atrasa o Largest Contentful Paint (LCP) em 200-600ms em conexão 3G, e o console mostra warning que polui. PageSpeed Insights penaliza.
- Fix (médio prazo): trocar pra Tailwind CLI gerando um `assets/tw.css` minificado (5-15 KB) num pre-commit hook ou no GitHub Actions. Mantém o "Pedro não é dev" intacto porque o build roda no servidor.

### L10 · `dashboard.html` title sem hífen padrão · **P2**
- Arquivo: `dashboard.html` l.17 — `<title>AI.arq - Dashboard</title>`
- Convenção do resto do site é `Página — AI.arq` (em-dash). Inconsistência pequena, ajeita ao adicionar noindex (L3).
- Fix: `<title>Dashboard — AI.arq</title>`.

### L11 · `admin.html` mesmo problema · **P2**
- Arquivo: `admin.html` l.15 — `<title>AI.arq - Admin</title>`
- Mesmo fix: `<title>Admin — AI.arq</title>` + noindex.

### L12 · Imagens com `alt=""` no nav (avatar) · **P2**
- Arquivo: `index.html` l.73 — `<img id="nav-avatar" src="" alt="">`
- Alt vazio é OK pra imagem decorativa, mas neste caso é o avatar do usuário e ele recebe `src` dinâmico no JS. Deveria receber `alt="Avatar de {nome}"` no momento que define o src. Leitor de tela hoje pula.
- Fix: setar `alt` junto com o `src` no JS quando carrega o avatar.

### L13 · Description do `cadastro.html` é genérica · **P2**
- Arquivo: `cadastro.html` l.16 (38 chars de conteúdo útil)
- "Cadastro do AI.arq — quantitativo de obra com IA. Primeiro projeto grátis, sem cartão." É curta (88 chars). Ok porque é noindex, mas se algum dia abrir vira problema. Não é prioritário.

### L14 · Falta linkagem de `precos.html` no `/#precos` antigo · **P1**
- Arquivos: `blog/posts/*.html` (todos), `blog/generate.py` NAV (l.55)
- O nav do blog ainda aponta pra `/#precos` (âncora interna do home) em vez da página dedicada `/precos.html`. Manda usuário pra home com scroll em vez da landing de preço (que tem schema Product). Perde sinal de comportamento (tempo, scroll) pro Google entender que `precos.html` é a página de preço canônica.
- Fix: no `generate.py`, trocar `href="/#precos"` por `href="/precos.html"` e regenerar.

### L15 · Página `precos.html` não está no nav do `index.html` · **P1**
- Arquivo: `index.html` l.64 — nav usa `<a href="precos.html">Preços</a>` ✓ OK
- Correção: erro meu na leitura inicial — index.html nav ESTÁ apontando pra precos.html. Mas o blog não. Confirma L14 isolado ao blog.
- (Manter este item pra cluster: alinhar nav entre site principal e blog num único template.)

---

## 🔴 Bloqueadores

Nenhum bloqueador hard. O caso mais próximo é a **L3** (páginas auth sem meta noindex direto) — risco de indexação acidental se virar URL pública por descuido, mas o `robots.txt` cobre 99% dos crawlers conhecidos.

---

## 📊 Top 5 quick wins (1h cada)

| # | Ação | Impacto | Esforço |
|---|---|---|---|
| 1 | Regenerar sitemap.xml (L1) — `python blog/generate.py` | Alto — recupera 1 post já publicado no índice do Google, prepara terreno pros próximos 14 | 5 min |
| 2 | Adicionar `<meta name="robots" content="noindex,nofollow">` em 7 páginas pós-login (L3) | Alto — fecha risco de indexação acidental do dashboard/admin | 30 min |
| 3 | Adicionar og:image + twitter cards em termos.html e privacidade.html (L4) | Médio — preview no WhatsApp/LinkedIn quando alguém cita "leu os termos" | 15 min |
| 4 | Adicionar `og:image:width/height/alt` em todo o site via `generate.py` + index/precos/faq (L6) | Médio — preview carrega ~300ms mais rápido | 30 min |
| 5 | Trocar `/#precos` por `/precos.html` no nav do blog (L14) — 1 edit no `generate.py` + regen | Alto — concentra sinal de comportamento na landing de preço | 15 min |

**Total: ~1h45min pros 5.**

---

## 📈 Top 3 projetos médios (1-3 dias)

### M1 · Internal linking automático entre posts (L2) · 1 dia
Editar `blog/generate.py` pra montar uma seção "Leia também" no final de cada post com 3 links escolhidos por overlap de `category` + `keywords`. Ideia: regra simples — primeiro tenta `category` igual (3 candidatos), depois fallback por keywords compartilhadas. Resultado: cluster topical robusto, especialmente nos triplets `bdi-*`, `memorial-*`, `sinapi/quantitativo-*`, `cronograma-*`. Hoje cada post é uma ilha; depois disso vira rede.

### M2 · Build de Tailwind no CI (L9) · 2 dias
Substituir `cdn.tailwindcss.com` por um build minificado servido como `assets/tw.css`. Implementar:
1. `tailwind.config.js` com `content: ['**/*.html', 'blog/generate.py']`
2. Step no `.github/workflows/deploy-pages.yml`: `npx tailwindcss -i src.css -o assets/tw.css --minify`
3. Trocar nas 33 páginas + no `generate.py` o `<script src=cdn>` por `<link href="/assets/tw.css">`
Resultado: LCP cai 200-600ms, console limpo, PageSpeed sobe 5-15 pontos. Mantém zero-friction pro Pedro (build roda na nuvem).

### M3 · Schema `BreadcrumbList` + `Organization` global (L7) · 1 dia
Adicionar no `index.html` o `Organization` com `sameAs` apontando pro Instagram @ai.arq.br e logo. Adicionar no `generate.py` o `BreadcrumbList` injetado em cada post: `Home > Blog > {category} > {title}`. Resultado: rich snippets com hierarquia visível nos resultados do Google (ganho de CTR mensurável em ~15-25% nos posts top).

---

## 🔮 Roadmap SEO 90 dias

### Mês 1 (jun 2026) — fundação
- Semana 1: aplicar todos os quick wins (L1, L3, L4, L6, L14) — total 2h
- Semana 2: M1 internal linking entre posts
- Semana 3: M3 BreadcrumbList + Organization schema
- Semana 4: ajustar `generate.py` pra regenerar sitemap automaticamente toda quinta (dia após publicar) via cron do GitHub Actions

### Mês 2 (jul 2026) — performance e cluster
- Semana 1-2: M2 build de Tailwind no CI
- Semana 3: criar 3 hub pages (clusters) — `/quantitativos/`, `/memorial-descritivo/`, `/sinapi/` — agregando os posts irmãos com intro original e 4-6 links pra posts filhos
- Semana 4: medir Search Console — quais queries trazem impressão mas não clique → otimizar title/description

### Mês 3 (ago 2026) — conteúdo e autoridade
- Lançar 4 posts pillar de 3000+ palavras com download de planilha modelo (lead magnet) pra captura de email
- Setup Search Console + Bing Webmaster Tools (se ainda não tem) e submeter sitemap atualizado
- Construir 3-5 backlinks orgânicos: aparecer em portais como Construtorenacional.com.br, ARCO da Construção, AECweb, CAU/BR — via guest posts ou citação como ferramenta IA
- Avaliar adicionar `LearningResource` schema nos posts que viraram tutoriais com download (Memorial PDF/DOCX e Cronograma Excel)

### Métricas de sucesso (alvos)
- **Indexação:** 21 URLs no Google em 30d (6 públicas + 15 posts conforme publish_date avança)
- **CTR médio:** subir de baseline atual pra 4-6% em 90d (rich snippets via Breadcrumb)
- **Sessions orgânicas/mês:** baseline atual → 300-600 sessões/mês em 90d (assumindo conteúdo manter ritmo semanal)
- **Top 10 ranking:** ao menos 5 queries com volume médio (>500/mês BR) — candidatas óbvias: "memorial descritivo modelo", "BDI obra cálculo", "SINAPI 2026", "quantitativo arquitetura", "cronograma físico-financeiro modelo"

---

## Anexo · Tamanhos de title/description

| Página | Title (chars, alvo 50-60) | Description (chars, alvo 150-160) | Status |
|---|---|---|---|
| index.html | 65 | 209 | Title ok limite · Description longa (corta no SERP em ~160) |
| precos.html | 60 | 148 | Ambos no ponto |
| faq.html | 73 | 170 | Title longo · Description um pouco acima |
| termos.html | 22 | 187 | Title curto demais (perde keyword) · Description longa |
| privacidade.html | 35 | 184 | Title curto · Description longa |
| blog/index.html | 91 | 186 | Title longo demais (Google corta no "|") · Description longa |
| Post BDI-obra | 97 | ~155 | Title corta no "|" — perda de keyword final |
| Post Memorial CAU | 81 | ~272 | Title ok no limite · Description longa demais |
| Post Quantitativo SINAPI | 84 | ~210 | Title ok · Description longa |
| Post Quanto cobrar 2026 | ~63 | ~160 | Ambos ok |
| Post Diferença orçamento×quantitativo | ~76 | ~205 | Title ok · Description longa |

**Padrão**: descriptions ficam frequentemente acima de 200 chars (média ~190). Google corta em ~160 no desktop e ~120 no mobile. Vale fazer uma passada no `posts.json` reduzindo todas as `description` pra 145-158 chars. Impacto pequeno mas garantido.
