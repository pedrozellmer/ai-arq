# -*- coding: utf-8 -*-
"""Escala em POLEGADA deixa de ser lida como centímetro.

🩸 11/09/2026, job b0fa9104 — PDF de uma loja de shopping americana. O `/C` do
`/Measure` é um fator de conversão e a unidade dele mora no `/U` do mesmo
dicionário; o código nunca leu o `/U` e dividia por `_CM_PER_PT` sempre. Num PDF
do AutoCAD americano o `/C` vem em POLEGADA por ponto, e `C × 72` é o próprio
denominador (o "3/8\" = 1'-0\"" da prancha é 1:32).

📏 Medido nos 71 viewports daquele arquivo: `C × 72` caía em 1/2/4/8/12/16/24/
32/48 com erro ≤0,064%, e a cota ESCRITA de 13.997 mm confirmou 1:32 (−0,002%).
Lido como centímetro o motor usou 1:13 — comprimento ÷2,46, área ÷6,06.

🧪 CONTROLE medido nos 14 PDFs brasileiros locais (47 viewports): 7 saem com
`snapped=False` (1:433, 1:581, 1:579, 1:158) e NENHUM casa como polegada; zero
ambíguos. A regra não mexe no que já era lido certo.

🪤 Fixture SINTÉTICA (pikepdf), nunca o arquivo do cliente: ele foi apagado no
fim da auditoria, e arquivo de cliente não vira fixture de repositório público.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pikepdf  # noqa: E402
import pdfvec_layers as pl  # noqa: E402

_C_IMPERIAL_1_32 = 32 / 72.0          # C × 72 = 32
_C_IMPERIAL_1_48 = 48 / 72.0
_C_METRICO_1_50 = 50 * (2.54 / 72.0)  # C / _CM_PER_PT = 50


def _pdf_com_viewports(tmp_path, cs, u="", nome="sintetico.pdf"):
    """PDF de uma página com um viewport por `C` da lista. Sem desenho nenhum:
    o que está sob teste é a leitura do /Measure."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(2592, 1728))     # ~ARCH D em pontos
    page = pdf.pages[0]
    vps = []
    for i, c in enumerate(cs):
        nf = pikepdf.Dictionary(Type=pikepdf.Name("/NumberFormat"), C=float(c))
        if u:
            nf.U = pikepdf.String(u)
        medida = pikepdf.Dictionary(Type=pikepdf.Name("/Measure"),
                                    Subtype=pikepdf.Name("/RL"),
                                    X=pikepdf.Array([nf]))
        # viewports pequenos: a folha inteira é ignorada de propósito pelo motor
        x0 = 100 + i * 300
        vps.append(pikepdf.Dictionary(Type=pikepdf.Name("/Viewport"),
                                      BBox=pikepdf.Array([x0, 100, x0 + 250, 700]),
                                      Measure=medida))
    page.VP = pikepdf.Array(vps)
    alvo = str(tmp_path / nome)
    pdf.save(alvo)
    return alvo


def test_prancha_americana_le_1_32_e_nao_1_13(tmp_path):
    """O caso real: dois viewports imperiais, nenhum métrico."""
    arq = _pdf_com_viewports(tmp_path, [_C_IMPERIAL_1_32, _C_IMPERIAL_1_32])
    r = pl.scale_from_viewport(arq)
    assert r.get("main_scale") == 32, r
    assert r.get("unidade") == "polegada", r
    assert r.get("snapped") is True, "escala imperial exata não é chute"


def test_CONTROLE_prancha_brasileira_continua_em_centimetro(tmp_path):
    arq = _pdf_com_viewports(tmp_path, [_C_METRICO_1_50, _C_METRICO_1_50])
    r = pl.scale_from_viewport(arq)
    assert r.get("main_scale") == 50, r
    assert r.get("unidade") == "cm", r


def test_CONTROLE_um_viewport_solto_NAO_vira_polegada(tmp_path):
    """🪤 Exige DOIS: um número que caia por acaso na faixa imperial não pode
    trocar a unidade da prancha inteira."""
    arq = _pdf_com_viewports(tmp_path, [_C_IMPERIAL_1_32])
    r = pl.scale_from_viewport(arq)
    assert r.get("unidade") == "cm", r
    assert r.get("main_scale") != 32, r


def test_CONTROLE_mistura_fica_no_metrico(tmp_path):
    """Imperial e métrico padrão na mesma página: prancha não mistura sistema de
    unidade, então não dá pra afirmar — segue como antes.

    🩸 14/09, mutante sobrevivente: a 1ª versão deste controle tinha UM imperial
    e um métrico, e nunca chegava aos dois que a regra exige — então tirar a
    cláusula `casam_metrico == 0` passava verde. O cenário que separa é DOIS
    imperiais convivendo com um métrico."""
    arq = _pdf_com_viewports(tmp_path, [_C_IMPERIAL_1_32, _C_METRICO_1_50])
    r = pl.scale_from_viewport(arq)
    assert r.get("unidade") == "cm", r

    arq2 = _pdf_com_viewports(tmp_path, [_C_IMPERIAL_1_32, _C_IMPERIAL_1_48,
                                         _C_METRICO_1_50], nome="mistura3.pdf")
    r2 = pl.scale_from_viewport(arq2)
    assert r2.get("unidade") == "cm", (
        "dois imperiais bastaram pra trocar a unidade de uma página que TEM "
        "escala métrica padrão: %s" % r2)
    assert pl._pagina_e_imperial(
        [{"c": _C_IMPERIAL_1_32, "u": ""}, {"c": _C_IMPERIAL_1_48, "u": ""},
         {"c": _C_METRICO_1_50, "u": ""}]) is False


def test_o_U_declarado_MANDA_nos_dois_sentidos(tmp_path):
    """Declaração explícita ganha da estatística. Nos 47 viewports locais
    ninguém declarava — mas quando declara, é ela que vale."""
    arq = _pdf_com_viewports(tmp_path, [_C_IMPERIAL_1_32, _C_IMPERIAL_1_48], u="in")
    r = pl.scale_from_viewport(arq)
    assert r.get("unidade") == "polegada" and r.get("main_scale") in (32, 48), r

    arq2 = _pdf_com_viewports(tmp_path, [_C_IMPERIAL_1_32, _C_IMPERIAL_1_32],
                              u="cm", nome="metrico_declarado.pdf")
    r2 = pl.scale_from_viewport(arq2)
    assert r2.get("unidade") == "cm", (
        "o /U dizia centímetro e a estatística passou por cima: %s" % r2)


def test_a_decisao_da_unidade_e_CHAMAVEL_e_exige_dois():
    """A regra mora fora do laço pra um teste conseguir chamar."""
    imp = {"c": _C_IMPERIAL_1_32, "u": ""}
    met = {"c": _C_METRICO_1_50, "u": ""}
    assert pl._pagina_e_imperial([imp, imp]) is True
    assert pl._pagina_e_imperial([imp]) is False
    assert pl._pagina_e_imperial([imp, met]) is False
    assert pl._pagina_e_imperial([met, met]) is False
    assert pl._pagina_e_imperial([]) is False
    assert pl._denominador_imperial(_C_IMPERIAL_1_32) == 32
    assert pl._denominador_imperial(_C_METRICO_1_50) is None
