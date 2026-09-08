# -*- coding: utf-8 -*-
"""Nenhum "Salvo" verde quando o servidor recusou a gravação.

🚨 25/08/2026. O backend passou a devolver **502** quando a escrita não
confirma — e o comentário dele, em `main.py`, dizia com todas as letras:
*"O front já está pronto: revisao.html trata !r.ok"*.

**Não tratava.** `authFetch` DEVOLVE a resposta e só lança em timeout
(`aiarq-utils.js`: `return resp`), então um 502 caía direto no
`toast.success('Salvo')`. Os quatro salvamentos de item — confirmar, editar,
comentar e marcar como existente — mentiam do mesmo jeito. Só a aprovação em
massa conferia `r.ok`.

🕳️ É a escrita que falha calada, do lado do cliente: ele corrige o número, vê
verde, fecha o navegador — e a correção não existe. Na única tela onde os 10
clientes que de fato editam fazem o trabalho deles.

🪤 O pior era o modal de edição: ele troca o NÚMERO do item na tela antes de
salvar. Falhando, o cliente ficava olhando a correção dele, marcada como
editada, sem ela existir no banco. Por isso o conserto tem duas metades —
conferir o status E desfazer a alteração na tela.

🪤 E a lição que se repete: o comentário no backend descrevia a INTENÇÃO como
se fosse o estado. Terceira vez no mesmo dia (o "Laav" e o "FIX total_users"
foram as outras duas).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔬 07/09/2026 — TRÊS BURACOS FECHADOS NA PRÓPRIA RÉGUA (um cético leu o guarda
e achou os três; nenhum deles estava no alvo, todos estavam na régua):

1. **O inventário via regex só via UMA forma de URL.** O template literal
   casava; `authFetch(API_BASE + '/api/items/' + job + '/review/' + id)` não —
   e nem a chamada da aprovação em massa, que não é `await` direto. Salvamento
   novo escrito com concatenação nascia FORA da lista auditada e o `>= 4`
   garantia só um piso. Agora o inventário sai da ÁRVORE: toda chamada cujo
   argumento contenha `/review/`, seja qual for a forma da URL.

2. **A auditoria parava na primeira porta.** Ela guardava só o 1º `if` com
   `return` e ignorava o resto; um segundo `if (r.status >= 500) return r;`
   logo abaixo era invisível. Agora avalia a DISJUNÇÃO de todas as saídas
   antecipadas — devolver a resposta por qualquer uma delas conta.

3. **`_declaracao` pegava a PRIMEIRA `function` com aquele nome.** O navegador
   executa a ÚLTIMA. Auditando a honesta enquanto a página roda a cega, o 502
   volta a virar toast verde. Esta casa já perdeu um dia com "duas funções com
   o MESMO nome" (smoke vermelho de 20/08). Agora declaração duplicada REPROVA.

🪤 Ressalva honesta: não há motor de JS nesta bancada. O que este arquivo
executa é a EXPRESSÃO DE DECISÃO do salvamento contra respostas HTTP de
mentira — não a página.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _corpo import fonte  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _revisao():
    return fonte("revisao.html")


# ══════════════════════════════════════════════════════════════════════════
#  A árvore (e o mapa de pais, que é o que permite ver o `.then` do sítio)
# ══════════════════════════════════════════════════════════════════════════
_CACHE = {}


def _ast_revisao():
    if "revisao" not in _CACHE:
        import esprima
        # 🔁 Não reimplemente a régua: `_normaliza` é a MESMA que o validador de
        # JS das 12 páginas usa pra fazer o esprima (ES2017) engolir `?.` e `??`.
        from test_js_paginas import _normaliza
        js = _normaliza("\n".join(re.findall(r"<script>(.*?)</script>",
                                             _revisao(), re.S)))
        _CACHE["revisao"] = (esprima.parseScript(js), js)
    return _CACHE["revisao"]


def _nos(raiz):
    """[(nó, pai)] de toda a árvore — em qualquer profundidade."""
    achados = []

    def _anda(n, pai):
        if isinstance(n, list):
            for x in n:
                _anda(x, pai)
            return
        if not hasattr(n, "type"):
            return
        achados.append((n, pai))
        for k in dir(n):
            if k.startswith("_") or k == "type":
                continue
            try:
                v = getattr(n, k)
            except Exception:
                continue
            if v is None or callable(v) or isinstance(v, (str, int, float, bool)):
                continue
            _anda(v, n)
    _anda(raiz, None)
    return achados


def _pais(raiz):
    return {id(n): p for n, p in _nos(raiz)}


def _pedacos_de_texto(n, acc=None):
    """Todo texto literal dentro de `n` — literal solto E pedaço de template.

    🔑 É o que faz o inventário parar de depender da FORMA da URL: template
    literal, concatenação com `+` e string crua caem todos aqui.
    """
    if acc is None:
        acc = []
    if isinstance(n, list):
        for x in n:
            _pedacos_de_texto(x, acc)
        return acc
    if not hasattr(n, "type"):
        return acc
    if n.type == "Literal" and isinstance(getattr(n, "value", None), str):
        acc.append(n.value)
    if n.type == "TemplateElement":
        acc.append(getattr(n.value, "cooked", "") or "")
    for k in dir(n):
        if k.startswith("_") or k == "type":
            continue
        try:
            v = getattr(n, k)
        except Exception:
            continue
        if v is None or callable(v) or isinstance(v, (str, int, float, bool)):
            continue
        _pedacos_de_texto(v, acc)
    return acc


def _nome_do_callee(c):
    cal = c.callee
    if cal.type == "Identifier":
        return cal.name
    if cal.type == "MemberExpression" and getattr(cal.property, "name", None):
        return cal.property.name
    return "(chamada anônima)"


def _inventario(raiz, pais=None):
    """[(nome, nó da chamada)] de todo POST de revisão de item feito pela tela.

    Pela ÁRVORE: qualquer `CallExpression` cujo argumento contenha `/review/`.
    Só as MAIS INTERNAS entram — `Promise.all(batch.map(it => authFetch(...)))`
    tem o texto dentro dela, mas quem faz o pedido é o `authFetch`.
    """
    if pais is None:
        pais = _pais(raiz)
    candidatos = []
    for n, _p in _nos(raiz):
        if n.type != "CallExpression":
            continue
        if "/review/" in "".join(_pedacos_de_texto(list(n.arguments))):
            candidatos.append(n)
    ids = {id(n) for n in candidatos}
    externos = set()
    for n in candidatos:
        p = pais.get(id(n))
        while p is not None:
            if id(p) in ids:
                externos.add(id(p))
            p = pais.get(id(p))
    return [(_nome_do_callee(n), n) for n in candidatos if id(n) not in externos]


def _declaracoes(no, nome):
    """TODAS as `function <nome>` da árvore — a duplicata é o achado."""
    return [n for n, _p in _nos(no)
            if n.type == "FunctionDeclaration" and getattr(n, "id", None)
            and n.id.name == nome]


def _avaliar(no, resposta):
    """Executa a expressão de decisão contra uma resposta HTTP de mentira.

    🔑 É isto que faz o guarda medir COMPORTAMENTO e não texto: `r.ok` e
    `r.ok || r.status >= 500` são duas strings parecidas e duas decisões
    opostas.
    """
    t = no.type
    if t == "Literal":
        return no.value
    if t == "Identifier":
        return resposta
    if t == "MemberExpression":
        return (_avaliar(no.object, resposta) or {}).get(no.property.name)
    if t == "UnaryExpression" and no.operator == "!":
        return not _avaliar(no.argument, resposta)
    if t == "LogicalExpression":
        a, b = _avaliar(no.left, resposta), _avaliar(no.right, resposta)
        return (a or b) if no.operator == "||" else (a and b)
    if t == "BinaryExpression":
        a, b = _avaliar(no.left, resposta), _avaliar(no.right, resposta)
        op = no.operator
        if op in (">=", ">", "<", "<="):
            a, b = (a or 0), (b or 0)
        return {">=": a >= b, ">": a > b, "<": a < b, "<=": a <= b,
                "===": a == b, "==": a == b, "!==": a != b, "!=": a != b}[op]
    raise AssertionError("a decisão do salvamento usa `%s`, que este guarda não "
                         "sabe avaliar — reescreva o guarda, não o afrouxe" % t)


#: (resposta do servidor, a chamada devolveu como boa?)
_RESPOSTAS = [
    ({"ok": True, "status": 200}, True),
    ({"ok": False, "status": 400}, False),
    ({"ok": False, "status": 401}, False),
    ({"ok": False, "status": 409}, False),
    ({"ok": False, "status": 500}, False),
    ({"ok": False, "status": 502}, False),   # 🚨 o caso real de 25/08
]


def _e_salvador_honesto(no, nome):
    """(ok, motivo) — `nome` só devolve resposta boa e reprova o resto lançando?"""
    fns = _declaracoes(no, nome)
    if not fns:
        return False, ("`%s` não é declarada em revisao.html — o salvamento sai "
                       "por uma função que este guarda não consegue ler (o "
                       "`authFetch` DEVOLVE a resposta e só lança em timeout)"
                       % nome)
    if len(fns) > 1:
        # 🚨 20/08: um dia inteiro perdido com duas funções de mesmo nome. O
        # navegador executa a ÚLTIMA; auditar a primeira é auditar código morto.
        return False, ("`%s` é declarada %d vezes em revisao.html — o navegador "
                       "executa a ÚLTIMA e este guarda não tem como saber qual "
                       "delas você conferiu. Apague a duplicata." % (nome, len(fns)))
    fn = fns[0]
    # 🪤 TODAS as saídas antecipadas, não só a primeira: uma segunda porta
    # (`if (r.status >= 500) return r;`) logo abaixo devolve o 502 como bom e
    # era invisível pra versão que guardava só o 1º `if`.
    saidas, tem_throw = [], False
    for st in fn.body.body:
        if st.type == "IfStatement":
            filhos = (st.consequent.body if st.consequent.type == "BlockStatement"
                      else [st.consequent])
            if any(f.type == "ReturnStatement" for f in filhos):
                saidas.append(st.test)
        if st.type == "ThrowStatement":
            tem_throw = True
        if st.type == "ReturnStatement":
            return False, ("`%s` tem um `return` que não decide nada sobre o "
                           "status: salva e devolve a resposta seja ela qual for"
                           % nome)
    if not saidas:
        return False, ("`%s` não decide nada sobre o status: salva e devolve a "
                       "resposta seja ela qual for" % nome)
    if not tem_throw:
        return False, "`%s` confere o status e não lança — não adianta nada" % nome
    for resp, esperado in _RESPOSTAS:
        devolveu = any(bool(_avaliar(c, resp)) for c in saidas)
        if devolveu is not esperado:
            return False, ("`%s` devolve a resposta como boa para HTTP %s (ok=%s) — "
                           "um salvamento que NÃO gravou vira 'Salvo' verde"
                           % (nome, resp["status"], resp["ok"]))
    return True, ""


def _condicoes_que_guardam_throw(cb):
    conds = []
    for n, _p in _nos(cb):
        if n.type != "IfStatement":
            continue
        alvo = (n.consequent.body if n.consequent.type == "BlockStatement"
                else [n.consequent])
        if any(f.type == "ThrowStatement" for f in alvo):
            conds.append(n.test)
    return conds


def _o_sitio_confere(chamada, pais):
    """O PONTO DE CHAMADA confere o status por conta própria?

    É o caso da aprovação em massa: chama `authFetch` (cego) e encadeia
    `.then(r => { if (!r.ok) throw ... })`. Vale tanto quanto um salvador
    honesto — e sem isto o guarda reprovaria código correto.
    """
    atual = chamada
    while True:
        p = pais.get(id(atual))
        if p is None or p.type != "MemberExpression" or p.object is not atual:
            return False
        avo = pais.get(id(p))
        if avo is None or avo.type != "CallExpression" or avo.callee is not p:
            return False
        if getattr(p.property, "name", None) == "then" and avo.arguments:
            for cond in _condicoes_que_guardam_throw(avo.arguments[0]):
                if all(bool(_avaliar(cond, resp)) is (not esperado)
                       for resp, esperado in _RESPOSTAS):
                    return True
        atual = avo


def _veredito(raiz, nome, chamada, pais):
    """(ok, motivo) pra UM sítio de salvamento."""
    if _declaracoes(raiz, nome):
        ok, motivo = _e_salvador_honesto(raiz, nome)
        if ok:
            return True, ""
        if _o_sitio_confere(chamada, pais):
            return True, ""
        return False, motivo
    if _o_sitio_confere(chamada, pais):
        return True, ""
    return False, ("o salvamento sai por `%s`, que não é declarada em "
                   "revisao.html (o `authFetch` DEVOLVE a resposta e só lança "
                   "em timeout) e o ponto de chamada não confere o status — um "
                   "POST que NÃO gravou vira 'Salvo' verde" % nome)


# ══════════════════════════════════════════════════════════════════════════
#  🧪 Controle: a régua acha as chamadas que existem e julga certo
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_a_avaliacao_PEGA_as_tres_formas_de_cegueira():
    """🧪 Prova, na própria régua, que a avaliação reprova o wrapper cego, a
    condição frouxa E a segunda porta aberta — e aprova o conserto."""
    import esprima
    cega = esprima.parseScript("async function _y(u,o){ return await authFetch(u,o); }")
    ok, motivo = _e_salvador_honesto(cega, "_y")
    assert not ok and "não decide nada" in motivo, motivo

    frouxa = esprima.parseScript(
        "async function _x(u,o){const r=await authFetch(u,o);"
        "if (r.ok || r.status >= 500) return r; throw new Error('x');}")
    ok2, motivo2 = _e_salvador_honesto(frouxa, "_x")
    assert not ok2 and "HTTP 5" in motivo2, motivo2

    # 🚨 A lacuna de 07/09: a segunda saída antecipada, invisível pra régua que
    # guardava só o primeiro `if`.
    segunda_porta = esprima.parseScript(
        "async function _w(u,o){const r=await authFetch(u,o);"
        "if (r.ok) return r;"
        "if (r.status >= 500) return r;"
        "throw new Error('x');}")
    ok3, motivo3 = _e_salvador_honesto(segunda_porta, "_w")
    assert not ok3 and "HTTP 500" in motivo3, motivo3

    boa = esprima.parseScript("async function _z(u,o){const r=await authFetch(u,o);"
                              "if (r.ok) return r; throw new Error('x');}")
    assert _e_salvador_honesto(boa, "_z")[0]


def test_CONTROLE_declaracao_duplicada_REPROVA():
    """🚨 O navegador executa a ÚLTIMA. Auditar a primeira é auditar código
    morto — foi o dia perdido de 20/08 ("duas funções com o MESMO nome")."""
    import esprima
    duas = esprima.parseScript(
        "async function _s(u,o){const r=await authFetch(u,o);"
        "if (r.ok) return r; throw new Error('x');}"
        "async function _s(u,o){ return await authFetch(u,o); }")
    assert len(_declaracoes(duas, "_s")) == 2
    ok, motivo = _e_salvador_honesto(duas, "_s")
    assert not ok and "declarada 2 vezes" in motivo, motivo


def test_CONTROLE_o_inventario_ve_a_url_montada_com_concatenacao():
    """🚨 A lacuna de 07/09: a regex antiga só via a URL em template literal.
    Salvamento novo escrito com `+` (ou com a URL numa variável) nascia FORA da
    lista auditada — guarda verde, cliente perdendo a correção."""
    import esprima
    concat = esprima.parseScript(
        "async function f(){ await authFetch(API_BASE + '/api/items/' + jobId + "
        "'/review/' + itemId, { method: 'POST' }); toast.success('Salvo'); }")
    inv = _inventario(concat)
    assert [n for n, _ in inv] == ["authFetch"], inv
    ok, motivo = _veredito(concat, inv[0][0], inv[0][1], _pais(concat))
    assert not ok and "não confere o status" in motivo, motivo


def test_CONTROLE_o_inventario_pega_a_chamada_MAIS_INTERNA():
    """`Promise.all(batch.map(it => authFetch(...)))` tem o texto em três
    níveis. Quem faz o POST é um só — auditar o `all` seria auditar o nada."""
    import esprima
    aninhado = esprima.parseScript(
        "async function f(){ await Promise.all(b.map(it => "
        "authFetch(`${API_BASE}/api/items/${jobId}/review/${it.id}`, {}))); }")
    assert [n for n, _ in _inventario(aninhado)] == ["authFetch"]


def test_CONTROLE_o_sitio_que_confere_sozinho_e_aceito():
    """A aprovação em massa não usa `_salvar`: ela mesma lança em `!r.ok`.
    Reprovar isso seria o guarda mentindo pro outro lado."""
    import esprima
    src = ("async function f(){ await Promise.all(b.map(it => "
           "authFetch(`${API_BASE}/api/items/${jobId}/review/${it.id}`, {})"
           ".then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); n++; })"
           ".catch(e => { falhou.push(e); }))); }")
    arv = esprima.parseScript(src)
    pais = _pais(arv)
    nome, chamada = _inventario(arv, pais)[0]
    assert _veredito(arv, nome, chamada, pais)[0]
    # e sem o `if (!r.ok) throw`, REPROVA
    cego = esprima.parseScript(src.replace(
        "if (!r.ok) throw new Error('HTTP ' + r.status); ", ""))
    pais2 = _pais(cego)
    nome2, chamada2 = _inventario(cego, pais2)[0]
    assert not _veredito(cego, nome2, chamada2, pais2)[0]


def test_controle_acha_todos_os_salvamentos_da_tela():
    raiz, _ = _ast_revisao()
    inv = _inventario(raiz)
    nomes = sorted(n for n, _ in inv)
    assert len(inv) >= 5, (
        "só achei %d salvamentos de item — o parser quebrou ou a tela mudou: %s"
        % (len(inv), nomes))
    assert nomes.count("_salvar") >= 4, nomes


# ══════════════════════════════════════════════════════════════════════════
#  O guarda
# ══════════════════════════════════════════════════════════════════════════
def test_nenhum_salvamento_ignora_o_status_da_resposta():
    """🚨 O caso real: `await authFetch(...)` seguido de toast verde."""
    raiz, _ = _ast_revisao()
    pais = _pais(raiz)
    inv = _inventario(raiz, pais)
    assert len(inv) >= 5, "o parser quebrou ou a tela mudou: %s" % [n for n, _ in inv]
    ruins = []
    for nome, chamada in inv:
        ok, motivo = _veredito(raiz, nome, chamada, pais)
        if not ok and motivo not in ruins:
            ruins.append(motivo)
    assert not ruins, "salvamento cego na tela de revisão:\n  " + "\n  ".join(ruins)


def test_o_salvar_confere_o_ok_e_lanca():
    raiz, _ = _ast_revisao()
    ok, motivo = _e_salvador_honesto(raiz, "_salvar")
    assert ok, motivo


def test_o_salvar_usa_a_frase_que_o_backend_mandou():
    """O 502 traz em `detail` a frase escrita pro cliente ("ela NÃO foi
    gravada"). Trocar por "erro 502" joga fora a única parte útil."""
    src = _revisao()
    i = src.index("async function _salvar(")
    assert "detail" in src[i:i + 700]


@pytest.mark.parametrize("ancora", [
    "const _antes = reviewState[itemId];",     # confirmar / excluir
    "const _antesCampos = {",                  # modal de edição e "existente"
])
def test_a_tela_desfaz_quando_nao_salvou(ancora):
    """🚨 Metade dois do conserto: sem desfazer, o cliente continua vendo a
    correção dele na tela — só que ela não existe no banco."""
    assert ancora in _revisao(), (
        "sumiu o snapshot do estado anterior (%s) — a tela volta a mostrar "
        "como salvo o que não salvou" % ancora)


def test_o_desfazer_esta_no_catch_de_cada_um():
    """Guardar o 'antes' e não restaurar seria pior: parece consertado."""
    src = _revisao()
    assert src.count("Object.assign(_alvo, _antesCampos)") == 1
    assert src.count("Object.assign(it, _antesCampos)") == 1
    # os dois caminhos de estado simples também restauram
    assert src.count("reviewState[itemId] = _antes;") >= 1


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO: o guarda tem que REPROVAR o código de ontem
# ══════════════════════════════════════════════════════════════════════════
_TELA_ANTIGA = """
async function review(itemId, action) {
  reviewState[itemId] = 'approved';
  render();
  try {
    await authFetch(`${API_BASE}/api/items/${jobId}/review/${itemId}`, {
      method: 'POST',
    });
    window.toast.success('Confirmado');
  } catch (e) {}
}
"""

_SALVADOR = ("async function _salvar(url, opts){ const r = await authFetch(url, opts);"
             " if (r.ok) return r; throw new Error('x'); }\n")


def test_controle_positivo_o_guarda_PEGA_a_tela_de_ontem():
    """Este é o código que estava no ar mentindo pro cliente."""
    import esprima
    arv = esprima.parseScript(_TELA_ANTIGA)
    pais = _pais(arv)
    inv = _inventario(arv, pais)
    assert [n for n, _ in inv] == ["authFetch"], inv
    ok, motivo = _veredito(arv, inv[0][0], inv[0][1], pais)
    assert not ok, "o guarda aprovou a tela que mentia pro cliente"
    assert "não confere o status" in motivo, motivo


def test_controle_negativo_o_guarda_APROVA_o_conserto():
    import esprima
    arv = esprima.parseScript(
        _SALVADOR + _TELA_ANTIGA.replace("await authFetch(", "await _salvar("))
    pais = _pais(arv)
    inv = _inventario(arv, pais)
    assert [n for n, _ in inv] == ["_salvar"], inv
    assert _veredito(arv, inv[0][0], inv[0][1], pais)[0]


# ══════════════════════════════════════════════════════════════════════════
#  O outro lado: o backend precisa continuar RECUSANDO
#
#  🔬 07/09/2026 — estes três eram um `assert "502" in trecho`. Liam o fonte de
#  UM dos dois `raise`; o outro (aprovação que não foi registrada em
#  `item_reviews`) não tinha guarda nenhum, e ele cobre a ação MAIS COMUM da
#  tela. Agora CHAMAM a rota.
# ══════════════════════════════════════════════════════════════════════════
import main  # noqa: E402


class _Payload:
    def __init__(self, action, edits=None, comment="", reviewed_by=""):
        self.action = action
        self.edits = edits
        self.comment = comment
        self.reviewed_by = reviewed_by


_ITEM_NO_BANCO = {"id": "11111111-1111-4111-8111-111111111111", "description": "Parede de alvenaria",
                  "unit": "m2", "quantity": 10.0, "confidence": "estimado",
                  "observations": "Fonte: layer 00_PAREDE"}


def _rota(monkeypatch, action, *, insert_ok=True, ja_revisado=False,
          patch_ok=True, edits=None):
    """Chama `submit_item_review` de verdade, com o Supabase dublado.

    Devolve (resposta, exceção) — a rota levanta HTTPException no 502.
    """
    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_insert",
                        lambda tabela, linha: bool(insert_ok))
    monkeypatch.setattr(main, "_assinatura_invalidar", lambda *a, **k: None)
    monkeypatch.setattr(main, "_agendar_aprendizado_revisao", lambda *a, **k: None)

    def _rest(metodo, caminho, *a, **kw):
        if metodo == "GET" and caminho.startswith("project_items"):
            return 200, [dict(_ITEM_NO_BANCO)]
        if metodo == "GET" and caminho.startswith("item_reviews"):
            return (200, [{"id": "rev-1", "comment": ""}]) if ja_revisado else (200, [])
        return 200, []
    monkeypatch.setattr(main, "_supa_rest_service", _rest)

    import urllib.request

    def _urlopen(req, *a, **kw):
        if not patch_ok:
            raise OSError("connection reset")
        class _R:
            status = 204
        return _R()
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)

    try:
        return main.submit_item_review(
            "job-de-teste", "11111111-1111-4111-8111-111111111111",
            _Payload(action, edits=edits), None), None
    except Exception as e:
        return None, e


def _e_502(erro):
    from fastapi import HTTPException
    return isinstance(erro, HTTPException) and erro.status_code == 502


def test_o_backend_ainda_devolve_502_quando_a_ESCRITA_nao_pegou(monkeypatch):
    """🪤 Guarda de front sozinho não guarda nada: se o backend voltar a
    responder 200 quando não gravou, a tela confere um status que mente."""
    resp, erro = _rota(monkeypatch, "edit", patch_ok=False,
                       edits={"quantity": 12.5})
    assert resp is None, "a rota respondeu %r com o PATCH falhando" % (resp,)
    assert _e_502(erro), erro
    assert "NÃO foi gravada" in str(erro.detail), erro.detail


def test_o_backend_devolve_502_quando_a_APROVACAO_nao_foi_registrada(monkeypatch):
    """🚨 O segundo 502, que não tinha guarda nenhum até 07/09 — e ele cobre a
    ação MAIS COMUM da tela (184 aprovações contra 108 edições até 31/08).

    Sem este `raise`, o insert em `item_reviews` falha, a rota responde
    200 `{"status":"ok","gravou":false}`, e a tela pinta o verde. É exatamente
    a mentira que este arquivo existe pra impedir.
    """
    resp, erro = _rota(monkeypatch, "approve", insert_ok=False)
    assert resp is None, (
        "aprovação que NÃO gravou em item_reviews respondeu %r — a tela vai "
        "mostrar 'Confirmado' em verde" % (resp,))
    assert _e_502(erro), erro
    assert "registrar esta aprovação" in str(erro.detail), erro.detail


def test_CONTROLE_a_aprovacao_que_GRAVOU_responde_ok(monkeypatch):
    """Controle negativo: apertar demais aqui derruba a ação mais usada."""
    resp, erro = _rota(monkeypatch, "approve", insert_ok=True)
    assert erro is None, erro
    assert resp["status"] == "ok" and resp["gravou"] is True, resp


def test_CONTROLE_aprovacao_repetida_nao_vira_502_falso(monkeypatch):
    """O dedupe de 01/08 pula o insert quando o item já foi aprovado. Isso NÃO
    é falha de escrita — virar 502 aqui seria erro na cara de quem clicou duas
    vezes."""
    resp, erro = _rota(monkeypatch, "approve", ja_revisado=True)
    assert erro is None, erro
    assert resp["status"] == "ok", resp


def test_CONTROLE_edicao_que_gravou_responde_ok(monkeypatch):
    resp, erro = _rota(monkeypatch, "edit", patch_ok=True, edits={"quantity": 12.5})
    assert erro is None, erro
    assert resp["gravou"] is True, resp


def test_o_comentario_do_backend_nao_afirma_mais_o_que_nao_era_verdade():
    """🪤 O comentário dizia 'O front já está pronto: revisao.html trata
    !r.ok' — e era mentira. Comentário que afirma estado do OUTRO arquivo
    envelhece mentindo; quem lê acredita e não confere."""
    src = fonte("main.py")
    assert "O front já está pronto" not in src, (
        "voltou a afirmar, no backend, um estado do front que ninguém "
        "verifica quando o front muda")
