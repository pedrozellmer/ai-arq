# -*- coding: utf-8 -*-
"""O título da vista escrito no PAPEL (como o Revit exporta) vale como título.

🩸 25/09/2026 — job `42f99f4f` (esgoto e pluvial exportados do REVIT). Cada
folha tinha 16 janelas e NENHUM título achado: o Revit escreve o nome de cada
vista no espaço do papel, logo abaixo da janela (layer `G-ANNO-TTLB`), com a
escala numa linha embaixo. Entre as vistas, três "3D - Térreo - …" — o
isométrico da tubulação — foram somadas como planta: 83% do tubo "✓ MEDIDO"
da folha 1 (planta 9,3 m, planilha 54,3 m).

Regras que os guardas prendem:
- sem título no modelo, vale o texto MAIOR logo abaixo da janela, no papel;
- a linha só de escala ("1 : 50") não é título; texto longe da janela também não;
- título achado no modelo manda (o papel é o plano B);
- "3D …" e "axonométrica" são o mesmo objeto redesenhado: 'fora'.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import tipo_do_desenho  # noqa: E402


def _viewport(lay, janela, centro_papel, esc=10.0):
    x0, y0, x1, y1 = janela
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    vp = lay.add_viewport(center=centro_papel, size=((x1 - x0) * esc, (y1 - y0) * esc),
                          view_center_point=(cx, cy), view_height=(y1 - y0))
    vp.dxf.view_target_point = (0, 0, 0)
    return vp


def _titulo_papel(lay, texto, centro_papel, janela, esc=10.0, abaixo=3.0, altura=3.0):
    """Texto no PAPEL junto do canto de baixo-esquerdo da janela (como o Revit)."""
    w = (janela[2] - janela[0]) * esc
    h = (janela[3] - janela[1]) * esc
    x0 = centro_papel[0] - w / 2
    y0 = centro_papel[1] - h / 2
    lay.add_text(texto, dxfattribs={"height": altura, "insert": (x0 + 2, y0 - abaixo)})
    return x0, y0


def _arquivo(tmp_path, titulo_3d="3D - Térreo - Banho", abaixo=3.0, titulo_modelo_3d=None,
             so_escala=False, escala_grande=False):
    """Planta (10 m de tubo) e vista 3D (30 m do MESMO tubo redesenhado), cada
    uma numa janela da mesma folha, títulos no PAPEL."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((2, 5), (12, 5), dxfattribs={"layer": "P-PIPE"})            # planta
    for k in range(3):                                                        # 3D
        msp.add_line((42, 3 + 3 * k), (52, 3 + 3 * k), dxfattribs={"layer": "P-PIPE"})
    if titulo_modelo_3d:
        msp.add_text(titulo_modelo_3d, dxfattribs={"height": 0.5, "insert": (43, 1)})
    lay = doc.layouts.new("FOLHA 01")
    jp, j3 = (0, 0, 20, 15), (40, 0, 60, 15)
    _viewport(lay, jp, (150, 200))
    _viewport(lay, j3, (400, 200))
    # o título da planta é um pouco MAIOR: se a janela 3D olhasse fora da sua
    # própria largura, pegaria este (e viraria planta)
    x0, y0 = _titulo_papel(lay, "Casa - Térreo - Planta Baixa", (150, 200), jp, altura=3.5)
    lay.add_text(" 1 : 50", dxfattribs={"height": 2.2, "insert": (x0 + 2, y0 - 6)})
    if so_escala:
        _titulo_papel(lay, " 1 : 20", (400, 200), j3, abaixo=abaixo, altura=2.2)
    elif titulo_3d:
        _titulo_papel(lay, titulo_3d, (400, 200), j3, abaixo=abaixo)
        # nota PEQUENA ainda mais perto da janela: o título é o texto MAIOR
        _titulo_papel(lay, "Nível +0,00", (400, 200), j3, abaixo=1.0, altura=1.5)
        if escala_grande:                                 # escala em letra MAIOR que o nome
            _titulo_papel(lay, "ESC. 1:25", (400, 200), j3, abaixo=5.0, altura=4.0)
    p = str(tmp_path / "revit.dxf")
    doc.saveas(p)
    return p


def _tubo(tmp_path, monkeypatch, liga=True, **kw):
    if liga:
        monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    else:
        monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    ex = dx.extract_dxf(_arquivo(tmp_path, **kw))
    return ex.get_walls_by_layer().get("P-PIPE"), ex


def test_a_vista_3D_com_titulo_no_papel_sai_da_soma(tmp_path, monkeypatch):
    tubo, ex = _tubo(tmp_path, monkeypatch)
    assert tubo == pytest.approx(10.0), "só a planta; o isométrico é o mesmo tubo"
    fora = [d for d in ex.folhas["desenhos_lista"] if d["tipo"] == "fora"]
    assert fora and fora[0]["titulo"] == "3D - Térreo - Banho"


def test_CONTROLE_a_chave_desliga_e_volta_como_era(tmp_path, monkeypatch):
    tubo, _ = _tubo(tmp_path, monkeypatch, liga=False)
    assert tubo == pytest.approx(40.0)


def test_CONTROLE_linha_so_de_escala_nao_e_titulo(tmp_path, monkeypatch):
    tubo, _ = _tubo(tmp_path, monkeypatch, so_escala=True)
    assert tubo == pytest.approx(40.0)


def test_escala_em_letra_maior_nao_rouba_o_lugar_do_titulo(tmp_path, monkeypatch):
    """A linha só de escala nunca é título — nem quando vem em letra maior."""
    tubo, _ = _tubo(tmp_path, monkeypatch, escala_grande=True)
    assert tubo == pytest.approx(10.0)


def test_CONTROLE_texto_longe_da_janela_nao_e_titulo(tmp_path, monkeypatch):
    """Nota lá embaixo na folha não é o título desta vista."""
    tubo, _ = _tubo(tmp_path, monkeypatch, abaixo=60.0)
    assert tubo == pytest.approx(40.0)


def test_titulo_no_modelo_manda_sobre_o_papel(tmp_path, monkeypatch):
    """Título achado no modelo (a regra de sempre) vence o texto do papel."""
    tubo, _ = _tubo(tmp_path, monkeypatch, titulo_modelo_3d="PLANTA BAIXA TÉRREO")
    assert tubo == pytest.approx(40.0)


@pytest.mark.parametrize("titulo, tipo", [
    ("3D - Térreo - Banho", "fora"),
    ("3D - Shaft de Drenagem e Ventilação", "fora"),
    ("VISTA AXONOMÉTRICA", "fora"),
    ("PERSPECTIVA 3D", "fora"),
    ("Casa de Lixo - Térreo - Planta Baixa", "planta"),
    ("PLANTA 3º PAV", "planta"),
    ("CD3D", ""),
])
def test_tipo_da_vista(titulo, tipo):
    assert tipo_do_desenho(titulo) == tipo


def test_a_ia_fica_sabendo_que_o_3D_ja_saiu(tmp_path, monkeypatch):
    _, ex = _tubo(tmp_path, monkeypatch)
    assert "3D - Térreo - Banho" in ex.to_structured_prompt()
