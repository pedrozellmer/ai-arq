# Re-auditoria SEO + Conteúdo — ai.arq.br (2026-06-09)

Auditor: seo-auditor-br · Escopo: re-check dos fixes da auditoria de 02/06 + estado Instagram/Blog · Beta v0.5

---

## Resumo

Os fixes "fáceis" da auditoria de 02/06 foram TODOS feitos e estão no ar: noindex direto nas 9 páginas pós-login/auth, nav do blog apontando pra `/precos.html`, og:image + twitter:card em termos/privacidade. Mas os dois P0 que mais sangram tráfego continuam mal resolvidos: o **internal linking entre posts não foi feito** (zero "Leia também" em todo o blog) e o **sitemap voltou a defasar** — lista 6 posts mas já são 7 publicados (faltou regenerar quando o post de 07/06 entrou). Instagram saudável: dos 20 posts agendados (w23-w25), 7 publicados, 13 pendentes, **0 falhas** — mas o token Meta vence ~13/06 e há posts agendados a partir dessa data que vão falhar se não renovar.

---

## ✅ Fixes de 02/06 confirmados (estão no ar)

1. **noindex direto nas páginas pós-login (L3 · era P1)** — CONFIRMADO. As 9 páginas têm `<meta name="robots" content="noindex,follow">` no código E no ar:
   - `dashboard.html`, `admin.html`, `projeto.html`, `revisao.html`, `cronograma.html`, `visualizar-prancha.html`, `meus-projetos.html` (as 7 que faltavam) + `login.html`, `cadastro.html` (já tinham).
   - Verificado em produção: `https://ai.arq.br/dashboard.html` retorna a meta noindex.

2. **Nav `/#precos` → `/precos.html` (L14 · era P1)** — CONFIRMADO. O `generate.py` (nav e footer) agora aponta pra `/precos.html`. `/#precos` só aparece no próprio doc de auditoria antigo, em nenhum HTML/JS de produção.

3. **og:image + twitter:card em termos/privacidade (L4 · era P2)** — CONFIRMADO. Ambas têm `og:image` (og-image.png) e `twitter:card=summary_large_image`.

4. **robots.txt** — íntegro no ar, bloqueando as 9 páginas auth/pós-login + `/_*` + `/backend/`, com `Sitemap:` apontado certo.

5. **Schema.org** — válido nas páginas críticas: `SoftwareApplication`+`Offer` (index), `Product`+`Brand`+3×`Offer` (precos), `FAQPage` com 9 Q&A (faq), `Article` em todos os posts (gerado no `generate.py`).

---

## ⚠️ Fixes que NÃO foram feitos

1. **🔴 Internal linking entre posts (L2 · era P0) — NÃO FEITO.**
   - O `generate.py` NÃO ganhou nenhuma lógica de "Posts relacionados" / "Leia também". Busca por `Leia também|Posts relacionados|related` em todo o `blog/` = **0 ocorrências**.
   - Existe exatamente **1** menção a outro post em todo o blog, e é um link em TEXTO PURO (não clicável, sem tag `<a>`) dentro do corpo de `5-erros-quantitativo-atraso-de-obra` apontando pra `como-ler-quadro-de-esquadrias-p1-p2`. Não conta como internal link de SEO.
   - Resultado: o cluster topical (quantitativo + SINAPI + BDI + memorial) continua sem nenhuma costura interna. Mesma lacuna de 02/06, intacta.

2. **🔴 Sitemap defasado de novo (L1 · era P0) — REGREDIU.**
   - O `render_sitemap()` filtra por `publish_date <= hoje` (lógica certa), MAS o sitemap só é regenerado quando alguém roda `python blog/generate.py`. Não rodou desde 02/06.
   - Hoje (09/06) há **7 posts** com `publish_date <= 09/06` (o 7º é `como-pedir-cotacao-fornecedor-obra`, publicado 07/06). O sitemap — tanto o do repo quanto o no ar em `https://ai.arq.br/sitemap.xml` — lista só **6 posts** (até 31/05). Falta o post de 07/06.
   - Causa raiz: não existe automação ligando "passou a data de publicação" → "regenera sitemap". Vai defasar de novo a cada post novo que cruza a data. (O próprio doc de 02/06 já recomendava cron diário no GitHub Actions — não foi implementado.)

3. **🟡 twitter:card ainda falta em `precos.html` e `faq.html` (L5 · era P2) — NÃO FEITO.**
   - Têm og:* mas não têm o bloco `twitter:*`. Compartilhamento no X cai pro modo "summary" sem imagem grande. (termos/privacidade/index foram corrigidos; precos/faq ficaram pra trás.)

4. **🟡 `og:image:width`/`height`/`alt` em nenhuma página (L6 · era P2) — NÃO FEITO.** Busca = 0 ocorrências. Atrasa o preview do card. Cosmético, baixa prioridade.

---

## 📱 Estado Instagram (20 posts w23-w25)

Query: `instagram_scheduled_posts` onde `publish_at >= 2026-06-02`. Hora do banco: **09/06 19:54 UTC**.

| Status | Qtd | Período |
|---|---|---|
| ✅ published | **7** | 02/06 → 08/06 |
| ⏳ pending | **13** | 09/06 → 21/06 |
| ✗ failed | **0** | — |

- **Publicação está rodando certinho.** Cada post publicado saiu ~10-13 segundos depois do horário agendado, com `media_id` real retornado pela Meta. Último sucesso: `feed_seg_w24` em 08/06 22:00 UTC (media_id `17964340...`). Nenhuma mensagem de erro em nenhum dos 20.
- Os 13 "pending" são normais — são posts FUTUROS (de hoje 09/06 22h UTC em diante) que ainda não chegaram no horário. O de hoje (`feed_ter_w24`, 09/06 22:00 UTC = 19h BRT) está pending porque o banco ainda marca 19:54 UTC.
- Histórico geral: 72 posts no total, só 2 failed em toda a história (nenhum em w23-w25).

### 🚨 ALERTA Token Meta — vence ~13/06, hoje é 09/06 (4 dias)
- O token está **funcionando hoje** (sem falhas até 08/06). Mas vence ~13/06.
- **Posts em risco se não renovar:** `feed_sab_w24` (13/06 14h UTC) e TODOS os 7 da w25 (15/06 → 21/06). São 8 posts que vão dar `failed` se o token expirar e não for renovado antes.
- A janela segura é até o post de 12/06 (`feed_sex_w24`). A partir de 13/06 é roleta.

---

## 🟡 Lacunas novas (desde 02/06)

1. **Title/description longos demais em algumas públicas (truncam no Google):**
   - `index.html` — meta description **203 chars** (limite ~160; o Google corta o final "...quem precifica é seu orçamentista...").
   - `blog/index.html` — title **84 chars** (corta em ~60) e description **180 chars**.
   - `faq.html` — title **66 chars** (levemente acima de 60; aceitável mas no limite).
   - Demais (precos, termos, privacidade) estão dentro da faixa.

2. **`termos.html` e `privacidade.html` sem nenhum schema.org** — não têm `WebPage` nem `Organization`. Não é crítico (são páginas legais), mas é a única lacuna de schema que sobrou.

3. **Blog: 7 publicados, fila saudável.** 21 posts no `posts.json`; 7 com data <= hoje (último: `como-pedir-cotacao-fornecedor-obra`, 07/06). Próximos agendados: `bdi-em-obra-o-que-e-como-calcular` (14/06), `diferenca-entre-orcamento-e-quantitativo` (21/06), seguindo 1/semana até 30/08. Cadência boa — o gargalo é o sitemap não acompanhar.

---

## 🛠️ Top quick wins (ordem de impacto/esforço)

1. **Regenerar o sitemap agora** (5 min) — rodar `python blog/generate.py` + commit. Resolve o post de 07/06 que está fora do índice. (`/regenblog` faz isso.)
2. **Automatizar a regen do sitemap** (~30 min) — cron diário no GitHub Actions rodando `generate.py` e commitando se mudou. Mata o problema na raiz pra não regredir de novo a cada post que cruza a data.
3. **Implementar "Leia também" no `generate.py`** (~2h) — bloco no fim de cada post com 3 links pra posts irmãos por `category` + `keywords`. É o maior ganho de SEO orgânico parado há 7 dias (P0 de 02/06 nunca tocado).
4. **Renovar token Meta ANTES de 13/06** (Pedro, na conta Meta) — sem isso, 8 posts (13/06→21/06) vão falhar. Mais urgente em prazo que os itens de SEO.
5. **Encurtar description do index (203→~155) e title/desc do blog/index** (10 min) — pra não truncar no SERP.
6. **twitter:card em precos.html e faq.html** (5 min) — copiar o bloco do index.

---

## ❓ Decisão pra Pedro

**O token do Instagram vence em ~4 dias (13/06) e tem 8 posts agendados pra depois disso.** Eu não consigo renovar token sozinho — precisa de você na conta Meta (Business/Graph API) gerando um token novo de longa duração e colando na env do Render (`META_ACCESS_TOKEN`). Quer que eu prepare o passo-a-passo de como gerar esse token, ou você já sabe fazer? Se não renovar até 12/06, os posts de sábado (13) em diante param de publicar.

Os fixes de SEO eu faço sozinho em auto mode (regenerar sitemap + automação + "Leia também" + encurtar metas). Só confirma se quer que eu rode tudo isso e commite, ou se prefere revisar antes.
