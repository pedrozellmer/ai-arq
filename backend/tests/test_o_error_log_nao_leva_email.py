# -*- coding: utf-8 -*-
"""Nenhum e-mail de cliente entra no `error_log` (22/09/2026).

Nasceu do alerta de NPS e cresceu com a varredura da TABELA, que achou **32
linhas com endereço em 7 stages** — duas famílias que a varredura do CÓDIGO
tinha perdido, porque montam a mensagem com `%s` em vez de f-string. As 32
foram mascaradas no banco no mesmo dia (viraram `user=<8 do user_id>`).

🩸 Medido em 22/09: TODAS as 8 linhas `nps:*-alerta` do `error_log` (4 de
promotor, 2 de neutro, 2 de detrator, de 02/09 a 22/09) tinham o endereço do
cliente em texto puro. A linha era
`f"... score_guardado={_nota} {row.get('user_email')} avisei_admin=..."`.

O AVISO ao Pedro continua levando o contato — ele precisa saber a quem
responder. O LOG é técnico: leva `user_id[:8]` e o `job_id`, que são opacos.
É a mesma regra que o `_alerta_recado` já seguia desde 06/09
(`test_recado_do_cliente_toca_campainha.py`); o NPS era o irmão esquecido.
A mesma varredura achou três `avaliacao:*` da nota por e-mail com o mesmo
defeito — guardados no fim deste arquivo.

Estes guardas EXECUTAM `_alerta_nps` de verdade, com a thread trocada por uma
chamada imediata e só as bordas dubladas (aviso, banco, log). Todos os dublês
aceitam `**k`: dublê de assinatura exata desarma calado quando a função real
ganha parâmetro novo (16 e 18/09).

🪤 `_alerta_nps` engole qualquer exceção dentro da thread (é best-effort). Se
um dublê quebrar, o alerta morre calado e o log fica VAZIO — e "nenhum e-mail
no log" passaria por mérito falso. Por isso todo teste exige primeiro que a
linha de log EXISTA, e só depois olha o que tem dentro.
"""
import os
import re
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

#: O MESMO padrão da consulta de 22/09 no banco — o guarda mede o que a
#: auditoria mediu, não uma versão mais frouxa.
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_EMAIL = "cliente-nn@example.com"
_UID = "a1b2c3d4-0000-4000-8000-000000000001"
_JOB = "5e7f9a0b-0000-4000-8000-000000000002"

_FAIXAS = [("promoter", 9), ("passive", 7), ("detractor", 2)]


class _ThreadImediata:
    """Roda o alvo na hora, no lugar da thread (mesmo truque do teste do
    recado: classe de verdade, `start` chama o alvo sem argumento)."""

    def __init__(self, target=None, *a, **k):
        self._alvo = target

    def start(self):
        if self._alvo:
            self._alvo()


@pytest.fixture
def bordas(monkeypatch):
    """Dubla aviso, banco e log; devolve o que cada um recebeu."""
    logs, avisos = [], []

    def _log(*a, **k):
        stage = a[0] if len(a) > 0 else k.get("stage")
        msg = a[1] if len(a) > 1 else k.get("message")
        job = a[2] if len(a) > 2 else k.get("job_id")
        logs.append({"stage": str(stage), "msg": str(msg), "job": job})

    def _aviso(*a, **k):
        avisos.append(" ".join(str(x) for x in list(a) + list(k.values())))
        return True

    monkeypatch.setattr(main, "_log_error", _log)
    monkeypatch.setattr(main, "_notify_admin", _aviso)
    monkeypatch.setattr(main, "_supa_rows", lambda *a, **k: [
        {"project_name": "Projeto Teste", "status": "done",
         "files_count": 2, "file_types": "pdf"}])
    monkeypatch.setattr(threading, "Thread", _ThreadImediata)
    return logs, avisos


def _linha(**sobre):
    base = {"user_id": _UID, "user_email": _EMAIL, "user_name": "cliente-nn",
            "score": 9, "comment": "Gostei", "context": "after_download",
            "job_id": _JOB}
    base.update(sobre)
    return base


def _log_do_alerta(logs, categoria):
    achados = [x for x in logs if x["stage"] == "nps:%s-alerta" % categoria]
    assert len(achados) == 1, (
        "esperava 1 linha `nps:%s-alerta` no log e vieram %d — o alerta "
        "morreu calado dentro da thread? logs=%r" % (categoria, len(achados), logs))
    return achados[0]


@pytest.mark.parametrize("categoria,nota", _FAIXAS)
def test_o_log_do_alerta_NAO_leva_email_de_cliente(bordas, categoria, nota):
    """O invariante: nenhuma das três faixas grava endereço no `error_log`."""
    logs, _ = bordas
    main._alerta_nps(_linha(score=nota), categoria)
    linha = _log_do_alerta(logs, categoria)
    m = _RE_EMAIL.search(linha["msg"])
    assert m is None, (
        "o e-mail do cliente (%s) foi parar no error_log em `nps:%s-alerta` — "
        "regra dura nº6. Mensagem: %r" % (m.group(0), categoria, linha["msg"]))


@pytest.mark.parametrize("categoria,nota", _FAIXAS)
def test_o_log_leva_o_identificador_OPACO(bordas, categoria, nota):
    """Tirar o e-mail não pode deixar a linha sem dono: ela leva o user_id
    truncado a 8 e o job_id (na mensagem e na coluna)."""
    logs, _ = bordas
    main._alerta_nps(_linha(score=nota), categoria)
    linha = _log_do_alerta(logs, categoria)
    assert "user=" + _UID[:8] in linha["msg"], linha["msg"]
    assert _UID not in linha["msg"], (
        "o user_id foi INTEIRO pro log — o combinado é truncar a 8")
    assert "job=" + _JOB in linha["msg"], linha["msg"]
    assert linha["job"] == _JOB, "a coluna job_id do error_log ficou vazia"


def test_sem_user_id_e_sem_job_o_log_segue_sem_email(bordas):
    """A porta da nota por e-mail (`email_relacional`) monta a linha com
    `job_id=""` e, se o perfil não for achado, `user_id=""`. Sem identificador
    opaco à mão, a tentação é voltar ao e-mail — o log fica com marcadores."""
    logs, _ = bordas
    main._alerta_nps(_linha(user_id="", job_id="", context="email_relacional"),
                     "promoter")
    linha = _log_do_alerta(logs, "promoter")
    assert _RE_EMAIL.search(linha["msg"]) is None, linha["msg"]
    assert "user=?" in linha["msg"] and "job=-" in linha["msg"], linha["msg"]


@pytest.mark.parametrize("categoria,nota", _FAIXAS)
def test_CONTROLE_o_aviso_ao_Pedro_CONTINUA_levando_o_contato(bordas, categoria, nota):
    """O outro lado: o e-mail sai do LOG, não do AVISO — o Pedro responde a
    alguém. E é o controle de que o endereço estava mesmo na entrada: sem
    isto, o teste do log passaria por não ter e-mail nenhum pra vazar."""
    _, avisos = bordas
    main._alerta_nps(_linha(score=nota), categoria)
    assert avisos, "o alerta não chegou a montar o aviso ao Pedro"
    assert any(_EMAIL in a for a in avisos), (
        "o aviso ao Pedro perdeu o contato do cliente — ele não tem a quem "
        "responder: %r" % avisos)


# ─────────────────────────────────────────────────────────────────────────────
#  Os irmãos da mesma porta — a nota que chega pelo e-mail (`/api/avaliar`)
# ─────────────────────────────────────────────────────────────────────────────
#  Achados na varredura do código de 22/09: três `_log_error` da avaliação
#  interpolavam o e-mail de quem respondeu. Mesmo tipo do alerta de NPS: o
#  endereço não é o que se diagnostica ali, e há identificador opaco à mão.

def _sem_email(logs, stage):
    achados = [x for x in logs if x["stage"] == stage]
    assert len(achados) == 1, (
        "esperava 1 linha `%s` no log e vieram %d: %r" % (stage, len(achados), logs))
    m = _RE_EMAIL.search(achados[0]["msg"])
    assert m is None, (
        "o e-mail do cliente (%s) foi parar no error_log em `%s` — regra dura "
        "nº6. Mensagem: %r" % (m.group(0), stage, achados[0]["msg"]))
    return achados[0]


def test_nota_baixa_da_entrega_NAO_leva_email_pro_log(bordas):
    """`_alerta_avaliacao_projeto` é cópia estrutural do `_alerta_nps`."""
    logs, avisos = bordas
    main._alerta_avaliacao_projeto(_JOB, _EMAIL, 1)
    linha = _sem_email(logs, "avaliacao:nota-baixa")
    assert "job=" + _JOB in linha["msg"] and linha["job"] == _JOB, linha
    assert any(_EMAIL in a for a in avisos), (
        "o aviso ao Pedro perdeu o contato do cliente: %r" % avisos)


def test_nps_por_email_que_NAO_gravou_nao_leva_email_pro_log(bordas, monkeypatch):
    logs, _ = bordas
    monkeypatch.setattr(main, "_supa_rows", lambda *a, **k: (
        [{"user_id": _UID, "full_name": "cliente-nn"}] if "profiles" in a else []))
    monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: False)
    monkeypatch.setattr(main, "_alerta_nps", lambda *a, **k: None)
    with pytest.raises(main.HTTPException) as ex:
        main.registrar_avaliacao(main.NotaAvaliacao(
            tipo="nps", e=_EMAIL, t=main._nota_token("nps", _EMAIL), n=8))
    assert ex.value.status_code == 502
    linha = _sem_email(logs, "avaliacao:nao-gravou")
    assert "user=" + _UID[:8] in linha["msg"], linha["msg"]


def test_comentario_de_nps_que_falhou_nao_leva_email_pro_log(bordas, monkeypatch):
    logs, _ = bordas
    monkeypatch.setattr(main, "_supa_rows", lambda *a, **k: [{"id": 77}])

    def _caiu(*a, **k):
        raise RuntimeError("PATCH caiu")

    monkeypatch.setattr(main, "_supa_rest_service", _caiu)
    with pytest.raises(main.HTTPException) as ex:
        main.avaliar_comentario(main.ComentarioAvaliacao(
            tipo="nps", e=_EMAIL, t=main._nota_token("nps", _EMAIL),
            texto="faltou o forro"))
    assert ex.value.status_code == 502
    linha = _sem_email(logs, "avaliacao:comentario-falhou")
    assert "resposta=77" in linha["msg"] and "PATCH caiu" in linha["msg"], linha["msg"]


# ─────────────────────────────────────────────────────────────────────────────
#  A recusa de upload — a porta única por onde passam as 10 recusas
# ─────────────────────────────────────────────────────────────────────────────
#  `upload:recusado` guardava `quem=<endereço>` (2 linhas em 13/09, as duas da
#  porta `sem-login`). Os chamadores passam user_id; o endereço que ainda
#  chegar vira apelido estável dentro do `_recusa_no_upload`.

def test_a_mascara_troca_o_endereco_e_mantem_o_resto(bordas):
    """`_sem_email_no_log` é a peça que as duas portas usam."""
    texto = ("SMTPRecipientsRefused: {'%s': (550, b'User unknown')}" % _EMAIL)
    saida = main._sem_email_no_log(texto)
    assert _RE_EMAIL.search(saida) is None, saida
    assert "550" in saida and "SMTPRecipientsRefused" in saida, (
        "a máscara comeu o diagnóstico junto com o endereço: %r" % saida)
    assert main._sem_email_no_log(texto) == saida, "o apelido mudou entre chamadas"
    assert main._sem_email_no_log("sem endereço nenhum") == "sem endereço nenhum"


def _apelido(msg):
    m = re.search(r"quem=(\S+)", msg)
    assert m, msg
    return m.group(1)


def test_recusa_de_upload_NAO_leva_email_pro_log(bordas):
    logs, _ = bordas
    with pytest.raises(main.HTTPException):
        main._recusa_no_upload(401, "Faça login para enviar um projeto.",
                               "sem-login", quem=_EMAIL)
    linha = _sem_email(logs, "upload:recusado")
    assert _apelido(linha["msg"]).startswith("u:"), linha["msg"]


def test_o_apelido_da_recusa_e_ESTAVEL_e_nao_depende_da_caixa(bordas):
    """Tirar o e-mail não pode custar a única coisa que a linha ensinava: que
    foi a MESMA pessoa nas duas tentativas de 13/09."""
    logs, _ = bordas
    for quem in (_EMAIL, _EMAIL.upper(), "  " + _EMAIL + "  "):
        with pytest.raises(main.HTTPException):
            main._recusa_no_upload(401, "x", "sem-login", quem=quem)
    recusas = [x for x in logs if x["stage"] == "upload:recusado"]
    assert len(recusas) == 3, logs
    apelidos = {_apelido(x["msg"]) for x in recusas}
    assert len(apelidos) == 1, ("a mesma pessoa gerou apelidos diferentes: %r" % apelidos)
    outro = "outra-pessoa@example.com"
    with pytest.raises(main.HTTPException):
        main._recusa_no_upload(401, "x", "sem-login", quem=outro)
    ultima = [x for x in logs if x["stage"] == "upload:recusado"][-1]["msg"]
    assert _apelido(ultima) not in apelidos, (
        "duas pessoas diferentes caíram no mesmo apelido: %r" % ultima)


def test_recusa_com_user_id_guarda_o_ID_inteiro(bordas):
    """Quem tem token entra pelo id — nada a mascarar, e o diagnóstico fica
    melhor do que era com o e-mail."""
    logs, _ = bordas
    with pytest.raises(main.HTTPException):
        main._recusa_no_upload(403, "x", "token-nao-bate", quem=_UID,
                               detalhe="form=%s token=%s" % (_UID, _UID))
    linha = _sem_email(logs, "upload:recusado")
    assert _apelido(linha["msg"]) == _UID, linha["msg"]


def test_CONTROLE_o_padrao_ACHA_o_email_no_formato_antigo():
    """O detector prova que reprova: a mensagem exatamente como o código
    gravava até 22/09 tem que casar com o padrão."""
    antiga = ("resposta='9 de 10' score_guardado=9 %s avisei_admin=True" % _EMAIL)
    m = _RE_EMAIL.search(antiga)
    assert m and m.group(0) == _EMAIL
