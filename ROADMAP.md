# 🗺️ Roadmap AI.arq

> **Última atualização:** 2026-04-26
> **Versão:** 1.0 — consolidação inicial das fases planejadas

Este documento consolida a visão de longo prazo do AI.arq: onde estamos hoje, pra onde vamos, e o que evitamos no caminho. Vive em `ROADMAP.md` na raiz do repo (não vai pro GitHub Pages — é doc interno).

---

## 🎯 Visão de longo prazo (3-5 anos)

> **"Ser o sistema operacional do escritório de arquitetura brasileiro"** — começando pelo problema mais doloroso (levantamento de quantitativos manual), expandindo pra cobrir todo o ciclo de trabalho do arquiteto: do brief inicial à entrega da obra.

A meta NÃO é "tudo de uma vez". É **wedge strategy**: uma porta de entrada afiada → ganha confiança → expande horizontalmente.

---

## ⚖️ Princípios fundamentais (regras duras)

Estas regras orientam toda decisão de produto e nunca devem ser violadas:

1. **🚨 NUNCA estimar nada como "confirmado"**
   Só vira BRANCO (confiável) o que foi medido/contado direto do CAD. Tudo o resto sai LARANJA (sugestão, revisar). Default sempre `estimado`.

2. **🚨 Isolamento absoluto de projetos**
   Cada projeto é processado em isolamento. Zero contaminação entre projetos diferentes. Zero benchmarks hardcoded. Valor vem da IA lendo arquivos + lógica geométrica, não de memorização.

3. **🚨 Calibração por densidade/ratio (nunca valor absoluto)**
   Orçamentos antigos alimentam ratios (lum/m², sprinkler/m²) pra ALERTAR anomalias. Nunca copiam valores absolutos pro projeto novo.

4. **🚨 Taxonomia hierárquica, sem achatar**
   Itens vivem em árvore (folha → família → grupo → capítulo). Cor, PD, tipo específico nunca somem porque afetam compra real.

5. **🚨 NÃO precificar, NÃO substituir profissional**
   AI.arq gera **quantitativo**, não orçamento. Quem precifica é o orçamentista. Toda interface deixa isso claro.

6. **🚨 LGPD: usuário = controlador, AI.arq = operador**
   Dados de cliente final do projeto pertencem ao usuário. AI.arq apenas processa.

---

## 🪜 Fases do produto

### **FASE 1 — Quantitativo a partir de CAD (HOJE)**
**Status:** 🟢 Em produção · 3 usuários · 1 ativo (Daniela)
**Lançamento:** Janeiro 2026

**Wedge:** "Do CAD à planilha de quantitativos em 5 minutos."

- Upload PDF/DWG/DXF → IA lê → gera XLSX com 18 disciplinas
- Memória técnica SINAPI (10.284 composições + 54.529 insumos) e TCPO BIM (1.333 + 6.733)
- Sistema de cores (BRANCO medido / LARANJA estimado / CINZA metadado / ROXO custos indiretos)
- Revisão inline com cashback granular (R$0,10/ação até R$20)
- Cashback por upload de planilha revisada (+R$20) e cotação fornecedor (+R$5)
- Disclaimer claro: não precifica, não substitui profissional

**Preços:** R$97 (1-5 pranchas) · R$157 (6-10) · R$247 (11-20) · R$10/prancha extra · 1º grátis

**Métrica de saída pra Fase 2:** 50+ usuários ativos com 200+ projetos processados.

---

### **FASE 2 — Comparativo de propostas de fornecedores**
**Status:** 🟡 Já existe parcialmente · refinar
**Estimativa:** 6-12 meses (depois Fase 1 madura)

**Lógica:** Depois do quantitativo, arquiteto manda pros fornecedores. Volta com várias planilhas de cotação.

- Upload de XLSX dos fornecedores (parser strict + fuzzy)
- Comparativo pareado item-a-item (ranking, discrepâncias, itens esquecidos)
- PPT executivo com a marca do escritório (logo + cor)
- Envio direto pro cliente final via WhatsApp
- Heurísticas de mercado pra alertar discrepância (% de variação suspeita, share MAT/MO atípico)

**Métrica de saída pra Fase 3:** 200+ usuários com MRR R$10k+.

---

### **FASE 3 — Cronograma de obra**
**Status:** 🔵 Planejado
**Estimativa:** 12-24 meses

**Lógica:** Do quantitativo + cotação aprovada nasce naturalmente "quando começa cada etapa".

- Gantt simples por projeto (já tinha protótipo no `cronograma-arquitetura` antigo)
- Gera cronograma a partir das disciplinas do quantitativo (heurísticas de duração)
- Dependências entre tarefas (não pode pintar antes de assentar piso)
- Datas planejadas vs reais
- Considera dias úteis e feriados nacionais BR
- Notificações de vencimento

**Diferencial vs Trello/MS Project:** já vem com as etapas certas porque conhece o quantitativo.

---

### **FASE 4 — ERP do escritório (financeiro + CRM + galeria)**
**Status:** 🔵 Planejado
**Estimativa:** 24-36 meses

**Lógica:** Cliente já confia no AI.arq pra projeto. Hora de virar "tudo num só lugar".

- **Financeiro do projeto:** receitas + despesas, parcelas, fluxo de caixa, alertas de vencimento, dashboard consolidado de todos os projetos
- **CRM:** anotações de interação com cliente, tags, histórico
- **Galeria:** upload S3 de plantas/PDFs/renders/documentos, organização por categoria
- **Notificações unificadas:** vencimentos financeiros + tarefas de cronograma
- **Dashboard executivo do escritório:** receita prevista, projetos ativos, próximos vencimentos

**Inspiração:** o protótipo `cronograma-arquitetura` que já existiu (Manus.im) — mas refeito no stack do AI.arq.

---

### **FASE 5 — CAD 2D → 3D massing automático**
**Status:** 🔵 Planejado
**Estimativa:** 12-18 meses

**Lógica:** Sobe a planta 2D, ganha o volume 3D em 1 clique pra apresentação.

- Reconhece planta 2D → eleva paredes/lajes/forros
- Texturização básica (paredes, vidros, pisos)
- Export GLB/GLTF pra renders externos (Veras, etc.) ou web viewer embutido
- Integração futura com Hunyuan3D-2 (open-source) ou Tripo (API)

**Por que esperar:** tecnologia ainda imatura pra arquitetura pesada. Concorrentes (Finch3D, Hypar, Maket) têm 3-5 anos de vantagem técnica. Mas em 2027-2028 o open-source 3D vai amadurecer.

---

### **FASE 6 — Texto → planta + 3D + quantitativo (generativo BR)**
**Status:** 🔵 Visão
**Estimativa:** 24 meses

**Lógica:** Brief textual → IA gera proposta com planta + 3D + quantitativo já calibrado SINAPI.

- "Quero casa térrea 120m², 3 quartos, suíte master, garagem 2 carros, terreno 12x25" → 5 propostas em 30s
- Cada proposta vem com planta 2D + volume 3D + quantitativo + custo estimado SINAPI
- Iteração textual ("aumenta a sala, diminui um quarto")
- Aderência a normas brasileiras (ABNT, código de obras municipal)

**Concorrentes:** Maket.ai (Canadá, US$29/mês) é o mais próximo, mas focado USA/EU.

**Diferencial AI.arq:** **único integrado com SINAPI + normas BR**.

---

### **FASE 7 — Sistema operacional do escritório BR**
**Status:** 🔵 Visão de longo prazo
**Estimativa:** 36 meses

Tudo das Fases 1-6 + integrações:
- Marketplace de orçamentistas (parceiros)
- Marketplace de fornecedores
- Tabela SINAPI ao vivo + alertas de variação
- Integração com Receita Federal pra emissão automática de NF
- API pra ERPs maiores (TOTVS, SAP)
- Versão internacional (México, Argentina, Portugal)

---

## 🚀 Estratégia de marketing (5 alavancas)

Identificadas em sessão de 2026-04-24. Estado atual:

| # | Alavanca | Status | Próximo passo |
|---|---|---|---|
| 1 | **Caso da Daniela** (testemunho video) | ⏳ Pendente | Marcar call 30min essa semana |
| 2 | **Instagram orgânico** | 🟢 Iniciado (semana 1 agendada via pg_cron) | Ver engajamento, planejar semana 2 |
| 3 | **SEO de cauda longa** (blog) | ⏳ Pendente | 10 títulos + estrutura `/blog/` |
| 4 | **Indique e ganhe** (R$50/indicação) | ⏳ Pendente | Construir no dashboard |
| 5 | **Cold outreach LinkedIn** | ⏳ Pendente | Listar 20 arquitetos + roteiro DM |

**O que NÃO fazer agora:**
- Pagar Google/Meta Ads (PMF ainda em validação)
- Eventos/feiras (ROI > 6 meses)
- PR / mídia (sem números pra contar história)
- Influenciadores grandes (>100k seguidores) sem case sólido

---

## 🛠️ Stack técnica atual

| Camada | Tecnologia | Hospedagem |
|---|---|---|
| **Frontend** | HTML estático + Tailwind CDN + JS vanilla + Supabase JS client | GitHub Pages (`ai.arq.br`) |
| **Backend** | FastAPI (Python 3.13) + Anthropic Claude (Sonnet 4.5 + Haiku 4.5) | Render (`ai-arq.onrender.com`) |
| **Banco** | Supabase Postgres | Supabase (US-West-2) |
| **Storage de arquivos** | Tempfile no Render (efêmero) + Supabase Storage (planejado) | — |
| **Pagamentos** | Stripe | — |
| **Auth** | Supabase Auth (email/senha + Google OAuth) | — |
| **Email transacional** | Supabase default (`noreply@mail.app.supabase.io`) | Migrar pra Resend ou SMTP custom |
| **Instagram automation** | pg_cron interno + Meta Graph API v21 | Render endpoint `/api/instagram/scheduler/tick` |
| **Escolha proposital** | HTML estático sem framework pesado pra começar simples e baratíssimo | — |

**Por que NÃO React/Next pra frontend (ainda):**
- HTML estático carrega instantâneo
- Pedro não é dev — Claude consegue editar direto sem build pipeline
- GitHub Pages = R$0
- Migração pra React faz sentido na Fase 4-5 quando a interface ficar complexa

---

## 📋 Pendências de infraestrutura

| # | Item | Prazo | Detalhes |
|---|---|---|---|
| 1 | **Email do domínio** (`pedro@ai.arq.br`) | Quando Pedro decidir | Cloudflare Email Routing (gratuito, 30min setup). Zoho free virou ruim em 2026 (sem IMAP/POP) |
| 2 | **SMTP custom no Supabase** | Após item 1 | Pra emails saírem como `noreply@ai.arq.br` em vez de Supabase default |
| 3 | **Renovar token Meta (Instagram)** | Antes de 13/06/2026 | Token expira 60 dias da criação (14/04). Automatizar via endpoint |
| 4 | **App Meta em modo Produção (App Review)** | Quando engajamento DM crescer | Hoje em dev mode — só testers interagem via DM. Postar funciona normal |
| 5 | **Plugar Gemini 2.5 Flash Image** | Fase 2 do Instagram | Pra hero images conceito (~R$0,15/imagem) |
| 6 | **Custom email templates Supabase em PT-BR** | Após item 1 | Magic link, bem-vindo, planilha pronta |

---

## 🎨 Identidade visual

- **Nome:** AI.arq
- **Tagline atual:** "Quantitativo com IA" (NÃO "Orçamento com IA" — corrigido em 2026-04-26)
- **Cores:**
  - Indigo `#4F46E5` (primária)
  - Cyan `#22D3EE` (acento)
  - Dark Slate `#0F172A` (fundo escuro)
  - Cream `#FAF7F0` (fundo claro)
- **Fonte:** Montserrat (Bold, SemiBold, Medium, Regular, Light)
- **Logo:** texto "AI.arq" em Montserrat Bold (sem bullet/ponto extra). Versão dark e indigo
- **Foto perfil Instagram:** 6 opções geradas em `Desktop/arq/instagram_profile_pic/` — pendente escolha

---

## 🤝 Posicionamento competitivo

| Categoria | Concorrente | Como AI.arq se diferencia |
|---|---|---|
| **Quantitativo manual** | Excel + estagiário | 100x mais rápido, 1/10 do custo |
| **Orçamento BR (PROJETIVI, OrçaFascio)** | Foco em precificar (não quantificar) | Complementar, não concorrente — AI.arq alimenta eles |
| **Floor plan generation gringa (Maket, Architechtures)** | Foco USA/EU, sem SINAPI, em inglês | Único pra BR, com SINAPI/TCPO integrado |
| **Render IA (Veras, PromeAI, Lookx)** | Só faz render, não quantifica | Foco diferente |
| **3D generative (Tripo, Adam, Kaedim)** | Genérico, não específico arq | Foco diferente |
| **ERPs de escritório (Trello + Conta Azul + Drive)** | Fragmentados, não integrados | Tudo num lugar com IA no centro |

**Concorrente direto que não existe ainda (e não tem):**
- IA brasileira focada em arquiteto
- Integrada com SINAPI/TCPO/normas BR
- Que vai do CAD ao quantitativo ao 3D ao cronograma

**Janela de oportunidade:** ~3 anos antes de Maket/Finch3D abrirem versão BR (se abrirem).

---

## 🚫 O que NÃO vamos fazer (decisões já tomadas)

- ❌ **Precificar itens** — fica pro orçamentista
- ❌ **Substituir profissional habilitado** — sempre revisar
- ❌ **Reaproveitar dados de cliente A no projeto B** — isolamento absoluto
- ❌ **Vender mensalidade** — modelo é pay-as-you-use
- ❌ **Vender carbono** ou outras "extensões éticas" sem product-market-fit
- ❌ **Reescrever em React agora** — HTML estático funciona até pelo menos Fase 3
- ❌ **Suportar fora do Brasil agora** — foco BR até Fase 7
- ❌ **Concorrer com Trello/Asana** em features genéricas — só features específicas pra arq

---

## 📚 Histórico de decisões importantes

| Data | Decisão | Razão |
|---|---|---|
| 2026-01 | Lançar AI.arq como SaaS pra arquitetos | Pedro identificou dor real no mercado |
| 2026-04-12 | Hospedar Supabase em US-East-1 | Latência aceitável, plano free generoso |
| 2026-04-14 | Configurar agente Instagram (Manus + tokens Meta) | Automação de marketing |
| 2026-04-19 | Adotar SINAPI como vocabulário (não TCPO) | Aberto, gratuito, atualizado mensalmente |
| 2026-04-19 | Arquitetura hierárquica capítulo→grupo→família→folha | Não achatar pra preservar contexto |
| 2026-04-19 | Classificador Claude Haiku pra mapear itens | Custo baixo, qualidade boa o suficiente |
| 2026-04-23 | Pivot da hero copy: "orçamento" → "quantitativo" | Posicionamento honesto |
| 2026-04-24 | Chat widget público com lead capture | Funil comercial |
| 2026-04-24 | Admin com cadastros incompletos visíveis | Recuperar leads mornos |
| 2026-04-26 | Engajadora Instagram via pg_cron + Meta API | Eliminar dependência de cron-job.org |
| 2026-04-26 | Roadmap formalizado neste arquivo | Memória institucional |

---

## 🎯 Próximos passos (curto prazo)

**Essa semana:**
1. Validar que os 7 posts Instagram saem automaticamente (pg_cron rodando)
2. Pedro escolher foto de perfil Instagram (1-6)
3. Pedro marcar call com Daniela pra testemunho

**Próximas 2 semanas:**
4. Implementar "indique e ganhe" no dashboard
5. Estrutura inicial de blog `/blog/` pra SEO
6. Primeiros 3 artigos de blog (long-tail)

**Próximo mês:**
7. Planejar Semana 2 do Instagram (com base no engajamento da semana 1)
8. Setup email do domínio (Cloudflare Routing)
9. Renovar token Meta + automatizar renovação

---

## 📞 Contatos / referências

- **Repo:** https://github.com/pedrozellmer/ai-arq
- **Site:** https://ai.arq.br
- **Backend:** https://ai-arq.onrender.com
- **Supabase project:** `kqjabzwgbfuivzlcfvvu` (ai-arq)
- **Instagram:** [@ai.arq.br](https://instagram.com/ai.arq.br)
- **Admin email:** zarelalopes@gmail.com

---

*Este documento é vivo. Atualizar a cada decisão estratégica relevante.*
