# -*- coding: utf-8 -*-
"""A área que o cliente INFORMA não vira quantidade de item (31/08/2026).

🩸 CASO FLAVIO (job f271473f, cliente novo, 16 PDFs, 31/08). Ele informou
400 m² no upload. A planilha saiu com **0% medido** e SEIS itens em m² com a
quantidade 400 — a área que ele mesmo digitou. Entre eles:

    "Rasgo em laje de concreto armado para implantação de nova escada" → 400 m²
    "Área Gourmet"  → 400 m²   (a própria observação do item dizia 18,05 m²)

Um rasgo de laje pra escada caracol com 400 m². Seis superfícies de 400 m² num
imóvel de 400 m² = 2.400 m² de piso e forro. O engenheiro bate o olho e perde a
confiança na planilha inteira — e ele TEM razão.

A causa: o ramo que carimba a área informada não olhava NENHUM valor. Bastava
o item ser superfície horizontal e o cliente ter informado a metragem.

As três travas, todas do mesmo princípio — **declaração do cliente é base pra
linha vazia, nunca substituto de número que já existe**:
  (a) só linha ZERADA;
  (b) não usa a declaração quando houve medição vetorial no job;
  (c) no máximo uma superfície por família (piso, forro) herda a área total.

🪤 Estes testes CHAMAM `_apply_area_honesty`. O guarda que lê fonte não pegaria
nada disto — a regra vive no valor, não no texto.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class _Item:
    def __init__(self, desc, unit, qty, obs="", origem="", conf="estimado"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.observations = obs
        self.origem = origem
        self.confidence = conf


def _flavio():
    """A configuração literal do caso, com os itens que saíram com 400."""
    return [
        _Item("Rasgo em laje de concreto armado para implantação de nova escada",
              "m²", 0),
        _Item("Área Gourmet — piso a definir", "m²", 18.05,
              obs="A prancha indica 'AGUARDAR PROJETO EXECUTIVO' (18,05 m²)"),
        _Item("Piso em tábua corrida de madeira Tauari", "m²", 0),
        _Item("Forro — pintura Branco Fosco", "m²", 0),
    ]


def test_rasgo_de_laje_NAO_herda_a_area_da_casa():
    """O item mais visível do estrago: um vão de escada com a área do imóvel."""
    itens = _flavio()
    main._apply_area_honesty(itens, total_area=400, total_area_source="informado",
                             pe_direito=3)
    rasgo = itens[0]
    assert rasgo.quantity != 400, (
        "o rasgo de laje voltou a herdar a área total do projeto")


def test_numero_que_ja_existia_NAO_VIRA_a_area_da_casa():
    """A Área Gourmet tinha 18,05 escrito na prancha e virou 400.

    🪤 Escrevi este teste na 1a versão exigindo que o 18,05 fosse PRESERVADO —
    e ele falhou. O certo era o meu teste, não o código: o 18,05 veio da IA
    LENDO a prancha, não da geometria, e a regra dura nº1 zera área lida por
    IA por design (caso Catarina, 20/07) — o número do desenho fica preservado
    no TEXTO da observação, pro cliente conferir.
    O ganho deste conserto é não virar 400. Preencher com o valor lido é outra
    decisão (o resgate de linha zerada), e não é esta."""
    itens = _flavio()
    main._apply_area_honesty(itens, total_area=400, total_area_source="informado",
                             pe_direito=3)
    gourmet = itens[1]
    assert gourmet.quantity != 400, (
        "a área informada sobrescreveu um número que a IA leu do desenho")
    assert "18,05" in (gourmet.observations or ""), (
        "o número que estava no desenho sumiu da observação")


def test_o_ESTRAGO_INTEIRO_do_caso_flavio_encolhe():
    """A conta que o cliente enxerga: quantas superfícies saem com a área da
    casa inteira. Eram SEIS num imóvel de 400 m² (2.400 m² de piso e forro)."""
    itens = _flavio()
    main._apply_area_honesty(itens, total_area=400, total_area_source="informado",
                             pe_direito=3)
    com400 = [i.description for i in itens if i.quantity == 400]
    assert len(com400) <= 2, "mais de 2 superfícies herdaram a área: " + str(com400)
    assert not any("rasgo" in d.lower() for d in com400)


def test_no_maximo_UMA_superficie_por_familia_herda_a_area():
    """6 itens de 400 m² num imóvel de 400 m² é aritmeticamente impossível."""
    itens = [_Item("Piso cerâmico", "m²", 0), _Item("Piso vinílico", "m²", 0),
             _Item("Piso laminado", "m²", 0), _Item("Forro de gesso", "m²", 0),
             _Item("Forro mineral", "m²", 0)]
    main._apply_area_honesty(itens, total_area=400, total_area_source="informado")
    com400 = [i for i in itens if i.quantity == 400]
    assert len(com400) <= 2, (
        "mais de uma superfície por família herdou a área total: "
        + str([i.description for i in com400]))


def test_havendo_medicao_vetorial_a_declaracao_NAO_vira_valor():
    """Regra nº3: declaração do cliente ALERTA, não vira número. Se o motor
    mediu, o que vale é a medição."""
    itens = [_Item("Piso cerâmico", "m²", 0)]
    main._apply_area_honesty(itens, total_area=400, total_area_source="informado",
                             pdfvec_m2=741.8)
    assert itens[0].quantity != 400, (
        "com medição vetorial no job, a área declarada ainda virou quantidade")


def test_CONTROLE_o_caso_legitimo_continua_funcionando():
    """A regra existe pra ajudar: planta sem cota, item de piso zerado, cliente
    informou a metragem. ISSO tem que continuar preenchendo — senão o conserto
    trocou um erro por outro."""
    itens = [_Item("Piso — área total da planta baixa", "m²", 0)]
    preench, _zer = main._apply_area_honesty(
        itens, total_area=120, total_area_source="informado")
    assert itens[0].quantity == 120, "o caso legítimo parou de ser preenchido"
    assert preench == 1
    assert "informada por você" in (itens[0].observations or "").lower()


def test_CONTROLE_piso_de_escada_ainda_e_superficie():
    """🪤 A tentação era bloquear a palavra 'escada' pra pegar o rasgo. Piso de
    escada É superfície e tem que continuar sendo — bloqueie o ATO (rasgo,
    abertura, demolição), nunca o objeto."""
    from engine_rules import is_floor_surface
    assert is_floor_surface("Piso da escada em granito") is True
    assert is_floor_surface("Rasgo em laje para nova escada") is False


def test_CONTROLE_revisao_do_cliente_continua_intocada():
    """Regra dura nº7: o que veio da revisão do cliente não se toca."""
    it = _Item("Piso vinílico", "m²", 45.30, origem="revisao_cliente")
    main._apply_area_honesty([it], total_area=310, total_area_source="informado")
    assert it.quantity == 45.30


def test_a_observacao_do_pdf_nao_promete_medir_o_item():
    """🩸 A observação carimbava a SOMA do job inteiro como se fosse a medição
    daquele item: um item de 18 m² recebia "Medido da GEOMETRIA do PDF (741.80
    m² de ambientes)". Enquanto a medição não for guardada por prancha, a frase
    vai SEM número — dizer menos é melhor que dizer errado."""
    it = _Item("Piso cerâmico", "m²", 50.0)
    main._apply_area_honesty([it], pdfvec_m2=741.8)
    obs = (it.observations or "").lower()
    assert "741" not in obs, (
        "a observação do item voltou a citar a soma do job como medição dele")
