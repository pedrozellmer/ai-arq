# -*- coding: utf-8 -*-
"""O filho da medição de PDF diz até onde chegou antes de morrer ou estourar o tempo.

🩸 10/09/2026 — reprocesso interno do job 7ddbccc1: a medição estourou os 75 s
pela terceira vez, e a sombra, com 170 s, também. Nenhuma das duas disse EM QUE
ETAPA o relógio venceu, porque o filho só imprime o JSON no fim.

🔑 FOTO POR ETAPA, só telemetria: `_measure_page` imprime uma linha marcada a
cada etapa (com flush), e o pai lê a última foto inteira quando o filho morre
ou estoura o tempo. Nada disso vira medição na planilha.

Estes guardas CHAMAM `filho_protegido`, `_measure_page`, o `rodar()` e o bloco
real do filho da promoção em `main.py`, com o `subprocess.run` espionado.
"""
import json
import os
import subprocess
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import filho_protegido as fp  # noqa: E402


def _linha_de_foto(**campos):
    d = dict(campos)
    d[fp.MARCA_DA_FOTO] = 1
    return json.dumps(d, separators=(",", ":"))


# ── imprimir e ler ───────────────────────────────────────────────────────────
def test_sem_o_env_nenhuma_foto_sai(monkeypatch, capsys):
    monkeypatch.delenv("FILHO_IMPRIME_FOTO", raising=False)
    fp.imprimir_foto({"etapa": "rooms", "t": 1.5})
    assert capsys.readouterr().out == ""


def test_com_o_env_sai_uma_linha_marcada_que_o_leitor_entende(monkeypatch, capsys):
    monkeypatch.setenv("FILHO_IMPRIME_FOTO", "1")
    fp.imprimir_foto({"etapa": "rooms", "t": 1.5})
    out = capsys.readouterr().out
    assert out.count(chr(10)) == 1, out
    assert fp.MARCA_DA_FOTO in out
    assert fp.ultima_foto(out) == {"etapa": "rooms", "t": 1.5}


def test_a_foto_nunca_derruba_quem_chama_nem_com_MemoryError(monkeypatch, capsys):
    monkeypatch.setenv("FILHO_IMPRIME_FOTO", "1")

    class _Bomba:
        """Mapeamento que estoura ao ser copiado. 🪤 A 1ª versão herdava de
        dict, e o `dict()` do CPython copia subclasse de dict pelo caminho
        rápido, sem chamar `keys()`: a bomba nunca explodia e o teste não
        provava nada."""
        def __bool__(self):
            return True

        def keys(self):
            raise MemoryError("sem memória montando a foto")

        def __getitem__(self, k):
            raise MemoryError("sem memória montando a foto")

    fp.imprimir_foto(_Bomba())   # não pode levantar
    assert capsys.readouterr().out == ""


def test_foto_grande_demais_nao_sai(monkeypatch, capsys):
    monkeypatch.setenv("FILHO_IMPRIME_FOTO", "1")
    fp.imprimir_foto({"etapa": "rooms", "lixo": "x" * 5000})
    assert capsys.readouterr().out == ""


def test_ultima_foto_le_BYTES_str_bytearray_e_None():
    duas = (_linha_de_foto(etapa="parse", t=10.0) + chr(10)
            + _linha_de_foto(etapa="rooms", t=40.1) + chr(10))
    assert fp.ultima_foto(duas.encode("utf-8")) == {"etapa": "rooms", "t": 40.1}
    assert fp.ultima_foto(duas) == {"etapa": "rooms", "t": 40.1}
    assert fp.ultima_foto(bytearray(duas.encode("utf-8"))) == {"etapa": "rooms", "t": 40.1}
    assert fp.ultima_foto(None) == {}
    assert fp.ultima_foto(b"") == {}


def test_ultima_foto_pula_linha_cortada_e_json_sem_marca():
    cortada = (_linha_de_foto(etapa="walls", t=50.0) + chr(10)
               + _linha_de_foto(etapa="cotas", t=51.0)[:15])
    assert fp.ultima_foto(cortada) == {"etapa": "walls", "t": 50.0}
    assert fp.ultima_foto('{"n_rooms": 3, "scale": 50}') == {}


def test_etiqueta_do_log_diz_LIDA_e_nunca_inventa_etapa():
    assert fp.foto_em_texto({"etapa": "rooms", "t": 40.1, "vmpeak_mb": 1051}) == (
        " [ultima_etapa_lida=rooms t=40.1s vmpeak=1051MB]")
    assert fp.foto_em_texto({}) == " [nenhuma etapa lida]"
    assert "VmPeak=" not in fp.foto_em_texto({"etapa": "x", "vmpeak_mb": 9}), (
        "a série do p95 casa 'VmPeak=' por regex — a foto não pode imitar")


# ── o flush sobrevive à morte ──────────────────────────────────────────────
def test_filho_REAL_que_sai_sem_esvaziar_o_buffer_ainda_entrega_a_foto():
    """`os._exit` pula o esvaziamento do buffer, como a morte por sinal: só o
    flush explícito garante que a foto chegou no pipe."""
    codigo = ("import sys, os; sys.path.insert(0, sys.argv[1]); "
              "import filho_protegido as f; "
              "f.imprimir_foto({'etapa': 'walls', 't': 2.0}); "
              "print('isto fica no buffer e se perde'); os._exit(1)")
    r = subprocess.run([sys.executable, "-c", codigo, _BACKEND], capture_output=True,
                       text=True, timeout=60, env=dict(os.environ, FILHO_IMPRIME_FOTO="1"))
    assert r.returncode != 0
    assert "se perde" not in r.stdout, "o controle não reproduziu a perda do buffer"
    assert fp.ultima_foto(r.stdout) == {"etapa": "walls", "t": 2.0}, r.stdout


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="SIGABRT de verdade: Linux")
def test_filho_REAL_que_ABORTA_ainda_entrega_a_foto():
    codigo = ("import sys, os; sys.path.insert(0, sys.argv[1]); "
              "import filho_protegido as f; "
              "f.imprimir_foto({'etapa': 'cotas', 't': 3.0}); os.abort()")
    r = subprocess.run([sys.executable, "-c", codigo, _BACKEND], capture_output=True,
                       text=True, timeout=60, env=dict(os.environ, FILHO_IMPRIME_FOTO="1"))
    assert r.returncode == -6, r.returncode
    assert fp.ultima_foto(r.stdout) == {"etapa": "cotas", "t": 3.0}, r.stdout


# ── o rodar() (sombra e pré-orçamento) ──────────────────────────────────────
def test_rodar_no_estouro_com_BYTES_devolve_a_foto_ANINHADA(monkeypatch):
    saida = (_linha_de_foto(etapa="rooms", t=40.1) + chr(10) + '{"etapa":"en').encode("utf-8")

    def _estoura(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 5, output=saida)
    monkeypatch.setattr(fp.subprocess, "run", _estoura)
    r = fp.rodar(["print(1)"], [], timeout_s=5, rotulo="filho da sombra")
    assert "estourou o tempo" in r["skip"], r
    assert r["foto"] == {"etapa": "rooms", "t": 40.1}, r
    assert "etapa" not in r and "n_rooms" not in r, "a foto não pode ir pro topo"


def test_rodar_no_estouro_sem_saida_nao_inventa_foto(monkeypatch):
    def _estoura(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 5, output=None)
    monkeypatch.setattr(fp.subprocess, "run", _estoura)
    r = fp.rodar(["print(1)"], [], timeout_s=5, rotulo="filho da sombra")
    assert "foto" not in r, r


class _Feito:
    def __init__(self, rc, stdout, stderr=""):
        self.returncode, self.stdout, self.stderr = rc, stdout, stderr


def test_rodar_na_morte_devolve_a_foto(monkeypatch):
    monkeypatch.setattr(fp.subprocess, "run", lambda cmd, **kw: _Feito(
        -6, _linha_de_foto(etapa="walls", t=33.0) + chr(10), "Fatal Python error: Aborted"))
    r = fp.rodar(["print(1)"], [], timeout_s=5, rotulo="filho da sombra")
    assert "morreu" in r["skip"] and r["foto"] == {"etapa": "walls", "t": 33.0}, r


def test_CONTROLE_rodar_rc0_com_JSON_final_devolve_o_mesmo_de_sempre(monkeypatch):
    final = {"file": "p.pdf", "n_rooms": 3, "scale": 50}
    saida = ("ruido de biblioteca" + chr(10) + _linha_de_foto(etapa="rooms", t=1.0)
             + chr(10) + json.dumps(final) + chr(10))
    monkeypatch.setattr(fp.subprocess, "run", lambda cmd, **kw: _Feito(0, saida))
    assert fp.rodar(["print(1)"], [], timeout_s=5) == final


def test_rodar_rc0_com_FOTO_na_ultima_linha_nao_vira_medicao(monkeypatch):
    monkeypatch.setattr(fp.subprocess, "run", lambda cmd, **kw: _Feito(
        0, _linha_de_foto(etapa="rooms", t=1.0, n_rooms=9) + chr(10)))
    r = fp.rodar(["print(1)"], [], timeout_s=5, rotulo="filho da sombra")
    assert "não terminou" in r["skip"], r
    assert "n_rooms" not in r and r["foto"]["etapa"] == "rooms", r


# ── o _measure_page imprime uma foto por etapa e não muda o resultado ────────
def test_measure_page_fotografa_cada_etapa_sem_mudar_a_medicao(tmp_path, monkeypatch, capsys):
    import pdf_vector
    from test_o_filho_devolve_o_proprio_pico import _pdf_em_branco, _sem_vision
    _sem_vision(monkeypatch)
    pdf = _pdf_em_branco(tmp_path)

    monkeypatch.delenv("FILHO_IMPRIME_FOTO", raising=False)
    sem = pdf_vector._measure_page(pdf, 0, "")
    assert capsys.readouterr().out == "", "sem o env o filho não pode imprimir foto"

    monkeypatch.setenv("FILHO_IMPRIME_FOTO", "1")
    com = pdf_vector._measure_page(pdf, 0, "")
    linhas = [l for l in capsys.readouterr().out.splitlines() if fp.MARCA_DA_FOTO in l]
    etapas_fotografadas = [json.loads(l)["etapa"] for l in linhas]
    assert etapas_fotografadas == list(com["etapas"]), (etapas_fotografadas, com["etapas"])

    fora = ("secs", "etapas", "mem_etapas", "mem_kb", "mem_kb_inicio")
    assert ({k: v for k, v in sem.items() if k not in fora}
            == {k: v for k, v in com.items() if k not in fora}), "a foto mudou a medição"


# ── o filho da PROMOÇÃO (main.py) ───────────────────────────────────────────
def test_a_promocao_liga_a_foto_no_env_que_chega_no_filho():
    from test_o_filho_da_medicao_diz_onde_morreu import _o_que_chegou_no_sp_run
    _argv, kw, _logs = _o_que_chegou_no_sp_run(rc=0, stdout="{}")
    assert (kw.get("env") or {}).get("FILHO_IMPRIME_FOTO") == "1", kw.get("env", {}).get("FILHO_IMPRIME_FOTO")


def test_o_log_de_MORTE_da_promocao_diz_a_ultima_etapa_antes_do_stdout():
    from test_o_filho_da_medicao_diz_onde_morreu import _o_que_chegou_no_sp_run
    _argv, _kw, logs = _o_que_chegou_no_sp_run(
        rc=-6, stdout=_linha_de_foto(etapa="walls", t=33.0, vmpeak_mb=1051) + chr(10),
        stderr="Fatal Python error: Aborted")
    msgs = [m for s, m in logs if s == "pdfvec:filho-morreu"]
    assert msgs, logs
    assert "ultima_etapa_lida=walls" in msgs[0], msgs[0]
    assert msgs[0].index("ultima_etapa_lida") < msgs[0].index("stdout:"), msgs[0]


def _estouro_na_promocao(output):
    """Executa o bloco real do filho da promoção com o `subprocess.run`
    estourando o tempo — como em produção, `output` em bytes ou None."""
    import _executa
    import main

    def _estoura(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 75, output=output)

    logs = []
    escopo = dict(vars(main))
    escopo.update({
        "os": os, "pdf_path": "/work/j/prancha.pdf", "page_index": 0,
        "_stem": "PRANCHA-01", "filename": "prancha.pdf", "_pdfvec_falhas": [],
        "_log_error": lambda stage, msg, *a, **k: logs.append((stage, msg)),
        "job_id": "job-teste", "_pdfvec_area_m2": 0.0, "_pdfvec_compr_m": 0.0,
        "_pdfvec_por_prancha": {}, "_vet_secao": "",
    })
    _real = subprocess.run
    subprocess.run = _estoura
    try:
        _executa.roda("process_job", "_pr = _sp.run(_cmd", escopo, tamanho=1)
    finally:
        subprocess.run = _real
    return [m for s, m in logs if s == "pdfvec:promo-falhou"], escopo


def test_o_log_de_ESTOURO_da_promocao_diz_a_ultima_etapa_com_BYTES():
    saida = (_linha_de_foto(etapa="rooms", t=70.2, vmpeak_mb=1680) + chr(10)).encode("utf-8")
    msgs, escopo = _estouro_na_promocao(saida)
    assert msgs, "o estouro não gerou log pdfvec:promo-falhou"
    assert "ultima_etapa_lida=rooms" in msgs[0], msgs[0]
    assert len(msgs[0]) <= 400, len(msgs[0])
    assert [f["motivo"] for f in escopo["_pdfvec_falhas"]] == ["tempo"], (
        "a foto não pode mudar a falha registrada")


def test_o_log_de_ESTOURO_sem_saida_diz_que_nao_ha_etapa():
    msgs, _escopo = _estouro_na_promocao(None)
    assert msgs and "[nenhuma etapa lida]" in msgs[0], msgs


# ── o resumo da sombra ──────────────────────────────────────────────────────
def test_a_sombra_resume_a_foto_curta(monkeypatch, tmp_path):
    from test_sombras_nao_perdem_evidencia import _roda_a_sombra_gorda
    bruto, payload = _roda_a_sombra_gorda(monkeypatch, tmp_path, 1, {
        "skip": "filho da sombra estourou o tempo", "timeout_s": 170,
        "foto": {"etapa": "rooms", "t": 169.9, "vmpeak_mb": 1800}})
    pag = payload["pages"][0]
    assert pag.get("foto_etapa") == "rooms" and pag.get("foto_t") == 169.9, pag
    assert "foto" not in pag, "a foto inteira não cabe no resumo"
