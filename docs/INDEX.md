# 📚 Mapa de contexto — AI.arq

> Índice de tudo o que tá documentado. Toda sessão Claude que importa fica registrada aqui. Se procurar uma decisão, começa por este arquivo.
>
> Última atualização: 2026-05-12

---

## 🎯 Docs canônicos (leia primeiro)

| Arquivo | O que tem |
|---|---|
| [`../CLAUDE.md`](../CLAUDE.md) | **Quick-start pra qualquer sessão Claude.** Quem é Pedro, regras duras, arquitetura, IDs/endpoints, estrutura de pastas, fluxo de trabalho. |
| [`../ROADMAP.md`](../ROADMAP.md) | **Visão de longo prazo (3-5 anos).** 7 fases, princípios fundamentais, posicionamento competitivo, decisões já tomadas. |
| [`../.claude/GRADE_INSTAGRAM.md`](../.claude/GRADE_INSTAGRAM.md) | **Grade editorial fixa do Instagram.** Rubrica por dia, horários travados, regras de voz, convenção slot_key. **LER ANTES de criar qualquer post.** |
| [`../../MAPA.md`](../../MAPA.md) | **Mapa das pastas no Desktop.** Onde achar projeto, working dir, archive. |

---

## 📜 Histórico de sessões

Cada sessão grande vira um arquivo aqui. Em vez de carregar 50+ MB de transcript, o arquivo resume decisões + commits + pendências.

| Quando | Arquivo | Resumo |
|---|---|---|
| 14/04/2026 | [`HISTORICO_AGENTE_INSTAGRAM.md`](HISTORICO_AGENTE_INSTAGRAM.md) | Criação do agente IG: backend (4 módulos), Meta Graph API v21, automação de posts |
| 2026-04 inicial | [`HISTORICO_SESSAO_COMPLETA.md`](HISTORICO_SESSAO_COMPLETA.md) | Fase 1 do produto: leitura CAD, geração planilha, configuração dominio/Render/Supabase, primeira UI |
| **10-12/05/2026** | [`HISTORICO_SESSAO_2026-05-10_a_12.md`](HISTORICO_SESSAO_2026-05-10_a_12.md) | **Sessão pesada 3 dias:** SINAPI rerank, 8 furos de segurança, página /precos, audit site, reorg pastas, grade IG, análise 114 agents → 3 produtos novos |

---

## 🔧 Materiais técnicos de referência

Arquivos externos guardados localmente em `arq/_archive/` (não vão pro git por tamanho/licença):

### PDFs (em `projeto_arq/docs/`, gitignored)
- `Manual de Elaboração de Orçamentos - Obras.pdf` — manual público do TCU
- `guia_planilha_orcamentaria_obra_privada.pdf` — referência de estrutura

### 114 agents ASV/Bravy (em `arq/_archive/templates_referencia/bravy/`)
- 57 agents Arquitetura + 57 agents Engenharia
- Atlas da jornada de 14 etapas do arquiteto BR
- **Catálogo mapeando cada um pra fase do nosso roadmap:** `arq/_archive/templates_referencia/bravy/CATALOGO.md`
- Já usado de inspiração em: `cronograma-gerador.md` (baseado no Eng 32)
- Próximos usos previstos: Eng 31 (BDI Fase 3c), Arq 42 + 08 + 56 (Memorial Fase 3a), Arq 26 (Caderno Fase 3b)
- **NÃO instalar todos em `.claude/agents/`** — extrair pontualmente quando começar cada fase

### 4 planilhas Sienge (em `arq/_archive/templates_referencia/sienge/`)
- **`materiais-sienge-planilha-orcamento-de-obra-3.xlsx`** (2019) — estrutura padrão antiga, 18 etapas + analítica SINAPI
- **`materiais-sienge-planilha-de-orcamento-de-obra-4-1.xlsx`** (2024) — versão modernizada (abas sin/cpe/ana/rel/das/com)
- **`Planilha-de-Orcamento-de-Obras-5.0-2-3.xlsx`** (2025) — **SINAPI 2025 com 8.868 composições** (validar contra nosso banco de 10.284)
- **`materiais-sienge-planilha-calculo-de-bdi-2-0.xlsx`** — **template completo de BDI** (Adm Central + Adm Local + Indiretas + Financeira + Lucro + Tributos). Base pro futuro agent `bdi-helper` (Fase 3).

### Prevision — 50 prompts ChatGPT (em `arq/_archive/templates_referencia/prevision/`)
- Qualidade média (templates pra usuário colar no ChatGPT, não agents)
- Valor real: **catálogo de 50 temas** que mercado BR procura. Identificados 8 não cobertos pelos Bravy:
  fast-tracking, Lean Construction, Last Planner System, planejamento reverso, férias coletivas BR,
  concretagens, ciclos repetitivos, plano de transição entre fases. Candidatos pra Fase 2+ do roadmap.

---

## 🤖 Agents Claude Code do AI.arq

Em `.claude/agents/` no repo. Cada um é especialista em uma área:

| Agent | O que faz |
|---|---|
| `copywriter-br` | Revisa copy do site pra soar natural BR |
| `seo-auditor-br` | Audita post de blog antes de publicar |
| `security-reviewer` | Revisão de segurança (RLS, secrets, LGPD) |
| `marketing-strategist` | Análise de métricas e ações de growth |
| `community-listener-br` | Escuta comunidade arquitetos BR |
| `competitor-watcher` | Monitora concorrência |
| `market-analyst-br` | Analisa mercado BR |
| `product-strategist` | Estratégia de produto e roadmap |
| `trend-scout-ai` | Tendências IA aplicadas |
| **`cronograma-gerador`** ⭐ | **Gera cronograma físico-financeiro a partir da planilha do AI.arq (Fase 2 do roadmap, criado em 12/05/2026)** |

---

## 📋 Decisões importantes registradas

Pra não perder regra que já foi discutida:

### Regras duras (NUNCA violar)

1. 🚨 **NUNCA estimar como "confirmado"** — só BRANCO o que veio do CAD, resto LARANJA
2. 🚨 **Isolamento absoluto de projetos** — zero contaminação, zero benchmark hardcoded
3. 🚨 **Calibração por densidade/ratio** — orçamentos antigos alimentam ratios pra ALERTAR, nunca copiam valor absoluto
4. 🚨 **Taxonomia hierárquica** — itens em árvore (folha → família → grupo → capítulo)
5. 🚨 **NÃO precificar, NÃO substituir profissional** — AI.arq gera QUANTITATIVO, não orçamento
6. 🚨 **LGPD: usuário = controlador, AI.arq = operador**

### Decisões de marca / posicionamento

- Tagline correta: **"Quantitativo com IA"** (NÃO "Orçamento com IA")
- Sem rosto / voz do Pedro no marketing — usar mascote AIrnaldo, testemunho Daniela, ou narrativa 3ª pessoa
- AIrnaldo: mascote funcional (fala BDI/SINAPI), SEM biografia inventada
- IG: rubrica fixa por dia, horários travados, voz do cliente (não voz interna)
- Cashback total max: R$ 45/projeto (R$ 20 inline + R$ 20 planilha + R$ 5 cotação)

### Decisões estratégicas (sessão 12/05)

- **Fase 2 do roadmap mudou:** era Comparativo de fornecedores, agora vira **Cronograma físico-financeiro** (pega tração mais rápido, não depende de fornecedor externo)
- **Os 114 agents ASV/Bravy** servem como atlas da jornada do arquiteto — nossa expansão é adicionar etapas adjacentes ao quantitativo, não competir frontalmente
- 3 produtos previstos próximos 12 meses: Cronograma (Fase 2) → Memorial descritivo (Fase 3a) → Caderno acabamentos (Fase 3b)

---

## 🚨 Como NÃO usar este índice

- ❌ Não tentar substituir leitura dos docs. Este é só catálogo.
- ❌ Não copiar trechos sem verificar a fonte (docs canônicos têm a verdade)
- ❌ Não atualizar histórico de sessão antiga retroativamente — cria sessão nova ou edita CLAUDE.md
- ❌ Não comitar arquivos sensíveis (PII de cliente, screenshots de WhatsApp) — vai pra `_local/` (gitignored)

---

## 🔄 Como manter este índice atualizado

**Quando criar:** depois de cada sessão pesada (3+ dias de trabalho, decisão estratégica grande, ou commit-chave).

**Como criar:**
1. Resumo da sessão em `docs/HISTORICO_SESSAO_<datas>.md`
2. Linha nova na tabela "Histórico de sessões" deste índice
3. Se mudou regra dura ou decisão estratégica, atualizar a seção correspondente aqui

**Quando NÃO criar:** sessões pequenas (1-2 commits, sem decisão nova) — só commitar normal.
