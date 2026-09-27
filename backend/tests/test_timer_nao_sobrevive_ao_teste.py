# -*- coding: utf-8 -*-
"""Timer aberto num teste não pode disparar no teste seguinte.

🩸 27/09/2026 — a bancada do CI no ce156b4 (commit que só mexia no site)
ficou vermelha na sonda de vida: "a sonda pagou por urllib.request.urlopen,
main._supabase_insert()". Quem pagou foi o `threading.Timer` de 90 s do
aprendizado da revisão (`_agendar_aprendizado_revisao`), armado por um teste de
revisão: o monkeypatch desfez os dublês no fim daquele teste, o timer ficou, e
90 s depois disparou com as funções REAIS no meio da medição da sonda. Medido
na bancada inteira com um gravador de threads: 4 testes deixavam o timer vivo.

O `conftest.py` cancela, no fim de cada teste, todo Timer iniciado nele. Este
arquivo prova que o vigia está armado sem ninguém pedir, que ele pega o timer
de verdade do main e que o cancelamento impede o disparo.
"""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conftest import TimersDoTeste  # noqa: E402


def test_CONTROLE_sem_cancelar_o_timer_dispara():
    """Sem este controle, "não disparou" podia ser só timer que nunca dispara."""
    disparou = threading.Event()
    t = threading.Timer(0.05, disparou.set)
    t.start()
    assert disparou.wait(5), "o timer não disparou nem sem cancelamento"


def test_o_timer_cancelado_pelo_vigia_nao_dispara():
    disparou = threading.Event()
    vigia = TimersDoTeste()
    with pytest.MonkeyPatch.context() as mp:
        vigia.armar(mp)
        t = threading.Timer(0.3, disparou.set)
        t.start()
        assert vigia.iniciados == [t]
        vigia.cancelar()
    t.join(5)
    assert not t.is_alive(), "o timer cancelado continua vivo"
    assert not disparou.wait(0.6), "o timer disparou depois de cancelado"


def test_o_vigia_esta_armado_sem_pedir_e_pega_o_timer_do_main():
    """Este teste NÃO pede a fixture: o vigia tem que estar lá sozinho
    (autouse). E o timer que ele pega é o do aprendizado da revisão de verdade."""
    import main
    vigia = getattr(threading.Timer.start, "vigia", None)
    assert vigia is not None, "o vigia de timers não está armado neste teste"
    main._agendar_aprendizado_revisao("timer-do-teste")
    agendado = main._APRENDIZADO_TIMERS.get("timer-do-teste")
    assert agendado is not None, "o main não agendou o aprendizado"
    assert agendado in vigia.iniciados, "o timer do aprendizado escapou do vigia"


def test_timer_continua_passando_pelo_start_de_quem_carimba(monkeypatch):
    """O guarda da sonda troca o Thread.start pra carimbar quem abriu cada
    thread. Um Timer aberto pela requisição tem que continuar carimbado — se o
    vigia guardasse o start do momento em que armou, o Timer pulava o carimbo e
    a sonda deixava de ver o custo dele."""
    carimbadas = []
    _start = threading.Thread.start

    def _start_carimbando(self, *a, **k):
        carimbadas.append(self)
        return _start(self, *a, **k)

    monkeypatch.setattr(threading.Thread, "start", _start_carimbando)
    t = threading.Timer(60, lambda: None)
    t.start()
    try:
        assert t in carimbadas, "o Timer pulou o Thread.start de quem carimba"
    finally:
        t.cancel()
