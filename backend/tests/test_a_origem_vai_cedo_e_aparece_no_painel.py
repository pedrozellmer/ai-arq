# -*- coding: utf-8 -*-
"""A origem vai pra conta cedo — e aparece no painel.

🩸 27/09/2026 — auditoria de telemetria, item 5. De 30/08 a 27/09:
  · 96 contas, 84 fichas — as 84 com `src` na conta; as 12 que pararam ANTES da
    ficha, todas sem origem: o `updateUser` só rodava no submit da ficha;
  · nenhuma tela mostrava o `src` (a lista do admin nem devolvia);
  · das 28 que DECLARARAM IA, só 6 chegaram com marca de IA no link e 17 pelo
    www.google.com — o declarado é a fonte do canal de IA; o técnico, do caminho.

🔑 A régua que monta a origem mora em aiarq-utils.js (cadastro e login usam a
mesma). O cadastro grava assim que vê a sessão e sabe que falta a ficha (sem
sobrescrever o 1º toque); o cadastro por e-mail manda no `signUp`. O painel
ganha "declarou × chegou por" e a ficha, "Chegou por". A lista do admin passou a
devolver os campos (migração ensaiada: 191 linhas antes e depois, as mesmas
permissões).
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _jsbancada import _do_marcador_ate_fechar, fonte_html, funcao_js, motor, rodar  # noqa: E402

_BACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MIG = os.path.join(_BACK, "migrations_pendentes", "admin_list_all_signups_com_origem.sql")
_TOQUE = {"label": "google", "ref": "www.google.com", "utm_campaign": "",
          "landing": "/blog/posts/x.html"}
_ESPERADO = {"src": "google", "src_ref": "www.google.com", "src_campaign": "",
             "src_landing": "/blog/posts/x.html"}


def _ler(js, expr):
    return json.loads(js.evaljs("JSON.stringify(%s)" % expr))


# ══════════════════════════════════════════════════════════════════════════
#  1. A régua única e a gravação cedo (cadastro.html)
# ══════════════════════════════════════════════════════════════════════════
def _cadastro(chamadas_var="__ch"):
    js = motor()
    js.evaljs(funcao_js("origemParaConta", "aiarq-utils.js"))
    js.evaljs("var %s = []; var window = { aiArqOrigemParaConta: origemParaConta };"
              "var sbClient = { auth: { updateUser: function (o) { %s.push(o);"
              " return Promise.resolve({ data: {}, error: null }); } } };" % (chamadas_var, chamadas_var))
    for f in ("_origemParaConta", "_origemQueFalta", "_gravarOrigemCedo"):
        js.evaljs(funcao_js(f, "cadastro.html"))
    return js


def test_a_conta_sem_origem_ganha_a_origem_JA():
    js = _cadastro()
    js.evaljs("window.aiArqSource = function () { return %s; }; null;" % json.dumps(_TOQUE))
    rodar(js, "(function(){ _gravarOrigemCedo({ full_name: 'x' }); return 1; })()")
    assert _ler(js, "__ch") == [{"data": _ESPERADO}]


def test_a_conta_que_JA_tem_origem_nao_e_sobrescrita():
    """1º toque não se sobrescreve: quem voltou por outro caminho continua com a
    origem de quando chegou."""
    js = _cadastro()
    js.evaljs("window.aiArqSource = function () { return %s; }; null;" % json.dumps(_TOQUE))
    rodar(js, "(function(){ _gravarOrigemCedo({ src: 'instagram' }); return 1; })()")
    assert _ler(js, "__ch") == []


def test_sem_primeiro_toque_nao_chama_nada():
    js = _cadastro()
    js.evaljs("window.aiArqSource = function () { return null; }; null;")
    rodar(js, "(function(){ _gravarOrigemCedo({}); return 1; })()")
    assert _ler(js, "__ch") == []


def test_a_gravacao_cedo_esta_ANTES_do_formulario_e_depois_da_checagem_de_ficha():
    """Ela tem que rodar quando a página já sabe que falta a ficha — antes do
    formulário aparecer (quem para ali é justamente quem ficava sem origem)."""
    src = fonte_html("cadastro.html")
    i_auth = src.index("async function checkAuth()")
    corpo = _do_marcador_ate_fechar(src, i_auth, "checkAuth")
    i_ficha = corpo.index("if (profile) {")
    i_cedo = corpo.index("_gravarOrigemCedo(meta);")
    i_form = corpo.index("if (_convite) {")
    assert i_ficha < i_cedo < i_form, "a gravação cedo saiu do lugar"


def test_CONTROLE_o_cadastro_nao_tem_mais_a_propria_copia_da_regua():
    corpo = funcao_js("_origemParaConta", "cadastro.html")
    assert "aiArqOrigemParaConta" in corpo and "src_landing" not in corpo, (
        "voltou a ter a própria cópia da régua — duas cópias divergem um dia")


# ══════════════════════════════════════════════════════════════════════════
#  2. O cadastro por e-mail (login.html)
# ══════════════════════════════════════════════════════════════════════════
def _signup(toque):
    src = fonte_html("login.html")
    i = src.index("const _origem = window.aiArqOrigemParaConta")
    j = src.index("{ email, password });", i) + len("{ email, password });")
    trecho = src[i:j]
    js = motor()
    js.evaljs(funcao_js("origemParaConta", "aiarq-utils.js"))
    js.evaljs("var __args = []; var email = 'a@b.c', password = 'x';"
              "var window = { aiArqOrigemParaConta: origemParaConta,"
              " aiArqSource: function () { return %s; } };"
              "var sbClient = { auth: { signUp: function (o) { __args.push(o);"
              " return Promise.resolve({ data: {}, error: null }); } } };"
              "async function __cria() { %s return 1; }" % (json.dumps(toque), trecho))
    r = rodar(js, "__cria()")
    assert "erro" not in r, r
    return _ler(js, "__args")


def test_o_signUp_por_email_leva_a_origem():
    args = _signup(_TOQUE)
    assert args == [{"email": "a@b.c", "password": "x", "options": {"data": _ESPERADO}}], args


def test_o_signUp_sem_primeiro_toque_nao_manda_data():
    assert _signup(None) == [{"email": "a@b.c", "password": "x"}]


# ══════════════════════════════════════════════════════════════════════════
#  3. O painel: "declarou × chegou por" e a ficha
# ══════════════════════════════════════════════════════════════════════════
def _dxc(pares):
    js = motor()
    js.evaljs(funcao_js("esc", "admin.html"))
    js.evaljs(funcao_js("_grupoChegou", "admin.html"))
    js.evaljs("var _COLUNAS_CHEGOU = ['Google', 'IA (marca no link)', 'direto', 'outra busca',"
              " 'redes', 'outro site', 'sem origem'];")
    js.evaljs(funcao_js("htmlDeclarouXChegou", "admin.html"))
    return js.evaljs("htmlDeclarouXChegou(%s, {google: 'Google'})" % json.dumps(pares))


def _celulas(html, rotulo):
    i = html.index(rotulo)
    linha = html[i:html.index("</tr>", i)]
    return [int(n) for n in re.findall(r"tabular-nums[^>]*>(\d+)<", linha)]


# os 28 que declararam IA de 30/08 a 27/09, pelo src gravado na conta (medido no banco)
_IA = ([("ia_gemini", "google")] * 17 + [("ia_chatgpt", "chatgpt.com")] * 3 + [("ia_gemini", "gemini")] * 2
       + [("ia_copilot", "copilot.com")] * 1 + [("ia_outra", "direto")] * 3 + [("ia_outra", "busca")] * 2)


def test_a_tabela_reproduz_28_6_17():
    pares = [{"declarou": d, "chegou": c} for d, c in _IA] + [{"declarou": "google", "chegou": "google"}] * 5
    html = _dxc(pares)
    # colunas usadas, na ordem: Google, IA (marca no link), direto, outra busca + total
    assert _celulas(html, "Uma IA indicou") == [17, 6, 3, 2, 28], _celulas(html, "Uma IA indicou")
    assert _celulas(html, 'text-gray-700">Google<') == [5, 0, 0, 0, 5]   # a LINHA, não o cabeçalho


def test_CONTROLE_sem_agrupar_a_IA_o_6_nao_apareceria():
    """Sem juntar chatgpt.com/gemini/copilot.com numa coluna, cada um viria solto
    e o "só 6 de 28 chegam com marca de IA" não se lê na tabela."""
    pares = [{"declarou": d, "chegou": c} for d, c in _IA]
    assert "IA (marca no link)" in _dxc(pares)


def test_a_tabela_avisa_quando_a_lista_veio_sem_a_origem_tecnica():
    html = _dxc([{"declarou": "google", "chegou": ""}])
    assert "sem a origem técnica" in html


def test_o_nome_que_vem_de_fora_sai_escapado():
    html = _dxc([{"declarou": "<img src=x onerror=alert(1)>", "chegou": "google"}])
    assert "<img" not in html and "&lt;img" in html


def _ficha(u):
    js = motor("var esc = function (s) { return String(s==null?'':s).replace(/[<>&\"]/g, function (c) {"
               " return {'<':'&lt;','>':'&gt;','&':'&amp;','\"':'&quot;'}[c]; }); };")
    js.evaljs(funcao_js("chegouPor", "admin-usuario.html"))
    return js.evaljs("chegouPor(%s)" % json.dumps(u))


def test_a_ficha_mostra_por_onde_chegou_e_escapa():
    h = _ficha({"src": "google", "src_ref": "www.google.com", "src_landing": "/faq.html"})
    assert "google" in h and "via www.google.com" in h and "entrou por /faq.html" in h
    assert "sem origem gravada" in _ficha({"src": ""})
    assert "<b>" not in _ficha({"src": "<b>x</b>"})


# ══════════════════════════════════════════════════════════════════════════
#  4. A migração (arquivo)
# ══════════════════════════════════════════════════════════════════════════
def test_a_migracao_devolve_as_permissoes_e_nao_escreve_email():
    txt = io.open(_MIG, encoding="utf-8").read()
    assert "drop function public.admin_list_all_signups();" in txt
    assert "revoke execute on function public.admin_list_all_signups() from public, anon;" in txt
    assert "grant execute on function public.admin_list_all_signups() to authenticated, service_role;" in txt
    for c in ("src", "src_ref", "src_campaign", "src_landing"):
        assert "%s text" % c in txt, c
    assert not re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", txt), "e-mail escrito no repo público"
