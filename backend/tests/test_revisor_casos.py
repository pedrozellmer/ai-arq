# -*- coding: utf-8 -*-
"""O revisor sabendo do caso (parte 3, peças A e B — 23/10/2026).

Projeto com caso fechado (`consertado`/`nao_e_defeito`) sai da contagem de suspeitos; se o cliente
fizer algo DEPOIS do fechamento, volta pra fila marcado "voltou". Cada regra tem o caso que dispara e
o vizinho que não dispara ([[feedback_teste_com_controle_positivo]]). Dados sintéticos.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import revisor_noturno as rn  # noqa: E402


def _ficha(jid="j1", nota=6, ultimo="2026-10-20T12:00:00+00:00", novidade=False, criado="2026-10-10"):
    return {"job_id": jid, "nota": nota, "ultimo_sinal_do_cliente": ultimo, "novidade": novidade,
            "criado_em": criado, "motivos": [], "sinais": {}}


def _caso(jid="j1", estado="consertado", fechado_em="2026-10-21T12:00:00+00:00", **kw):
    c = {"job_id": jid, "estado": estado, "fechado_em": fechado_em, "forma": "bloco sem atributo",
         "origem": "motor:bloco-sem-identidade", "conserto_commit": "abc1234", "chave": None,
         "teste": "backend/tests/test_x.py::test_y"}
    c.update(kw)
    return c


def test_sem_caso_a_ficha_fica_como_estava():
    f = rn.aplicar_casos([_ficha()], [])[0]
    assert f["caso"] is None and rn.e_suspeito(f) and not rn.tratado(f)


def test_consertado_sai_da_contagem_de_suspeitos():
    f = rn.aplicar_casos([_ficha()], [_caso()])[0]
    assert f["caso"]["tratado"] is True and f["caso"]["voltou"] is False
    assert not rn.e_suspeito(f)


def test_nao_e_defeito_tambem_sai():
    f = rn.aplicar_casos([_ficha()], [_caso(estado="nao_e_defeito")])[0]
    assert rn.tratado(f) and not rn.e_suspeito(f)


def test_a_nota_nao_muda_com_o_caso():
    f = rn.aplicar_casos([_ficha(nota=9)], [_caso()])[0]
    assert f["nota"] == 9


def test_cliente_que_age_depois_do_conserto_volta_pra_fila():
    f = rn.aplicar_casos([_ficha(ultimo="2026-10-22T09:00:00+00:00")], [_caso()])[0]
    assert f["caso"]["voltou"] is True and f["caso"]["tratado"] is False
    assert rn.e_suspeito(f)


def test_sinal_antes_do_conserto_nao_e_voltar():
    f = rn.aplicar_casos([_ficha(ultimo="2026-10-21T11:59:00+00:00")], [_caso()])[0]
    assert f["caso"]["voltou"] is False and rn.tratado(f)


def test_projeto_sem_nenhum_sinal_do_cliente_fica_tratado():
    f = rn.aplicar_casos([_ficha(ultimo=None)], [_caso()])[0]
    assert rn.tratado(f) and not rn.voltou(f)


def test_caso_aberto_so_anota_e_continua_contando():
    for estado in ("olhando", "confirmado"):
        f = rn.aplicar_casos([_ficha()], [_caso(estado=estado, fechado_em=None)])[0]
        assert f["caso"]["estado"] == estado and not rn.tratado(f) and rn.e_suspeito(f)


def test_estado_digitado_errado_nao_esconde_o_projeto():
    f = rn.aplicar_casos([_ficha()], [_caso(estado="consertad0")])[0]
    assert not rn.tratado(f) and rn.e_suspeito(f)


def test_fechado_sem_data_nao_some_calado():
    f = rn.aplicar_casos([_ficha()], [_caso(fechado_em=None)])[0]
    assert not rn.tratado(f) and rn.e_suspeito(f)


def test_nota_baixa_nunca_e_suspeito_com_ou_sem_caso():
    assert not rn.e_suspeito(rn.aplicar_casos([_ficha(nota=2)], [])[0])
    assert not rn.e_suspeito(rn.aplicar_casos([_ficha(nota=2, ultimo="2026-10-25T00:00:00+00:00")],
                                               [_caso()])[0])


def test_a_ficha_leva_o_que_o_painel_mostra():
    c = rn.aplicar_casos([_ficha()], [_caso()])[0]["caso"]
    assert c == dict(c, forma="bloco sem atributo", origem="motor:bloco-sem-identidade",
                     conserto_commit="abc1234", teste="backend/tests/test_x.py::test_y")
    assert c["fechado_em"].startswith("2026-10-21")


def test_carimbo_sem_fuso_no_fechamento_nao_derruba():
    f = rn.aplicar_casos([_ficha(ultimo="2026-10-22T09:00:00+00:00")],
                         [_caso(fechado_em="2026-10-21")])[0]
    assert rn.voltou(f)


def test_a_fila_poe_o_tratado_no_fim_e_o_que_voltou_na_frente():
    fichas = [_ficha("tratado", nota=12), _ficha("comum", nota=6),
              _ficha("voltou", nota=6, ultimo="2026-10-22T09:00:00+00:00"), _ficha("baixa", nota=1)]
    casos = [_caso("tratado"), _caso("voltou")]
    ordem = [f["job_id"] for f in rn.aplicar_casos(fichas, casos)]
    assert ordem == ["voltou", "comum", "baixa", "tratado"]
