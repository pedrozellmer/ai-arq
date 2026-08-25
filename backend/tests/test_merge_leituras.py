# -*- coding: utf-8 -*-
"""Merge de leituras: a melhor prancha de cada, sem duplicar nada.

Pedro, 24/08/2026: *"não podemos fazer um merge entre as planilhas e unificar
isso pelo motor tb? tipo um terceiro projeto"*.

Os números do caso que motivou (Alan, e1c48ed7 × ev597afa), medidos no banco:

    original   147 itens ·  92 medidos · 4 pranchas
    releitura  263 itens · 151 medidos · 7 pranchas
    MERGE      307 itens · 179 medidos · 7 pranchas

🔑 O merge existe porque a releitura NÃO é superconjunto: nas 4 pranchas que já
funcionavam ela perdeu 35 itens e 20 medições. As 38 portas dele (5 tipos, 34
medidas do CAD) viraram uma linha "Portas internas", quantidade 0, estimado.

🚨 A invariante que impede duplicar: cada prancha entra INTEIRA, de um lado só.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from engine_rules import (merge_itens, merge_plano, merge_sobreposicoes,
                          merge_tokens)


def _it(prancha, desc, qtd=1, medido=True, unit="un", sort=0):
    return {"ref_sheet": prancha, "description": desc, "quantity": qtd,
            "unit": unit, "confidence": "confirmado" if medido else "estimado",
            "discipline": "Elétrica", "section": "8. Elétrica",
            "sort_order": sort, "item_num": str(sort), "observations": "",
            "origem": None}


# ── O caso Alan, reduzido ao essencial ─────────────────────────────────────
PAI = (
    [_it("4366-EL-E.dxf", "Porta P80E — bloco P80E", 23),
     _it("4366-EL-E.dxf", "Porta P80 — bloco P80", 9),
     _it("4366-EL-E.dxf", "Porta P60T — bloco P60T", 4, medido=False),
     _it("4366-EL-E.dxf", "Detector de presença/alarme IVP — bloco IVP", 22)]
    + [_it("4366-EL-B.dxf", "Disjuntor %d" % i, 1, medido=False) for i in range(9)]
)
FILHO = (
    [_it("4366-EL-E.dxf", "Portas internas — tipo a definir", 0, medido=False),
     _it("4366-EL-E.dxf", "Detector/sensor IVP — segurança", 22)]
    + [_it("4366-EL-B.dxf", "Disjuntor %d" % i, 1, medido=False) for i in range(8)]
    + [_it("3073-AQ-E.dxf", "Alvenaria nova", 104.41, unit="ml")]
    + [_it("4366-LO-E.dxf", "Sensor IVP (infravermelho passivo)", 21)]
)


# ══════════════════════════════════════════════════════════════════════════
#  O plano: quem vence cada prancha
# ══════════════════════════════════════════════════════════════════════════
def test_prancha_que_so_a_releitura_tem_entra():
    """É o motivo nº1 do merge: 3 pranchas do Alan tinham morrido na 1ª leitura."""
    plano = merge_plano(PAI, FILHO)
    p = [x for x in plano["pranchas"] if x["prancha"] == "3073-AQ-E.dxf"][0]
    assert p["lado"] == "filho"
    assert "só a releitura" in p["motivo"]


def test_prancha_onde_o_original_mediu_mais_fica_com_o_original():
    """🚨 O caso das 38 portas. Sem isto, o merge não teria razão de existir —
    seria só a releitura com outro nome."""
    plano = merge_plano(PAI, FILHO)
    p = [x for x in plano["pranchas"] if x["prancha"] == "4366-EL-E.dxf"][0]
    assert p["lado"] == "pai", "a prancha das portas foi pro lado errado"
    assert "mediu mais" in p["motivo"]


def test_empate_de_medidos_desempata_por_itens():
    plano = merge_plano(PAI, FILHO)
    p = [x for x in plano["pranchas"] if x["prancha"] == "4366-EL-B.dxf"][0]
    assert p["lado"] == "pai", "9 itens × 8, ambos 0 medidos — devia ficar com o pai"


def test_empate_total_fica_com_o_que_o_cliente_ja_viu():
    a = [_it("X.dxf", "Item", 1)]
    b = [_it("X.dxf", "Item de outro jeito", 1)]
    p = merge_plano(a, b)["pranchas"][0]
    assert p["lado"] == "pai"
    assert "empate" in p["motivo"]


def test_o_total_do_merge_e_a_soma_das_pranchas_escolhidas():
    plano = merge_plano(PAI, FILHO)
    assert plano["total_itens"] == sum(p["itens"] for p in plano["pranchas"])
    assert plano["total_medidos"] == sum(p["medidos"] for p in plano["pranchas"])


def test_o_merge_bate_ou_supera_os_dois_lados_sozinhos():
    """Se não superasse, não valeria criar um terceiro projeto."""
    plano = merge_plano(PAI, FILHO)
    med_pai = sum(1 for x in PAI if x["confidence"] == "confirmado")
    med_filho = sum(1 for x in FILHO if x["confidence"] == "confirmado")
    assert plano["total_medidos"] >= max(med_pai, med_filho)


# ══════════════════════════════════════════════════════════════════════════
#  🚨 A invariante: nunca misturar dentro da mesma prancha
# ══════════════════════════════════════════════════════════════════════════
def test_cada_prancha_vem_INTEIRA_de_um_lado_so():
    """Se uma prancha viesse dos dois lados, o mesmo objeto entraria duas vezes
    com nomes diferentes — a IA batiza diferente a cada leitura."""
    plano = merge_plano(PAI, FILHO)
    itens = merge_itens(PAI, FILHO, plano)
    lado_esperado = {p["prancha"]: p["lado"] for p in plano["pranchas"]}
    for pr, lado in lado_esperado.items():
        do_pai = [x for x in PAI if x["ref_sheet"] == pr]
        do_filho = [x for x in FILHO if x["ref_sheet"] == pr]
        na_saida = [x for x in itens if x["ref_sheet"] == pr]
        assert len(na_saida) == len(do_pai if lado == "pai" else do_filho)


def test_o_numero_de_itens_do_merge_e_exatamente_o_planejado():
    plano = merge_plano(PAI, FILHO)
    assert len(merge_itens(PAI, FILHO, plano)) == plano["total_itens"]


def test_nenhum_item_aparece_duas_vezes():
    plano = merge_plano(PAI, FILHO)
    itens = merge_itens(PAI, FILHO, plano)
    chaves = [(x["ref_sheet"], x["description"]) for x in itens]
    assert len(chaves) == len(set(chaves))


def test_o_merge_NAO_promove_selo():
    """🚨 Regra dura nº1. Item que chegou estimado sai estimado — o merge escolhe
    DE ONDE vem a linha, nunca o que ela vale."""
    plano = merge_plano(PAI, FILHO)
    itens = merge_itens(PAI, FILHO, plano)
    origem = {(x["ref_sheet"], x["description"]): x["confidence"]
              for x in PAI + FILHO}
    for x in itens:
        assert x["confidence"] == origem[(x["ref_sheet"], x["description"])]


def test_o_merge_preserva_a_taxonomia():
    """🚨 Regra dura nº4: discipline/section viajam colados no item."""
    plano = merge_plano(PAI, FILHO)
    for x in merge_itens(PAI, FILHO, plano):
        assert x.get("discipline") and x.get("section")


def test_mexer_na_saida_nao_mexe_na_entrada():
    """O merge devolve cópias — senão gravar o novo job corromperia a leitura
    original em memória."""
    plano = merge_plano(PAI, FILHO)
    itens = merge_itens(PAI, FILHO, plano)
    itens[0]["quantity"] = -999
    assert all(x["quantity"] != -999 for x in PAI + FILHO)


# ══════════════════════════════════════════════════════════════════════════
#  Sobreposição entre pranchas: APONTAR, nunca somar nem apagar
# ══════════════════════════════════════════════════════════════════════════
def test_acha_o_mesmo_sensor_contado_em_duas_pranchas():
    """🚨 O caso IVP: 22 na prancha de elétrica + 21 na de segurança = 43, quando
    o desenho tem ~22. Ler MAIS prancha criou a dobra."""
    plano = merge_plano(PAI, FILHO)
    sob = merge_sobreposicoes(merge_itens(PAI, FILHO, plano))
    ivp = [s for s in sob if s["codigo"] == "IVP"]
    assert ivp, "não apontou o IVP em duas pranchas"
    assert ivp[0]["soma_se_somar"] == 43
    assert ivp[0]["maior_sozinho"] == 22
    assert len(ivp[0]["pranchas"]) == 2


def test_NAO_soma_e_NAO_apaga_nada():
    """🚨 Regra dura nº3 e a lição de 17/08: a passada que removia 'duplicata'
    achou que Ø8 e Ø16 eram a mesma coisa e derrubou 18.168 kg para 508 kg."""
    plano = merge_plano(PAI, FILHO)
    itens = merge_itens(PAI, FILHO, plano)
    antes = len(itens)
    merge_sobreposicoes(itens)
    assert len(itens) == antes, "a detecção de sobreposição mexeu na lista"
    ivp = [x for x in itens if "IVP" in x["description"]]
    assert sorted(x["quantity"] for x in ivp) == [21, 22], (
        "alguém somou ou apagou o IVP")


def test_codigo_numa_prancha_so_nao_e_sobreposicao():
    """Controle negativo: senão todo código do projeto viraria alarme."""
    sob = merge_sobreposicoes([_it("A.dxf", "Sensor XPTO", 5),
                               _it("A.dxf", "Outro XPTO", 3)])
    assert not [s for s in sob if s["codigo"] == "XPTO"]


def test_item_zerado_nao_gera_alarme_de_dobra():
    """Linha com quantidade 0 não soma nada — alarmar sobre ela é ruído."""
    sob = merge_sobreposicoes([_it("A.dxf", "Sensor ZZZ", 0),
                               _it("B.dxf", "Sensor ZZZ", 0)])
    assert not sob


# ── O extrator de código ───────────────────────────────────────────────────
def test_pega_codigo_de_verdade():
    t = merge_tokens("Detector de presença/alarme IVP — bloco IVP")
    assert "IVP" in t


def test_pega_codigo_com_numero():
    assert "P80E" in merge_tokens("Porta P80E — folha simples — bloco P80E")


def test_NAO_confunde_palavra_portuguesa_em_caixa_alta():
    """🪤 'CAIXA' e 'PORTA' em caixa alta são palavra, não identidade — e geravam
    alarme falso ('Classificadora de caixa' × 'Caixa de passagem')."""
    t = merge_tokens("CAIXA de passagem na PAREDE — PORTA e PISO")
    assert not (t & {"CAIXA", "PAREDE", "PORTA", "PISO"})


def test_NAO_pega_palavra_normal():
    assert not merge_tokens("Alvenaria nova em bloco cerâmico com chapisco")


def test_unidade_diferente_nao_e_a_mesma_coisa():
    """Contagem de peças × metros de cabo do mesmo código não é dobra."""
    sob = merge_sobreposicoes([_it("A.dxf", "Cabo CFTV", 5, unit="un"),
                               _it("B.dxf", "Cabo CFTV", 30, unit="ml")])
    assert not sob


# ══════════════════════════════════════════════════════════════════════════
#  🔬 Contra DESCRIÇÃO REAL de produção, não contra o que eu imagino
# ══════════════════════════════════════════════════════════════════════════
#
# 🪤 A lição de 11/08: "teste fora do caminho real mede outra coisa" — me pegou
# 3 vezes numa noite. Estas strings vieram do banco de produção (jobs e1c48ed7
# e ev597afa, cliente Alan). O Postgres e o Python têm motores de regex
# diferentes; a detecção roda no Python e foi conferida contra o SQL: os dois
# apontam os MESMOS 16 códigos neste projeto.
_REAIS = [
    ("Eletroduto de aço carbono galvanizado a fogo (AGF) para sistema de CFTV",
     {"AGF", "CFTV"}),
    ("Sensor DTBC — fornecimento, instalação e configuração de sensor", {"DTBC"}),
    ("Identificação GGC — placa/sinalização de identificação", {"GGC"}),
    ("Detector de presença/alarme IVP — bloco IVP", {"IVP"}),
    ("Extintor de incêndio — fornecimento e instalação conforme PPCI", {"PPCI"}),
    ("Prateleira — conforme especificação do projeto (bloco PRAT)", {"PRAT"}),
]


def test_extrai_os_codigos_reais_do_projeto_do_alan():
    for desc, esperado in _REAIS:
        assert merge_tokens(desc) == esperado, desc


def test_caixa_mista_nao_vira_codigo():
    """'Midea' escrito assim não é identidade — só conta quando o nome do BLOCO
    traz 'MIDEA' em caixa alta, que é outro item."""
    assert not merge_tokens(
        "Fornecimento e instalação de split Hi-Wall Midea 12.000 BTU")
    assert "MIDEA" in merge_tokens("Ar-condicionado — bloco VA-Hi-Wall-MIDEA-12kBtu-VS")


def test_nome_de_bloco_composto_vira_pedacos_e_isso_esta_ok():
    """'EL_QUA.FORCA' sai como {'FORCA','QUA'} — pedaços, não o nome inteiro.

    Documentado de propósito: não é o ideal, mas também não é dano. Pedaço só
    vira alarme se cruzar prancha, e um quadro de força desenhado em duas
    pranchas É sobreposição de verdade. Se um dia isso gerar ruído, o conserto
    é deixar '_', '.' e '-' dentro do token — não mexer na stoplist."""
    assert merge_tokens("Quadro de força — EL_QUA.FORCA — quadro elétrico") == {"FORCA", "QUA"}


# ══════════════════════════════════════════════════════════════════════════
#  🖥️ O que a tela real mostrou, e o que precisou mudar
# ══════════════════════════════════════════════════════════════════════════
def test_varias_linhas_da_MESMA_prancha_viram_uma_entrada():
    """🚨 24/08, 1ª vez que o Pedro viu a tela. O CFTV saía assim:

        13 em AQ-E · 9 em EL-E · 3 em EL-E · 2 em EL-E · 1 em EL-E · 1 em EL-E

    Seis entradas da MESMA prancha — que são 6 tipos de câmera diferentes
    (CFTV3, CFTV8, CFTV16, CFTV4, CFTV12, DOME), e NÃO duplicata entre si.

    A pergunta da sobreposição é sempre ENTRE pranchas: "a prancha X e a Y
    estão mostrando o mesmo equipamento?". Sem somar por prancha primeiro, o
    alarme exagera e a linha vira ruído — e alarme ruidoso ensina a ignorar.
    """
    itens = [
        _it("AQ-E.dxf", "Câmera CFTV tipo 3", 13),
        _it("EL-E.dxf", "Câmera CFTV tipo 3 — bloco CFTV3", 9),
        _it("EL-E.dxf", "Câmera CFTV tipo 8 — bloco CFTV8", 3),
        _it("EL-E.dxf", "Câmera CFTV tipo 16 — bloco CFTV16", 2),
        _it("EL-E.dxf", "Câmera CFTV tipo 4 — bloco CFTV4", 1),
        _it("EL-E.dxf", "Câmera dome CFTV — bloco DOME", 1),
        _it("EL-E.dxf", "Câmera CFTV tipo 12 — bloco CFTV12", 1),
        _it("LO-E.dxf", "CFTV Sala Online", 1),
    ]
    s = [x for x in merge_sobreposicoes(itens) if x["codigo"] == "CFTV"][0]
    assert len(s["linhas"]) == 3, (
        "esperava UMA entrada por prancha (AQ-E, EL-E, LO-E), veio %d" % len(s["linhas"]))
    porp = {l["prancha"]: l["quantidade"] for l in s["linhas"]}
    assert porp == {"AQ-E.dxf": 13.0, "EL-E.dxf": 17.0, "LO-E.dxf": 1.0}


def test_a_entrada_da_prancha_diz_quantas_linhas_resumiu():
    """Sem isso, '17 em EL-E' esconde que ali são 6 tipos distintos — e o
    orçamentista precisa saber que não é uma linha só."""
    itens = [_it("A.dxf", "Câmera CFTV tipo 3", 9),
             _it("A.dxf", "Câmera CFTV tipo 8", 3),
             _it("B.dxf", "CFTV Sala", 1)]
    s = [x for x in merge_sobreposicoes(itens) if x["codigo"] == "CFTV"][0]
    a = [l for l in s["linhas"] if l["prancha"] == "A.dxf"][0]
    assert a["linhas"] == 2


def test_a_maior_prancha_sozinha_e_por_PRANCHA_nao_por_linha():
    """🔑 É o contraste que decide: 'somando daria 31, maior prancha sozinha 17'
    diz que há 14 unidades em risco. Com 'maior LINHA sozinha 13' o número não
    respondia pergunta nenhuma."""
    itens = [_it("A.dxf", "Sensor ZZZ tipo 1", 9),
             _it("A.dxf", "Sensor ZZZ tipo 2", 8),
             _it("B.dxf", "Sensor ZZZ geral", 15)]
    s = [x for x in merge_sobreposicoes(itens) if x["codigo"] == "ZZZ"][0]
    assert s["soma_se_somar"] == 32
    assert s["maior_sozinho"] == 17, "voltou a medir a maior LINHA em vez da maior PRANCHA"
