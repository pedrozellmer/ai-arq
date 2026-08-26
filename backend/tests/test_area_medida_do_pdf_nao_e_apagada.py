# -*- coding: utf-8 -*-
"""O motor mediu a área do PDF, mandou a IA usar — e depois apagou.

🚨 26/08/2026, caso **Construtora Mr** (job das 12:50, cliente novo do dia).
O log conta o filme inteiro:

    12:51  pdfvec:promo         3 ambientes, 13,6 m² medidos da geometria vetorial
                                "SEM prova de cota — injetado como estimado"
    12:52  motor:consenso-area  campo=total_area n=0 leituras=[]
    12:53  motor:honestidade    preenchidos=0 zerados=9

`_apply_area_honesty` só reconhece `origem='dxf_geom'`, então apagou os 9. E
o contador `zerados` só sobe quando a quantidade era **maior que zero** — ou
seja, havia número e ele foi apagado.

A planilha que ele **baixou às 13:20** ficou assim:

    0 m²  Piso cerâmico ou porcelanato        0 m²  Pintura látex acrílica
    0 m²  Forro em gesso acartonado           0 m²  Massa corrida
    0 m²  Parede em alvenaria de bloco        0 m²  Revestimento de banheiro
    0 m²  Parede em drywall                   0 m²  Demolição de paredes
    0 ml  Rodapé

E a observação que sobrou dizia *"Área NÃO medida (lida de PDF por IA, não da
geometria)"* — **falso**: foi medida da geometria vetorial do PDF. As contagens
saíram certas (11 pontos de esgoto, 10 tomadas, 8 luminárias, 6 portas), então
ele recebeu tudo que se conta e nada do que se mede.

🔑 **Não é decisão de produto nova.** A de 12/08 (Hospital 2 de julho, onde 56
ambientes e 1.167 m² viraram ZERO) já definiu: medição de PDF sem prova de cota
VALE, como estimativa com a procedência escrita. O passo de injeção implementa
essa decisão; a regra de honestidade é que não ficava sabendo dela.

🚫 E continua NÃO virando 'confirmado': a escala veio do carimbo, e carimbo é
declaração, não prova — mesma família do "cabeçalho mente a unidade", que já
custou erro de 1000×.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_M2_MEDIDO = 13.6          # o que o motor vetorial mediu no PDF dele


def _fatia():
    """Roda só o pedaço do main.py com a honestidade (importar o módulo inteiro
    abre conexão com Supabase/Stripe). Mesmo molde de test_area_honesty_pd.py."""
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


class _Item:
    def __init__(self, description, unit, quantity, observations="", origem=""):
        self.description = description
        self.unit = unit
        self.quantity = quantity
        self.observations = observations
        self.origem = origem
        self.confidence = None


def _piso(q=13.6):
    return _Item("Piso cerâmico ou porcelanato — tipo, dimensão, cor e "
                 "fabricante a confirmar", "m²", q)


def _forro(q=13.6):
    return _Item("Forro em gesso acartonado ou forro modular — tipo, "
                 "espessura a confirmar", "m²", q)


def _valor(it):
    return float(getattr(it, "quantity", 0) or 0)


def test_a_area_medida_do_PDF_sobrevive():
    """O caso do Construtora Mr, do jeito que a produção roda."""
    h = _fatia()["_apply_area_honesty"]
    piso, forro = _piso(), _forro()
    h([piso, forro], total_area=0, total_area_source="", pe_direito=0,
      pdfvec_m2=_M2_MEDIDO)
    assert _valor(piso) == 13.6, (
        "o piso medido do PDF foi apagado de novo — o cliente recebe 0 m² numa "
        "planta que a gente MEDIU")
    assert _valor(forro) == 13.6, "o forro foi apagado"


def test_a_procedencia_vai_escrita_na_linha():
    """Estimativa sem procedência é chute. Com procedência é o que o produto
    promete entregar quando não dá pra provar a escala."""
    h = _fatia()["_apply_area_honesty"]
    piso = _piso()
    h([piso], total_area=0, total_area_source="", pe_direito=0,
      pdfvec_m2=_M2_MEDIDO)
    obs = (piso.observations or "").lower()
    assert "geometria do pdf" in obs, (
        "a linha não diz de onde veio o número: %r" % piso.observations)
    assert "carimbo" in obs, "não avisa que a escala veio do carimbo"
    assert "não medida" not in obs and "nao medida" not in obs, (
        "sobrou o aviso ANTIGO dizendo que não foi medida — era justamente a "
        "frase falsa que o Construtora Mr recebeu")


def test_NUNCA_vira_confirmado():
    """🚨 Regra dura nº1. Carimbo é declaração, cota é prova."""
    h = _fatia()["_apply_area_honesty"]
    piso = _piso()
    h([piso], total_area=0, total_area_source="", pe_direito=0,
      pdfvec_m2=_M2_MEDIDO)
    assert str(getattr(piso.confidence, "value", piso.confidence)) == "estimado", (
        "área de PDF com escala de carimbo saiu como MEDIDA: %r" % piso.confidence)


def test_parede_e_pintura_CONTINUAM_zerando():
    """🚨 Trava nº2. O motor vetorial mede o CHÃO dos ambientes, não a altura.

    Parede e pintura dependem do pé-direito, que ninguém mediu. Se passassem,
    a gente estaria entregando a multiplicação do LLM como se fosse medição.
    """
    h = _fatia()["_apply_area_honesty"]
    parede = _Item("Parede em alvenaria de bloco cerâmico 9×19×19cm", "m²", 12.0)
    pintura = _Item("Pintura látex acrílica — cor a confirmar", "m²", 11.0)
    h([parede, pintura], total_area=0, total_area_source="", pe_direito=0,
      pdfvec_m2=_M2_MEDIDO)
    assert _valor(parede) == 0, "parede sobreviveu — não medimos altura nenhuma"
    assert _valor(pintura) == 0, "pintura sobreviveu — mesma coisa"


def test_numero_que_NAO_CABE_na_medicao_e_apagado():
    """🚨 Trava nº3. Sem ela, um chute da IA pegaria carona na medição.

    13,6 m² de ambientes não viram 310 m² de piso. O teto é 1,3× o medido.
    """
    h = _fatia()["_apply_area_honesty"]
    chute = _piso(310.0)
    h([chute], total_area=0, total_area_source="", pe_direito=0,
      pdfvec_m2=_M2_MEDIDO)
    assert _valor(chute) == 0, (
        "310 m² sobreviveram numa planta de 13,6 m² medidos — a trava de "
        "plausibilidade furou e a porta do m² inventado reabriu")


def test_sem_medicao_do_PDF_nada_muda():
    """Regressão: job sem motor vetorial se comporta EXATAMENTE como antes.

    O caso Catarina (20/07) é o motivo de a regra existir: Vision chuta
    "Forro Sala 52 m²" numa planta sem cota. Isso tem que continuar zerando.
    """
    h = _fatia()["_apply_area_honesty"]
    chute = _Item("Forro de gesso — Sala", "m²", 52.0)
    n_fill, blanked = h([chute], total_area=0, total_area_source="",
                        pe_direito=0, pdfvec_m2=0)
    assert _valor(chute) == 0, "m² de Vision sem medição sobreviveu"
    assert blanked == 1, "o contador de zerados parou de contar"


def test_edicao_do_cliente_continua_intocada():
    """🚨 Regra dura nº7: o que o cliente corrigiu não se toca, nunca."""
    h = _fatia()["_apply_area_honesty"]
    dele = _piso(45.30)
    dele.origem = "revisao_cliente"
    h([dele], total_area=0, total_area_source="", pe_direito=0,
      pdfvec_m2=_M2_MEDIDO)
    assert _valor(dele) == 45.30, "encostou no número que o cliente digitou"


def test_o_call_site_acumula_e_PASSA_a_medicao():
    """🪤 Guarda de CALL SITE: a função pode estar certa e nunca receber o dado.

    Foi exatamente esse o defeito — `pdfvec` media, e a honestidade nunca
    ficava sabendo. Testar só a função não pega isso.
    """
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    corpo = chr(10).join(l for l in fonte.split(chr(10))
                         if not l.strip().startswith("#"))
    assert "_pdfvec_area_m2 = 0.0" in corpo, (
        "o acumulador da área medida no PDF sumiu")
    assert corpo.count("_pdfvec_area_m2 +=") >= 2, (
        "a soma não cobre os DOIS ramos da promoção (escala provada por cota e "
        "escala sem prova) — o caso do Construtora Mr é o segundo")
    assert "pdfvec_m2=_pv_m2" in corpo, (
        "o valor é acumulado e NÃO é passado pra honestidade — a função existe "
        "e nunca recebe o dado, que é o defeito de origem")
    i_soma = corpo.find("_pdfvec_area_m2 +=")
    i_uso = corpo.find("pdfvec_m2=_pv_m2")
    assert 0 < i_soma < i_uso, "soma depois de usar não serve pra nada"
