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

**NUNCA ESTIMAR COMO "CONFIRMADO". Só use "confirmado" quando a quantidade vem de UMA das fontes abaixo:**
- Quadro/legenda/tabela que LISTA EXPLICITAMENTE a quantidade do item (ex: "85 un" em tabela de esquadrias)
- Cota numérica visível na planta referente a esse item específico

**TUDO o que não for isso deve ser "estimado" (aparecerá em laranja pro usuário confirmar):**
- Contagem visual de símbolos (benchmark: IA acerta 26-41%) → SEMPRE estimado
- Cálculo por área/perímetro × fórmula → SEMPRE estimado
- Fórmulas/números calibrados por fornecedor de outros projetos → SEMPRE estimado (nunca usar valores de outro projeto)
- Qualquer quantidade inferida de convenção ou boa prática → SEMPRE estimado
- Itens "padrão de obra" (ADM local, limpeza final) → SEMPRE estimado

Na dúvida entre "confirmado" e "estimado", ESCOLHA "estimado". É preferível 100 itens laranja que o usuário confirma um a um do que 1 item branco com número inventado.

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

## FORROS (discipline: "Forros")
Para CADA tipo de forro listado NA LEGENDA do projeto atual:
- Copiar nome/código/especificação da legenda (modelo, dimensão, fabricante)
- ÁREA: somar áreas hachuradas ou regiões delimitadas na planta que correspondem àquele tipo
- Se não houver hachura diferenciada, somar as áreas das salas/ambientes listados para aquele tipo
- Pé-direito (PD): extrair da legenda quando especificado
Tipos comuns a buscar (mas SÓ incluir se estiverem na planta): forro mineral modular, forro gesso liso, forro ripado, laje aparente tratada.

## ACABAMENTOS DE FORRO
- Tabica/cantoneira de acabamento: somar perímetro interno dos ambientes com forro
- Cubetas, transições, reforços: buscar na legenda
- Alçapões de inspeção: contar símbolos específicos na planta

## LUMINÁRIAS (discipline: "Iluminação")
Para CADA tipo de luminária listado NA LEGENDA do projeto atual:
- Copiar código, modelo, fabricante, lâmpada (potência, temperatura de cor), driver, acabamento
- QUANTIDADE: se houver quadro de cargas com totais numéricos, usar esse número (confirmado).
  Senão, contar símbolos na planta por varredura sistemática quadrante a quadrante e marcar "estimado".
- Incluir luminárias de emergência, trilhos, barras cênicas, perfis LED quando constarem

## ITENS TÉCNICOS NO TETO (discipline conforme tipo)
- Sprinklers → "Incêndio e Segurança"
- Detectores de fumaça → "Incêndio e Segurança"
- Caixa de som / sonorização → "Complementares"
- Sensor de presença → "Instalações Elétricas e Dados"
- Projetor multimídia → "Complementares"
- Difusores / grelhas AC → "Ar-Condicionado"
- Grelha de exaustão → "Ar-Condicionado"

Retorne JSON com TODOS os itens encontrados. Não inventar quantidades — se incerto, marcar "estimado"."""


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

## MARCENARIA SOB MEDIDA (discipline: "Marcenaria")
Para CADA peça listada NA LEGENDA desta prancha:
- Código (ex.: M01, M02 — usar o código do projeto atual)
- Descrição completa
- Dimensões EXATAS da legenda (L×P×A)
- Material copiado da legenda (MDF, laminados, chapas especiais)
- Quantidade exata da legenda

Tipos comuns a buscar (SÓ incluir se aparecerem na planta/legenda): mesas de reunião, expositores, estantes de diferentes alturas, aparadores, marcenaria de copa, painéis decorativos.

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

## ELEMENTOS EXISTENTES (em project_data.kept_elements)
Liste tudo que EXISTE HOJE na planta do projeto atual como strings descritivas em português. Copiar o que está na planta — NÃO usar nomes de variáveis nem inventar ambientes.
Exemplos de formato: "1× sala de reunião 6 pessoas (divisória de vidro)", "Open plan staff com estações de trabalho", "Core (elevadores, escadas, banheiros) — sem intervenção".

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


def analyze_sheet(client: anthropic.Anthropic, sheet: SheetInfo) -> dict:
    prompt = PROMPTS_POR_TIPO.get(sheet.sheet_type, "Analise esta prancha de arquitetura e extraia todos os itens para orçamento. Retorne JSON com array 'items', cada item com: item_num, description, unit, quantity, observations, ref_sheet, confidence, discipline.")

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
