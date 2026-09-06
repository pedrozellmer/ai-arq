# -*- coding: utf-8 -*-
"""O selo de medição sobrevive à consolidação — caso cliente-16 (30/08/2026).

🩸 O bug: o consolidador criava BudgetItem novo SEM `origem` em 6 lugares.
Item de m² MEDIDO por hachura no DXF (origem 'dxf_geom') era fundido entre
pranchas, perdia o selo, e `_apply_area_honesty` — que só poupa 'dxf_geom' —
zerava a medição com o carimbo "lida de PDF por IA". No eval ev502981 (motor
de 30/08, ANTES deste conserto): 2.528,97 m² de piso, 2.295,07 m² de
revestimento, 110,83 m² de forro, 127,71 m² de telha e 19,67 m² de ventilação
— todos medidos, todos ZERO na planilha.

Estes testes CHAMAM `_consolidate_items` e `_apply_area_honesty` de verdade.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import BudgetItem, Confidence  # noqa: E402


def _item(descr, qty, unit="m²", origem="dxf_geom", sheet="P1.dxf", disc="Pisos e Rodapés"):
    return BudgetItem(item_num="1", description=descr, unit=unit, quantity=qty,
                      observations="Fonte: área hachurada do layer A-FLOR-PATT = "
                                   f"{qty} m² (141 hachuras)",
                      ref_sheet=sheet, confidence=Confidence("estimado"),
                      discipline=disc, origem=origem)


def _consolida(itens):
    import main
    return main._consolidate_items(itens)


def test_fusao_de_mesma_qty_preserva_o_selo():
    """Passada 2 (o berço do caso cliente-16): 4 pranchas, mesma área medida."""
    itens = [_item("Piso — área total de padrões de piso (layer A-FLOR-PATT)",
                   2528.97, sheet=f"ARQ_HARMONIA_0{i}.dxf") for i in range(1, 5)]
    saida = _consolida(itens)
    piso = [x for x in saida if "Piso" in x.description]
    assert len(piso) == 1, [x.description for x in saida]
    assert piso[0].origem == "dxf_geom", (piso[0].origem, piso[0].observations)
    assert piso[0].quantity == 2528.97


def test_mesma_qty_com_UMA_medida_ja_e_medida():
    """O número mantido é idêntico ao medido — regra 'qualquer' da passada 2."""
    itens = ([_item("Forro — layer X", 110.83, origem="dxf_geom")]
             + [_item("Forro — layer X", 110.83, origem="", sheet=f"P{i}.pdf")
                for i in range(2, 4)])
    saida = _consolida(itens)
    forro = [x for x in saida if "Forro" in x.description]
    assert len(forro) == 1 and forro[0].origem == "dxf_geom"


def test_CONTROLE_soma_mista_NAO_ganha_selo():
    """🧪 Regra nº1: soma de medido + não-medido é parcialmente medida —
    consolidação por FAMÍLIA (soma) com origens mistas sai SEM selo."""
    itens = [
        _item("Porta conforme especificação 01", 1, unit="un", origem="dxf_geom",
              disc="Esquadrias"),
        _item("Porta conforme especificação 02", 1, unit="un", origem="",
              disc="Esquadrias"),
        _item("Porta conforme especificação 03", 1, unit="un", origem="",
              disc="Esquadrias"),
    ]
    saida = _consolida(itens)
    portas = [x for x in saida if "orta" in x.description]
    if len(portas) == 1:          # fundiu (é o esperado na passada 3)
        assert portas[0].origem == "", portas[0].origem
    else:                          # não fundiu: cada um mantém o seu — também ok
        assert {p.origem for p in portas} == {"dxf_geom", ""}


def test_o_zerador_POUPA_o_item_fundido_medido():
    """O fim da história: depois da fusão, _apply_area_honesty NÃO zera."""
    import main
    itens = [_item("Piso — área total (layer A-FLOR-PATT)", 2528.97,
                   sheet=f"AH_0{i}.dxf") for i in range(1, 5)]
    saida = _consolida(itens)
    fill, blank = main._apply_area_honesty(saida, 0, "", pe_direito=0)
    piso = [x for x in saida if "Piso" in x.description][0]
    assert piso.quantity == 2528.97, "o zerador matou m² MEDIDO de novo"
    assert blank == 0


def test_CONTROLE_POSITIVO_sem_selo_o_zerador_zera():
    """🧪 O zerador continua fazendo o trabalho dele: m² sem origem = zera
    (caso cliente-21 segue protegido)."""
    import main
    itens = [_item("Forro estimado pela IA", 52.0, origem="")]
    fill, blank = main._apply_area_honesty(itens, 0, "", pe_direito=0)
    assert itens[0].quantity == 0 and blank == 1


def test_specs_sobrevivem_a_fusao():
    """Marca/cor/spec_origem também eram descartados (família do achado de
    25/08 — escrito num lado, lido no outro)."""
    a = _item("Piso — layer A", 100.0)
    a.marca = "Portobello"
    a.cor = "cinza"
    a.spec_origem = "legenda da prancha"
    b = _item("Piso — layer A", 100.0, sheet="P2.dxf")
    saida = _consolida([a, b])
    piso = [x for x in saida if "Piso" in x.description][0]
    assert piso.marca == "Portobello" and piso.cor == "cinza"
