# -*- coding: utf-8 -*-
"""O motor lê o arquivo pelas FOLHAS: esquema/detalhe fora da soma, planta-tipo × andares.

🩸 24/09/2026 — job `0a999117`, projeto de gás de um prédio de 7 andares: um DWG
com 12 folhas (plantas do térreo ao 8º, ESQUEMA VERTICAL, detalhes) lado a lado
no mesmo modelspace. O motor somava o layer do arquivo inteiro:

    tubo embutido "✓ MEDIDO" .... 1.088 m  = plantas UMA vez + 837 m do esquema
                                              vertical (o mesmo tubo de novo) + detalhes
    pelas plantas × andares ....... ~531 m  ("QUARTO/QUINTO/SEXTO PAVIMENTO" vale ×3)
    fogões ........................ 31      (prédio: 42)

Com a leitura por folha, no arquivo real: 535 m e 49 fogões (os 7 a mais estão
num desenho que nenhuma folha mostra — fica como antes, de propósito).
🪤 A janela da viewport é ALVO + centro da vista. Sem o alvo o tubo cai na
folha errada — os DXF daqui têm alvo ≠ 0 de propósito.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import dxf_slim  # noqa: E402
from engine_rules import andares_do_titulo, tipo_do_desenho  # noqa: E402

ALVO = (31.0, 11.0)          # alvo da vista ≠ 0, como no arquivo real


# ── o título diz o que é ──────────────────────────────────────────────────────
@pytest.mark.parametrize("titulo, tipo", [
    ("PLANTA BAIXA TÉRREO", "planta"),
    ("PLANTA BAIXA QUARTO/QUINTO/SEXTO PAVIMENTO", "planta"),
    ("PLANTA BAIXA TELHADO", "planta"),
    ("GARAGEM", "planta"),
    ("ESQUEMA VERTICAL DE GÁS", "fora"),
    ("DETALHE PLANTA BAIXA TÍPICA DO PI", "fora"),       # detalhe ganha de planta
    ("PLANTA DE SITUAÇÃO", "fora"),
    ("PLANTA AMPLIADA BANHEIRO", "fora"),
    ("ISOMÉTRICO ÁGUA FRIA", "fora"),
    ("CORTE AA", "vista"),
    ("ELEVAÇÃO 1", "vista"),
    ("0226.AT.405.ELEV. BAR", "vista"),
    ("LEGENDA", ""),
    ("QUADRO DE ÁREAS", ""),
])
def test_tipo_do_desenho(titulo, tipo):
    assert tipo_do_desenho(titulo) == tipo


@pytest.mark.parametrize("titulo, n", [
    ("PLANTA BAIXA PRIMEIRO E SEGUNDO PAVIMENTO", 2),
    ("PLANTA BAIXA QUARTO/QUINTO/SEXTO PAVIMENTO", 3),
    ("4 - 5 E 6 PAV.", 3),
    ("1 E 2 PAV.", 2),
    ("1º, 2º e 3º pavimentos", 3),
    ("2º AO 7º PAVIMENTO", 6),
    ("SEGUNDO AO SÉTIMO PAVIMENTO", 6),
    ("PAVIMENTO TIPO (6X)", 6),
    ("ESC. 1:50 - 2 E 3 PAV", 2),            # o 50 da escala não é andar
])
def test_andares_do_titulo(titulo, n):
    assert andares_do_titulo(titulo)[0] == n


@pytest.mark.parametrize("titulo", [
    "PLANTA BAIXA TERCEIRO PAVIMENTO",
    "7 PAV",
    "PAVIMENTO TIPO",                  # tipo sem dizer quantos: não chuta
    "2 - 7 PAV",                       # do 2º ao 7º, ou 2º e 7º? não chuta
    "PLANTA DO QUARTO E SALA",         # quarto é cômodo aqui
    "ESCALA 1:50 - 2º PAVIMENTO",      # 50 é escala, não andar
])
def test_CONTROLE_sem_certeza_e_um_andar(titulo):
    assert andares_do_titulo(titulo)[0] == 1


# ── o arquivo: planta-tipo e esquema lado a lado ──────────────────────────────
def _viewport(lay, janela, centro_papel=(200, 150)):
    """Viewport que mostra `janela` (x0,y0,x1,y1) do modelspace, com alvo ≠ 0."""
    x0, y0, x1, y1 = janela
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    esc = 10.0                                   # 10 unidades de papel por metro
    vp = lay.add_viewport(center=centro_papel, size=((x1 - x0) * esc, (y1 - y0) * esc),
                          view_center_point=(cx, cy), view_height=(y1 - y0))
    vp.dxf.view_target_point = (ALVO[0], ALVO[1], 0)
    vp.dxf.view_center_point = (cx - ALVO[0], cy - ALVO[1])
    return vp


def _titulo(msp, doc, texto, x, y):
    if "TIT" not in doc.blocks:
        b = doc.blocks.new("TIT")
        b.add_attdef("TITULODODESENHO", (0, 0), dxfattribs={"height": 0.3})
    msp.add_blockref("TIT", (x, y)).add_attrib("TITULODODESENHO", texto, (x, y))


def _arquivo(tmp_path, titulo_planta="PLANTA BAIXA QUARTO/QUINTO/SEXTO PAVIMENTO",
             titulo_esquema="ESQUEMA VERTICAL DE GÁS", folhas=True, sobrepor=False,
             elevacao=False):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6                  # metros
    msp = doc.modelspace()
    fog = doc.blocks.new("FOGAO")
    fog.add_circle((0, 0), 0.3)
    # PLANTA em x 0..20: 10 m de tubo + 2 fogões
    msp.add_line((2, 5), (12, 5), dxfattribs={"layer": "GAS-TUBO"})
    msp.add_blockref("FOGAO", (4, 8), dxfattribs={"layer": "GAS-PONTO"})
    msp.add_blockref("FOGAO", (8, 8), dxfattribs={"layer": "GAS-PONTO"})
    _titulo(msp, doc, titulo_planta, 5, 1)
    # ESQUEMA em x 40..60: 30 m do mesmo tubo redesenhado + 1 fogão desenhado
    msp.add_line((41, 5), (56, 5), dxfattribs={"layer": "GAS-TUBO"})
    msp.add_line((41, 7), (56, 7), dxfattribs={"layer": "GAS-TUBO"})
    msp.add_blockref("FOGAO", (45, 12), dxfattribs={"layer": "GAS-PONTO"})
    _titulo(msp, doc, titulo_esquema, 45, 1)
    if folhas:
        _viewport(doc.layouts.new("4 - 5 E 6 PAV."), (0, 0, 20, 15))
        _viewport(doc.layouts.new("ESQ VERT"), (40, 0, 60, 15))
        if sobrepor:                              # uma 3ª folha mostra parte do esquema como planta
            _titulo(msp, doc, "PLANTA BAIXA COBERTURA", 65, 13)   # título FORA do esquema
            _viewport(doc.layouts.new("COB"), (45, 3, 70, 15))
    if elevacao:                                  # revestimento de parede: só existe na elevação
        h = msp.add_hatch(dxfattribs={"layer": "REVEST-PAREDE"})
        h.paths.add_polyline_path([(82, 2), (86, 2), (86, 5), (82, 5)], is_closed=True)
        _titulo(msp, doc, "ELEVAÇÃO 1", 84, 1)
        if folhas:
            _viewport(doc.layouts.new("ELEV"), (80, 0, 100, 15))
    p = str(tmp_path / "gas.dxf")
    doc.saveas(p)
    return p


def test_esquema_sai_da_soma_e_a_planta_tipo_vale_por_tres(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert ex.get_walls_by_layer().get("GAS-TUBO") == pytest.approx(30.0), \
        "10 m da planta × 3 andares; os 30 m do esquema não entram"
    assert ex.get_block_summary().get("FOGAO") == 6, "2 fogões × 3 andares; o do esquema não"
    assert ex.folhas.get("aplicada") is True


def test_CONTROLE_a_chave_desliga_e_tudo_volta_como_era(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert ex.get_walls_by_layer().get("GAS-TUBO") == pytest.approx(40.0)
    assert ex.get_block_summary().get("FOGAO") == 3


def test_CONTROLE_sem_folhas_nada_muda(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, folhas=False))
    assert ex.get_walls_by_layer().get("GAS-TUBO") == pytest.approx(40.0)
    assert ex.get_block_summary().get("FOGAO") == 3
    assert not ex.folhas.get("aplicada")


def test_CONTROLE_titulo_que_nao_diz_o_que_e_fica_como_esta(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, titulo_planta="FOLHA 01", titulo_esquema="FOLHA 02"))
    assert ex.get_walls_by_layer().get("GAS-TUBO") == pytest.approx(40.0)


def test_CONTROLE_titulo_que_diz_um_andar_nao_e_multiplicado_pelo_nome_da_folha(tmp_path, monkeypatch):
    """A folha se chama "4 - 5 E 6 PAV." e o título diz TERCEIRO: discordam → 1."""
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, titulo_planta="PLANTA BAIXA TERCEIRO PAVIMENTO"))
    assert ex.get_walls_by_layer().get("GAS-TUBO") == pytest.approx(10.0)


def test_titulo_sem_andar_usa_o_nome_da_folha(tmp_path, monkeypatch):
    """"PLANTA BAIXA PAVIMENTO TIPO" não diz quantos; a folha "4 - 5 E 6 PAV." diz."""
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, titulo_planta="PLANTA BAIXA PAVIMENTO TIPO"))
    assert ex.get_walls_by_layer().get("GAS-TUBO") == pytest.approx(30.0)


def test_CONTROLE_desenhos_que_discordam_ficam_com_peso_um(tmp_path, monkeypatch):
    """Um pedaço do esquema aparece numa 3ª folha como 'planta': ali ninguém sabe
    quem tem razão, e o que está na sobreposição fica como era (peso 1)."""
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, sobrepor=True))
    # o tubo e o fogão do esquema caem no esquema (fora) E na 3ª folha (planta):
    # desenhos que discordam → peso 1, como era. A planta-tipo continua × 3.
    assert ex.get_walls_by_layer().get("GAS-TUBO") == pytest.approx(30.0 + 30.0)
    assert ex.get_block_summary().get("FOGAO") == 6 + 1


def test_a_janela_usa_o_alvo_da_vista(tmp_path, monkeypatch):
    """Sem somar o ALVO, a janela da planta cairia em x 31..51 — em cima do
    esquema — e o resultado inverteria. É o erro que eu cometi no estudo."""
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    doc = ezdxf.readfile(_arquivo(tmp_path))
    mapa = dx.mapa_de_folhas(doc)
    caixas = {f["tipo"]: f["caixa"] for f in mapa["folhas"]}
    assert caixas["planta"][0] == pytest.approx(0.0) and caixas["fora"][0] == pytest.approx(40.0)


def test_a_ia_fica_sabendo_o_que_ja_vem_multiplicado(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    txt = dx.extract_dxf(_arquivo(tmp_path)).to_structured_prompt()
    assert "DESENHOS DESTE ARQUIVO" in txt
    assert "vale por 3 andares" in txt and "ESQUEMA VERTICAL" in txt


def test_o_emagrecido_guarda_as_janelas_da_folha_ativa(tmp_path):
    """O filtro textual do dxf-slim só guardava o que o motor MEDE; as VIEWPORTs
    da folha ativa moram em ENTITIES e sumiam."""
    doc = ezdxf.new("R2018")
    doc.modelspace().add_line((0, 0), (5, 0))
    lay = doc.layouts.new("ATIVA")
    lay.add_viewport(center=(100, 100), size=(100, 50), view_center_point=(2, 0), view_height=5)
    doc.layouts.set_active_layout("ATIVA")
    src, out = str(tmp_path / "a.dxf"), str(tmp_path / "a.slim.dxf")
    doc.saveas(src)
    dxf_slim.emagrecer_por_texto(src, out)
    lido = ezdxf.readfile(out)
    vps = [v for v in lido.layouts.get("ATIVA").query("VIEWPORT") if v.dxf.get("id", 2) != 1]
    assert len(vps) == 1


def test_o_log_de_producao_diz_o_que_a_leitura_fez(tmp_path, monkeypatch):
    """Sem esta linha, "o esquema entrou na soma" só se descobre baixando o arquivo."""
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    import main
    assert "motor:leitura-por-folha" in main._STAGES_DIAGNOSTICO
    ex = dx.extract_dxf(_arquivo(tmp_path))
    linha = main._leitura_por_folha_resumo(ex)
    assert "aplicada=sim" in linha and "×3" in linha and "fora=1" in linha, linha
    ex2 = dx.extract_dxf(_arquivo(tmp_path, folhas=False))
    assert "aplicada=nao" in main._leitura_por_folha_resumo(ex2)


def test_CONTROLE_elevacao_fica_na_soma(tmp_path, monkeypatch):
    """Medido no acervo: tirar as elevações de um lavabo levou a área de 50,5
    para 30,0 m² — o revestimento de parede SÓ existe na elevação. Vista fica
    como era; o esquema continua saindo."""
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, elevacao=True))
    assert ex.get_areas_by_layer().get("REVEST-PAREDE") == pytest.approx(12.0)
    assert ex.get_walls_by_layer().get("GAS-TUBO") == pytest.approx(30.0)


@pytest.mark.parametrize("texto, titulo", [
    ("PLANTA BAIXA TÉRREO", True),
    ("01 - DETALHE DO PI", True),
    ("DET. FORRO REMOVÍVEL / CORTE B", True),
    ("ESQUEMA VERTICAL DE GÁS", True),
    ("SIGLA DE AMPLIAÇÃO I \"XX\" número da ampliação", False),   # legenda, não título
    ("VER DETALHE 3", False),                                      # chamada, não título
    ("NOTA: TUBULAÇÃO EM PLANTA", False),
])
def test_texto_solto_so_e_titulo_se_comecar_pelo_que_o_desenho_e(texto, titulo):
    from engine_rules import parece_titulo_de_desenho
    assert parece_titulo_de_desenho(texto) is titulo


def test_det_abreviado_e_detalhe():
    assert tipo_do_desenho("DET. FORRO REMOVÍVEL / CORTE B") == "fora"


def test_CONTROLE_legenda_dentro_da_planta_nao_tira_a_planta(tmp_path, monkeypatch):
    """🩸 No acervo: "SIGLA DE AMPLIAÇÃO…" (texto de legenda) virou título e
    tirou 448 m de uma planta inteira."""
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((2, 5), (12, 5), dxfattribs={"layer": "PAREDE"})
    msp.add_text("SIGLA DE AMPLIAÇÃO I \"XX\" número da ampliação",
                 dxfattribs={"height": 0.5, "insert": (3, 9)})
    msp.add_text("ESQUEMA VERTICAL", dxfattribs={"height": 0.5, "insert": (42, 9)})
    msp.add_line((41, 5), (56, 5), dxfattribs={"layer": "PAREDE"})
    _viewport(doc.layouts.new("A"), (0, 0, 20, 15))
    _viewport(doc.layouts.new("B"), (40, 0, 60, 15))
    p = str(tmp_path / "leg.dxf")
    doc.saveas(p)
    ex = dx.extract_dxf(p)
    assert ex.get_walls_by_layer().get("PAREDE") == pytest.approx(10.0), \
        "a planta fica (a legenda não é título); só o esquema sai"


def test_CONTROLE_marcador_pequeno_nao_e_titulo(tmp_path, monkeypatch):
    """🩸 No acervo: o marcador "DET.XX" (altura 0,1) numa janela de legenda cuja
    maior letra é 0,3 virou título e tirou 448 m. Título é a letra GRANDE."""
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((2, 5), (12, 5), dxfattribs={"layer": "PAREDE"})
    msp.add_text("LEGENDA GERAL", dxfattribs={"height": 0.3, "insert": (3, 12)})
    msp.add_text("DET.XX", dxfattribs={"height": 0.1, "insert": (3, 9)})
    msp.add_text("ESQUEMA VERTICAL", dxfattribs={"height": 0.5, "insert": (42, 9)})
    msp.add_line((41, 5), (56, 5), dxfattribs={"layer": "PAREDE"})
    _viewport(doc.layouts.new("A"), (0, 0, 20, 15))
    _viewport(doc.layouts.new("B"), (40, 0, 60, 15))
    p = str(tmp_path / "det.dxf")
    doc.saveas(p)
    assert dx.extract_dxf(p).get_walls_by_layer().get("PAREDE") == pytest.approx(10.0)
