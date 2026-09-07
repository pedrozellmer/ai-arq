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
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import fonte  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _revisao():
    return fonte("revisao.html")


def _chamadas_de_gravacao(src):
    """Cada POST de revisão de item feito pela tela."""
    return re.findall(r"await\s+(\w+)\(`\$\{API_BASE\}/api/items/\$\{jobId\}/review/",
                      src)


# ══════════════════════════════════════════════════════════════════════════
#  🧪 Controle: o parser acha as chamadas que existem
# ══════════════════════════════════════════════════════════════════════════
def _ast_revisao():
    import esprima
    # 🔁 Não reimplemente a régua: `_normaliza` é a MESMA que o validador de JS
    # das 12 páginas usa pra fazer o esprima (ES2017) engolir `?.` e `??`.
    from test_js_paginas import _normaliza
    js = _normaliza("\n".join(re.findall(r"<script>(.*?)</script>", _revisao(), re.S)))
    return esprima.parseScript(js), js


def _declaracao(no, nome):
    """A `function <nome>` dentro da árvore, em qualquer profundidade."""
    achado = []

    def _anda(n):
        if isinstance(n, list):
            for x in n:
                _anda(x)
            return
        if not hasattr(n, "type"):
            return
        if n.type == "FunctionDeclaration" and getattr(n, "id", None) \
                and n.id.name == nome:
            achado.append(n)
        for k in dir(n):
            if k.startswith("_") or k == "type":
                continue
            try:
                _anda(getattr(n, k))
            except Exception:
                pass
    _anda(no)
    return achado[0] if achado else None


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
    fn = _declaracao(no, nome)
    if fn is None:
        return False, ("`%s` não é declarada em revisao.html — o salvamento sai "
                       "por uma função que este guarda não consegue ler (o "
                       "`authFetch` DEVOLVE a resposta e só lança em timeout)"
                       % nome)
    cond, tem_throw = None, False
    for st in fn.body.body:
        if st.type == "IfStatement" and cond is None:
            filhos = (st.consequent.body if st.consequent.type == "BlockStatement"
                      else [st.consequent])
            if any(f.type == "ReturnStatement" for f in filhos):
                cond = st.test
        if st.type == "ThrowStatement":
            tem_throw = True
    if cond is None:
        return False, ("`%s` não decide nada sobre o status: salva e devolve a "
                       "resposta seja ela qual for" % nome)
    if not tem_throw:
        return False, "`%s` confere o status e não lança — não adianta nada" % nome
    for resp, esperado in _RESPOSTAS:
        if bool(_avaliar(cond, resp)) is not esperado:
            return False, ("`%s` devolve a resposta como boa para HTTP %s (ok=%s) — "
                           "um salvamento que NÃO gravou vira 'Salvo' verde"
                           % (nome, resp["status"], resp["ok"]))
    return True, ""


def test_CONTROLE_a_avaliacao_PEGA_as_duas_formas_de_cegueira():
    """🧪 Prova, na própria régua, que a avaliação reprova o wrapper cego E a
    condição frouxa — e aprova o conserto."""
    import esprima
    cega = esprima.parseScript("async function _y(u,o){ return await authFetch(u,o); }")
    ok, motivo = _e_salvador_honesto(cega, "_y")
    assert not ok and "não decide nada" in motivo, motivo
    frouxa = esprima.parseScript(
        "async function _x(u,o){const r=await authFetch(u,o);"
        "if (r.ok || r.status >= 500) return r; throw new Error('x');}")
    ok2, motivo2 = _e_salvador_honesto(frouxa, "_x")
    assert not ok2 and "HTTP 5" in motivo2, motivo2
    boa = esprima.parseScript("async function _z(u,o){const r=await authFetch(u,o);"
                              "if (r.ok) return r; throw new Error('x');}")
    assert _e_salvador_honesto(boa, "_z")[0]


def test_controle_acha_os_quatro_salvamentos():
    chamadas = _chamadas_de_gravacao(_revisao())
    assert len(chamadas) >= 4, (
        "só achei %d salvamentos de item — o parser quebrou ou a tela mudou "
        "de forma: %s" % (len(chamadas), chamadas))


# ══════════════════════════════════════════════════════════════════════════
#  O guarda
# ══════════════════════════════════════════════════════════════════════════
def test_nenhum_salvamento_ignora_o_status_da_resposta():
    """🚨 O caso real: `await authFetch(...)` seguido de toast verde."""
    no, js = _ast_revisao()
    chamadas = _chamadas_de_gravacao(js)
    assert len(chamadas) >= 4, "o parser quebrou ou a tela mudou: %s" % chamadas
    ruins = []
    for nome in sorted(set(chamadas)):
        ok, motivo = _e_salvador_honesto(no, nome)
        if not ok:
            ruins.append(motivo)
    assert not ruins, "salvamento cego na tela de revisão:\n  " + "\n  ".join(ruins)

def test_o_salvar_confere_o_ok_e_lanca():
    no, _ = _ast_revisao()
    ok, motivo = _e_salvador_honesto(no, "_salvar")
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
  reviewState[itemId] = 'approved';
  render();
  try {
    await authFetch(`${API_BASE}/api/items/${jobId}/review/${itemId}`, {
      method: 'POST',
    });
    window.toast.success('Confirmado');
  } catch (e) {}
"""


def test_controle_positivo_o_guarda_PEGA_a_tela_de_ontem():
    """Este é o código que estava no ar mentindo pro cliente."""
    cruas = [c for c in _chamadas_de_gravacao(_TELA_ANTIGA) if c == "authFetch"]
    assert cruas, "o guarda não vê o `await authFetch` direto — não guarda nada"


def test_controle_negativo_o_guarda_APROVA_o_conserto():
    nova = _TELA_ANTIGA.replace("await authFetch(", "await _salvar(")
    assert not [c for c in _chamadas_de_gravacao(nova) if c == "authFetch"]


# ══════════════════════════════════════════════════════════════════════════
#  O outro lado: o backend precisa continuar RECUSANDO
# ══════════════════════════════════════════════════════════════════════════
def test_o_backend_ainda_devolve_502_quando_nao_gravou():
    """🪤 Guarda de front sozinho não guarda nada: se o backend voltar a
    responder 200 quando não gravou, a tela confere um status que mente."""
    src = fonte("main.py")
    i = src.index("if _tentou_escrever and not _escreveu:")
    trecho = src[i:i + 400]
    assert "502" in trecho
    assert "NÃO foi gravada" in trecho


def test_o_comentario_do_backend_nao_afirma_mais_o_que_nao_era_verdade():
    """🪤 O comentário dizia 'O front já está pronto: revisao.html trata
    !r.ok' — e era mentira. Comentário que afirma estado do OUTRO arquivo
    envelhece mentindo; quem lê acredita e não confere."""
    src = fonte("main.py")
    assert "O front já está pronto" not in src, (
        "voltou a afirmar, no backend, um estado do front que ninguém "
        "verifica quando o front muda")
