# -*- coding: utf-8 -*-
"""Informar a área com a revisão aberta não derruba a revisão.

🩸 27/10/2026 (07d11935, 239 linhas) — o cliente clicou "Completar itens de área"
na tela de revisão. `/inform-area` levou 83 s e a tela desistiu em 45 ("✗ Não
consegui agora"), sem recarregar. O servidor seguiu e trocou todas as linhas por
linhas de id novo. Dali em diante toda revisão foi com id morto: chave estrangeira
no banco, 502 na rota, "Failed to fetch" no navegador — 16 erros na tela, 40+
recusas no servidor. As 11 confirmações que ele já tinha feito ficaram soltas.
📏 `/inform-area`: 33 vezes em 13 projetos em 30 dias.

🚨 Os guardas CHAMAM a rota (banco de mentira) e rodam as funções da tela (motor JS).
"""
import os
import re
import sys
import urllib.request

import pytest
from fastapi import HTTPException

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _jsbancada import fonte_html, funcao_js, motor, rodar  # noqa: E402

_ITEM = "22222222-2222-4222-8222-222222222222"
NL = chr(10)


def _rota(monkeypatch, leitura, insert_ok):
    """`leitura`: o que o GET da linha devolve — (status, linhas) ou exceção."""
    def _svc(metodo, caminho, *a, **k):
        if metodo == "GET" and caminho.startswith("project_items?"):
            if isinstance(leitura, Exception):
                raise leitura
            return leitura
        return 200, []

    monkeypatch.setattr(main, "_supa_rest_service", _svc)
    monkeypatch.setattr(main, "_supabase_insert", lambda t, l: insert_ok)
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: None)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)
    monkeypatch.setattr(main, "_require_project_owner", lambda r, j: None)
    monkeypatch.setattr(main, "_agendar_aprendizado_revisao", lambda *a, **k: None)
    monkeypatch.setattr(main, "_assinatura_invalidar", lambda *a, **k: None)
    monkeypatch.setattr(main, "_contar_itens_no_banco", lambda j: None)
    return type("R", (), {"headers": {}})()


def _revisar(req, action, **k):
    p = main.ReviewPayload(action=action, comment="", reviewed_by="x@y.com", **k)
    return main.submit_item_review("job12345", _ITEM, p, req)


# ── a rota ────────────────────────────────────────────────────────────────
def test_o_caso_confirmar_linha_que_sumiu_e_409_com_a_frase(monkeypatch):
    req = _rota(monkeypatch, (200, []), insert_ok=False)
    with pytest.raises(HTTPException) as e:
        _revisar(req, "approve")
    assert e.value.status_code == 409 and e.value.detail == main._LINHA_SUBSTITUIDA


def test_editar_linha_que_sumiu_e_409(monkeypatch):
    req = _rota(monkeypatch, (200, []), insert_ok=False)
    with pytest.raises(HTTPException) as e:
        _revisar(req, "edit", edits={"quantity": 5})
    assert e.value.status_code == 409


def test_CONTROLE_linha_que_existe_e_o_banco_falhou_segue_502(monkeypatch):
    req = _rota(monkeypatch, (200, [{"id": _ITEM}]), insert_ok=False)
    with pytest.raises(HTTPException) as e:
        _revisar(req, "approve")
    assert e.value.status_code == 502


def test_CONTROLE_leitura_que_falhou_nao_vira_linha_sumida(monkeypatch):
    req = _rota(monkeypatch, RuntimeError("supabase fora"), insert_ok=False)
    with pytest.raises(HTTPException) as e:
        _revisar(req, "approve")
    assert e.value.status_code == 502


def test_CONTROLE_banco_que_respondeu_erro_nao_vira_linha_sumida(monkeypatch):
    req = _rota(monkeypatch, (500, []), insert_ok=False)
    with pytest.raises(HTTPException) as e:
        _revisar(req, "approve")
    assert e.value.status_code == 502


def test_CONTROLE_confirmar_que_gravou_nao_pergunta_nada(monkeypatch):
    req = _rota(monkeypatch, (200, []), insert_ok=True)
    assert _revisar(req, "approve")["status"] == "ok"


# ── as revisões sobrevivem à troca ────────────────────────────────────────
def _banco(monkeypatch, linhas_antes, linhas_depois, revisoes):
    estado = {"linhas": linhas_antes, "patches": []}

    def _tudo(tabela, params=None, **k):
        return 200, (revisoes if tabela == "item_reviews" else estado["linhas"])

    def _svc(metodo, caminho, corpo=None, *a, **k):
        estado["patches"].append((caminho, corpo))
        return 200, []

    monkeypatch.setattr(main, "_supa_rest_tudo", _tudo)
    monkeypatch.setattr(main, "_supa_rest_service", _svc)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    estado["trocar"] = lambda: estado.update(linhas=linhas_depois)
    return estado


def _L(i, d, u="m²"):
    return {"id": i, "description": d, "unit": u}


def test_o_caso_a_confirmacao_volta_pra_linha_nova(monkeypatch):
    b = _banco(monkeypatch, [_L("v1", "Piso"), _L("v2", "Forro")],
               [_L("n1", "Piso"), _L("n2", "Forro")],
               [{"id": 7, "item_id": "v1"}])
    antes = main._revisoes_por_linha_antes_do_swap("j")
    b["trocar"]()
    assert main._religar_revisoes_apos_swap("j", antes) == 1
    assert b["patches"] == [("item_reviews?id=eq.7", {"item_id": "n1"})]


def test_CONTROLE_duas_linhas_iguais_nao_dizem_qual_foi_tocada(monkeypatch):
    b = _banco(monkeypatch, [_L("v1", "Piso"), _L("v2", "Piso")],
               [_L("n1", "Piso"), _L("n2", "Piso")],
               [{"id": 7, "item_id": "v1"}])
    antes = main._revisoes_por_linha_antes_do_swap("j")
    b["trocar"]()
    assert main._religar_revisoes_apos_swap("j", antes) == 0 and b["patches"] == []


def test_CONTROLE_duas_revisoes_na_mesma_descricao_ficam_soltas(monkeypatch):
    b = _banco(monkeypatch, [_L("v1", "Piso"), _L("v2", "Piso")], [_L("n1", "Piso")],
               [{"id": 7, "item_id": "v1"}, {"id": 8, "item_id": "v2"}])
    antes = main._revisoes_por_linha_antes_do_swap("j")
    b["trocar"]()
    assert main._religar_revisoes_apos_swap("j", antes) == 0 and b["patches"] == []


def test_CONTROLE_unidade_diferente_nao_casa(monkeypatch):
    b = _banco(monkeypatch, [_L("v1", "Piso", "m²")], [_L("n1", "Piso", "ml")],
               [{"id": 7, "item_id": "v1"}])
    antes = main._revisoes_por_linha_antes_do_swap("j")
    b["trocar"]()
    assert main._religar_revisoes_apos_swap("j", antes) == 0


def test_religar_nunca_derruba_a_rota(monkeypatch):
    def _quebra(*a, **k):
        raise RuntimeError("fora")
    monkeypatch.setattr(main, "_supa_rest_tudo", _quebra)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    assert main._revisoes_por_linha_antes_do_swap("j") == {}
    assert main._religar_revisoes_apos_swap("j", {"7": ("Piso", "m²")}) == 0


def test_o_inform_area_guarda_antes_e_religa_depois_do_swap():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read()
    i = src.index("def inform_project_area(")
    a = src.index("_revisoes_por_linha_antes_do_swap(job_id)", i)
    p = src.index("_persist_items_to_supabase(job_id, items)", i)
    r = src.index("_religar_revisoes_apos_swap(job_id, _revs_antes)", i)
    assert a < p < r


# ── a chamada morta do TCPO ───────────────────────────────────────────────
def test_o_tcpo_nao_chama_a_rpc_que_saiu_do_banco(monkeypatch):
    import tcpo_matcher as _tm

    def _proibido(*a, **k):
        raise AssertionError("chamou a RPC dropada em 22/07")
    monkeypatch.setattr(_tm, "_supabase_rpc", _proibido)
    assert _tm.match_item("Piso porcelanato 60x60") == []


# ── o teto da tela ────────────────────────────────────────────────────────
_UTILS = fonte_html("aiarq-utils.js")


def _lentas():
    m = re.search(r"var _lentas = /(.+)/i;", _UTILS)
    assert m, "a lista de rotas lentas mudou de forma"
    return re.compile(m.group(1), re.I)


def test_informar_area_tem_o_teto_das_rotas_lentas():
    assert _lentas().search("https://api.ai.arq.br/api/project/abc/inform-area")


def test_CONTROLE_rota_comum_segue_no_teto_curto():
    assert not _lentas().search("https://api.ai.arq.br/api/items/abc/review/1")


# ── a tela ────────────────────────────────────────────────────────────────
_SRC = fonte_html("revisao.html")
_CACHE = "window = this; window.aiarqCache = {limpar: function () { __limpou++; }}; var __limpou = 0;"


def _js_salvar(status):
    pre = NL.join([
        _CACHE,
        "var __recargas = 0; var _planilhaMudou = function () { __recargas++; };",
        "var authFetch = function () { return Promise.resolve({ok: %s, status: %d,"
        " clone: function () { return {json: function () {"
        " return Promise.resolve({detail: 'nao gravou'}); }}; }}); };"
        % ("true" if status < 400 else "false", status),
        funcao_js("_salvar", "revisao.html", _SRC),
        "var __st = null;",
        "async function __tenta() { try { await _salvar('u', {}); return 'ok'; }"
        " catch (e) { __st = e.status; return e.message; } }",
    ])
    return motor(pre)


def test_salvar_com_409_recarrega_as_linhas_e_diz_o_que_houve():
    js = _js_salvar(409)
    r = rodar(js, "__tenta()")
    assert "recarreguei as linhas" in r["valor"]
    assert js.evaljs("__recargas") == 1 and js.evaljs("__st") == 409


@pytest.mark.parametrize("status", [502, 500, 401])
def test_CONTROLE_outro_erro_nao_recarrega(status):
    js = _js_salvar(status)
    rodar(js, "__tenta()")
    assert js.evaljs("__recargas") == 0


def _js_recarga():
    return motor(NL.join([
        _CACHE,
        "var __args = []; var __resolver = null;",
        "var loadItems = function (r) { __args.push(r); return Promise.resolve(); };",
        "var _recarregandoPlanilha = false; var reviewState = {morto: 'approved'};",
        funcao_js("_planilhaMudou", "revisao.html", _SRC),
    ]))


def test_a_recarga_limpa_o_cache_e_nao_conta_como_abertura():
    js = _js_recarga()
    rodar(js, "_planilhaMudou()")
    assert js.evaljs("__limpou") == 1
    assert js.evaljs("JSON.stringify(__args)") == "[true]"
    assert js.evaljs("Object.keys(reviewState).length") == 0, "ids mortos no 'já revisados'"


def test_CONTROLE_lote_com_varias_recusas_recarrega_uma_vez():
    js = _js_recarga()
    js.evaljs("_recarregandoPlanilha = true; 1;")
    rodar(js, "_planilhaMudou()")
    assert js.evaljs("__args.length") == 0


def _js_espera(id_novo_na_volta):
    """`id_novo_na_volta`: em qual consulta a lista já vem com id novo (0 = nunca)."""
    return motor(NL.join([
        _CACHE,
        "var setTimeout = function (f) { f(); };",
        "var API_BASE = ''; var jobId = 'j'; var items = [{id: 'v1'}, {id: 'v2'}];",
        "var __voltas = 0; var __mudou = 0; var __falha = 0;",
        "var _planilhaMudou = function () { __mudou++; return Promise.resolve(); };",
        "var authFetch = function () { __voltas++;"
        " if (__falha && __voltas === __falha) return Promise.reject(new Error('rede'));"
        " var novo = %d && __voltas >= %d;"
        " return Promise.resolve({ok: true, json: function () {"
        " return Promise.resolve({items: novo ? [{id: 'n1'}] : [{id: 'v1'}, {id: 'v2'}]}); }}); };"
        % (id_novo_na_volta, id_novo_na_volta),
        "var _ESPERA_REMONTAGEM = {passoMs: 1, vezes: 5};",
        "var __msg = {textContent: '', className: ''};",
        funcao_js("_esperarRemontagem", "revisao.html", _SRC),
    ]))


def test_a_espera_recarrega_quando_os_ids_trocam():
    js = _js_espera(3)
    assert rodar(js, "_esperarRemontagem(__msg)")["valor"] is True
    assert js.evaljs("__voltas") == 3 and js.evaljs("__mudou") == 1
    assert js.evaljs("__limpou") == 3, "o cache de 30 s esconderia a troca"


def test_CONTROLE_nada_mudou_a_espera_desiste():
    js = _js_espera(0)
    assert rodar(js, "_esperarRemontagem(__msg)")["valor"] is False
    assert js.evaljs("__voltas") == 5 and js.evaljs("__mudou") == 0


def test_a_espera_aguenta_uma_consulta_que_falha():
    js = _js_espera(3)
    js.evaljs("__falha = 1; 1;")
    assert rodar(js, "_esperarRemontagem(__msg)")["valor"] is True


def _js_convite(resposta):
    """Roda o `submitConviteArea` REAL. `resposta`: status, ou 0 = sem resposta."""
    return motor(NL.join([
        _CACHE,
        "var __el = {}; function __e(id) { return __el[id] || (__el[id] ="
        " {value: '2810', textContent: '', className: '', disabled: false}); }",
        "var document = {getElementById: __e};",
        "var API_BASE = ''; var jobId = 'j'; var projMeta = {}; var __espera = 0; var __r = true;",
        "var __ev = []; window.trackEvent = function (n) { __ev.push(n); };",
        "var trackEvent = window.trackEvent;",
        "var loadItems = function () { return Promise.resolve(); };",
        "var _esperarRemontagem = function () { __espera++; return Promise.resolve(__r); };",
        "var authFetch = function () { %s };" % (
            "return Promise.reject(new Error('demorou'));" if resposta == 0 else
            "return Promise.resolve({ok: false, status: %d});" % resposta),
        funcao_js("submitConviteArea", "revisao.html", _SRC),
        "1;",
    ]))


@pytest.mark.parametrize("resposta", [0, 502, 524])
def test_sem_resposta_a_tela_espera_antes_de_dizer_que_falhou(resposta):
    js = _js_convite(resposta)
    rodar(js, "submitConviteArea()")
    assert js.evaljs("__espera") == 1
    textos = js.evaljs("JSON.stringify(Object.keys(__el).map(function (k) { return __el[k].textContent; }))")
    assert "Pronto" in textos and "Não consegui" not in textos


def test_CONTROLE_nada_mudou_diz_que_nao_conseguiu():
    js = _js_convite(0)
    js.evaljs("__r = false; 1;")
    rodar(js, "submitConviteArea()")
    assert "Não consegui" in js.evaljs(
        "JSON.stringify(Object.keys(__el).map(function (k) { return __el[k].textContent; }))")


@pytest.mark.parametrize("resposta", [400, 401, 422])
def test_CONTROLE_recusa_do_servidor_nao_espera_nada(resposta):
    js = _js_convite(resposta)
    rodar(js, "submitConviteArea()")
    assert js.evaljs("__espera") == 0
