# -*- coding: utf-8 -*-
"""27/09/2026 — as duas peças do tick horário que o Pedro escolheu:
  • "Anonimizar após 12 meses": a `email_sent_log` perde endereço, assunto e job das linhas com mais de 12 meses
    (fica o tipo e a data — o volume por tipo da Central segue contando). E-mail VAZIO, não texto fixo: as funções
    do admin já pulam o vazio e nenhum cruzamento por e-mail casa com ele;
  • "Resumo diário" das @menções: a marca do dia vai no e-mail INTERNO (a do aviso de cadastro) — no e-mail da pessoa
    ela entraria no teto semanal dos e-mails de marketing dela.
E o guarda que faltava: o guarda da Central só lê o main.py, e os e-mails do Escritório saem de outros módulos.
"""
import inspect
import os
import re
import sys
from datetime import datetime, timedelta

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


class LogFiel:
    """A `email_sent_log` em memória, filtrando o PATCH como o PostgREST (lt. na data, neq. no e-mail)."""
    def __init__(self, linhas):
        self.linhas, self.chamadas = linhas, []

    def __call__(self, method, path, body=None, params=None, prefer=None, timeout=15):
        self.chamadas.append((method, path, body, params, prefer))
        assert method == "PATCH" and path.strip("/") == "email_sent_log"
        assert set(params) <= {"sent_at", "email", "select"}, params
        corte, fora = params["sent_at"], params["email"]
        assert corte.startswith("lt.") and fora.startswith("neq.")
        alvo = [x for x in self.linhas if x["sent_at"] < corte[3:] and x["email"] != fora[4:]]
        for x in alvo:
            x.update(body)
        return 200, [{"id": x["id"]} for x in alvo]


@pytest.fixture
def _dia_limpo(monkeypatch):
    monkeypatch.setitem(main._EMAIL_LOG_ANONIMIZADO, "dia", None)
    erros = []
    monkeypatch.setattr(main, "_log_error", lambda stage, msg, *a, **k: erros.append((stage, msg)))
    return erros


def _quando(dias_atras):
    return (datetime.utcnow() - timedelta(days=dias_atras)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_linha_de_mais_de_12_meses_perde_endereco_assunto_e_job_e_fica_tipo_e_data(monkeypatch, _dia_limpo):
    velha = {"id": 1, "email": "cliente@exemplo.com", "subject": "Fulana te convidou: Casa", "job_id": "job-1",
             "kind": "escritorio_convite", "sent_at": _quando(400)}
    ja_feita = {"id": 2, "email": "", "subject": None, "job_id": None, "kind": "boas_vindas", "sent_at": _quando(500)}
    recente = {"id": 3, "email": "cliente@exemplo.com", "subject": "Sua planilha", "job_id": "job-2",
               "kind": "leitura_nova", "sent_at": _quando(300)}
    log = LogFiel([velha, ja_feita, recente])
    monkeypatch.setattr(main, "_supa_rest_service", log)
    assert main._anonimizar_emails_antigos() == {"status": "ok", "anonimizadas": 1}
    assert velha == {"id": 1, "email": "", "subject": None, "job_id": None, "kind": "escritorio_convite",
                     "sent_at": velha["sent_at"]}
    assert recente["email"] == "cliente@exemplo.com" and recente["job_id"] == "job-2"      # controle: 300 dias fica
    # o corte é 12 meses (365 dias), não "uns meses"
    corte = datetime.strptime(log.chamadas[0][3]["sent_at"][3:], "%Y-%m-%dT%H:%M:%SZ")
    assert abs((datetime.utcnow() - corte) - timedelta(days=365)) < timedelta(minutes=5)


def test_uma_vez_por_dia(monkeypatch, _dia_limpo):
    log = LogFiel([])
    monkeypatch.setattr(main, "_supa_rest_service", log)
    main._anonimizar_emails_antigos()
    assert main._anonimizar_emails_antigos() == {"status": "ja_rodou_hoje"} and len(log.chamadas) == 1


def test_falha_registra_e_tenta_de_novo_no_proximo_tick(monkeypatch, _dia_limpo):
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (500, None))
    assert main._anonimizar_emails_antigos() == {"status": "erro"}
    assert _dia_limpo and _dia_limpo[0][0] == "email-log:anonimizar"
    log = LogFiel([])
    monkeypatch.setattr(main, "_supa_rest_service", log)
    assert main._anonimizar_emails_antigos()["status"] == "ok" and len(log.chamadas) == 1


def test_a_marca_do_resumo_vai_no_email_interno_e_diz_se_era_a_primeira(monkeypatch):
    feitas = []

    def banco(method, path, body=None, params=None, prefer=None, timeout=15):
        feitas.append((method, path, body, prefer))
        return (201, [dict(body)]) if len(feitas) == 1 else (201, [])       # a 2ª bate na chave única
    monkeypatch.setattr(main, "_supa_rest_service", banco)
    assert main._marcar_resumo_de_mencoes("2026-09-27:uid-1") is True
    assert main._marcar_resumo_de_mencoes("2026-09-27:uid-1") is False
    metodo, caminho, corpo, prefer = feitas[0]
    assert metodo == "POST" and "on_conflict=email,kind,ref" in caminho
    assert corpo == {"email": main.NOTIFY_EMAIL, "kind": "escritorio_mencoes", "ref": "2026-09-27:uid-1"}
    assert "ignore-duplicates" in prefer and "return=representation" in prefer
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (500, None))
    assert main._marcar_resumo_de_mencoes("2026-09-27:uid-1") is None


def test_o_tick_anonimiza_antes_da_chave_dos_emails_e_resume_as_mencoes_depois_dela():
    src = inspect.getsource(main.emails_auto_tick)
    chave = src.index('if os.environ.get("EMAILS_AUTO", "1") == "0":')
    # reter menos não pode depender de e-mail ligado (como a faxina do Drive)
    assert src.index("_anonimizar_emails_antigos()") < chave
    assert chave < src.index("_menc.rodada(now, _marcar_resumo_de_mencoes, dry=bool(dry))")
    assert src.count('"mencoes": _mencoes') == 2              # a resposta do dry e a do envio contam as menções


def test_todo_email_do_escritorio_tem_ficha_na_central():
    import escritorio_mencoes
    usados = {escritorio_mencoes.KIND}
    for nome in ("escritorio.py", "escritorio_drive.py", "escritorio_mencoes.py"):
        with open(os.path.join(_BACKEND, nome), encoding="utf-8") as f:
            usados |= set(re.findall('log_kind="([a-z_]+)"', f.read()))
    assert {"escritorio_emissao_cliente", "escritorio_mencoes"} <= usados     # controle: o guarda enxerga os novos
    sem_ficha = usados - {c["key"] for c in main._EMAIL_CATALOG}
    assert not sem_ficha, f"e-mail do Escritório sem ficha na Central: {sorted(sem_ficha)}"
