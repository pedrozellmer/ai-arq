# -*- coding: utf-8 -*-
"""O "Veio de" da consolidação grava cada parte INTEIRA.

🩸 05/10/2026 — a parte ia cortada: só o último trecho depois do " — ", em 28
caracteres ("especificação, dimensão e ma 2.0"). A especificação de cada parte
sumia — "Bomba submersível … — 2 variantes" juntava duas bombas de modelos
diferentes e a linha só mostrava a 1ª. Medido no banco (90 dias, jobs de
cliente): 384 linhas consolidadas em 95 jobs; numa amostra de 40, 8–12 juntavam
coisas diferentes. A regra de NÃO fundir fica para depois, medida no acervo;
aqui é só o rastro.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import main as m                                   # noqa: E402


class _It:
    def __init__(self, desc, qty, unit="un", num="1", disc="Hidráulica"):
        self.description, self.quantity, self.unit = desc, qty, unit
        self.item_num, self.discipline = num, disc
        self.observations, self.confidence, self.origem = "", "estimado", ""
        self.ref_sheet, self.marca, self.codigo_fabricante = "p.dxf", "", ""
        self.cor, self.spec_origem = "", ""


def test_a_especificacao_de_cada_parte_fica():
    r = m._resumo_do_grupo([
        _It("Bomba submersível para poço de drenagem — modelo Marca-A 1¼\", 220V monofásica", 1.0),
        _It("Bomba submersível para poço de drenagem — modelo Marca-B XK 350P, 220V", 1.0)])
    assert "modelo Marca-A 1¼\", 220V monofásica 1.0" in r, r
    assert "modelo Marca-B XK 350P, 220V 1.0" in r, r


def test_o_trecho_do_meio_tambem_fica():
    """A capacidade estava no MEIO da descrição: o corte antigo guardava só "sala"."""
    r = m._resumo_do_grupo([_It("Split hi-wall — 18.000 BTU — sala", 2.0),
                            _It("Split hi-wall — 24.000 BTU — quarto", 2.0)])
    assert "18.000 BTU" in r and "24.000 BTU" in r, r


def test_as_marcas_que_outras_regras_leem_nao_viajam():
    """A observação da linha consolidada não pode carregar "a definir",
    "conforme projeto", "layer"… de uma parte (há regras que leem isso)."""
    r = m._resumo_do_grupo([_It("Ar-condicionado — especificação a definir conforme projeto", 1.0),
                            _It("Ar-condicionado — medido no layer AC-X", 1.0)])
    low = r.lower()
    assert "a definir" not in low and "conforme projeto" not in low and "layer" not in low, r
    assert "Ar-condicionado" in r


def test_a_parte_muito_longa_tem_rede():
    r = m._resumo_do_grupo([_It("X" * 300, 1.0)])
    assert len(r) < 220 and r.startswith("X" * 200 + "…"), len(r)


def test_CONTROLE_o_teto_de_partes_continua():
    grupo = [_It("Luminária — sala %d" % i, 0.5) for i in range(12)]
    r = m._resumo_do_grupo(grupo)
    assert "(+8)" in r and r.count(" · ") == 4, r


def test_na_consolidacao_a_observacao_traz_as_partes_inteiras():
    """Pelo caminho de verdade (`_consolidate_items`)."""
    nomes = ["Lajes", "Vigas", "Pilares", "Escadas"]
    itens = [_It("Concreto estrutural fck=30MPa — %s (pavimento tipo)" % n, 0.5, unit="m³",
                 num=str(i + 1), disc="Estrutura") for i, n in enumerate(nomes)]
    saida = m._consolidate_items(itens)
    assert len(saida) == 1, [i.description for i in saida]
    obs = saida[0].observations
    for n in nomes:
        assert "Concreto estrutural fck=30MPa — %s (pavimento tipo) 0.5" % n in obs, obs
