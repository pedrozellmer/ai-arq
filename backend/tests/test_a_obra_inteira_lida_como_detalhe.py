# -*- coding: utf-8 -*-
"""A obra inteira lida como "detalhe" não zera a medição do arquivo.

🩸 12/10/2026 — numa avaliação, um prédio inteiro (3.049 blocos, 8 km de linha,
326 nomes de ambiente) estava numa janela só, cujo maior texto era "DETALHES". A
leitura por folha deu ao desenho o tipo 'fora' e tirou TUDO da medição: a
planilha saiu só com o que estava escrito.

A trava age só com as TRÊS juntas: todos os desenhos do arquivo são 'fora', a
medição iria a zero, e as janelas têm 10 ou mais nomes de ambiente dentro.

📏 O A/B no acervo (328 arquivos) derrubou as duas metades sozinhas, e os dois
casos estão aqui como controle:
  • "todos 'fora' + zero" disparava em pranchas que são SÓ diagrama unifilar
    (0 nomes de ambiente) e devolvia os fios à soma;
  • "10 ou mais nomes de ambiente na janela" disparava num esquema de prumada com
    os cômodos escritos andar por andar, num arquivo com as plantas ao lado.
"""
import io
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import dwg_extractor as dx  # noqa: E402

ALVO = (31.0, 11.0)
_COMODOS = ["SALA 01", "SALA 02", "COZINHA", "COPA", "BANHEIRO", "WC", "HALL", "DEPÓSITO",
            "CIRCULAÇÃO", "CORREDOR", "LAVANDERIA", "GARAGEM", "ESCRITÓRIO", "VARANDA"]


# ── direto na régua ──────────────────────────────────────────────────────────
def _coisas():
    walls = [dx.WallSegment(layer="PAREDE", length=10.0, start=(2, 5), end=(12, 5)),
             dx.WallSegment(layer="PAREDE", length=4.0, start=(2, 8), end=(6, 8))]
    hatches = [dx.HatchArea(layer="PISO", area=12.0, bbox=(2, 2, 6, 5))]
    blocks = [dx.BlockCount(name="PORTA", count=3, positions=[(3, 3), (5, 6), (9, 9)]),
              dx.BlockCount(name="PIA", count=1, positions=[(7, 7)])]
    return walls, hatches, [], blocks


def _mapa(*regs):
    """regs = (título, tipo, caixa, nomes de ambiente dentro)."""
    fs = []
    for i, (t, tp, cx, amb) in enumerate(regs):
        f = {"folha": "F%d" % i, "titulo": t, "tipo": tp, "caixa": cx, "andares": 1}
        if tp == "fora":
            f["ambientes_dentro"] = amb
        fs.append(f)
    return {"folhas": fs}


def test_a_obra_inteira_numa_janela_de_detalhes_fica_como_estava():
    walls, hatches, pols, blocks = _coisas()
    mapa = _mapa(("DETALHES", "fora", (0, 0, 20, 15), 326))
    res = dx.aplicar_leitura_por_folha(walls, hatches, pols, blocks, mapa)
    assert res["aplicada"] is False and res["motivo"].startswith("tiraria TUDO do arquivo"), res
    assert "326 nomes de ambiente" in res["motivo"] and "DETALHES" in res["motivo"]
    assert res[dx._FOLHA_TIRARIA_TUDO] == {"comprimento": 14.0, "area": 12.0, "blocos": 4}
    assert [(w.length, w.peso) for w in walls] == [(10.0, 1.0), (4.0, 1.0)]
    assert [h.area for h in hatches] == [12.0]
    assert [(b.name, b.count, b.positions) for b in blocks] == [
        ("PORTA", 3, [(3, 3), (5, 6), (9, 9)]), ("PIA", 1, [(7, 7)])]
    f = mapa["folhas"][0]
    assert (f["tipo"], f["tipo_recusado"], f["nao_e_detalhe"]) == ("", "fora", "DETALHES (326 ambientes)")


@pytest.mark.parametrize("nomes, trava", [(0, False), (3, False), (9, False), (10, True), (14, True)])
def test_o_corte_e_dez_nomes_de_ambiente(nomes, trava):
    walls, hatches, pols, blocks = _coisas()
    mapa = _mapa(("DETALHES", "fora", (0, 0, 20, 15), nomes))
    res = dx.aplicar_leitura_por_folha(walls, hatches, pols, blocks, mapa)
    assert (dx._FOLHA_TIRARIA_TUDO in res) is trava
    assert bool(blocks) is trava and (mapa["folhas"][0]["tipo"] == "") is trava


def test_os_nomes_de_todas_as_janelas_fora_somam():
    walls, hatches, pols, blocks = _coisas()
    mapa = _mapa(("DETALHE 1", "fora", (0, 0, 8, 15), 6), ("DETALHE 2", "fora", (8, 0, 20, 15), 6))
    res = dx.aplicar_leitura_por_folha(walls, hatches, pols, blocks, mapa)
    assert dx._FOLHA_TIRARIA_TUDO in res and res["desenhos"] == 2
    assert sum(b.count for b in blocks) == 4 and all(f["tipo"] == "" for f in mapa["folhas"])


def test_CONTROLE_o_diagrama_sem_comodos_sai_inteiro_mesmo_zerando_o_arquivo():
    """O caso que derrubou a 1ª versão: prancha que é SÓ diagrama unifilar. A folha
    tira os fios de propósito, e o arquivo fica sem medição nenhuma."""
    walls, hatches, pols, blocks = _coisas()
    mapa = _mapa(("DIAGRAMA DOS QUADROS TERMINAIS", "fora", (0, 0, 20, 15), 0))
    res = dx.aplicar_leitura_por_folha(walls, hatches, pols, blocks, mapa)
    assert res["aplicada"] is True and dx._FOLHA_TIRARIA_TUDO not in res
    assert not walls and not hatches and not blocks
    assert mapa["folhas"][0]["tipo"] == "fora" and "nao_e_detalhe" not in mapa["folhas"][0]


def test_CONTROLE_o_esquema_de_prumada_cheio_de_comodos_sai_quando_ha_planta_ao_lado():
    """O caso que derrubou a 2ª versão: 146 nomes de ambiente dentro do esquema (os
    cômodos escritos andar por andar), num arquivo que tem as plantas. Não zera o
    arquivo — a régua da folha vale, e o tubo do esquema sai."""
    walls, hatches, pols, blocks = _coisas()
    walls.append(dx.WallSegment(layer="TUBO", length=30.0, start=(41, 5), end=(56, 5)))
    mapa = _mapa(("PLANTA BAIXA", "planta", (0, 0, 20, 15), 0),
                 ("CORTE ESQUEMÁTICO DE ÁGUA FRIA", "fora", (40, 0, 60, 15), 146))
    res = dx.aplicar_leitura_por_folha(walls, hatches, pols, blocks, mapa)
    assert res["aplicada"] is True and dx._FOLHA_TIRARIA_TUDO not in res
    assert sum(w.length for w in walls) == 14.0, "os 30 m do esquema saem"
    assert [f["tipo"] for f in mapa["folhas"]] == ["planta", "fora"]


def test_CONTROLE_sobrando_qualquer_coisa_a_regua_vale():
    walls, hatches, pols, blocks = _coisas()
    blocks.append(dx.BlockCount(name="POSTE", count=1, positions=[(200, 200)]))
    mapa = _mapa(("DETALHES", "fora", (0, 0, 20, 15), 326))
    res = dx.aplicar_leitura_por_folha(walls, hatches, pols, blocks, mapa)
    assert res["aplicada"] is True
    assert [(b.name, b.count) for b in blocks] == [("POSTE", 1)] and not walls and not hatches


def test_CONTROLE_folha_so_de_vistas_zera_o_comprimento_de_proposito():
    walls = [dx.WallSegment(layer="GUARDA-CORPO", length=40.0, start=(0, 10), end=(40, 10))]
    mapa = _mapa(("FACHADA A", "vista", (0, 0, 40, 20), 0))
    res = dx.aplicar_leitura_por_folha(walls, [], [], [], mapa)
    assert res["aplicada"] is True and not walls and dx._FOLHA_TIRARIA_TUDO not in res


def test_CONTROLE_detalhe_mais_vista_nao_dispara_mesmo_zerando():
    """Nem todos os desenhos são 'fora': a trava não entra (a vista zera o
    comprimento dela de propósito, e o detalhe sai como sempre)."""
    walls, hatches, pols, blocks = _coisas()
    walls.append(dx.WallSegment(layer="PAREDE", length=30.0, start=(41, 5), end=(56, 5)))
    mapa = _mapa(("DETALHES", "fora", (0, 0, 20, 15), 14), ("CORTE AA", "vista", (40, 0, 60, 15), 0))
    res = dx.aplicar_leitura_por_folha(walls, hatches, pols, blocks, mapa)
    assert res["aplicada"] is True and dx._FOLHA_TIRARIA_TUDO not in res
    assert not walls and not blocks


def test_CONTROLE_arquivo_que_ja_nao_tinha_nada_nao_dispara():
    mapa = _mapa(("DETALHES", "fora", (0, 0, 20, 15), 326))
    assert dx._FOLHA_TIRARIA_TUDO not in dx.aplicar_leitura_por_folha([], [], [], [], mapa)


# ── o arquivo, de ponta a ponta ──────────────────────────────────────────────
def _viewport(lay, janela):
    x0, y0, x1, y1 = janela
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    vp = lay.add_viewport(center=(200, 150), size=((x1 - x0) * 10.0, (y1 - y0) * 10.0),
                          view_center_point=(cx, cy), view_height=(y1 - y0))
    vp.dxf.view_target_point = (ALVO[0], ALVO[1], 0)
    vp.dxf.view_center_point = (cx - ALVO[0], cy - ALVO[1])


def _doc(titulo, comodos, com_planta=False, comodos_na_planta=0):
    """Uma janela (x 0..20) com 10 m de tubo, 3 fogões, o título e `comodos` nomes de
    ambiente dentro. `com_planta`: uma 2ª janela ao lado, com título de planta."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    doc.blocks.new("FOGAO").add_circle((0, 0), 0.3)
    b = doc.blocks.new("TIT")
    b.add_attdef("TITULODODESENHO", (0, 0), dxfattribs={"height": 0.3})
    msp.add_line((2, 5), (12, 5), dxfattribs={"layer": "GAS-TUBO"})
    for x in (4, 8, 11):
        msp.add_blockref("FOGAO", (x, 8), dxfattribs={"layer": "GAS-PONTO"})
    for k, nome in enumerate(_COMODOS[:comodos]):
        msp.add_text(nome, dxfattribs={"height": 0.2, "insert": (1 + (k % 6) * 3, 10 + (k // 6))})
    msp.add_blockref("TIT", (5, 1)).add_attrib("TITULODODESENHO", titulo, (5, 1))
    _viewport(doc.layouts.new("FOLHA 1"), (0, 0, 20, 15))
    if com_planta:
        msp.add_line((41, 5), (56, 5), dxfattribs={"layer": "GAS-TUBO"})
        msp.add_blockref("FOGAO", (45, 12), dxfattribs={"layer": "GAS-PONTO"})
        msp.add_blockref("TIT", (45, 1)).add_attrib("TITULODODESENHO", "PLANTA BAIXA TÉRREO", (45, 1))
        for k, nome in enumerate(_COMODOS[:comodos_na_planta]):
            msp.add_text(nome, dxfattribs={"height": 0.2, "insert": (41 + (k % 6) * 3, 9 + (k // 6))})
        _viewport(doc.layouts.new("FOLHA 2"), (40, 0, 60, 15))
    return doc


def _extrai(tmp_path, doc):
    p = str(tmp_path / "obra.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


def test_o_mapa_conta_os_nomes_de_ambiente_DENTRO_de_cada_janela_fora():
    m = dx.mapa_de_folhas(_doc("DETALHES", 2, com_planta=True, comodos_na_planta=14))
    assert [(f["tipo"], f.get("ambientes_dentro")) for f in m["folhas"]] == [("fora", 2), ("planta", None)]
    assert dx.mapa_de_folhas(_doc("DETALHES", 14))["folhas"][0]["ambientes_dentro"] == 14
    assert dx.mapa_de_folhas(_doc("DETALHES", 14))["folhas"][0]["tipo"] == "fora", "o mapa não decide: conta"


def test_a_obra_inteira_numa_janela_de_detalhes_continua_medida(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = _extrai(tmp_path, _doc("DETALHES", 14))
    assert ex.get_walls_by_layer().get("GAS-TUBO") == pytest.approx(10.0)
    assert ex.get_block_summary().get("FOGAO") == 3
    assert ex.folhas.get("aplicada") is False and "tiraria TUDO" in ex.folhas.get("motivo", "")
    d = ex.folhas["desenhos_lista"][0]
    assert d["tipo"] == "" and d["nao_e_detalhe"] == "DETALHES (14 ambientes)"
    texto = ex.to_structured_prompt()
    assert "FOGAO" in texto and "GAS-TUBO" in texto


def test_CONTROLE_o_esquema_sem_comodos_continua_fora_mesmo_zerando(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = _extrai(tmp_path, _doc("ESQUEMA VERTICAL DE GÁS", 0))
    assert ex.get_walls_by_layer().get("GAS-TUBO", 0.0) == 0.0
    assert not ex.get_block_summary().get("FOGAO")
    assert ex.folhas.get("aplicada") is True
    assert "nao_e_detalhe" not in ex.folhas["desenhos_lista"][0]


def test_CONTROLE_o_detalhe_cheio_de_comodos_ao_lado_da_planta_sai(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = _extrai(tmp_path, _doc("DETALHES", 14, com_planta=True))
    assert ex.get_walls_by_layer().get("GAS-TUBO") == pytest.approx(15.0), "só os 15 m da planta"
    assert ex.get_block_summary().get("FOGAO") == 1
    assert [d["tipo"] for d in ex.folhas["desenhos_lista"]] == ["fora", "planta"]


def test_o_log_da_leitura_por_folha_diz_qual_janela_e_por_que(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    import main
    linha = main._leitura_por_folha_resumo(_extrai(tmp_path, _doc("DETALHES", 14)))
    assert "aplicada=nao" in linha and "tiraria TUDO" in linha
    assert "nao_e_detalhe=[DETALHES (14 ambientes)]" in linha
    sem = main._leitura_por_folha_resumo(_extrai(tmp_path, _doc("DETALHES", 14, com_planta=True)))
    assert "nao_e_detalhe" not in sem


def test_a_medida_por_folha_e_refeita_com_o_mapa_neutro():
    fonte = io.open(os.path.join(_BACKEND, "dwg_extractor.py"), encoding="utf-8").read()
    i = fonte.index("_folhas = aplicar_leitura_por_folha(walls, hatches, polygon_areas, blocks, _mapa)")
    j = fonte.index("_n_txt = _marcar_textos_repetidos_da_planta(texts, _mapa)", i)
    trecho = fonte[i:j]
    assert "if _folhas.get(_FOLHA_TIRARIA_TUDO):" in trecho
    assert "_medida = medir_por_folha(walls, hatches, polygon_areas, blocks, _mapa)" in trecho
