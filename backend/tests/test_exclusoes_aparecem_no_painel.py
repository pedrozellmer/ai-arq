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


import json as _json_t  # noqa: E402
import urllib.request as _ureq_t  # noqa: E402

import pytest  # noqa: E402

import main as _m  # noqa: E402

_RETRATO = {"description": "Bancada de granito 3,20 m", "unit": "m",
            "quantity": 3.2, "discipline": "Marcenaria",
            "confidence": "confirmado"}
_LINHA_EXCLUSAO = {"job_id": "job-01", "item_id": None, "action": "reject",
                   "edits": {"_item_id": "it-1", "_antes": dict(_RETRATO)},
                   "comment": "", "reviewed_at": "2026-09-05T12:00:00+00:00"}
_LINHA_APROVACAO = {"job_id": "job-01", "item_id": "it-2", "action": "approve",
                    "edits": {}, "comment": "",
                    "reviewed_at": "2026-09-05T12:01:00+00:00"}
_LINHA_EDICAO = {"job_id": "job-02", "item_id": "it-3", "action": "edit",
                 "edits": {"quantity": 9.0}, "comment": "",
                 "reviewed_at": "2026-09-05T12:02:00+00:00"}
# 🪤 06/09/2026 — EXCLUSÃO SEM RETRATO. O `_antes` só passou a ser gravado em
# 31/08 ([[project_exclusao_se_autodestruia_20260831]]); as rejeições de antes
# disso — e qualquer uma que venha com `edits` vazio ou nulo — chegam SEM ele.
# O fixture só tinha a linha completa, então trocar `_antes_do_item` por um
# `r["edits"]["_antes"]` direto estouraria KeyError, o `except` engoliria e o
# painel INTEIRO viraria `{"erro": ...}` — as 48 exclusões some junto com as
# aprovações e edições. Verde, porque ninguém mandava a linha sem retrato.
_LINHA_EXCLUSAO_SEM_ANTES = {"job_id": "job-03", "item_id": None,
                             "action": "reject", "edits": None, "comment": "",
                             "reviewed_at": "2026-09-05T12:03:00+00:00"}
_LINHA_EXCLUSAO_2 = {"job_id": "job-02", "item_id": None, "action": "reject",
                     "edits": {"_item_id": "it-9",
                               "_antes": {"description": "Porta de correr 2,10 m",
                                          "unit": "un", "quantity": 1.0,
                                          "discipline": "Esquadrias",
                                          "confidence": "estimado"}},
                     "comment": "", "reviewed_at": "2026-09-05T12:04:00+00:00"}


class _RespT:
    def __init__(self, payload):
        self._b = _json_t.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _como_o_postgrest(linhas, url):
    """Responde como o PostgREST responderia: só as colunas do `select=`, na
    `order=` pedida, cortado no `limit=`.

    🪤 06/09/2026 — O FAKE DE ANTES IGNORAVA OS TRÊS. Devolvia a linha inteira,
    na ordem de entrada, sem limite. Com isso a rota podia parar de pedir
    `action` no `select` (todo `r.get("action")` viraria None e as exclusões
    voltariam a ser zero), ou pedir `limit=1`, e o guarda seguia verde — porque
    o banco de mentira era generoso onde o de verdade é literal.
    """
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(url).query)
    saida = [dict(r) for r in linhas]
    ordem = (q.get("order") or [""])[0]
    if ordem:
        col, _, direcao = ordem.partition(".")
        saida.sort(key=lambda r: str(r.get(col) or ""), reverse=(direcao == "desc"))
    sel = (q.get("select") or ["*"])[0]
    if sel and sel.strip() != "*":
        cols = [c.strip() for c in sel.split(",") if c.strip()]
        saida = [{c: r.get(c) for c in cols} for r in saida]
    lim = (q.get("limit") or [""])[0]
    if lim.isdigit():
        saida = saida[:int(lim)]
    return saida


@pytest.fixture
def painel(monkeypatch):
    """Chama `admin_revision_feedback` DE VERDADE, com o banco de mentira."""
    ctl = {"urls": [], "linhas": [], "url_item_reviews": None}
    monkeypatch.setattr(_m, "_require_admin", lambda r: {"email": "admin@example.com"})

    def _fake(req, timeout=None):
        url = getattr(req, "full_url", str(req))
        ctl["urls"].append(url)
        if "item_reviews" in url:
            ctl["url_item_reviews"] = url
            return _RespT(_como_o_postgrest(ctl["linhas"], url))
        return _RespT([])

    monkeypatch.setattr(_ureq_t, "urlopen", _fake)

    def _chamar(linhas):
        ctl["linhas"] = list(linhas)
        return _m.admin_revision_feedback(request=None)

    ctl["chamar"] = _chamar
    return ctl



# ══════════════════════════════════════════════════════════════════════════
#  1. O RESUMO CONTA E DESCREVE
# ══════════════════════════════════════════════════════════════════════════
def test_o_resumo_separa_as_exclusoes(painel):
    """O guarda antigo so exigia a palavra `"exclusoes"` num recorte do fonte.

    🪤 DUAS exclusoes, nao uma: com uma so, `rejeicoes[:1]` e um `break` no
    primeiro casamento ficavam verdes - e na base sao 48, de 6 projetos.
    """
    ri = painel["chamar"]([_LINHA_EXCLUSAO, _LINHA_EXCLUSAO_2, _LINHA_APROVACAO,
                           _LINHA_EDICAO])["revisao_inline"]
    assert ri["exclusoes"] == 2, (
        "o resumo do admin nao contou as duas exclusoes (contou %r) - os sinais "
        "de item inventado seguem invisiveis" % ri["exclusoes"])
    assert len(ri["exclusoes_itens"]) == 2, (
        "o painel recebeu %d retrato(s) para 2 exclusoes - o admin ve o numero "
        "e nao ve O QUE o motor inventou" % len(ri["exclusoes_itens"]))
    assert ri["aprovacoes"] == 1 and ri["edicoes"] == 1, (
        "a separacao por acao se embaralhou: %r" % ri)


def test_o_retrato_que_chega_ao_painel_e_o_do_ITEM_APAGADO(painel):
    """🪤 Presenca do campo nao basta: `"descricao": None` em toda linha passaria
    num teste de chave. O que o admin precisa e o CONTEUDO do `_antes`."""
    ri = painel["chamar"]([_LINHA_EXCLUSAO])["revisao_inline"]
    x = ri["exclusoes_itens"][0]
    assert x["descricao"] == _RETRATO["description"], (
        "a descricao do item apagado chegou como %r" % (x["descricao"],))
    assert x["unidade"] == _RETRATO["unit"], x
    assert x["quantidade"] == _RETRATO["quantity"], x
    assert x["disciplina"] == _RETRATO["discipline"], x
    assert x["selo"] == _RETRATO["confidence"], x
    assert x["job_id"] == "job-01" and x["quando"] == _LINHA_EXCLUSAO["reviewed_at"], x


def test_a_exclusao_SEM_retrato_nao_derruba_o_painel_inteiro(painel):
    """🩸 O `_antes` só é gravado desde 31/08. Rejeição anterior a isso (ou com
    `edits` nulo) chega sem retrato — e é a MAIORIA das 48. Se a leitura do
    retrato explodir, o `except` da rota engole e `revisao_inline` inteiro vira
    `{"erro": ...}`: some a exclusão, somem as aprovações, some tudo."""
    ri = painel["chamar"]([_LINHA_EXCLUSAO_SEM_ANTES, _LINHA_EXCLUSAO,
                           _LINHA_APROVACAO])["revisao_inline"]
    assert "erro" not in ri, (
        "a exclusao sem `_antes` derrubou o bloco inteiro: %r" % ri)
    assert ri["exclusoes"] == 2 and ri["aprovacoes"] == 1, ri
    sem = [x for x in ri["exclusoes_itens"] if x["job_id"] == "job-03"]
    assert len(sem) == 1, (
        "a exclusao sem retrato sumiu da lista - o admin nao fica sabendo que "
        "ela existiu: %r" % ri["exclusoes_itens"])
    assert sem[0]["descricao"] is None, (
        "sem `_antes` nao ha de onde tirar descricao; veio %r" % sem[0]["descricao"])


def test_a_consulta_PEDE_o_que_o_resumo_usa(painel):
    """🪤 O fake de antes ignorava `select`, `order` e `limit`, e a fixture
    guardava as URLs sem que ninguem afirmasse nada. Agora o banco de mentira
    responde SO o que foi pedido — entao esta afirmacao e sobre a requisicao que
    a rota fez de verdade, nao sobre o texto do fonte."""
    painel["chamar"]([_LINHA_EXCLUSAO, _LINHA_APROVACAO])
    url = painel["url_item_reviews"]
    assert url, "a rota nem consultou item_reviews"
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(url).query)
    cols = [c.strip() for c in q["select"][0].split(",")]
    for col in ("job_id", "action", "edits", "comment", "reviewed_at"):
        assert col in cols, (
            "a consulta parou de pedir a coluna `%s` — sem ela o resumo lê None "
            "e o sinal desaparece calado (select=%r)" % (col, q["select"][0]))
    assert q["order"][0] == "reviewed_at.desc", (
        "a ordem saiu de `reviewed_at.desc`: o corte em 500/20 passaria a "
        "descartar as revisoes MAIS NOVAS (order=%r)" % q.get("order"))
    assert int(q["limit"][0]) >= 500, (
        "o teto da consulta caiu para %r — as exclusoes antigas somem do "
        "painel sem ninguem avisar" % q.get("limit"))


def test_CONTROLE_a_rota_responde_e_o_bloco_da_revisao_inline_existe(painel):
    """Sem isto, um `revisao_inline` que virasse `{"erro": ...}` passaria."""
    ri = painel["chamar"]([_LINHA_APROVACAO])["revisao_inline"]
    assert "erro" not in ri, ri
    assert ri["aprovacoes"] == 1, ri


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
