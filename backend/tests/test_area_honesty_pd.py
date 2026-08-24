# -*- coding: utf-8 -*-
"""A honestidade de área e a derivação por pé-direito, testadas JUNTAS.

🚨 Caso Tammyres (23/08/2026, job 66b4d692): ela informou 2,70 m no envio, a
leitura mediu 303,96 m de parede no layer A-WALL e a IA escreveu a conta na
observação de 3 itens. A honestidade zerou 2 (pintura e alvenaria) e deixou a
massa corrida com 817 m² — a mesma área. O cliente informou o dado e a conta
sumiu da planilha.

🚨 Auditoria do mesmo dia, 2ª rodada: o conserto acima criou dois problemas
piores, e é por isso que este arquivo passou a testar a CADEIA inteira em vez
de uma função sozinha:

  (2) preservar por TEXTO deixava passar m² inventado. O prompt do motor manda
      o modelo escrever "pé-direito informado" na observação — num job só-PDF
      ele inventa o perímetro e a frase vinha junto. Texto não é prova; prova é
      existir comprimento com origem 'dxf_geom' no mesmo job.

  (3) preservar a pintura do modelo DESLIGA a nossa derivação determinística
      (ela desiste quando já existe quantidade). A ordem honestidade →
      derivação é deliberada: a honestidade limpa o m² que o LLM multiplicou e
      a derivação preenche com Σ(comprimento medido) × PD × 2 faces. Sem isso
      passamos a entregar a aritmética do LLM, que é o componente NÃO
      determinístico do motor.

  (7) linha com número E com "Área NÃO medida — informe a área no upload" é
      instrução que, se obedecida, destrói o próprio número.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fatia():
    """Executa o pedaço do main.py que contém honestidade + derivações, sem
    importar o módulo inteiro (main.py conecta em Supabase/Stripe no import)."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("_RX_SECAO_PILAR")
    i = src.rindex("\n", 0, i) + 1
    j = src.index("\ndef _dedupe_revisoes", i)
    from engine_rules import (AREA_UNITS_HONESTY as _A, FLOOR_M2_UNITS as _F,
                              is_floor_surface as _isf)
    from models import Confidence
    import re as _re
    ns = {"__name__": "honesty_ns", "_AREA_UNITS_HONESTY": _A,
          "_FLOOR_M2_UNITS": _F, "_is_floor_surface": _isf,
          "Confidence": Confidence, "_re_honesty": _re, "_re": _re, "re": _re}
    exec(compile(src[i:j], "main_slice", "exec"), ns)
    return ns


def _carrega_funcao():
    return _fatia()["_apply_area_honesty"]


class _Item:
    """Suficiente pro que as funções leem — inclui `origem`, que é o campo que
    passou a decidir a preservação."""

    def __init__(self, description, unit, quantity, observations="", origem=""):
        self.description = description
        self.unit = unit
        self.quantity = quantity
        self.observations = observations
        self.origem = origem
        self.confidence = None


def _parede_medida(metros=303.96):
    """A prova de que o comprimento saiu da geometria, não do chute do modelo."""
    return _Item("Alvenaria de vedação — paredes internas", "m", metros,
                 "Medido no layer A-WALL", origem="dxf_geom")


# ══════════════════════════════════════════════════════════════════════════
#  A CADEIA: é assim que o process_job roda (honestidade e DEPOIS derivação)
# ══════════════════════════════════════════════════════════════════════════
def test_cadeia_entrega_a_conta_NOSSA_e_nao_a_do_modelo():
    """Tammyres, do jeito que a produção roda.

    O modelo escreveu 820,69 m² (= 303,96 × 2,70, UMA face). A nossa conta é
    303,96 × 2,70 × 2 faces = 1.641,4 m², que é o contrato documentado da
    derivação. Quem tem que sobreviver é a nossa.
    """
    ns = _fatia()
    honesty = ns["_apply_area_honesty"]
    pintura_ia = _Item("Pintura acrílica interna em paredes", "m²", 820.69,
                       "Derivado de: A-WALL = 303.96 ml × 2,70 m (pé-direito informado) = 820.69 m²")
    itens = [_parede_medida(), pintura_ia]

    honesty(itens, total_area=0, total_area_source="", pe_direito=2.7)
    assert pintura_ia.quantity == 0, (
        "a honestidade tem que limpar o m² do LLM pra a derivação entrar — "
        "senão a linha fica com a aritmética do modelo")

    n = ns["_derive_pintura_pe_direito"](itens, 2.7)
    assert n == 1
    assert abs(pintura_ia.quantity - round(303.96 * 2.7 * 2, 1)) < 0.11, (
        "esperava a conta determinística (2 faces), veio %s" % pintura_ia.quantity)
    assert pintura_ia.origem == "deriv_pd", "a conta nossa tem que ficar marcada"
    assert str(getattr(pintura_ia.confidence, "value", pintura_ia.confidence)) == "estimado"


def test_cadeia_nao_zera_de_novo_o_que_a_derivacao_preencheu():
    """A honestidade roda outra vez (releitura, /inform-area). O que é NOSSO
    sobrevive pela ORIGEM, sem depender de reconhecer texto."""
    ns = _fatia()
    it = _Item("Pintura acrílica interna em paredes", "m²", 1641.4,
               "⚠ ESTIMADO — 303.9 m de parede × pé-direito 2.70 m informado por você × 2 faces.",
               origem="deriv_pd")
    ns["_apply_area_honesty"]([it], total_area=0, total_area_source="", pe_direito=2.7)
    assert it.quantity == 1641.4


# ══════════════════════════════════════════════════════════════════════════
#  ACHADO 2 — texto não é prova
# ══════════════════════════════════════════════════════════════════════════
def test_sem_comprimento_medido_a_frase_nao_salva_o_numero():
    """Job só-PDF: o modelo inventa o perímetro e escreve a frase que o nosso
    próprio prompt pediu. Isso é o caso Catarina voltando pela porta do
    pé-direito — tem que zerar."""
    f = _carrega_funcao()
    it = _Item("Massa corrida sobre paredes", "m²", 817.0,
               "Perímetro aprox. 120 m × 2,70 m (pé-direito informado por você) — planta em PDF",
               origem="vision_pdf")
    f([it], total_area=0, total_area_source="", pe_direito=2.7)
    assert it.quantity == 0, "m² sem geometria nenhuma sobreviveu só por causa do texto"


def test_com_comprimento_medido_o_item_sem_derivacao_nossa_e_preservado():
    """Massa corrida não tem derivação determinística nossa. Se o job MEDIU
    parede de verdade, a conta tem procedência e fica — como estimado."""
    f = _carrega_funcao()
    massa = _Item("Massa corrida sobre paredes", "m²", 817.0,
                  "A-WALL = 303.96 ml × 2,70 m (pé-direito informado) = 817 m²")
    f([_parede_medida(), massa], total_area=0, total_area_source="", pe_direito=2.7)
    assert massa.quantity == 817.0
    assert "informado por você" in (massa.observations or "").lower()
    assert str(getattr(massa.confidence, "value", massa.confidence)) == "estimado"


# ══════════════════════════════════════════════════════════════════════════
#  ACHADO 7 — a linha não pode ter número E mandar apagar o número
# ══════════════════════════════════════════════════════════════════════════
def test_linha_preenchida_nao_carrega_o_aviso_que_destroi_o_numero():
    ns = _fatia()
    alvo = _Item("Pintura látex paredes internas", "m²", 0,
                 "requer pé-direito | Área NÃO medida (lida de PDF por IA, não da "
                 "geometria) — preencha a metragem, informe a área no upload ou "
                 "envie o DXF pra medir.")
    ns["_derive_pintura_pe_direito"]([_parede_medida(100.0), alvo], 2.7)
    assert alvo.quantity > 0
    obs = (alvo.observations or "").lower()
    assert "não medida" not in obs and "informe a área no upload" not in obs, (
        "linha com número não pode mandar o cliente fazer o que apaga o número:\n" + obs)


def test_preservada_tambem_sai_sem_o_aviso_contraditorio():
    f = _carrega_funcao()
    massa = _Item("Massa corrida sobre paredes", "m²", 817.0,
                  "A-WALL = 303.96 ml × 2,70 m (pé-direito informado) | Área NÃO medida — "
                  "informe a área no upload")
    f([_parede_medida(), massa], total_area=0, total_area_source="", pe_direito=2.7)
    assert massa.quantity == 817.0
    assert "não medida" not in (massa.observations or "").lower()


# ══════════════════════════════════════════════════════════════════════════
#  O que já valia antes e continua valendo
# ══════════════════════════════════════════════════════════════════════════
def test_zera_m2_inventado_quando_nao_ha_pe_direito():
    f = _carrega_funcao()
    it = _Item("Forro de gesso — Sala 3", "m²", 52.0, "Estimado da planta")
    f([it], total_area=0, total_area_source="", pe_direito=0)
    assert it.quantity == 0
    assert "não medida" in (it.observations or "").lower()


def test_nao_preserva_quando_a_obs_nao_cita_o_pe_direito_informado():
    f = _carrega_funcao()
    it = _Item("Revestimento cerâmico", "m²", 120.0, "Estimado por índice de densidade")
    f([_parede_medida(), it], total_area=0, total_area_source="", pe_direito=2.7)
    assert it.quantity == 0


def test_medido_do_cad_nunca_e_tocado():
    f = _carrega_funcao()
    it = _Item("Piso porcelanato", "m²", 118.5, "Hachura única no layer ARQ-PISO",
               origem="dxf_geom")
    f([it], total_area=0, total_area_source="", pe_direito=0)
    assert it.quantity == 118.5
    assert it.confidence is None       # não mexeu em nada


def test_area_informada_preenche_piso_e_forro():
    f = _carrega_funcao()
    piso = _Item("Piso vinílico", "m²", 0, "Área NÃO medida — informe a área no upload")
    n_fill, _ = f([piso], total_area=118.5, total_area_source="informado", pe_direito=0)
    assert n_fill == 1 and piso.quantity == 118.5
    # o rótulo "(não medida)" PODE ficar — ele descreve a procediência. O que não
    # pode é a INSTRUÇÃO que apaga o número se o cliente obedecer.
    assert "informe a área no upload" not in (piso.observations or "").lower()
    assert "informada por você" in (piso.observations or "").lower()


# ══════════════════════════════════════════════════════════════════════════
#  O regex, com controle negativo
# ══════════════════════════════════════════════════════════════════════════
def test_regex_casa_o_texto_do_proprio_motor():
    rx = _fatia()["_RX_DERIV_PD"]
    reais = [
        "⚠ ESTIMADO — 303.9 m de parede × pé-direito 2.70 m informado por você × 2 faces.",
        "📐 ÁREA COM O PÉ-DIREITO QUE VOCÊ INFORMOU: 303.96 m × 2.7 m = 820.69 m² por face",
        "Derivado das seções contadas: 3 seção(ões) × pé-direito 2,7 m (informado por você)",
        "Derivado de: A-WALL = 303.96 ml × 2,70 m (pé-direito informado) = 820.69 m²",
    ]
    for t in reais:
        assert rx.search(t), "o regex não casa texto que o PRÓPRIO motor escreve: " + t


def test_regex_nao_casa_texto_sem_pe_direito_informado():
    rx = _fatia()["_RX_DERIV_PD"]
    for t in ["Estimado por índice de densidade (0,8 un/m²)",
              "Altura de 2,70 m adotada por padrão de mercado",
              "Pé-direito não informado — não deu pra derivar",
              "Área lida da legenda da prancha"]:
        assert not rx.search(t), "o regex casa texto que NÃO tem procedência: " + t


# ══════════════════════════════════════════════════════════════════════════
#  Guardas dos helpers novos
# ══════════════════════════════════════════════════════════════════════════
def test_tem_comprimento_medido_exige_origem_dxf_geom():
    f = _fatia()["_tem_comprimento_medido"]
    assert f([_parede_medida()])
    assert not f([_Item("Parede", "m", 303.96, "", origem="vision_pdf")])
    assert not f([_Item("Parede", "m", 0, "", origem="dxf_geom")])
    assert not f([_Item("Piso", "m²", 118.5, "", origem="dxf_geom")])
    assert not f([])


def test_derivacao_deterministica_cobre_pintura_de_parede_e_forma_de_pilar():
    f = _fatia()["_tem_derivacao_deterministica"]
    assert f("Pintura acrílica interna em paredes", "m²")
    assert f("Fôrma de pilar em chapa compensada", "m²")
    # teto/forro não: a conta comprimento × PD é de parede
    assert not f("Pintura do teto", "m²")
    assert not f("Pintura de forro de gesso", "m²")
    # unidade errada não
    assert not f("Pintura acrílica interna em paredes", "m")
    assert not f("Massa corrida sobre paredes", "m²")
