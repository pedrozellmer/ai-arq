# -*- coding: utf-8 -*-
"""Leitura que falha não pode virar "não existe" — nem gravar duplicata.

🩸 08/09/2026, varredura dos 90 logs que nunca dispararam. Dois instrumentos
mortos pela MESMA causa: `except Exception` em volta de funções que **nunca
levantam**.

`_supa_rest_service` termina em `except Exception: return 0, None` e converte
HTTPError em `return e.code, None` — ela nunca propaga. `_supa_rows` embrulha
isso em outro try/except e **"devolve [] em qualquer falha"** (a docstring dela
diz isso com todas as letras). Quem confia no `except` fica com um alarme que
não toca.

──────────────────────────────────────────────────────────────────────────────
1. `avaliacao:dedup` — o pior dos dois, porque tem EFEITO COLATERAL.

A rota `/api/avaliar` procura uma nota anterior pra decidir entre PATCH
(trocar) e INSERT (criar). A busca usava `_supa_rows`: quando ela falha,
devolve `[]` — **indistinguível de "essa pessoa ainda não avaliou"**. O código
caía no INSERT e gravava nota DUPLICADA, disparando de novo o alerta pro
Pedro. É exatamente o bug que a auditoria de 31/08 consertou.

Provado rodando (rede caída e HTTP 500): `_supa_rows` devolveu `[]`, sem
levantar e sem log.

🪤 Numa base com 7 respostas de NPS em toda a história, uma duplicata não é
ruído — é uma fatia grande do dado.

🔑 Agora decide pelo STATUS. Não deu pra conferir → **não grava**: repetir é
pior que perder, porque a duplicata contamina a média E o alerta.

──────────────────────────────────────────────────────────────────────────────
2. `alerta-cadastro:perfil-agora` — o fail-closed funcionava, e era mudo.

A função já devolvia None quando a leitura falhava (e o chamador pula, em vez
de chutar — chutar aqui vira e-mail errado permanente). O que faltava era o
RASTRO: numa madrugada de Supabase instável os lembretes de cadastro somem e a
ausência de alerta se lê como "ninguém parou no meio do cadastro".
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
from fastapi import HTTPException  # noqa: E402

FALHAS = [
    ("rede caiu", urllib.error.URLError("sem rede")),
    ("HTTP 500", urllib.error.HTTPError("u", 500, "erro", {}, None)),
    ("conexão resetada", OSError("connection reset by peer")),
]


@pytest.fixture
def banco_fora(monkeypatch):
    def cair(exc):
        logs = []
        monkeypatch.setattr(main, "_log_error",
                            lambda stage, msg, job=None, **k: logs.append((stage, str(msg))))
        monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: None)
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda *a, **k: (_ for _ in ()).throw(exc))
        return logs
    return cair


# ══════════════════════════════════════════════════════════════════════════
#  0 · a premissa: essas funções NUNCA levantam (é por isso que o except morre)
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("nome,exc", FALHAS, ids=[f[0] for f in FALHAS])
def test_supa_rows_devolve_lista_vazia_sem_levantar(banco_fora, nome, exc):
    """Se um dia ela passar a levantar, os `except` da casa voltam a valer — e
    este teste avisa que a premissa mudou."""
    banco_fora(exc)
    assert main._supa_rows("GET", "qualquer", params={"limit": "1"}) == []


@pytest.mark.parametrize("nome,exc", FALHAS, ids=[f[0] for f in FALHAS])
def test_supa_rest_service_devolve_status_sem_levantar(banco_fora, nome, exc):
    banco_fora(exc)
    st, rows = main._supa_rest_service("GET", "/qualquer")
    assert rows is None and st != 200, (st, rows)


# ══════════════════════════════════════════════════════════════════════════
#  1 · 🚨 a avaliação NÃO grava quando não conseguiu conferir
# ══════════════════════════════════════════════════════════════════════════
def _payload(nota=5):
    return main.NotaAvaliacao(tipo="projeto", k="job-1", e="cliente@exemplo.test",
                              t="token-x", n=nota)


@pytest.mark.parametrize("nome,exc", FALHAS, ids=[f[0] for f in FALHAS])
def test_dedup_que_falha_NAO_grava_nota(banco_fora, monkeypatch, nome, exc):
    """🚨 O invariante. Antes: leitura falhava → `[]` → INSERT → nota duplicada
    e alerta repetido pro Pedro."""
    logs = banco_fora(exc)
    # 🪤 O nome certo é `_nota_token_ok`. A 1ª versão fingiu
    # `_token_avaliacao_ok` com `raising=False` — que CRIA um atributo que
    # ninguém usa. O teste morria no 403 do token, sem nunca chegar no código
    # consertado, e o erro só apareceu porque a mensagem do 403 não batia.
    monkeypatch.setattr(main, "_nota_token_ok", lambda *a, **k: True)
    gravou = []
    monkeypatch.setattr(main, "_supabase_insert",
                        lambda tabela, dados, **k: gravou.append(tabela))
    with pytest.raises(HTTPException) as ex:
        main.registrar_avaliacao(_payload())
    assert ex.value.status_code >= 500, ex.value.status_code
    assert not gravou, (
        "🚨 gravou sem saber se já existia nota — é a duplicata que a auditoria "
        "de 31/08 consertou (gravou em %r)" % gravou)
    assert any(s == "avaliacao:dedup" for s, _ in logs), [s for s, _ in logs]


def test_a_mensagem_do_erro_chega_legivel_na_tela(banco_fora, monkeypatch):
    """🪤 `obrigado.html` decide por `d.status !== 'ok'` e só mostra o texto
    quando ele vem em `detail` (string). Um dict próprio faria a tela dizer "o
    servidor respondeu 200", que confunde mais do que ajuda."""
    banco_fora(urllib.error.URLError("sem rede"))
    # 🪤 O nome certo é `_nota_token_ok`. A 1ª versão fingiu
    # `_token_avaliacao_ok` com `raising=False` — que CRIA um atributo que
    # ninguém usa. O teste morria no 403 do token, sem nunca chegar no código
    # consertado, e o erro só apareceu porque a mensagem do 403 não batia.
    monkeypatch.setattr(main, "_nota_token_ok", lambda *a, **k: True)
    with pytest.raises(HTTPException) as ex:
        main.registrar_avaliacao(_payload())
    assert isinstance(ex.value.detail, str) and ex.value.detail
    assert "nota" in ex.value.detail.lower()


# ══════════════════════════════════════════════════════════════════════════
#  2 · o lembrete de cadastro deixa rastro quando não consegue conferir
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("nome,exc", FALHAS, ids=[f[0] for f in FALHAS])
def test_perfil_que_nao_deu_pra_ler_deixa_rastro(banco_fora, nome, exc):
    logs = banco_fora(exc)
    assert main._perfil_existe_agora("cliente@exemplo.test") is None, (
        "chutou em vez de pular — chutar aqui vira e-mail errado permanente")
    assert any(s == "alerta-cadastro:perfil-agora" for s, _ in logs), (
        "🚨 o lembrete foi adiado e NINGUÉM soube — a ausência de alerta se lê "
        "como 'ninguém parou no meio do cadastro'")


def test_a_leitura_por_UID_tambem_deixa_rastro(monkeypatch):
    """A 2ª leitura (por uid) tinha o mesmo buraco."""
    logs = []
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job=None, **k: logs.append((stage, str(msg))))
    chamadas = {"n": 0}

    def _rest(metodo, caminho, **k):
        chamadas["n"] += 1
        return (200, []) if chamadas["n"] == 1 else (503, None)

    monkeypatch.setattr(main, "_supa_rest_service", _rest)
    assert main._perfil_existe_agora("cliente@exemplo.test", uid="uid-1") is None
    assert any("uid" in m for s, m in logs if s == "alerta-cadastro:perfil-agora"), logs


# ══════════════════════════════════════════════════════════════════════════
#  3 · 🧪 CONTROLE — o caminho feliz não pode ter mudado
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_perfil_que_existe_devolve_True_sem_log(monkeypatch):
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, [{"user_id": "uid-1"}]))
    assert main._perfil_existe_agora("cliente@exemplo.test") is True
    assert not logs, "logou falha numa leitura que funcionou — alarme falso"


def test_CONTROLE_perfil_ausente_devolve_False_sem_log(monkeypatch):
    """Ausência CONFIRMADA é resposta, não falha: aí o lembrete PODE sair."""
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (200, []))
    assert main._perfil_existe_agora("cliente@exemplo.test") is False
    assert not logs
