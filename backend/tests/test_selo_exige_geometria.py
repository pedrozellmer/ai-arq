# -*- coding: utf-8 -*-
"""REGRA DURA Nº1: o selo "✓ MEDIDO do CAD" exige procedência de GEOMETRIA.

🚨 24/08/2026. Medido no acervo de produção: **61 itens, em 19 projetos de 15
clientes**, foram entregues com `confirmado` (branco na planilha, "✓ MEDIDO do
CAD") tendo como única procedência um TEXTO lido da prancha. 23 deles em m²,
somando **33.962 m²** apresentados como medidos.

A rede que existia (`selos_sem_medida`) só pegava `confirmado` com quantidade
ZERO. Para `confirmado` com um número vindo de texto não havia rede nenhuma.

🪤 Esta regra decide olhando TEXTO — e a lição do dia anterior foi justamente
"texto não é prova". A diferença é a DIREÇÃO: ela só REBAIXA, nunca promove.
Errar pro lado de "estimado" custa uma revisão a mais ao cliente; errar pro lado
de "medido" põe um número sem lastro na planilha usando o selo que o produto
reserva pra confiança. Na dúvida, rebaixa.

Todos os casos abaixo são observações REAIS, copiadas de itens que já foram
entregues a clientes.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from engine_rules import selos_sem_geometria  # noqa: E402


def _it(obs, conf="confirmado", q=10.0, origem="", desc="Item", unit="m²"):
    return {"description": desc, "unit": unit, "quantity": q,
            "confidence": conf, "observations": obs, "origem": origem}


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLE POSITIVO — casos REAIS que estavam com selo de medido
# ══════════════════════════════════════════════════════════════════════════
REAIS_QUE_DEVEM_CAIR = [
    "Fonte: texto layer 'ARQ-TEXTO 1': 'AREA TOTAL CLINICA = 264,54 m²'. "
    "Inclui todas as áreas internas.",
    "Conforme legenda código 04 da primeira tabela — área aproximada explícita",
    "Fonte: texto layer 'txt' — 'A = 48.00 m²'. Identificado como Sala de Aula 02.",
    "Fonte: texto na legenda 'TOTAL DE CADEIRAS NEWNET 16003 EXISTENTES = 151 UNIDADES'",
    "Fonte: texto '30.995,80 m²' explícito no layer 'INC_LIN02' e 'FOLHA'. "
    "Área total construída conforme carimbo do projeto.",
    "LM1 conforme legenda de luminárias",
    "Conforme legenda código 01 — quantidade explícita na tabela",
]


def test_texto_com_selo_de_medido_e_rebaixado():
    itens = [_it(o) for o in REAIS_QUE_DEVEM_CAIR]
    ach = selos_sem_geometria(itens)
    faltaram = [REAIS_QUE_DEVEM_CAIR[i] for i in range(len(itens))
                if i not in {a["indice"] for a in ach}]
    assert not faltaram, (
        "estes já foram entregues como '✓ MEDIDO do CAD' e continuariam:\n  "
        + "\n  ".join(f[:100] for f in faltaram))


def test_o_pior_caso_real_e_pego():
    """O total do PRÉDIO colado numa linha de acabamento de piso, com selo de
    medido. Errado no número e errado no selo."""
    it = _it("Fonte: texto layer 'ARQ-TEXTO 1': 'AREA TOTAL CLINICA = 264,54 m²'.",
             q=264.54, desc="Piso — revestimento de piso interno")
    assert selos_sem_geometria([it])


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLE NEGATIVO — medição de verdade não pode ser rebaixada
# ══════════════════════════════════════════════════════════════════════════
REAIS_QUE_DEVEM_FICAR = [
    "Fonte: 84 INSERTs do bloco '_VAONER025250652500550005500' (CONTAGEM DE BLOCOS).",
    "Fonte: 2 INSERTs do bloco 'LOUÇA - bacia deca unic planta'.",
    "Fonte: comprimento do layer 'ARQ-DEMOLIR' = 93.85 m. Textos no layer indicam: "
    "WC 02, WC 04, PM-01.",
    "Fonte: comprimento total do layer 'PVC' = 75,73 m. Textos associados: Ø100, Ø150.",
    "Fonte: área hachurada do layer 'ARQ-DET-GENF' = 12,33 m² (soma de 12 hachuras).",
    "Fonte: comprimento total do layer ARQ-SOCULO = 409,13 m. Texto 'SÓCULO DE "
    "ALVENARIA' aparece 6× na prancha (layer ARQ-TXT-1_100).",
]


def test_medicao_de_verdade_nao_e_tocada():
    """🪤 Os três últimos citam TEXTO na observação — mas a medida veio da
    geometria. Rebaixá-los seria destruir o trabalho do motor."""
    itens = [_it(o) for o in REAIS_QUE_DEVEM_FICAR]
    ach = selos_sem_geometria(itens)
    assert not ach, (
        "rebaixou medição legítima:\n  " + "\n  ".join(
            REAIS_QUE_DEVEM_FICAR[a["indice"]][:100] for a in ach))


def test_origem_dxf_geom_fecha_a_questao():
    """Quem tem origem explícita de geometria não é julgado por texto nenhum."""
    assert not selos_sem_geometria(
        [_it("Conforme legenda código 01 — quantidade explícita", origem="dxf_geom")])


def test_nao_acusa_quem_nao_declarou_procedencia():
    """Sem observação, ou com observação que não diz de onde veio, a rede se
    cala. Acusar no escuro seria rebaixar meio acervo por precaução."""
    assert not selos_sem_geometria([_it("")])
    assert not selos_sem_geometria([_it("Item de praxe para obras de reforma.")])
    assert not selos_sem_geometria([_it("Revisar antes de orçar.")])


def test_so_mexe_em_quem_esta_marcado_como_medido():
    assert not selos_sem_geometria([_it("Conforme legenda", conf="estimado")])
    assert not selos_sem_geometria([_it("Fonte: texto na legenda", conf="verificar")])


def test_a_rede_so_REBAIXA_nunca_promove():
    """Guarda de direção: a função devolve índices pra rebaixar. Se algum dia
    ela apontar um item que NÃO está confirmado, virou promoção."""
    itens = [_it("Fonte: texto na legenda", conf="estimado"),
             _it("Fonte: texto na legenda", conf="confirmado")]
    ach = selos_sem_geometria(itens)
    assert [a["indice"] for a in ach] == [1]


def test_a_rede_esta_ligada_no_process_job():
    import io
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert "selos_sem_geometria as _ssg" in src, "a rede existe mas não roda"
    i = src.index("selos_sem_geometria as _ssg")
    trecho = src[i:i + 1400]
    assert "_CfG.ESTIMADO" in trecho, "não rebaixa o selo"
    assert "motor:selo-sem-geometria" in trecho, "não deixa rastro no log"
    assert "LIDO de um texto da prancha" in trecho, "não explica ao cliente"
