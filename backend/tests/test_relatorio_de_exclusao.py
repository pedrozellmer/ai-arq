# -*- coding: utf-8 -*-
"""Relatorio de exclusao de dados (LGPD): diz onde ha dado do titular e NAO apaga.

🩸 14/11/2026 — o 1o pedido de exclusao foi atendido a mao e a lista do que
procurar (tabelas por projeto, por e-mail e por usuario, Storage, cache da IA)
ficou so na cabeca de quem fez. A rota devolve essa lista preenchida.

O que este arquivo sustenta:
  - a regua acha projeto pelo e-mail, pelo usuario e os filhotes;
  - tabela que nao deu pra ler aparece em `nao_li` (nunca some calada);
  - o que tem obrigacao de guarda aparece em `atencao`;
  - a rota so le: nenhum verbo de escrita, e-mail no corpo, admin exigido.

Tudo sintetico, sem rede.
"""
import io
import os
import re
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

_EMAIL = "titular@exemplo.test"
_USUARIO = "usuario-generico-1"


class _Banco:
    """Dublê do banco: guarda os pedidos e responde pelo que foi semeado."""

    def __init__(self, falha=()):
        self.pedidos = []
        self.falha = set(falha)

    def busca(self, tabela, params):
        self.pedidos.append((tabela, dict(params)))
        if tabela in self.falha:
            return None
        if tabela == "profiles":
            if params.get("email") == "eq." + _EMAIL:
                return [{"user_id": _USUARIO, "email": _EMAIL}]
            return []
        if tabela == "projects":
            if params.get("user_email") == "eq." + _EMAIL:
                return [{"job_id": "aaaa1111", "status": "done", "pago_cents": 9900}]
            if params.get("user_id") == "eq." + _USUARIO:
                return [{"job_id": "aaaa1111", "status": "done", "pago_cents": 9900},
                        {"job_id": "bbbb2222", "status": "done"}]
            if "parent_job_id" in params:
                assert params["parent_job_id"] == "in.(aaaa1111,bbbb2222)"
                return [{"job_id": "evcc3333", "parent_job_id": "aaaa1111", "is_eval": True}]
            return []
        if tabela == "project_items" and "job_id" in params:
            assert params["job_id"] == "in.(aaaa1111,bbbb2222,evcc3333)"
            return [{"job_id": "aaaa1111"}] * 57
        if tabela == "error_log":
            return [{"job_id": "aaaa1111"}] * main._EXCLUSAO_TETO
        if tabela == "financeiro_lancamentos":
            return [{"job_id": "aaaa1111"}]
        if tabela == "usage_events" and params.get("user_email") == "eq." + _EMAIL:
            return [{"user_email": _EMAIL}] * 3
        if tabela == "user_credits" and params.get("user_id") == "eq." + _USUARIO:
            return [{"user_id": _USUARIO}]
        if tabela == "llm_cache":
            return [{"tag": "dxf:planta generica.dwg"}] * 2 if "planta generica.dwg" in params["tag"] else []
        return []


def _storage(bucket, prefixo):
    if bucket == main.PRANCHAS_BUCKET and prefixo == "aaaa1111/":
        return ["aaaa1111/planta generica.dwg", "aaaa1111/previa.png"]
    if bucket == main.PLANILHAS_BUCKET and prefixo == "aaaa1111":
        return ["aaaa1111.xlsx"]
    return []


def _roda(falha=()):
    banco = _Banco(falha)
    return main._relatorio_de_exclusao("  Titular@Exemplo.TEST ", banco.busca, _storage), banco


def test_acha_usuario_projetos_e_filhotes():
    rel, _ = _roda()
    assert rel["email"] == _EMAIL and rel["usuarios"] == [_USUARIO]
    assert [p["job_id"] for p in rel["projetos"]] == ["aaaa1111", "bbbb2222", "evcc3333"]
    filhote = rel["projetos"][2]
    assert filhote["pai"] == "aaaa1111" and filhote["avaliacao"] is True
    assert rel["apaga_algo"] is False


def test_conta_por_projeto_por_email_e_por_usuario():
    rel, _ = _roda()
    banco = {(b["tabela"], b["por"]): b["linhas"] for b in rel["banco"]}
    assert banco[("project_items", "job_id")] == 57
    assert banco[("usage_events", "user_email")] == 3
    assert banco[("user_credits", "user_id")] == 1
    assert banco[("profiles", "email")] == 1
    assert banco[("error_log", "job_id")] == "%d+" % main._EXCLUSAO_TETO, "bateu no teto: não é o total"
    assert ("item_reviews", "job_id") not in banco, "tabela vazia não entra na lista"


def test_storage_e_cache_da_ia():
    rel, _ = _roda()
    assert {"bucket": main.PRANCHAS_BUCKET, "prefixo": "aaaa1111/", "arquivos": 2} in rel["storage"]
    assert {"bucket": main.PLANILHAS_BUCKET, "prefixo": "aaaa1111", "arquivos": 1} in rel["storage"]
    assert rel["cache_da_ia"] == [{"arquivo": "planta generica.dwg", "linhas": 2}]


def test_o_que_tem_obrigacao_de_guarda_vira_atencao():
    rel, _ = _roda()
    tabelas = [a["tabela"] for a in rel["atencao"]]
    for t in ("financeiro_lancamentos", "user_credits", "projects", "llm_cache", "auth.users"):
        assert t in tabelas, t
    assert tabelas.count("financeiro_lancamentos") == 1


def test_tabela_que_nao_deu_pra_ler_aparece_e_nao_some_calada():
    rel, _ = _roda(falha=("item_reviews", "chat_leads"))
    assert "item_reviews (por job_id)" in rel["nao_li"]
    assert "chat_leads (por email)" in rel["nao_li"]
    limpo, _ = _roda()
    assert limpo["nao_li"] == [], "CONTROLE: sem falha a lista fica vazia"


def test_sem_projeto_nao_procura_por_job_nem_no_cache():
    banco = _Banco()
    rel = main._relatorio_de_exclusao("outro@exemplo.test", banco.busca, _storage)
    assert rel["projetos"] == [] and rel["storage"] == [] and rel["cache_da_ia"] == []
    assert not any("job_id" in p for _t, p in banco.pedidos if _t != "projects")
    assert not any(t == "llm_cache" for t, _p in banco.pedidos)


@pytest.mark.parametrize("ruim", ["", None, "sem-arroba", "   "])
def test_email_invalido_recusa(ruim):
    with pytest.raises(ValueError):
        main._relatorio_de_exclusao(ruim, _Banco().busca, _storage)


def test_toda_tabela_listada_e_consultada():
    _, banco = _roda()
    vistas = {t for t, _p in banco.pedidos}
    faltam = (set(main._EXCLUSAO_POR_JOB) | set(main._EXCLUSAO_POR_EMAIL)
              | set(main._EXCLUSAO_POR_USUARIO)) - vistas
    assert not faltam, faltam


def test_a_rota_so_le_exige_admin_e_recebe_o_email_no_corpo():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    ini = src.index('@app.post("/api/admin/relatorio-de-exclusao")')
    rota = src[ini:src.index("\n@app.", ini + 10)]
    assert "_require_admin(request)" in rota
    assert "await request.json()" in rota and "query_params" not in rota
    regua = src[src.index("def _relatorio_de_exclusao("):ini]
    for trecho in (rota, regua):
        assert not re.search(r'"(DELETE|PATCH|PUT|POST)"', trecho), "a rota de relatório escreveu"
        assert "_supabase_storage_delete" not in trecho and "_log_error" not in trecho
    assert '_supa_rest_service("GET", tabela' in rota
