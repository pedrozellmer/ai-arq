# -*- coding: utf-8 -*-
"""A linha lida FORA da prancha dona da sua disciplina é repetição — e sai.

🩸 24/09/2026, "Regina e Ronaldo" (job b6df4f3d, 6 pranchas DTZ): o piso saiu
por ambiente lido na planta de PONTOS (28,7 m²) e de novo como porcelanato na
planta de PISO; o forro, 28,7 m² na PONTOS e 36 m² na FORRO.

🧪 Os controles vêm da SIMULAÇÃO em 90 dias de dados reais: a regra larga
tirava 274 linhas de 19 projetos, muitas legítimas. Cada controle abaixo é um
desses casos, com o nome de prancha REAL. A regra final tira 11 linhas de 3
projetos, todas conferidas à mão.
"""
import ast
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from engine_rules import (  # noqa: E402
    andar_da_prancha,
    disciplinas_da_prancha,
    familia_do_item,
    repetidos_entre_pranchas as repetidos,
)


def _it(ref, disc, desc):
    return {"ref_sheet": ref, "discipline": disc, "description": desc}


PISO = "1026.ARR.600.PISO.00.dxf"
FORRO = "1026.ARR.700.FORRO.00.dxf"
PONTOS = "1026.ARR.500.PONTOS.00.dxf"
LAYOUT = "1026.ARR.200.LAYOUT.00.dxf"


# ── nomes reais: quem é dono de quê, e de que andar ────────────────────────
@pytest.mark.parametrize("nome, donas, andar", [
    (PISO, {"piso"}, ""),
    (FORRO, {"forro"}, ""),
    (PONTOS, set(), ""),
    ("PROJETO 10 - PLANTA DE PISO - 1O PISO_LIBREDWG", {"piso"}, "1PAV"),
    ("FORMA.PDF (PRANCHA PISO 2 — FÔRMAS)", set(), "2PAV"),
    ("VIGA.PDF (PISO 1 — DESENHO DE VIGAS)", set(), "1PAV"),
    ("08.18_P PISO_LUANA_09.04.PDF (08/18 — PLAN", {"piso"}, ""),
    ("11.18_P RODAPE_LUANA_09.04.PDF", {"rodape"}, ""),
    ("CC_AP_PAGINACAO TERREO_R00.PDF", {"piso"}, "TERREO"),
    ("CC_AP_FORRO E CLIMATIZACAO 1O PAV._R00.PDF", {"forro"}, "1PAV"),
    ("KFC-ITU-ARQ-EXE-R03-FL04-PLANTA DE PISOS_1", {"piso"}, ""),
    ("2600575-01-BRA-PRIN-MACAE-EXE-04-PIS-R02.PDF", {"piso"}, ""),
    ("03-PISCINA_ARQUITETONICO_PRANCHA-11-12.PDF", set(), ""),
    ("MEMORIAL DESCRITIVO RESIDENCIAL CONDOMINIO (PISOS)", set(), ""),
    ("RA-BVAR (Prancha 5 — Planta de Demolição Forro 2º Pav)", set(), "2PAV"),
])
def test_a_prancha_pelo_nome(nome, donas, andar):
    assert disciplinas_da_prancha(nome) == donas
    assert andar_da_prancha(nome) == andar


# ── o caso real: sai o que a planta de PONTOS repetiu ──────────────────────
def _projeto_dtz():
    return [
        _it(PISO, "Pisos e Rodapés", "Porcelanato Portobello Posto 12 — 28,39 m²"),
        _it(PISO, "Pisos e Rodapés", "Piso vinílico — 1,73 m²"),
        _it(FORRO, "Forros", "Forro em gesso acartonado novo"),
        _it(PONTOS, "Pisos e Rodapés", "Piso — Sala — especificação a definir"),
        _it(PONTOS, "Pisos e Rodapés", "Piso — Quarto — especificação a definir"),
        _it(PONTOS, "Forros", "Forro — especificação a definir conforme memorial"),
        _it(PONTOS, "Instalações Elétricas e Dados", "Tomada baixa — 16 un"),
    ]


def test_o_caso_DTZ_tira_o_piso_e_o_forro_da_planta_de_pontos():
    itens = _projeto_dtz()
    fora, det = repetidos(itens)
    assert fora == {3, 4, 5}, det
    assert all(d["de"] == PONTOS for d in det)


def test_a_tomada_da_planta_de_pontos_NUNCA_sai():
    fora, _ = repetidos(_projeto_dtz())
    assert 6 not in fora


# ── controles: cada um é um falso positivo que a simulação achou ──────────
def test_CONTROLE_sem_prancha_dona_nada_sai():
    itens = [_it(PONTOS, "Pisos e Rodapés", "Piso — Sala"),
             _it(LAYOUT, "Forros", "Forro de gesso")]
    assert repetidos(itens) == (set(), [])


def test_CONTROLE_planta_baixa_e_detalhe_nao_sao_outra_disciplina():
    """Piso da copa no DETALHE e piso tátil da ACESSIBILIDADE são legítimos."""
    itens = [_it("13-24 PROJ ARQ - PAGINACAO GERAL FORRO E PISO", "Pisos e Rodapés", "Piso cerâmico geral"),
             _it("18-24 PROJ ARQ - DET COPA BANCADAS", "Pisos e Rodapés", "Piso cerâmico da copa"),
             _it("14-24 PROJ ARQ - ACESSIBILIDADE", "Pisos e Rodapés", "Piso tátil direcional"),
             _it("ARQ04 - PLANTA BAIXA - TERREO", "Pisos e Rodapés", "Piso cerâmico do salão")]
    assert repetidos(itens)[0] == set()


def test_CONTROLE_memorial_nao_e_dono():
    itens = [_it("MEMORIAL DESCRITIVO (PISOS)", "Pisos e Rodapés", "Piso cerâmico"),
             _it(PONTOS, "Pisos e Rodapés", "Piso — Sala")]
    assert repetidos(itens)[0] == set()


def test_CONTROLE_planta_de_demolicao_nao_manda_embora_o_forro_NOVO():
    itens = [_it("Prancha 5 — Planta de Demolição Forro 2º Pav", "Forros", "Forro novo em gesso"),
             _it("Prancha 2 — Planta de Layout Proposto 2º Pav", "Forros", "Forro modular 0,60×0,60 novo")]
    assert repetidos(itens)[0] == set()


def test_CONTROLE_andar_diferente_nao_e_repeticao():
    itens = [_it("CC_AP_PAGINACAO TERREO_R00.PDF", "Pisos e Rodapés", "Piso porcelanato"),
             _it("CC_AP_LAYOUT 1O PAV._R00.PDF", "Pisos e Rodapés", "Piso porcelanato do 1º")]
    assert repetidos(itens)[0] == set()


def test_mesmo_andar_e_repeticao():
    itens = [_it("CC_AP_PAGINACAO TERREO_R00.PDF", "Pisos e Rodapés", "Piso porcelanato"),
             _it("CC_AP_LAYOUT TERREO_R00.PDF", "Pisos e Rodapés", "Piso porcelanato do térreo")]
    assert repetidos(itens)[0] == {1}


def test_CONTROLE_a_unica_sanca_do_projeto_fica():
    """Sanca só na prancha de luminotécnico; a de forro não tem sanca."""
    itens = [_it("CC_AP_Forro e Climatizacao Terreo_R00.pdf", "Forros", "Estrutura metálica de fixação do forro"),
             _it("CC_AP_Forro e Climatizacao Terreo_R00.pdf", "Forros", "Acabamento de transição / perfil"),
             _it("CC_AP_Luminotecnico Terreo_R00.pdf", "Forros", "Sanca de gesso para receber perfil LED")]
    assert repetidos(itens)[0] == set()


def test_CONTROLE_dona_vazia_nao_manda_ninguem_embora():
    itens = [_it(PISO, "Revestimentos", "Revestimento de parede"),
             _it(PONTOS, "Pisos e Rodapés", "Piso — Sala")]
    assert repetidos(itens)[0] == set()


@pytest.mark.parametrize("desc", [
    "Demolição de piso existente", "Remoção de forro", "Retirada do rodapé",
    "[EXISTENTE — preservar] Forro existente", "Piso a remanejar"])
def test_CONTROLE_demolicao_remocao_e_existente_nunca_saem(desc):
    assert familia_do_item("Pisos e Rodapés", desc) is None or \
        familia_do_item("Forros", desc) is None
    itens = [_it(PISO, "Pisos e Rodapés", "Piso porcelanato"),
             _it(FORRO, "Forros", "Forro de gesso"),
             _it(PONTOS, "Pisos e Rodapés", desc)]
    assert 2 not in repetidos(itens)[0]


def test_rodape_sem_prancha_propria_pertence_a_de_piso():
    itens = [_it(PISO, "Pisos e Rodapés", "Rodapé poliestireno 10 cm"),
             _it(LAYOUT, "Pisos e Rodapés", "Rodapé — material a definir")]
    assert repetidos(itens)[0] == {1}


def test_sublinhado_nao_mata_a_borda_do_nome():
    """'_P PISO_LUANA': o '_' é letra pro regex."""
    assert disciplinas_da_prancha("08.18_P PISO_LUANA_09.04.PDF") == {"piso"}


# ── o motor CHAMA a régua antes de consolidar, com chave de desligar ──────
def test_o_motor_tira_os_repetidos_antes_da_consolidacao():
    fonte = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    arvore = ast.parse(fonte)
    fn = next(n for n in ast.walk(arvore)
              if isinstance(n, ast.FunctionDef) and n.name == "process_job")
    def _linhas(nome):
        return [c.lineno for c in ast.walk(fn) if isinstance(c, ast.Call)
                and (getattr(c.func, "id", None) or getattr(c.func, "attr", None)) == nome]
    rep, cons = _linhas("_repetidos"), _linhas("_consolidate_items")
    assert rep and cons and min(rep) < min(cons), (rep, cons)
    assert 'os.getenv("LEITURA_POR_PROJETO"' in fonte
