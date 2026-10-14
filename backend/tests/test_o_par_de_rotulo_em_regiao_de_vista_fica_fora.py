# -*- coding: utf-8 -*-
"""O par RÓTULO ↔ ÁREA DA REGIÃO cuja região está DENTRO de corte/elevação sai da seção do prompt.

🩸 13/10/2026 — a seção casa o texto com a região fechada que o contém e diz
"Use como a quantidade daquele ambiente", e nunca olhou a marca `na_vista` da
região: num arquivo de corte, o nome do cômodo escrito em cada andar casava com
a hachura da PAREDE vista de lado (44 pares num arquivo só).
📏 No acervo: 142 dos 590 pares dos arquivos com vista, e nenhum é área de ambiente.
🔑 Subtração: a área da região continua em ÁREAS HACHURADAS POR LAYER, com o
aviso de vista de lado que já existia.
🪤 Pela marca da região QUE CASOU: tirar a região da lista antes de casar faria o
texto dela cair na próxima maior que o contém.

🪤 Nomes FICTÍCIOS (repositório público).
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
import engine_rules as E  # noqa: E402

CHAVE = "PAR_DE_ROTULO_EM_VISTA_FORA"
MARCA = "rotulo_em_vista_fora"
CABECALHO = "RÓTULO ↔ ÁREA DA REGIÃO (casado na geometria, não é chute):"


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.delenv(CHAVE, raising=False)


# ── o par leva a marca da região que casou ───────────────────────────────────
def _regiao(layer, m2, caixa, vista=False):
    h = dx.HatchArea(layer=layer, area=m2, bbox=caixa, preenchimento=1.0)
    if vista:
        h.na_vista = True
    return h


def _texto(t, x, y, **mais):
    return dx.TextAnnotation(layer="TEXTO", text=t, position=(x, y), height=0.2, **mais)


def test_o_par_diz_se_a_regiao_esta_na_vista():
    pares = E.casar_texto_com_regiao(
        [_texto("SANIT.", 3, 3), _texto("SALA", 23, 3)],
        [_regiao("ARQ-REVEST", 3.84, (2, 2, 4, 4), vista=True), _regiao("PISO", 16.0, (21, 1, 25, 5))])
    assert {p["texto"]: p["na_vista"] for p in pares} == {"SANIT.": True, "SALA": False}


def test_a_regiao_em_dicionario_tambem_leva_a_marca():
    par = E.casar_texto_com_regiao(
        [{"text": "SANIT.", "position": (3, 3)}],
        [{"layer": "X", "area": 4.0, "bbox": (2, 2, 4, 4), "preenchimento": 1.0, "na_vista": True}])
    assert [p["na_vista"] for p in par] == [True]
    sem = E.casar_texto_com_regiao(
        [{"text": "SANIT.", "position": (3, 3)}],
        [{"layer": "X", "area": 4.0, "bbox": (2, 2, 4, 4), "preenchimento": 1.0}])
    assert [p["na_vista"] for p in sem] == [False]


# ── a seção do prompt ────────────────────────────────────────────────────────
def _extracao(textos, regioes, marca=True, contornos=()):
    return dx.DXFExtraction(
        filename="desenho.dxf", blocks=[], walls=[], hatches=list(regioes), texts=list(textos), layers=[],
        dimensions=[], metadata=({MARCA: {"pares": 0, "m2": 0.0}} if marca else {}),
        polygon_areas=list(contornos))


def _secao(prompt):
    ls = prompt.splitlines()
    if CABECALHO not in ls:
        return None
    i = ls.index(CABECALHO)
    return ls[i + 2:ls.index("", i)]


TEXTOS = [_texto("SANIT.", 3, 3), _texto("SALA", 23, 3)]
REGIOES = [("ARQ-REVEST", 3.84, (2, 2, 4, 4), True), ("PISO", 16.0, (21, 1, 25, 5), False)]


def _regioes():
    return [_regiao(*r) for r in REGIOES]


def test_o_par_da_regiao_de_vista_sai_e_o_da_planta_fica():
    assert _secao(_extracao(TEXTOS, _regioes()).to_structured_prompt()) == [
        '  "SALA"  →  16.00 m²  (hachura no layer PISO)']


def test_CONTROLE_sem_a_marca_do_extrator_a_secao_e_a_de_hoje():
    assert _secao(_extracao(TEXTOS, _regioes(), marca=False).to_structured_prompt()) == [
        '  "SANIT."  →  3.84 m²  (hachura no layer ARQ-REVEST)',
        '  "SALA"  →  16.00 m²  (hachura no layer PISO)']


def test_CONTROLE_sem_regiao_de_vista_a_marca_nao_muda_nada():
    regs = [_regiao(l, a, c, False) for l, a, c, _v in REGIOES]
    com = _extracao(TEXTOS, regs).to_structured_prompt()
    assert _secao(com) == _secao(_extracao(TEXTOS, regs, marca=False).to_structured_prompt())
    assert len(_secao(com)) == 2


def test_quando_todo_par_e_de_vista_a_secao_nem_abre():
    so_vista = [_regiao("ARQ-REVEST", 3.84, (2, 2, 4, 4), True), _regiao("FACHADA", 16.0, (21, 1, 25, 5), True)]
    prompt = _extracao(TEXTOS, so_vista).to_structured_prompt()
    assert _secao(prompt) is None and "RÓTULO ↔ ÁREA" not in prompt
    assert _secao(_extracao(TEXTOS, so_vista, marca=False).to_structured_prompt()) is not None


def test_a_area_da_regiao_continua_no_prompt_com_o_aviso_de_vista():
    """Subtração só do PAR: a medida não some, e segue dita como vista de lado."""
    prompt = _extracao(TEXTOS, _regioes()).to_structured_prompt()
    da_area = [l for l in prompt.splitlines() if l.startswith("  ARQ-REVEST:")]
    assert len(da_area) == 1 and "3.84 m²" in da_area[0] and "DENTRO de corte/elevação" in da_area[0]


def test_o_texto_da_regiao_de_vista_nao_cai_na_regiao_maior_que_a_contem():
    """A região de vista está DENTRO de uma maior, que não é de vista: o texto
    é dela (a menor) e sai com ela — não vira rótulo da maior."""
    textos = [_texto("SANIT.", 3, 3)]
    regs = [_regiao("ARQ-REVEST", 3.84, (2, 2, 4, 4), True), _regiao("TERRENO", 400.0, (0, 0, 20, 20))]
    assert _secao(_extracao(textos, regs).to_structured_prompt()) is None
    # CONTROLE: sem a de vista na lista, o mesmo texto casaria com a maior
    assert [p["area"] for p in E.casar_texto_com_regiao(textos, regs[1:])] == [400.0]


def test_o_contorno_fechado_de_vista_tambem_sai():
    contornos = [dx.HatchArea(layer="PAINEL", area=6.0, pattern="contorno fechado", bbox=(2, 2, 4, 5),
                              preenchimento=1.0)]
    contornos[0].na_vista = True
    assert _secao(_extracao([_texto("SANIT.", 3, 3)], [], contornos=contornos).to_structured_prompt()) is None
    assert _secao(_extracao([_texto("SANIT.", 3, 3)], [], marca=False, contornos=contornos).to_structured_prompt()) == [
        '  "SANIT."  →  6.00 m²  (contorno fechado no layer PAINEL)']


def test_o_resto_nao_listado_conta_so_o_que_ficou():
    """O teto de 60 e o "(+N par(es) não listado(s))" valem pro que a seção lista."""
    textos, regs = [], []
    for i in range(65):                                   # 65 da planta
        textos.append(_texto("SALA %02d" % i, 100 + 10 * i + 1, 1))
        regs.append(_regiao("PISO", 10.0 + i, (100 + 10 * i, 0, 100 + 10 * i + 4, 4)))
    for i in range(7):                                    # 7 do corte
        textos.append(_texto("SANIT. %d" % i, 10 * i + 1, 51))
        regs.append(_regiao("ARQ-REVEST", 3.0 + i, (10 * i, 50, 10 * i + 2, 52), True))
    com = _secao(_extracao(textos, regs).to_structured_prompt())
    assert len(com) == 61 and com[-1] == "  (+5 par(es) não listado(s))"
    assert not [l for l in com if "SANIT." in l]
    sem = _secao(_extracao(textos, regs, marca=False).to_structured_prompt())
    assert sem[-1] == "  (+12 par(es) não listado(s))"


def test_a_marca_nao_sai_crua_nos_metadados_do_prompt():
    ex = _extracao(TEXTOS, _regioes())
    ex.metadata[MARCA] = {"pares": 7, "m2": 31.5}
    prompt = ex.to_structured_prompt()
    assert MARCA not in prompt and "31.5" not in prompt
    assert MARCA in dx.DXFExtraction._METADADOS_FORA_DO_PROMPT


# ── o rastro ────────────────────────────────────────────────────────────────
def test_o_rastro_conta_os_pares_de_vista_e_soma_a_area():
    regs = _regioes() + [_regiao("FACHADA", 25.22, (40, 0, 45, 5), True)]
    textos = TEXTOS + [_texto("P.MET.2", 42, 2)]
    assert dx.rotulo_em_vista_fora(textos, [], regs) == {"pares": 2, "m2": 29.06}


def test_a_soma_do_rastro_e_arredondada():
    """0,1 + 0,2 em ponto flutuante dá 0,30000000000000004: o registro leva 0,3."""
    regs = [_regiao("ARQ-REVEST", 0.1, (2, 2, 4, 4), True), _regiao("FACHADA", 0.2, (21, 1, 25, 5), True)]
    assert dx.rotulo_em_vista_fora(TEXTOS, [], regs) == {"pares": 2, "m2": 0.3}


def test_CONTROLE_o_rastro_sem_par_de_vista_e_zero():
    regs = [_regiao(l, a, c, False) for l, a, c, _v in REGIOES]
    assert dx.rotulo_em_vista_fora(TEXTOS, [], regs) == {"pares": 0, "m2": 0.0}
    assert dx.rotulo_em_vista_fora([], [], []) == {"pares": 0, "m2": 0.0}
    assert dx.rotulo_em_vista_fora(None, None, None) == {"pares": 0, "m2": 0.0}
    # o zero do registro é do mesmo tipo do resto (0.0, não 0)
    assert repr(dx.rotulo_em_vista_fora(TEXTOS, [], regs)) == "{'pares': 0, 'm2': 0.0}"


def test_a_etiqueta_solta_nao_entra_no_rastro_como_nao_entra_na_secao():
    """O rastro conta o MESMO par que a seção lista: o ATTDEF solto fica fora dos dois."""
    textos = [_texto("SANIT.", 3, 3, de_attdef=True)]
    regs = [_regiao("ARQ-REVEST", 3.84, (2, 2, 4, 4), True)]
    assert dx.rotulo_em_vista_fora(textos, [], regs) == {"pares": 0, "m2": 0.0}
    assert dx.pares_rotulo_regiao(textos, [], regs) == []
    assert _secao(_extracao(textos, regs, marca=False).to_structured_prompt()) is None


def test_o_rastro_nunca_levanta(caplog):
    class _Quebrado:
        @property
        def position(self):
            raise RuntimeError("texto quebrado")

    with caplog.at_level(logging.WARNING):
        assert dx.rotulo_em_vista_fora([_Quebrado()], [], _regioes()) == {"pares": 0, "m2": 0.0}
    assert [r for r in caplog.records if "rotulo_em_vista_fora" in r.getMessage()]


def test_CONTROLE_o_rastro_do_caso_comum_nao_avisa(caplog):
    with caplog.at_level(logging.WARNING):
        dx.rotulo_em_vista_fora(TEXTOS, [], _regioes())
        dx.rotulo_em_vista_fora(None, None, None)
    assert not [r for r in caplog.records if "rotulo_em_vista_fora" in r.getMessage()]


# ── da leitura por folha ao prompt ───────────────────────────────────────────
def test_a_marca_e_a_que_a_leitura_por_folha_poe():
    """Sem pôr a marca à mão: planta e corte no mesmo arquivo, e quem marca a
    região do corte é `aplicar_leitura_por_folha`."""
    mapa = {"folhas": [
        {"tipo": "vista", "titulo": "CORTE A-A", "caixa": (0, 0, 10, 10)},
        {"tipo": "vista", "titulo": "ELEVAÇÃO 1", "caixa": (20, 0, 30, 10)},
        {"tipo": "planta", "titulo": "PLANTA", "caixa": (40, 0, 50, 10), "andares": 1}]}
    hatches = [dx.HatchArea(layer="AZULEJO", area=9.0, bbox=(3, 3, 6, 6), preenchimento=1.0),
               dx.HatchArea(layer="REVEST", area=6.0, bbox=(24, 4, 26, 6), preenchimento=1.0),
               dx.HatchArea(layer="PISO", area=12.0, bbox=(42, 3, 46, 6), preenchimento=1.0)]
    walls = [dx.WallSegment(layer="PAR", length=7.0, start=(44.5, 5), end=(45.5, 5))]
    dx.aplicar_leitura_por_folha(walls, hatches, [], [], mapa)
    assert [bool(getattr(h, "na_vista", False)) for h in hatches] == [True, True, False]
    textos = [_texto("SANIT.", 4, 4), _texto("ACM", 25, 5), _texto("SALA", 44, 4)]
    assert dx.rotulo_em_vista_fora(textos, [], hatches) == {"pares": 2, "m2": 15.0}
    assert _secao(_extracao(textos, hatches).to_structured_prompt()) == [
        '  "SALA"  →  12.00 m²  (hachura no layer PISO)']
    assert len(_secao(_extracao(textos, hatches, marca=False).to_structured_prompt())) == 3


# ── do DXF ao prompt ─────────────────────────────────────────────────────────
def _hachura(msp, layer, x0, y0, w, h):
    hx = msp.add_hatch(dxfattribs={"layer": layer})
    hx.paths.add_polyline_path([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)], is_closed=True)


def _dxf(tmp_path, desenho="A_Corte AA_1_", nome="desenho.dxf", contorno=False):
    """Com `desenho` = prefixo do ArchiCAD de um corte, o arquivo inteiro é
    vista; com "" os mesmos layers são de uma planta comum."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    par, gc, esc, rev = (desenho + s for s in ("ARQ - Parede", "ARQ - Guarda-Corpo", "EST - Escada", "ARQ - Revestimento"))
    for n in (par, gc, esc, rev, "ARQ - Texto", desenho + "ARQ - Forro"):
        doc.layers.add(n)
    if contorno:                                          # um contorno FECHADO de 6 m², com o nome dentro
        msp.add_lwpolyline([(10, 4), (13, 4), (13, 6), (10, 6)], close=True, dxfattribs={"layer": desenho + "ARQ - Forro"})
        msp.add_text("COPA", height=0.25, dxfattribs={"layer": "ARQ - Texto"}).set_placement((11.0, 5.0))
    for y in (0.0, 3.0, 6.0, 9.0):
        msp.add_line((0, y), (20, y + 0.4), dxfattribs={"layer": par})
    for k in range(8):
        msp.add_line((2.5 * k, 10), (2.5 * k + 2.5, 11), dxfattribs={"layer": gc})
    for k in range(10):
        msp.add_line((22 + k, 0.3 * k), (23 + k, 0.3 * k + 0.3), dxfattribs={"layer": esc})
    _hachura(msp, rev, 2.0, 4.0, 4.0, 3.0)                # 12 m²
    msp.add_text("SANIT.", height=0.25, dxfattribs={"layer": "ARQ - Texto"}).set_placement((3.0, 5.0))
    p = str(tmp_path / nome)
    doc.saveas(p)
    return p


LINHA_DO_PAR = '  "SANIT."  →  12.00 m²  (hachura no layer %sARQ - Revestimento)'


def test_no_arquivo_de_corte_o_par_sai_e_o_rastro_vai_pro_registro(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        ex = dx.extract_dxf(_dxf(tmp_path))
    assert ex.folhas.get("aplicada") is True and ex.folhas["desenhos_lista"][0]["tipo"] == "vista"
    assert ex.metadata[MARCA] == {"pares": 1, "m2": 12.0}
    prompt = ex.to_structured_prompt()
    assert _secao(prompt) is None and '"SANIT."  →' not in prompt
    da_area = [l for l in prompt.splitlines() if l.strip().startswith("A_Corte AA_1_ARQ - Revestimento:")]
    assert da_area and all("DENTRO de corte/elevação" in l and "12.00 m²" in l for l in da_area), da_area
    log = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[rotulo-vista]")]
    assert log == ["[rotulo-vista] desenho.dxf: 1 par(es) RÓTULO ↔ ÁREA em região de corte/elevação "
                   "fora da seção (12.00 m²)"]


def test_no_arquivo_de_corte_o_contorno_fechado_sai_junto_com_a_hachura(tmp_path, monkeypatch):
    ex = dx.extract_dxf(_dxf(tmp_path, contorno=True))
    assert [(round(float(p.area), 2), bool(getattr(p, "na_vista", False))) for p in ex.polygon_areas] == [(6.0, True)]
    assert ex.metadata[MARCA] == {"pares": 2, "m2": 18.0}
    assert _secao(ex.to_structured_prompt()) is None
    # CONTROLE: com a chave em 0 os dois pares estão na seção
    monkeypatch.setenv(CHAVE, "0")
    sem = dx.extract_dxf(_dxf(tmp_path, nome="b.dxf", contorno=True))
    assert sorted(_secao(sem.to_structured_prompt())) == sorted([
        LINHA_DO_PAR % "A_Corte AA_1_", '  "COPA"  →  6.00 m²  (contorno fechado no layer A_Corte AA_1_ARQ - Forro)'])


def test_na_fachada_tambem(tmp_path):
    ex = dx.extract_dxf(_dxf(tmp_path, desenho="F_Fachada Sul_2_"))
    assert ex.metadata[MARCA] == {"pares": 1, "m2": 12.0} and _secao(ex.to_structured_prompt()) is None


def test_CONTROLE_com_a_chave_em_zero_o_corte_lista_o_par_como_hoje(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(CHAVE, "0")
    with caplog.at_level(logging.INFO):
        ex = dx.extract_dxf(_dxf(tmp_path))
    assert ex.folhas["desenhos_lista"][0]["tipo"] == "vista"
    assert MARCA not in ex.metadata
    assert _secao(ex.to_structured_prompt()) == [LINHA_DO_PAR % "A_Corte AA_1_"]
    assert not [r for r in caplog.records if r.getMessage().startswith("[rotulo-vista]")]


def test_CONTROLE_na_planta_o_par_fica_e_o_rastro_e_zero(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        ex = dx.extract_dxf(_dxf(tmp_path, desenho=""))
    assert not any(getattr(h, "na_vista", False) for h in ex.hatches)
    assert ex.metadata[MARCA] == {"pares": 0, "m2": 0.0}
    assert _secao(ex.to_structured_prompt()) == [LINHA_DO_PAR % ""]
    assert not [r for r in caplog.records if r.getMessage().startswith("[rotulo-vista]")]


def test_o_prompt_refeito_depois_sem_a_chave_no_ambiente_segue_a_marca(tmp_path, monkeypatch):
    """O prompt é refeito no servidor, onde a chave de uma avaliação não vale:
    quem decide é a marca que o extract_dxf deixou no registro."""
    ligada = dx.extract_dxf(_dxf(tmp_path, nome="a.dxf"))
    monkeypatch.setenv(CHAVE, "0")
    assert _secao(ligada.to_structured_prompt()) is None
    desligada = dx.extract_dxf(_dxf(tmp_path, nome="b.dxf"))
    monkeypatch.delenv(CHAVE)
    assert _secao(desligada.to_structured_prompt()) == [LINHA_DO_PAR % "A_Corte AA_1_"]


# ── o log e a chave ───────────────────────────────────────────────────────
def test_o_log_do_job_diz_quantos_pares_sairam():
    import main

    class _Ex:
        metadata = {MARCA: {"pares": 44, "m2": 187.9}}

    assert main._rotulo_em_vista_fora_resumo(_Ex()) == " | rotulo_em_vista_fora=[44 par(es) 187.9m2]"

    class _Zero:
        metadata = {MARCA: {"pares": 0, "m2": 0.0}}

    class _Sem:
        metadata = {}

    assert main._rotulo_em_vista_fora_resumo(_Zero()) == ""
    assert main._rotulo_em_vista_fora_resumo(_Sem()) == "" and main._rotulo_em_vista_fora_resumo(None) == ""
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    linha = fonte[fonte.index('"motor:parede-medida",\n                            "arq=%s layers_de_parede'):][:700]
    assert "_rotulo_em_vista_fora_resumo(extraction)" in linha and "topo: %s%s%s" in linha


def test_a_chave_e_lida_no_extrator_e_e_avaliavel():
    fonte = io.open(os.path.join(_BACKEND, "dwg_extractor.py"), encoding="utf-8").read()
    assert fonte.count('os.environ.get("%s"' % CHAVE) == 1
    import inspect
    assert CHAVE not in inspect.getsource(dx.DXFExtraction.to_structured_prompt).replace(
        "chave\n            # %s" % CHAVE, ""), "a chave é do extract_dxf; o prompt lê a MARCA"
    assert 'os.environ.get("%s"' % CHAVE in inspect.getsource(dx.extract_dxf)
    main = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    bloco = re.search(r"_CHAVES_AVALIAVEIS = frozenset\(\{(.*?)\}\)", main, re.S).group(1)
    assert '"%s"' % CHAVE in bloco
