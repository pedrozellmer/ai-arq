# -*- coding: utf-8 -*-
"""A prova de escala por cota cai quando as LINHAS DE COTA sustentam outra escala.

🩸 02/10/2026 — estudo do acervo (H87). Uma planta de casa em 1:40 (a própria
folha escreve "1:40" numa das pranchas) saiu "escala 1:50 PROVADA por 3/4
cota(s)": o `validate_scale` aceita 2 pares cota × parede a ±2 % e, com ~180
cotas e centenas de paredes, a coincidência passa. Cada cota medida contra a
linha de cota que ela mede dá 1:40 em ~100 valores distintos.

📏 No acervo, nas 40 provas da produção com cópia local: as 2 falsas caem e as
38 verdadeiras ficam — inclusive as de só 2 pares, que são o motivo de não se
subir o mínimo de pares (12 verdadeiras têm 2 a 4).

Regras que os guardas prendem:
- o juiz só DESMENTE: a escala não muda e nada é promovido;
- desmente só com grupo FORTE (≥ 10 famílias de valor, amplitude ≥ 3), noutra
  escala (> 15 %), e com mais de 3× o apoio da escala provada;
- valores a 2 % um do outro são a mesma cota (níveis "750,80 / 750,65");
- o juiz olha só a região da validação: a implantação 1:200 não derruba a
  prova da planta 1:50 ao lado;
- prova verdadeira com poucos pares fica provada.

🪤 Fixture SINTÉTICA (pikepdf / listas), nunca arquivo de cliente.
"""
import os
import socket
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pdf_vector  # noqa: E402
import pdfvec_carimbo  # noqa: E402
import pdfvec_cotas as C  # noqa: E402

_PT_M = 0.0254 / 72.0
#: 12 cotas diferentes, de 0,60 a 6,40 m (amplitude 10,7)
_VALORES = (0.60, 0.85, 1.10, 1.45, 1.80, 2.25, 2.70, 3.20, 3.90, 4.60, 5.50, 6.40)


def _cadeia(esc, valores=_VALORES, x0=60.0, y0=780.0, passo=40.0):
    """[(x, y, texto, comprimento_pt)]: uma cota por linha, cada uma sobre a
    sua linha de cota desenhada na escala `esc`."""
    out = []
    for i, v in enumerate(valores):
        out.append((x0, y0 - passo * i, ("%.2f" % v).replace(".", ","), v / (_PT_M * esc)))
    return out


#: parede dupla em volta da cadeia: sem ela a "vista principal" do clustering é
#: uma linha de cota solta, e a validação (e o juiz) olham só aquela caixa
_PAREDE = b"2 w 40 320 m 560 320 l 560 800 l 40 800 l h S 52 332 m 548 332 l 548 788 l 52 788 l h S "


def _pdf(tmp_path, cotas, nome="folha.pdf", moldura=_PAREDE):
    pikepdf = pytest.importorskip("pikepdf")
    pdf = pikepdf.Pdf.new()
    pg = pdf.add_blank_page(page_size=(1191, 842))
    pg.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pikepdf.Dictionary(
        Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)))
    corpo = b"1 w "
    for x, y, txt, L in cotas:
        corpo += b"%.2f %.2f m %.2f %.2f l S " % (x, y - 4, x + L, y - 4)
        corpo += b"BT /F1 9 Tf %.2f %.2f Td (%s) Tj ET " % (x + L / 2 - 9, y, txt.encode("latin-1"))
    pg.Contents = pdf.make_stream(corpo + moldura)
    p = str(tmp_path / nome)
    pdf.save(p)
    return p


def _pares(esc, valores, ruido=0.0):
    return [(esc * (1 + ruido * ((i % 3) - 1)), v) for i, v in enumerate(valores)]


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("rede bloqueada no guarda")))
    monkeypatch.setitem(sys.modules, "fitz", None)


# ── os pares: cota × a linha que passa sob ela ─────────────────────────────

def _tok(cx, cy, w, h, valor):
    return {"text": "x", "value_m": valor, "center": (cx, cy),
            "bbox": (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)}


def test_cota_deitada_casa_com_a_linha_horizontal_sob_ela():
    L = 5.0 / (_PT_M * 50)
    pares = C.pares_cota_linha([_tok(150, 203, 20, 6, 5.0)], [((100, 195), (100 + L, 195))])
    assert len(pares) == 1 and abs(pares[0][0] - 50) < 0.01 and pares[0][1] == 5.0


def test_cota_em_pe_casa_com_a_linha_vertical():
    L = 2.0 / (_PT_M * 25)
    pares = C.pares_cota_linha([_tok(300, 400, 6, 20, 2.0)], [((306, 400 - L / 2), (306, 400 + L / 2))])
    assert len(pares) == 1 and abs(pares[0][0] - 25) < 0.01


def test_CONTROLE_linha_longe_ou_ao_lado_ou_atravessada_nao_casa():
    t = [_tok(150, 203, 20, 6, 5.0)]
    assert C.pares_cota_linha(t, [((100, 180), (400, 180))]) == []      # 23 pt abaixo
    assert C.pares_cota_linha(t, [((200, 197), (400, 197))]) == []      # não passa sob o centro
    assert C.pares_cota_linha(t, [((150, 150), (150, 250))]) == []      # perpendicular


# ── a régua do juiz (pura) ─────────────────────────────────────────────────

def test_grupo_forte_noutra_escala_desmente():
    d = C.juiz_desmente(_pares(40, _VALORES, 0.01), 50)
    assert d and abs(d["escala"] - 40) < 1.5 and d["familias"] == 12 and d["apoio"] == 0


def test_CONTROLE_o_grupo_forte_na_propria_escala_nao_desmente():
    assert C.juiz_desmente(_pares(40, _VALORES, 0.01), 40) is None


def test_menos_de_10_familias_nao_desmente():
    assert C.juiz_desmente(_pares(40, _VALORES[:9]), 50) is None
    assert C.juiz_desmente(_pares(40, _VALORES[:10]), 50)               # controle: 10 basta


def test_amplitude_curta_nao_desmente():
    curtos = [1.0 + 0.1 * i for i in range(12)]                          # 1,0 a 2,1 m
    assert C.juiz_desmente(_pares(40, curtos), 50) is None


def test_niveis_quase_iguais_sao_uma_familia_so():
    niveis = [7.50 + 0.012 * i for i in range(12)] + [0.5, 1.6]          # "750,80/750,65…"
    assert C.juiz_desmente(_pares(40, niveis), 50) is None


def test_apoio_da_escala_provada_protege_a_prova():
    grupo = _pares(40, _VALORES)
    apoio4 = _pares(50, (0.70, 1.30, 2.00, 3.00), 0.05)     # 47,5 / 50 / 52,5
    apoio3 = _pares(50, (0.70, 1.30, 2.00), 0.05)
    assert C.juiz_desmente(grupo + apoio4, 50) is None                  # 4 × 3 = 12, não < 12
    assert C.juiz_desmente(grupo + apoio3, 50)                          # 3 × 3 = 9 < 12


def test_grupo_a_menos_de_15_por_cento_e_a_mesma_escala():
    assert C.juiz_desmente(_pares(44, _VALORES), 50) is None          # 12 %: fora do apoio, dentro dos 15 %
    assert C.juiz_desmente(_pares(42, _VALORES), 50)                    # controle: 16 %


def test_sem_pares_ou_sem_escala_nao_quebra():
    assert C.juiz_desmente([], 50) is None
    assert C.juiz_desmente(_pares(40, _VALORES), 0) is None
    assert C.juiz_desmente(_pares(40, _VALORES), None) is None


# ── no PDF: a região da validação ──────────────────────────────────────────

def _segs(path):
    import pdfplumber
    from pdfvec_rooms import _collect_raw_segments_rapido
    with pdfplumber.open(path) as pdf:
        return _collect_raw_segments_rapido(pdf.pages[0])


def test_no_pdf_a_cadeia_de_1_40_desmente_a_prova_de_1_50(tmp_path):
    p = _pdf(tmp_path, _cadeia(40))
    d = C.prova_desmentida_pela_linha_de_cota(p, 0, 50, None, _segs(p))
    assert d and abs(d["escala"] - 40) < 1.5, d


def test_a_implantacao_fora_da_regiao_nao_derruba_a_prova_da_planta(tmp_path):
    """Implantação 1:200 à esquerda (12 cotas), planta 1:50 à direita (3)."""
    p = _pdf(tmp_path, _cadeia(200, x0=40) + _cadeia(50, valores=(0.90, 1.80, 2.70), x0=700), moldura=b"")
    s = _segs(p)
    assert C.prova_desmentida_pela_linha_de_cota(p, 0, 50, (650, 0, 1191, 842), s) is None
    assert C.prova_desmentida_pela_linha_de_cota(p, 0, 50, None, s)     # controle: a folha toda


# ── a página inteira (o caminho da produção) ───────────────────────────────

def _mede(monkeypatch, path, escala_carimbo, validada=True):
    monkeypatch.setattr(pdfvec_carimbo, "read_carimbo_scale",
                        lambda *a, **k: {"main_scale": escala_carimbo, "declared_scales": [escala_carimbo],
                                         "indicadas": False})
    monkeypatch.setattr(C, "validate_scale",
                        lambda *a, **k: {"n_cotas": 12, "n_matches": 3 if validada else 1, "segunda": None,
                                         "dominante": False, "validada": validada, "exemplos": []})
    return pdf_vector._measure_page(path, 0, "sem-chave")


def test_prova_por_coincidencia_cai_e_a_escala_fica(tmp_path, monkeypatch):
    out = _mede(monkeypatch, _pdf(tmp_path, _cadeia(40)), 50)
    assert out.get("scale") == 50, out                  # a escala NÃO muda
    assert out.get("escala_validada") is False, out
    assert out.get("prova_desmentida", {}).get("escala"), out


def test_CONTROLE_prova_verdadeira_com_2_pares_fica_provada(tmp_path, monkeypatch):
    out = _mede(monkeypatch, _pdf(tmp_path, _cadeia(50)), 50)
    assert out.get("escala_validada") is True, out
    assert "prova_desmentida" not in out


def test_CONTROLE_sem_prova_o_juiz_nem_roda(tmp_path, monkeypatch):
    out = _mede(monkeypatch, _pdf(tmp_path, _cadeia(40)), 50, validada=False)
    assert out.get("escala_validada") is False and "prova_desmentida" not in out, out


def test_erro_no_juiz_deixa_a_prova_como_estava(tmp_path, monkeypatch):
    def _quebra(*a, **k):
        raise RuntimeError("juiz quebrou")
    monkeypatch.setattr(C, "prova_desmentida_pela_linha_de_cota", _quebra)
    out = _mede(monkeypatch, _pdf(tmp_path, _cadeia(40)), 50)
    assert out.get("escala_validada") is True, out
    assert out.get("err_prova_juiz", "").startswith("RuntimeError"), out
    assert "err_cotas" not in out, out


def test_a_prova_desmentida_vira_declaracao_com_a_frase_do_carimbo():
    import main as M
    promove, motivo = M._a_escala_sustenta_a_medicao({"scale_src": "carimbo", "escala_validada": False})
    assert promove and "sem confirmação por medida" in motivo
