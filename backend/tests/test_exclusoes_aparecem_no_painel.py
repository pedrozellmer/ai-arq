# -*- coding: utf-8 -*-
"""As exclusões do cliente eram invisíveis no painel — e são o sinal mais forte.

🩸 05/09/2026. O resumo do admin separava `approve` e `edit` e ignorava
`reject`. Resultado: **48 exclusões, de 6 projetos**, gravadas desde 31/08 e
nunca lidas por ninguém.

🔑 Pelo comentário do próprio `submit_item_review`: *"exclusão é o sinal MAIS
direto de erro do motor — o cliente dizendo 'isto não existe na minha obra'"*.
Aprovação diz que acertamos; edição diz que erramos o número; **exclusão diz que
inventamos o item**.

🪤 O QUE foi apagado não está mais em `project_items`: a FK `item_reviews.item_id`
é ON DELETE CASCADE e o item some junto. O retrato vive em `edits._antes`,
gravado de propósito em 31/08 justamente porque a exclusão se autodestruía —
ver [[project_exclusao_se_autodestruia_20260831]]. Sem ler o `_antes`, o painel
mostraria "2 exclusões" e nada mais, que não serve pra nada.

🪤 É a terceira vez em dois dias que o mesmo defeito aparece: gravar o sinal e
não ler. Antes disso foi a revisão inline (01/08, 24 sinais parados) e o botão
"faltou um item" (05/09, nasceu cego no mesmo dia).
Ver [[feedback_o_aviso_tem_que_chegar]].
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

_RAIZ = os.path.dirname(_BACKEND)


def _main_py():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _admin_html():
    return io.open(os.path.join(_RAIZ, "admin.html"), encoding="utf-8").read()


def _bloco_do_resumo(src):
    """O dict `revisao_inline`, dos dois extremos — nunca janela fixa."""
    i = src.index('resumo["revisao_inline"] = {')
    return src[i:src.index('    except Exception as _e2:', i)]


# ══════════════════════════════════════════════════════════════════════════
#  1. O RESUMO CONTA E DESCREVE
# ══════════════════════════════════════════════════════════════════════════
def test_o_resumo_separa_as_exclusoes():
    bloco = _bloco_do_resumo(_main_py())
    assert '"exclusoes"' in bloco, (
        "o resumo do admin não conta as exclusões — 48 sinais de item "
        "inventado seguem invisíveis")


def test_o_resumo_manda_O_QUE_foi_apagado():
    """🪤 Só o número não serve: "2 exclusões" não diz o que a gente inventou."""
    bloco = _bloco_do_resumo(_main_py())
    assert '"exclusoes_itens"' in bloco
    for campo in ('"descricao"', '"unidade"', '"quantidade"', '"disciplina"', '"selo"'):
        assert campo in bloco, (
            "o resumo não manda %s do item apagado — sem isso não dá pra saber "
            "que tipo de item o motor inventa" % campo)


def test_le_o_retrato_ANTES_e_nao_a_tabela_de_itens():
    """O item não existe mais: a FK é ON DELETE CASCADE. Quem consultar
    `project_items` pelo item_id vai achar nada — foi assim que eu mesmo perdi
    as 48 rejeições num JOIN, em 04/09."""
    bloco = _bloco_do_resumo(_main_py())
    assert "_antes" in bloco, (
        "o resumo não lê o retrato `_antes` — o item apagado não está mais em "
        "project_items, então não há de onde tirar a descrição")


# ══════════════════════════════════════════════════════════════════════════
#  2. O PAINEL MOSTRA
# ══════════════════════════════════════════════════════════════════════════
def test_o_painel_tem_o_bloco_e_ele_ENTRA_no_html():
    """🩸 06/09/2026 — este guarda cobrava a linha inteira
    (`inlineHtml = faltouHtml + excHtml +`) e REPROVOU quando um bloco novo
    entrou na frente do "faltou". Ordem e vizinhos nunca foram o invariante:
    o fato é que `excHtml` entra no que a tela exibe. Reaproveita o mesmo
    verificador do guarda do "faltou um item", pra não haver duas réguas."""
    from test_faltou_um_item import entra_no_inlineHtml
    html = _admin_html()
    assert "excHtml" in html, "o painel não monta o bloco das exclusões"
    assert entra_no_inlineHtml(html, "excHtml"), (
        "o bloco existe mas não entra no que é exibido — código morto que "
        "passa em teste de existência")


def test_o_painel_escapa_o_que_veio_do_ITEM():
    """A descrição vem do motor, mas passou pela edição do cliente antes de ser
    apagada. Vai pro painel por innerHTML: sem escape, é porta de injeção."""
    html = _admin_html()
    i = html.index("excHtml")
    bloco = html[i:i + 1300]
    for campo in ("esc(x.descricao", "esc(x.job_id)", "esc(x.disciplina)"):
        assert campo in bloco, "campo sem escape no painel: %s" % campo


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES POSITIVOS
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_resumo_de_ANTES_e_reprovado():
    antes = '''
            resumo["revisao_inline"] = {
                "aprovacoes": len(aprov),
                "edicoes": len(edits),
                "projetos": 3,
            }
    except Exception as _e2:
'''
    bloco = antes[antes.index('resumo["revisao_inline"] = {'):]
    assert '"exclusoes"' not in bloco, (
        "o critério aprova o resumo que ignorava as exclusões — não julga nada")


def test_CONTROLE_bloco_montado_e_NAO_exibido_e_reprovado():
    """A regressão mais provável não é apagar o bloco — é esquecer de somá-lo."""
    orfao = "const excHtml = `...`;\nconst inlineHtml = faltouHtml + (cond ? `x` : '');"
    assert "inlineHtml = faltouHtml + excHtml +" not in orfao, (
        "o controle está mal montado")
