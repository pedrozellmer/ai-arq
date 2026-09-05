# -*- coding: utf-8 -*-
"""O filho da medição de PDF devolve o PRÓPRIO pico de memória e o tempo por etapa.

🔬 05/09/2026, PASSO 3 do estudo do teto. O RLIMIT_AS de 2 GB cobra endereço
VIRTUAL (VmPeak). Tudo que a gente tinha medido era RESIDENTE (VmHWM): o
contêiner no Render, o RSS local. O filho do William (135fdfac) morreu com
≤ ~1,06 GB residentes quando o kernel cobrou 2 GB virtuais — a folga entre os
dois é a incógnita que decide o valor do teto, e NUNCA foi medida em produção.
O próprio comentário do teto (03/09) admite: "não medimos ainda o pico das 109
medições que dão certo".

Só observação: o filho lê /proc/self/status no início, após cada etapa e nos
dois returns, e devolve no MESMO JSON que já manda pro pai. O pai guarda em
`_pdfvec_por_prancha` e grava uma linha compacta `pdfvec:memoria`. Nenhum
número medido muda.

🪤 No Windows não existe /proc: tudo cai em {} e nada quebra — por isso as
asserções de valor só rodam em Linux (o CI), e as de FORMA rodam em qualquer
sistema.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import pdf_vector  # noqa: E402
from _corpo import fonte, sem_comentarios  # noqa: E402

_SRC_MAIN = sem_comentarios(fonte("main.py"))
_SO_LINUX = pytest.mark.skipif(not sys.platform.startswith("linux"),
                               reason="/proc só existe no Linux; produção é Linux")


# ── o leitor de /proc ─────────────────────────────────────────────────────
def test_parse_le_os_campos_que_importam():
    txt = ("Name:\tpython3\nVmPeak:\t 2048000 kB\nVmSize:\t 1500000 kB\n"
           "VmHWM:\t  900000 kB\nVmRSS:\t  850000 kB\nVmData:\t 1200000 kB\nThreads:\t1\n")
    m = pdf_vector._parse_proc_status(txt)
    assert m == {"VmPeak": 2048000, "VmSize": 1500000, "VmHWM": 900000,
                 "VmRSS": 850000, "VmData": 1200000}


def test_CONTROLE_parse_nao_engasga_com_lixo():
    assert pdf_vector._parse_proc_status("") == {}
    assert pdf_vector._parse_proc_status("VmPeak:\tnão-é-número\nqualquer coisa\n") == {}
    assert pdf_vector._parse_proc_status(None) == {}


def test_mem_kb_nunca_levanta_e_devolve_dict():
    m = pdf_vector._mem_kb()
    assert isinstance(m, dict)


@_SO_LINUX
def test_no_linux_o_pico_virtual_e_o_residente_vem_preenchidos():
    m = pdf_vector._mem_kb()
    assert m.get("VmPeak", 0) > 0 and m.get("VmHWM", 0) > 0, m
    assert m["VmPeak"] >= m["VmHWM"], "virtual nunca é menor que residente"
    assert m.get("ru_maxrss", 0) > 0


# ── o filho devolve etapas e memória nos DOIS returns ─────────────────────
def _pdf_em_branco(tmp_path):
    pikepdf = pytest.importorskip("pikepdf")
    p = tmp_path / "branco.pdf"
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(842, 595))
    pdf.save(str(p))
    return str(p)


def _sem_vision(monkeypatch):
    # 🚫 nada de chamada paga nem de rede no teste: o carimbo falha na hora
    import pdfvec_carimbo
    def _boom(*a, **k):
        raise RuntimeError("Vision desligada no teste")
    monkeypatch.setattr(pdfvec_carimbo, "read_carimbo_scale", _boom)


def test_retorno_cedo_sem_escala_TAMBEM_devolve_etapas_e_memoria(tmp_path, monkeypatch):
    _sem_vision(monkeypatch)
    out = pdf_vector._measure_page(_pdf_em_branco(tmp_path), 0, "")
    assert out.get("skip"), "página em branco tinha que sair por 'sem escala'"
    for k in ("mem_kb_inicio", "mem_kb", "etapas", "mem_etapas", "secs"):
        assert k in out, f"faltou {k} no retorno cedo — a morte por memória mora ANTES da escala"
    assert isinstance(out["etapas"], dict) and isinstance(out["mem_kb"], dict)
    assert {"viewport", "carimbo", "cotas_derivacao"} <= set(out["etapas"]), out["etapas"]
    assert all(isinstance(v, float) for v in out["etapas"].values())


def test_caminho_completo_devolve_o_tempo_de_cada_etapa(tmp_path, monkeypatch):
    _sem_vision(monkeypatch)
    import pdfvec_layers
    # escala vinda do viewport: pula a Vision e entra nas etapas pesadas
    monkeypatch.setattr(pdfvec_layers, "scale_from_viewport",
                        lambda *a, **k: {"main_scale": 100.0, "main_bbox": (0.0, 0.0, 842.0, 595.0),
                                         "viewports": [], "page_size": (842.0, 595.0)})
    out = pdf_vector._measure_page(_pdf_em_branco(tmp_path), 0, "")
    assert out.get("scale") == 100.0 and "skip" not in out
    et = out["etapas"]
    assert {"viewport", "rooms", "envoltoria", "walls", "cotas", "layers"} <= set(et), et
    assert "carimbo" not in et, "com viewport a Vision não roda — e não pode aparecer como etapa"
    assert "mem_kb" in out and "mem_etapas" in out


@_SO_LINUX
def test_no_linux_o_JSON_do_filho_traz_VmPeak_maior_que_zero(tmp_path, monkeypatch):
    _sem_vision(monkeypatch)
    out = pdf_vector._measure_page(_pdf_em_branco(tmp_path), 0, "")
    assert out["mem_kb"].get("VmPeak", 0) > 0
    assert out["mem_kb_inicio"].get("VmSize", 0) > 0
    assert out["mem_etapas"], "cada etapa tem que deixar [VmRSS, VmHWM]"


# ── o pai GUARDA e GRAVA ──────────────────────────────────────────────────
def test_o_pai_guarda_memoria_e_etapas_nos_DOIS_ramos_da_promocao():
    assert _SRC_MAIN.count('"mem_kb": _vm.get("mem_kb") or {}') == 2, (
        "os dois ramos da promoção (com prova de cota e sem) têm que guardar mem_kb")
    assert _SRC_MAIN.count('"etapas": _vm.get("etapas") or {}') == 2
    assert _SRC_MAIN.count('"mem_kb_inicio": _vm.get("mem_kb_inicio") or {}') == 2


def test_o_pai_grava_a_linha_pdfvec_memoria_com_VmPeak_e_VmHWM():
    # 🪤 o NOME do stage também aparece na lista _STAGES_DIAGNOSTICO — procurar a CHAMADA
    i = _SRC_MAIN.find('_log_error("pdfvec:memoria"')
    assert i > 0, "o log pdfvec:memoria sumiu — o número volta a não existir no banco"
    trecho = _SRC_MAIN[max(0, i - 1500):i]
    for chave in ("VmPeak", "VmHWM", "ini_VmSize", "etapas="):
        assert chave in trecho, f"a linha pdfvec:memoria perdeu {chave}"


def test_pdfvec_memoria_e_diagnostico_nao_erro():
    """🪤 23/08: stage novo com severity padrão entope o painel 'Erros do motor'."""
    i = _SRC_MAIN.find("_STAGES_DIAGNOSTICO = frozenset(")
    assert i > 0
    assert '"pdfvec:memoria"' in _SRC_MAIN[i:i + 2500]


# ── controles ─────────────────────────────────────────────────────────────
def test_CONTROLE_a_checagem_dos_dois_ramos_sabe_REPROVAR():
    falso = 'x = {"secs": float(_vm.get("secs") or 0)}'
    assert falso.count('"mem_kb": _vm.get("mem_kb") or {}') == 0
