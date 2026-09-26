"""26/09/2026 — Pedro: "trocar de página está devagar".

Medido: cada chamada à API leva 0,5–0,85 s e as telas do projeto pedem os MESMOS dados uma atrás da
outra (os logs do Render mostravam /api/items 2× por abertura). O aiarq-utils.js guarda a leitura na aba
por 30 s (aiarqCache) e o menu adianta os dados ao apontar.

O que NÃO pode acontecer, e é isto que se cobra aqui:
  • guardar rota com efeito colateral (o ?marcar=1 da revisão marca o projeto como visto);
  • guardar escrita (POST/PUT/DELETE);
  • mostrar dado de ANTES de uma mudança: toda escrita, por qualquer caminho, apaga o guardado, e a
    leitura que atravessou uma escrita não é guardada.
"""
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..")


def _ler(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


UTILS = _ler("aiarq-utils.js")


def _regex_da_lista():
    m = re.search(r"var _CACHE_PFX = .*?_CACHE_OK = /(.*?)/;", UTILS, re.S)
    assert m, "a lista de rotas do cache sumiu"
    return re.compile(m.group(1).replace("\\/", "/"))


API = "https://api.ai.arq.br/api/"


def test_a_lista_aceita_as_leituras_do_projeto():
    ok = _regex_da_lista()
    for rota in ("items/abc123", "items/abc123/review-state", "cronograma/abc123", "cronograma/abc123/full",
                 "memorial/abc123/estrutura", "projects/abc123/quotes", "projeto/abc123/coerencia",
                 "meus-entregaveis", "projects/by-user/11111111-2222-3333-4444-555555555555"):
        assert ok.search(API + rota), rota


def test_a_lista_recusa_efeito_colateral_e_escrita():
    ok = _regex_da_lista()
    for rota in ("items/abc123/review-state?marcar=1",    # marca o projeto como visto
                 "memorial/abc123/estrutura?fresco=1",      # pede pra refazer
                 "items/abc123/review/xyz",                 # grava revisão
                 "items/abc123/finalize", "items/abc123/review-finalize", "items/abc123/faltou",
                 "project/abc123/reprocess", "status/abc123", "projeto/abc123/acesso",
                 "projeto/abc123/chat", "cronograma/abc123/pdf"):
        assert not ok.search(API + rota), rota


def test_so_get_entra():
    i = UTILS.index("cabe: function (url, metodo) {")
    corpo = UTILS[i:UTILS.index("},", i)]
    assert "String(metodo).toUpperCase() === 'GET'" in corpo


def test_toda_escrita_por_qualquer_caminho_apaga_o_guardado():
    i = UTILS.index("var _fetchOrig = window.fetch.bind(window);")
    corpo = UTILS[i:UTILS.index("} catch (e) {}", i)]
    assert "=== 'GET'" in corpo and "=== 'HEAD'" in corpo
    # apaga ANTES de mandar e DEPOIS da resposta (deu certo ou não)
    assert corpo.count("window.aiarqCache.limpar();") == 3


def test_leitura_que_atravessou_uma_escrita_nao_e_guardada():
    bloco = UTILS[UTILS.index("window.aiarqCache = {"):]
    assert "_cacheGeracao++;" in bloco[bloco.index("limpar: function () {"):][:120]
    i = UTILS.index("window.authFetch = async function (url, options) {")
    af = UTILS[i:UTILS.index("\n  };\n", i)]
    assert "var _g0 = window.aiarqCache.geracao();" in af
    # 26/09: o texto é lido pra quem espera a mesma leitura, mas só é GUARDADO se não houve escrita no meio
    assert "if (window.aiarqCache.geracao() === _g0) window.aiarqCache.guardar(url, _uid, _txt);" in af
    pj = _ler("projeto.html")
    j = pj.index("const lerComCache = async (url, headers, teto) => {")
    lc = pj[j:pj.index("\n  };\n", j)]
    assert "C.geracao() === g0" in lc and "C.guardar(url, uid, texto)" in lc


def test_a_chave_leva_o_id_da_pessoa():
    assert "return _CACHE_PFX + (uid || '') + '|' + String(url);" in UTILS


def test_o_menu_so_adianta_leituras_da_lista():
    menu = _ler("menu-lateral.js")
    i = menu.index("function adiantarDados(pagina) {")
    corpo = menu[i:menu.index("\n  }\n", i)]
    ok = _regex_da_lista()
    urls = [(a.replace("/api/", "", 1), b) for a, b in
            re.findall(r"window\.authFetch\(b \+ '([^']+)' \+ j(?: \+ '([^']*)')?\)", corpo)]
    assert urls, "o menu não adianta mais nada?"
    for base, resto in urls:
        assert ok.search(API + base + "abc123" + (resto or "")), base + (resto or "")
    assert "marcar" not in corpo

def _regex_so_registro():
    m = re.search(r"var _SO_REGISTRO = /(.*?)/;", UTILS)
    assert m, "a lista de envios que só registram sumiu"
    return re.compile(m.group(1).replace("\\/", "/"))


def test_telemetria_nao_apaga_o_cache_mas_escrita_de_verdade_apaga():
    # 🩸 26/09 (auditoria): o /api/track dispara em quase toda página e apagava o cache ao abrir
    so = _regex_so_registro()
    for u in ("https://api.ai.arq.br/api/track", "https://api.ai.arq.br/api/notify/welcome",
              "https://api.ai.arq.br/api/nps", "https://x.supabase.co/auth/v1/token?grant_type=refresh_token"):
        assert so.search(u), u
    for u in ("https://api.ai.arq.br/api/items/abc/review/it1", "https://api.ai.arq.br/api/items/abc/finalize",
              "https://api.ai.arq.br/api/project/abc/reprocess", "https://api.ai.arq.br/api/cronograma/abc",
              "https://x.supabase.co/rest/v1/escritorio_tarefas", "https://api.ai.arq.br/api/tracker-novo"):
        assert not so.search(u), u
    i = UTILS.index("var _fetchOrig = window.fetch.bind(window);")
    corpo = UTILS[i:UTILS.index("} catch (e) {}", i)]
    assert corpo.index("_SO_REGISTRO.test(") < corpo.index("window.aiarqCache.limpar();")


def test_a_mesma_leitura_ao_mesmo_tempo_vai_uma_vez_so():
    i = UTILS.index("window.authFetch = async function (url, options) {")
    af = UTILS[i:UTILS.index("\n  };\n", i)]
    assert "_emVoo[_chaveVoo].g === _g0" in af, "só espera leitura da mesma geração"
    assert "_deOutro !== null && window.aiarqCache.geracao() === _g0" in af, "escrita no meio: busca a sua"
    assert "if (_emVoo[_chaveVoo] === _meuVoo) delete _emVoo[_chaveVoo];" in af, "não apaga o registro de outra leitura"
    # quem esperava SEMPRE é liberado (no finally, deu certo ou não)
    fin = af[af.index("} finally {"):]
    assert "_resolveVoo(_txtVoo);" in fin


# controle positivo (26/09): pôr "|items\/[^/?#]+\/review-state\?marcar=1" na lista reprovou
# test_a_lista_recusa_efeito_colateral_e_escrita; tirar o "_cacheGeracao++;" reprovou o da travessia.
