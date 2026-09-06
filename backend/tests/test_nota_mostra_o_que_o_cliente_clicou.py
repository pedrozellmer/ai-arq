# -*- coding: utf-8 -*-
"""A nota mostrada é o que a pessoa CLICOU, não a tradução que a gente guardou.

🩸 02/09/2026, caso cliente-19 (job `17d6e1f2`). Ele clicou **"😐 Mais ou
menos"** na página do projeto, e o alerta chegou pro Pedro dizendo:

    🟡 NPS 7 — neutro
    Nota: 7/10

O Pedro lê "ele deu sete de dez". O cliente disse "mais ou menos" — que é
informação diferente e mais pobre.

🪤 SÃO DUAS TELAS GRAVANDO NA MESMA COLUNA `score`:

  · `after_download` → widget do dashboard, ONZE botões de 0 a 10 (o `data-score`
    bate com o rótulo; essa parte está correta). Nota de verdade.
  · `after_project`  → TRÊS botões (projeto.html:441-443):
        👍 Ajudou bastante → 9
        😐 Mais ou menos   → 7
        👎 Não muito       → 2
    O número é tradução NOSSA. A pessoa nunca viu uma régua de 0 a 10.

📏 Das SEIS avaliações da história inteira do produto, DUAS vieram da escala de
três (cliente-19 e cliente-09) — e o painel mostrava as seis do mesmo jeito. Com seis
respostas, misturar uma escala de 3 pontos com uma de 11 esvazia o número.

🔑 Este conserto NÃO mexe na coleta nem no valor guardado — isso é decisão de
produto do Pedro. Mexe em como o número é APRESENTADO, que é onde nasce o
engano: no e-mail de alerta e no painel.

🪤 Fora dos três valores conhecidos, cai no rótulo numérico. Se um dia a página
do projeto mandar outra coisa, mostrar o número cru é melhor que inventar uma
carinha que ninguém clicou.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


# ── O rótulo ───────────────────────────────────────────────────────────────
def test_a_escolha_de_3_botoes_mostra_a_CARINHA():
    """🩸 O caso do cliente-19."""
    r = main._nps_rotulo(7, "after_project")
    assert "Mais ou menos" in r, r
    assert "7 de 10" not in r, (
        "continua dizendo 'de 10' pra quem escolheu entre três opções: %s" % r)


def test_os_TRES_botoes_da_pagina_do_projeto():
    assert "Ajudou bastante" in main._nps_rotulo(9, "after_project")
    assert "Mais ou menos" in main._nps_rotulo(7, "after_project")
    assert "Não muito" in main._nps_rotulo(2, "after_project")


def test_o_rotulo_DIZ_que_eram_3_opcoes():
    """Sem isso, "😐 Mais ou menos" ainda parece uma nota numa régua larga."""
    assert "3 opções" in main._nps_rotulo(7, "after_project")


def test_CONTROLE_a_nota_de_VERDADE_continua_sendo_nota():
    """🧪 O widget do dashboard tem 11 botões e o cliente escolhe o número.
    Ali "7" é sete mesmo, e o conserto não pode transformar em carinha."""
    assert main._nps_rotulo(7, "after_download") == "7 de 10"
    assert main._nps_rotulo(10, "manual") == "10 de 10"
    assert main._nps_rotulo(0, "after_review") == "0 de 10"


def test_CONTROLE_valor_inesperado_na_pagina_do_projeto_cai_no_NUMERO():
    """🪤 Se a página passar a mandar 5, inventar uma carinha seria pior que
    mostrar o número cru."""
    assert main._nps_rotulo(5, "after_project") == "5 de 10"


def test_CONTROLE_score_ilegivel_nao_estoura():
    assert main._nps_rotulo(None, "after_project") == "?"
    assert main._nps_rotulo("abc", "after_download") == "?"


# ── O alerta que chega no Pedro ────────────────────────────────────────────
def _fonte():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _sem_comentarios(t):
    return "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("#"))


def test_o_email_NAO_diz_mais_barra_10_pra_todo_mundo():
    """🩸 A linha exata que enganava: `<b>Nota:</b> {_nota}/10`."""
    limpo = _sem_comentarios(_fonte())
    assert "<b>Nota:</b> {_nota}/10" not in limpo, (
        "o e-mail voltou a afirmar '/10' pra quem escolheu entre três botões")


def test_o_email_USA_o_rotulo():
    limpo = _sem_comentarios(_fonte())
    assert "_rotulo = _nps_rotulo(" in limpo, "o alerta não calcula o rótulo"
    assert "<b>Resposta:</b> {_rotulo}" in limpo, "o corpo do e-mail não usa o rótulo"


def test_o_log_guarda_os_DOIS_o_rotulo_e_o_numero():
    """🪤 O número guardado continua importando pra investigar depois — o que
    muda é que ele para de ser a única coisa que aparece."""
    limpo = _sem_comentarios(_fonte())
    assert "score_guardado={_nota}" in limpo, (
        "o log perdeu o número cru, que é o que permite auditar")
    assert "resposta={_rotulo!r}" in limpo, "o log não registra o que foi clicado"


# ── O painel ───────────────────────────────────────────────────────────────
def test_o_painel_conhece_o_contexto_da_pagina_do_projeto():
    """Antes ele caía no `|| r.context` e mostrava a string crua
    "after_project" pro Pedro."""
    adm = io.open(os.path.join(_RAIZ, "admin.html"), encoding="utf-8").read()
    assert "'after_project':  'Na página do projeto'" in adm, (
        "o painel ainda mostra a chave técnica em vez do nome da tela")


def test_o_painel_mostra_a_carinha_no_lugar_do_numero():
    adm = io.open(os.path.join(_RAIZ, "admin.html"), encoding="utf-8").read()
    assert "_btn3" in adm and "Mais ou menos" in adm, (
        "o painel continua mostrando só o número traduzido")
    assert "_escolha ? _escolha.slice(0, 2) : r.score" in adm, (
        "a bolinha não troca o número pela carinha quando foi escolha de 3")


def test_CONTROLE_o_painel_PRESERVA_o_numero_no_title():
    """O número guardado não pode sumir: ele fica no `title`, pra conferência."""
    adm = io.open(os.path.join(_RAIZ, "admin.html"), encoding="utf-8").read()
    assert "guardado como ' + r.score" in adm, (
        "o número guardado sumiu da tela — não dá pra auditar o que foi gravado")
