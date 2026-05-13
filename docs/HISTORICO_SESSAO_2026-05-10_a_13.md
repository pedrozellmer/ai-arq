# 📜 Histórico Sessão — 10 a 12 maio 2026

> Sessão pesada de 3 dias com: melhorias profundas no motor SINAPI, fechamento de 8 furos de segurança, criação de página de preços, auditoria do site, reorganização de pastas, grade editorial Instagram + 7 imagens da semana w20, e análise estratégica dos 114 agentes ASV/Bravy com proposta de 3 novos produtos.
>
> Linha de base: AI.arq tem 8 usuários (3 ativos: Rafael, Sidnei, Weslei + Daniela DTZ), backend voltou pra deploy após 7 dias de Dockerfile quebrado, motor com qualidade alta (100% sucesso em maio vs 27% em abril).

---

## 🗓️ 10 de maio (sábado) — SINAPI matcher + segurança + organização

### Motor SINAPI — qualidade alta finalmente

Iteração depois do Pedro perguntar "pq não 100%?". 3 melhorias progressivas:

**Commit `aa58abc`** — pré-tradução de vocabulário + bitola contextual:
- Dicionário `_PRE_TRANSLATE` traduz "tubulação" → "tubo pvc soldável" antes da busca SINAPI
- `_extract_bitola` só anexa dimensão se contexto é tubo/cabo/eletroduto (escada 30cm não vira "30MM")
- `_GENERIC_TERMS` filtra "Ponto", "Sistema" como primeira palavra
- Sinônimos PT-BR expandidos pra 50+ termos

**Commit `e6dd3cc`** — rerank por spec técnica + penalidade demolição:
- `_rerank_by_specs` boost +0.5 quando descrição SINAPI casa amperagem/bitola
- Regex flexível aceita "10 A" com espaço e "1,5 MM²" com vírgula
- Penalidade -0.5 pra códigos REMOÇÃO/DEMOLIÇÃO quando query é obra nova
- Pool RPC ampliado limit*3 → limit*8

**Commit `0f8a951`** — multi-spec e ranges:
- "Disjuntor 10A/16A/20A" gera 3 targets (não só o primeiro)
- "Cabo 4-6mm²" gera target pra 4 e 6 separadamente

**Resultado validado em Weslei v8 (41/41 matches):**
- Disjuntor 10A → 93653 DIN 10A (antes: 200A)
- Cabo 2,5mm² → 91927 (antes: 1,5mm²)
- Eletroduto 25mm → 91835 DN 25 MM (antes: 20 MM)
- Forro gesso → 99054 ACABAMENTO (antes: 97641 REMOÇÃO)

### Deploy Render destravado depois de 7 dias

Commit `8125c98` (04/05) tinha colocado `libredwg-tools` no Dockerfile dentro do mesmo `RUN` das deps Qt. Apt-get falhava, build inteiro morria, deploy revertia.

**Commit `5c73a45`** — separou `libredwg-tools` num RUN próprio com `|| echo` final. Build continua mesmo se libredwg falhar (Python já usa `shutil.which()` como guard).

Backend voltou. As 8 melhorias da semana entraram em produção: dedup cross-prancha, prompt hidráulico, dwg fix, SINAPI matcher, pré-tradução, rerank, multi-spec, Dockerfile fix.

### Auditoria de segurança — 8 furos fechados

Triggered pelo Pedro pedindo "reunião de board" pra ver estado geral. Audit revelou:

**P0 (autorização / cashback):**
1. `POST /api/process` aceitava `user_id` no Form sem validar JWT — atacante criava projeto em nome de outro usuário e consumia créditos dele
2. `POST /api/projects/{job_id}/quotes/upload` — atacante ganhava R$ 5 cashback em nome alheio
3. `POST /api/projects/{job_id}/revised-sheet/upload` — atacante ganhava R$ 20 cashback alheio
4. `GET /api/user/{user_id}/cashback-all` — qualquer um listava saldo financeiro de qualquer usuário

**P1 (debug endpoints abertos):**
5. `/api/debug/supa-log` expunha queries internas + payloads
6. `/api/debug/dwg` revelava layout do filesystem via `find /`
7. `/api/debug/oda-log/{job_id}` — qualquer um com job_id de 8 chars puxava log

**P2 (path traversal):**
8. 6 endpoints faziam `os.path.join(work_dir, upload.filename)` sem sanitizar — cliente malicioso mandava `../../etc/cron.d/x`

**Commit `26165d4`** — fechou os 8. Novo helper `_safe_local_filename()` (10/10 testes anti-traversal). `_require_admin` + `_require_project_owner` aplicados.

**Commit `4e09f5f`** — frontend ajustado pra mandar `Authorization: Bearer` nos 3 endpoints agora protegidos (dashboard cashback-all, projeto quotes-upload, projeto revised-sheet-upload).

Validado em produção com curl: 4/4 testes passaram (401 sem Bearer, 200 no root).

### Página `/precos.html` — Commit `1137d3d`

Pedro queria calculadora de preço pra parar de ouvir "quanto custa" no chat. Página dedicada com:
- Slider interativo 1-50 pranchas → preço real-time
- Mostra faixa (Pequeno/Médio/Grande), R$/prancha, % economia
- Tabela 4 tiers (Grátis + 3 pagos)
- 8 features incluídas
- FAQ específico de preço (8 perguntas)
- Design coerente com index.html

Nav e sitemap atualizados. Footer ganhou link "Preços".

### Auditoria site — 5 inconsistências fechadas

Pedro pediu auditoria pra "não ter desencontro de informação":

1. **Cashback** — index dizia R$ 20, precos dizia R$ 25, real é R$ 45 max. Padronizado em todos lugares.
2. **"Memória Técnica"** — nome velho da aba, foi renomeada pra "Referências SINAPI-TCPO" mas site não atualizou. 6 lugares ajustados.
3. **Tipologias** — index listava 4, faq listava 5. Adicionado "educacional" no index.
4. **Zero link Instagram** em todo o site. Agora ícone IG no footer de 7 HTMLs.
5. **Cadastro sem atribuição de fonte** — sem "onde nos conheceu". Campo novo + migration `referral_source` no banco.

Commit `b1a5b07`.

### Reorganização de pastas — Commit `d36ee37`

Estrutura caótica. Antes:
- `Desktop/arq/`: 9 itens soltos no root
- `Desktop/arq/arq/`: 267 arquivos + 28 subpastas
- `Desktop/arq/projeto_arq/`: 40+ arquivos no root (HISTORICOs, TESTE_*.xlsx, frontend Next.js abandonado, logos)

Depois:
- `Desktop/arq/`: 3 pastas (arq, projeto_arq, _archive) + MAPA.md
- `arq/`: 5 pastas (_cad_teste, projetos_clientes, _marketing, _scripts, _archive)
- `projeto_arq/`: HTMLs no root + docs/ + assets/logos/ + _local/ (gitignored)

### Grade editorial Instagram + 7 imagens semana w20

Bug detectado pelo Pedro: AIrnaldo apresentado na quinta 07/05 com legenda "vai postar toda quarta". Erro de marca.

**Criado `.claude/GRADE_INSTAGRAM.md`** — grade fixa por dia (Bastidor seg, Erro caro ter, Quarta do AIrnaldo, Pergunta qui, Real da sexta, Comparativo sáb, Convite dom). Horários fixos. Convenção slot_key `feed_<dia>_w<n>`.

**Script gerador `arq/_scripts/gen_semana_w20.py`** com 7 funções Pillow (1080x1080 PNG, Montserrat, paleta indigo/cyan). Saída em `instagram_assets/semana_w20/`. Commit `f1ea96d`.

**Inserção no banco** — 7 posts agendados em `instagram_scheduled_posts`. Bug detectado e corrigido: eu confundi 12/05 como segunda (era terça). UPDATE -1 dia em todos.

---

## 🗓️ 12 de maio (terça) — bizarrice no IG + análise dos 114 agents

### Bizarrice do Bastidor — Pedro chamou atenção

Post de segunda 11/05 saiu com:
- "100% projetos sem erro em maio (vs 27% em abril)"
- "8 furos de segurança fechados"
- "41/41 matches SINAPI"
- "R$ 45 cashback (era R$ 20)"

Pedro disse: "esta semana o motor fechou 8 furos de segurança. absurdo isso". **Auto-sabotagem clássica de SaaS** — cliente lê "tinha falha". Pedro deletou o post.

**Nova regra na grade IG (commit `2c728c4`):** "voz do cliente, não voz interna". Banidas as palavras `motor`, `match`, `deploy`, `rerank`, `RLS`, `X furos de segurança fechados`, `X% sem erro`. Validação: "arquiteto de 12 anos ia pensar 'que legal' ou 'que estranho'?".

**Bastidor de segunda passa a ser bastidor da OBRA do cliente**, não do código. Exemplos: "3 tipos de projeto que rodaram essa semana", "1 pergunta que mais chegou no chat".

**3 posts pendentes da w20 reescritos** no banco: PDF vs DWG (tirado "a IA tem que ler imagem"), Comparativo (tirado "REF. PRANCHA"), Convite (abertura nova com cenário real).

### Análise dos 114 agentes ASV Digital / Bravy

Pedro mandou 2 zips: `57 Agents Arquitetura.zip` + `57 Agents Engenharia.zip`. Análise:

**O que é:** 114 subagents Claude Code vendidos como produto pra escritórios BR. Cada agent .md tem prompt detalhado com NBRs, workflows, código Python, catálogo de fabricantes reais.

**Qualidade:** alta. Cita Acórdão TCU 2622/2013, NBR 13532, RDC ANVISA, AsBEA, IT-25. Trabalho de gente que viveu canteiro.

**Concorrente?** Não direto. AI.arq processa binário (DWG → planilha). Eles geram texto a partir de briefing. Camadas opostas.

**Reframe estratégico:** os 114 agents revelam a JORNADA completa de 14 etapas do arquiteto BR. AI.arq cobre 1 etapa (quantitativo). Cada nova fase do roadmap não inventa — adiciona uma etapa adjacente reusando output anterior.

### 3 produtos novos propostos (priorizados)

**Produto 1 — Cronograma físico-financeiro automático (4-6 semanas)**
- Cliente recebe quantitativo + 1 clique gera Gantt + .mpp + curva S
- Reusa dados que já temos. Não precifica (só distribui esforço).
- Preço: R$ 50 extra ou bundle no plano Médio+
- **Aprovado pelo Pedro nesta sessão. Agente criado: `.claude/agents/cronograma-gerador.md`.**

**Produto 2 — Memorial descritivo + RRT (8-10 semanas)**
- Cliente recebe quantitativo + AI.arq escreve memorial pra prefeitura
- Output PDF formato CAU + RRT preenchido + checklist documentos
- Preço: R$ 80 extra ou bundle

**Produto 3 — Caderno de acabamentos com fabricantes BR (12-16 semanas)**
- Cliente recebe quantitativo + 1 clique escolhe fabricante por item
- Output XLSX por ambiente com Portobello/Eliane/Deca/etc + preço referência + link ficha técnica
- Monetização: R$ 100 extra OU comissão de afiliado dos fabricantes (B2B)

### Decisão de board

**Cronograma vai pra Fase 2 oficial do roadmap**, antes do Comparativo (que era a Fase 2 original). Razão: Comparativo depende de cotação externa de fornecedor; Cronograma só precisa do que já temos.

---

### Final do dia 12 — descobertas estratégicas

**🏗️ Projeto Manus antigo localizado: 60% da Fase 5 já existe**

Pedro lembrou do projeto `cronograma-arquitetura-extracted` no `_archive`. Análise rápida revelou:

- Stack: React + tRPC + Drizzle (MySQL)
- Módulos prontos: Projetos, Tasks/Timeline (com dias úteis), CRM Notes, Financeiro (entrada %/fixa + parcelas auto + edição), Galeria (PDF/DWG/plantas), AI Chat Box, Dashboards (CashFlow/CRM/Financial/General), Mapa
- Cobre Fase 5 do roadmap (ERP do escritório) em ~60%
- **Decisão:** NÃO migrar agora (8 usuários, prematuro). Quando virar Fase 5 (>50 usuários), aproveitar código existente. Encurta de 24-36 meses pra 12-18.
- ROADMAP atualizado com nota dessa descoberta na Fase 5

**📊 5 planilhas de referência adicionadas (movidas pra `arq/_archive/templates_referencia/`)**

| Planilha | Valor | Próxima ação |
|---|---|---|
| Sienge Orçamento v3 (2019) | Estrutura padrão BR antiga | Referência |
| Sienge Orçamento v4 (2024) | Layout modernizado | Referência |
| Sienge Orçamento v5.0 (2025) | SINAPI 2025 com 8.868 composições | TODO: validar contra nosso banco de 10.284 |
| **Sienge BDI** | Template completo (Adm Central, Adm Local, Indiretas, Financeira, Lucro, Tributos) com fórmulas | **Base do agent `bdi-helper` da Fase 3c** |
| Prevision (50 prompts) | Qualidade média mas catálogo de temas BR | 8 temas únicos viraram "Features candidatas pós-Fase 4" |

**📋 ROADMAP reestruturado**

- **Fase 3c — BDI Helper** adicionada (era só Memorial + Caderno). Reusa template Sienge BDI como base. Respeita regra dura "não precificar" — sugere BDI mas orçamentista decide.
- **Fase 5 — código Manus 60% pronto** anotado. Estimativa cai de 24-36 pra 12-18 meses.
- **Seção "Features candidatas (radar pós-Fase 4)"** com 11 features mapeadas das 5 planilhas:
  - Adjacentes ao Cronograma: Fast-tracking, Lean+Last Planner, Planejamento reverso, Concretagens, Ciclos repetitivos
  - Operacional Fase 5: Cenários de atraso, Transição entre fases, Férias coletivas BR
  - Validação técnica: Conformidade NBR 9050/15575, Restrições ambientais

**🕵️ Análise externa — orbit-o-r.com**

Pedro mostrou landing page vendendo "Ultimate Guide AI for Architects" + "ARQYN APP" por £12.50.

Veredito: scam ou info-product de baixíssimo valor.
- "ARQYN APP" não existe nos rankings de AI tools pra arquitetura (ferramentas reais: ArchSynth, ArchiVinci, mbue, Rayon, MyArchitectAI)
- orbit-o-r.com sem reviews, sem CNPJ, sem refund policy, preço em £
- Conteúdo prometido (Midjourney pra arquitetos) tem TUDO de graça em Archgyan, Educasium, Aituts

**Insight estratégico:** existe mercado pagando £12.50 por PDF de prompt. Confirma que arquiteto BR paga por IA aplicada. Nosso 1º projeto grátis entrega valor maior que esses scams — só precisa entregar.

**🎨 Cronograma Weslei (POC do agent `cronograma-gerador`)**

Tentei rodar o agent no projeto real do Weslei pra demo. Geramos:
- Gantt PNG (7 fases mapeadas das 8 disciplinas)
- Curva S PNG (25/50/75/100% com datas)
- Cronograma XLSX (com bugs visuais — duplicação Jul/26 e "0%" azul poluindo)
- Memorial MD

Bugs identificados:
- Calendário usando +30 dias em vez de mês civil (jul/26 aparece 2x)
- "0%" em células vazias deveria ficar em branco
- Texto "produtividade média BR" inferiorizante — virou "produtividade típica de mercado"

**Pivot do Pedro:** em vez de PNG/PPT separado, melhor virar **aba dentro da planilha gerada** com fórmulas Excel — cliente muda data início, tudo recalcula. Script `adicionar_aba_cronograma_weslei.py` iniciado mas não finalizado nessa sessão (continua próxima).

---

### 13/05 — Atlas completo + visão ERP

Pedro pediu pra catalogar TUDO que recebemos (Bravy 114 + Prevision 50 + Amanda 10X 20) num roadmap unificado pensando ERP completo. Concorrência mapeada:

- **Flowup** (1.000+ escritórios BR, parceiro ASBEA/CREA): ERP gestão+financeiro, sem IA técnica, não lê CAD
- **Vobi** (Y Combinator, R$5B obras/ano): foco construtora, 3 agents IA (Financeiro/Compras/Diário) mas IA é assistência, não leitura de CAD
- **Sienge**: 12 módulos, caro, foco incorporadora
- **Projetools, GestãoClick**: pequenos
- **Amanda 10X**: curso, não SaaS — não é concorrente, é gerador de lead aquecido

**Vantagem AI.arq defensável:** leitura de binário (DWG/PDF) + IA específica de arquitetura. Flowup/Vobi não vão entrar nessa briga sem refazer stack.

**Criado `docs/ATLAS_FEATURES.md`** — documento canônico com ~140 features mapeadas de 3 fontes + roadmap próprio, organizadas em 10 fases. Posicionamento competitivo. Sequenciamento sugerido.

**ROADMAP reestruturado pra 10 fases:**
- Fase 1: Quantitativo (HOJE)
- Fase 2: Cronograma (CONSTRUINDO)
- Fase 3: Documentação técnica (a, b, c, d, e — Memorial, Caderno, BDI, **Orçamento por Ambiente** quick win, outros)
- Fase 4: Comparativo fornecedor
- Fase 5: ERP escritório (60% pronto via Manus)
- Fase 6: **Pré-projeto + viabilidade urbana** (NOVA — captura no funil cedo, inspirada Amanda 10X)
- Fase 7: CAD 2D → 3D + render
- Fase 8: **Conformidade NBR** (NOVA — diferencial competitivo, nenhum BR faz)
- Fase 9: Generativo (texto → projeto)
- Fase 10: SO escritório completo + pós-obra

**5 fontes externas catalogadas e organizadas em `arq/_archive/templates_referencia/`:**
- bravy/ (114 agents + CATALOGO.md)
- sienge/ (4 planilhas — orçamento, BDI, SINAPI 2025)
- prevision/ (50 prompts ChatGPT)
- arquiteto10x/ (apostila 51 páginas, 20 skills)

---

## 📌 Pendências carregadas pra próxima sessão

- [ ] Mandar planilha v8 do Weslei via WhatsApp (`arq/projetos_clientes/weslei_ghisleri/quantitativo_weslei_v8_RERANK.xlsx`)
- [ ] Pedir testemunho da Daniela (DTZ) em vídeo (1 min)
- [ ] **Cronograma como aba na planilha gerada** — terminar `adicionar_aba_cronograma_weslei.py` (fórmulas Excel, recalcula com mudança da data início)
- [ ] Backend endpoint `/api/cronograma/generate` + integração com agente
- [ ] **Atualizar `cronograma-gerador.md`** com as 16 etapas oficiais Sienge (em vez das 18 que eu chutei): SERVIÇOS INICIAIS → MOVIMENTAÇÃO DE TERRA → FUNDAÇÃO → ESTRUTURA CA → PAREDE → ESQUADRIAS → COBERTURA → IMPERMEABILIZAÇÃO → REVESTIMENTOS → PREVENTIVO INCÊNDIO → PROJETO ELÉTRICO → PROJETO HIDROSSANITÁRIO → LOUÇAS E METAIS → SERVIÇOS COMPLEMENTARES → PINTURAS → RETIRADA DE ENTULHO
- [ ] **Validar nosso SINAPI** contra os 8.868 da planilha Sienge 2025
- [ ] Gerar 7 imagens da semana w21 (18-24/05) seguindo grade nova (Bastidor da OBRA, não do código)
- [ ] Avaliar se rola parceria com Bravy / ASV Digital (cross-sell mútuo)
- [ ] Pendência futura: cancelados (19 stories status=canceled poluindo histórico) — pedir aprovação Pedro pra DELETE em massa

---

## 💾 Commits desta sessão (em ordem)

```
aa58abc  Sinapi matcher: pré-tradução vocabulário + bitola contextual
e6dd3cc  Sinapi matcher: rerank por spec técnica + penalidade demolição
0f8a951  Sinapi matcher: suporta multi-spec e ranges
5c73a45  Dockerfile: libredwg-tools opcional (destrava deploy)
26165d4  Segurança: fecha 8 furos (auth, RLS bypass, path traversal)
4e09f5f  Frontend: Authorization Bearer em endpoints protegidos
1137d3d  Página /precos.html + grade editorial IG
b1a5b07  Audit site: 5 inconsistências fechadas + cadastro c/ origem + IG link
d36ee37  Reorganização: pastas limpas (docs/, _local/, assets/logos/)
f1ea96d  IG: imagens da semana 20 seguindo grade
2c728c4  Grade IG: regra anti-bizarrice (voz cliente, não voz interna)
```
