# -*- coding: utf-8 -*-
"""O MESMO arquivo duas vezes no envio é lido uma vez.

🩸 26/09/2026 — job `facb8346`: a cliente mandou "…TIP_R06.pdf" e
"…TIP_R06 (1).pdf" (o nome que o navegador dá ao baixar de novo), byte a byte
iguais. O motor leu os dois como pranchas diferentes — numa leitura de
arquitetura, as quantidades daquela planta sairiam em DOBRO. O /add-file já
barrava o gêmeo pelo sha256; o envio inicial e o reprocesso, não.

🪤 O guarda EXECUTA `_process_job_throttled`, a porta única dos seis disparos
(upload, reprocesso, filhote, retomada, combinação, anexo).
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
import main  # noqa: E402

JOB = "job12345"   # 🔒 rótulo, nunca pessoa


def _arq(tmp_path, nome, conteudo):
    p = tmp_path / nome
    p.write_bytes(conteudo)
    return str(p)


@pytest.fixture
def porta(monkeypatch):
    """A porta única com o motor, a fila e o banco trocados por espiões."""
    esp = {"motor": [], "logs": []}

    def _motor(*a, **k):
        esp["motor"].append((a, k))

    def _log(stage, message, job_id=None, severity="error", *a, **k):
        esp["logs"].append((stage, message, job_id, severity))

    monkeypatch.setattr(main, "process_job", _motor)
    monkeypatch.setattr(main, "_log_error", _log)
    monkeypatch.setattr(main, "_recusa_por_paginas", lambda *a, **k: False)
    monkeypatch.setattr(main, "_esperar_vaga", lambda *a, **k: None)
    monkeypatch.setattr(main, "_liberar_vaga", lambda *a, **k: None)
    return esp


def _lidos(esp):
    a, k = esp["motor"][-1]
    return [os.path.basename(p) for p in (a[1] if len(a) > 1 else k["file_paths"])]


# ── o caso ─────────────────────────────────────────────────────────────────────
def test_o_caso_o_mesmo_pdf_com_nome_de_download_repetido_e_lido_uma_vez(porta, tmp_path):
    fps = [_arq(tmp_path, "PLANTA_TIPO.pdf", b"%PDF planta tipo"),
           _arq(tmp_path, "PLANTA_TIPO (1).pdf", b"%PDF planta tipo"),
           _arq(tmp_path, "UTP.pdf", b"%PDF outra prancha")]
    main._process_job_throttled(JOB, fps, "/tmp/x")
    assert _lidos(porta) == ["PLANTA_TIPO.pdf", "UTP.pdf"]


def test_o_log_diz_qual_saiu_e_de_quem_era_copia(porta, tmp_path):
    fps = [_arq(tmp_path, "A.pdf", b"mesmo"), _arq(tmp_path, "A - Copia.pdf", b"mesmo")]
    main._process_job_throttled(JOB, fps, "/tmp/x")
    rep = [x for x in porta["logs"] if x[0] == "motor:arquivo-repetido"]
    assert rep and "A - Copia.pdf = A.pdf" in rep[0][1] and rep[0][2] == JOB, porta["logs"]
    assert rep[0][3] == "info"
    assert "motor:arquivo-repetido" in main._STAGES_DIAGNOSTICO


def test_file_paths_por_nome_tambem(porta, tmp_path):
    fps = [_arq(tmp_path, "A.pdf", b"mesmo"), _arq(tmp_path, "B.pdf", b"mesmo")]
    main._process_job_throttled(JOB, file_paths=fps, work_dir="/tmp/x")
    assert _lidos(porta) == ["A.pdf"]


def test_o_resto_dos_argumentos_chega_igual(porta, tmp_path):
    fps = [_arq(tmp_path, "A.pdf", b"mesmo"), _arq(tmp_path, "B.pdf", b"mesmo")]
    main._process_job_throttled(JOB, fps, "/tmp/trabalho", "residencial", project_type="arquitetura")
    a, k = porta["motor"][-1]
    assert a[0] == JOB and a[2:] == ("/tmp/trabalho", "residencial") and k == {"project_type": "arquitetura"}


# ── o que NÃO pode sair ────────────────────────────────────────────────────────
def test_CONTROLE_nome_parecido_conteudo_diferente_fica(porta, tmp_path):
    """Revisão R05 e R06 da mesma prancha, ou "(1)" que é outro desenho: ficam."""
    fps = [_arq(tmp_path, "PLANTA.pdf", b"revisao 5"), _arq(tmp_path, "PLANTA (1).pdf", b"revisao 6")]
    main._process_job_throttled(JOB, fps, "/tmp/x")
    assert _lidos(porta) == ["PLANTA.pdf", "PLANTA (1).pdf"]
    assert not [x for x in porta["logs"] if x[0] == "motor:arquivo-repetido"]


def test_CONTROLE_arquivo_que_nao_abre_fica_pro_motor_decidir(porta, tmp_path):
    fps = [_arq(tmp_path, "A.pdf", b"x"), str(tmp_path / "sumiu.pdf"), str(tmp_path / "sumiu.pdf")]
    main._process_job_throttled(JOB, fps, "/tmp/x")
    assert _lidos(porta) == ["A.pdf", "sumiu.pdf", "sumiu.pdf"]


def test_CONTROLE_um_arquivo_so_nem_calcula(porta, tmp_path, monkeypatch):
    chamou = []
    monkeypatch.setattr(main, "_sha256_do_arquivo", lambda *a, **k: chamou.append(1) or "h")
    main._process_job_throttled(JOB, [_arq(tmp_path, "A.pdf", b"x")], "/tmp/x")
    assert not chamou and _lidos(porta) == ["A.pdf"]


def test_a_regua_de_paginas_conta_o_que_vai_ser_lido(porta, tmp_path, monkeypatch):
    """A cópia não pode empurrar o envio pra cima do teto de páginas."""
    viu = []
    monkeypatch.setattr(main, "_recusa_por_paginas", lambda job, fps, *a, **k: viu.append(list(fps)) or False)
    fps = [_arq(tmp_path, "A.pdf", b"mesmo"), _arq(tmp_path, "B.pdf", b"mesmo")]
    main._process_job_throttled(JOB, fps, "/tmp/x")
    assert [os.path.basename(p) for p in viu[0]] == ["A.pdf"]
