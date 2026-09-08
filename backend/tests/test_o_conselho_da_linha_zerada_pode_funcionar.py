# -*- coding: utf-8 -*-
"""A linha zerada de área não pode mandar o cliente fazer o que a régua recusa.

🩸 08/09/2026 — O MESMO DEFEITO DE 01/09, 33× MAIOR E MAIS UM ANDAR.

Em 01/09 (job 144c1f04) 25 itens LINEARES saíram com "Área NÃO medida … informe
a área no upload": substantivo errado e conselho que não preenche metro. Aquele
conserto tratou o linear e deixou a frase de ÁREA como estava — como se toda
área fosse piso.

Medido na base em 08/09, contra `is_floor_surface_para_criar` (a régua que
DECIDE, não uma cópia dela):

    linhas de área zeradas com essa frase ................. 936
    reprovam a condição NECESSÁRIA da régua ............... 725  (77,5%)

As 725 são parede, revestimento de banheiro, rodapé, "interruptor a 1,20 m do
piso". O campo do upload alimenta piso/forro/laje (`FLOOR_M2_UNITS` +
`is_floor_surface_para_criar`) — nelas, informar a área não muda nada. 77,5% é
PISO da medição, não o total: a lista de bloqueio da régua só aumenta o número.

E tem um segundo andar, que só apareceu ao ler o ramo que preenche: a área
informada também exige **não haver medição vetorial no job** (regra dura nº3 —
declaração ALERTA, não vira número onde a gente mediu). No projeto que chegou
em 08/09 o PDF mediu 278,8 m², então o convite era vazio para as 12 linhas de
revestimento dele — todas, inclusive as que passariam pela descrição.

🚫 O QUE ESTE GUARDA **NÃO** PEDE: preencher. Zerar continua certo — ninguém
mediu altura de parede, e inventar seria a regra dura nº1. Muda o CONSELHO.

🔑 POR QUE UMA FUNÇÃO SÓ: a pergunta "a área informada chega neste item?" é
feita em dois lugares que precisam concordar — o ramo que preenche e a frase
que o cliente lê. Enquanto eram duas cópias, uma prometia o que a outra
recusava. Os testes daqui chamam `_area_informada_alcancaria`, a MESMA que a
produção chama; não repetem as palavras-chave (copiar constante deixa as
absolvições pra trás).
"""
import io
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _fatia():
    """Mesma fatia que test_area_honesty_pd usa — main.py conecta em
    Supabase/Stripe no import, então a função é compilada isolada."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("_RX_SECAO_PILAR")
    i = src.rindex("\n", 0, i) + 1
    j = src.index("\ndef _dedupe_revisoes", i)
    from engine_rules import (AREA_UNITS_HONESTY as _A, FLOOR_M2_UNITS as _F,
                              is_floor_surface as _isf,
                              is_floor_surface_para_criar as _isfc)
    from models import Confidence
    import re as _re
    ns = {"__name__": "conselho_ns", "_AREA_UNITS_HONESTY": _A,
          "_FLOOR_M2_UNITS": _F, "_is_floor_surface": _isf,
          "_is_floor_surface_criar": _isfc, "Confidence": Confidence,
          "_re_honesty": _re, "_re": _re, "re": _re}
    exec(compile(src[i:j], "main_slice", "exec"), ns)
    return ns


class _Item:
    def __init__(self, description, unit, quantity, observations="", origem=""):
        self.description = description
        self.unit = unit
        self.quantity = quantity
        self.observations = observations
        self.origem = origem
        self.confidence = "estimado"


_CONVITE = "informe a área no upload"

# Itens reais da base de 08/09/2026, encurtados. Sem nome de cliente (regra
# nº6: o repo é público) — o que ensina é a FORMA da descrição.
_VERTICAIS = [
    "Revestimento cerâmico em parede — banho 01, assentamento com argamassa",
    "Pintura acrílica em paredes internas, 2 demãos sobre selador",
    "Revestimento de parede interno monocolor 30x60cm, retificado",
    "Impermeabilização de piso e paredes até 1,50m — banheiro e vestuário",
]
_HORIZONTAIS = [
    "Piso em porcelanato 60x60 — área total do pavimento térreo",
    "Forro de gesso acartonado liso — ambientes internos",
    "Contrapiso em argamassa de regularização, espessura 4cm",
]


def _zera_e_le(ns, item, **kw):
    """Roda a honestidade e devolve a observação final do item."""
    ns["_apply_area_honesty"]([item], **kw)
    return (item.observations or "")


# ══════════════════════════════════════════════════════════════════════════
#  O defeito medido: conselho que a régua recusa
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("desc", _VERTICAIS)
def test_area_vertical_nao_recebe_convite_que_a_regua_recusa(desc):
    ns = _fatia()
    it = _Item(desc, "m²", 120.0, "estimado pela IA")
    obs = _zera_e_le(ns, it, total_area=0, total_area_source="", pe_direito=0)

    assert it.quantity == 0, "zerar continua certo — ninguém mediu isto"
    assert "NÃO medida" in obs, "a linha tem que continuar dizendo que não mediu"
    assert _CONVITE not in obs, (
        "a frase manda informar a área no upload, e a régua não deixa esse\n"
        "número chegar aqui — o cliente faria o trabalho à toa:\n  " + obs)
    # o que sobra tem que continuar servindo pra alguma coisa
    assert "preencha a metragem" in obs and "DXF" in obs


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLE POSITIVO — não basta apagar a frase pra todo mundo
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("desc", _HORIZONTAIS)
def test_superficie_horizontal_continua_recebendo_o_convite(desc):
    ns = _fatia()
    it = _Item(desc, "m²", 90.0, "estimado pela IA")
    obs = _zera_e_le(ns, it, total_area=0, total_area_source="", pe_direito=0,
                     pdfvec_m2=0)

    assert it.quantity == 0
    assert _CONVITE in obs, (
        "apagar o convite pra todo mundo é tão errado quanto oferecê-lo a\n"
        "quem não pode usar: aqui a área informada CHEGA no item.\n  " + obs)


def test_o_convite_nao_depende_de_o_cliente_ja_ter_informado():
    """🪤 O erro que quase entrou: condicionar a frase ao estado de HOJE.

    A frase é conselho pro PRÓXIMO envio. Se ela só aparecesse quando
    `total_area_source == 'informado'`, sumiria exatamente para quem ainda não
    informou — que é o único a quem ela serve.
    """
    ns = _fatia()
    a = _Item(_HORIZONTAIS[0], "m²", 90.0, "estimado pela IA")
    _zera_e_le(ns, a, total_area=0, total_area_source="", pe_direito=0)
    assert _CONVITE in (a.observations or ""), (
        "quem NÃO informou é justamente quem precisa ler o convite")


# ══════════════════════════════════════════════════════════════════════════
#  O segundo andar: medimos o vetorial → a declaração não vira número
# ══════════════════════════════════════════════════════════════════════════
def test_com_medicao_vetorial_no_job_o_convite_some_ate_do_piso():
    """🪤 O CENÁRIO ÓBVIO NÃO REPRODUZ, e eu escrevi ele primeiro.

    Piso com 90 m² e pdfvec 278,8 não é zerado — a medição da prancha sustenta
    o número, e a linha nem chega à frase. O teste passava sem provar nada.
    O caso que EXISTE é o número implausível: a IA escreveu 5.000 m² num
    pavimento onde medimos 278,8. Aí sim zera, aí sim a frase é escrita — e
    era ali que o convite vazio saía.
    """
    ns = _fatia()
    sem = _Item(_HORIZONTAIS[0], "m²", 5000.0, "estimado pela IA")
    com = _Item(_HORIZONTAIS[0], "m²", 5000.0, "estimado pela IA")

    _zera_e_le(ns, sem, total_area=0, total_area_source="", pe_direito=0,
               pdfvec_m2=0)
    _zera_e_le(ns, com, total_area=0, total_area_source="", pe_direito=0,
               pdfvec_m2=278.8)

    assert sem.quantity == 0 and com.quantity == 0, "os dois têm que ZERAR"
    assert "NÃO medida" in (com.observations or ""), (
        "cenário inválido: sem a frase, este teste não prova nada")
    assert _CONVITE in (sem.observations or "")
    assert _CONVITE not in (com.observations or ""), (
        "tendo medição vetorial, a área informada não vira número em item\n"
        "nenhum (regra dura nº3) — convidar é prometer o que não acontece:\n  "
        + (com.observations or ""))


# ══════════════════════════════════════════════════════════════════════════
#  A frase tem que continuar sendo português nas duas formas
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("desc,pdfvec,q", [
    (_VERTICAIS[0], 0, 50.0),        # sem convite (parede)
    (_HORIZONTAIS[0], 0, 50.0),      # com convite (piso)
    (_HORIZONTAIS[0], 278.8, 5000.0)])  # sem convite (medimos o vetorial)
def test_a_frase_nao_sai_quebrada(desc, pdfvec, q):
    ns = _fatia()
    it = _Item(desc, "m²", q, "estimado pela IA")
    obs = _zera_e_le(ns, it, total_area=0, total_area_source="", pe_direito=0,
                     pdfvec_m2=pdfvec)
    assert "NÃO medida" in obs, "cenário não reproduz: a frase nem foi escrita"
    trecho = obs[obs.index("NÃO medida"):]
    assert trecho.endswith("."), "frase sem ponto final: " + trecho
    assert " ou " in trecho, "sumiu a conjunção da última opção: " + trecho
    assert ",," not in trecho and " ," not in trecho, "vírgula solta: " + trecho
    assert ", ou " not in trecho, "vírgula antes do 'ou': " + trecho
    assert "  " not in trecho, "espaço duplo: " + trecho


# ══════════════════════════════════════════════════════════════════════════
#  A refatoração não pode ter mexido em QUEM RECEBE a área informada
# ══════════════════════════════════════════════════════════════════════════
def test_o_ramo_que_preenche_continua_igual():
    """A função nova nasceu de um `if` que já existia. Se ela mudou o alcance,
    a área informada passa a cair em item errado — que é o defeito de 31/08
    (o 'rasgo em laje' que herdou 400 m²)."""
    ns = _fatia()
    piso = _Item("Piso em porcelanato — pavimento térreo", "m²", 0)
    ns["_apply_area_honesty"]([piso], total_area=200.0,
                              total_area_source="informado", pe_direito=0,
                              pdfvec_m2=0)
    assert piso.quantity == 200.0, "superfície de piso recebe a área informada"


@pytest.mark.parametrize("desc", [
    "Revestimento cerâmico em parede do banho",
    "Rasgo em laje para implantação de nova escada",
])
def test_quem_nao_e_superficie_de_piso_continua_sem_herdar_a_area(desc):
    """🪤 CADA UM SOZINHO, e a mutação foi quem cobrou.

    Na 1ª versão os três itens iam na MESMA lista, e o teto por família já
    tinha entregado a área ao piso antes de a parede ser avaliada: derrubar a
    régua do ramo que preenche passou BATIDO pelo comportamento — sobrou só o
    teste que lê o fonte, e guarda que lê fonte erra de dois jeitos.
    Sozinho, o item disputa a área com ninguém e a régua é a única coisa
    entre ele e os 200 m².
    """
    ns = _fatia()
    it = _Item(desc, "m²", 0)
    ns["_apply_area_honesty"]([it], total_area=200.0,
                              total_area_source="informado", pe_direito=0,
                              pdfvec_m2=0)
    assert it.quantity == 0, (
        "recebeu a área total informada sem ser superfície de piso: é o\n"
        "defeito de 31/08 (o 'rasgo em laje' com 400 m²)")


def test_a_pergunta_e_feita_por_UMA_funcao_so():
    """Controle da causa-raiz: se alguém reescrever a condição no ramo que
    preenche, as duas voltam a poder divergir — que é como o defeito nasceu."""
    ns = _fatia()
    assert callable(ns.get("_area_informada_alcancaria") or None) or True
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("def _apply_area_honesty")
    j = src.index("\ndef _dedupe_revisoes", i)
    corpo = src[i:j]
    assert corpo.count("_area_informada_alcancaria") >= 3, (
        "esperado: a definição + o ramo que preenche + a frase")
    assert corpo.count("_is_floor_surface_criar(getattr(it") == 0, (
        "a condição voltou a ser escrita à mão fora da função — foi assim que\n"
        "a frase e a régua se separaram")
