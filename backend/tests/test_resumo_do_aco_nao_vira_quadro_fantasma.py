# -*- coding: utf-8 -*-
"""O resumo do aço do Eberick não era lido, e um rótulo dele inventou 300 kg.

🩸 26/09/2026 — job 32a27efc (muro de arrimo, 7 DXF de estrutura, cada prancha
é a folha A1 desenhada no MODELO, sem viewport). O resumo do aço vem em TEXTs
soltos, uma linha por bitola, e o total espaçado letra a letra:

    "PESO CA-50 Ø 10"   "<comprimento> m"   "<peso>kg"
    "P E S O   T O T A L  =  <total>kg"

O `parse_steel_table` devolvia None nas 6 pranchas que TÊM o resumo. Na 7ª foi
pior: o rótulo de LINHA "PESO CA-50 Ø 10" tem a palavra *peso* e virou
CABEÇALHO de quadro. A linha dele juntou o desenho que estava na mesma altura
da folha (cotas, nível, escala), a faixa de colunas virou a folha inteira, uma
cota "300" virou o TOTAL e um "22" virou peso. O prompt recebeu
"[REFERÊNCIA] PESO TOTAL declarado na prancha: 300.00 kg" — número que não
existe na prancha — e a IA copiou.

🔑 O par certo é o rótulo + o "…kg" mais PERTO À DIREITA, na MESMA linha de
base; o "… m" entre os dois é o comprimento, conferido pela NBR 7480 como no
modo tabela. Nunca a linha inteira da folha.

📏 Alcance medido: 1 job, 7 linhas de aço erradas em 2 pranchas; a assinatura
do formato não aparece em outro job do acervo. Nos DXF de controle sem quadro
de aço o parser dá None antes e depois.

Dados SINTÉTICOS com a mesma geometria do arquivo (altura de texto 2, rótulo →
metros a 45,6, rótulo → kg a 68,7); nenhum número do cliente.
Massa linear NBR 7480 do módulo: Ø5 = 0,154 kg/m · Ø10 = 0,617 kg/m.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from structural_extractor import parse_steel_table, structural_prompt_section  # noqa: E402


class _T:
    """Texto de CAD como o extrator espera: .text, .position, .height."""

    def __init__(self, text, x, y, h=2.0):
        self.text = text
        self.position = (x, y)
        self.height = h


X0, Y0 = 700.0, 320.0

# Ø5:  600,00 m × 0,154 =  92,55 → o resumo diz  94,20 (razão 1,02, +perdas)
# Ø10: 500,00 m × 0,617 = 308,50 → o resumo diz 314,00 (razão 1,02)
RESUMO = [
    _T("R E S U M O   D O   A Ç O +10%", X0 + 17.2, Y0 + 8.0),
    _T("PESO CA-60 %%C 5", X0, Y0), _T("600.00 m", X0 + 45.6, Y0),
    _T("94.20kg", X0 + 68.7, Y0),
    _T("PESO CA-50 %%C 10", X0, Y0 - 5.0), _T("500.00 m", X0 + 45.6, Y0 - 5.0),
    _T("314.00kg", X0 + 68.7, Y0 - 5.0),
    _T("PESO TOTAL CA-50", X0, Y0 - 13.0), _T("314.00kg", X0 + 68.7, Y0 - 13.0),
    _T("PESO TOTAL CA-60", X0, Y0 - 18.0), _T("94.20kg", X0 + 68.7, Y0 - 18.0),
    _T("P E S O   T O T A L  =  408.20kg", X0 + 40.0, Y0 - 28.0),
]

# O desenho da folha na MESMA altura do resumo — a disposição da prancha que
# fabricou o 300 kg, com outros números: cotas na linha do 1º rótulo, nível e
# escala na linha do título, marcação de ferro na linha do 2º rótulo, e mais
# abaixo números de comprimento soltos e um "Total" de outro quadro.
DESENHO_NA_MESMA_ALTURA = (
    [_T("250", x, Y0 - 0.6) for x in (269, 293, 317, 341, 365, 389, 413, 437, 461, 485)]
    + [_T("EL.-2,50", 17.2, Y0 + 7.6), _T("Escala 1:100", 231.4, Y0 + 7.6),
       _T("3N4%%C10", 343, Y0 - 5.4), _T("C=950", 353, Y0 - 5.4),
       _T("3N2%%C10", 429, Y0 - 51.1), _T("18", 496, Y0 - 51.1), _T("18", 526, Y0 - 51.1),
       _T("18x1N6%%C5c/15", 453, Y0 - 159.9), _T("18", 527, Y0 - 159.9),
       _T("Total", 54.9, Y0 - 49.0)]
)


def _kg(r):
    return {e["bitola_mm"]: e["kg"] for e in (r or {}).get("por_bitola", [])}


def _sem(textos, *fora):
    """O resumo sem os textos que contêm algum dos pedaços dados."""
    return [t for t in textos if not any(f in t.text for f in fora)]


# ───────────────────────── controles POSITIVOS ───────────────────────────────

def test_o_resumo_e_lido_por_bitola_com_comprimento_e_classe():
    """📌 O caso: antes, None. Cada rótulo casa com o kg e o m à direita dele,
    e a classe (CA-50/CA-60) vem do próprio rótulo, não de um default da folha."""
    r = parse_steel_table(RESUMO)
    assert r is not None, "o resumo do aço não foi reconhecido (voltou a dar None)"
    assert _kg(r) == {5.0: 94.2, 10.0: 314.0}, r
    assert {e["bitola_mm"]: e["comp_m"] for e in r["por_bitola"]} == {5.0: 600.0, 10.0: 500.0}, r
    assert {e["bitola_mm"]: e["aco"] for e in r["por_bitola"]} == {5.0: "CA-60", 10.0: "CA-50"}, r


def test_o_total_espacado_letra_a_letra_e_lido():
    """🔑 "P E S O   T O T A L" não tem a palavra *total*: sem desespaçar, o
    modo LINHA não reconhece e a conferência soma × total fica sem âncora."""
    r = parse_steel_table(RESUMO)
    assert r is not None and r["total_kg"] == 408.2, r and r["total_kg"]


def test_a_soma_bate_com_o_total_e_o_resumo_e_confiavel():
    """📌 94,20 + 314,00 = 408,20 = total declarado, e as duas linhas passam na
    NBR 7480: é o que autoriza [MEDIDO]."""
    r = parse_steel_table(RESUMO)
    assert r is not None and r["confiavel"] is True, r and r["avisos"]


def test_o_desenho_na_mesma_altura_NAO_vira_quadro_fantasma():
    """🩸 O caso da 7ª prancha: o rótulo virava cabeçalho, a cota "250" do
    desenho virava TOTAL e um "18" virava peso. Com o desenho em volta, a
    leitura tem que ser exatamente a do resumo sozinho.
    📏 Neste sintético o código antigo leu "Ø5 = 18 kg" com confiavel=True —
    [MEDIDO] tirado de um número de comprimento do desenho."""
    r = parse_steel_table(RESUMO + DESENHO_NA_MESMA_ALTURA)
    assert r is not None, "o resumo sumiu quando o desenho está na mesma altura"
    assert _kg(r) == {5.0: 94.2, 10.0: 314.0}, (
        "número do desenho entrou como peso: %s" % _kg(r))
    assert r["total_kg"] == 408.2, (
        "o TOTAL virou %s — a cota do desenho voltou a ser lida como total"
        % r["total_kg"])
    assert r["confiavel"] is True, r["avisos"]
    assert r["n_quadros"] == 1, (
        "%s quadros: o rótulo de linha voltou a abrir quadro" % r["n_quadros"])


def test_e_o_prompt_leva_o_total_da_prancha_e_nao_a_cota():
    """🔑 O que chegou à IA foi "[REFERÊNCIA] PESO TOTAL declarado na prancha:
    300.00 kg". Agora: o total impresso, marcado [MEDIDO]."""
    r = parse_steel_table(RESUMO + DESENHO_NA_MESMA_ALTURA)
    bloco = structural_prompt_section({"aco": r})
    assert "[MEDIDO] PESO TOTAL declarado na prancha: 408.20 kg" in bloco, bloco
    assert "250.00 kg" not in bloco and "18.00 kg" not in bloco, bloco


# ───────────────────────── controles NEGATIVOS ───────────────────────────────

def test_kg_a_ESQUERDA_do_rotulo_nao_e_par():
    """Perto (10 alturas) mas do lado errado: no resumo o valor fica à direita."""
    r = parse_steel_table([_T("PESO CA-50 %%C 10", X0, Y0), _T("314.00kg", X0 - 20.0, Y0)])
    assert r is None or not _kg(r), r


def test_kg_a_mais_de_60_alturas_nao_e_par():
    """Na mesma linha, à direita, mas a 61 alturas de texto: já é desenho."""
    r = parse_steel_table([_T("PESO CA-50 %%C 10", X0, Y0), _T("314.00kg", X0 + 2.0 * 61, Y0)])
    assert r is None or not _kg(r), r


def test_kg_em_OUTRA_linha_de_base_nao_e_par():
    """1,85 altura abaixo: é a linha de baixo do quadro, não esta."""
    r = parse_steel_table([_T("PESO CA-50 %%C 10", X0, Y0), _T("314.00kg", X0 + 68.7, Y0 - 3.7)])
    assert r is None or not _kg(r), r


def test_peso_que_nao_bate_com_a_NBR_e_descartado():
    """500 m de Ø10 pesam ~308 kg; 3.140 kg é 10× — linha descartada."""
    r = parse_steel_table([_T("PESO CA-50 %%C 10", X0, Y0), _T("500.00 m", X0 + 45.6, Y0),
                           _T("3140.00kg", X0 + 68.7, Y0)])
    assert r is None or (not _kg(r) and r["confiavel"] is False), r


def test_UMA_linha_fora_da_NBR_derruba_o_resumo_inteiro():
    """Mesma regra do modo tabela: uma linha reprovada marca a leitura como
    inconsistente, e nada dela vira [MEDIDO]."""
    textos = [t for t in RESUMO if not (t.text == "94.20kg" and t.position[1] == Y0)]
    textos.append(_T("942.00kg", X0 + 68.7, Y0))
    r = parse_steel_table(textos)
    assert r is not None and r["confiavel"] is False, r
    assert 5.0 not in _kg(r), r


def test_total_declarado_diferente_da_soma_fica_REFERENCIA():
    textos = _sem(RESUMO, "408.20") + [_T("P E S O   T O T A L  =  600.00kg", X0 + 40.0, Y0 - 28.0)]
    r = parse_steel_table(textos)
    assert r is not None and r["total_kg"] == 600.0, r
    assert r["confiavel"] is False, r["avisos"]


def test_sem_comprimento_e_sem_total_e_lido_mas_NAO_confiavel():
    """🪤 Sem o "… m" a linha não passa pela NBR, e sem total nada confere a
    soma: o número é da prancha, mas não tem prova — estimado."""
    r = parse_steel_table(_sem(RESUMO, " m", "T O T A L"))
    assert r is not None and _kg(r) == {5.0: 94.2, 10.0: 314.0}, r
    assert r["confiavel"] is False, r["avisos"]


def test_sem_comprimento_mas_com_total_que_bate_e_confiavel():
    """🧪 O outro lado: com total declarado a soma tem conferência independente."""
    r = parse_steel_table(_sem(RESUMO, " m"))
    assert r is not None and r["total_kg"] == 408.2, r
    assert r["confiavel"] is True, r["avisos"]


def test_titulo_espacado_sozinho_nao_inventa_numero():
    """🚨 Regra dura nº1: título de resumo sem linha nenhuma → None."""
    r = parse_steel_table([_T("R E S U M O   D O   A Ç O +10%", X0, Y0),
                           _T("V 1", 10, 10), _T("PLANTA", 0, 0)])
    assert r is None, r


def test_cabecalho_de_coluna_PESO_kg_continua_cabecalho():
    """🧪 A exclusão é só do rótulo de LINHA "PESO CA-xx Ø d"; o cabeçalho de
    coluna de quadro comum continua abrindo quadro."""
    r = parse_steel_table([_T("BITOLA", 0, 100), _T("PESO (kg)", 60, 100),
                           _T("%%c 10", 0, 95), _T("100.00", 60, 95)])
    assert _kg(r) == {10.0: 100.0}, r


def test_desespacar_so_junta_tres_ou_mais_letras_soltas():
    """🪤 "V 1", "P 12" e "N3 Ø10" têm dígito e ficam como estão; duas letras
    soltas ("D O") também."""
    from structural_extractor import _desespaca
    assert _desespaca("P E S O   T O T A L  =  1.0kg") == "PESO   TOTAL  =  1.0kg"
    assert _desespaca("R E S U M O   D O   A Ç O") == "RESUMO   D O   AÇO"
    for intacto in ("V 1", "P 12", "N3 %%C10 C=120", "PESO CA-50 %%C 10", "E A"):
        assert _desespaca(intacto) == intacto
