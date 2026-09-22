# -*- coding: utf-8 -*-
"""Reprocesso e re-tentativa automática não podem rodar o MESMO projeto juntos.

🩸 16/09/2026, ao vivo, cliente NOVO no primeiro projeto. A leitura caiu quatro
vezes por queda de conexão. Aconteceu isto, nesta ordem:

    14:58:36  auto-retry 1/2   — a varredura de 5 min agendou sozinha
    15:02:52  reprocesso       — a gente disparou pela mão (cria um FILHOTE)
    15:03:37  auto-retry 2/2   — a varredura subiu de novo, em PARALELO
    15:09:02  filhote fecha    — 46 itens → e-mail "sem quantidade medida"
    15:14:43  original fecha   — 67 itens → e-mail "planilha atualizada"

Dois motores no mesmo arquivo: dois resultados diferentes, IA paga duas vezes, e
DOIS e-mails em cinco minutos contando histórias diferentes pra quem estava
conhecendo o produto.

O e-mail duplicado é o sintoma; o trabalho duplicado é a doença. Por isso são
duas travas, e a de cima é a que importa:

  1. a varredura NÃO retenta projeto que já tem reprocesso vivo (ou pronto);
  2. cinto: o aviso de fim de job deduplica pela RAIZ da família (pai e filhote
     compartilham a mesma), não pelo job_id — que são dois.

🚨 Os guardas de 1 chamam `_auto_retry_erros_transitorios` de verdade; os de 2
rodam a fatia real do fim do `process_job` (`_fim_do_job`).
"""
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import main  # noqa: E402
from _fim_do_job import roda_ate_o_email  # noqa: E402

_PAI = "pai-0001"
_ERRO_PASSAGEIRO = ("⚠ Os servidores de IA estavam sobrecarregados neste "
                    "momento — é um problema temporário do provedor.")


# ── 1. a varredura não pisa no reprocesso ──────────────────────────────────
def _varredura(monkeypatch, filhotes, *, leitura_quebra=False, http=200, count=0):
    """Roda a varredura REAL com um projeto em erro e os filhotes informados.

    Devolve `(jobs que ela mandou retomar, alertas que saíram pro Pedro)`.
    """
    retomados = []
    alertas = []

    class _Resp:
        def read(self_):
            import json
            return json.dumps([{
                "job_id": _PAI, "user_email": "cliente-nn@example.com",
                "project_name": "projeto de teste",
                "error_message": _ERRO_PASSAGEIRO,
                "typology": "office", "project_type": "arquitetura",
                "auto_resume_count": count,
                "created_at": "2026-09-16T17:52:00Z"}]).encode("utf-8")

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())

    def _supa(metodo, caminho, **k):
        if leitura_quebra:
            raise RuntimeError("banco fora do ar")
        assert "parent_job_id=eq.%s" % _PAI in caminho, caminho
        if http != 200:
            return http, None
        return 200, [{"status": s} for s in filhotes]

    monkeypatch.setattr(main, "_supa_rest_service", _supa)
    # 21/09: `**k` — a re-tentativa passou a mandar `status_esperado="error"`;
    # com a assinatura exata este dublê quebraria (e o de produção, que é o
    # real, é engolido pelo laço periódico — a varredura morreria calada).
    monkeypatch.setattr(main, "_retomar_job_do_storage",
                        lambda j, t, p, **k: retomados.append(j) or True)
    monkeypatch.setattr(main, "_email_auto_ja_enviado", lambda *a, **k: False)
    monkeypatch.setattr(main, "_email_auto_registrar", lambda *a, **k: None)
    monkeypatch.setattr(main, "_notify_admin",
                        lambda assunto, corpo=" ", **k: alertas.append(corpo) or True)
    monkeypatch.setattr(main, "_error_log_causa_real", lambda *a, **k: "")
    monkeypatch.setattr(main, "_linha_do_email_ao_cliente", lambda *a, **k: "")
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)

    main._auto_retry_erros_transitorios()
    return retomados, alertas


def test_a_varredura_NAO_retenta_projeto_com_reprocesso_RODANDO(monkeypatch):
    """O caso exato de 16/09: às 15:03 havia filhote de 15:02 em andamento."""
    assert _varredura(monkeypatch, ["processing"])[0] == [], (
        "a varredura subiu um segundo motor no mesmo arquivo")


def test_a_varredura_NAO_retenta_quando_o_reprocesso_ja_FECHOU(monkeypatch):
    """Filhote pronto = o cliente já tem planilha. Retentar o pai só produz uma
    segunda planilha diferente e um segundo e-mail."""
    assert _varredura(monkeypatch, ["done"])[0] == []


def test_o_filhote_que_MORREU_nao_rouba_a_segunda_chance(monkeypatch):
    """🪤 Controle: se o reprocesso também falhou, a varredura é justamente
    quem ainda pode salvar o projeto — ela TEM que rodar."""
    assert _varredura(monkeypatch, ["error"])[0] == [_PAI]


def test_CONTROLE_sem_filhote_a_varredura_retenta_normalmente(monkeypatch):
    assert _varredura(monkeypatch, [])[0] == [_PAI]


def test_CONTROLE_tentativas_esgotadas_nao_retentam(monkeypatch):
    assert _varredura(monkeypatch, [], count=2)[0] == []


def test_leitura_quebrada_NAO_libera_dois_motores(monkeypatch):
    """🪤 Fail-closed de propósito: errar pra cá custa 5 minutos de espera;
    errar pro outro lado custa o motor rodando duas vezes no mesmo arquivo."""
    assert _varredura(monkeypatch, [], leitura_quebra=True)[0] == []


def test_resposta_de_erro_do_banco_tambem_segura(monkeypatch):
    """🪤 São DOIS caminhos de falha e só um levanta exceção: o banco pode
    responder 500 sem estourar nada. Quem cobre só o `except` deixa metade
    aberta."""
    assert _varredura(monkeypatch, [], http=500)[0] == []


def test_na_duvida_NAO_retenta_mas_o_alerta_SAI(monkeypatch):
    """🩸 Achado ao rodar os guardas vizinhos, não este arquivo: a 1ª versão
    deste conserto dava `continue` no bloco inteiro. Não re-tentava (certo) e
    também NÃO alertava (errado) — um projeto morto ficaria sem aviso nenhum
    por causa de uma leitura que falhou.

    🔑 As duas decisões têm preços opostos: motor em dobro é caro, aviso a mais
    é barato. Por isso a dúvida é um valor próprio, não sinônimo de 'tem
    filhote'.
    """
    retomados, alertas = _varredura(monkeypatch, [], leitura_quebra=True)
    assert retomados == [], "rodou um segundo motor sem saber se já tinha um"
    assert alertas, "o projeto morreu e ninguém foi avisado"
    assert "não consegui conferir" in alertas[0], (
        "o alerta mentiu a causa — dizer 'esgotou as tentativas' quando nem "
        "tentou é pior que não avisar: %r" % (alertas[0][:160],))


def test_quem_tem_filhote_NAO_vira_alerta(monkeypatch):
    """🪤 Controle do outro lado: com reprocesso em andamento não há o que o
    Pedro faça — alertar seria ruído."""
    retomados, alertas = _varredura(monkeypatch, ["processing"])
    assert retomados == [] and alertas == [], alertas


def test_CONTROLE_erro_terminal_de_verdade_continua_alertando(monkeypatch):
    retomados, alertas = _varredura(monkeypatch, [], count=2)
    assert retomados == []
    assert alertas and "esgotou as 2 re-tentativas" in alertas[0], alertas


# ── 2. o cinto: um aviso por família ───────────────────────────────────────
class _Item(object):
    def __init__(self, confidence="estimado"):
        self.description = "piso ceramico"
        self.unit = "m2"
        self.quantity = 10.0
        self.confidence = confidence
        self.discipline = "Pisos"
        self.origem = "ia"


def _fim(monkeypatch, *, ja_avisado, parent_job_id=None, reprocess_count=0):
    registros = []
    return roda_ate_o_email(
        [_Item(), _Item("confirmado")],
        parent_job_id=parent_job_id, reprocess_count=reprocess_count,
        antes_do_email={
            "_aviso_de_fim_recente": lambda *a, **k: ja_avisado,
            "_email_auto_registrar":
                lambda mail, kind, ref="", **k: registros.append((kind, ref)),
            "_registros_do_teste": registros,
        }), registros


def test_o_filhote_NAO_reavisa_quem_o_pai_ja_avisou(monkeypatch):
    with pytest.raises(AssertionError) as _e:
        _fim(monkeypatch, ja_avisado=True, parent_job_id=_PAI)
    assert "nenhum e-mail" in str(_e.value), (
        "o cinto não segurou: saiu um segundo aviso pro mesmo projeto")


def test_o_aviso_de_REPROCESSO_tambem_respeita_a_familia(monkeypatch):
    """🪤 São três ramos de e-mail no fim do job (complemento · reprocesso ·
    planilha pronta). O gate da FAMÍLIA vale nos dois últimos; este é o ramo que
    mandou o segundo e-mail em 16/09 — `reprocess_count>0`.
    🩸 21/09: o complemento (anexo) saiu deste gate e tem trava própria, por
    rodada — "tem que receber e-mail em todos" (Pedro). Ver
    test_todo_anexo_avisa_o_cliente.py."""
    with pytest.raises(AssertionError) as _e:
        _fim(monkeypatch, ja_avisado=True, reprocess_count=1)
    assert "nenhum e-mail" in str(_e.value), (
        "o ramo do reprocesso furou o gate da família")


def test_CONTROLE_o_reprocesso_avisa_quando_ninguem_avisou_ainda(monkeypatch):
    diario, _reg = _fim(monkeypatch, ja_avisado=False, reprocess_count=1)
    assert diario["emails"], "quem reprocessa sozinho ficou sem aviso nenhum"
    assert "reprocess" in (diario["emails"][-1]["kind"] or ""), diario["emails"][-1]["kind"]


def test_CONTROLE_projeto_sem_aviso_recente_continua_avisando(monkeypatch):
    diario, _reg = _fim(monkeypatch, ja_avisado=False)
    assert diario["emails"], "o cliente ficou sem o aviso de planilha pronta"


def test_a_chave_do_dedup_e_a_RAIZ_e_nao_o_job(monkeypatch):
    """🔑 O defeito era a chave: pai e filhote são dois `job_id`, então dedup
    por job nunca veria o irmão. A família tem uma raiz só."""
    _diario, registros = _fim(monkeypatch, ja_avisado=False, parent_job_id=_PAI)
    fim = [r for r in registros if r[0] == "fim_de_job"]
    assert fim, "o aviso saiu sem registrar a ficha da família"
    assert fim[0][1] == _PAI, (
        "registrou com a chave errada (%r) — o irmão não vai enxergar" % (fim[0][1],))


def test_na_duvida_o_aviso_SAI(monkeypatch):
    """🪤 Ao contrário do resto desta casa, este gate ENVIA quando não consegue
    ler: o duplo já morre na trava de cima, e um e-mail a mais é muito melhor
    que o cliente nunca saber que a planilha ficou pronta."""
    def _explode(*a, **k):
        raise RuntimeError("banco fora do ar")
    monkeypatch.setattr(urllib.request, "urlopen", _explode)
    assert main._aviso_de_fim_recente("cliente-nn@example.com", _PAI) is False
