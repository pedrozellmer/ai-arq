# -*- coding: utf-8 -*-
"""Integração com Claude API para análise de pranchas de arquitetura."""
import base64
import json
import os
from pathlib import Path
import anthropic
from models import SheetType, SheetInfo, BudgetItem, ProjectData, Confidence
from llm_retry import call_with_retry


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

## QUANTIDADES PARA REFORMA
- Orçar APENAS o que MUDA — não a totalidade da área
- Carpete existente que PERMANECE = NÃO orçar demolição nem reposição
- Forro que MANTÉM (ex: estúdio) = NÃO orçar demolição
- Área aberta que só muda mobiliário = NÃO orçar paredes/forro novos
- Para alvenaria: SUBTRAIR vãos de portas e janelas

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


PROMPT_PONTOS = """Analise DETALHADAMENTE estas imagens da prancha de PONTOS ELÉTRICOS.

## REGRA DURA DE ISOLAMENTO
**Extraia APENAS o que APARECE EXPLICITAMENTE NA LEGENDA / QUADRO DE CARGAS / PLANTA deste arquivo.**
Não gere item por "tipicamente tem em projeto assim". Se a legenda não lista um ponto específico, ele NÃO entra. Se você não consegue ler a legenda, retorne items=[] em vez de chutar.

## LEGENDA DE SÍMBOLOS ≠ LISTA DE ITENS
**CRÍTICO**: uma LEGENDA de símbolos (retângulo explicando "○ = tomada 2P+T, ● = ponto de dados, △ = interruptor, etc.") **NÃO é uma lista de itens a orçar**. É só referência visual. Você só deve criar um item de orçamento quando:
- O símbolo aparece contado na planta (ex: você consegue contar 15 tomadas desenhadas)
- OU o quadro de cargas dá o TOTAL explícito ("Tomadas 2P+T: 15 un")

Se você só vê a entrada na legenda sem conseguir contar ocorrências na planta NEM ver número total, NÃO crie o item. É pior incluir item com qty=1 genérica ("água fria = 1 un") do que omitir.

Exemplo ERRADO (não fazer):
- "Água fria — 1 un — conforme legenda" ← a legenda só explica o símbolo ◐
- "Disjuntor 1×16 — 1 un — conforme legenda" ← legenda de quadro elétrico
- "Espelho 4×2 — 1 un" ← "4×2" é caixa elétrica 10×5cm, NÃO é espelho real

Exemplo CORRETO:
- "Tomada 2P+T 10A h=30cm — 15 un — contadas na planta de pontos" (com contagem de verdade)

## DESAMBIGUAÇÃO DE NOTAÇÕES
- **Caixa elétrica "4×2"**: padrão brasileiro (~10cm×5cm). Nunca confunda com dimensões de mobiliário, espelho ou quadro.
- **Caixa "4×4"**: padrão (~10cm×10cm), idem.
- **Disjuntor "1×16"** ou "2×25": "1×" é número de polos, "16" é amperagem. Não é quantidade.

## ELÉTRICA (discipline: "Instalações Elétricas e Dados")
Pra cada símbolo elétrico desenhado na planta OU listado na legenda (tomadas, interruptores, pontos de dados, caixas de saída, sensores):
- Copiar a descrição EXATA como está na legenda (tensão, amperagem, altura, localização)
- Agrupar por tipo/código
- Quantidade: contagem objetiva dos símbolos no layer correspondente ou total do quadro de cargas
- Altura de instalação: só se estiver escrita na planta/legenda

## SEGURANÇA (discipline: "Incêndio e Segurança")
Só incluir itens de segurança se aparecerem EXPLICITAMENTE na legenda deste arquivo (ex: sprinkler, detector de fumaça, alarme, extintor, CFTV). NÃO presumir controle de acesso, fechadura eletromagnética, câmera etc se a planta não mostra.

## QUANDO NÃO TEM LEGENDA LEGÍVEL
Se a imagem não tem legenda legível e você só vê planta de pontos sem tags claras:
- Retorne APENAS os tipos que consegue identificar com certeza absoluta pelo símbolo desenhado
- Marque todos como "estimado"
- NÃO preencha lista genérica do tipo "projeto corporativo típico"

## REFORMA — O QUE MUDA
Se a planta separa "pontos existentes" de "pontos novos/remanejados", SÓ orçar os novos/remanejados.

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


def analyze_sheet(client: anthropic.Anthropic, sheet: SheetInfo,
                  typology: str = "office") -> dict:
    base_prompt = PROMPTS_POR_TIPO.get(sheet.sheet_type, "Analise esta prancha de arquitetura e extraia todos os itens para orçamento. Retorne JSON com array 'items', cada item com: item_num, description, unit, quantity, observations, ref_sheet, confidence, discipline.")

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
        response = call_with_retry(
            client,
            tag=f"analyzer:{sheet.filename}",
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


def analyze_all_sheets(sheets: list[SheetInfo], api_key: str,
                       progress_callback=None,
                       typology: str = "office") -> tuple[ProjectData, list[BudgetItem]]:
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

        result = analyze_sheet(client, sheet, typology=typology)

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
