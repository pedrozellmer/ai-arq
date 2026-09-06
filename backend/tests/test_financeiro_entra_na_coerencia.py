# -*- coding: utf-8 -*-
"""Regra nº7, cláusula "no mesmo commit em que nasce": o financeiro da obra entra no
aviso de coerência do projeto.

Auditoria de 06/09/2026: o financeiro nasceu em 05/09 e NÃO tinha entrado em
`_coerencia_do_projeto` nem em coerencia.js — a tela do financeiro marcava linha a
linha ("item mudou"), mas o painel do projeto dizia "tudo em dia". Este arquivo
cobra o fato pela mesma régua da tela (`_fin_estado_da_origem`):
  • lançamento do quantitativo cujo retrato (quantidade/unidade) não bate com o item
    de agora → `desatualizado`, com a frase que o painel mostra;
  • só linhas livres/comparativo → em dia (não vigiamos a cotação ainda);
  • leitura falhando → `indisponivel`, nunca "em dia" por engano;
  • o painel (coerencia.js) tem o financeiro e o botão leva pra financeiro.html.
🧪 Controle: retrato IGUAL ao item → não desatualiza.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _corpo import fonte, sem_comentarios  # noqa: E402

JOB = "job-coer-1"
ITEM = {"id": "11111111-1111-4111-8111-111111111111", "description": "Porcelanato 60x60", "quantity": 1062.0, "unit": "m2"}


def _servico(monkeypatch, lanc, itens):
    def fake(method, path, body=None, params=None, prefer=None, timeout=15):
        if "/financeiro_lancamentos?" in path:
            return lanc
        if "/project_items?" in path:
            return itens
        return (200, [])
    monkeypatch.setattr(main, "_supa_rest_service", fake)


def _linha(**k):
    base = {"id": "l1", "origem": "quantitativo", "origem_ref_id": ITEM["id"], "origem_ref_pos": None,
            "origem_quantidade": 1062.0, "origem_unidade": "m2", "descricao": "Porcelanato 60x60"}
    base.update(k)
    return base


def test_CONTROLE_retrato_igual_ao_item_esta_em_dia(monkeypatch):
    _servico(monkeypatch, (200, [_linha()]), (200, [ITEM]))
    c = main._coerencia_do_financeiro(JOB)
    assert c["existe"] is True and c["desatualizado"] is False and c["n"] == 1 and c["frase"] == ""


def test_item_que_mudou_de_quantidade_desatualiza_com_a_frase(monkeypatch):
    _servico(monkeypatch, (200, [_linha(), _linha(id="l2", origem_ref_id="22222222-2222-4222-8222-222222222222",
                                                  descricao="Rejunte")]),
             (200, [{**ITEM, "quantity": 990.0}]))
    c = main._coerencia_do_financeiro(JOB)
    assert c["desatualizado"] is True and c["mudados"] == 1 and c["removidos"] == 1 and c["n_velhos"] == 2
    assert c["frase"] == "1 com item que mudou de quantidade e 1 com item que saiu da planilha"


def test_so_linhas_livres_ou_de_cotacao_nao_desatualizam(monkeypatch):
    _servico(monkeypatch, (200, [_linha(origem="livre"), _linha(id="l2", origem="comparativo")]), (500, None))
    c = main._coerencia_do_financeiro(JOB)
    assert c["existe"] is True and c["desatualizado"] is False


def test_sem_lancamento_nao_existe_e_leitura_falhando_e_indisponivel(monkeypatch):
    _servico(monkeypatch, (200, []), (200, [ITEM]))
    assert main._coerencia_do_financeiro(JOB) == {"existe": False, "desatualizado": False}
    _servico(monkeypatch, (500, None), (200, [ITEM]))
    c = main._coerencia_do_financeiro(JOB)
    assert c["indisponivel"] is True and c["desatualizado"] is False, "banco fora não vira 'tudo em dia'"
    _servico(monkeypatch, (200, [_linha()]), (500, None))
    c2 = main._coerencia_do_financeiro(JOB)
    assert c2["existe"] is True and c2["indisponivel"] is True and c2["desatualizado"] is False


def test_o_painel_do_projeto_carrega_o_financeiro():
    src = sem_comentarios(fonte("main.py"))
    i = src.find("def _coerencia_do_projeto(")
    j = src.find("\n@app.", i)
    corpo = src[i:j]
    assert "financeiro = _coerencia_do_financeiro(job_id)" in corpo
    assert '("financeiro", financeiro)' in corpo and '"financeiro": financeiro' in corpo
    k = src.find('@app.get("/api/projeto/{job_id}/coerencia")')
    assert '"financeiro": _vazio' in src[k:k + 1500], "o fallback da rota também carrega a chave"
    js = fonte("coerencia.js")
    assert "nome: 'financeiro da obra'" in js and "financeiro.html?job_id=" in js
    assert "chave === 'financeiro'" in js and "Abrir o financeiro" in js
