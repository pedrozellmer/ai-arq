# -*- coding: utf-8 -*-
"""Pilar com o MESMO rótulo em dois retângulos da MESMA seção não sai [MEDIDO].

🩸 26/09/2026 — job 32a27efc, prancha 0007: a folha tinha duas plantas (dois
níveis) e P3..P7 estavam desenhados nas duas. `count_pillars` tira duplicata
só por CENTRO (contorno duplo), então contou 33 retângulos — 28 rótulos
distintos — e o `sorted(set(nomes))` escondia a repetição. O prompt dizia
"[MEDIDO] seção …: 33 un", e a linha saiu com selo confirmado.

🔑 O conserto só AVISA: o número continua o dos desenhos (33). "É o mesmo
pilar" é hipótese — pode ser outro pilar com o mesmo nome. Vira [REFERÊNCIA]
com os dois números e os nomes repetidos.

Tudo sintético (retângulos e rótulos genéricos).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from structural_extractor import StructRect, count_pillars, structural_prompt_section  # noqa: E402


class _T:
    def __init__(self, text, x, y):
        self.text = text
        self.position = (x, y)
        self.height = 50.0
        self.layer = "TEXTO"


class _NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _r(cx, w=0.19, h=0.30):
    return StructRect("EST-PILAR", w, h, w * 1000, h * 1000, cx, 0)


def test_POSITIVO_mesmo_rotulo_em_dois_desenhos_da_mesma_secao_vira_REFERENCIA():
    p = count_pillars(_NS(struct_rects=[_r(0), _r(40000), _r(3000)],
                          texts=[_T("P3", 0, 250), _T("P3", 40000, 250), _T("P8", 3000, 250)],
                          blocks=[]))
    s = p["por_secao"][0]
    assert s["repetidos"] == ["P3"]
    assert s["qtd"] == 3 and s["distintos"] == 2
    assert p["rects_qtd"] == 3 and p["total"] == 3, "o número NÃO muda — só o aviso"
    txt = structural_prompt_section({"pilares": p})
    assert "[REFERÊNCIA] 3 pilares contados" in txt
    assert "[REFERÊNCIA] seção 19x30 cm: 3 desenhos de pilar (P3, P8)" in txt
    assert "P3 aparece(m) em mais de um desenho: 2 pilares distintos pelo nome" in txt
    assert 'Gere o item com 3, confidence="estimado"' in txt
    assert "[MEDIDO] seção" not in txt and "[MEDIDO] 3 pilares" not in txt
    # a regra geral logo abaixo não pode desdizer a linha [REFERÊNCIA]
    assert "quantidade literal, [MEDIDO] = confirmado e [REFERÊNCIA] = estimado." in txt
    assert "quantidade literal, confirmado." not in txt


def test_POSITIVO_uma_secao_repetida_e_outra_nao_o_cabecalho_ja_e_REFERENCIA():
    """Basta UMA seção com rótulo repetido para o total não ser [MEDIDO]; a
    outra seção, sem repetição, segue [MEDIDO]."""
    p = count_pillars(_NS(struct_rects=[_r(0), _r(40000), _r(20000, w=0.40, h=0.40)],
                          texts=[_T("P3", 0, 250), _T("P3", 40000, 250), _T("P9", 20000, 350)],
                          blocks=[]))
    txt = structural_prompt_section({"pilares": p})
    assert "[REFERÊNCIA] 3 pilares contados" in txt and "[MEDIDO] 3 pilares" not in txt
    assert "[REFERÊNCIA] seção 19x30 cm: 2 desenhos de pilar (P3)" in txt
    assert "[MEDIDO] seção 40x40 cm: 1 un (P9)" in txt


def test_NEGATIVO_rotulos_distintos_seguem_MEDIDO():
    p = count_pillars(_NS(struct_rects=[_r(0, h=0.40), _r(3000, h=0.40)],
                          texts=[_T("P1", 0, 300), _T("P7", 3000, 300)], blocks=[]))
    assert p["por_secao"][0]["repetidos"] == [] and p["por_secao"][0]["distintos"] == 2
    txt = structural_prompt_section({"pilares": p})
    assert "[MEDIDO] 2 pilares contados" in txt
    assert "[MEDIDO] seção 19x40 cm: 2 un (P1, P7)" in txt
    assert "[REFERÊNCIA]" not in txt.split("PILARES", 1)[1]
    assert "quantidade literal, confirmado. A seção veio da geometria (medida)." in txt


def test_NEGATIVO_retangulo_sem_rotulo_nao_e_repeticao():
    """Um pilar rotulado e outro sem rótulo: 2 distintos, segue [MEDIDO]."""
    p = count_pillars(_NS(struct_rects=[_r(0), _r(3000)], texts=[_T("P33", 0, 250)], blocks=[]))
    s = p["por_secao"][0]
    assert s["repetidos"] == [] and s["distintos"] == 2 and s["qtd"] == 2
    txt = structural_prompt_section({"pilares": p})
    assert "[MEDIDO] 2 pilares contados" in txt and "[MEDIDO] seção 19x30 cm: 2 un (P33)" in txt


def test_NEGATIVO_mesmo_rotulo_em_secoes_diferentes_sao_pilares_diferentes():
    """P33 novo 19x30 e P33 existente 40x40: seções diferentes, nada repetido."""
    p = count_pillars(_NS(struct_rects=[_r(0), _r(20000, w=0.40, h=0.40)],
                          texts=[_T("P33", 0, 250), _T("P33", 20000, 350)], blocks=[]))
    assert len(p["por_secao"]) == 2
    assert all(s["repetidos"] == [] and s["distintos"] == 1 for s in p["por_secao"])
    txt = structural_prompt_section({"pilares": p})
    assert "[MEDIDO] 2 pilares contados" in txt and "[REFERÊNCIA]" not in txt.split("PILARES", 1)[1]
