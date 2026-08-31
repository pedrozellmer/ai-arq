# -*- coding: utf-8 -*-
"""A exclusão do cliente deixa rastro (31/08/2026).

🩸 O buraco, medido no banco: `item_reviews.item_id` tem FK pra
`project_items` com **ON DELETE CASCADE**. No `reject`, o backend gravava o
registro da exclusão e logo abaixo apagava o item — e o banco levava o
registro junto. Resultado em toda a história do produto:
    approve: 184   edit: 108   reject: 0
Zero. Com o botão da lixeira existindo desde sempre (e ganhando confirmação
dupla em 09/08 justamente porque gente usava demais).

🔑 Exclusão é o sinal MAIS direto de erro do motor — é o cliente dizendo
"isto não existe na minha obra". Perdemos 4 meses disso, calado.

Conserto sem tocar no schema de produção: no reject o `item_id` vai NULO
(sem vínculo = sem cascata) e o id real fica dentro de `edits`, que é jsonb
e não tem FK. Junto: o "antes" passa a ser lido também no reject — senão o
registro sobrevive dizendo nada.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


def _fonte_da_rota():
    import inspect
    return inspect.getsource(main.submit_item_review)


def test_reject_grava_SEM_vinculo_com_o_item():
    """Com vínculo, a cascata do banco apaga o registro junto com o item."""
    src = _fonte_da_rota()
    assert '"item_id": (None if action == "reject" else item_id)' in src, (
        "o reject voltou a gravar item_id preenchido — a FK é ON DELETE "
        "CASCADE e o registro vai ser apagado junto com o item")


def test_o_id_do_item_excluido_fica_guardado():
    """Sem vínculo, mas sem perder QUAL item era."""
    src = _fonte_da_rota()
    assert '_item_id' in src, "o id do item excluído não está sendo preservado"


def test_o_antes_e_lido_TAMBEM_no_reject():
    """Registro que sobrevive sem dizer O QUE sumiu não serve pra nada."""
    src = _fonte_da_rota()
    assert 'if action in ("edit", "reject"):' in src, (
        "o 'antes' voltou a ser lido só no edit — a exclusão fica sem conteúdo")


def test_CONTROLE_a_FK_continua_em_cascata():
    """🧪 Este teste documenta POR QUE o conserto é assim. Se um dia a FK virar
    SET NULL no banco, dá pra simplificar — mas enquanto for CASCATA, gravar o
    vínculo no reject = perder o registro. O guarda de cima depende disto."""
    src = _fonte_da_rota()
    # a explicação tem que continuar no código pra ninguém "simplificar" sem saber
    assert "CASCADE" in src, (
        "sumiu o comentário que explica por que o item_id vai nulo — sem ele, "
        "alguém 'conserta' isso de volta e a exclusão some outra vez")
