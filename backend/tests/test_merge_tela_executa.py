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

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)

from _bancada_js import Pagina  # noqa: E402

# O que a rota /merge-preview devolve — o suficiente pra tela montar.
_RESPOSTA = {
    "resumo": "2 pranchas disputadas",
    "pranchas": [{"stem": "4366-EL-E", "vencedora": "A", "porque": "mediu mais"}],
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


def test_o_teto_de_tempo_da_tela_e_explicito():
    """Dois pedaços, um teste: a tela PEDE 180 s e o authFetch OBEDECE.

    🚨 A rota do estudo não casa a regex de "rotas lentas" do authFetch. Se o
    pedido explícito for ignorado, o corte volta pros 45 s de sempre — e a
    juíza sozinha já leva ~21 s."""
    p = _estudo(_RESPOSTA)
    p.chama("mergeEstudar('ev597afa'); 1")
    pedidos = json.loads(p.eval("JSON.stringify(window.__pedidos)"))
    alvo = [x for x in pedidos if "/merge-preview/" in x["url"]]
    assert alvo, "o estudo não chamou /merge-preview: %s" % pedidos
    assert alvo[0]["timeoutMs"] == 180000, (
        "a tela pediu %s ms pro estudo — o authFetch corta em 45 s quem não "
        "pede" % alvo[0]["timeoutMs"])

    # …e o authFetch DE VERDADE tem que respeitar o que foi pedido.
    p2 = Pagina(("aiarq-utils.js",))
    p2.eval("fetch = function(){ return new Promise(function(){}); };1")
    p2.limpa_eventos()
    p2.chama("window.authFetch('https://x/api/admin/merge-preview/ev1', "
             "{timeoutMs: 180000}); 1")
    prazos = [e["ms"] for e in p2.eventos() if e["tipo"] == "setTimeout"]
    assert 180000 in prazos, (
        "o authFetch ignorou o timeoutMs pedido e armou o corte em %s — a "
        "rota do estudo volta a morrer aos 45 s" % prazos)
