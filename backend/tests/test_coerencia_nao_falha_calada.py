# -*- coding: utf-8 -*-
"""A regra dura nº7 não pode dizer "tudo em dia" quando não conseguiu conferir.

🩸 08/09/2026 — PROVADO RODANDO, depois de uma varredura por instrumentos
mortos. O log `coerencia:projeto` existe desde 02/08 e **nunca disparou em
produção**: 0 linhas em 5.464 eventos do `error_log`, em 37 dias.

Não era sorte. O `except` da rota é inalcançável, porque todo ajudante engole a
própria falha e devolve valor benigno:
  · `_assinatura_atual` devolve "" em qualquer exceção (só um `print`);
  · `_supabase_get_cronograma` devolve None tanto pra "não existe" quanto pra
    "não consegui ler" — a docstring de `_fin_cronograma_salvo` já dizia isso;
  · `_supa_rest_service` NUNCA levanta: devolve (0, None) ou (código, None).

Medido com o Supabase 100% fora do ar — URLError, HTTP 500 e conexão resetada,
os três dando o mesmo resultado:

    tudo_em_dia=True   desatualizados=[]   erro=None   logs=0

Ou seja: **"não consegui conferir" saía IDÊNTICO a "está tudo em dia"**. O
cliente não via banner nenhum e baixava cronograma e memorial velhos pra mandar
pro cliente dele — que é exatamente o que a regra nº7 existe pra impedir.

🪤 E o caso pior não é o silêncio total: é a falha PARCIAL. Com a leitura do
memorial caindo e a planilha velha, a resposta vinha `desatualizados:['planilha']`
e o memorial SUMIA da lista. A resposta parece saudável — o cliente lê "só a
planilha está velha", conclui que o resto está fresco, e manda o memorial velho.

🔑 O conserto não é um `except` melhor: é parar de depender de exceção. Cada
leitura que falha marca o entregável como `indisponivel` e deixa rastro NO PONTO
em que a falha é conhecida. `conferido` responde a pergunta que a tela precisava
e não tinha: "dá pra confiar nesta resposta?".
"""
import os
import sys
import urllib.error
import urllib.request

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

JOB = "job-coer-08"


@pytest.fixture
def sem_banco(monkeypatch):
    """Derruba o Supabase de verdade — pelo `urlopen`, como na produção."""
    def cair(exc):
        logs = []
        monkeypatch.setattr(main, "_log_error",
                            lambda stage, msg, job_id=None, **k: logs.append((stage, str(msg))))
        monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: None)
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda *a, **k: (_ for _ in ()).throw(exc))
        return logs
    return cair


FALHAS = [
    ("rede caiu", urllib.error.URLError("sem rede")),
    ("HTTP 500", urllib.error.HTTPError("u", 500, "erro", {}, None)),
    ("conexão resetada", OSError("connection reset by peer")),
    ("tempo esgotado", TimeoutError("timed out")),
]


# ══════════════════════════════════════════════════════════════════════════
#  1 · 🚨 o invariante: sem conseguir ler, a resposta NÃO diz que está em dia
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("nome,exc", FALHAS, ids=[f[0] for f in FALHAS])
def test_leitura_que_falha_marca_indisponivel_e_deixa_rastro(sem_banco, nome, exc):
    logs = sem_banco(exc)
    r = main._coerencia_do_projeto(JOB)
    assert r.get("conferido") is False, (
        "com o banco fora do ar a resposta se diz conferida (%s)" % nome)
    assert r.get("indisponivel"), "nenhum entregável marcado como indisponível"
    assert logs, (
        "🚨 a leitura falhou e NADA foi para o error_log — 'não consegui' "
        "ficou igual a 'não havia'")
    assert any(s == "coerencia:projeto" for s, _ in logs), [s for s, _ in logs]


def test_cada_entregavel_diz_que_nao_foi_conferido(sem_banco):
    """A marca é POR ENTREGÁVEL, não só no topo: a tela do cronograma e a do
    memorial só olham o pedaço delas."""
    sem_banco(urllib.error.URLError("sem rede"))
    r = main._coerencia_do_projeto(JOB)
    for nome in ("planilha", "cronograma", "memorial", "comparativo"):
        assert r[nome].get("indisponivel") is True, (
            "%s não se marcou indisponível: %r" % (nome, r[nome]))
        assert r[nome].get("desatualizado") is False, (
            "%s se disse desatualizado sem ter sido lido — alarme falso é o "
            "defeito oposto, e ensina o cliente a ignorar o aviso" % nome)


def test_uma_leitura_alimenta_DOIS_entregaveis_e_os_dois_caem_juntos(sem_banco):
    """🪤 `projects` traz planilha E comparativo. Se ela cai, os dois ficam sem
    resposta — antes os dois saíam como 'em dia', dois avisos sumindo de uma vez."""
    sem_banco(urllib.error.HTTPError("u", 500, "erro", {}, None))
    r = main._coerencia_do_projeto(JOB)
    assert r["planilha"].get("indisponivel") and r["comparativo"].get("indisponivel")
    assert "planilha" in r["indisponivel"] and "comparativo" in r["indisponivel"]


def test_o_log_nao_repete_a_mesma_leitura_duas_vezes(sem_banco):
    """Uma leitura, um rastro. Dois logs pra mesma falha viram parede de ruído
    e ensinam a ignorar o error_log."""
    logs = sem_banco(urllib.error.URLError("sem rede"))
    main._coerencia_do_projeto(JOB)
    mensagens = [m for s, m in logs if s == "coerencia:projeto"]
    assert len(mensagens) == len(set(mensagens)), mensagens


# ══════════════════════════════════════════════════════════════════════════
#  2 · 🚨 a falha PARCIAL — pior que o silêncio total
# ══════════════════════════════════════════════════════════════════════════
def test_falha_parcial_nao_APAGA_o_entregavel_da_resposta(monkeypatch):
    """Com o memorial falhando e o resto respondendo, o memorial não pode
    simplesmente sumir: a resposta ficaria com cara de saudável."""
    logs = []
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job_id=None, **k: logs.append((stage, str(msg))))
    monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: None)
    monkeypatch.setattr(main, "_assinatura_atual", lambda job: "assinatura-x")
    monkeypatch.setattr(main, "_revisoes_depois_de",
                        lambda job, quando: {"editados": 0, "excluidos": 0})
    monkeypatch.setattr(main, "_coerencia_do_financeiro",
                        lambda job: {"existe": False, "desatualizado": False})
    monkeypatch.setattr(main, "_fin_cronograma_salvo", lambda req, job: (200, None))

    def _rest(metodo, caminho, **k):
        if caminho.startswith("project_memorial"):
            return (500, None)                     # só o memorial cai
        if caminho.startswith("projects"):
            return (200, [{"planilha_gerada_em": "2026-01-01",
                           "planilha_assinatura": "velha",
                           "comparativo_gerado_em": None,
                           "comparativo_assinatura": None}])
        return (200, [])

    monkeypatch.setattr(main, "_supa_rest_service", _rest)
    r = main._coerencia_do_projeto(JOB)

    assert "planilha" in r["desatualizados"], "o cenário perdeu o alvo"
    assert r["memorial"].get("indisponivel") is True, (
        "🚨 o memorial sumiu da resposta: o cliente lê 'só a planilha está "
        "velha' e manda o memorial velho pro cliente dele")
    assert r.get("conferido") is False, (
        "a resposta se diz conferida com uma leitura caída — parece saudável "
        "e não é")
    assert logs, "falha parcial não deixou rastro"
    # 🚨 E O ALARME TEM QUE SER PRECISO. Marcar TUDO como indisponível quando
    # UMA leitura cai é o defeito oposto: some o aviso de verdade da planilha
    # velha no meio de um "não consegui conferir nada", e o cliente aprende a
    # ignorar o aviso. A mutação que espalhava a marca passou batida até isto
    # entrar — nenhum teste exigia que a leitura que FUNCIONOU ficasse de fora.
    assert r["planilha"].get("indisponivel") is not True, (
        "a planilha FOI lida e saiu marcada como indisponível: %r" % r["planilha"])
    assert r["comparativo"].get("indisponivel") is not True
    assert r["indisponivel"] == ["memorial"], (
        "só o memorial caiu, e a marca respingou em %r" % r["indisponivel"])


# ══════════════════════════════════════════════════════════════════════════
#  3 · 🧪 CONTROLE — o caminho feliz não pode ter mudado
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_com_o_banco_de_pe_a_resposta_e_conferida(monkeypatch):
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_assinatura_atual", lambda job: "assinatura-x")
    monkeypatch.setattr(main, "_revisoes_depois_de",
                        lambda job, quando: {"editados": 0, "excluidos": 0})
    monkeypatch.setattr(main, "_coerencia_do_financeiro",
                        lambda job: {"existe": False, "desatualizado": False})
    monkeypatch.setattr(main, "_fin_cronograma_salvo", lambda req, job: (200, None))
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (200, []))
    r = main._coerencia_do_projeto(JOB)
    assert r.get("conferido") is True and r.get("indisponivel") == []
    assert r.get("tudo_em_dia") is True and r.get("desatualizados") == []


def test_CONTROLE_entregavel_velho_continua_sendo_acusado(monkeypatch):
    """O alarme de verdade não pode ter sumido no conserto do alarme mudo."""
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_assinatura_atual", lambda job: "assinatura-nova")
    monkeypatch.setattr(main, "_revisoes_depois_de",
                        lambda job, quando: {"editados": 0, "excluidos": 0})
    monkeypatch.setattr(main, "_coerencia_do_financeiro",
                        lambda job: {"existe": False, "desatualizado": False})
    monkeypatch.setattr(main, "_fin_cronograma_salvo", lambda req, job: (200, None))
    monkeypatch.setattr(main, "_supa_rest_service", lambda metodo, caminho, **k: (
        (200, [{"planilha_gerada_em": "2026-01-01", "planilha_assinatura": "velha",
                "comparativo_gerado_em": None, "comparativo_assinatura": None}])
        if caminho.startswith("projects") else (200, [])))
    r = main._coerencia_do_projeto(JOB)
    assert r["desatualizados"] == ["planilha"], r["desatualizados"]
    assert r.get("tudo_em_dia") is False
    assert r.get("conferido") is True, "leitura que FUNCIONOU virou indisponível"
