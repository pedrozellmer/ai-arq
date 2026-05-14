# 🤖 Contexto pra Claude — AI.arq

> **Você é Claude trabalhando no projeto AI.arq.** Esse arquivo é a sua orientação inicial. Lê tudo aqui antes de agir. O dono do projeto é o **Pedro Zellmer** (não-técnico, prefere ações em auto mode, fala português brasileiro coloquial).
>
> **Última atualização:** 2026-04-26

---

## 🛠️ Recursos Claude Code disponíveis (use!)

Esse projeto tem configurações prontas em `.claude/`. Use proativamente.

### Subagents (`.claude/agents/`)
- **`seo-auditor-br`** — audita post de blog antes de publicar (keyword, densidade, schema, fontes). Use quando editar `blog/posts.json` ou criar post novo.
- **⭐ `coo-conector`** — Chief Operating Officer. Conecta as 8 áreas (Produto, Marketing IG/Blog/Email, Jurídico, SEO, CS, Finanças, Conhecimento). Quando uma mudança rola (feature nova, pricing, fix de segurança), checa o que cada área precisa fazer e executa ou delega. Garante que nada escape. **Invoque depois de cada commit grande OU diga "COO, rolar feature X".**
- **`copywriter-br`** — revisa copy do site pra soar natural/coloquial brasileiro. Use quando editar texto de landing/FAQ/email.
- **`security-reviewer`** — revisão de segurança focada em SaaS (RLS, secrets, LGPD). Use antes de cada deploy ou ao mexer em auth/RLS/uploads.
- **`marketing-strategist`** — análise de métricas e ações de growth. Use quando Pedro perguntar sobre crescimento.

### Slash commands (`.claude/commands/`)
- **`/deploy`** — commit + push pro main com mensagem padronizada
- **`/regenblog`** — roda `python blog/generate.py` pra recriar os HTMLs
- **`/checksite`** — health check (site, backend, IG, DB) em paralelo

### Hooks (`.claude/settings.json` + `.claude/hooks/`)
- **Pre-commit secret scanner** — bloqueia commits com API keys, tokens, .env
- **On-save blog regen** — quando `blog/posts.json` muda, regenera HTMLs automaticamente
- **Post-push deploy notify** — após `git push`, mostra resumo no terminal (opcional: Telegram)

### Skills (`.claude/skills/`)
- **`seo-pt-br`** — gera/otimiza conteúdo SEO em PT-BR (posts, landing, meta description)

### MCP servers já conectados
- **Supabase MCP** — `mcp__dbd6b42c-...` — query banco direto, criar tabelas, executar SQL

### MCP servers ativáveis (TODO)
- **Stripe MCP** — relatórios financeiros direto pelo Claude. Setup em `.claude/STRIPE_MCP_SETUP.md`. Ativar quando 30+ usuários ativos.

---

## 📋 Quick start (leia isso primeiro)

Se você é uma sessão nova de Claude lendo isso pela primeira vez:

1. **Leia este arquivo inteiro** (15min) — pega o panorama
2. **Leia `ROADMAP.md`** (na raiz, mesmo lugar) — visão de longo prazo + decisões
3. Pra qualquer dúvida específica do código, **leia o arquivo direto** (não confie em memória)
4. **Auto mode é o padrão** — Pedro prefere que você execute em vez de pedir confirmação. Só pare pra perguntar se for destrutivo.
5. **Português coloquial** — sem jargão técnico em explicações pro Pedro. Use "você" e seja direto.

---

## 👤 Quem é o usuário

- **Nome:** Pedro Zellmer
- **Email:** zarelalopes@gmail.com (admin do sistema)
- **WhatsApp:** (21) 98207-9721
- **Empresa:** Fami Capital (separado do AI.arq, mas é o mesmo Pedro)
- **Perfil técnico:** **NÃO é dev**. Não roda comandos, não edita código manualmente. Você executa tudo.
- **Estilo de trabalho:**
  - Prefere AUTO MODE (executa sem perguntar)
  - Manda screenshots pra apontar problemas
  - Direto e objetivo, gosta de respostas curtas
  - Português coloquial brasileiro ("né", "tá", "bora")
  - Não quer relatórios longos, quer ação
- **Coisas que ele odeia:**
  - Jargão técnico desnecessário
  - Promessas vazias ("posso fazer tal coisa") — quer que faça
  - Texto longo demais quando uma frase resolve
  - Esquecimento de regras já estabelecidas (especialmente as duras)

---

## 🎯 O que é AI.arq

**SaaS brasileiro pra arquitetos** que gera planilha de quantitativos a partir de CAD (PDF, DWG, DXF). A IA lê as pranchas, identifica 18 disciplinas, e devolve XLSX com referência SINAPI/TCPO.

- **Site:** https://ai.arq.br
- **Backend:** https://ai-arq.onrender.com (Render)
- **Tagline atual:** "Quantitativo com IA" (NÃO "Orçamento com IA" — corrigido)
- **Fase atual:** Fase 1 (quantitativo) do roadmap de 10 fases — Fase 2 (Cronograma) em construção
- **Estado:** Beta v0.5.0 · 3 usuários cadastrados (1 ativa: Daniela Teixeira/DTZ Arquitetura)

### Modelo de negócio
- **1º projeto: GRÁTIS** (sem cartão)
- R$ 97 (1-5 pranchas) · R$ 157 (6-10) · R$ 247 (11-20) · +R$ 10/prancha extra
- Sem mensalidade, paga só quando usa
- Cashback (vigente desde 2026-05-13): R$30 upload planilha revisada + R$10/cotação fornecedor (cap 3 = R$30) = até R$60/projeto. Revisão inline não gera mais cashback — só treina a IA.

---

## 🚨 Regras DURAS (nunca violar)

Essas 6 regras são intransigíveis. Se você sugerir algo que violar, Pedro vai te corrigir na hora.

1. **🚨 NUNCA estimar como "confirmado"** — só BRANCO (medido) o que veio direto do CAD. Tudo o resto é LARANJA (estimado, revisar). Default sempre `estimado`, nunca `confirmado`.

2. **🚨 Isolamento absoluto de projetos** — cada projeto processado em isolamento. Zero contaminação entre projetos. Zero benchmarks hardcoded. Valor = IA lendo arquivos + lógica geométrica, NÃO memorização.

3. **🚨 Calibração por densidade/ratio (nunca valor absoluto)** — orçamentos antigos alimentam ratios (lum/m², sprinkler/m²) pra ALERTAR anomalias. Nunca copiam valores absolutos pro projeto novo.

4. **🚨 Taxonomia hierárquica, sem achatar** — itens vivem em árvore (folha → família → grupo → capítulo). Cor, PD, tipo específico nunca somem porque afetam compra real.

5. **🚨 NÃO precificar, NÃO substituir profissional** — AI.arq gera **quantitativo**, não orçamento. Quem precifica é o orçamentista. Toda interface deixa isso claro.

6. **🚨 LGPD: usuário = controlador, AI.arq = operador** — dados de cliente final pertencem ao usuário, AI.arq apenas processa.

---

## 🏗️ Arquitetura técnica

| Camada | Tecnologia | Onde fica |
|---|---|---|
| **Frontend** | HTML estático + Tailwind CDN + JS vanilla + Supabase JS | GitHub Pages (`ai.arq.br`) — domínio próprio |
| **Backend** | FastAPI (Python 3.13) + Anthropic Claude (Sonnet 4.5 + Haiku 4.5) | Render (free tier) |
| **Banco** | Supabase Postgres | Supabase US-West-2 |
| **Storage de arquivos** | Tempfile no Render (efêmero) + Supabase Storage | Bucket `contact-attachments` |
| **Pagamentos** | Stripe | — |
| **Auth** | Supabase Auth (email/senha + Google OAuth) | — |
| **Email transacional** | Supabase default (`noreply@mail.app.supabase.io`) | Migrar pra Resend ou SMTP custom (pendente) |
| **Instagram automation** | pg_cron interno (Supabase) + Meta Graph API v21 | `/api/instagram/scheduler/tick` |
| **Deploy** | GitHub Actions (.github/workflows/deploy-pages.yml) | Push em `main` → deploy automático |

### Por que HTML estático sem framework
Pedro não é dev → Claude consegue editar direto sem build pipeline. GitHub Pages = R$0. Migração pra React fica pra Fase 4-5 quando interface ficar complexa.

---

## 📁 Estrutura de pastas (DUAS pastas, ambas no Desktop)

> ⚠️ **Importante:** o projeto vive em **DUAS pastas separadas** no Desktop. Qualquer pessoa migrando o projeto precisa copiar AS DUAS.

### `arq/` — working directory (testes + assets gerados)
```
arq/                                  ← cwd do shell por convenção
├── 0326.CGR.14.*.dwg                 ← arquivos DWG de teste (Citrus)
├── 225.AFS.*.pdf                     ← arquivos PDF de teste (AFS)
├── *.dwg, *.pdf, *.dxf               ← outros projetos de teste
├── TESTE_*.xlsx                      ← outputs de teste do backend
├── quantitativos_aiarq_*.xlsx        ← outputs reais do backend pra inspeção
│
├── gen_carrossel_post1.py            ← script que gerou o carrossel IG
├── gen_semana1.py                    ← script dos 7 posts IG semana 1
├── gen_profile_pic.py                ← script da foto de perfil IG (6 opções)
├── gen_roadmap_docx.py               ← script que gerou Roadmap_AIarq.docx
│
├── instagram_post1_carousel/         ← 6 PNGs do carrossel "Como funciona"
├── instagram_semana1/                ← 7 PNGs dos posts semana 1 + LEGENDAS.md
├── instagram_profile_pic/            ← 6 opções de foto de perfil
│
├── Roadmap_AIarq.docx                ← roadmap em Word pra apresentação
├── cronograma-arquitetura.zip        ← projeto antigo Manus (referência)
├── cronograma-arquitetura-extracted/ ← extraído do zip pra inspecionar
│
└── Manual de Elaboração de Orçamentos - Obras.pdf  ← referência técnica
```

**Quando usar `arq/`:** rodar scripts de geração, testar com DWG/PDF, guardar outputs do backend pra inspeção. **Não vai pro git.**

### `projeto_arq/` — repositório git (código de produção)
```
projeto_arq/                          ← raiz do repo (deploy GitHub Pages)
├── CLAUDE.md                         ← este arquivo
├── ROADMAP.md                        ← visão de longo prazo + decisões
├── VERSION                           ← v0.5.0
├── index.html                        ← landing pública
├── login.html, cadastro.html         ← auth
├── dashboard.html                    ← área do usuário (com sidebar)
├── projeto.html                      ← detalhe de um projeto + Reportar problema
├── revisao.html                      ← interface de revisão dos itens
├── admin.html                        ← painel admin (Pedro only)
├── faq.html, termos.html, privacidade.html
├── chat-widget.js                    ← widget de chat público (lead capture)
├── contact-modal.js                  ← modal de contato (com modo "ticket")
├── onboarding-tour.js                ← tour 5 steps pra novo usuário
├── sitemap.xml, robots.txt           ← SEO
│
├── blog/                             ← /blog/ no site
│   ├── index.html                    ← listagem de posts (filtra por data)
│   ├── posts.json                    ← FONTE DA VERDADE dos 12 posts
│   ├── generate.py                   ← gera os HTMLs a partir do JSON
│   ├── posts/                        ← 12 HTMLs gerados
│   └── downloads/                    ← Memorial Descritivo PDF + DOCX
│
├── instagram_assets/                 ← imagens dos posts IG
│   └── semana1/                      ← 7 PNGs 1080x1080
│
├── backend/                          ← código do backend FastAPI
│   ├── main.py                       ← endpoint principal (~5000 linhas)
│   ├── instagram_*.py                ← agente IG (api, agent, store, webhook)
│   ├── analyzer.py                   ← lê CAD e extrai itens
│   ├── spreadsheet.py                ← gera XLSX
│   ├── consolidator.py               ← consolida itens
│   ├── cashback.py                   ← lógica de cashback
│   ├── density.py                    ← calibração por densidade
│   ├── sinapi/, tcpo/                ← bases SINAPI e TCPO carregadas
│   └── assets/                       ← fontes Montserrat + fotos Unsplash
│
├── .github/workflows/                ← deploy automático
│   └── deploy-pages.yml              ← workflow customizado pra GitHub Pages
│
└── HISTORICO_*.md                    ← históricos de sessões antigas
```

---

## 🔐 Onde está cada configuração / segredo

> ⚠️ **A maioria das configurações está NA NUVEM**, não no PC do Pedro. Boa notícia pra migração — quase nada precisa ser refeito.

| Config / Segredo | Onde está | Vai junto na cópia? |
|---|---|---|
| **ANTHROPIC_API_KEY** | `backend/.env` (local) + Render env vars (cloud) | ✅ Sim, no `.env` |
| **META_ACCESS_TOKEN** (Instagram) | `backend/.env` + Render env vars | ✅ Sim, no `.env` |
| **META_APP_SECRET** | `backend/.env` + Render env vars | ✅ Sim, no `.env` |
| **META_VERIFY_TOKEN** | `backend/.env` + Render env vars | ✅ Sim, no `.env` |
| **IG_USER_ID** | `backend/.env` + Render env vars | ✅ Sim, no `.env` |
| **STRIPE_SECRET_KEY** | Render env vars (cloud) | ☁️ Cloud, não precisa migrar |
| **Supabase URL + anon key** | Hardcoded nos HTMLs (público, OK) | ✅ No código |
| **Supabase service role** | Render env vars (cloud, sensível) | ☁️ Cloud, não precisa migrar |
| **Configuração Render** | Painel Render (cloud) | ☁️ Cloud |
| **Configuração GitHub Pages** | Painel GitHub (cloud) | ☁️ Cloud |
| **DNS ai.arq.br** | No registrador do domínio (cloud) | ☁️ Cloud |
| **Configuração Supabase project** | Painel Supabase (cloud) | ☁️ Cloud |
| **Tabelas + RLS Supabase** | No projeto Supabase | ☁️ Cloud |
| **Storage bucket Supabase** | No projeto Supabase | ☁️ Cloud |
| **Credenciais git (push)** | Git Credential Manager / GitHub CLI no PC | 🔄 **Refazer no PC novo** |
| **Login Claude Code** | Conta Anthropic no PC | 🔄 **Refazer no PC novo** |
| **Login no navegador (Pedro)** | Browser do PC | 🔄 **Refazer no PC novo** |

### Migração — checklist do PC novo

**Coisas que VÃO automaticamente (com a pasta):**
- ✅ Todo o código
- ✅ `backend/.env` com secrets (não está no git, vai como arquivo local)
- ✅ Histórico git (`.git/` dentro de `projeto_arq/`)
- ✅ Configuração git do projeto (user.email, user.name)

**Coisas que precisam ser REFEITAS no PC novo:**
1. **Instalar Claude Code** + login na sua conta Anthropic
2. **Instalar Git for Windows** se ainda não tem
3. **Login GitHub via CLI** ou Git Credential Manager:
   ```bash
   git config --global user.name "Pedro Zellmer"
   git config --global user.email "pedro.zellmer@famicapital.com.br"
   # Pra autenticação: usa o Git Credential Manager (instalado com Git for Windows)
   # Primeiro push vai abrir browser pra autorizar GitHub
   ```
4. **Instalar Python 3.13** (se for rodar scripts locais — `python blog/generate.py`, `gen_*.py`)
5. **Login no Supabase, Render, GitHub, Stripe** via navegador (conta web do Pedro)

**Coisas que NÃO precisam ser feitas:**
- ❌ Não precisa reconfigurar Render (já tem env vars lá, deploy é automático)
- ❌ Não precisa reconfigurar Supabase (banco + storage continuam intactos)
- ❌ Não precisa reconfigurar GitHub Pages (workflow continua rodando)
- ❌ Não precisa renovar DNS ou domínio (continua apontando)
- ❌ Não precisa reinstalar dependências Python (só se for rodar backend local — nunca faz)

### Como verificar tudo OK no PC novo

```bash
# 1. Pasta tá lá?
ls "C:/Users/admin/Desktop/arq/projeto_arq"

# 2. backend/.env tá com secrets?
ls -la "C:/Users/admin/Desktop/arq/projeto_arq/backend/.env"

# 3. Git funciona?
cd "C:/Users/admin/Desktop/arq/projeto_arq" && git status

# 4. Site tá no ar?
curl -I https://ai.arq.br

# 5. Backend tá respondendo?
curl https://ai-arq.onrender.com/health  # ou qualquer endpoint
```

Se algum falhar, me peça pra investigar.

---

## 🔌 IDs e endpoints importantes

### Supabase
- **Project ID:** `kqjabzwgbfuivzlcfvvu` (nome: ai-arq, US-East-1)
- **URL:** `https://kqjabzwgbfuivzlcfvvu.supabase.co`
- **Anon key:** está hardcoded em vários HTMLs (não é segredo, é meant pra ser público)
- **Service role key:** NÃO usar — backend usa anon key (suficiente pra operação)

### GitHub
- **Repo:** https://github.com/pedrozellmer/ai-arq
- **Branch principal:** `main`
- **Workflow de deploy:** `.github/workflows/deploy-pages.yml`

### Render
- **Service:** ai-arq-backend
- **URL:** https://ai-arq.onrender.com
- **Deploy:** automático em push pro main
- **Free tier:** o serviço dorme após 15min de inatividade

### Instagram (Meta Graph API v21)
- **App:** AI.arq-IG (ID: 1421819986294553)
- **Conta IG:** @ai.arq.br (ID: 17841427729064017)
- **Token:** META_ACCESS_TOKEN (env Render, expira ~13/06/2026)
- **Webhook:** https://ai-arq.onrender.com/api/instagram/webhook

### Stripe
- Configurado, chave em env do Render

---

## 📊 Estado atual das features

### ✅ No ar e funcionando
- Landing page com hero, recursos, preços, FAQ
- Cadastro/login (Supabase Auth + Google OAuth)
- Dashboard do usuário (projetos, cashback, cadastro, pagamentos)
- Upload de CAD (PDF/DWG/DXF) → processamento → planilha XLSX
- Sistema de cores (BRANCO medido / LARANJA estimado / CINZA metadado / ROXO indireto)
- Revisão inline (sem cashback — alimenta calibração da IA pro próximo projeto)
- Comparativo de fornecedores (upload XLSX múltiplos → quadro comparativo)
- Painel admin (Pedro): usuários, códigos beta, projetos, calibração, NPS, insights, leads chat, mensagens
- Cadastros incompletos visíveis no admin com botão "Reenviar login" (magic link)
- Chat widget público (Claude Haiku 4.5, lead capture com nome+email)
- Modal de contato com modo "ticket" (do projeto: assuntos pré-definidos + upload)
- Aba "Mensagens" no admin com filtros, badges, ações (responder por email, marcar lida, arquivar, WhatsApp)
- Onboarding tour 5 steps pro primeiro acesso (auto-trigger se onboarded != true)
- Blog com 12 posts agendados (1/semana, 26/04 a 12/07/2026), pesquisa profunda + fontes ABNT
- Memorial Descritivo PDF + DOCX baixáveis no post 1
- Instagram com 7 posts agendados via pg_cron (dia1 publicado em 26/04)
- SEO: sitemap.xml, robots.txt, schema.org Article em cada post

### ⏳ Pendente
- **Indique-e-ganhe** ⭐ TOP PRIORIDADE (viral loop)
- **Notificações por email** (planilha pronta, cashback ganho, retorno após 30d)
- **WhatsApp como canal de contato** (botão flutuante)
- **Página de cases** (após gravar testemunho da Daniela)
- Templates email Supabase em PT-BR
- Linkagem interna entre posts do blog
- Calculadora de preço interativa na landing
- Página `/precos.html` dedicada
- Setup email do domínio (Cloudflare Email Routing — pendente decisão Pedro)
- Renovar token Meta antes de 13/06/2026

### ❌ NÃO fazer agora (decisão tomada)
- Mobile app / PWA — exagero pra 3 usuários
- Programa de afiliados — só faz sentido com 100+ usuários
- Pagar Google/Meta Ads — antes de PMF não vale
- Reescrever em React — funciona até Fase 3
- Suportar fora do Brasil — foco BR até Fase 10
- Concorrer com Trello/Asana em features genéricas

---

## 🎨 Identidade visual

- **Nome:** AI.arq
- **Cores:**
  - Indigo `#4F46E5` (primária)
  - Cyan `#22D3EE` (acento)
  - Dark Slate `#0F172A` (fundo escuro)
  - Cream `#FAF7F0` (fundo claro)
- **Fonte do site:** **Inter** (4 pesos: 400, 500, 600, 700) via Google Fonts com `display=swap`. Atualizado 2026-05-14 — antes este doc dizia Montserrat mas o site sempre usou Inter. Inter foi mantida porque já está em produção e é mais legível em telas pequenas.
- **Fonte de assets gerados** (PNGs do Instagram, capas de PDF): Montserrat (Bold/SemiBold/Regular). Arquivos em `backend/assets/` e `arq/_scripts/`.
- **Logo:** texto "AI.arq" em Inter Bold no site, Montserrat Bold em PNGs/PDFs
- **Foto perfil Instagram:** opção 5 escolhida (`5-inline_dark_tagline.png`)

---

## 🔄 Fluxo de trabalho típico

### Quando Pedro pede algo
1. **Entenda o pedido** (não invente requisito)
2. **Execute** — auto mode é o padrão
3. **Commit + push** — Pedro espera ver no ar (~2min de deploy)
4. **Comunique resultado** com:
   - O que mudou (1-2 frases)
   - Onde testar
   - Próximos passos opcionais

### Quando alterar HTML do site
1. Edita o arquivo
2. `git add` específico (NÃO use `git add -A` — adiciona muita coisa não-desejada)
3. `git commit -m "msg em pt-br + Co-Authored-By: Claude"`
4. `git push origin main`
5. GitHub Pages publica em ~2min

### Quando alterar backend
1. Edita `backend/main.py` ou outros arquivos
2. Commit + push
3. Render faz deploy automático em ~3min
4. Backend pode dormir (free tier) — primeira request acorda

### Quando criar/alterar tabela Supabase
1. Use a MCP `mcp__dbd6b42c-...__apply_migration` (DDL) ou `execute_sql` (DML)
2. Migrations são versionadas automaticamente no projeto Supabase
3. NÃO crie service role key no frontend

### Quando atualizar blog
1. Edita `blog/posts.json` (fonte da verdade)
2. Roda `python blog/generate.py` (regenera todos os HTMLs)
3. Commit + push (inclui posts/, sitemap.xml, robots.txt)
4. Sitemap inclui só posts já publicados (filtra por data)

### Quando atualizar Instagram

🚨 **ANTES DE QUALQUER POST, LEIA `.claude/GRADE_INSTAGRAM.md`** — grade fixa
por dia da semana, regras duras de marca, convenção de slot_key.

1. Cada dia tem rubrica fixa (Bastidor seg, Erro caro ter, AIrnaldo qua, etc)
2. AIrnaldo posta SOMENTE quarta. Nunca outro dia.
3. NUNCA citar dia da semana na legenda sem o post estar travado nesse dia
4. Use Supabase MCP pra ver/alterar `instagram_scheduled_posts`
5. Imagens ficam em `instagram_assets/semana1/` (semana1) ou nomes equivalentes
6. pg_cron roda `/api/instagram/scheduler/tick` a cada 15min automaticamente
7. Convenção slot_key: `feed_<dia>_w<n>` (ex: `feed_qua_w2`, `airnaldo_w3`)

---

## 🛠️ Comandos úteis

```bash
# Ver status do git
git status --short

# Conferir commit recente
git log --oneline -5

# Regenerar blog
cd blog && python generate.py

# Conferir endpoint backend
curl https://ai-arq.onrender.com/api/instagram/scheduler/list

# Ver post no ar
curl -I https://ai.arq.br/blog/
```

---

## 📚 Referências externas (pra Claude consultar)

- **ROADMAP.md** — visão de longo prazo + 10 fases + decisões estratégicas (Fase 2 atual: Cronograma)
- **docs/INDEX.md** — mapa de contexto: índice de todos os históricos, regras duras, decisões importantes
- **docs/ATLAS_FEATURES.md** — ~140 features mapeadas de 3 fontes externas + posicionamento competitivo Flowup/Vobi/Sienge
- **README.md** (se existir) — overview rápido
- **docs/HISTORICO_AGENTE_INSTAGRAM.md** — como o agente IG foi configurado (movido pra docs/ em 10/05/2026)
- **docs/HISTORICO_SESSAO_COMPLETA.md** — registros de sessões antigas (movido pra docs/ em 10/05/2026)

---

## 🚧 Armadilhas conhecidas (pra não cair)

1. **`git add -A`** adiciona arquivos não-desejados (TESTE_*.xlsx, _preview_*.json, etc.) — sempre seja específico nos `git add`
2. **Render free tier dorme** — primeiro request após 15min inativo demora 30-60s
3. **GitHub Pages cache** — às vezes precisa hard refresh (Ctrl+Shift+R) pra ver mudança
4. **Supabase metadata não invalida** após updateUser — usuário precisa re-login pra ver mudanças
5. **Chrome console errors com `cookieManager`** — são extensão do Chrome, ignorar
6. **Variável Supabase JS** — em alguns HTMLs é `sb`, em outros é `sbClient`. Sempre confira antes de dar comando ao Pedro
7. **Tailwind CSS warning no console** — usa CDN em produção, sabido, ignorar
8. **`onboarding-tour.js`** auto-trigger só dispara se: logado + onboarded != true + (sem hash OU hash=#home)

---

## 💬 Como continuar conversas

### Cenário: PC novo, primeira sessão Claude
1. **Pedro copiou AS DUAS pastas** do Desktop antigo: `arq/` e `projeto_arq/`. Confirme isso antes de assumir tudo está disponível.
2. Pedro abre Claude Code dentro de `projeto_arq/`
3. Claude carrega esse `CLAUDE.md` automaticamente (convenção)
4. Claude responde a primeira pergunta já com contexto

### Como verificar se as duas pastas estão presentes
```bash
ls "C:/Users/admin/Desktop/arq/arq" | head -5
ls "C:/Users/admin/Desktop/arq/projeto_arq" | head -5
```
Se uma das duas não tiver, peça pro Pedro copiar do PC antigo.

### Cenário: Memória pessoal foi pro PC novo (raro)
A pasta `~/.claude/projects/.../memory/MEMORY.md` pode não ter sido copiada. Sem problema — esse arquivo aqui é self-contained.

### Cenário: Pedro pergunta algo específico que você não sabe
**Não invente.** Diga "Não tenho contexto disso na minha sessão. Pode me dar mais detalhes?" ou leia o arquivo relevante antes de responder.

---

## 🎯 Próxima ação recomendada (quando Pedro voltar)

Se Pedro perguntar "o que fazemos agora?", recomenda **Indique-e-ganhe** — é a próxima alavanca de maior impacto/menor custo. Detalhado em `ROADMAP.md`.

---

**Boa sessão! 🚀**
