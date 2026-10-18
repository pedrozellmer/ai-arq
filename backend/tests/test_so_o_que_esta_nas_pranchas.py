# -*- coding: utf-8 -*-
"""A opção de medir SÓ o que está nas pranchas (chave SO_O_QUE_ESTA_NAS_PRANCHAS).

🩸 18/10/2026 — revisão da semana: 22 de 59 projetos em CAD (90 dias) tinham
mais de 20 % do comprimento no modelo fora de todas as janelas das pranchas, e
o motor só AVISA. Num elétrico, metade das luminárias e tomadas estava em duas
plantas que nenhuma folha mostra (249 → 135 luminárias, 130 → 62 tomadas). Se
aquilo é versão antiga ou outro pavimento, só o cliente sabe — a régua
automática foi medida em 10/10 e não serve. Por isso: OPÇÃO por projeto,
padrão desligada, ligada pela avaliação isolada quando o cliente confirma.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import main  # noqa: E402

CHAVE = "SO_O_QUE_ESTA_NAS_PRANCHAS"


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    monkeypatch.delenv(CHAVE, raising=False)


def _viewport(lay, janela, centro_papel=(200, 150)):
    x0, y0, x1, y1 = janela
    esc = 10.0
    return lay.add_viewport(center=centro_papel, size=((x1 - x0) * esc, (y1 - y0) * esc),
                            view_center_point=((x0 + x1) / 2, (y0 + y1) / 2), view_height=(y1 - y0))


def _desenho(msp, doc, x, comprimento, largura_hachura, n_lum):
    """4 linhas de `comprimento`, uma hachura 10 × `largura_hachura` e `n_lum` luminárias, a partir de x."""
    for y in (5, 10, 15, 20):
        msp.add_line((x + 5, y), (x + 5 + comprimento, y), dxfattribs={"layer": "ELE-ELETROCALHA"})
    h = msp.add_hatch(dxfattribs={"layer": "PISO-CERAMICO"})
    h.paths.add_polyline_path([(x + 5, 22), (x + 15, 22), (x + 15, 22 + largura_hachura),
                               (x + 5, 22 + largura_hachura)], is_closed=True)
    if "LUMINARIA EMBUTIR" not in doc.blocks:
        b = doc.blocks.new("LUMINARIA EMBUTIR")
        b.add_circle((0, 0), 0.3)
    for k in range(n_lum):
        msp.add_blockref("LUMINARIA EMBUTIR", (x + 6 + 2 * k, 3), dxfattribs={"layer": "ELE-ILUMINACAO"})


def _arquivo(tmp_path, fora=True, folhas=True, janela=(0, 0, 40, 30), nome="ele.dxf"):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6                  # metros
    msp = doc.modelspace()
    _desenho(msp, doc, 0, 25, 6, 10)             # na prancha: 100 m, 60 m², 10 luminárias
    if fora:
        _desenho(msp, doc, 200, 20, 7, 8)        # no modelo, fora: 80 m, 70 m², 8 luminárias
    if folhas:
        _viewport(doc.layouts.new("ILUMINACAO"), janela)
    p = str(tmp_path / nome)
    doc.saveas(p)
    return p


def _lum(ex):
    return {b.name: b.count for b in ex.blocks}.get("LUMINARIA EMBUTIR", 0)


def test_CONTROLE_com_a_chave_desligada_e_como_era(tmp_path):
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert _lum(ex) == 18
    assert ex.get_walls_by_layer().get("ELE-ELETROCALHA") == pytest.approx(180.0)
    assert ex.get_areas_by_layer().get("PISO-CERAMICO") == pytest.approx(130.0)
    assert "so_nas_pranchas" not in ex.metadata
    assert ex.metadata.get("fora_das_pranchas")                 # o aviso de sempre


def test_o_caso_com_a_chave_ligada_so_conta_o_que_esta_nas_pranchas(tmp_path, monkeypatch):
    monkeypatch.setenv(CHAVE, "1")
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert _lum(ex) == 10
    assert ex.get_walls_by_layer().get("ELE-ELETROCALHA") == pytest.approx(100.0)
    assert ex.get_areas_by_layer().get("PISO-CERAMICO") == pytest.approx(60.0)
    s = ex.metadata["so_nas_pranchas"]
    assert s["aplicada"] is True and s["blocos"] == 8
    assert s["m"] == pytest.approx(80.0) and s["m2"] == pytest.approx(70.0)
    # o que ficou fora não entrou na conta: o aviso de "entrou na conta" não vale mais
    assert "fora_das_pranchas" not in ex.metadata


def test_o_registro_nao_vai_cru_pro_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv(CHAVE, "1")
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert "so_nas_pranchas" not in ex.to_structured_prompt()


def test_CONTROLE_janela_que_mostra_pouco_nao_tira_nada(tmp_path, monkeypatch):
    """O projetista que plota do modelo: a janela pega um canto — tirar zeraria."""
    monkeypatch.setenv(CHAVE, "1")
    ex = dx.extract_dxf(_arquivo(tmp_path, janela=(0, 0, 4, 2)))
    s = ex.metadata["so_nas_pranchas"]
    assert s["aplicada"] is False and "pouco" in s["motivo"], s
    assert _lum(ex) == 18
    assert ex.get_walls_by_layer().get("ELE-ELETROCALHA") == pytest.approx(180.0)


def test_CONTROLE_sem_prancha_nao_ha_o_que_tirar(tmp_path, monkeypatch):
    monkeypatch.setenv(CHAVE, "1")
    ex = dx.extract_dxf(_arquivo(tmp_path, folhas=False))
    assert _lum(ex) == 18
    assert not (ex.metadata.get("so_nas_pranchas") or {}).get("aplicada")


def test_CONTROLE_tudo_dentro_nada_muda(tmp_path, monkeypatch):
    monkeypatch.setenv(CHAVE, "1")
    ex = dx.extract_dxf(_arquivo(tmp_path, fora=False))
    assert _lum(ex) == 10
    assert ex.get_walls_by_layer().get("ELE-ELETROCALHA") == pytest.approx(100.0)
    s = ex.metadata["so_nas_pranchas"]
    assert s["aplicada"] is True and s["blocos"] == 0 and s["m"] == 0


@pytest.mark.parametrize("fracao_m,fracao_bl,age", [
    (0.25, 0.0, True), (0.0, 0.25, True), (0.15, 0.15, False),
])
def test_a_trava_olha_comprimento_OU_blocos(fracao_m, fracao_bl, age):
    folhas = {"folhas": [{"folha": "A", "tipo": "", "caixa": (0, 0, 10, 10)}], "origem": ""}
    walls = [dx.WallSegment(layer="L", length=100 * fracao_m, start=(1, 1), end=(2, 1)),
             dx.WallSegment(layer="L", length=100 * (1 - fracao_m), start=(50, 1), end=(51, 1))]
    n_dentro = int(round(100 * fracao_bl))
    b = dx.BlockCount(name="B", count=100, layer="L",
                      positions=[(5, 5)] * n_dentro + [(50, 50)] * (100 - n_dentro))
    res = dx.tirar_o_que_nao_esta_nas_pranchas(walls, [], [], [b], folhas)
    assert res["aplicada"] is age, res


def test_CONTROLE_desenhos_achados_no_modelo_nao_sao_pranchas():
    """Mapa de `origem` "modelo"/"prefixo dos layers": fora deles não é fora das pranchas."""
    def _ws():
        return [dx.WallSegment(layer="L", length=90, start=(1, 1), end=(9, 1)),      # dentro
                dx.WallSegment(layer="L", length=10, start=(50, 1), end=(60, 1))]    # fora
    walls = _ws()
    res = dx.tirar_o_que_nao_esta_nas_pranchas(
        walls, [], [], [], {"folhas": [{"caixa": (0, 0, 10, 10)}], "origem": "modelo"})
    assert res["aplicada"] is False and len(walls) == 2
    # a mesma geometria com janelas do papel: tira o de fora (a trava não é o que segurou acima)
    walls = _ws()
    res = dx.tirar_o_que_nao_esta_nas_pranchas(
        walls, [], [], [], {"folhas": [{"caixa": (0, 0, 10, 10)}], "origem": ""})
    assert res["aplicada"] is True and len(walls) == 1


def test_a_chave_e_avaliavel_e_lida_no_extrator():
    assert CHAVE in main._CHAVES_AVALIAVEIS
    with open(dx.__file__, encoding="utf-8") as f:
        src = f.read()
    assert 'os.environ.get("%s", "0") == "1"' % CHAVE in src     # padrão: desligada


def test_a_planilha_diz_o_que_saiu():
    arqs = [{"nome": "ELE-02", "so_nas_pranchas": {"aplicada": True, "m": 4834.3, "m2": 37.1, "blocos": 774}}]
    linhas = main._linhas_fora_das_pranchas(arqs)
    assert len(linhas) == 1 and linhas[0].startswith("📐 Medimos só o que está nas pranchas"), linhas
    assert "4.834 m" in linhas[0] and "774 peça(s)" in linhas[0], linhas


def test_a_planilha_diz_quando_a_opcao_nao_agiu():
    arqs = [{"nome": "PSG-01", "so_nas_pranchas": {"aplicada": False,
                                                   "motivo": "as janelas mostram pouco do desenho"}}]
    linhas = main._linhas_fora_das_pranchas(arqs)
    assert len(linhas) == 1 and "ficou como estava" in linhas[0] and "PSG-01" in linhas[0], linhas


def test_CONTROLE_sem_a_opcao_a_linha_de_sempre():
    arqs = [{"nome": "A", "fora_das_pranchas": {"m": 80, "total_m": 180, "m2": 0, "total_m2": 0}}]
    linhas = main._linhas_fora_das_pranchas(arqs)
    assert len(linhas) == 1 and linhas[0].startswith("⚠ Parte do desenho está FORA"), linhas
