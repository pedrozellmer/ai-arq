# -*- coding: utf-8 -*-
"""O aço lido do RESUMO DO AÇO não perde o selo por dois falsos alarmes.

🩸 26/09/2026 — job 32a27efc (estrutura Eberick, 7 DXF). Com o resumo do aço
enfim lido certo, 9 das 12 linhas de aço — todas com o número exato do quadro —
saíram laranja:

  1. a trava da SOMA disparava na CONFERÊNCIA que a IA escreve do total:
     "Total declarado: 255,93 kg (42,65 + 213,28 = 255,93 ✓)" na linha de
     42,65. A linha é PARCELA de uma conta que fecha; quem somou foi a
     conferência. E "(CA-50 + CA-60)" é nome de classe de aço, não adição.
  2. a exceção do quadro de aço não reconhecia "RESUMO DO AÇO" (com "do") nem o
     título espaçado "R E S U M O  D O  A Ç O".

Selo perdido, não número errado — mas é o selo que diz ao cliente o que foi lido.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine_rules import (  # noqa: E402
    a_fonte_declarada_e_uma_soma,
    selo_apos_regra_da_soma,
    selos_sem_geometria,
)

_CONFERE = ("Fonte: quadro/resumo de aço da prancha. Comprimento total 271,66 m. "
            "Total declarado na prancha: 255,93 kg (42,65 + 213,28 = 255,93 ✓).")


# ══════════════════════════════════════════════════════════════════════════
#  1) A regra da soma: conferência do total ≠ soma que gerou a linha
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_a_linha_e_parcela_de_uma_conta_que_fecha():
    for q in (42.65, 213.28):
        conf, obs, somou = selo_apos_regra_da_soma("confirmado", _CONFERE, q)
        assert (conf, somou) == ("confirmado", False), q
        assert obs == _CONFERE


def test_o_caso_com_o_total_na_frente():
    obs = "Peso lido do quadro. Peso total declarado na prancha: 653.70 kg = 142.02 + 511.68 ✓."
    assert not a_fonte_declarada_e_uma_soma(obs, 511.68)
    assert not a_fonte_declarada_e_uma_soma(obs, 142.02)


def test_o_caso_classe_de_aco_nao_e_adicao():
    obs = "Fonte: quadro/resumo de aço lido da prancha. Total geral declarado: 371,11 kg (CA-50 + CA-60)."
    assert not a_fonte_declarada_e_uma_soma(obs, 92.26)


def test_CONTROLE_a_linha_que_E_o_total_continua_caindo():
    conf, obs, somou = selo_apos_regra_da_soma("confirmado", _CONFERE, 255.93)
    assert (conf, somou) == ("estimado", True)
    assert obs.startswith("⚠ SOMA")


def test_CONTROLE_sem_a_quantidade_vale_a_regra_de_antes():
    assert a_fonte_declarada_e_uma_soma(_CONFERE)
    assert a_fonte_declarada_e_uma_soma(_CONFERE, None)


def test_CONTROLE_conta_que_nao_fecha_nao_e_conferencia():
    obs = "Total: 300,00 kg (42,65 + 213,28 = 300,00)."
    assert a_fonte_declarada_e_uma_soma(obs, 42.65)


def test_CONTROLE_quantidade_que_nao_e_parcela_continua_caindo():
    assert a_fonte_declarada_e_uma_soma(_CONFERE, 100.0)


def test_CONTROLE_classe_de_aco_com_numero_somado_continua_soma():
    obs = "Resumo: CA-50 Ø10 (671,00 kg) + CA-60 Ø5 (167,99 kg) = 838,99 kg ✓."
    assert a_fonte_declarada_e_uma_soma(obs, 838.99)


def test_CONTROLE_contagem_de_tipos_com_palavra_no_meio_continua_soma():
    """O '2' de 'tipo 2' não pode passar por parcela: a conta precisa ser
    puramente numérica pra valer como conferência."""
    obs = "Fonte: CONTAGEM DE BLOCOS — 'VENEZIANA' (tipo 1): 1 un + (tipo 2): 1 un = 2 un."
    for q in (1, 2):
        assert a_fonte_declarada_e_uma_soma(obs, q), q
    obs2 = "Fonte: bloco 'Suporte': tipo1=2 + tipo2=1 + tipo3=1 = 4 un."
    for q in (1, 2, 4):
        assert a_fonte_declarada_e_uma_soma(obs2, q), q


def test_CONTROLE_outra_soma_na_mesma_observacao_continua_valendo():
    obs = _CONFERE + " Área: Sala 7,8 + Quarto 10,8 = 18,6 m²."
    assert a_fonte_declarada_e_uma_soma(obs, 42.65)


def test_CONTROLE_palavra_de_soma_na_fonte_continua_valendo():
    obs = "Fonte: soma dos quadros de aço das pranchas: 42,65 + 213,28 = 255,93."
    assert a_fonte_declarada_e_uma_soma(obs, 42.65)


def test_CONTROLE_linha_total_com_parcela_quase_do_tamanho_do_total():
    """A borda que a revisão achou: com a tolerância de 0,5%, a linha que É o
    total também 'bate' com uma parcela de mais de 99,5% dele. Continua soma."""
    casos = [
        ("Fonte: contagem de blocos 'Montante' — tipo1=1190, tipo2=3, tipo3=2 → 1190+3+2 = 1195 un.", 1195),
        ("Fonte: polígonos do layer PISO. Área: 245,30 + 1,20 = 246,50 m².", 246.50),
        ("Peso CA-50: 1.068,47 kg = 1.065,12 + 3,35.", 1068.47),
        ("Total: 512,40 + 1,10 + 0,90 = 514,40 m.", 514.40),
    ]
    for obs, q in casos:
        assert a_fonte_declarada_e_uma_soma(obs, q), (obs, q)


def test_CONTROLE_classes_de_aco_com_o_total_depois_continuam_soma():
    obs = "Fonte: quadro/resumo de aço da prancha. Peso total de aço (CA-50 + CA-60) = 838,99 kg."
    assert a_fonte_declarada_e_uma_soma(obs, 838.99)


def test_o_main_passa_a_quantidade_para_a_trava():
    """Sem a quantidade, a trava cai na regra de antes em silêncio (rebaixa a
    conferência de novo): o 3º argumento é o que liga o conserto."""
    fonte = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "main.py"), encoding="utf-8").read()
    chamadas = [n for n in ast.walk(ast.parse(fonte)) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "_regra_soma"]
    assert len(chamadas) == 1, len(chamadas)
    args = chamadas[0].args
    assert len(args) == 3 and getattr(args[2], "id", "") == "qty", ast.dump(chamadas[0])


# ══════════════════════════════════════════════════════════════════════════
#  2) A exceção do quadro de aço: "RESUMO DO AÇO" e o título espaçado
# ══════════════════════════════════════════════════════════════════════════
def _linha_de_aco(obs):
    return {"description": "Aço CA-50 Ø 10,0 mm", "unit": "kg", "quantity": 671.0,
            "confidence": "confirmado", "origem": "dxf_geom", "observations": obs}


def test_o_caso_resumo_DO_aco_nao_e_acusado():
    obs = ("Valor copiado LITERALMENTE do quadro 'RESUMO DO AÇO' na prancha (layer "
           "TABELAS): 'PESO CA-50 Ø 10 = 671.00 kg', comprimento total 1068.47 m.")
    assert selos_sem_geometria([_linha_de_aco(obs)]) == []


def test_o_caso_titulo_espacado_nao_e_acusado():
    obs = ("Fonte: quadro 'R E S U M O D O A Ç O +10%' lido do layer TABELAS — "
           "'PESO CA-50 Ø 10 = 654.82 kg'.")
    assert selos_sem_geometria([_linha_de_aco(obs)]) == []


def test_CONTROLE_numero_de_texto_sem_o_quadro_continua_acusado():
    obs = "Fonte: texto no layer TABELAS: '671.00 kg'."
    assert [a["indice"] for a in selos_sem_geometria([_linha_de_aco(obs)])] == [0]


def test_CONTROLE_resumo_de_outra_coisa_continua_acusado():
    obs = "Fonte: tabela 'RESUMO DO PROJETO' no layer TABELAS: '671.00 kg'."
    assert [a["indice"] for a in selos_sem_geometria([_linha_de_aco(obs)])] == [0]


def test_CONTROLE_os_falsos_da_revisao_continuam_acusados():
    """A 1ª versão juntava a observação inteira sem espaço: 'quadro de a
    conferir' virava 'quadrodeaco'. E não olhava negação nem a unidade."""
    for obs in ("Não há resumo do aço nesta prancha; peso lido do texto no layer TEXTOS: '671.00 kg'.",
                "Fonte: tabela 'RESUMO DO ACOMPANHAMENTO' no layer TABELAS: '671.00 kg'.",
                "Fonte: texto 'quadro de a conferir' no layer TABELAS: '671.00 kg'."):
        assert [a["indice"] for a in selos_sem_geometria([_linha_de_aco(obs)])] == [0], obs
    concreto = dict(_linha_de_aco("Fonte: tabela de consumo de concreto ao lado do RESUMO DO AÇO: 12,5 m³."),
                    unit="m³", quantity=12.5)
    assert [a["indice"] for a in selos_sem_geometria([concreto])] == [0]
