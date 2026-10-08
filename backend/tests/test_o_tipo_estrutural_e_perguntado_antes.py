# -*- coding: utf-8 -*-
"""O tipo do projeto é perguntado ANTES do envio quando os nomes são de estrutura.

📏 07/10/2026. O aviso "esses arquivos parecem de projeto ESTRUTURAL" vinha na
RESPOSTA do envio, com o projeto já criado e rodando como arquitetura. Desde o
conserto do regex (03/09) ele disparou 6 vezes, as 6 eram estrutura de verdade,
e só 1 pessoa reenviou no tipo certo. Os outros 5 saíram lidos como
arquitetura: concreto, aço e fôrma perdidos.

🔑 A régua de "nome estrutural" mora no SERVIDOR (`_nome_parece_estrutural`,
4 consertos). A estimativa de preço, que a tela já chama ao escolher os
arquivos, passa a devolver um booleano por arquivo — e a tela só pergunta.

🚨 Os guardas CHAMAM o código: a rota pelo TestClient, a tela num motor JS.
🧪 Controles: tipo já Estrutura não pergunta; minoria de nomes (apoio no meio
da arquitetura) não pergunta; sem resposta do servidor não pergunta; sem o
toast não cai no confirm() nativo; "Manter Arquitetura" não troca nada.
"""
import io
import json
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

from _jsbancada import fonte_html, funcao_js, motor, rodar  # noqa: E402

_SRC = fonte_html("dashboard.html")
NL = chr(10)

# nomes SINTÉTICOS no formato dos casos reais (nada de nome de cliente aqui)
_EST = ["100-EST-EX-0001-PIL-R00.dwg", "100-EST-EX-0002-PIL-R00.dwg",
        "GALPAO - FUNDACOES FORMAS E ARMACAO.dwg"]
_ARQ = ["PLANTA BAIXA TERREO.dwg", "CORTES E FACHADAS.pdf", "LAYOUT.dwg"]


# ══════════════════════════════════════════════════════════════════════════
#  O SERVIDOR: a estimativa diz quais nomes têm cara de estrutura
# ══════════════════════════════════════════════════════════════════════════
def _cliente(monkeypatch):
    import main as _m
    import pricing
    monkeypatch.setattr(_m, "_rate_limit_ok", lambda *a, **k: True)
    # o precheck roda num filho protegido e lê o arquivo: não é o que se testa
    monkeypatch.setattr(pricing, "precheck_em_filho", lambda paths: [])
    from fastapi.testclient import TestClient
    return TestClient(_m.app, raise_server_exceptions=False)


def _pdf_minimo():
    return (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF")


def _estima(monkeypatch, nomes):
    cli = _cliente(monkeypatch)
    arquivos = [("files", (n, io.BytesIO(_pdf_minimo()), "application/pdf"))
                for n in nomes]
    r = cli.post("/api/estimate-price", files=arquivos, data={"known_pranchas": "0"})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    return r.json()


def test_a_estimativa_devolve_um_booleano_por_arquivo_NA_ORDEM(monkeypatch):
    nomes = [_ARQ[0], _EST[0], _ARQ[1], _EST[2]]
    d = _estima(monkeypatch, nomes)
    assert d.get("nomes_estruturais") == [False, True, False, True], d


def test_a_regra_e_a_MESMA_do_aviso_depois_do_envio(monkeypatch):
    """Nada de 2ª régua: o booleano é o `_nome_parece_estrutural` do envio,
    inclusive nas exceções que ele aprendeu (negação, ESTRUTURADO, Lajeado)."""
    import main as _m
    nomes = ["ARQ_EXE_REV01_SEM ESTRUTURAL.pdf", "CABEAMENTO ESTRUTURADO.dwg",
             "LAJEADO-CENTRO.dwg", "PILAR-P1.dwg", "ARMAÇÕES.pdf", "ESTRUT_TERREO.pdf"]
    d = _estima(monkeypatch, nomes)
    assert d["nomes_estruturais"] == [_m._nome_parece_estrutural(n) for n in nomes], d
    assert d["nomes_estruturais"] == [False, False, False, True, True, True], d


def test_CONTROLE_so_reprecificar_sem_arquivo_devolve_lista_vazia(monkeypatch):
    cli = _cliente(monkeypatch)
    r = cli.post("/api/estimate-price", data={"known_pranchas": "4"})
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("nomes_estruturais") == []


def test_o_evento_da_pergunta_e_aceito_pelo_track():
    import main as _m
    assert _m._track_evento_aceito("aviso-pre-envio:estrutural")


# ══════════════════════════════════════════════════════════════════════════
#  A TELA: a pergunta, rodando de verdade
# ══════════════════════════════════════════════════════════════════════════
def _preludio(nomes, marcados, tipo="arquitetura", com_toast=True, escolha=True,
              toast_quebra=False):
    lista = ", ".join("{name: %s, size: 10, lastModified: 1}" % json.dumps(n)
                      for n in nomes)
    partes = [
        "var selectedFiles = [%s];" % lista,
        "var _efKey = function (f) { return f.name + ':' + f.size + ':' + f.lastModified; };",
        "var _nomeEstrutural = new Map();",
    ]
    for n in marcados:
        partes.append("_nomeEstrutural.set(%s + ':10:1', true);" % json.dumps(n))
    partes += [
        "var __sel = {value: %s, dataset: {}};" % json.dumps(tipo),
        "var document = {getElementById: function (id) {"
        " return id === 'project-type' ? __sel : null; }};",
        "var __msg = null, __op = null, __confirmou = 0, __ev = [], __pd = 0;",
        "var confirm = function (m) { __confirmou++; return true; };",
        "var trackEvent = function (nome, meta) { __ev.push([nome, meta]); };",
        "var aplicarTextoDoPeDireito = function () { __pd++; };",
        "var window = {};",
    ]
    if com_toast:
        if toast_quebra:
            partes.append("window.toast = { confirm: function (msg, op) {"
                          " __msg = msg; return Promise.reject(new Error('x')); } };")
        else:
            partes.append(
                "window.toast = { confirm: function (msg, op) { __msg = msg; __op = op;"
                " return Promise.resolve(%s); } };" % ("true" if escolha else "false"))
    partes += [funcao_js("_arquivosComCaraDeEstrutura", "dashboard.html", _SRC),
               funcao_js("_confirmarTipoEstrutural", "dashboard.html", _SRC)]
    return NL.join(partes)


def _resp(nomes, marcados, **kw):
    js = motor(_preludio(nomes, marcados, **kw))
    return js, rodar(js, "_confirmarTipoEstrutural()")


def test_todos_com_cara_de_estrutura_PERGUNTA_e_troca_o_tipo():
    js, r = _resp(_EST, _EST)
    assert r.get("ok"), r
    assert r["valor"] == "trocou"
    assert js.evaljs("__sel.value") == "estrutura", "a resposta não trocou o tipo"
    assert js.evaljs("__sel.dataset.escolhidoAMao") == "1"
    assert js.evaljs("__pd") == 1, "o texto do pé-direito não acompanhou o tipo"
    msg = js.evaljs("__msg")
    assert "Os 3 arquivos parecem de projeto ESTRUTURAL" in msg, msg
    assert _EST[0] in msg, msg
    assert "não mede aço, pilares nem lajes" in msg, msg
    assert js.evaljs("__op.ok") == "Ler como Estrutura"
    assert js.evaljs("__op.cancel") == "Manter Arquitetura"


def test_o_placar_registra_a_ESCOLHA():
    js, _ = _resp(_EST, _EST)
    ev = js.evaljs("JSON.stringify(__ev)")
    assert json.loads(ev) == [["aviso-pre-envio:estrutural",
                               {"type": "estrutura", "n": 3, "tela": "envio"}]], ev


def test_MANTER_arquitetura_nao_troca_nada_e_segue():
    js, r = _resp(_EST, _EST, escolha=False)
    assert r["valor"] == "seguir"
    assert js.evaljs("__sel.value") == "arquitetura"
    assert js.evaljs("__sel.dataset.escolhidoAMao") is None
    assert json.loads(js.evaljs("JSON.stringify(__ev)"))[0][1]["type"] == "arquitetura"


def test_maioria_estrutural_tambem_pergunta():
    nomes = [_EST[0], _EST[1], _ARQ[0]]
    js, r = _resp(nomes, [_EST[0], _EST[1]])
    assert r["valor"] == "trocou"
    assert "2 dos 3 arquivos parecem" in js.evaljs("__msg")


def test_um_arquivo_so():
    js, r = _resp([_EST[0]], [_EST[0]])
    assert r["valor"] == "trocou"
    assert js.evaljs("__msg").startswith("O arquivo parece de projeto ESTRUTURAL")


def test_nome_comprido_e_cortado_na_mensagem():
    longo = "X" * 80 + "-EST-PIL.dwg"
    js, _ = _resp([longo], [longo])
    msg = js.evaljs("__msg")
    assert longo not in msg and ("X" * 45 + "...") in msg, msg


def test_CONTROLE_tipo_ja_ESTRUTURA_nao_pergunta():
    js, r = _resp(_EST, _EST, tipo="estrutura")
    assert r["valor"] == "seguir"
    assert js.evaljs("__msg") is None


def test_CONTROLE_MINORIA_estrutural_nao_pergunta():
    """Um "sapatas.pdf" no meio da arquitetura é apoio, não engano de tipo."""
    nomes = ["SAPATAS.pdf"] + ["ARQ-%02d.pdf" % i for i in range(26)]
    js, r = _resp(nomes, ["SAPATAS.pdf"])
    assert r["valor"] == "seguir"
    assert js.evaljs("__msg") is None
    assert js.evaljs("__sel.value") == "arquitetura"


def test_CONTROLE_sem_resposta_do_servidor_nao_opina():
    """Estimativa falhou ou não voltou: nenhum booleano, nenhuma pergunta — o
    aviso depois do envio continua valendo."""
    js, r = _resp(_EST, [])
    assert r["valor"] == "seguir"
    assert js.evaljs("__msg") is None


def test_CONTROLE_sem_o_toast_NAO_cai_no_confirm_nativo():
    js, r = _resp(_EST, _EST, com_toast=False)
    assert r["valor"] == "seguir"
    assert js.evaljs("__confirmou") == 0, "caiu no confirm() nativo (trava a aba)"
    assert js.evaljs("__sel.value") == "arquitetura"


def test_CONTROLE_toast_que_QUEBRA_nao_trava_o_envio():
    js, r = _resp(_EST, _EST, toast_quebra=True)
    assert r.get("ok"), r
    assert r["valor"] == "seguir"
    assert js.evaljs("__sel.value") == "arquitetura"


# ══════════════════════════════════════════════════════════════════════════
#  A TELA guarda o que o servidor respondeu
# ══════════════════════════════════════════════════════════════════════════
def _preludio_estimativa(resposta):
    return NL.join([
        "var window = {API_UPLOAD_BASE: 'https://api'};",
        "var lastEstimate = null, lastEstimateKey = '', estimateAbortCtrl = null;",
        "var estimateFileCache = new Map();",
        "var _efKey = function (f) { return f.name + ':' + f.size + ':' + f.lastModified; };",
        "var _nomeEstrutural = new Map();",
        "var __render = 0; var renderEstimate = function () { __render++; };",
        "var AbortController = function () { this.signal = {}; this.abort = function () {}; };",
        "var FormData = function () { this.append = function () {}; };",
        "var fetch = function () { return Promise.resolve({ok: true,"
        " json: function () { return Promise.resolve(%s); }}); };" % json.dumps(resposta),
        "var console = {warn: function () {}};",
        funcao_js("_estimatePriceNow", "dashboard.html", _SRC),
    ])


def _arqs_js(nomes):
    return "[%s]" % ", ".join("{name: %s, size: 10, lastModified: 1}" % json.dumps(n)
                              for n in nomes)


def test_a_tela_GUARDA_o_booleano_de_cada_arquivo():
    nomes = [_ARQ[0], _EST[0]]
    js = motor(_preludio_estimativa({
        "total_pranchas": 2, "price_brl": 97, "breakdown": [], "warnings": [],
        "nomes_estruturais": [False, True]}))
    r = rodar(js, "_estimatePriceNow(%s)" % _arqs_js(nomes))
    assert r.get("ok"), r
    assert js.evaljs("_nomeEstrutural.get(%s)" % json.dumps(_EST[0] + ":10:1")) is True
    assert js.evaljs("_nomeEstrutural.get(%s)" % json.dumps(_ARQ[0] + ":10:1")) is False


def test_CONTROLE_lista_de_tamanho_errado_nao_e_guardada():
    """Não casa por posição = não chuta qual é qual."""
    js = motor(_preludio_estimativa({
        "total_pranchas": 2, "price_brl": 97, "breakdown": [], "warnings": [],
        "nomes_estruturais": [True]}))
    rodar(js, "_estimatePriceNow(%s)" % _arqs_js([_ARQ[0], _EST[0]]))
    assert js.evaljs("_nomeEstrutural.size") == 0


def test_CONTROLE_servidor_antigo_sem_o_campo_nao_quebra_a_estimativa():
    js = motor(_preludio_estimativa({
        "total_pranchas": 1, "price_brl": 97, "breakdown": [], "warnings": []}))
    r = rodar(js, "_estimatePriceNow(%s)" % _arqs_js([_EST[0]]))
    assert r.get("ok"), r
    assert js.evaljs("__render") == 1, "a estimativa parou de desenhar o preço"
    assert js.evaljs("_nomeEstrutural.size") == 0


# ══════════════════════════════════════════════════════════════════════════
#  A ORDEM no envio
# ══════════════════════════════════════════════════════════════════════════
def test_a_pergunta_do_tipo_vem_ANTES_das_outras_no_envio():
    """🪤 Guarda de FONTE, só pra ordem: o tipo decide antes do formato e dos
    campos. A prova de comportamento são os testes de cima."""
    i_tipo = _SRC.index("await _confirmarTipoEstrutural()")
    i_pdf = _SRC.index("await _confirmarSoPdf()")
    i_prem = _SRC.index("await _confirmarPremissasVazias()")
    assert i_tipo < i_pdf < i_prem
    assert _SRC.count("await _confirmarTipoEstrutural()") == 1
