# -*- coding: utf-8 -*-
"""A exclusão do cliente tem que virar aprendizado (01/09/2026).

🩸 A CADEIA INTEIRA, que levou 4 meses pra fechar:
  1. o cliente exclui um item na tela → é o sinal MAIS FORTE que existe. Editar
     diz "o número está errado"; excluir diz "este item o motor INVENTOU";
  2. até 31/08 o registro se autodestruía: `item_reviews.item_id` tinha FK
     ON DELETE CASCADE, então apagar o item apagava a prova junto. Resultado:
     184 approve, 108 edit e **0 reject** em 4 meses de produto;
  3. consertado o CASCADE, as exclusões começaram a chegar — 20 em 2 projetos,
     16 com o `_antes` completo;
  4. 🪤 e aí apareceu ESTE buraco: `processar_revisao_inline` filtrava
     `action=eq.edit` e jogava fora todo reject. O cliente-14 fez **18 exclusões**
     e o aprendizado gerou **zero linhas**.

🔑 É o padrão da casa: consertar um bug LIGA código que estava morto, e o passo
seguinte não aceita o que passou a chegar. O comparador já sabia classificar
"removido" desde sempre — nunca tinha sido alimentado.

🪤 O item excluído entra só do lado ORIGINAL. Pôr também do lado revisado o
transformaria em "alterado", e o pareamento fuzzy poderia casá-lo com um item
parecido que o cliente MANTEVE — inventando uma alteração que ninguém fez.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import revision_feedback as rf  # noqa: E402

_CAMPOS = ("item_num", "description", "unit", "quantity", "confidence", "discipline")


def _item(num, desc, unit, qtd, disc="Fechamentos", conf="estimado", _id=None):
    d = {"item_num": num, "description": desc, "unit": unit, "quantity": qtd,
         "confidence": conf, "discipline": disc}
    if _id:
        d["id"] = _id
    return d


def _monta(monkeypatch, atuais, editados, excluidos):
    """Dublê das duas leituras + captura do que seria gravado."""
    gravado = {}
    monkeypatch.setattr(rf, "_buscar_itens_com_id", lambda job: atuais)
    monkeypatch.setattr(rf, "_buscar_antes_das_edicoes",
                        lambda job: (editados, excluidos))
    monkeypatch.setattr(rf, "salvar_feedback",
                        lambda job, res, arquivo="": gravado.update(res) or True)
    return gravado


def test_exclusao_SOZINHA_ja_gera_aprendizado(monkeypatch):
    """🚨 O caso do cliente-14: 18 exclusões, nenhuma edição. Antes disto, o
    aprendizado devolvia False e a revisão inteira ia pro lixo."""
    atuais = [_item("1.1", "Piso cerâmico", "m²", 80.0, "Pisos", _id="a")]
    excluido = {k: v for k, v in _item(
        "2.1", "Parede contada duas vezes", "m", 49.9).items()}
    gravado = _monta(monkeypatch, atuais, {}, [excluido])

    ok = rf.processar_revisao_inline("job-1")
    assert ok is True, "exclusão sozinha não gerou linha de aprendizado"
    assert gravado["totais"]["n_removidos"] == 1, gravado["totais"]
    assert gravado["totais"]["n_alterados"] == 0, (
        "a exclusão virou 'alterado' — o item excluído não pode entrar do lado "
        "revisado")


def test_o_item_EXCLUIDO_aparece_com_o_que_o_cliente_apagou(monkeypatch):
    """Sem o conteúdo, o registro diz que algo sumiu e não diz O QUÊ — e é o
    'o quê' que ensina o motor a não inventar de novo."""
    atuais = [_item("1.1", "Piso cerâmico", "m²", 80.0, "Pisos", _id="a")]
    excluido = {"item_num": "2.1", "description": "Parede contada duas vezes",
                "unit": "m", "quantity": 49.9, "confidence": "estimado",
                "discipline": "Fechamentos"}
    gravado = _monta(monkeypatch, atuais, {}, [excluido])
    rf.processar_revisao_inline("job-1")
    removidos = [i for i in gravado["itens"] if i.get("acao") == "removido"]
    assert removidos, "nenhum item marcado como removido"
    achou = str(removidos[0]).lower()
    assert "parede contada duas vezes" in achou, (
        "o registro não guarda a descrição do que foi excluído: %s" % removidos[0])


def test_edicao_e_exclusao_JUNTAS_contam_as_duas(monkeypatch):
    atuais = [_item("1.1", "Piso cerâmico", "m²", 95.0, "Pisos", _id="a")]
    editados = {"a": {"quantity": 80.0}}          # cliente corrigiu 80 -> 95
    excluido = {"item_num": "2.1", "description": "Item que não existe na obra",
                "unit": "un", "quantity": 3, "confidence": "estimado",
                "discipline": "Complementares"}
    gravado = _monta(monkeypatch, atuais, editados, [excluido])
    rf.processar_revisao_inline("job-1")
    t = gravado["totais"]
    assert t["n_removidos"] == 1 and t["n_alterados"] == 1, t


def test_CONTROLE_so_aprovacao_continua_NAO_gerando(monkeypatch):
    """🧪 Aprovar sem corrigir não ensina nada — e gerar linha vazia infla o
    painel de aprendizado com projeto que não ensinou nada."""
    atuais = [_item("1.1", "Piso cerâmico", "m²", 80.0, "Pisos", _id="a")]
    _monta(monkeypatch, atuais, {}, [])
    assert rf.processar_revisao_inline("job-1") is False


def test_CONTROLE_projeto_sem_itens_nao_quebra(monkeypatch):
    _monta(monkeypatch, [], {}, [{"description": "x", "unit": "un",
                                  "quantity": 1, "item_num": "1",
                                  "confidence": "estimado", "discipline": "y"}])
    assert rf.processar_revisao_inline("job-1") is False


def test_CONTROLE_a_busca_pede_edit_E_reject():
    """🪤 Guarda de call-site: a função pode estar certa e a CONSULTA continuar
    filtrando só 'edit' — foi exatamente assim que a exclusão sumiu por meses."""
    import inspect
    src = inspect.getsource(rf._buscar_antes_das_edicoes)
    assert "action=in.(edit,reject)" in src, (
        "a consulta voltou a pedir só 'edit' — a exclusão some de novo, calada")
