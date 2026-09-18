# -*- coding: utf-8 -*-
"""Quando os DOIS conversores recusam o DWG, o log tem que dizer POR QUÊ.

🩸 16/09/2026. O `dwg:convert-fail` registrava só o nome do arquivo — e é o caso
PIOR: o cliente não recebe medição nenhuma. Em 60 dias, 28 jobs caíram aqui.

O motivo do ODA já era guardado desde 14/09 (`dwg_failure_detail`), mas só
aparecia no ramo em que o plano B DÁ CERTO (`libredwg:usado-no-fluxo`). O motivo
do plano B não era guardado em lugar nenhum: morria num `logger.warning`, e o
log do Render é descartado.

🔑 A pergunta que isso destrava é a leitura de ~21/09 — "vale trocar de
conversor?". Ela se decide justamente nos arquivos que ninguém abre, e sobre
eles a gente não tinha uma linha.

Estes guardas CHAMAM `_try_libredwg_convert` (com dublê de processo) e
`_porques_da_conversao` — e o último roda o `process_job` DE VERDADE com um DWG
que não converte, pra provar que a linha do motor usa isso. (O motor importa
`convert_dwg_to_dxf` dentro da função, então o dublê alcança.)
"""
import json
import os
import socket
import subprocess
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dwg_extractor as dx  # noqa: E402
import main  # noqa: E402

_DWG = "/tmp/aiarq_jobs/guarda/PRANCHA-EXECUTIVO-R03.dwg"


def _limpa():
    dx._FALHA_LIBREDWG.clear()
    dx._FALHA_DETALHE.clear()


# ── o plano B passa a registrar por que não converteu ──────────────────────
def test_plano_B_desinstalado_deixa_rastro(monkeypatch):
    _limpa()
    monkeypatch.setattr("shutil.which", lambda _n: None)
    assert dx._try_libredwg_convert(_DWG, "/tmp") is None
    assert "não instalado" in dx.libredwg_failure_detail(_DWG), dx._FALHA_LIBREDWG


def test_plano_B_desligado_por_env_deixa_rastro(monkeypatch):
    _limpa()
    monkeypatch.setattr("shutil.which", lambda _n: "/usr/bin/dwg2dxf")
    monkeypatch.setenv("LIBREDWG_FALLBACK", "0")
    assert dx._try_libredwg_convert(_DWG, "/tmp") is None
    assert "desligado" in dx.libredwg_failure_detail(_DWG), dx._FALHA_LIBREDWG


def test_plano_B_que_RECUSA_guarda_a_mensagem_do_conversor(monkeypatch):
    _limpa()
    monkeypatch.setattr("shutil.which", lambda _n: "/usr/bin/dwg2dxf")
    monkeypatch.setenv("LIBREDWG_FALLBACK", "1")

    class _R:
        returncode = 1
        stdout = ""
        stderr = "ERROR: Failed to decode header\nnot a DWG file?\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    assert dx._try_libredwg_convert(_DWG, "/tmp") is None
    _det = dx.libredwg_failure_detail(_DWG)
    assert "saiu 1" in _det and "Failed to decode header" in _det, _det
    assert "\n" not in _det, "tem que caber em UMA linha: %r" % _det


def test_plano_B_que_sai_zero_SEM_arquivo_e_caso_diferente(monkeypatch):
    """rc=0 sem arquivo é 'converteu e sumiu'; rc≠0 é 'recusou'. Quem ler o log
    em 21/09 precisa saber de qual dos dois se trata."""
    _limpa()
    monkeypatch.setattr("shutil.which", lambda _n: "/usr/bin/dwg2dxf")
    monkeypatch.setenv("LIBREDWG_FALLBACK", "1")

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    assert dx._try_libredwg_convert(_DWG, "/tmp/nao-existe-nada-aqui") is None
    assert "não gerou arquivo" in dx.libredwg_failure_detail(_DWG), dx._FALHA_LIBREDWG


def test_plano_B_que_estoura_o_tempo_e_o_que_quebra_tambem(monkeypatch):
    _limpa()
    monkeypatch.setattr("shutil.which", lambda _n: "/usr/bin/dwg2dxf")
    monkeypatch.setenv("LIBREDWG_FALLBACK", "1")

    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="dwg2dxf", timeout=300)

    monkeypatch.setattr(subprocess, "run", _timeout)
    assert dx._try_libredwg_convert(_DWG, "/tmp") is None
    assert "tempo" in dx.libredwg_failure_detail(_DWG), dx._FALHA_LIBREDWG

    _limpa()

    def _explode(*a, **k):
        raise OSError("Permission denied")

    monkeypatch.setattr(subprocess, "run", _explode)
    assert dx._try_libredwg_convert(_DWG, "/tmp") is None
    _det = dx.libredwg_failure_detail(_DWG)
    assert "OSError" in _det and "Permission denied" in _det, _det


def test_o_rastro_cabe_em_uma_linha_e_tem_teto():
    _limpa()
    dx._anotar_falha_libredwg(_DWG, "erro enorme\n" + ("x" * 900))
    _det = dx.libredwg_failure_detail(_DWG)
    assert len(_det) <= 240, len(_det)
    assert "\n" not in _det


def test_CONTROLE_arquivo_que_converteu_nao_tem_rastro_de_falha():
    _limpa()
    assert dx.libredwg_failure_detail("/tmp/OUTRO.dwg") == ""
    assert dx.dwg_failure_detail("/tmp/OUTRO.dwg") == ""


# ── a linha que vai pro log do motor ───────────────────────────────────────
def test_a_linha_do_log_traz_os_DOIS_motivos():
    _limpa()
    dx._FALHA_DETALHE[dx._chave_da_falha(_DWG)] = "OdError: Object improperly read <AcDbTextStyleTableRecord>"
    dx._anotar_falha_libredwg(_DWG, "dwg2dxf saiu 1: ERROR: Failed to decode header")
    _linha = main._porques_da_conversao(_DWG)
    assert "ODA:" in _linha and "Object improperly read" in _linha, _linha
    assert "plano B:" in _linha and "Failed to decode header" in _linha, _linha
    assert _linha.startswith(" | "), _linha


def test_CONTROLE_so_um_motivo_registrado_nao_inventa_o_outro():
    _limpa()
    dx._FALHA_DETALHE[dx._chave_da_falha(_DWG)] = "OdError: Unexpected end of file"
    _linha = main._porques_da_conversao(_DWG)
    assert "ODA: OdError: Unexpected end of file" in _linha, _linha
    assert "plano B" not in _linha, _linha


def test_CONTROLE_sem_motivo_nenhum_a_linha_DIZ_que_nao_tem():
    """🪤 Silêncio parecendo dado é o que custou este conserto. Se ninguém
    registrou, a linha fala isso em vez de sair vazia."""
    _limpa()
    _linha = main._porques_da_conversao("/tmp/SEM-REGISTRO.dwg")
    assert "nenhum dos dois conversores registrou motivo" in _linha, _linha


def test_a_telemetria_NUNCA_derruba_o_job_que_ja_esta_falhando(monkeypatch):
    """O job aqui já está em falha; a leitura do motivo não pode levantar."""
    _limpa()
    monkeypatch.setattr(dx, "dwg_failure_detail",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("banco fora")))
    _linha = main._porques_da_conversao(_DWG)
    assert "motivo não lido" in _linha and "RuntimeError" in _linha, _linha


def test_o_MOTOR_grava_os_motivos_quando_o_DWG_nao_converte(monkeypatch, tmp_path):
    """🚨 Guarda de CALL SITE: a função pode estar certa e nunca ser chamada.

    Roda `process_job` com um DWG que os dois conversores recusam e olha a linha
    que o motor gravou — não o fonte."""
    import llm_retry

    _limpa()
    # 🔒 Nome NEUTRO: o repo é público e regra nº6 vale também em teste —
    # o que o guarda precisa é de um .dwg qualquer, não do arquivo de alguém.
    _dwg = tmp_path / "prancha-de-teste-R03.dwg"
    _dwg.write_bytes(b"AC1032" + b"\x00" * 64)     # cabeçalho de DWG, corpo inútil
    dx._FALHA_DETALHE[dx._chave_da_falha(_dwg)] = "OdError: Object improperly read <AcDbTextStyleTableRecord>"
    dx._anotar_falha_libredwg(str(_dwg), "dwg2dxf saiu 1: ERROR: Failed to decode header")
    logs = []

    class _JobsMudo:
        def update_field(self, *a, **k):
            pass

    class _Resp:
        def read(self, *a):
            return json.dumps([{"auto_resume_count": 0, "reprocess_count": 0}]).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(dx, "convert_dwg_to_dxf", lambda *_a, **_k: None)
    monkeypatch.setattr(dx, "dwg_has_aec_markers", lambda *_a, **_k: False)
    # 🪤 16/09: sem estas duas linhas o `process_job` subia a prancha pro Storage
    # DE VERDADE e deixava uma thread de rede correndo — o guarda da sonda de
    # vida pegou isso na bancada, várias dezenas de testes depois. Teste que
    # encosta na rede suja a casa inteira.
    monkeypatch.setattr(main, "_supabase_storage_upload_prancha", lambda *a, **k: True)
    monkeypatch.setattr(socket.socket, "connect",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("rede bloqueada no guarda")))
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-guarda-local")
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, message, *a, **k: logs.append((stage, str(message))))
    monkeypatch.setattr(main, "_supabase_update", lambda *a, **k: None)
    monkeypatch.setattr(main, "_projeto_patch", lambda *a, **k: None)
    monkeypatch.setattr(main, "_send_email_smtp", lambda *a, **k: True)
    monkeypatch.setattr(main, "jobs", _JobsMudo())
    monkeypatch.setattr(llm_retry, "call_with_retry_stream",
                        lambda *a, **k: types.SimpleNamespace(
                            content=[types.SimpleNamespace(text="```json\n{\"items\": []}\n```")],
                            stop_reason="end_turn",
                            usage=types.SimpleNamespace(output_tokens=1, input_tokens=1)))
    try:
        main.process_job("guarda-convert-fail", [str(_dwg)], str(tmp_path),
                         project_type="arquitetura")
    except BaseException:
        pass        # o job termina em falha de propósito: é o caso pior

    _linhas = [m for s, m in logs if s == "dwg:convert-fail"]
    assert len(_linhas) == 1, "o motor não registrou a falha: %r" % [s for s, _ in logs][:20]
    assert "ODA:" in _linhas[0] and "Object improperly read" in _linhas[0], _linhas[0]
    assert "plano B:" in _linhas[0] and "Failed to decode header" in _linhas[0], _linhas[0]


def test_o_stage_do_caso_pior_continua_sendo_AVISO_e_nao_diagnostico():
    """`dwg:convert-fail` fala de cliente sem medição: tem que aparecer no
    painel, não virar linha de diagnóstico silenciosa."""
    assert "dwg:convert-fail" not in main._STAGES_DIAGNOSTICO
