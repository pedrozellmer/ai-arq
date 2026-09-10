# -*- coding: utf-8 -*-
"""A lista de comprimentos por layer diz QUAL layer é anotação — e não apaga nenhuma.

🩸 09/09/2026. `COMPRIMENTOS POR LAYER` é a seção que autoriza selo BRANCO no
prompt do DXF (*"Comprimento calculado em COMPRIMENTOS POR LAYER"*), e ela ia
CRUA pra IA. O `walls` que a alimenta recebe TODA
LINE/LWPOLYLINE/POLYLINE/ARC/CIRCLE do modelspace **sem filtro de layer**,
enquanto os outros dois caminhos que alimentam `walls` filtram.

🩸 E eu escrevi aqui, num comentário permanente, que *"o bloco de ÁREA logo
abaixo tem allowlist E denylist"* — **errado**. As listas `_AREA_ALLOW`/
`_AREA_DENY` valem só pra POLILINHA FECHADA (`_consider_poly`); o laço de HATCH,
que é o que alimenta `ÁREAS HACHURADAS POR LAYER`, **não filtra layer nenhum**.
Ou seja: hachura em layer de anotação também vira área. A revisão adversarial
pegou a afirmação falsa, e o rótulo passou a valer pros dois blocos.

📏 MEDIDO nos logs de produção `motor:parede-medida` (7 jobs, 98 layers de
topo): **18 layers de anotação somando 7.401 m de 29.227 m — 25,3%** do que o
motor chama de "comprimento de parede". Num pórtico, `ARQ_TEX-4` sozinha era
88,8% do arquivo. ⚠️ N pequeno (o stage é recente) — indício forte, não prova
fechada.

🚫 POR QUE NÃO FILTRAR, que era o conserto óbvio:
  1. `sinal_medido` é `len(blocks) + len(walls) + ...` e decide se a extração é
     declarada **ESTÉRIL**. Tirar layers de `walls` faria arquivo legítimo
     passar a ser recusado — trocaria um defeito visível por um invisível.
  2. A casa já decidiu o contrário no consolidador, em 06/09: *"duplicar é um
     erro que o arquiteto VÊ; apagar é um erro que ele NÃO vê"*.

🔑 Então a lista continua INTEIRA e ganha um rótulo. E há rede embaixo: o
rebaixamento determinístico do selo (`layer_is_anotacao` no `main.py`) pega o
que passar, pra o conserto não depender de a IA obedecer ao texto.
"""
import os
import re
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import dwg_extractor as dx  # noqa: E402


def _prompt(walls_por_layer):
    e = dx.DXFExtraction(filename="x.dxf", blocks=[], walls=[], hatches=[],
                         texts=[], layers=[], dimensions=[])
    e.get_walls_by_layer = lambda: dict(walls_por_layer)
    txt = e.to_structured_prompt()
    # 🪤 `.*?\n\n` NÃO serve: quando não há hachura nem texto, esta é a ÚLTIMA
    # seção do prompt e não existe linha em branco depois — o regex devolvia
    # None e o teste acusava "a seção sumiu" com ela lá, inteira. Pior: no meu
    # ensaio manual eu li o FALLBACK (`txt[:400]`) como se fosse o casamento.
    # Corta até a linha em branco OU até o fim.
    m = re.search(r"COMPRIMENTOS POR LAYER:.*?(?=\n\n|\Z)", txt, re.S)
    assert m, "a seção COMPRIMENTOS POR LAYER sumiu do prompt"
    return m.group(0)


_CASO_REAL = {"ARQ_TEX-4": 3782.3, "ARQ_ALV-4": 91.35,
              "A-WALL": 200.0, "FOR-DIM": 44.0}


# ══════════════════════════════════════════════════════════════════════════
#  🔑 Rotula — e NÃO apaga
# ══════════════════════════════════════════════════════════════════════════
def test_layer_de_anotacao_vem_MARCADA():
    txt = _prompt(_CASO_REAL)
    for layer in ("ARQ_TEX-4", "FOR-DIM"):
        linha = next(l for l in txt.splitlines() if l.strip().startswith(layer))
        assert "ANOTAÇÃO" in linha, (
            "%s foi pra IA sem aviso nenhum: %r" % (layer, linha))


def test_CONTROLE_layer_de_OBRA_nao_recebe_aviso():
    """🧪 Sem isto, marcar TUDO passaria no teste acima — e a IA aprenderia a
    ignorar o aviso, que é o mesmo que não ter aviso."""
    txt = _prompt(_CASO_REAL)
    for layer in ("ARQ_ALV-4", "A-WALL"):
        linha = next(l for l in txt.splitlines() if l.strip().startswith(layer))
        assert "ANOTAÇÃO" not in linha, (
            "%s (layer de obra) recebeu aviso de anotação: %r" % (layer, linha))


def test_a_lista_continua_INTEIRA_com_os_numeros():
    """🚫 O conserto NÃO é filtrar. Apagar mexe em `sinal_medido` (que declara
    extração estéril) e é o erro que ninguém vê."""
    txt = _prompt(_CASO_REAL)
    for layer, metros in _CASO_REAL.items():
        assert layer in txt, "%s sumiu da lista — foi FILTRADO" % layer
        assert ("%.2f" % metros) in txt, (
            "o comprimento de %s sumiu: a medição é real e não pode ser "
            "escondida" % layer)


def test_o_aviso_diz_O_QUE_FAZER_nao_so_o_que_e():
    """🪤 Aviso que só classifica não muda comportamento. Este tem que proibir
    o uso como quantidade — é a frase que o prompt precisa pra decidir."""
    linha = next(l for l in _prompt(_CASO_REAL).splitlines()
                 if "ARQ_TEX-4" in l)
    for pedaco in ("não use como quantidade", "NÃO é elemento de obra"):
        assert pedaco in linha, "o aviso não diz %r: %r" % (pedaco, linha)


def test_o_rodape_conta_quantas_sao():
    txt = _prompt(_CASO_REAL)
    assert "2 marcada(s) como ANOTAÇÃO" in txt, txt


def test_o_texto_NAO_contem_a_palavra_layer_seguida_de_palavra():
    """🩸 A revisão adversarial pegou isto ANTES do push, e é sutil.

    A régua que lê o layer da observação (`_LAYER_RE`, main.py) casa
    "layer <PALAVRA>" e captura a PALAVRA. Meu texto original dizia
    "LAYER DE ANOTAÇÃO" — se a IA ecoasse isso na observação (e o rodapé PEDE
    que ela escreva a origem lá), a régua devolveria o layer fantasma 'DE', o
    `all(layer_is_anotacao(...))` viraria False e **o rebaixamento não
    dispararia**. O aviso escrito pra defender a regra nº1 desligaria a rede
    que a garante.

    🔑 Consertado nos dois lados: a régua ignora preposição (main.py,
    `_NAO_E_LAYER`) e o texto não usa mais "layer" antes de palavra comum.
    Este guarda cuida do segundo lado; o primeiro tem guarda próprio.
    """
    import re as _re
    txt = _prompt(_CASO_REAL)
    for linha in txt.splitlines():
        if "ANOTAÇÃO" not in linha:
            continue
        depois = linha.split("ANOTAÇÃO")[0]
        assert not _re.search(r"(?i)layer\s+[A-Za-zÀ-ÿ]", depois), (
            "o aviso voltou a ter 'layer <palavra>' — a régua da observação "
            "vai capturar a palavra como se fosse nome de layer: %r" % linha)


def test_a_AREA_hachurada_tambem_e_rotulada():
    """🩸 Eu tinha escrito num comentário permanente que o bloco de ÁREA
    "tem allowlist E denylist" — e ERREI. Aquelas listas valem só pra polilinha
    fechada (`_consider_poly`); o laço de HATCH não filtra layer nenhum. Ou
    seja, hachura de layer de anotação também vira área. O rótulo vale pros
    dois lados."""
    import re as _re
    e = dx.DXFExtraction(filename="x.dxf", blocks=[], walls=[], hatches=[],
                         texts=[], layers=[], dimensions=[])
    e.get_walls_by_layer = lambda: {}          # prancha SEM parede — o NameError
    e.get_areas_by_layer = lambda: {"ARQ_TXT-1": 12.0, "ARQ-PISO": 88.0}
    txt = e.to_structured_prompt()
    m = _re.search("ÁREAS HACHURADAS POR LAYER:.*?(?=" + chr(10) * 2 + "|\\Z)",
                   txt, _re.S)
    assert m, "a seção de áreas sumiu"
    bloco = m.group(0)
    anot = next(l for l in bloco.splitlines() if l.strip().startswith("ARQ_TXT-1"))
    piso = next(l for l in bloco.splitlines() if l.strip().startswith("ARQ-PISO"))
    assert "ANOTAÇÃO" in anot, anot
    assert "ANOTAÇÃO" not in piso, piso
    assert "88.00" in piso, "a área do layer de obra sumiu"


def test_sem_anotacao_NAO_aparece_rodape_nem_aviso():
    """🔒 Prancha limpa não pode ganhar ruído — aviso em toda prancha vira
    papel de parede e para de ser lido."""
    txt = _prompt({"A-WALL": 120.0, "ARQ_ALV": 33.3})
    assert "ANOTAÇÃO" not in txt, txt


# ══════════════════════════════════════════════════════════════════════════
#  A rede embaixo: o conserto não depende de a IA obedecer
# ══════════════════════════════════════════════════════════════════════════
def test_existe_REDE_deterministica_alem_do_texto():
    """🔑 Prompt é pedido, não garantia. O rebaixamento do selo por
    `layer_is_anotacao` tem que continuar existindo no `main.py` — se alguém
    apagar a rede achando que o aviso resolve, aqui reprova."""
    import ast
    import io
    # 🪤 Exigir só que a régua seja CHAMADA não basta: há DOIS call sites no
    # `main.py` (o selo e o dedup de m²), e a mutação que desligou o do SELO
    # sobreviveu porque o outro continuava lá. O fato é "existe um ramo que
    # consulta a régua E rebaixa o selo pra estimado".
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    rebaixam = []
    for n in ast.walk(ast.parse(fonte)):
        if not isinstance(n, ast.If):
            continue
        consulta = any(
            isinstance(c, ast.Call)
            and (getattr(c.func, "id", None) or getattr(c.func, "attr", None))
            in ("_layer_is_anotacao", "layer_is_anotacao")
            for c in ast.walk(n.test))
        if not consulta:
            continue
        vira_estimado = any(
            isinstance(x, ast.Assign)
            and any(getattr(t, "id", None) == "conf" for t in x.targets)
            and isinstance(x.value, ast.Constant) and x.value.value == "estimado"
            for x in ast.walk(ast.Module(body=n.body, type_ignores=[])))
        if vira_estimado:
            rebaixam.append(n.lineno)
    assert rebaixam, (
        "sumiu o ramo que consulta a régua de anotação E rebaixa o selo — o "
        "conserto passou a depender de a IA ler o aviso do prompt, e prompt é "
        "pedido, não garantia")


@pytest.mark.parametrize("quebrado", [{}, None])
def test_lista_vazia_nao_derruba_o_prompt(quebrado):
    """🔒 Isto roda no caminho do cliente."""
    e = dx.DXFExtraction(filename="x.dxf", blocks=[], walls=[], hatches=[],
                         texts=[], layers=[], dimensions=[])
    e.get_walls_by_layer = lambda: (quebrado or {})
    assert isinstance(e.to_structured_prompt(), str)


def test_a_regua_indisponivel_NAO_quebra_a_extracao():
    """🪤 O import da régua é best-effort de propósito: `dwg_extractor` roda
    também no processo FILHO, onde o sys.path é montado na mão. Se ele falhar,
    a lista sai sem rótulo — nunca sem lista."""
    import io
    fonte = io.open(os.path.join(_BACKEND, "dwg_extractor.py"), encoding="utf-8").read()
    i = fonte.index("from engine_rules import layer_is_anotacao")
    trecho = fonte[max(0, i - 200):i + 200]
    assert "try:" in trecho and "except" in trecho, (
        "o import da régua deixou de ser best-effort: uma falha dele passa a "
        "matar a extração inteira")
