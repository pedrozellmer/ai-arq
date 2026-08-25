# -*- coding: utf-8 -*-
"""Tira MARCA, CÓDIGO e COR de dentro da descrição e põe em campo próprio.

Pedro, 24/08/2026, desenhando o Caderno de acabamentos: *"ele revisa a qtd em
quantitativos, e depois no caderno vai especificando a marca, modelo, o sku,
justamente pra mandar pra orçar (...) vamos continuar não orçando nada, apenas
facilitando mais ainda, e quando tiver o sku no projeto a gente sugere"*.

🔑 O ponto de partida é que **isso já está escrito**. O prompt do motor manda,
em `analyzer.py`, que "TODA descrição deve ser completa: serviço + material +
fabricante + referência + cor + dimensão". A gente já paga a IA pra extrair, e
depois cola tudo num campo de texto só. Medido no acervo: 304 itens citam marca
conhecida e 226 trazem algum código escrito.

🚨 A ARMADILHA, vista em dado real antes de eu escrever uma linha: nem todo
"cód."/"ref."/"modelo" é código de FABRICANTE. Do banco:

    "Janela JA04 — ... (código JA04)"              ← tag do quadro de esquadrias
    "Cadeira — ref. bloco 'CADEIRA 19 - PLANTA'"   ← nome de bloco do CAD
    "Detalhe de porta (ref. 1008831)"              ← referência de detalhe
    "Piso tátil — bloco de referência PODOTÁTIL"   ← nome de bloco

Um regex ingênuo encheria o caderno de lixo — e lixo com cara de especificação é
pior que campo vazio, porque o cliente manda pro fornecedor.

**A regra que separa: código só é código de fabricante se houver um FABRICANTE
por perto.** "JA04" sozinho é tag do projeto; "2020.CB3" ao lado de "Deca" é SKU.
Falha fechada: sem marca identificável, não se afirma nada.

🚫 Isto NÃO inventa dado. Não consulta catálogo, não sugere produto, não
precifica (regra dura nº5) e não usa nada de outro projeto (regra nº2). Só lê o
que o arquiteto escreveu na prancha dele.
"""
import re as _re

# Fabricantes vistos no acervo real + os grandes do mercado BR. A lista existe
# porque ela é o DISCRIMINADOR: sem marca reconhecida, nada é afirmado.
# 🪤 Entradas curtas e ambíguas ficam de fora de propósito — "3M" casava "3m" de
# 3 metros em 15 itens do acervo (falso positivo pego num controle).
_MARCAS = (
    "Portobello", "Eliane", "Decortiles", "Biancogres", "Portinari", "Ceusa",
    "Cerbras", "Itaunense", "Deca", "Docol", "Roca", "Celite", "Incepa",
    "Lorenzetti", "Tramontina", "Suvinil", "Coral", "Sherwin-Williams",
    "Sherwin", "Tigre", "Amanco", "Krona", "Astra", "Duratex", "Dexco",
    "Tarkett", "Knauf", "Placo", "Saint-Gobain", "Isover", "Gypsum",
    "Trombini", "Carrier", "Midea", "Daikin", "Hitachi", "Fujitsu", "Elgin",
    "Springer", "Brastemp", "Consul", "Electrolux", "Philips", "Osram",
    "Lumicenter", "Interlight", "WEG", "Schneider", "Siemens", "Legrand",
    "Pial", "Steck", "Cemar", "Bticino", "Termotécnica", "Termotecnica",
    "Artplan", "Votorantim", "Gerdau", "Perflex", "Censi", "Atlas",
)
# 🪤 Nomes de marca que também são palavra comum em português. Testado em dado
# real: sem tratamento, "pintura cor coral" virava marca=Coral.
_MARCAS_AMBIGUAS = frozenset(("coral", "atlas", "astra"))

_RX_MARCA = _re.compile(
    r"(?<![A-Za-zÀ-ú])(" + "|".join(_re.escape(m) for m in _MARCAS) + r")(?![A-Za-zÀ-ú])",
    _re.IGNORECASE)

# "cor coral", "cor azul coral" — a marca não conta quando vem logo depois de "cor".
_RX_COR_ANTES = _re.compile(r"\bcor\s+(?:[a-zà-ú]+\s+)?$", _re.IGNORECASE | _re.UNICODE)

# "fabricante X" / "marca X": pega quem não está na lista, quando o texto DIZ
# que é fabricante. Mais confiável que a lista, porque o próprio autor rotulou.
# 🚨 25/08, achado pelo Pedro na tela do admin depois de eu dar o extrator por
# pronto: "…marca Arte em Ladrilhos" saía como marca **"Arte"** — meia marca,
# que não existe como empresa. A versão anterior pegava UM token só. Agora
# pega até três, aceitando os conectores minúsculos do meio ("em", "de", "e"),
# que é como se escreve nome de empresa em português.
#
# 🪤 O ponto é o PONTO FINAL. No acervo, três itens escrevem "…, marca Laav.
# Acabamento a confirmar": emendar a próxima palavra maiúscula daria
# "Laav Acabamento". Por isso o "." saiu da classe de caracteres — o nome
# termina ali, e de quebra "Laav." e "Laav" param de ser duas marcas.
#
# 🪤 E a continuação só vale COM o conector minúsculo. Sem essa trava, medindo
# em texto real, o nome comia o que vinha depois:
#     "marca Montal NBR-5419"        -> marca="Montal NBR-5419"  (norma)
#     "marca Lumini LED 3000K"       -> marca="Lumini LED"       (tecnologia)
#     "marca Durafloor Linha Nature" -> marca="Durafloor Linha Nature" (linha)
# Duas maiúsculas seguidas quase nunca são o nome da empresa; "X em Y" é.
_RX_FABRICANTE_DITO = _re.compile(
    r"(?:fabricante|marca)\s*:?\s*"
    r"([A-ZÀ-Ú][\wÀ-ú&\-]{2,24}"
    r"(?:\s+(?:de|do|da|dos|das|em|e)\s+[A-ZÀ-Ú][\wÀ-ú&\-]{2,24}){0,2})",
    _re.UNICODE)

# Código de produto: precedido de cód./ref./modelo, OU no formato pontuado
# típico de SKU (2042.C83, P.47.26, TEL-779, 38KCX22, BRH85MK).
_RX_CODIGO_ROTULADO = _re.compile(
    r"(?:c[óo]d(?:igo)?\.?|ref(?:er[êe]ncia)?\.?|modelo)\s*:?\s*"
    r"([A-Z0-9][A-Z0-9][A-Z0-9./_\-]{1,18})",
    _re.IGNORECASE)
# 🪤 O segmento do meio pode ter UM caractere só: "2315.C.060" é o código real
# de uma barra de apoio Deca do acervo. Exigir 2+ perdia esse caso.
# 🪤 25/08: sem o "_" aqui, "ref. 2310_C_070_ESC" saía cortado em "2310" — a
# FAMÍLIA da barra de apoio, não o modelo. O fornecedor pode mandar a de 80cm no
# lugar da de 70. Sublinhado separa SKU tanto quanto ponto e hífen.
_RX_CODIGO_SOLTO = _re.compile(
    r"(?<![\w.])((?:[A-Z]{1,4}[\-._]?\d{2,6}[A-Z0-9._\-]{0,12})"
    r"|(?:\d{2,4}[._][A-Z0-9]{1,6}(?:[._][A-Z0-9]{1,6})*))(?![\w])")

# Palavras que denunciam que aquele "código" é do PROJETO, não do fabricante.
_RUIDO = ("bloco", "layer", "quadro de esquadrias", "detalhe", "prancha",
          "planta baixa", "legenda", "vista", "corte", "item de legenda",
          "arquivo", "paginação", "levantamento")

# Onde o nome da cor termina. Sem isto, "cor coral sobre massa corrida" saía
# inteiro como se fosse o nome da cor.
_PARA_A_COR = frozenset((
    "sobre", "em", "de", "do", "da", "com", "para", "conforme", "no", "na",
    "e", "ou", "nas", "nos", "aplicada", "aplicado", "acabamento", "ref",
    "cód", "cod", "código", "codigo", "linha", "formato", "dimensão", "dimensao",
    # 🪤 25/08: "Teste de cor in loco das amostras" saía como cor="in loco das"
    "in", "loco", "teste", "amostra", "amostras", "definir", "escolher",
    # 🪤 25/08, medindo os 44 itens que têm cor e NÃO têm marca: sobravam dois
    # jeitos de o projeto dizer "ainda não sei" que a guarda não conhecia —
    # "cor NÃO identificados" e "cor POR definir". Eram os 2 únicos erros dos
    # 30 que saíam com cor.
    "não", "nao", "por", "sem", "indefinida", "indefinido", "confirmar",
    "especificar", "identificado", "identificados", "identificada",
    # acabamento colado no nome da cor: "cor Branco Gelo antiderrapante"
    "antiderrapante", "retificado", "retificada", "esmaltado", "esmaltada",
    "polido", "polida", "acetinado", "acetinada"))

# 🪤 Aceita minúscula: "cor branca" vale tanto quanto "cor Branco Neve", e
# exigir maiúscula perdia o revestimento Eliane do acervo.
#
# 🚨 25/08/2026 — dois defeitos meus na MESMA linha, achados na auditoria antes
# de qualquer gravação. A versão anterior era `\bcor\s*:?\s*(...)`:
#
#  1) fronteira só ANTES da palavra. Então "cor" casava como PREFIXO e o resto
#     virava o nome da cor:
#         "Porta de correr"                     -> cor="rer"
#         "Massa corrida PVA ... Coral Branco"  -> cor="rida PVA"   ← e com
#            marca junto, isso seria GRAVADO
#         "Suporte de corrimão"                 -> cor="rimão"
#         "Rodapé em corte reto"                -> cor="te reto"
#         "Massa corrida cor Branco Neve Suvinil" -> cor="rida cor Branco"
#     Esse último é o caso que o comentário logo abaixo jurava tratar: a cor
#     real é "Branco Neve" e saía destruída, porque o "corrida" vem antes.
#     Medido no acervo: 380 dos 679 itens com cor preenchida eram lixo assim.
#
#  2) sem IGNORECASE. "Cor: Branco Neve", "COR BRANCA" e "Cor Palha" — a forma
#     mais comum de escrever numa prancha — não casavam com NADA.
#
# 🪤 Os dois juntos importam: consertar só a caixa faria "Cortina" virar
# cor="tina". A fronteira depois de "cor" é o que segura.
# 🪤 25/08 (auditoria): "cor Branco Gelo GE17" saía como "Branco Gelo GE" — o
# `[A-Za-zÀ-ú]+` mordia as letras do código e largava o "17". O `(?![\wÀ-ú])`
# obriga a palavra a terminar de verdade: em "GE17" ela não termina, então o
# código inteiro fica de fora do nome da cor.
_RX_COR = _re.compile(
    r"\bcor(?![a-zà-ú])\s*:?\s*"
    r"([A-Za-zÀ-ú][\wÀ-ú]+(?:\s+[A-Za-zÀ-ú]+(?![\wÀ-ú])){0,2})",
    _re.IGNORECASE | _re.UNICODE)


# ══════════════════════════════════════════════════════════════════════════
#  🚨 25/08 — os 3 jeitos de afirmar uma MARCA que o projeto não afirmou
# ══════════════════════════════════════════════════════════════════════════
# A auditoria mediu 102 itens (72 + 30) saindo com marca errada. Duas causas.

# (1) MARCA EM ABERTO — 72 itens, 17 projetos, 13 clientes.
# O arquiteto escreve "Knauf, Placo ou similar", "Carrier ou similar", "Deca ou
# equivalente" JUSTAMENTE pra não fechar fornecedor: é ele garantindo a
# concorrência de preço da obra dele. Pegar a primeira e gravar como decisão
# tomada fecha a concorrência no documento que ele assina.
# 🪤 Num caso real o projeto ofereceu QUATRO ("Tarkett ou Santa Luzia ou
# Interfloor ou Architech") e saía só Tarkett.
_RX_MARCA_ABERTA = _re.compile(
    r"\bou\s+(?:similar(?:es)?|equivalente|semelhante|superior|de\s+qualidade)"
    r"|similar(?:es)?\s+aprovad|de\s+qualidade\s+(?:igual|equivalente|superior)"
    r"|\bou\s+outra\s+marca", _re.IGNORECASE | _re.UNICODE)

# 🪤 "Tarkett ou Santa Luzia ou Interfloor ou Architech": três das quatro não
# estão na lista de marcas, então contar marcas conhecidas dava UMA e a regra
# passava batido. O que denuncia a alternativa é o "ou" seguido de NOME PRÓPRIO
# logo depois da marca. Minúscula não conta ("Deca ou registro de gaveta" é
# outro item da mesma linha, não outra marca).
_RX_OU_OUTRO_NOME = _re.compile(r"\bou\s+[A-ZÀ-Ú][\wÀ-ú]{2,}", _re.UNICODE)

# (2) MARCA DO VIZINHO — 30 itens, 9 projetos, 6 clientes.
# Rejunte, argamassa, massa corrida, selador e perfil herdam a marca do
# acabamento que eles só SERVEM: "Rejunte para porcelanato Oregon Gray Satin
# Biancogres" virava rejunte marca Biancogres — e a Biancogres é cerâmica, não
# fabrica rejunte. O fornecedor recebe pedido de produto que aquele fabricante
# não vende, e devolve sem cotar.
#
# 🪤 A regra NÃO pode ser "marca depois de 'para'": "Torneira PARA cozinha …
# 1167.C.LNK Deca" é um SKU Deca legítimo, e estava entre os 12 exemplos
# certos. O que denuncia o vizinho é a preposição introduzindo OUTRO PRODUTO,
# não um cômodo ou um uso. Por isso a lista é de EXPRESSÕES, não de palavras.
_LIGA_A_OUTRO_PRODUTO = (
    "para assentamento", "para rejuntamento", "para assentar",
    "para pintura", "para a pintura", "para revestimento", "para porcelanato",
    "para cerâmica", "para ceramica",
    # 🪤 "para piso" sozinho NÃO serve: "tinta PARA PISO Suvinil" é a marca da
    # própria tinta — o item é a pintura. Só vale quando vem outro PRODUTO
    # depois ("rejunte para piso porcelanato Tivoli — Eliane").
    "para piso porcelanato", "para piso cerâmico", "para piso ceramico",
    "compatível com", "compativel com", "conforme o revestimento",
    "associad", "prévia a", "prévia à", "previa a", "previo a", "prévio a",
    "de base para", "aplicação prévia", "aplicacao previa", "recebimento de",
)
# 🪤 Duas expressões saíram desta lista depois de eu medir o estrago — e o
# jeito de descobrir foi comparar ANTES × DEPOIS nas 338 descrições reais, não
# olhar os casos que eu já sabia:
#
#   "assentamento de" matava "Fornecimento e assentamento de porcelanato
#      Brooklyn Terrazzo — Biancogres": aqui o item É o porcelanato. O que
#      denuncia o vizinho é "PARA assentamento" (aí o item é a argamassa).
#   "sobre massa/parede/teto" matava "Pintura acrílica premium SOBRE massa
#      corrida — Coral": aqui o item É a tinta, e "sobre massa corrida" é só o
#      substrato. Os casos que essas entradas pegavam ("Massa corrida sobre
#      paredes — preparo de base PARA PINTURA acrílica Coral") já caem em
#      "para pintura" e "de base para", então elas só somavam risco.


def _posicao_do_vizinho(d_baixo: str) -> int:
    """Onde começa a parte da frase que fala de OUTRO produto (-1 se não há)."""
    achou = -1
    for exp in _LIGA_A_OUTRO_PRODUTO:
        p = d_baixo.find(exp)
        if p >= 0 and (achou < 0 or p < achou):
            achou = p
    return achou


def _marcas_no_texto(d: str):
    """Marcas da lista achadas no texto, sem sobreposição e sem repetir.

    🪤 "Sherwin-Williams" e "Sherwin" são duas entradas da lista e casam no
    MESMO pedaço de texto — contar as duas faria toda citação da Sherwin virar
    "duas marcas" e cair na regra de marca em aberto. Some o span menor."""
    brutas = []
    for cand in _RX_MARCA.finditer(d):
        if cand.group(1).lower() in _MARCAS_AMBIGUAS:
            if _RX_COR_ANTES.search(d[max(0, cand.start() - 14):cand.start()]):
                continue          # "cor coral" é cor, não fabricante
        brutas.append(cand)
    fora = set()
    for i, a in enumerate(brutas):
        for j, b in enumerate(brutas):
            if i != j and a.start() >= b.start() and a.end() <= b.end() \
                    and (a.end() - a.start()) < (b.end() - b.start()):
                fora.add(i)
    return [c for i, c in enumerate(brutas) if i not in fora]


def _canonica(achado: str):
    """A grafia da lista, não a do texto — senão TIGRE, Tigre e tigre viram
    três marcas diferentes no caderno."""
    for oficial in _MARCAS:
        if oficial.lower() == achado.lower():
            return oficial
    return None


# ══════════════════════════════════════════════════════════════════════════
#  🚨 25/08 — o que NUNCA é código de fabricante (17 itens, 12 projetos)
# ══════════════════════════════════════════════════════════════════════════
# Saíam como SKU: norma técnica ("Montal · NBR-5419"), diâmetro nominal de tubo
# ("Tigre · DN40"), bitola de cabo ("Termotécnica · CA25") e nome de bloco do
# AutoCAD ("Midea · VA-Hi-Wall-MIDEA-12k").
#
# 🔑 Um código errado é justo o campo que o fornecedor usa pra achar a peça.
# Barra de apoio errada em banheiro acessível reprova vistoria.
_RX_NAO_E_CODIGO = _re.compile(
    r"^(?:NBR|ABNT|ISO|IEC|ASTM|DIN|NR|NM)[-.\s]?\d"      # norma técnica
    r"|^DN[-.\s]?\d+$"                                     # diâmetro nominal
    r"|^CA[-.\s]?\d{2,3}$"                                 # bitola de aço CA-50
    r"|^EST[-.\s]?\d{2,3}$"                                # aço estrutural
    r"|BTU"                                                # potência
    r"|^\d{2,4}[Vv]$"                                      # tensão: 127V, 220V
    r"|HI[-]?WALL|CASSETE|PISO[-]?TETO",                   # nome de bloco de CAD
    _re.IGNORECASE | _re.UNICODE)


def _nao_e_codigo_de_fabricante(cand: str, marca: str, depois: str = "") -> bool:
    """Barra o que nunca é SKU. Falha FECHADA: na dúvida, não afirma.

    `depois` é o pedacinho de texto logo após o candidato — é ele que denuncia
    a unidade colada no número."""
    if _RX_NAO_E_CODIGO.search(cand):
        return True
    # 🪤 "split Hi-Wall Midea 12.000 BTU": barrar o nome do bloco fez o
    # extrator cair na CAPACIDADE. Número seguido de unidade não é modelo.
    if _re.match(r"\s*(?:btus?|w|kw|va|lpf|litros?|l\b|mm|cm|m²|m2)\b",
                 depois, _re.IGNORECASE):
        return True
    # 🪤 Nome de bloco do CAD costuma trazer a própria marca dentro
    # ("VA-Hi-Wall-MIDEA-12k"). SKU de fabricante não repete o fabricante.
    if marca and marca.lower() in cand.lower():
        return True
    return False


def _tem_separador(cand: str) -> int:
    return 1 if any(s in cand for s in (".", "-", "_")) else 0


def _tem_ruido_perto(texto: str, pos: int, janela: int = 60) -> bool:
    """O código está colado numa palavra que indica referência do PROJETO?"""
    trecho = texto[max(0, pos - janela):pos + janela].lower()
    return any(r in trecho for r in _RUIDO)


def extrair_spec(descricao: str) -> dict:
    """Devolve {marca, codigo, cor} do que ESTÁ ESCRITO. Campo ausente = None.

    🚨 `codigo` só sai quando há marca — é o que separa SKU de fabricante de tag
    do projeto. Sem marca, devolve codigo=None mesmo que haja "cód. XXXX" no
    texto: é melhor não afirmar do que afirmar errado.
    """
    d = str(descricao or "")
    if not d.strip():
        return {"marca": None, "codigo": None, "cor": None}

    marca = None
    achadas = _marcas_no_texto(d)

    # 🚨 (1) o projeto deixou a marca EM ABERTO — de propósito. Não fechar
    # por ele. Vale tanto pro "ou similar" quanto pra 2+ marcas oferecidas.
    _nomes = {(_canonica(c.group(1)) or c.group(1).lower()) for c in achadas}
    _em_aberto = bool(_RX_MARCA_ABERTA.search(d)) or len(_nomes) >= 2
    if not _em_aberto and achadas:
        # "<Marca> ou <OutroNome>" logo depois: alternativa oferecida
        _depois = d[achadas[0].end():achadas[0].end() + 40]
        _em_aberto = bool(_RX_OU_OUTRO_NOME.search(_depois))

    _viz = _posicao_do_vizinho(d.lower())
    if achadas:
        m = achadas[0]
        # 🚨 (2) a marca fala de OUTRO produto, que este item só serve
        if _viz < 0 or m.start() < _viz:
            if _em_aberto:
                # 🔑 marca EM ABERTO não é marca omitida: é o que o projeto
                # diz. Sai a lista inteira, na ordem do texto, marcada como
                # REFERÊNCIA — "Knauf/Placo (ou similar)". Apagar seria jogar
                # fora o que o arquiteto escreveu; sair só a primeira seria
                # fechar a concorrência que ele deixou aberta.
                _ordem = []
                for c in achadas:
                    nome = _canonica(c.group(1)) or c.group(1)
                    if nome not in _ordem:
                        _ordem.append(nome)
                marca = "/".join(_ordem)
            else:
                marca = _canonica(m.group(1))

    if not marca:
        m2 = _RX_FABRICANTE_DITO.search(d)
        if m2 and (_viz < 0 or m2.start() < _viz):
            marca = m2.group(1).strip(" .,-")

    codigo = None
    # 🪤 Com DUAS marcas oferecidas ("Tarkett Classy cod. 24032160 ou Santa
    # Luzia mod. 466"), não dá pra saber de quem é o código. Só sai quando a
    # marca é uma só — mesmo em aberto ("Deca Oval L56.17 ou equivalente").
    if marca and "/" not in marca:
        candidatos = []
        for rx in (_RX_CODIGO_ROTULADO, _RX_CODIGO_SOLTO):
            for mc in rx.finditer(d):
                cand = mc.group(1).strip(" .,-_")
                if len(cand) < 4 or cand.isalpha():
                    continue
                if _tem_ruido_perto(d, mc.start()):
                    continue
                # 🪤 Dimensão não é código: "38x38x50cm", "60x60", "0,835m".
                if _re.fullmatch(r"\d+[xX×]\d+.*", cand):
                    continue
                if _nao_e_codigo_de_fabricante(cand, marca, d[mc.end(1):mc.end(1) + 10]):
                    continue
                candidatos.append(cand)
        # 🪤 O extrator parava no PRIMEIRO código e escolhia o errado: saía
        # "Deca · CR10" (CR10 = cromado, é o acabamento) enquanto o código de
        # verdade — "1198_C37" — estava escrito na mesma linha e era ignorado
        # só porque tem sublinhado. E "ref. 2310_C_070_ESC" saía cortado em
        # "2310", que é a FAMÍLIA: o fornecedor pode mandar a barra de 80cm no
        # lugar da de 70. Agora junta todos e fica com o mais específico.
        if candidatos:
            codigo = max(candidatos, key=lambda c: (len(c), _tem_separador(c)))

    cor = None
    mc = _RX_COR.search(d)
    if mc:
        c = mc.group(1).strip(" .,-")
        # "cor da legenda", "cor a definir" não são cor
        if not _re.match(r"(da|do|a\s+definir|conforme|padr[ãa]o)", c, _re.IGNORECASE):
            # 🪤 A janela de até 3 palavras engolia o resto da frase: "cor coral
            # sobre massa corrida" saía inteiro como cor. Corta na primeira
            # palavra que não pode fazer parte de um nome de cor.
            _marcas_min = {x.lower() for x in _MARCAS}
            _palavras = []
            _tokens = c.split()
            for _i, _w in enumerate(_tokens):
                _wl = _w.lower().strip(",.;:")
                # 🪤 "cor Branco Neve Suvinil" — o nome da cor acaba onde a
                # MARCA começa. Sem isto o fabricante virava parte da cor.
                if _wl in _marcas_min and _palavras:
                    break
                if _wl in _PARA_A_COR:
                    # 🪤 25/08: "cor CINZA DE GRIFE" (nome de catálogo da Coral)
                    # saía como "CINZA", em 7 itens de um projeto só. O "de" do
                    # meio de um nome em CAIXA ALTA faz parte do nome — não é a
                    # preposição que encerra a cor.
                    _prox = _tokens[_i + 1] if _i + 1 < len(_tokens) else ""
                    _no_meio_de_nome = (
                        _wl in ("de", "do", "da")
                        and _palavras and _palavras[-1].isupper()
                        and _prox[:1].isupper())
                    if not _no_meio_de_nome:
                        break
                _palavras.append(_w)
            cor = " ".join(_palavras)[:40] or None

    return {"marca": marca, "codigo": codigo, "cor": cor,
            "aberta": bool(marca) and _em_aberto}


# ══════════════════════════════════════════════════════════════════════════
#  🚦 TORNEIRA — fechada 25/08 de manhã, ABERTA 25/08 à tarde
# ══════════════════════════════════════════════════════════════════════════
# A auditoria de hoje rodou este extrator sobre as 338 descrições reais do
# acervo: dos 361 itens que ele marcaria, **127 (35%) levam informação que o
# arquiteto NÃO escreveu pra aquele item**. Os quatro defeitos, medidos:
#
#   72 itens — "Knauf/Placo ou similar", "Deca ou equivalente", 4 marcas
#              oferecidas: sai UMA, como se fosse decisão tomada. O projeto
#              deixou a concorrência aberta de propósito e o caderno fecha.
#   30 itens — rejunte/argamassa/massa/perfil herdam a marca do acabamento que
#              eles só servem: "Rejunte para porcelanato ... Biancogres" vira
#              rejunte marca Biancogres, e a Biancogres não faz rejunte.
#   17 itens — norma e bitola viram SKU: "Montal · NBR-5419", "Tigre · DN40".
#   13 itens — cor cortada: "cor CINZA DE GRIFE" sai "CINZA".
#
# 🔑 Enquanto isso não estiver consertado, o carimbo NÃO vai pro cliente. Campo
# vazio é honesto; campo com cara de especificação e conteúdo errado vira
# pedido de orçamento errado — o caderno existe pra ser MANDADO pro fornecedor.
# É a regra dura nº1 aplicada à especificação: na dúvida, não afirmar.
#
# 🪤 A trava é só do lado do CLIENTE. A simulação do admin continua rodando o
# extrator inteiro — é ela que mede se o conserto funcionou.
#
# ✅ ABERTA em 25/08/2026, com o Pedro decidindo as duas que eram dele:
#   • "ou similar" sai como REFERÊNCIA ("Deca · L56.17 (ou similar)"), não some
#     e não vira decisão — 73 itens;
#   • a COR passa a valer sem marca junto — medido em 44 itens reais que têm
#     cor e não têm marca: 28 saem com cor e os 28 estão certos.
# Critério de aceite cumprido: os 9 casos da auditoria saem limpos, os 3 falsos
# positivos que o próprio conserto criou viraram teste, e os 122 itens que
# mudaram no acervo foram conferidos um a um.
LIBERADO_PRO_CLIENTE = True


def spec_origem(spec: dict) -> str:
    """De onde veio a especificação. Mesma disciplina do medido/estimado:
    quem lê a planilha precisa saber se aquilo o arquiteto escreveu ou se
    alguém sugeriu.

    🔑 `lido:referencia` é o caso "ou similar": o projeto CITOU a marca mas
    deixou a escolha aberta de propósito. Guardar isso separado é o que impede
    a planilha de transformar referência em decisão — e é o mesmo princípio do
    medido × estimado, aplicado à especificação.

    🚨 25/08: a COR passou a valer sozinha. Medido em 44 itens reais que têm
    cor e não têm marca: 28 saem com cor e os 28 estão certos (Branco Gelo,
    Branco Gatinho, Branco Kemtone, cinza escuro…); os outros 16 dão vazio
    porque o próprio projeto diz "a definir". "Pintura cor Azul Munsell" não
    precisa de fabricante pra ser verdade.
    """
    if not (spec.get("marca") or spec.get("codigo") or spec.get("cor")):
        return ""
    return "lido:referencia" if spec.get("aberta") else "lido"
