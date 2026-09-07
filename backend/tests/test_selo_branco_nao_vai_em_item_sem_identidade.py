# -*- coding: utf-8 -*-
""""✓ MEDIDO DO CAD" num item cujo nome é o do bloco — o selo mais forte no
item mais fraco.

🩸 04/09/2026, olhando o PRIMEIRO projeto da cliente-22 (Bolognesi, "Parque
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


# ═══════════════════════════════════════════════════════════════════════════
#  O MOTOR, EXECUTADO
# ═══════════════════════════════════════════════════════════════════════════
# 🩸 06/09/2026 — OS DOIS GUARDAS ABAIXO ERAM CEGOS, provado por mutação.
# Eles liam o fonte: um procurava a Call `_sem_ident` na AST e as strings
# `_CfB.ESTIMADO` / "não sabemos o que é" numa janela de 2.200 chars; o outro
# proibia a grafia `_CfB.CONFIRMADO` na mesma janela. Duas mutações passaram
# por baixo dos dois, com a bancada verde:
#   (a) inverter a guarda — `if not _sem_ident(...)` virando `if _sem_ident(...)`.
#       A Call continua lá, as strings continuam lá, e o efeito INVERTE: os
#       itens sem identidade voltam a sair ✓ MEDIDO e o aviso passa a sujar
#       justamente os itens que a gente identificou de verdade.
#   (b) acrescentar um `else: _it.confidence = _CfB("confirmado")` — PROMOVE,
#       violando a regra dura nº1, sem escrever a literal que o teste proibia.
# Agora eles CHAMAM a regra e olham o selo que sai. Para isso, a regra saiu de
# dentro do `process_job` e virou `main.rebaixar_itens_sem_identidade`.


class _ItemFalso:
    """O mínimo que a regra toca. Objeto simples de propósito: o código de
    produção lê tudo por getattr, e um BudgetItem real exigiria campos que não
    têm nada a ver com o que está sendo testado."""

    def __init__(self, description, unit, confidence, observations=""):
        self.description = description
        self.unit = unit
        self.confidence = confidence
        self.observations = observations


def _selo(it):
    return str(getattr(getattr(it, "confidence", None), "value",
                       getattr(it, "confidence", "")) or "")


def test_o_motor_chama_a_regra_e_REBAIXA():
    """Guarda de EFEITO: item sem identidade entra BRANCO e sai LARANJA."""
    import main
    from models import Confidence

    sem_ident = _ItemFalso(
        "Equipamento não identificado — bloco CAD '1258C37_v' — verificar com projetista",
        "un", Confidence.CONFIRMADO)
    n = main.rebaixar_itens_sem_identidade([sem_ident])
    assert _selo(sem_ident) == "estimado", (
        "o item sem identidade continuou com o selo BRANCO — é o defeito da "
        "cliente-22, 55 itens na base")
    assert n == 1, "a contagem de rebaixados não bate: %r" % n
    assert "não sabemos o que é" in sem_ident.observations, (
        "sumiu a explicação NA LINHA — aviso de topo o cliente não liga ao item")


def test_CONTROLE_o_item_IDENTIFICADO_sai_INTACTO():
    """🪤 O outro lado, e o que pega a inversão da guarda. Se a condição virar
    do avesso, ESTE item é que seria rebaixado e sujo com o aviso — e o teste
    de cima continuaria verde sozinho."""
    import main
    from models import Confidence

    ok = _ItemFalso("Janela JA04 — alumínio, 1,20x1,00m", "un",
                    Confidence.CONFIRMADO, observations="medida da prancha A-04")
    main.rebaixar_itens_sem_identidade([ok])
    assert _selo(ok) == "confirmado", (
        "a regra rebaixou um item IDENTIFICADO — a guarda foi invertida e "
        "estamos jogando fora medição legítima")
    assert "não sabemos o que é" not in ok.observations, (
        "o aviso de 'não sabemos o que é' foi parar num item que a gente "
        "identificou — o cliente lê que não sabemos algo que sabemos")


def test_o_rebaixamento_NUNCA_promove():
    """🚨 Regra dura nº1: só rebaixa. Executa os dois casos em que uma promoção
    apareceria — o item sem identidade que JÁ era estimado, e o identificado."""
    import main
    from models import Confidence

    itens = [
        _ItemFalso("Bloco/elemento não identificado — fuy — identificar e especificar",
                   "un", Confidence.ESTIMADO),
        _ItemFalso("Alvenaria de vedação — bloco cerâmico 14cm", "m²",
                   Confidence.ESTIMADO),
    ]
    main.rebaixar_itens_sem_identidade(itens)
    for it in itens:
        assert _selo(it) != "confirmado", (
            "a regra PROMOVEU um item para CONFIRMADO (%r) — ela só pode "
            "rebaixar. É a regra dura nº1 pelo avesso." % it.description[:50])


def test_a_regra_e_CHAMADA_pelo_motor():
    """Regra correta que ninguém chama é código morto. Aqui só a chamada — o
    efeito já está provado acima, executando."""
    chamou = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "rebaixar_itens_sem_identidade"
                 for n in ast.walk(ast.parse(_FONTE)))
    assert chamou, (
        "o motor parou de consultar a regra — os itens sem identidade voltam "
        "a sair com ✓ MEDIDO")


def test_o_rebaixamento_e_condicionado_ao_selo_ATUAL():
    """🪤 Executa em vez de ler: um item sem identidade que JÁ era estimado não
    pode ser contado como rebaixado. Contagem inflada vira alarme falso no
    error_log e a gente aprende errado sobre o tamanho do problema."""
    import main
    from models import Confidence

    ja_laranja = _ItemFalso("Bloco/elemento não identificado — fuy", "un",
                            Confidence.ESTIMADO)
    n = main.rebaixar_itens_sem_identidade([ja_laranja])
    assert n == 0, (
        "contou como rebaixado um item que já era estimado — o rebaixamento "
        "deixou de ser condicionado ao selo atual")
    # e mesmo sem rebaixar, a explicação NA LINHA tem que ir
    assert "não sabemos o que é" in ja_laranja.observations


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
