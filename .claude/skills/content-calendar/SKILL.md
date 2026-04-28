---
name: content-calendar
description: Gera calendário editorial mensal coordenando blog, Instagram (feed + stories + reels), email e LinkedIn. Use quando o Pedro pedir planejamento de marketing pro mês, ou quando os subagents (reels, captions, stories) gerarem conteúdo.
---

# Content Calendar (AI.arq)

Skill que gera calendário editorial coordenado entre canais. Visualiza tudo num esquema único pra Pedro saber o que vai sair onde e quando.

## Stack de canais

| Canal | Frequência | Formato |
|---|---|---|
| **Blog** | 1×/semana (domingo) | Post 1500-2500 palavras |
| **IG Feed** | 3×/semana (seg/qua/sex) | Carrossel ou imagem única |
| **IG Reels** | 2-3×/semana | Vídeo 15-60s |
| **IG Stories** | 3-5×/dia (todos os dias) | Enquete, pergunta, bastidor |
| **Email** | 1× newsletter/mês + transacionais | HTML + plain text |
| **LinkedIn** | 1×/semana (3ª feira) | Texto longo + carrossel |

## Workflow pra gerar calendário

### Input
- Mês de referência (ex: "Maio 2026")
- Temas prioritários (do roadmap ou pedidos do Pedro)
- Eventos importantes (lançamentos, feriados, campanhas)

### Processo

1. **Mapeia 4-5 semanas do mês** com slots por dia
2. **Distribui temas** equilibrando educacional + venda + bastidores
3. **Coordena entre canais** (Reel da terça pode ser teaser do post do domingo)
4. **Define hashtags semanais** (rotaciona pra não bater filtro)
5. **Gera cronograma de stories** (3-5 ideias/dia)
6. **Sugere CTAs específicos** (cada post tem CTA único)

### Output

Markdown formatado tipo:

```markdown
# Calendário Editorial AI.arq — Maio 2026

## Visão Geral
- Tema do mês: SINAPI 2026 + retrofit comercial
- Lançamento previsto: feature X em 15/05
- Meta de seguidores IG: +50

## Semana 1 (29/04 a 05/05)

### Domingo 03/05
- 📝 BLOG: "Como fazer planilha de quantitativos de obra"
- 📷 IG Feed: Repost do blog em carrossel
- 📲 Stories: 5 stories (enquete sobre processo, link pro blog)
- 📧 Email: Newsletter mensal (resumo do mês anterior)

### Segunda 04/05
- 📷 IG Feed: Card "8 horas → 5 minutos"
- 🎬 IG Reels: Tela gravada do dashboard
- 💼 LinkedIn: Texto longo "Por que decidi usar IA pra orçamento"

### Terça 05/05
- 🎬 IG Reels: Antes/depois (Excel vs AI.arq)
- 📲 Stories: Bastidores + enquete
- 💬 LinkedIn DM: 3 mensagens cold outreach

[... continua todos os dias do mês ...]
```

## Princípios do calendário

### 1. Regra de 3 (qualquer post tem 1 dos 3):
- **Educar** — ensina algo (ex: como ler quadro de esquadrias)
- **Conectar** — humano, bastidores, opinião
- **Vender** — case, demo, oferta

Distribuição saudável: 50% educar / 30% conectar / 20% vender.
NUNCA 100% vender (queima audiência).

### 2. Coordenação cross-canal
Mesmo tema pode aparecer em formatos diferentes em canais diferentes:

```
Tema: BDI

Domingo: Blog longo (1500 pal) explicando BDI
Terça: Reel curto (30s) — "BDI em 30s"
Quarta: IG Feed — Carrossel "5 erros sobre BDI"
Sexta: LinkedIn — Texto opinião sobre transparência de BDI
Sáb/Dom: Stories — 3 enquetes "Você calcula seu BDI?"
```

Cada canal pega quem prefere aquele formato. Mesmo arquiteto vê 3-4 vezes o tema mas em formatos diferentes (efeito mere-exposure aumenta lembrança).

### 3. Janelas ótimas BR

| Canal | Melhor horário | Pior horário |
|---|---|---|
| Blog | Domingo manhã | Sex à noite |
| IG Feed | Ter/Qua/Qui 18-20h | Sáb tarde |
| IG Reels | Seg/Qua/Sex 19-21h | Madrugada |
| IG Stories | Distribuído (8h, 12h, 18h, 20h) | Madrugada |
| LinkedIn | Ter/Qua 7-9h ou 17-18h | Fim de semana |
| Email | Ter ou Qui 10h | Sex à noite |

### 4. Mix de formatos visuais

Pra IG feed nunca repetir mesmo tipo de imagem 2 dias seguidos:
- Card com texto
- Carrossel educacional
- Foto real (bastidor)
- Print do dashboard
- Gráfico/visualização
- Quote / depoimento

## Exemplos de temas mensais (rotação)

### Mês 1 — "Os fundamentos"
SINAPI, BDI, memorial descritivo, levantamento básico

### Mês 2 — "Erros e armadilhas"
7 erros, BDI errado, esquecimento de disciplinas, retrofit

### Mês 3 — "Workflow profissional"
Pedido de cotação, comparativo de propostas, apresentação

### Mês 4 — "IA e produtividade"
Como IA muda arquitetura, integração com Revit, cases

### Mês 5 — "Tipologias específicas"
Retrofit comercial, residencial luxo, hospitalar, educacional

### Mês 6 — "Comercial / vendas"
Como precificar, contratos, gestão de cliente, escala

## Quando atuar proativamente

- Pedro pede "calendário pra próximo mês"
- Início de cada mês (gerar pro mês seguinte)
- Quando lança feature nova (montar campanha)
- Após análise do `marketing-strategist` que sugere reposicionamento
