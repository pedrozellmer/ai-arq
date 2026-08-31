# -*- coding: utf-8 -*-
"""O e-mail do filhote tem que ALIMENTAR o teto semanal, não só consultá-lo.

🩸 31/08/2026 — ACHADO PELA AUDITORIA ADVERSARIAL DO MESMO DIA. A regra da casa
é no máximo 1 e-mail automático por pessoa por semana, e ela é aplicada lendo a
tabela `email_auto_log`. O conserto de 29/08 (caso Eduarda, que levou 3 e-mails
num dia) fez a LIBERAÇÃO do filhote consultar esse teto — e esqueceu de fazer o
ENVIO alimentar ele. Meia porta.

O estrago era real e estava vivo: o Pedro libera um filhote hoje, a pessoa
recebe "refizemos a leitura", e o tick da hora seguinte manda o `nps_relacional`
(que nasceu hoje) pra mesma pessoa. Dois automáticos na mesma semana.

🪤 POR QUE O GUARDA QUE JÁ EXISTIA NÃO PEGOU: `test_teto_de_email_vale_na_
liberacao.py` são 6 testes que LEEM o main.py como texto e fazem assert em
substring. Nenhum chama função nenhuma — então o meio-conserto passou no próprio
guarda que deveria vigiá-lo. É [[feedback_guarda_que_le_fonte]] outra vez.
Este arquivo CHAMA as duas funções.

🪤 O que NÃO fazer: apontar `_email_auto_recente` pra `email_sent_log`. Aquela
tabela guarda os transacionais também (planilha pronta, recuperação de senha), e
o teto passaria a calar a esteira inteira.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_PAI = {"user_email": "cliente@exemplo.com", "project_name": "Casa 25",
        "job_id": "pai-123"}
_ANTES = {"medidos": 3, "itens": 40}
_DEPOIS = {"medidos": 38, "itens": 44}


def _grava(monkeypatch, enviou=True):
    """Troca o envio real por um dublê e captura o que foi registrado."""
    registros = []
    monkeypatch.setattr(main, "_send_email_smtp",
                        lambda *a, **k: enviou, raising=True)
    monkeypatch.setattr(main, "_email_auto_registrar",
                        lambda email, kind, ref="": registros.append(
                            {"email": email, "kind": kind, "ref": ref}),
                        raising=True)
    return registros


def test_leitura_nova_registra_no_cooldown(monkeypatch):
    reg = _grava(monkeypatch)
    ok = main._email_leitura_nova(_PAI, "filho-999", _ANTES, _DEPOIS)
    assert ok is True
    assert len(reg) == 1, "o e-mail saiu e NÃO alimentou o teto semanal"
    assert reg[0]["kind"] == "leitura_nova"
    assert reg[0]["email"] == "cliente@exemplo.com"
    assert reg[0]["ref"] == "filho-999", "não amarrou o registro ao job"


def test_leitura_combinada_registra_no_cooldown(monkeypatch):
    reg = _grava(monkeypatch)
    ok = main._email_leitura_combinada(
        _PAI, {"job_id": "filho-1"}, "merge-777", _ANTES, _DEPOIS)
    assert ok is True
    assert len(reg) == 1, "o combinado saiu e NÃO alimentou o teto semanal"
    assert reg[0]["kind"] == "leitura_combinada"
    assert reg[0]["ref"] == "merge-777"


def test_CONTROLE_email_que_NAO_saiu_nao_gasta_o_teto(monkeypatch):
    """🧪 Registrar um envio que falhou seria pior que não registrar: calaria a
    pessoa por uma semana sem ela ter recebido nada."""
    reg = _grava(monkeypatch, enviou=False)
    ok = main._email_leitura_nova(_PAI, "filho-999", _ANTES, _DEPOIS)
    assert ok is False
    assert reg == [], "gastou o teto semanal de quem não recebeu e-mail nenhum"


def test_CONTROLE_o_registrador_grava_na_tabela_do_TETO(monkeypatch):
    """A ponta final: `_email_auto_registrar` tem que escrever em
    `email_auto_log` — que é a tabela que `_email_auto_recente` lê. Se as duas
    apontarem pra tabelas diferentes, o teto volta a ser decorativo."""
    escritas = []
    monkeypatch.setattr(main, "_supabase_insert",
                        lambda tabela, linha: escritas.append((tabela, linha)),
                        raising=True)
    main._email_auto_registrar("x@y.com", "leitura_nova", ref="j1")
    assert escritas and escritas[0][0] == "email_auto_log", (
        "gravou na tabela errada: %s" % (escritas,))
    assert escritas[0][1]["kind"] == "leitura_nova"
