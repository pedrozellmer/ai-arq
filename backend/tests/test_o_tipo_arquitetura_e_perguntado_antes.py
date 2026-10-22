# -*- coding: utf-8 -*-
"""O ESPELHO: tipo Estrutura marcado com arquivos de ARQUITETURA é perguntado
ANTES do envio.

🩸 21/10/2026. Dois clientes no mesmo dia marcaram Estrutura com arquitetura
(25 DWG/DXF com o código ARQ, 23 PDF "…-Arq-EX-…"): 103 de 123 e 17 de 18
linhas sem quantidade, e um 👎. A pergunta de 07/10
(`test_o_tipo_estrutural_e_perguntado_antes`) só olhava o outro sentido.
📏 120 dias de projetos enviados como Estrutura: 6 projetos de 5 clientes com
a maioria dos nomes assim; nenhum estrutural de verdade com esse código.

🔑 Mesma forma do irmão: a régua mora no SERVIDOR (`_nome_parece_arquitetura`),
a estimativa devolve um booleano por arquivo e a tela só pergunta.
🚨 Os guardas CHAMAM o código: a rota pelo TestClient, a tela num motor JS.
🧪 Controles: tipo já Arquitetura não pergunta; minoria não pergunta; sem
resposta do servidor não pergunta; sem o toast não cai no confirm() nativo;
"Manter Estrutura" não troca nada; quem acabou de trocar pra Estrutura não é
perguntado de volta.
"""
import json
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

from _jsbancada import fonte_html, funcao_js, motor, rodar  # noqa: E402
import test_o_tipo_estrutural_e_perguntado_antes as _irmao  # noqa: E402

_SRC = fonte_html("dashboard.html")
NL = chr(10)

# nomes SINTÉTICOS no formato dos casos reais (nada de nome de cliente aqui)
_ARQ = ["XYZ-ARQ-F01-01-SUBSOLO-R11.dwg", "Planta-Baixa-Bloco-Arq-EX-F03-R01-a.pdf",
        "CASA TESTE - ARQ - PE - R00.dwg"]
_EST = ["100-EST-EX-0001-PIL-R00.dwg", "GALPAO - FUNDACOES FORMAS E ARMACAO.dwg"]
_NEUTRO = ["Lista_Acabamentos.pdf", "Memorial descritivo.pdf"]


# ══════════════════════════════════════════════════════════════════════════
#  A RÉGUA (servidor)
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("nome", _ARQ + [
    "0635-PQ01-ARQ-AP-103-TOA-TIP_R06 (1).pdf",
    "PROJETO ARQUITETONICO.pdf",
    "Arquitetura terreo.dwg",
    "arq.dwg",
])
def test_nome_de_arquitetura_e_reconhecido(nome):
    import main as _m
    assert _m._nome_parece_arquitetura(nome), nome


@pytest.mark.parametrize("nome", _EST + _NEUTRO + [
    "ARQUIVO 1.pdf",            # a palavra não é o código
    "MARQUISE.dwg",             # "arq" dentro de outra palavra
    "parq-01.dwg",
    "SEM ARQUITETURA.pdf",      # negada (a mesma negação do espelho)
    "ARQ-EST-PIL-01.dwg",       # tem cara dos DOIS: a dúvida não é desta régua
    "",
    None,
])
def test_CONTROLE_o_que_nao_e_nome_de_arquitetura(nome):
    import main as _m
    assert not _m._nome_parece_arquitetura(nome), nome


def test_a_estimativa_devolve_um_booleano_por_arquivo_NA_ORDEM(monkeypatch):
    nomes = [_EST[0], _ARQ[0], _NEUTRO[0], _ARQ[1]]
    d = _irmao._estima(monkeypatch, nomes)
    assert d.get("nomes_arquitetura") == [False, True, False, True], d
    # e o irmão segue igual na mesma resposta
    assert d.get("nomes_estruturais") == [True, False, False, False], d


def test_CONTROLE_so_reprecificar_sem_arquivo_devolve_lista_vazia(monkeypatch):
    cli = _irmao._cliente(monkeypatch)
    r = cli.post("/api/estimate-price", data={"known_pranchas": "4"})
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("nomes_arquitetura") == []


def test_o_evento_da_pergunta_e_aceito_pelo_track():
    import main as _m
    assert _m._track_evento_aceito("aviso-pre-envio:arquitetura")


# ══════════════════════════════════════════════════════════════════════════
#  A TELA: a pergunta, rodando de verdade
# ══════════════════════════════════════════════════════════════════════════
def _preludio(nomes, marcados, tipo="estrutura", com_toast=True, escolha=True,
              toast_quebra=False):
    lista = ", ".join("{name: %s, size: 10, lastModified: 1}" % json.dumps(n)
                      for n in nomes)
    partes = [
        "var selectedFiles = [%s];" % lista,
        "var _efKey = function (f) { return f.name + ':' + f.size + ':' + f.lastModified; };",
        "var _nomeArquitetura = new Map();",
    ]
    for n in marcados:
        partes.append("_nomeArquitetura.set(%s + ':10:1', true);" % json.dumps(n))
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
    partes += [funcao_js("_arquivosComCaraDeArquitetura", "dashboard.html", _SRC),
               funcao_js("_confirmarTipoArquitetura", "dashboard.html", _SRC)]
    return NL.join(partes)


def _resp(nomes, marcados, **kw):
    js = motor(_preludio(nomes, marcados, **kw))
    return js, rodar(js, "_confirmarTipoArquitetura()")


def test_todos_com_cara_de_arquitetura_PERGUNTA_e_troca_o_tipo():
    js, r = _resp(_ARQ, _ARQ)
    assert r.get("ok"), r
    assert r["valor"] == "trocou"
    assert js.evaljs("__sel.value") == "arquitetura", "a resposta não trocou o tipo"
    assert js.evaljs("__sel.dataset.escolhidoAMao") == "1"
    assert js.evaljs("__pd") == 1, "o texto do pé-direito não acompanhou o tipo"
    msg = js.evaljs("__msg")
    assert "Os 3 arquivos parecem de projeto de ARQUITETURA" in msg, msg
    assert _ARQ[0] in msg, msg
    assert "não mede paredes, piso, forro nem esquadrias" in msg, msg
    assert js.evaljs("__op.ok") == "Ler como Arquitetura"
    assert js.evaljs("__op.cancel") == "Manter Estrutura"


def test_o_placar_registra_a_ESCOLHA():
    js, _ = _resp(_ARQ, _ARQ)
    ev = js.evaljs("JSON.stringify(__ev)")
    assert json.loads(ev) == [["aviso-pre-envio:arquitetura",
                               {"type": "arquitetura", "n": 3, "tela": "envio"}]], ev


def test_MANTER_estrutura_nao_troca_nada_e_segue():
    js, r = _resp(_ARQ, _ARQ, escolha=False)
    assert r["valor"] == "seguir"
    assert js.evaljs("__sel.value") == "estrutura"
    assert js.evaljs("__sel.dataset.escolhidoAMao") is None
    assert json.loads(js.evaljs("JSON.stringify(__ev)"))[0][1]["type"] == "estrutura"


def test_maioria_com_memorial_e_lista_no_meio_tambem_pergunta():
    """O caso de 21/10: 21 pranchas Arq + memorial + lista de acabamentos."""
    nomes = ["P-%02d-Arq-EX-R01.pdf" % i for i in range(21)] + _NEUTRO
    marcados = nomes[:21]
    js, r = _resp(nomes, marcados)
    assert r["valor"] == "trocou"
    assert "21 dos 23 arquivos parecem" in js.evaljs("__msg")


def test_um_arquivo_so():
    js, r = _resp([_ARQ[0]], [_ARQ[0]])
    assert r["valor"] == "trocou"
    assert js.evaljs("__msg").startswith("O arquivo parece de projeto de ARQUITETURA")


def test_CONTROLE_tipo_ja_ARQUITETURA_nao_pergunta():
    js, r = _resp(_ARQ, _ARQ, tipo="arquitetura")
    assert r["valor"] == "seguir"
    assert js.evaljs("__msg") is None


def test_CONTROLE_MINORIA_de_arquitetura_nao_pergunta():
    """Uma planta de arquitetura no meio da estrutura é apoio, não engano de tipo."""
    nomes = [_ARQ[0]] + ["100-EST-EX-%04d-FOR-R00.dwg" % i for i in range(9)]
    js, r = _resp(nomes, [_ARQ[0]])
    assert r["valor"] == "seguir"
    assert js.evaljs("__msg") is None
    assert js.evaljs("__sel.value") == "estrutura"


def test_CONTROLE_sem_resposta_do_servidor_nao_opina():
    js, r = _resp(_ARQ, [])
    assert r["valor"] == "seguir"
    assert js.evaljs("__msg") is None


def test_CONTROLE_sem_o_toast_NAO_cai_no_confirm_nativo():
    js, r = _resp(_ARQ, _ARQ, com_toast=False)
    assert r["valor"] == "seguir"
    assert js.evaljs("__confirmou") == 0, "caiu no confirm() nativo (trava a aba)"
    assert js.evaljs("__sel.value") == "estrutura"


def test_CONTROLE_toast_que_QUEBRA_nao_trava_o_envio():
    js, r = _resp(_ARQ, _ARQ, toast_quebra=True)
    assert r.get("ok"), r
    assert r["valor"] == "seguir"
    assert js.evaljs("__sel.value") == "estrutura"


# ══════════════════════════════════════════════════════════════════════════
#  A TELA guarda o que o servidor respondeu
# ══════════════════════════════════════════════════════════════════════════
def _preludio_estimativa(resposta):
    return _irmao._preludio_estimativa(resposta).replace(
        "var _nomeEstrutural = new Map();",
        "var _nomeEstrutural = new Map(); var _nomeArquitetura = new Map();", 1)


def test_a_tela_GUARDA_o_booleano_de_cada_arquivo():
    nomes = [_EST[0], _ARQ[0]]
    js = motor(_preludio_estimativa({
        "total_pranchas": 2, "price_brl": 97, "breakdown": [], "warnings": [],
        "nomes_estruturais": [True, False], "nomes_arquitetura": [False, True]}))
    r = rodar(js, "_estimatePriceNow(%s)" % _irmao._arqs_js(nomes))
    assert r.get("ok"), r
    assert js.evaljs("_nomeArquitetura.get(%s)" % json.dumps(_ARQ[0] + ":10:1")) is True
    assert js.evaljs("_nomeArquitetura.get(%s)" % json.dumps(_EST[0] + ":10:1")) is False
    assert js.evaljs("_nomeEstrutural.get(%s)" % json.dumps(_EST[0] + ":10:1")) is True


def test_CONTROLE_lista_de_tamanho_errado_nao_e_guardada():
    js = motor(_preludio_estimativa({
        "total_pranchas": 2, "price_brl": 97, "breakdown": [], "warnings": [],
        "nomes_arquitetura": [True]}))
    rodar(js, "_estimatePriceNow(%s)" % _irmao._arqs_js([_EST[0], _ARQ[0]]))
    assert js.evaljs("_nomeArquitetura.size") == 0


def test_CONTROLE_servidor_antigo_sem_o_campo_nao_quebra_a_estimativa():
    js = motor(_preludio_estimativa({
        "total_pranchas": 1, "price_brl": 97, "breakdown": [], "warnings": []}))
    r = rodar(js, "_estimatePriceNow(%s)" % _irmao._arqs_js([_ARQ[0]]))
    assert r.get("ok"), r
    assert js.evaljs("__render") == 1, "a estimativa parou de desenhar o preço"
    assert js.evaljs("_nomeArquitetura.size") == 0


# ══════════════════════════════════════════════════════════════════════════
#  AS DUAS PERGUNTAS JUNTAS, no envio
# ══════════════════════════════════════════════════════════════════════════
def _duas(nomes, est, arq, tipo, escolha):
    """As duas funções de verdade e o trecho do envio que as chama."""
    pre = _preludio(nomes, arq, tipo=tipo, escolha=escolha)
    pre = pre.replace("var _nomeArquitetura = new Map();",
                      "var _nomeArquitetura = new Map(); var _nomeEstrutural = new Map();", 1)
    extra = [pre]
    for n in est:
        extra.append("_nomeEstrutural.set(%s + ':10:1', true);" % json.dumps(n))
    extra += [funcao_js("_arquivosComCaraDeEstrutura", "dashboard.html", _SRC),
              funcao_js("_confirmarTipoEstrutural", "dashboard.html", _SRC)]
    i = _SRC.rindex("if (", 0, _SRC.index("await _confirmarTipoEstrutural()"))
    j = _SRC.index("}", _SRC.index("await _confirmarTipoArquitetura();", i)) + 1
    extra.append("async function __envio() { "
                 + _SRC[i:j] + " return __sel.value; }")
    return motor(NL.join(extra))


def test_metade_de_cada_lado_quem_TROCOU_pra_estrutura_nao_e_perguntado_de_volta():
    """🪤 1 nome de estrutura + 1 de arquitetura: as duas maiorias valem. A
    pessoa aceitou Estrutura na 1ª pergunta — a 2ª não pode desfazer."""
    js = _duas([_EST[0], _ARQ[0]], [_EST[0]], [_ARQ[0]], tipo="arquitetura", escolha=True)
    r = rodar(js, "__envio()")
    assert r.get("ok"), r
    assert r["valor"] == "estrutura", "a 2ª pergunta desfez a escolha da 1ª"
    ev = json.loads(js.evaljs("JSON.stringify(__ev)"))
    assert [e[0] for e in ev] == ["aviso-pre-envio:estrutural"], ev


def test_estrutura_marcada_com_arquitetura_chega_na_pergunta_pelo_envio():
    js = _duas(_ARQ, [], _ARQ, tipo="estrutura", escolha=True)
    r = rodar(js, "__envio()")
    assert r.get("ok"), r
    assert r["valor"] == "arquitetura"
    ev = json.loads(js.evaljs("JSON.stringify(__ev)"))
    assert [e[0] for e in ev] == ["aviso-pre-envio:arquitetura"], ev
