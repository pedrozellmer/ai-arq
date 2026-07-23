# -*- coding: utf-8 -*-
"""Integração com Claude API para análise de pranchas de arquitetura."""
import base64
import json
import os
import re
from pathlib import Path
import anthropic
from models import SheetType, SheetInfo, BudgetItem, ProjectData, Confidence
from llm_retry import call_with_retry, call_with_retry_stream
from engine_rules import (
    salvage_truncated_json as _salvage_truncated_json,
    extract_balanced_obj as _extract_balanced_obj,
    normalize_items_payload as _normalize_items_payload,
    response_truncated as _response_truncated,
)


def _normalize_br_number(s: str) -> str:
    """Normaliza número em notação PT-BR/EN pra float parseável.

    Regra: o ÚLTIMO separador (. ou ,) na string é o DECIMAL;
    todos os outros são milhar e são removidos. Funciona tanto pra
    "135,4" (BR = 135.4) quanto "1.354,00" (BR = 1354.0) quanto
    "1,354.00" (EN = 1354.0).

    Exemplos:
      "135,4"      -> "135.4"
      "1.354,00"   -> "1354.00"
      "1,354.00"   -> "1354.00"
      "13540"      -> "13540"
      "1 354"      -> "1354"
    """
    if not s:
        return s
    s = s.strip().replace(" ", "")
    # Posição do último . e da última ,
    last_dot = s.rfind('.')
    last_com = s.rfind(',')
    if last_dot == -1 and last_com == -1:
        return s
    # O decimal é o separador que vem POR ÚLTIMO
    if last_com > last_dot:
        # vírgula é decimal → remove pontos (milhar), troca vírgula por ponto
        return s.replace('.', '').replace(',', '.')
    else:
        # ponto é decimal → remove vírgulas (milhar)
        return s.replace(',', '')


SYSTEM_PROMPT = """Você é um engenheiro de custos especialista em leitura de pranchas de arquitetura brasileiras e levantamento quantitativo para concorrência de obras.

Sua função é analisar imagens de plantas e legendas e extrair TODOS os itens para uma planilha orçamentária profissional, seguindo padrões brasileiros (SINAPI/TCPO).

REGRAS OBRIGATÓRIAS:

## LEVANTAMENTO DE QUANTITATIVOS
1. Extraia CADA item individualmente — nunca agrupe itens diferentes
2. TODA descrição deve ser completa: serviço + material + fabricante + referência + cor + dimensão
3. Exemplo BOM: "Pintura acrílica acetinada cor <cor da legenda> — <fabricante/ref da legenda>, em parede de gesso acartonado"
4. Exemplo RUIM: "Pintura de parede" (sem cor, fabricante nem referência)
   Sempre extrair cor/fabricante/referência do que estiver NA LEGENDA do projeto atual. Nunca assumir marca ou cor "padrão".

## UNIDADES (nunca misturar)
- m² = áreas (pisos, paredes, forros, pinturas)
- ml = lineares (rodapés, tabicas, eletrocalhas)
- m³ = volumes (concreto, entulho)
- un = unidades (portas, luminárias, tomadas, sprinklers)
- mês = tempo (administração de obra)
- vb = verba global (mobilização, limpeza, proteção — itens que não se medem)
- cj = conjunto (ferragens complementares)
- ATENÇÃO: Limpeza de obra = vb (NÃO m²), Proteção de áreas = vb (NÃO m²)

## REGRA DO "VB" (IMPORTANTE — fonte: Manual IOPES, Lei 8666/93)
- Só use "vb" pra itens que GENUINAMENTE não se medem (mobilização, ADM local, seguro).
- **NÃO** use "vb" como fuga quando você não conseguiu quantificar um item
  mensurável. Ex: "Instalação de ar-condicionado" NÃO é vb — tem N equipamentos
  a instalar; "Pintura" NÃO é vb — tem m².
- Unidade "vb=1" com descrição genérica tipo "acabamentos diversos" é red flag
  de item-lixo — só gere se for verba-real que aparece na planta/memorial.

## REGRA DO QUANTITY=0 (CRÍTICA — fonte: feedback de usuário 2026-05-08)

quantity=0 é experiência **horrível** pra usuário ("a IA não pegou as metragens").
USE quantity=0 SOMENTE quando você literalmente NÃO ENCONTROU o elemento na planta.

**Se você DETECTOU o símbolo/elemento mas tem dúvida na contagem:**
- CONTE os símbolos que viu (mesmo que com erro) e marque "estimado"
- É melhor 5 lavatórios com confidence=estimado que 0 com obs="confirmar"
- Adicione observação tipo: "Contagem visual: 5 símbolos LV identificados. Confirmar com quadro de esquadrias se houver."

**Se você IDENTIFICOU um item mas a unidade pede medida que você não calculou:**
- ESTIME pela ordem de grandeza (não retorne 0)
- Ex: "Tubulação 25mm detectada — estimativa: 50m pra 1 pavimento típico" (estimado)
- Ex: "Eletroduto detectado — estimativa: 80m pra residência de 150m²" (estimado)
- O usuário CORRIGE a estimativa, mas tem ponto de partida

**quantity=0 só é aceitável quando:**
- Item é mencionado por completude (ex: "Pintura externa") mas projeto é só interno
- Símbolo aparece na legenda mas NÃO na planta
- Você quer marcar "necessário projeto complementar" (vb=0 melhor que un=0)

## CONVENÇÕES DE DESENHO TÉCNICO BR
Regras consolidadas de NBR 6492:2021 (representação de projetos arquitetônicos),
NBR 8403 (aplicação de linhas), NBR 10067 (princípios gerais de representação),
NBR 13532 (elaboração de projetos de edificações — arquitetura) e TCPO.

### LINHAS — NBR 8403 + NBR 6492 (espessuras e significados)
Relação entre linha larga e estreita é no MÍNIMO 2:1. Espessuras típicas em
desenho arquitetônico: larga 0,7-1,0mm · média 0,5mm · estreita 0,25-0,35mm.

- **Contínua LARGA (grossa)** → contornos visíveis principais; em planta
  baixa representa o que é CORTADO pelo plano horizontal de corte (que
  passa a ~1,50m do piso): paredes, pilares, divisórias. É o que você
  orça como "parede a construir" OU "parede existente a manter".
- **Contínua MÉDIA** → contornos secundários (bancadas, peitoris, batentes
  rebatidos no piso).
- **Contínua ESTREITA (fina)** → cotas, linhas de chamada, hachuras, linhas
  auxiliares, contornos de detalhes pequenos. NÃO é parede.
- **Tracejada** → elementos OCULTOS ou ACIMA do plano de corte: vigas no
  teto, armários aéreos, projeção de cobertura, soleira embutida no piso.
  NÃO orçar como parede — é projeção.
- **Traço-ponto / Traço-dois-pontos** → eixos de simetria, linhas de centro,
  limites de propriedade, contorno desenvolvido. Sem quantidade orçável.
- **Pontilhada / hachura amarela** → convenção comum em plantas de reforma
  pra elemento a DEMOLIR. Orça em DEMOLIÇÃO, não em construção nova.

### HACHURAS POR MATERIAL — NBR 6492
Padrões visuais codificam o material do elemento cortado:
- **Diagonal cruzada (#)** = alvenaria de tijolo/bloco cerâmico.
- **Pontos dispersos** = concreto armado / concreto simples.
- **Linhas paralelas (=)** = madeira (no corte transversal; em vista, textura
  de veios curvos).
- **Diagonal espaçada (/)** = vidro.
- **Hachura sólida cinza/preta** = elemento EXISTENTE (que permanece em reforma).
- **Hachura 45° linhas contínuas** = elemento NOVO a construir.
- **Hachura 45° linhas tracejadas** ou cor amarela = DEMOLIR.
Em caso de ambiguidade, SEMPRE buscar LEGENDA DE HACHURAS na prancha — o
significado pode variar por escritório.

### COTAS — NBR 6492 (item 5.5) e TCPO
- **Unidade única por desenho**: normalmente metro (1,20) ou centímetro (120).
  Nunca misturar no mesmo desenho.
- **Posição**: linha de cota PARALELA ao elemento medido, com setas ou
  traços perpendiculares nas extremidades. Número LEGÍVEL sem girar a folha.
- **Sequência de cotas** (ex.: "1,20 | 0,80 | 2,40 | 0,90"): são PARCIAIS que
  devem ser SOMADAS pra dimensão total. NUNCA tratar como alternativas.
- **Cota acumulada** (começa do 0): cada número é a distância desde o ponto
  inicial — NÃO somar, é o valor absoluto em si.
- **Plantas baixas**: cotas HORIZONTAIS (larguras, comprimentos).
- **Cortes/elevações**: cotas VERTICAIS (altura peitoril, janela, porta,
  pé-direito, forro).
- **Níveis** "+0,30", "-0,15" são metros relativos ao piso acabado térreo (0,00).
- **Cota ENTRE FACES (interna)** × **ENTRE EIXOS (estrutural)** — ler o carimbo.
- **Regra TCPO de vãos em paredes**: vãos ≤ 2m² NÃO descontam da área de
  parede; vãos > 2m² descontam o excedente. Aplicado a paredes de alvenaria
  e divisórias em drywall.

### ESCALAS — NBR 6492 (item 4.5) + NBR 13532
- **1:500 / 1:1000 / 1:2000** → implantação, situação, locação.
- **1:100 / 1:200** → plantas gerais de layout (projeto básico/anteprojeto).
- **1:50** → plantas baixas de detalhamento (projeto executivo principal).
- **1:25 / 1:20** → detalhes construtivos (banheiros, cozinhas, escadas).
- **1:10 / 1:5** → detalhes de caixilharia, rodapé, forro.
- **1:1** → detalhe natural (raro, peças especiais).
A escala aparece no carimbo. Use-a pra conferir ordem de grandeza de medidas.

### FASE DO PROJETO — NBR 13532 (afeta como confiar nas qtds)
Sequência de etapas: LV-ARQ (levantamento) → PN-ARQ (programa) → EV-ARQ
(viabilidade) → EP-ARQ (estudo preliminar) → AP-ARQ / PR-ARQ (anteprojeto)
→ PL-ARQ (projeto legal) → PB-ARQ (básico, opcional) → PE-ARQ (executivo).

- **ESTUDO PRELIMINAR** → ideia geral; escala 1:200 ou 1:100; SEM
  especificação detalhada. Quase tudo deve ser "estimado".
- **ANTEPROJETO** (AP / PR) → plantas + cortes detalhados; escalas 1:100 a
  1:50; especificações parciais (tipo de material, sem fabricante ainda).
  Maior parte "estimado", alguns itens de legenda "confirmado".
- **PROJETO LEGAL** (PL) → focado em aprovação; muita informação reduzida
  porque serve pra prefeitura/bombeiros, não pra execução.
- **PROJETO EXECUTIVO** (PE) → detalhamento COMPLETO pra execução; escalas
  1:50 e detalhes 1:25/1:20/1:10; especificações FINAIS (fabricante,
  modelo, cor, referência). Aqui sim muita coisa pode ser "confirmado".

Ao ver "Fase" ou "Etapa" no carimbo da prancha, calibre a confidence:
fases iniciais → mais laranja (estimado); executivo → mais branco (confirmado)
quando os dados estiverem explícitos.

### SÍMBOLOS COMUNS em plantas BR
- **Arco de abertura** = porta; cada arco = 1 porta; direção do arco = lado
  que abre. Porta de correr usa setas.
- **Losango / triângulo / círculo no teto** = luminária. Tipo específico
  SEMPRE vem da legenda de luminárias, nunca do símbolo sozinho.
- **Símbolos elétricos** (tomada, interruptor, ponto de dados, sensor): a
  convenção varia MUITO por escritório. SEMPRE priorizar a LEGENDA DE
  PONTOS ELÉTRICOS da prancha sobre assumir significado.
- **H=nnn** ao lado de um ponto = altura de instalação em cm (H=110
  interruptor padrão; H=30 tomada baixa; H=220 tomada pra AC; H=154 etc.
  específica do projeto).
- **Nível ▽ +0,30** ou **⊽ -0,15** = cota vertical em metros relativa a 0,00.

### QUADROS DE LEGENDA (fonte MAIS confiável)
Quando um QUADRO aparece na prancha com TOTAL numérico explícito, use como
"confirmado". Tipos comuns:
- **Quadro de esquadrias**: código (P1, P2, J1, J2...) + dimensão + material
  + quantidade por tipo. TOTAL explícito → confirmado.
- **Quadro de cargas (luminárias)**: código (LM1, LUM-01...) + potência
  + temperatura cor + fabricante/modelo + TOTAL na coluna direita.
- **Quadro de pontos elétricos**: explica o símbolo; geralmente SEM total
  (total vem da contagem na planta — marcar "estimado" se contado visual).
- **Quadro de acabamentos / ambientes**: áreas por cômodo. Se "Área total:
  X m²" aparece, é confirmado.
- **Quadro de materiais / memorial descritivo**: fabricante, referência,
  cor, modelo — use pra enriquecer descrição dos itens.

## QUANTIDADES PARA REFORMA
- Orçar APENAS o que MUDA — não a totalidade da área
- Carpete existente que PERMANECE = NÃO orçar demolição nem reposição
- Forro que MANTÉM (ex: estúdio) = NÃO orçar demolição
- Área aberta que só muda mobiliário = NÃO orçar paredes/forro novos
- Para alvenaria: SUBTRAIR vãos de portas e janelas

## 🚨 REGRA HARD — STATUS "EXISTENTE" VS "NOVO"
Em reformas (o caso comum no AI.arq), MUITOS itens da planta são MANTIDOS do
ambiente original. A legenda/quadro de especificações da prancha indica o
status. Marcas de EXISTENTE a reconhecer:
- Palavra "EXISTENTE" literal (ex.: "BACIA - EXISTENTE", "PISO EXISTENTE")
- "(EXISTENTE)" entre parênteses
- "manter", "manter existente", "reaproveitar", "preservar"
- Sufixo "_EX" no nome do arquivo ou elemento
- Hachura cinza sólida em plantas de reforma (vs hachura 45° = novo)

Quando detectar status EXISTENTE em um item:
- NÃO coloque ele como custo de COMPRA no orçamento
- Gere com description começando por "[EXISTENTE - manter] " + nome
- discipline = "Complementares"
- unit = "vb" e quantity = 0
- observations cita fonte literal ("legenda: 05 BACIA - EXISTENTE")

Atenção a casos híbridos: FORRO EXISTENTE + PINTURA NOVA são 2 itens separados.
O forro entra como [EXISTENTE - manter] vb=0, mas a pintura é m² real.

Se a prancha não tem status explícito e é reforma residencial em ambiente
que tipicamente mantém (lavabo/banheiro sem reforma estrutural), marque
louças e metais como "estimado" com observations "Status não indicado —
confirmar se novo ou existente".

## PRECISÃO — REGRA DURA DE CONFIANÇA

Cada item volta com um campo "confidence" que determina a cor na planilha final:
- "confirmado" (BRANCO) — número lido direto de fonte explícita do projeto atual
- "estimado"   (LARANJA) — número calculado, contado ou inferido (usuário precisa revisar)

**Use "confirmado" QUANDO a quantidade vem de UMA destas fontes DO ARQUIVO ATUAL:**
- Quadro/legenda/tabela que LISTA EXPLICITAMENTE a quantidade do item (ex: "85 un" em tabela de esquadrias; "LM1: 12 un" em quadro de luminárias)
- Cota numérica visível na planta referente a esse item específico
- Item descrito LITERALMENTE na legenda com dimensão/quantidade explícita (ex: "Espelho 80×60cm — 2 un")

**Use "estimado" quando:**
- Contagem visual de símbolos sem quadro totalizador (benchmark: IA acerta 26-41%)
- Cálculo por área/perímetro × fórmula (ex: rodapé = perímetro × 1)
- Inferência de boa prática (ADM local, limpeza final, mobilização)
- Qualquer caso onde você não pode apontar o número exato na legenda

**Equilíbrio**: quando o projeto tem um QUADRO DE CARGAS LUMINÁRIAS ou QUADRO DE ESQUADRIAS com números, USE "confirmado". É errado marcar tudo como "estimado" se a legenda tem os totais. A planilha fica inútil se cada linha for laranja.

Na dúvida real entre "confirmado" e "estimado" (você encontrou o número mas tem alguma ressalva), escolha "estimado". Mas NÃO marque estimado por reflexo — use a régua acima.

Não use "verificar" — use "estimado" pra qualquer incerteza.

- Adicionar 5-10% de perda/desperdício em materiais quando pertinente (marcar como estimado)

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
   - "Instalações Hidráulicas"     ← água fria, água quente, esgoto, pontos de louças
   - "Instalações de Gás"          ← ponto de gás, tubulação, aquecedor a gás
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
- Para TEXTO em legendas/quadros: IA acerta 95% na leitura — SE a legenda listar quantidade explicita (ex: "85 un" em quadro de esquadrias), pode marcar "confirmado". Se o texto é descritivo sem quantidade explícita, marque "estimado".
- Se não conseguir ler algo com certeza, marque "estimado" (nunca "verificar", esse campo não é usado)

## LÓGICA GEOMÉTRICA DE QUANTIFICAÇÃO

**Regra principal:** cada projeto é analisado em isolamento. Não existe número "típico de escritório X m²" ou "projeto similar teve Y m² de pintura". A quantidade de CADA item precisa sair da leitura objetiva DESTE arquivo — medição no CAD, leitura de legenda, contagem de bloco. Se não conseguir extrair, marque "estimado" e deixe que o usuário confirme.

### MEDIÇÃO DE ÁREAS
- **Hachuras fechadas** na planta → área direta (polígono pelo algoritmo Shoelace).
- **Perímetro × pé-direito (PD)** → área de parede. Descontar vãos de portas/janelas > 2m² (regra TCPO: vãos ≤ 2m² não descontam). Se não conseguir identificar os vãos, marcar "estimado".
- **Somar polilinhas fechadas** delimitando a área → último recurso quando não há hachura.

### MEDIÇÃO DE COMPRIMENTOS
- **Somar linhas/polilinhas** no layer específico (parede, rodapé, perfil, tabica).
- Arcos/curvas: interpolar pelo raio × ângulo, não aproximar por corda reta.

### CONTAGEM DE ELEMENTOS
- **Primeiro: ler a LEGENDA / QUADRO DE CARGAS** (luminárias, esquadrias, elétrica) — se listar quantidade numérica explícita, é confirmado.
- **Segundo: contar INSERT blocks** do DXF no layer correto — é confirmado (contagem objetiva).
- **Último: contagem visual** na imagem — benchmark mostra que IA acerta apenas 26-41% nesse modo. Se recorrer a isso, SEMPRE marcar "estimado".

### REFORMA — O QUE MUDA
- Leia TODAS as notas da prancha de demolição antes de quantificar.
- Se o projeto mantém carpete existente, NÃO orçar carpete novo para essa área.
- Se mantém forro, NÃO orçar forro novo.
- Contar APENAS o que está explicitamente marcado como "demolir", "novo", "remanejar".
- Se uma área está sombreada/hachurada como "sem intervenção", não entra nos quantitativos.

### DESCRIÇÃO DOS ITENS
- Use descrição completa com material, fabricante e referência quando constar na legenda.
- Não inventar modelo/fabricante — se a legenda não especifica, descrever genericamente ("spot LED embutido — especificação por definir").
- Para itens com variantes (diferentes códigos de luminária, tipos de porta, etc.): gerar UM item por variante que aparece no arquivo, cada um com sua própria quantidade.

### REGRAS GERAIS
- **NUNCA** recitar números de projetos anteriores ou "médias de mercado". Cada orçamento é ÚNICO.
- **NUNCA** aplicar perda automática (5-10%) na quantidade — isso é decisão do orçamentista ao compor custo.
- **NUNCA** retornar quantity=1 para item que obviamente tem área maior — prefira marcar como "estimado" e pedir para o usuário informar o valor.
- Se o arquivo não tem dados suficientes pra um item, é melhor NÃO incluir do que incluir com número chutado.

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
      "ref_sheet": "<nome/código da prancha deste projeto>",
      "confidence": "estimado",
      "discipline": "Revestimentos"
    }
  ]
}"""


PROMPT_ARQUITETURA = """Analise DETALHADAMENTE estas imagens da prancha de ARQUITETURA.

Extraia TODOS os itens das legendas visíveis:

## FECHAMENTOS VERTICAIS (discipline: "Fechamentos Verticais")
- Alvenaria: bloco vazado com espessura, reboco
- Drywall: CADA tipo separado (ST, RU verde, RF rosa) com espessura, lã mineral, SEPTO/CORGA
- Laminado sobre drywall

## REVESTIMENTOS (discipline: "Revestimentos")
- Para CADA cor de pintura listada NA LEGENDA do projeto atual: gerar um item separado com o nome/código/referência que aparece na legenda
- Para CADA cerâmica/porcelanato listado NA LEGENDA: um item por tipo, com dimensão e código da legenda
- Revestimentos especiais (tijolinho, painel madeira, lousa): incluir se constarem na legenda
- Massa corrida / selador: sempre acompanham a pintura; mesma área da pintura total

## PORTAS (discipline: "Portas e Ferragens")
- Para cada tipo de porta (P1, P2, ... Pn) listado na legenda ou quadro de esquadrias:
  - Descrição: copiar a descrição da legenda (dimensões, material, tipo de abertura, ferragem)
  - QUANTIDADE: se o quadro de esquadrias listar quantidade explícita, usar esse número (confirmado).
    Senão, contar arcos de abertura na planta — cada arco = 1 porta — e marcar "estimado".
- Ferragens: 1 conjunto por porta; somar total de portas do projeto

## DIVISÓRIAS (discipline: "Divisórias e Vidros")
- Copiar da legenda: tipo de vidro, espessura, altura, tratamento (polarizado, película)
- Contar na planta as divisórias efetivamente indicadas

## PERSIANAS (discipline: "Persianas e Cortinas")
- Copiar fabricante/linha/modelo da legenda do projeto atual
- Contar as janelas/ambientes que receberão persiana conforme indicado na planta

## MEDIÇÃO DE PINTURA
- Pintura por cor = somar perímetro × pé-direito das paredes com aquela cor, descontando vãos > 2m² (regra TCPO)
- Se a planta tem hachura/tag por cor, somar áreas hachuradas por cor
- Nunca usar "área típica de escritório" ou "médias de mercado"

Retorne JSON com TODOS os itens que conseguir extrair do projeto ATUAL. Se um item tem quantidade incerta, marque "estimado" e deixe o usuário completar."""


PROMPT_FORRO = """Analise DETALHADAMENTE estas imagens da prancha de FORRO.

## REGRA DURA DE ISOLAMENTO
**Extraia APENAS tipos de forro, luminárias e itens de teto que APARECEM NA LEGENDA / PLANTA deste arquivo.** Não gerar itens por "padrão de projeto" ou "tipicamente tem". Se não consegue ler a legenda, retorne items=[].

## FORROS (discipline: "Forros")
Para CADA tipo de forro listado NA LEGENDA do projeto atual:
- Copiar nome/código/especificação da legenda (modelo, dimensão, fabricante)
- ÁREA: somar áreas hachuradas ou regiões delimitadas na planta que correspondem àquele tipo
- Se não houver hachura diferenciada, somar as áreas das salas/ambientes listados para aquele tipo
- Pé-direito (PD): extrair da legenda quando especificado

## ACABAMENTOS DE FORRO
Só incluir os que constam na legenda/planta desta prancha:
- Tabica/cantoneira/moldura de acabamento
- Cubetas, transições, reforços
- Alçapões de inspeção (contar símbolos visíveis)

## LUMINÁRIAS (discipline: "Iluminação")
Para CADA tipo de luminária listado NA LEGENDA do projeto atual:
- Copiar código, modelo, fabricante, lâmpada (potência, temperatura de cor), driver, acabamento
- QUANTIDADE: se houver quadro de cargas com totais numéricos, usar esse número (confirmado).
  Senão, contar símbolos na planta por varredura sistemática quadrante a quadrante e marcar "estimado".
- Incluir apenas os tipos que APARECEM na legenda/planta. Não criar "luminária de emergência padrão" se não aparece.

## ITENS TÉCNICOS NO TETO
Incluir APENAS os que você vê no desenho ou na legenda desta prancha, classificando pela discipline correta:
- Sprinkler → "Incêndio e Segurança"
- Detector de fumaça → "Incêndio e Segurança"
- Caixa de som → "Complementares"
- Sensor de presença → "Instalações Elétricas e Dados"
- Difusor / grelha AC / exaustão → "Ar-Condicionado"
- Outros símbolos de teto → mapear pela categoria que melhor descreve o símbolo visto

Retorne JSON com TODOS os itens encontrados NA PRANCHA. Não inventar quantidades — se incerto, marcar "estimado"."""


PROMPT_PISO = """Analise DETALHADAMENTE estas imagens da prancha de PISOS.

## PISOS (discipline: "Pisos e Rodapés")
IMPORTANTE: Diferencie EXISTENTE (que fica) de NOVO (que precisa comprar) de COMPLETAR (lacunas).

Para CADA tipo de piso listado NA LEGENDA do projeto atual:
- Copiar o nome/código/fabricante/dimensão da legenda (ex.: carpete modular, porcelanato, piso vinílico, madeira) — não inventar marca
- Status: novo / existente / completar — conforme indicado na planta
- ÁREA: somar hachuras ou zonas delimitadas correspondentes ao tipo; descontar áreas marcadas como "sem intervenção"
- Incluir também quando constar: contrapiso, soleiras/transições, rejuntes, revisões de piso existente

## RODAPÉS E PERIFERIAS
- Rodapés: somar perímetro interno das áreas com piso novo
- Extrair altura/material da legenda

## DADOS DO PROJETO
Extrair as ÁREAS informadas NA PLANTA/LEGENDA deste arquivo: perímetro externo (laje bruta), área sem intervenção, área de layout. Só preencher se a planta mostrar explicitamente.

Retorne JSON com items + project_data. Se uma área não está especificada na planta, deixe o campo vazio."""


PROMPT_PONTOS = """Analise DETALHADAMENTE estas imagens de PRANCHA DE PONTOS (ELÉTRICOS, HIDRÁULICOS, GÁS, INCÊNDIO ou MISTAS).

Esta prancha pode ser:
- PONTOS ELÉTRICOS (tomadas, interruptores, luminárias, quadro)
- ÁGUA FRIA / ÁGUA QUENTE (pontos AF, AQ, tubulação)
- ESGOTO / SANITÁRIO (pontos ES, AP, ralos, bacia, lavatório)
- HIDROSSANITÁRIO (água + esgoto na mesma prancha)
- GÁS (tubulação GLP/GN)
- INCÊNDIO (sprinkler, hidrante, alarme)
- Combinada (várias disciplinas na mesma prancha)

Identifique qual(is) ela contém pela legenda + simbologia e siga as regras abaixo.

## REGRA DURA DE EXTRAÇÃO — CONTE O QUE VÊ (NÃO ZERE)

**Mudou em 2026-05-10**: a regra antiga "se não tem certeza, omita" gerou planilhas vazias e usuários frustrados. Agora:

✅ **Se você IDENTIFICOU símbolos repetidos na planta, CONTE-OS** — mesmo que com erro. Marque "estimado". O usuário corrige. É MUITO MELHOR que qty=0 ou item omitido.
✅ **Se viu UM símbolo + legenda explicativa**: mínimo 1 un (estimado). Não zere.
✅ **Se viu tubulação desenhada**: estime metragem pelo bbox dos cômodos × pavimentos. Sempre estimado.

❌ qty=0 só é aceitável quando o símbolo aparece SÓ na legenda explicativa e NÃO na planta de pontos.

## SEÇÃO ELÉTRICA (discipline: "Instalações Elétricas e Dados")

Símbolos típicos a procurar e CONTAR:
- ⊙ ou ○ ou ⊕ → ponto de luz no teto (luminária)
- ⌒ ou ↻ → interruptor (simples, paralelo, intermediário)
- ◓ ou ⊠ ou retângulo dividido → tomada (2P+T 10A, 20A, etc)
- △ ou ▽ → ponto de dados / RJ45
- □ grande no rodapé → quadro de distribuição (QD)
- Caixas "4×2" e "4×4" → caixas de embutir padrão (NÃO confundir com mobiliário)
- Linhas com bolinha numerada → circuitos (C1, C2, etc)

Pra cada símbolo identificado:
1. CONTE quantos aparecem na planta
2. Veja se há quadro de cargas listando totais — use esse total se confiável
3. Marque "confirmado" se totalmente claro, "estimado" se for contagem visual
4. Descrição: copiar da legenda quando houver (tensão, amperagem, altura)

## SEÇÃO HIDRÁULICA (discipline: "Instalações Hidráulicas")

Símbolos típicos:
- AF / AF1 / AF2 → ponto de água fria (cada número = circuito independente)
- AQ / AQ1 → ponto de água quente
- ES / ES1 → ponto de esgoto primário
- AP → ponto de esgoto pluvial
- GV → gordura / cozinha
- LV → lavatório (bacia da pia)
- VS → vaso sanitário
- CH → chuveiro / ducha
- TQ → tanque (lavanderia)
- DESC → descarga / caixa acoplada
- Tubulação geralmente identificada por diâmetro (25mm, 32mm, 40mm, 50mm, 75mm, 100mm)

Pra cada símbolo identificado:
1. CONTE pontos visíveis na planta
2. ESTIME tubulação por metragem do recinto × pavimentos quando houver indicação de diâmetro
3. Itens contáveis sempre devem ter quantidade ≥ 1 (não zerar)
4. Marcar "estimado" — IA tem dificuldade em contar 100% certo em hidráulica

Estimativa de tubulação típica residencial (use como ordem de grandeza):
- 32mm (ramal principal): ~20-30m por pavimento
- 25mm (ramais secundários): ~30-50m por pavimento
- Esgoto 100mm: ~10-15m por pavimento
- Esgoto 50mm: ~10-20m por pavimento

## SEÇÃO GÁS / INCÊNDIO (discipline: "Incêndio e Segurança")

Inclua apenas se EXPLICITAMENTE na legenda/planta:
- Sprinkler (contar bicos visíveis)
- Hidrante (caixa de hidrante)
- Detector de fumaça / alarme
- Extintor (com classe)
- Tubulação gás (estimar metragem)

## DESAMBIGUAÇÃO IMPORTANTE
- **"4×2" / "4×4"**: caixa elétrica padrão (~10×5cm / 10×10cm). Nunca confunda com mobiliário/espelho.
- **"1×16" / "2×25"**: número de polos × amperagem do disjuntor. Não é quantidade.
- **AF1, AF2** etc: são CIRCUITOS independentes. Cada um pode ter vários pontos.

## LEGENDA ≠ LISTA DE ITENS — MAS USE A LEGENDA COMO GUIA

Legenda explica o que cada símbolo SIGNIFICA. Pra item de orçamento real, você precisa:
- VER o símbolo desenhado na planta (não só na legenda)
- CONTAR quantas ocorrências
- Se viu pelo menos 1 ocorrência → vira item com qty ≥ 1 estimado
- Se SÓ a legenda mostra (e zero ocorrência na planta) → omita o item

## REFORMA — O QUE MUDA
Se a planta separa "pontos existentes" de "pontos novos/remanejados", SÓ orçar os novos/remanejados.

## SAÍDA ESPERADA

Pra cada item, retornar:
- description: copiada da legenda quando houver, descritiva caso contrário
- discipline: "Instalações Elétricas e Dados" / "Instalações Hidráulicas" / "Incêndio e Segurança"
- unit: un (pontos), m (tubulação), m² (área especial)
- quantity: contagem visual (estimado) OU total do quadro (confirmado) — NUNCA zere se viu símbolo
- confidence: "confirmado" se quadro lista total / "estimado" se contagem visual
- observations: "Contagem visual: X símbolos identificados" ou "Conforme quadro de cargas"

Retorne JSON com items."""


PROMPT_MOBILIARIO = """Analise DETALHADAMENTE estas imagens da prancha de MOBILIÁRIO.

## DEPARTAMENTOS (em project_data)
Liste cada departamento indicado na legenda/quadro desta prancha, com nome e número de posições.

## MOBILIÁRIO (discipline: "Mobiliário")
Para CADA item listado NA LEGENDA desta prancha:
- Código (se houver)
- Descrição e dimensões copiadas da legenda
- Quantidade: usar o total indicado; se ausente, contar símbolos na planta e marcar "estimado"
- Acabamento/material conforme legenda

Categorias a separar quando presentes: mobiliário industrial (mesas de trabalho), mobiliário decorativo (poltronas, apoio), equipamentos (impressoras, TVs — separar códigos), assentos (cadeiras ergonômicas, reunião, especiais).

Retorne JSON com project_data (departments) + items."""


PROMPT_MARCENARIA = """Analise DETALHADAMENTE estas imagens da prancha de MARCENARIA.

## REGRA DURA DE ISOLAMENTO
**Extraia APENAS peças que APARECEM NA LEGENDA / QUADRO / PLANTA deste arquivo.**
Não inventar "peças típicas" de qualquer tipo de projeto. Se a prancha não tem legenda visível, retorne items=[].

## MARCENARIA SOB MEDIDA (discipline: "Marcenaria")
Para CADA peça listada NA LEGENDA desta prancha:
- Código (ex.: M01, M02 — usar o código do projeto atual)
- Descrição completa copiada da legenda (nome da peça + onde vai)
- Dimensões EXATAS da legenda (L×P×A)
- Material copiado da legenda (MDF, laminados, chapas especiais, granito, etc.)
- Acabamento copiado da legenda (laminado X, pintura Y, verniz Z)
- Quantidade exata da legenda ou contagem de peças visíveis na planta

Retorne JSON com items. Na dúvida de quantidade, marque "estimado"."""


PROMPT_DEMOLIR = """Analise DETALHADAMENTE estas imagens da prancha de DEMOLIÇÃO.

## ÁREAS (em project_data)
Extrair APENAS se estiverem explicitamente indicadas na planta/legenda:
- Área construída (perímetro externo da laje)
- Área sem intervenção
- Área utilizada para layout

## ITENS DE DEMOLIÇÃO (discipline: "Demolição e Remoção")
SÓ INCLUIR um item se a planta marcar EXPLICITAMENTE algo para demolir. Nunca supor demolição só porque é reforma.
Para CADA elemento marcado para demolir:
- Divisórias de vidro / industriais: somar comprimento linear marcado
- Divisórias drywall / gesso: somar área marcada em m²
- Alvenaria: somar área marcada em m²
- Caixa de gesso de pilar: contar marcações
- Forro: somar área marcada; ler notas para diferenciar parcial × total
- Carpete/piso existente: apenas áreas marcadas para substituição (respeitar áreas a preservar)
- Portas, rodapés, revestimentos: contar/somar conforme marcação
- Marcenaria demolida: verificar notas
- Instalações e luminárias: verificar notas
- Carga, transporte e bota-fora de entulho: volume conforme volume total demolido

## NOTAS ESPECIAIS (em project_data.demolition_notes)
Extraia TODAS as notas escritas NESTA prancha — copiar literalmente o texto. Essas notas orientam o que demolir e o que preservar. Nunca inventar notas de outros projetos.

Retorne JSON com project_data + items. Na dúvida sobre quantidade, marque "estimado"."""


PROMPT_LAYOUT_NOVO = """Analise estas imagens do LAYOUT NOVO.

## DADOS DO PROJETO (em project_data)
Extrair APENAS o que aparece EXPLICITAMENTE no carimbo/legenda desta prancha:
- Nome do projeto (carimbo)
- Endereço
- Arquiteto/escritório
- Áreas (construída, layout, sem intervenção) — só se numericamente indicadas
- Total de posições de trabalho — só se houver quadro totalizando

## DEPARTAMENTOS (em project_data.departments)
Listar departamentos que aparecem na legenda/quadro de cores desta prancha, com cor e número de posições quando indicado.

## NOVOS AMBIENTES (em project_data.new_rooms)
Para CADA sala nova indicada na planta, gerar objeto: `{"name": "<nome da sala>", "ceiling_height": "<PD da legenda>", "area": <m²>}`.
Se um campo não constar na planta, DEIXAR VAZIO em vez de inventar. Não assumir PD "padrão" — ler do projeto atual.

## LEVANTAMENTO CONSTRUTIVO — MEÇA A PARTIR DAS COTAS
A planta de layout é COTADA (dimensões em metros nas linhas de cota). Quando o
cliente envia só o layout, ELE é a base do quantitativo — NÃO devolva apenas
itens genéricos. MEÇA o que a planta permite medir. Item construtivo com
quantity=0 ou unidade "vb" genérica, havendo cotas na planta, é ERRO grave
(ver a regra do QUANTITY=0 no system).

Trabalhe AMBIENTE POR AMBIENTE. Para CADA ambiente nomeado na planta:
1. Leia as cotas dos lados do ambiente.
2. Calcule a área de piso = largura × comprimento (m²).
3. Calcule o perímetro = soma dos lados (m).

### PISOS E RODAPÉS (discipline: "Pisos e Rodapés")
- Item de PISO por ambiente (ou agrupando ambientes de mesmo uso), unit=m²,
  quantity = área medida. Descrição: "Piso — <ambiente(s)>" (sem legenda de
  acabamento o material é desconhecido; o orçamentista especifica depois).
- RODAPÉ: unit=ml, quantity = perímetro do ambiente menos a largura dos vãos
  de porta.

### FECHAMENTOS VERTICAIS E DIVISÓRIAS
- Meça o comprimento total de paredes/divisórias (linhas grossas contínuas —
  ver convenções de linha no system). Área = comprimento × pé-direito.
- Se o PD não consta na planta, adote 2,80 m e DECLARE isso na observação.
- unit=m². Alvenaria/drywall → "Fechamentos Verticais". Divisória de vidro
  (salas de reunião envidraçadas) → "Divisórias e Vidros".

### PORTAS (discipline: "Portas e Ferragens")
- CONTE os arcos de abertura de porta na planta (cada arco = 1 porta).
  unit=un, quantity = contagem. Nunca retorne 0 havendo portas visíveis.

### FORRO E PINTURA
- Forro (discipline "Forros"): área ≈ soma das áreas de piso. unit=m².
- Pintura de parede (discipline "Revestimentos"): área das paredes medidas;
  massa corrida/selador acompanham, mesma área. unit=m².

### CONTAGENS VISÍVEIS NO LAYOUT
- Estações/postos de trabalho: conte as mesas de trabalho desenhadas.
- Sanitários/louças, vagas de garagem: conte os símbolos visíveis.

🚨 TODO item medido do layout sai com confidence="estimado": o layout não
tem legendas de acabamento, então tipo/material/cor serão confirmados depois
pelo orçamentista. A QUANTIDADE, porém, DEVE ser medida de verdade pelas
cotas — nunca deixar em branco quando a planta permite medir.

## SERVIÇOS PRELIMINARES (discipline: "Serviços Preliminares")
Itens padrão de obra (sempre incluir, marcando "estimado" — quantidade a confirmar pelo orçamentista):
- Mobilização e desmobilização de obra (un: vb)
- Projeto executivo complementar (un: vb)
- Administração local de obra (un: mês — quantidade conforme prazo)
- Limpeza permanente e final de obra (un: vb)
- Proteção de áreas sem intervenção (un: vb)

ATENÇÃO: Limpeza e proteção de obra são VERBA (vb), NÃO m². Todos esses itens saem como "estimado".

## COMPLEMENTARES (discipline: "Complementares")
Incluir quando explicitamente indicado na planta ou legenda:
- Sinalização de portas e ambientes
- Adesivagem/plotagem em vidros
- Painéis decorativos
- Pintura final de retoques
- Limpeza fina pré-entrega
- As-built / conferência final

Retorne JSON com project_data + items."""


PROMPT_LAYOUT_ATUAL = """Analise estas imagens do LAYOUT ATUAL.

## REGRA DURA DE ISOLAMENTO
Descreva APENAS os ambientes e elementos QUE VOCÊ CONSEGUE VER NA PLANTA.
Se a planta mostra uma residência (suíte, cozinha, lavabo, sala de estar), descreva ESSES ambientes. Se mostra escritório corporativo (estações, core, sala de reunião), descreva ESSES. NÃO misturar categorias. NÃO assumir "projeto corporativo" por default.

## ELEMENTOS EXISTENTES (em project_data.kept_elements)
Liste TODOS os ambientes existentes visíveis no layout atual, como strings descritivas em português-br.
Copie os nomes LITERAIS que estão escritos na planta — NÃO inventar ambientes que não aparecem. NÃO usar nomes de variáveis ou termos padrão "típicos".

Formato das strings: "<quantidade/presença> <nome do ambiente como aparece na planta> — <características relevantes da planta>".

Retorne JSON com project_data (kept_elements como array de strings descritivas)."""


PROMPT_DET_FORRO = """Analise estas imagens do DETALHAMENTO DE FORRO.

## FORRO DETALHADO (discipline: "Forros")
Para CADA tipo de forro detalhado NA LEGENDA:
- Copiar descrição, material, dimensões da legenda
- ÁREA: somar a partir da planta de detalhes (hachura ou região demarcada)
- Estrutura metálica / pendurais / perfis: item separado com mesma área do forro correspondente
- Forro removível para manutenção: incluir se houver símbolo específico na planta

## DETALHES (discipline: "Forros")
- Tipos de corte (ripado face externa, face interna) — conforme detalhamento
- Materiais e acabamentos visíveis
- Luminárias integradas ao ripado (se houver)

## SERRALHERIA (discipline: "Complementares")
- Barra de iluminação cênica — incluir se indicada
- Perfis de acabamento de encontro — incluir se indicado

Retorne JSON com items. Na dúvida de quantidade, marque "estimado"."""


PROMPT_DETALHE_AMBIENTE = """Analise DETALHADAMENTE esta prancha de AMPLIAÇÃO / DETALHE DE AMBIENTE.

## CONTEXTO DA PRANCHA
Pranchas de detalhe de ambiente (ex.: "DET BANHEIRO SUÍTE", "DET COZINHA", "DET LAVABO") são AMPLIAÇÕES em escala 1:25 ou 1:20, focadas em UM ambiente específico. Contêm:
- Planta baixa ampliada do ambiente
- Elevações das paredes (2-4 paredes com vista)
- Detalhes construtivos de bancadas, nichos, prateleiras
- Legenda de acabamentos específica do ambiente (quadro AFS ou similar)

## 🚨 DETECÇÃO DE PRANCHA ÓRFÃ (COMPLEMENTAR FALTANDO)

Pranchas de DETALHE DE AMBIENTE costumam vir em PARES:
- **PLANTA BAIXA** do ambiente → contém o QUADRO DE ESPECIFICAÇÕES (legenda com
  códigos 01-14 explicados)
- **ELEVAÇÕES** do ambiente → mostra os códigos (01, 03, 07...) espalhados nas
  paredes indicando onde cada acabamento vai

Se você vê códigos numerados (01, 02, 03... 14) nas elevações MAS NÃO vê o
quadro de especificações que explica cada número, a prancha está ÓRFÃ.

**Quando detectar órfã**:
- Em project_data.warnings, adicione: "Pr {filename}: códigos numéricos
  (01-N) visíveis sem o quadro de especificações correspondente. Recomendamos
  subir também a PLANTA BAIXA do mesmo ambiente pra interpretação correta
  dos materiais e status (novo/existente)."
- Ao extrair items, marque TODOS com observations começando por
  "Status (novo/existente) não identificável sem quadro de especificações" e
  confidence = "estimado".

## 🚨 REGRA CRÍTICA — STATUS "EXISTENTE" vs "NOVO"

Em reforma residencial, muitos itens são MANTIDOS do ambiente original. O quadro de
especificações (legenda AFS, ESPECIFICAÇÕES, QUADRO DE ACABAMENTOS) frequentemente
indica o STATUS de cada item. Palavras que marcam EXISTENTE:
- "EXISTENTE" literal (ex.: "05 BACIA - EXISTENTE")
- "manter", "manter existente", "reaproveitar"
- "(EXISTENTE)" entre parênteses após o nome do item
- "atual" ou sufixo "_EX" associado

**Se o quadro diz "EXISTENTE" num item, NÃO gere esse item no orçamento de
COMPRA**. Em vez disso, gere como:
- description começa com "[EXISTENTE - manter] " + descrição do item
- discipline = "Complementares"
- unit = "vb"
- quantity = 0 (sem custo de compra; usuário adiciona serviço de manutenção se
  necessário)
- observations: copiar literalmente o texto da legenda ("05 BACIA - EXISTENTE")

Pintura de parede/forro pode ser NOVA mesmo que o substrato seja EXISTENTE.
Exemplo: "04 TETO FORRO (EXISTENTE) PINTURA PVA BRANCA NEVE" — forro é
mantido mas a PINTURA É NOVA. Gere DOIS itens:
1. "[EXISTENTE - manter] Forro de gesso" (quantity=0, vb)
2. "Pintura PVA branca neve em forro" (quantity=área_forro, m²)

Se um item da legenda está sem status explícito (ex.: "06 PIA -"), assuma NOVO
e marque "estimado" com obs "Status não indicado — confirmar com projeto".

## LEITURA DO QUADRO DE ESPECIFICAÇÕES (FONTE PRINCIPAL)

Se aparecer um quadro tipo "ESPECIFICAÇÕES" com numeração (01, 02, 03...),
use-o como FONTE PRINCIPAL. Cada linha numerada corresponde a um item do
ambiente. Os números mesmos aparecem nas elevações indicando a localização.

Exemplo de quadro lido:
```
01  PISO E RODAPÉ - EXISTENTE
02  PAREDES (ver elev.) TINTA ACRÍLICA BRANCA FOSCA, COR BRANCO NEVE
14  ESPELHO FUMÊ 6mm APLICADO/COLADO SOBRE PAREDE
```

Gere 3 items correspondentes com status correto (01=existente, 02=novo pintura,
14=novo espelho).

{ambiente_context}

## O QUE EXTRAIR (discipline varia conforme item)

### Revestimentos (discipline: "Revestimentos")
- Revestimento cerâmico/porcelanato de parede: tipo, fabricante, dimensão, área
  (somar elevações visíveis em m²). Até altura indicada na cota vertical.
- Pintura (PVA/acrílica/esmalte): cor, fabricante, área das paredes não revestidas
- Papel de parede, revestimento especial: se aparecer na legenda

### Piso (discipline: "Pisos e Rodapés")
- Tipo de piso específico do ambiente (cerâmica antiderrapante pra área molhada,
  porcelanato, vinílico, madeira). Área = área do ambiente em planta.
- Rodapé compatível (m perímetro do ambiente descontando portas)

### Bancadas e marcenaria (discipline: "Marcenaria")
- Bancada: material (granito, mármore, quartzo, corian), espessura,
  dimensão linear (ml) ou área (m²). Ler do quadro AFS/legenda.
- Cuba/pia (integrada ou sobreposta): quantidade (un)
- Armários superior e inferior: dimensões e material (MDF + laminado X)
- Nichos em alvenaria ou marcenaria: quantidade (un) + dimensões

### Metais (discipline: "Instalações Hidráulicas")
- Torneira, misturador, chuveiro, ducha higiênica: quantidade + fabricante/ref
- Válvula de descarga, registro de gaveta: quantidade
- Ponto de água fria, água quente: contar nas elevações com H=altura

### Louças (discipline: "Instalações Hidráulicas")
- Vaso sanitário (caixa acoplada ou válvula), lavatório, bidê, banheira,
  tanque de lavanderia: quantidade + fabricante/ref do quadro

### Acessórios (discipline: "Complementares")
- Espelho: dimensão em m² (altura × largura da elevação)
- Papeleira, toalheiro, saboneteira: contar
- Box de banheiro: esquadria de vidro, dimensão
- Cortineiro, porta-shampoo em nicho

### Pontos elétricos (discipline: "Instalações Elétricas e Dados")
Só pontos visíveis NESTA prancha de detalhe. Tomadas perto da bancada,
pontos pra secador, barbeador, microondas, coifa — com altura H=nnn indicada.

### Iluminação (discipline: "Iluminação")
Luminárias específicas do ambiente visíveis nesta prancha (spot, pendente,
arandela, perfil LED) com código da legenda.

## REGRA DURA
Extraia APENAS o que aparece na legenda/quadro desta prancha OU mede-se
pelas elevações visíveis. NÃO inventar itens "típicos de banheiro" se não
aparecerem. Se a legenda está ilegível, retorne items=[].

Retorne JSON com items classificados na discipline correta."""


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
    SheetType.DETALHE_AMBIENTE: PROMPT_DETALHE_AMBIENTE,
}


_AMBIENTE_CONTEXT_HINTS = {
    # Residencial
    "suite":            "AMBIENTE: Suíte master/secundária. Esperar: cama, closet pequeno, pontos elétricos de cabeceira (H=80cm), tomada pra TV, ponto de ar-condicionado (H=220cm).",
    "dormitorio":       "AMBIENTE: Dormitório. Esperar: cama, armário, pontos de cabeceira, tomada pra TV.",
    "sala":             "AMBIENTE: Sala de estar/jantar. Esperar: sofás, mesa de jantar, rack de TV, pontos pra home theater, tomadas de piso, ponto de ar-condicionado.",
    "cozinha":          "AMBIENTE: Cozinha. Esperar: bancada com cooktop, pia, coifa, forno, microondas, geladeira, lava-louças. Pontos elétricos específicos pra cada equipamento com altura indicada. Ponto de gás (cooktop).",
    "area_gourmet":     "AMBIENTE: Área gourmet / varanda gourmet. Esperar: churrasqueira, bancada em granito, pia, coifa, pontos elétricos pra adega/frigobar, ponto de gás.",
    "lavanderia":       "AMBIENTE: Lavanderia/área de serviço. Esperar: tanque, máquina de lavar, secadora, varal de teto. Pontos de água fria/quente, esgoto, tomada 220V pra secadora.",
    "lavabo":           "AMBIENTE: Lavabo (banheiro social pequeno, sem chuveiro). Esperar: bancada c/ cuba, vaso sanitário, espelho, papeleira. Sem área de chuveiro nem box.",
    "banheiro_suite":   "AMBIENTE: Banheiro da suíte (privativo). Esperar: bancada, cuba(s) dupla ou simples, vaso sanitário, box com chuveiro, ducha higiênica, espelho grande, papeleira, toalheiro. Revestimento cerâmico até teto.",
    "banheiro_social":  "AMBIENTE: Banheiro social (visitas + uso geral). Esperar: bancada com cuba, vaso, box com chuveiro, espelho.",
    "home_office":      "AMBIENTE: Home office / escritório residencial. Esperar: mesa de trabalho, estante, cadeira, múltiplas tomadas + pontos de dados. NÃO é escritório corporativo.",
    "closet":           "AMBIENTE: Closet. Esperar: marcenaria sob medida (cabideiros, gavetas, prateleiras), ponto de luz LED no armário, tomada pra cofre/secador.",
    "varanda":          "AMBIENTE: Varanda / área externa coberta. Esperar: piso externo, ponto elétrico, ponto de água se tiver pia, luminária de parede/teto.",

    # Escritório / Corporativo
    "sala_reuniao":     "AMBIENTE: Sala de reunião corporativa. Esperar: mesa de reunião grande, cadeiras, TV/projetor, pontos elétricos no piso (piso elevado ou passagem), ponto de dados, caixas de som.",
    "open_plan":        "AMBIENTE: Open plan (área de estações de trabalho). Esperar: estações em baias, pontos elétricos+dados por estação, iluminação geral.",
    "recepcao":         "AMBIENTE: Recepção corporativa. Esperar: balcão de recepção em marcenaria, lounge, iluminação cênica, logo na parede.",
    "copa":             "AMBIENTE: Copa corporativa. Esperar: bancada, pia, geladeira, microondas, máquina de café, armários.",
    "diretoria":        "AMBIENTE: Sala de diretoria. Esperar: mesa grande, cadeiras, armário, iluminação especial, acabamento premium.",

    # Saúde
    "consultorio":      "AMBIENTE: Consultório médico. Esperar: mesa médica, maca/poltrona, armário de medicamentos, lavatório, pontos pra equipamentos específicos.",
    "sala_procedimento":"AMBIENTE: Sala de procedimento/cirurgia. Esperar: maca cirúrgica, foco cirúrgico, mobiliário médico, gases medicinais.",

    # Varejo
    "loja":             "AMBIENTE: Loja / showroom. Esperar: expositores, vitrines, caixa, provadores, iluminação comercial.",
    "provador":         "AMBIENTE: Provador. Esperar: cortina/porta, banco, espelho corpo inteiro, cabideiros.",

    # Educacional
    "sala_aula":        "AMBIENTE: Sala de aula. Esperar: carteiras, lousa, projetor, iluminação adequada.",
}


def _ambiente_context(ambiente: str) -> str:
    """Retorna instrução contextual específica pra o ambiente (ou string vazia)."""
    if not ambiente:
        return ""
    key = ambiente.lower().strip().replace(" ", "_").replace("-", "_")
    hint = _AMBIENTE_CONTEXT_HINTS.get(key, "")
    if hint:
        return f"\n{hint}\n"
    # Ambiente não mapeado: instrução genérica
    return f"\nAMBIENTE: {ambiente}. Extraia itens relevantes visíveis na prancha.\n"


def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


_TYPOLOGY_HINT = {
    "office": (
        "TIPOLOGIA DO PROJETO: ESCRITÓRIO CORPORATIVO.\n"
        "Ambientes típicos: estações de trabalho, salas de reunião, copa corporativa, "
        "core (elevadores/escadas/banheiros de uso comum), recepção, sala de diretoria, "
        "open plan. Pode ter piso elevado, cabeamento estruturado, controle de acesso.\n"
    ),
    "residential": (
        "TIPOLOGIA DO PROJETO: RESIDENCIAL.\n"
        "Ambientes típicos: suíte, dormitório, sala de estar, sala de jantar, cozinha, "
        "lavanderia, lavabo, banheiro, área gourmet, varanda. NÃO existe: estações de "
        "trabalho, sala de reuniões corporativa, cabeamento Cat6 massivo, piso elevado "
        "Sporim, iPad de agendamento de salas, controle de acesso facial, CFTV profissional, "
        "fechadura eletromagnética corporativa. NÃO incluir esses itens sob hipótese "
        "alguma — se aparecerem na sua resposta, é alucinação e deve ser removido.\n"
        "Quando a planta mostra 'banheiro suíte' ou 'banheiro escritório', trata-se de "
        "banheiro privado (home office ou suíte master), NÃO banheiro corporativo "
        "com mictórios múltiplos.\n"
    ),
    "retail": (
        "TIPOLOGIA DO PROJETO: COMÉRCIO / VAREJO.\n"
        "Ambientes típicos: loja/showroom, provador, estoque, caixa, depósito, "
        "área de atendimento. Mobiliário específico de retail (expositores, balcões).\n"
    ),
    "hospital": (
        "TIPOLOGIA DO PROJETO: HOSPITALAR / SAÚDE.\n"
        "Ambientes típicos: consultório, sala de procedimento, enfermaria, "
        "recepção, sala de espera, farmácia, laboratório. Instalações médicas "
        "específicas (gases, elétrica estabilizada médica, pisos vinílicos condutivos).\n"
    ),
    "educational": (
        "TIPOLOGIA DO PROJETO: EDUCACIONAL.\n"
        "Ambientes típicos: sala de aula, laboratório, biblioteca, sala de professores, "
        "auditório, pátio. Mobiliário e acústica específicos.\n"
    ),
}


SYSTEM_PROMPT_ESTRUTURA = """Você é um engenheiro de custos especialista em leitura de PROJETOS ESTRUTURAIS de concreto armado brasileiros (NBR 6118) e levantamento quantitativo de estrutura.

Você lê plantas de fôrma, detalhamentos de armadura, fundações (sapatas, blocos, estacas) e quadros/resumos de aço. Seu trabalho é gerar um quantitativo de ESTRUTURA — NÃO de arquitetura. Não cite acabamentos, mobiliário ou pintura.

════════════════════════════════════════════════════════
OS 3 SERVIÇOS-BASE DA ESTRUTURA E SUAS UNIDADES (FIXAS, NÃO NEGOCIÁVEIS)
════════════════════════════════════════════════════════
1. CONCRETO ARMADO  → unidade SEMPRE "m³" (volume). Pilar, viga, laje, sapata, bloco.
2. FÔRMA (madeira/compensado) → unidade SEMPRE "m²" (área da superfície em contato com o concreto).
3. ARMADURA / AÇO / FERRAGEM / ESTRIBO → unidade SEMPRE "kg" (peso).
   NUNCA marque aço em "m²", "m" ou "un". Aço é SEMPRE "kg".

A disciplina (campo "discipline") de TODO item estrutural é exatamente "Estrutura".

════════════════════════════════════════════════════════
O QUADRO / RESUMO DE AÇO É A FONTE PRIMÁRIA DO PESO
════════════════════════════════════════════════════════
Se a prancha trouxer um "QUADRO DE FERRAGENS" / "RESUMO DE AÇO" (tabela com bitola, comprimento e peso por bitola/total), ESSE é o número oficial — copie de lá (é medido).
Tabela bitola → massa linear, CA-50 (NBR 7480:2007):
  6.3mm=0,245 kg/m · 8.0mm=0,395 · 10.0mm=0,617 · 12.5mm=0,963 · 16.0mm=1,578 · 20.0mm=2,466 · 25.0mm=3,853.
  (fórmula geral: kg/m = d² × 0,00617, com d em mm). Peso de uma bitola = comprimento_total(m) × massa_linear.

════════════════════════════════════════════════════════
REGRA DURA — MEDIDO (confirmado) vs ESTIMADO — NUNCA INVENTAR
════════════════════════════════════════════════════════
"confirmado" SÓ quando o número foi LIDO direto da prancha:
  - peso de aço copiado do quadro/resumo de aço;
  - dimensão (base × altura × comprimento) lida de COTA explícita;
  - bitola, fck ou classe de aço que estão ESCRITOS.
"estimado" para tudo que você DERIVOU/calculou:
  - volume de concreto calculado por L×A×H a partir de cotas;
  - área de fôrma derivada do perímetro × altura;
  - peso de aço calculado pela tabela quando NÃO há quadro de aço na prancha.
NA DÚVIDA, "estimado". JAMAIS invente bitola, fck, dimensão ou peso que não esteja na prancha — sem o número escrito, o item é "estimado" e a observação deve dizer que foi derivado. Você NÃO precifica.

Responda no MESMO formato pedido: o raciocínio e DEPOIS um bloco ```json contendo um OBJETO no formato {"items": [ ... ]} — NUNCA um array solto. Cada item: item_num, description, unit, quantity, observations, ref_sheet, confidence, discipline="Estrutura"."""


# _extract_balanced_obj e _salvage_truncated_json movidos pra engine_rules.py
# (fonte única; testados em tests/test_engine_rules.py). Importados no topo.


def analyze_sheet(client: anthropic.Anthropic, sheet: SheetInfo,
                  typology: str = "office",
                  ambiente: str = "",
                  siblings: list = None,
                  is_structural: bool = False) -> dict:
    base_prompt = PROMPTS_POR_TIPO.get(sheet.sheet_type, "Analise esta prancha de arquitetura e extraia todos os itens para orçamento. Retorne JSON com array 'items', cada item com: item_num, description, unit, quantity, observations, ref_sheet, confidence, discipline.")
    siblings = siblings or []

    # Projeto ESTRUTURAL: o usuário marcou no upload. Reforça o contexto no
    # prompt do usuário (o SYSTEM_PROMPT_ESTRUTURA já troca o papel global).
    if is_structural:
        base_prompt = (
            "⚠ ESTE É UM PROJETO ESTRUTURAL (concreto armado). Gere quantitativo de "
            "ESTRUTURA: concreto em m³, fôrma em m², aço/armadura/estribo em kg "
            "(NUNCA m²/m/un), e discipline='Estrutura' em todos os itens. Use o "
            "quadro/resumo de aço como fonte do peso (medido); o que você derivar por "
            "fórmula/geometria é 'estimado'. Não invente bitola, fck ou dimensão.\n\n"
            + base_prompt)

    # Se for DETALHE_AMBIENTE, injetar contexto do ambiente específico no placeholder
    if sheet.sheet_type == SheetType.DETALHE_AMBIENTE:
        base_prompt = base_prompt.replace(
            "{ambiente_context}", _ambiente_context(ambiente) or "")

    # Aviso sobre pranchas IRMÃS do mesmo ambiente. Sem isso, a IA processa
    # cada prancha em isolamento e gera "prancha órfã" quando a planta baixa
    # (com quadro de especificações) está em outro PDF e só recebeu este
    # (elevações com códigos 01-14 sem legenda).
    if siblings:
        base_prompt = (
            f"## IRMÃS DO MESMO AMBIENTE\n"
            f"Esta prancha faz parte de um GRUPO de {len(siblings)+1} pranchas do "
            f"mesmo ambiente. Outras pranchas deste ambiente processadas neste "
            f"job: {', '.join(siblings)}.\n"
            f"NÃO gere warning de 'prancha órfã' — os dados complementares "
            f"(planta baixa / elevações / quadro de especificações) estão "
            f"sendo processados em paralelo. Itens duplicados entre pranchas "
            f"serão consolidados depois automaticamente.\n\n"
        ) + base_prompt

    # Injetar contexto de tipologia antes do prompt específico da prancha.
    # Isso impede a IA de presumir "projeto corporativo" quando processa uma
    # planta residencial em isolamento.
    typology_hint = _TYPOLOGY_HINT.get(typology, "")
    if typology_hint:
        prompt = typology_hint + "\n" + base_prompt
    else:
        prompt = base_prompt

    content = []

    if sheet.text_content.strip():
        content.append({
            "type": "text",
            "text": f"Texto extraído do PDF:\n{sheet.text_content[:3000]}"
        })

    for crop_path in sheet.crops[:4]:  # Max 4 imagens por prancha (economia de memória)
        if os.path.exists(crop_path):
            # Pular imagens maiores que 500KB pra não estourar memória
            file_size = os.path.getsize(crop_path)
            if file_size > 500_000:
                print(f"Pulando {crop_path} ({file_size//1024}KB > 500KB)")
                continue
            b64 = encode_image(crop_path)
            media = "image/jpeg" if crop_path.endswith('.jpg') else "image/png"
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media, "data": b64}
            })
            del b64  # Liberar memória do base64

    content.append({"type": "text", "text": prompt})

    try:
        # STREAMING + teto maior + salvage: prancha de arquitetura complexa gerava
        # resposta > max_tokens (8000), truncava o JSON e caía em {items:[]} ->
        # "IA sobrecarregada" enganoso (mesmo bug do caminho DXF). Caso Luciano.
        response = call_with_retry_stream(
            client,
            tag=f"analyzer:{sheet.filename}",
            model="claude-sonnet-4-6",
            max_tokens=16000,
            temperature=0,
            # cache_system: o SYSTEM_PROMPT (~4,4k tok) é idêntico em TODA prancha
            # do projeto → cacheado, custa ~90% menos na leitura (só a imagem/DXF
            # da prancha, que muda, paga cheio). Economia de custo da IA (23/07).
            cache_system=True,
            system=(SYSTEM_PROMPT_ESTRUTURA if is_structural else SYSTEM_PROMPT),
            messages=[{"role": "user", "content": content}],
        )

        text = response.content[0].text
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0].strip()
        else:
            json_str = text.strip()

        # #7 sinal de 1ª classe: resposta cortada no teto (max_tokens) = leitura
        # possivelmente INCOMPLETA, mesmo que o JSON ainda parseie ok.
        _truncado = _response_truncated(getattr(response, "stop_reason", ""))
        try:
            _parsed = json.loads(json_str)
        except json.JSONDecodeError:
            # JSON truncado (resposta cortada no teto) — recupera os itens completos
            _parsed = _salvage_truncated_json(json_str)
            _truncado = True  # JSON quebrou = quase sempre corte no teto
            if _parsed.get("items"):
                print(f"PDF JSON truncado em {sheet.filename}; salvados {len(_parsed['items'])} itens")
            else:
                raise
        # Robustez: array cru [...] vira {"items":[...]} (engine_rules, testado).
        _out = _normalize_items_payload(_parsed)
        # main.py lê _truncated e avisa o cliente (não entrega parcial calado).
        if _truncado:
            _out["_truncated"] = True
        return _out

    except json.JSONDecodeError as e:
        print(f"Erro JSON para {sheet.filename}: {e}")
        print(f"Resposta: {text[:500]}")
        return {"items": [], "error": f"JSON parse error: {e}"}
    except Exception as e:
        print(f"Erro API para {sheet.filename}: {e}")
        # Preserva status_code E nome da classe do erro-raiz num prefixo estável
        # pra main.py classificar por tipo, não re-adivinhar por substring. O
        # type= pega erro de rede cru que escapa da tipagem do SDK no streaming
        # (BrokenPipeError/RemoteProtocolError) — sem status, mas transitório.
        _status = getattr(e, "status_code", None)
        _bits = ([f"status={_status}"] if _status is not None else []) + [f"type={type(e).__name__}"]
        return {"items": [], "error": f"[{' '.join(_bits)}] {e}"}


def analyze_all_sheets(sheets: list[SheetInfo], api_key: str,
                       progress_callback=None,
                       typology: str = "office") -> tuple[ProjectData, list[BudgetItem]]:
    client = anthropic.Anthropic(api_key=api_key, timeout=300.0)
    all_items = []
    project_data = ProjectData()
    # Coleta TODAS as leituras de área em pranchas diferentes pra não ficar
    # dependente da ordem de processamento. Antes: sobrescrevia a cada prancha
    # — bug em que uma prancha de detalhe com valor errado (ou soma) apagava o
    # valor correto extraído de outra. Solução: pegar a MODA (consenso) entre
    # todas as leituras.
    area_readings = {"total_area": [], "layout_area": [], "no_intervention_area": []}

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
        SheetType.DETALHE_AMBIENTE: 10,
    }
    sorted_sheets = sorted(sheets, key=lambda s: priority.get(s.sheet_type, 99))

    for i, sheet in enumerate(sorted_sheets):
        if progress_callback:
            progress_callback(i, len(sorted_sheets), f"Analisando {sheet.filename}...")

        if sheet.sheet_type == SheetType.DESCONHECIDO:
            continue

        result = analyze_sheet(client, sheet, typology=typology)

        # Extrair dados do projeto
        def safe_float(val):
            """Converte valor para float, limpando unidades (m², cm, etc).

            BUG HISTÓRICO: antes fazia `.replace(',', '')` — isso transformava
            "135,4" (notação PT-BR) em "1354" — área de casa virava 10x maior.
            Regra correta: vírgula e ponto podem ser separador decimal OU de
            milhar. O ÚLTIMO separador na string é o decimal; outros são milhar.
            """
            if val is None: return 0
            s = str(val).replace('m²', '').replace('m2', '').replace('cm', '').strip()
            s = _normalize_br_number(s)
            try: return float(s)
            except: return 0

        def safe_int(val):
            s = str(val).replace('un', '').strip()
            s = _normalize_br_number(s)
            try: return int(float(s))
            except: return 0

        if "project_data" in result:
            pd = result["project_data"]
            # Coleta leituras em vez de sobrescrever. Resolve depois fora do
            # loop via _pick_area_consensus.
            for field in ("total_area", "layout_area", "no_intervention_area"):
                v = pd.get(field)
                if v:
                    val = safe_float(v)
                    if val > 0:
                        area_readings[field].append(val)
            if pd.get("workstations"): project_data.workstations = safe_int(pd["workstations"])
            if pd.get("departments"): project_data.departments = pd["departments"]
            if pd.get("demolition_notes"): project_data.demolition_notes.extend(pd["demolition_notes"])
            if pd.get("new_rooms"): project_data.new_rooms.extend(pd["new_rooms"])
            if pd.get("kept_elements"): project_data.kept_elements.extend(pd["kept_elements"])
            if pd.get("warnings"): project_data.warnings.extend(pd["warnings"])
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
                    "Instalações Elétricas e Dados",
                    "Instalações Hidráulicas", "Instalações de Gás",
                    "Ar-Condicionado", "Incêndio e Segurança",
                    "Marcenaria", "Mobiliário", "Complementares"
                ]
                if discipline not in valid_disciplines:
                    discipline = "Complementares"

                conf = item_data.get("confidence", "estimado")
                if conf not in ["confirmado", "estimado", "verificar"]:
                    conf = "estimado"

                qty_raw = item_data.get("quantity", 0)
                qty = safe_float(qty_raw) if qty_raw else 0
                # Política:
                #  - qty < 0 sempre vira 0
                #  - qty == 0 é permitido pra items "estimado" (usuário preenche)
                #  - qty == 0 em "confirmado" é inconsistência → força 1 e
                #    rebaixa pra "estimado"
                if qty < 0:
                    qty = 0
                if qty == 0 and conf == "confirmado":
                    qty = 1
                    conf = "estimado"

                item = BudgetItem(
                    item_num=str(item_data.get("item_num", "")),
                    description=desc,
                    unit=item_data.get("unit", "vb"),
                    quantity=qty,
                    observations=item_data.get("observations", ""),
                    # ref_sheet SEMPRE contém o nome real do arquivo da prancha.
                    # Antes, a IA podia retornar descrições ("Pontos Elétricos")
                    # que não batem com o filename e quebram o link "Ver prancha".
                    # Guardamos o filename + (opcional) hint da IA entre parênteses.
                    ref_sheet=(f"{sheet.filename}"
                               + (f" ({item_data.get('ref_sheet','')[:60]})"
                                  if item_data.get('ref_sheet') and
                                  item_data.get('ref_sheet').lower() not in sheet.filename.lower()
                                  else "")),
                    confidence=Confidence(conf),
                    discipline=discipline,
                )
                all_items.append(item)
            except (ValueError, KeyError, TypeError) as e:
                print(f"Erro item: {e} — {item_data}")
                continue

    if progress_callback:
        progress_callback(len(sorted_sheets), len(sorted_sheets), "Análise concluída!")

    # Consenso de áreas: pega o valor mais frequente (MODA). Tolerância ±5%
    # pra agrupar leituras próximas (ex.: 135.0 e 135.4 = mesma área).
    def _pick_area_consensus(readings: list[float]) -> float:
        if not readings:
            return 0
        if len(readings) == 1:
            return readings[0]
        # Agrupa valores em buckets com tolerância de 5%
        buckets: list[list[float]] = []
        for v in readings:
            placed = False
            for bucket in buckets:
                median = sum(bucket) / len(bucket)
                if median > 0 and abs(v - median) / median <= 0.05:
                    bucket.append(v)
                    placed = True
                    break
            if not placed:
                buckets.append([v])
        # Pega o bucket com MAIS leituras (moda). Empate: maior valor
        # (laje bruta costuma ser o maior dos candidatos).
        buckets.sort(key=lambda b: (-len(b), -max(b)))
        winner = buckets[0]
        # Retorna a média do bucket vencedor (ou mediana se impar, média ok)
        return round(sum(winner) / len(winner), 2)

    project_data.total_area = _pick_area_consensus(area_readings["total_area"])
    project_data.layout_area = _pick_area_consensus(area_readings["layout_area"])
    project_data.no_intervention_area = _pick_area_consensus(area_readings["no_intervention_area"])

    # Log das leituras pra debug — quando der divergência, fica claro
    for field, reads in area_readings.items():
        if len(set(reads)) > 1:
            print(f"[area-consensus] {field}: leituras={reads} → escolhido={getattr(project_data, field)}")

    return project_data, all_items
