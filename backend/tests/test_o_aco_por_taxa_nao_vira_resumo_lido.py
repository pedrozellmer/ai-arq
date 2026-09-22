# -*- coding: utf-8 -*-
"""Aço calculado por TAXA não vira "aço lido do resumo de aço da prancha".

🩸 22/09/2026 — revisão adversária do conserto do job `ee801b82`. O aviso de
estrutura ganhou a frase verdadeira pro caso dela ("O aço foi lido do resumo
de aço das próprias pranchas em N linha(s)"), decidida por
`engine_rules.linhas_de_aco_do_resumo`. A 1ª versão da régua contava qualquer
citação do quadro que não estivesse negada — e a IA escreve a citação duas
vezes nas linhas por taxa:

    "ESTIMADO. Não há quadro de aço nestas pranchas. Taxa 100 kg/m³ adotada
     para vigas. Verificar projeto estrutural e quadro de ferragens."

A 1ª citação é negada; a 2ª é RECOMENDAÇÃO, não procedência. A régua pulava a
1ª e contava a 2ª. No job 08ba5752 (PDF de arquitetura lido como estrutura,
aviso emitido em 17/09, zero quadro de aço) 6 de 7 linhas contavam. O aviso
trocaria a frase VERDADEIRA ("o quadro de ferros é outra prancha (ARM)") por
"o aço foi lido do resumo de aço das próprias pranchas em 6 linha(s)" — número
de taxa (regra nº3) dito como transcrito do desenho. E, sem marca de altura, o
ramo virava "resumo-de-aco": sumia o "reprocesse escolhendo 'Ler como
Arquitetura'", que é o diagnóstico certo desse caso.

🔑 A citação só conta se o mesmo trecho da frase AFIRMA de onde o número veio
("lido do", "fonte:", "extraído do", "confirmado no", "a partir do"...), não
nega o quadro antes nem depois, e não é trecho de peso por taxa.

📏 Medido (90 d, sem avaliação, now() de testemunha 22/09 15:37): 148 linhas
kg > 0 citam quadro/resumo/lista em 15 jobs. A régua antiga contava 130, esta
conta 119 — saem 12 (as 6 do 08ba5752, as 2 do 62c49fe6, a recomendação do
7f7ef56a, uma estimativa por comprimento do f8d8e6d8 e 3 linhas de soma/
diagnóstico) e entram 3 (o PLURAL "Soma confirmada dos quadros de ferragens"
do 7f7ef56a, que a régua antiga, só no singular, não enxergava).
🪤 Por JOB zeram só os DOIS sem quadro nenhum (08ba5752 6→0, 62c49fe6 2→0);
7f7ef56a vai de 1 pra 3, porque a régua antiga contava ali a linha errada.
🩸 A primeira medição desta revisão disse "130→116, e os TRÊS zeram": ela
peneirou o acervo com a regex ANTIGA (sem plural) e mediu o alcance da régua
nova pelo corte da velha — o mesmo laço de 19/09 ("o número que eu medi pode
ser o meu próprio corte"). Daí os dois controles de plural aqui embaixo.

🧪 A régua é chamada direto, e o aviso roda pelo TRECHO REAL do main.py (o
mesmo recorte de `test_o_aviso_de_estrutura_diz_o_que_o_job_tem`). O controle
positivo são as linhas do caso ee801b82, que continuam contando — guarda que só
cala não guarda nada.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
from test_o_aviso_de_estrutura_diz_o_que_o_job_tem import (  # noqa: E402
    _aco_do_resumo, _it, _roda)

_ARM = "outra prancha (ARM)"
_RESUMO_LIDO = "resumo de aço das próprias pranchas"
_LER_COMO_ARQ = "Ler como Arquitetura"

# As redações REAIS das linhas por taxa/cálculo do acervo (sem nome de arquivo).
_DO_08ba5752 = [
    "ESTIMADO. Não há quadro de aço nestas pranchas. Taxa 150 kg/m³ adotada para "
    "pilares. Verificar projeto estrutural e quadro de ferragens.",
    "ESTIMADO. Não há quadro de aço nestas pranchas. Taxa 100 kg/m³ adotada para "
    "vigas. Verificar projeto estrutural e quadro de ferragens.",
    "ESTIMADO. Não há quadro de aço nestas pranchas (arquitetura). Taxa 12 kg/m² "
    "adotada para laje maciça. Verificar projeto estrutural e quadro de ferragens.",
    "ESTIMADO. Não há quadro de aço nem detalhamento de armadura nestas pranchas "
    "(arquitetura). Taxa de consumo 80 kg/m³ adotada como referência. Verificar "
    "projeto estrutural e quadro de ferragens específico.",
]
_DO_62c49fe6 = (
    "ESTIMADO. Calculado pela taxa típica de 100 kg/m³ aplicada ao volume estimado "
    "de concreto em pilares (30,73 m³). Não há quadro/resumo de aço na prancha "
    "extraída. Bitolas não identificadas no CAD. Revisar com projeto de armação ou "
    "quadro de ferragens.")
_DO_7f7ef56a = (
    "Estimado. Soma dos itens 3+4+5: 143,07+2,89+42,09=188,05 kg. Não há "
    "quadro/resumo de aço consolidado nesta prancha; todos os valores foram "
    "derivados por cálculo a partir das indicações de bitola e comprimento lidas "
    "no desenho. Recomenda-se conferir com quadro de ferragens quando disponível.")
#: As TRÊS linhas do mesmo job que vieram MESMO do quadro — no plural, que a
#: régua antiga (só "quadro de ferragens") não enxergava.
_DO_7f7ef56a_COM_QUADRO = [
    "Soma confirmada dos quadros de ferragens (com +10%): G1 = 19,2 kg + G2 = "
    "19,2 kg + G3 = 37,4 kg. Total = 75,8 kg. NÃO inclui P31. | Estimativa: lido "
    "de PDF, não medido em geometria — envie DWG/DXF pra medir",
    "Soma confirmada dos quadros de ferragens (com +10%): G1 = 83,6 kg + G2 = "
    "83,6 kg + G3 = 229,9 kg. Total = 397,1 kg. NÃO inclui P31. | Estimativa: "
    "lido de PDF, não medido em geometria — envie DWG/DXF pra medir",
    # 🪤 esta tem "Taxa média ponderada" numa frase VIZINHA: a trava da taxa é
    # por trecho, senão derrubaria uma linha que veio do quadro de verdade
    "Soma confirmada dos quadros de ferragens (com +10%): G1 = 102,8 kg + G2 = "
    "102,8 kg + G3 = 267,3 kg. Total = 472,9 kg. NÃO inclui P31. Taxa média "
    "ponderada: G1/G2 ≈ 141,71 kg/m³; G3 ≈ 220,40 kg/m³. | Estimativa: lido de "
    "PDF, não medido em geometria — envie DWG/DXF pra medir",
]


def _conta(obs, q=1000.0):
    return er.linhas_de_aco_do_resumo([_it("Armadura CA-50", q, "kg", obs)])


# ══════════════════════════════════════════════════════════════════════════
#  🩸 A régua, com as frases de verdade
# ══════════════════════════════════════════════════════════════════════════
def test_linha_por_TAXA_que_so_RECOMENDA_o_quadro_nao_conta_08ba5752():
    """🩸 A 1ª citação negada, a 2ª só recomenda — nenhuma é procedência."""
    for obs in _DO_08ba5752:
        assert _conta(obs) == 0, (
            "linha por TAXA contada como aço lido do resumo:\n" + obs)


def test_revisar_ou_conferir_com_o_quadro_nao_e_procedencia():
    assert _conta(_DO_62c49fe6) == 0, _DO_62c49fe6
    assert _conta(_DO_7f7ef56a) == 0, _DO_7f7ef56a


def test_as_outras_formas_de_dizer_que_NAO_ha_quadro():
    for obs in ("Estimado por taxa de 100 kg/m³. A prancha não apresenta quadro de aço.",
                "Estimado por taxa. Ausência de resumo de aço na prancha.",
                "Estimado por taxa. Quadro de aço não encontrado nesta prancha.",
                "Estimado por taxa. Falta o resumo de aço (prancha ARM não enviada)."):
        assert _conta(obs) == 0, obs


def test_negacao_DEPOIS_da_citacao_desfaz_o_fonte():
    """🪤 "Fonte:" antes e "não localizado" depois: a fonte foi negada."""
    assert _conta("Fonte: quadro de aço não localizado nesta prancha.") == 0


def test_negacao_ANTES_desfaz_o_verbo_de_procedencia():
    """🪤 "extraído do" afirma — "não foi extraído do" nega."""
    assert _conta("Não foi extraído do quadro de aço; peso por cálculo de "
                  "comprimento.") == 0


def test_trecho_de_peso_por_taxa_nao_vira_resumo_mesmo_com_conforme():
    """🪤 "conforme" afirma — mas o número saiu da taxa (regra nº3)."""
    assert _conta("Taxa de 80 kg/m³ adotada conforme quadro de aço típico de "
                  "piscinas.") == 0


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES POSITIVOS — o que é lido do quadro continua contando
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_as_linhas_do_caso_ee801b82_continuam_contando():
    """As 7 linhas que a IA tirou do RESUMO DE AÇO do caso, na redação dela."""
    assert er.linhas_de_aco_do_resumo(_aco_do_resumo()) == 7


def test_CONTROLE_as_formas_de_procedencia_do_acervo_contam():
    for obs in ("Fonte: quadro de aço da prancha (layer [2]) — 'Ø 8.0 mm: 810 kg'.",
                "Quantidade confirmada no resumo de aço da prancha: CA-50 ø10,0mm.",
                "Valores confirmados pelo quadro de resumo de aço da prancha.",
                "Peso total declarado no quadro/resumo de aço da prancha.",
                "Valor extraído diretamente do Quadro 'Resumo Aço' da prancha.",
                "Total explícito no quadro 'Resumo Aço FUNDAÇÃO': 41kg.",
                "Soma dos quadros de ferragens das pranchas: 1.200 kg.",
                "Resumo de aço CA-50 lido: CTot=100 m, PTot=39 kg."):
        assert _conta(obs) == 1, obs


def test_CONTROLE_o_PLURAL_quadros_de_ferragens_conta_7f7ef56a():
    """🩸 A régua antiga só via o SINGULAR ("quadro de ferragens"), e as três
    linhas de verdade do 7f7ef56a dizem "quadros". Medir o alcance com a regex
    velha escondeu isso: o job parecia zerar e na verdade sobe de 1 pra 3."""
    for obs in _DO_7f7ef56a_COM_QUADRO:
        assert _conta(obs) == 1, "perdeu o plural do quadro:\n" + obs


def test_CONTROLE_no_MESMO_job_a_linha_por_calculo_continua_fora():
    """🧪 O par do controle acima: no mesmo job, as linhas que NÃO vieram do
    quadro seguem em zero — senão o teste de cima passaria com a régua boba."""
    for obs in (
            "Estimado. Calculado por comprimento × massa linear (tabela NBR "
            "7480). Sem quadro de aço na prancha.",
            "Estimado. Soma dos itens 3+6+9: 58,28+54,49+47,26 = 160,03 kg. Sem "
            "quadro de aço na prancha — todos os valores calculados pela tabela "
            "de massa linear NBR 7480."):
        assert _conta(obs) == 0, obs


def test_CONTROLE_a_citacao_negada_ao_lado_de_uma_afirmada_conta_a_afirmada():
    """🪤 Não é "qualquer negação derruba a linha": a IA escreve "não há quadro
    exclusivo para sapatas" ao lado do resumo de onde tirou o número."""
    assert _conta("Valor lido do RESUMO DE AÇO CA-50 da prancha. Não há quadro de "
                  "aço exclusivo para sapatas — ver totais gerais.") == 1
    # e na ordem inversa: a 1ª citação negada, a 2ª é a procedência
    assert _conta("Não há quadro de aço exclusivo para sapatas; o peso foi lido "
                  "do RESUMO DE AÇO CA-50 da prancha.") == 1


# ══════════════════════════════════════════════════════════════════════════
#  🩸 O aviso de estrutura de um job SÓ com aço por taxa (formato do 08ba5752)
# ══════════════════════════════════════════════════════════════════════════
def _itens_por_taxa(com_marca_de_altura):
    itens = [
        _it("Concreto armado — vigas da área de lazer", 50, "m³",
            "Estimado por cotas." + (" Altura de viga não indicada."
                                     if com_marca_de_altura else "")),
        _it("Fôrma — laje de cobertura", 0, "m²",
            "Área não calculada: altura não legível." if com_marca_de_altura
            else "Área não calculada."),
    ]
    itens += [_it("Armadura CA-50 — elemento %d" % k, 1000.0 + k, "kg", obs)
              for k, obs in enumerate(_DO_08ba5752)]
    return itens


def test_o_job_por_taxa_mantem_a_frase_VERDADEIRA_do_ARM():
    avisos, log, _ns = _roda(_itens_por_taxa(com_marca_de_altura=True))
    txt = avisos[0]
    assert _RESUMO_LIDO not in txt, (
        "disse que o aço foi lido do resumo num job SEM quadro de aço, com todo "
        "o peso por taxa:\n" + txt)
    assert _ARM in txt, "sumiu a frase verdadeira do quadro de ferros:\n" + txt
    assert "aco_do_resumo=0" in log, log
    assert "ramo=falta-altura" in log, log


def test_o_job_por_taxa_SEM_marca_de_altura_volta_ao_ler_como_arquitetura():
    """Sem marca de altura, a régua falsa mudava o ramo pra "resumo-de-aco" e
    sumia o conselho certo pra PDF de arquitetura lido como estrutura."""
    avisos, log, _ns = _roda(_itens_por_taxa(com_marca_de_altura=False))
    txt = avisos[0]
    assert "ramo=falta-prancha" in log, log
    assert _LER_COMO_ARQ in txt, txt
    assert _RESUMO_LIDO not in txt, txt


def test_CONTROLE_o_mesmo_job_COM_resumo_lido_diz_de_onde_veio_o_aco():
    """Mesmos itens + as 7 linhas do resumo do caso: aí a frase é verdade."""
    avisos, log, _ns = _roda(_itens_por_taxa(com_marca_de_altura=False)
                             + _aco_do_resumo())
    txt = avisos[0]
    assert "resumo de aço das próprias pranchas em 7 linha(s)" in txt, txt
    assert "ramo=resumo-de-aco" in log, log
