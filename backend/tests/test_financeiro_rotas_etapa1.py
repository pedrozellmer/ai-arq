# -*- coding: utf-8 -*-
"""Financeiro da obra, etapa 1 — as rotas (CRUD por projeto, como o USUÁRIO).

05/09/2026. Maquete aprovada pelo Pedro; tabela `financeiro_lancamentos` criada
no mesmo dia; aqui o segundo pedaço: GET/POST/PATCH/DELETE em /api/financeiro.
Três lentes adversariais (FastAPI/RLS, falha silenciosa, produto) passaram pelo
código antes do push — os achados delas viraram os testes da 2ª metade deste
arquivo (semântica de ERRO: banco fora não é "não existe", nem "removido").

O que estes guardas provam, cada um com o FATO na mão (não a forma):
  • regra nº5 — nenhum valor nasce no servidor: `valor` None fica None (nunca 0);
    o valor da cotação entra só como cópia do que o cliente subiu, em centavos,
    e só quando a tela NÃO mandou o campo;
  • regra nº7 — quem nasce do quantitativo/da cotação grava o RETRATO da origem
    (descrição crua, quantidade a 4 casas, unidade) no MESMO insert, e o GET diz
    'ok' / 'mudou' / 'removido' / 'ambiguo' pela régua única (quantidade OU unidade);
  • regra nº2 — toda leitura de origem e toda escrita por id filtram job_id NA
    URL (além da RLS): item de outro projeto é 404, não retrato;
  • coerência — vencimento por fase OU por data, pago exige valor, pago_em só em
    pago; a régua do valor (não negativo, teto, 2 casas) e o teto de texto são
    ditos em português ANTES do CHECK do banco;
  • 🪤 vazio ≠ falhou — lista vazia é [] com 200; (500, None) vira 502, não [] nem
    404; project_items indisponível vira 'indisponivel', nunca 'removido';
  • admin lê pelo service_role com `somente_leitura` e NÃO escreve (LGPD nº6).
🧪 Controles positivos: o fake do banco registra as chamadas; `_isolado` reprova
URL sem job_id; o PATCH sem mudança NÃO escreve; (200, []) segue sendo 404.
"""
import os
import re
import sys
import types

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _corpo import fonte, sem_comentarios  # noqa: E402

HTTPException = main.HTTPException
JOB = "job-teste-1"
UID_ITEM = "11111111-1111-4111-8111-111111111111"
UID_COT = "22222222-2222-4222-8222-222222222222"
UID_LANC = "33333333-3333-4333-8333-333333333333"
REQ = types.SimpleNamespace(headers={"Authorization": "Bearer jwt-do-cliente"})
DONO = {"id": "uid-dono", "email": "cliente@exemplo.com"}
ADMIN = {"id": "uid-admin", "email": "zarelalopes@gmail.com"}


class _Banco:
    """Fake do `_supa_rest_as_user`: grava toda chamada e responde por (método, trecho do path)."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def __call__(self, request, method, path, body=None, params=None, prefer=None, timeout=15):
        self.chamadas.append({"m": method, "path": path, "body": body, "prefer": prefer})
        for m, trecho, resp in self.respostas:
            if m == method and trecho in path:
                return resp
        return (200, [])

    def so(self, metodo):
        return [c for c in self.chamadas if c["m"] == metodo]


@pytest.fixture
def dono(monkeypatch):
    monkeypatch.setattr(main, "_require_project_owner", lambda request, job_id: "uid-dono")
    monkeypatch.setattr(main, "_get_user_from_request", lambda request, tolerante=False: dict(DONO))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)


def _banco(monkeypatch, respostas):
    b = _Banco(respostas)
    monkeypatch.setattr(main, "_supa_rest_as_user", b)
    return b


def _isolado(chamada):
    """Leitura de origem e escrita por id TÊM que filtrar job_id na URL (nº2)."""
    return f"job_id=eq.{JOB}" in chamada["path"]


def _erro(fn, *a, **k):
    with pytest.raises(HTTPException) as ex:
        fn(*a, **k)
    return ex.value


_ATUAL = {"id": UID_LANC, "job_id": JOB, "escopo": "obra", "origem": "quantitativo",
          "origem_ref_id": UID_ITEM, "origem_ref_pos": None, "origem_quantidade": 1062.0,
          "origem_unidade": "m2", "categoria": "Pisos", "descricao": "Piso porcelanato 60x60",
          "fornecedor": "", "valor": None, "forma_pagamento": "", "venc_tipo": "fase",
          "venc_fase": "Pisos", "venc_quando": "inicio", "venc_data": None,
          "status": "cotado", "pago_em": None}
_GET_ATUAL = ("GET", f"/{main._FIN_TABELA}?id=eq.", (200, [_ATUAL]))
_PATCH_OK = ("PATCH", f"/{main._FIN_TABELA}?id=eq.", (200, [{**_ATUAL}]))


# ══════════════════════════════════════════════════════════════════════════
#  a régua do valor, o teto de texto e a normalização da linha
# ══════════════════════════════════════════════════════════════════════════
def test_valor_none_fica_none_e_nunca_vira_zero():
    assert main._fin_valor(None) is None and main._fin_valor("") is None
    assert main._fin_valor(0) == 0.0, "zero DIGITADO é valor; ausência é None"
    assert main._fin_valor("1234.56") == 1234.56


@pytest.mark.parametrize("ruim", [10.555, -1, float("nan"), float("inf"), 1e13, "abc"])
def test_valor_fora_da_regua_e_400_em_portugues(ruim):
    e = _erro(main._fin_valor, ruim)
    assert e.status_code == 400 and e.detail.startswith("valor:")


def test_texto_tem_teto_em_portugues_e_o_limite_passa():
    assert len(main._fin_texto("x" * 500, "descricao")) == 500
    e = _erro(main._fin_texto, "x" * 501, "descricao")
    assert e.status_code == 400 and e.detail.startswith("descricao:") and "500" in e.detail
    e2 = _erro(main._fin_normalizar, {"categoria": "P", "descricao": "x", "fornecedor": "f" * 201})
    assert e2.detail.startswith("fornecedor:")


def test_linha_livre_normalizada_com_vencimento_por_fase_padrao():
    out = main._fin_normalizar({"categoria": " Pisos ", "descricao": "Rejunte", "valor": "150.5"})
    assert out["categoria"] == "Pisos" and out["origem"] == "livre" and out["valor"] == 150.5
    assert (out["venc_tipo"], out["venc_fase"], out["venc_quando"], out["venc_data"]) == ("fase", "Pisos", "inicio", None)
    assert out["status"] == "cotado" and out["pago_em"] is None


def test_vencimento_por_data_zera_o_lado_da_fase_e_exige_a_data():
    out = main._fin_normalizar({"categoria": "Pisos", "descricao": "x", "venc_tipo": "data",
                                "venc_data": "2027-04-30", "venc_fase": "Pisos", "venc_quando": "fim"})
    assert (out["venc_fase"], out["venc_quando"], out["venc_data"]) == (None, None, "2027-04-30")
    e = _erro(main._fin_normalizar, {"categoria": "Pisos", "descricao": "x", "venc_tipo": "data"})
    assert e.status_code == 400 and "venc_data" in e.detail


def test_pago_exige_valor_e_pago_em_so_existe_em_pago():
    e = _erro(main._fin_normalizar, {"categoria": "P", "descricao": "x", "status": "pago"})
    assert e.status_code == 400 and "pago exige valor" in e.detail
    ok = main._fin_normalizar({"categoria": "P", "descricao": "x", "status": "pago", "valor": 10, "pago_em": "2027-03-02"})
    assert ok["pago_em"] == "2027-03-02"
    rebaixado = main._fin_normalizar({"categoria": "P", "descricao": "x", "status": "contratado", "pago_em": "2027-03-02"})
    assert rebaixado["pago_em"] is None, "saiu de pago → pago_em zera (regra da maquete)"


@pytest.mark.parametrize("campo,ruim", [("origem", "cotacao"), ("status", "quitado"),
                                        ("venc_tipo", "mes"), ("venc_quando", "meio")])
def test_enumeracoes_fora_da_lista_sao_400(campo, ruim):
    base = {"categoria": "P", "descricao": "x", "venc_tipo": "fase"}
    base[campo] = ruim
    e = _erro(main._fin_normalizar, base)
    assert e.status_code == 400 and e.detail.startswith(campo + ":")


def test_a_chave_de_religacao_e_a_regua_da_casa():
    """🔁 não reimplemente a régua: `[EXISTENTE - manter]`, travessão e ponto final
    casam na fusão da casa (_norm_desc) — têm que casar aqui também."""
    assert main._fin_norm("Porta de madeira 80x210 [EXISTENTE - manter]") == main._fin_norm("Porta de madeira 80x210")
    assert main._fin_norm("Alvenaria de vedação — 1/2 vez") == main._fin_norm("Alvenaria de vedacao - 1/2 vez")
    assert main._fin_norm("Piso porcelanato 60x60.") == main._fin_norm("piso PORCELANATO 60x60")


# ══════════════════════════════════════════════════════════════════════════
#  criar: retrato da origem no mesmo insert, isolamento na URL
# ══════════════════════════════════════════════════════════════════════════
def test_criar_do_quantitativo_grava_o_retrato_e_ignora_a_descricao_digitada(monkeypatch, dono):
    b = _banco(monkeypatch, [
        ("GET", "/project_items?", (200, [{"id": UID_ITEM, "description": "Piso porcelanato 60x60",
                                             "quantity": 1062.0, "unit": "m2"}])),
        ("POST", f"/{main._FIN_TABELA}", (201, [{"id": UID_LANC}])),
    ])
    p = main.FinanceiroLancamentoIn(categoria="Pisos", origem="quantitativo", origem_ref_id=UID_ITEM,
                                    descricao="lixo digitado", fornecedor="Casa do Piso")
    r = main.financeiro_criar(JOB, p, REQ)
    assert r["status"] == "ok" and r["lancamento"]["id"] == UID_LANC
    leitura = b.so("GET")[0]
    assert f"id=eq.{UID_ITEM}" in leitura["path"] and _isolado(leitura), "a origem tem que ser DESTE job"
    corpo = b.so("POST")[0]["body"]
    assert corpo["descricao"] == "Piso porcelanato 60x60", "a descrição vem CRUA da origem, não da tela"
    assert corpo["origem_ref_id"] == UID_ITEM and corpo["origem_ref_pos"] is None
    assert corpo["origem_quantidade"] == 1062.0 and corpo["origem_unidade"] == "m2"
    assert corpo["job_id"] == JOB and corpo["escopo"] == "obra"
    assert corpo["valor"] is None, "nº5: valor não informado fica None"
    assert corpo["fornecedor"] == "Casa do Piso"
    assert (corpo["venc_tipo"], corpo["venc_fase"], corpo["venc_quando"]) == ("fase", "Pisos", "inicio")
    assert b.so("POST")[0]["prefer"] == "return=representation"


def test_criar_do_quantitativo_com_item_de_OUTRO_projeto_e_404(monkeypatch, dono):
    _banco(monkeypatch, [("GET", "/project_items?", (200, []))])
    p = main.FinanceiroLancamentoIn(categoria="Pisos", origem="quantitativo", origem_ref_id=UID_ITEM)
    e = _erro(main.financeiro_criar, JOB, p, REQ)
    assert e.status_code == 404


def test_criar_fora_da_linha_livre_sem_ref_e_400(monkeypatch, dono):
    _banco(monkeypatch, [])
    p = main.FinanceiroLancamentoIn(categoria="Pisos", origem="quantitativo")
    e = _erro(main.financeiro_criar, JOB, p, REQ)
    assert e.status_code == 400 and "origem_ref_id" in e.detail


def test_origem_invalida_e_400_ANTES_de_bater_no_banco(monkeypatch, dono):
    b = _banco(monkeypatch, [])
    p = main.FinanceiroLancamentoIn(categoria="P", origem="comp", origem_ref_id=UID_COT, origem_ref_pos=0)
    e = _erro(main.financeiro_criar, JOB, p, REQ)
    assert e.status_code == 400 and e.detail.startswith("origem:")
    assert not b.chamadas, "origem inválida não pode gerar leitura nenhuma"


def test_criar_do_comparativo_copia_fornecedor_e_valor_da_cotacao_SO_quando_a_tela_nao_mandou(monkeypatch, dono):
    cot = {"id": UID_COT, "supplier_name": "Gesso & Cia",
           "items": [{"desc": "Forro de gesso acartonado", "un": "m2", "qtd": 812, "total": 56800}]}
    b = _banco(monkeypatch, [("GET", "/project_supplier_quotes?", (200, [cot])),
                             ("POST", f"/{main._FIN_TABELA}", (201, [{"id": UID_LANC}]))])
    p = main.FinanceiroLancamentoIn(categoria="Forros", origem="comparativo", origem_ref_id=UID_COT, origem_ref_pos=0)
    main.financeiro_criar(JOB, p, REQ)
    corpo = b.so("POST")[0]["body"]
    assert corpo["descricao"] == "Forro de gesso acartonado" and corpo["origem_ref_pos"] == 0
    assert corpo["fornecedor"] == "Gesso & Cia" and corpo["valor"] == 56800.0
    assert corpo["origem_quantidade"] == 812.0 and corpo["origem_unidade"] == "m2"
    assert _isolado(b.so("GET")[0])
    # o cliente digitou fornecedor e valor: os dele vencem a cotação
    b2 = _banco(monkeypatch, [("GET", "/project_supplier_quotes?", (200, [cot])),
                              ("POST", f"/{main._FIN_TABELA}", (201, [{"id": UID_LANC}]))])
    p2 = main.FinanceiroLancamentoIn(categoria="Forros", origem="comparativo", origem_ref_id=UID_COT,
                                     origem_ref_pos=0, fornecedor="Outro Gesso", valor=50000)
    main.financeiro_criar(JOB, p2, REQ)
    c2 = b2.so("POST")[0]["body"]
    assert c2["fornecedor"] == "Outro Gesso" and c2["valor"] == 50000.0
    # o cliente APAGOU o valor pré-preenchido (mandou null de propósito): o None dele vale
    b3 = _banco(monkeypatch, [("GET", "/project_supplier_quotes?", (200, [cot])),
                              ("POST", f"/{main._FIN_TABELA}", (201, [{"id": UID_LANC}]))])
    p3 = main.FinanceiroLancamentoIn(categoria="Forros", origem="comparativo", origem_ref_id=UID_COT,
                                     origem_ref_pos=0, valor=None, fornecedor="")
    main.financeiro_criar(JOB, p3, REQ)
    c3 = b3.so("POST")[0]["body"]
    assert c3["valor"] is None and c3["fornecedor"] == "", "o que a tela mandou explícito não é desfeito"


def test_total_da_cotacao_entra_em_centavos_e_total_zero_fica_sem_valor(monkeypatch, dono):
    cot = {"id": UID_COT, "supplier_name": "X",
           "items": [{"desc": "a", "un": "m2", "qtd": 812, "total": 56795.8272},
                     {"desc": "b", "un": "un", "qtd": 3, "total": 0}]}
    b = _banco(monkeypatch, [("GET", "/project_supplier_quotes?", (200, [cot])),
                             ("POST", f"/{main._FIN_TABELA}", (201, [{"id": UID_LANC}]))])
    main.financeiro_criar(JOB, main.FinanceiroLancamentoIn(categoria="F", origem="comparativo",
                                                            origem_ref_id=UID_COT, origem_ref_pos=0), REQ)
    assert b.so("POST")[0]["body"]["valor"] == 56795.83, "cópia do total em centavos — não é 400 nem preço nosso"
    b2 = _banco(monkeypatch, [("GET", "/project_supplier_quotes?", (200, [cot])),
                              ("POST", f"/{main._FIN_TABELA}", (201, [{"id": UID_LANC}]))])
    main.financeiro_criar(JOB, main.FinanceiroLancamentoIn(categoria="F", origem="comparativo",
                                                            origem_ref_id=UID_COT, origem_ref_pos=1), REQ)
    assert b2.so("POST")[0]["body"]["valor"] is None, "total 0 é linha sem preço, não R$ 0,00"


def test_criar_do_comparativo_com_linha_que_nao_existe_e_404(monkeypatch, dono):
    cot = {"id": UID_COT, "supplier_name": "X", "items": [{"desc": "a", "un": "un", "qtd": 1}]}
    _banco(monkeypatch, [("GET", "/project_supplier_quotes?", (200, [cot]))])
    p = main.FinanceiroLancamentoIn(categoria="F", origem="comparativo", origem_ref_id=UID_COT, origem_ref_pos=3)
    e = _erro(main.financeiro_criar, JOB, p, REQ)
    assert e.status_code == 404 and "linha 3" in e.detail


def test_criar_livre_sem_descricao_e_400_e_nao_bate_no_banco(monkeypatch, dono):
    b = _banco(monkeypatch, [])
    e = _erro(main.financeiro_criar, JOB, main.FinanceiroLancamentoIn(categoria="P"), REQ)
    assert e.status_code == 400 and "descricao" in e.detail
    assert not b.so("POST")


def test_criar_com_escopo_honorarios_e_400_nesta_etapa(monkeypatch, dono):
    b = _banco(monkeypatch, [])
    e = _erro(main.financeiro_criar, JOB, main.FinanceiroLancamentoIn(categoria="P", descricao="x", escopo="honorarios"), REQ)
    assert e.status_code == 400 and "escopo" in e.detail and not b.chamadas


def test_criar_com_pago_em_sem_estar_pago_ou_data_junto_com_fase_e_400(monkeypatch, dono):
    _banco(monkeypatch, [])
    e = _erro(main.financeiro_criar, JOB, main.FinanceiroLancamentoIn(categoria="P", descricao="x", pago_em="2027-01-01"), REQ)
    assert e.status_code == 400 and "pago_em" in e.detail
    e2 = _erro(main.financeiro_criar, JOB, main.FinanceiroLancamentoIn(categoria="P", descricao="x", venc_data="2027-01-01"), REQ)
    assert e2.status_code == 400 and "fase OU data" in e2.detail


def test_banco_recusando_a_linha_vira_400_com_orientacao_nao_stacktrace(monkeypatch, dono):
    _banco(monkeypatch, [("POST", f"/{main._FIN_TABELA}", (400, None))])
    p = main.FinanceiroLancamentoIn(categoria="P", descricao="x")
    e = _erro(main.financeiro_criar, JOB, p, REQ)
    assert e.status_code == 400 and "recusou" in e.detail and "violates" not in e.detail


def test_leitura_da_origem_com_banco_fora_e_502_nao_404(monkeypatch, dono):
    for resp in ((500, None), (0, None)):
        _banco(monkeypatch, [("GET", "/project_items?", resp)])
        p = main.FinanceiroLancamentoIn(categoria="P", origem="quantitativo", origem_ref_id=UID_ITEM)
        e = _erro(main.financeiro_criar, JOB, p, REQ)
        assert e.status_code == 502, f"{resp} virou {e.status_code}: banco fora não é 'não existe'"
        assert "tente de novo" in e.detail


# ══════════════════════════════════════════════════════════════════════════
#  a semântica do erro do banco: por código, não por faixa
# ══════════════════════════════════════════════════════════════════════════
def test_403_do_banco_e_403_sem_falar_de_valor(monkeypatch, dono):
    _banco(monkeypatch, [("POST", f"/{main._FIN_TABELA}", (403, None))])
    e = _erro(main.financeiro_criar, JOB, main.FinanceiroLancamentoIn(categoria="P", descricao="x"), REQ)
    assert e.status_code == 403 and "valor" not in e.detail


def test_401_do_banco_vira_401_pra_o_authFetch_da_tela_reagir(monkeypatch, dono):
    _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?job_id=eq.", (401, None))])
    e = _erro(main.financeiro_listar, JOB, REQ)
    assert e.status_code == 401 and "sessão" in e.detail


def test_404_do_banco_numa_leitura_e_502_nao_orientacao_sobre_valor(monkeypatch, dono):
    _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?job_id=eq.", (404, None))])
    e = _erro(main.financeiro_listar, JOB, REQ)
    assert e.status_code == 502 and "valor" not in e.detail


# ══════════════════════════════════════════════════════════════════════════
#  editar: mescla com a linha atual, filtra por id E job_id, não escreve à toa
# ══════════════════════════════════════════════════════════════════════════
def test_editar_valor_manda_so_a_mudanca_e_o_updated_at(monkeypatch, dono):
    b = _banco(monkeypatch, [_GET_ATUAL, ("PATCH", f"/{main._FIN_TABELA}?id=eq.", (200, [{**_ATUAL, "valor": 100.0}]))])
    r = main.financeiro_editar(JOB, UID_LANC, main.FinanceiroLancamentoPatch(valor=100), REQ)
    assert r["status"] == "ok" and r["lancamento"]["valor"] == 100.0
    assert _isolado(b.so("GET")[0]) and _isolado(b.so("PATCH")[0])
    assert b.so("PATCH")[0]["body"] == {"valor": 100.0, "updated_at": "now()"}


def test_editar_descricao_de_linha_do_quantitativo_e_400(monkeypatch, dono):
    _banco(monkeypatch, [_GET_ATUAL])
    e = _erro(main.financeiro_editar, JOB, UID_LANC, main.FinanceiroLancamentoPatch(descricao="x"), REQ)
    assert e.status_code == 400 and "edite lá" in e.detail


def test_editar_para_pago_sem_valor_e_400_e_com_valor_passa_sem_carimbar_data(monkeypatch, dono):
    _banco(monkeypatch, [_GET_ATUAL])
    e = _erro(main.financeiro_editar, JOB, UID_LANC, main.FinanceiroLancamentoPatch(status="pago"), REQ)
    assert e.status_code == 400 and "pago exige valor" in e.detail
    b = _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?id=eq.", (200, [{**_ATUAL, "valor": 100.0}])),
                             ("PATCH", f"/{main._FIN_TABELA}?id=eq.", (200, [{**_ATUAL, "valor": 100.0, "status": "pago"}]))])
    main.financeiro_editar(JOB, UID_LANC, main.FinanceiroLancamentoPatch(status="pago"), REQ)
    assert b.so("PATCH")[0]["body"] == {"status": "pago", "updated_at": "now()"}, "o servidor NÃO carimba pago_em"


def test_apagar_o_valor_de_linha_paga_exige_o_status_junto(monkeypatch, dono):
    paga = {**_ATUAL, "valor": 118000.0, "status": "pago", "pago_em": "2026-09-10"}
    _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?id=eq.", (200, [paga]))])
    e = _erro(main.financeiro_editar, JOB, UID_LANC, main.FinanceiroLancamentoPatch(valor=None), REQ)
    assert e.status_code == 400 and "mande também o novo status" in e.detail
    b = _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?id=eq.", (200, [paga])),
                             ("PATCH", f"/{main._FIN_TABELA}?id=eq.", (200, [{**paga, "valor": None, "status": "contratado", "pago_em": None}]))])
    main.financeiro_editar(JOB, UID_LANC, main.FinanceiroLancamentoPatch(valor=None, status="contratado"), REQ)
    assert b.so("PATCH")[0]["body"] == {"valor": None, "status": "contratado", "pago_em": None, "updated_at": "now()"}


def test_pago_em_ou_venc_data_mandados_onde_nao_se_aplicam_sao_400_nao_silencio(monkeypatch, dono):
    _banco(monkeypatch, [_GET_ATUAL])
    e = _erro(main.financeiro_editar, JOB, UID_LANC, main.FinanceiroLancamentoPatch(pago_em="2026-09-01"), REQ)
    assert e.status_code == 400 and "pago_em" in e.detail
    e2 = _erro(main.financeiro_editar, JOB, UID_LANC, main.FinanceiroLancamentoPatch(venc_data="2027-01-01"), REQ)
    assert e2.status_code == 400 and "fase OU data" in e2.detail


def test_editar_para_data_fixa_zera_o_lado_da_fase(monkeypatch, dono):
    b = _banco(monkeypatch, [_GET_ATUAL, _PATCH_OK])
    main.financeiro_editar(JOB, UID_LANC,
                           main.FinanceiroLancamentoPatch(venc_tipo="data", venc_data="2027-04-30"), REQ)
    corpo = b.so("PATCH")[0]["body"]
    assert corpo["venc_tipo"] == "data" and corpo["venc_data"] == "2027-04-30"
    assert corpo["venc_fase"] is None and corpo["venc_quando"] is None


def test_trocar_categoria_arrasta_a_fase_padrao_mas_respeita_escolha_explicita(monkeypatch, dono):
    b = _banco(monkeypatch, [_GET_ATUAL, _PATCH_OK])   # venc_fase == categoria: era só o padrão
    main.financeiro_editar(JOB, UID_LANC, main.FinanceiroLancamentoPatch(categoria="Revestimentos"), REQ)
    assert b.so("PATCH")[0]["body"] == {"categoria": "Revestimentos", "venc_fase": "Revestimentos", "updated_at": "now()"}
    escolhida = {**_ATUAL, "categoria": "Fechamentos / alvenaria", "venc_fase": "Esquadrias"}
    b2 = _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?id=eq.", (200, [escolhida])), _PATCH_OK])
    main.financeiro_editar(JOB, UID_LANC, main.FinanceiroLancamentoPatch(categoria="Esquadrias e vidros"), REQ)
    assert b2.so("PATCH")[0]["body"] == {"categoria": "Esquadrias e vidros", "updated_at": "now()"}, "fase escolhida à mão fica"


def test_editar_sem_mudanca_NAO_escreve(monkeypatch, dono):
    b = _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?id=eq.", (200, [{**_ATUAL, "valor": 100.0}]))])
    r = main.financeiro_editar(JOB, UID_LANC, main.FinanceiroLancamentoPatch(valor=100), REQ)
    assert r.get("sem_mudanca") is True and not b.so("PATCH")


def test_editar_sem_campo_nenhum_e_400_ANTES_de_ler_o_banco_e_id_torto_e_400(monkeypatch, dono):
    b = _banco(monkeypatch, [_GET_ATUAL])
    e = _erro(main.financeiro_editar, JOB, UID_LANC, main.FinanceiroLancamentoPatch(), REQ)
    assert e.status_code == 400 and "nada" in e.detail and not b.chamadas
    for torto in ("1 OR 1=1", UID_LANC + "\n"):
        e2 = _erro(main.financeiro_editar, JOB, torto, main.FinanceiroLancamentoPatch(valor=1), REQ)
        assert e2.status_code == 400, repr(torto)
    assert _erro(main.financeiro_remover, JOB, UID_LANC + "\n", REQ).status_code == 400


def test_editar_lancamento_de_outro_projeto_e_404_e_banco_fora_e_502(monkeypatch, dono):
    _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?id=eq.", (200, []))])
    assert _erro(main.financeiro_editar, JOB, UID_LANC, main.FinanceiroLancamentoPatch(valor=1), REQ).status_code == 404
    _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?id=eq.", (0, None))])
    assert _erro(main.financeiro_editar, JOB, UID_LANC, main.FinanceiroLancamentoPatch(valor=1), REQ).status_code == 502


def test_patch_cuja_linha_sumiu_no_meio_e_404_nao_tente_de_novo(monkeypatch, dono):
    _banco(monkeypatch, [_GET_ATUAL, ("PATCH", f"/{main._FIN_TABELA}?id=eq.", (200, []))])
    e = _erro(main.financeiro_editar, JOB, UID_LANC, main.FinanceiroLancamentoPatch(valor=1), REQ)
    assert e.status_code == 404 and "outra aba" in e.detail
    _banco(monkeypatch, [_GET_ATUAL, ("PATCH", f"/{main._FIN_TABELA}?id=eq.", (500, None))])
    assert _erro(main.financeiro_editar, JOB, UID_LANC, main.FinanceiroLancamentoPatch(valor=1), REQ).status_code == 502


# ══════════════════════════════════════════════════════════════════════════
#  remover e listar
# ══════════════════════════════════════════════════════════════════════════
def test_remover_filtra_id_e_job_e_devolve_o_removido(monkeypatch, dono):
    b = _banco(monkeypatch, [("DELETE", f"/{main._FIN_TABELA}?id=eq.", (200, [{"id": UID_LANC}]))])
    r = main.financeiro_remover(JOB, UID_LANC, REQ)
    assert r["removido"]["id"] == UID_LANC and _isolado(b.so("DELETE")[0])
    _banco(monkeypatch, [("DELETE", f"/{main._FIN_TABELA}?id=eq.", (200, []))])
    assert _erro(main.financeiro_remover, JOB, UID_LANC, REQ).status_code == 404


def _itens_e_lancamentos():
    l_ok = {**_ATUAL, "id": "a"}
    l_mudou = {**_ATUAL, "id": "b", "origem_ref_id": "44444444-4444-4444-8444-444444444444",
               "descricao": "Forro de gesso", "origem_quantidade": 812.0}
    l_removido = {**_ATUAL, "id": "c", "origem_ref_id": "55555555-5555-4555-8555-555555555555",
                  "descricao": "Item que sumiu"}
    l_livre = {**_ATUAL, "id": "d", "origem": "livre", "origem_ref_id": None}
    itens = [{"id": UID_ITEM, "description": "Piso porcelanato 60x60", "quantity": 1062.0, "unit": "m2"},
             {"id": "novo-id", "description": "FORRO DE GESSO", "quantity": 790.0, "unit": "m2"}]
    return [l_ok, l_mudou, l_removido, l_livre], itens


def test_listar_diz_o_estado_da_origem_de_cada_linha(monkeypatch, dono):
    lancs, itens = _itens_e_lancamentos()
    _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?job_id=eq.", (200, lancs)),
                         ("GET", "/project_items?", (200, itens))])
    r = main.financeiro_listar(JOB, REQ)
    est = {l["id"]: l for l in r["lancamentos"]}
    assert est["a"]["origem_estado"] == "ok"
    assert est["b"]["origem_estado"] == "mudou" and est["b"]["origem_atual"] == {"quantidade": 790.0, "unidade": "m2"}
    assert est["b"]["origem_ref_id_atual"] == "novo-id", "religou por descrição normalizada (id novo do /add-file)"
    assert est["c"]["origem_estado"] == "removido"
    assert est["d"]["origem_estado"] == "ok"
    assert r["itens_lidos"] is True and r["somente_leitura"] is False


def test_listar_com_project_items_fora_NAO_carimba_removido(monkeypatch, dono):
    lancs, _ = _itens_e_lancamentos()
    for resp in ((500, None), (0, None)):
        _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?job_id=eq.", (200, lancs)),
                             ("GET", "/project_items?", resp)])
        r = main.financeiro_listar(JOB, REQ)
        estados = [l["origem_estado"] for l in r["lancamentos"]]
        assert "removido" not in estados and "mudou" not in estados, f"{resp}: {estados}"
        assert estados == ["indisponivel", "indisponivel", "indisponivel", "ok"]
        assert r["itens_lidos"] is False


def test_listar_com_1000_itens_trata_como_corte_e_nao_afirma_removido(monkeypatch, dono):
    lancs, _ = _itens_e_lancamentos()
    mil = [{"id": f"i{n}", "description": f"item {n}", "quantity": 1, "unit": "un"} for n in range(1000)]
    _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?job_id=eq.", (200, lancs)),
                         ("GET", "/project_items?", (200, mil))])
    r = main.financeiro_listar(JOB, REQ)
    assert r["itens_truncados"] is True and all(l["origem_estado"] != "removido" for l in r["lancamentos"])


def test_listar_com_banco_falhando_e_502_e_NAO_lista_vazia(monkeypatch, dono):
    _banco(monkeypatch, [("GET", f"/{main._FIN_TABELA}?job_id=eq.", (500, None))])
    e = _erro(main.financeiro_listar, JOB, REQ)
    assert e.status_code == 502


def test_estado_da_origem_muda_por_unidade_tambem():
    it = {"id": UID_ITEM, "description": "Piso", "quantity": 1062.0, "unit": "m"}
    r = main._fin_estado_da_origem(_ATUAL, {UID_ITEM: it}, {})
    assert r["origem_estado"] == "mudou"


def test_religacao_com_dois_homonimos_so_escolhe_pelo_retrato_senao_ambiguo():
    lanc = {**_ATUAL, "origem_ref_id": "id-velho", "descricao": "Tomada 2P+T 10A",
            "origem_quantidade": 8.0, "origem_unidade": "un"}
    a = {"id": "n1", "description": "Tomada 2P+T 10A", "quantity": 12.0, "unit": "un"}
    b = {"id": "n2", "description": "Tomada 2P+T 10A", "quantity": 8.0, "unit": "un"}
    chave = main._fin_norm("Tomada 2P+T 10A")
    r = main._fin_estado_da_origem(lanc, {}, {chave: [a, b]})
    assert r["origem_estado"] == "ok" and r["origem_ref_id_atual"] == "n2", "religa no que casa com o retrato"
    r2 = main._fin_estado_da_origem({**lanc, "origem_quantidade": 5.0}, {}, {chave: [a, b]})
    assert r2 == {"origem_estado": "ambiguo", "origem_candidatos": 2}, "sem casamento único, não chuta"


# ══════════════════════════════════════════════════════════════════════════
#  admin: lê pelo service_role com somente_leitura; não escreve (LGPD nº6)
# ══════════════════════════════════════════════════════════════════════════
def test_admin_le_pelo_service_role_e_nao_escreve(monkeypatch):
    monkeypatch.setattr(main, "_require_project_owner", lambda request, job_id: "uid-dono")
    monkeypatch.setattr(main, "_get_user_from_request", lambda request, tolerante=False: dict(ADMIN))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    como_user = _banco(monkeypatch, [])                       # a RLS devolveria [] pro admin
    servico = []

    def _svc(method, path, body=None, params=None, prefer=None, timeout=15):
        servico.append((method, path))
        if "/project_items?" in path:
            return (200, [])
        return (200, [{**_ATUAL, "id": "a"}])
    monkeypatch.setattr(main, "_supa_rest_service", _svc)
    r = main.financeiro_listar(JOB, REQ)
    assert r["somente_leitura"] is True and [l["id"] for l in r["lancamentos"]] == ["a"]
    assert servico and all(f"job_id=eq.{JOB}" in p for _m, p in servico), "mesmo pelo service, a URL isola o job"
    assert not como_user.chamadas, "admin não lê pelo próprio JWT (a RLS mentiria [])"
    for fn, args in ((main.financeiro_criar, (JOB, main.FinanceiroLancamentoIn(categoria="P", descricao="x"), REQ)),
                     (main.financeiro_editar, (JOB, UID_LANC, main.FinanceiroLancamentoPatch(valor=1), REQ)),
                     (main.financeiro_remover, (JOB, UID_LANC, REQ))):
        e = _erro(fn, *args)
        assert e.status_code == 403 and "admin" in e.detail
    assert not como_user.chamadas


# ══════════════════════════════════════════════════════════════════════════
#  controles positivos e guarda de forma mínima (a URL isola por job)
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_helper_isolado_reprova_url_sem_job():
    assert not _isolado({"path": f"/{main._FIN_TABELA}?id=eq.{UID_LANC}"})
    assert _isolado({"path": f"/{main._FIN_TABELA}?id=eq.{UID_LANC}&job_id=eq.{JOB}"})


def test_toda_escrita_por_id_no_fonte_filtra_job_id_na_url():
    src = sem_comentarios(fonte("main.py"))
    # 🪤 o cabeçalho da seção é comentário e `sem_comentarios` o apaga — ancorar em CÓDIGO
    i = src.find('_FIN_TABELA = "financeiro_lancamentos"')
    j = src.find('@app.post("/api/items/{job_id}/review-finalize")', i)
    assert 0 < i < j, "não achei a seção do financeiro no fonte"
    regiao = src[i:j]
    assert regiao.count("?id=eq.{lanc_id}&job_id=eq.{jq}") == 3, "GET-atual, PATCH e DELETE"
    assert not re.search(r'\?id=eq\.\{lanc_id\}(?!&job_id=eq\.\{jq\})', regiao), \
        "sobrou escrita/leitura por id sem o filtro de job logo em seguida"
    # 4 do CRUD + 2 dos exports (05/09) + 3 do lote (modelo, conferir, aplicar — 06/09):
    # TODA rota da seção confere o dono antes de tocar no banco
    assert regiao.count("_require_project_owner(request, job_id)") == 9
    # o `def` também casa: 1 definição + 3 chamadas (POST, PATCH e DELETE recusam admin)
    # 1 definição + POST, PATCH, DELETE (05/09) + conferir e aplicar o lote (06/09):
    # o admin LÊ o financeiro do cliente, nunca escreve (LGPD nº6)
    assert regiao.count("_fin_so_o_dono_escreve(request, owner)") == 6, (
        "POST, PATCH, DELETE e as duas do lote recusam admin")
