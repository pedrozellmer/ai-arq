# -*- coding: utf-8 -*-
"""O NOME do ambiente e a ÁREA escrita na etiqueta chegam à IA como PAR, por desenho.

📏 10/10/2026 — estudo do acervo (342 DXF, 127 jobs): 56 jobs (44 %) têm
etiqueta de área de cômodo, 4.223 etiquetas. O prompt levava o nome e a área em
listas separadas de texto ("CIRCULAÇÃO ×4", "49,82 m² ×3") e quem lia tinha de
adivinhar qual área é de qual ambiente.

Anatomia MEDIDA da etiqueta: o nome no mesmo texto ("BANHO ÁREA=16,35m2") ou num
texto ACIMA da área (até 5 alturas, em outro layer, letra de 0,88 a 2,2×); o que
vem EMBAIXO é atributo (pé-direito, perímetro, piso); a etiqueta de cômodo
estreito vem girada 90°, e "acima" se mede no eixo do próprio texto.

🩸 A mesma planta em 3 pranchas + 1 cópia no modelo: "×N" misturava desenhos que
davam o MESMO ambiente com áreas diferentes. Por isso a lista sai POR DESENHO.

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

H = 0.20                               # altura da letra da etiqueta


def _t(texto, x, y, h=H, layer="AMB-TEXTO", rot=0.0):
    return dx.TextAnnotation(layer=layer, text=texto, position=(x, y), height=h, rotation=rot)


def _pares(textos):
    pares, sem = er.ambientes_com_area_escrita(textos)
    return sorted((p["nome"], p["m2"], p["como"]) for p in pares), sorted(s["m2"] for s in sem)


# ══════════════════════════════════════════════════════════════════════════
#  O nome no MESMO texto
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("texto, nome, m2", [
    ("BANHO ÁREA=16,35m2", "BANHO", 16.35),
    ("COZINHA Ar = 13.80 m²", "COZINHA", 13.80),
    ("SALA 21 A=38,56 m²", "SALA 21", 38.56),
    ("05 A=42,70 m²", "05", 42.70),
    ("DEPÓSITO - ÁREA: 7,20 m²", "DEPÓSITO", 7.20),
    ("COPA A=12,00m%%178", "COPA", 12.00),
    ("SECRETARIA AF= 13.93m²", "SECRETARIA", 13.93),        # área de FORRO
    ("CIRCULAÇÃO AP= 187.42m²", "CIRCULAÇÃO", 187.42),      # área de PISO
    ("AP 101 A=52,30m²", "AP 101", 52.30),                  # "AP" no meio do nome fica
])
def test_o_nome_no_mesmo_texto(texto, nome, m2):
    assert _pares([_t(texto, 0, 0)]) == ([(nome, m2, "mesmo")], [])


def test_area_sozinha_nao_tem_nome_no_mesmo_texto():
    assert er.nome_do_ambiente_no_rotulo("A= 12,30 m²") is None
    assert er.nome_do_ambiente_no_rotulo("ÁREA=12,30m²") is None
    assert er.nome_do_ambiente_no_rotulo("AF= 13.93m²") is None
    assert er.nome_do_ambiente_no_rotulo("12,30 m²") is None


def test_o_texto_em_duas_linhas_do_mtext_e_um_texto_so():
    assert _pares([_t("SALA DE ESTAR\nA=20,00m²", 0, 0)]) == ([("SALA DE ESTAR", 20.0, "mesmo")], [])


# ══════════════════════════════════════════════════════════════════════════
#  O nome ACIMA, em outro texto
# ══════════════════════════════════════════════════════════════════════════
def test_o_nome_acima_da_area_em_outro_layer():
    tx = [_t("CIRCULAÇÃO", 10, 10 + 3 * H, layer="AMB-NOME"), _t("A=49,82m²", 10, 10, layer="AMB-AREA")]
    assert _pares(tx) == ([("CIRCULAÇÃO", 49.82, "acima")], [])


def test_o_que_vem_embaixo_da_area_e_atributo_nao_nome():
    """Nome em cima, área, e EMBAIXO o pé-direito e o piso: só se olha pra cima."""
    tx = [_t("A=12,00m²", 10, 10), _t("PD 2.69M", 10, 10 - 1.5 * H), _t("Piso Cerâmico", 10, 10 - 3 * H)]
    assert _pares(tx) == ([], [12.0])
    assert _pares(tx + [_t("COZINHA", 10, 10 + 2 * H)]) == ([("COZINHA", 12.0, "acima")], [])


def test_ate_tres_linhas_de_codigo_entre_o_nome_e_a_area():
    """Entre o nome e a área cabem as linhas que não são nome: nível, código, pé-direito."""
    tx = [_t("SALA DE ESPERA", 10, 10 + 5 * H), _t("+1.00", 10, 10 + 3.7 * H), _t("P.A.", 10, 10 + 2.5 * H),
          _t("PD 2,60", 10, 10 + 1.3 * H), _t("A=18,40m²", 10, 10)]
    assert _pares(tx) == ([("SALA DE ESPERA", 18.4, "acima")], [])


def test_acima_demais_ja_nao_e_da_etiqueta():
    assert _pares([_t("ARQUIVO", 10, 10 + 5.8 * H), _t("A=9,00m²", 10, 10)]) == ([("ARQUIVO", 9.0, "acima")], [])
    assert _pares([_t("ARQUIVO", 10, 10 + 6.5 * H), _t("A=9,00m²", 10, 10)]) == ([], [9.0])


def test_a_regua_e_a_maior_das_duas_letras():
    """Área miúda e nome 2,2× maior: 3 alturas DO NOME acima são 6,6 da área."""
    tx = [_t("AUDITÓRIO", 10, 10 + 3 * 2.2 * H, h=2.2 * H), _t("A=120,00m²", 10, 10)]
    assert _pares(tx) == ([("AUDITÓRIO", 120.0, "acima")], [])


def test_texto_de_letra_miuda_acima_e_atributo_nao_nome():
    tx = [_t("Forro de gesso", 10, 10 + 2 * H, h=0.6 * H), _t("A=15,00m²", 10, 10)]
    assert _pares(tx) == ([], [15.0])


def test_o_nome_pode_ter_a_letra_um_pouco_menor():
    tx = [_t("VESTIÁRIO", 10, 10 + 2 * H, h=0.88 * H), _t("A=15,00m²", 10, 10)]
    assert _pares(tx) == ([("VESTIÁRIO", 15.0, "acima")], [])


def test_titulo_de_letra_grande_acima_nao_e_nome():
    tx = [_t("PLANTA BAIXA", 10, 10 + 1.2 * 4 * H, h=4 * H), _t("A=15,00m²", 10, 10)]
    assert _pares(tx) == ([], [15.0])


def test_o_que_nao_tem_cara_de_nome_nao_e_nome():
    for nao_nome in ("PD 2.69M", "P.D. 3,00", "H 2,10", "+0,15", "P1", "3,20 x 4,10", "L=12,00m"):
        assert _pares([_t(nao_nome, 10, 10 + 2 * H), _t("A=15,00m²", 10, 10)]) == ([], [15.0]), nao_nome
    # 🪤 medida no nome não barra: a vaga é nome
    assert _pares([_t("VAGA 2,50x5,00m", 10, 10 + 2 * H), _t("A=12,50m²", 10, 10)]) == (
        [("VAGA 2,50x5,00m", 12.5, "acima")], [])


def test_a_janela_lateral_cresce_com_o_tamanho_do_nome():
    area = "A=12,00m²"                                  # 9 letras: até 7 + 4,5 alturas à direita
    assert _pares([_t("SALA", 10 + 11 * H, 10 + 2 * H), _t(area, 10, 10)]) == ([("SALA", 12.0, "acima")], [])
    assert _pares([_t("SALA", 10 + 12.5 * H, 10 + 2 * H), _t(area, 10, 10)]) == ([], [12.0])
    # nome de 4 letras começa até 7 + 2 alturas antes da área; o comprido, bem antes
    assert _pares([_t("SALA", 10 - 8.5 * H, 10 + 2 * H), _t(area, 10, 10)]) == ([("SALA", 12.0, "acima")], [])
    assert _pares([_t("SALA", 10 - 10 * H, 10 + 2 * H), _t(area, 10, 10)]) == ([], [12.0])
    comprido = "SALA DE REUNIÕES DA DIRETORIA"            # 25 letras: até 7 + 12,5 alturas antes
    assert _pares([_t(comprido, 10 - 18 * H, 10 + 2 * H), _t(area, 10, 10)]) == ([(comprido, 12.0, "acima")], [])


def test_o_nome_ao_lado_da_area_um_pouco_acima():
    """O nome escrito AO LADO: 10 alturas ao longo da linha e uma acima. Na MESMA
    linha (nada acima) continua não sendo da etiqueta."""
    area = "A=11,00m²"
    assert _pares([_t("CONCILIAÇÃO", 10 + 10 * H, 10 + 1 * H), _t(area, 10, 10)]) == (
        [("CONCILIAÇÃO", 11.0, "acima")], [])
    assert _pares([_t("CONCILIAÇÃO", 10 - 10 * H, 10 + 1 * H), _t(area, 10, 10)]) == (
        [("CONCILIAÇÃO", 11.0, "acima")], [])
    assert _pares([_t("CONCILIAÇÃO", 10 + 10 * H, 10), _t(area, 10, 10)]) == ([], [11.0])


def test_tabela_valor_e_nome_na_mesma_linha_nao_e_etiqueta():
    """🩸 Medido no acervo (2 arquivos, 20 pares errados): tabela "valor | nome" com
    o nome NA MESMA LINHA, à direita, e as linhas a 2,5 alturas. O nome da linha
    de CIMA fica "ao lado e um pouco acima" do valor de baixo — e casava. Não
    casa: a etiqueta de área mais perto daquele nome é a da própria linha dele."""
    tx = []
    for k, (valor, nome) in enumerate([("40,08", "Apto 101"), ("20,74", "Apto 102"),
                                       ("20,90", "Apto 103"), ("25,62", "Apto 104")]):
        y = 10 - 2.5 * H * k
        tx += [_t("A=%sm²" % valor, 10, y), _t(nome, 10 + 10.5 * H, y)]
    assert _pares(tx) == ([], [20.74, 20.9, 25.62, 40.08])


def test_o_nome_ao_lado_quase_na_mesma_linha_nao_casa_por_ruido():
    """No arquivo real o nome da MESMA linha da tabela casava ou não conforme o
    ruído da coordenada (dy de milésimos). Ao lado, só de 0,4 altura pra cima."""
    area = "A=20,74m²"
    assert _pares([_t("Apto 109", 10 + 10 * H, 10 + 0.01 * H), _t(area, 10, 10)]) == ([], [20.74])
    assert _pares([_t("Apto 109", 10 + 10 * H, 10 + 0.3 * H), _t(area, 10, 10)]) == ([], [20.74])
    assert _pares([_t("Apto 109", 10 + 10 * H, 10 + 0.5 * H), _t(area, 10, 10)]) == ([("Apto 109", 20.74, "acima")], [])
    # 🪤 PERTO (a etiqueta comum) continua valendo logo acima da linha
    assert _pares([_t("Apto 109", 10, 10 + 0.3 * H), _t(area, 10, 10)]) == ([("Apto 109", 20.74, "acima")], [])


def test_o_nome_ao_lado_e_da_area_mais_perto_dele():
    """Duas áreas disputam o mesmo nome ao lado: fica com a mais perto; a outra, sem nome."""
    tx = [_t("ARQUIVO MORTO", 10 + 10 * H, 10 + 1 * H), _t("A=11,00m²", 10, 10),
          _t("A=6,00m²", 10 + 10 * H, 10 - 2 * H)]            # esta está logo ABAIXO do nome
    assert _pares(tx) == ([("ARQUIVO MORTO", 6.0, "acima")], [11.0])


# ══════════════════════════════════════════════════════════════════════════
#  O nome em DUAS linhas
# ══════════════════════════════════════════════════════════════════════════
def test_o_nome_em_duas_linhas():
    tx = [_t("SANITÁRIO", 10, 10 + 3.5 * H), _t("MASCULINO", 10, 10 + 2 * H), _t("A=6,30m²", 10, 10)]
    assert _pares(tx) == ([("SANITÁRIO MASCULINO", 6.3, "acima")], [])


def test_a_linha_de_cima_em_outro_layer_nao_e_do_nome():
    tx = [_t("SETOR ADMINISTRATIVO", 10, 10 + 3.5 * H, layer="AMB-SETOR"), _t("ALMOXARIFADO", 10, 10 + 2 * H),
          _t("A=6,30m²", 10, 10)]
    assert _pares(tx) == ([("ALMOXARIFADO", 6.3, "acima")], [])


def test_a_primeira_linha_do_nome_com_a_letra_maior():
    """ "REUNIÃO" em letra 1,39× maior, em cima de "10 lugares": é o mesmo nome."""
    tx = [_t("REUNIÃO", 10, 10 + 2 * H + 2 * H, h=1.39 * H), _t("10 lugares", 10, 10 + 2 * H),
          _t("A=11,00m²", 10, 10)]
    assert _pares(tx) == ([("REUNIÃO 10 lugares", 11.0, "acima")], [])


def test_o_nome_da_etiqueta_vizinha_nao_vira_a_primeira_linha_do_meu():
    """🩸 Medido no acervo (3 arquivos): duas etiquetas lado a lado, a da direita um
    pouco mais alta e com letra maior. "COPA TERCEIROS" virava a 1ª linha de
    "COPA" ("COPA TERCEIROS COPA = 35,00") e a etiqueta de 7,30 ficava sem nome.
    O texto que é o nome mais perto de ALGUMA área é nome dela."""
    tx = [_t("COPA", 10, 10 + 2 * H), _t("A=35,00m²", 10, 10),
          _t("COPA TERCEIROS", 10 + 9 * H, 10 + 1.2 * H + 2.2 * 1.3 * H, h=1.3 * H),
          _t("A=7,30m²", 10 + 9 * H, 10 + 1.2 * H)]
    assert _pares(tx) == ([("COPA", 35.0, "acima"), ("COPA TERCEIROS", 7.3, "acima")], [])
    assert _pares(list(reversed(tx))) == ([("COPA", 35.0, "acima"), ("COPA TERCEIROS", 7.3, "acima")], [])


def test_a_linha_de_cima_com_outra_letra_nao_e_do_nome():
    """No mesmo layer, logo acima do nome: a letra 2× maior é título de setor, a
    miúda é observação — nenhuma das duas é a 1ª linha do nome."""
    base = [_t("ALMOXARIFADO", 10, 10 + 2 * H), _t("A=6,30m²", 10, 10)]
    grande = _t("ALA NORTE", 10 + H, 10 + 2 * H + 2 * H, h=2 * H)
    assert _pares(base + [grande]) == ([("ALMOXARIFADO", 6.3, "acima")], [])
    miuda = _t("(ver detalhe)", 10, 10 + 2 * H + 1.2 * H, h=0.6 * H)
    assert _pares(base + [miuda]) == ([("ALMOXARIFADO", 6.3, "acima")], [])


def test_a_linha_de_cima_longe_nao_e_do_nome():
    tx = [_t("RECEPÇÃO", 10, 10 + 2 * H + 3 * H), _t("TESOURARIA", 10, 10 + 2 * H), _t("A=6,30m²", 10, 10)]
    assert _pares(tx) == ([("TESOURARIA", 6.3, "acima")], [])


# ══════════════════════════════════════════════════════════════════════════
#  A etiqueta GIRADA
# ══════════════════════════════════════════════════════════════════════════
def test_a_etiqueta_girada_90_graus():
    """Girada 90°, "acima" da linha do texto é à ESQUERDA no desenho."""
    tx = [_t("CORREDOR", 10 - 2 * H, 10, rot=90.0), _t("A=8,10m²", 10, 10, rot=90.0)]
    assert _pares(tx) == ([("CORREDOR", 8.1, "girada")], [])


def test_CONTROLE_o_mesmo_arranjo_sem_o_giro_nao_casa():
    """Com os dois textos na horizontal, o nome à esquerda na mesma linha não está acima."""
    tx = [_t("CORREDOR", 10 - 2 * H, 10), _t("A=8,10m²", 10, 10)]
    assert _pares(tx) == ([], [8.1])


def test_girada_o_texto_do_lado_errado_e_o_atributo():
    """Girada 90°, o que está à DIREITA no desenho está embaixo da área: é atributo."""
    tx = [_t("ÁREA TÉCNICA", 10 + 2 * H, 10, rot=90.0), _t("A=8,10m²", 10, 10, rot=90.0)]
    assert _pares(tx) == ([], [8.1])


def test_nome_e_area_com_angulos_diferentes_nao_sao_a_mesma_etiqueta():
    tx = [_t("CORREDOR", 10, 10 + 2 * H, rot=0.0), _t("A=8,10m²", 10, 10, rot=90.0)]
    assert _pares(tx) == ([], [8.1])
    tx = [_t("CORREDOR", 10, 10 + 2 * H, rot=10.0), _t("A=8,10m²", 10, 10, rot=0.0)]
    assert _pares(tx)[0] == [("CORREDOR", 8.1, "acima")]


def test_180_e_360_graus_nao_sao_girada():
    tx = [_t("CORREDOR", 10, 10 + 2 * H, rot=360.0), _t("A=8,10m²", 10, 10, rot=0.0)]
    assert _pares(tx) == ([("CORREDOR", 8.1, "acima")], [])


# ══════════════════════════════════════════════════════════════════════════
#  A área não pega o nome do vizinho
# ══════════════════════════════════════════════════════════════════════════
def test_a_area_sem_nome_nao_pega_o_nome_do_vizinho():
    """A etiqueta B não tem nome. O mais perto dela é o nome da A — que já é da A
    (mais perto). B fica SEM nome: não desce pro segundo mais perto."""
    tx = [_t("LAVANDERIA", 10, 10 + 2 * H), _t("A=5,00m²", 10, 10),          # etiqueta A
          _t("A=7,00m²", 10 + 3 * H, 10 + 0.4 * H),                          # etiqueta B, sem nome
          _t("DESPENSA", 10 + 3 * H, 10 + 5.5 * H)]                           # 2º mais perto da B
    pares, sem = _pares(tx)
    assert pares == [("LAVANDERIA", 5.0, "acima")] and sem == [7.0]


def test_cada_nome_e_de_uma_area_so():
    tx = [_t("LAVANDERIA", 10, 10 + 2 * H), _t("A=5,00m²", 10, 10), _t("A=7,00m²", 10, 10 + 1 * H)]
    pares, sem = _pares(tx)
    assert pares == [("LAVANDERIA", 7.0, "acima")] and sem == [5.0]


def test_duas_etiquetas_lado_a_lado_cada_uma_com_o_seu_nome():
    tx = [_t("QUARTO 1", 10, 10 + 2 * H), _t("A=9,00m²", 10, 10),
          _t("QUARTO 2", 10 + 20 * H, 10 + 2 * H), _t("A=11,00m²", 10 + 20 * H, 10)]
    assert _pares(tx) == ([("QUARTO 1", 9.0, "acima"), ("QUARTO 2", 11.0, "acima")], [])


# ══════════════════════════════════════════════════════════════════════════
#  TOTAL e RESUMO não são cômodo; lote não é etiqueta de cômodo
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("nome, resumo", [
    ("ÁREA TOTAL", True), ("ÁREA ÚTIL", True), ("ÁREA PRIVATIVA", True), ("ÁREA CONSTRUÍDA", True),
    ("PAVIMENTO TÉRREO", True), ("ÁREA UTILIZADA", True), ("APARTAMENTO TIPO", True),
    ("QUADRO DE ÁREAS", True), ("TABELA DE ÁREAS", True),
    ("ÁREA COMUM", True), ("ÁREAS COMUNS", True), ("NÍVEL DESTINADO A ÁREA DE USO COMUM", True),
    # 🪤 "comum" no meio do nome é cômodo (medido no acervo: 9 etiquetas iam pros totais)
    ("HALL ÁREA COMUM ESCADA E ELEVADOR", False), ("RESÍDUOS COMUM", False), ("WC COMUM", False),
    ("ÁREA DE SERVIÇO", False), ("ÁREA TÉCNICA", False), ("ÁREA DE TRABALHO", False),
    ("SALA DE ESTAR", False), ("COZINHA", False),
])
def test_total_e_resumo_ficam_marcados(nome, resumo):
    assert er.nome_de_ambiente_e_resumo(nome) is resumo
    pares, _sem = er.ambientes_com_area_escrita([_t(nome + " A=30,00m²", 0, 0)])
    assert [(p["nome"], p["resumo"]) for p in pares] == [(nome, resumo)]


def test_cabecalho_de_quadro_em_cima_do_valor_nao_e_comodo():
    """🩸 Medido no acervo: "399,89 m²" embaixo da coluna "ÁREA" de um quadro saía
    como um cômodo chamado ÁREA; "9,37 m²" embaixo de "QUANTIDADE", idem. O
    cabeçalho casa (não deixa a área pegar o texto seguinte), mas sai como RESUMO."""
    for cab in ("ÁREA", "QUANTIDADE", "Área:", "TOTAL", "(ÁREA)"):
        pares, sem = er.ambientes_com_area_escrita(
            [_t("SALA DE AULA", 10, 10 + 4.5 * H), _t(cab, 10, 10 + 2 * H), _t("399,89 m²", 10, 10)])
        assert [(p["nome"], p["resumo"]) for p in pares] == [(cab, True)] and sem == [], cab
    # 🪤 só a palavra SOZINHA: "ÁREA DE SERVIÇO" e "QUANTIDADE MÍNIMA" são outros textos
    assert er.nome_de_ambiente_e_resumo("ÁREA DE SERVIÇO") is False
    assert er.nome_de_ambiente_e_resumo("05") is False, "o número da loja é nome, não cabeçalho"


def test_rotulo_de_lote_nao_entra():
    assert _pares([_t("ÁREA DO TERRENO = 300,00 m²", 0, 0)]) == ([], [])
    # o nome de lote num texto à parte casa, mas sai como RESUMO — fora dos ambientes
    pares, _sem = er.ambientes_com_area_escrita([_t("LOTE 12", 0, 2 * H), _t("A=300,00m²", 0, 0)])
    assert [(p["nome"], p["resumo"]) for p in pares] == [("LOTE 12", True)]


def test_sem_etiqueta_de_area_nao_ha_o_que_listar():
    assert er.ambientes_com_area_escrita([_t("COZINHA", 0, 0), _t("12,30", 0, -H), _t("3,20 m", 2, 0)]) == ([], [])
    assert er.ambientes_com_area_escrita([]) == ([], [])
    assert er.ambientes_com_area_escrita(None) == ([], [])


def test_texto_sem_altura_usa_a_mediana_do_desenho():
    tx = [_t("COZINHA", 10, 10 + 2 * H), _t("A=12,00m²", 10, 10, h=0), _t("x", 50, 50), _t("y", 60, 60)]
    assert _pares(tx)[0] == [("COZINHA", 12.0, "acima")]


def test_a_posicao_do_par_e_a_da_etiqueta_de_area():
    pares, sem = er.ambientes_com_area_escrita(
        [_t("COZINHA", 10, 10 + 2 * H), _t("A=12,00m²", 10, 10), _t("A=3,00m²", 40, 40)])
    assert (pares[0]["x"], pares[0]["y"]) == (10, 10)
    assert (sem[0]["x"], sem[0]["y"], sem[0]["texto"]) == (40, 40, "A=3,00m²")


# ══════════════════════════════════════════════════════════════════════════
#  POR DESENHO — o mesmo ambiente em várias pranchas não soma
# ══════════════════════════════════════════════════════════════════════════
def _etiquetas(x0, circulacao, reuniao, extra=()):
    tx = [_t("CIRCULAÇÃO", x0 + 10, 10 + 3 * H), _t("A=%s" % circulacao, x0 + 10, 10),
          _t("SALA DE REUNIÃO A=%s" % reuniao, x0 + 20, 15)]
    return tx + list(extra)


def _mapa(origem=""):
    m = {"folhas": [
        {"folha": "A1 PLANTA", "titulo": "PLANTA BAIXA TÉRREO", "tipo": "planta", "caixa": (0, 0, 40, 30)},
        {"folha": "A2 LAYOUT", "titulo": "PLANTA DE LAYOUT TÉRREO", "tipo": "planta", "caixa": (50, 0, 90, 30)},
    ]}
    if origem:
        m["origem"] = origem
    return m


def _tudo():
    return (_etiquetas(0, "49,82m²", "26,75m²")
            + _etiquetas(50, "49,82m²", "29,86m²")
            + _etiquetas(200, "46,60m²", "29,86m²",
                         extra=[_t("ÁREA TOTAL = 491,00m²", 220, 25), _t("A=90,00m²", 230, 5)]))


def test_os_pares_saem_por_desenho_e_o_de_fora_por_ultimo():
    amb = dx.ambientes_por_desenho(_tudo(), _mapa())
    assert amb["por_desenho"] is True
    assert (amb["etiquetas"], amb["pares"], amb["sem_nome"]) == (8, 7, 1)
    g1, g2, fora = amb["grupos"]
    assert g1["desenho"] == "PLANTA BAIXA TÉRREO — folha A1 PLANTA" and g1["tipo"] == "planta" and not g1["fora"]
    assert g1["ambientes"] == [["CIRCULAÇÃO", 49.82, 1], ["SALA DE REUNIÃO", 26.75, 1]]
    assert g2["desenho"] == "PLANTA DE LAYOUT TÉRREO — folha A2 LAYOUT"
    assert g2["ambientes"] == [["CIRCULAÇÃO", 49.82, 1], ["SALA DE REUNIÃO", 29.86, 1]]
    assert fora["fora"] is True and fora["desenho"] == ""
    assert fora["ambientes"] == [["CIRCULAÇÃO", 46.6, 1], ["SALA DE REUNIÃO", 29.86, 1]]
    assert fora["totais"] == [["ÁREA TOTAL", 491.0, 1]] and fora["sem_nome"] == [90.0]
    assert g1["totais"] == [] and g1["sem_nome"] == []


def test_o_grupo_de_fora_fica_por_ultimo_mesmo_vindo_primeiro():
    amb = dx.ambientes_por_desenho(list(reversed(_tudo())), _mapa())
    assert [g["fora"] for g in amb["grupos"]] == [False, False, True]
    assert [g["desenho"].split(" — ")[0] for g in amb["grupos"][:2]] == [
        "PLANTA BAIXA TÉRREO", "PLANTA DE LAYOUT TÉRREO"], "os desenhos saem na ordem do mapa"


def test_no_mesmo_desenho_etiquetas_iguais_sao_xN():
    tx = [_t("SUÍTE A=22,50m²", 5 + 8 * i, 20) for i in range(4)] + [_t("SUÍTE A=24,00m²", 5, 5)]
    amb = dx.ambientes_por_desenho(tx, _mapa())
    assert amb["grupos"][0]["ambientes"] == [["SUÍTE", 22.5, 4], ["SUÍTE", 24.0, 1]]


def test_a_etiqueta_que_duas_janelas_mostram_sai_uma_vez_no_grupo_dos_dois():
    """🩸 Medido no acervo: 3 pranchas mostrando a MESMA região do modelo
    repetiam as 95 etiquetas 3 vezes. A etiqueta é UM texto: sai uma vez."""
    m = _mapa()
    m["folhas"][1]["caixa"] = (0, 0, 40, 30)              # a mesma região do modelo em 2 pranchas
    amb = dx.ambientes_por_desenho(_etiquetas(0, "49,82m²", "26,75m²"), m)
    assert len(amb["grupos"]) == 1 and amb["pares"] == 2
    g = amb["grupos"][0]
    assert g["desenhos"] == 2 and not g["fora"] and g["tipo"] == "planta"
    assert g["desenho"] == ("PLANTA BAIXA TÉRREO — folha A1 PLANTA"
                            " + PLANTA DE LAYOUT TÉRREO — folha A2 LAYOUT")
    assert g["ambientes"] == [["CIRCULAÇÃO", 49.82, 1], ["SALA DE REUNIÃO", 26.75, 1]]
    ls = dx._linhas_dos_ambientes(amb)
    cab = next(l for l in ls if l.startswith("  [PLANTA BAIXA"))
    assert "as MESMAS etiquetas, mostradas nos 2 desenhos" in cab and "conte UMA vez" in cab
    assert sum(1 for l in ls if "CIRCULAÇÃO = 49.82 m²" in l) == 1


def test_a_janela_que_mostra_so_um_pedaco_divide_o_desenho_em_dois_grupos():
    """A prancha A mostra a planta toda; a B, só o canto da sala de reunião (uma
    ampliação). A sala sai no grupo "A + B"; a circulação, só no "A". Nada se repete."""
    m = _mapa()
    m["folhas"][1].update(tipo="fora", caixa=(18, 13, 30, 18))
    amb = dx.ambientes_por_desenho(_etiquetas(0, "49,82m²", "26,75m²"), m)
    so_a, a_e_b = amb["grupos"]
    assert (so_a["desenhos"], so_a["ambientes"]) == (1, [["CIRCULAÇÃO", 49.82, 1]])
    assert (a_e_b["desenhos"], a_e_b["ambientes"]) == (2, [["SALA DE REUNIÃO", 26.75, 1]])
    assert a_e_b["tipo"] == "", "planta + ampliação: o grupo não tem um tipo só"
    assert sum(k for g in amb["grupos"] for _n, _v, k in g["ambientes"]) == amb["pares"] == 2


def test_muitos_desenhos_com_a_mesma_etiqueta_o_cabecalho_resume():
    m = {"folhas": [{"folha": "F%d" % i, "titulo": "PLANTA %d" % i, "tipo": "planta", "caixa": (0, 0, 40, 30)}
                    for i in range(6)]}
    amb = dx.ambientes_por_desenho(_etiquetas(0, "49,82m²", "26,75m²"), m)
    (g,) = amb["grupos"]
    assert g["desenhos"] == 6 and g["desenho"].endswith("PLANTA 3 — folha F3 (+2)")


def test_duas_janelas_do_mesmo_desenho_sao_um_grupo_so():
    m = _mapa()
    m["folhas"][1].update(folha="A1 PLANTA", titulo="PLANTA BAIXA TÉRREO", caixa=(0, 0, 40, 30))
    amb = dx.ambientes_por_desenho(_etiquetas(0, "49,82m²", "26,75m²"), m)
    assert len(amb["grupos"]) == 1
    assert amb["grupos"][0]["ambientes"] == [["CIRCULAÇÃO", 49.82, 1], ["SALA DE REUNIÃO", 26.75, 1]]


@pytest.mark.parametrize("mapa", [None, {}, {"folhas": []}, "modelo", "modelo sem janela"])
def test_sem_janela_do_papel_a_lista_e_uma_so(mapa):
    """Sem mapa, ou com os desenhos achados pelo título no modelo: "fora deles"
    não quer dizer fora das pranchas — sai tudo num grupo, com ×N."""
    if isinstance(mapa, str):
        mapa = _mapa(origem=mapa)
    amb = dx.ambientes_por_desenho(_tudo(), mapa)
    assert amb["por_desenho"] is False and len(amb["grupos"]) == 1
    g = amb["grupos"][0]
    assert g["fora"] is False
    assert g["ambientes"] == [["CIRCULAÇÃO", 46.6, 1], ["CIRCULAÇÃO", 49.82, 2],
                              ["SALA DE REUNIÃO", 26.75, 1], ["SALA DE REUNIÃO", 29.86, 2]]
    assert g["totais"] == [["ÁREA TOTAL", 491.0, 1]] and g["sem_nome"] == [90.0]


def test_sem_etiqueta_de_area_nao_ha_registro():
    assert dx.ambientes_por_desenho([_t("COZINHA", 1, 1), _t("3,20", 2, 2)], _mapa()) == {}
    assert dx.ambientes_por_desenho([], _mapa()) == {}


def test_nunca_levanta(monkeypatch):
    def _quebra(_t):
        raise RuntimeError("x")
    monkeypatch.setattr(er, "ambientes_com_area_escrita", _quebra)
    assert dx.ambientes_por_desenho(_tudo(), _mapa()) == {}


# ══════════════════════════════════════════════════════════════════════════
#  A seção do prompt
# ══════════════════════════════════════════════════════════════════════════
def test_a_secao_por_desenho_diz_que_nao_soma():
    ls = dx._linhas_dos_ambientes(dx.ambientes_por_desenho(_tudo(), _mapa()))
    txt = "\n".join(ls)
    assert ls[0].startswith("AMBIENTE ↔ ÁREA ESCRITA NA ETIQUETA")
    assert "NÃO some um desenho com o outro" in txt and "outra versão da planta" in txt
    assert "só lugares diferentes (outro pavimento" in txt, "dois desenhos podem ser dois andares com os mesmos cômodos"
    assert "a quantidade é a MEDIDA" in txt and "a área escrita serve pra" in txt, (
        "sem a precedência, a linha medida do ambiente vira linha estimada pela etiqueta")
    assert "  [PLANTA BAIXA TÉRREO — folha A1 PLANTA]  (planta)" in ls
    assert "    CIRCULAÇÃO = 49.82 m²" in ls and "    SALA DE REUNIÃO = 26.75 m²" in ls
    assert "    CIRCULAÇÃO = 46.60 m²" in ls
    i_fora = next(i for i, l in enumerate(ls) if l.startswith("  [FORA DAS PRANCHAS"))
    assert i_fora > ls.index("  [PLANTA DE LAYOUT TÉRREO — folha A2 LAYOUT]  (planta)")
    assert any("totais/resumos escritos (NÃO são ambiente" in l and "ÁREA TOTAL = 491.00 m²" in l
               for l in ls[i_fora:])
    assert any("+ 1 etiqueta(s) de área SEM nome por perto: 90.00 m²" in l for l in ls[i_fora:])
    assert ls[-1] == ""


def test_a_janela_geral_ou_sem_leitura_e_dita_no_grupo_de_fora():
    """ "Fora das janelas lidas" não é "nenhuma prancha mostra": a janela geral e a
    que não deu pra ler ficam fora do mapa — a seção diz quantas são."""
    m = _mapa()
    assert dx.ambientes_por_desenho(_tudo(), m)["janelas_nao_usadas"] == 0
    sem = "\n".join(dx._linhas_dos_ambientes(dx.ambientes_por_desenho(_tudo(), m)))
    assert "sem leitura ficou" not in sem
    m.update(gerais=2, sem_janela=1)
    amb = dx.ambientes_por_desenho(_tudo(), m)
    assert amb["janelas_nao_usadas"] == 3
    assert "(3 janela(s) geral(is) ou sem leitura ficou(aram) de fora)" in "\n".join(dx._linhas_dos_ambientes(amb))
    m["origem"] = "modelo"                                # sem janela do papel não há "fora"
    assert dx.ambientes_por_desenho(_tudo(), m)["janelas_nao_usadas"] == 0


def test_a_secao_sem_mapa_avisa_do_xN():
    ls = dx._linhas_dos_ambientes(dx.ambientes_por_desenho(_tudo(), None))
    txt = "\n".join(ls)
    assert "a mesma etiqueta N vezes no ARQUIVO" in txt and "POR DESENHO" not in txt
    assert "  CIRCULAÇÃO = 49.82 m²   ×2" in ls and "  CIRCULAÇÃO = 46.60 m²" in ls
    assert not any(l.startswith("  [") for l in ls)


def test_o_tipo_do_desenho_vai_no_cabecalho():
    m = _mapa()
    m["folhas"][0]["tipo"], m["folhas"][1]["tipo"] = "fora", ""
    ls = dx._linhas_dos_ambientes(dx.ambientes_por_desenho(_tudo(), m))
    assert "  [PLANTA BAIXA TÉRREO — folha A1 PLANTA]  (detalhe/esquema)" in ls
    assert "  [PLANTA DE LAYOUT TÉRREO — folha A2 LAYOUT]" in ls


def test_a_lista_cortada_diz_quantos_ficaram_de_fora():
    tx = [_t("LOJA %02d A=%d,00m²" % (i, 10 + i), 2 + (i % 12) * 3, 2 + (i // 12) * 3) for i in range(30)]
    amb = dx.ambientes_por_desenho(tx, None)
    ls = dx._linhas_dos_ambientes(amb, limite=25)
    assert sum(1 for l in ls if l.startswith("  LOJA ")) == 25
    assert "  (+5 par(es) deste grupo não listado(s))" in ls
    inteira = dx._linhas_dos_ambientes(amb)
    assert sum(1 for l in inteira if l.startswith("  LOJA ")) == 30
    assert not any("não listado" in l for l in inteira)


def test_as_areas_sem_nome_alem_do_teto_viram_contagem():
    tx = [_t("A=%d,00m²" % (10 + i), 2 + i * 3, 2) for i in range(15)]
    ls = dx._linhas_dos_ambientes(dx.ambientes_por_desenho(tx, None))
    linha = next(l for l in ls if "SEM nome" in l)
    assert linha.startswith("  + 15 etiqueta(s) de área SEM nome por perto: 10.00 · 11.00")
    assert linha.endswith("21.00 (+3) m²")


def test_sem_registro_nao_ha_secao():
    assert dx._linhas_dos_ambientes(None) == [] and dx._linhas_dos_ambientes({}) == []
    assert dx._linhas_dos_ambientes({"grupos": [{"ambientes": [], "totais": [], "sem_nome": []}]}) == []


# ══════════════════════════════════════════════════════════════════════════
#  REGRA DURA Nº1 — área escrita não leva selo de medido
# ══════════════════════════════════════════════════════════════════════════
def _item(obs, conf="confirmado"):
    return {"description": "Piso da sala", "unit": "m²", "quantity": 12.3, "confidence": conf,
            "observations": obs, "origem": "dxf_geom"}


@pytest.mark.parametrize("obs", [
    "Fonte: AMBIENTE ↔ ÁREA ESCRITA NA ETIQUETA — SALA = 12,30 m².",
    "Área escrita na etiqueta do ambiente: SALA = 12,30 m².",
    "Fonte: secao AMBIENTE - AREA ESCRITA NA ETIQUETA (SALA = 12.30 m2).",
])
def test_linha_que_cita_a_secao_nao_passa_com_selo_de_medido(obs):
    """A seção entrega o número que o PROJETISTA escreveu. Se a IA der selo de
    medido citando a seção, o guarda do selo tem de acusar."""
    achados = er.selos_sem_geometria([_item(obs)])
    assert [a["indice"] for a in achados] == [0], obs


def test_CONTROLE_a_mesma_linha_como_estimado_nao_e_acusada():
    assert er.selos_sem_geometria([_item("Fonte: AMBIENTE ↔ ÁREA ESCRITA NA ETIQUETA — SALA = 12,30 m².",
                                         conf="estimado")]) == []


def test_CONTROLE_etiqueta_sozinha_nao_e_procedencia_de_texto():
    """🪤 "etiqueta" SOZINHA não entra na lista: 4 linhas confirmadas de
    comprimento de layer citam "diâmetros pelas etiquetas" e são medição."""
    assert er.selos_sem_geometria([_item("Diâmetros conferidos pelas etiquetas do desenho.")]) == []
    assert "etiqueta" not in er._PROCEDENCIA_TEXTO


def test_CONTROLE_area_medida_que_tambem_cita_a_etiqueta_fica_com_o_selo():
    """A área veio da hachura; a etiqueta só confere. É medição."""
    obs = "Fonte: área hachurada no layer 'PISO' = 12,31 m²; confere com a área escrita na etiqueta (12,30 m²)."
    assert er.selos_sem_geometria([_item(obs)]) == []


# ══════════════════════════════════════════════════════════════════════════
#  Do arquivo ao prompt
# ══════════════════════════════════════════════════════════════════════════
def _viewport(lay, janela, centro_papel=(200, 150)):
    x0, y0, x1, y1 = janela
    esc = 10.0
    return lay.add_viewport(center=centro_papel, size=((x1 - x0) * esc, (y1 - y0) * esc),
                            view_center_point=((x0 + x1) / 2, (y0 + y1) / 2), view_height=(y1 - y0))


def _titulo(msp, doc, texto, x, y):
    if "TIT" not in doc.blocks:
        b = doc.blocks.new("TIT")
        b.add_attdef("TITULODODESENHO", (0, 0), dxfattribs={"height": 0.3})
    msp.add_blockref("TIT", (x, y)).add_attrib("TITULODODESENHO", texto, (x, y))


def _planta(msp, x0, circulacao, reuniao, girada=None):
    for y in (2, 28):
        msp.add_line((x0 + 2, y), (x0 + 38, y), dxfattribs={"layer": "ARQ-PAREDE"})
    msp.add_text("CIRCULAÇÃO", dxfattribs={"height": H, "layer": "AMB-NOME", "insert": (x0 + 10, 10 + 3 * H)})
    msp.add_text("A=%s" % circulacao, dxfattribs={"height": H, "layer": "AMB-AREA", "insert": (x0 + 10, 10)})
    msp.add_mtext("SALA DE REUNIÃO\\PA=%s" % reuniao,
                  dxfattribs={"char_height": H, "layer": "AMB-AREA", "insert": (x0 + 20, 15)})
    if girada:
        msp.add_text("SHAFT", dxfattribs={"height": H, "layer": "AMB-NOME", "insert": (x0 + 30 - 2 * H, 20),
                                          "rotation": 90})
        mt = msp.add_mtext("A=%s" % girada, dxfattribs={"char_height": H, "layer": "AMB-AREA",
                                                         "insert": (x0 + 30, 20)})
        mt.dxf.text_direction = (0, 1, 0)                 # MTEXT girado pela DIREÇÃO, não pelo `rotation`


def _arquivo(tmp_path, folhas=True, copia_fora=True):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6                         # metros
    msp = doc.modelspace()
    _planta(msp, 0, "49,82m²", "26,75m²", girada="2,40m²")
    _titulo(msp, doc, "PLANTA BAIXA TÉRREO", 20, 1)
    _planta(msp, 50, "49,82m²", "29,86m²")
    _titulo(msp, doc, "PLANTA DE LAYOUT TÉRREO", 70, 1)
    if copia_fora:
        _planta(msp, 200, "46,60m²", "29,86m²")
    if folhas:
        _viewport(doc.layouts.new("A1 PLANTA"), (0, 0, 40, 30))
        _viewport(doc.layouts.new("A2 LAYOUT"), (50, 0, 90, 30))
    p = str(tmp_path / "planta.dxf")
    doc.saveas(p)
    return p


def test_o_extrator_guarda_o_angulo_do_texto(tmp_path):
    ex = dx.extract_dxf(_arquivo(tmp_path))
    ang = {(t.text, round(t.position[0], 2)): t.rotation for t in ex.texts}
    assert ang[("SHAFT", round(30 - 2 * H, 2))] == pytest.approx(90.0)
    assert ang[("A=2,40m²", 30.0)] == pytest.approx(90.0), "o MTEXT girado pela direção do texto"
    assert ang[("CIRCULAÇÃO", 10.0)] == 0.0
    assert all(isinstance(t.rotation, float) for t in ex.texts)


def test_o_texto_sem_angulo_e_horizontal():
    assert dx.TextAnnotation(layer="X", text="Y").rotation == 0.0
    assert dx._angulo_do_texto(object()) == 0.0


def test_do_arquivo_ao_prompt_por_desenho(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    monkeypatch.delenv("AMBIENTE_AREA_ESCRITA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path))
    amb = ex.metadata.get("ambientes_area_escrita")
    assert amb and amb["por_desenho"] is True, amb
    por = {g["desenho"] or "FORA": g["ambientes"] for g in amb["grupos"]}
    assert por["PLANTA BAIXA TÉRREO — folha A1 PLANTA"] == [
        ["CIRCULAÇÃO", 49.82, 1], ["SALA DE REUNIÃO", 26.75, 1], ["SHAFT", 2.4, 1]]
    assert por["PLANTA DE LAYOUT TÉRREO — folha A2 LAYOUT"] == [
        ["CIRCULAÇÃO", 49.82, 1], ["SALA DE REUNIÃO", 29.86, 1]]
    assert por["FORA"] == [["CIRCULAÇÃO", 46.6, 1], ["SALA DE REUNIÃO", 29.86, 1]]
    prompt = ex.to_structured_prompt()
    assert "AMBIENTE ↔ ÁREA ESCRITA NA ETIQUETA" in prompt
    assert "  [PLANTA BAIXA TÉRREO — folha A1 PLANTA]  (planta)\n    CIRCULAÇÃO = 49.82 m²" in prompt
    assert "[FORA DAS PRANCHAS" in prompt and "    CIRCULAÇÃO = 46.60 m²" in prompt
    assert "ambientes_area_escrita:" not in prompt, "o registro cru não vai pro prompt — só a seção"


def test_do_arquivo_ao_prompt_sem_folha(tmp_path, monkeypatch):
    monkeypatch.delenv("AMBIENTE_AREA_ESCRITA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, folhas=False))
    amb = ex.metadata["ambientes_area_escrita"]
    assert amb["por_desenho"] is False and len(amb["grupos"]) == 1
    prompt = ex.to_structured_prompt()
    assert "  CIRCULAÇÃO = 49.82 m²   ×2" in prompt and "a mesma etiqueta N vezes no ARQUIVO" in prompt
    assert "[FORA DAS PRANCHAS" not in prompt


def test_com_a_leitura_por_folha_desligada_a_lista_e_uma_so(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    monkeypatch.delenv("AMBIENTE_AREA_ESCRITA", raising=False)
    amb = dx.extract_dxf(_arquivo(tmp_path)).metadata["ambientes_area_escrita"]
    assert amb["por_desenho"] is False and amb["pares"] == 7


def test_a_chave_desliga_sem_deploy(tmp_path, monkeypatch):
    monkeypatch.setenv("AMBIENTE_AREA_ESCRITA", "0")
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert "ambientes_area_escrita" not in ex.metadata
    assert "AMBIENTE ↔ ÁREA ESCRITA" not in ex.to_structured_prompt()


def test_CONTROLE_planta_sem_etiqueta_de_area_fica_como_era(tmp_path, monkeypatch):
    monkeypatch.delenv("AMBIENTE_AREA_ESCRITA", raising=False)
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "ARQ-PAREDE"})
    msp.add_text("COZINHA", dxfattribs={"height": H, "layer": "AMB-NOME", "insert": (2, 2)})
    p = str(tmp_path / "sem.dxf")
    doc.saveas(p)
    ex = dx.extract_dxf(p)
    assert "ambientes_area_escrita" not in ex.metadata
    assert "AMBIENTE ↔ ÁREA ESCRITA" not in ex.to_structured_prompt()
