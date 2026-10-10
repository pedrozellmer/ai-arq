# -*- coding: utf-8 -*-
"""O que entrou na conta e nenhuma janela das pranchas mostra vira AVISO, com o número.

🩸 09/10/2026 — DWG de reforma com 27 janelas no layout. As três plantas das
pranchas somavam 2.554 m de linha; no modelo, fora de todas as janelas, havia
mais 5.611 m: as plantas de outro projeto do mesmo prédio e uma fileira de
cópias de trabalho. A leitura por folha pesa cada trecho pela POSIÇÃO, e o que
não toca desenho nenhum conta 1 — a alvenaria saiu ~3× e nada na tela dizia por
quê. O número já existia (`medida.sem_folha`), só no log.

🩸 10/10 — o mesmo projeto, com o modelo limpo: em metro sobraram 5 %, em área
844 de 1.048 m² (hachuras esquecidas ao lado das plantas, que viraram uma linha
de piso de 850 m²). Por isso o aviso olha metro E área.

📏 A faixa é medida. Acervo: 40 de 96 jobs com janelas têm arquivo com mais de
20 % do metro fora delas; em 17 as janelas não cobrem quase nada (o projetista
plota do modelo) — tirar o de fora zeraria esses, e avisar seria alarme falso.
Por isso: só AVISA, e só de 20 % a 90 %, com 50 m (ou m²) fora e dentro.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import main  # noqa: E402


# ── o arquivo: a planta na prancha e uma cópia dela esquecida no modelo ───────
def _viewport(lay, janela, centro_papel=(200, 150)):
    x0, y0, x1, y1 = janela
    esc = 10.0
    return lay.add_viewport(center=centro_papel, size=((x1 - x0) * esc, (y1 - y0) * esc),
                            view_center_point=((x0 + x1) / 2, (y0 + y1) / 2), view_height=(y1 - y0))


def _titulo(msp, doc, texto, x, y):
    if "TIT" not in doc.blocks:
        b = doc.blocks.new("TIT")
        b.add_attdef("TITULODODESENHO", (0, 0), dxfattribs={"height": 0.3})
    msp.add_blockref("TIT", (x, y)).add_attrib("TITULODODESENHO", texto, (x, y))


def _desenho(msp, x, comprimento, largura_hachura):
    """4 linhas de `comprimento` e uma hachura de 10 × `largura_hachura`, a partir de x."""
    for y in (5, 10, 15, 20):
        msp.add_line((x + 5, y), (x + 5 + comprimento, y), dxfattribs={"layer": "GAS-TUBO"})
    h = msp.add_hatch(dxfattribs={"layer": "PISO-CERAMICO"})
    h.paths.add_polyline_path([(x + 5, 22), (x + 15, 22), (x + 15, 22 + largura_hachura),
                               (x + 5, 22 + largura_hachura)], is_closed=True)


def _arquivo(tmp_path, copia_fora=True, folhas=True, folha="A1 TERREO",
             titulo="PLANTA BAIXA TÉRREO", elevacao=False):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6                  # metros
    msp = doc.modelspace()
    _desenho(msp, 0, 25, 6)                      # na prancha: 100 m e 60 m²
    _titulo(msp, doc, titulo, 20, 1)
    if copia_fora:
        _desenho(msp, 200, 20, 7)                # esquecida no modelo: 80 m e 70 m²
    if elevacao:                                 # 50 m de linha vista de lado: sai da soma
        msp.add_line((82, 5), (97, 5), dxfattribs={"layer": "GAS-TUBO"})
        msp.add_line((82, 8), (97, 8), dxfattribs={"layer": "GAS-TUBO"})
        msp.add_line((82, 11), (102, 11), dxfattribs={"layer": "GAS-TUBO"})
        _titulo(msp, doc, "ELEVAÇÃO 1", 90, 1)
    if folhas:
        _viewport(doc.layouts.new(folha), (0, 0, 40, 30))
        if elevacao:
            _viewport(doc.layouts.new("ELEV"), (80, 0, 105, 15))
    p = str(tmp_path / "planta.dxf")
    doc.saveas(p)
    return p


def test_o_extrator_mede_o_que_ficou_fora_das_janelas(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path))
    f = ex.metadata.get("fora_das_pranchas")
    assert f, "80 m e 70 m² estão no modelo fora da única janela — tem de sair medido"
    assert f["m"] == pytest.approx(80.0) and f["total_m"] == pytest.approx(180.0)
    assert f["fracao"] == pytest.approx(80 / 180, abs=0.001)
    assert f["m2"] == pytest.approx(70.0) and f["total_m2"] == pytest.approx(130.0)
    assert f["fracao_m2"] == pytest.approx(70 / 130, abs=0.001)
    assert f["janelas_sem_leitura"] == 0
    # só mede: a soma não muda
    assert ex.get_walls_by_layer().get("GAS-TUBO") == pytest.approx(180.0)
    assert ex.get_areas_by_layer().get("PISO-CERAMICO") == pytest.approx(130.0)


def test_o_total_e_o_que_FICOU_na_conta_planta_tipo_vale_pelos_andares(tmp_path, monkeypatch):
    """A fração é sobre a soma que o cliente recebe: a planta-tipo de 3 andares pesa 3."""
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, folha="4 - 5 E 6 PAV.", titulo="PLANTA BAIXA PAVIMENTO TIPO"))
    f = ex.metadata["fora_das_pranchas"]
    assert f["m"] == pytest.approx(80.0) and f["total_m"] == pytest.approx(3 * 100.0 + 80.0)
    assert f["m2"] == pytest.approx(70.0) and f["total_m2"] == pytest.approx(3 * 60.0 + 70.0)
    assert f["fracao"] == pytest.approx(80 / 380, abs=0.001)


def test_o_total_nao_conta_a_linha_que_a_vista_tirou(tmp_path, monkeypatch):
    """Os 50 m da elevação saem da soma; contar com eles encolheria a fração do que está fora."""
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, elevacao=True))
    f = ex.metadata["fora_das_pranchas"]
    assert f["m"] == pytest.approx(80.0) and f["total_m"] == pytest.approx(180.0)


def test_CONTROLE_tudo_dentro_da_janela_nao_mede_nada(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, copia_fora=False))
    assert "fora_das_pranchas" not in ex.metadata
    assert ex.get_walls_by_layer().get("GAS-TUBO") == pytest.approx(100.0)


def test_CONTROLE_sem_prancha_nenhuma_nao_ha_o_que_estar_fora(tmp_path, monkeypatch):
    """Arquivo sem layout: tudo seria "fora" — número que não diz nada."""
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, folhas=False))
    assert "fora_das_pranchas" not in ex.metadata


# ── a medida, peça por peça ───────────────────────────────────────────────────
def _w(x0, x1, peso=1.0):
    w = dx.WallSegment(layer="L", length=abs(x1 - x0), start=(x0, 5.0), end=(x1, 5.0))
    w.peso = peso
    return w


def _h(area, bbox=(0, 0, 1, 1), peso=1.0):
    h = dx.HatchArea(layer="H", area=area, bbox=bbox)
    h.peso = peso
    return h


_MAPA = {"folhas": [{"caixa": (0, 0, 20, 20), "tipo": "planta"}], "gerais": 0, "sem_janela": 0}
_MEDIDA = {"sem_folha": {"m": 30.0, "m2": 40.0, "blocos": 0}}


def test_o_que_nao_tem_posicao_fica_fora_do_total():
    sem_posicao = dx.WallSegment(layer="L", length=999.0)            # explodido de bloco
    sem_caixa = dx.HatchArea(layer="H", area=999.0)
    f = dx.fora_das_pranchas([_w(0, 10, peso=3.0), _w(100, 130), sem_posicao],
                             [_h(20.0, peso=3.0), _h(40.0, bbox=(100, 0, 110, 4)), sem_caixa], [],
                             _MEDIDA, _MAPA)
    assert f["total_m"] == pytest.approx(60.0) and f["fracao"] == pytest.approx(0.5)
    assert f["total_m2"] == pytest.approx(100.0) and f["fracao_m2"] == pytest.approx(0.4)


def test_area_de_contorno_fechado_entra_no_total():
    f = dx.fora_das_pranchas([_w(0, 10)], [_h(10.0)], [_h(50.0, bbox=(100, 0, 110, 5))], _MEDIDA, _MAPA)
    assert f["total_m2"] == pytest.approx(60.0)


@pytest.mark.parametrize("origem", ["modelo", "modelo sem janela"])
def test_CONTROLE_desenho_achado_pelo_titulo_no_modelo_nao_e_prancha(origem):
    """Com `origem`, as caixas do mapa são desenhos achados pelo TÍTULO dentro do
    modelspace — "fora deles" não quer dizer fora das pranchas."""
    assert dx.fora_das_pranchas([_w(0, 10), _w(100, 130)], [], [], _MEDIDA, dict(_MAPA, origem=origem)) == {}
    assert dx.fora_das_pranchas([_w(0, 10), _w(100, 130)], [], [], _MEDIDA, dict(_MAPA, origem=""))


@pytest.mark.parametrize("medida, mapa", [
    ({}, _MAPA),
    ({"sem_folha": {"m": 0.0, "m2": 0.0, "blocos": 7}}, _MAPA),
    (_MEDIDA, {"folhas": []}),
    (_MEDIDA, None),
    (None, None),
])
def test_CONTROLE_sem_medida_ou_sem_janela_devolve_vazio(medida, mapa):
    assert dx.fora_das_pranchas([_w(0, 10)], [], [], medida, mapa) == {}


def test_so_area_fora_tambem_mede():
    f = dx.fora_das_pranchas([_w(0, 10)], [_h(10.0), _h(40.0, bbox=(100, 0, 110, 4))], [],
                             {"sem_folha": {"m": 0.0, "m2": 40.0, "blocos": 0}}, _MAPA)
    assert f["m"] == 0.0 and f["fracao"] == 0.0
    assert f["m2"] == pytest.approx(40.0) and f["fracao_m2"] == pytest.approx(0.8)


def test_a_janela_girada_ou_em_3d_que_nao_se_le_vai_junto():
    f = dx.fora_das_pranchas([_w(0, 10), _w(100, 130)], [], [], _MEDIDA, dict(_MAPA, sem_janela=2))
    assert f["janelas_sem_leitura"] == 2


def test_nunca_levanta():
    assert dx.fora_das_pranchas(None, None, None, _MEDIDA, _MAPA)["total_m"] == 0.0
    assert dx.fora_das_pranchas([object()], [], [], _MEDIDA, _MAPA) == {}


# ── a linha que o cliente lê ──────────────────────────────────────────────────
def _arq(nome, m=0.0, total_m=0.0, m2=0.0, total_m2=0.0, sem=0):
    """Como o extrator grava: a fração vem arredondada em 3 casas."""
    return {"nome": nome, "status": "cotas", "fora_das_pranchas": {
        "m": m, "total_m": total_m, "fracao": round(m / total_m, 3) if total_m else 0.0,
        "m2": m2, "total_m2": total_m2, "fracao_m2": round(m2 / total_m2, 3) if total_m2 else 0.0,
        "janelas_sem_leitura": sem}}


def test_a_linha_traz_o_arquivo_e_o_numero():
    linhas = main._linhas_fora_das_pranchas([_arq("REFORMA REV01", m=5611.0, total_m=8668.0)])
    assert len(linhas) == 1
    assert linhas[0].startswith("⚠ Parte do desenho está FORA das pranchas — REFORMA REV01: ")
    assert "65 % do comprimento (5.611 m de 8.668 m)" in linhas[0]
    assert "área de hachura" not in linhas[0]
    assert "envie de novo" in linhas[0]


def test_a_area_avisa_sozinha_quando_o_metro_esta_limpo():
    """O arquivo limpo de 10/10: 5 % do metro, 81 % da área. 🪤 O percentual sai de
    fora/total: a fração gravada (0,805) arredondava pra "80 %" na leitura real."""
    linha, = main._linhas_fora_das_pranchas([_arq("QUANTITATIVO", m=307.1, total_m=6364.2,
                                                  m2=844.2, total_m2=1048.1)])
    assert "81 % da área de hachura (844 m² de 1.048 m²)" in linha
    assert "do comprimento" not in linha


def test_a_faixa_e_decidida_pelos_numeros_nao_pela_fracao_gravada():
    a = _arq("A", m=500.0, total_m=1000.0)
    del a["fora_das_pranchas"]["fracao"]
    assert "50 % do comprimento" in main._linhas_fora_das_pranchas([a])[0]
    b = _arq("B", m=10.0, total_m=1000.0)
    b["fora_das_pranchas"]["fracao"] = 0.5          # fração que não bate com os números: valem os números
    assert main._linhas_fora_das_pranchas([b]) == []


def test_metro_e_area_na_mesma_linha():
    linha, = main._linhas_fora_das_pranchas([_arq("A", m=5611.0, total_m=8668.0, m2=888.0, total_m2=1090.0)])
    assert "65 % do comprimento (5.611 m de 8.668 m) e 81 % da área de hachura (888 m² de 1.090 m²)" in linha


@pytest.mark.parametrize("m, total", [
    (50.0, 250.0),          # 20 % exatos, com 50 m fora
    (899.0, 1000.0),        # 89,9 %
    (300.0, 350.0),         # 86 %, com 50 m dentro
])
def test_a_faixa_avisa(m, total):
    assert main._linhas_fora_das_pranchas([_arq("A", m=m, total_m=total)])
    assert main._linhas_fora_das_pranchas([_arq("A", m2=m, total_m2=total)])


@pytest.mark.parametrize("m, total, por_que", [
    (199.0, 1000.0, "19,9 % — sobra comum de desenho"),
    (900.0, 1000.0, "90 % — as janelas não cobrem o desenho: o projetista plota do modelo"),
    (1000.0, 1000.0, "100 % — idem"),
    (49.0, 120.0, "41 %, mas só 49 fora"),
    (300.0, 349.0, "86 %, mas só 49 dentro"),
    (0.0, 1000.0, "nada fora"),
    (0.0, 0.0, "nada medido"),
])
def test_CONTROLE_fora_da_faixa_cala(m, total, por_que):
    assert main._linhas_fora_das_pranchas([_arq("A", m=m, total_m=total)]) == [], por_que
    assert main._linhas_fora_das_pranchas([_arq("A", m2=m, total_m2=total)]) == [], por_que


def test_uma_linha_so_por_projeto_com_ate_quatro_arquivos():
    arqs = [_arq("P%d" % i, m=500.0, total_m=1000.0) for i in range(6)] + [_arq("LIMPO", m=10.0, total_m=1000.0)]
    linhas = main._linhas_fora_das_pranchas(arqs)
    assert len(linhas) == 1
    assert all(("P%d: " % i) in linhas[0] for i in range(4)) and "P4: " not in linhas[0]
    assert "; e mais 2." in linhas[0] and "LIMPO" not in linhas[0]


def test_a_janela_que_nao_se_le_e_dita_so_quando_existe():
    com, = main._linhas_fora_das_pranchas([_arq("A", m=500.0, total_m=1000.0, sem=1)])
    sem, = main._linhas_fora_das_pranchas([_arq("A", m=500.0, total_m=1000.0)])
    assert "1 janela(s) girada(s) ou em 3D" in com
    assert "girada" not in sem


def test_contagem_de_janela_estragada_nao_derruba_a_linha():
    linha, = main._linhas_fora_das_pranchas([_arq("A", m=500.0, total_m=1000.0, sem="x")])
    assert "50 % do comprimento" in linha and "girada" not in linha


def test_a_linha_nao_fala_em_motor():
    """Regra da casa na área logada: quem fala é "a gente"."""
    linha, = main._linhas_fora_das_pranchas([_arq("A", m=500.0, total_m=1000.0, m2=500.0, total_m2=1000.0, sem=1)])
    assert "motor" not in linha.lower()


@pytest.mark.parametrize("arqs", [
    None, [], [None], [{}], [{"nome": "A", "status": "cotas"}],
    [{"nome": "A", "fora_das_pranchas": {"m": "x", "total_m": None}}],
    [{"nome": "A", "fora_das_pranchas": "texto"}],
])
def test_CONTROLE_sem_a_medida_nao_ha_linha_nem_erro(arqs):
    assert main._linhas_fora_das_pranchas(arqs) == []


# ── a fiação dentro do processamento (onde nenhum teste alcança) ──────────────
_FIOS = ('_res_esc["fora_das_pranchas"] = _md_u["fora_das_pranchas"]',
         "_linhas_esc += _linhas_fora_das_pranchas(_escala_arqs)")


def _fiacao_inteira(fonte: str) -> bool:
    return all(fio in fonte for fio in _FIOS)


def _aviso_tem_rede_propria(fonte: str) -> bool:
    """A soma do aviso novo aos avisos está SOZINHA num try que pega Exception?
    Sem isso, um erro aqui cairia no `except` de fora e levaria junto as linhas
    de escala — o aviso novo apagando os antigos."""
    import ast
    for no in ast.walk(ast.parse(fonte)):
        if not (isinstance(no, ast.Try) and len(no.body) == 1 and isinstance(no.body[0], ast.AugAssign)):
            continue
        soma = no.body[0]
        if getattr(soma.target, "id", "") == "_linhas_esc" and "_linhas_fora_das_pranchas" in ast.dump(soma.value):
            return any(getattr(h.type, "id", "") == "Exception" for h in no.handlers)
    return False


def test_o_processamento_leva_a_medida_ate_os_avisos_do_projeto():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as fh:
        fonte = fh.read()
    assert _fiacao_inteira(fonte)
    for fio in _FIOS:                            # o guarda reprova quando um fio some
        assert not _fiacao_inteira(fonte.replace(fio, "pass"))
    assert _aviso_tem_rede_propria(fonte)


def test_CONTROLE_o_guarda_da_rede_propria_reprova():
    soma = "_linhas_esc += _linhas_fora_das_pranchas(x)"
    assert _aviso_tem_rede_propria("try:\n    %s\nexcept Exception:\n    pass\n" % soma)
    assert not _aviso_tem_rede_propria(soma + "\n")
    assert not _aviso_tem_rede_propria("try:\n    a = 1\n    %s\nexcept Exception:\n    pass\n" % soma)
    assert not _aviso_tem_rede_propria("try:\n    %s\nexcept NameError:\n    pass\n" % soma)
