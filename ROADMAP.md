# 🗺️ Roadmap AI.arq

> **Última atualização:** 2026-05-25
> **Versão:** 2.1 — Fase 5 redesenhada (ERP focado, não completo) após análise Braxio

Este documento consolida a visão de longo prazo do AI.arq: onde estamos hoje, pra onde vamos, e o que evitamos no caminho. Vive em `ROADMAP.md` na raiz do repo (não vai pro GitHub Pages — é doc interno).

> **🗺️ Atlas completo de features:** [`docs/ATLAS_FEATURES.md`](docs/ATLAS_FEATURES.md) — ~140 features mapeadas de 3 fontes externas (Bravy 114, Prevision 50, Amanda 10X 20) + roadmap próprio. Posicionamento competitivo (Flowup, Vobi, Sienge). **Documento canônico da visão de longo prazo.**

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

### **FASE 2 — Cronograma físico-financeiro automático** ⭐ (mudou em 12/05/2026)
**Status:** 🟢 Em construção — agent `cronograma-gerador` rascunhado
**Estimativa:** 4-8 semanas pra MVP

**Por que veio pra Fase 2 (antes era Fase 3):** Comparativo de fornecedores (antiga Fase 2) depende de cotação externa — gargalo no mundo real. Cronograma só precisa do que JÁ temos (planilha quantitativa). Reuso direto, tração mais rápida.

**Lógica:** Cliente recebe quantitativo + 1 clique gera Gantt + .mpp + curva S. Sem precificar — só distribui esforço no tempo.

- Endpoint `/api/cronograma/generate` que recebe `job_id` + duração total + tipologia
- Distribui 18 disciplinas no calendário por sequenciamento padrão BR
- Output: Gantt PNG + cronograma XLSX + curva S + memorial breve
- Agent `.claude/agents/cronograma-gerador.md` já criado
- Ressalva obrigatória: "validar com engenheiro responsável"

**Decisão registrada em [docs/HISTORICO_SESSAO_2026-05-10_a_12.md](docs/HISTORICO_SESSAO_2026-05-10_a_12.md).**

**Métrica de saída pra Fase 3:** 30+ cronogramas gerados + 50+ usuários com MRR R$ 3k+.

---

### **FASE 3 — Memorial descritivo + RRT + Caderno de acabamentos** ⭐ (consolidada em 12/05/2026)
**Status:** 🔵 Planejado
**Estimativa:** 8-16 semanas (depois Fase 2 estável)

**Lógica:** Cobrir o resto do ciclo CAU/prefeitura. Reusa quantitativo + adiciona texto/escolha.

**3a — Memorial descritivo + RRT**
- AI.arq escreve memorial PDF formato CAU/prefeitura (PMSP/PMRJ/POA)
- Cruza disciplinas do quantitativo com NBR 13532
- Pré-preenche RRT (arquiteto só assina)
- Checklist de documentos pra protocolo
- Agents base inspirados: `42-NBR-13532`, `08-projeto-legal-aprovacao-prefeitura`, `56-RRT-CAU`
- Preço: R$ 80 extra ou bundle

**3b — Caderno de acabamentos (FF&E)**
- Cliente escolhe fabricante BR pra cada item (Portobello/Eliane/Decortiles/Deca/Suvinil)
- Saída XLSX por ambiente com código fabricante + preço referência + link ficha técnica + prazo entrega
- Banco de SKUs (500-1000 produtos) + matcher
- **Monetização B2B possível:** comissão de afiliado dos fabricantes (em vez de cobrar do arquiteto)
- Agent base inspirado: `26-especificacao-acabamentos-caderno`

**3c — BDI Helper**
- Cliente recebe quantitativo + sugestão de BDI calibrado por tipo de obra (residencial/comercial/pública/retrofit)
- Decomposição: Adm Central (4-7%) + Adm Local + Despesas Indiretas + Despesa Financeira (1-2%) + Lucro (6-12%) + Tributos (8-13%)
- Editável célula a célula no XLSX (UX: amarelo % vs azul R$)
- Agent base: `31-BDI-Acordao-2622-TCU` (Bravy)
- **Template pronto:** [Sienge — Cálculo de BDI](../../arq/_archive/templates_referencia/sienge/materiais-sienge-planilha-calculo-de-bdi-2-0.xlsx). Copiar estrutura.
- Respeita regra dura: AI.arq SUGERE BDI, orçamentista DECIDE. Sugestão tem aviso "validar com seu orçamentista".

**3d — Orçamento por Ambiente** ⚡ (adicionado em 13/05/2026)
- View nova da planilha: organiza por **cômodo** (cozinha, banheiro, sala) em vez de por disciplina
- Resumo executivo: top 5 ambientes mais caros + custo por m² de cada
- Permite cliente decidir o que cortar quando orçamento não fecha
- **Quick win:** dados já existem na planilha, só nova view — 1 semana de dev
- Inspiração: Skill 4.4 do Arquiteto 10X (@amandag.ia)

**3e — Outros documentos técnicos** (radar)
- Memorial AVCB (agent Arq 31), Memorial SPDA (Eng 12), EIV (Arq 33)
- Relatório de visita técnica (Skill 4.6 / Arq 28)
- Orçamento sintético + analítico SINAPI (Eng 29 + 30)

---

### **FASE 4 — Comparativo de propostas de fornecedores** (era Fase 2)
**Status:** 🟡 Já existe parcialmente · refinar
**Estimativa:** depois Fase 3 estável

**Lógica:** Depois do quantitativo + cronograma + memorial, arquiteto manda pros fornecedores. Volta com várias planilhas de cotação.

- Upload de XLSX dos fornecedores (parser strict + fuzzy)
- Comparativo pareado item-a-item (ranking, discrepâncias, itens esquecidos)
- PPT executivo com a marca do escritório (logo + cor)
- Envio direto pro cliente final via WhatsApp
- Heurísticas de mercado pra alertar discrepância (% de variação suspeita, share MAT/MO atípico)

**Por que foi pra Fase 4:** depende do mundo real (fornecedores enviarem orçamento). Cronograma + memorial entregam valor sem essa dependência externa.

---

### **FASE 5 — ERP focado do escritório** ⭐ (redesenhada 25/05/2026 após análise Braxio)
**Status:** 🟢 Esqueleto **60% pronto** (código Manus antigo) · escopo redesenhado em 25/05/2026
**Estimativa:** 6-9 meses pro core (era 12-18 com escopo cheio)

**Decisão estratégica (25/05/2026):** depois de analisar a central de ajuda completa do Braxio (92 docs, 17 áreas), redefinimos Fase 5 pra **escopo focado** em vez de "ERP completo". A maioria do Braxio é commodity bem feita (NFSe, OFX, agenda, biblioteca de produtos) que custaria 18 meses construindo pra empatar. Vamos focar nas 5 peças que amarram o wedge técnico (quantitativo+cronograma) ao dia-a-dia do escritório.

#### 🎯 ESCOPO DA FASE 5 (só esses 5 módulos)

1. **Cliente / CRM básico** — cadastro PF/PJ, pipeline 5 status, ficha completa, anotações, importação de planilha
2. **Projeto consolidado** — cabeçalho (cliente/área/endereço/equipe) + abas Tarefas/Cronograma/Orçamento/Financeiro/Arquivos. NÃO replicar todas as 10 abas do Braxio — só as que conectam com nosso motor
3. **Orçamento operacional** — herda a planilha do quantitativo (já gerada pela Fase 1!), adiciona cotações múltiplas por fornecedor, status (Pendente/Cotado/Aprovado/Comprado/Recusado). **Aqui é o diferencial:** Braxio começa do zero, a gente começa populado do CAD.
4. **🔥 Reserva Técnica (RT) automatizada** — feature-âncora do ERP. Compra na cotação vira receita no DRE em 1 clique. **Esse é o gancho emocional que faz arquiteto aceitar pagar mensalidade.** Ninguém mais no mercado faz fluido.
5. **Portal Cliente granular** — 6 controles finos (esconde preço, fornecedor, pendência, responsável, datas reais, fase). NÃO é só "galeria de arquivos" — é portal de obra vivo. Subestimar isso entrega portal inferior ao do Braxio.

#### 🚫 O QUE NÃO ENTRA NA FASE 5 (intencional)

- **NFSe completa** — 18 meses de trabalho regulatório/municipal. Parceria com Conta Azul ou similar faz mais sentido.
- **OFX banco a banco** — commodity (8 bancos BR). Integração via Pluggy ou Belvo se virar prioridade.
- **DRE completo + Fluxo de Caixa** — versão simplificada por projeto OK, DRE global do escritório fica fora.
- **Agenda + Google/iCloud sync** — commodity. Usuário usa Google Calendar próprio.
- **Biblioteca de produtos** — temos SINAPI/TCPO (melhor!). Não duplicar.
- **NFSe, recibos, custos fixos recorrentes** — tudo pertence ao parceiro fiscal.

#### 🛡️ Permissões e multiusuário — DAY 1, não "depois"

Lição dura da análise Braxio: escritório de 5+ pessoas exige permissões granulares no dia 1. Refatorar autenticação depois custa caro (refactor de RLS no Supabase, migração de dados, regenerar tokens).

- 5 cargos: Proprietário, Sócio, Admin, Coordenador, Colaborador
- 4 níveis por módulo: Completo / Visualizar / Atribuído / Sem acesso
- Aplicar via Supabase RLS desde a 1ª query da Fase 5

#### 💰 Modelo de preço — HÍBRIDO (decisão dura, 25/05/2026)

**Avulso continua** (R$97-247 por projeto) como porta de entrada pelo wedge. Cliente paga R$97 pelo quantitativo, vira lead.

**Mensalidade só pro módulo ERP** — quem ativa CRM+Projeto+Orçamento+RT+Portal paga mensalidade tipo R$79-149/mês (a definir; menor que Braxio R$119 pra estar abaixo da concorrência inicialmente). Não substitui avulso, soma.

Isso revoga a decisão antiga "NÃO vender mensalidade — modelo é pay-as-you-use". A regra agora é: **avulso pra quantitativo, mensalidade pra ERP. Híbrido.**

#### 📦 Código base existente

- Localização: `arq/_archive/cronograma-arquitetura-extracted/`
- Stack: React + tRPC + Drizzle (MySQL) — migrar pra Supabase quando ativar a Fase
- Já tem: Tasks/Timeline, CRM Notes, Financeiro (entrada+parcelas+edição), Galeria, AI Chat Box, Dashboards (Cash flow, CRM, Financial), Mapa de projeto
- **Falta:** integrar com motor AI.arq atual + 114 agents Bravy
- **Próximo passo (quando ativar Fase 5):** auditar quais das 5 peças do escopo já têm esqueleto no código herdado. Cliente/CRM e Financeiro provavelmente sim. RT e Portal granular provavelmente não.

#### 📅 Quando começar

Quando atingir **50+ usuários ativos** (hoje ~8). Não antes — esticaria produto fino sobre fundação rasa.

#### 🎯 5 lacunas do Braxio que a Fase 5 defende

Mapeadas na análise de 25/05/2026 — ao construir Fase 5, manter essas vantagens visíveis em todo lugar:

1. **Lemos CAD/DWG/PDF.** Braxio aceita upload mas trata como blob.
2. **Orçamento já populado do CAD.** No Braxio o cara digita item por item, manual.
3. **Comparativo de fornecedor automatizado** com IA sugerindo equivalentes e alertando preço fora da curva.
4. **Versionamento automático de arquivos.** Braxio confessa na ajuda: "ainda não cria histórico automático de versões".
5. **IA que faz o trabalho.** A "IA" do Braxio é assistente que responde "quais projetos atrasados?". A nossa gera planilha.

**Fonte completa:** análise de 92 docs da central de ajuda Braxio em 25/05/2026 — relatório em `docs/ANALISE_BRAXIO.md` (se criado posteriormente).

---

### **FASE 6 — Pré-projeto + viabilidade urbana** ⭐ (adicionado em 13/05/2026)
**Status:** ⚪ Radar
**Estimativa:** depois Fase 5 ter tração

**Lógica:** Entrar **antes** do CAD. Captura cliente no estágio mais cedo do funil (ele ainda nem desenhou). Diferencial vs Flowup/Vobi: eles não cobrem pré-projeto, só execução.

- **Estudo de Viabilidade Urbana** — 8 itens: taxa de ocupação, coef. aproveitamento, gabarito, recuos, permeabilidade, vagas, uso, restrições especiais. Cruza com código local do município. Devolve VIÁVEL / VIÁVEL COM AJUSTES / INVIÁVEL.
- **Análise de terreno** — planialtimétrico + insolação + ventos
- **Programa de Necessidades** — zonas funcionais + hierarquia (essencial/importante/desejo)
- **Moodboard conceitual** — IA generativa pra referência visual
- **Estudo preliminar** (residencial / comercial) — partido + estudo de massas

**Agents base inspirados:** Skill 3.1-3.4 do Arquiteto 10X · Arq 01-07 Bravy

**Diferencial:** captura o lead **antes** do projeto existir. Aluno do curso Amanda 10X aprende a fazer Briefing → AI.arq entrega Briefing pronto.

---

### **FASE 7 — CAD 2D → 3D massing automático**
**Status:** 🔵 Planejado
**Estimativa:** 12-18 meses

**Lógica:** Sobe a planta 2D, ganha o volume 3D em 1 clique pra apresentação.

- Reconhece planta 2D → eleva paredes/lajes/forros
- Texturização básica (paredes, vidros, pisos)
- Export GLB/GLTF pra renders externos (Veras, etc.) ou web viewer embutido
- Integração futura com Hunyuan3D-2 (open-source) ou Tripo (API)
- **Renders 3D Interno + Externo** (Skill 5.2 e 5.3 do Arquiteto 10X)
- **Planta humanizada** (Skill 5.1)

**Por que esperar:** tecnologia ainda imatura pra arquitetura pesada. Concorrentes (Finch3D, Hypar, Maket) têm 3-5 anos de vantagem técnica. Mas em 2027-2028 o open-source 3D vai amadurecer.

---

### **FASE 8 — Conformidade e auditoria normativa** ⭐ (adicionado em 13/05/2026)
**Status:** ⚪ Radar
**Estimativa:** depois Fase 3 estável

**Lógica:** Diferencial competitivo enorme. **Nenhum concorrente BR faz auditoria automática de NBR** — nem Flowup, nem Vobi, nem Sienge. A gente já tem o pipeline de leitura de CAD (Fase 1) — aproveita pra adicionar verificação normativa.

- **Verificador NBR 9050** (acessibilidade) — 7 categorias: portas/circulações, banheiros acessíveis, cozinhas adaptáveis, alturas, sinalização, estacionamento. Output em quadro-resumo ✅/⚠/❌
- **Verificador NBR 15575** (desempenho) — categorias estrutural/térmico/acústico/lumínico
- **Verificador NBR 9077** (saídas de emergência)
- **Análise de código local** — cruza projeto vs lei municipal vigente
- **Compatibilização Arq × Engenharias** — confronta arquitetura, estrutural, hidro, elétrico → lista de conflitos

**Agents base:** Skill 6.1-6.4 do Arquiteto 10X · Arq 32, 38, 39, 50 Bravy

**Monetização:** módulo premium. Arquiteto entrega projeto pra cliente comercial/público sabendo que tá conforme. Vale R$ 50-100 por auditoria.

---

### **FASE 9 — Texto → planta + 3D + quantitativo (generativo BR)**
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

### **FASE 10 — Sistema operacional do escritório BR**
**Status:** 🔵 Visão de longo prazo
**Estimativa:** 36+ meses

Tudo das Fases 1-9 + integrações + pós-obra:
- Marketplace de orçamentistas (parceiros)
- Marketplace de fornecedores
- Tabela SINAPI ao vivo + alertas de variação
- Integração com Receita Federal pra emissão automática de NF
- API pra ERPs maiores (TOTVS, SAP)
- **Pós-obra:** Habite-se, Averbação cartório (RGI), Regularização REURB, INSS/CNO/CEI, Manual do proprietário (NBR 14037)
- Versão internacional (México, Argentina, Portugal)

---

## 🧭 Posicionamento competitivo (atualizado 13/05/2026)

| Player | Cobertura | Preço | Vantagem AI.arq |
|---|---|---|---|
| **[Braxio](https://www.braxio.com.br/)** ⭐ benchmark detalhado | ERP completo: CRM, Propostas, Projetos com 10 abas, Tarefas+workflows, Horas, Orçamentos com cotações múltiplas, **Reserva Técnica → DRE**, Obras (execução+visitas+pendências+Gantt+PDF), Financeiro completo, **NFSe completa (A1+LC116+reforma tributária)**, **OFX 8 bancos BR**, Portal Cliente com 6 controles granulares, Arquivos com pastas padrão, Biblioteca, Fornecedores, Agenda+Google/iCloud, Equipe+5 cargos+permissões | R$119 / R$199 / R$319 / mês | **Não lê CAD. Aceita DWG mas trata como blob. Orçamento começa do zero (manual). Sem versionamento automático de arquivos (confessam na ajuda). IA é só assistente operacional, não faz o trabalho.** Análise completa: 92 docs lidos em 25/05/2026. |
| **[Flowup](https://www.flowup.me/)** (1.000+ escritórios BR) | ERP projeto+financeiro+equipe. Parceiro ASBEA/CREA | sob consulta | **Não lê CAD. Não gera quantitativo. Sem IA técnica.** |
| **[Vobi](https://www.vobi.com.br/)** (Y Combinator, R$5B obras/ano) | Gestão de obra completa. 3 agents IA (Financeiro, Compras, Diário) | sob consulta | **Foco construtora, não escritório. IA é assistência, não leitura de CAD.** |
| **[Sienge](https://www.sienge.com.br/)** | 12 módulos, construtora grande | caro | **Caro. Foco incorporadora.** |
| **[Projetools](https://www.projetools.com.br)** | Gestão escritório arq | — | **Pequeno, sem IA.** |
| **[Arquiteto 10X](https://amandag.ia)** (curso) | 20 skills Claude pra arquiteto BR | — | **É curso, não SaaS. Cliente dele é nosso lead aquecido.** |

**Aposta dura:** **leitura de binário (DWG/PDF) + IA específica de arquitetura** é nossa vantagem defensável. Flowup/Vobi/Braxio não vão entrar nessa briga sem refazer stack inteiro. Tempo é nosso aliado.

**Sobre o Braxio especificamente:** é o produto mais maduro pra o nosso público-alvo. NÃO é concorrente direto hoje (eles cobrem admin, a gente cobre técnico), mas se entrarmos na Fase 5 viramos sobrepostos. Estratégia: defender o wedge técnico que eles não têm + replicar só as 5 peças que conectam (CRM+Projeto+Orç+RT+Portal). Resto não vale o tempo.

---

## 🧭 Features candidatas (radar pós-Fase 4)

Mapeado em 12/05/2026 a partir das 50 prompts Prevision + 114 agents Bravy. Não tem timing definido, mas é o que mercado BR procura e não está coberto hoje:

### Adjacentes ao Cronograma (Fase 2)
- **Fast-tracking** — plano de aceleração de obra quando atraso já aconteceu
- **Lean Construction + Last Planner System** — pull planning + lookahead 6 semanas
- **Planejamento reverso** — do final pro início, tipo Goldratt
- **Concretagens** — datas precisas de concretagem com curva de cura
- **Ciclos repetitivos** — pavtipo a pavtipo em multifamiliar

### Operacional (Fase 5 ERP)
- **Cenários de atraso** — simulador "e se isso der errado?"
- **Plano de transição entre fases** — handoff entre estrutura → vedação → acabamento
- **Férias coletivas BR** — peculiaridade local que ninguém cobre (~22/12 a 03/01)

### Validação técnica
- **Conformidade com normas** (NBR 9050 acessibilidade, NBR 15575 desempenho) — auditoria automática do CAD
- **Análise de restrições ambientais** — terreno × CONAMA × outorga ANA

Fontes: Prevision 50 prompts + Bravy 114 agents.

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
- ✏️ **~~Vender mensalidade~~ → REVOGADO em 25/05/2026.** Agora é HÍBRIDO: avulso pro quantitativo (porta de entrada), mensalidade só pro módulo ERP (Fase 5).
- ❌ **Vender carbono** ou outras "extensões éticas" sem product-market-fit
- ❌ **Reescrever em React agora** — HTML estático funciona até pelo menos Fase 3
- ❌ **Suportar fora do Brasil agora** — foco BR até Fase 10
- ❌ **Concorrer com Trello/Asana** em features genéricas — só features específicas pra arq
- ❌ **NFSe completa, OFX banco a banco, DRE global do escritório, agenda com sync, biblioteca de produtos** — commodity bem feita por parceiros (Conta Azul, Pluggy, Belvo). Não replicar Braxio aqui. Decidido 25/05/2026.

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
| 2026-05-24 | Hero focado no wedge (quantitativo do CAD), comparativo/PPT viram bônus | Promessa central afiada, conversão maior |
| 2026-05-24 | Cadastro em 2 etapas — CPF só antes do 1º pagamento | CPF no cadastro era atrito alto pra testar o gratuito |
| 2026-05-25 | Análise competitiva profunda do Braxio (92 docs lidos) | Pedro decidiu seguir visão ERP, precisava de benchmark real |
| 2026-05-25 | Fase 5 redesenhada: ERP focado em 5 módulos (Cliente+Projeto+Orç+RT+Portal), não ERP completo | Replicar tudo do Braxio = 18 meses pra empatar. Focar onde wedge se amplifica. |
| 2026-05-25 | Reserva Técnica é feature-âncora da Fase 5 | É o gancho emocional que faz arquiteto aceitar mensalidade. Nenhum concorrente faz fluido. |
| 2026-05-25 | Modelo de preço vira HÍBRIDO: avulso continua, mensalidade entra só pra módulo ERP | Revoga decisão "não vender mensalidade". Avulso = porta de entrada (wedge), mensalidade = retenção (Fase 5). |
| 2026-05-25 | Permissões por cargo (5 cargos × 4 níveis) são DAY 1 da Fase 5 | Lição do Braxio: refactor de auth depois custa caro. Escritório 5+ pessoas exige no dia 1. |
| 2026-05-25 | NÃO replicar: NFSe completa, OFX, DRE escritório, agenda, biblioteca produtos | Commodity bem feita pelos parceiros (Conta Azul, Pluggy). Foco nosso é técnico, não admin. |

---

## 🎯 Próximos passos (curto prazo)

### ✅ Já feito (2026-04-26)
- Blog `/blog/` no ar com 12 posts agendados (3 meses de conteúdo)
- 7 posts Instagram agendados via pg_cron, dia1 já publicado
- Memorial Descritivo com PDF + DOCX baixáveis
- Modal de contato com modo "ticket" pra projetos
- Aba "Mensagens" no admin com filtros e ações

### 🔥 Top 5 melhorias do site (priorizadas em 26/04)
Identificadas em sessão de planejamento. Ordem de impacto:

1. **Indique-e-ganhe** ⭐ — viral loop de baixo custo
   - Link único no dashboard de cada usuário
   - Indicado: 1º projeto extra grátis
   - Indicador: R$ 50 cashback quando indicado pagar 1º projeto
   - Justificativa: 10x mais barato que Google Ads, 5x mais conversão

2. **Onboarding guiado** ✅ EM ANDAMENTO (escolhido pra fazer 26/04)
   - Tour overlay no primeiro acesso ao dashboard
   - Estado salvo em `user_metadata.onboarded`
   - Reduz dropout do primeiro uso (estimado 30-50% atualmente)

3. **Notificações por email pro usuário**
   - "Sua planilha está pronta" quando processamento termina
   - "Você ganhou R$ X de cashback"
   - "Faz 30 dias sem usar — vamos lá?"
   - Mantém engajamento sem custo recorrente

4. **WhatsApp como canal de contato**
   - Botão verde flutuante em todas as páginas
   - Mensagem pré-preenchida com contexto da página
   - Brasileiro responde WhatsApp 10x mais rápido que email

5. **Página de cases/depoimento**
   - `/cases.html` com card da Daniela (após call de testemunho)
   - Quote, foto, métrica concreta
   - Sem prova social, todo o resto rende metade

### 🛠️ Quick wins paralelos (1-2h cada)
- Templates email Supabase em PT-BR (hoje sai em inglês)
- Linkagem interna entre posts do blog (SEO booster)
- Calculadora de preço interativa na landing
- Página `/precos.html` dedicada (hoje misturado na landing)
- Avatar default colorido (inicial em vez de cinza genérico)

### ⚠️ NÃO fazer agora
- Mobile app / PWA — exagero pra 3 usuários
- Programa de afiliados — só faz sentido com 100+ usuários
- Landing por disciplina — overkill antes de SEO básico validar
- Pagar Google Ads — antes do PMF não vale
- Reescrever em React — funciona até fase 3
- Redesign visual completo — está OK, foco em features

### 🔁 Pendências infra (recorrentes)
- Renovar token Meta antes de 13/06/2026 (60 dias do gerado em 14/04)
- Setup email do domínio (Cloudflare Routing — pendente decisão Pedro)
- Plugar Gemini 2.5 Flash Image (Fase 2 do Instagram)

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
