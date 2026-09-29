# -*- coding: utf-8 -*-
"""O envio de arquivos usa o login de AGORA, não o de quando a página abriu.

🩸 29/09/2026 — caso 18c57c3c. Cliente novo: cadastro às 14:25, painel aberto
a tarde toda; às 17:23–17:26 apertou "Processar" três vezes e levou 401 nas
três. Só passou às 17:49, quando voltou pelo link do e-mail e a página
recarregou. O `accessToken` do dashboard é lido UMA vez, ao abrir; o login do
Supabase vence em 1 h. Em 23/08 a consulta de status passou a pedir a sessão
na hora — o envio ficou de fora.
📏 90 dias (usage_events, só quem aceitou a telemetria — piso): 4 pessoas,
9 envios com 401, entre 1h43 e 11h09 de aba aberta; 3 nunca mais subiram nada
(uma era cliente novo, sem nenhum projeto).

Roda o `startProcessing` REAL no motor JS (a mesma encenação do teste do anexo
recusado) e olha o cabeçalho que o XHR do `/api/process` mandou.
"""
import json
import os
import sys
import time

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

from _jsbancada import motor, rodar  # noqa: E402
import test_o_anexo_recusado_nao_vira_projeto_sozinho as _anexo  # noqa: E402

_CAPTURA = "this.setRequestHeader = function () {};"


def _preludio():
    p = _anexo._PRELUDIO
    assert p.count(_CAPTURA) == 1, "a encenação do XHR mudou: ajuste a captura do cabeçalho"
    return p.replace(_CAPTURA, "this.setRequestHeader = function (k, v) {"
                               " (x._hdr = x._hdr || {})[k] = v; __hdrs.push([x._u, k, v]); };"
                     ) + "\nvar __hdrs = [];\n1;"


def _envio(sessao="", refresh="", resposta=None, mutacoes=()):
    """Um envio de 1 DWG, sem projeto irmão. `sessao`/`refresh` = JS da sessão
    que o Supabase devolve. Devolve (resultado do motor, estado da tela)."""
    _site, fonte = _anexo._fonte_das_funcoes(mutacoes)
    js = motor(_preludio())
    js.evaljs(fonte + "\n;1;")
    js.evaljs("_soPdfNoEnvio = function () { return false; };"
              "var selectedFiles = [{ name: 'eletrico.dwg' }]; __candidatos = [];"
              "accessToken = 'jwt-da-abertura-vencido'; 1;")
    if sessao:
        js.evaljs("sbClient = { auth: { getSession: function () { %s } %s } }; 1;"
                  % (sessao, (", refreshSession: function () { %s }" % refresh) if refresh else ""))
    if resposta:
        js.evaljs("__respProcess = %s; 1;" % json.dumps(resposta))
    r = rodar(js, "startProcessing()")
    tela = json.loads(js.evaljs(
        "JSON.stringify({hdrs: __hdrs, estados: __estados, erro: errorMessage.textContent,"
        " ev: __ev})"))
    return r, tela


def _auth_do_process(tela):
    return [v for u, k, v in tela["hdrs"] if "/api/process" in u and k == "Authorization"]


def _sessao(token, faltam_s):
    return ("return Promise.resolve({ data: { session: { access_token: %s,"
            " expires_at: %d } } });" % (json.dumps(token), int(time.time()) + faltam_s))


def test_o_caso_o_envio_manda_o_login_de_agora():
    r, tela = _envio(sessao=_sessao("jwt-renovado-agora", 3000))
    assert "ok" in r, r
    assert _auth_do_process(tela) == ["Bearer jwt-renovado-agora"], tela["hdrs"]


def test_faltando_pouco_pra_vencer_renova_antes_de_subir():
    """Arquivo grande leva minutos; o servidor confere o login no fim."""
    r, tela = _envio(sessao=_sessao("jwt-quase-vencendo", 120),
                     refresh=_sessao("jwt-novinho", 3600))
    assert "ok" in r, r
    assert _auth_do_process(tela) == ["Bearer jwt-novinho"], tela["hdrs"]


def test_com_folga_nao_renova_a_toa():
    r, tela = _envio(sessao=_sessao("jwt-com-folga", 3000),
                     refresh="throw new Error('não era pra renovar');")
    assert _auth_do_process(tela) == ["Bearer jwt-com-folga"], (r, tela["hdrs"])


def test_supabase_fora_do_ar_segue_com_o_que_tinha():
    """Falha ao pedir a sessão não pode derrubar o envio (fica como era)."""
    r, tela = _envio(sessao="return Promise.reject(new Error('sem rede'));")
    assert "ok" in r, r
    assert _auth_do_process(tela) == ["Bearer jwt-da-abertura-vencido"], tela["hdrs"]


def test_401_diz_o_que_fazer_em_vez_do_texto_do_servidor():
    r, tela = _envio(sessao=_sessao("jwt-x", 3000), resposta={
        "status": 401, "texto": '{"detail":"Autenticação requerida (Bearer token ausente ou inválido)"}'})
    assert "sessão expirou" in tela["erro"] and "Recarregue a página" in tela["erro"], tela["erro"]
    assert "Bearer" not in tela["erro"], tela["erro"]
    assert ["upload_erro", {"type": "401"}] in tela["ev"], tela["ev"]


def test_CONTROLE_sem_o_conserto_volta_o_login_da_abertura():
    r, tela = _envio(sessao=_sessao("jwt-renovado-agora", 3000), mutacoes=[(
        "accessToken = (await _tokenDoEnvio()) || accessToken;", "")])
    assert _auth_do_process(tela) == ["Bearer jwt-da-abertura-vencido"], tela["hdrs"]
