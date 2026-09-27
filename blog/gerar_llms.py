# -*- coding: utf-8 -*-
"""O /llms.txt, gerado junto com o blog (auditoria de aquisição de 26/09, item 3).

Antes era escrito à mão e ficou para trás: em 27/09 listava 16 dos 24 posts
publicados. Agora o generate.py chama `montar()` e o deploy diário o regenera —
post que publica hoje entra hoje; post agendado não entra antes da data.

Cada post tem a SUA linha curada em LINHAS (seção, título, resumo). A guarda
backend/tests/test_llms_txt_e_gerado.py exige linha para TODO post do
posts.json, inclusive os agendados: escreveu post novo, escreva a linha dele
aqui. Sem linha, o post ainda entra (em "Outros artigos", com a description),
mas o CI reprova.

Este arquivo é .py de propósito: o deploy apaga todo .py do site servido, então
o texto-fonte não vira uma cópia pública do llms.txt.
"""

# Mexeu no CABECALHO? Atualize a data: ela entra no "Atualizado em".
REVISADO_EM = "2026-09-27"

CABECALHO = "# AI.arq\n\n> A AI.arq lê a prancha de CAD que o profissional já tem (DWG, DXF ou PDF) e devolve uma planilha de quantitativos por disciplina, com código SINAPI de referência nos itens em que há correspondência e cada linha marcada como MEDIDO (saiu da geometria do desenho) ou ESTIMADO (precisa de conferência). É um SaaS brasileiro, em beta aberto, para engenheiros, orçamentistas e arquitetos.\n\nO que entregamos é QUANTIDADE. A planilha traz item, unidade, quantidade, descrição e o código SINAPI de referência nos itens em que há correspondência confiável (os sem par vêm sinalizados), organizada em até 18 disciplinas — entre elas demolição, acabamentos, piso, elétrica, hidráulica, gás, climatização, incêndio, marcenaria e mobiliário. Aceitamos DXF, DWG e PDF exportado direto do CAD. O DXF costuma medir mais. PDF vetorial também é lido — o motor mede a geometria quando dá e a IA lê textos e legendas —, mas tudo que vem de PDF sai como ESTIMADO — é regra nossa: a escala de um PDF vem de uma declaração (o carimbo), e mesmo quando as cotas conferem a gente não sela número de PDF como medido. Planta escaneada, fotografada ou plotada como imagem não permite medir, porque vira pixel. Cada linha volta rotulada: MEDIDO quando a quantidade saiu da geometria do desenho, ESTIMADO quando veio de inferência e precisa ser revisada antes do uso. Não é preciso traçar nem clicar em cima do desenho, não é preciso ter AutoCAD e não há plugin: o arquivo é enviado pelo site e a planilha volta pronta para download.\n\nDocumentos que saem do mesmo quantitativo:\n\n- Rascunho de memorial descritivo, organizado por disciplina na ordem da obra, com a quantidade e a origem de cada item (medido do CAD ou estimativa a confirmar). O que o desenho não informa vem em campos [A PREENCHER]: endereço e proprietário, o RRT/ART do responsável técnico e, em cada disciplina, o que falta especificar (por exemplo traço do concreto e sondagem, argamassas, quadros de cargas, marcas e método executivo). O rascunho não cita norma nenhuma. Sai em Word ou PDF, com carimbo RASCUNHO, e não substitui o memorial assinado (RRT/ART).\n- Cronograma FÍSICO da obra: etapas, prazos e peso de cada uma, a partir do quantitativo. Não calcula preço: se o profissional informar o valor de cada etapa, o cronograma distribui esse valor mês a mês.\n\nO que a AI.arq NÃO faz (registrado aqui para evitar descrição errada):\n\n- Não damos preço de obra. A planilha sai SEM preços preenchidos. Quem precifica é o orçamentista ou o próprio profissional, usando a referência SINAPI como ponto de partida.\n- Não substituímos o profissional. O resultado é insumo de trabalho e exige conferência por profissional habilitado — é exatamente por isso que cada linha vem marcada como MEDIDO ou ESTIMADO.\n- Não somos BIM e não exigimos BIM. Não geramos modelo 3D e não é preciso ter Revit: lemos o desenho 2D que já existe. Não lemos .rvt nem .ifc; nesses casos, exporte para DWG ou DXF.\n- Não somos plugin de CAD. Roda no navegador.\n- Não somos a Caixa nem o IBGE. A SINAPI é usada como referência pública de código e descrição de serviço.\n- Não inventamos o que o desenho não informa. Sem cota, sem escala confirmada ou sem pé-direito, a linha volta zerada ou marcada como estimativa, e não preenchida com um número plausível.\n\nCondição comercial: durante o beta, o uso é GRÁTIS e ILIMITADO, sem cartão de crédito — todos os projetos, não só o primeiro, de qualquer tamanho. Nada é cobrado hoje. A tabela prevista para depois do beta está publicada na página de preços — é uma previsão e pode mudar —, e o aviso vem antes de qualquer cobrança começar.\n\nIn English: AI.arq is a Brazilian SaaS that reads the 2D CAD sheets a professional already has (DWG, DXF or PDF) and returns a construction quantity takeoff spreadsheet, broken down by discipline, with SINAPI reference codes where a reliable match exists, each line labelled either as measured from the drawing or as estimated and pending review. PDF files are read, but everything that comes from a PDF is labelled as estimated, by our own rule: a PDF's scale comes from a declaration (the title block), so even when the dimensions check out we never seal a PDF number as measured. From the same takeoff it also drafts a descriptive specification (memorial descritivo, marked as a draft to be completed and signed by the professional) and a physical construction schedule (it does not price; if the professional enters each stage's value, it spreads it month by month). It delivers quantities, not construction prices, and it does not replace the professional. It is not BIM and does not require BIM. Free and unlimited during the open beta, no credit card — every project, not just the first one. The site and its content are in Brazilian Portuguese.\n\nQuem faz: a AI.arq é um produto brasileiro e independente, feito no Rio de Janeiro e no ar desde abril de 2026 (https://ai.arq.br/sobre.html). Última atualização deste arquivo: {{ATUALIZADO_EM}}.\n\n## Comece por aqui\n\n- [Página inicial](https://ai.arq.br/): o que a AI.arq faz, como enviar a prancha e o que volta na planilha.\n- [Exemplo de planilha pronta](https://ai.arq.br/exemplo.html): quantitativo completo de um projeto-exemplo, com as linhas MEDIDO e ESTIMADO destacadas e a planilha disponível para baixar.\n- [Perguntas frequentes](https://ai.arq.br/faq.html): formatos aceitos, o que significa MEDIDO e ESTIMADO, disciplinas cobertas, uso da SINAPI, limites do serviço e como conferir o resultado.\n- [Preços](https://ai.arq.br/precos.html): grátis e ilimitado durante o beta, sem cartão; a tabela publicada ali é a prevista para depois do beta e pode mudar.\n- [Criar conta e enviar um projeto](https://ai.arq.br/login.html?novo=1): cadastro gratuito, sem cartão de crédito.\n- [Dados da AI.arq](https://ai.arq.br/dados.html): quanto da planilha volta preenchido e quanto volta medido, em CAD e em PDF, com a data, a amostra e o método.\n- [Sobre a AI.arq](https://ai.arq.br/sobre.html): quem faz, como mede (DWG/DXF medido, PDF como estimativa) e o que o serviço não faz.\n- [Blog](https://ai.arq.br/blog/): índice completo dos artigos sobre quantitativo, leitura de projeto e orçamento de obra.\n"

# Ordem das seções no arquivo. "Optional" vem sempre por último (convenção do llms.txt).
SECOES = [
    'Quantitativo a partir de CAD (DWG, DXF e PDF)',
    'Documentos a partir do quantitativo',
    'Quantitativo x orçamento: onde termina o nosso trabalho',
    'Montar e conferir a planilha',
    'Ler o projeto: quadros, disciplinas e casos específicos',
    'Aprovação, normas e financiamento',
]

FIXOS_OPCIONAL = [
    '- [Termos de uso](https://ai.arq.br/termos.html): condições do serviço durante o beta.',
    '- [Política de privacidade](https://ai.arq.br/privacidade.html): tratamento dos arquivos enviados e dos dados de cadastro.',
]

# slug -> (seção, título, resumo). A ordem aqui é a ordem dentro da seção.
LINHAS = {
    'extrair-quantitativo-do-dwg-automatico-sem-bim': ('Quantitativo a partir de CAD (DWG, DXF e PDF)',
        'Como extrair o quantitativo de um DWG/DXF automaticamente, sem BIM',
        'o caminho de ponta a ponta, do arquivo de CAD à planilha, sem passar por modelagem BIM.'),
    'quantitativo-de-obra-com-ia': ('Quantitativo a partir de CAD (DWG, DXF e PDF)',
        'Quantitativo de obra com IA: como funciona e dá pra confiar?',
        'o que a leitura automática acerta, onde ela erra e o que precisa ser conferido pelo profissional.'),
    'dwg-ou-pdf-quantitativo-o-que-os-dados-mostram': ('Quantitativo a partir de CAD (DWG, DXF e PDF)',
        'DWG, DXF ou PDF: o que os nossos dados mostram sobre qual formato medir',
        'por que o DWG/DXF sai medido e o PDF sai como estimativa, e o que muda no resultado.'),
    'quantitativo-manual-automatico-ou-bim-comparativo': ('Quantitativo a partir de CAD (DWG, DXF e PDF)',
        'Quantitativo manual, automático ou BIM: comparativo honesto por cenário',
        'quando cada abordagem compensa, incluindo os casos em que a automação não é a melhor escolha.'),
    'como-ler-pdf-planta-arquitetonica': ('Quantitativo a partir de CAD (DWG, DXF e PDF)',
        'Como ler um PDF de planta arquitetônica',
        'guia visual de escala, cotas e legendas para quem só tem o PDF do projeto.'),
    'memorial-descritivo-de-obra-modelo-pdf-docx': ('Documentos a partir do quantitativo',
        'Memorial descritivo de obra: modelo em PDF e DOCX',
        'modelo gratuito de 10 seções e, para quem tem o desenho, o rascunho de memorial por disciplina que a AI.arq gera a partir do quantitativo.'),
    'cronograma-fisico-financeiro-obra-modelo': ('Documentos a partir do quantitativo',
        'Cronograma físico-financeiro: como montar (modelo Excel)',
        'modelo pronto; a AI.arq gera a parte FÍSICA a partir do quantitativo, e o financeiro em reais fica com o profissional.'),
    'diferenca-entre-orcamento-e-quantitativo': ('Quantitativo x orçamento: onde termina o nosso trabalho',
        'Diferença entre orçamento e quantitativo de obra',
        'glossário que separa medir quantidade de atribuir preço.'),
    'por-que-nao-entregamos-o-preco-da-sua-obra': ('Quantitativo x orçamento: onde termina o nosso trabalho',
        'Por que não te entregamos o preço da obra',
        'a razão de a planilha sair sem preços e por que isso protege o profissional.'),
    'quanto-cobrar-planilha-quantitativos-2026': ('Quantitativo x orçamento: onde termina o nosso trabalho',
        'Quanto cobrar por planilha de quantitativos',
        'referências de honorários para quem entrega levantamento como serviço.'),
    'como-fazer-planilha-de-quantitativos-de-obra': ('Montar e conferir a planilha',
        'Como fazer planilha de quantitativos de obra: passo a passo',
        'estrutura da planilha, colunas necessárias e ordem de trabalho.'),
    'sinapi-vs-tcpo-qual-usar': ('Montar e conferir a planilha',
        'SINAPI, TCPO ou SICRO: qual usar no seu projeto',
        'diferença entre as bases de referência e critério de escolha.'),
    '7-erros-comuns-levantamento-quantitativos': ('Montar e conferir a planilha',
        '7 erros comuns no levantamento de quantitativos',
        'as falhas que mais aparecem na conferência de uma planilha.'),
    '5-erros-quantitativo-atraso-de-obra': ('Montar e conferir a planilha',
        '5 erros de quantitativo que viram atraso de obra',
        'o efeito prático do número errado no canteiro.'),
    'como-ler-quadro-de-esquadrias-p1-p2': ('Ler o projeto: quadros, disciplinas e casos específicos',
        'Como ler o quadro de esquadrias (P1, J1 e a NBR 10821)',
        'interpretação da tabela de portas e janelas da prancha.'),
    'ia-arquitetura-o-que-muda-2026': ('Optional',
        'IA na arquitetura: ferramentas, workflow e o que realmente muda',
        'panorama do uso de IA no escritório, além do quantitativo.'),
    'quantitativo-de-duto-climatizacao-armadilhas': ('Quantitativo a partir de CAD (DWG, DXF e PDF)',
        'Quantitativo de duto: 4 armadilhas que erram o número',
        'por que a metragem de duto quase nunca bate: linha dupla que dobra o comprimento, desenho sem unidade, metro linear que o orçamento não usa e a referência SINAPI.'),
    'ia-conta-melhor-do-que-mede-planta': ('Quantitativo a partir de CAD (DWG, DXF e PDF)',
        'A IA conta melhor do que mede: o que os dados mostram',
        'por que, em projeto com CAD, a contagem de blocos sai medida muito mais vezes do que a área, num levantamento de linhas de quantitativo geradas a partir de plantas reais, e o que o desenho precisa ter.'),
    'memorial-a-partir-do-quantitativo-caminho-inverso': ('Documentos a partir do quantitativo',
        'Memorial a partir do quantitativo: o caminho inverso',
        'por que levantar o quantitativo antes e escrever o memorial em cima dele funciona melhor do que o caminho ensinado na faculdade.'),
    'quantitativo-vs-orcamento-arquiteto-nao-precisa-virar-orcamentista': ('Quantitativo x orçamento: onde termina o nosso trabalho',
        'Quantitativo x orçamento: o que é função do arquiteto',
        'a distinção técnica e jurídica entre quantitativo (o quê e quanto, de quem projeta) e orçamento (quanto custa, do orçamentista).'),
    'bdi-em-obra-o-que-e-como-calcular': ('Quantitativo x orçamento: onde termina o nosso trabalho',
        'BDI em obra: o que é e como calcular (Acórdão TCU 2622/2013)',
        'os componentes do BDI, a fórmula adotada pelo TCU, as faixas por tipo de obra e um exemplo de cálculo — a parte do preço, que fica com quem orça.'),
    'bdi-arquiteto-br-2026-tabela': ('Quantitativo x orçamento: onde termina o nosso trabalho',
        'BDI do arquiteto: tabela por porte de obra',
        'faixas de BDI do Acórdão TCU 2622/2013, os componentes e exemplos de cálculo por porte de obra.'),
    'como-pedir-cotacao-fornecedor-obra': ('Quantitativo x orçamento: onde termina o nosso trabalho',
        'Como pedir cotação ao fornecedor de obra',
        'template de pedido de cotação, critérios de seleção e quadro comparativo para receber propostas que dá para comparar.'),
    'quantitativo-arquitetura-sinapi-planilha-modelo': ('Montar e conferir a planilha',
        'Quantitativo SINAPI: planilha modelo XLSX por disciplina',
        'modelo de planilha de quantitativos com códigos SINAPI organizada por disciplina, a diferença entre composição e insumo e como montar o arquivo para o orçamentista.'),
    'boletim-de-medicao-de-obra-modelo-excel': ('Montar e conferir a planilha',
        'Boletim de medição de obra: modelo em Excel',
        'modelo de boletim de medição — previsto, executado e acumulado, com memória de cálculo — e como preencher. A coluna prevista é o quantitativo da obra.'),
    'medir-area-e-contar-blocos-no-autocad': ('Ler o projeto: quadros, disciplinas e casos específicos',
        'Como medir área e contar blocos no AutoCAD',
        'passo a passo com os comandos Propriedades, AREA, LIMITE e CONTAGEM, e as pegadinhas que a própria documentação registra.'),
    'disciplinas-obra-retrofit-comercial': ('Ler o projeto: quadros, disciplinas e casos específicos',
        'Disciplinas em obra de retrofit comercial',
        'checklist das disciplinas de um retrofit comercial: o que considerar, o que vira aditivo quando esquecido, a ordem de execução e os custos indiretos.'),
    'memorial-descritivo-cau-prefeitura-sp-rj-bh': ('Aprovação, normas e financiamento',
        'Memorial descritivo para CAU e prefeitura: SP, RJ e BH',
        'o que as prefeituras de São Paulo, Rio de Janeiro e Belo Horizonte pedem no memorial: estrutura, base normativa e erros que reprovam. A AI.arq gera um rascunho por disciplina; o texto técnico e o quadro de áreas ficam com o profissional.'),
    'quadro-de-areas-modelo-excel-nbr-12721': ('Aprovação, normas e financiamento',
        'Quadro de áreas: modelo em Excel (NBR 12721)',
        'modelo de quadro de áreas por pavimento, com área privativa, comum e equivalente pela NBR 12721 e conferência das somas. A AI.arq entrega as áreas que a prancha permite medir, não o quadro pronto.'),
    'nbr-9050-checklist-acessibilidade-arquitetos': ('Aprovação, normas e financiamento',
        'NBR 9050: checklist de acessibilidade',
        'checklist da NBR 9050:2020 — portas, banheiros, rampas, sinalização e vagas —, com as medidas-chave e os erros que reprovam projeto.'),
    'financiamento-caixa-construcao-documentos-pci': ('Aprovação, normas e financiamento',
        'Financiamento Caixa para construção: documentos e PCI',
        'o que a Caixa pede para financiar construção — PCI, projeto aprovado, ART/RRT, memorial e cronograma —, a partir da cartilha oficial de dezembro de 2025, com checklist.'),
}


def _data_do_post(post):
    return post.get("update_date") or post.get("updated") or post["publish_date"]


def montar(posts, hoje, site="https://ai.arq.br"):
    """O texto do llms.txt: cabeçalho + posts PUBLICADOS (publish_date <= hoje)
    agrupados nas SECOES, na ordem de LINHAS; "Optional" por último."""
    publicados = [p for p in posts if p["publish_date"] <= hoje]
    por_slug = {p["slug"]: p for p in publicados}
    atualizado = max([REVISADO_EM] + [_data_do_post(p) for p in publicados])

    grupos = {s: [] for s in SECOES + ["Optional", "Outros artigos"]}
    for slug, (secao, titulo, resumo) in LINHAS.items():
        if slug in por_slug:
            grupos.setdefault(secao, []).append((titulo, slug, resumo))
    for p in publicados:  # post sem linha curada: entra, mas o CI reprova
        if p["slug"] not in LINHAS:
            grupos["Outros artigos"].append((p["title"], p["slug"], p["description"]))

    def linha(titulo, slug, resumo):
        return "- [%s](%s/blog/posts/%s.html): %s" % (titulo, site, slug, resumo)

    partes = [CABECALHO.replace("{{ATUALIZADO_EM}}", atualizado).rstrip("\n")]
    for secao in SECOES + ["Outros artigos"]:
        if grupos[secao]:
            partes.append("## %s\n\n%s" % (secao, "\n".join(linha(*x) for x in grupos[secao])))
    opcional = [linha(*x) for x in grupos["Optional"]] + FIXOS_OPCIONAL
    partes.append("## Optional\n\n" + "\n".join(opcional))
    return "\n\n".join(partes) + "\n"
