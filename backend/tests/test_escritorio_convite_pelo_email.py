# -*- coding: utf-8 -*-
"""26/09/2026 — uma convidada, no celular: o código do convite (#t=…) se perdeu na volta do login pelo Google
e a página parava em "Não achei o convite", com o convite PENDENTE pro e-mail dela no banco.

Conserto: logada e sem código, a página pergunta ao servidor os convites em aberto pro e-mail da conta
(/convite/pendentes) e aceita pelo `convite_id`. Sem o código, a prova é o E-MAIL. O que se cobra:
  • só e-mail CONFIRMADO serve (senão bastava criar conta com o e-mail de outra pessoa);
  • a lista só traz convite do e-mail EXATO da conta, em aberto e no prazo — sem código, sem e-mail alheio;
  • aceitar por convite_id de OUTRO e-mail é 404 (o mesmo de "não existe": não revela convite alheio);
  • o PATCH do aceite continua exigindo status=convidado (dois aceites não ativam duas contas).
"""
import os
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import escritorio as esc  # noqa: E402
from fastapi import HTTPException  # noqa: E402


@pytest.fixture(autouse=True)
def _devolve_as_pecas_do_modulo():
    antes = (esc._SERVICO, esc._COMO_USUARIO, esc._USUARIO, esc._ENVIAR, esc._MOLDURA, esc._REGISTRAR)
    yield
    (esc._SERVICO, esc._COMO_USUARIO, esc._USUARIO, esc._ENVIAR, esc._MOLDURA, esc._REGISTRAR) = antes


PROJ = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
CID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
REQ = types.SimpleNamespace(headers={"Authorization": "Bearer jwt"})
CONVIDADA = {"id": "uid-convidada", "email": "convidada@exemplo.com", "email_confirmado": True}
NAO_CONFIRMADA = {"id": "uid-x", "email": "convidada@exemplo.com", "email_confirmado": False}
OUTRA = {"id": "uid-outra", "email": "outra@exemplo.com", "email_confirmado": True}
FUTURO = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
PASSADO = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


class _Banco:
    def __init__(self, respostas):
        self.respostas = respostas
        self.chamadas = []

    def __call__(self, method, path, body=None, params=None, prefer=None, timeout=15, **_k):
        self.chamadas.append({"m": method, "path": path, "body": body, "params": params or {}})
        for m, tabela, filtro, resp in self.respostas:
            if m == method and tabela in path and all((params or {}).get(k) == v for k, v in filtro.items()):
                return resp
        return (200, [])

    def escritas(self):
        return [c for c in self.chamadas if c["m"] in ("POST", "PATCH", "DELETE")]


def _montar(banco, usuario):
    esc.configurar(servico=banco, como_usuario=None, usuario=lambda r: usuario,
                   enviar=None, moldura=None, registrar=None)


_LISTA = ("GET", "escritorio_membros", {"email": "eq.convidada@exemplo.com", "status": "eq.convidado"},
          (200, [{"id": CID, "projeto_id": PROJ, "convite_expira": FUTURO},
                 {"id": "vencido", "projeto_id": PROJ, "convite_expira": PASSADO}]))
_PROJETO = ("GET", "escritorio_projetos", {}, (200, [{"nome": "Projeto Exemplo"}]))
_ADMIN = ("GET", "escritorio_membros", {"papel": "eq.dono"}, (200, [{"nome": "Admin Exemplo"}]))


def _linha(email="convidada@exemplo.com", status="convidado", expira=FUTURO):
    return ("GET", "escritorio_membros", {"id": f"eq.{CID}"},
            (200, [{"id": CID, "projeto_id": PROJ, "email": email, "nome": None, "status": status, "convite_expira": expira}]))


# ── a lista ──
def test_lista_traz_so_o_convite_em_aberto_e_no_prazo_do_email_da_conta():
    banco = _Banco([_LISTA, _PROJETO, _ADMIN])
    _montar(banco, CONVIDADA)
    r = esc.convites_pendentes_da_conta(REQ)
    assert r == {"convites": [{"convite_id": CID, "projeto": "Projeto Exemplo", "convidado_por": "Admin Exemplo"}]}
    busca = banco.chamadas[0]["params"]
    assert busca["email"] == "eq.convidada@exemplo.com" and busca["status"] == "eq.convidado"
    assert "convite_hash" not in busca["select"] and "email" not in busca["select"], "nada de código nem e-mail na resposta"
    assert banco.escritas() == []


def test_email_nao_confirmado_nao_ve_convite_nenhum():
    banco = _Banco([_LISTA, _PROJETO, _ADMIN])
    _montar(banco, NAO_CONFIRMADA)
    assert esc.convites_pendentes_da_conta(REQ) == {"convites": []}
    assert banco.chamadas == [], "sem e-mail confirmado nem pergunta ao banco"


def test_conta_sem_a_marca_de_confirmacao_tambem_nao_ve():
    # quem não diz que confirmou (ex.: dublê antigo, resposta sem o campo) não passa: só True vale
    _montar(_Banco([_LISTA]), {"id": "uid", "email": "convidada@exemplo.com"})
    assert esc.convites_pendentes_da_conta(REQ) == {"convites": []}


def test_lista_sem_login_e_401():
    _montar(_Banco([_LISTA]), None)
    with pytest.raises(HTTPException) as e:
        esc.convites_pendentes_da_conta(REQ)
    assert e.value.status_code == 401


def test_banco_fora_e_502_e_nao_lista_vazia():
    _montar(_Banco([("GET", "escritorio_membros", {"status": "eq.convidado"}, (500, None))]), CONVIDADA)
    with pytest.raises(HTTPException) as e:
        esc.convites_pendentes_da_conta(REQ)
    assert e.value.status_code == 502


# ── o aceite pelo convite_id ──
def test_aceitar_pelo_id_com_o_mesmo_email_ativa():
    banco = _Banco([_linha(), ("PATCH", "escritorio_membros", {}, (200, [{"id": CID}]))])
    _montar(banco, CONVIDADA)
    r = esc.aceitar_convite(REQ, {"convite_id": CID})
    assert r["ok"] is True and r["projeto_id"] == PROJ and r["email_da_conta_diferente"] is False
    busca = banco.chamadas[0]["params"]
    assert busca["id"] == f"eq.{CID}" and busca["email"] == "eq.convidada@exemplo.com", "a busca já filtra pelo e-mail da conta"
    patch = banco.escritas()[-1]
    assert patch["params"] == {"id": f"eq.{CID}", "status": "eq.convidado"}
    assert patch["body"]["user_id"] == CONVIDADA["id"] and patch["body"]["status"] == "ativo"


def test_aceitar_pelo_id_de_convite_de_outro_email_e_404_e_nao_escreve():
    banco = _Banco([_linha(email="convidada@exemplo.com")])
    _montar(banco, OUTRA)
    with pytest.raises(HTTPException) as e:
        esc.aceitar_convite(REQ, {"convite_id": CID})
    assert e.value.status_code == 404 and banco.escritas() == []


def test_aceitar_pelo_id_sem_email_confirmado_e_404_sem_ler_o_banco():
    banco = _Banco([_linha()])
    _montar(banco, NAO_CONFIRMADA)
    with pytest.raises(HTTPException) as e:
        esc.aceitar_convite(REQ, {"convite_id": CID})
    assert e.value.status_code == 404 and banco.chamadas == []


def test_aceitar_pelo_id_invalido_e_404():
    _montar(_Banco([]), CONVIDADA)
    for ruim in ("", "abc", "'; drop table x; --", CID + "x"):
        with pytest.raises(HTTPException) as e:
            esc.aceitar_convite(REQ, {"convite_id": ruim})
        assert e.value.status_code == 404


def test_aceitar_pelo_id_vencido_e_410():
    banco = _Banco([_linha(expira=PASSADO)])
    _montar(banco, CONVIDADA)
    with pytest.raises(HTTPException) as e:
        esc.aceitar_convite(REQ, {"convite_id": CID})
    assert e.value.status_code == 410 and banco.escritas() == []


def test_o_token_continua_valendo_e_tem_precedencia():
    t = "T" * 43
    banco = _Banco([("GET", "escritorio_membros", {"convite_hash": f"eq.{esc.hash_do_token(t)}"},
                     (200, [{"id": "m1", "projeto_id": PROJ, "email": "outra@exemplo.com", "nome": "X",
                             "status": "convidado", "convite_expira": FUTURO}])),
                    ("PATCH", "escritorio_membros", {}, (200, [{"id": "m1"}]))])
    _montar(banco, CONVIDADA)
    r = esc.aceitar_convite(REQ, {"token": t, "convite_id": CID})
    assert r["ok"] is True and r["email_da_conta_diferente"] is True   # o caminho do código segue igual


def test_a_rota_nova_esta_no_app():
    import main
    assert "/api/escritorio/convite/pendentes" in {r.path for r in main.app.routes}


def test_o_login_do_servidor_diz_se_o_email_foi_confirmado():
    src = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    i = src.index("def _get_user_from_request(")
    corpo = src[i:src.index("\ndef ", i + 10)]
    assert '"email_confirmado": bool(data.get("email_confirmed_at") or data.get("confirmed_at"))' in corpo


def test_a_pagina_do_convite_procura_pelo_email_quando_nao_tem_codigo():
    h = open(os.path.join(os.path.dirname(os.path.dirname(_AQUI)), "convite.html"), encoding="utf-8").read()
    assert "if (!token) return semCodigo();" in h
    assert "api('convite/pendentes', {}, SESSAO)" in h
    assert "CONVITE_ID ? { convite_id: CONVITE_ID } : { token }" in h
    s = h[h.index("async function semCodigo() {"):h.index("async function iniciar() {")]
    assert "sb.from('profiles')" in s and "location.href = 'cadastro.html'" in s, "sem ficha não entra no projeto"

# controle positivo (26/09): aceitar e-mail não confirmado (`if not eu:` em _email_da_conta) reprovou 3;
# tirar o `"email": f"eq.{email}"` da busca por id reprovou 1 (a conferência de baixo segura o 404 — defesa
# em dobro, por isso o teste cobra o filtro na busca); a página sem `semCodigo()` reprovou 1. Restaurado: 14 verdes.
