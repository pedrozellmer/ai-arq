# -*- coding: utf-8 -*-
"""O financeiro entra na coerencia do projeto — medido EXECUTANDO a funcao."""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402

JOB = "job-coer-1"
ITEM = {"id": "11111111-1111-4111-8111-111111111111",
        "description": "Porcelanato 60x60", "quantity": 1062.0, "unit": "m2"}


def _linha(**k):
    base = {"id": "l1", "origem": "quantitativo", "origem_ref_id": ITEM["id"],
            "origem_ref_pos": None, "origem_quantidade": 1062.0,
            "origem_unidade": "m2", "descricao": "Porcelanato 60x60"}
    base.update(k)
    return base


def _servico(monkeypatch, lanc, itens):
    """Devolve a lista de caminhos LIDOS — quem foi consultado também é fato."""
    lidos = []

    def fake(method, path, body=None, params=None, prefer=None, timeout=15):
        lidos.append(path)
        if "/financeiro_lancamentos?" in path:
            return lanc
        if "/project_items?" in path:
            return itens
        return (200, [])
    monkeypatch.setattr(main, "_supa_rest_service", fake)
    return lidos


def test_so_linhas_livres_ou_de_cotacao_nao_desatualizam(monkeypatch):
    """🪤 O guarda velho olhava só `desatualizado is False` — e isso é False
    pelos dois caminhos, porque `_fin_estado_da_origem` também devolve 'ok'
    pra origem que não é quantitativo. A mutação passava por cima dele.

    O que MUDA de verdade: com só linha livre/comparativo, a função nem PRECISA
    ler o quantitativo. Se ela for lá, o banco fora do ar vira `indisponivel`
    num financeiro que está em dia — alarme sobre nada, e uma consulta a mais
    em toda abertura de projeto."""
    lidos = _servico(monkeypatch,
                     (200, [_linha(origem="livre"),
                            _linha(id="l2", origem="comparativo")]),
                     (500, None))
    c = main._coerencia_do_financeiro(JOB)
    assert c["existe"] is True and c["n"] == 2
    assert c["desatualizado"] is False, (
        "linha livre/comparativo foi vigiada pela régua do quantitativo: %s" % c)
    assert not c.get("indisponivel"), (
        "com o quantitativo fora do ar, um financeiro só de linha livre saiu "
        "como 'não sei dizer': %s" % c)
    assert c["mudados"] == 0 and c["frase"] == ""
    assert not [p for p in lidos if "project_items" in p], (
        "foi ler o quantitativo pra conferir linha que não nasceu dele: %s" % lidos)

    # 🧪 Controle positivo: a MESMA base, com linha DO QUANTITATIVO, lê e acusa.
    lidos2 = _servico(monkeypatch, (200, [_linha()]),
                      (200, [{**ITEM, "quantity": 990.0}]))
    c2 = main._coerencia_do_financeiro(JOB)
    assert [p for p in lidos2 if "project_items" in p], (
        "nem a linha do quantitativo faz a função ler o quantitativo")
    assert c2["desatualizado"] is True and c2["mudados"] == 1, (
        "controle: o item mudou de 1062 para 990 e a régua não viu — o teste "
        "acima não prova nada")
