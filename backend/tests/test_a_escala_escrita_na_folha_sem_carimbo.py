# -*- coding: utf-8 -*-
"""A escala ESCRITA na folha é lida do texto quando o carimbo não diz nada.

🩸 25/09/2026 — job `87adfbde` (projeto de interiores, 2 PDF). Cada folha traz
"ESCALA 1 : 75" logo abaixo do título da planta, e o log dizia `sem escala
(viewport, carimbo nem cota)` → nada medido. A leitura do rótulo ao lado da
vista só rodava quando o carimbo dizia "indicadas" (gatilho de quando isso
custava Vision); o carimbo destas folhas nem tinha campo de escala.
📏 Amostra de 131 páginas mortas "sem escala": 18, de 5 clientes, tinham
"ESC… 1:N" escrito. Ler o texto é de graça.

Regras que os guardas prendem:
- carimbo sem escala e sem "indicadas" → vale o "ESCALA 1:N" escrito na folha;
- só o rótulo COM a palavra; "1:75" solto não decide;
- carimbo que tem escala manda; "indicadas" segue pelo caminho da vista;
- a procedência nova tem frase pro cliente, e diz que é DECLARAÇÃO.
"""
import os
import socket
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

# 🩸 A 1ª versão montava o PDF com `fitz` (PyMuPDF) e fazia `importorskip` no
# TOPO: sem `fitz` (o CI e a produção não têm) o arquivo inteiro pulava e o
# código de produção usava `fitz` também — o conserto era inerte lá. Agora o PDF
# nasce com pikepdf (requirements), como nos outros guardas de PDF.
import pdf_vector  # noqa: E402
import pdfvec_carimbo  # noqa: E402
import pdfvec_escala_por_vista  # noqa: E402


def _pdf(tmp_path, rotulo="ESCALA 1 : 75"):
    """Uma folha A3 deitada com uma planta de linhas, título e o rótulo embaixo."""
    pikepdf = pytest.importorskip("pikepdf")
    pdf = pikepdf.Pdf.new()
    pg = pdf.add_blank_page(page_size=(1191, 842))
    pg.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pikepdf.Dictionary(
        Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)))
    linhas = b"2 w 200 342 m 700 342 l S 700 342 m 700 642 l S 700 642 m 200 642 l S " \
             b"200 642 m 200 342 l S 450 342 m 450 642 l S "
    texto = b"BT /F1 12 Tf 300 302 Td (PLANTA DO APARTAMENTO) Tj ET "
    if rotulo:
        texto += b"BT /F1 9 Tf 320 282 Td (" + rotulo.encode("latin-1") + b") Tj ET "
    pg.Contents = pdf.make_stream(linhas + texto)
    p = str(tmp_path / "folha.pdf")
    pdf.save(p)
    return p


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("rede bloqueada no guarda")))
    # 🔒 O CI e a produção NÃO têm `fitz` (PyMuPDF). Esta máquina tem — e foi
    # por isso que a 1ª versão passou aqui e era inerte lá. Com `fitz` bloqueado,
    # código que depender dele quebra ESTE guarda também aqui.
    monkeypatch.setitem(sys.modules, "fitz", None)


def _carimbo(monkeypatch, escala=None, indicadas=False):
    monkeypatch.setattr(pdfvec_carimbo, "read_carimbo_scale",
                        lambda *a, **k: {"main_scale": escala, "declared_scales": [escala] if escala else [],
                                         "indicadas": indicadas})


def test_a_escala_escrita_na_folha_vale_quando_o_carimbo_nao_diz(tmp_path, monkeypatch):
    _carimbo(monkeypatch)
    out = pdf_vector._measure_page(_pdf(tmp_path), 0, "sem-chave")
    assert out.get("scale_src") == "texto", out.get("skip")
    assert out.get("scale") == 75


def test_CONTROLE_razao_solta_sem_a_palavra_nao_decide(tmp_path, monkeypatch):
    _carimbo(monkeypatch)
    out = pdf_vector._measure_page(_pdf(tmp_path, rotulo="1 : 75"), 0, "sem-chave")
    assert out.get("scale_src") != "texto"


def test_CONTROLE_sem_rotulo_nenhum_continua_sem_escala_pelo_texto(tmp_path, monkeypatch):
    _carimbo(monkeypatch)
    out = pdf_vector._measure_page(_pdf(tmp_path, rotulo=None), 0, "sem-chave")
    assert out.get("scale_src") != "texto"


def test_carimbo_com_escala_manda(tmp_path, monkeypatch):
    _carimbo(monkeypatch, escala=100)
    out = pdf_vector._measure_page(_pdf(tmp_path), 0, "sem-chave")
    assert out.get("scale_src") == "carimbo" and out.get("scale") == 100


def test_indicadas_segue_pelo_caminho_da_vista(tmp_path, monkeypatch):
    """Com 'indicadas', quem lê é o leitor por vista — não este."""
    _carimbo(monkeypatch, indicadas=True)
    monkeypatch.setattr(pdfvec_escala_por_vista, "read_view_scales",
                        lambda *a, **k: {"main_scale": None})
    out = pdf_vector._measure_page(_pdf(tmp_path), 0, "sem-chave")
    assert out.get("scale_src") != "texto"


def test_a_fonte_nova_tem_frase_de_procedencia_e_diz_que_e_declaracao():
    import main as M
    assert "texto" in M._FONTE_DA_ESCALA
    como, ressalva = M._frase_da_escala_sem_prova("texto")
    assert como and "declara" in ressalva.lower()


def test_a_escala_do_texto_nao_vira_medida():
    """Declarada, não medida: a promoção entra como estimado (regra nº1)."""
    import main as M
    promove, motivo = M._a_escala_sustenta_a_medicao({"scale_src": "texto"})
    assert promove and "sem confirmação por medida" in motivo
