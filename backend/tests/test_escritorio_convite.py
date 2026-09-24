# -*- coding: utf-8 -*-
"""Escritório (piloto DTZ, 23/09/2026) — o convite.

O que estes guardas provam, com o FATO na mão:
  • o token NUNCA vai pro banco: o que se grava é o SHA-256; o e-mail leva o
    token no FRAGMENTO (#t=), que não sai do navegador;
  • só a admin convida — e quem decide que é admin é o BANCO (rpc
    escritorio_papel com o login da pessoa), não um campo do corpo;
  • ativar alguém só acontece no aceite, com token válido e não vencido, e o
    PATCH do aceite exige `status=eq.convidado` na URL (dois aceites do mesmo
    token não ativam duas contas);
  • 🪤 vazio ≠ falhou: banco fora (500, None) é 502 "tente de novo", nunca 404
    "convite não existe";
  • a página pública do convite não mostra o e-mail inteiro.
🧪 Controles positivos: o fake grava as chamadas; sem login é 401; conta que
não é admin reprova ANTES de qualquer escrita.
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
    """🩸 24/09: estes testes trocam as peças do módulo por dublês; sem devolver, a
    PRÉVIA do painel (test_todo_email_que_sai_tem_ficha) rodava depois com a moldura
    falsa e reprovava — só no CI, onde a ordem dos testes é outra."""
    antes = (esc._SERVICO, esc._COMO_USUARIO, esc._USUARIO, esc._ENVIAR, esc._MOLDURA, esc._REGISTRAR)
    yield
    (esc._SERVICO, esc._COMO_USUARIO, esc._USUARIO, esc._ENVIAR, esc._MOLDURA, esc._REGISTRAR) = antes

PROJ = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
REQ = types.SimpleNamespace(headers={"Authorization": "Bearer jwt"})
ADMIN = {"id": "uid-admin", "email": "admin@exemplo.com"}
EQUIPE = {"id": "uid-equipe", "email": "equipe@exemplo.com"}
FUTURO = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
PASSADO = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


class _Banco:
    """Fake do banco: responde por (método, tabela, trecho dos params) e grava tudo."""

    def __init__(self, respostas):
        self.respostas = respostas
        self.chamadas = []

    def __call__(self, method, path, body=None, params=None, prefer=None, timeout=15, **_k):
        self.chamadas.append({"m": method, "path": path, "body": body, "params": params or {}})
        for m, tabela, filtro, resp in self.respostas:
            if m == method and tabela in path and all(
                    (params or {}).get(k) == v for k, v in filtro.items()):
                return resp
        return (200, [])

    def escritas(self):
        return [c for c in self.chamadas if c["m"] in ("POST", "PATCH", "DELETE")]


def _montar(banco, usuario=ADMIN, papel="dono", enviados=None):
    enviados = enviados if enviados is not None else []

    def como_usuario(request, method, path, body=None, **_k):
        assert path == "rpc/escritorio_papel" and body == {"p_projeto": PROJ}
        return (200, papel)

    def enviar(to, assunto, html, texto="", log_kind="", **_k):
        enviados.append({"to": to, "assunto": assunto, "html": html, "texto": texto, "kind": log_kind})
        return True

    esc.configurar(servico=banco, como_usuario=como_usuario, usuario=lambda r: usuario,
                   enviar=enviar, moldura=lambda titulo, corpo, **k: f"<h1>{titulo}</h1>{corpo}<a href='{k.get('cta_url')}'>", registrar=None)
    return enviados


_PROJETO = ("GET", "escritorio_projetos", {}, (200, [{"id": PROJ, "nome": "Projeto Exemplo", "dono": ADMIN["id"]}]))
_ADMIN = ("GET", "escritorio_membros", {"papel": "eq.dono"}, (200, [{"nome": "Admin Exemplo", "email": ADMIN["email"]}]))
_CRIADO = ("POST", "escritorio_membros", {}, (201, [{"id": "m-novo"}]))


# ── peças puras ──
def test_o_link_leva_o_token_no_fragmento_e_nao_na_query():
    link = esc.link_do_convite("TOKEN123")
    assert link == "https://ai.arq.br/convite.html#t=TOKEN123"
    assert "?" not in link


def test_o_token_tem_256_bits_e_o_hash_e_sha256():
    t = esc.novo_token()
    assert len(t) >= 43 and esc.novo_token() != t
    assert len(esc.hash_do_token(t)) == 64 and esc.hash_do_token(t) != t


def test_mascara_nao_mostra_o_email_inteiro():
    assert esc.mascarar("pessoa.equipe@exemplo.com") == "pe***@exemplo.com"
    assert esc.mascarar("sem-arroba") == ""


@pytest.mark.parametrize("ruim", ["", "pessoa", "pessoa@", "a b@c.com", "x" * 250 + "@a.com"])
def test_email_ruim_reprova_em_portugues(ruim):
    with pytest.raises(HTTPException) as e:
        esc.normalizar_email(ruim)
    assert e.value.status_code == 400


def test_email_e_normalizado():
    assert esc.normalizar_email("  Equipe@Exemplo.COM ") == "equipe@exemplo.com"


def test_expirado():
    assert esc.expirado(PASSADO) and not esc.expirado(FUTURO) and esc.expirado(None) and esc.expirado("lixo")


# ── convidar ──
def test_convite_novo_grava_so_o_hash_e_manda_o_token_por_email():
    banco = _Banco([_PROJETO, _ADMIN, _CRIADO])
    enviados = _montar(banco)
    r = esc.convidar(PROJ, REQ, {"email": " Equipe@Exemplo.com ", "nome": "Pessoa Equipe", "telefone": "(11) 9 0000-0002"})
    assert r["ok"] and r["email_enviado"] and r["membro_id"] == "m-novo"
    token = r["link"].split("#t=")[1]
    post = [c for c in banco.escritas() if c["m"] == "POST"][0]
    assert post["body"]["convite_hash"] == esc.hash_do_token(token)
    assert token not in str(post["body"])                      # o token em si NÃO vai pro banco
    assert post["body"]["email"] == "equipe@exemplo.com"
    assert post["body"]["papel"] == "freela" and post["body"]["status"] == "convidado"
    assert post["body"]["nome"] == "Pessoa Equipe" and post["body"]["telefone"] == "(11) 9 0000-0002"
    assert enviados[0]["to"] == "equipe@exemplo.com" and enviados[0]["kind"] == "escritorio_convite"
    assert token in enviados[0]["html"] and enviados[0]["assunto"] == "Admin te convidou: Projeto Exemplo"


def test_quem_nao_e_admin_nao_convida_e_nada_e_escrito():
    banco = _Banco([_PROJETO, _ADMIN, _CRIADO])
    enviados = _montar(banco, usuario=EQUIPE, papel="freela")
    with pytest.raises(HTTPException) as e:
        esc.convidar(PROJ, REQ, {"email": "x@y.com"})
    assert e.value.status_code == 403 and banco.escritas() == [] and enviados == []


def test_sem_login_e_401():
    banco = _Banco([])
    _montar(banco, usuario=None)
    with pytest.raises(HTTPException) as e:
        esc.convidar(PROJ, REQ, {"email": "x@y.com"})
    assert e.value.status_code == 401 and banco.chamadas == []


def test_nao_convida_o_proprio_email():
    _montar(_Banco([_PROJETO]))
    with pytest.raises(HTTPException) as e:
        esc.convidar(PROJ, REQ, {"email": "ADMIN@exemplo.com"})
    assert e.value.status_code == 400


def test_quem_ja_esta_ativo_e_409():
    banco = _Banco([_PROJETO, ("GET", "escritorio_membros", {"email": "eq.equipe@exemplo.com"}, (200, [{"id": "m1", "status": "ativo"}]))])
    _montar(banco)
    with pytest.raises(HTTPException) as e:
        esc.convidar(PROJ, REQ, {"email": "equipe@exemplo.com"})
    assert e.value.status_code == 409 and banco.escritas() == []


def test_reconvite_troca_o_token_e_zera_a_conta_ligada():
    banco = _Banco([_PROJETO, _ADMIN,
                    ("GET", "escritorio_membros", {"email": "eq.equipe@exemplo.com"}, (200, [{"id": "m1", "status": "removido"}])),
                    ("PATCH", "escritorio_membros", {}, (200, [{"id": "m1"}]))])
    _montar(banco)
    r = esc.convidar(PROJ, REQ, {"email": "equipe@exemplo.com"})
    patch = banco.escritas()[0]
    assert patch["m"] == "PATCH" and patch["params"]["id"] == "eq.m1" and patch["params"]["projeto_id"] == f"eq.{PROJ}"
    assert patch["body"]["status"] == "convidado" and patch["body"]["user_id"] is None
    assert patch["body"]["convite_hash"] == esc.hash_do_token(r["link"].split("#t=")[1])


def test_texto_acima_do_teto_reprova_antes_do_banco():
    banco = _Banco([_PROJETO])
    _montar(banco)
    with pytest.raises(HTTPException) as e:
        esc.convidar(PROJ, REQ, {"email": "a@b.com", "telefone": "9" * 41})
    assert e.value.status_code == 400 and banco.escritas() == []


def test_banco_fora_e_502_e_nao_404():
    _montar(_Banco([("GET", "escritorio_projetos", {}, (500, None))]))
    with pytest.raises(HTTPException) as e:
        esc.convidar(PROJ, REQ, {"email": "a@b.com"})
    assert e.value.status_code == 502


# ── ver e aceitar ──
def _convite(status="convidado", expira=FUTURO):
    return ("GET", "escritorio_membros", {"convite_hash": f"eq.{esc.hash_do_token('T' * 43)}"},
            (200, [{"id": "m1", "projeto_id": PROJ, "email": "equipe@exemplo.com", "nome": None,
                    "status": status, "convite_expira": expira}]))


def test_ver_convite_mostra_projeto_e_email_mascarado():
    _montar(_Banco([_convite(), ("GET", "escritorio_projetos", {}, (200, [{"nome": "Projeto Exemplo"}])), _ADMIN]))
    r = esc.ver_convite({"token": "T" * 43})
    assert r == {"projeto": "Projeto Exemplo", "convidado_por": "Admin Exemplo", "email": "eq***@exemplo.com", "expirado": False}


def test_token_que_nao_existe_e_404_e_banco_fora_e_502():
    _montar(_Banco([]))
    with pytest.raises(HTTPException) as e:
        esc.ver_convite({"token": "X" * 43})
    assert e.value.status_code == 404
    _montar(_Banco([("GET", "escritorio_membros", {}, (500, None))]))
    with pytest.raises(HTTPException) as e:
        esc.ver_convite({"token": "X" * 43})
    assert e.value.status_code == 502


def test_aceitar_ativa_com_a_conta_logada_e_apaga_o_hash():
    banco = _Banco([_convite(), ("PATCH", "escritorio_membros", {}, (200, [{"id": "m1"}]))])
    _montar(banco, usuario=EQUIPE)
    r = esc.aceitar_convite(REQ, {"token": "T" * 43})
    assert r == {"ok": True, "projeto_id": PROJ, "email_da_conta_diferente": False}
    patch = banco.escritas()[0]
    assert patch["body"]["user_id"] == EQUIPE["id"] and patch["body"]["status"] == "ativo"
    assert patch["body"]["convite_hash"] is None
    assert patch["params"] == {"id": "eq.m1", "status": "eq.convidado"}   # dois aceites não ativam duas contas


def test_aceitar_com_outra_conta_vale_mas_avisa():
    banco = _Banco([_convite(), ("PATCH", "escritorio_membros", {}, (200, [{"id": "m1"}]))])
    _montar(banco, usuario={"id": "uid-x", "email": "outra.conta@exemplo.com"})
    assert esc.aceitar_convite(REQ, {"token": "T" * 43})["email_da_conta_diferente"] is True


def test_convite_vencido_e_410_e_nao_escreve():
    banco = _Banco([_convite(expira=PASSADO)])
    _montar(banco, usuario=EQUIPE)
    with pytest.raises(HTTPException) as e:
        esc.aceitar_convite(REQ, {"token": "T" * 43})
    assert e.value.status_code == 410 and banco.escritas() == []


def test_convite_ja_usado_e_404():
    _montar(_Banco([_convite(status="ativo")]), usuario=EQUIPE)
    with pytest.raises(HTTPException) as e:
        esc.aceitar_convite(REQ, {"token": "T" * 43})
    assert e.value.status_code == 404


def test_aceitar_sem_login_e_401():
    banco = _Banco([_convite()])
    _montar(banco, usuario=None)
    with pytest.raises(HTTPException) as e:
        esc.aceitar_convite(REQ, {"token": "T" * 43})
    assert e.value.status_code == 401 and banco.chamadas == []


def test_as_rotas_estao_no_app():
    import main
    caminhos = {r.path for r in main.app.routes}
    for c in ("/api/escritorio/projetos/{projeto_id}/convites", "/api/escritorio/convite/ver", "/api/escritorio/convite/aceitar"):
        assert c in caminhos, c


def test_assunto_cabe_no_celular_e_o_email_tem_previa():
    # o guarda de e-mails da casa só lê main.py; o convite mora em escritorio.py e se guarda aqui
    longo = esc.assunto_do_convite("Admin Exemplo", "Projeto de nome bem comprido — reforma completa da casa")
    assert len(longo) <= esc.TETO_ASSUNTO and longo.endswith("…") and longo.startswith("Admin te convidou:")
    vistos = {}
    esc.configurar(servico=None, como_usuario=None, usuario=None, enviar=None,
                   moldura=lambda titulo, corpo, **k: vistos.update(k) or "", registrar=None)
    esc.email_do_convite("Admin Exemplo", "d@x.com", "ABV", "https://ai.arq.br/convite.html#t=x")
    assert vistos.get("preheader") and vistos["preheader"] != "Convite para ABV"


def test_aceitar_sem_nome_pega_o_nome_do_cadastro_e_com_nome_nao_mexe():
    banco = _Banco([_convite(), ("GET", "profiles", {}, (200, [{"full_name": "Pessoa Equipe"}])),
                    ("PATCH", "escritorio_membros", {}, (200, [{"id": "m1"}]))])
    _montar(banco, usuario=EQUIPE)
    esc.aceitar_convite(REQ, {"token": "T" * 43})
    assert banco.escritas()[0]["body"]["nome"] == "Pessoa Equipe"
    # o admin já tinha dado nome: o do cadastro NÃO passa por cima
    ja_tem = ("GET", "escritorio_membros", {"convite_hash": f"eq.{esc.hash_do_token('T' * 43)}"},
              (200, [{"id": "m1", "projeto_id": PROJ, "email": "equipe@exemplo.com", "nome": "Apelido dado pelo admin",
                      "status": "convidado", "convite_expira": FUTURO}]))
    banco2 = _Banco([ja_tem, ("GET", "profiles", {}, (200, [{"full_name": "Pessoa Equipe"}])),
                     ("PATCH", "escritorio_membros", {}, (200, [{"id": "m1"}]))])
    _montar(banco2, usuario=EQUIPE)
    esc.aceitar_convite(REQ, {"token": "T" * 43})
    assert "nome" not in banco2.escritas()[0]["body"]


def test_perfil_ilegivel_nao_impede_o_aceite():
    banco = _Banco([_convite(), ("GET", "profiles", {}, (500, None)),
                    ("PATCH", "escritorio_membros", {}, (200, [{"id": "m1"}]))])
    _montar(banco, usuario=EQUIPE)
    assert esc.aceitar_convite(REQ, {"token": "T" * 43})["ok"] is True
    assert "nome" not in banco.escritas()[0]["body"]
