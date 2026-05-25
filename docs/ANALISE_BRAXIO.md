# Análise Competitiva — Braxio

> **Data:** 2026-05-25
> **Fonte:** 92 docs da central de ajuda do Braxio (https://www.braxio.com.br/ajuda) lidos integralmente.
> **Contexto:** Pedro confirmou direção ERP pro AI.arq. Braxio é o produto mais maduro do mercado pro mesmo público-alvo (escritório de arquitetura BR pequeno/médio). Análise feita pra dimensionar Fase 5 do roadmap.

---

## 1. Inventário Braxio (compacto)

| Categoria | Feature | Profundidade |
|---|---|---|
| CRM | Clientes (PF/PJ), pipeline 5 status, ficha completa, origem, importação planilha | 4 |
| CRM | Propostas (3 métodos: m²/hora/manual), aceite cria projeto+financeiro, aditivos, exportar PDF | 4 |
| Projetos | Cabeçalho com cliente/área/endereço/equipe/permissões, abas (Visão/Tarefas/Cronograma/Orç/Obra/Financ/Horas/Arq/Portal) | 5 |
| Projetos | Workflows (templates de etapas+tarefas reutilizáveis para projeto/cliente/proposta/orçamento) | 4 |
| Tarefas | 4 escopos (Minhas/Escritório/CRM/Projetos), kanban+tabela, subtarefas, timer | 4 |
| Horas | Timer ou manual, estimado vs registrado, relatório por projeto/etapa/pessoa, "pior etapa" | 4 |
| Orçamentos | Grupos+itens+cotações múltiplas por fornecedor, status (Pendente/Cotado/Aprovado/Comprado/Recusado), templates | 4 |
| Orçamentos | **Reserva Técnica** (compra → RT pendente → RT recebida → vira receita no DRE) | 5 |
| Orçamentos | Export PDF/CSV/Excel com seções configuráveis | 3 |
| Obras | Execução por serviço (responsável/início/fim/fornecedor), templates de obra | 4 |
| Obras | Cronograma Gantt da obra (dia/semana/mês) | 3 |
| Obras | Visitas com foto/áudio/observações, pendências com severidade, relatório de obra/visita em PDF | 5 |
| Financeiro | Receitas/despesas, parcelas, custos fixos recorrentes, conta a pagar/receber, anexo NF+recibo na transação | 5 |
| Financeiro | Bancos com OFX (Itaú/Brad/Santander/Nubank/Inter/BTG/BB/Sicoob), conciliação match-a-match | 5 |
| Financeiro | Categorias DRE 2 níveis (subgrupo+categoria), bandeira "aparece no DRE", código contábil opcional | 5 |
| Financeiro | DRE anual, fluxo de caixa previsto/realizado, relatório por período | 4 |
| Fiscal | NFSe completa: assistente CNPJ→Receita, A1 (.pfx), códigos LC116+CNAE+reforma tributária, templates discriminação com variáveis, cancelamento, rejeição+reemissão | 5 |
| Fiscal | Aba "Sem NF emitida" cruza recebíveis sem nota | 4 |
| Portal Cliente | Módulos liga/desliga (Entregas/Orçamentos/Obra), visibilidade granular (esconder preço/fornecedor/pendência), "Ver como cliente", token regenerável | 5 |
| Arquivos | Pastas em 3 níveis com estrutura padrão pronta (Briefing→Entrega), upload 100MB, visibilidade por cargo, DWG/SKP aceitos mas sem leitura | 3 |
| Arquivos | Versionamento: **NÃO há histórico automático**, só nomes manuais (R00/R01) | 1 |
| Biblioteca | Produtos/cotações reutilizáveis com foto+link+fornecedor (mas não é estoque) | 3 |
| Fornecedores | Cadastro completo, contatos, avaliações, vínculo orçamento+obra, "Clube de Pontuação" | 4 |
| Agenda | Calendário com tipos, integração Google Calendar e iCloud (senha de app) | 4 |
| Config | Equipe+5 cargos, permissões por módulo, listas customizáveis, templates, workflows, lixeira | 4 |
| IA | "Assistente IA" em rollout controlado para perguntas operacionais — sem leitura de CAD | 2 |

## 2. Heatmap AI.arq vs Braxio

Legenda: ✓ cobre · ~ parcial · ✗ não cobre · ⭐ faz MELHOR · 🚫 não faz sentido replicar

| Feature Braxio | AI.arq hoje | AI.arq Fase 5 |
|---|---|---|
| CAD → quantitativo XLSX | ⭐ (não existe no Braxio) | ⭐ |
| Comparativo de fornecedores em planilha | ⭐ (com IA) | ⭐ |
| PPT com marca para cliente | ⭐ | ⭐ |
| Cronograma físico-financeiro automatizado | ✗ (Fase 2 em construção) | ⭐ |
| Cliente/CRM com pipeline | ✗ | ~ |
| Propostas com 3 métodos de cálculo + aceite vira projeto | ✗ | ~ |
| Projeto com 10 abas estruturado | ✗ | ~ |
| Tarefas com 4 escopos + workflows | ✗ | ~ |
| Apontamento de horas + relatórios | ✗ | ~ |
| Orçamento operacional (cotações múltiplas) | ✓ (planilha) | ⭐ (puxando do CAD) |
| Reserva Técnica → financeiro | ✗ | ~ |
| Obras: execução + visitas com foto/áudio + pendências + Gantt + relatório PDF | ✗ | ~ |
| Financeiro completo (receitas/desp/parcelas/custos fixos) | ✗ | ~ |
| Bancos + OFX + conciliação | ✗ | 🚫 (commodity, parceria Pluggy) |
| Categorias DRE + DRE + fluxo caixa | ✗ | ~ (versão simples do projeto, não global) |
| NFSe completa (A1, LC116, reforma tributária) | ✗ | 🚫 (parceria Conta Azul) |
| Portal Cliente com visibilidade granular | ✗ | ~ |
| Arquivos com pastas padrão + 3 níveis | ✗ | ~ |
| Versionamento de arquivos automático | ✗ | ⭐ (oportunidade clara) |
| Biblioteca de produtos reutilizáveis | ~ (SINAPI/TCPO) | ⭐ (SINAPI/TCPO + IA, melhor) |
| Fornecedores com avaliação + Clube de Pontuação | ✗ | ~ |
| Agenda + Google/iCloud | ✗ | 🚫 (commodity) |
| Equipe + cargos + permissões + listas | ✗ | ~ (DAY 1) |
| IA leitura de CAD/PDF | ⭐ | ⭐ |
| IA operacional "quais projetos atrasados?" | ✗ | ~ |

## 3. 5 features Braxio que o AI.arq deveria considerar

Ordem por impacto/custo:

1. **Reserva Técnica (RT) automatizada** — compra na cotação vira receita no DRE com 1 clique. Killer feature emocional pro arquiteto, ninguém mais no mercado faz fluido. Custo médio, impacto alto. (`orcamentos-cotacoes/reserva-tecnica.md`)
2. **Aceite de proposta cria projeto + parcelas no financeiro em 1 ação** — junção tripla CRM/Projeto/Financ que define o ERP do arquiteto. Custo médio, impacto alto. (`propostas/aceite.md`)
3. **Custos fixos recorrentes** — modelo gera despesa pendente todo mês. Simples de fazer, retém usuário. Custo baixo, impacto médio. (`financeiro/custos-recorrentes.md`)
4. **Conciliação OFX banco a banco** — 8 bancos brasileiros nomeados (Nubank/Inter/Sicoob incluídos). Resolve a dor #1 do escritório que mistura PJ/PF. Custo médio, impacto alto. **MAS:** parceria Pluggy/Belvo faz mais sentido que construir do zero. (`financeiro/bancos-ofx.md`)
5. **NFSe com assistente CNPJ→Receita** — fluxo de 3 min, A1+ISS+CNAE+reforma tributária. Quase impossível de copiar (regulatório/municipal), mas grande lock-in. Custo alto, impacto alto. **DECISÃO:** não replicar, parceria com Conta Azul ou Bling. (`fiscal/configurar-nfse.md`)

## 4. 5 lacunas do Braxio que defendem o wedge AI.arq

1. **Zero leitura de CAD/DWG/PDF** — eles aceitam upload de DWG mas tratam como blob. Nosso wedge inteiro vive aqui. (`arquivos/enviar-arquivos.md` cita DWG/SKP como formato aceito, sem inteligência)
2. **Orçamento começa do zero** — usuário digita item/categoria/quantidade manual em todo projeto. AI.arq gera o orçamento já populado do CAD em minutos. (`orcamentos-cotacoes/itens-e-grupos.md`)
3. **Sem comparativo de fornecedor automatizado** — cotação por cotação na mão, sem IA sugerindo equivalentes ou alertando preço fora da curva.
4. **Sem versionamento automático de arquivos** — confessam no help: "A aba Arquivos ainda não cria histórico automático de versões". Oportunidade clara. (`arquivos/versionamento.md`)
5. **IA é só "assistente que explica"** — em rollout controlado, responde "quais projetos atrasados?". Não faz trabalho de fato. AI.arq faz o trabalho. (`comece-por-aqui/boas-vindas.md`)

## 5. Recomendação estratégica

**Caminho B com tempero de C: defender o wedge, depois ERP mínimo focado nas peças que amarram quantitativo → cronograma → financeiro do projeto, e parar aí.**

A maioria do Braxio é commodity bem feita (CRM/agenda/OFX/NFSe) que custaria 18 meses construindo pra empatar. Construir tudo na Fase 5 é cilada — o que diferencia o AI.arq vive no CAD, não no formulário de cliente. A sequência defensiva é:

1. **Ship Fase 2 (cronograma) já** — é a ponte natural do quantitativo e o Braxio só tem cronograma manual.
2. **Abrir Fase 5 só com 5 módulos:** Cliente + Projeto + Orçamento + Reserva Técnica + Portal Cliente. Mínimo pra manter o arquiteto dentro do produto entre projetos.
3. **Pular:** NFSe, OFX, DRE completo, agenda, biblioteca de produtos. Parceria/integração faz mais sentido que reconstruir.

**Sobre preço:** mensalidade é inevitável quando entra dado recorrente (financeiro, portal cliente vivo). Mas mantém avulso como porta de entrada — o cliente paga R$97 pelo quantitativo, vira lead pra mensalidade quando começa a usar Fase 2/5. Híbrido, não substituição.

## 6. 3 riscos subestimados no roadmap original (pré-25/05)

1. **Reserva Técnica é o gancho emocional do arquiteto** — não estava claro no roadmap que esse é o item que faz o profissional aceitar pagar mensalidade. Sem RT amarrada ao DRE, AI.arq Fase 5 é só "outra ferramenta de projeto" competindo com Trello+planilha. **Corrigido:** RT virou feature-âncora destacada.

2. **Portal Cliente com visibilidade granular é trabalho enorme e silencioso** — Braxio tem 6 controles finos (esconder preço/fornecedor/pendência/responsável/datas reais/fornecedor de fase). Subestimar isso é entregar portal feio que o cliente compara mal com Braxio. Roadmap antigo falava "galeria" mas portal de obra ao vivo é outra coisa. **Corrigido:** portal granular como módulo dedicado.

3. **Permissões por cargo (Proprietário/Sócio/Admin/Coord/Colab) com nível Completo/Visualizar/Atribuído/Sem acesso** — escritório de 5+ pessoas exige isso no dia 1. Construir multiusuário sério tarde custa caro pq vira refactor de banco. Se Fase 5 começa em 50 usuários, vários já são escritórios com equipe — não pode adiar permissões pra "depois". **Corrigido:** permissões marcadas como DAY 1 da Fase 5.

---

## Apêndice — Decisões duras que saíram dessa análise

Registradas no `ROADMAP.md` em 25/05/2026:

- Fase 5 redesenhada: ERP focado em 5 módulos (Cliente+Projeto+Orç+RT+Portal), não ERP completo.
- Reserva Técnica é feature-âncora da Fase 5.
- Modelo de preço vira HÍBRIDO: avulso continua pro quantitativo, mensalidade entra só pra módulo ERP.
- Permissões por cargo (5 cargos × 4 níveis) são DAY 1 da Fase 5.
- NÃO replicar: NFSe completa, OFX, DRE global, agenda, biblioteca produtos.
