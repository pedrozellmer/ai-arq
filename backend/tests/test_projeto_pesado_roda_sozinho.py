# -*- coding: utf-8 -*-
"""Projeto PESADO roda sozinho; os leves podem dividir o contêiner.

🩸 29/09/2026, a queda. A 2ª vaga abriu num VALE de memória (22 %) e, minutos
depois, duas conversões de DWG de ~60 MB (~2 GB cada) rodaram juntas e passaram
dos 4 GB. A régua da 2ª vaga olhava a memória NA ENTRADA, que não prevê o pico
da conversão. Desde então `JOBS_SIMULTANEOS=1` e cliente novo esperou até 92 min
na fila atrás de um projeto só de PDF. O conserto anotado naquele dia ("DWG
grande = vaga exclusiva") é este.

🔑 Com `JOBS_SIMULTANEOS=1` nada muda (um por vez). O peso só decide quando a
2ª vaga está ligada. Falha FECHADA: o que não se sabe é pesado.
"""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


@pytest.fixture(autouse=True)
def _fila_limpa(monkeypatch):
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    estado = (main._JOBS_RODANDO, main._PESADOS_RODANDO, main._JOBS_SIMULTANEOS)
    main._JOBS_RODANDO = 0
    main._PESADOS_RODANDO = 0
    main._JOBS_SIMULTANEOS = 2
    main._FILA_DE_SENHAS.clear()
    main._VAGA_EXTRA.set(False)
    main._DIVIDIU_O_SERVIDOR.set(False)
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.20)   # folga de sobra
    yield
    main._JOBS_RODANDO, main._PESADOS_RODANDO, main._JOBS_SIMULTANEOS = estado
    main._FILA_DE_SENHAS.clear()
    main._VAGA_EXTRA.set(False)
    main._DIVIDIU_O_SERVIDOR.set(False)


def _arq(tmp_path, nome, mb):
    """Arquivo esparso do tamanho pedido (não ocupa disco de verdade)."""
    p = tmp_path / nome
    with open(p, "wb") as f:
        f.truncate(int(mb * 1024 * 1024))
    return str(p)


# ══════════════════════════════════════════════════════════════════════════
#  1. O peso
# ══════════════════════════════════════════════════════════════════════════
def test_so_pdf_e_leve(tmp_path):
    assert main._job_e_pesado([_arq(tmp_path, "a.pdf", 8), _arq(tmp_path, "b.pdf", 40)]) is False


def test_cad_pequeno_e_leve(tmp_path):
    assert main._job_e_pesado([_arq(tmp_path, "planta.dwg", 5), _arq(tmp_path, "x.dxf", 19)]) is False


@pytest.mark.parametrize("nome, mb", [("planta.dwg", 25), ("PLANTA.DXF", 21), ("prancha.dwg", 60)])
def test_cad_acima_de_20_mb_e_pesado(tmp_path, nome, mb):
    assert main._job_e_pesado([_arq(tmp_path, "a.pdf", 2), _arq(tmp_path, nome, mb)]) is True


def test_pdf_enorme_tambem_e_pesado(tmp_path):
    assert main._job_e_pesado([_arq(tmp_path, "apresentacao.pdf", 150)]) is True


def test_compactado_e_pesado(tmp_path):
    assert main._job_e_pesado([_arq(tmp_path, "projeto.zip", 1)]) is True


@pytest.mark.parametrize("caminhos", [None, [], ["/nao/existe/planta.pdf"], 42])
def test_o_que_nao_se_sabe_e_pesado(caminhos):
    assert main._job_e_pesado(caminhos) is True


# ══════════════════════════════════════════════════════════════════════════
#  2. A régua da vaga
# ══════════════════════════════════════════════════════════════════════════
def test_dois_leves_dividem():
    assert main._tem_vaga_agora(1, pesado=False, pesados_rodando=0) is True


def test_pesado_chegando_nao_entra_ao_lado_de_ninguem():
    assert main._tem_vaga_agora(1, pesado=True, pesados_rodando=0) is False


def test_leve_chegando_nao_entra_ao_lado_do_pesado():
    assert main._tem_vaga_agora(1, pesado=False, pesados_rodando=1) is False


def test_o_primeiro_entra_sempre_mesmo_pesado():
    assert main._tem_vaga_agora(0, pesado=True, pesados_rodando=0) is True


def test_com_a_chave_em_1_nada_muda():
    main._JOBS_SIMULTANEOS = 1
    assert main._tem_vaga_agora(1, pesado=False, pesados_rodando=0) is False


def test_a_memoria_continua_valendo_entre_leves(monkeypatch):
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.60)
    assert main._tem_vaga_agora(1, pesado=False, pesados_rodando=0) is False


# ══════════════════════════════════════════════════════════════════════════
#  3. O contador de pesados entra e sai junto com a vaga
# ══════════════════════════════════════════════════════════════════════════
def test_o_pesado_e_contado_e_descontado():
    main._esperar_vaga(_espera_s=0.01, pesado=True)
    assert (main._JOBS_RODANDO, main._PESADOS_RODANDO) == (1, 1)
    main._liberar_vaga(pesado=True)
    assert (main._JOBS_RODANDO, main._PESADOS_RODANDO) == (0, 0)


def test_o_leve_nao_mexe_no_contador_de_pesados():
    main._esperar_vaga(_espera_s=0.01, pesado=False)
    assert (main._JOBS_RODANDO, main._PESADOS_RODANDO) == (1, 0)
    main._liberar_vaga(pesado=False)
    assert (main._JOBS_RODANDO, main._PESADOS_RODANDO) == (0, 0)


def test_com_um_pesado_no_ar_o_leve_espera_e_entra_quando_ele_sai():
    main._esperar_vaga(_espera_s=0.01, pesado=True)            # o pesado no ar
    entrou = threading.Event()

    def _leve():
        main._esperar_vaga(_espera_s=0.01, pesado=False)
        entrou.set()

    t = threading.Thread(target=_leve, daemon=True)
    t.start()
    assert not entrou.wait(0.3), "o leve entrou ao lado do pesado"
    main._liberar_vaga(pesado=True)
    assert entrou.wait(5), "o leve não entrou depois que o pesado saiu"
    t.join(timeout=5)
    main._liberar_vaga(pesado=False)


def test_com_um_leve_no_ar_outro_leve_entra_na_hora():
    main._esperar_vaga(_espera_s=0.01, pesado=False)
    entrou = threading.Event()

    def _leve():
        main._esperar_vaga(_espera_s=0.01, pesado=False)
        entrou.set()

    t = threading.Thread(target=_leve, daemon=True)
    t.start()
    assert entrou.wait(5), "dois leves não dividiram o contêiner"
    t.join(timeout=5)
    assert main._JOBS_RODANDO == 2 and main._PESADOS_RODANDO == 0
    main._liberar_vaga(pesado=False)
    main._liberar_vaga(pesado=False)


# ══════════════════════════════════════════════════════════════════════════
#  4. A porta única passa o MESMO peso pra entrada e pra saída
# ══════════════════════════════════════════════════════════════════════════
def test_a_porta_unica_mede_o_peso_e_devolve_igual(monkeypatch, tmp_path):
    visto = {}
    monkeypatch.setattr(main, "_esperar_vaga", lambda *a, **k: visto.setdefault("entrada", k.get("pesado")))
    monkeypatch.setattr(main, "_liberar_vaga", lambda *a, **k: visto.setdefault("saida", k.get("pesado")))
    monkeypatch.setattr(main, "_recusa_por_paginas", lambda *a, **k: False)
    monkeypatch.setattr(main, "process_job", lambda *a, **k: None)
    main._process_job_throttled("abc12345", [_arq(tmp_path, "planta.dwg", 30)], str(tmp_path))
    assert visto == {"entrada": True, "saida": True}


def test_a_porta_unica_devolve_o_contador_mesmo_quando_o_job_estoura(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "_recusa_por_paginas", lambda *a, **k: False)

    def _explode(*a, **k):
        raise RuntimeError("estourou")

    monkeypatch.setattr(main, "process_job", _explode)
    with pytest.raises(RuntimeError):
        main._process_job_throttled("abc12345", [_arq(tmp_path, "planta.dwg", 30)], str(tmp_path))
    assert (main._JOBS_RODANDO, main._PESADOS_RODANDO) == (0, 0)


def test_o_log_da_fila_diz_o_peso(monkeypatch):
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda st, msg, *a, **k: logs.append(msg))
    main._anotar_vaga("esperando-na-fila", 1, True, 1)
    assert logs and logs[0].endswith("pesado=1 pesados_rodando=1")
