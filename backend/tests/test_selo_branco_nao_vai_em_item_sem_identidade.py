# -*- coding: utf-8 -*-
""""✓ MEDIDO DO CAD" num item cujo nome é o do bloco — o selo mais forte no
item mais fraco.

🩸 04/09/2026, olhando o PRIMEIRO projeto da Caroline (Bolognesi, "Parque
Aurora"). A planilha dela trazia:

    "Equipamento não identificado — bloco CAD '1258C37_v' — verificar com
     projetista"   ·   1 un   ·   ✓ MEDIDO DO CAD

🔑 MEDIDO na base inteira antes de mexer: **75 itens** desta classe em projetos
de cliente, **55 com o selo branco** — 5% de TODO o branco da história do
produto. E o número que fecha o caso: das **6 vezes** em que um cliente rejeitou
um item BRANCO, **6 de 6 eram desta classe**. É a única coisa que faz alguém
apagar algo que a gente afirmou ter medido.

Nomes que já foram entregues a cliente pagante, todos brancos:
`'ftjrtf'` · `'WGWRRG'` · `'6we4f65we4f'` · `'dgcfr'` · `'esw3r'` · `'CP525_p'`

O que a geometria prova é que existem N ocorrências DE ALGUMA COISA. Não prova
QUE COISA é. A contagem é honesta; a identidade não existe.

🪤 A fronteira foi calibrada CONTRA A BASE, item a item, e é estreita de
propósito. A primeira versão pegava 58 itens e levava junto "Janela j3",
"Difusor/Grelha", "Esquadria flexível" e "Mobiliário — bloco e48" — itens que a
gente identificou de verdade, onde só falta o TIPO. Três cortes resolveram:
  • só CONTAGEM (un/pç): em m²/ml o "não identificado" quase sempre é do
    MATERIAL ("cobertura — material não identificado") e o item existe;
  • "não identificados POR bloco específico" sai (porta é porta);
  • o nome do item tem que SER o bloco, não citá-lo.
"""
import pytest

from engine_rules import item_e_bloco_sem_identidade as _sem_identidade

# ── Descrições REAIS do banco (04/09/2026), copiadas como estão ────────────
# As que a gente PRECISA pegar: a identidade do item é o nome do bloco.
_INCOGNITAS = [
    ("Equipamento não identificado — bloco CAD '1258C37_v' — verificar com projetista", "un"),
    ("Bloco/elemento não identificado — fuy — identificar e especificar", "un"),
    ("Bloco/elemento não identificado — WGWRRG — identificar e especificar", "un"),
    ("Elemento não identificado — bloco 'dgcfr' — identificar tipo e especificação", "un"),
    ("Elemento não identificado — bloco '6we4f65we4f' — identificar tipo", "un"),
    ("Bloco não identificado — 'CP525_p' — verificar com projetista", "un"),
    ("Bloco CAD genérico CADNIC01000131 — elemento não identificado (12 unidades)", "un"),
    ("Bloco 7190917_p — elemento a identificar na prancha (bloco genérico, 7 unidades)", "un"),
    ("Bloco A3 — elemento a identificar na prancha (bloco genérico, 1 unidade)", "un"),
    ("Bloco genérico 'WW' — elemento a identificar — confirmar tipo e especificação", "un"),
    ("Elemento bloco 'new block12' — especificação a identificar pelo projetista", "un"),
    ("Elemento bloco 'RS' — provável sanitário ou lavatório — especificação a identificar", "un"),
    ("Blocos de família IFC não identificados — 'Family - ___' (10 instâncias únicas)", "un"),
]

# As que NÃO podem ser pegas: o item tem nome de verdade, só falta o tipo.
_LEGITIMAS = [
    ("Janela j3 — conforme bloco 'j3' (tipo a identificar no quadro de esquadrias)", "un"),
    ("Difusor/Grelha de insuflamento ou retorno — fornecimento e instalação "
     "(bloco genérico 'aouhfafvw' — tipo a identificar em campo)", "un"),
    ("Esquadria flexível — bloco ESQ FLEX (tipo a identificar — especificação a confirmar)", "un"),
    ("Mobiliário — bloco e48 (tipo a identificar na prancha)", "un"),
    ("Portas de alumínio natural — demais tipos não identificados por bloco específico "
     "— ver mapa de esquadrias", "un"),
    ("Portas em madeira com pintura — demais tipos não identificados por bloco específico", "un"),
    ("Bucha de redução de ferro galvanizado BSP — 3/4\" × 1/2\" — conforme bloco "
     "'Buchas de redução - 3_4_ - 1_2_'", "un"),
    # em m²/ml o "não identificado" fala do MATERIAL, e o item existe
    ("Cobertura inclinada — estrutura de telhado com caimento identificado no corte "
     "— material de cobertura não identificado", "m²"),
    ("Revestimento de fachada — réguas / lâminas verticais (material não identificado "
     "— possivelmente alumínio composto)", "m²"),
    ("Área hachurada — ambiente a identificar (layer 0, 20 hachuras)", "m²"),
    # e o clássico: "bloco" é o material, não a identidade
    ("Alvenaria de bloco cerâmico 14×19×29 cm — paredes internas e externas", "m²"),
    ("Alvenaria de bloco cerâmico — paredes", "un"),
    ("Piso cerâmico / porcelanato — Cozinha — especificação a definir", "m²"),
]


@pytest.mark.parametrize("desc,un", _INCOGNITAS)
def test_a_identidade_e_o_bloco_entao_a_regra_PEGA(desc, un):
    assert _sem_identidade(desc, un), (
        "este item voltou a passar como identificado, e vai sair com ✓ MEDIDO: "
        "%r" % desc[:90])


@pytest.mark.parametrize("desc,un", _LEGITIMAS)
def test_item_com_nome_de_verdade_NAO_e_pego(desc, un):
    assert not _sem_identidade(desc, un), (
        "a regra apertou demais e pegou um item legítimo — ele perderia o selo "
        "sem motivo: %r" % desc[:90])


def test_a_unidade_de_contagem_e_a_fronteira():
    """🪤 O corte que evitou 7 falsos positivos: em m²/ml, "não identificado"
    fala do MATERIAL."""
    d = "Elemento não identificado — bloco 'xyz'"
    assert _sem_identidade(d, "un")
    assert _sem_identidade(d, "pç")
    for u in ("m²", "ml", "m", "m³", "vb", "kg"):
        assert not _sem_identidade(d, u), (
            "a regra passou a pegar %s — nessas unidades o item costuma "
            "existir e o que falta é o material" % u)


def test_entrada_estranha_nao_derruba():
    for d, u in ((None, "un"), ("", "un"), ("Bloco X", None), (123, "un")):
        assert _sem_identidade(d, u) in (True, False)


# ══════════════════════════════════════════════════════════════════════════
#  O motor tem que APLICAR a regra — não basta ela existir
# ══════════════════════════════════════════════════════════════════════════
import ast  # noqa: E402
import io  # noqa: E402
import os  # noqa: E402

_FONTE = io.open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()


def test_o_motor_chama_a_regra_e_REBAIXA():
    chamou = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "_sem_ident"
                 for n in ast.walk(ast.parse(_FONTE)))
    assert chamou, (
        "o motor parou de consultar a regra — os itens sem identidade voltam "
        "a sair com ✓ MEDIDO")
    i = _FONTE.index("from engine_rules import item_e_bloco_sem_identidade")
    bloco = _FONTE[i:i + 2200]
    assert "_CfB.ESTIMADO" in bloco, "sumiu o rebaixamento do selo"
    assert "não sabemos o que é" in bloco, (
        "sumiu a explicação NA LINHA — aviso de topo o cliente não liga ao item")


def test_o_rebaixamento_NUNCA_promove():
    """🚨 Regra nº1: só rebaixa. Se um dia promover, é o furo que o selo existe
    pra fechar."""
    i = _FONTE.index("from engine_rules import item_e_bloco_sem_identidade")
    bloco = _FONTE[i:i + 2200]
    assert "_CfB.CONFIRMADO" not in bloco, (
        "este bloco passou a poder marcar item como CONFIRMADO — ele só pode "
        "rebaixar")
    assert 'if _cf == "confirmado":' in bloco, (
        "o rebaixamento deixou de ser condicionado ao selo atual")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — a regra de ANTES, no MESMO insumo
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_sem_a_regra_os_itens_da_base_passariam():
    """Antes de hoje não havia julgamento nenhum: tudo passava.

    Aplicar "a regra antiga" (que não existe) aos 13 itens reais tem que
    aprovar os 13 — é isso que provava que eles saíam brancos.
    """
    def _regra_ANTIGA(_desc, _un):
        return False          # não havia regra: nada era rebaixado

    passavam = [d for d, u in _INCOGNITAS if not _regra_ANTIGA(d, u)]
    assert len(passavam) == len(_INCOGNITAS), "controle mal montado"
    pega_hoje = [d for d, u in _INCOGNITAS if _sem_identidade(d, u)]
    assert len(pega_hoje) == len(_INCOGNITAS), (
        "a regra de hoje não cobre todos os itens reais que motivaram o "
        "conserto — passariam %d de %d"
        % (len(_INCOGNITAS) - len(pega_hoje), len(_INCOGNITAS)))
