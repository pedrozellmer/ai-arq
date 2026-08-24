"""A honestidade de área não pode zerar o que foi derivado do pé-direito informado.

🚨 Caso Tammyres (23/08/2026, job 66b4d692): ela informou 2,70 m no envio, a
leitura mediu 303,96 m de parede no layer A-WALL e a IA escreveu a conta na
observação de 3 itens. A honestidade zerou 2 (pintura e alvenaria) e deixou a
massa corrida com 817 m² — a mesma área. O cliente informou o dado e a conta
sumiu da planilha.
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _carrega_funcao():
    """Extrai _apply_area_honesty do main.py sem importar o módulo inteiro
    (main.py conecta em Supabase/Stripe na importação)."""
    import io
    import re
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "main.py"), encoding="utf-8").read()
    i = src.index("import re as _re_honesty")
    j = src.index("\ndef _dedupe_revisoes", i)
    from engine_rules import (AREA_UNITS_HONESTY as _A, FLOOR_M2_UNITS as _F,
                              is_floor_surface as _isf)
    from models import Confidence
    ns = {"__name__": "honesty_ns", "_AREA_UNITS_HONESTY": _A,
          "_FLOOR_M2_UNITS": _F, "_is_floor_surface": _isf, "Confidence": Confidence}
    exec(compile(src[i:j], "main_slice", "exec"), ns)
    return ns["_apply_area_honesty"]


class _Item:
    def __init__(self, description, unit, quantity, observations="", origem=""):
        self.description = description
        self.unit = unit
        self.quantity = quantity
        self.observations = observations
        self.origem = origem
        self.confidence = None


def test_preserva_area_derivada_do_pe_direito_informado():
    f = _carrega_funcao()
    it = _Item("Pintura acrílica interna em paredes", "m²", 820.69,
               "Derivado de: A-WALL = 303.96 ml × 2,70 m (pé-direito informado) = 820.69 m²")
    f([it], total_area=0, total_area_source="", pe_direito=2.7)
    assert it.quantity == 820.69, "área derivada do pé-direito informado foi zerada"
    assert "informado por você" in (it.observations or "").lower()


def test_zera_m2_inventado_quando_nao_ha_pe_direito():
    """Controle negativo: o caso Catarina (Vision chutando m²) segue zerado."""
    f = _carrega_funcao()
    it = _Item("Forro de gesso — Sala", "m²", 52.0, "Estimativa visual da planta")
    f([it], total_area=0, total_area_source="", pe_direito=0)
    assert it.quantity == 0, "m² inventado deveria ter sido zerado"


def test_nao_preserva_quando_a_obs_nao_cita_o_pe_direito_informado():
    """Controle negativo: PD informado no job não libera qualquer m²."""
    f = _carrega_funcao()
    it = _Item("Piso cerâmico", "m²", 99.0, "Estimativa por ambiente")
    f([it], total_area=0, total_area_source="", pe_direito=2.7)
    assert it.quantity == 0


def test_medido_do_cad_nunca_e_tocado():
    f = _carrega_funcao()
    it = _Item("Piso", "m²", 186.52, "hachura A-FLOR-PATT", origem="dxf_geom")
    f([it], total_area=0, total_area_source="", pe_direito=2.7)
    assert it.quantity == 186.52


# ── 23/08/2026, auditoria do dia: os controles negativos originais cobriam só o
# fácil. Estes vieram dos textos REAIS que o motor e a IA escrevem. ──────────
def _rx():
    import io as _io, os as _os, re as _re
    src = _io.open(_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                                 "main.py"), encoding="utf-8").read()
    i = src.index("_RX_DERIV_PD = _re_honesty.compile(")
    ns = {"_re_honesty": _re}
    exec(src[i:src.index("\n\n", i)], ns)
    return ns["_RX_DERIV_PD"]


def test_regex_casa_o_texto_do_proprio_motor():
    rx = _rx()
    reais = [
        "Derivado de: A-WALL = 303.96 ml × 2,70 m (pé-direito informado) = 820.69 m²",
        "⚠ ESTIMADO — 303.9 m de parede × pé-direito 2.70 m informado por você × 2 faces.",
        "Derivado das seções contadas: 3 seção(ões) × pé-direito 2.7 m (informado por você) × contagem",
        "ÁREA COM O PÉ-DIREITO QUE VOCÊ INFORMOU: 820,69 m²",
    ]
    faltando = [t for t in reais if not rx.search(t)]
    assert not faltando, f"o regex nao reconhece texto que o motor escreve: {faltando}"


def test_regex_nao_casa_texto_sem_pe_direito_informado():
    rx = _rx()
    nao = [
        "Estimativa visual da planta, sem cota",
        "Pé-direito de projeto: 2,80 m conforme corte AA",
        "Área informada por você (não medida): assumido = área total do projeto",
    ]
    casou = [t for t in nao if rx.search(t)]
    assert not casou, f"o regex libera preservacao indevida em: {casou}"
