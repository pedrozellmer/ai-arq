# -*- coding: utf-8 -*-
"""O dono do projeto vem do LOGIN, e o log de acesso não anota dado pessoal.

🩸 25/09/2026. O upload do painel mandava e-mail, nome completo e nome do
projeto na QUERY STRING do `POST /api/process`, e o chat mandava a pergunta na
query do `/api/agent/ask`. O uvicorn grava a URL inteira (e o preflight
`OPTIONS` grava de novo): 18 linhas com e-mail em ~30 h, 8 pessoas.

Esta é a metade do SERVIDOR do conserto — a da tela está em
`test_dado_pessoal_nao_vai_na_url.py`. O servidor:
  1. tira e-mail e nome do LOGIN (o token), aceita o nome do projeto no form e
     a pergunta no JSON — e ainda entende a URL velha;
  2. mascara esses campos no log de acesso, se chegarem mesmo assim.

🔑 Por que o servidor entende OS DOIS formatos: a tela sai pelo GitHub Pages
em ~1 min, o servidor pelo Render em vários. Tela nova com servidor velho
gravaria projeto SEM e-mail (o aviso de "pronto" não chegaria) e o chat
responderia 400. Por isso o servidor sobe primeiro — e a aba que o cliente
deixou aberta antes do deploy continua funcionando.
"""
import asyncio
import io
import json
import logging
import os
import sys
import types
from urllib.parse import unquote_plus

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import log_de_acesso  # noqa: E402
import main  # noqa: E402

EMAIL = "cliente@exemplo.com"
NOME = "Cliente Exemplo"
PROJETO = "Projeto Exemplo"
UID = "00000000-0000-4000-8000-000000000001"
PERGUNTA = "quantos metros de rodapé tem na sala do Cliente Exemplo?"


def _vazamentos(texto, valores):
    """Quais destes valores aparecem no texto — cru ou decodificado."""
    cru, lido = texto or "", unquote_plus(texto or "")
    return [v for v in valores if v in cru or v in lido]


# ══════════════════════════════════════════════════════════════════════════
#  1. O SERVIDOR — identidade do token, nome do projeto no form
# ══════════════════════════════════════════════════════════════════════════
class _Upload:
    def __init__(self, filename, conteudo=b"%PDF-1.4 planta de mentira\n"):
        self.filename = filename
        self._c = conteudo
        self.size = len(conteudo)
        self._i = 0

    async def seek(self, n):
        self._i = n

    async def read(self, n=-1):
        if n is None or n < 0:
            n = len(self._c) - self._i
        pedaco = self._c[self._i:self._i + n]
        self._i += len(pedaco)
        return pedaco


class _Pedido:
    def __init__(self):
        self.headers = {}
        self.client = types.SimpleNamespace(host="203.0.113.9")


_TOKEN_COMPLETO = {"id": UID, "email": EMAIL, "nome": NOME}


@pytest.fixture
def banco(monkeypatch, tmp_path):
    """A rota de produção inteira; só rede, banco e motor saem do ar.
    Devolve a lista de linhas gravadas em `projects`."""
    linhas = []

    def _insert(tabela, dados, *a, **k):
        if tabela == "projects":
            linhas.append(dict(dados))

    monkeypatch.setattr(main, "_supabase_insert", _insert)
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda request, tolerante=False: dict(_TOKEN_COMPLETO))
    monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: True)
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_envio_recente_igual", lambda assinatura: None)
    monkeypatch.setattr(main, "_registrar_envio", lambda assinatura, job_id: None)
    monkeypatch.setattr(main, "_process_job_throttled", lambda *a, **k: None)
    monkeypatch.setattr(main, "_notify_admin", lambda *a, **k: True)
    monkeypatch.setattr(main, "_projeto_ja_enviado", lambda *a, **k: None)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    return linhas


def _sobe(**k):
    """Chama `/api/process` DE VERDADE, direto (sem o FastAPI na frente).
    🪤 `sheet_*` têm `Form(default=[])`: chamada direta recebe o objeto Form."""
    async def _go():
        return await main.process_files(
            request=_Pedido(), background_tasks=None, files=[_Upload("planta.pdf")],
            sheet_types=[], sheet_ambientes=[], **k)
    return asyncio.run(_go())


def test_o_servidor_tira_email_e_nome_do_LOGIN(banco):
    """A tela nova não manda id, e-mail nem nome — e o projeto nasce com os três."""
    _sobe(nome_do_projeto=PROJETO)
    assert len(banco) == 1, banco
    p = banco[0]
    assert (p["user_id"], p["user_email"], p["user_name"]) == (UID, EMAIL, NOME), p
    assert p["project_name"] == PROJETO, (
        "o nome do projeto que veio no FORM não chegou ao banco: %r" % p["project_name"])


def test_o_token_VENCE_o_que_a_URL_velha_diz(banco):
    """A aba velha ainda manda e-mail/nome na query. O dono é quem o token diz."""
    _sobe(nome_do_projeto=PROJETO, user_id=UID,
          user_email="outra-pessoa@exemplo.com", user_name="Outra Pessoa")
    assert (banco[0]["user_email"], banco[0]["user_name"]) == (EMAIL, NOME), banco[0]


def test_a_aba_VELHA_ainda_consegue_enviar(banco, monkeypatch):
    """Compatibilidade: tudo na query, nada no form, token sem nome (formato
    de antes de 25/09). O projeto nasce igual — nome do projeto e nome da
    pessoa vêm da URL, como vinham."""
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda request, tolerante=False: {"id": UID, "email": EMAIL})
    _sobe(project_name=PROJETO, user_id=UID, user_email=EMAIL, user_name=NOME)
    p = banco[0]
    assert (p["project_name"], p["user_email"], p["user_name"]) == (PROJETO, EMAIL, NOME), p


def test_o_admin_subindo_pela_conta_do_cliente_nao_troca_o_email_dele(banco, monkeypatch):
    """🪤 Se o token vencesse sempre, o projeto que o admin sobe pela conta do
    cliente nasceria com o e-mail do ADMIN — e o aviso de pronto iria pra ele."""
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda request, tolerante=False: {
                            "id": "uid-do-admin", "email": main.ADMIN_EMAIL, "nome": "Admin Exemplo"})
    _sobe(nome_do_projeto=PROJETO, user_id=UID, user_email=EMAIL, user_name=NOME)
    p = banco[0]
    assert (p["user_id"], p["user_email"], p["user_name"]) == (UID, EMAIL, NOME), p


def test_pelo_FASTAPI_de_verdade_o_form_chega_na_rota(banco, monkeypatch):
    """🪤 A chamada direta pula o FastAPI — ela não prova que o campo
    `project_name` do multipart vira `nome_do_projeto` (alias), nem que ele não
    briga com o `project_name` da query. Aqui passa pelo parse de verdade."""
    from fastapi.testclient import TestClient
    cliente = TestClient(main.app, raise_server_exceptions=False)
    arq = ("planta.pdf", io.BytesIO(b"%PDF-1.4 planta de mentira\n"), "application/pdf")

    r = cliente.post("/api/process?typology=office", files={"files": arq},
                     data={"project_name": PROJETO},
                     headers={"Authorization": "Bearer token-de-teste"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert banco[-1]["project_name"] == PROJETO, banco[-1]
    assert banco[-1]["user_email"] == EMAIL, banco[-1]

    # e a URL velha (nada no form) continua funcionando pelo mesmo caminho
    arq = ("planta2.pdf", io.BytesIO(b"%PDF-1.4 outra planta\n"), "application/pdf")
    r = cliente.post("/api/process?typology=office&project_name=Projeto+Antigo",
                     files={"files": arq},
                     headers={"Authorization": "Bearer token-de-teste"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert banco[-1]["project_name"] == "Projeto Antigo", banco[-1]


# ── O chat ────────────────────────────────────────────────────────────────
class _ReqChat:
    def __init__(self, corpo=b""):
        self._corpo = corpo
        self.state = types.SimpleNamespace()

    async def body(self):
        return self._corpo


def _pergunta_que_chega(monkeypatch, corpo, question_na_query=""):
    import agent
    visto = {}

    def _falso_ask(job_id, question, max_iterations=8, history=None, **k):
        visto["q"], visto["h"] = question, history
        return {"answer": "ok", "tool_calls": [], "iterations": 1}

    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: "dono")
    monkeypatch.setattr(agent, "ask", _falso_ask)
    monkeypatch.setattr(agent, "tipos_de_arquivo_do_projeto",
                        lambda *a, **k: {"pdf": 1, "dxf": 0, "dwg": 0})
    asyncio.run(main.agent_ask(_ReqChat(corpo), job_id="job0001",
                               question=question_na_query))
    return visto


def test_o_chat_le_a_pergunta_do_CORPO(monkeypatch):
    corpo = json.dumps({"question": PERGUNTA, "history": [{"role": "user", "content": "oi"}]})
    visto = _pergunta_que_chega(monkeypatch, corpo.encode("utf-8"))
    assert visto["q"] == PERGUNTA, visto
    assert visto["h"] == [{"role": "user", "content": "oi"}], visto


def test_o_chat_da_aba_VELHA_ainda_responde(monkeypatch):
    corpo = json.dumps({"history": []}).encode("utf-8")
    assert _pergunta_que_chega(monkeypatch, corpo, PERGUNTA)["q"] == PERGUNTA


def test_o_chat_confere_o_DONO_antes_de_ler_o_corpo(monkeypatch):
    """A pergunta mudou pro corpo, mas a ordem de antes fica: quem não é dono
    é barrado sem que o corpo dele entre na memória."""
    from fastapi import HTTPException
    lidos = []

    class _ReqEspia(_ReqChat):
        async def body(self):
            lidos.append(1)
            return b'{"question": "x"}'

    def _nao_e_dono(*a, **k):
        raise HTTPException(403, "não é seu")
    monkeypatch.setattr(main, "_require_project_owner", _nao_e_dono)
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.agent_ask(_ReqEspia(), job_id="job0001", question=""))
    assert e.value.status_code == 403 and lidos == [], (
        "o corpo de quem não é dono foi lido (%d vez)" % len(lidos))


def test_CONTROLE_chat_sem_pergunta_em_lugar_nenhum_e_recusado(monkeypatch):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _pergunta_que_chega(monkeypatch, json.dumps({"history": []}).encode("utf-8"))
    assert e.value.status_code == 400


# ── O nome sai do login ───────────────────────────────────────────────────
class _RespAuth:
    def __init__(self, payload):
        self._p = payload

    def read(self):
        return json.dumps(self._p).encode("utf-8")


@pytest.mark.parametrize("meta,esperado", [
    ({"full_name": NOME, "name": "Outro"}, NOME),
    ({"name": NOME}, NOME),
    ({}, ""),
    (None, ""),
    (["formato", "estranho"], ""),     # 🪤 não pode virar 503 de "login"
])
def test_o_login_devolve_o_nome_do_cadastro(monkeypatch, meta, esperado):
    import urllib.request
    payload = {"id": UID, "email": "Cliente@Exemplo.com", "user_metadata": meta}
    monkeypatch.setattr(main, "SUPABASE_URL", "https://supa.exemplo.test")
    monkeypatch.setattr(main, "SUPABASE_KEY", "chave-de-teste")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _RespAuth(payload))
    req = types.SimpleNamespace(headers={"Authorization": "Bearer token-de-teste"})
    u = main._get_user_from_request(req)
    assert u == {"id": UID, "email": EMAIL, "nome": esperado}, u


# ══════════════════════════════════════════════════════════════════════════
#  2. O LOG DE ACESSO — a aba velha continua mandando; o log não anota
# ══════════════════════════════════════════════════════════════════════════
# 🪤 Exatamente o que o uvicorn 0.30 (h11_impl) chama. O `AccessFormatter`
# desempacota os 5 argumentos — o filtro tem que devolver 5.
_FORMATO_UVICORN = '%s - "%s %s HTTP/%s" %d'
_URL_VELHA = ("/api/process?typology=office&project_type=arquitetura"
              "&project_name=Projeto+Exemplo&user_id=%s"
              "&user_email=cliente%%40exemplo.com&user_name=Cliente+Exemplo" % UID)


class _Captura(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.registros = []

    def emit(self, record):
        self.registros.append(record)


def _loga(nome_do_logger, caminho):
    lg = logging.getLogger(nome_do_logger)
    cap, nivel = _Captura(), lg.level
    lg.addHandler(cap)
    lg.setLevel(logging.INFO)
    try:
        lg.info(_FORMATO_UVICORN, "10.0.0.1:5000", "POST", caminho, "1.1", 200)
    finally:
        lg.removeHandler(cap)
        lg.setLevel(nivel)
    assert len(cap.registros) == 1, "a linha nem saiu — o filtro engoliu o acesso?"
    return cap.registros[0]


def test_o_log_de_acesso_do_uvicorn_nao_anota_o_dado_pessoal():
    """O filtro está no logger `uvicorn.access` porque o `main` o instala ao
    ser importado — é assim que ele chega na produção."""
    rec = _loga("uvicorn.access", _URL_VELHA)
    linha = rec.getMessage()
    vazou = _vazamentos(linha, [EMAIL, NOME, PROJETO])
    assert not vazou, "o log de acesso ainda grava %s: %s" % (vazou, linha)
    assert "user_email=<omitido>" in linha, linha
    assert "typology=office" in linha and UID in linha, (
        "o filtro apagou o que NÃO é pessoal — o log perde o diagnóstico: %s" % linha)
    assert len(rec.args) == 5, "o AccessFormatter do uvicorn desempacota 5: %r" % (rec.args,)


def test_CONTROLE_sem_o_filtro_a_mesma_linha_VAZA():
    """Prova que a captura enxerga: o mesmo acesso num logger sem o filtro sai
    com o e-mail."""
    linha = _loga("aiarq.teste.sem_filtro", _URL_VELHA).getMessage()
    assert EMAIL in unquote_plus(linha), linha


def test_a_pergunta_do_chat_tambem_e_mascarada():
    linha = _loga("uvicorn.access",
                  "/api/agent/ask?job_id=job0001&question=quantos%20metros%3F").getMessage()
    assert "question=<omitido>" in linha and "job_id=job0001" in linha, linha


@pytest.mark.parametrize("caminho,esperado", [
    ("/api/x?email=a%40b.com", "/api/x?email=<omitido>"),
    ("/api/x?a=1&EMAIL=a%40b.com&b=2", "/api/x?a=1&EMAIL=<omitido>&b=2"),
    ("/api/x?not_email=1&user_email_hash=2", "/api/x?not_email=1&user_email_hash=2"),
    ("/api/sem/query", "/api/sem/query"),
])
def test_a_mascara_troca_so_o_valor_das_chaves_pessoais(caminho, esperado):
    assert log_de_acesso.mascarar_query(caminho) == esperado


@pytest.mark.parametrize("args", [None, (), ("so", "dois"), (1, 2, 3, 4, 5), {"a": 1}])
def test_argumento_de_formato_estranho_passa_intacto(args):
    rec = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "x", None, None)
    rec.args = args
    assert log_de_acesso.SemDadoPessoalNaUrl().filter(rec) is True
    assert rec.args == args


def test_o_filtro_nunca_derruba_a_requisicao(monkeypatch):
    """Exceção no filtro sobe até o `logger.info` do protocolo HTTP e derruba a
    resposta. Se a máscara quebrar por dentro, a linha sai como veio."""
    def _quebra(caminho):
        raise RuntimeError("máscara quebrada")
    monkeypatch.setattr(log_de_acesso, "mascarar_query", _quebra)
    rec = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1,
                            _FORMATO_UVICORN, None, None)
    rec.args = ("10.0.0.1:5000", "POST", _URL_VELHA, "1.1", 200)
    assert log_de_acesso.SemDadoPessoalNaUrl().filter(rec) is True
    assert rec.args[2] == _URL_VELHA


def test_instalar_duas_vezes_nao_duplica_o_filtro():
    lg = log_de_acesso.instalar("aiarq.teste.instala")
    log_de_acesso.instalar("aiarq.teste.instala")
    assert sum(1 for f in lg.filters
               if getattr(f, "marca_aiarq_sem_dado_pessoal", False)) == 1
