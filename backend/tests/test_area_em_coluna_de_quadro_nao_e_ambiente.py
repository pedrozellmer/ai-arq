# -*- coding: utf-8 -*-
"""A ÁREA escrita em COLUNA de quadro é célula de tabela, não etiqueta de cômodo.

🩸 12/10/2026 — avaliação de uma escola com a seção AMBIENTE ↔ ÁREA ESCRITA
ligada: "INTERNOS ÁREA = 619,00 m²" e "PEITORIS E SOLEIRAS = 225,00 m²" saíram
como ambientes e o forro foi orçado com os 619. São células da coluna ÁREA de um
quadro de acabamentos (DESCRIÇÃO | ÁREA).

📏 Medido pelo motor nos 88 arquivos do acervo com etiqueta de área (59 jobs,
5.082 etiquetas): 34 pilhas em 18 arquivos de 17 jobs, lidas uma a uma — todas
quadro. Saem 196 etiquetas "sem nome", 20 totais com o nome do cabeçalho e 8
ambientes falsos. Com o teto do vão até 12 alturas de letra só entra quadro; em
13 entram salas de verdade. A régua para em 6,5.

🪤 O que NÃO é célula, medido: a etiqueta com o nome no próprio texto (layout de
loja, uma por expositor, a 2,8 alturas) e a lista escrita nome/área/nome/área.

🪤 Nomes e layers FICTÍCIOS (repositório público, regra nº6).
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402

H = 0.20                               # altura da letra
FRASE = ("(as áreas escritas em linha de quadro não entram aqui: são célula de tabela, com a"
         " descrição ao lado)")


def _t(texto, x, y, h=H, layer="AMB-TEXTO", rot=0.0):
    return dx.TextAnnotation(layer=layer, text=texto, position=(x, y), height=h, rotation=rot)


def _celulas(textos):
    """→ (as áreas que são célula, as que ficam) — pelo valor, em ordem."""
    pares, sem = er.ambientes_com_area_escrita(textos)
    cs = er.celulas_de_quadro_de_area(pares, sem, textos)
    todas = [(q["x"], q["y"], q["m2"]) for q in pares] + [(s["x"], s["y"], s["m2"]) for s in sem]
    return (sorted(m for x, y, m in todas if (x, y) in cs), sorted(m for x, y, m in todas if (x, y) not in cs))


def _quadro(x, y, areas, passo=4.0, h=H, lado=-37.0, dy=0.0, descricao="COR %d (PINTURA EPÓXI)"):
    """Uma coluna de áreas (uma célula a cada `passo` alturas) com a descrição
    da linha a `lado` alturas, `dy` alturas acima da linha da área."""
    tx = []
    for k, a in enumerate(areas):
        yk = y - k * passo * h
        tx.append(_t(a, x, yk, h=h))
        if descricao:
            tx.append(_t(descricao % (k + 1), x + lado * h, yk + dy * h, h=h))
    return tx


AREAS = ["615 m²", "218 m²", "231 m²", "35 m²", "142 m²"]
VALORES = [35.0, 142.0, 218.0, 231.0, 615.0]


# ══════════════════════════════════════════════════════════════════════════
#  O quadro
# ══════════════════════════════════════════════════════════════════════════
def test_a_coluna_de_areas_de_um_quadro_e_celula():
    assert _celulas(_quadro(10, 10, AREAS)) == (VALORES, [])


def test_o_caso_do_incidente_o_nome_montado_com_o_titulo_e_o_cabecalho():
    """O título do quadro ("INTERNOS") em cima do cabeçalho da coluna ("ÁREA")
    virava o nome da 1ª célula. Sem a régua é um AMBIENTE de 615 m²."""
    tx = _quadro(10, 10, AREAS) + [_t("ÁREA", 10, 10 + 2.2 * H), _t("INTERNOS", 10, 10 + 4.2 * H)]
    pares, sem = er.ambientes_com_area_escrita(tx)
    assert [(p["nome"], p["m2"], p["resumo"]) for p in pares] == [("INTERNOS ÁREA", 615.0, False)], \
        "CONTROLE: o desenho do teste reproduz o defeito"
    assert (10, 10) in er.celulas_de_quadro_de_area(pares, sem, tx)
    assert _celulas(tx) == (VALORES, [])


def test_a_descricao_meia_linha_fora_das_areas():
    """Medido: num quadro a descrição fica MEIA linha abaixo da área (as áreas a
    2,4 alturas uma da outra, a descrição 1,2 abaixo). Vale a faixa da linha."""
    assert _celulas(_quadro(10, 10, AREAS, passo=2.4, dy=-1.2, lado=-22)) == (VALORES, [])


def test_a_descricao_em_duas_linhas_com_a_ancora_no_topo():
    """Medido: a descrição de duas linhas fica gravada 1,2 altura ACIMA da linha da área."""
    tx = _quadro(10, 10, AREAS, dy=0.0)
    tx[1] = _t("PISO INDUSTRIAL POLIDO\n(PINTURA EPÓXI)", 10 - 37 * H, 10 + 1.2 * H)
    assert _celulas(tx) == (VALORES, [])


def test_a_descricao_pode_estar_a_direita():
    assert _celulas(_quadro(10, 10, AREAS, lado=+15)) == (VALORES, [])


def test_a_letra_e_a_da_propria_etiqueta_nao_a_do_arquivo():
    """🩸 Medido: um quadro de letra 0,9 num arquivo de letra 0,5 — pela letra do
    arquivo o passo dava 4,4; pela dele, 2,4."""
    grande = _quadro(10, 10, AREAS, passo=5.0, h=2 * H)          # 10 "letras do arquivo", 5 das dele
    miudos = [_t("texto %d" % i, 200 + i, 200) for i in range(40)]
    assert _celulas(grande + miudos) == (VALORES, [])
    pequeno = _quadro(10, 10, AREAS, passo=10.0, h=H / 2)        # 5 "letras do arquivo", 10 das dele
    graudos = [_t("texto %d" % i, 200 + i, 200, h=H) for i in range(40)]
    assert _celulas(pequeno + graudos) == ([], VALORES)
    # …nem a da MAIOR etiqueta de área do arquivo: uma área de letra 4× maior, longe dali
    assert _celulas(pequeno + graudos + [_t("A=90,00m²", 300, 300, h=2 * H)]) == ([], sorted(VALORES + [90.0]))


def test_a_etiqueta_sem_altura_usa_a_mediana_do_desenho():
    tx = _quadro(10, 10, AREAS)
    tx[0] = _t("615 m²", 10, 10, h=0)
    assert _celulas(tx) == (VALORES, [])


# ══════════════════════════════════════════════════════════════════════════
#  A régua: 3 ou mais, a mesma x, CADA vão, o texto na faixa
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_duas_areas_empilhadas_nao_sao_coluna():
    assert _celulas(_quadro(10, 10, AREAS[:2])) == ([], [218.0, 615.0])
    assert _celulas(_quadro(10, 10, AREAS[:3])) == ([218.0, 231.0, 615.0], [])


@pytest.mark.parametrize("passo, celula", [(2.4, True), (6.0, True), (6.5, True), (6.6, False), (12.0, False)])
def test_cada_celula_a_ate_seis_e_meia_alturas_da_de_cima(passo, celula):
    """Medido: os quadros do acervo vão de 1,4 a 6,1; a pilha de cômodos mais
    apertada só fecha 3 seguidas a 9,3. O teto vale no valor exato (a conta em
    ponto flutuante dá 6,500000000000004)."""
    assert _celulas(_quadro(10, 10, AREAS, passo=passo)) == ((VALORES, []) if celula else ([], VALORES))


def test_a_regua_e_cada_vao_nao_o_passo_mediano():
    """🪤 Medido: pela mediana, uma etiqueta a 28 alturas da última célula
    entrava na pilha. Um cômodo ali sairia junto com o quadro."""
    y_longe = 10 - 2 * 2.5 * H - 28 * H
    tx = (_quadro(10, 10, AREAS[:3], passo=2.5)
          + [_t("DEPÓSITO", 10, y_longe + 2 * H), _t("A=7,20m²", 10, y_longe), _t("PISO CIMENTADO", 10 - 20 * H, y_longe)])
    assert _celulas(tx) == ([218.0, 231.0, 615.0], [7.2])
    pares, _sem = er.ambientes_com_area_escrita(tx)
    assert [(p["nome"], p["m2"]) for p in pares] == [("DEPÓSITO", 7.2)]


def test_o_vao_grande_no_meio_parte_a_coluna_em_duas():
    """Quadro em dois grupos de linhas: cada grupo com 3 ou mais é coluna; o
    grupo de 2 que sobra, não."""
    cima = _quadro(10, 10, ["11 m²", "12 m²", "13 m²"], passo=3.0)
    baixo3 = _quadro(10, 10 - 2 * 3.0 * H - 9 * H, ["21 m²", "22 m²", "23 m²"], passo=3.0)
    assert _celulas(cima + baixo3) == ([11.0, 12.0, 13.0, 21.0, 22.0, 23.0], [])
    assert _celulas(cima + baixo3[:4]) == ([11.0, 12.0, 13.0], [21.0, 22.0])


@pytest.mark.parametrize("de_lado, celula", [(0.4, True), (0.95, True), (2.0, True), (2.1, False), (10.0, False)])
def test_a_de_baixo_fica_a_ate_duas_alturas_de_lado_da_de_cima(de_lado, celula):
    """Medido: dentro do mesmo quadro as áreas desalinham até 0,95 altura (número
    centrado ou à direita, gravado pelo início). De 1 a 5 alturas de folga o
    acervo dá o mesmo; a régua fica em 2."""
    tx = _quadro(10, 10, AREAS)
    tx[4] = _t("231 m²", 10 + de_lado * H, 10 - 2 * 4 * H)       # a 3ª célula, deslocada
    assert _celulas(tx) == ((VALORES, []) if celula else ([], VALORES)), "fora da folga a pilha parte em 2 + 1 + 2"


def test_CONTROLE_etiquetas_em_escada_nao_sao_coluna_mesmo_com_outras_no_caminho():
    """🪤 Agrupar pela x primeiro encadeava etiquetas vizinhas pela planta toda:
    A, C e E descem em escada (3 alturas de lado cada) e B e D, lá embaixo,
    fecham o caminho pela x. O elo é de cada uma com a de CIMA."""
    tx = []
    for nome, dx_, dy_ in [("A", 0.0, 0.0), ("C", 3.0, -4.0), ("E", 6.0, -8.0), ("B", 1.5, -40.0), ("D", 4.5, -44.0)]:
        y = 10 + dy_ * H
        tx += [_t("%d1,00 m²" % (ord(nome) - 64), 10 + dx_ * H, y), _t("ESPECIFICAÇÃO " + nome, 10 - 30 * H, y)]
    assert _celulas(tx) == ([], [11.0, 21.0, 31.0, 41.0, 51.0])


def test_a_regua_do_vao_e_a_maior_das_duas_letras():
    """Célula de letra maior no meio da coluna (um subtotal): o vão se mede pela
    maior das duas letras — 8 alturas da pequena são 4 da grande."""
    tx = [_t("11 m²", 10, 10), _t("12 m²", 10, 10 - 8 * H, h=2 * H), _t("13 m²", 10, 10 - 16 * H)]
    tx += [_t("LINHA %d DO QUADRO" % k, 10 - 30 * H, 10 - 8 * k * H) for k in range(3)]
    assert _celulas(tx) == ([11.0, 12.0, 13.0], [])


@pytest.mark.parametrize("com_descricao, celula", [(5, True), (4, True), (3, False), (0, False)])
def test_a_descricao_em_oitenta_por_cento_das_linhas(com_descricao, celula):
    tx = _quadro(10, 10, AREAS, descricao="")
    tx += [_t("COR %d (PINTURA EPÓXI)" % k, 10 - 37 * H, 10 - k * 4 * H) for k in range(com_descricao)]
    assert _celulas(tx) == ((VALORES, []) if celula else ([], VALORES))


def test_CONTROLE_o_texto_da_linha_tem_de_estar_ao_lado():
    """De 1,5 a 80 alturas de lado: o que está colado na área ou do outro lado
    da prancha não é a descrição da linha."""
    assert _celulas(_quadro(10, 10, AREAS, lado=-100)) == ([], VALORES)
    assert _celulas(_quadro(10, 10, AREAS, lado=+1.0)) == ([], VALORES)
    assert _celulas(_quadro(10, 10, AREAS, lado=-80)) == (VALORES, [])


def test_CONTROLE_o_texto_fora_da_faixa_da_linha_nao_conta():
    """A faixa é ± meio passo: a 4 alturas uma da outra, o texto 2,5 acima já é
    da linha de cima — e a 1ª linha fica sem ninguém."""
    tx = _quadro(10, 10, AREAS[:3], descricao="")
    tx += [_t("COR %d (PINTURA EPÓXI)" % k, 10 - 37 * H, 10 - k * 4 * H + 2.5 * H) for k in range(1)]
    assert _celulas(tx) == ([], [218.0, 231.0, 615.0])


def test_CONTROLE_a_faixa_e_meio_passo_entre_VIZINHAS():
    """Quatro áreas a 3 alturas uma da outra, cada uma com um texto 2,2 abaixo
    dela: o texto cai na faixa da linha de BAIXO (0,8 acima dela), e a 1ª linha
    fica sem ninguém — 3 de 4. Medindo o passo até a área mais LONGE de cima a
    faixa dobrava e a 1ª linha ganhava o texto."""
    tx = _quadro(10, 10, AREAS[:4], passo=3.0, dy=-2.2)
    assert _celulas(tx) == ([], [35.0, 218.0, 231.0, 615.0])
    assert _celulas(_quadro(10, 10, AREAS[:4], passo=3.0, dy=-1.4)) == ([35.0, 218.0, 231.0, 615.0], [])


def test_CONTROLE_outra_coluna_de_areas_ao_lado_nao_e_a_descricao():
    """O texto da linha é o que NÃO é etiqueta de área (medido: todo quadro do
    acervo tem a descrição). Duas pilhas de etiquetas lado a lado não se provam."""
    tx = _quadro(10, 10, AREAS[:3], descricao="") + _quadro(10 + 12 * H, 10, ["41 m²", "42 m²", "43 m²"], descricao="")
    assert _celulas(tx) == ([], [41.0, 42.0, 43.0, 218.0, 231.0, 615.0])
    # …nem a etiqueta inteira ("LOJA 1 20,00 m²", nome e área no mesmo texto) ao lado de cada uma
    tx = _quadro(10, 10, AREAS[:3], descricao="")
    tx += [_t("LOJA %d 2%d,00 m²" % (k, k), 10 + 15 * H, 10 - k * 4 * H) for k in range(3)]
    assert _celulas(tx)[0] == []


def test_CONTROLE_marca_curta_na_linha_nao_e_descricao():
    """O texto da linha é uma DESCRIÇÃO (3 letras ou mais): a marca de porta e o
    traço de célula vazia ao lado de etiquetas empilhadas não fazem um quadro."""
    for marca in ("P1", "-", "02"):
        tx = _quadro(10, 10, AREAS[:3], descricao="")
        tx += [_t(marca, 10 + 15 * H, 10 - k * 4 * H) for k in range(3)]
        assert _celulas(tx) == ([], [218.0, 231.0, 615.0]), marca
    tx = _quadro(10, 10, AREAS[:3], descricao="")
    tx += [_t("P1A", 10 + 15 * H, 10 - k * 4 * H) for k in range(3)]
    assert _celulas(tx) == ([218.0, 231.0, 615.0], [])


# ══════════════════════════════════════════════════════════════════════════
#  O que NÃO é célula
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_comodos_empilhados_com_texto_ao_lado_ficam():
    """Três salas uma embaixo da outra, a 12 alturas, cada uma com a
    especificação do piso ao lado: etiqueta de cômodo."""
    tx = []
    for k, (nome, area) in enumerate([("SALA 1", "A=20,26m²"), ("SALA 2", "A=20,30m²"), ("SALA 3", "A=19,90m²")]):
        y = 10 - k * 12 * H
        tx += [_t(nome, 10, y + 2 * H), _t(area, 10, y), _t("PISO VINÍLICO", 10 + 20 * H, y)]
    assert _celulas(tx) == ([], [19.9, 20.26, 20.3])


def test_CONTROLE_etiquetas_sem_nome_empilhadas_sem_texto_ao_lado_ficam():
    """Medido: etiquetas de forro de cabines ("AF= 2.43m²"), sem nome, a 5–9
    alturas uma da outra e sem nada na linha."""
    tx = [_t("AF= 2,99m²", 10, 10), _t("AF= 2,43m²", 10, 10 - 5 * H), _t("AF= 2,45m²", 10, 10 - 10 * H)]
    assert _celulas(tx) == ([], [2.43, 2.45, 2.99])


def test_CONTROLE_a_etiqueta_com_o_nome_no_proprio_texto_fica():
    """🪤 Medido: layout de loja, uma etiqueta por expositor ("SETOR A ÁREA=1,11m2"),
    empilhadas a 2,8 alturas e com outros textos na linha. É par CERTO."""
    tx = []
    for k, area in enumerate(["1,11", "1,12", "1,13", "1,14"]):
        y = 10 - k * 2.8 * H
        tx += [_t("SETOR A ÁREA=%sm2" % area, 10, y), _t("GÔNDOLA TIPO 2", 10 + 30 * H, y)]
    assert _celulas(tx) == ([], [1.11, 1.12, 1.13, 1.14])
    pares, _sem = er.ambientes_com_area_escrita(tx)
    assert {p["como"] for p in pares} == {"mesmo"}


def test_CONTROLE_a_lista_escrita_nome_area_nome_area_fica():
    """Medido: "ÁREAS COMPUTÁVEIS" em cima de "779,72 m²", e assim por diante, a
    5,7 alturas — o nome em cima de cada área e nada ao lado. O par é certo.
    O nome está DENTRO da faixa da linha (2 alturas acima, meio passo = 2,85) e
    quase na mesma x: "ao lado" só começa a 1,5 altura."""
    tx = []
    for k, (nome, area) in enumerate([("VARANDAS", "78,23 m²"), ("PISCINA", "57,00 m²"), ("QUIOSQUE", "31,40 m²")]):
        y = 10 - k * 5.7 * H
        tx += [_t(nome, 10 - 0.5 * H, y + 2 * H), _t(area, 10, y)]
    assert _celulas(tx) == ([], [31.4, 57.0, 78.23])
    pares, sem = er.ambientes_com_area_escrita(tx)
    assert sorted(p["nome"] for p in pares) == ["PISCINA", "QUIOSQUE", "VARANDAS"] and sem == []


def test_CONTROLE_etiquetas_giradas_nao_entram():
    """A coluna é de texto deitado: etiqueta girada 90° (cômodo estreito) empilha
    ao longo de x, e a régua não olha."""
    tx = _quadro(10, 10, AREAS)
    for i in range(0, len(tx), 2):
        tx[i] = _t(tx[i].text, tx[i].position[0], tx[i].position[1], rot=90.0)
    assert _celulas(tx) == ([], VALORES)


def test_CONTROLE_a_mesma_etiqueta_gravada_duas_vezes_no_mesmo_ponto():
    """O vão tem de ser maior que zero: três cópias da mesma etiqueta no mesmo
    ponto não são três linhas de quadro."""
    tx = [_t("615 m²", 10, 10), _t("615 m²", 10, 10), _t("615 m²", 10, 10), _t("COR 1 (PINTURA EPÓXI)", 10 - 37 * H, 10)]
    assert _celulas(tx)[0] == []


def test_sem_etiqueta_nao_ha_celula():
    assert er.celulas_de_quadro_de_area([], [], []) == set()
    assert er.celulas_de_quadro_de_area(None, None, None) == set()


# ══════════════════════════════════════════════════════════════════════════
#  Por desenho, e a seção do prompt
# ══════════════════════════════════════════════════════════════════════════
def _planta(x0=10.0):
    return [_t("COZINHA", x0, 20 + 2 * H), _t("A=34,20m²", x0, 20), _t("REFEITÓRIO A=52,10m²", x0 + 8, 24),
            _t("A=4,00m²", x0 + 16, 21)]                         # esta, sem nome


def _mapa(duas=False):
    folhas = [{"folha": "A1 PLANTA", "titulo": "PLANTA BAIXA TÉRREO", "tipo": "planta", "caixa": (0, 0, 60, 30)}]
    if duas:
        folhas.append({"folha": "A2 QUADROS", "titulo": "PLANTA DE PISO", "tipo": "planta", "caixa": (100, 0, 160, 30)})
    return {"folhas": folhas}


def _com_quadro(x_quadro=40.0):
    return (_planta() + _quadro(x_quadro, 12, AREAS)
            + [_t("ÁREA", x_quadro, 12 + 2.2 * H), _t("INTERNOS", x_quadro, 12 + 4.2 * H)])


def test_a_celula_nao_entra_em_ambientes_totais_nem_sem_nome():
    amb = dx.ambientes_por_desenho(_com_quadro(), _mapa())
    (g,) = amb["grupos"]
    assert g["ambientes"] == [["COZINHA", 34.2, 1], ["REFEITÓRIO", 52.1, 1]]
    assert g["totais"] == [] and g["sem_nome"] == [4.0]
    assert g["em_quadro"] == 5
    assert (amb["etiquetas"], amb["pares"], amb["sem_nome"], amb["em_quadro"]) == (8, 2, 1, 5)


def test_CONTROLE_sem_a_regua_o_quadro_estava_na_lista(monkeypatch):
    monkeypatch.setattr(er, "celulas_de_quadro_de_area", lambda *_a: set())
    amb = dx.ambientes_por_desenho(_com_quadro(), _mapa())
    (g,) = amb["grupos"]
    assert ["INTERNOS ÁREA", 615.0, 1] in g["ambientes"]
    assert g["sem_nome"] == [4.0, 35.0, 142.0, 218.0, 231.0] and g["em_quadro"] == 0
    assert (amb["etiquetas"], amb["pares"], amb["sem_nome"], amb["em_quadro"]) == (8, 3, 5, 0)


def test_a_secao_diz_que_ha_area_em_quadro_sem_numero_nenhum():
    ls = dx._linhas_dos_ambientes(dx.ambientes_por_desenho(_com_quadro(), _mapa()))
    assert [l.strip() for l in ls].count(FRASE) == 1
    txt = "\n".join(ls)
    assert "COZINHA = 34.20 m²" in txt and "REFEITÓRIO = 52.10 m²" in txt
    for numero in ("615", "218", "231", "35.00", "142"):
        assert numero not in txt, numero
    assert "INTERNOS" not in txt
    assert "(há etiquetas de área sem nome neste desenho; não são listadas: não são ambiente)" in txt, \
        "a sem-nome da planta continua sendo dita"
    # a frase não conta as células: é a lição do corte do nível
    frase = next(l for l in ls if FRASE in l)
    assert not any(c.isdigit() for c in frase)


def test_a_frase_sai_no_grupo_do_desenho_que_tem_o_quadro():
    """Planta numa prancha, planta + quadro noutra: a frase sai só na segunda,
    depois das linhas do grupo."""
    tx = _planta() + _planta(110.0) + _quadro(140, 12, AREAS)
    amb = dx.ambientes_por_desenho(tx, _mapa(duas=True))
    g1, g2 = amb["grupos"]
    assert (g1["em_quadro"], g2["em_quadro"]) == (0, 5)
    ls = dx._linhas_dos_ambientes(amb)
    i1 = next(i for i, l in enumerate(ls) if l.startswith("  [PLANTA BAIXA TÉRREO"))
    i2 = next(i for i, l in enumerate(ls) if l.startswith("  [PLANTA DE PISO"))
    (i_frase,) = [i for i, l in enumerate(ls) if FRASE in l]
    assert i1 < i2 < i_frase
    assert ls[i_frase].startswith("    ("), "no recuo das linhas do grupo"


def test_o_desenho_so_de_quadro_nao_vira_grupo_na_secao():
    tx = _planta() + _quadro(140, 12, AREAS)
    amb = dx.ambientes_por_desenho(tx, _mapa(duas=True))
    assert [g["em_quadro"] for g in amb["grupos"]] == [0, 5]
    txt = "\n".join(dx._linhas_dos_ambientes(amb))
    assert "[PLANTA BAIXA TÉRREO" in txt and "[PLANTA DE PISO" not in txt and FRASE not in txt


def test_o_arquivo_so_de_quadro_nao_tem_secao():
    amb = dx.ambientes_por_desenho(_quadro(40, 12, AREAS), _mapa())
    assert (amb["etiquetas"], amb["pares"], amb["sem_nome"], amb["em_quadro"]) == (5, 0, 0, 5)
    assert dx._linhas_dos_ambientes(amb) == []


def test_sem_mapa_de_folhas_tambem():
    amb = dx.ambientes_por_desenho(_com_quadro(), None)
    (g,) = amb["grupos"]
    assert amb["por_desenho"] is False and g["em_quadro"] == 5 and g["sem_nome"] == [4.0]
    assert sum(1 for l in dx._linhas_dos_ambientes(amb) if FRASE in l) == 1


def test_CONTROLE_planta_sem_quadro_fica_como_era():
    amb = dx.ambientes_por_desenho(_planta(), _mapa())
    (g,) = amb["grupos"]
    assert g["em_quadro"] == 0 and amb["em_quadro"] == 0
    assert (amb["etiquetas"], amb["pares"], amb["sem_nome"]) == (3, 2, 1)
    assert FRASE not in "\n".join(dx._linhas_dos_ambientes(amb))


def test_a_tabela_valor_e_nome_na_mesma_linha_sai_da_lista_dos_sem_nome():
    """A tabela "valor | nome" de 11/10 (o nome NA MESMA linha não casa, e as 4
    áreas iam pra linha "SEM nome por perto"): agora são células."""
    tx = []
    for k, (valor, nome) in enumerate([("40,08", "Apto 101"), ("20,74", "Apto 102"),
                                       ("20,90", "Apto 103"), ("25,62", "Apto 104")]):
        y = 10 - 2.5 * H * k
        tx += [_t("A=%sm²" % valor, 10, y), _t(nome, 10 + 10.5 * H, y)]
    amb = dx.ambientes_por_desenho(tx + _planta(), _mapa())
    (g,) = amb["grupos"]
    assert g["sem_nome"] == [4.0] and g["em_quadro"] == 4


# ══════════════════════════════════════════════════════════════════════════
#  Do arquivo ao prompt
# ══════════════════════════════════════════════════════════════════════════
def _dxf(tmp_path, com_quadro=True):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (60, 0), (60, 30), (0, 30)], close=True, dxfattribs={"layer": "ARQ-PAREDE"})
    for t in (_com_quadro() if com_quadro else _planta()):
        msp.add_text(t.text, dxfattribs={"height": t.height, "insert": t.position, "layer": "ARQ-TEXTO"})
    p = str(tmp_path / ("com_quadro.dxf" if com_quadro else "sem_quadro.dxf"))
    doc.saveas(p)
    return p


def test_do_arquivo_ao_prompt(tmp_path, monkeypatch):
    monkeypatch.delenv("AMBIENTE_AREA_ESCRITA", raising=False)
    ex = dx.extract_dxf(_dxf(tmp_path))
    amb = ex.metadata["ambientes_area_escrita"]
    assert (amb["etiquetas"], amb["pares"], amb["sem_nome"], amb["em_quadro"]) == (8, 2, 1, 5)
    prompt = ex.to_structured_prompt()
    i = prompt.index("AMBIENTE ↔ ÁREA ESCRITA NA ETIQUETA")
    secao = prompt[i:prompt.index("\n\n", i)]
    assert "COZINHA = 34.20 m²" in secao and FRASE in " ".join(secao.split())
    assert "615" not in secao and "INTERNOS" not in secao


def test_CONTROLE_do_arquivo_sem_quadro_a_secao_nao_fala_de_quadro(tmp_path, monkeypatch):
    monkeypatch.delenv("AMBIENTE_AREA_ESCRITA", raising=False)
    ex = dx.extract_dxf(_dxf(tmp_path, com_quadro=False))
    assert ex.metadata["ambientes_area_escrita"]["em_quadro"] == 0
    assert "linha de quadro" not in ex.to_structured_prompt()
