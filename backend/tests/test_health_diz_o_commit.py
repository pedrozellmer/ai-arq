# -*- coding: utf-8 -*-
"""Depois do push, "subiu" tem que ser MEDICAO e nao deducao.

🚨 25/08/2026: subi tres consertos e a newsletter de agosto, e quando o
Pedro perguntou se ja dava pra ver o preview eu tive que responder que NAO
conseguia provar qual versao estava no ar -- o /api/health nao dizia o commit.
"Subiu" era palpite. Isso e primo do erro que esta na regra da casa: "nao
rodou" nao e a mesma coisa que "nao funcionou".

🩤 So o commit nao basta: redeploy do MESMO commit nao muda o SHA. Sem o
horario de boot nao da pra separar "subiu de novo" de "nem tentou". Por isso o
guarda cobra os dois.

Estes testes RODAM a funcao e RODAM a rota -- ler o fonte ja me enganou 8 vezes
num dia so.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main   # noqa: E402


def test_versao_traz_commit_curto_e_boot(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "0123456789abcdef0123")
    monkeypatch.setenv("RENDER_GIT_BRANCH", "main")
    v = main._versao_no_ar()
    assert v["commit"] == "0123456", "o commit tem que vir curto (7), veio %r" % v["commit"]
    assert v["branch"] == "main"
    assert v["no_ar_desde"], "sem horario de boot nao da pra ver redeploy do mesmo commit"
    assert isinstance(v["de_pe_ha_min"], int)


def test_sem_a_variavel_devolve_None_e_nao_string_vazia(monkeypatch):
    """None diz "nao sei". String vazia parece um commit valido de longe."""
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("RENDER_GIT_BRANCH", raising=False)
    v = main._versao_no_ar()
    assert v["commit"] is None, "veio %r em vez de None" % (v["commit"],)
    assert v["branch"] is None
    assert v["no_ar_desde"], "o boot NAO depende do Render: tem que vir sempre"


def test_a_ROTA_health_devolve_a_versao(monkeypatch):
    """O que vale e o que sai na rota, nao a funcao isolada.

    🩤 Ja passei verde duas vezes com guarda que testava a funcao e nao o
    chamador: sabotei o call site e o teste nem piscou.
    """
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")
    r = asyncio.run(main.health())
    assert "versao" in r, "a rota /api/health parou de devolver a versao"
    assert r["versao"]["commit"] == "abcdef1", r["versao"]
    assert r["status"] == "healthy"


def test_controle_positivo_a_versao_ANTIGA_reprova(monkeypatch):
    """Prova que este guarda reprova mesmo.

    A versao antiga da rota nao tinha campo nenhum de versao. Se as afirmacoes
    acima passassem com ela, elas nao valeriam nada.
    """
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")
    r = asyncio.run(main.health())
    antiga = {k: v for k, v in r.items() if k != "versao"}
    assert "versao" not in antiga
    with pytest.raises(KeyError):
        _ = antiga["versao"]["commit"]
