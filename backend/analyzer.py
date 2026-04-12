# -*- coding: utf-8 -*-
"""Integração com Claude API para análise de pranchas de arquitetura."""
import base64
import json
import os
from pathlib import Path
import anthropic
from models import SheetType, SheetInfo, BudgetItem, ProjectData, Confidence


SYSTEM_PROMPT = """Você é um engenheiro de custos especialista em leitura de pranchas de arquitetura brasileiras e levantamento quantitativo para concorrência de obras.

Sua função é analisar imagens de plantas e legendas e extrair TODOS os itens para uma planilha orçamentária profissional, seguindo padrões brasileiros (SINAPI/TCPO).

REGRAS OBRIGATÓRIAS:

## LEVANTAMENTO DE QUANTITATIVOS
1. Extraia CADA item individualmente — nunca agrupe itens diferentes
2. TODA descrição deve ser completa: serviço + material + fabricante + referência + cor + dimensão
3. Exemplo BOM: "Pintura acrílica acetinada cor Branco Neve — Coral Dulux A.5/041, em parede de gesso acartonado"
4. Exemplo RUIM: "Pintura de parede"

## UNIDADES (nunca misturar)
- m² = áreas (pisos, paredes, forros, pinturas)
- ml = lineares (rodapés, tabicas, eletrocalhas)
- m³ = volumes (concreto, entulho)
- un = unidades (portas, luminárias, tomadas, sprinklers)
- mês = tempo (administração de obra)
- vb = verba global (mobilização, limpeza, proteção — itens que não se medem)
- cj = conjunto (ferragens complementares)
- ATENÇÃO: Limpeza de obra = vb (NÃO m²), Proteção de áreas = vb (NÃO m²)

## QUANTIDADES PARA REFORMA
- Orçar APENAS o que MUDA — não a totalidade da área
- Carpete existente que PERMANECE = NÃO orçar demolição nem reposição
- Forro que MANTÉM (ex: estúdio) = NÃO orçar demolição
- Área aberta que só muda mobiliário = NÃO orçar paredes/forro novos
- Para alvenaria: SUBTRAIR vãos de portas e janelas

## PRECISÃO
- Quando a quantidade vem da LEGENDA = confidence "confirmado"
- Quando CONTOU na planta = confidence "estimado"
- Quando ESTIMOU por área = confidence "verificar"
- Na dúvida, arredondar para CIMA (melhor sobrar que faltar)
- Adicionar 5-10% de perda/desperdício em materiais quando pertinente

## PORTUGUÊS BRASILEIRO
- Acentuação PERFEITA (é, ã, ç, ó, í, ê, â, etc.)
- Não usar "orcamento", usar "orçamento"
- Não usar "area", usar "área"

6. Cada item DEVE ter o campo "discipline" preenchido com uma destas categorias EXATAS:
   - "Serviços Preliminares"
   - "Demolição e Remoção"
   - "Fechamentos Verticais"
   - "Revestimentos"
   - "Pisos e Rodapés"
   - "Forros"
   - "Portas e Ferragens"
   - "Divisórias e Vidros"
   - "Persianas e Cortinas"
   - "Iluminação"
   - "Instalações Elétricas e Dados"
   - "Ar-Condicionado"
   - "Incêndio e Segurança"
   - "Marcenaria"
   - "Mobiliário"
   - "Complementares"

## MÉTODO DE ANÁLISE
- Você tem VISÃO PERFEITA e atenção extrema aos detalhes
- Antes de responder, analise a imagem SISTEMATICAMENTE:
  1. Varra da ESQUERDA para DIREITA, de CIMA para BAIXO
  2. Identifique CADA elemento visível
  3. Leia CADA texto/legenda completamente
  4. Conte símbolos um por um quando necessário
- Para contagem de símbolos (portas, luminárias, sprinklers):
  ATENÇÃO: benchmark mostra que IA acerta apenas 26-41% na contagem de símbolos em plantas.
  Por isso: USE AS FÓRMULAS de estimativa por m² em vez de contar símbolos.
  Se contar na planta, SEMPRE marque confidence "estimado" e adicione nota "confirmar com projeto executivo".
- Para TEXTO em legendas: IA acerta 95% — confie nas legendas e marque confidence "confirmado".
- Se não conseguir ler algo com certeza, marque confidence "verificar"

## ESTIMATIVA DE QUANTIDADES — FÓRMULAS OBRIGATÓRIAS
NUNCA retorne quantity=1 para itens que claramente têm área ou quantidade maior.
Use estas FÓRMULAS REAIS para calcular:

### PINTURA/REVESTIMENTO (fonte: TCPO/SINAPI)
- Fórmula: Área = Perímetro das paredes × Pé-direito
- REGRA TCPO para vãos: NÃO descontar vãos ≤ 2 m². Para vãos > 2 m², descontar apenas o excedente.
  Ex: porta 2,10×0,80m = 1,68 m² → NÃO desconta. Janela 3×2m = 6 m² → desconta 4 m².
- Escritório ~1200 m² útil com PD médio ~2,80m e ~120m de paredes = ~336 m² de parede
- Pintura branca (geral): ~60-70% das paredes = 200-250 m² + paredes dos dois lados = 400-500 m²
- Cores de destaque: ~5-10% da área de pintura = 20-50 m² por cor
- Cerâmicas (copas/úmidas): ~25-40 m² por tipo
- Massa corrida/selador: MESMA ÁREA da pintura total
- Perda de tinta: incluir 10% sobre a área calculada

### PORTAS
- CONTAR na planta: cada arco de abertura = 1 porta
- Se não conseguir contar, estimar por número de salas:
  - Escritório com ~15 salas + 3 copas + 2 CPDs + 2 escadas = ~22-28 portas
  - Distribuição típica: P3 (mais comum) ~30%, P1/P2 ~20%, P4/P5 ~20%, P6/P7 ~10%
- Ferragens: 1 conjunto por porta (somar total de portas)

### PISOS (fonte: norma de instalação)
- Área = Comprimento × Largura + 10% perda (instalação reta) ou + 15% (diagonal)
- REFORMA: orçar APENAS áreas que MUDAM:
  - Carpete a COMPLETAR: ~15-20% da área existente = ~150-250 m²
  - Carpete NOVO (modelo diferente): somar zonas marcadas = ~100-200 m²
  - Porcelanato (copas renovadas): ~50-80 m²
- Rodapé: perímetro interno das áreas com piso novo

### FORROS
- Mineral modular: ~25-40% da área útil (áreas open plan) = ~150-300 m²
- Gesso liso: somar áreas das salas fechadas individualmente
- Ripado: estimar pela zona hachurada na planta (geralmente ~100-170 m²)
- Tabica: perímetro interno onde há troca forro-parede = ~300-400 ml

### LUMINÁRIAS (fonte: NBR 8995 — 500 lux para escritório)
- Fórmula: N = (Iluminância × Área) / (Fluxo luminoso × fator utilização × fator manutenção)
- Regra simplificada para escritório 500 lux:
  - Downlights LED (D3, ~800 lm): ~1 a cada 3-5 m² = para 300m² → ~60-100 un
  - Lineares T5 (R4, ~2500 lm): ~1 a cada 8-12 m² = para 200m² → ~20-50 un
  - Pendentes lineares (P5, ~10.000 lm): ~1 a cada 15-20 m² = para 300m² → ~15-30 un
  - Spots/decorativos: contar individualmente na planta

### SPRINKLERS (fonte: NBR 10897 — risco leve)
- Escritório = risco leve: 1 sprinkler a cada 20,9 m² (máximo)
- Espaçamento: mínimo 1,8m, máximo 4,6m
- Para 800 m² de forro: ~800/20,9 ≈ ~38 sprinklers total
- Remanejamento em reforma: ~60-70% do total

### AR-CONDICIONADO
- Regra: 600-800 BTU/m² base + 600 BTU/pessoa + 600 BTU/eletrônico
- Para remanejamento em reforma: contar difusores na planta
- Difusores novos: ~1 a cada 15-25 m² em áreas novas

### ELÉTRICA (fonte: Pr. 500 — padrão por posição)
- Tomadas comuns: 2 por posição + ~30 extras (copas, circulação)
- Tomadas estabilizadas: 2 por posição + ~20 extras
- Dados/VOIP: 1 por posição + ~20 extras
- Interruptores: ~1-2 por sala/ambiente = ~25-35 total
- Caixa de piso (Sporim): ~60% dos pontos em piso elevado
- Réguas de tomadas: 1 por posição de trabalho

### MARCENARIA (fonte: projeto)
- Ler dimensões EXATAS da legenda (L × P × A)
- Material MDF: adicionar 5-10% de perda sobre chapas
- Cada peça = 1 un (não agrupar peças diferentes)

### DEMOLIÇÃO EM REFORMA
- Divisórias vidro: somar ml das salas EXISTENTES que serão demolidas
- Drywall: somar m² das paredes a demolir (altura × comprimento de cada trecho)
- Forro: área TOTAL menos zonas que MANTÊM forro existente
- Carpete: APENAS áreas de substituição (REMIX existente que fica NÃO conta)
- Entulho: regra geral ~1 m³ a cada 30-40 m² de demolição
- Perda em paredes de alvenaria para desconto de vãos: mesmo critério TCPO

FORMATO DE RESPOSTA — retorne APENAS JSON válido:
{
  "project_data": { ... },
  "items": [
    {
      "item_num": "1",
      "description": "Descrição completa com material, fabricante, referência",
      "unit": "m²",
      "quantity": 100,
      "observations": "Nota relevante",
      "ref_sheet": "Pr.400",
      "confidence": "confirmado",
      "discipline": "Revestimentos"
    }
  ]
}"""


PROMPT_ARQUITETURA = """Analise DETALHADAMENTE estas imagens da prancha de ARQUITETURA (Pr. 400).

Extraia TODOS os itens das legendas visíveis:

## FECHAMENTOS VERTICAIS (discipline: "Fechamentos Verticais")
- Alvenaria: bloco vazado com espessura, reboco
- Drywall: CADA tipo separado (ST, RU verde, RF rosa) com espessura, lã mineral, SEPTO/CORGA
- Laminado sobre drywall

## REVESTIMENTOS (discipline: "Revestimentos")
- CADA cor de pintura separada: Branco Neve, Cinza de Grife 50YY 63/041, tinta lousa preta, epóxi Wandepoxy, Azul Assinatura 30BB, Azul Echarpe 90BG
- CADA cerâmica: Metro White BR Eliane 20×10, Forma Slim Branco BR Eliane 30×40
- Revestimento tijolinho Arte em Ladrilhos salmão
- Painel madeira Cumaru com portas
- Massa corrida PVA + selador (preparação)

## PORTAS (discipline: "Portas e Ferragens")
Para CADA tipo P1 a P7:
- Descrição completa: dimensões, material, tipo abertura, ferragem La Fonte
- QUANTIDADE: CONTAR os arcos de abertura na planta. Cada arco = 1 porta.
  Se não conseguir contar, ESTIMAR:
  - P1 (MDF Branco TX, passa-visor, mola aérea): ~3-5 un (copas, serviço)
  - P2 (Camarão MDF Branco TX): ~2-4 un (sanitários, pequenos ambientes)
  - P3 (BP Freijó Puro, alumínio): ~4-8 un (salas individuais)
  - P4 (vidro temperado 10mm): ~2-4 un (salas com transparência)
  - P5 (dupla BP Freijó Puro): ~2-4 un (salas de reunião grandes)
  - P6 (dupla vidro + fixas, mola piso): ~1-2 un (entrada principal)
  - P7 (industrial corta-fogo aço): ~1-2 un (saídas emergência)
- Ferragens: 1 conjunto por porta = somar todas as portas
- NUNCA colocar quantity=1 para TODAS as portas

## DIVISÓRIAS (discipline: "Divisórias e Vidros")
- Vidro liso incolor h=2550mm com porta
- Vidro polarizado h=2550mm com porta
- Vidro fixo extra clear acima de parede
- Película de segurança/privacidade
- Perfil/sapato alumínio

## PERSIANAS (discipline: "Persianas e Cortinas")
- Cortina rolô Solar: Luxaflex Silver Screen, acionamento, material
- Cortina rolô Blackout: Luxaflex QN Morrison

REGRAS DE QUANTIDADE:
- Pintura Branco Neve: estimar ~400-500 m² (paredes gerais de um escritório ~1200 m²)
- Cinza de Grife: estimar ~100-150 m² se aplicado em rodapé e paredes de circulação
- Lousa preta: ~8-15 m² (1-2 paredes de sala de reunião)
- Epóxi: ~15-25 m² (copas/áreas úmidas)
- Azul Assinatura/Echarpe: ~5-20 m² cada (paredes de destaque)
- Cerâmicas: ~20-30 m² cada tipo (copas)
- Tijolinho: ~10-15 m²
- Painel Cumaru: ~30-40 m²
- Portas: CONTAR os arcos de abertura na planta — NÃO colocar 1 para cada tipo
- Massa corrida/selador: mesma área da pintura total (~450-600 m²)

Retorne JSON com TODOS os itens encontrados."""


PROMPT_FORRO = """Analise DETALHADAMENTE estas imagens da prancha de FORRO (Pr. 700).

## FORROS (discipline: "Forros")
Para cada tipo, ESTIMAR A ÁREA baseado na planta:
- Forro mineral modular (Geometrone Tegular): ~150-300 m² (áreas open plan PD=3,40m)
- Forro gesso liso h=2,55m: somar áreas das salas fechadas (~80-150 m²)
- Forro gesso liso h=2,95m: refeitório (~100-120 m²)
- Forro ripado: ~100-170 m² (zona perimetral staff/lounge) + estrutura metálica (mesma área)
- Laje aparente tratamento/pintura: ~60-100 m²
- Tabica/acabamento forro-parede: ~300-400 ml (perímetro interno)
- Cubetas gesso/drywall: ~30-50 ml
- Eletrocalha h=3,22m: ~60-100 ml
- Alçapões: ~5-10 un

## LUMINÁRIAS (discipline: "Iluminação")
Para CADA tipo de luminária na legenda, extraia:
- Código (D3, D8, R4, P5, P6, etc.)
- Modelo completo e fabricante
- Lâmpada: tipo, potência, temperatura de cor
- Driver/reator: tipo, tensão
- Acabamento e fixação
- CONTE os símbolos na planta: varra cada quadrante sistematicamente, numere cada um (D3 #1, D3 #2...) e dê o total por tipo
- Se a contagem for aproximada por sobreposição, marque confidence "estimado" e adicione nota "confirmar com quadro de cargas"

Incluir também:
- Luminária de emergência autônoma
- Trilho eletrificado
- Barra de iluminação cênica
- LED LINE perfil com fita flex
- Retrofit de luminárias existentes (se mencionado em notas)

## ITENS TÉCNICOS NO TETO (discipline conforme tipo)
- Sprinklers → "Incêndio e Segurança"
- Detectores fumaça → "Incêndio e Segurança"
- Caixa de som → "Incêndio e Segurança"
- Sensor presença → "Instalações Elétricas e Dados"
- Projetor no teto → "Complementares"
- Difusores AC → "Ar-Condicionado"
- Grelha exaustão → "Ar-Condicionado"

Retorne JSON com TODOS os itens."""


PROMPT_PISO = """Analise DETALHADAMENTE estas imagens da prancha de PISOS (Pr. 600).

## PISOS (discipline: "Pisos e Rodapés")
IMPORTANTE: Diferencie EXISTENTE (que fica) de NOVO (que precisa comprar) de COMPLETAR (lacunas).

Para CADA tipo na legenda:
- Carpete REMIX 2.0 Milliken Trímero Modular TMP141 100×100cm — EXISTENTE? COMPLETAR?
- Carpete Formwork Milliken FMK101/FWK45/FWK182 50×50cm — NOVO
- Carpete Remix Remastered MXT141 Dub w/ Apple — NOVO
- Porcelanato MUNARI Cimento AC — dimensão exata (80×80 ou 90×90?)
- Contrapiso elástico MONARQ
- Piso madeira Cumaru (existente ou novo?)
- Jardim pedrisco branco — altura exata
- Rodapé metálico h=10cm
- Rodapé MDF laca fosca branca h=80mm (marcenaria)
- Soleira/transição de piso
- Rejunte área porcelanato
- Revisão de carpete geral existente (nota da prancha)

Extraia as ÁREAS informadas: perímetro externo, área sem intervenção, área layout.

Retorne JSON com items + project_data com áreas."""


PROMPT_PONTOS = """Analise DETALHADAMENTE estas imagens da prancha de PONTOS ELÉTRICOS (Pr. 500).

## ELÉTRICA (discipline: "Instalações Elétricas e Dados")
- Pontos elétricos COMUNS (2P+T): calcular baseado em posições de trabalho
- Pontos elétricos ESTABILIZADOS
- Pontos DADOS/VOIP (RJ45 Cat6)
- Tipos de instalação: piso elevado (Sporim), alvenaria, mobiliário (réguas), teto, armário/copa
- Interruptores: simples, three-way, dimmer/polarização
- Sensor de presença
- Ponto Wi-Fi (access point)
- Quadro de força/elétrica novo
- Eletrocalha metálica (complementar ao existente)
- Eletroduto metálico/PVC
- Cabeamento elétrico geral
- Cabeamento estruturado Cat6
- Ponto para TV + armário multimídia
- IPAD para agendamento de salas

## SEGURANÇA (discipline: "Incêndio e Segurança")
- Controle de acesso FACIAL (com altura de instalação)
- Fechadura eletromagnética
- Dispositivo antipânico
- CFTV ponto + suporte
- Controle de ponto

Extraia TODAS as alturas de instalação mencionadas.
Extraia TODAS as notas (impressoras circuitos independentes, tomadas serviço, etc.)

Retorne JSON com items."""


PROMPT_MOBILIARIO = """Analise DETALHADAMENTE estas imagens da prancha de MOBILIÁRIO (Pr. 300).

## DEPARTAMENTOS (em project_data)
Liste cada departamento com nome e número de posições.

## MOBILIÁRIO INDUSTRIAL (discipline: "Mobiliário")
- CADA tipo de mesa com código, dimensões, acabamento, quantidade EXATA da legenda

## MOBILIÁRIO DECORATIVO (discipline: "Mobiliário")
- CADA item: poltrona, mesa apoio, mesa centro, banqueta — com código e quantidade EXATA

## EQUIPAMENTOS (discipline: "Mobiliário")
- Impressoras: quantidade, voltagem
- TVs: tamanho, voltagem, quantidade
- Separar EQ-01, EQ-02, EQ-03

## ASSENTOS (discipline: "Mobiliário")
- Cadeiras escritório ergonômicas (134 posições)
- Cadeiras de reunião
- Cadeira específica sala Sissi

Retorne JSON com project_data (departments) + items."""


PROMPT_MARCENARIA = """Analise DETALHADAMENTE estas imagens da prancha de MARCENARIA (Pr. 301).

## MARCENARIA SOB MEDIDA (discipline: "Marcenaria")
Para CADA peça, extraia:
- Código (M01, M02, etc.)
- Descrição completa
- Dimensões EXATAS (L×P×A em cm)
- Material: MDF, BP Freijó Puro, tampo, caixa de tomadas
- Quantidade EXATA da legenda

Itens típicos:
- Mesas de reunião módulo pé caixa (vários tamanhos)
- Expositor
- Mesa alta com nichos e prateleira
- Estantes altas com nichos (vários tamanhos — listar CADA um)
- Estante baixa
- Estante com vão para TV
- Aparador refeitório
- Marcenaria nova da copa (se mencionado)
- Painel ripado decorativo

Retorne JSON com items."""


PROMPT_DEMOLIR = """Analise DETALHADAMENTE estas imagens da prancha de DEMOLIÇÃO (Pr. 100).

## ÁREAS (em project_data)
- Área construída (perímetro externo da laje)
- Área sem intervenção
- Área utilizada para layout

## ITENS DE DEMOLIÇÃO (discipline: "Demolição e Remoção")
Separe CADA tipo:
- Remoção de divisórias de VIDRO/industriais existentes (em ml)
- Demolição de divisórias em DRYWALL/gesso (em m²)
- Demolição de alvenaria existente (em m²)
- Remoção de caixa em gesso do pilar (un) — se mencionado
- Remoção de forro existente (parcial? total?) — se há nota "manter forro"
- Remoção de forro existente (PARCIAL — verificar nota sobre manter forro do estúdio)
- Remoção de carpete (APENAS áreas de substituição — carpete REMIX 2.0 existente PERMANECE em grande parte, orçar só ~350 m² não a totalidade)
- Remoção de portas e batentes
- Remoção de rodapés
- Remoção de revestimentos cerâmicos
- Demolição de marcenaria da copa — se mencionado
- Remoção de instalações elétricas/dados
- Remoção de luminárias existentes
- Carga, transporte e bota-fora de entulho

## NOTAS ESPECIAIS (em project_data.demolition_notes)
Extraia TODAS as notas escritas na prancha, especialmente:
- "DEMOLIR SOMENTE A FORMA MODULADA. MANTER O FORRO DE GESSO"
- "DEMOLIR MARCENARIAS DA COPA E PREVER NOVA"
- "DEMOLIR CAIXA EM GESSO DO PILAR"

Retorne JSON com project_data + items."""


PROMPT_LAYOUT_NOVO = """Analise estas imagens do LAYOUT NOVO (Pr. 200).

## DADOS DO PROJETO (em project_data)
- Nome do projeto (se visível no carimbo)
- Endereço
- Arquiteto/escritório
- Áreas (construída, layout, sem intervenção)
- Total de posições de trabalho

## DEPARTAMENTOS (em project_data.departments)
Liste cada departamento com cor e número de posições.

## NOVOS AMBIENTES (em project_data.new_rooms)
Liste CADA sala nova como objeto com TODOS os campos preenchidos:
{"name": "Sala Ana Paula Andrade", "ceiling_height": "255cm", "area": 16.5}
NUNCA deixar ceiling_height ou area vazios — se não souber exato, ESTIMAR.
PDs típicos: salas fechadas=255cm, circulação=280cm, staff/open plan=340cm, projeção gesso=295cm.

## SERVIÇOS PRELIMINARES (discipline: "Serviços Preliminares")
Adicione itens padrão com estas unidades EXATAS:
- Mobilização e desmobilização de obra — UN: vb, QTD: 1
- Projeto executivo complementar — UN: vb, QTD: 1
- Administração local de obra (engenheiro + mestre) — UN: mês, QTD: 3
- Limpeza permanente e final de obra — UN: vb, QTD: 1
- Proteção de áreas sem intervenção — UN: vb, QTD: 1

ATENÇÃO: Limpeza e proteção são VERBA (vb=1), NÃO m²!

## COMPLEMENTARES (discipline: "Complementares")
- Sinalização de portas e ambientes
- Adesivagem/plotagem em vidros
- Painéis decorativos
- Pintura final de retoques
- Limpeza fina pré-entrega
- As-built / conferência final

Retorne JSON com project_data + items."""


PROMPT_LAYOUT_ATUAL = """Analise estas imagens do LAYOUT ATUAL (Pr. 201).

## ELEMENTOS EXISTENTES (em project_data.kept_elements)
Liste tudo que EXISTE HOJE como strings descritivas completas (NÃO use nomes de variáveis como "salas_fechadas"):
- "1× reunião 6 pessoas (divisória de vidro)"
- "1× sala diretor (divisória de vidro)"
- "2× salas gerente (divisórias de vidro)"
- "Open plan STAFF com estações de trabalho"
- "Refeitório — XX m² (HOJE com mesas de trabalho)"
- "Copa 1 + Copa 2 + Café + Lavagem"
- "Core (elevadores, escadas, banheiros) — sem intervenção"

Use DESCRIÇÕES completas em português, NÃO nomes de variáveis.

Retorne JSON com project_data (kept_elements como array de strings descritivas)."""


PROMPT_DET_FORRO = """Analise estas imagens do DETALHAMENTO DE FORRO (Pr. 701).

## FORRO RIPADO (discipline: "Forros")
- Área estimada do forro ripado (baseado na planta)
- Estrutura metálica / pendurais / perfis (item separado, mesma área)
- Forro removível para manutenção

## DETALHES (discipline: "Forros")
- Tipos de corte (ripado face externa, face interna)
- Materiais e acabamentos visíveis
- Luminárias integradas ao ripado

## SERRALHERIA (discipline: "Complementares")
- Barra iluminação cênica perfil "U"
- Perfil quadrado acabamento encontro com gesso

Retorne JSON com items."""


PROMPTS_POR_TIPO = {
    SheetType.ARQUITETURA: PROMPT_ARQUITETURA,
    SheetType.FORRO: PROMPT_FORRO,
    SheetType.PISO: PROMPT_PISO,
    SheetType.PONTOS: PROMPT_PONTOS,
    SheetType.MOBILIARIO: PROMPT_MOBILIARIO,
    SheetType.MARCENARIA: PROMPT_MARCENARIA,
    SheetType.DEMOLIR: PROMPT_DEMOLIR,
    SheetType.LAYOUT_NOVO: PROMPT_LAYOUT_NOVO,
    SheetType.LAYOUT_ATUAL: PROMPT_LAYOUT_ATUAL,
    SheetType.DET_FORRO: PROMPT_DET_FORRO,
}


def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def analyze_sheet(client: anthropic.Anthropic, sheet: SheetInfo) -> dict:
    prompt = PROMPTS_POR_TIPO.get(sheet.sheet_type, "Analise esta prancha de arquitetura e extraia todos os itens para orçamento. Retorne JSON com array 'items', cada item com: item_num, description, unit, quantity, observations, ref_sheet, confidence, discipline.")

    content = []

    if sheet.text_content.strip():
        content.append({
            "type": "text",
            "text": f"Texto extraído do PDF:\n{sheet.text_content[:3000]}"
        })

    for crop_path in sheet.crops[:8]:
        if os.path.exists(crop_path):
            b64 = encode_image(crop_path)
            media = "image/jpeg" if crop_path.endswith('.jpg') else "image/png"
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media, "data": b64}
            })

    content.append({"type": "text", "text": prompt})

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )

        text = response.content[0].text
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0].strip()
        else:
            json_str = text.strip()

        return json.loads(json_str)

    except json.JSONDecodeError as e:
        print(f"Erro JSON para {sheet.filename}: {e}")
        print(f"Resposta: {text[:500]}")
        return {"items": [], "error": f"JSON parse error: {e}"}
    except Exception as e:
        print(f"Erro API para {sheet.filename}: {e}")
        return {"items": [], "error": str(e)}


def analyze_all_sheets(sheets: list[SheetInfo], api_key: str, progress_callback=None) -> tuple[ProjectData, list[BudgetItem]]:
    client = anthropic.Anthropic(api_key=api_key)
    all_items = []
    project_data = ProjectData()

    # Ordenar: layout novo primeiro (pega dados do projeto), depois demolição, depois o resto
    priority = {
        SheetType.LAYOUT_NOVO: 0,
        SheetType.LAYOUT_ATUAL: 1,
        SheetType.DEMOLIR: 2,
        SheetType.ARQUITETURA: 3,
        SheetType.FORRO: 4,
        SheetType.PISO: 5,
        SheetType.PONTOS: 6,
        SheetType.MOBILIARIO: 7,
        SheetType.MARCENARIA: 8,
        SheetType.DET_FORRO: 9,
    }
    sorted_sheets = sorted(sheets, key=lambda s: priority.get(s.sheet_type, 99))

    for i, sheet in enumerate(sorted_sheets):
        if progress_callback:
            progress_callback(i, len(sorted_sheets), f"Analisando {sheet.filename}...")

        if sheet.sheet_type == SheetType.DESCONHECIDO:
            continue

        result = analyze_sheet(client, sheet)

        # Extrair dados do projeto
        def safe_float(val):
            """Converte valor para float, limpando unidades (m², cm, etc)."""
            if val is None: return 0
            s = str(val).replace('m²', '').replace('m2', '').replace('cm', '').replace(',', '').strip()
            try: return float(s)
            except: return 0

        def safe_int(val):
            s = str(val).replace('un', '').replace(',', '').strip()
            try: return int(float(s))
            except: return 0

        if "project_data" in result:
            pd = result["project_data"]
            if pd.get("total_area"): project_data.total_area = safe_float(pd["total_area"])
            if pd.get("layout_area"): project_data.layout_area = safe_float(pd["layout_area"])
            if pd.get("no_intervention_area"): project_data.no_intervention_area = safe_float(pd["no_intervention_area"])
            if pd.get("workstations"): project_data.workstations = safe_int(pd["workstations"])
            if pd.get("departments"): project_data.departments = pd["departments"]
            if pd.get("demolition_notes"): project_data.demolition_notes.extend(pd["demolition_notes"])
            if pd.get("new_rooms"): project_data.new_rooms.extend(pd["new_rooms"])
            if pd.get("kept_elements"): project_data.kept_elements.extend(pd["kept_elements"])
            if pd.get("name") and not project_data.name: project_data.name = pd["name"]
            if pd.get("address") and not project_data.address: project_data.address = pd["address"]
            if pd.get("architect") and not project_data.architect: project_data.architect = pd["architect"]

        # Extrair itens
        for item_data in result.get("items", []):
            try:
                desc = item_data.get("description", "")
                if not desc or len(desc) < 3:
                    continue

                discipline = item_data.get("discipline", "")
                valid_disciplines = [
                    "Serviços Preliminares", "Demolição e Remoção", "Fechamentos Verticais",
                    "Revestimentos", "Pisos e Rodapés", "Forros", "Portas e Ferragens",
                    "Divisórias e Vidros", "Persianas e Cortinas", "Iluminação",
                    "Instalações Elétricas e Dados", "Ar-Condicionado", "Incêndio e Segurança",
                    "Marcenaria", "Mobiliário", "Complementares"
                ]
                if discipline not in valid_disciplines:
                    discipline = "Complementares"

                conf = item_data.get("confidence", "estimado")
                if conf not in ["confirmado", "estimado", "verificar"]:
                    conf = "estimado"

                qty_raw = item_data.get("quantity", 1)
                qty = safe_float(qty_raw) if qty_raw else 1
                if qty <= 0: qty = 1

                item = BudgetItem(
                    item_num=str(item_data.get("item_num", "")),
                    description=desc,
                    unit=item_data.get("unit", "vb"),
                    quantity=qty,
                    observations=item_data.get("observations", ""),
                    ref_sheet=item_data.get("ref_sheet", f"Pr.{sheet.filename[:7]}"),
                    confidence=Confidence(conf),
                    discipline=discipline,
                )
                all_items.append(item)
            except (ValueError, KeyError, TypeError) as e:
                print(f"Erro item: {e} — {item_data}")
                continue

    if progress_callback:
        progress_callback(len(sorted_sheets), len(sorted_sheets), "Análise concluída!")

    return project_data, all_items
