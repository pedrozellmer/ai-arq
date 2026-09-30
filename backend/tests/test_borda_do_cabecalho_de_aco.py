# -*- coding: utf-8 -*-
"""O cabeçalho do quadro de aço tem a borda DELE — o desenho na mesma altura não
vira coluna do quadro.

🩸 30/09/2026 (estudo do acervo) — o agrupamento em linhas é da prancha inteira:
na altura do cabeçalho e das linhas do quadro caem textos do DESENHO. Cada um
virava coluna "outro" e a borda do quadro ia até a ponta da folha.
  · Eberick: um "Ø 16" de marcação na linha do Ø10 roubou a bitola → a linha
    reprovou na massa linear e sumiu → soma 17.138 × total 18.252 → estimado.
  · CYPE: a linha "Total:" da tabela vizinha, na mesma altura, virou total
    deste quadro → um peso que não existe na prancha, carimbado confiável.

Regras que os guardas prendem:
- o resumo do Eberick com o desenho em volta lê as 5 bitolas e bate o total;
- o "Total:" de outra tabela na mesma altura NÃO vira total confiável;
- a coluna "outro" colada (PESO kg/m) continua absorvendo os números dela;
- quadro com só a coluna de peso reconhecida continua lendo a bitola ao lado;
- o quadro acaba pelo VÃO: linha do desenho no meio não o encerra, linha
  alinhada muito abaixo não entra, e sem altura de letra fica a trava antiga.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from dwg_extractor import TextAnnotation as T  # noqa: E402
import structural_extractor as se  # noqa: E402

# Posições e alturas de um resumo real do Eberick (layer "2") com a marcação do
# desenho em volta (layer "1") — só números e siglas.
_EBERICK = [
    ("1", "C/10", -4.749, 42.125, 0.1), ("2", "RESUMO DE AÇO", 3.997, 42.125, 0.125),
    ("1", "C/10", -8.75, 42.035, 0.1),
    ("2", "AÇO", 3.016, 41.906, 0.125), ("2", "BIT", 4.071, 41.906, 0.125),
    ("2", "COMPR", 5.061, 41.908, 0.125), ("2", "PESO", 6.875, 41.908, 0.125),
    ("1", "C/11", -24.488, 41.904, 0.1), ("1", "90", -13.3, 41.885, 0.1),
    ("1", "350", -16.8, 41.835, 0.1), ("1", "344", -5.099, 41.825, 0.1),
    ("1", "C/11", -24.338, 41.804, 0.1), ("1", "C/11", -19.837, 41.794, 0.1),
    ("1", "N1", -8.75, 41.735, 0.1),
    ("2", "m", 5.418, 41.692, 0.1), ("2", "kgf", 7.107, 41.692, 0.1), ("2", "mm", 4.232, 41.669, 0.1),
    ("1", "N3", -24.488, 41.604, 0.1), ("1", "394", -20.187, 41.594, 0.1),
    ("2", "8", 3.82, 41.506, 0.1), ("1", "N1", -24.338, 41.504, 0.1), ("2", "50A", 2.736, 41.503, 0.1),
    ("2", "3044", 4.94, 41.503, 0.1), ("2", "1202", 6.864, 41.503, 0.1),
    ("1", "33", -8.75, 41.435, 0.1), ("1", "Ø 12.5", -4.749, 41.425, 0.1),
    ("2", "50A", 2.736, 41.328, 0.1), ("2", "10", 3.82, 41.331, 0.1),
    ("2", "1805", 4.94, 41.328, 0.1), ("2", "1114", 6.864, 41.328, 0.1),
    ("1", "Ø 16", -19.837, 41.294, 0.1), ("1", "34", -24.338, 41.204, 0.1),
    ("2", "12.5", 3.82, 41.156, 0.1), ("2", "50A", 2.736, 41.153, 0.1),
    ("2", "3926", 4.94, 41.153, 0.1), ("2", "3781", 6.864, 41.153, 0.1),
    ("1", "N2", -4.749, 41.125, 0.1), ("1", "2x34", -24.488, 41.104, 0.1),
    ("1", "N2", -19.837, 40.994, 0.1), ("2", "50A", 2.736, 40.978, 0.1),
    ("2", "16", 3.82, 40.981, 0.1), ("2", "7507", 4.94, 40.978, 0.1), ("2", "11846", 6.864, 40.978, 0.1),
    ("1", "33", -4.749, 40.825, 0.1),
    ("2", "20", 3.82, 40.806, 0.1), ("2", "50A", 2.736, 40.803, 0.1),
    ("2", "125", 4.94, 40.803, 0.1), ("2", "309", 6.864, 40.803, 0.1),
    ("1", "34", -19.837, 40.694, 0.1),
    ("2", "Peso Total        50A =", 2.553, 40.594, 0.125), ("2", "18252 kgf", 6.235, 40.594, 0.125),
]


def _textos(linhas):
    return [T(lay, txt, (x, y), h) for lay, txt, x, y, h in linhas]


def test_eberick_com_o_desenho_em_volta_le_as_cinco_bitolas_e_bate_o_total():
    r = se.parse_steel_table(_textos(_EBERICK))
    assert r, r
    kg = {b["bitola_mm"]: b["kg"] for b in r["por_bitola"]}
    assert kg == {8.0: 1202.0, 10.0: 1114.0, 12.5: 3781.0, 16.0: 11846.0, 20.0: 309.0}, r
    assert r["total_kg"] == 18252.0, r
    assert r["confiavel"] is True, r


def test_total_de_outra_tabela_na_mesma_altura_nao_vira_total_confiavel():
    # quadro com bitola que não é da lista (a linha não conta) e, na altura de
    # uma linha dele, o "Total:" de outra tabela lá na ponta esquerda da folha
    # + um número solto do desenho na coluna de peso
    h = 2.5
    txts = [T("0", "LEGENDA", (0, 0), h), T("0", "BITOLA", (80, 0), h),
            T("0", "COMP", (90, 0), h), T("0", "PESO", (100, 0), h),
            T("0", "Ø6", (80, -10), h), T("0", "12.0", (90, -10), h), T("0", "3.0", (100, -10), h),
            T("0", "Total:", (2, -20), h), T("0", "347", (101, -20), h)]
    r = se.parse_steel_table(txts)
    assert r is None or not r["confiavel"], r


def _quadro_com_massa_linear():
    # a coluna PESO (kg/m) é "outro", colada nas reconhecidas: ela tem que
    # ABSORVER o 0,395 — senão ele vira o peso da linha
    h = 2.5
    return [T("0", "BITOLA", (0, 0), h), T("0", "COMP (m)", (10, 0), h),
            T("0", "PESO (kg/m)", (20, 0), h), T("0", "PESO (kg)", (30, 0), h),
            T("0", "Ø8", (0, -10), h), T("0", "100", (10, -10), h),
            T("0", "0.395", (20, -10), h), T("0", "39.5", (30, -10), h)]


def test_coluna_de_massa_linear_colada_continua_absorvendo_os_numeros_dela():
    r = se.parse_steel_table(_quadro_com_massa_linear())
    assert r and [(b["bitola_mm"], b["kg"]) for b in r["por_bitola"]] == [(8.0, 39.5)], r


def test_so_a_coluna_de_peso_reconhecida_ainda_le_a_bitola_da_coluna_ao_lado():
    h = 2.5
    txts = [T("0", "DESCRIÇÃO", (0, 0), h), T("0", "PESO", (10, 0), h),
            T("0", "Ø8 CA-50", (0, -10), h), T("0", "39.5", (10, -10), h)]
    r = se.parse_steel_table(txts)
    assert r and [(b["bitola_mm"], b["kg"]) for b in r["por_bitola"]] == [(8.0, 39.5)], r


def test_colunas_coladas_em_cadeia_e_o_resto_fora():
    rec = [("bitola", 0.0), ("comp", 10.0), ("peso", 20.0)]
    outros = [("outro", -12.0), ("outro", -26.0), ("outro", 200.0)]
    # passo 10 → -12 cola no 0; -26 cola no -12 (em cadeia); 200 fica fora
    assert sorted(x for _n, x in se._colunas_coladas(rec, outros)) == [-26.0, -12.0]


# ───────── a parada do quadro é o VÃO, não "3 linhas fora seguidas" ─────────
#
# Com a borda certa, as linhas do DESENHO entre o cabeçalho e os dados ficam
# fora dela. A trava antiga contava 3 seguidas e encerrava o quadro antes do
# primeiro dado — foi assim que o "Resumo Aço" do CYPE (radier) perdia o
# Ø6,3 362,7 m → 89 kg, que confere na NBR. Posições de um quadro real; a
# 1ª coluna ("Resumo Aço") fica longe das reconhecidas e NÃO é colada.
_RESUMO_CYPE = [
    ("Resumo Aço", 75.25, 47.503), ("Comp. total", 79.33, 47.503), ("Peso", 81.6, 47.503),
    ("12", 50.0, 47.28), ("P3", 52.0, 47.28), ("7", 55.0, 47.28),           # desenho
    ("Térreo", 75.79, 47.05), ("(m)", 80.07, 47.05), ("(kg)", 81.68, 47.05),
    ("8", 54.0, 46.82),                                                     # desenho
    ("Armadura longitudinal", 73.59, 46.597),
    ("20", 49.6, 46.30), ("15", 51.8, 46.30), ("3.1", 54.1, 46.30),         # desenho
    ("CA-50", 73.59, 46.005), ("Ø6.3", 78.31, 46.005), ("362.7", 79.89, 46.005), ("89", 81.8, 46.005),
]


def test_linhas_do_desenho_entre_o_cabecalho_e_os_dados_nao_encerram_o_quadro():
    r = se.parse_steel_table([T("0", t, (x, y), 0.27) for t, x, y in _RESUMO_CYPE])
    assert r and [(b["bitola_mm"], b["kg"]) for b in r["por_bitola"]] == [(6.3, 89.0)], r


def _quadro_com_intruso(h, linhas_fora=0):
    # quadro que fecha (150 + 50 + 200 + 100 = TOTAL 500), mais alto que 6
    # alturas de letra, e, bem abaixo, uma marcação do desenho ALINHADA com as
    # colunas por coincidência (confere na NBR: 10,4 m de Ø12,5 = 10 kg) — se
    # entrar, a soma vira 510 e o quadro cai
    txts = [T("0", "BITOLA", (0, 0), h), T("0", "COMPR. (m)", (30, 0), h), T("0", "PESO (kg)", (60, 0), h)]
    y = 0.0
    for bit, comp, kg in (("8", "379.70", "150.00"), ("10", "81.00", "50.00"),
                          ("12.5", "207.70", "200.00"), ("16", "63.40", "100.00")):
        y -= 0.35
        txts += [T("0", "%%c " + bit, (0, y), h), T("0", comp, (30, y), h), T("0", kg, (60, y), h)]
    y -= 0.35
    txts += [T("0", "TOTAL", (0, y), h), T("0", "500.00", (60, y), h)]
    for _ in range(linhas_fora):
        y -= 0.35
        txts.append(T("0", "N1", (500, y), h))
    y -= 0.35 if linhas_fora else 3.0
    txts += [T("0", "%%c 12.5", (0, y), h), T("0", "10.40", (30, y), h), T("0", "10.00", (60, y), h)]
    return txts


def test_linha_alinhada_muito_abaixo_do_quadro_nao_entra():
    # 3,0 abaixo do TOTAL = 15 alturas de letra: é desenho, não linha da tabela
    r = se.parse_steel_table(_quadro_com_intruso(0.2))
    kg = sum(b["kg"] for b in r["por_bitola"])
    assert (kg, r["total_kg"], r["confiavel"]) == (500.0, 500.0, True), r


def test_sem_altura_de_letra_fica_a_trava_das_3_linhas_fora():
    # sem altura não há régua de vão: 3 linhas fora seguidas encerram o quadro
    r = se.parse_steel_table(_quadro_com_intruso(0, linhas_fora=3))
    kg = sum(b["kg"] for b in r["por_bitola"])
    assert (kg, r["total_kg"], r["confiavel"]) == (500.0, 500.0, True), r
