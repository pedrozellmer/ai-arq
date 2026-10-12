# -*- coding: utf-8 -*-
"""O bloco do SÍMBOLO DE NÍVEL não é peça — pelo nome, lido do jeito certo.

🩸 12/10/2026 — "Marcadores de nível — 106 un", com a fonte "106 INSERTs do bloco"
do símbolo de nível da planta. O extrator já descartava bloco de anotação cujo
nome COMEÇA por NIVEL / NIV / LEVEL (sem acento, com separador); o símbolo
escapava por acento ("NÍVEL-PLANTA"), por falta de separador ("nivelcorte1"),
por prefixo de padrão ("XX-Nível Planta-1", "cota nível planta") e por ser a
família de cota de elevação do Revit, que nem tem "nível" no nome.
📏 Medido no acervo pelo motor (65 arquivos): 125 blocos, 1.982 inserções em 23
jobs contados como peça; lidos um a um, todos anotação.
🪤 O lado falso tem forma: o Revit exporta "<família> - <tipo>-<id>-<vista>", e
a VISTA muitas vezes se chama "Nível 1". Montante, pilar, vaga e piso
direcional com "nível" só na vista são PEÇA (730 blocos, 1.520 inserções no
acervo). A régua olha a família, não o nome inteiro. E "sensor de nível",
"chave de nível", "caixa…" continuam peça.

Todo caso de contagem passa pelo `extract_dxf` (um DXF sintético de verdade).
🪤 Nomes e siglas FICTÍCIOS, com a mesma forma dos medidos (repositório público).
"""
import io
import os
import re
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import dwg_extractor as dx  # noqa: E402

CHAVE = "SIMBOLO_DE_NIVEL_E_ANOTACAO"

SIMBOLO = [
    # começa por nível / níveis / niv / level — agora com acento, colado em número ou em corte/planta
    "NÍVEL", "Nível PB", "nível-planta", "nível_P", "NIVEL1", "NÍVEL2", "níveis corte fachada", "nivelcorte1",
    "NIVELPLANTA", "NIV", "niv 2", "nível-corte-direita",
    # "nível planta" / "nível corte" com prefixo de padrão
    "XPTO-Nível Planta-1", "XPTO-Nível Corte-1_050", "XPTO-Nível Planta-1_100-flat", "ZZ-SIMB-NÍVEL PLANTA",
    "ZZ-100-Nível Planta",                            # número curto entre hífens não é id do Revit: não corta o nome
    # cota (de) nível
    "COTA NÍVEL PLANTA", "cota nível corte", "cota de nível salas", "COTANIVEL", "L_CotaNível_PL_PA",
    "SIMBOLO_COTA NÍVEL_PLANTA", "SIMBOLO_COTA NIVÉL_CORTE",
    # símbolo … nível; indicação de nível; diferença de nível
    "ZZ_SMB_Nivel_Fake - Planta-13719740-PLANTA TÉRREO", "SÍMBOLO DE NÍVEL", "indicação nivel2", "INDICAÇÃO DE NÍVEL",
    "IND NÍVEL PB",
    "INDNIV-P", "DIFERENÇA DE NÍVEL - RETO_2",
    # as famílias do Revit: a cabeça de nível e a cota de elevação
    "Nível - Nível Acabado-377425-A", "Nível - Nível Osso-717611-Fachada Fundos",
    "Nível - M_Cabeça do nível - Círculo 2-395302-Corte AA", "Level - M_Level Head - Circle-24867-Corte BB",
    "Elevações de ponto - M_Cota de elevação - Alvo preenchido-123456-Planta Baixa",
    "Elevações de ponto - Nível Corte_Simples-90485-Corte 1", "Elevação de ponto - Corte-870094-Corte Longitudinal",
    "Spot Elevations - Planta-411685-PLANTA TÉRREO",
    "Coordenadas de ponto - M_Spot Elevation - Target Filled-55123-Nível 1",
]

PECA = [
    # "nível" só na VISTA do Revit (depois de -<id>- ou -V<n>-): é o pavimento, não o símbolo
    "Montante retangular - 3x5-2518207-Nível 1", "Montante retangular - 5x3 M1-V257-Nível 0",
    "Pilar estrutural - 15x40-2654842-Nível 2", "Piso direcional 25 - Piso direcional 25-V689-Nível 1",
    "Vaga padrão - 5,00 x 2,50 m-V12-Nível 1", "Paraciclo U - Paraciclo U-2081752-Nível 1",
    "Tomada - TS-110A-11418054-Planta de nível 2", "Painel - Vidro 16mm-3459667-Nível Corte",
    "Guarda-corpo - Vidro-2686-Nível Corte",          # id de 4 dígitos (medido: "…-2686-…")
    "Painel - Vidro-V18-Nível Corte AA",              # "V<n>": a cópia de vista
    # o instrumento e a peça que têm "nível" no nome
    "Instrumentos - Sensor de nível LSH-540123-Planta", "CHAVE DE NÍVEL", "CAIXA DE NÍVEL", "REGULADOR DE NÍVEL",
    "BOIA DE NÍVEL", "Pilar pré-moldado com 2 mísulas em nível - 40x40-9912345-Fôrma",
    # "niv" e "spot" de dentro de outra palavra
    "Cuba de embutir universal oval", "NIVELADOR", "NIVELAMENTO DE PISO", "Spot de embutir", "SPOT-01 - Spot-33881-Forro",
    "MASCOTA NÍVEL",                                  # "cota" de dentro de outra palavra não é cota de nível
    # o que a régua não reconhece continua como hoje
    "2º NÍVEL", "FP_3-NÍVEL", "A_NÍVEL", "DESNÍVEL", "DESNÍVEL PLANTA", "PORTA 80", "", None,
]


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.delenv(CHAVE, raising=False)


@pytest.mark.parametrize("nome", SIMBOLO)
def test_o_nome_e_de_simbolo_de_nivel(nome):
    assert dx.nome_de_simbolo_de_nivel(nome) is True, nome


@pytest.mark.parametrize("nome", PECA)
def test_CONTROLE_o_nome_nao_e_de_simbolo_de_nivel(nome):
    assert dx.nome_de_simbolo_de_nivel(nome) is False, nome


def test_a_regua_olha_a_familia_do_revit_nao_a_vista():
    """O mesmo "Nível 1" no fim do nome: símbolo quando a FAMÍLIA é a de nível,
    peça quando a família é outra."""
    assert dx.nome_de_simbolo_de_nivel("Nível - Nível Acabado-377425-Nível 1")
    assert not dx.nome_de_simbolo_de_nivel("Guarda-corpo - Vidro-377425-Nível 1")
    # o id pode vir como "V<n>" (cópia de vista) e a vista pode ter hífen
    assert dx.nome_de_simbolo_de_nivel("Elevações de ponto - Corte-V51-Corte 3D - Demolição")
    assert not dx.nome_de_simbolo_de_nivel("Montante - 3x3-V255-Nível 1 - Cópia")
    assert not dx.nome_de_simbolo_de_nivel("Luminária - Plafon-204897-Cota de nível do forro")


# ── do DXF à contagem ────────────────────────────────────────────────────────

_BLOCOS = [("XPTO-Nível Planta-1", 5), ("Nível - Nível Acabado-377425-A", 2), ("COTA NÍVEL PLANTA", 3),
           ("NIVEL PB", 2),                                            # este o guarda antigo já tirava
           ("PORTA 80", 3), ("Montante retangular - 3x5-2518207-Nível 1", 4), ("CHAVE DE NÍVEL", 2)]


def _dxf(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True, dxfattribs={"layer": "ARQ-PAREDE"})
    for k, (nome, n) in enumerate(_BLOCOS):
        b = doc.blocks.new(name=nome)
        b.add_circle((0, 0), 0.15)
        b.add_line((-0.3, 0), (0.3, 0))
        b.add_line((0, -0.3), (0, 0.3))
        b.add_lwpolyline([(0, 0), (0.2, 0.2), (0.4, 0)])
        for i in range(n):
            msp.add_blockref(nome, (2 + 3 * i, 2 + 2 * k), dxfattribs={"layer": "ARQ-SIMB"})
    p = str(tmp_path / "niveis.dxf")
    doc.saveas(p)
    return p


def _contagem(ex):
    return {b.name: b.count for b in ex.blocks}


def test_o_simbolo_de_nivel_sai_da_contagem_e_a_peca_fica(tmp_path):
    ex = dx.extract_dxf(_dxf(tmp_path))
    assert _contagem(ex) == {"PORTA 80": 3, "Montante retangular - 3x5-2518207-Nível 1": 4, "CHAVE DE NÍVEL": 2}
    assert ex.blocos_descartados["anotacao"] == 5 + 2 + 3 + 2          # o descarte é CONTADO, não calado
    p = ex.to_structured_prompt()
    assert "XPTO-Nível Planta" not in p and "COTA NÍVEL PLANTA" not in p and "Nível Acabado" not in p
    assert "PORTA 80" in p and "CHAVE DE NÍVEL" in p


def test_CONTROLE_com_a_chave_em_zero_e_como_hoje(tmp_path, monkeypatch):
    monkeypatch.setenv(CHAVE, "0")
    ex = dx.extract_dxf(_dxf(tmp_path))
    c = _contagem(ex)
    assert c == {n: k for n, k in _BLOCOS if n != "NIVEL PB"}           # só o que o guarda antigo já tirava
    assert ex.blocos_descartados["anotacao"] == 2
    assert "XPTO-Nível Planta-1" in ex.to_structured_prompt()


def test_o_que_nao_e_bloco_de_nivel_nao_muda_com_a_chave(tmp_path, monkeypatch):
    com = dx.extract_dxf(_dxf(tmp_path))
    monkeypatch.setenv(CHAVE, "0")
    sem = dx.extract_dxf(_dxf(tmp_path))
    c_com, c_sem = _contagem(com), _contagem(sem)
    assert all(c_sem[n] == k for n, k in c_com.items())
    assert set(c_sem) - set(c_com) == {"XPTO-Nível Planta-1", "Nível - Nível Acabado-377425-A", "COTA NÍVEL PLANTA"}
    assert len(com.walls) == len(sem.walls) and len(com.texts) == len(sem.texts)


def test_a_chave_e_lida_no_extrator_e_e_avaliavel():
    fonte = io.open(os.path.join(_BACKEND, "dwg_extractor.py"), encoding="utf-8").read()
    assert fonte.count('os.environ.get("%s"' % CHAVE) == 1
    main = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    bloco = re.search(r"_CHAVES_AVALIAVEIS = frozenset\(\{(.*?)\}\)", main, re.S).group(1)
    assert '"%s"' % CHAVE in bloco
