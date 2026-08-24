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
"(cria um novo job)". Se ele tivesse clicado nele no projeto do Alan naquele
momento, teria gastado o reprocesso grátis do cliente num teste — justo o que a
gente queria guardar pra depois de provar o conserto.

Quando o dono do produto hesita entre dois botões, o problema é do botão.
"""
import io
import os

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _admin():
    return io.open(os.path.join(_RAIZ, "admin.html"), encoding="utf-8").read()


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
