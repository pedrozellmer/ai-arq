# -*- coding: utf-8 -*-
"""A chave do selo: a única régua da casa que PROMOVE — e só com prova.

🩸 22/09/2026. Até hoje TODA régua de revisão só sabia rebaixar: "Só REBAIXA.
Nunca promove nada" aparece em 12 lugares, e há 32 pontos de rebaixamento só
no `main.py`. O efeito, medido no acervo de 60 dias: quem decide o teto do que
sai medido é a IA, e o revisor só pode baixá-lo. Em 69 jobs com CAD, **15
entregaram ZERO linha medida** e 43 (62%) menos de 1 em 4 — com a geometria
medida ali, no mesmo envio.

🔑 Esta régua roda POR ÚLTIMO, depois das 32 travas, e promove só o que a
geometria do arquivo prova: a quantidade da linha É um número que o motor
mediu. Nenhuma trava é desarmada — a prova exigida é o NÚMERO, não a redação.

🧪 Controles positivos (sem eles, "promoveu" passaria por mérito falso):
o que a IA declarou ter ADOTADO não sobe; layer de anotação não sobe (a rede
de 24/08, 61 itens em 19 projetos selados a partir de texto); `vision_pdf`
nunca sobe (regra dura nº1); e quem já está confirmado não é tocado.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from engine_rules import (  # noqa: E402
    prova_da_geometria,
    selo_com_prova_da_geometria as chave,
)

#: o que o motor mediu num envio real de estrutura (job 64fa324b)
INDICE = {
    "area": [("0", 194.08), ("FO-Textos das lajes", 88.0)],
    "comprimento": [("FO-Vigas", 1041.24), ("FO-Textos dos pilares", 312.5)],
    "contagem": [("PILAR-18x40", 16), ("PORTA-80", 7)],
}


def _it(q, unit="m²", obs="", conf="estimado", origem="dxf_geom", desc="Item"):
    return {"description": desc, "unit": unit, "quantity": q,
            "confidence": conf, "observations": obs, "origem": origem}


# ── o que a geometria prova ────────────────────────────────────────────────
@pytest.mark.parametrize("q, unit, porque", [
    (194.08, "m²", "área hachurada medida no layer 0"),
    (1041.24, "m", "comprimento somado do layer FO-Vigas"),
    (1041.24, "ml", "ml é a mesma grandeza que m"),
    (16, "un", "contagem literal de blocos"),
    (194.0799, "m²", "0,5% de tolerância — arredondamento não derruba prova"),
])
def test_a_quantidade_que_o_motor_MEDIU_sobe(q, unit, porque):
    achados = chave([_it(q, unit)], INDICE)
    assert len(achados) == 1, porque
    assert achados[0]["motivo"]


def test_a_observacao_diz_de_ONDE_veio_a_prova():
    """O motivo vira rastro: sem ele ninguém audita a promoção depois."""
    motivo = prova_da_geometria(194.08, "m²", "", INDICE)
    assert "layer '0'" in motivo and "194,08" in motivo


# ── controles positivos: o que NÃO pode subir ──────────────────────────────
@pytest.mark.parametrize("obs, porque", [
    ("Estimado. Seção predominante 14×40 cm adotada como dominante.",
     "o modelo ADOTOU a seção — insumo dele, não do arquivo"),
    ("Área considerada igual à da laje do pavimento tipo.",
     "'considerada' é adoção"),
    ("Espessura de praxe 10 cm.", "praxe é convenção, não medida"),
    ("Valor aproximado conferido em obra.", "aproximado não é medido"),
    ("Área arbitrada pela planta de cobertura.", "arbitrada é escolha"),
])
def test_CONTROLE_insumo_que_a_IA_ADOTOU_nao_sobe(obs, porque):
    assert chave([_it(194.08, "m²", obs)], INDICE) == [], porque


def test_CONTROLE_layer_de_ANOTACAO_nao_sobe():
    """A rede de 24/08: 61 itens em 19 projetos saíram medidos a partir de
    texto de prancha. O comprimento das letras é real e não é serviço."""
    assert chave([_it(88.0, "m²")], INDICE) == [], (
        "'FO-Textos das lajes' é anotação — não pode virar medida")


def test_CONTROLE_item_de_PDF_nunca_sobe():
    """Regra dura nº1: Vision lê número, não mede geometria."""
    assert chave([_it(194.08, "m²", origem="vision_pdf")], INDICE) == []


def test_CONTROLE_quem_ja_esta_CONFIRMADO_nao_e_tocado():
    assert chave([_it(194.08, "m²", conf="confirmado")], INDICE) == []


def test_CONTROLE_linha_em_BRANCO_nao_vira_medida():
    """Quantidade zero é o que o cliente preenche — promover viraria número
    do nada."""
    assert chave([_it(0, "m²")], INDICE) == []


@pytest.mark.parametrize("unit", ["m³", "kg", "vb", "cj"])
def test_CONTROLE_unidade_que_o_motor_NAO_mede_nao_sobe(unit):
    """O motor mede comprimento, área e contagem. Volume é sempre área ×
    espessura (e a espessura vem de texto); peso vem de tabela."""
    assert chave([_it(194.08, unit)], INDICE) == []


def test_CONTROLE_numero_que_NAO_bate_com_nada_nao_sobe():
    assert chave([_it(77.77, "m²")], INDICE) == []


def test_CONTROLE_a_grandeza_tem_que_casar_com_a_unidade():
    """1041,24 é comprimento medido; a mesma quantidade em m² não é prova."""
    assert chave([_it(1041.24, "m²")], INDICE) == []
    assert len(chave([_it(1041.24, "m")], INDICE)) == 1


def test_a_chave_NUNCA_rebaixa():
    """Anda só pra cima: item confirmado sem prova nenhuma sai como entrou."""
    itens = [_it(77.77, "m²", conf="confirmado")]
    assert chave(itens, INDICE) == []
    assert itens[0]["confidence"] == "confirmado"


def test_indice_vazio_nao_promove_nada():
    assert chave([_it(194.08, "m²")], {}) == []
    assert chave([_it(194.08, "m²")], None) == []


# ══════════════════════════════════════════════════════════════════════════
#  A chave está LIGADA — e no lugar certo
#  🪤 A lição da miniatura (17/09) e a das três mutações inócuas (18/09):
#     presença não é consequência. Uma régua perfeita chamada depois de
#     gravar, ou com o retorno no lixo, deixa a bancada verde e o cliente
#     com a planilha laranja.
# ══════════════════════════════════════════════════════════════════════════
import ast  # noqa: E402

_MAIN = os.path.join(os.path.dirname(_AQUI), "main.py")


def _process_job_ast():
    with open(_MAIN, encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == "process_job":
            return no
    raise AssertionError("não achei process_job em main.py")


def _linhas_de(fn, alvo):
    """Linhas em que `alvo` é chamado dentro da função."""
    fora = []
    for no in ast.walk(fn):
        if not isinstance(no, ast.Call):
            continue
        f = no.func
        nome = getattr(f, "id", None) or getattr(f, "attr", None)
        if nome == alvo:
            fora.append(no.lineno)
    return fora


def test_a_chave_e_chamada_UMA_vez_no_fluxo_do_job():
    chamadas = _linhas_de(_process_job_ast(), "_chave_selo")
    assert len(chamadas) == 1, (
        "esperava uma única chamada da chave do selo no process_job e achei "
        "%d — duas chamadas viram isca (a 2ª mascara a 1ª)" % len(chamadas))


def test_a_chave_roda_ANTES_de_gravar_no_banco():
    """🔑 Depois do `_persist_items_to_supabase` ela promoveria objetos em
    memória que o banco já não tem — verde na bancada, laranja pro cliente."""
    fn = _process_job_ast()
    chave = _linhas_de(fn, "_chave_selo")
    grava = _linhas_de(fn, "_persist_items_to_supabase")
    assert chave and grava, "sumiu a chave ou a gravação"
    assert min(chave) < min(grava), (
        "a chave do selo roda DEPOIS de gravar (linha %d vs %d): o cliente "
        "receberia a planilha sem as promoções" % (min(chave), min(grava)))


def test_a_chave_roda_DEPOIS_das_travas_de_rebaixamento():
    """A ordem inversa desfaria rebaixamento legítimo: promover primeiro e
    rebaixar depois é o mesmo que não promover — mas com log dizendo que sim."""
    fn = _process_job_ast()
    chave = min(_linhas_de(fn, "_chave_selo"))
    for trava in ("_tira_medido_do_desenho_de_quem_nao_foi_menos",
                  "_tira_medido_do_desenho_de_quem_nao_foi_medido"):
        linhas = _linhas_de(fn, trava)
        if linhas:
            assert min(linhas) < chave, (
                "%s roda DEPOIS da chave — o rebaixamento desfaria a "
                "promoção" % trava)


def test_o_retorno_da_chave_NAO_vai_pro_lixo():
    """🩸 Uma das três mutações de 18/09 que passaram verdes foi exatamente
    esta: chamar a régua e jogar o retorno fora. Aqui o retorno TEM que virar
    atribuição de `confidence` em algum item."""
    fn = _process_job_ast()
    usa_confidence = False
    for no in ast.walk(fn):
        if isinstance(no, ast.Assign):
            for alvo in no.targets:
                if getattr(alvo, "attr", None) != "confidence":
                    continue
                v = no.value
                # 🔑 22/09: a promoção passa pela PORTA ÚNICA
                # (`_selo_medido_com_prova`), não por `Confidence('confirmado')`
                # solto — ver test_selo_exige_geometria. O guarda segue o
                # caminho novo em vez de cobrar a forma antiga.
                if isinstance(v, ast.Call):
                    nome = getattr(v.func, "id", None) or getattr(v.func, "attr", None)
                    if nome == "_selo_medido_com_prova":
                        usa_confidence = True
    assert usa_confidence, (
        "nenhuma promoção pela porta única no process_job — a chave está "
        "chamada mas não muda selo nenhum")
