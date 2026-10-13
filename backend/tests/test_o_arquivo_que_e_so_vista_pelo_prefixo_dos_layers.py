# -*- coding: utf-8 -*-
"""O arquivo que é SÓ VISTA, dito pelo prefixo dos layers do ArchiCAD.

🩸 13/10/2026 — um projeto de 8 DWG exportados do ArchiCAD: dois arquivos são
CORTE e foram medidos como planta ("guarda-corpo — comprimento total no corte
571,60 ml", com selo). Não há texto de título no modelo: a leitura por folha
saiu "nenhum desenho com título que diga o que é".
🔑 O ArchiCAD prefixa os layers de cada desenho posto na folha com
"<id>_<nome do desenho>_<n>_". O nome do desenho é o 2º campo.
📏 No acervo (326 DWG) a convenção aparece em 2 arquivos, os dois PLANTA; 76 DWG
têm palavra de vista no nome de ALGUM layer (a marca de corte da planta), nunca
com mais de 38 % do comprimento.
🪤 Os lados falsos: o nome INTEIRO do layer ("…_ANT.Marcador - Corte") não
decide, só o campo do desenho; o nome do desenho não vira título de planta
("(3° ao 24° pavto) - 22x" não multiplica); e o mapa-chave, que no caso é 90 %
do comprimento de cada prancha, fica fora da conta dos 90 %.

🪤 Nomes FICTÍCIOS, com a mesma forma dos medidos (repositório público).
"""
import io
import logging
import os
import re
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import dwg_extractor as dx  # noqa: E402

CHAVE = "VISTA_PELO_PREFIXO_DOS_LAYERS"

VISTA = ["Corte AA", "CORTE BB", "Corte Longitudinal", "Cortes", "CRT01", "CRT 02", "crt-3",
         "Elevação Norte", "ELEVAÇÕES", "Elevacao 2", "Elev 1", "ELEV. 03",
         "Fachada Frontal", "FACHADAS", "FACH 02", "Corte AA - Térreo"]
NAO_VISTA = ["Planta Baixa", "Pav.tipo 1", "Terraço", "Cobertura", "MAPA CHAVE",
             "PAVIMENTO TIPO I (3° ao 24° pavto) - 22x",
             # detalhe e esquema ganham, como no título
             "Detalhe do corte", "DET 05 - Corte", "Corte esquemático", "Ampliação da fachada",
             # a palavra dentro de outra
             "Recorte", "Elevador", "Cortina de vidro", "Fachadeiro", "Elevatória",
             # o que esta régua não promete
             "Vista 01", "Perspectiva", "Legenda de portas", "", None]


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.delenv(CHAVE, raising=False)


@pytest.mark.parametrize("nome", VISTA)
def test_o_nome_do_desenho_e_de_vista(nome):
    assert dx.nome_de_desenho_e_vista(nome) is True, nome


@pytest.mark.parametrize("nome", NAO_VISTA)
def test_CONTROLE_o_nome_do_desenho_nao_e_de_vista(nome):
    assert dx.nome_de_desenho_e_vista(nome) is False, nome


# ── a régua, sobre o comprimento medido ──────────────────────────────────────
class _W:
    def __init__(self, layer, length):
        self.layer, self.length = layer, length


_CORTE = ["A_Corte AA_1_ARQ - Parede", "A_Corte AA_1_ARQ - Guarda-Corpo", "A_Corte AA_1_EST - Escada"]
_PLANTA = ["1_PLANTA BAIXA_1_ARQ - Parede", "1_PLANTA BAIXA_1_ARQ - Piso", "1_PLANTA BAIXA_1_ANT.Marcador - Corte"]
_MAPA = "001_MAPA CHAVE_3_0"


def _walls(*pares):
    return [_W(layer, m) for layer, m in pares]


def test_o_caso_o_corte_com_o_mapa_chave_pesando_nove_vezes_mais():
    r = dx.vista_pelo_prefixo_dos_layers(
        _walls((_CORTE[0], 60.0), (_CORTE[1], 40.0), (_CORTE[2], 20.0), (_MAPA, 1000.0)), _CORTE + [_MAPA, "0"])
    assert r == {"titulo": "Corte AA", "desenhos": 1, "fracao": 1.0, "m": 120.0, "m_total": 120.0,
                 "m_mapa_chave": 1000.0, "m_legenda": 0.0}


def test_CONTROLE_o_que_pesa_nove_vezes_mais_e_nao_e_mapa_chave_impede():
    outro = "001_OUTRO DESENHO_3_0"
    assert dx.vista_pelo_prefixo_dos_layers(
        _walls((_CORTE[0], 60.0), (_CORTE[1], 40.0), (_CORTE[2], 20.0), (outro, 1000.0)), _CORTE + [outro]) == {}


@pytest.mark.parametrize("mapa", ["001_MAPA CHAVE_3_0", "9_Mapa-Chave_12_0", "K_PLANTA CHAVE_2_Linhas",
                                  "K_Planta-chave térreo_2_0", "X_KEY PLAN_1_0", "X_Keyplan_1_0"])
def test_o_mapa_chave_fica_fora_da_conta_em_todas_as_grafias(mapa):
    r = dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 10.0), (mapa, 500.0)), _CORTE + [mapa])
    assert r and r["m_mapa_chave"] == 500.0 and r["fracao"] == 1.0, mapa


@pytest.mark.parametrize("legenda", ["LG_Acabamentos_11_0", "XPTO - LEG_Portas de madeira_7_0",
                                     "9_Legenda de pisos_4_Linhas", "LEG_Pisos_2_0", "Q_LEGENDAS_5_Texto"])
def test_a_legenda_fica_fora_da_conta_pelo_id_ou_pelo_nome(legenda):
    r = dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 10.0), (legenda, 500.0)), _CORTE + [legenda])
    assert r and r["m_legenda"] == 500.0 and r["m_mapa_chave"] == 0.0 and r["fracao"] == 1.0, legenda


@pytest.mark.parametrize("outro", ["ALG_Bloco_3_0", "COLEG_Sala_3_0", "9_Legendario_4_0", "LG2_Bloco_3_0"])
def test_CONTROLE_o_que_so_parece_legenda_conta_como_resto_do_arquivo(outro):
    assert dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 10.0), (outro, 500.0)), _CORTE + [outro]) == {}, outro


def test_dois_cortes_no_mesmo_arquivo_somam():
    bb = ["B_Corte BB_2_ARQ - Parede", "B_Corte BB_2_ARQ - Piso", "B_Corte BB_2_EST - Viga"]
    r = dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 60.0), (bb[0], 40.0)), _CORTE + bb)
    assert r["titulo"] == "Corte AA | Corte BB" and r["desenhos"] == 2 and r["fracao"] == 1.0


def test_a_fracao_vale_em_noventa_por_cento_exatos_e_nao_abaixo():
    nomes = _CORTE + _PLANTA
    assert dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 90.0), (_PLANTA[0], 10.0)), nomes)["fracao"] == 0.9
    assert dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 89.99), (_PLANTA[0], 10.01)), nomes) == {}
    # o que está FORA da convenção também é o resto do arquivo
    assert dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 89.0), ("0", 11.0)), nomes) == {}
    assert dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 95.0), ("0", 5.0)), nomes)["fracao"] == 0.95


def test_noventa_por_cento_exatos_valem_mesmo_quando_a_soma_em_ponto_flutuante_fica_um_fio_abaixo():
    """14,31 + 28,62 são 42,93 de corte em 47,70: 90 % exatos — e a divisão dá 0,8999999999999999."""
    paredes = _walls((_CORTE[0], 14.31), (_CORTE[1], 28.62), (_PLANTA[0], 4.77))
    assert (14.31 + 28.62) / (14.31 + 28.62 + 4.77) < 0.9                  # a armadilha existe
    assert dx.vista_pelo_prefixo_dos_layers(paredes, _CORTE + _PLANTA)["fracao"] == 0.9


def test_CONTROLE_a_planta_da_convencao_nao_e_vista():
    assert dx.vista_pelo_prefixo_dos_layers(_walls((_PLANTA[0], 80.0), (_PLANTA[1], 20.0)), _PLANTA) == {}


def test_CONTROLE_o_nome_inteiro_do_layer_nao_decide_so_o_campo_do_desenho():
    """A marca de corte da planta: "…_ANT.Marcador - Corte". O layer diz corte, o
    desenho é a planta — e `tipo_do_desenho` do nome inteiro diria 'vista'."""
    from engine_rules import tipo_do_desenho
    assert tipo_do_desenho(_PLANTA[2].replace("_", " ")) == "vista"
    assert dx.vista_pelo_prefixo_dos_layers(_walls((_PLANTA[2], 100.0)), _PLANTA) == {}


def test_CONTROLE_fora_da_convencao_o_layer_chamado_corte_nao_decide():
    nomes = ["CORTE", "A-CORTE", "ARQ_CORTE_1", "PAREDE"]
    assert dx.vista_pelo_prefixo_dos_layers(_walls(("CORTE", 95.0), ("PAREDE", 5.0)), nomes) == {}
    assert dx.vista_pelo_prefixo_dos_layers(_walls(("ARQ_CORTE_1", 100.0)), nomes) == {}


def test_CONTROLE_o_prefixo_e_o_COMECO_do_nome_do_layer_e_o_id_e_curto():
    """O id do desenho tem até 12 letras ("XX - LEG" é o mais longo medido). Um nome de
    layer comprido com "_Corte AA_1_" no meio não é a convenção."""
    nomes = ["PAVIMENTO TERREO_Corte AA_1_" + s for s in ("ARQ - Parede", "ARQ - Piso", "EST - Viga")]
    assert dx.vista_pelo_prefixo_dos_layers(_walls((nomes[0], 30.0)), nomes) == {}


def test_CONTROLE_o_prefixo_com_menos_de_tres_layers_nao_e_desenho():
    assert dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 100.0)), _CORTE[:2]) == {}
    assert dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 100.0)), _CORTE)


def test_CONTROLE_corte_com_planta_ou_com_detalhe_pesando_nao_e_arquivo_de_vista():
    det = ["2_Detalhe 1_ Shaft_12_ARQ - Parede", "2_Detalhe 1_ Shaft_12_ARQ - Piso", "2_Detalhe 1_ Shaft_12_HID - Tubo"]
    assert dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 85.0), (_PLANTA[0], 15.0)), _CORTE + _PLANTA) == {}
    assert dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 80.0), (det[0], 20.0)), _CORTE + det) == {}


def test_a_forma_do_prefixo_medida_no_acervo():
    """O <n> não é sempre 1, o id pode ter espaço e hífen, o nome pode ter "_"."""
    for pre in ("A_Corte AA_12_", "XPTO - CRT_Corte AA_2_", "C_Corte 1_ escada_7_", "6._Fachada Sul_1_"):
        nomes = [pre + s for s in ("ARQ - Parede", "ARQ - Piso", "EST - Viga")]
        assert dx.vista_pelo_prefixo_dos_layers(_walls((nomes[0], 30.0)), nomes), pre
    # o prefixo acaba no PRIMEIRO "_<n>_": o resto é o nome do layer, mesmo com "_2_" dentro
    nomes = ["A_Corte AA_1_ARQ_2_Parede", "A_Corte AA_1_ARQ_3_Piso", "A_Corte AA_1_EST_2_Viga"]
    assert dx.vista_pelo_prefixo_dos_layers(_walls((nomes[0], 30.0)), nomes)["titulo"] == "Corte AA"


def test_a_tabela_e_a_entidade_podem_escrever_o_layer_com_caixa_diferente():
    """Nome de layer não distingue maiúscula no CAD; o título sai como a entidade escreve."""
    tabela = [n.upper() for n in _CORTE]
    r = dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 30.0), (_CORTE[1].lower(), 10.0)), tabela)
    assert r["titulo"] == "Corte AA" and r["desenhos"] == 1 and r["m"] == 40.0


def test_sem_comprimento_ou_com_entrada_torta_devolve_vazio(caplog):
    with caplog.at_level(logging.WARNING):
        assert dx.vista_pelo_prefixo_dos_layers([], _CORTE) == {}
        assert dx.vista_pelo_prefixo_dos_layers(None, None) == {}
        assert dx.vista_pelo_prefixo_dos_layers(_walls((_CORTE[0], 0.0), (_MAPA, 500.0)), _CORTE + [_MAPA]) == {}
        assert dx.vista_pelo_prefixo_dos_layers([object()], [None, 3]) == {}
    # arquivo sem comprimento é o caso comum, não um erro: sai pelo "se", não pela exceção
    assert not [r for r in caplog.records if "vista_pelo_prefixo_dos_layers" in r.getMessage()]


# ── do DXF à medição ─────────────────────────────────────────────────────────
def _hachura(msp, layer, x0, y0, w, h):
    hx = msp.add_hatch(dxfattribs={"layer": layer})
    hx.paths.add_polyline_path([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)], is_closed=True)


def _dxf(tmp_path, desenho="A_Corte AA_1_", nome="vista.dxf", mapa=True):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    par, gc, esc, rev = (desenho + s for s in ("ARQ - Parede", "ARQ - Guarda-Corpo", "EST - Escada", "ARQ - Revestimento"))
    for n in (par, gc, esc, rev):
        doc.layers.add(n)
    # o corte: paredes, o guarda-corpo com as diagonais, a escada em degraus
    for y in (0.0, 3.0, 6.0, 9.0):
        msp.add_line((0, y), (20, y + 0.4), dxfattribs={"layer": par})
    for k in range(8):
        msp.add_line((2.5 * k, 10), (2.5 * k + 2.5, 11), dxfattribs={"layer": gc})
    for k in range(10):
        msp.add_line((22 + k, 0.3 * k), (23 + k, 0.3 * k + 0.3), dxfattribs={"layer": esc})
    _hachura(msp, rev, 2.0, 4.0, 4.0, 3.0)        # o painel ao fundo: 12 m², fica
    _hachura(msp, rev, 0.0, 2.9, 6.0, 0.2)        # a laje cortada: faixa de 0,2 m, sai (só no corte)
    b = doc.blocks.new(name="BACIA 01")
    b.add_circle((0, 0), 0.2)
    b.add_line((-0.3, 0), (0.3, 0))
    for i in range(2):
        msp.add_blockref("BACIA 01", (5 + 4 * i, 1), dxfattribs={"layer": rev})
    if mapa:
        doc.layers.add("001_MAPA CHAVE_3_0")
        for k in range(20):                       # o mapa-chave: 1.000 m num layer só
            msp.add_line((200, 3.0 * k), (250, 3.0 * k + 0.5), dxfattribs={"layer": "001_MAPA CHAVE_3_0"})
    p = str(tmp_path / nome)
    doc.saveas(p)
    return p


def _metros(ex):
    return round(sum(float(v) for v in ex.get_walls_by_layer().values()), 1)


def _area(ex):
    return round(sum(float(h.area) * float(getattr(h, "peso", 1.0)) for h in ex.hatches), 2)


def test_o_arquivo_de_corte_sai_como_vista(tmp_path):
    ex = dx.extract_dxf(_dxf(tmp_path))
    f = ex.folhas
    assert f.get("aplicada") is True, f
    assert f["desenhos_lista"] == [{"folha": "modelo", "titulo": "Corte AA", "tipo": "vista", "andares": 1,
                                    "como": "prefixo dos layers"}]
    assert f["origem"] == "prefixo dos layers"
    assert f["vista_pelo_prefixo"]["titulo"] == "Corte AA" and f["vista_pelo_prefixo"]["m_mapa_chave"] > 900
    assert _metros(ex) == 0.0, ex.get_walls_by_layer()             # o comprimento sai — o do mapa-chave junto
    assert _area(ex) == 12.0                                       # o painel fica; a seção fina cortada sai
    assert all(getattr(h, "na_vista", False) for h in ex.hatches)
    assert {b.name: b.count for b in ex.blocks} == {"BACIA 01": 2}  # a peça que só o corte mostra fica
    prompt = ex.to_structured_prompt()
    assert "o objeto visto DE LADO" in prompt and "Corte AA" in prompt
    # a área que fica vai ao prompt MARCADA: vista de lado, não é piso, laje nem forro
    da_area = [l for l in prompt.splitlines() if l.strip().startswith("A_Corte AA_1_ARQ - Revestimento:")]
    assert da_area and all("DENTRO de corte/elevação" in l and "12.00 m²" in l for l in da_area), da_area


def test_CONTROLE_com_a_chave_em_zero_e_como_hoje(tmp_path, monkeypatch):
    monkeypatch.setenv(CHAVE, "0")
    ex = dx.extract_dxf(_dxf(tmp_path))
    assert ex.folhas.get("aplicada") is False
    assert ex.folhas.get("motivo") == "nenhum desenho com título que diga o que é"
    assert _metros(ex) > 1000 and _area(ex) == 13.2
    assert "o objeto visto DE LADO" not in ex.to_structured_prompt()


def test_na_fachada_a_faixa_fina_fica(tmp_path):
    """Seção cortada só existe no CORTE: na elevação toda a área é revestimento."""
    ex = dx.extract_dxf(_dxf(tmp_path, desenho="F_Fachada Sul_2_"))
    assert ex.folhas["desenhos_lista"][0]["titulo"] == "Fachada Sul"
    assert _metros(ex) == 0.0 and _area(ex) == 13.2


def test_CONTROLE_a_planta_com_a_convencao_fica_igual_e_o_nome_nao_multiplica(tmp_path, monkeypatch):
    desenho = "4._PAV TIPO I (3° ao 24° pavto) - 22x_1_"
    p = _dxf(tmp_path, desenho=desenho, nome="planta.dxf", mapa=False)
    com = dx.extract_dxf(p)
    monkeypatch.setenv(CHAVE, "0")
    sem = dx.extract_dxf(p)
    assert com.folhas.get("aplicada") is False and "vista_pelo_prefixo" not in com.folhas
    assert _metros(com) == _metros(sem) > 0 and _area(com) == _area(sem) == 13.2
    assert all(float(getattr(w, "peso", 1.0)) == 1.0 for w in com.walls)
    assert com.to_structured_prompt() == sem.to_structured_prompt()


@pytest.mark.parametrize("tipo", ["planta", "fora", "vista"])
def test_CONTROLE_com_desenho_de_tipo_no_mapa_a_regua_nem_e_consultada(tmp_path, monkeypatch, tipo):
    """Título ou janela que diga o que o desenho é ganha do prefixo."""
    chamadas = []
    orig_mapa, orig_regua = dx.mapa_de_folhas, dx.vista_pelo_prefixo_dos_layers

    def mapa(doc):
        m = orig_mapa(doc)
        m["folhas"] = [{"folha": "F1", "titulo": "DESENHO 1", "tipo": tipo, "andares": 1,
                        "caixa": (-10.0, -10.0, 300.0, 100.0), "como": ""}]
        return m

    def regua(walls, nomes_de_layer):
        chamadas.append(1)
        return orig_regua(walls, nomes_de_layer)

    monkeypatch.setattr(dx, "mapa_de_folhas", mapa)
    monkeypatch.setattr(dx, "vista_pelo_prefixo_dos_layers", regua)
    ex = dx.extract_dxf(_dxf(tmp_path))
    assert not chamadas
    assert [(d["tipo"], d["titulo"], d["como"]) for d in ex.folhas["desenhos_lista"]] == [(tipo, "DESENHO 1", "")]
    assert "vista_pelo_prefixo" not in ex.folhas
    monkeypatch.setattr(dx, "mapa_de_folhas", orig_mapa)
    dx.extract_dxf(_dxf(tmp_path, nome="de_novo.dxf"))
    assert chamadas == [1], "sem tipo no mapa, a régua é consultada"


def test_o_desenho_que_vai_pra_leitura_por_folha_e_o_arquivo_inteiro(tmp_path, monkeypatch):
    visto = {}
    orig = dx.aplicar_leitura_por_folha

    def espia(walls, hatches, polygon_areas, blocks, mapa):
        visto["mapa"] = {k: (list(v) if k == "folhas" else v) for k, v in mapa.items()}
        visto["pontos"] = ([w.start for w in walls] + [w.end for w in walls]
                           + [p for b in blocks for p in b.positions]
                           + [(h.bbox[0], h.bbox[1]) for h in hatches] + [(h.bbox[2], h.bbox[3]) for h in hatches])
        return orig(walls, hatches, polygon_areas, blocks, mapa)

    monkeypatch.setattr(dx, "aplicar_leitura_por_folha", espia)
    dx.extract_dxf(_dxf(tmp_path))
    (reg,) = visto["mapa"]["folhas"]
    assert (reg["tipo"], reg["andares"], reg["arquivo_inteiro"], reg["titulo"]) == ("vista", 1, True, "Corte AA")
    assert len(visto["pontos"]) > 50 and all(dx._dentro(p, reg["caixa"]) for p in visto["pontos"])


# ── o trecho sem posição ─────────────────────────────────────────────────────
def _parede(layer, m, a=(0, 0), b=(0, 0)):
    return dx.WallSegment(layer=layer, length=m, start=a, end=b)


def test_no_arquivo_que_e_inteiro_vista_o_trecho_sem_posicao_tambem_sai():
    reg = {"folha": "modelo", "titulo": "Corte AA", "tipo": "vista", "andares": 1, "caixa": (-1, -1, 50, 50),
           "arquivo_inteiro": True}
    walls = [_parede("X", 7.0), _parede("X", 5.0, (0, 0), (5, 0))]
    r = dx.aplicar_leitura_por_folha(walls, [], [], [], {"folhas": [reg]})
    assert walls == [] and r["vista"]["m"] == 12.0 and r["depois"]["comprimento"] == 0


def test_CONTROLE_na_vista_que_e_uma_regiao_o_trecho_sem_posicao_fica():
    reg = {"folha": "modelo", "titulo": "Corte AA", "tipo": "vista", "andares": 1, "caixa": (-1, -1, 50, 50)}
    walls = [_parede("X", 7.0), _parede("X", 5.0, (0, 0), (5, 0))]
    r = dx.aplicar_leitura_por_folha(walls, [], [], [], {"folhas": [reg]})
    assert [w.length for w in walls] == [7.0] and r["vista"]["m"] == 5.0
    # e duas vistas, uma delas marcada, não são "o arquivo inteiro"
    walls = [_parede("X", 7.0)]
    dx.aplicar_leitura_por_folha(walls, [], [], [], {"folhas": [dict(reg, arquivo_inteiro=True), dict(reg)]})
    assert [w.length for w in walls] == [7.0]
    # nem a marca num desenho que não é vista
    walls = [_parede("X", 7.0), _parede("X", 5.0, (0, 0), (5, 0))]
    dx.aplicar_leitura_por_folha(walls, [], [], [], {"folhas": [dict(reg, tipo="fora", arquivo_inteiro=True)]})
    assert [w.length for w in walls] == [7.0]


def test_a_caixa_do_arquivo_contem_tudo_o_que_tem_posicao():
    class _H:
        bbox = (1010.0, 1010.0, 1030.0, 1040.0)

    class _B:
        positions = [(995.0, 1002.0), (1100.0, 1003.0)]

    # 🪤 o trecho sem posição (0,0)-(0,0) não puxa a caixa pra origem
    cx = dx._caixa_do_arquivo([_parede("X", 1.0), _parede("X", 5.0, (1000, 993), (1005, 1000))], [_H()], [], [_B()])
    assert cx == (995.0, 993.0, 1100.0, 1040.0)
    assert not dx._dentro((0.0, 0.0), cx)
    vazia = dx._caixa_do_arquivo([_parede("X", 1.0)], [], [], [])
    assert dx._dentro((123456.0, -98765.0), vazia) and dx._dentro((0.0, 0.0), vazia)


# ── o log e a chave ──────────────────────────────────────────────────────────
def test_o_log_diz_que_foi_pelo_prefixo(tmp_path):
    import main
    linha = main._leitura_por_folha_resumo(dx.extract_dxf(_dxf(tmp_path)))
    assert "aplicada=sim" in linha and "vistas=1" in linha
    assert " origem=prefixo-dos-layers[Corte AA 100% de " in linha and "mapa-chave 1000" in linha


def test_a_chave_e_lida_no_extrator_e_e_avaliavel():
    fonte = io.open(os.path.join(_BACKEND, "dwg_extractor.py"), encoding="utf-8").read()
    assert fonte.count('os.environ.get("%s"' % CHAVE) == 1
    main = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    bloco = re.search(r"_CHAVES_AVALIAVEIS = frozenset\(\{(.*?)\}\)", main, re.S).group(1)
    assert '"%s"' % CHAVE in bloco
