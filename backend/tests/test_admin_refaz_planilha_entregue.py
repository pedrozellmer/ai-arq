# -*- coding: utf-8 -*-
"""Botão de admin pra refazer planilha que já foi entregue errada.

🩸 03/09/2026. A gente consertou um defeito que já tinha posto arquivo errado
na mão de dois clientes: a planilha refeita saía sem os avisos e com a área que
ELES digitaram carimbada como "Área construída — perímetro externo da laje" —
a planilha afirmando uma medição que não houve (regra dura nº1).

O conserto valia do próximo arquivo em diante, e **não havia caminho pra
alcançar os que já saíram**: a rota que refaz (`/api/items/{job}/finalize`) é
travada no dono do projeto, e não existia rota de admin.

🔑 Isto NÃO é reprocessar. Não relê o CAD, não chama IA, não gasta o reprocesso
grátis do cliente e não manda e-mail — só remonta o `.xlsx` com os itens que já
estão no banco. O botão "Reprocessar (do cliente)", que fica ao lado, faz todas
essas quatro coisas; confundir os dois custa caro.

⏭️ Serve pra toda vez que um conserto nosso precisar alcançar arquivo velho —
que, pelo que este dia mostrou, não vai ser raro.

🪤 ESTE ARQUIVO NASCEU DE UM ERRO MEU. A primeira versão da função JS foi
escrita com os `\n` virando QUEBRA DE LINHA REAL dentro da string — JavaScript
inválido, que teria quebrado o painel inteiro. Passou no meu olho e no
balanço de parênteses; quem pegou foi o parser. Por isso o guarda abaixo
PARSEIA o JS em vez de procurar texto.
"""
import io
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main as m                                    # noqa: E402
from _corpo import corpo_de, fonte, sem_comentarios, so_o_que_roda  # noqa: E402

_ADMIN = fonte("admin.html")


def _funcao_js(nome, src=None):
    src = src if src is not None else _ADMIN
    i = src.find("async function %s(" % nome)
    if i < 0:
        i = src.find("function %s(" % nome)
    assert i >= 0, "não achei a função %s em admin.html" % nome
    prof, k = 0, src.find("{", i)
    while k < len(src):
        if src[k] == "{":
            prof += 1
        elif src[k] == "}":
            prof -= 1
            if prof == 0:
                return src[i:k + 1]
        k += 1
    raise AssertionError("chaves desbalanceadas em %s" % nome)


# ── A rota ─────────────────────────────────────────────────────────────────
def test_a_rota_existe_e_e_SO_de_admin():
    corpo = sem_comentarios(corpo_de("admin_refazer_planilha"))
    assert "_require_admin(request)" in corpo, (
        "a rota que sobrescreve arquivo de cliente ficou sem trava de admin")
    assert "rebuild_planilha_from_review(job_id, request)" in corpo, (
        "parou de reusar a remontagem que já existe — cópia nova da mesma regra")


def test_a_rota_NAO_reprocessa():
    """🚨 A diferença que importa: reprocessar relê o CAD, chama IA, manda
    e-mail e queima o reprocesso grátis. Esta rota não pode fazer nada disso."""
    # 🪤 `so_o_que_roda` tira a DOCSTRING também: a docstring desta rota
    # explica que ela "não gasta o reprocesso grátis", e a primeira versão
    # deste teste reprovou por causa do próprio texto. É a 5ª vez hoje que um
    # guarda meu acusa a documentação que escrevi pra justificá-lo.
    corpo = so_o_que_roda("admin_refazer_planilha")
    # 🪤 Procurar a PALAVRA "reprocess" era frouxo demais: a própria mensagem
    # de log diz "sem gastar reprocesso" e o guarda reprovava o texto que
    # existe pra explicar que ele NÃO faz isso. O que importa é a CHAMADA.
    for proibido in ("process_job(", "_send_email_smtp(", "Thread(",
                     "admin_reprocess", "anthropic", "generate_budget"):
        assert proibido not in corpo, (
            "a rota de refazer passou a chamar %r — virou reprocesso" % proibido)


def test_a_rota_deixa_rastro():
    corpo = sem_comentarios(corpo_de("admin_refazer_planilha"))
    assert '_log_error("motor:refaz-planilha-admin"' in corpo
    assert "motor:refaz-planilha-admin" in m._STAGES_DIAGNOSTICO, (
        "stage fora da lista de diagnóstico vira alarme vermelho no painel")


# ── O botão ────────────────────────────────────────────────────────────────
def test_o_botao_existe_e_chama_a_funcao():
    assert 'adminRefazerPlanilha(' in _ADMIN
    assert "/api/admin/refazer-planilha/" in _ADMIN


def test_o_confirm_DIZ_o_que_a_acao_NAO_faz():
    """🪤 O botão vizinho ('Reprocessar do cliente') gasta o reprocesso grátis
    e manda e-mail. Se o texto não separar os dois, o Pedro clica no errado —
    foi exatamente a pergunta dele em 24/08: 'isso não confunde?'."""
    fn = _funcao_js("adminRefazerPlanilha")
    baixo = fn.lower()
    # 🩸 04/09: casava o literal `confirm(` e quebrou quando as dez ações
    # do painel passaram a usar `_confirmaOuAvisa(` — invólucro que confirma E
    # avisa na recusa (antes, cancelar sumia em silêncio). O que importa é ter
    # confirmação bloqueante, não o nome dela.
    assert ("confirm(" in fn or "_confirmaOuAvisa(" in fn), (
        "some sem confirmação numa ação que sobrescreve arquivo")
    assert "nao rele o cad" in baixo or "não relê o cad" in baixo
    assert "nao gasta o reprocesso" in baixo or "não gasta o reprocesso" in baixo


# ── O guarda que nasceu do meu erro ────────────────────────────────────────
def test_a_funcao_do_botao_e_JAVASCRIPT_VALIDO():
    """🩸 A 1ª versão desta função tinha os `\n` como QUEBRA DE LINHA REAL
    dentro da string — JS inválido, que teria derrubado o painel inteiro.
    Balanço de parênteses não pega (o arquivo já é desbalanceado por causa de
    parêntese dentro de string, antes e depois). Só o parser pega."""
    esprima = __import__("esprima")
    esprima.parseScript(_funcao_js("adminRefazerPlanilha"))


def test_CONTROLE_o_parser_REPROVA_exatamente_o_erro_que_eu_cometi():
    """🧪 Sem isto o teste acima poderia estar parseando qualquer coisa."""
    esprima = __import__("esprima")
    quebrado = ("function x(){ if(!confirm('linha um\n"
                "'\n + 'linha dois')) return; }")
    try:
        esprima.parseScript(quebrado)
    except Exception:
        return
    raise AssertionError("o parser aceitou string com quebra de linha real — "
                         "o guarda acima deixou de provar alguma coisa")


def test_as_classes_do_botao_estao_VIVAS_no_css():
    """🚨 Tailwind é build estático aqui: classe fora do CSS nasce invisível."""
    css = io.open(os.path.join(_RAIZ, "tailwind.min.css"), encoding="utf-8").read()
    # a linha INTEIRA do botão (o `title` é longo; janela curta não alcança
    # o `class`, e foi assim que a 1ª versão deste teste achou zero classe)
    i = _ADMIN.find("_btns.push('<button onclick=\"adminRefazerPlanilha(")
    assert i > 0, "não achei a linha do botão"
    trecho = _ADMIN[i:_ADMIN.find(chr(10), i)]
    classes = set()
    for g in re.findall(r'class=\\?"([^"\\]+)', trecho):
        classes.update(g.split())
    mortas = []
    for c in classes:
        esc = "." + "".join("\\" + ch if ch in ".:[]/%" else ch for ch in c)
        if not re.search(re.escape(esc) + r"(?=[\s,{:.>+~])", css):
            mortas.append(c)
    assert not mortas, "classes do botão que nascem invisíveis: %s" % mortas


def test_CONTROLE_o_detector_de_classe_morta_REPROVA():
    css = io.open(os.path.join(_RAIZ, "tailwind.min.css"), encoding="utf-8").read()
    assert not re.search(r"\.bg-violet-700(?=[\s,{:.>+~])", css)
    assert re.search(r"\.bg-indigo-50(?=[\s,{:.>+~])", css)
