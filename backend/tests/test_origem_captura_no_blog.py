# -*- coding: utf-8 -*-
"""A captura de ORIGEM tem que rodar em página SEM supabase-js (o blog).

🩸 31/08/2026: o bloco de first-touch (`_captureSource`) estava DEPOIS do
`return` do guarda do supabase-js em aiarq-utils.js. No blog — página estática,
sem SDK — o arquivo saía no return e a origem NUNCA era capturada. Medido no
banco: dos 9 `view_blog_post`, os 4 com `src` eram todos do MESMO navegador
(que já tinha o dado salvo desde julho); os 5 sem `src` eram visitantes novos.
Todos os outros eventos do site: 100% com src.

Consequência real: quem chegava do Google num post e depois se cadastrava
perdia o first-touch — o referrer virava ai.arq.br e a pessoa era carimbada
como "direto". O canal que a gente mais quer medir era o único cego.

🪤 Mesma família do conserto de 28/08 (subiram o trackEvent pra antes do guarda
e deixaram a origem pra trás). Meio conserto é o mais caro: dá a sensação de
resolvido.
"""
import io
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UTILS = os.path.join(RAIZ, "aiarq-utils.js")


def _fonte():
    return io.open(UTILS, encoding="utf-8").read()


def _pos_guarda(src):
    """Onde o arquivo faz `return` por falta do supabase-js."""
    i = src.index("if (!window.supabase || typeof window.supabase.createClient")
    return src.index("return;", i)


def test_captura_de_origem_roda_ANTES_do_guarda():
    src = _fonte()
    assert src.index("_captureSource") < _pos_guarda(src), (
        "a captura de first-touch voltou pra DEPOIS do return do guarda — no "
        "blog ela não roda e todo visitante novo perde a origem")


def test_trackEvent_tambem_antes_do_guarda():
    """O conserto de 28/08 não pode regredir junto."""
    src = _fonte()
    assert src.index("window.trackEvent = function") < _pos_guarda(src)


def test_aiArqSource_disponivel_no_blog():
    """O leitor da origem (usado no cadastro pra atribuir a conta) também
    precisa existir em página estática."""
    src = _fonte()
    assert src.index("window.aiArqSource = function") < _pos_guarda(src)


def test_CONTROLE_POSITIVO_o_detector_pega_a_ordem_errada():
    """🧪 Prova que o teste reprova mesmo: com a ordem invertida, falha."""
    # arquivo sintético com a ordem ANTIGA (captura DEPOIS do return)
    falso = ("window.trackEvent = function () {};\n"
             "if (!window.supabase || typeof window.supabase.createClient !== 'function') {\n"
             "  return;\n}\n"
             "(function _captureSource() {})();\n"
             "window.aiArqSource = function () {};\n")
    g = falso.index("return;", falso.index(
        "if (!window.supabase || typeof window.supabase.createClient"))
    assert falso.index("_captureSource") > g, (
        "o controle não reproduziu a ordem errada — o guarda acima não vale nada")
