# -*- coding: utf-8 -*-
"""A TELA do merge, executada — não lida.

🪤 O guarda antigo (`test_o_teto_de_tempo_da_tela_e_explicito`, em
test_merge_email_cliente.py) procurava a string `timeoutMs: 180000` numa janela
de 300 caracteres depois de `/api/admin/merge-preview/` no admin.html. Texto
presente não é comportamento: o `authFetch` podia ignorar o pedido e cortar em
45 s de novo com a string intacta no arquivo.

Aqui o JS roda de verdade (duktape, via `_bancada_js.Pagina`): a tela PEDE o
teto e o `authFetch` REAL arma o corte com o número pedido.
"""
import json
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)

from _bancada_js import Pagina  # noqa: E402

# O que a rota /merge-preview devolve — o suficiente pra tela montar.
_RESPOSTA = {
    "resumo": "2 pranchas disputadas",
    "pranchas": [{"stem": "4366-EL-E", "vencedora": "A", "porque": "mediu mais"}],
}

# O que a rota /merge-criar devolve — o botão que de fato CRIA o projeto
# combinado e chama a IA uma vez por prancha disputada. É o mais demorado dos
# dois, e era o que estava sem guarda nenhum.
_RESPOSTA_CRIAR = {
    "job_id": "mg12ab34", "itens": 412, "medidos": 288,
    "original": {"medidos": 251}, "releitura": {"medidos": 205},
    "do_pai": ["4366-EL-E"], "do_filho": ["4366-AR-A"],
    "sobreposicoes": 2, "proximo_passo": "confira e decida se libera",
}

_FETCH_OK = """
window.__pedidos = [];
window.authFetch = function (url, opts) {
  opts = opts || {};
  window.__pedidos.push({ url: String(url), timeoutMs: opts.timeoutMs || 0,
                          method: opts.method || 'GET' });
  return Promise.resolve({
    ok: true, status: 200,
    json: function () { return Promise.resolve(window.__RESP || {}); }
  });
};
window.__RESP = %s;
1;
"""


def _com(resposta):
    """O prelúdio com o authFetch de mentira que ANOTA o que foi pedido."""
    return _FETCH_OK % json.dumps(resposta)


def _estudo(resposta):
    """A página do admin carregada e pronta pra rodar `mergeEstudar`.

    🪤 O `authFetch` de mentira entra DEPOIS dos arquivos: o aiarq-utils.js
    define o real e sobrescreveria um que entrasse antes — foi assim que a 1ª
    versão desta bancada mediu o `fetch` real e viu `__pedidos` vazio.
    """
    p = Pagina(("aiarq-utils.js", "admin.html"))
    p.eval(_com(resposta))
    return p


# Os DOIS botões do merge. Nenhum dos dois casa a regex de "rotas lentas" do
# authFetch, então os dois dependem do teto explícito — e o de CRIAR é o mais
# demorado (chama a IA uma vez por prancha disputada, depois monta o projeto).
_BOTOES = [
    ("mergeEstudar", "mergeEstudar('ev597afa'); 1", "/merge-preview/", "GET",
     _RESPOSTA),
    ("mergeCriar", "mergeCriar('ev597afa'); 1", "/merge-criar/", "POST",
     _RESPOSTA_CRIAR),
]


@pytest.mark.parametrize("_nome,js,rota,metodo,resposta", _BOTOES,
                         ids=[b[0] for b in _BOTOES])
def test_o_teto_de_tempo_da_tela_e_explicito(_nome, js, rota, metodo, resposta):
    """A tela PEDE 180 s — nos DOIS botões.

    🚨 As rotas do merge não casam a regex de "rotas lentas" do authFetch. Se o
    pedido explícito sumir, o corte volta pros 45 s de sempre — e a juíza
    sozinha já leva ~21 s.

    🪤 06/09: a conversão pra execução cobria só o `mergeEstudar` e deixou o
    `mergeCriar` — o botão que de fato cria o projeto combinado — sem guarda
    nenhum, enquanto o guarda velho, de texto, cobria os dois. Era uma
    REGRESSÃO de cobertura escondida dentro de uma melhoria.
    """
    p = _estudo(resposta)
    p.chama(js)
    pedidos = json.loads(p.eval("JSON.stringify(window.__pedidos)"))
    alvo = [x for x in pedidos if rota in x["url"]]
    assert alvo, "%s não chamou %s: %s" % (_nome, rota, pedidos)
    assert alvo[0]["timeoutMs"] == 180000, (
        "%s pediu %s ms — o authFetch corta em 45 s quem não pede"
        % (_nome, alvo[0]["timeoutMs"]))
    assert alvo[0]["method"] == metodo, (
        "%s chamou %s com método %r" % (_nome, rota, alvo[0]["method"]))


@pytest.mark.parametrize("rota", ["/api/admin/merge-preview/ev1",
                                  "/api/admin/merge-criar/ev1"])
def test_o_authFetch_OBEDECE_o_teto_pedido_e_nao_arma_outro(rota):
    """O authFetch DE VERDADE arma UM corte, e é o que foi pedido.

    🪤 06/09: a versão anterior perguntava `180000 in prazos`. Com isso, um
    corte extra mais curto convivendo com o pedido passava verde: o pedido de
    180 s ficava escrito no arquivo e a requisição morria aos 45 s do mesmo
    jeito. Agora se cobra a lista INTEIRA de prazos armados.
    """
    p2 = Pagina(("aiarq-utils.js",))
    p2.eval("fetch = function(){ return new Promise(function(){}); };1")
    p2.limpa_eventos()
    p2.chama("window.authFetch('https://x%s', {timeoutMs: 180000}); 1" % rota)
    prazos = [e["ms"] for e in p2.eventos() if e["tipo"] == "setTimeout"]
    assert prazos == [180000], (
        "o authFetch armou %s pra %s — era pra ser um corte só, de 180 s. "
        "Qualquer prazo mais curto aí dentro mata a requisição antes, com o "
        "pedido de 180 s intacto no código." % (prazos, rota))
