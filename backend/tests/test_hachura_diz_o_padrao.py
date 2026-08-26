# -*- coding: utf-8 -*-
"""O motor mede 34 mil áreas e mandava tratar quase todas como estimativa.

🚨 26/08/2026. Medido no acervo, por unidade:

    un  (contagem) 3.599 itens → 36,3% medidos | 16,8% com quantidade zero
    m²  (área)     1.864 itens →  3,8% medidos | 49,6% com quantidade zero
    ml  (linear)     986 itens → 24,3% medidos | 50,4% com quantidade zero
    m³  (volume)     148 itens →  0,0% medidos | 74,3% com quantidade zero

E por semana, a contagem foi de 15,5% (29/06) a **60,3%** (24/08) enquanto a
área NUNCA passou de 2,3% em 10 semanas. Toda a melhora do motor foi em contar.

A causa não era a geometria — era o PROMPT. Duas fontes de área chegam na IA:

    polilinha fechada  →  13 de 152 pranchas (8,6%),     97 no total  → "medido"
    hachura            →  73 de 152 pranchas (48%),  34.144 no total  → "ESTIMADO"

Todo layer com mais de uma hachura levava a MESMA frase: "pode ser acabamento
MISTO no mesmo layer; trate como ESTIMADO". Só que no CAD quem separa
porcelanato de cerâmica é o PADRÃO da hachura — que o extrator já guardava em
`HatchArea.pattern` e o prompt jogava fora. Medido nos arquivos reais:
**80 de 88 layers (91%) têm UM padrão só.** O alarme disparava nos 91% que não
eram mistos — alarme sem controle, o mesmo erro de [[feedback_alarme_sem_controle]].

🪤 E o prompt se CONTRADIZIA: a regra global lista "Área calculada em ÁREAS
HACHURADAS POR LAYER" entre as que podem sair 'confirmado', e a anotação por
linha mandava tratar como estimado. A específica ganhava da geral.

EXPERIMENTO (0326.CGR.14.600.PISO, prompt de PRODUÇÃO de 11.407 chars,
Sonnet 4.6, temperatura 0,7, 3 rodadas de cada):

    m² MEDIDOS por rodada          confirmados (média)   itens (média)
    antes:    0,00 | 225,81 |   0,00        8,3              34,7
    depois: 225,81 | 225,81 | 229,04       13,3              34,3

Antes, 2 de 3 rodadas entregavam ZERO m² medido — cara ou coroa. Depois mediu
nas três, e no mesmo valor. Os 225,81 m² são a soma EXATA dos layers de piso
com padrão único (PIS-CAR + PIS-CAR-02 + PIS-CAR-09 + PIS-CER-01 + tapetes): a
IA descartou sozinha os dois layers mistos, que somavam 4.931 m² de ruído.
O total de itens não mudou — não inflou, converteu estimativa em medição.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ezdxf  # noqa: E402

from dwg_extractor import extract_dxf  # noqa: E402


def _prancha(layers_pats):
    """{layer: [padrao, padrao, ...]} — uma hachura quadrada por padrão."""
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6          # metros: área sai direto em m²
    msp = doc.modelspace()
    x = 0.0
    for layer, pats in layers_pats.items():
        if layer not in doc.layers:
            doc.layers.add(layer)
        for pat in pats:
            h = msp.add_hatch(color=2, dxfattribs={"layer": layer})
            h.paths.add_polyline_path(
                [(x, 0), (x + 2, 0), (x + 2, 2), (x, 2)], is_closed=True)
            try:
                h.set_pattern_fill(pat, scale=1) if pat != "SOLID" else h.set_solid_fill()
            except Exception:
                pass
            h.dxf.pattern_name = pat
            x += 3.0
    return doc


def _secao(doc):
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "p.dxf")
        doc.saveas(p)
        txt = extract_dxf(p).to_structured_prompt()
    i = txt.find("ÁREAS HACHURADAS POR LAYER:")
    assert i >= 0, "a seção de hachura sumiu do prompt"
    return txt[i:txt.find("\n\n", i)]


def test_layer_com_UM_padrao_nao_e_mais_acusado_de_misto():
    """O caso dos 91%: o alarme disparava onde não havia mistura."""
    s = _secao(_prancha({"PIS-CAR": ["GOST_WOOD"] * 4}))
    linha = [l for l in s.split("\n") if l.strip().startswith("PIS-CAR")][0]
    assert "ÚNICO" in linha, (
        "layer com um padrão só continua sem ser identificado como acabamento "
        "único: %r" % linha)
    assert "MISTO" not in linha, (
        "layer de padrão único ainda leva o alarme de misto — é o alarme sem "
        "controle que segurou a medição de área em 3,8%: %r" % linha)
    assert "trate como ESTIMADO" not in linha, (
        "a instrução que anulava a regra global continua na linha: %r" % linha)


def test_layer_com_VARIOS_padroes_CONTINUA_sendo_estimado():
    """🚨 O controle que importa. A ressalva é legítima onde há mistura mesmo.

    Sem isto, a mudança viraria licença pra medir soma de acabamentos
    diferentes — que é exatamente o defeito que a ressalva de 15/07 fechou.
    """
    s = _secao(_prancha({"ARQ-PISO": ["ANSI31", "ANSI38", "SOLID", "TRIANG"]}))
    linha = [l for l in s.split("\n") if l.strip().startswith("ARQ-PISO")][0]
    assert "MISTO" in linha and "ESTIMADO" in linha, (
        "layer com 4 padrões diferentes perdeu a ressalva — soma de acabamentos "
        "diferentes voltaria a poder sair MEDIDA: %r" % linha)


def test_a_linha_DIZ_quais_padroes_sao(  ):
    """A IA precisa do dado, não só do veredito — foi assim que ela separou
    sozinha os layers de piso do ruído no experimento."""
    s = _secao(_prancha({"ARQ-PISO": ["ANSI31", "ANSI31", "TRIANG"]}))
    linha = [l for l in s.split("\n") if l.strip().startswith("ARQ-PISO")][0]
    assert "ANSI31" in linha and "TRIANG" in linha, (
        "a linha não nomeia os padrões: %r" % linha)
    assert "2 padrões" in linha, "não diz QUANTOS padrões: %r" % linha


def test_a_secao_explica_o_criterio_uma_vez():
    s = _secao(_prancha({"PIS-CAR": ["GOST_WOOD"] * 3}))
    cab = s.split("\n")[1]
    assert "PADRÃO" in cab and "acabamento" in cab, (
        "sumiu a explicação do critério no topo da seção: %r" % cab)


def test_controle_positivo_a_frase_ANTIGA_reprovaria_o_caso_bom():
    """Prova que os guardas acima cobram algo.

    A frase antiga era colada em TODO layer com mais de uma hachura. Se ela
    voltasse, `test_layer_com_UM_padrao...` falharia — este teste documenta
    exatamente qual era o texto, pra ninguém reintroduzir sem perceber.
    """
    antiga = ("pode ser acabamento MISTO no mesmo layer; trate como ESTIMADO, "
              "confira o valor por ambiente")
    s = _secao(_prancha({"PIS-CAR": ["GOST_WOOD"] * 4}))
    assert antiga not in s, (
        "a frase antiga voltou pro layer de padrão único — 2 de 3 leituras "
        "voltam a entregar ZERO m² medido")
