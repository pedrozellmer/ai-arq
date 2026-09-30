# -*- coding: utf-8 -*-
"""A planta repetida no modelo SÓ REBAIXA: contagem do tipo copiado e m/m²/m³.

🩸 29/09/2026 (job 6437838e). DWG elétrico com a planta-base desenhada 5 vezes
no modelo, uma por prancha de disciplina: pia 10 (real 2), bacia 10 (2), vaga
PNE 5 (1)… e, com a unidade certa, as cotas provavam a escala — a contagem
inflada saía ✓ MEDIDO, e o layer da eletrocalha virava 6.428 m. Pedro, 29/09:
subir o detector de planta repetida (D1, em sombra desde 28/09) só REBAIXANDO —
nenhum número muda.
"""
import ast
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
from dwg_extractor import BlockCount, copias_em_sombra, tipos_nas_copias  # noqa: E402

# a planta-base (6 tipos, como no teste do D1) e um símbolo que mora numa vista só
PLANTA = {
    "PIA-P": [(1.0, 1.0), (4.0, 2.5)],
    "BACIAAC": [(0.5, 6.0), (7.0, 9.0)],
    "VOG13": [(3.0, 3.0), (6.0, 3.0), (9.0, 8.0)],
    "vaga PNE": [(2.0, 9.5)],
    "Asta con bandera T3 - Planta-flat-1-flat-1": [(10.5, 9.5)],
    "PONTO-TV": [(8.0, 1.5), (2.5, 5.0), (11.5, 6.0)],
    "QUADRO": [(0.2, 0.2), (5.5, 8.5)],
}
V1, V2 = (128.65, 0.0), (0.0, -82.9)
VISTAS = [(0, 0), V1, (2 * V1[0], 0.0), V2, (V1[0], V2[1])]
AMBAR = [(20.0 + 2.5 * i, 20.0 + 2.4 * j) for i in range(7) for j in range(10)]   # 70, só na 1ª


def _blocos():
    pos = {n: [] for n in PLANTA}
    for vx, vy in VISTAS:
        for n, ps in PLANTA.items():
            pos[n] += [(x + vx, y + vy) for x, y in ps]
    pos["AMBAR"] = list(AMBAR)
    return [BlockCount(name=n, count=len(ps), layer="0", positions=ps) for n, ps in pos.items()]


def _resumo(blocos):
    return {b.name: b.count for b in blocos}


# ══════════════════════════════════════════════════════════════════════════
#  1. Quem está nas cópias
# ══════════════════════════════════════════════════════════════════════════
def test_o_detector_acha_as_copias_e_a_segunda_passada_acha_os_tipos_de_1_peca():
    blocos = _blocos()
    c = copias_em_sombra(blocos, 1.0)
    assert c and c.get("vetores"), c
    tipos = tipos_nas_copias(blocos, c["vetores"], 1.0)
    for n in PLANTA:
        assert n in tipos, (n, tipos)
    assert "AMBAR" not in tipos, "o símbolo da disciplina mora numa vista só"


def test_a_segunda_passada_nao_inventa_vetor():
    blocos = _blocos()
    assert tipos_nas_copias(blocos, [], 1.0) == {}
    assert tipos_nas_copias(blocos, None, 1.0) == {}


def test_a_segunda_passada_tem_a_tolerancia_do_detector():
    """Peça a 6 cm do ponto da cópia não é cópia (a tolerância é 5 cm)."""
    b = [BlockCount(name="X", count=2, layer="0", positions=[(0.0, 0.0), (10.06, 0.0)])]
    assert tipos_nas_copias(b, [[10.0, 0.0]], 1.0) == {}
    b = [BlockCount(name="X", count=2, layer="0", positions=[(0.0, 0.0), (10.03, 0.0)])]
    assert tipos_nas_copias(b, [[10.0, 0.0]], 1.0) == {"X": 1}


def test_a_segunda_passada_trabalha_em_metros():
    """O vetor vem em metros; as posições, em unidade do desenho (aqui, cm)."""
    b = [BlockCount(name="X", count=2, layer="0", positions=[(0.0, 0.0), (1000.0, 0.0)])]
    assert tipos_nas_copias(b, [[10.0, 0.0]], 0.01) == {"X": 1}


def test_a_copia_na_soma_e_no_dobro_dos_vetores():
    b = [BlockCount(name="D", count=2, layer="0", positions=[(0.0, 0.0), (V1[0], V2[1])]),
         BlockCount(name="E", count=2, layer="0", positions=[(0.0, 0.0), (2 * V1[0], 0.0)])]
    t = tipos_nas_copias(b, [list(V1), list(V2)], 1.0)
    assert set(t) == {"D", "E"}, t


def _dxf_da_planta_repetida(caminho):
    import ezdxf
    d = ezdxf.new("R2010")
    d.header["$INSUNITS"] = 6                     # metros
    msp = d.modelspace()
    for n in list(PLANTA) + ["AMBAR"]:
        blk = d.blocks.new(name=n)
        blk.add_lwpolyline([(0, 0), (0.4, 0), (0.4, 0.4), (0, 0.4)], close=True)
    for vx, vy in VISTAS:
        for n, ps in PLANTA.items():
            for x, y in ps:
                msp.add_blockref(n, (x + vx, y + vy))
    for x, y in AMBAR:
        msp.add_blockref("AMBAR", (x, y))
    d.saveas(caminho)


def test_de_ponta_a_ponta_a_extracao_marca_a_planta_repetida(tmp_path):
    import dwg_extractor as dx
    p = str(tmp_path / "eletrico.dxf")
    _dxf_da_planta_repetida(p)
    md = dx.extract_dxf(p).metadata
    tipos = (md.get("copias_sombra") or {}).get("tipos_copiados") or {}
    assert "vaga PNE" in tipos, "a 2ª passada não pegou o tipo de 1 peça por cópia: %r" % tipos
    assert "PIA-P" in tipos and "AMBAR" not in tipos, tipos
    assert md.get("planta_repetida"), sorted(md)
    assert er.caveat_atinge_unidade(md, "m") is True
    assert er.caveat_atinge_unidade(md, "un") is False


def test_a_extracao_junta_a_segunda_passada_na_lista_do_rebaixamento(tmp_path, monkeypatch):
    """No caso real a 2ª passada achou 13 tipos que o detector deixou de fora;
    no sintético o detector já acha todos — então a ligação se prova assim."""
    import dwg_extractor as dx
    p = str(tmp_path / "eletrico.dxf")
    _dxf_da_planta_repetida(p)
    monkeypatch.setattr(dx, "tipos_nas_copias", lambda *a, **k: {"SENTINELA": 7})
    tipos = (dx.extract_dxf(p).metadata.get("copias_sombra") or {}).get("tipos_copiados") or {}
    assert tipos.get("SENTINELA") == 7, tipos
    assert "PIA-P" in tipos, "a lista do detector tem de continuar lá"


# ══════════════════════════════════════════════════════════════════════════
#  2. O selo — só rebaixa, e só o tipo copiado
# ══════════════════════════════════════════════════════════════════════════
COPIADOS = set(PLANTA)
BLOCOS = _resumo(_blocos())


@pytest.mark.parametrize("citado, n", [
    ("PIA-P", 10), ("BACIAAC", 10), ("VOG13", 15), ("vaga PNE", 5),
    ("Asta con bandera T3", 5),          # a RAIZ que o prompt mostra à IA
])
def test_a_contagem_do_tipo_copiado_sai_laranja(citado, n):
    obs = "Fonte: %d INSERTs do bloco '%s' em CONTAGEM DE BLOCOS." % (n, citado)
    conf, nova, mexeu = er.selo_apos_planta_repetida("confirmado", obs, n, "un", COPIADOS, BLOCOS)
    assert (conf, mexeu) == ("estimado", True), (citado, nova)
    assert nova.startswith(er.MARCA_PLANTA_REPETIDA)
    assert "a contagem pode somar" in nova[:110], "o essencial tem de caber no que a tela mostra"
    assert nova.endswith(obs), "a observação da IA fica inteira"


def test_o_simbolo_que_mora_numa_vista_so_continua_medido():
    obs = "Fonte: 70 INSERTs do bloco 'AMBAR' em CONTAGEM DE BLOCOS."
    assert er.selo_apos_planta_repetida("confirmado", obs, 70, "un", COPIADOS, BLOCOS) == (
        "confirmado", obs, False)


def test_o_bloco_citado_de_passagem_nao_rebaixa():
    """A fonte é o AMBAR; a pia citada depois, com o mesmo número, não conta."""
    blocos = dict(BLOCOS, AMBAR=10)
    obs = "Fonte: 10 INSERTs do bloco 'AMBAR'. Perto da pia (bloco 'PIA-P')."
    assert er.selo_apos_planta_repetida("confirmado", obs, 10, "un", COPIADOS, blocos)[2] is False


@pytest.mark.parametrize("conf, q, unit, copiados", [
    ("estimado", 10, "un", COPIADOS),      # já está laranja
    ("confirmado", 2, "un", COPIADOS),     # a IA já dividiu: não é a contagem
    ("confirmado", 10, "m", COPIADOS),     # não é contagem
    ("confirmado", 10, "un", set()),       # não há planta repetida
])
def test_CONTROLE_o_que_nao_e_contagem_do_copiado_fica(conf, q, unit, copiados):
    obs = "Fonte: 10 INSERTs do bloco 'PIA-P'."
    assert er.selo_apos_planta_repetida(conf, obs, q, unit, copiados, BLOCOS) == (conf, obs, False)


def test_a_marca_esta_nas_marcas_de_rebaixamento():
    """Sem isto, a chave do selo promove de volta o que a regra rebaixou."""
    assert er.MARCA_PLANTA_REPETIDA in er.MARCAS_DE_REBAIXAMENTO


# ══════════════════════════════════════════════════════════════════════════
#  3. Comprimento e área: ressalva de escala
# ══════════════════════════════════════════════════════════════════════════
def test_a_ressalva_rebaixa_metro_e_nao_contagem():
    txt = er.ressalva_da_planta_repetida({"pecas": 122, "vetores": [[0, 82.9, 82, 20, []]]})
    assert "repetida" in txt and "122" in txt
    md = {"planta_repetida": txt}
    assert er.extraction_has_quality_caveat(md) is True
    for u in ("m", "ml", "m²", "m³"):
        assert er.caveat_atinge_unidade(md, u) is True, u
    for u in ("un", "kg", "vb"):
        assert er.caveat_atinge_unidade(md, u) is False, u


@pytest.mark.parametrize("cop", [None, {}, {"pecas": 0, "vetores": []}, {"pecas": 5}])
def test_CONTROLE_sem_copia_sem_ressalva(cop):
    assert er.ressalva_da_planta_repetida(cop) == ""


# ══════════════════════════════════════════════════════════════════════════
#  4. A raiz do nome: uma receita só
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("nome, raiz", [
    ("Asta con bandera T3 - Planta-flat-1-flat-1", "Asta con bandera T3"),
    ("Viga_12_1", "Viga"), ("Hebebuehne_5", "Hebebuehne"),
    ("carregador externo-flat-1-flat-1", "carregador externo-flat-1-flat-1"),
    ("PIA-P", "PIA-P"), ("", ""),
])
def test_a_raiz_do_nome(nome, raiz):
    assert er.raiz_do_nome_do_bloco(nome) == raiz


def _fonte(nome):
    return io.open(os.path.join(os.path.dirname(_AQUI), nome), encoding="utf-8").read()


def _funcoes(arv):
    return {n.name: n for n in ast.walk(arv)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_o_prompt_usa_a_mesma_receita_da_raiz():
    arv = ast.parse(_fonte("dwg_extractor.py"))
    fn = _funcoes(arv)["to_structured_prompt"]
    chamadas = {getattr(c.func, "id", "") for c in ast.walk(fn) if isinstance(c, ast.Call)}
    assert "_raiz_bloco" in chamadas, "o prompt voltou a ter a própria receita da raiz"


# ══════════════════════════════════════════════════════════════════════════
#  5. O motor aplica — no lugar certo
# ══════════════════════════════════════════════════════════════════════════
def _lista_que_contem(fn, no):
    for pai in ast.walk(fn):
        for campo in ("body", "orelse", "finalbody"):
            lista = getattr(pai, campo, None)
            if isinstance(lista, list) and no in lista:
                return lista
    return None


def test_o_motor_rebaixa_logo_depois_da_regra_da_legenda():
    fn = _funcoes(ast.parse(_fonte("main.py")))["process_job"]
    ch = lambda nome: [n for n in ast.walk(fn) if isinstance(n, ast.Assign)  # noqa: E731
                       and isinstance(n.value, ast.Call)
                       and getattr(n.value.func, "id", "") == nome]
    copias, legenda = ch("_regra_copias"), ch("_regra_amostra")
    assert len(copias) == 1 and len(legenda) == 1
    args = [getattr(a, "id", None) for a in copias[0].value.args]
    assert args == ["conf", "obs_raw", "qty", "normalized_unit", "_blocos_copiados",
                    "_blocos_n"], args
    lista = _lista_que_contem(fn, copias[0])
    assert lista is not None and legenda[0] in lista, "a regra ficou atrás de um `if`"
    assert lista.index(legenda[0]) < lista.index(copias[0])
    ramos = [n for n in lista if isinstance(n, ast.If) and getattr(n.test, "id", "") == "_era_copia"]
    assert ramos and any(isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") ==
                         "_rebaixado_pela_fonte" for x in ast.walk(ramos[0]))


def test_a_chave_do_selo_nao_sobe_a_contagem_do_tipo_copiado():
    """O índice da chave pula o tipo copiado — senão ela promove de volta."""
    fn = _funcoes(ast.parse(_fonte("main.py")))["process_job"]
    achou = False
    for f in ast.walk(fn):
        if not isinstance(f, ast.For):
            continue
        nomes = {getattr(x, "id", None) for x in ast.walk(f.target)}
        if "_blk" not in nomes:
            continue
        pula = [s for s in f.body if isinstance(s, ast.If)
                and "_copiados_ig" in {getattr(x, "id", None) for x in ast.walk(s.test)}
                and any(isinstance(y, ast.Continue) for y in s.body)]
        achou = achou or bool(pula)
    assert achou, "a chave do selo voltou a indexar a contagem do tipo copiado"
