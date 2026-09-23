# -*- coding: utf-8 -*-
"""A janela que pergunta o pé-direito e a área — rodando o JS de verdade.

💡 Ideia do Pedro, 22/09/2026: *"quando o cliente foi enviar o projeto, abriu
uma janela… tipo 'tem certeza, não quero informar isso'. Muitos clientes
acabam não subindo, e isso ajudaria muito na criação das planilhas."*

📊 Medido antes de escrever (90 dias, 210 projetos de cliente): **28 (13,3%)
informaram o pé-direito**, 28 a área, e **170 (81%) não informaram nada**. O
campo está na tela desde agosto e fica vazio — a tela pedia o dado sem dizer
o que se perde sem ele.

🔑 E o custo mudou hoje: com a regra nova do selo, o pé-direito informado
entra como INSUMO MEDIDO na conta do CAD (contagem × seção × pé-direito), em
vez de rebaixar a linha. Sem ele, fôrma de pilar e área de parede saem em
branco ou estimadas.

🚨 Este guarda EXECUTA o JavaScript da tela num motor JS (Duktape) — não
procura texto no arquivo. A varredura por mutação de 06/09 provou cegos os
guardas que liam fonte.

🧪 Controles positivos: quem informou UM dos dois não é perguntado; "enviar
assim mesmo" segue; e sem o toast a tela NÃO cai no `confirm()` nativo (ele
trava a aba — visto em 19/09) — segue em silêncio, porque travar o envio
custa o projeto inteiro.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)

from _jsbancada import fonte_html, funcao_js, motor, rodar  # noqa: E402

_SRC = fonte_html("dashboard.html")
NL = chr(10)


def _preludio(pd="", area="", com_toast=True, escolha=True):
    """Encena o DOM: dois campos e (ou não) o toast da casa."""
    partes = [
        "var __campos = {'project-pe-direito': %r, 'project-area': %r};" % (pd, area),
        "var __focado = null;",
        "var document = { getElementById: function(id) {",
        "  if (!(id in __campos)) return null;",
        "  return { value: __campos[id],",
        "           scrollIntoView: function(){},",
        "           focus: function(){ __focado = id; } };",
        "} };",
        "var setTimeout = function(f){ f(); };",
        "var window = {};",
        # 🪤 O `confirm` EXISTE no prelúdio de propósito. Sem ele, chamar
        # confirm() dá ReferenceError, cai no catch e devolve 'seguir' — e o
        # guarda do confirm nativo passava verde COM o defeito (provado por
        # sabotagem em 22/09). Aqui ele existe, registra, e devolve true:
        # se a tela chamar, o resultado muda E a chamada fica marcada.
        "var __confirmou = 0;",
        "var confirm = function(m){ __confirmou++; return true; };",
    ]
    if com_toast:
        partes.append(
            "window.toast = { confirm: function(msg, op){ __msg = msg; __op = op;"
            " return Promise.resolve(%s); } };" % ("true" if escolha else "false"))
    partes += ["var __msg = null, __op = null;",
               funcao_js("_premissasEmBranco", "dashboard.html", _SRC),
               funcao_js("_confirmarPremissasVazias", "dashboard.html", _SRC)]
    return NL.join(partes)


def _resp(**kw):
    js = motor(_preludio(**kw))
    return js, rodar(js, "_confirmarPremissasVazias()")


# ── o caso que motivou: os dois em branco ──────────────────────────────────
def test_com_os_DOIS_em_branco_a_janela_pergunta():
    js, r = _resp(pd="", area="")
    assert r.get("ok"), r
    assert r["valor"] == "informar", (
        "a pessoa clicou em 'Informar agora' e o envio seguiu assim mesmo: %r" % r)
    msg = js.evaljs("__msg")
    assert "pé-direito" in msg and "área total" in msg
    assert "5 segundos" in msg, "a janela tem que dizer que é rápido"


def test_a_janela_diz_o_QUE_SE_PERDE_nao_so_pede_o_dado():
    """🔑 O campo já existe e fica vazio em 81% — repetir o pedido não muda
    nada. O que muda é dizer o custo."""
    js, _ = _resp(pd="", area="")
    msg = js.evaljs("__msg")
    for pedaco in ("parede", "pintura", "fôrma de pilar", "em branco"):
        assert pedaco in msg, "a janela não diz o que se perde (%r): %r" % (pedaco, msg)


def test_as_duas_saidas_estao_na_janela():
    js, _ = _resp(pd="", area="")
    op = js.evaljs("JSON.stringify(__op)")
    assert "Informar agora" in op and "Enviar assim mesmo" in op, op


def test_quem_escolhe_ENVIAR_ASSIM_MESMO_segue():
    """🪤 Nunca obrigatório: às vezes a pessoa não sabe o pé-direito, e travar
    o envio por isso custa o projeto inteiro."""
    _js, r = _resp(pd="", area="", escolha=False)
    assert r["valor"] == "seguir", r


# ── controles positivos ────────────────────────────────────────────────────
@pytest.mark.parametrize("pd, area, quem", [
    ("2,80", "", "informou o pé-direito"),
    ("", "320", "informou a área"),
    ("2,80", "320", "informou os dois"),
])
def test_CONTROLE_quem_JA_informou_nao_e_perguntado(pd, area, quem):
    js, r = _resp(pd=pd, area=area)
    assert r["valor"] == "seguir", "perguntou a quem %s: %r" % (quem, r)
    assert js.evaljs("__msg") is None, "abriu a janela à toa (%s)" % quem


def test_CONTROLE_sem_o_toast_NAO_cai_no_confirm_nativo():
    """🪤 19/09: `confirm()` nativo trava a aba. Sem o toast da casa, a tela
    segue em silêncio — perguntar não vale um envio travado.

    🩸 22/09: a 1ª versão deste guarda passou VERDE numa sabotagem que punha
    `confirm()` de volta — porque o prelúdio não definia `confirm`, a chamada
    explodia e o catch devolvia 'seguir' por acidente. Agora o prelúdio TEM
    confirm, e o guarda cobra que ele não foi chamado."""
    js, r = _resp(pd="", area="", com_toast=False)
    assert r.get("ok"), r
    assert r["valor"] == "seguir", r
    assert js.evaljs("__confirmou") == 0, (
        "a tela caiu no confirm() nativo — ele trava a aba do cliente")


def test_CONTROLE_o_toast_que_QUEBRA_nao_trava_o_envio():
    """Promessa rejeitada (toast com defeito) não pode segurar o projeto."""
    pre = _preludio(pd="", area="").replace(
        "return Promise.resolve(true);", "return Promise.reject(new Error('x'));")
    js = motor(pre)
    r = rodar(js, "_confirmarPremissasVazias()")
    assert r.get("ok") and r["valor"] == "seguir", r
