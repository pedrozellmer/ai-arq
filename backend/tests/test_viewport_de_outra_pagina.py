# -*- coding: utf-8 -*-
"""Lista de viewports de OUTRA folha não dá escala a esta página (H68c).

🩸 01/10/2026 — estudo do acervo. Um PDF de várias pranchas trazia, em cada
página, a lista /VP de TODAS as folhas juntas. Numa página menor metida no meio,
a maioria das caixas ficava fora da página — e as poucas que caíam dentro, por
acaso, davam 1:50 a uma folha de detalhes que diz "ESCALA 1:25" no texto. Sem o
/VP, a escala vem do carimbo/texto, como antes do H68.

🪤 Fixture SINTÉTICA (pikepdf), nunca arquivo de cliente.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pikepdf  # noqa: E402
import pdfvec_layers as pl  # noqa: E402

_PAPEL = 25.4 / 72.0                            # papel 1:1 em mm
_M = lambda den: den * 2.54 / 72.0 / 100.0      # noqa: E731  /C em m/pt

_A0_DE_PE = (1684, 3370)
_A1_DEITADA = (2384, 1684)


def _pdf(tmp_path, pagina, vps, nome="sintetico.pdf"):
    """`vps` = [(C, (x0, y0, x1, y1)), ...] na página de tamanho `pagina`."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=pagina)
    lista = []
    for c, bb in vps:
        nf = pikepdf.Dictionary(Type=pikepdf.Name("/NumberFormat"), C=float(c))
        nf.U = pikepdf.String("")
        medida = pikepdf.Dictionary(Type=pikepdf.Name("/Measure"),
                                    Subtype=pikepdf.Name("/RL"), X=pikepdf.Array([nf]))
        lista.append(pikepdf.Dictionary(Type=pikepdf.Name("/Viewport"),
                                        BBox=pikepdf.Array(list(bb)), Measure=medida))
    pdf.pages[0].VP = pikepdf.Array(lista)
    alvo = str(tmp_path / nome)
    pdf.save(alvo)
    return alvo


# A lista "de todas as folhas": várias folhas A0 de pé + vistas a 1:50 que se
# espalham pela altura toda da A0 (y até ~3.270).
_DENTRO_DA_A1 = [(_M(50), (763, 115, 1626, 445)), (_M(50), (1952, 538, 2275, 861)),
                 (_M(50), (129, 392, 774, 1100)), (_M(50), (642, 404, 1625, 1324))]
_SO_NA_A0 = [(_PAPEL, (0, 0, 1683, 3370))] * 6 + [
    (_M(50), (153, 1368, 533, 3265)), (_M(50), (642, 1400, 1625, 2320)),
    (_M(50), (642, 2345, 1625, 3265)), (_M(50), (641, 690, 1625, 3265)),
    (_M(50), (92, 691, 1030, 3273)), (_M(50), (92, 754, 999, 3273))]


def test_lista_de_outra_folha_nao_da_escala(tmp_path):
    """O caso real: página A1 com a lista da A0 — 12 de 16 caixas fora."""
    arq = _pdf(tmp_path, _A1_DEITADA, _DENTRO_DA_A1 + _SO_NA_A0)
    assert pl.scale_from_viewport(arq) == {}


def test_CONTROLE_a_mesma_lista_na_folha_dela_le_1_50(tmp_path):
    """A MESMA lista na página A0 (todas as caixas dentro) segue dando 1:50 em
    metro — o H68 não perde nada nas folhas certas."""
    arq = _pdf(tmp_path, _A0_DE_PE, _DENTRO_DA_A1 + _SO_NA_A0)
    r = pl.scale_from_viewport(arq)
    assert r.get("main_scale") == 50, r
    assert r.get("unidade") == "m", r


def test_CONTROLE_minoria_fora_segue_valendo(tmp_path):
    """Poucas caixas fora (3 de 10) não derrubam a lista: o PDF real tinha 3 de
    28 fora nas folhas certas, e lá o carimbo diz 1/50 como o viewport."""
    fora = [(_M(50), (92, 691, 1030, 3273))] * 3
    dentro = [(_PAPEL, (0, 0, 2383, 1683))] + [(_M(50), (100, 100, 2200, 1500))] * 6
    arq = _pdf(tmp_path, _A1_DEITADA, dentro + fora)
    r = pl.scale_from_viewport(arq)
    assert r.get("main_scale") == 50, r


def test_CONTROLE_empate_fica_como_era(tmp_path):
    """Metade fora e metade dentro: não é MAIORIA → a lista vale (como antes)."""
    fora = [(_M(50), (92, 691, 1030, 3273))] * 3
    dentro = [(_M(50), (100, 100, 2200, 1500))] * 3
    arq = _pdf(tmp_path, _A1_DEITADA, dentro + fora)
    assert pl.scale_from_viewport(arq).get("main_scale") == 50


def test_folga_de_2_pontos_na_borda():
    """Caixa que passa da borda por até 2 pt (arredondamento do exportador)
    conta como dentro; 3 pt já é fora."""
    mb = [0, 0, 2384, 1684]
    assert not pl._fora_da_pagina([0, 0, 2386, 1686], mb)
    assert pl._fora_da_pagina([0, 0, 2387.5, 1684], mb)
    assert pl._fora_da_pagina([-3, 0, 100, 100], mb)


def test_caixa_com_os_cantos_invertidos():
    """O exportador escreve caixa com x0 > x1 (houve uma assim no PDF real): a
    conta usa o menor e o maior de cada eixo, não a ordem."""
    mb = [0, 0, 2384, 1684]
    assert pl._fora_da_pagina([2390, 0, 100, 100], mb)
    assert pl._fora_da_pagina([100, 1700, 200, 100], mb)
    assert pl._fora_da_pagina([100, 100, 200, -50], mb)       # passa da borda de BAIXO
    assert pl._fora_da_pagina([-50, 100, 200, 300], mb)
    assert not pl._fora_da_pagina([1382, 1165, 1193, 1547], mb)


def test_mediabox_que_nao_comeca_no_zero():
    """A MediaBox pode começar fora da origem: a conta usa as 4 bordas dela."""
    mb = [100, 200, 2484, 1884]
    assert not pl._fora_da_pagina([150, 250, 2400, 1800], mb)
    assert pl._fora_da_pagina([0, 0, 500, 500], mb)
    assert pl._fora_da_pagina([150, 250, 2400, 1890], mb)


def test_decisao_pura_conta_so_caixa_legivel():
    """Entrada sem /BBox legível não vota (nem pra dentro nem pra fora)."""
    mb = [0, 0, 1000, 1000]
    vps = [{"/BBox": [0, 0, 5000, 5000]}, {"/BBox": [0, 0, 5000, 5000]},
           {"/BBox": [0, 0, 500, 500]}, {"/BBox": None}, {}]
    assert pl._lista_de_outra_pagina(vps, mb) is True
    assert pl._lista_de_outra_pagina([{}, {"/BBox": None}], mb) is False
