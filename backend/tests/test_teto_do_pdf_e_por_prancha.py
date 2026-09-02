# -*- coding: utf-8 -*-
"""O teto que segura m² inventado é da MAIOR PRANCHA, nunca da SOMA.

🩸 MEDIDO em 01/09/2026, no job 144c1f04 (flavio anderson, 20 PDFs — o maior
caderno da base). O ramo do pdfvec preserva o número que a IA leu quando ele
"cabe no que foi medido": `q <= 1.3 * pdfvec_m2`. Só que `pdfvec_m2` acumula
prancha a prancha, e um caderno do MESMO imóvel (PAREDE, FORRO, ILUMINAÇÃO,
PISO, RODAPÉ) é a mesma planta contada em cada disciplina:

    PAREDE 270,6 · FORRO 24,2 · ILUMINAÇÃO 185,4 · PISO 41,5 · RODAPÉ 63,6
    soma = 585,3 m²  →  teto 761 m²
    maior prancha = 270,6 m²  →  teto 351 m²

O apartamento tem ~270 m². Com 5 das 20 pranchas lidas o teto já estava 2,8×
frouxo, e cresce a cada prancha nova.

🔑 O EFEITO NÃO É INFLAR NÚMERO — é DESLIGAR A TRAVA. Essa comparação é a
trava 3 das três que o próprio cabeçalho do ramo promete, e existe pra impedir
que um chute de m² da IA sobreviva de carona (regra dura nº1). Quanto maior o
caderno, mais frouxa ela fica: o teto cresce com o tamanho do CADERNO em vez de
com o tamanho do IMÓVEL.

🪤 Job de UMA prancha (o caso comum) tem maior == soma: o conserto não muda
nada ali, e `test_CONTROLE_uma_prancha_so_NAO_muda_nada` guarda isso.

🪤 Sem medição por prancha o teto CAI DE VOLTA na soma, de propósito: teto 0
zeraria todo item de área do job. Errar pro lado de antes é aceitável; zerar
item de cliente por falta de dado, não — foi assim que em 31/08 eu apaguei
13,6 m² MEDIDOS de item real pra "fechar um rasgo".

🚨 Zerar CALADO seria bug por si só (a família das 144 linhas engolidas em 37
jobs): o conserto conta quantos itens o teto novo derrubou, grava em
`error_log` e vira aviso pro cliente. Os testes do fim guardam isso.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


class _Item:
    def __init__(self, desc, unit, qty, ref_sheet="", obs="", origem="",
                 conf="estimado"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.ref_sheet = ref_sheet
        self.observations = obs
        self.origem = origem
        self.confidence = conf


def _prancha(arquivo, m2):
    return {"arquivo": arquivo, "rooms_m2": m2, "n_rooms": 10, "walls_m": 0,
            "n_walls": 0, "grupo_maior_m2": m2, "scale": 75,
            "scale_src": "cotas", "escala_validada": True, "cotas_batem": 7}


# as 5 primeiras pranchas do job 144c1f04, com os números do error_log
CADERNO = {
    "parede_p0": _prancha("07.18_P PAREDE_LUANA_09.04.pdf", 270.6),
    "forro_p0": _prancha("02.18_P FORRO_LUANA_09.04.pdf", 24.2),
    "ilum_p0": _prancha("03.18_P ILUMINACAO_LUANA_09.04.pdf", 185.4),
    "piso_p0": _prancha("08.18_P PISO_LUANA_09.04.pdf", 41.5),
    "rodape_p0": _prancha("11.18_P RODAPE_LUANA_09.04.pdf", 63.6),
}
SOMA = 585.3          # o que o teto usava
MAIOR = 270.6         # o que o teto usa agora


def _fonte():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


# ── O conserto ─────────────────────────────────────────────────────────────
def test_chute_que_cabia_na_SOMA_e_nao_cabe_na_maior_prancha_e_ZERADO():
    """🩸 O item que o conserto existe pra pegar.

    700 m² de piso num apartamento de 270: passava (1,3 × 585,3 = 761) e agora
    não passa (1,3 × 270,6 = 351)."""
    it = _Item("Piso cerâmico", "m²", 700.0)
    main._apply_area_honesty([it], pdfvec_m2=SOMA, pdfvec_por_prancha=CADERNO)
    assert it.quantity == 0, (
        "m² que não cabe na maior prancha sobreviveu — a trava 3 continua "
        "desligada num caderno de várias pranchas")


def test_numero_que_CABE_na_maior_prancha_SOBREVIVE():
    """🧪 O contrário do teste acima: apertar o teto não pode virar tesoura.
    300 m² num imóvel cuja maior prancha mede 270,6 cabe na folga de 1,3×."""
    it = _Item("Piso cerâmico", "m²", 300.0)
    main._apply_area_honesty([it], pdfvec_m2=SOMA, pdfvec_por_prancha=CADERNO)
    assert it.quantity == 300.0, (
        "o teto novo zerou um número que cabe na maior prancha — apertou "
        "demais e virou o erro de 31/08 (apagar medição de item real)")


def test_CONTROLE_POSITIVO_com_a_regra_ANTIGA_o_chute_sobreviveria():
    """🧪 O controle que prova que o teste acima guarda alguma coisa.

    Sem medição por prancha o código cai na regra ANTIGA (teto = soma). Se o
    mesmo item de 700 m² sobrevive aqui e morre lá em cima, a diferença é o
    conserto — e não um teste que passaria de qualquer jeito."""
    it = _Item("Piso cerâmico", "m²", 700.0)
    main._apply_area_honesty([it], pdfvec_m2=SOMA, pdfvec_por_prancha=None)
    assert it.quantity == 700.0, (
        "o controle não reproduz o comportamento ANTIGO — sem ele, o teste "
        "principal poderia estar passando por outro motivo")


def test_CONTROLE_uma_prancha_so_NAO_muda_nada():
    """🪤 O caso comum. Uma prancha só: maior == soma, teto idêntico ao de
    antes. Se este teste quebrar, o conserto vazou pra quem não tinha bug."""
    uma = {"unica_p0": _prancha("PLANTA BAIXA.pdf", 100.0)}
    cabe = _Item("Piso cerâmico", "m²", 120.0)     # 120 <= 130
    nao_cabe = _Item("Piso vinílico", "m²", 140.0)  # 140 > 130
    main._apply_area_honesty([cabe, nao_cabe], pdfvec_m2=100.0,
                             pdfvec_por_prancha=uma)
    assert cabe.quantity == 120.0, "job de uma prancha mudou de comportamento"
    assert nao_cabe.quantity == 0, "job de uma prancha mudou de comportamento"


def test_sem_medicao_por_prancha_NAO_zera_tudo():
    """🪤 Teto 0 zeraria todo item de área. Na falta do dado, vale a régua
    antiga — errar pro lado de antes, nunca apagar item de cliente."""
    it = _Item("Piso cerâmico", "m²", 90.0)
    main._apply_area_honesty([it], pdfvec_m2=100.0, pdfvec_por_prancha={})
    assert it.quantity == 90.0, (
        "sem medição por prancha o teto virou 0 e zerou item de cliente")


def test_o_selo_continua_ESTIMADO():
    """🚨 Regra dura nº1: item de PDF nunca sai confirmado."""
    it = _Item("Piso cerâmico", "m²", 300.0)
    main._apply_area_honesty([it], pdfvec_m2=SOMA, pdfvec_por_prancha=CADERNO)
    assert str(getattr(it.confidence, "value", it.confidence)) == "estimado"


# ── O conserto tem que ser VISÍVEL ─────────────────────────────────────────
def test_conta_quantos_o_teto_novo_derrubou():
    """📏 'Apertei o teto' não se prova sozinho. O contador mede a diferença
    entre as duas réguas no item real."""
    itens = [_Item("Piso cerâmico", "m²", 700.0),
             _Item("Forro de gesso", "m²", 650.0),
             _Item("Piso vinílico", "m²", 200.0)]   # este cabe, não conta
    main._apply_area_honesty(itens, pdfvec_m2=SOMA, pdfvec_por_prancha=CADERNO)
    assert getattr(main._apply_area_honesty, "ultimo_apertou_teto", 0) == 2, (
        "o contador não separa quem caiu POR CAUSA do teto novo de quem já "
        "caía antes")


def test_CONTROLE_o_contador_NAO_conta_quem_ja_caia_antes():
    """🧪 Item que estourava as DUAS réguas não é mérito do conserto."""
    it = _Item("Piso cerâmico", "m²", 5000.0)      # > 1,3 × soma também
    main._apply_area_honesty([it], pdfvec_m2=SOMA, pdfvec_por_prancha=CADERNO)
    assert getattr(main._apply_area_honesty, "ultimo_apertou_teto", 0) == 0, (
        "o contador está inflado: conta item que a régua antiga já derrubava")


def test_o_cliente_e_AVISADO_de_que_a_linha_ficou_em_branco():
    """🚨 Zerar calado é bug por si só (família das 144 linhas engolidas).
    Guarda de ponto de chamada — o controle abaixo prova que sabe reprovar."""
    limpo = "\n".join(l for l in _fonte().splitlines()
                      if not l.lstrip().startswith("#"))
    assert "ultimo_apertou_teto" in limpo, (
        "o caller não lê o contador — o conserto é invisível")
    assert "maior prancha medida" in limpo, (
        "o cliente não é avisado de por que a linha ficou vazia")
    assert "motor:teto-por-prancha" in limpo, (
        "o descarte não vira linha em error_log")


def test_CONTROLE_a_checagem_de_chamada_sabe_REPROVAR():
    """🧪 Sem isto, o teste acima passaria com o aviso desligado."""
    falso = "\n".join([
        "        # _apt = ultimo_apertou_teto  (comentado)",
        "        pass",
    ])
    limpo = "\n".join(l for l in falso.splitlines()
                      if not l.lstrip().startswith("#"))
    assert "ultimo_apertou_teto" not in limpo, (
        "a checagem aceita a linha COMENTADA — não guarda nada")


# ── 🩸 02/09 — QUANDO A MEDIÇÃO ESTÁ INCOMPLETA, O TETO NÃO APERTA ─────────
# Job 5f28b6ab (karina savitski, TEKOA — PRIMEIRO projeto dela). O PDF tinha 3
# páginas e UMA ESTOUROU O TEMPO. Sobraram 2 pranchas medidas (129,1 e 116,4) e
# o teto virou 168 m². Ele zerou "Mezanino — área total 255,66 m²" — número que
# estava ESCRITO NA PRANCHA, não chute da IA. O prédio tem 592,08 m² no quadro
# de dados; 255 m² de mezanino é plausível, e a maior prancha medida é só um
# pavimento.
#
# 🔑 A falha foi de PREMISSA: apertar o teto supõe que medimos o bastante pra
# saber o tamanho do imóvel. Quando uma prancha não foi medida, a gente SABE que
# não sabe — e apertar ali é cobrar do cliente uma falha nossa.
TEKOA = {
    "p1": _prancha("TEKOA RESERVA_EXE_REV01.pdf", 116.4),
    "p2": _prancha("TEKOA RESERVA_EXE_REV01.pdf", 129.1),
}
SOMA_TEKOA = 245.5          # teto antigo: 319,2
MAIOR_TEKOA = 129.1         # teto novo:   167,8


def test_MEDICAO_INCOMPLETA_nao_aperta_o_teto():
    """🩸 O mezanino da karina. 255,66 não cabe em 1,3 × 129,1, mas a gente só
    mediu 2 das 3 páginas — não temos base pra dizer que é demais."""
    it = _Item("Laje do mezanino", "m²", 255.66)
    main._apply_area_honesty([it], pdfvec_m2=SOMA_TEKOA,
                             pdfvec_por_prancha=TEKOA,
                             medicao_incompleta=True)
    assert it.quantity == 255.66, (
        "zerou uma área que estava escrita na prancha, apertando o teto em cima "
        "de uma medição que a gente sabia estar incompleta")


def test_CONTROLE_com_a_medicao_COMPLETA_o_teto_continua_apertando():
    """🧪 O conserto não pode desligar a trava: medição completa, teto aperta.
    Se este teste cair junto com o de cima, a exceção virou regra."""
    it = _Item("Laje do mezanino", "m²", 255.66)
    main._apply_area_honesty([it], pdfvec_m2=SOMA_TEKOA,
                             pdfvec_por_prancha=TEKOA,
                             medicao_incompleta=False)
    assert it.quantity == 0, (
        "com todas as pranchas medidas o teto tem que valer — senão a trava 3 "
        "voltou a ser decorativa")


def test_CONTROLE_medicao_incompleta_NAO_libera_o_absurdo():
    """🪤 Voltar pro teto antigo não é abrir a porteira: o teto da soma continua
    valendo, e número que não cabe nem nele segue zerado."""
    it = _Item("Laje do mezanino", "m²", 5000.0)
    main._apply_area_honesty([it], pdfvec_m2=SOMA_TEKOA,
                             pdfvec_por_prancha=TEKOA,
                             medicao_incompleta=True)
    assert it.quantity == 0, "medição incompleta virou porta aberta"


def test_o_caller_avisa_o_teto_de_que_faltou_prancha():
    """Guarda de ponto de chamada — o controle abaixo prova que sabe reprovar."""
    limpo = "\n".join(l for l in _fonte().splitlines()
                      if not l.lstrip().startswith("#"))
    assert "medicao_incompleta=bool(_pdfvec_falhas_flag)" in limpo, (
        "o motor sabe que uma prancha falhou e não conta isso pro teto")


def test_CONTROLE_a_checagem_de_chamada_sabe_REPROVAR():
    falso = "            # medicao_incompleta=bool(_pdfvec_falhas_flag)"
    limpo = "\n".join(l for l in falso.splitlines()
                      if not l.lstrip().startswith("#"))
    assert "medicao_incompleta=bool(_pdfvec_falhas_flag)" not in limpo
