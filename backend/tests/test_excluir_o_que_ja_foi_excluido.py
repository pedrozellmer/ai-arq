# -*- coding: utf-8 -*-
"""Excluir um item que JÁ foi excluído é sucesso, não "Erro ao salvar".

🩸 22/10/2026. Um cliente clicou "excluir" em dois itens que já tinha excluído
(tela de outra aba / 2º clique). O histórico (`item_reviews`) apontava pra um
item que não existe mais — o banco recusou pela chave estrangeira (409) —, a
rota respondeu 502 e a tela mostrou "Erro ao salvar: …" sobre uma exclusão que
já estava feita. E o evento de erro não dizia QUAL erro (só job_id e cid).

🔑 Só quando o banco RESPONDEU que o item não está lá. Leitura que falhou não é
"não existe": segue o caminho de sempre (e o 502 de sempre, se a escrita falhar).
🚨 Os guardas CHAMAM a rota (banco de mentira) e as funções da tela (motor JS).
"""
import os
import sys
import urllib.request

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _jsbancada import fonte_html, funcao_js, motor, rodar  # noqa: E402

_ITEM = "22222222-2222-4222-8222-222222222222"
NL = chr(10)


def _rota(monkeypatch, leitura):
    """`leitura` = o que o GET do item devolve: (status, linhas) ou uma exceção."""
    escritas = {"insert": 0, "urlopen": []}

    def _svc(metodo, caminho, *a, **k):
        if metodo == "GET" and caminho.startswith("project_items?"):
            if isinstance(leitura, Exception):
                raise leitura
            return leitura
        return 200, []

    def _insert(tabela, linha):
        escritas["insert"] += 1
        return True

    def _urlopen(req, timeout=None):
        escritas["urlopen"].append(req.get_method())
        return None

    monkeypatch.setattr(main, "_supa_rest_service", _svc)
    monkeypatch.setattr(main, "_supabase_insert", _insert)
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)
    monkeypatch.setattr(main, "_require_project_owner", lambda r, j: None)
    monkeypatch.setattr(main, "_agendar_aprendizado_revisao", lambda *a, **k: None)
    monkeypatch.setattr(main, "_assinatura_invalidar", lambda *a, **k: None)
    monkeypatch.setattr(main, "_contar_itens_no_banco", lambda j: None)
    req = type("R", (), {"headers": {}})()
    return req, escritas


def _excluir(req, action="reject"):
    p = main.ReviewPayload(action=action, comment="", reviewed_by="x@y.com")
    return main.submit_item_review("job12345", _ITEM, p, req)


def test_o_caso_excluir_o_que_ja_saiu_e_SUCESSO_sem_escrita(monkeypatch):
    req, esc = _rota(monkeypatch, (200, []))
    r = _excluir(req)
    assert r.get("status") == "ok" and r.get("ja_excluido") is True, r
    assert esc["insert"] == 0, "tentou gravar histórico de item que não existe (o 409)"
    assert esc["urlopen"] == [], "tentou apagar o que já não existe"


def test_CONTROLE_item_que_existe_segue_o_caminho_de_sempre(monkeypatch):
    req, esc = _rota(monkeypatch, (200, [{"description": "Porta", "unit": "un",
                                          "quantity": 3, "observations": "",
                                          "confidence": "estimado", "discipline": "X",
                                          "ref_sheet": "a"}]))
    r = _excluir(req)
    assert not r.get("ja_excluido"), r
    assert esc["insert"] == 1 and "DELETE" in esc["urlopen"], esc


def test_CONTROLE_leitura_que_FALHOU_nao_vira_ja_excluido(monkeypatch):
    req, esc = _rota(monkeypatch, RuntimeError("supabase fora"))
    r = _excluir(req)
    assert not r.get("ja_excluido"), "falha de leitura foi lida como 'não existe'"
    assert "DELETE" in esc["urlopen"]


def test_CONTROLE_banco_respondeu_ERRO_nao_vira_ja_excluido(monkeypatch):
    req, esc = _rota(monkeypatch, (500, []))
    r = _excluir(req)
    assert not r.get("ja_excluido"), r


def test_CONTROLE_editar_item_que_nao_existe_nao_e_atalho_de_exclusao(monkeypatch):
    req, esc = _rota(monkeypatch, (200, []))
    p = main.ReviewPayload(action="edit", comment="", reviewed_by="x@y.com",
                           edits={"quantity": 5})
    r = main.submit_item_review("job12345", _ITEM, p, req)
    assert not r.get("ja_excluido"), r


# ══════════════════════════════════════════════════════════════════════════
#  A TELA: o evento de erro diz QUAL erro
# ══════════════════════════════════════════════════════════════════════════
_SRC = fonte_html("revisao.html")


def _js(resposta_ok, status):
    pre = NL.join([
        "var authFetch = function () { return Promise.resolve({ok: %s, status: %d,"
        " clone: function () { return {json: function () {"
        " return Promise.resolve({detail: 'nao gravou'}); }}; }}); };"
        % ("true" if resposta_ok else "false", status),
        funcao_js("_salvar", "revisao.html", _SRC),
        funcao_js("_tipoDoErroDeSalvar", "revisao.html", _SRC),
        "var __tipo = null;",
        "async function __tenta() { try { await _salvar('u', {}); return 'ok'; }"
        " catch (e) { __tipo = _tipoDoErroDeSalvar(e); return e.message; } }",
    ])
    return motor(pre)


def test_o_erro_de_salvar_carrega_o_codigo_http():
    js = _js(False, 409)
    r = rodar(js, "__tenta()")
    assert r.get("ok"), r
    assert r["valor"] == "nao gravou"
    assert js.evaljs("__tipo") == "http-409"


def test_sem_resposta_o_tipo_e_rede():
    js = motor(funcao_js("_tipoDoErroDeSalvar", "revisao.html", _SRC))
    assert js.evaljs("_tipoDoErroDeSalvar(new Error('timeout'))") == "rede"
    assert js.evaljs("_tipoDoErroDeSalvar(null)") == "rede"


def test_os_dois_eventos_de_erro_mandam_o_type():
    """Guarda de FONTE só pra presença do campo nas duas chamadas."""
    linhas = [l for l in _SRC.splitlines() if "trackEvent('revisao_salvou_erro'" in l]
    assert len(linhas) == 2, linhas
    i = _SRC.index("trackEvent('revisao_salvou_erro', { job_id: jobId,", _SRC.index("falhou.length"))
    assert "type: 'lote-'" in _SRC[i:i + 200]
    assert "type: _tipoDoErroDeSalvar(e)" in linhas[0] or "type: _tipoDoErroDeSalvar(e)" in linhas[1]


@pytest.mark.parametrize("status,ok", [(200, True)])
def test_CONTROLE_resposta_ok_nao_vira_erro(status, ok):
    js = _js(ok, status)
    r = rodar(js, "__tenta()")
    assert r["valor"] == "ok" and js.evaljs("__tipo") is None


def test_o_evento_aceita_o_type_no_track():
    assert main._track_evento_aceito("revisao_salvou_erro")
