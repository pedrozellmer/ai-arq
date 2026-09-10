# -*- coding: utf-8 -*-
"""O leitor rápido do content stream dá a MESMA coleta das salas que o pdfminer.

🩸 10/09/2026 — a foto por etapa mostrou em produção que a página de 234 ambientes
morre no PARSE: o pdfplumber montando o layout do pdfminer levou 62 s e bateu o
teto de 2 GB. O leitor do content stream (`pdfvec_walls._fast_stream_segments`)
já existia nas paredes. A/B no corpus de teste: coleta 8–10× mais rápida, pico
51–75% menor e as MESMAS salas, vistas e envoltória nas 7 pranchas — depois de
consertar dois defeitos da coleta antiga que o A/B achou (diagonal espelhada e
salas que dependiam da ordem dos traços).

Estes guardas CHAMAM as duas coletas, `detect_rooms` e `_measure_page`, num PDF
sintético com um pouco de tudo que um CAD exporta.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import pdf_vector  # noqa: E402
import pdfvec_rooms  # noqa: E402
import pdfvec_walls  # noqa: E402


def _pdf_com_de_tudo(tmp_path):
    pikepdf = pytest.importorskip("pikepdf")
    p = tmp_path / "de_tudo.pdf"
    pdf = pikepdf.Pdf.new()
    pagina = pdf.add_blank_page(page_size=(842, 595))
    # bloco de CAD: uma linha e uma curva, invocado duas vezes com transformação
    bloco = pdf.make_stream(b"1 w 0 0 m 40 0 l S 0 10 m 10 40 30 40 40 10 c S")
    bloco["/Type"] = pikepdf.Name.XObject
    bloco["/Subtype"] = pikepdf.Name.Form
    bloco["/BBox"] = [0, 0, 60, 60]
    pagina.Resources = pikepdf.Dictionary({"/XObject": pikepdf.Dictionary({"/Fm0": bloco})})
    conteudo = (b"1 w 100 100 200 150 re S "                     # retângulo
                b"400 500 m 520 380 l S "                          # diagonal DESCENDENTE
                b"600 100 m 700 100 l S 600 100 m 700 100 l S "   # linha duplicada
                b"50 50 m 50.5 50.2 l S "                         # micro-segmento
                b"300 300 m 350 360 400 360 450 300 c S "         # curva -> corda
                b"500 200 m 560 200 l 560 260 l h f "             # caminho só preenchido
                b"10 10 30 30 re W n "                             # recorte, não pinta
                b"q 1 0 0 1 150 400 cm /Fm0 Do Q "
                b"q 1 0 0 1 250 420 cm /Fm0 Do Q")
    pagina.Contents = pdf.make_stream(conteudo)
    pdf.save(str(p))
    return str(p)


def _pdf_com_salas(tmp_path):
    pikepdf = pytest.importorskip("pikepdf")
    p = tmp_path / "salas.pdf"
    pdf = pikepdf.Pdf.new()
    pagina = pdf.add_blank_page(page_size=(842, 595))
    pagina.Contents = pdf.make_stream(
        b"1 w 100 100 200 150 re S 400 100 200 150 re S "
        b"100 500 m 400 500 l S 400 500 m 400 330 l S "
        b"400 330 m 200 330 l S 200 330 m 100 500 l S")   # trapézio com lado descendo
    pdf.save(str(p))
    return str(p)


def _chaves(segs):
    fora = set()
    for (ax, ay), (bx, by) in segs:
        k = (round(ax, 1), round(ay, 1), round(bx, 1), round(by, 1))
        if k[:2] > k[2:]:
            k = (k[2], k[3], k[0], k[1])
        fora.add(k)
    return fora


def _as_duas_coletas(pdf):
    import pdfplumber
    with pdfplumber.open(pdf) as d:
        pg = d.pages[0]
        return (pdfvec_rooms._collect_raw_segments(pg),
                pdfvec_rooms._collect_raw_segments_rapido(pg),
                float(pg.width), float(pg.height))


# ── a coleta ──────────────────────────────────────────────────────────────────
def test_as_duas_coletas_dao_os_MESMOS_segmentos_num_pdf_com_de_tudo(tmp_path):
    pdfminer, rapido, _w, _h = _as_duas_coletas(_pdf_com_de_tudo(tmp_path))
    a, b = _chaves(pdfminer), _chaves(rapido)
    assert a == b, {"so_pdfminer": sorted(a - b), "so_rapido": sorted(b - a)}
    assert len(rapido) == len(set(_chaves(rapido))), "o leitor rápido não deduplicou"
    assert (50.0, 50.0, 50.5, 50.2) not in b, "o micro-segmento passou pelo filtro"
    assert (300.0, 300.0, 450.0, 300.0) in b, "a curva não virou corda"


def test_as_salas_sao_as_MESMAS_com_as_duas_coletas(tmp_path):
    pdf = _pdf_com_salas(tmp_path)
    pdfminer, rapido, w, h = _as_duas_coletas(pdf)
    a = pdfvec_rooms.detect_rooms(pdf, 0, 100.0, None, _segments=(pdfminer, w, h))
    b = pdfvec_rooms.detect_rooms(pdf, 0, 100.0, None, _segments=(rapido, w, h))
    assert [round(r["area_m2"], 2) for r in a] == [round(r["area_m2"], 2) for r in b], (a, b)
    assert len(b) == 3, "2 retângulos + o trapézio de parede inclinada: %r" % b


def test_a_curva_vira_CORDA_nas_salas_e_NAO_nas_paredes():
    ctm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    dados = b"300 300 m 350 360 400 360 450 300 c S"
    com = pdfvec_walls._fast_stream_segments(dados, ctm, None, cordas=True)
    sem = pdfvec_walls._fast_stream_segments(dados, ctm, None)
    assert (300.0, 300.0, 450.0, 300.0) in com, com
    assert sem == [], "paredes não podem ganhar corda de curva: %r" % sem


def test_as_cordas_atravessam_o_BLOCO_de_CAD(tmp_path):
    _pdfminer, rapido, _w, _h = _as_duas_coletas(_pdf_com_de_tudo(tmp_path))
    # a corda da curva do bloco, (0,10)-(40,10), transladada por (150,400)
    assert (150.0, 410.0, 190.0, 410.0) in _chaves(rapido), sorted(_chaves(rapido))


# ── o parse único ─────────────────────────────────────────────────────────────
def _escala_pelo_viewport(monkeypatch):
    import pdfvec_carimbo
    import pdfvec_layers
    monkeypatch.setattr(pdfvec_layers, "scale_from_viewport",
                        lambda *a, **k: {"main_scale": 100.0, "main_bbox": None,
                                         "viewports": [], "page_size": (842.0, 595.0)})

    def _boom(*a, **k):
        raise RuntimeError("Vision desligada no teste")
    monkeypatch.setattr(pdfvec_carimbo, "read_carimbo_scale", _boom)


def _espiao_do_pdfminer(monkeypatch):
    chamadas = []
    real = pdfvec_rooms._collect_raw_segments

    def espiao(pg):
        chamadas.append(1)
        return real(pg)
    monkeypatch.setattr(pdfvec_rooms, "_collect_raw_segments", espiao)
    return chamadas


def test_o_parse_unico_usa_o_leitor_RAPIDO_por_padrao(tmp_path, monkeypatch):
    _escala_pelo_viewport(monkeypatch)
    monkeypatch.delenv("PDFVEC_PARSE_RAPIDO", raising=False)
    monkeypatch.delenv("PDFVEC_PARSE_UNICO", raising=False)
    chamadas = _espiao_do_pdfminer(monkeypatch)
    out = pdf_vector._measure_page(_pdf_com_salas(tmp_path), 0, "")
    assert out.get("parse_leitor") == "rapido", out
    assert chamadas == [], "o parse único chamou o pdfminer mesmo com o leitor rápido ligado"


def test_leitor_rapido_quebrado_cai_no_PDFMINER_e_registra(tmp_path, monkeypatch):
    _escala_pelo_viewport(monkeypatch)
    monkeypatch.delenv("PDFVEC_PARSE_RAPIDO", raising=False)
    normal = pdf_vector._measure_page(_pdf_com_salas(tmp_path), 0, "")

    def _quebra(pg):
        raise ValueError("imagem inline grande demais para o caminho rapido")
    monkeypatch.setattr(pdfvec_rooms, "_collect_raw_segments_rapido", _quebra)
    out = pdf_vector._measure_page(_pdf_com_salas(tmp_path), 0, "")
    assert out.get("parse_leitor") == "pdfminer", out
    assert out.get("err_parse_rapido", "").startswith("ValueError"), out
    assert out.get("rooms_m2") == normal.get("rooms_m2"), (out.get("rooms_m2"), normal.get("rooms_m2"))


def test_falta_de_memoria_no_leitor_rapido_NAO_cai_no_pdfminer(tmp_path, monkeypatch):
    _escala_pelo_viewport(monkeypatch)
    monkeypatch.delenv("PDFVEC_PARSE_RAPIDO", raising=False)

    def _sem_memoria(pg):
        raise MemoryError("sem memória lendo o content stream")
    monkeypatch.setattr(pdfvec_rooms, "_collect_raw_segments_rapido", _sem_memoria)
    out = pdf_vector._measure_page(_pdf_com_salas(tmp_path), 0, "")
    assert out.get("err_parse_unico", "").startswith("MemoryError"), out
    # o parse ÚNICO não tentou o pdfminer (o caminho antigo por etapa, que roda
    # depois de qualquer falha do parse único, é outra decisão)
    assert "parse_leitor" not in out, out
    assert not any(k == "err_parse_rapido" for k in out), (
        "falta de memória no leitor rápido não pode virar 'tenta o pdfminer'")


def test_interruptor_DESLIGADO_usa_o_pdfminer(tmp_path, monkeypatch):
    _escala_pelo_viewport(monkeypatch)
    monkeypatch.setenv("PDFVEC_PARSE_RAPIDO", "0")
    out = pdf_vector._measure_page(_pdf_com_salas(tmp_path), 0, "")
    assert out.get("parse_leitor") == "pdfminer", out


def test_ligado_e_desligado_dao_a_MESMA_medicao(tmp_path, monkeypatch):
    _escala_pelo_viewport(monkeypatch)
    pdf = _pdf_com_salas(tmp_path)
    fora = ("secs", "etapas", "mem_etapas", "mem_kb", "mem_kb_inicio",
            "parse_unico", "parse_leitor", "err_parse_rapido")
    monkeypatch.setenv("PDFVEC_PARSE_RAPIDO", "0")
    a = {k: v for k, v in pdf_vector._measure_page(pdf, 0, "").items() if k not in fora}
    monkeypatch.setenv("PDFVEC_PARSE_RAPIDO", "1")
    b = {k: v for k, v in pdf_vector._measure_page(pdf, 0, "").items() if k not in fora}
    assert a == b, {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
