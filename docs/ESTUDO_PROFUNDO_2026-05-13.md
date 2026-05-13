# 🔬 Estudo Profundo — 13 maio 2026

> Consolida pesquisa profunda na web + leitura aprofundada de 8+ skills/agents (Bravy Eng 33/34/35 + Amanda 10X módulos 2-6 + Prevision sobre curva S). Cobre macroeconomia, concorrência, normas técnicas e backlog priorizado.
>
> **Objetivo:** transformar 190+ items catalogados em decisões concretas pra AI.arq nos próximos 6 meses.

---

## 1. 🌍 Macroeconomia da construção BR 2026

### Números-chave (CBIC, Sienge, Exame, TOTVS)

- **PIB construção civil:** projeção +3.5% em 2026, melhor que 2025
- **Vetores de crescimento:**
  - Queda de juros (Selic em trajetória de baixa)
  - Orçamento recorde FGTS pra habitação
  - Minha Casa Minha Vida com novas contratações
  - Investimentos em infraestrutura (+2% setor)
- **Vetores de dor (oportunidade pro AI.arq):**
  - **Escassez de mão de obra qualificada** ← IA é alternativa
  - Carga tributária alta
  - Custo MO + juros altos pra obra privada
  - Complexidade normativa (NRs, NBRs, leis municipais)

### Tendências tecnológicas confirmadas (todas as fontes citam)

1. **BIM deixou de ser promessa → padrão** em projetos médio/grande
2. **IA otimiza processos** especialmente onde escassez MO dói (orçamento, planejamento, compras)
3. **Industrialização** (pré-fabricados, modular) acelerada
4. **Sustentabilidade/ESG** virou critério, não diferencial
5. **Adaptabilidade** (LGPD, compliance) caro de gerenciar manual

**Implicação AI.arq:** estamos no setor certo, no momento certo. Setor crescendo + dor real onde IA serve.

---

## 2. 🏢 Concorrência aprofundada

### Mapa de jogadores BR (2026)

| Player | Nicho | Ferramenta forte | Gap que AI.arq explora |
|---|---|---|---|
| **Sienge** | Construtora grande | ERP + módulos integráveis (12) | Caro, complexo, não lê CAD, foco incorporadora |
| **Vobi** | Obras médio/grande | Gestão completa + IA (Financeiro/Compras/Diário) — backed Y Combinator | Foco construtora, IA é assistência (não leitura) |
| **Flowup** | Escritório arq | ERP projeto+financeiro+equipe — 1.000+ clientes BR | Não lê CAD, sem IA técnica |
| **Mobuss** | Construtora médio | Gestão obra mobile-first | Sem IA, sem leitura CAD |
| **TOTVS Construção** | ERP enterprise | Integração contábil | Caro, sem IA específica |
| **Projetools** | Escritório arq | Vertical, simples | Pequeno, sem IA |

### Mapa de jogadores generativos (global, possíveis entrantes)

| Player | País | Preço | Foco | Risco pra AI.arq |
|---|---|---|---|---|
| **Maket.ai** | Canadá | US$29/mo | Geração de planta 2D | Médio (foco residencial) |
| **Finch3D** | EU | US$50/mo | Massing + Revit plugin | Baixo (precisa Revit) |
| **Hypar** | EUA | Free tier | Computational design open | Baixo (técnico demais) |
| **Autodesk Forma** | Global | US$250-400+/mo | Site planning | Baixo (caro) |
| **TestFit** | EUA | US$250+/mo | Site optimization | Baixo (foco USA) |
| **Snaptrude** | Global | Free freemium | BIM colaborativo | Médio |

**Insight crítico:** TODOS esses generativos focam **planta + 3D**. Nenhum cobre **quantitativo BR com SINAPI**. Janela ainda aberta — mas é janela, não eternidade. Tempo de chegar pra valer é 12-24 meses.

### Vantagem defensável do AI.arq

```
              Lê CAD?    SINAPI BR?    18 disciplinas BR?    Preço?
Sienge        ❌         ✅ (manual)    ✅                    R$ 3k+/mês
Vobi          ❌         🟡             🟡                    R$ 800+/mês
Flowup        ❌         ❌             ❌                    R$ 600+/mês
Maket         ❌         ❌             ❌                    US$ 29/mês
Finch         ❌         ❌             ❌                    US$ 50/mês
AI.arq HOJE   ✅         ✅             ✅                    R$ 97/projeto
```

**3 trincheiras defensáveis:**
1. **Leitura de CAD nativo** (DWG/PDF/DXF) — moat técnico real
2. **SINAPI integrado** (10K composições no banco)
3. **Pricing por projeto** vs assinatura — barreira baixa pra entrar

---

## 3. 📐 Normas técnicas — gap gigante de mercado

Pesquisa web revelou que **NÃO existe verificador automático IA pra NBR 9050 e NBR 15575 em 2026**. Tem só ferramentas tradicionais (não-IA) e softwares de cálculo isolado.

### Demanda real

- **NBR 9050** (acessibilidade) — obrigatória em uso público/semi-público
- **NBR 15575** (desempenho) — habitacional obrigatória desde 2013
- **NBR 9077** (saídas emergência) — todo projeto
- **NBR 16280** (reforma) — qualquer reforma estrutural
- **Lei 14.133** (orçamento público) — exige SINAPI + BDI evidenciado

**Toda obra precisa atender.** Toda. E o arquiteto/orçamentista hoje faz **manual**, lê o PDF da norma e checa item por item. Custa tempo + erros.

### Oportunidade AI.arq

Fase 8 do roadmap (Conformidade NBR) é **diferencial enorme**. Pesquisa profissional sobre **"verificador automático NBR"** em 2026 retorna 0 produtos comerciais brasileiros. Janela aberta.

**Estimativa de valor:** R$ 100-200 por auditoria (cliente economiza 4-8h de revisão manual).

---

## 4. 🔍 Lições profundas dos materiais

### Eng 33 — Curva S avançada

Lições além do que implementei na Fase 2:

- **Curva S sigmoidal** (logística): `P(t) = 100 / (1 + e^(-k(t/T - 0.5)))` com k=8-12
- **EVM completo:** PV (planned), EV (earned), AC (actual), CV, SV, CPI, SPI
- **Projeção término (EAC):** `BAC/CPI` ou `AC + (BAC-EV)/CPI`
- **Marco legal medição:** Lei 14.133 Art 117 (obrigatória), Art 121 (fiscalização), Art 137 (retenção)
- **Acórdãos TCU:** 2622/2013 (BDI), 1466/2017 (medição+glosa), 2369/2011 (projeção)

**Gap na nossa implementação:**
- Curva S atual é **linear** (peso igual por disciplina). Sigmoidal seria mais realista.
- Não calculamos EVM (depende de dado real, que ainda não temos)
- Não cita marco legal — vale citar Acórdão 2622 na ressalva

### Eng 34 — EAP/WBS

Lições:
- **Entregáveis, não tarefas** — "Parede pintada" (entregável), não "Pintar parede" (atividade)
- **Work packages 8-80h** — granularidade certa
- **Regra dos 100%** — soma das partes = todo, sem sobreposição
- **Dicionário WBS** — cada pacote tem descrição + critério aceitação + recursos
- **Codificação hierárquica:** 1.1.2.3 (capítulo.fase.entregável.pacote)

**Gap:** nosso cronograma usa disciplina (atividade), não entregável. Vale evoluir.

### Eng 35 — Last Planner System

**INSIGHT MAIOR DE TUDO QUE LI:** caso real BR (Minha Casa Minha Vida em Ribeirão Preto) com LPS implementado economizou **R$ 3.043.523,79 e 4 meses de prazo**.

Estrutura LPS:
1. **Master Plan** (cronograma todo, 12-36m, milestones)
2. **Phase Plan** (3-12m, workshop colaborativo pull)
3. **Lookahead** (6-8 semanas, "make ready")
4. **Weekly Work Plan** (comprometimento semanal, só atividades 100% prontas)

Métrica-chave: **PPC** (Percent Plan Complete) — atividades concluídas / planejadas. Obra padrão BR sem LPS = 35-50%. Com LPS = 75-80%.

**Oportunidade pro AI.arq Fase 2:** evoluir de "Gantt clássico" pra **"Gantt + Lookahead 6 semanas + PPC tracker"**. Diferencial real. Nenhum concorrente BR oferece interface LPS estruturada.

### Amanda 10X — síntese das 20 skills

Padrão claro de UX que vale adotar:
- **Arquivo numerado** (`05_programa.txt`, `11_quantitativo.txt`) — sequência clara
- **Project-Cliente** = pasta digital por cliente (template duplicável)
- **Knowledge base** = arquivos do cliente carregados → IA consulta
- **Comando explícito** ("Skill X — gera Y a partir de Z")
- **Output em 5 blocos** (O que é · Quando usar · Como ativar · O que recebe · Dica)

**Skills que mais batem com Fase 2-3 do nosso roadmap:**
- 4.3 Quantitativo (já cobrimos, mas dela é manual a partir do caderno; nossa é automática do CAD)
- **4.4 Orçamento por Ambiente** (não cobrimos, quick win — view nova da planilha)
- 4.5 Texto pra Prefeitura (Fase 3a, vale incluir)
- 6.1 Verificador NBR 9050 (Fase 8, gap competitivo)
- 6.4 Compatibilização (Fase 8, requer leitura de múltiplos projetos)

### Prevision (50 prompts) — síntese

Maioria genérica. Mas títulos confirmam **dores reais do mercado:**
- Aceleração de cronograma quando atraso (P22, P28, P36, P39)
- Planejamento reverso (P38)
- Concretagens (P23)
- Cenários de atraso (P42)
- Férias coletivas BR (P43) — peculiaridade que nenhum software estrangeiro cobre

---

## 5. 🎯 Decisões críticas derivadas

### Decisão 1: Cronograma é DIFERENCIAL FORTE, vale aprofundar

Pesquisa confirma que Last Planner economiza R$3 mi e 4 meses na obra real. A versão "Gantt + Curva S" que fiz na Fase 2 é **boa pra começar, fraca pra reter**.

**Iteração 2 do Cronograma (próximas 6-8 semanas):**
- Lookahead 6 semanas (nova aba)
- PPC tracker (cliente marca atividade concluída → calcula %)
- Causa raiz NCR (causas de não cumprimento)
- Comparativo previsto vs realizado
- Curva S sigmoidal (não linear)
- Citação Acórdão TCU 2622/2013

### Decisão 2: Verificador NBR 9050 é OURO escondido

Nenhum concorrente BR faz auditoria automática de NBR. Demanda obrigatória legal.

**Fase 8a (priorizar antes de Fase 5 ERP):**
- Verificador NBR 9050 com 7 categorias da Amanda Skill 6.1
- Output: relatório ✅/⚠/❌ por item
- Cliente sobe planta (PDF/DWG), AI.arq devolve auditoria
- Preço sugerido: R$ 100-150 por auditoria
- Janela de mercado: 12-24 meses antes de concorrente fazer

### Decisão 3: Orçamento por Ambiente = quick win imediato

Skill 4.4 Amanda confirma que **organizar orçamento por cômodo** (não por disciplina) é insight UX importante. Cliente vê "cozinha custou R$X, banheiro R$Y" → decide o que cortar.

**Implementação:** view nova na planilha que já geramos. 3-5 dias.

### Decisão 4: Manter aposta no leitor CAD

Nenhum concorrente lê DWG/PDF nativo. **Investir mais nessa trincheira:**
- Melhorar parser DWG (atualmente ODA + libredwg)
- Adicionar IFC (BIM nativo)
- Adicionar RVT (Revit) — mais difícil mas crítico
- Detecção de objetos (paredes, vagas, escadas, etc) com vision model

### Decisão 5: NÃO atacar Fase 5 (ERP) agora

Flowup tem 1.000+ escritórios. Brigar com ele agora sem produto técnico maduro seria suicídio. **Diferenciar primeiro, escalar depois.**

Fase 5 ERP só faz sentido quando:
- Tivermos 50+ usuários ativos pagantes
- 200+ projetos processados
- Pelo menos 3 diferenciais técnicos (CAD + SINAPI + NBR audit)

---

## 6. 📋 Backlog priorizado (próximos 6 meses)

### Mês 1 (resto de maio + junho)
1. ⚡ **Orçamento por Ambiente** (quick win) — 1 semana
2. 🔧 Iteração 2 Cronograma: Lookahead 6 semanas + PPC tracker — 3 semanas
3. 📊 Atualizar agent `cronograma-gerador.md` com Acórdão TCU + sigmoidal — 1 dia

### Mês 2 (julho)
4. 🎯 **POC Verificador NBR 9050** — 4 semanas
   - 7 categorias da Skill Amanda 6.1
   - Output relatório PDF + tabela web
   - Pricing R$ 150/auditoria

### Mês 3 (agosto)
5. 📝 **Memorial Descritivo PDF** — Fase 3a — 4 semanas
   - Template NBR 13531/13532
   - Cruza disciplinas detectadas
   - Output pra prefeitura SP/RJ/POA

### Mês 4 (setembro)
6. 🧾 **BDI Helper** — Fase 3c — 3 semanas
   - Template Sienge BDI como base
   - Adm Central + Adm Local + Indiretas + Financeira + Lucro + Tributos
   - Calibração por tipo de obra

### Mês 5 (outubro)
7. 🪑 **Caderno de Acabamentos** — Fase 3b — 4 semanas
   - Catálogo 500 SKUs (Portobello/Eliane/Deca/Suvinil)
   - Sistema de codificação
   - Monetização B2B (afiliado)

### Mês 6 (novembro)
8. 📋 **Texto pra Prefeitura + RRT** — Fase 3a complemento — 3 semanas
9. Avaliar Fase 8b (Verificador NBR 15575) ou Fase 5 ERP (se métricas justificarem)

### Sempre em paralelo
- Marketing: blog 1x/semana, IG segundo grade
- Feedback loop com Rafael/Sidnei/Weslei/Daniela
- Iterar SINAPI matcher (qualidade matches)
- Onboarding tour

---

## 7. 🚨 Alertas estratégicos

### Que vigiar de perto

- **Vobi anunciar leitor CAD** — risco médio (eles têm capital Y Combinator). Probabilidade 12 meses: 30%.
- **Maket.ai chegar no Brasil** — risco baixo no curto (foco USA). Probabilidade 12 meses: 15%.
- **Sienge adicionar IA** — risco baixo (eles preferem comprar startup). Probabilidade 12 meses: 20%.
- **Flowup adicionar quantitativo** — risco médio. Probabilidade 12 meses: 25%.

### Cenário "se tudo der certo" (3 anos)

- 500+ usuários ativos
- R$ 80k MRR
- Cobertura: Fase 1 + 2 + 3 + 8 (quantitativo, cronograma, documentação, conformidade)
- Negociação com Flowup ou Vobi pra integração/aquisição

### Cenário "se tudo der errado" (3 anos)

- Vobi ou Flowup adicionam leitura CAD primeiro → diferencial cai
- Maket chega no Brasil com US$ 29/mês → preço pressionado
- Audiência não cresce além de 50 usuários

**Defesa principal:** velocidade. Cada mês que demoramos pra diferenciar mais (NBR audit, Last Planner real, multi-fase pacote completo) é mês a mais de gap fechando.

---

## 8. 📚 Material que ainda devo estudar (próxima sessão de estudo)

- [ ] Bravy Arq 26 (Caderno acabamentos) — texto completo
- [ ] Bravy Arq 42 (NBR 13532) — texto completo
- [ ] Bravy Arq 56 (RRT/CAU) — texto completo
- [ ] Bravy Eng 36 (EVM) — texto completo
- [ ] Bravy Eng 31 (BDI Acórdão TCU) — texto completo
- [ ] Sienge Cálculo BDI — abrir planilha pra ver fórmulas
- [ ] Projeto Manus antigo — ler schema.ts + rotas tRPC pra ver UX

Cada um abre 1 sessão dedicada quando atacarmos a fase correspondente.

---

## 9. ✅ TL;DR — O que muda a partir desse estudo

1. **Cronograma sai do "Gantt simples" pra "LPS-inspired"** — Lookahead + PPC + NCR
2. **Verificador NBR 9050 entra como Fase 8a** (prioridade depois de Orçamento por Ambiente)
3. **Orçamento por Ambiente = quick win imediato** (1 semana)
4. **Memorial Descritivo = primeira feature Fase 3** (não BDI, não Caderno)
5. **Sequência ajustada:** Fase 2 v2 → 3d → 8a → 3a → 3c → 3b
6. **NÃO Fase 5 ERP agora** — diferenciar técnico primeiro

Roadmap longo prazo (10 fases) mantém estrutura. Mudou só **ordem** dentro das fases iniciais.

---

**Sources das pesquisas web:**
- [Tendências Construção Civil 2026 — Sienge](https://sienge.com.br/blog/tendencias-da-construcao-civil/)
- [TOTVS — Tendências 2026 (ESG, IA)](https://www.totvs.com/blog/gestao-para-construcao/tendencias-construcao-civil/)
- [CBIC projeção 2026](https://cbic.org.br/construcao-civil-projeta-2026-mais-positivo-que-2025-impulsionado-por-credito-e-investimentos/)
- [Exame — 5 tendências](https://exame.com/bussola/em-2026-construcao-civil-priorizara-processos-industrializados/)
- [Vobi](https://www.vobi.com.br/) / [Flowup arquitetos](https://www.flowup.me/escritorios-de-arquitetura/)
- [Maket review 2026](https://www.archpulse.co/tool/maket-ai) / [Finch3D review](https://illustrarch.com/articles/75056-finch3d-review.html)
- [Last Planner BR — caso Ribeirão Preto](https://nppg.org.br/revistas/gestaoegerenciamento/article/view/1775)
- [Lei 14.133 Orçamento detalhado — TCU](https://licitacoesecontratos.tcu.gov.br/4-4-3-6-orcamento-detalhado-do-custo-global-da-obra/)
- [BDI Acórdão TCU](https://zenite.blog.br/qual-e-a-composicao-de-bdi-nas-contratacoes-de-obras-de-acordo-com-o-tcu/)
- [NBR 9050 Vanzolini](https://vanzolini.org.br/organizacoes/certificacoes/nbr-9050/) / [NBR 15575 Mobuss](https://www.mobussconstrucao.com.br/blog/nbr-15575/)
