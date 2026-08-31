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


def test_o_antes_e_lido_TAMBEM_no_reject(monkeypatch):
    """🚨 31/08, AUDITORIA: esta era a versao FRACA deste teste. Ela fazia
    `assert 'if action in ("edit", "reject"):' in inspect.getsource(...)` — e
    essa substring aparece DUAS vezes na rota: uma e o conserto, a outra e
    codigo sem relacao nenhuma (invalidacao de assinatura). Desfazendo o
    conserto, a segunda ocorrencia ficava de pe e os 8 testes seguiam VERDES.

    O arquivo foi escrito HOJE como penitencia de "os 4 testes liam o FONTE", e
    metade dele ainda lia. Agora CHAMA a rota com action="reject" e olha a linha
    que foi parar em `item_reviews`.

    🔑 Por que o `_antes` importa tanto no reject: o item e APAGADO logo depois,
    e `item_reviews.item_id` tem FK ON DELETE CASCADE — o vinculo vai nulo de
    proposito. Entao `edits["_antes"]` e a UNICA copia do que o cliente excluiu."""
    gravadas = []
    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_insert",
                        lambda tabela, linha: gravadas.append((tabela, linha)) or True)

    _ITEM = {"id": "it-1", "description": "Parede de alvenaria (sobreposicao)",
             "quantity": 49.9, "unit": "m", "confidence": "estimado",
             "observations": "possivel sobreposicao com a prancha vizinha"}

    def _fake_rest(metodo, caminho, **kw):
        if metodo == "GET" and caminho.startswith("project_items"):
            return 200, [_ITEM]
        if metodo == "GET" and caminho.startswith("item_reviews"):
            return 200, []          # sem revisao anterior: vai INSERIR
        return 200, []
    monkeypatch.setattr(main, "_supa_rest_service", _fake_rest)

    class _P:
        action = "reject"
        edits = {}
        comment = "esse item nao existe na minha obra"
        reviewed_by = ""
    _erro = None
    try:
        main.submit_item_review("job-1", "it-1", _P(), None)
    except Exception as _e:
        _erro = _e    # o resto da rota (apagar o item, e-mail) nao e o objeto aqui
    # 🪤 sem isto, um AttributeError meu no dublê passava por "a rota nao gravou"
    # e eu ficaria consertando o codigo certo. Se nada foi gravado, mostre o erro.

    linhas = [l for (t, l) in gravadas if t == "item_reviews"]
    assert linhas, ("o reject nao gravou linha nenhuma em item_reviews "
                    "(excecao na rota: %r)" % (_erro,))
    edits = linhas[0].get("edits") or {}
    assert "_antes" in edits, (
        "o reject gravou SEM o _antes — como o item e apagado em seguida e a FK "
        "e CASCATA, isso apaga a unica copia do que o cliente excluiu")
    assert edits["_antes"].get("description") == _ITEM["description"]
    assert float(edits["_antes"].get("quantity") or 0) == 49.9


def test_CONTROLE_a_explicacao_da_cascata_continua_no_codigo():
    """Se um dia a FK virar SET NULL no banco, da pra simplificar - mas
    enquanto for CASCATA, gravar o vinculo no reject = perder o registro."""
    import inspect
    src = inspect.getsource(main.monta_linha_de_revisao)
    assert "CASCADE" in src, (
        "sumiu a explicacao de por que o item_id vai nulo - sem ela, alguem "
        "'conserta' isso de volta e a exclusao some outra vez")
