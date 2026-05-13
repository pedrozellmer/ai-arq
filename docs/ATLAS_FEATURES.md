# 🗺️ Atlas de Features AI.arq — Visão ERP Completo

> **Documento canônico** com TODAS as ~184 skills/agents que catalogamos de 3 fontes externas + roadmap próprio. Organizado pelas 9 fases do AI.arq pra virar **o sistema operacional do escritório de arquitetura BR**.
>
> Última atualização: 2026-05-13

---

## 📜 Visão estratégica

**Hoje:** AI.arq cobre **1 das 14 etapas** da jornada do arquiteto BR (Quantitativo).

**Visão:** AI.arq cobre **todas as 14**, em 9 fases sequenciais. ERP completo, com IA aplicada onde dói (leitura de CAD, geração de documento técnico, verificação normativa) e CRUD onde precisa (financeiro, clientes, equipe).

**Diferencial duro:** somos os únicos que **leem o CAD binário** (DWG/PDF) e devolvem dado estruturado. Flowup, Vobi, Sienge fazem CRUD em cima de dado que o usuário digita — a gente extrai do projeto direto.

---

## 🏢 Mapa competitivo BR (2026)

### Concorrentes que viraremos quando crescer

| Player | O que fazem | O que falta | Stack IA |
|---|---|---|---|
| **[Flowup](https://www.flowup.me/escritorios-de-arquitetura/)** | ERP de gestão projeto+financeiro+equipe. 1.000+ escritórios BR. Parceiros ASBEA/CREA/Sebrae | **Não lê CAD. Não gera quantitativo técnico.** | Sem IA específica |
| **[Vobi](https://www.vobi.com.br/)** | Gestão de obra completa. R$5B obras/ano. Backed Y Combinator | Foco em CONSTRUTORA (não escritório). 3 agents IA (Financeiro, Compras, Diário) — assistência, não leitura de projeto | "Agentes de IA" (claim forte) |
| **[Sienge](https://www.sienge.com.br/)** | 12 módulos, construtora grande | Caro. Foco incorporadora. ERP genérico | Sem IA central |
| **[Projetools](https://www.projetools.com.br)** | Gestão escritório arq | Pequeno. Sem IA | — |
| **[GestãoClick](https://gestaoclick.com.br/)** | ERP genérico c/ vertical arq | Não específico de obra | — |

### AI.arq vs eles

```
              Lê CAD?    IA técnica?   Foco arquiteto?    ERP completo?
Flowup        ❌         ❌            ✅                  ✅
Vobi          ❌         🟡 (assist)   🟡 (mais obra)     ✅
Sienge        ❌         ❌            ❌ (construtora)    ✅
AI.arq HOJE   ✅         ✅            ✅                  ❌ (só Fase 1)
AI.arq META   ✅         ✅            ✅                  ✅
```

**Aposta:** o IA específico de arquitetura (não genérico) + leitura CAD é nossa vantagem defensável. Flowup/Vobi não vão entrar nessa briga sem refazer stack inteiro. Tempo é nosso aliado.

---

## 🪜 9 fases do produto — atlas completo

Legenda de fonte:
- 🟦 **B**ravy (114 agents técnicos) · 🟨 **P**revision (50 prompts) · 🟩 **A**manda 10X (20 skills) · ⚪ **AI**.arq próprio

Legenda de status:
- 🟢 **HOJE** · 🔵 **Construindo** · ⚪ **Radar** · ⏳ **Longo prazo**

---

### **FASE 1 — Quantitativo a partir de CAD** 🟢 HOJE

**Lógica:** sobe PDF/DWG/DXF → recebe XLSX com 18 disciplinas, cores por confiança, refs SINAPI/TCPO.

| Feature | Status | Inspiração |
|---|---|---|
| Leitura DWG/PDF/DXF | 🟢 rodando | ⚪ AI |
| Detecção de 18 disciplinas | 🟢 rodando | ⚪ AI + 🟦 Eng 30 SINAPI |
| Sistema de cores (branco/laranja/cinza/roxo) | 🟢 rodando | ⚪ AI |
| Matcher SINAPI (10K composições) | 🟢 rodando | ⚪ AI + 🟦 Eng 30 |
| Matcher TCPO BIM | 🟢 rodando | ⚪ AI |
| Revisão inline + cashback | 🟢 rodando | ⚪ AI |

**Pendência:** validar nosso banco (10.284 SINAPI) vs Sienge 2025 (8.868).

---

### **FASE 2 — Cronograma físico-financeiro** 🔵 CONSTRUINDO

**Lógica:** quantitativo + duração desejada → Gantt + curva S + cronograma XLSX + fluxo físico mensal.

| Feature | Status | Inspiração |
|---|---|---|
| Sequenciamento 16 etapas Sienge | 🔵 agent criado | 🟦 Eng 32 · Sienge oficial |
| Cronograma físico (Gantt) | 🔵 POC Weslei feita | 🟦 Eng 32 |
| Curva S avanço físico | 🔵 POC Weslei feita | 🟦 Eng 33 · 🟨 P15 |
| Curva S avanço financeiro | ⚪ radar | 🟦 Eng 33 · 🟨 P16 |
| Aba dentro da planilha (fórmulas Excel) | 🔵 em código | ⚪ AI (pivot do Pedro) |
| EAP/WBS pacotes de trabalho | ⚪ radar | 🟦 Eng 34 · 🟨 P6 |
| Last Planner System (pull planning) | ⚪ radar | 🟦 Eng 35 · 🟨 P20, P24 |
| EVM Earned Value PMI | ⚪ radar | 🟦 Eng 36 · 🟨 P34 |
| Fast-tracking (aceleração) | ⚪ radar | 🟨 P22, P28, P36, P39 |
| Planejamento reverso | ⚪ radar | 🟨 P38 |
| Concretagens (datas e cura) | ⚪ radar | 🟨 P23 |
| Ciclos repetitivos (pavtipo) | ⚪ radar | 🟨 P32 |
| Cenários de atraso | ⚪ radar | 🟨 P42 |
| Plano de transição entre fases | ⚪ radar | 🟨 P41 |
| Férias coletivas BR (22/12-03/01) | ⚪ radar | 🟨 P43 |
| Layout de canteiro | ⚪ radar | 🟨 P9 |
| Logística de materiais | ⚪ radar | 🟨 P5 |

---

### **FASE 3 — Documentação técnica do projeto** 🔵 PLANEJADO

A Amanda chama esse de "**módulo de MAIOR percepção de valor**" — é onde o cliente fala "isso vale o curso inteiro". Pra gente, é onde a planilha de Fase 1 vira **pacote completo** que o arquiteto entrega.

#### 3a — Memorial Descritivo (NBR 13531/13532) ⚪
| Feature | Status | Inspiração |
|---|---|---|
| Memorial PDF formato CAU | ⚪ radar | 🟩 4.1 · 🟦 Arq 42 |
| Projeto legal pra PMSP/PMRJ/POA | ⚪ radar | 🟦 Arq 08 |
| RRT/CAU pré-preenchido | ⚪ radar | 🟦 Arq 56 · 🟦 Eng 53 (ART) |
| Texto pra prefeitura (rascunho) | ⚪ radar | 🟩 4.5 |
| Checklist documentos protocolo | ⚪ radar | 🟦 Arq 29 (alvará) · 🟦 Arq 30 (habite-se) |

#### 3b — Caderno de Especificações ⚪
| Feature | Status | Inspiração |
|---|---|---|
| Caderno por ambiente (FF&E) | ⚪ radar | 🟩 4.2 · 🟦 Arq 26 |
| Catálogo fabricantes BR (Portobello/Eliane/Deca/Suvinil) | ⚪ radar | 🟦 Arq 26 |
| Sistema de códigos (REV-PISO-01) | ⚪ radar | 🟦 Arq 26 |
| Datasheets anexos | ⚪ radar | 🟦 Arq 26 |
| Monetização B2B (afiliado fabricante) | ⚪ ideia | ⚪ AI |

#### 3c — BDI Helper ⚪
| Feature | Status | Inspiração |
|---|---|---|
| Decomposição Adm Central + Adm Local + Indiretas + Financeira + Lucro + Tributos | ⚪ radar | 🟦 Eng 31 · Sienge BDI template |
| Calibração por tipo de obra | ⚪ radar | ⚪ AI |
| Fórmulas TCU Acórdão 2622 | ⚪ radar | 🟦 Eng 31 |
| UX cores amarelo (%) / azul (R$) | ⚪ radar | Sienge BDI template |

#### 3d — Orçamento por Ambiente (Quick win) ⚪
| Feature | Status | Inspiração |
|---|---|---|
| View nova da planilha (agrupado por cômodo) | ⚪ radar — **1 dia de dev** | 🟩 4.4 |
| Resumo executivo (top 5 ambientes mais caros) | ⚪ radar | 🟩 4.4 |
| Custo por m² do ambiente | ⚪ radar | 🟩 4.4 |

#### 3e — Outros documentos técnicos
| Feature | Status | Inspiração |
|---|---|---|
| Orçamento sintético | ⚪ radar | 🟦 Eng 29 |
| Orçamento analítico SINAPI/SBC/CUB | ⚪ radar | 🟦 Eng 30 |
| Relatório de visita técnica | ⚪ radar | 🟩 4.6 · 🟦 Arq 28 |
| Memorial AVCB/CLCB | ⚪ radar | 🟦 Arq 31 |
| Memorial SPDA (NBR 5419) | ⚪ radar | 🟦 Eng 12 |
| Estudo de impacto vizinhança (EIV) | ⚪ radar | 🟦 Arq 33 |

---

### **FASE 4 — Cotação + Comparativo de fornecedor** 🟡 PARCIAL

Já existe parcial. Refinar com input dos templates.

| Feature | Status | Inspiração |
|---|---|---|
| Upload XLSX fornecedor (parser strict + fuzzy) | 🟢 rodando | ⚪ AI |
| Comparativo pareado item-a-item | 🟢 rodando | ⚪ AI |
| Ranking + discrepâncias + itens esquecidos | 🟢 rodando | ⚪ AI |
| PPT executivo com marca do escritório | 🟢 rodando | ⚪ AI |
| Heurísticas de mercado (% variação suspeita) | 🟢 rodando | ⚪ AI |
| Envio direto cliente final (WhatsApp) | 🟢 rodando | ⚪ AI |

---

### **FASE 5 — ERP do escritório** ⚪ 60% PRONTO

Esqueleto existe no projeto Manus antigo (`arq/_archive/cronograma-arquitetura-extracted/`).

#### 5a — Gestão comercial (pré-projeto)
| Feature | Status | Inspiração |
|---|---|---|
| Briefing inteligente (cliente novo) | ⚪ Manus base | 🟩 2.1, 2.2 |
| Gerador de proposta CAU/IAB | ⚪ Manus base | 🟩 2.3 · 🟦 Arq 54 |
| Gerador de contrato arquiteto-cliente | ⚪ Manus base | 🟩 2.3 · 🟦 Arq 55 · 🟦 Eng 56 |
| Honorários CAU calculados | ⚪ radar | 🟦 Arq 54 |

#### 5b — CRM
| Feature | Status | Inspiração |
|---|---|---|
| Notas por cliente | ⚪ Manus base | Manus existente |
| Follow-up + tags | ⚪ Manus base | Manus existente |
| Leads do chat widget | 🟢 rodando | ⚪ AI |
| Onboarding tour | 🟢 rodando | ⚪ AI |

#### 5c — Financeiro
| Feature | Status | Inspiração |
|---|---|---|
| Entrada % ou fixa | ⚪ Manus base | Manus existente |
| Parcelas auto-geradas (intervalo configurável) | ⚪ Manus base | Manus existente |
| Edição de cada parcela | ⚪ Manus base | Manus existente |
| Fluxo de caixa | ⚪ Manus base | Manus existente |
| Despesas + receitas multi-entrada | ⚪ Manus base | Manus existente |
| Dashboard executivo | ⚪ Manus base | Manus existente |
| NFSe (nota fiscal de serviço) | ⚪ radar | Vobi/Flowup têm |
| Conciliação bancária | ⚪ radar | Vobi/Flowup têm |

#### 5d — Galeria + Storage
| Feature | Status | Inspiração |
|---|---|---|
| Upload PDF/DWG/plantas | 🟢 rodando | ⚪ AI |
| Organização por categoria | ⚪ Manus base | Manus existente |
| Histórico de versões | ⚪ radar | ⚪ AI |

#### 5e — Equipe + alocação
| Feature | Status | Inspiração |
|---|---|---|
| Time tracking | ⚪ radar | Flowup/Vobi |
| Alocação por projeto | ⚪ radar | Flowup |
| Organograma equipe | ⚪ radar | 🟨 P4 |
| Dimensionamento de equipes por atividade | ⚪ radar | 🟨 P30 |

#### 5f — Portal do cliente
| Feature | Status | Inspiração |
|---|---|---|
| Cliente acompanha andamento | ⚪ radar | Vobi tem |
| Aprovações inline | ⚪ radar | ⚪ AI |
| Mensagens | ⚪ radar | ⚪ AI |

---

### **FASE 6 — Pré-projeto + viabilidade** ⚪ RADAR

Entrar **antes** do CAD. Captura cliente no estágio mais cedo do funil.

| Feature | Status | Inspiração |
|---|---|---|
| **Estudo de viabilidade urbana** (8 itens: TO, CA, gabarito, recuos, permeabilidade, vagas, uso, restrições) | ⚪ radar | 🟩 3.3 · 🟦 Arq 01 |
| Análise de terreno (planialtimétrico + insolação) | ⚪ radar | 🟩 3.1 · 🟦 Arq 02, 04 · 🟦 Eng 37 |
| Programa de necessidades (zonas funcionais + hierarquia) | ⚪ radar | 🟩 3.2 · 🟦 Arq 03 |
| Moodboard conceitual | ⚪ radar | 🟩 3.4 · 🟦 Arq 25 |
| Estudo preliminar (residencial/comercial) | ⚪ radar | 🟦 Arq 05, 06 |
| Anteprojeto | ⚪ radar | 🟦 Arq 07 |
| Estudo de massas urbanas | ⚪ radar | 🟦 Arq 04 |

---

### **FASE 7 — Visualização + render** ⏳ LONGO PRAZO

| Feature | Status | Inspiração |
|---|---|---|
| Planta humanizada | ⏳ futuro | 🟩 5.1 · 🟦 Arq 52 |
| Render interno 3D | ⏳ futuro | 🟩 5.2 · 🟦 Arq 51 |
| Render externo 3D | ⏳ futuro | 🟩 5.3 · 🟦 Arq 51 |
| CAD 2D → 3D massing automático | ⏳ futuro | ⚪ AI |
| IA generativa Midjourney/Veras integrada | ⏳ futuro | 🟦 Arq 57 |
| Pranchas A1/A2 finalizadas | ⏳ futuro | 🟦 Arq 53 |

---

### **FASE 8 — Conformidade + auditoria normativa** ⚪ RADAR

Diferencial enorme. Nenhum concorrente faz auditoria automática de NBR.

| Feature | Status | Inspiração |
|---|---|---|
| **Verificador NBR 9050 (Acessibilidade)** | ⚪ radar | 🟩 6.1 · 🟦 Arq 32 |
| **Verificador NBR 15575 (Desempenho)** | ⚪ radar | 🟩 6.2 · 🟦 Arq 38 |
| Verificador NBR 9077 (Saídas de emergência) | ⚪ radar | 🟦 Arq 39 |
| Verificador NBR 16280 (Reforma) | ⚪ radar | 🟦 Arq 40 |
| Análise de código local (município) | ⚪ radar | 🟩 6.3 · 🟦 Arq 41 |
| **Compatibilização com complementares** (Arq × Estr × Hidro × Elét × AVAC) | ⚪ radar | 🟩 6.4 · 🟦 Arq 50 |
| Critérios de aceitação por etapa | ⚪ radar | 🟨 P7 |
| Controle de não-conformidades | ⚪ radar | 🟨 P18 |
| Análise de restrições ambientais | ⚪ radar | 🟨 P27 |
| Restrições NR (NR-18, NR-35, NR-10) | ⚪ radar | 🟦 Eng 47-51 |

---

### **FASE 9 — Pós-obra + manutenção** ⏳ LONGO PRAZO

| Feature | Status | Inspiração |
|---|---|---|
| Habite-se | ⏳ futuro | 🟦 Arq 30 |
| Averbação em cartório (RGI) | ⏳ futuro | 🟦 Arq 34 |
| Regularização REURB | ⏳ futuro | 🟦 Arq 35 |
| INSS/CNO/CEI matrícula obra | ⏳ futuro | 🟦 Arq 36 |
| Procedimento de entrega da obra | ⏳ futuro | 🟨 P12 |
| Manual do proprietário (NBR 14037) | ⏳ futuro | ⚪ AI |
| Monitoramento pós-obra | ⏳ futuro | ⚪ AI |

---

### **FASE 10 — Generativo (texto → projeto)** ⏳ MUITO LONGO PRAZO

Visão de 3-5 anos. Cliente descreve, AI.arq gera projeto + 3D + quantitativo.

| Feature | Status | Inspiração |
|---|---|---|
| Texto → planta 2D inicial | ⏳ futuro | ⚪ AI |
| Planta 2D → 3D + quantitativo (já temos último passo) | ⏳ futuro | ⚪ AI |
| IA generativa de arquitetura (própria) | ⏳ futuro | 🟦 Arq 57 |

---

## 📊 Estatísticas do atlas

```
Total de features mapeadas:        ~140 itens
Rodando hoje (🟢):                   ~12
Construindo (🔵):                    ~8
Radar de curto/médio (⚪):           ~80
Longo prazo (⏳):                    ~40

Fonte de inspiração:
- Bravy (B):           114 agents técnicos · maioria das features Fase 3, 8
- Prevision (P):       50 prompts · cobertura Fase 2 (cronograma)
- Amanda 10X (A):      20 skills · cobertura Fase 3 (módulo M4 inteiro)
- AI.arq próprio:      Fases 1, 4 + estratégia
```

---

## 🎯 Sequenciamento sugerido (ordem de ataque)

### Próximos 3 meses (semana a semana)
1. ✅ Fase 1 estabilizada (HOJE)
2. 🔵 Fase 2 Cronograma (em curso) — terminar aba Excel com fórmulas
3. 🔵 Fase 3d **Orçamento por Ambiente** (quick win — 1 semana)
4. 🔵 Fase 3a **Memorial Descritivo** (4 semanas)

### Mês 4-6
5. Fase 3c **BDI Helper** (template Sienge pronto)
6. Fase 3b **Caderno acabamentos** (catálogo fabricantes BR)
7. Fase 4 **Comparativo** refinar

### Mês 7-12
8. Fase 5 (ERP) — começar pelo **financeiro + galeria** (Manus base)
9. Fase 8 **Verificadores NBR 9050 + 15575** — diferencial competitivo

### Ano 2
10. Fase 5 completa (CRM + equipe + portal cliente)
11. Fase 6 **Estudo de Viabilidade** (captura no funil cedo)
12. Fase 8 **Compatibilização** (Arq × engenharias)

### Ano 3+
13. Fase 7 (visualização + render)
14. Fase 9 (pós-obra)
15. Fase 10 (generativo)

---

## 🎯 Pra revisar TODA semana

Esse atlas é vivo. A cada feature lançada:
- ✅ Mover de ⚪ pra 🟢
- Re-priorizar próximas (validar com usuários reais)
- Adicionar novas que aparecerem em conversas/feedback

A meta de longo prazo é simples: **se um arquiteto BR fizer um projeto novo em 2030, ele faz no AI.arq ponta a ponta**. Da primeira reunião com cliente ao habite-se. Esse documento é o caminho até lá.
