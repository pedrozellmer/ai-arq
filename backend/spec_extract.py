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
_RX_FABRICANTE_DITO = _re.compile(
    r"(?:fabricante|marca)\s*:?\s*([A-ZÀ-Ú][\wÀ-ú&.\-]{2,24})", _re.UNICODE)

# Código de produto: precedido de cód./ref./modelo, OU no formato pontuado
# típico de SKU (2042.C83, P.47.26, TEL-779, 38KCX22, BRH85MK).
_RX_CODIGO_ROTULADO = _re.compile(
    r"(?:c[óo]d(?:igo)?\.?|ref(?:er[êe]ncia)?\.?|modelo)\s*:?\s*"
    r"([A-Z0-9][A-Z0-9][A-Z0-9./\-]{1,18})",
    _re.IGNORECASE)
# 🪤 O segmento do meio pode ter UM caractere só: "2315.C.060" é o código real
# de uma barra de apoio Deca do acervo. Exigir 2+ perdia esse caso.
_RX_CODIGO_SOLTO = _re.compile(
    r"(?<![\w.])((?:[A-Z]{1,4}[\-.]?\d{2,6}[A-Z0-9.\-]{0,8})"
    r"|(?:\d{2,4}\.[A-Z0-9]{1,6}(?:\.[A-Z0-9]{1,6})?))(?![\w])")

# Palavras que denunciam que aquele "código" é do PROJETO, não do fabricante.
_RUIDO = ("bloco", "layer", "quadro de esquadrias", "detalhe", "prancha",
          "planta baixa", "legenda", "vista", "corte", "item de legenda",
          "arquivo", "paginação", "levantamento")

# Onde o nome da cor termina. Sem isto, "cor coral sobre massa corrida" saía
# inteiro como se fosse o nome da cor.
_PARA_A_COR = frozenset((
    "sobre", "em", "de", "do", "da", "com", "para", "conforme", "no", "na",
    "e", "ou", "nas", "nos", "aplicada", "aplicado", "acabamento", "ref",
    "cód", "cod", "código", "codigo", "linha", "formato", "dimensão", "dimensao"))

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
_RX_COR = _re.compile(
    r"\bcor(?![a-zà-ú])\s*:?\s*([A-Za-zÀ-ú][\wÀ-ú]+(?:\s+[A-Za-zÀ-ú]+){0,2})",
    _re.IGNORECASE | _re.UNICODE)


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
    m = None
    for _cand in _RX_MARCA.finditer(d):
        if _cand.group(1).lower() in _MARCAS_AMBIGUAS:
            if _RX_COR_ANTES.search(d[max(0, _cand.start() - 14):_cand.start()]):
                continue      # "cor coral" é cor, não fabricante
        m = _cand
        break
    if m:
        # devolve com a grafia canônica da lista, não a do texto
        achado = m.group(1).lower()
        for oficial in _MARCAS:
            if oficial.lower() == achado:
                marca = oficial
                break
    if not marca:
        m2 = _RX_FABRICANTE_DITO.search(d)
        if m2:
            marca = m2.group(1).strip(" .,-")

    codigo = None
    if marca:
        for rx in (_RX_CODIGO_ROTULADO, _RX_CODIGO_SOLTO):
            for mc in rx.finditer(d):
                cand = mc.group(1).strip(" .,-")
                if len(cand) < 4 or cand.isalpha():
                    continue
                if _tem_ruido_perto(d, mc.start()):
                    continue
                # 🪤 Dimensão não é código: "38x38x50cm", "60x60", "0,835m".
                if _re.fullmatch(r"\d+[xX×]\d+.*", cand):
                    continue
                codigo = cand
                break
            if codigo:
                break

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
            for _w in c.split():
                _wl = _w.lower().strip(",.;:")
                # 🪤 "cor Branco Neve Suvinil" — o nome da cor acaba onde a
                # MARCA começa. Sem isto o fabricante virava parte da cor.
                if _wl in _PARA_A_COR or (_wl in _marcas_min and _palavras):
                    break
                _palavras.append(_w)
            cor = " ".join(_palavras)[:40] or None

    return {"marca": marca, "codigo": codigo, "cor": cor}


# ══════════════════════════════════════════════════════════════════════════
#  🚨 TORNEIRA FECHADA — 25/08/2026
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
LIBERADO_PRO_CLIENTE = False


def spec_origem(spec: dict) -> str:
    """De onde veio a especificação. Mesma disciplina do medido/estimado:
    quem lê a planilha precisa saber se aquilo o arquiteto escreveu ou se
    alguém sugeriu. Por ora só existe o caso 'lido'."""
    return "lido" if (spec.get("marca") or spec.get("codigo")) else ""
