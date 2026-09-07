# -*- coding: utf-8 -*-
"""O que o cliente DISSE atravessa o DELETE do reprocesso.

🩸 07/09/2026 — `item_reviews.item_id` tem **ON DELETE CASCADE**, e o
`/add-file` reprocessa NO MESMO job_id: apaga todas as linhas de
`project_items` e insere de novo. Cada revisão presa a uma linha ia junto,
em silêncio.

MEDIDO na base antes do conserto:
    413 revisões em job vivo
    364 morrem no cascade
     49 sobrevivem (as exclusões, que já têm item_id nulo)
      1 recado digitado em risco — o ÚNICO da história do produto

A gente passou a noite de 06/09 tornando aquele recado visível (ele tinha
ficado 4 dias invisível). Bastava o cliente anexar um arquivo pra ele sumir —
e sem rastro, porque `_arquivar_versao_anterior` guarda os ITENS, não as
revisões.

🔑 A casa já tinha visto METADE disto. `_spec_do_cliente_antes_do_swap` resgata
o que o cliente ESPECIFICOU (marca, cor, código) e o comentário lá diz por quê:
*"o cliente especifica 30 itens, anexa uma prancha, e perde os 30 — calado, com
e-mail de 'planilha atualizada'"*. A mesma frase valia para o que ele DISSE, e
ninguém tinha ligado os dois.

🪤 POR QUE `item_id = NULL` E NÃO RE-APONTAR. As 48 exclusões de 31/08 já vivem
assim, e o painel lê o retrato em `edits._antes`. Re-apontar exigiria casar por
descrição — que muda entre leituras — e a revisão iria parar no item errado.
Perder o vínculo é honesto; vincular errado é pior que não vincular.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

JOB = "17d6e1f2"


@pytest.fixture
def banco(monkeypatch):
    """Captura o PATCH que solta as revisões."""
    chamadas = []

    def _svc(metodo, caminho, corpo=None, **k):
        chamadas.append({"m": metodo, "path": caminho, "body": corpo})
        return (204, None)

    monkeypatch.setattr(main, "_supa_rest_service", _svc)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    return chamadas


# ═══════════════════════════════════════════════════════════════════════════
#  As revisões saem da FK antes do DELETE
# ═══════════════════════════════════════════════════════════════════════════

def test_solta_as_revisoes_do_job(banco):
    """🚨 O invariante: `item_id` vira NULL, então o DELETE não as leva."""
    main._soltar_revisoes_do_cascade(JOB)
    assert len(banco) == 1, "esperava um PATCH, veio %r" % banco
    c = banco[0]
    assert c["m"] == "PATCH", c["m"]
    assert c["body"] == {"item_id": None}, (
        "não soltou o vínculo — o CASCADE continua levando tudo: %r" % c["body"])


def test_mexe_SO_no_job_pedido(banco):
    """🪤 Sem o filtro por job, um reprocesso soltaria as revisões de TODOS os
    projetos da base — regra dura nº2 (isolamento) pelo avesso."""
    main._soltar_revisoes_do_cascade(JOB)
    caminho = banco[0]["path"]
    assert "job_id=eq.%s" % JOB in caminho, (
        "o PATCH não está preso a este job: %r" % caminho)


def test_nao_mexe_em_quem_JA_estava_solto(banco):
    """As 48 exclusões de 31/08 já têm `item_id` nulo. Mexer nelas à toa
    inflaria a contagem e sujaria o log sem motivo."""
    caminho = banco[0] if banco else None
    main._soltar_revisoes_do_cascade(JOB)
    assert "item_id=not.is.null" in banco[-1]["path"], (
        "o PATCH não filtra quem já está solto: %r" % banco[-1]["path"])
    del caminho


# ═══════════════════════════════════════════════════════════════════════════
#  Falhar não pode ser calado, nem derrubar a planilha
# ═══════════════════════════════════════════════════════════════════════════

def test_se_o_PATCH_falha_fica_o_rastro(monkeypatch):
    """🪤 Sem rastro, a perda das revisões seria invisível — que é exatamente
    como ela era antes deste conserto."""
    logs = []
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (500, None))
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job=None, **k: logs.append((stage, msg, job, k.get("severity"))))
    assert main._soltar_revisoes_do_cascade(JOB) == 0
    assert logs, "a falha sumiu sem rastro"
    stage, msg, job, sev = logs[0]
    assert "revisao" in stage and sev == "error"
    assert job == JOB
    assert "morrer" in msg, "o log não diz o que se perde: %r" % msg


def test_NUNCA_levanta_mesmo_com_o_banco_fora(monkeypatch):
    """🚨 A mesma regra do resgate irmão: perder o resgate é ruim, não entregar
    a planilha é pior. Se isto levantasse, o reprocesso inteiro morreria."""
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("banco fora")))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    assert main._soltar_revisoes_do_cascade(JOB) == 0   # devolve, não explode


# ═══════════════════════════════════════════════════════════════════════════
#  Está LIGADO no reprocesso, e ANTES do DELETE
# ═══════════════════════════════════════════════════════════════════════════

def test_o_resgate_roda_ANTES_do_delete():
    """🔑 Depois do DELETE não adianta: as linhas já foram. A ordem é o
    conserto inteiro."""
    import inspect
    fonte = inspect.getsource(main)
    i_solta = fonte.find("_soltar_revisoes_do_cascade(job_id)")
    i_del = fonte.find('project_items?job_id=eq.{job_id}", method=\'DELETE\'')
    assert i_solta > 0, "o resgate não é chamado no reprocesso — código morto"
    assert i_del > 0, "não achei o DELETE do swap"
    assert i_solta < i_del, (
        "o resgate roda DEPOIS do DELETE — as revisões já foram embora")


def test_o_resgate_da_ESPECIFICACAO_continua_de_pe():
    """🪤 O irmão dele não pode ter sido perdido no conserto de hoje: ele
    protege marca, cor e código que o cliente preencheu."""
    import inspect
    fonte = inspect.getsource(main)
    assert "_spec_do_cliente_antes_do_swap(job_id)" in fonte, (
        "sumiu o resgate da especificação — o cliente perde os 30 itens que "
        "especificou, calado, com e-mail de 'planilha atualizada'")


# ═══════════════════════════════════════════════════════════════════════════
#  🧪 Controle: o CASCADE é real
# ═══════════════════════════════════════════════════════════════════════════

def test_CONTROLE_a_FK_e_mesmo_CASCADE():
    """Se a FK deixar de ser CASCADE um dia, este arquivo inteiro vira
    desnecessário — e é bom que quem descobrir isso saiba por aqui, em vez de
    remover o resgate achando que nunca fez falta.

    🪤 O guarda não consulta o banco (a bancada roda sem rede): ele cobra a
    MIGRAÇÃO que criou a FK, que é o registro versionado da decisão.
    """
    import glob
    import io
    achou = False
    for p in glob.glob(os.path.join(_BACKEND, "migrations*", "*.sql")) + \
             glob.glob(os.path.join(_BACKEND, "*.sql")):
        s = io.open(p, encoding="utf-8", errors="replace").read().lower()
        if "item_reviews" in s and "cascade" in s:
            achou = True
    if not achou:
        pytest.skip("a migração da FK não está versionada aqui — medido no "
                    "banco em 07/09: item_reviews_item_id_fkey = CASCADE")
