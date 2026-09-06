# -*- coding: utf-8 -*-
"""Item de área zerado recebe a medição da PRÓPRIA prancha (31/08/2026).

🩸 CASO FLAVIO (job f271473f). O motor mediu 6 pranchas — 80,5 · 107,7 · 166,1
· 77,1 · 112,0 · 198,4 m² — e entregou 32 linhas de área ZERADAS. A medição
existia, por prancha, e não chegava a item nenhum.

🚨 ESTE É O ÚNICO PASSO DO PLANO QUE CRIA NÚMERO ONDE NÃO HAVIA. Todos os
outros consertos do dia TIRARAM número errado. Por isso as quatro travas, e
por isso metade dos testes deste arquivo são CONTROLES do que NÃO pode
acontecer:

  1. o selo continua ESTIMADO. Sempre. Nunca "confirmado" — a escala do PDF
     vem do carimbo, e carimbo é declaração, não prova (regra dura nº1);
  2. só linha ZERADA. Número que já existe é resposta de alguém;
  3. no máximo UM piso e UM forro por prancha — atribuir a área do pavimento a
     vários itens é o erro do "resumo geral somado em dobro" (28/08);
  4. na DÚVIDA, não preenche NADA. Dois itens da mesma família apontando pra
     mesma prancha deixam os dois zerados. Linha vazia é honesta; palpite não.

🪤 O casamento é por PREFIXO do nome do arquivo: `ref_sheet` pode chegar como
"planta.pdf (hint da IA)", e comparar a string inteira nunca casaria.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def _prancha(arquivo, m2, validada=True, scale=50):
    return {"arquivo": arquivo, "rooms_m2": m2, "n_rooms": 10, "walls_m": 0,
            "n_walls": 0, "grupo_maior_m2": m2, "scale": scale,
            "scale_src": "cotas" if validada else "carimbo",
            "escala_validada": validada, "cotas_batem": 29 if validada else 0}


PP = {"alv1_p0": _prancha("CC_AP_Alvenaria Terreo_R00.pdf", 80.5)}


def _selo(it):
    return str(getattr(it.confidence, "value", it.confidence))


def test_linha_zerada_recebe_a_medicao_da_prancha_dela():
    """O ganho: a linha para de sair vazia tendo medição."""
    it = _Item("Piso cerâmico", "m²", 0,
               ref_sheet="CC_AP_Alvenaria Terreo_R00.pdf (planta baixa)")
    main._apply_area_honesty([it], pdfvec_por_prancha=PP)
    assert it.quantity == 80.5
    assert "medidos nesta prancha" in (it.observations or "").lower()


def test_TRAVA_1_o_selo_continua_estimado():
    """🚨 Regra dura nº1. Medir a planta não é conferir o item."""
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="CC_AP_Alvenaria Terreo_R00.pdf")
    main._apply_area_honesty([it], pdfvec_por_prancha=PP)
    assert _selo(it) == "estimado", "item de PDF saiu confirmado — proibido"


def test_TRAVA_2_numero_que_ja_existe_NAO_VIRA_a_area_da_prancha():
    """🪤 Escrevi este teste exigindo que o 42,0 fosse PRESERVADO, e ele falhou.
    O certo era o teste, não o código: um número que a IA leu (sem prova de
    geometria) é ZERADO pela regra de honestidade que já existia — é o mesmo
    comportamento do caso cliente-21, 20/07.
    O que o passo 7 garante aqui é o que ele NÃO faz: não sobrescreve o número
    existente com a área da prancha. Se um dia o valor lido bater com a
    medição, quem resgata é o passo 6, comparando NÚMERO, não a família."""
    it = _Item("Piso cerâmico", "m²", 42.0, ref_sheet="CC_AP_Alvenaria Terreo_R00.pdf")
    main._apply_area_honesty([it], pdfvec_por_prancha=PP)
    assert it.quantity != 80.5, (
        "o passo 7 sobrescreveu um número que já existia com a área da prancha")


def test_TRAVA_3_so_um_piso_e_um_forro_por_prancha():
    """Um piso e um forro da MESMA prancha podem ser preenchidos; dois pisos
    da mesma prancha, não (é o caso ambíguo da trava 4)."""
    piso = _Item("Piso cerâmico", "m²", 0, ref_sheet="CC_AP_Alvenaria Terreo_R00.pdf")
    forro = _Item("Forro de gesso", "m²", 0, ref_sheet="CC_AP_Alvenaria Terreo_R00.pdf")
    main._apply_area_honesty([piso, forro], pdfvec_por_prancha=PP)
    assert piso.quantity == 80.5 and forro.quantity == 80.5


def test_TRAVA_4_na_duvida_NAO_preenche_nenhum():
    """🧪 O teste que mais importa deste arquivo. Dois pisos apontando pra
    mesma prancha: não dá pra saber qual é a área dela — então nenhum recebe.
    Errar pra menos é a regra da casa."""
    a = _Item("Piso cerâmico", "m²", 0, ref_sheet="CC_AP_Alvenaria Terreo_R00.pdf")
    b = _Item("Piso vinílico", "m²", 0, ref_sheet="CC_AP_Alvenaria Terreo_R00.pdf")
    main._apply_area_honesty([a, b], pdfvec_por_prancha=PP)
    assert a.quantity == 0 and b.quantity == 0, (
        "com dois candidatos na mesma família e prancha, preencheu mesmo assim")


def test_item_de_OUTRA_prancha_nao_recebe():
    """A medição é da prancha dele, não de qualquer prancha do job."""
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="CC_AP_Luminotecnico_R00.pdf")
    main._apply_area_honesty([it], pdfvec_por_prancha=PP)
    assert it.quantity == 0


def test_item_SEM_ref_sheet_nao_recebe():
    """Sem saber de qual prancha o item veio, não há atribuição possível."""
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="")
    main._apply_area_honesty([it], pdfvec_por_prancha=PP)
    assert it.quantity == 0


def test_CONTROLE_rasgo_de_laje_nao_recebe_a_area_da_prancha():
    """🪤 O item do caso cliente-14. Intervenção parcial não é superfície — a
    peneira do passo 1 tem que valer aqui também, senão o rasgo troca 400 m²
    por 80,5 m² e continua absurdo."""
    it = _Item("Rasgo em laje para nova escada", "m²", 0,
               ref_sheet="CC_AP_Alvenaria Terreo_R00.pdf")
    main._apply_area_honesty([it], pdfvec_por_prancha=PP)
    assert it.quantity == 0


def test_CONTROLE_item_medido_do_CAD_e_intocado():
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="CC_AP_Alvenaria Terreo_R00.pdf",
               origem="dxf_geom")
    main._apply_area_honesty([it], pdfvec_por_prancha=PP)
    assert it.quantity == 0, "encostou em item que veio da geometria do CAD"


def test_CONTROLE_sem_medicao_nada_muda():
    """Sem prancha medida, o comportamento é exatamente o de antes."""
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="qualquer.pdf")
    main._apply_area_honesty([it], pdfvec_por_prancha=None)
    assert it.quantity == 0


def test_a_procedencia_diz_de_qual_prancha_veio():
    """Estimativa sem procedência é chute. Tem que dizer a prancha e a escala."""
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="CC_AP_Alvenaria Terreo_R00.pdf")
    main._apply_area_honesty([it], pdfvec_por_prancha=PP)
    obs = (it.observations or "")
    assert "CC_AP_Alvenaria Terreo_R00.pdf" in obs
    assert "1:50" in obs
    assert "cota da própria prancha" in obs


# ─────────────────────────────────────────────────────────────────────────────
# 🚨 31/08, AUDITORIA DO MESMO DIA. Os 11 testes acima usam um `PP` com UMA
# prancha só — e por isso não viram dois furos graves, os dois provados rodando:
#   1. PDF com várias páginas: o item levava a MAIOR página do arquivo (erro de
#      2,46× no caso testado) e a observação jurava ser "esta prancha";
#   2. nome de arquivo que é prefixo de outro: o item recebia o número da
#      prancha ERRADA, e quem decidia era a ordem de processamento.
# Os dois erravam pra MAIS — contra as quatro travas que o cabeçalho promete.
# ─────────────────────────────────────────────────────────────────────────────

def _pp2(*pares):
    return {("p%d" % i): _prancha(a, m) for i, (a, m) in enumerate(pares)}


def test_PDF_MULTIPAGINA_nao_preenche_nenhum_item():
    """🩸 O item do térreo recebia a área da COBERTURA. `ref_sheet` guarda só o
    nome do arquivo, nunca a página — então não há como saber de qual pavimento
    o item veio. Arquivo com 2+ páginas medidas é ambíguo: não preenche."""
    pp = {"proj_p0": _prancha("PROJETO.pdf", 80.5),
          "proj_p1": _prancha("PROJETO.pdf", 107.7),
          "proj_p2": _prancha("PROJETO.pdf", 198.4)}
    it = _Item("Piso cerâmico do térreo", "m²", 0, ref_sheet="PROJETO.pdf")
    main._apply_area_honesty([it], pdfvec_por_prancha=pp)
    assert it.quantity == 0, (
        "levou a maior página do arquivo (%.2f) como se fosse a prancha dele"
        % it.quantity)


def test_PDF_MULTIPAGINA_avisa_o_cliente():
    """Recusar em silêncio faz parecer que o motor não mediu nada."""
    pp = {"a_p0": _prancha("PROJETO.pdf", 80.5), "a_p1": _prancha("PROJETO.pdf", 198.4)}
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="PROJETO.pdf")
    main._apply_area_honesty([it], pdfvec_por_prancha=pp)
    amb = getattr(main._apply_area_honesty, "ultimo_ambiguos", [])
    assert any(a[1] == "multipagina" for a in amb), (
        "não registrou a ambiguidade — o cliente não fica sabendo")


def test_NOME_PREFIXO_o_casamento_EXATO_ganha_do_prefixo():
    """🩸 "PLANTA BAIXA.pdf" (80,5) e "PLANTA BAIXA 2 PAVIMENTO.pdf" (198,4):
    o item do 2º pavimento recebia 80,5 e a observação nomeava a prancha errada."""
    pp = _pp2(("PLANTA BAIXA.pdf", 80.5), ("PLANTA BAIXA 2 PAVIMENTO.pdf", 198.4))
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="PLANTA BAIXA 2 PAVIMENTO.pdf")
    main._apply_area_honesty([it], pdfvec_por_prancha=pp)
    assert it.quantity == 198.4, "casou com o prefixo em vez do nome exato"
    assert "PLANTA BAIXA 2 PAVIMENTO.pdf" in (it.observations or "")


def test_NOME_PREFIXO_nao_depende_da_ORDEM_das_pranchas():
    """🪤 Quem decidia o vencedor era a ordem de processamento: invertendo o
    dict, o MESMO item saía com outro número."""
    for pares in (((("PLANTA BAIXA.pdf", 80.5)), (("PLANTA BAIXA 2 PAV.pdf", 198.4))),
                  ((("PLANTA BAIXA 2 PAV.pdf", 198.4)), (("PLANTA BAIXA.pdf", 80.5)))):
        it = _Item("Piso cerâmico", "m²", 0, ref_sheet="PLANTA BAIXA 2 PAV.pdf")
        main._apply_area_honesty([it], pdfvec_por_prancha=_pp2(*pares))
        assert it.quantity == 198.4, "a ordem das pranchas mudou o resultado"


def test_NOME_CURTO_nao_captura_prancha_alheia():
    """🪤 "01.pdf" capturava qualquer ref_sheet que contivesse "01"."""
    pp = _pp2(("01.pdf", 12.0), ("ARQ-R01.pdf", 240.0))
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="ARQ-R01.pdf")
    main._apply_area_honesty([it], pdfvec_por_prancha=pp)
    assert it.quantity == 240.0, "o nome curto sequestrou o item da outra prancha"


def test_o_hint_da_IA_no_ref_sheet_CONTINUA_casando():
    """O casamento por prefixo existe pra isto — não pode ter morrido no conserto."""
    it = _Item("Piso cerâmico", "m²", 0,
               ref_sheet="CC_AP_Alvenaria Terreo_R00.pdf (planta baixa, hint da IA)")
    main._apply_area_honesty([it], pdfvec_por_prancha=PP)
    assert it.quantity == 80.5
