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
    # duas áreas no mesmo texto: o nome é o que vem depois da primeira (medido: 24 pares do acervo)
    ("ÁREA DE CORTE= 46,72m² ÁREA DE ATERRO= 2,50m²", "ÁREA DE ATERRO", 2.50),
    ("SECRETARIA AF= 13.93m²", "SECRETARIA", 13.93),        # área de FORRO
    ("CIRCULAÇÃO AP= 187.42m²", "CIRCULAÇÃO", 187.42),      # área de PISO
    ("AP 101 A=52,30m²", "AP 101", 52.30),                  # "AP" no meio do nome fica
])
def test_o_nome_no_mesmo_texto(texto, nome, m2):
    assert _pares([_t(texto, 0, 0)]) == ([(nome, m2, "mesmo")], [])


@pytest.mark.parametrize("texto, m2", [
    ("A:426,98m²x6 = 2.561,88m²", 2561.88),     # área × pavimentos: depois da outra área só sobra o multiplicador
    ("429,00 m² x 2 = 858,00 m²", 858.00),
    ("894,89x7 = 6.264,23 m²", 6264.23),        # número × número
    ("A: 894,89x7 = 6.264,23 m²", 6264.23),
    ("2x4 = 8,00 m²", 8.00),
])
def test_conta_antes_do_igual_nao_e_nome_de_ambiente(texto, m2):
    """📏 Acervo (2 pranchas de aprovação): a linha de conta saía como um
    ambiente chamado "x6" ou "894,89x7". Continua etiqueta de área — sem nome."""
    assert er.rotulo_area_de_comodo(texto) == pytest.approx(m2)
    assert er.nome_do_ambiente_no_rotulo(texto) is None
    assert _pares([_t(texto, 0, 0)]) == ([], [m2])


def test_CONTROLE_nome_com_x_ou_numero_que_nao_e_conta_fica():
    assert er.nome_do_ambiente_no_rotulo("X1 A=12,30 m²") == "X1"          # sem número na frente nem outra área
    assert er.nome_do_ambiente_no_rotulo("05 A=42,70 m²") == "05"
    assert er.nome_do_ambiente_no_rotulo("BOX 2 A=3,10 m²") == "BOX 2"
    assert er.nome_do_ambiente_no_rotulo("SALA 2x4 A=8,00 m²") == "SALA 2x4"


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
#  A ÂNCORA do texto — a régua mede pelo INÍCIO dele
# ══════════════════════════════════════════════════════════════════════════
LARG = er._AMB_LARGURA_DA_LETRA


def _ta(texto, x, y, al, h=H, layer="AMB-TEXTO", rot=0.0):
    return dx.TextAnnotation(layer=layer, text=texto, position=(x, y), height=h, rotation=rot, alinhamento=al)


def test_o_nome_ancorado_a_direita_e_medido_pelo_inicio():
    """🩸 Arquivo de cliente: os nomes eram MTEXT ancorado no topo-DIREITA. O ponto
    gravado é a ponta direita; lido como início, o nome ficava 14 alturas à
    direita de onde está e a área pegava o nome do cômodo vizinho."""
    nome = "DEFENSORIA PÚBLICA 01"
    fim = 10 + len(nome) * H * LARG
    assert _pares([_ta(nome, fim, 10 + 2 * H, 2), _t("A=8,37m²", 10, 10)]) == ([(nome, 8.37, "acima")], [])
    # CONTROLE: o mesmo ponto como INÍCIO fica 14,7 alturas à direita da área — fora
    assert _pares([_ta(nome, fim, 10 + 2 * H, 0), _t("A=8,37m²", 10, 10)]) == ([], [8.37])


@pytest.mark.parametrize("al, passo", [(2, 8.0), (1, 4.5)])
def test_comodos_lado_a_lado_com_o_nome_ancorado_no_fim_ou_no_meio(al, passo):
    """Lido como início, o nome de cada cômodo cai em cima da área do cômodo
    SEGUINTE — e todo par sai deslocado de um."""
    nomes, areas = ["DEFENSOR 01", "DEFENSOR 02", "DEFENSOR 03"], ["8,37", "8,40", "8,73"]
    tx = []
    for i, (n, a) in enumerate(zip(nomes, areas)):
        x = 10 + i * passo * H
        ancora = x + (1.0 if al == 2 else 0.5) * len(n) * H * LARG
        tx += [_ta(n, ancora, 10 + 2 * H, al), _t("A=%sm²" % a, x, 10)]
    assert _pares(tx) == ([("DEFENSOR 01", 8.37, "acima"), ("DEFENSOR 02", 8.4, "acima"),
                           ("DEFENSOR 03", 8.73, "acima")], [])


def test_a_ancora_segue_o_giro_do_texto():
    """Girada 90°, o texto corre pra cima: o FIM dele está acima do início."""
    nome = "CORREDOR DE SERVIÇO"
    larg = len(nome) * H * LARG
    tx = [_ta(nome, 10 - 2 * H, 10 + larg, 2, rot=90.0), _t("A=8,10m²", 10, 10, rot=90.0)]
    assert _pares(tx) == ([(nome, 8.1, "girada")], [])


def test_a_area_ancorada_a_direita_tambem_e_medida_pelo_inicio_e_guarda_a_posicao_gravada():
    area = "A=8,37m²"
    fim = 10 + len(area) * H * LARG
    pares, sem = er.ambientes_com_area_escrita([_t("COPA", 10, 10 + 2 * H), _ta(area, fim, 10, 2)])
    assert [(p["nome"], p["m2"]) for p in pares] == [("COPA", 8.37)] and sem == []
    assert (pares[0]["x"], pares[0]["y"]) == (fim, 10), "o par guarda o ponto gravado, não o início calculado"
    _p, sem = er.ambientes_com_area_escrita([_ta("A=3,00m²", 40, 40, 2)])
    assert (sem[0]["x"], sem[0]["y"]) == (40, 40)


def test_texto_de_varias_linhas_a_largura_e_a_da_maior():
    """Somar as letras das duas linhas recuaria o início 5,6 alturas além da
    conta — pra cima da etiqueta do cômodo à ESQUERDA, que levaria o nome."""
    nome = "SALA DE\nREUNIÕES DA DIRETORIA"
    fim = 10 + len("REUNIÕES DA DIRETORIA") * H * LARG
    tx = [_ta(nome, fim, 10 + 2 * H, 2), _t("A=30,00m²", 10, 10), _t("A=9,00m²", 10 - 6 * H, 10)]
    assert _pares(tx) == ([("SALA DE REUNIÕES DA DIRETORIA", 30.0, "acima")], [9.0])


def test_o_par_pelo_mesmo_texto_tambem_guarda_o_ponto_gravado():
    pares, _sem = er.ambientes_com_area_escrita([_ta("COPA A=8,37m²", 40, 40, 2)])
    assert (pares[0]["nome"], pares[0]["x"], pares[0]["y"]) == ("COPA", 40, 40)


# ══════════════════════════════════════════════════════════════════════════
#  A etiqueta inteira num texto só, sem "="
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("texto, esperado", [
    ("COPA 2,00 m²", ("COPA", 2.0)),
    ("SUÍTE 01\n14,44m²", ("SUÍTE 01", 14.44)),
    ("PROFESSORES 13,83M²", ("PROFESSORES", 13.83)),
    ("ÁREA TOTAL 1.234,56 m²", ("ÁREA TOTAL", 1234.56)),
    ("VAGA 2,50x5,00 12,50 m²", ("VAGA 2,50x5,00", 12.5)),
    ("137 und ou 8,56 m²", None),                    # nota de quantidade: não começa por letra
    ("12,30 m²", None), ("B 12,30 m²", None), ("P1 12,30 m²", None),     # nome curto demais
    # a palavra que só anuncia a área: a etiqueta vale, SEM nome (o nome está no texto de cima)
    ("Área 35,00 m²", (None, 35.0)), ("ÁREA 7,28 m²", (None, 7.28)), ("A 12,30 m²", (None, 12.3)),
    ("CANTEIRO AJARDINADO COM PLANTIO DE ÁRVORE PORTE MÉDIO ÁREA MÍNIMA 1m²", None),
    ("ÁREA DE CORTE 46,72m² ÁREA DE ATERRO 2,50m²", None),      # duas áreas no mesmo texto
    ("TERRENO 300,00 m²", None), ("COPA 0,80 m²", None),
    ("SALA A=12,00m²", None), ("COPA: 2,00 m²", None),           # com "=" ou ":" é a outra régua
    ("COMPRIMENTO 12,30 m", None),
])
def test_nome_e_area_no_mesmo_texto(texto, esperado):
    assert er.nome_e_area_no_mesmo_texto(texto) == esperado


def test_a_etiqueta_sem_igual_vira_par_pelo_mesmo_texto():
    """📏 Acervo: uma casa inteira com as 33 etiquetas nesta forma."""
    tx = [_t("GARAGEM\n47,55m²", 0, 0), _t("COZINHA 13,57m²", 30, 0), _t("SUÍTE 01 14,44m²", 60, 0)]
    assert _pares(tx) == ([("COZINHA", 13.57, "mesmo"), ("GARAGEM", 47.55, "mesmo"),
                           ("SUÍTE 01", 14.44, "mesmo")], [])


def test_area_anunciada_sem_igual_procura_o_nome_em_cima():
    """📏 Acervo: 36 etiquetas "Área 35,00 m²" em 2 pranchas, com o nome do cômodo
    no texto de cima. "Área" é o prefixo, não o nome — nem um total chamado ÁREA."""
    pares, sem = er.ambientes_com_area_escrita([_t("COPA", 10, 10 + 2 * H), _t("Área 35,00 m²", 10, 10)])
    assert [(p["nome"], p["m2"], p["como"], p["resumo"]) for p in pares] == [("COPA", 35.0, "acima", False)]
    assert sem == []
    assert _pares([_t("Área 35,00 m²", 10, 10)]) == ([], [35.0])


def test_texto_que_ja_traz_a_propria_area_nao_e_nome_de_outra():
    """🩸 Arquivo de cliente: saía "PROFESSORES 13,83M² = 2,50 m²"."""
    pares, sem = _pares([_t("PROFESSORES 13,83M²", 10, 10 + 2 * H), _t("A=2,50m²", 10, 10)])
    assert pares == [("PROFESSORES", 13.83, "mesmo")] and sem == [2.5]
    # e o texto com m² que NÃO é etiqueta inteira também não serve de nome
    assert _pares([_t("137 und ou 8,56 m²", 10, 10 + 2 * H), _t("A=2,50m²", 10, 10)]) == ([], [2.5])
    # CONTROLE: medida sem m² no nome continua valendo
    assert _pares([_t("VAGA 2,50x5,00m", 10, 10 + 2 * H), _t("A=12,50m²", 10, 10)])[0] == [
        ("VAGA 2,50x5,00m", 12.5, "acima")]


# ══════════════════════════════════════════════════════════════════════════
#  A sigla de 2 letras
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sigla", ["A.S", "WC", "W.C.", "TI"])
def test_a_sigla_colada_a_etiqueta_e_o_nome(sigla):
    """🩸 Arquivo de cliente: "A.S" (área de serviço) logo acima de 10 etiquetas,
    todas sem nome porque a sigla tem 2 letras."""
    tx = [_t(sigla, 10, 10 + 1.8 * H), _t("A=3,34m²", 10, 10)]
    assert _pares(tx) == ([(sigla, 3.34, "acima")], [])


def test_a_sigla_so_vale_no_mesmo_layer_e_com_a_mesma_letra_da_area():
    area = _t("A=3,34m²", 10, 10)
    assert _pares([_t("WC", 10, 10 + 1.8 * H, layer="OUTRO"), area]) == ([], [3.34])
    assert _pares([_t("WC", 10, 10 + 1.8 * H, h=1.3 * H), area]) == ([], [3.34])
    assert _pares([_t("WC", 10, 10 + 1.8 * H, h=1.08 * H), area]) == ([("WC", 3.34, "acima")], [])


def test_a_sigla_nao_vale_ao_lado_nem_como_primeira_linha():
    assert _pares([_t("WC", 10 + 10 * H, 10 + 1 * H), _t("A=3,34m²", 10, 10)]) == ([], [3.34])
    tx = [_t("WC", 10, 10 + 3.5 * H), _t("MASCULINO", 10, 10 + 2 * H), _t("A=3,34m²", 10, 10)]
    assert _pares(tx) == ([("MASCULINO", 3.34, "acima")], [])


def test_o_nome_inteiro_ganha_da_sigla_mais_longe():
    tx = [_t("COZINHA", 10, 10 + 2 * H), _t("TI", 10, 10 + 4 * H), _t("A=12,00m²", 10, 10)]
    assert _pares(tx) == ([("COZINHA", 12.0, "acima")], [])


@pytest.mark.parametrize("codigo", ["P.A.", "PA", "PD", "P.D."])
def test_codigo_de_atributo_nao_e_sigla_de_comodo(codigo):
    """ "P.A." e "PD" são a linha de código entre o nome e a área (piso acabado,
    pé-direito) — mesmo com a letra da área, nunca são o nome."""
    assert _pares([_t(codigo, 10, 10 + 1.8 * H), _t("A=12,00m²", 10, 10)]) == ([], [12.0])
    tx = [_t("COZINHA", 10, 10 + 4 * H), _t(codigo, 10, 10 + 1.8 * H), _t("A=12,00m²", 10, 10)]
    assert _pares(tx) == ([("COZINHA", 12.0, "acima")], [])


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
    # 📏 acervo (prancha de aprovação): o título da planta com a área do andar saía como cômodo
    ("Planta Baixa - 1º Pavto", True), ("Planta Baixa Tipo 2x", True), ("2º PAVTO", True), ("TIPO (5º e 9º Pavtos)", True),
    ("PLANTÃO MÉDICO", False), ("SALA DE PLANTAS", False),
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
    # a precedência, medida no acervo: o total MEDIDO do layer não é trocado pela etiqueta…
    um = " ".join(l.strip() for l in ls)
    assert ("A área escrita NÃO troca o total de um acabamento MEDIDO por layer" in um
            and "o total medido continua sendo a quantidade do acabamento" in um), (
        "sem isto a soma das etiquetas passa por cima da hachura medida do acabamento")
    # …e contra a REGIÃO do rótulo vale a ESCRITA (a região junta vizinhos ou é um pedaço)
    assert ("com área mais de 10 % diferente da escrita, fique com a ESCRITA e cite a da região na observação"
            in um)
    assert "(mesmo nome, uma vez de cada lado)" in um, "nome repetido não dá pra casar região com etiqueta"
    assert "ÁREAS HACHURADAS POR LAYER, ÁREAS DE CONTORNO FECHADO POR LAYER" in um


def test_a_secao_cita_as_outras_pelo_nome_que_elas_tem_no_prompt():
    """A precedência aponta pra outras seções do prompt: se o cabeçalho delas
    mudar de nome, a frase fica apontando pra lugar nenhum."""
    import inspect
    fonte = inspect.getsource(dx.DXFExtraction.to_structured_prompt)
    for cab in ('"ÁREAS HACHURADAS POR LAYER:"', '"ÁREAS DE CONTORNO FECHADO POR LAYER ',
                '"RÓTULO ↔ ÁREA DA REGIÃO '):
        assert cab in fonte, cab


def test_a_secao_por_desenho_lista_os_grupos():
    ls = dx._linhas_dos_ambientes(dx.ambientes_por_desenho(_tudo(), _mapa()))
    assert "  [PLANTA BAIXA TÉRREO — folha A1 PLANTA]  (planta)" in ls
    assert "    CIRCULAÇÃO = 49.82 m²" in ls and "    SALA DE REUNIÃO = 26.75 m²" in ls
    assert "    CIRCULAÇÃO = 46.60 m²" in ls
    i_fora = next(i for i, l in enumerate(ls) if l.startswith("  [FORA DAS PRANCHAS"))
    assert i_fora > ls.index("  [PLANTA DE LAYOUT TÉRREO — folha A2 LAYOUT]  (planta)")
    assert any("+ 1 etiqueta(s) de área SEM nome por perto: 90.00 m²" in l for l in ls[i_fora:])
    assert ls[-1] == ""


# 🩸 11/10/2026 — a 1ª planilha em produção com a seção: 18 linhas de piso por
# ambiente viraram UMA de 491 m², tirada do "TOTAL = 491,00 m²" que a seção
# listava entre os totais do grupo fora das pranchas.
def test_a_secao_diz_como_usar_uma_linha_por_ambiente():
    um = " ".join(l.strip() for l in dx._linhas_dos_ambientes(dx.ambientes_por_desenho(_tudo(), _mapa())))
    assert "→ COMO USAR, quando houver item de piso, forro ou outro acabamento por área: UMA linha POR AMBIENTE" in um
    assert "tirando os ambientes de UM desenho só (o de planta baixa, quando houver)" in um
    assert "Acabamento sem especificação continua sendo uma linha por ambiente" in um
    assert ("se juntar ambientes numa linha, a quantidade é a SOMA das áreas deles naquele desenho"
            " — NUNCA um total escrito") in um
    # o "como usar" vem ANTES das ressalvas e da lista
    assert um.index("→ COMO USAR") < um.index("⚠ A área escrita NÃO troca") < um.index("[PLANTA BAIXA TÉRREO")


def test_a_secao_sem_desenho_diz_como_usar_sem_falar_de_desenho():
    um = " ".join(l.strip() for l in dx._linhas_dos_ambientes(dx.ambientes_por_desenho(_tudo(), None)))
    assert "→ COMO USAR, quando houver item de piso, forro ou outro acabamento por área: UMA linha POR AMBIENTE" in um
    assert "a quantidade é a SOMA das áreas deles — NUNCA um total escrito" in um
    assert "UM desenho só" not in um and "naquele desenho" not in um


def test_o_total_escrito_fora_das_pranchas_nao_e_posto_na_frente():
    """Com desenho das pranchas na lista, o total do grupo de fora é de cópia de
    trabalho ou de quadro solto: a seção diz que existe, sem o número."""
    ls = dx._linhas_dos_ambientes(dx.ambientes_por_desenho(_tudo(), _mapa()))
    i_fora = next(i for i, l in enumerate(ls) if l.startswith("  [FORA DAS PRANCHAS"))
    assert "    (1 total(is)/resumo(s) escrito(s) aqui fora não listado(s): não são área de piso nem de forro)" \
        in ls[i_fora:]
    assert not any("491" in l for l in ls), "o número do total não aparece em lugar nenhum da seção"
    assert not any("totais/resumos escritos" in l for l in ls)
    assert "    CIRCULAÇÃO = 46.60 m²" in ls[i_fora:], "os ambientes de fora continuam listados"


def test_o_aviso_dos_totais_de_fora_conta_as_etiquetas():
    tx = _tudo() + [_t("ÁREA TOTAL = 491,00m²", 240, 25), _t("ÁREA ÚTIL = 351,00m²", 250, 25)]
    ls = dx._linhas_dos_ambientes(dx.ambientes_por_desenho(tx, _mapa()))
    assert "    (3 total(is)/resumo(s) escrito(s) aqui fora não listado(s): não são área de piso nem de forro)" in ls
    assert not any("491" in l or "351" in l for l in ls)


def test_o_total_de_um_desenho_das_pranchas_e_listado_com_o_aviso():
    tx = _tudo() + [_t("ÁREA ÚTIL = 76,57m²", 30, 25)]            # dentro da 1ª prancha
    ls = dx._linhas_dos_ambientes(dx.ambientes_por_desenho(tx, _mapa()))
    linha = next(l for l in ls if "totais/resumos escritos" in l)
    assert ls.index(linha) < next(i for i, l in enumerate(ls) if l.startswith("  [PLANTA DE LAYOUT"))
    assert "ÁREA ÚTIL = 76.57 m²" in linha
    assert "NÃO são ambiente e NÃO são área de piso nem de forro" in linha
    assert "total costuma ser área construída ou do lote, com parede e área externa" in linha
    assert "servem só pra conferir a soma dos ambientes" in linha


def test_sem_desenho_das_pranchas_o_total_e_listado_com_o_aviso():
    """Lista única (sem janela do papel) ou SÓ o grupo de fora: aí o total é tudo
    o que há — fica listado, com o aviso."""
    unica = dx._linhas_dos_ambientes(dx.ambientes_por_desenho(_tudo(), None))
    linha = next(l for l in unica if "totais/resumos escritos" in l)
    assert "ÁREA TOTAL = 491.00 m²" in linha and "NÃO são área de piso nem de forro" in linha
    assert not any("aqui fora não listado" in l for l in unica)
    so_fora = dx._linhas_dos_ambientes(dx.ambientes_por_desenho(
        _etiquetas(200, "46,60m²", "29,86m²", extra=[_t("ÁREA TOTAL = 491,00m²", 220, 25)]), _mapa()))
    assert any(l.startswith("  [FORA DAS PRANCHAS") for l in so_fora)
    assert any("totais/resumos escritos" in l and "ÁREA TOTAL = 491.00 m²" in l for l in so_fora)


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


def _so_textos(tmp_path, monta):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "ARQ-PAREDE"})
    monta(msp)
    p = str(tmp_path / "textos.dxf")
    doc.saveas(p)
    return p


def test_o_extrator_guarda_a_ancora_do_mtext(tmp_path):
    """A coluna do attachment_point: 1/4/7 = início, 2/5/8 = meio, 3/6/9 = fim.
    O TEXT alinhado fica 0: o `insert` dele já é o início."""
    from ezdxf.enums import TextEntityAlignment

    def monta(msp):
        for i, ap in enumerate((1, 2, 3, 5, 7, 9)):
            msp.add_mtext("NOME %d" % ap, dxfattribs={"char_height": H, "layer": "AMB-NOME", "insert": (i * 5, 5),
                                                      "attachment_point": ap})
        msp.add_text("TEXTO À DIREITA", dxfattribs={"height": H, "layer": "AMB-NOME"}).set_placement(
            (40, 5), align=TextEntityAlignment.RIGHT)
    ex = dx.extract_dxf(_so_textos(tmp_path, monta))
    al = {t.text: t.alinhamento for t in ex.texts}
    assert al == {"NOME 1": 0, "NOME 2": 1, "NOME 3": 2, "NOME 5": 1, "NOME 7": 0, "NOME 9": 2,
                  "TEXTO À DIREITA": 0}
    assert dx.TextAnnotation(layer="X", text="Y").alinhamento == 0
    assert dx._ancora_do_texto(object()) == (0, 0.0, 0.0)


def _ancoras(tmp_path, monta):
    ex = dx.extract_dxf(_so_textos(tmp_path, monta))
    return {t.text: (t.alinhamento, t.ancora_dx, t.largura_da_caixa) for t in ex.texts}


def test_o_paragrafo_do_mtext_diz_onde_o_texto_comeca_dentro_da_caixa(tmp_path):
    """A coluna do attachment_point só prende a CAIXA ao ponto; dentro dela o
    texto se alinha pelo código de parágrafo. (alinhamento, do ponto gravado
    até o ponto de referência, largura da caixa)."""
    def monta(msp):
        def mt(txt, ap, caixa):
            msp.add_mtext(txt, dxfattribs={"char_height": H, "layer": "AMB-NOME", "insert": (5, 5),
                                           "attachment_point": ap, "width": caixa})
        mt("\\pxql;ESQUERDA NO CENTRO", 8, 4.0)
        mt("\\pxqc;CENTRO NA DIREITA", 3, 4.0)
        mt("\\pxqc;CENTRO NA ESQUERDA", 1, 4.0)
        mt("\\pxqr;DIREITA NA ESQUERDA", 7, 4.0)
        mt("\\pxsm0.75,qc;DEPOIS DA VIRGULA", 1, 4.0)        # o `q` vem depois de outros parâmetros
        mt("\\pxqj;JUSTIFICADO", 2, 4.0)                     # justificado e distribuído começam na borda esquerda
        mt("\\pxqd;DISTRIBUIDO", 9, 4.0)
        mt("\\pt53.24,66.55;SO TABULACAO", 2, 4.0)           # código de parágrafo sem alinhamento: vale a coluna
        mt("\\pxql;SEM CAIXA", 2, 0.0)                       # sem caixa não há dentro de quê alinhar
        mt("SEM CODIGO", 3, 4.0)
        mt("\\pxqr;O MESMO DA COLUNA", 3, 4.0)
    assert _ancoras(tmp_path, monta) == {
        "ESQUERDA NO CENTRO": (0, -2.0, 4.0),
        "CENTRO NA DIREITA": (1, -2.0, 4.0),
        "CENTRO NA ESQUERDA": (1, 2.0, 4.0),
        "DIREITA NA ESQUERDA": (2, 4.0, 4.0),
        "DEPOIS DA VIRGULA": (1, 2.0, 4.0),
        "JUSTIFICADO": (0, -2.0, 4.0),
        "DISTRIBUIDO": (0, -4.0, 4.0),
        "SO TABULACAO": (1, 0.0, 4.0),
        "SEM CAIXA": (1, 0.0, 0.0),
        "SEM CODIGO": (2, 0.0, 4.0),
        "O MESMO DA COLUNA": (2, 0.0, 4.0),
    }


def _ambientes_do_arquivo(tmp_path, monta):
    amb = dx.extract_dxf(_so_textos(tmp_path, monta)).metadata["ambientes_area_escrita"]
    return [g["ambientes"] for g in amb["grupos"]], amb["sem_nome"]


def test_do_arquivo_ao_par_com_o_paragrafo_a_esquerda_na_caixa_presa_pelo_centro(tmp_path, monkeypatch):
    """📏 Acervo, com as proporções do arquivo: uma fileira de salas a 16,5
    alturas uma da outra. O nome é MTEXT preso pelo centro embaixo (8) numa caixa
    de 24,4 alturas com o parágrafo à ESQUERDA; a área (letra 0,8) é MTEXT preso
    pela direita (9) e termina 5,6 alturas antes do ponto do nome — os dois
    começam juntos. Pela coluna sozinha o nome ficava 9 alturas à direita e cada
    área ia pro nome da sala vizinha."""
    monkeypatch.delenv("AMBIENTE_AREA_ESCRITA", raising=False)
    salas = [("12", "10,00"), ("13", "11,50"), ("14", "12,25")]

    def monta(msp):
        for i, (n, a) in enumerate(salas):
            x = 20 + i * 16.5 * H
            msp.add_mtext("\\pxql;SALA DE \\PEXAME %s" % n,
                          dxfattribs={"char_height": H, "layer": "AMB-NOME", "attachment_point": 8,
                                      "width": 24.4 * H, "insert": (x, 5)})
            msp.add_mtext("\\pxt7.26216;A= %s m²" % a,
                          dxfattribs={"char_height": 0.8 * H, "layer": "AMB-AREA", "attachment_point": 9,
                                      "width": 99.5 * H, "insert": (x - 5.6 * H, 5 - 1.2 * H)})
    grupos, sem = _ambientes_do_arquivo(tmp_path, monta)
    assert grupos == [[["SALA DE EXAME 12", 10.0, 1], ["SALA DE EXAME 13", 11.5, 1], ["SALA DE EXAME 14", 12.25, 1]]]
    assert sem == 0


def test_do_arquivo_ao_par_com_o_paragrafo_centrado_na_caixa_presa_pela_esquerda(tmp_path, monkeypatch):
    """A forma mais comum no acervo (2.294 MTEXT): caixa presa pela ESQUERDA,
    parágrafo centrado. "COPA" no meio de uma caixa de 30 alturas começa 13,6
    alturas depois do ponto gravado; a área está centrada embaixo dele."""
    monkeypatch.delenv("AMBIENTE_AREA_ESCRITA", raising=False)

    def monta(msp):
        msp.add_mtext("\\pxqc;COPA", dxfattribs={"char_height": H, "layer": "AMB-NOME", "attachment_point": 1,
                                                 "width": 30 * H, "insert": (5, 5)})
        msp.add_text("A=9,50m²", dxfattribs={"height": H, "layer": "AMB-AREA", "insert": (5 + 12 * H, 5 - 2.6 * H)})
    assert _ambientes_do_arquivo(tmp_path, monta) == ([[["COPA", 9.5, 1]]], 0)


def test_do_arquivo_ao_par_com_o_nome_girado_e_o_paragrafo_a_esquerda(tmp_path, monkeypatch):
    """A caixa acompanha o giro do texto: no nome a 90° ela sobe, e a borda
    esquerda dela fica 15 alturas ABAIXO do ponto gravado."""
    monkeypatch.delenv("AMBIENTE_AREA_ESCRITA", raising=False)

    def monta(msp):
        mt = msp.add_mtext("\\pxql;SHAFT TÉCNICO",
                           dxfattribs={"char_height": H, "layer": "AMB-NOME", "attachment_point": 8,
                                       "width": 30 * H, "insert": (20 - 1.6 * H, 5 + 15 * H)})
        mt.dxf.text_direction = (0, 1, 0)
        msp.add_text("A=2,40m²", dxfattribs={"height": H, "layer": "AMB-AREA", "insert": (20, 5), "rotation": 90})
    assert _ambientes_do_arquivo(tmp_path, monta) == ([[["SHAFT TÉCNICO", 2.4, 1]]], 0)


def test_o_texto_mais_largo_que_a_caixa_e_quebrado_e_nao_passa_dela(tmp_path, monkeypatch):
    """O nome comprido numa caixa estreita o CAD quebra em linhas: centrado, ele
    começa no máximo meia CAIXA antes do ponto — não meio texto antes. Sem esse
    teto o nome ficava 10,9 alturas à esquerda, a área preferia o "COPA" ao
    lado (6,7 alturas) e, como o "COPA" já é da área dele, ficava sem nome."""
    monkeypatch.delenv("AMBIENTE_AREA_ESCRITA", raising=False)

    def monta(msp):
        msp.add_mtext("DEPÓSITO DE MATERIAL DE LIMPEZA",
                      dxfattribs={"char_height": H, "layer": "AMB-NOME", "attachment_point": 8,
                                  "width": 8 * H, "insert": (20, 5)})
        msp.add_text("A=9,50m²", dxfattribs={"height": H, "layer": "AMB-AREA", "insert": (20 - 3 * H, 5 - 1.6 * H)})
        msp.add_text("COPA", dxfattribs={"height": H, "layer": "AMB-NOME", "insert": (20 + 3.5 * H, 5)})
        msp.add_text("A=4,20m²", dxfattribs={"height": H, "layer": "AMB-AREA", "insert": (20 + 3.5 * H, 5 - 1.6 * H)})
    assert _ambientes_do_arquivo(tmp_path, monta) == (
        [[["COPA", 4.2, 1], ["DEPÓSITO DE MATERIAL DE LIMPEZA", 9.5, 1]]], 0)


def test_CONTROLE_sem_caixa_o_paragrafo_nao_move_o_texto(tmp_path, monkeypatch):
    """Sem caixa (largura 0) o texto fica preso ao ponto pela coluna: o nome
    centrado no ponto continua centrado, com ou sem "\\pxql;" — e casa com a
    área centrada embaixo dele. (Quem reprova o contrário é o teste da âncora:
    "SEM CAIXA" = (1, 0, 0).)"""
    monkeypatch.delenv("AMBIENTE_AREA_ESCRITA", raising=False)

    def monta(msp):
        msp.add_mtext("\\pxql;ALMOXARIFADO DE MATERIAIS", dxfattribs={
            "char_height": H, "layer": "AMB-NOME", "attachment_point": 8, "width": 0.0, "insert": (20, 5)})
        msp.add_text("A=9,50m²", dxfattribs={"height": H, "layer": "AMB-AREA",
                                             "insert": (20 - 4 * LARG * H, 5 - 1.6 * H)})
    assert _ambientes_do_arquivo(tmp_path, monta) == ([[["ALMOXARIFADO DE MATERIAIS", 9.5, 1]]], 0)


def test_do_arquivo_ao_par_com_o_nome_ancorado_a_direita(tmp_path, monkeypatch):
    """O caso do arquivo de cliente, do DXF até o registro: três cômodos lado a
    lado, o nome em MTEXT ancorado no topo-direita."""
    monkeypatch.delenv("AMBIENTE_AREA_ESCRITA", raising=False)
    comodos = [("DEFENSOR 01", "8,37"), ("DEFENSOR 02", "8,40"), ("DEFENSOR 03", "8,73")]

    def monta(msp):
        for i, (n, a) in enumerate(comodos):
            x = 2 + i * 8 * H
            msp.add_mtext(n, dxfattribs={"char_height": H, "layer": "AMB-NOME", "attachment_point": 3,
                                         "insert": (x + len(n) * H * LARG, 5 + 2 * H)})
            msp.add_text("A=%sm²" % a, dxfattribs={"height": H, "layer": "AMB-AREA", "insert": (x, 5)})
    amb = dx.extract_dxf(_so_textos(tmp_path, monta)).metadata["ambientes_area_escrita"]
    assert [g["ambientes"] for g in amb["grupos"]] == [
        [["DEFENSOR 01", 8.37, 1], ["DEFENSOR 02", 8.4, 1], ["DEFENSOR 03", 8.73, 1]]]


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
