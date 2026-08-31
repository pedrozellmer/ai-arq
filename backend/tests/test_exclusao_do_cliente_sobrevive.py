# -*- coding: utf-8 -*-
"""A exclusao do cliente deixa rastro (31/08/2026).

O buraco, medido no banco: `item_reviews.item_id` tem FK pra `project_items`
com ON DELETE CASCADE. No `reject`, o backend gravava o registro da exclusao e
logo abaixo apagava o item - e o banco levava o registro junto. Placar de toda
a historia do produto ate 31/08:  approve 184 | edit 108 | reject 0.
Zero, com o botao da lixeira existindo desde sempre (e ganhando confirmacao
dupla em 09/08 justamente porque gente usava demais).

Exclusao e o sinal MAIS direto de erro do motor - o cliente dizendo "isto nao
existe na minha obra". Perdemos 4 meses disso, calado.

Conserto sem tocar no schema de producao: no reject o `item_id` vai NULO (sem
vinculo = sem cascata) e o id real fica dentro de `edits`, que e jsonb e nao
tem FK. Junto: o "antes" passa a ser lido tambem no reject - senao o registro
sobrevive dizendo nada.

RECAIDA NO MESMO DIA, e a licao que fica: a 1a versao deste arquivo tinha 4
testes e TODOS liam o FONTE da rota (`'_item_id' in src`). A string estava la,
o pytest ficou verde, e em producao o `_item_id` nunca chegou ao banco - dois
`if` seguidos refaziam o dicionario e o segundo apagava o primeiro. Quem pegou
foi o cliente. Agora os guardas CHAMAM `monta_linha_de_revisao` e conferem o
dicionario que sai. Ver feedback_guarda_que_le_fonte.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

JOB = "job-teste"
ITEM = "11111111-2222-3333-4444-555555555555"
ANTES = {"description": "Parede - layer 00_PAREDE", "unit": "m2",
         "quantity": 115.32, "confidence": "estimado"}


def _reject(edits=None, antes=ANTES):
    return main.monta_linha_de_revisao(JOB, ITEM, "reject", edits, antes)


def test_reject_grava_SEM_vinculo_com_o_item():
    """Com vinculo, a cascata do banco apaga o registro junto com o item."""
    assert _reject()["item_id"] is None, (
        "o reject voltou a gravar item_id preenchido - a FK e ON DELETE "
        "CASCADE e o registro vai ser apagado junto com o item")


def test_o_id_do_item_excluido_fica_guardado():
    """Sem vinculo, mas sem perder QUAL item era."""
    assert _reject()["edits"]["_item_id"] == ITEM


def test_o_reject_guarda_id_E_conteudo_JUNTOS():
    """O bug de 31/08 em uma linha: um enriquecimento apagava o outro.

    Este e o teste que faltava. Os dois tem que sair na MESMA linha - id sem
    conteudo nao diz o que sumiu; conteudo sem id nao se liga a nada."""
    edits = _reject()["edits"]
    assert "_item_id" in edits and "_antes" in edits, (
        f"reject perdeu metade do rastro: chaves={sorted(edits)}")
    assert edits["_antes"]["description"] == ANTES["description"]


def test_o_que_o_cliente_mandou_nao_e_atropelado():
    """Enriquecer nao pode apagar o payload do cliente."""
    edits = _reject(edits={"comment_extra": "nao existe na obra"})["edits"]
    assert edits["comment_extra"] == "nao existe na obra"
    assert "_item_id" in edits and "_antes" in edits


def test_edit_continua_com_vinculo_e_com_antes():
    """CONTROLE: so o reject perde o vinculo. Edit nao apaga o item, entao a
    cascata nao o ameaca - e o vinculo vale (une revisao e item)."""
    linha = main.monta_linha_de_revisao(JOB, ITEM, "edit", {"quantity": 9}, ANTES)
    assert linha["item_id"] == ITEM, "edit nao pode perder o vinculo"
    assert linha["edits"]["_antes"] == ANTES
    assert "_item_id" not in linha["edits"], "so o reject precisa do id avulso"


def test_approve_sem_antes_nao_inventa_chave():
    """CONTROLE NEGATIVO: aprovacao simples nao mexe em edits."""
    linha = main.monta_linha_de_revisao(JOB, ITEM, "approve", None, None)
    assert linha["item_id"] == ITEM and linha["edits"] is None


def test_o_antes_e_lido_TAMBEM_no_reject():
    """O 'antes' vem de uma leitura no banco la na rota; aqui so garanto que a
    rota continua pedindo essa leitura pro reject. Este SIM le o fonte - de
    proposito, porque e uma chamada de I/O que o unit test nao executa."""
    import inspect
    src = inspect.getsource(main.submit_item_review)
    assert 'if action in ("edit", "reject"):' in src, (
        "o 'antes' voltou a ser lido so no edit - a exclusao fica sem conteudo")


def test_CONTROLE_a_explicacao_da_cascata_continua_no_codigo():
    """Se um dia a FK virar SET NULL no banco, da pra simplificar - mas
    enquanto for CASCATA, gravar o vinculo no reject = perder o registro."""
    import inspect
    src = inspect.getsource(main.monta_linha_de_revisao)
    assert "CASCADE" in src, (
        "sumiu a explicacao de por que o item_id vai nulo - sem ela, alguem "
        "'conserta' isso de volta e a exclusao some outra vez")
