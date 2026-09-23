# -*- coding: utf-8 -*-
"""O segundo envio na mesma página não pode mostrar o aviso do primeiro.

🩸 15/09/2026 — achado pela revisão adversarial da telemetria dos avisos (e
confirmado por um cético). A caixa `#aviso-aec` do dashboard é preenchida com
`innerHTML +=` e NADA a limpava: nem o `startProcessing`, nem "Novo projeto",
nem "Tentar de novo". Um segundo envio sem recarregar a página reabria a caixa
com os avisos — e os NOMES DE ARQUIVO — do envio anterior; se o novo também
tivesse aviso, ele entrava embaixo do velho. Medido no banco: 0 ocorrências até
15/09. Defeito de tela, não urgente, mas é dado do projeto errado na frente do
cliente.

O que este arquivo cobra, RODANDO a tela (nunca procurando palavra):
  · o `startProcessing` de verdade, até o instante em que a tela de
    processamento abre — a caixa tem que estar vazia e escondida NESSE momento;
  · dois envios seguidos, com o despacho real da resposta e o
    `mostrarAvisoAec` real: no segundo, só o aviso do segundo;
  · e um CONTROLE que roda a mesma cena sem a limpeza e exige que o aviso velho
    continue lá — prova de que o guarda enxerga o defeito.
"""
import io
import json
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)

from _navegador import (atributos, bloco_a_partir_de, montar,  # noqa: E402
                        rodar, sem_await)

_RAIZ = os.path.dirname(os.path.dirname(_AQUI))
_CHAMADA = "_limparAvisosDoEnvio();"
_PAROU = "__parou_na_tela_de_processamento"

_PRIMEIRO = {"job_id": "aa11bb22",
             "aviso_aec": {"titulo": "t-primeiro", "texto": "velho",
                           "arquivos": ["arquivo-do-primeiro.dwg"]}}
_SEGUNDO = {"job_id": "cc33dd44",
            "aviso_estrutural": {"titulo": "t-segundo", "texto": "novo",
                                 "arquivos": ["arquivo-do-segundo.pdf"]}}


def _site():
    return io.open(os.path.join(_RAIZ, "dashboard.html"), encoding="utf-8").read()


def _despacho(site):
    """O trecho REAL que recebe a resposta do upload e chama `mostrarAvisoAec`."""
    k = site.index("currentJobId = data.job_id;")
    i = site.rindex("const data = await res.json();", 0, k)
    fim = site.index("\n", site.index("if (data.aviso_area)", k))
    trecho = site[i:fim]
    # 🧪 controle do recorte: janela errada mediria outra coisa em silêncio.
    assert "aviso_estrutural" in trecho and len(trecho) < 3000, trecho[:200]
    return sem_await(trecho)


def _cena(respostas, sem_limpeza=False):
    """Envio 1 → `startProcessing` (até abrir a tela de processamento) → envio 2.

    O `showState` é trocado por um dublê que FOTOGRAFA a caixa e interrompe o
    `startProcessing` ali: o que vem depois é o upload por XHR, que não é o
    assunto deste guarda. Tudo antes dele roda como no navegador.
    """
    site = _site()
    caixa = atributos(site, "aviso-aec")
    assert caixa, "o id 'aviso-aec' sumiu do dashboard — o JS escreve nele"
    iniciar = sem_await(bloco_a_partir_de(site, "async function startProcessing(",
                                          "dashboard.html", fecho=""))
    if sem_limpeza:
        assert iniciar.count(_CHAMADA) == 1, (
            "o controle não achou a chamada da limpeza no startProcessing: %d"
            % iniciar.count(_CHAMADA))
        iniciar = iniciar.replace(_CHAMADA, "", 1)
    despacho = _despacho(site)
    js = [montar([{"id": "aviso-aec", "tag": caixa["tag"], "attrs": caixa["attrs"],
                   "html": ""}]),
          "_ligarTelemetria();",
          "var currentJobId = null, userCreditsCents = 0, DADOS = null, __naHora = null;",
          "var params = { project_type: 'arquitetura' };",
          "var res = { json: function () { return DADOS; } };",
          "var stateProcessing = { id: 'state-processing' };",
          "function requestNotificationPermission() {}",
          "var sbClient = { auth: { getSession: function () {"
          " return { data: { session: null } }; } } };",
          "function showState(s) {"
          " var b = document.getElementById('aviso-aec');"
          " __naHora = { html: b.innerHTML, escondida: b.classList.contains('hidden') };"
          " throw new Error('%s'); }" % _PAROU,
          bloco_a_partir_de(site, "function mostrarAvisoAec(", "dashboard.html", fecho=""),
          bloco_a_partir_de(site, "function _limparAvisosDoEnvio(", "dashboard.html", fecho=""),
          # 🪤 22/09: dependências novas do `startProcessing` (a janela do
          # pé-direito). Sem elas o JS real para em ReferenceError.
          bloco_a_partir_de(site, "function _premissasEmBranco(", "dashboard.html", fecho=""),
          bloco_a_partir_de(site, "function _confirmarPremissasVazias(", "dashboard.html", fecho=""),
          # 🪤 `_soPdfNoEnvio` lê `selectedFiles`, que nesta cena não existe:
          # o assunto aqui é a CAIXA de avisos, não o envio. Lista vazia =
          # o aviso de só-PDF não abre, e o `startProcessing` segue reto.
          "var selectedFiles = [];",
          "var _ehPdf = function (f) { return /[.]pdf$/i.test((f && f.name) || ''); };",
          bloco_a_partir_de(site, "function _soPdfNoEnvio(", "dashboard.html", fecho=""),
          bloco_a_partir_de(site, "function _confirmarSoPdf(", "dashboard.html", fecho=""),
          "function startProcessing__real() {}",
          iniciar,
          "function _enviar(dados) { DADOS = dados; (function () { %s })(); }" % despacho]
    for n, dados in enumerate(respostas):
        if n > 0:
            js.append("try { startProcessing(); } catch (e) {"
                      " if (String(e && e.message) !== '%s') throw e; }" % _PAROU)
        js.append("_enviar(%s);" % json.dumps(dados, ensure_ascii=False))
    return rodar(js, "({html: document.getElementById('aviso-aec').innerHTML,"
                     " visivel: _visivel('aviso-aec'), naHora: __naHora,"
                     " ev: __eventos})")


def test_o_segundo_envio_so_mostra_o_aviso_do_segundo():
    r = _cena([_PRIMEIRO, _SEGUNDO])
    assert "t-segundo" in r["html"] and "arquivo-do-segundo.pdf" in r["html"], (
        "o aviso do segundo envio não foi desenhado: %r" % r["html"][:300])
    assert "t-primeiro" not in r["html"], (
        "a caixa ainda mostra o aviso do envio ANTERIOR: %r" % r["html"][:300])
    assert "arquivo-do-primeiro.dwg" not in r["html"], (
        "o nome do arquivo do envio anterior continua na tela")
    assert r["visivel"], "o aviso do segundo envio não ficou visível"


def test_a_caixa_esta_VAZIA_e_ESCONDIDA_quando_a_tela_de_processamento_abre():
    """🔑 A limpeza tem que acontecer ANTES de a tela abrir — se vier depois,
    o cliente vê o aviso velho enquanto o arquivo sobe."""
    r = _cena([_PRIMEIRO, {"job_id": "cc33dd44"}])
    assert r["naHora"] is not None, (
        "o startProcessing não chegou a abrir a tela de processamento — a cena "
        "não mediu nada")
    assert r["naHora"]["html"] == "", (
        "a tela de processamento abriu com o aviso velho: %r" % r["naHora"]["html"][:200])
    assert r["naHora"]["escondida"], "a caixa vazia abriu visível"


def test_segundo_envio_SEM_aviso_deixa_a_caixa_vazia_e_fora_da_tela():
    r = _cena([_PRIMEIRO, {"job_id": "cc33dd44"}])
    assert r["html"] == "", r["html"][:300]
    assert not r["visivel"], "a caixa vazia ficou visível no segundo envio"


def test_a_telemetria_conta_so_o_aviso_de_cada_envio():
    """O evento de exibição continua um por envio (ver
    test_o_aviso_do_tipo_deixa_rastro): limpar a caixa não pode fazer o aviso
    novo sumir nem o velho ser contado de novo."""
    r = _cena([_PRIMEIRO, _SEGUNDO])
    nomes = [e[0] for e in r["ev"] if e[0].startswith("aviso-envio:")]
    assert nomes == ["aviso-envio:aec", "aviso-envio:estrutural"], nomes


def test_CONTROLE_sem_a_limpeza_o_aviso_velho_FICA_na_tela():
    """O guarda acima só vale se souber acusar. Aqui a MESMA cena roda com a
    chamada da limpeza tirada do `startProcessing` — e o defeito original tem
    que aparecer."""
    r = _cena([_PRIMEIRO, _SEGUNDO], sem_limpeza=True)
    assert "t-primeiro" in r["html"] and "t-segundo" in r["html"], (
        "sem a limpeza a cena devia mostrar os DOIS avisos empilhados — se não "
        "mostra, o guarda perdeu a capacidade de ver o defeito: %r" % r["html"][:300])
    assert r["naHora"]["html"] != "", "sem a limpeza a caixa não devia estar vazia"
