# -*- coding: utf-8 -*-
"""Faz `pytest tests/` rodar a bancada INTEIRA.

🚨 23/08/2026 (auditoria): `pytest tests/` colhia 6 testes de UM arquivo e
abortava com `ValueError: I/O operation on closed file`. Os outros 17 arquivos
— consolidação, cotas, engine_rules, estrutural, jobs_lock, revision_feedback —
NUNCA rodavam junto. A rede de segurança existia e estava apagada.

Causa: 13 dos 18 arquivos `test_*.py` são SCRIPTS, não módulos de pytest: eles
executam no import, trocam `sys.stdout` por um TextIOWrapper (que o pytest
depois tenta ler fechado) e terminam em `sys.exit()`.

Reescrever os 13 seria caro e arriscado — eles são a bancada que segurou o motor
o ano inteiro. Em vez disso: o pytest ignora esses arquivos na coleção normal
(`collect_ignore`) e `test_scripts_legados.py` roda cada um em SUBPROCESSO,
conferindo o código de saída. Ninguém fica de fora, e quem escrever teste novo
no formato pytest é colhido normalmente.
"""
import io
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))


# ── 🔒 27/09/2026 (auditoria SI): a bancada NÃO alcança o Supabase de produção ─────────────────────────────
# `main.py` e `sinapi_matcher.py` caem no endereço de PRODUÇÃO, com a chave pública, quando a env falta — e nem
# este PC nem o CI têm as variáveis. Medido nos logs do Supabase (24 h): a bancada daqui e a do CI mandavam
# milhares de chamadas pra produção e ~2.900 voltavam recusadas (gravar no error_log, update_project_status,
# DELETE em project_items…). Nada gravou SÓ porque a chave de servidor não estava no ambiente: com ela, a bancada
# escreveria de verdade na produção. Rodada inteira com este bloqueio: 7.510 ok, 1 teste dependia da produção
# (test_avaliacao_um_clique, consertado com dublê).
# Aqui toda abertura de URL do urllib (urlopen e build_opener passam por OpenerDirector.open) para *.supabase.co
# vira erro de rede — o mesmo caso que o código já trata quando o Supabase cai. Teste que precisa de resposta do
# banco usa dublê (monkeypatch), como os outros.
class ProducaoBloqueadaNosTestes(urllib.error.URLError):
    """Um teste tentou chamar o Supabase de verdade."""


def host_bloqueado(host) -> bool:
    h = str(host or "").lower().rstrip(".")
    return h == "supabase.co" or h.endswith(".supabase.co")


_abrir_original = urllib.request.OpenerDirector.open


def _abrir_sem_producao(self, fullurl, *args, **kwargs):
    alvo = fullurl if isinstance(fullurl, str) else getattr(fullurl, "full_url", "")
    try:
        partes = urllib.parse.urlsplit(alvo)
    except Exception:
        partes = None
    if partes is not None and host_bloqueado(partes.hostname):
        raise ProducaoBloqueadaNosTestes(
            "teste tentou chamar o Supabase de verdade (%s%s) — use um dublê" % (partes.hostname, partes.path))
    return _abrir_original(self, fullurl, *args, **kwargs)


urllib.request.OpenerDirector.open = _abrir_sem_producao


# ── ⏲️ 27/09/2026: timer aberto num teste NÃO dispara no teste seguinte ───────────────────────────────────────
# `submit_item_review` (edit/reject) agenda o aprendizado da revisão num `threading.Timer` de 90 s. O monkeypatch
# desfaz os dublês no fim do teste; o timer, não. 90 s depois ele disparava com as funções REAIS no meio de
# qualquer outro teste do mesmo worker — foi o vermelho intermitente da sonda de vida no CI do ce156b4 ("a sonda
# pagou por urllib.request.urlopen, main._supabase_insert()"). Medido na bancada inteira: 4 testes deixavam o
# timer vivo. Aqui todo Timer iniciado durante um teste é cancelado no fim dele; quem precisa que um timer
# dispare espera por ele DENTRO do teste.
class TimersDoTeste:
    def __init__(self):
        self.iniciados = []

    def armar(self, monkeypatch):
        vigia = self

        def _start_anotado(timer, *a, **k):
            vigia.iniciados.append(timer)
            # 🪤 procura o Thread.start NA HORA, não guarda o de agora: o guarda da sonda troca o start pra
            # carimbar quem abriu cada thread, e um Timer aberto pela requisição tem que continuar carimbado.
            return threading.Thread.start(timer, *a, **k)

        _start_anotado.vigia = vigia
        monkeypatch.setattr(threading.Timer, "start", _start_anotado)

    def cancelar(self):
        for t in self.iniciados:
            t.cancel()


@pytest.fixture(autouse=True)
def _timer_nao_sobrevive_ao_teste(monkeypatch):
    vigia = TimersDoTeste()
    vigia.armar(monkeypatch)
    yield vigia
    vigia.cancelar()


def _e_script(nome: str) -> bool:
    """True se o arquivo EXECUTA NO IMPORT (formato script), e só isso.

    🚨 24/08/2026 (2ª validação): a versão anterior devolvia True sempre que
    `"\ndef test_" not in src` — e num teste escrito em CLASSE o `def test_`
    está indentado, então nunca casava. Efeito medido com controle positivo:
    um arquivo com `class TestX: def test_deve_falhar(self): assert 1 == 2`
    era classificado como "script legado", o pytest não colhia, o subprocesso
    só importava o módulo (a classe é definida, nada executa), saía 0 — e a
    suíte contava **143 passed**. Um teste que afirma 1 == 2 passou por
    aprovado. Era a armadilha de 23/08 de novo: verde não é o mesmo que
    "rodou".
    """
    try:
        src = io.open(os.path.join(_AQUI, nome), encoding="utf-8").read()
    except Exception:
        return False
    # Tem teste no formato pytest? Função OU CLASSE, em qualquer indentação —
    # era a classe que escapava antes.
    tem_pytest = re.search(r"^[ \t]*(def test_|class Test)", src, re.M) is not None
    # Quebra a coleção do pytest? (`sys.exit` no import aborta a suíte inteira,
    # e trocar o sys.stdout faz o pytest ler um arquivo já fechado.)
    _nl = chr(10)
    quebra_colecao = (_nl + "sys.exit(") in src or (_nl + "sys.stdout = ") in src
    if quebra_colecao:
        return True
    return not tem_pytest


def scripts_legados():
    return sorted(n for n in os.listdir(_AQUI)
                  if n.startswith("test_") and n.endswith(".py")
                  and n != "test_scripts_legados.py" and _e_script(n))


collect_ignore = scripts_legados()
