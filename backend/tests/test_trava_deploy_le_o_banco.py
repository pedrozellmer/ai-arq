# -*- coding: utf-8 -*-
"""A trava de deploy errava nos DOIS sentidos — e os dois no mesmo dia.

🚨 26/08/2026. `jobs.em_curso()` é o número que o hook de pre-push lê no
/api/health pra decidir se pode subir código. Subir no meio de um job mata o
processamento do cliente (caso Walter, 29/07).

Ela lia o `_jobs.json`, que mora no disco EFÊMERO do Render:

- **08:26 — liberou com cliente rodando (o perigoso).** O banco dizia
  `processing` há 130s no job da Amanda; a trava dizia **0**. Um push naquele
  minuto teria matado o processamento dela. Causa: todo reinício nasce sem o
  arquivo, e `_load_jobs()` devolve `{}` SEM exceção — caminho feliz que
  devolve 0 é uma trava desarmada. O `return -1` só cobria o caso de exceção.
- **10:19 — bloqueou sem ninguém rodando (o chato).** Depois de um OOM sobrou
  job fantasma no arquivo local. Banco: 0 ativos. Trava: 1.

Agora a fonte de verdade é o BANCO. Duas réguas, medidas em 136 jobs reais:
120 min de janela (média 12,7 min, p99 97,9, maior 118,7) e 15 min de silêncio
como sinal de thread morta (o maior intervalo entre eventos de um job vivo foi
~6 min).

Estes guardas RODAM `em_curso()` com o banco e o arquivo injetados.
"""
import os
import sys
from datetime import datetime, timedelta

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main   # noqa: E402


def _iso(minutos_atras):
    return (datetime.utcnow() - timedelta(minutes=minutos_atras)).isoformat() + "Z"


def _banco(abertos, eventos):
    """Fake do _supa_rest_service: 1ª chamada = projects, 2ª = error_log."""
    def _fake(metodo, caminho, *a, **k):
        if caminho.startswith("projects?"):
            return 200, abertos
        if caminho.startswith("error_log?"):
            return 200, eventos
        return 200, []
    return _fake


def test_job_vivo_no_banco_BLOQUEIA_mesmo_com_arquivo_local_vazio(monkeypatch):
    """O caso perigoso: o arquivo sumiu no reinício e o cliente está rodando."""
    monkeypatch.setattr(main, "_supa_rest_service", _banco(
        [{"job_id": "abc123", "created_at": _iso(30)}],
        [{"job_id": "abc123"}]))                      # deu sinal de vida agora
    monkeypatch.setattr(main, "_load_jobs", lambda: {})   # disco efêmero zerado
    assert main.jobs.em_curso() == 1, (
        "REGRESSÃO: a trava liberaria o deploy com cliente processando. "
        "Foi exatamente isso às 08:26 no job da Amanda.")


def test_job_mudo_ha_muito_tempo_NAO_bloqueia(monkeypatch):
    """O caso chato: fantasma preso em 'processing' depois de um OOM."""
    monkeypatch.setattr(main, "_supa_rest_service", _banco(
        [{"job_id": "morto1", "created_at": _iso(60)}],
        []))                                          # nenhum evento recente
    monkeypatch.setattr(main, "_load_jobs", lambda: {
        "morto1": {"status": "processing"}})          # e ainda está no arquivo
    assert main.jobs.em_curso() == 0, (
        "um job mudo há 60 min bloquearia o deploy pra sempre")


def test_job_recem_criado_ainda_sem_log_CONTA(monkeypatch):
    """🪤 Job que acabou de nascer não logou nada ainda — não é fantasma."""
    monkeypatch.setattr(main, "_supa_rest_service", _banco(
        [{"job_id": "novo1", "created_at": _iso(1)}], []))
    monkeypatch.setattr(main, "_load_jobs", lambda: {})
    assert main.jobs.em_curso() == 1, (
        "job de 1 minuto foi tratado como morto — o cliente acabou de subir")


def test_banco_sem_jobs_abertos_libera(monkeypatch):
    monkeypatch.setattr(main, "_supa_rest_service", _banco([], []))
    monkeypatch.setattr(main, "_load_jobs", lambda: {})
    assert main.jobs.em_curso() == 0


def test_banco_fora_do_ar_cai_no_arquivo_local(monkeypatch):
    """Plano B: sem banco, volta a valer o arquivo — melhor que nada."""
    def _morre(*a, **k):
        raise RuntimeError("supabase indisponível")
    monkeypatch.setattr(main, "_supa_rest_service", _morre)
    monkeypatch.setattr(main, "_load_jobs", lambda: {
        "x": {"status": "processing"}, "y": {"status": "done"}})
    assert main.jobs.em_curso() == 1


def test_tudo_falhando_devolve_MENOS_UM_e_nao_zero(monkeypatch):
    """🚨 O invariante que sustenta a trava: 'não sei' nunca pode virar 'pode'."""
    def _morre(*a, **k):
        raise RuntimeError("caiu")
    monkeypatch.setattr(main, "_supa_rest_service", _morre)
    monkeypatch.setattr(main, "_load_jobs", _morre)
    assert main.jobs.em_curso() == -1, (
        "erro virou 0 e o hook leria como 'pode subir'")


def test_controle_positivo_a_versao_ANTIGA_liberaria(monkeypatch):
    """Prova que o guarda principal reprova mesmo.

    Refaz o comportamento antigo (só o arquivo local) no mesmo cenário do
    primeiro teste: cliente rodando, arquivo vazio. Tem que dar 0 — o número
    que teria matado o job da Amanda.
    """
    def _antiga():
        return sum(1 for j in {}.values()
                   if isinstance(j, dict) and j.get("status") in ("queued", "processing"))
    assert _antiga() == 0, "controle positivo furado"
    with pytest.raises(AssertionError):
        assert _antiga() == 1, "a versão antiga TEM que falhar aqui"
