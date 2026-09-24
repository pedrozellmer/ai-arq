# -*- coding: utf-8 -*-
"""A PROVA do conector do AI.arq no Claude (Fase 0, 21/09/2026).

Pedro autorizou em 21/09: construir o conector, só leitura no começo, e ANTES
de tudo uma prova de 1–2 dias no servidor real, num endereço separado, sem
dado de cliente. A prova responde se o Claude manda a chave depois do login —
a issue anthropics/claude-ai-mcp#1038 (15/09/2026) diz que às vezes não manda;
se acontecer aqui, nada mais se constrói.

Estes guardas EXECUTAM as rotas de verdade pelo `main.app` (TestClient, sem
o startup) e fazem o caminho inteiro de um cliente OAuth: descoberta →
tela → código → chave → chamada MCP → renovação. Os ataques que a prova tem
que recusar mesmo sem dado atrás (porque a Fase 1 herda este código) estão
aqui também: código reusado, verificador errado, retorno fora da lista,
chave inventada, resource de outro servidor.
"""
import base64
import hashlib
import os
import sys
import urllib.parse

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402
import conector_teste as ct  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CLAUDE = "https://claude.ai/api/mcp/auth_callback"
RECURSO = "https://api.ai.arq.br/mcp-teste"
EMISSOR = "https://api.ai.arq.br"
URL_PRM = "https://api.ai.arq.br/.well-known/oauth-protected-resource/mcp-teste"
CID = "https://claude.ai/oauth/mcp-oauth-client-metadata"
VERIF = "verificador-de-teste-" + "x" * 40


def _desafio(v=VERIF):
    return base64.urlsafe_b64encode(hashlib.sha256(v.encode("ascii")).digest()).rstrip(b"=").decode()


@pytest.fixture
def cli(monkeypatch):
    logs = []
    monkeypatch.setattr(ct, "_REGISTRAR", lambda *a: logs.append(a))
    # a fila de log roda em thread; aqui síncrono, pra o teste ler na hora
    monkeypatch.setattr(ct, "_registrar",
                        lambda etapa, dados, *a, **k: logs.append(("conector-teste:" + etapa, dict(dados))))
    buscas = []
    monkeypatch.setattr(ct, "_buscar_cimd", lambda cid: buscas.append(cid) or {"buscado": True, "fumaca": True})
    for guardado in (ct._CODIGOS, ct._CHAVES, ct._RENOVACOES, ct._REPETICOES, ct._REVOGADAS,
                     ct._CIMD_CACHE, ct._ULTIMA_CHAVE_EMITIDA, ct._FREIOS):
        guardado.clear()
    monkeypatch.delenv("CONECTOR_TESTE", raising=False)
    c = TestClient(main.app, base_url="https://api.ai.arq.br")
    c.logs, c.buscas = logs, buscas
    return c


def _pedido(**troca):
    q = {"response_type": "code", "client_id": CID, "redirect_uri": CLAUDE, "state": "estado-1",
         "scope": "teste", "code_challenge": _desafio(), "code_challenge_method": "S256",
         "resource": RECURSO}
    q.update(troca)
    return q


def _codigo(cli, **troca):
    q = _pedido(**troca)
    r = cli.post("/authorize", data=q, follow_redirects=False)
    assert r.status_code == 302, r.text
    loc = urllib.parse.urlsplit(r.headers["location"])
    return q, urllib.parse.parse_qs(loc.query), loc


def _chave(cli):
    q, qs, _ = _codigo(cli)
    r = cli.post("/token", data={
        "grant_type": "authorization_code", "code": qs["code"][0], "client_id": CID,
        "redirect_uri": CLAUDE, "code_verifier": VERIF, "resource": RECURSO})
    assert r.status_code == 200, r.text
    return r.json()


def _mcp(cli, corpo, chave=None, **cab):
    h = dict(cab)
    if chave:
        h["Authorization"] = "Bearer " + chave
    return cli.post("/mcp-teste", json=corpo, headers=h)


def _init(versao="2025-06-18"):
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": versao, "capabilities": {},
                       "clientInfo": {"name": "claude-ai", "version": "0.1.0"}}}


# ══════════════════════════════════════════════════════════════════════════
#  1 · o caminho que o Claude faz, do começo ao fim
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_caminho_inteiro_do_claude(cli):
    r = _mcp(cli, _init())
    assert r.status_code == 401
    www = r.headers["www-authenticate"]
    assert www.startswith("Bearer ") and f'resource_metadata="{URL_PRM}"' in www

    prm = cli.get("/.well-known/oauth-protected-resource/mcp-teste").json()
    assert prm["resource"] == "https://api.ai.arq.br/mcp-teste", "tem que bater BYTE A BYTE com a URL colada"
    assert prm["authorization_servers"] == [EMISSOR]

    meta = cli.get("/.well-known/oauth-authorization-server").json()
    assert meta["issuer"] == EMISSOR, "issuer tem que ser idêntico ao anunciado no PRM"
    assert meta["client_id_metadata_document_supported"] is True
    assert "none" in meta["token_endpoint_auth_methods_supported"], "sem 'none' o Claude não usa CIMD"
    assert meta["code_challenge_methods_supported"] == ["S256"], "sem isto o cliente MCP recusa"
    assert "registration_endpoint" not in meta, "DCR fica de fora: CIMD primeiro (decisão de 21/09)"

    tela = cli.get("/authorize", params=_pedido())
    assert tela.status_code == 200 and "Permitir" in tela.text
    assert "Nenhum projeto nem dado seu é lido" in tela.text

    q, qs, loc = _codigo(cli)
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == CLAUDE
    assert qs["state"] == ["estado-1"] and qs["iss"] == [EMISSOR]

    tok = cli.post("/token", data={
        "grant_type": "authorization_code", "code": qs["code"][0], "client_id": CID,
        "redirect_uri": CLAUDE, "code_verifier": VERIF, "resource": RECURSO})
    assert tok.status_code == 200
    assert tok.headers["cache-control"] == "no-store"
    t = tok.json()
    assert t["token_type"] == "Bearer" and t["expires_in"] == ct.VIDA_CHAVE and t["refresh_token"]

    r = _mcp(cli, _init(), t["access_token"])
    assert r.status_code == 200 and r.json()["result"]["protocolVersion"] == "2025-06-18"
    assert r.json()["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert _mcp(cli, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                t["access_token"]).status_code == 202
    ferr = _mcp(cli, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, t["access_token"],
                **{"MCP-Protocol-Version": "2025-06-18"}).json()["result"]["tools"]
    assert [f["name"] for f in ferr] == ["teste_de_conexao"]
    assert ferr[0]["annotations"]["readOnlyHint"] is True
    res = _mcp(cli, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "teste_de_conexao", "arguments": {}}},
               t["access_token"], **{"MCP-Protocol-Version": "2025-06-18"}).json()["result"]
    assert res["isError"] is False
    assert "Conectado" in res["content"][0]["text"] and "2025-06-18" in res["content"][0]["text"]


def test_ping_e_versao_desconhecida_no_initialize(cli):
    t = _chave(cli)
    assert _mcp(cli, {"jsonrpc": "2.0", "id": 9, "method": "ping"}, t["access_token"]).json() == {
        "jsonrpc": "2.0", "id": 9, "result": {}}
    r = _mcp(cli, _init("1999-01-01"), t["access_token"]).json()
    assert r["result"]["protocolVersion"] in ct.VERSOES, "versão que não atendemos: responde a nossa"


# ══════════════════════════════════════════════════════════════════════════
#  2 · o que a prova tem que recusar (a Fase 1 herda este código)
# ══════════════════════════════════════════════════════════════════════════
def test_codigo_nao_serve_duas_vezes(cli):
    q, qs, _ = _codigo(cli)
    dados = {"grant_type": "authorization_code", "code": qs["code"][0], "client_id": CID,
             "redirect_uri": CLAUDE, "code_verifier": VERIF}
    assert cli.post("/token", data=dados).status_code == 200
    r = cli.post("/token", data=dados)
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


@pytest.mark.parametrize("campo,valor", [
    ("code_verifier", "outro-verificador-" + "y" * 40),
    ("redirect_uri", "https://claude.com/api/mcp/auth_callback"),
    ("client_id", "https://claude.ai/oauth/outro"),
    ("resource", "https://api.ai.arq.br/mcp"),
])
def test_token_recusa_o_que_nao_confere(cli, campo, valor):
    q, qs, _ = _codigo(cli)
    dados = {"grant_type": "authorization_code", "code": qs["code"][0], "client_id": CID,
             "redirect_uri": CLAUDE, "code_verifier": VERIF, "resource": RECURSO}
    dados[campo] = valor
    r = cli.post("/token", data=dados)
    assert r.status_code == 400 and r.json()["error"] in ("invalid_grant", "invalid_target"), r.text
    assert "access_token" not in r.text


def test_codigo_vencido_nao_vale(cli, monkeypatch):
    q, qs, _ = _codigo(cli)
    agora = ct._agora()
    monkeypatch.setattr(ct, "_agora", lambda: agora + ct.VIDA_CODIGO + 1)
    r = cli.post("/token", data={
        "grant_type": "authorization_code", "code": qs["code"][0], "client_id": CID,
        "redirect_uri": CLAUDE, "code_verifier": VERIF})
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


@pytest.mark.parametrize("troca", [
    {"redirect_uri": "https://atacante.example/callback"},
    {"redirect_uri": "http://claude.ai/api/mcp/auth_callback"},
    {"redirect_uri": "https://claude.ai/api/mcp/auth_callback/../../x"},
    {"redirect_uri": ""},
    {"client_id": ""},
])
def test_cliente_ou_retorno_ruim_para_na_TELA_sem_redirect(cli, troca):
    """Retorno não conferido: o erro NUNCA redireciona (redirect aberto)."""
    q = _pedido(**troca)
    tela = cli.get("/authorize", params=q, follow_redirects=False)
    assert tela.status_code == 400 and "Permitir" not in tela.text
    r = cli.post("/authorize", data=q, follow_redirects=False)
    assert r.status_code == 400 and "location" not in r.headers
    assert not ct._CODIGOS


@pytest.mark.parametrize("troca,erro", [
    ({"code_challenge_method": "plain"}, "invalid_request"),
    ({"code_challenge": ""}, "invalid_request"),
    ({"code_challenge_method": ""}, "invalid_request"),
    ({"response_type": "token"}, "unsupported_response_type"),
    ({"resource": "https://outro.example/mcp"}, "invalid_target"),
])
def test_resto_ruim_VOLTA_pro_claude_com_o_erro(cli, troca, erro):
    """Com o retorno conferido, o erro volta por redirect com state e iss
    (OAuth 2.1 §4.1.2.1) — e nenhum código nasce."""
    q = _pedido(**troca)
    for r in (cli.get("/authorize", params=q, follow_redirects=False),
              cli.post("/authorize", data=q, follow_redirects=False)):
        assert r.status_code == 302, r.text
        loc = urllib.parse.urlsplit(r.headers["location"])
        qs = urllib.parse.parse_qs(loc.query)
        assert f"{loc.scheme}://{loc.netloc}{loc.path}" == CLAUDE
        assert qs["error"] == [erro] and qs["state"] == ["estado-1"] and qs["iss"] == [EMISSOR]
        assert "code" not in qs
    assert not ct._CODIGOS


def test_loopback_do_claude_code_e_aceito(cli):
    q, qs, loc = _codigo(cli, redirect_uri="http://localhost:53682/callback",
                         client_id="https://claude.ai/oauth/claude-code-client-metadata")
    assert loc.netloc == "localhost:53682" and qs["code"]


def test_barra_final_no_resource_passa(cli):
    q, qs, _ = _codigo(cli, resource=RECURSO + "/")
    assert qs["code"]


@pytest.mark.parametrize("cab", [
    None, "Bearer inventada", "Basic dXNlcjpzZW5oYQ==", "Bearer ",
])
def test_mcp_sem_chave_valida_pede_login(cli, cab):
    h = {"Authorization": cab} if cab is not None else {}
    r = cli.post("/mcp-teste", json=_init(), headers=h)
    assert r.status_code == 401
    assert f'resource_metadata="{URL_PRM}"' in r.headers["www-authenticate"]
    assert "result" not in r.json()


def test_chave_vencida_pede_login_com_invalid_token(cli, monkeypatch):
    t = _chave(cli)
    agora = ct._agora()
    monkeypatch.setattr(ct, "_agora", lambda: agora + ct.VIDA_CHAVE + 1)
    r = _mcp(cli, _init(), t["access_token"])
    assert r.status_code == 401 and 'error="invalid_token"' in r.headers["www-authenticate"]


def test_jwt_do_site_nao_abre_o_mcp(cli):
    """A chave do conector é um sorteio em memória; um JWT do Supabase (o login
    do site) não pode valer aqui."""
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4Iiwicm9sZSI6ImF1dGhlbnRpY2F0ZWQifQ.assinatura"
    assert _mcp(cli, _init(), jwt).status_code == 401


# ══════════════════════════════════════════════════════════════════════════
#  3 · renovação (pergunta 5)
# ══════════════════════════════════════════════════════════════════════════
def _renovar(cli, renov):
    return cli.post("/token", data={"grant_type": "refresh_token",
                                                 "refresh_token": renov, "client_id": CID})


def test_renovacao_troca_o_par_e_a_velha_morre(cli, monkeypatch):
    t = _chave(cli)
    r1 = _renovar(cli, t["refresh_token"])
    assert r1.status_code == 200
    n = r1.json()
    assert n["access_token"] != t["access_token"] and n["refresh_token"] != t["refresh_token"]
    assert _mcp(cli, _init(), n["access_token"]).status_code == 200
    # retry de rede dentro da janela: o MESMO par, não um terceiro
    assert _renovar(cli, t["refresh_token"]).json() == n
    agora = ct._agora()
    monkeypatch.setattr(ct, "_agora", lambda: agora + ct.JANELA_REPETICAO + 1)
    r3 = _renovar(cli, t["refresh_token"])
    assert r3.status_code == 400 and r3.json()["error"] == "invalid_grant"


def test_renovacao_inventada_ou_de_outro_cliente(cli):
    assert _renovar(cli, "inventada").json()["error"] == "invalid_grant"
    t = _chave(cli)
    r = cli.post("/token", data={"grant_type": "refresh_token",
                                              "refresh_token": t["refresh_token"],
                                              "client_id": "https://claude.ai/oauth/outro"})
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


def test_token_so_aceita_formulario(cli):
    r = cli.post("/token", json={"grant_type": "refresh_token", "refresh_token": "x"})
    assert r.status_code == 400 and r.json()["error"] == "invalid_request"
    r = cli.post("/token", data={"grant_type": "password"})
    assert r.json()["error"] == "unsupported_grant_type"


# ══════════════════════════════════════════════════════════════════════════
#  4 · transporte
# ══════════════════════════════════════════════════════════════════════════
def test_get_e_delete_no_mcp_sao_405(cli):
    for metodo in ("GET", "DELETE"):
        r = cli.request(metodo, "/mcp-teste")
        assert r.status_code == 405 and r.headers["allow"] == "POST"


def test_metodo_e_ferramenta_desconhecidos(cli):
    t = _chave(cli)["access_token"]
    assert _mcp(cli, {"jsonrpc": "2.0", "id": 5, "method": "resources/list"}, t).json()["error"]["code"] == -32601
    r = _mcp(cli, {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                   "params": {"name": "apagar_tudo", "arguments": {}}}, t).json()
    assert r["error"]["code"] == -32602


def test_corpo_ilegivel_e_400(cli):
    t = _chave(cli)["access_token"]
    r = cli.post("/mcp-teste", content=b"{nao e json", headers={
        "Authorization": "Bearer " + t, "Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700


def test_lote_e_recusado(cli):
    """Lote JSON-RPC saiu na 2025-06-18 e não negociamos a 2025-03-26."""
    t = _chave(cli)["access_token"]
    r = _mcp(cli, [{"jsonrpc": "2.0", "id": 1, "method": "ping"},
                   {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}], t)
    assert r.status_code == 400 and r.json()["error"]["code"] == -32600


def test_id_volta_com_o_mesmo_tipo(cli):
    t = _chave(cli)["access_token"]
    assert _mcp(cli, {"jsonrpc": "2.0", "id": "123", "method": "ping"}, t).json()["id"] == "123"
    assert _mcp(cli, {"jsonrpc": "2.0", "id": 7, "method": "ping"}, t).json()["id"] == 7


# ══════════════════════════════════════════════════════════════════════════
#  4b · o cliente da spec 2026-07-28 tem que VOLTAR ao initialize
# ══════════════════════════════════════════════════════════════════════════
_META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
         "io.modelcontextprotocol/clientCapabilities": {}}


@pytest.mark.parametrize("corpo,cab", [
    ({"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": _META}},
     {"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "server/discover"}),
    ({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": _META}}, {}),
    ({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, {"MCP-Protocol-Version": "2026-07-28"}),
    ({"jsonrpc": "2.0", "id": 5, "method": "server/discover"}, {}),
    ({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
      "params": {"name": "teste_de_conexao", "arguments": {}}}, {"MCP-Protocol-Version": "2099-01-01"}),
])
def test_pedido_moderno_recebe_400_de_corpo_VAZIO(cli, corpo, cab):
    """🔑 Corpo vazio é o único sinal sem ambiguidade (spec 2026-07-28,
    Backward Compatibility). Com -32022/-32020/-32601 o cliente conclui que o
    servidor é moderno e NÃO volta — e a prova morreria calada."""
    t = _chave(cli)["access_token"]
    r = _mcp(cli, corpo, t, **cab)
    assert r.status_code == 400
    assert r.content == b"", r.content
    assert "mcp-session-id" not in {k.lower() for k in r.headers}


def test_depois_da_recusa_o_initialize_funciona(cli):
    t = _chave(cli)["access_token"]
    assert _mcp(cli, {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
                      "params": {"_meta": _META}}, t,
                **{"MCP-Protocol-Version": "2026-07-28"}).status_code == 400
    r = _mcp(cli, _init("2025-11-25"), t)
    assert r.status_code == 200 and r.json()["result"]["protocolVersion"] == "2025-11-25"


def test_initialize_nunca_e_recusado_pela_versao(cli):
    """No initialize, 400/404/405 faz o cliente 2025 tentar o transporte antigo
    (GET de SSE) — e o nosso GET é 405. Versão estranha no initialize = a nossa."""
    t = _chave(cli)["access_token"]
    for v in ("2026-07-28", "2025-03-26", ""):
        r = _mcp(cli, _init(v), t, **{"MCP-Protocol-Version": "2026-07-28"})
        assert r.status_code == 200 and r.json()["result"]["protocolVersion"] == ct.VERSAO_PADRAO


def test_CONTROLE_versao_de_2025_no_cabecalho_passa(cli):
    t = _chave(cli)["access_token"]
    for v in ct.VERSOES + ("",):
        h = {"MCP-Protocol-Version": v} if v else {}
        assert _mcp(cli, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, t, **h).status_code == 200


# ══════════════════════════════════════════════════════════════════════════
#  4c · dois endereços, chaves que não se misturam
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def direto(cli):
    c = TestClient(main.app, base_url="https://ai-arq.onrender.com")
    c.logs = cli.logs
    return c


def test_o_endereco_direto_anuncia_ele_mesmo(direto):
    prm = direto.get("/.well-known/oauth-protected-resource/mcp-teste").json()
    assert prm["resource"] == "https://ai-arq.onrender.com/mcp-teste"
    assert prm["authorization_servers"] == ["https://ai-arq.onrender.com"]
    meta = direto.get("/.well-known/oauth-authorization-server").json()
    assert meta["issuer"] == "https://ai-arq.onrender.com"
    assert meta["token_endpoint"] == "https://ai-arq.onrender.com/token"


def test_host_forjado_nao_muda_o_que_e_anunciado(cli):
    r = cli.get("/.well-known/oauth-protected-resource/mcp-teste", headers={"Host": "atacante.example"})
    assert r.json()["resource"] == RECURSO
    r = cli.get("/.well-known/oauth-authorization-server", headers={"Host": "atacante.example"})
    assert r.json()["issuer"] == EMISSOR


def test_chave_de_um_endereco_nao_abre_o_outro(cli, direto):
    t = _chave(cli)["access_token"]
    r = direto.post("/mcp-teste", json=_init(), headers={"Authorization": "Bearer " + t})
    assert r.status_code == 401 and 'error="invalid_token"' in r.headers["www-authenticate"]
    assert "ai-arq.onrender.com/.well-known" in r.headers["www-authenticate"]


def test_codigo_de_um_endereco_nao_troca_no_outro(cli, direto):
    q, qs, _ = _codigo(cli)
    r = direto.post("/token", data={"grant_type": "authorization_code", "code": qs["code"][0],
                                    "client_id": CID, "redirect_uri": CLAUDE, "code_verifier": VERIF})
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


def test_prm_e_emissor_tambem_nos_caminhos_de_reserva(cli):
    """O Claude cai pra raiz do PRM e pro openid-configuration; o mesmo JSON."""
    a = cli.get("/.well-known/oauth-protected-resource/mcp-teste").json()
    assert cli.get("/.well-known/oauth-protected-resource").json() == a
    b = cli.get("/.well-known/oauth-authorization-server").json()
    assert cli.get("/.well-known/openid-configuration").json() == b


def test_401_tem_a_forma_que_o_claude_espera(cli):
    r = _mcp(cli, _init())
    assert r.status_code == 401 and r.json()["error"] == "invalid_token"
    assert 'error="invalid_token"' not in r.headers["www-authenticate"], (
        "sem chave nenhuma não é chave inválida")


def test_a_tela_mostra_quem_pede(cli):
    tela = cli.get("/authorize", params=_pedido())
    assert "Pedido feito por: <b>claude.ai</b>" in tela.text


def test_o_ip_nunca_vai_pro_log(cli):
    t = _chave(cli)
    _mcp(cli, _init(), t["access_token"], **{"CF-Connecting-IP": "160.79.105.7", "CF-Ray": "abc123-GRU"})
    cli.get("/authorize", params=_pedido(), headers={"CF-Connecting-IP": "200.10.20.30"})
    tudo = repr(cli.logs)
    assert "160.79.105.7" not in tudo and "200.10.20.30" not in tudo
    ultimo = [d for e, d in cli.logs if e == "conector-teste:mcp"][-1]
    assert ultimo["cf_ray"] == "abc123-GRU" and ultimo["zona_ai_arq"] is True


# ══════════════════════════════════════════════════════════════════════════
#  5 · o que a prova precisa ANOTAR — e o que nunca pode anotar
# ══════════════════════════════════════════════════════════════════════════
def test_o_log_responde_as_perguntas_e_nunca_leva_segredo(cli):
    t = _chave(cli)
    _mcp(cli, _init(), t["access_token"], **{"CF-Connecting-IP": "160.79.105.7",
                                              "Origin": "https://claude.ai"})
    etapas = [e for e, _ in cli.logs]
    for e in ("conector-teste:permitiu", "conector-teste:token", "conector-teste:mcp"):
        assert e in etapas, etapas
    ultimo = [d for e, d in cli.logs if e == "conector-teste:mcp"][-1]
    assert ultimo["faixa_claude"] is True, "pergunta 4: veio da faixa do Claude?"
    assert ultimo["origin"] == "https://claude.ai", "pergunta 6"
    assert ultimo["versao_pedida"] == "2025-06-18", "pergunta 2"
    assert ultimo["chave"] == "ok", "pergunta 1"
    tudo = repr(cli.logs)
    for segredo in (t["access_token"], t["refresh_token"], VERIF):
        assert segredo not in tudo, "segredo no error_log"
    assert not any("code=" in repr(d) for _, d in cli.logs)


def test_a_assinatura_da_1038_fica_marcada(cli):
    """Chave emitida e, logo depois, chamada SEM ela: é o que a prova caça."""
    _chave(cli)
    _mcp(cli, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
         **{"CF-Connecting-IP": "160.79.104.1", "User-Agent": "Claude-User"})
    d = [d for e, d in cli.logs if e == "conector-teste:mcp-sem-chave"][-1]
    assert d["seg_desde_ultima_chave_deste_host"] is not None and d["seg_desde_ultima_chave_deste_host"] < 5
    assert d["suspeita_1038"] is True


def test_a_sonda_de_cadastro_nao_e_a_assinatura(cli, direto):
    """A sonda do Claude ao adicionar o conector (initialize via python-httpx,
    sem chave) é legítima; e a chave emitida no OUTRO host não conta."""
    _chave(cli)
    _mcp(cli, _init("2025-11-25"), **{"User-Agent": "python-httpx/0.28.1"})
    d = [d for e, d in cli.logs if e == "conector-teste:mcp-sem-chave"][-1]
    assert d["suspeita_1038"] is False
    direto.post("/mcp-teste", json=_init(), headers={"User-Agent": "Claude-User"})
    d = [d for e, d in cli.logs if e == "conector-teste:mcp-sem-chave"][-1]
    assert d["host"] == "ai-arq.onrender.com" and d["seg_desde_ultima_chave_deste_host"] is None
    assert d["suspeita_1038"] is False


def test_cimd_so_e_buscado_em_host_do_claude():
    """O documento CIMD é buscado pelo servidor: URL qualquer = SSRF."""
    assert ct._buscar_cimd("https://169.254.169.254/latest/meta-data") == {
        "buscado": False, "motivo": "host fora da lista"}
    assert ct._buscar_cimd("http://claude.ai/oauth/x")["buscado"] is False
    assert ct._buscar_cimd("https://claude.ai.atacante.example/x")["buscado"] is False


def test_a_tela_busca_o_cimd_do_claude(cli):
    cli.get("/authorize", params=_pedido())
    assert cli.buscas == [CID]
    info = [d for e, d in cli.logs if e == "conector-teste:autorizar"][-1]
    assert info["cimd"] == {"buscado": True, "fumaca": True}


def test_a_tela_nao_pode_ser_emoldurada(cli):
    tela = cli.get("/authorize", params=_pedido())
    assert tela.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in tela.headers["content-security-policy"]


def test_campo_malicioso_na_tela_vai_escapado(cli):
    tela = cli.get("/authorize", params=_pedido(state="\"'><script>alert(1)</script>"))
    assert "<script>alert(1)" not in tela.text


# ══════════════════════════════════════════════════════════════════════════
#  6 · a prova se desliga
# ══════════════════════════════════════════════════════════════════════════
ROTAS = [("GET", "/.well-known/oauth-protected-resource/mcp-teste"),
         ("GET", "/.well-known/oauth-authorization-server"),
         ("GET", "/authorize"), ("POST", "/authorize"),
         ("POST", "/token"), ("POST", "/mcp-teste"), ("GET", "/mcp-teste")]


def test_desligada_pelo_ambiente_tudo_some(cli, monkeypatch):
    monkeypatch.setenv("CONECTOR_TESTE", "0")
    for m, p in ROTAS:
        assert cli.request(m, p).status_code == 404, p


def test_depois_do_prazo_tudo_some(cli, monkeypatch):
    monkeypatch.setattr(ct, "_agora", lambda: ct.PROVA_ATE.timestamp() + 1)
    for m, p in ROTAS:
        assert cli.request(m, p).status_code == 404, p


def test_CONTROLE_antes_do_prazo_responde(cli, monkeypatch):
    monkeypatch.setattr(ct, "_agora", lambda: ct.PROVA_ATE.timestamp() - 60)
    assert cli.get("/.well-known/oauth-protected-resource/mcp-teste").status_code == 200


def test_a_prova_TEM_prazo_pra_morrer_sozinha():
    """A prova some sozinha se a gente esquecer dela.

    🔑 23/09: o prazo era 05/10 porque a prova era de 1–2 dias. Ela PASSOU em
    23/09 e o Pedro decidiu *"esquece 05/10, vamos fazer no nosso tempo"* —
    então virou 31/12/2026. O que NÃO muda é existir um prazo: a tela de
    permissão ainda não pede conta, e o Pedro aceitou o risco com a razão de
    que *"ninguém vai ter o link"*. Prazo é a rede pra quando essa premissa
    deixar de valer sem ninguém perceber.
    🪤 Este guarda existe pra impedir que alguém empurre a data pra sempre.
    Quando a Fase 1 entrar (login de verdade), a prova inteira sai.
    """
    from datetime import datetime, timezone
    assert ct.PROVA_ATE <= datetime(2027, 1, 31, tzinfo=timezone.utc), (
        "prazo longo demais: a prova tem que morrer sozinha")
    assert ct.PROVA_ATE > datetime(2026, 9, 23, tzinfo=timezone.utc), (
        "prazo no passado: a prova estaria morta")


def test_as_rotas_da_prova_nao_bloqueiam_o_laco(cli):
    """Rota async com rede dentro congela o site (27/08). Aqui a rede (CIMD e
    log) vai por fila própria de threads."""
    import inspect
    for nome in ("metadados_do_recurso", "metadados_do_emissor", "autorizar_tela",
                 "autorizar_permitir", "token", "mcp", "mcp_sem_post"):
        fonte = inspect.getsource(getattr(ct, nome))
        for proibido in ("urlopen(", ".open(", "_supabase_insert", "requests.", "_REGISTRAR("):
            assert proibido not in fonte, (nome, proibido)
    assert "_cimd_sem_prender_a_tela" in inspect.getsource(ct.autorizar_tela)
    assert "_EXEC_REDE" in inspect.getsource(ct._cimd_sem_prender_a_tela)
    assert inspect.getsource(ct).count("_SEM_REDIRECT.open(") == 1, "rede nova fora da fila própria"


# ══════════════════════════════════════════════════════════════════════════
#  7 · o que a revisão da casa pede de um servidor de login (Fase 1 herda)
# ══════════════════════════════════════════════════════════════════════════
def _troca(cli, qs, **extra):
    d = {"grant_type": "authorization_code", "code": qs["code"][0], "client_id": CID,
         "redirect_uri": CLAUDE, "code_verifier": VERIF}
    d.update(extra)
    return cli.post("/token", data=d)


def test_codigo_reusado_VALIDO_derruba_as_chaves_que_ele_rendeu(cli):
    q, qs, _ = _codigo(cli)
    t = _troca(cli, qs).json()
    assert _mcp(cli, _init(), t["access_token"]).status_code == 200
    assert _troca(cli, qs).json()["error"] == "invalid_grant"
    assert _mcp(cli, _init(), t["access_token"]).status_code == 401, "a chave do código roubado sobreviveu"
    assert _renovar(cli, t["refresh_token"]).json()["error"] == "invalid_grant"


def test_CONTROLE_replay_com_parametro_errado_nao_revoga(cli):
    q, qs, _ = _codigo(cli)
    t = _troca(cli, qs).json()
    assert _troca(cli, qs, code_verifier="z" * 50).json()["error"] == "invalid_grant"
    assert _mcp(cli, _init(), t["access_token"]).status_code == 200


def test_renovacao_reaproveitada_depois_da_janela_derruba_a_conexao(cli, monkeypatch):
    t = _chave(cli)
    n = _renovar(cli, t["refresh_token"]).json()
    agora = ct._agora()
    monkeypatch.setattr(ct, "_agora", lambda: agora + ct.JANELA_REPETICAO + 5)
    assert _renovar(cli, t["refresh_token"]).json()["error"] == "invalid_grant"
    assert _mcp(cli, _init(), n["access_token"]).status_code == 401, "par novo sobreviveu ao reuso"
    assert _renovar(cli, n["refresh_token"]).json()["error"] == "invalid_grant"


@pytest.mark.parametrize("verif", ["curto", "x" * 129, "com espaco " + "x" * 40])
def test_verificador_fora_do_formato(cli, verif):
    """O desafio é calculado do PRÓPRIO verificador ruim: sem a checagem de
    formato (43–128, RFC 7636 §4.1), o PKCE bateria e a chave sairia."""
    q, qs, _ = _codigo(cli, code_challenge=_desafio(verif))
    assert _troca(cli, qs, code_verifier=verif).json()["error"] == "invalid_grant"


def test_CONTROLE_verificador_no_formato_com_o_proprio_desafio(cli):
    v = "a" * 43
    q, qs, _ = _codigo(cli, code_challenge=_desafio(v))
    assert _troca(cli, qs, code_verifier=v).status_code == 200


def test_renovacao_de_um_endereco_nao_vale_no_outro(cli, direto):
    t = _chave(cli)
    r = direto.post("/token", data={"grant_type": "refresh_token",
                                    "refresh_token": t["refresh_token"], "client_id": CID})
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


def test_parametro_repetido_e_invalid_request(cli):
    q, qs, _ = _codigo(cli)
    corpo = ("grant_type=authorization_code&code=" + urllib.parse.quote(qs["code"][0])
             + "&code=outro&client_id=" + urllib.parse.quote(CID, safe="")
             + "&code_verifier=" + VERIF)
    r = cli.post("/token", content=corpo, headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 400 and r.json()["error"] == "invalid_request"


def test_token_sem_redirect_uri_e_aceito(cli):
    """O OAuth 2.1 tirou o redirect_uri do /token; se vier, tem que bater."""
    q, qs, _ = _codigo(cli)
    r = cli.post("/token", data={"grant_type": "authorization_code", "code": qs["code"][0],
                                 "client_id": CID, "code_verifier": VERIF})
    assert r.status_code == 200 and r.json()["access_token"]


class _RespFalsa:
    def __init__(self, status, corpo):
        self.status, self._c = status, corpo

    def read(self, n):
        return self._c[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _cimd_com(monkeypatch, status, corpo):
    import json as _json
    abertos = []

    class _Abridor:
        def open(self, req, timeout=None):
            abertos.append(req.full_url)
            return _RespFalsa(status, corpo if isinstance(corpo, bytes) else _json.dumps(corpo).encode())

    monkeypatch.setattr(ct, "_SEM_REDIRECT", _Abridor())
    ct._CIMD_CACHE.clear()
    return abertos


def test_cimd_le_o_documento_do_claude(monkeypatch):
    abertos = _cimd_com(monkeypatch, 200, {"client_id": CID, "client_name": "Claude",
                                           "redirect_uris": [CLAUDE],
                                           "token_endpoint_auth_method": "none"})
    r = ct._buscar_cimd(CID)
    assert abertos == [CID]
    assert r["client_id_confere"] is True and r["redirect_uris"] == [CLAUDE]


def test_cimd_documento_grande_ou_status_estranho_vira_erro(monkeypatch):
    _cimd_com(monkeypatch, 200, b"x" * 9000)
    assert "8 KB" in ct._buscar_cimd(CID)["erro"]
    _cimd_com(monkeypatch, 204, b"")
    assert "204" in ct._buscar_cimd(CID)["erro"]


def test_cimd_nao_segue_redirecionamento():
    assert ct._NaoSegue().redirect_request(None, None, 302, "Found", {}, "https://x/") is None
    assert any(isinstance(h, ct._NaoSegue) for h in ct._SEM_REDIRECT.handlers)


# ══════════════════════════════════════════════════════════════════════════
#  8 · a revisão de 21/09: memória, fila de log, CIMD, rótulos, barra final
# ══════════════════════════════════════════════════════════════════════════
def test_client_id_gigante_para_na_tela(cli):
    q = _pedido(client_id="https://claude.ai/oauth/" + "x" * 600)
    assert cli.post("/authorize", data=q, follow_redirects=False).status_code == 400
    assert not ct._CODIGOS


@pytest.mark.parametrize("desafio", ["a" * 42, "a" * 44, "a" * 200000, "=" * 43],
                         ids=["42", "44", "gigante", "sinal-de-igual"])
def test_desafio_fora_do_formato_S256_nao_e_guardado(cli, desafio):
    """🩸 revisão: client_id e desafio de ~1 MB cada ficavam 10 min na memória;
    ~1000 pedidos derrubariam o processo único. O S256 sempre tem 43."""
    q = _pedido(code_challenge=desafio)
    r = cli.post("/authorize", data=q, follow_redirects=False)
    if len(desafio) > 16384:
        assert r.status_code == 400, "o teto do formulário devia barrar antes"
    else:
        assert r.status_code == 302 and "error=invalid_request" in r.headers["location"]
    assert not ct._CODIGOS


def test_campo_do_formulario_grande_demais_e_recusado(cli):
    q = _pedido(state="s" * 20000)
    assert cli.post("/authorize", data=q, follow_redirects=False).status_code == 400
    assert not ct._CODIGOS


def test_POST_authorize_tem_freio_por_IP(cli):
    h = {"CF-Connecting-IP": "200.1.2.3"}
    for _ in range(ct.CODIGOS_POR_IP[0]):
        assert cli.post("/authorize", data=_pedido(), headers=h, follow_redirects=False).status_code == 302
    r = cli.post("/authorize", data=_pedido(), headers=h, follow_redirects=False)
    assert r.status_code == 429
    outro = cli.post("/authorize", data=_pedido(), headers={"CF-Connecting-IP": "200.9.9.9"},
                     follow_redirects=False)
    assert outro.status_code == 302, "o freio é por IP, não geral"


def test_cheio_RECUSA_o_novo_e_nao_despeja_a_chave_que_vale(cli, monkeypatch):
    """🩸 revisão: despejar o mais antigo deixava qualquer um derrubar a chave
    do Pedro cunhando 2001 pares sem login."""
    t = _chave(cli)
    q, qs, _ = _codigo(cli, state="x")
    monkeypatch.setattr(ct, "TETO_GUARDADOS", len(ct._CHAVES))
    r = _troca(cli, qs)
    assert r.status_code == 503 and r.json()["error"] == "temporarily_unavailable"
    assert _mcp(cli, _init(), t["access_token"]).status_code == 200, "a chave que valia foi despejada"


def test_corpo_grande_demais_e_413_sem_ler_tudo(cli):
    r = cli.post("/token", content=b"a=" + b"x" * (ct.TETO_CORPO_TOKEN + 10),
                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 413
    t = _chave(cli)["access_token"]
    r = cli.post("/mcp-teste", content=b"{" + b" " * (ct.TETO_CORPO_MCP + 10) + b"}",
                 headers={"Authorization": "Bearer " + t, "Content-Type": "application/json"})
    assert r.status_code == 413


def test_json_fundo_demais_nao_vira_500(cli):
    """RecursionError não é ValueError: virava 500 antes até da chave."""
    fundo = b"[" * 100000
    r = cli.post("/mcp-teste", content=fundo, headers={"Content-Type": "application/json"})
    assert r.status_code == 401
    t = _chave(cli)["access_token"]
    r = cli.post("/mcp-teste", content=fundo, headers={"Authorization": "Bearer " + t,
                                                        "Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700


def test_barra_final_no_mcp_nao_redireciona(cli):
    """307 pra outra URL e o Claude perde a chave (#1056)."""
    r = cli.post("/mcp-teste/", json=_init(), follow_redirects=False)
    assert r.status_code == 401
    t = _chave(cli)["access_token"]
    r = cli.post("/mcp-teste/", json=_init(), headers={"Authorization": "Bearer " + t},
                 follow_redirects=False)
    assert r.status_code == 200
    assert [d for e, d in cli.logs if e == "conector-teste:mcp"][-1]["barra"] is True
    assert cli.get("/mcp-teste/", follow_redirects=False).status_code == 405


@pytest.mark.parametrize("cab,forma", [
    ("Bearer undefined", "palavra"), ("Bearer null", "palavra"),
    ("Bearer a.b.c", "jwt"), ("Bearer " + "Z" * 43, "nossa"), ("Bearer x", "outra"),
])
def test_o_log_diz_a_CARA_da_chave_recusada(cli, cab, forma):
    """A #1038 pode chegar como "Bearer undefined" — tem que se distinguir de
    chave velha, sem gravar o segredo."""
    cli.post("/mcp-teste", json=_init(), headers={"Authorization": cab})
    d = [d for e, d in cli.logs if e == "conector-teste:mcp-chave-recusada"][-1]
    assert d["forma"] == forma and d["chave"] == "invalida"
    if forma in ("nossa", "jwt"):
        assert cab.split(" ", 1)[1] not in repr(d), "segredo no log"


def test_renovacao_usada_como_chave_aparece_no_log(cli):
    t = _chave(cli)
    _mcp(cli, _init(), t["refresh_token"])
    d = [d for e, d in cli.logs if e == "conector-teste:mcp-chave-recusada"][-1]
    assert d["e_renovacao"] is True


def test_chave_vencida_continua_dizendo_vencida_depois_de_outra_emissao(cli, monkeypatch):
    t = _chave(cli)
    agora = ct._agora()
    monkeypatch.setattr(ct, "_agora", lambda: agora + ct.VIDA_CHAVE + 5)
    _chave(cli)                                   # a emissão poda o guardado
    _mcp(cli, _init(), t["access_token"])
    d = [d for e, d in cli.logs if e == "conector-teste:mcp-chave-recusada"][-1]
    assert d["chave"] == "vencida"


def test_log_separa_rotacao_de_repeticao_e_conta_geracao(cli):
    t = _chave(cli)
    n = _renovar(cli, t["refresh_token"]).json()
    _renovar(cli, t["refresh_token"])
    toks = [d for e, d in cli.logs if e == "conector-teste:token" and d.get("ok")]
    assert [(d["geracao"], d["repetida"]) for d in toks] == [(1, False), (2, False), (2, True)]
    _mcp(cli, _init(), n["access_token"])
    d = [d for e, d in cli.logs if e == "conector-teste:mcp"][-1]
    assert d["geracao"] == 2 and 0 < d["resta_s"] <= ct.VIDA_CHAVE


def test_o_par_em_claro_some_depois_da_janela(cli, monkeypatch):
    t = _chave(cli)
    _renovar(cli, t["refresh_token"])
    assert len(ct._REPETICOES) == 1
    agora = ct._agora()
    monkeypatch.setattr(ct, "_agora", lambda: agora + ct.JANELA_REPETICAO + 5)
    _chave(cli)
    assert ct._REPETICOES == {}, "par válido em claro sobreviveu à janela"


def test_o_GET_anota_se_veio_chave(cli):
    t = _chave(cli)["access_token"]
    cli.get("/mcp-teste", headers={"Authorization": "Bearer " + t})
    d = [d for e, d in cli.logs if e == "conector-teste:mcp-get"][-1]
    assert d["chave"] == "ok"


def test_cimd_so_e_buscado_depois_do_pedido_passar(cli):
    cli.get("/authorize", params=_pedido(redirect_uri="https://atacante.example/cb"))
    cli.get("/authorize", params=_pedido(code_challenge="curto"))
    assert cli.buscas == [], "buscou o CIMD de pedido recusado"
    cli.get("/authorize", params=_pedido())
    assert cli.buscas == [CID]


def test_cimd_so_sob_oauth_e_sem_usuario_na_url():
    for cid in ("https://claude.ai/qualquer/caminho", "https://claude.ai@atacante.example/oauth/x",
                "https://x:y@claude.ai/oauth/x", "https://claude.ai:8443/oauth/x"):
        assert ct._buscar_cimd(cid)["buscado"] is False, cid


def test_cimd_sem_vaga_nao_espera(monkeypatch):
    abertos = _cimd_com(monkeypatch, 200, {"client_id": CID})
    assert ct._SEMAFORO_REDE.acquire(blocking=False) and ct._SEMAFORO_REDE.acquire(blocking=False)
    try:
        assert ct._buscar_cimd_com_vaga(CID) == {"buscado": False, "motivo": "fila cheia"}
    finally:
        ct._SEMAFORO_REDE.release()
        ct._SEMAFORO_REDE.release()
    assert abertos == []


def test_cimd_com_erro_nao_fica_no_cache(monkeypatch):
    _cimd_com(monkeypatch, 500, b"")
    ct._buscar_cimd(CID)
    assert CID not in ct._CIMD_CACHE


class _Grava:
    def __init__(self):
        self.linhas = []

    def __call__(self, stage, msg, *a, **k):
        self.linhas.append((stage, msg))


def test_a_fila_de_log_tem_teto_e_o_descarte_e_CONTADO(monkeypatch):
    """🩸 revisão: fila sem teto, 1 insert por pedido anônimo — uma rajada
    enchia a memória e o error_log por horas."""
    import queue as _q
    g = _Grava()
    monkeypatch.setattr(ct, "_REGISTRAR", g)
    monkeypatch.setattr(ct, "_FILA", _q.Queue(maxsize=5))
    monkeypatch.setattr(ct, "_garantir_consumidor", lambda: None)
    monkeypatch.setitem(ct._DESCARTADOS, "n", 0)
    for i in range(8):
        ct._registrar("descoberta-recurso", {"faixa_claude": True, "i": i}, "160.79.104.9")
    assert ct._FILA.qsize() == 5 and ct._DESCARTADOS["n"] == 3
    ct._gravar(ct._FILA.get())
    assert g.linhas[0] == ("conector-teste:descartados", '{"n": 3}'), "descarte calado"
    assert g.linhas[1][0] == "conector-teste:descoberta-recurso"
    assert '"t":' in g.linhas[1][1]


def test_freio_de_log_por_IP_so_pra_quem_nao_e_o_claude(monkeypatch):
    import queue as _q
    monkeypatch.setattr(ct, "_REGISTRAR", _Grava())
    monkeypatch.setattr(ct, "_FILA", _q.Queue(maxsize=1000))
    monkeypatch.setattr(ct, "_garantir_consumidor", lambda: None)
    monkeypatch.setitem(ct._DESCARTADOS, "n", 0)
    ct._FREIOS.clear()
    for _ in range(ct.LOG_POR_IP[0] + 10):
        ct._registrar("descoberta-recurso", {"faixa_claude": False}, "200.1.2.3")
    assert ct._FILA.qsize() == ct.LOG_POR_IP[0] and ct._DESCARTADOS["n"] == 10
    for _ in range(ct.LOG_POR_IP[0] + 10):
        ct._registrar("mcp", {"faixa_claude": True}, "160.79.104.9")
    assert ct._FILA.qsize() == 2 * ct.LOG_POR_IP[0] + 10, "a linha do Claude não pode ser freada"


def test_o_consumidor_de_log_e_daemon(monkeypatch):
    """Um deploy não pode esperar a fila de log esvaziar."""
    monkeypatch.setattr(ct, "_REGISTRAR", _Grava())
    ct._garantir_consumidor()
    assert ct._CONSUMIDOR["thread"].daemon is True
