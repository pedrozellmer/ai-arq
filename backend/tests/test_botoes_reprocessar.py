# -*- coding: utf-8 -*-
"""Os dois botões que re-rodam o projeto precisam dizer o que fazem.

🚨 24/08/2026. O Pedro, único usuário do admin, perguntou:
    "tem avaliar e reprocessar de botão, isso não confunde?"

Confunde — e o risco é assimétrico:

    ↻ Reprocessar  → age NO PROJETO DO CLIENTE: ele passa a ver a versão nova,
                     recebe e-mail, e QUEIMA o reprocesso grátis dele. É 1 por
                     projeto; depois a rota responde 402 e não volta nunca.
    🧪 Avaliar      → job isolado: cliente não vê, sem e-mail, não gasta nada.

E o botão PERIGOSO era o único SEM tooltip, com um confirm que dizia apenas
"(cria um novo job)". Se ele tivesse clicado nele no projeto do cliente-19 naquele
momento, teria gastado o reprocesso grátis do cliente num teste — justo o que a
gente queria guardar pra depois de provar o conserto.

Quando o dono do produto hesita entre dois botões, o problema é do botão.
"""
import io
import os
import re as _re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _admin():
    return io.open(os.path.join(_RAIZ, "admin.html"), encoding="utf-8").read()


# 🩸 04/09/2026 — estes guardas casavam o literal `confirm(`, e quebraram
# quando as dez ações do painel passaram a chamar `_confirmaOuAvisa(`, um
# invólucro que confirma E avisa quando a resposta é não (antes, recusar sumia
# em silêncio). O COMPORTAMENTO que eles protegem — um diálogo por botão, antes
# do window.open — não mudou. Guarda preso ao NOME da função reprova refactor
# honesto; o que importa é a chamada de confirmação, em qualquer das formas.
_RE_CONFIRMA = _re.compile(r"(?<![\w_])(confirm|_confirmaOuAvisa)\s*\(")


def _confirmacoes(corpo):
    """Quantas confirmações bloqueantes este corpo tem."""
    return len(_RE_CONFIRMA.findall(corpo))


def _onde_confirma(corpo):
    """Posição da PRIMEIRA confirmação. -1 se não houver."""
    m = _RE_CONFIRMA.search(corpo)
    return m.start() if m else -1


def test_o_botao_que_mexe_no_cliente_avisa_no_rotulo():
    src = _admin()
    assert src.count("Reprocessar (do cliente)") >= 2, (
        "o rótulo tem que dizer de quem é o projeto — o botão aparece em DOIS "
        "lugares e os dois precisam avisar")


def test_o_botao_seguro_avisa_que_e_isolado():
    assert "Avaliar (isolado)" in _admin()


def test_o_botao_perigoso_tem_tooltip():
    """Era o ÚNICO dos quatro sem tooltip — justamente o que gasta o grátis."""
    src = _admin()
    i = src.index('onclick="adminReprocess(')
    trecho = src[i:i + 400]
    assert "title=" in trecho, "o botão que queima o reprocesso grátis segue sem tooltip"
    assert "GASTA" in trecho.upper()


def test_o_confirm_diz_as_tres_consequencias():
    src = _admin()
    i = src.index("async function adminReprocess")
    corpo = src[i:i + 2000]
    for termo in ("PASSA A VER", "RECEBE e-mail", "GASTA o reprocesso"):
        assert termo in corpo, (
            "o confirm não avisa '%s' — dizia só '(cria um novo job)'" % termo)
    assert "Avaliar (isolado)" in corpo, (
        "o confirm precisa apontar a saída segura, senão só assusta")


def test_o_botao_seguro_tambem_confirma_e_diz_que_e_seguro():
    """Contrapeso: se só o perigoso avisa, o medo de errar paralisa os dois."""
    src = _admin()
    i = src.index("async function adminEvalReprocess")
    corpo = src[i:i + 2200]
    assert "NÃO gasta o reprocesso" in corpo
    assert "fica intacto" in corpo


def test_as_duas_rotas_continuam_sendo_diferentes():
    """Guarda estrutural: se um dia os dois botões chamarem a mesma rota, todo
    o texto acima vira mentira."""
    src = _admin()
    assert "/api/admin/eval-reprocess/" in src, "sumiu a rota isolada"
    assert "}/reprocess`" in src, "sumiu a rota que age no projeto do cliente"
    assert src.count("adminEvalReprocess(") >= 2, "o botão Avaliar sumiu da tela"


# ══════════════════════════════════════════════════════════════════════════
#  🚨 O conserto de 18h05 quebrou o botão às 18h23
# ══════════════════════════════════════════════════════════════════════════
def _funcao(nome):
    src = _admin()
    i = src.index("async function " + nome)
    j = src.index("\nasync function ", i + 10)
    return src[i:j]


def test_confirm_vem_ANTES_do_window_open():
    """🚨 24/08 18h23. Ao "melhorar" o aviso do botão seguro eu acrescentei um
    SEGUNDO confirm — e ele caiu DEPOIS do `window.open`.

    No Safari do iPhone o navegador troca pra a aba nova assim que ela abre, e o
    confirm dispara na aba de TRÁS, onde ninguém o vê. O Pedro clicou, viu tela
    preta, e a função ficou parada esperando resposta de um diálogo invisível.
    Nenhum job de avaliação foi criado — conferido no banco.

    Regra: diálogo bloqueante SEMPRE antes de abrir janela."""
    corpo = _funcao("adminEvalReprocess")
    i_conf = _onde_confirma(corpo)
    assert i_conf >= 0, "sumiu a confirmação do botão de avaliar"
    i_open = corpo.index("window.open(")
    assert i_conf < i_open, (
        "tem confirm DEPOIS do window.open — no celular ele abre numa aba que o "
        "usuário não está vendo e trava o botão")


def test_um_confirm_so_por_botao():
    """Dois diálogos seguidos pro mesmo clique é ruído; e foi o segundo que
    quebrou tudo."""
    for nome in ("adminEvalReprocess", "adminReprocess"):
        n = _confirmacoes(_funcao(nome))
        assert n == 1, "%s tem %d confirms — esperado 1" % (nome, n)


def test_o_confirm_unico_do_avaliar_ainda_diz_que_e_seguro():
    """O aviso que eu queria dar não podia sumir junto com o conserto."""
    corpo = _funcao("adminEvalReprocess")
    for termo in ("NÃO vê nada", "NÃO manda e-mail", "NÃO gasta o reprocesso"):
        assert termo in corpo, "sumiu do confirm: " + termo


def test_nenhum_botao_do_admin_abre_janela_antes_de_perguntar():
    """Guarda geral: a mesma armadilha vale pra qualquer função futura."""
    src = _admin()
    ruins = []
    for m in __import__("re").finditer(r"async function (\w+)\(", src):
        nome = m.group(1)
        try:
            corpo = _funcao(nome)
        except ValueError:
            continue
        if "window.open(" not in corpo or "confirm(" not in corpo:
            continue
        if corpo.index("confirm(") > corpo.index("window.open("):
            ruins.append(nome)
    assert not ruins, (
        "estas funções abrem janela ANTES de perguntar — no celular o diálogo "
        "fica invisível e o botão trava: %s" % ruins)
