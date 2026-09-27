# -*- coding: utf-8 -*-
"""Aprovar vários posts de uma vez (Instagram e LinkedIn) — rodando o JavaScript REAL do admin.

27/09/2026 — Pedro, depois de aprovar os 4 do LinkedIn um por um (4 cliques, 4 confirmações):
"deixa opção no admin, tanto linkedin quanto instagram, pra aprovar vários ao mesmo tempo".

O que não pode acontecer, e este guarda cobra executando o código (dukpy), não lendo o fonte:
- uma falha no meio PARAR a leva e deixar o resto sem aprovar, calado;
- a tela dizer "aprovados" sem dizer quais NÃO foram e por quê;
- entrar na seleção o que o botão individual não deixaria aprovar (IG sem mídia, LinkedIn sem
  imagem/texto, ou post que já saiu do rascunho) — seleção velha vazando pra lista recarregada;
- clique duplo disparar duas levas;
- IG e LinkedIn trocarem de rota ou de status (IG aprova com 'pending', LinkedIn com 'approved').
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _jsbancada import funcao_js, motor, rodar  # noqa: E402

_ADMIN = "admin.html"
_FUNCOES = ("igHasMedia", "podeAprovarJunto", "selIds", "caixaSelecao", "aprovarVarios",
            "resumoAprovacao", "_mudarStatusPost", "aprovarSelecionados", "_confirmaOuAvisa")

_PRELUDIO = r"""
var window = this;
var API_BASE = 'https://api.exemplo.local';
var SEL_APROVAR = { ig: {}, li: {} };
var _aprovandoVarios = false;
var IG_POSTS = [], LI_POSTS = [];
var __chamadas = [], __alertas = [], __recargas = [], __avisos = [], __confirmar = true, __falhar = {};
function _adminToast(msg){ __avisos.push(String(msg)); }
function igEsc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function confirm(){ return __confirmar; }
function alert(t){ __alertas.push(String(t)); }
function loadInstagramPosts(){ __recargas.push('ig'); }
function loadLinkedinPosts(){ __recargas.push('li'); }
var document = { getElementById: function(){ return null; } };
function authFetch(url, opts){
  var corpo = JSON.parse(opts.body);
  __chamadas.push({ url: url, id: corpo.id, status: corpo.status });
  var erro = __falhar[corpo.id];
  return Promise.resolve({
    ok: !erro, status: erro ? 400 : 200,
    json: function(){ return Promise.resolve(erro ? { detail: erro } : { status: 'ok' }); }
  });
}
true;
"""


def _js():
    js = motor(_PRELUDIO)
    for nome in _FUNCOES:
        js.evaljs(funcao_js(nome, _ADMIN))
    return js


def _ig(id_, status="pending_approval", imagem="https://x/a.png"):
    return {"id": id_, "slot_key": "feed_" + id_, "status": status, "media_type": "feed", "image_url": imagem}


def _li(id_, status="pending_approval", imagem="https://x/a.jpg", texto="Post."):
    return {"id": id_, "slot_key": "li_" + id_, "status": status, "image_url": imagem, "texto": texto}


# ── o laço ─────────────────────────────────────────────────────────────────────

def test_uma_falha_no_meio_NAO_para_a_leva():
    js = _js()
    js.evaljs("var __vistos = []; true;")
    r = rodar(js, "aprovarVarios(['a','b','c'], function(id){ __vistos.push(id); "
                  "if (id === 'b') return Promise.reject(new Error('sem imagem')); return Promise.resolve(); })")
    assert "erro" not in r, r
    v = r["valor"]
    assert js.evaljs("__vistos") == ["a", "b", "c"], "a leva parou na falha (ou mudou a ordem)"
    assert v["ok"] == ["a", "c"], v
    assert v["falhou"] == [{"id": "b", "erro": "sem imagem"}], v


def test_o_resumo_diz_quantos_foram_e_QUAIS_nao_foram_e_por_que():
    js = _js()
    t = js.evaljs("resumoAprovacao({ok:['1','2'], falhou:[{id:'3', erro:'sem imagem'}]}, "
                  "function(id){ return 'feed_' + id; })")
    assert "2 posts aprovados" in t, t
    assert "1 não foi" in t and "feed_3" in t and "sem imagem" in t, t
    so_um = js.evaljs("resumoAprovacao({ok:['1'], falhou:[]})")
    assert "1 post aprovado" in so_um and "não foi" not in so_um, so_um


# ── quem entra na seleção ──────────────────────────────────────────────────────

def test_so_entra_o_que_o_botao_individual_deixaria_aprovar():
    js = _js()
    casos = [
        ("ig", _ig("1"), True),
        ("ig", _ig("2", status="pending"), False),            # já aprovado
        ("ig", _ig("3", imagem=""), False),                    # sem mídia
        ("li", _li("4"), True),
        ("li", _li("5", imagem=None), False),                  # sem imagem
        ("li", _li("6", texto="   "), False),                  # sem texto
        ("li", _li("7", status="scheduled"), False),           # já está no LinkedIn
    ]
    for tipo, post, esperado in casos:
        assert js.evaljs("podeAprovarJunto(%s, %s)" % (json.dumps(tipo), json.dumps(post))) is esperado, (tipo, post)
        caixa = js.evaljs("caixaSelecao(%s, %s)" % (json.dumps(tipo), json.dumps(post)))
        assert (('type="checkbox"' in caixa) is esperado), (tipo, post, caixa)


def test_selecao_velha_nao_vaza_pra_lista_recarregada():
    """Marcou, e o post saiu do rascunho (aprovado noutra aba / sem imagem): não vai na leva."""
    js = _js()
    js.evaljs("IG_POSTS = %s; SEL_APROVAR.ig = {'1': true, '2': true, '9': true}; true;"
              % json.dumps([_ig("1"), _ig("2", status="pending")]))
    assert js.evaljs("selIds('ig')") == ["1"]


def test_a_caixa_escapa_o_id():
    js = _js()
    caixa = js.evaljs("caixaSelecao('ig', %s)" % json.dumps(_ig("x\"><img src=y>")))
    assert "<img" not in caixa, caixa


# ── a leva inteira, pela rota de cada rede ─────────────────────────────────────

def test_instagram_aprova_pela_rota_do_ig_com_pending_e_segue_depois_da_falha():
    js = _js()
    js.evaljs("IG_POSTS = %s; SEL_APROVAR.ig = {'1': true, '2': true, '3': true}; __falhar = {'2': 'Esse post ainda não tem imagem'}; true;"
              % json.dumps([_ig("1"), _ig("2"), _ig("3")]))
    r = rodar(js, "aprovarSelecionados('ig')")
    assert "erro" not in r, r
    chamadas = js.evaljs("__chamadas")
    assert [c["id"] for c in chamadas] == ["1", "2", "3"], chamadas
    assert all(c["url"].endswith("/api/admin/instagram/posts/status") and c["status"] == "pending" for c in chamadas), chamadas
    alerta = js.evaljs("__alertas")[0]
    assert "2 posts aprovados" in alerta and "feed_2" in alerta and "não tem imagem" in alerta, alerta
    assert js.evaljs("__recargas") == ["ig"], "a lista não recarregou depois da leva"
    assert js.evaljs("selIds('ig')") == [], "a seleção ficou marcada depois de aprovar"


def test_linkedin_aprova_pela_rota_do_linkedin_com_approved():
    js = _js()
    js.evaljs("LI_POSTS = %s; SEL_APROVAR.li = {'4': true, '5': true}; true;" % json.dumps([_li("4"), _li("5")]))
    rodar(js, "aprovarSelecionados('li')")
    chamadas = js.evaljs("__chamadas")
    assert [c["id"] for c in chamadas] == ["4", "5"], chamadas
    assert all(c["url"].endswith("/api/admin/linkedin/posts/status") and c["status"] == "approved" for c in chamadas), chamadas
    assert js.evaljs("__recargas") == ["li"]


def test_cancelar_a_confirmacao_nao_aprova_nada_e_DIZ_que_nada_foi_feito():
    """Pela regra do painel (test_recusa_no_admin_nao_some_calada): o "não" não some calado."""
    js = _js()
    js.evaljs("IG_POSTS = %s; SEL_APROVAR.ig = {'1': true}; __confirmar = false; true;" % json.dumps([_ig("1")]))
    rodar(js, "aprovarSelecionados('ig')")
    assert js.evaljs("__chamadas") == [] and js.evaljs("__alertas") == []
    assert any("nada foi feito" in a.lower() for a in js.evaljs("__avisos")), js.evaljs("__avisos")


def test_clique_duplo_nao_dispara_duas_levas():
    js = _js()
    js.evaljs("IG_POSTS = %s; SEL_APROVAR.ig = {'1': true, '2': true}; true;" % json.dumps([_ig("1"), _ig("2")]))
    rodar(js, "Promise.all([aprovarSelecionados('ig'), aprovarSelecionados('ig')])")
    ids = [c["id"] for c in js.evaljs("__chamadas")]
    assert ids == ["1", "2"], "clique duplo aprovou em dobro: %r" % ids
