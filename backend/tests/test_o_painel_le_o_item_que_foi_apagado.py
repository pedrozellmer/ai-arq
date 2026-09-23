# -*- coding: utf-8 -*-
"""O painel de rejeições tem que ler o item que a rejeição APAGOU.

🩸 23/09/2026 — o painel "Itens mais rejeitados — indicam alucinação do motor,
candidatos a ajustar no prompt" mostrava:

    "Nenhum padrão de rejeição ainda."

com **432 rejeições** nos últimos 30 dias. Não era falta de dado — era o
painel procurando no lugar de onde o dado tinha sido removido:

    item_desc = item_descs.get(item_id)     # busca em project_items
    if action == "reject" and item_desc:    # NUNCA entra
        rejected_patterns[key] += 1

🔑 **Rejeitar APAGA o item** de `project_items`. Medido: dos 432 rejeitados,
**432 já não existiam** na tabela. `item_desc` vinha None nos 432 e o contador
ficava vazio pra sempre.

🔑 E o dado estava guardado: `edits._antes` traz o item INTEIRO no momento da
rejeição. Uma consulta nele revelou o que o painel devia mostrar há 30 dias:
**82 rejeições de mobiliário, 71 com selo MEDIDO**, e **117 linhas "a
confirmar"** onde o motor acha o código e não lê o quadro.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _corpo import corpo_de  # noqa: E402


def _carrega():
    """Executa SÓ a função do main.py — importar o módulo inteiro conecta em
    Supabase/Stripe. Mesmo padrão de `test_area_honesty_pd`."""
    ns = {"__name__": "painel_ns"}
    exec(compile(corpo_de("retrato_do_item_revisado"), "main_slice", "exec"), ns)
    return ns["retrato_do_item_revisado"]


retrato_do_item_revisado = _carrega()


def _review(action="reject", desc=None, disc=None, conf=None, edits=True):
    r = {"action": action, "item_id": "abc-123"}
    if edits:
        antes = {}
        if desc is not None:
            antes["description"] = desc
        if disc is not None:
            antes["discipline"] = disc
        if conf is not None:
            antes["confidence"] = conf
        r["edits"] = {"_antes": antes}
    return r


# ══════════════════════════════════════════════════════════════════════════
#  O CASO REAL: o item foi apagado
# ══════════════════════════════════════════════════════════════════════════
def test_le_o_item_APAGADO_pelo_retrato_guardado():
    """Os 432: `project_items` não tem mais, `edits._antes` tem."""
    r = _review(desc="Arara frontal adulto — expositor conforme bloco",
                disc="Mobiliário", conf="confirmado")
    desc, disc, medido = retrato_do_item_revisado(r, None)
    assert desc.startswith("Arara frontal adulto"), desc
    assert disc == "Mobiliário"
    assert medido is True, "era linha com selo MEDIDO — o caso mais grave"


def test_CONTROLE_o_codigo_VELHO_nao_veria_nada():
    """Prova que o painel ficava vazio: sem a tabela, ele não tinha fonte."""
    r = _review(desc="Gôndola sem cabeceira", disc="Mobiliário")
    desc_velho = None          # item_descs.get(item_id) — item apagado
    assert desc_velho is None, (
        "o controle parou de provar: o item rejeitado TEM que sumir da tabela")
    assert retrato_do_item_revisado(r, desc_velho)[0] == "Gôndola sem cabeceira"


def test_marca_quando_a_linha_rejeitada_saiu_como_MEDIDA():
    """🚨 Regra dura nº1: é onde a credibilidade do selo branco é gasta."""
    assert retrato_do_item_revisado(
        _review(desc="x", conf="confirmado"), None)[2] is True
    assert retrato_do_item_revisado(
        _review(desc="x", conf="estimado"), None)[2] is False
    assert retrato_do_item_revisado(
        _review(desc="x"), None)[2] is False


def test_devolve_a_disciplina_pra_separar_inventado_de_escopo():
    """Mobiliário rejeitado é motor inventando; Hidráulica é cliente cortando."""
    assert retrato_do_item_revisado(
        _review(desc="x", disc="Mobiliário"), None)[1] == "Mobiliário"


# ══════════════════════════════════════════════════════════════════════════
#  A TABELA VEM PRIMEIRO quando o item ainda existe
# ══════════════════════════════════════════════════════════════════════════
def test_quando_o_item_EXISTE_vale_a_descricao_ATUAL():
    """🪤 `approve`/`edit` não apagam o item, e o cliente pode ter corrigido a
    descrição depois. O retrato é de ANTES — usá-lo ali mostraria o texto
    velho como se fosse o atual."""
    r = _review(action="edit", desc="Descricao ANTIGA", disc="Forros")
    desc, disc, _ = retrato_do_item_revisado(r, "Descricao ATUAL corrigida")
    assert desc == "Descricao ATUAL corrigida", desc
    assert disc == "Forros", "a disciplina ainda sai do retrato"


# ══════════════════════════════════════════════════════════════════════════
#  NÃO PODE QUEBRAR
# ══════════════════════════════════════════════════════════════════════════
def test_review_sem_edits_nao_explode():
    assert retrato_do_item_revisado(_review(edits=False), None) == (None, None, False)


def test_edits_em_formato_inesperado_nao_explode():
    for ruim in ({"edits": None}, {"edits": []}, {"edits": "texto"},
                 {"edits": {"_antes": None}}, {"edits": {"_antes": "x"}},
                 {"edits": {}}, {}, None):
        assert retrato_do_item_revisado(ruim, None) == (None, None, False), ruim


def test_descricao_vazia_conta_como_ausente():
    """String vazia não pode virar chave de padrão no contador."""
    assert retrato_do_item_revisado(_review(desc=""), None)[0] is None
    assert retrato_do_item_revisado(_review(desc="   "), None)[0] is None


def test_a_chave_do_padrao_agrupa_por_tres_palavras():
    """É como o painel agrupa — duas araras diferentes viram o mesmo padrão."""
    a = retrato_do_item_revisado(
        _review(desc="Arara frontal adulto Pepe — expositor"), None)[0]
    b = retrato_do_item_revisado(
        _review(desc="Arara frontal adulto infantil — outro"), None)[0]
    assert " ".join(a.lower().split()[:3]) == " ".join(b.lower().split()[:3])


def test_o_selo_MEDIDO_tambem_sai_quando_o_item_AINDA_existe():
    """🩸 A sabotagem pegou este buraco: eu só testava o caminho do item
    apagado, e o caminho da tabela devolvia o selo sem nenhum guarda olhando.

    Vale pra `edit`/`approve`, que não apagam o item: saber que a linha tocada
    tinha selo MEDIDO é o mesmo sinal da regra dura nº1.
    """
    r = _review(action="edit", desc="qualquer", disc="Forros", conf="confirmado")
    desc, disc, medido = retrato_do_item_revisado(r, "Descricao ATUAL")
    assert desc == "Descricao ATUAL"
    assert disc == "Forros"
    assert medido is True, (
        "com o item na tabela, o selo MEDIDO do retrato tem que sair igual")


def test_com_o_item_na_tabela_e_selo_estimado_NAO_marca():
    r = _review(action="edit", desc="qualquer", conf="estimado")
    assert retrato_do_item_revisado(r, "Descricao ATUAL")[2] is False
