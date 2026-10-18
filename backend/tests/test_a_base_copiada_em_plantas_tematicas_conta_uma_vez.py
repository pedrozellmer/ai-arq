# -*- coding: utf-8 -*-
"""A base de arquitetura copiada em plantas temáticas do mesmo andar conta UMA vez.

🩸 18/10/2026 — elétrico de galpão: a planta de iluminação e a de força do mesmo
pavimento trazem, cada uma, a base de arquitetura explodida: cadeiras e vasos
saíam em dobro. O registro de cópias achava o vetor exato, mas só
rebaixava o selo. O que separa "temas do mesmo andar" de "andares repetidos": os
símbolos que NÃO se copiam moram cada um de um lado (tomada só na de força,
luminária só na de iluminação). Medido em 12 arquivos de cliente: ≥ 0,91 nos de
plantas temáticas; ≤ 0,71 nos legítimos (duas unidades lado a lado, fachada em
módulo). Chave BASE_COPIADA_UMA_VEZ, padrão desligada.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import main  # noqa: E402

CHAVE = "BASE_COPIADA_UMA_VEZ"
V = 40.0                                         # a planta B é a A deslocada 40 m em x
MOVEIS = ["CADEIRA", "MESA", "ARMARIO", "VASO", "PIA", "SOFA"]


def _base(dx0):
    """6 tipos de móvel × 4 peças, numa planta de 20 × 10 m a partir de dx0."""
    out = {}
    for k, nome in enumerate(MOVEIS):
        out[nome] = [(dx0 + 2 + 3 * k, 2 + 2 * j) for j in range(4)]
    return out


def _blocos(tema_a, tema_b, nome_a="TOMADA", nome_b="LUMINARIA"):
    pos = {}
    for d in (_base(0.0), _base(V)):
        for n, ps in d.items():
            pos.setdefault(n, []).extend(ps)
    if tema_a:
        pos.setdefault(nome_a, []).extend((1 + 0.9 * i, 5.0) for i in range(tema_a))
    if tema_b:
        pos.setdefault(nome_b, []).extend((V + 1 + 0.9 * i, 5.5) for i in range(tema_b))
    return [dx.BlockCount(name=n, count=len(ps), layer="L", positions=list(ps)) for n, ps in pos.items()]


def _conta(blocos):
    return {b.name: b.count for b in blocos}


_COPIAS = {"pecas": 24, "vetores": [[V, 0.0, 24, 6, MOVEIS[:3]]]}


def test_o_caso_temas_do_mesmo_andar_a_base_conta_uma_vez():
    bl = _blocos(tema_a=15, tema_b=15)
    r = dx.base_copiada_em_plantas_tematicas(bl, _COPIAS, 1.0)
    c = _conta(bl)
    assert r["aplicada"] is True and r["pecas"] == 24, r
    assert all(c[n] == 4 for n in MOVEIS), c
    assert c["TOMADA"] == 15 and c["LUMINARIA"] == 15, c          # o tema de cada planta fica inteiro
    cad = next(b for b in bl if b.name == "CADEIRA")
    assert all(p[0] < V for p in cad.positions), cad.positions     # fica a do original; sai a de p + v


@pytest.mark.parametrize("por_lado,ok", [(9, False), (10, True)])
def test_o_minimo_de_simbolos_fora_da_copia(por_lado, ok):
    """Cada lado com o seu tema (≥ 5), mas 18 símbolos no total ainda não provam."""
    bl = _blocos(tema_a=por_lado, tema_b=por_lado)
    assert dx.base_copiada_em_plantas_tematicas(bl, _COPIAS, 1.0)["aplicada"] is ok


def test_CONTROLE_andares_repetidos_tudo_conta():
    """Os dois lados têm tomada E luminária: é outro andar, não outro tema."""
    bl = _blocos(tema_a=0, tema_b=0)
    extra = []
    for dx0 in (0.0, V):
        extra.append(dx.BlockCount(name="TOMADA", count=8, layer="L",
                                   positions=[(dx0 + 1 + 0.9 * i, 5.0) for i in range(8)]))
        extra.append(dx.BlockCount(name="LUMINARIA", count=8, layer="L",
                                   positions=[(dx0 + 1 + 0.9 * i, 5.6) for i in range(8)]))
    bl += extra
    r = dx.base_copiada_em_plantas_tematicas(bl, _COPIAS, 1.0)
    assert r["aplicada"] is False, r
    assert sum(b.count for b in bl if b.name == "CADEIRA") == 8


def test_CONTROLE_planta_inteira_repetida_sem_tema_nada_sai():
    bl = _blocos(tema_a=2, tema_b=2)
    r = dx.base_copiada_em_plantas_tematicas(bl, _COPIAS, 1.0)
    assert r["aplicada"] is False, r
    assert _conta(bl)["CADEIRA"] == 8


def test_CONTROLE_tema_so_de_um_lado_nao_basta():
    """Exclusividade alta mas a outra planta não tem tema nenhum: não prova 'outro tema'."""
    bl = _blocos(tema_a=30, tema_b=0)
    r = dx.base_copiada_em_plantas_tematicas(bl, _COPIAS, 1.0)
    assert r["aplicada"] is False, r


def test_CONTROLE_no_revit_compara_a_familia_e_nao_o_nome():
    """Revit: cada peça com número próprio. Com o nome cru, todo tipo seria 'exclusivo'."""
    bl = _blocos(tema_a=0, tema_b=0)
    for dx0, vista in ((0.0, "PLANTA A"), (V, "PLANTA B")):
        for i in range(12):
            # a forma do export do Revit: família - tipo-NÚMERO DA PEÇA-VISTA
            nome = "Rectangular Mullion - AL00_L050_A050-%d-%s" % (14055630 + i + int(dx0), vista)
            bl.append(dx.BlockCount(name=nome, count=1, layer="L", positions=[(dx0 + 1 + 1.5 * i, 5.0)]))
    r = dx.base_copiada_em_plantas_tematicas(bl, _COPIAS, 1.0)
    assert r["aplicada"] is False, r


def test_CONTROLE_sem_vetor_provado_nada_acontece():
    bl = _blocos(tema_a=15, tema_b=15)
    assert dx.base_copiada_em_plantas_tematicas(bl, {}, 1.0)["aplicada"] is False
    assert _conta(bl)["CADEIRA"] == 8


@pytest.mark.parametrize("pares,ok", [(9, False), (10, True)])
def test_o_minimo_de_pares(pares, ok):
    bl = []
    for k in range(pares):
        bl.append(dx.BlockCount(name="M%d" % k, count=2, layer="L", positions=[(1 + 1.5 * k, 2 + 6 * (k % 2)), (V + 1 + 1.5 * k, 2 + 6 * (k % 2))]))
    bl.append(dx.BlockCount(name="TOMADA", count=12, layer="L", positions=[(1 + 1.2 * i, 5) for i in range(12)]))
    bl.append(dx.BlockCount(name="LUMINARIA", count=12, layer="L", positions=[(V + 1 + 1.2 * i, 5) for i in range(12)]))
    r = dx.base_copiada_em_plantas_tematicas(bl, {"vetores": [[V, 0.0]]}, 1.0)
    assert r["aplicada"] is ok, r


# ── de ponta a ponta: o arquivo, o registro de cópias e a chave ────────────────
def _arquivo(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for nome in MOVEIS + ["TOMADA", "LUMINARIA"]:
        b = doc.blocks.new(nome)
        b.add_circle((0, 0), 0.2)
    for dx0 in (0.0, V):
        for n, ps in _base(dx0).items():
            for p in ps:
                msp.add_blockref(n, p)
        msp.add_lwpolyline([(dx0, 0), (dx0 + 20, 0), (dx0 + 20, 12), (dx0, 12)], close=True,
                           dxfattribs={"layer": "PAREDE"})
    for i in range(15):
        msp.add_blockref("TOMADA", (1 + 0.9 * i, 5.0))
        msp.add_blockref("LUMINARIA", (V + 1 + 0.9 * i, 5.5))
    p = str(tmp_path / "ilum_forca.dxf")
    doc.saveas(p)
    return p


@pytest.fixture
def _sem_chave(monkeypatch):
    monkeypatch.delenv(CHAVE, raising=False)


def test_ponta_a_ponta_com_a_chave_ligada(tmp_path, monkeypatch):
    monkeypatch.setenv(CHAVE, "1")
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert (ex.metadata.get("copias_sombra") or {}).get("vetores"), ex.metadata.get("copias_sombra")
    c = _conta(ex.blocks)
    assert c.get("CADEIRA") == 4 and c.get("TOMADA") == 15 and c.get("LUMINARIA") == 15, c
    assert ex.metadata["base_em_plantas_tematicas"]["aplicada"] is True
    assert "base_em_plantas_tematicas" not in ex.to_structured_prompt()


def test_CONTROLE_ponta_a_ponta_com_a_chave_desligada_e_como_era(tmp_path, _sem_chave):
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert _conta(ex.blocks).get("CADEIRA") == 8
    assert "base_em_plantas_tematicas" not in ex.metadata


def test_a_chave_e_avaliavel_e_desligada_por_padrao():
    assert CHAVE in main._CHAVES_AVALIAVEIS
    with open(dx.__file__, encoding="utf-8") as f:
        assert 'os.environ.get("%s", "0") == "1"' % CHAVE in f.read()


def test_a_planilha_diz_o_que_contou_uma_vez():
    arqs = [{"nome": "ELE-02", "base_em_plantas_tematicas": {
        "aplicada": True, "pecas": 123, "nomes": {"cadeira fixa": 37, "armario alto": 21}}}]
    linhas = main._linhas_fora_das_pranchas(arqs)
    assert len(linhas) == 1 and "contadas uma vez" in linhas[0] and "123 peça(s)" in linhas[0], linhas
    assert "cadeira fixa 37" in linhas[0], linhas
