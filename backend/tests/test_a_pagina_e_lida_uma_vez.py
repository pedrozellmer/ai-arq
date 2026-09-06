# -*- coding: utf-8 -*-
"""A medição vetorial de PDF lê a página UMA vez, não três — sem mudar um número.

🔬 05/09/2026, PASSO 13 do estudo do teto. detect_views, detect_rooms e a
envoltória chamavam a MESMA coleta (pdfvec_rooms._collect_raw_segments) três
vezes na mesma página. Medido: o parse é ~85% do tempo de cada etapa (HNSC
31+33+32 s; CPQ11 50+74+92 s) e três picos de memória empilhados em vez de um.
Com o teto de memória já domado (passo 8), o muro que sobrou é o cronômetro de
75 s — e a página do cliente-39 leva 103 s.

A coleta é função determinística da página e nenhum consumidor muta a lista
(`_filter_segments` cria `kept`; `_drop_frame_and_stamp` cria `out`), então
servir a mesma lista aos três não pode mudar resultado. Este arquivo prova
isso num PDF sintético e garante que os QUATRO consumidores recebem a lista.

🪤 Interruptor PDFVEC_PARSE_UNICO=0 volta ao parse por etapa sem deploy.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import pdf_vector   # noqa: E402
import pdfvec_rooms  # noqa: E402
import pdfvec_views  # noqa: E402
from _corpo import fonte, sem_comentarios  # noqa: E402

_SRC = sem_comentarios(fonte("pdf_vector.py"))


# ── fixture: uma folha com dois quadrados fechados (2 "ambientes") ─────────
def _pdf_com_salas(tmp_path):
    pikepdf = pytest.importorskip("pikepdf")
    p = tmp_path / "salas.pdf"
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(842, 595))
    # dois retângulos de 200×150 pt: em 1:100, 200 pt = 7,06 m → ~37 m² cada
    conteudo = (b"1 w 100 100 200 150 re S 400 100 200 150 re S "
                b"100 400 m 700 400 l S ")     # + uma linha solta (não fecha nada)
    page.Contents = pdf.make_stream(conteudo)
    pdf.save(str(p))
    return str(p)


def _escala_pelo_viewport(monkeypatch):
    import pdfvec_layers
    import pdfvec_carimbo
    monkeypatch.setattr(pdfvec_layers, "scale_from_viewport",
                        lambda *a, **k: {"main_scale": 100.0, "main_bbox": None,
                                         "viewports": [], "page_size": (842.0, 595.0)})
    def _boom(*a, **k):
        raise RuntimeError("Vision desligada no teste")
    monkeypatch.setattr(pdfvec_carimbo, "read_carimbo_scale", _boom)


def _sem_ruido(out: dict) -> dict:
    """Tira o que muda entre rodadas (tempo, memória) e o carimbo do parse único."""
    return {k: v for k, v in out.items()
            if k not in ("secs", "etapas", "mem_etapas", "mem_kb", "mem_kb_inicio",
                         "parse_unico", "err_parse_unico")}


# ── 1. detect_rooms com _segments == detect_rooms parseando ───────────────
def test_detect_rooms_com_segmentos_prontos_da_o_mesmo_resultado(tmp_path):
    pdf = _pdf_com_salas(tmp_path)
    import pdfplumber
    with pdfplumber.open(pdf) as d:
        pg = d.pages[0]
        segs = (pdfvec_rooms._collect_raw_segments(pg), float(pg.width), float(pg.height))
    a = pdfvec_rooms.detect_rooms(pdf, 0, 100.0, None)
    b = pdfvec_rooms.detect_rooms(pdf, 0, 100.0, None, _segments=segs)
    assert a == b
    assert len(a) == 2, f"o fixture tem 2 salas fechadas, saiu {len(a)}"
    # e a lista compartilhada NÃO foi mutada pelo consumidor
    c = pdfvec_rooms.detect_rooms(pdf, 0, 100.0, None, _segments=segs)
    assert c == b, "detect_rooms mutou a lista de segmentos — o 3º consumidor veria outra página"


def test_detect_views_com_os_mesmos_segmentos_nao_muta_a_lista(tmp_path):
    pdf = _pdf_com_salas(tmp_path)
    import pdfplumber
    with pdfplumber.open(pdf) as d:
        pg = d.pages[0]
        raw = pdfvec_rooms._collect_raw_segments(pg)
        segs = (raw, float(pg.width), float(pg.height))
    antes = list(raw)
    pdfvec_views.detect_views(pdf, 0, _segments=segs)
    assert raw == antes, "detect_views mutou a lista compartilhada"


# ── 2. _measure_page: os QUATRO consumidores recebem a lista; resultado igual ──
def _grava_chamadas(monkeypatch):
    chamadas = {"views": [], "rooms": []}
    _dv, _dr = pdfvec_views.detect_views, pdfvec_rooms.detect_rooms

    def dv(*a, **k):
        chamadas["views"].append(k.get("_segments"))
        return _dv(*a, **k)

    def dr(*a, **k):
        chamadas["rooms"].append(k.get("_segments"))
        return _dr(*a, **k)
    monkeypatch.setattr(pdfvec_views, "detect_views", dv)
    monkeypatch.setattr(pdfvec_rooms, "detect_rooms", dr)
    return chamadas


def test_com_o_interruptor_ligado_TODOS_recebem_a_mesma_lista(tmp_path, monkeypatch):
    _escala_pelo_viewport(monkeypatch)
    monkeypatch.delenv("PDFVEC_PARSE_UNICO", raising=False)   # default = ligado
    ch = _grava_chamadas(monkeypatch)
    out = pdf_vector._measure_page(_pdf_com_salas(tmp_path), 0, "")
    assert out.get("parse_unico", 0) > 0, out
    assert "parse" in out["etapas"]
    assert ch["views"] and ch["rooms"], "views e rooms têm que ter sido chamados"
    todos = ch["views"] + ch["rooms"]
    assert all(s is not None for s in todos), f"algum consumidor parseou sozinho: {[s is None for s in todos]}"
    assert len({id(s[0]) for s in todos}) == 1, "cada consumidor recebeu uma lista diferente — não é parse único"
    assert len(ch["rooms"]) >= 2, "salas + envoltória são duas chamadas de detect_rooms"


def test_com_o_interruptor_desligado_volta_ao_parse_por_etapa(tmp_path, monkeypatch):
    _escala_pelo_viewport(monkeypatch)
    monkeypatch.setenv("PDFVEC_PARSE_UNICO", "0")
    ch = _grava_chamadas(monkeypatch)
    out = pdf_vector._measure_page(_pdf_com_salas(tmp_path), 0, "")
    assert "parse_unico" not in out and "parse" not in out["etapas"]
    assert all(s is None for s in ch["views"] + ch["rooms"])


def test_ligado_e_desligado_dao_o_MESMO_resultado(tmp_path, monkeypatch):
    _escala_pelo_viewport(monkeypatch)
    pdf = _pdf_com_salas(tmp_path)
    monkeypatch.setenv("PDFVEC_PARSE_UNICO", "0")
    a = _sem_ruido(pdf_vector._measure_page(pdf, 0, ""))
    monkeypatch.setenv("PDFVEC_PARSE_UNICO", "1")
    b = _sem_ruido(pdf_vector._measure_page(pdf, 0, ""))
    assert a == b, {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
    # com bbox=None o detect_views elege UMA vista principal (um dos quadrados): 1 sala
    assert a.get("n_rooms", 0) >= 1 and a.get("rooms_m2", 0) > 0


def test_falha_na_coleta_unica_cai_no_caminho_antigo(tmp_path, monkeypatch):
    """Coleta única quebrada não pode derrubar a medição: vira None e cada
    etapa parseia como antes."""
    _escala_pelo_viewport(monkeypatch)
    monkeypatch.delenv("PDFVEC_PARSE_UNICO", raising=False)
    def _boom(*a, **k):
        raise RuntimeError("coleta quebrada de propósito")
    monkeypatch.setattr(pdfvec_rooms, "_collect_raw_segments", _boom)
    out = pdf_vector._measure_page(_pdf_com_salas(tmp_path), 0, "")
    assert "err_parse_unico" in out and "parse_unico" not in out
    # e a medição seguiu pelo caminho antigo (views tem a própria cópia da coleta)
    assert "n_views" in out or "err_views" in out


# ── 3. fonte: interruptor e os quatro repasses ─────────────────────────────
def test_o_interruptor_existe_e_o_default_e_ligado():
    assert 'os.environ.get("PDFVEC_PARSE_UNICO", "1") != "0"' in _SRC


def test_os_quatro_consumidores_recebem__segments():
    assert _SRC.count("_segments=_segs") == 4, (
        "views + rooms + rooms(viewport irmã) + envoltória = 4 repasses; "
        f"achei {_SRC.count('_segments=_segs')}")


# ── controle ──────────────────────────────────────────────────────────────
def test_CONTROLE_o_gravador_reprova_chamada_sem_segments():
    ch = {"views": [None], "rooms": [None, None]}
    assert not all(s is not None for s in ch["views"] + ch["rooms"])
