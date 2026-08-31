# -*- coding: utf-8 -*-
"""A peneira do ATO de intervenção não pode apagar medição que já existe.

🩸 31/08/2026 — BUG MEU, ACHADO PELA AUDITORIA DO MESMO DIA (algumas horas
depois de eu subir). Pra consertar o caso Flavio ("Rasgo em laje para nova
escada" herdando os 400 m² que o cliente digitou) eu acrescentei as palavras do
ATO — rasgo, abertura, vão, furo, recorte, demoli, remoç, shaft — dentro de
`FLOOR_AREA_BLOCK_KW`.

O erro: essa lista é a peneira de TRÊS ramos da honestidade, e só dois CRIAM
número. O terceiro PRESERVA a medição que o motor vetorial tirou do PDF. Com a
peneira alargada, o item real do job eva97d1d (Construtora Mr, 26/08) —
"Remoção de revestimento cerâmico existente em piso", 13,60 m² MEDIDOS da
geometria — passou a sair ZERADO, e a linha dizia as duas coisas ao mesmo
tempo: "Medido da GEOMETRIA do PDF" E "Área NÃO medida". É exatamente a frase
falsa que o conserto de 26/08 nasceu pra matar.

🔑 A REGRA QUE FICA: bloquear o ato de intervenção vale onde o motor vai
INVENTAR número a partir de uma declaração. Onde a medição é NOSSA, a palavra
na descrição não desmente a régua — um rasgo de 13,6 m² medidos é 13,6 m².
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from engine_rules import (is_floor_surface,            # noqa: E402
                          is_floor_surface_para_criar)


class _Item:
    def __init__(self, desc, unit, qty, obs="", ref_sheet="", origem="vision_pdf"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.observations = obs
        self.ref_sheet = ref_sheet
        self.origem = origem
        self.confidence = "estimado"


# o item literal do banco (job eva97d1d), com a observação que SÓ o ramo do
# pdfvec escreve — é a assinatura de que aquele número veio da geometria
_DESC_REAL = ("Remoção de revestimento cerâmico/porcelanato existente em piso "
              "dos ambientes a reformar")
_OBS_REAL = ("Medido da GEOMETRIA do PDF (13.60 m² de ambientes), com escala "
             "lida do carimbo e NÃO confirmada por cota.")


def test_o_item_REAL_do_construtora_mr_continua_com_os_13_60():
    """🧪 O caso que a auditoria usou como prova. Não é sintético: é a linha
    que está no banco desde 26/08."""
    it = _Item(_DESC_REAL, "m²", 13.6, obs=_OBS_REAL)
    main._apply_area_honesty([it], pdfvec_m2=13.6)
    assert it.quantity == 13.6, (
        "a peneira do ATO apagou 13,60 m² MEDIDOS da geometria do PDF")


def test_a_linha_nao_pode_dizer_MEDIDO_e_NAO_MEDIDA_ao_mesmo_tempo():
    """🪤 O sintoma mais feio do bug: as duas frases na mesma observação."""
    it = _Item(_DESC_REAL, "m²", 13.6, obs=_OBS_REAL)
    main._apply_area_honesty([it], pdfvec_m2=13.6)
    o = (it.observations or "").lower()
    assert not ("geometria do pdf" in o and "não medida" in o), (
        "a observação afirma e nega a medição na mesma linha: %s" % it.observations)


def test_CONTROLE_o_rasgo_continua_SEM_herdar_a_area_informada():
    """O conserto de hoje não pode ser desfeito: quem CRIA número segue
    bloqueando o ato. É o item do caso Flavio."""
    it = _Item("Rasgo em laje de concreto armado para implantação de nova escada",
               "m²", 0)
    main._apply_area_honesty([it], total_area=400, total_area_source="informado")
    assert it.quantity == 0, "o rasgo voltou a herdar a área total informada"


def test_CONTROLE_o_rasgo_continua_SEM_receber_a_area_da_prancha():
    """Passo 7 também CRIA número — a peneira do ato vale lá."""
    pp = {"p0": {"arquivo": "planta.pdf", "rooms_m2": 80.5, "n_rooms": 10,
                 "walls_m": 0, "n_walls": 0, "grupo_maior_m2": 80.5, "scale": 50,
                 "scale_src": "cotas", "escala_validada": True, "cotas_batem": 29}}
    it = _Item("Rasgo em laje para nova escada", "m²", 0, ref_sheet="planta.pdf")
    main._apply_area_honesty([it], pdfvec_por_prancha=pp)
    assert it.quantity == 0


def test_as_duas_peneiras_sao_MESMO_diferentes():
    """Se as duas ficarem iguais de novo, o bug volta inteiro e calado."""
    d = "Remoção de piso cerâmico"
    assert is_floor_surface(d) is True, "a peneira de PRESERVAR bloqueou o ato"
    assert is_floor_surface_para_criar(d) is False, "a peneira de CRIAR deixou passar"


def test_CONTROLE_superficie_normal_passa_nas_DUAS():
    for d in ("Piso cerâmico 60x60", "Forro de gesso acartonado",
              "Piso da escada em granito"):
        assert is_floor_surface(d), d
        assert is_floor_surface_para_criar(d), d


def test_CONTROLE_o_que_a_peneira_antiga_ja_bloqueava_segue_bloqueado():
    """Rodapé e parede nunca foram superfície horizontal — nas duas peneiras."""
    for d in ("Rodapé em porcelanato", "Piso de parede do banheiro"):
        assert not is_floor_surface(d), d
        assert not is_floor_surface_para_criar(d), d
