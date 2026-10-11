# -*- coding: utf-8 -*-
"""No export do Revit a VISTA vem escrita no nome do bloco — e a peça do corte
ficava na contagem junto com a da planta.

🩸 11/10/2026 — caso de uma residência exportada do Revit (planta, layout e 5
cortes no mesmo arquivo). A regra de sempre: "o bloco da vista sai se o MESMO
bloco é contado fora dela". No Revit cada vista ganha os seus blocos,
"<família - tipo>-<id>-<vista>": a geladeira da planta e a do corte têm nomes
diferentes, nunca eram "o mesmo bloco", e as 20 geladeiras da planilha eram as
da planta somadas às dos cortes.

📏 Medido no arquivo: 533 inserções, 239 com "Corte N" no nome; 0 saíam; 91
dessas 239 estavam em região que a leitura por folha não deu como vista (corte
sem título lido como planta, ou fora de todo desenho). O id não é um por peça
(o mesmo id vem 6× no layout), a variante V<n> não se repete entre planta e
corte; o que é igual dos dois lados é a FAMÍLIA - TIPO. Quem só existe no corte
(as terças do telhado, 118 inserções) fica: é o único registro.

🩸 A 1ª versão caiu no A/B do acervo (28 arquivos de 18 jobs), e cada motivo é
um teste aqui: uma contagem SUBIA (ela desligava a regra antiga no bloco de
corte); numa prancha a elevação mostra 123 vagas e a planta delas está em OUTRO
arquivo (aqui só há 4); as fachadas e os cortes de um prédio mostram todos os
andares (193 pilares) contra a planta-tipo desenhada uma vez. A quarta trava é de
princípio: a quantidade pode caber e ser OUTRO trecho, então o vão das peças
no corte tem de caber no alcance delas na planta (no caso conferido fecha: 133
pisos táteis numa faixa de 37,93 na elevação, 149 numa caixa de diagonal 37,92
na planta — a mesma calçada, e sai).

🪤 Nomes de família e de vista FICTÍCIOS (repositório público, regra nº6).
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from dwg_extractor import BlockCount, _peca_do_revit  # noqa: E402


# ── o nome ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("nome, peca, vista, de_corte", [
    ("GELADEIRA - 398-3878392-Corte 3", "GELADEIRA - 398", "corte 3", True),
    ("GELADEIRA - 398-3878392-LAYOUT PAV_ TERREO", "GELADEIRA - 398", "layout pav_ terreo", False),
    ("JANELA BASCULANTE - 150-V3-Corte 4", "JANELA BASCULANTE - 150", "corte 4", True),
    # id + variante: a vista é a mesma "elevacao norte" da forma só com id
    ("PORTA - 70x210-5493970-V2-Elevação Norte", "PORTA - 70x210", "elevacao norte", True),
    ("PORTA - 70x210-5493970-Elevação Norte", "PORTA - 70x210", "elevacao norte", True),
    ("PORTA - 70x210-5493970-ELEV 3", "PORTA - 70x210", "elev 3", True),
    ("COBOGO - 20-123456-Fachada Sul", "COBOGO - 20", "fachada sul", True),
    ("VIGA - 15x40-123456-Seção 1", "VIGA - 15x40", "secao 1", True),
    ("VIGA - 15x40-123456-Section 2", "VIGA - 15x40", "section 2", True),
    # o plural, medido no acervo ("CORTES B_ C_", "Elevações")
    ("VIGA - 15x40-123456-CORTES B_ C_", "VIGA - 15x40", "cortes b_ c_", True),
    ("VIGA - 15x40-123456-Elevações", "VIGA - 15x40", "elevacoes", True),
    ("VIGA - 15x40-123456-Fachadas", "VIGA - 15x40", "fachadas", True),
    ("VIGA - 15x40-123456-Seções", "VIGA - 15x40", "secoes", True),
    ("VIGA - 15x40-123456-Sections", "VIGA - 15x40", "sections", True),
    # a palavra inteira: "elevador" não é elevação, "recorte" não é corte
    ("BOTOEIRA - 1-123456-CASA DE MAQUINAS DO ELEVADOR", "BOTOEIRA - 1", "casa de maquinas do elevador", False),
    ("RODAPE - 7-123456-RECORTE DO PISO", "RODAPE - 7", "recorte do piso", False),
    ("LUMINARIA - A-123456-PAV_ INFERIOR - PLATAFORMA", "LUMINARIA - A", "pav_ inferior - plataforma", False),
    ("TELHA - 1-123456-PLANTA DE COBERTURA", "TELHA - 1", "planta de cobertura", False),
    # "vista" e "perspectiva" no nome não dizem corte: no Revit toda prancha é uma "vista"
    ("SOFA - 3L-123456-Vista 1", "SOFA - 3L", "vista 1", False),
    ("SOFA - 3L-123456-Perspectiva", "SOFA - 3L", "perspectiva", False),
    # o primeiro "-<id>-" é o do Revit; o que vem depois é a vista inteira
    ("CUBA - 1-123456-BLOCO B-654321-Corte 1", "CUBA - 1", "bloco b-654321-corte 1", True),
])
def test_o_nome_do_bloco_do_revit(nome, peca, vista, de_corte):
    assert _peca_do_revit(nome) == (peca, vista, de_corte)


@pytest.mark.parametrize("nome", [
    "PIA", "PORTA-80-CORTE", "TOMADA-1234-Corte 2", "-123456-Corte 1", "P-V1234-Corte 1",
    "CORTE AA", "JANELA 120x100", "", None, "BLOCO-123456", "BLOCO-V3",
])
def test_CONTROLE_nome_que_nao_e_do_revit_nao_tem_peca(nome):
    """Sem "-<id de 5+ dígitos>-" nem "-V<n>-" seguido da vista, o nome é um nome qualquer."""
    assert _peca_do_revit(nome) == ("", "", False)


# ── a régua, na leitura por folha ────────────────────────────────────────────
def _mapa():
    return {"folhas": [
        {"tipo": "vista", "titulo": "CORTE A-A", "caixa": (0, 0, 10, 10)},
        {"tipo": "planta", "titulo": "LAYOUT TERREO", "caixa": (40, 0, 50, 10), "andares": 1},
        # o corte SEM título, que a leitura por folha deu como planta
        {"tipo": "planta", "titulo": "PLANTA", "caixa": (60, 0, 70, 10), "andares": 1},
        {"tipo": "fora", "titulo": "DETALHE", "caixa": (80, 0, 90, 10)},
        {"tipo": "planta", "titulo": "PAVIMENTO TIPO (3X)", "caixa": (100, 0, 110, 10), "andares": 3},
    ]}


VISTA, PLANTA, CORTE_LIDO_COMO_PLANTA, FORA, TIPO_3X, NENHUM = (5, 5), (45, 5), (65, 5), (85, 5), (105, 5), (200, 5)


def _bl(nome, *pos):
    return BlockCount(name=nome, count=len(pos), positions=list(pos))


def _caso():
    return [
        _bl("GELADEIRA - 398-3878392-LAYOUT TERREO", *[PLANTA] * 6),
        _bl("GELADEIRA - 398-3878392-Corte 3", VISTA, VISTA),
        _bl("GELADEIRA - 398-3878392-Corte 4", CORTE_LIDO_COMO_PLANTA, CORTE_LIDO_COMO_PLANTA),
        _bl("GELADEIRA - 398-4073647-Corte 5", NENHUM),            # outro id, fora de todo desenho
        _bl("TERCA - 6x12-111111-Corte 3", *[VISTA] * 5),          # só existe em corte
        _bl("TERCA - 6x12-111111-Corte 4", *[CORTE_LIDO_COMO_PLANTA] * 3),
        _bl("JANELA BASCULANTE - 150-V1-LAYOUT TERREO", PLANTA, PLANTA),
        _bl("JANELA BASCULANTE - 150-V3-Corte 3", VISTA),          # a variante muda de vista pra vista
        _bl("PIA", VISTA, PLANTA),
        _bl("PAPELEIRA", VISTA),
    ]


def _aplica(blocks, mapa=None):
    res = dx.aplicar_leitura_por_folha([], [], [], blocks, _mapa() if mapa is None else mapa)
    return res, {b.name: b.count for b in blocks}


def _base(blocks, mapa=None):
    """A regra de ANTES no mesmo caso: os mesmos blocos com o nome sem a forma do Revit
    (o "-" vira "_"), pra régua nova não ter o que ler. Devolve as contagens, na ordem."""
    copia = [BlockCount(name=b.name.replace("-", "_"), count=b.count, positions=list(b.positions)) for b in blocks]
    dx.aplicar_leitura_por_folha([], [], [], copia, _mapa() if mapa is None else mapa)
    vivos = {b.name: b.count for b in copia}
    return [vivos.get(b.name.replace("-", "_"), 0) for b in blocks]


def test_a_peca_do_corte_sai_quando_a_familia_esta_na_planta():
    res, b = _aplica(_caso())
    assert b["GELADEIRA - 398-3878392-LAYOUT TERREO"] == 6
    assert "GELADEIRA - 398-3878392-Corte 3" not in b, "região de vista: a família é a da planta"
    assert "GELADEIRA - 398-3878392-Corte 4" not in b, "o nome diz corte, mesmo na região lida como planta"
    assert "GELADEIRA - 398-4073647-Corte 5" not in b, "outro id e fora de todo desenho: a família é a mesma"
    assert "JANELA BASCULANTE - 150-V3-Corte 3" not in b, "só variante, sem id: a família é a mesma"
    assert b["JANELA BASCULANTE - 150-V1-LAYOUT TERREO"] == 2
    assert res["vista"]["blocos"] == 2 + 2 + 1 + 1 + 1          # … e a pia (a regra de antes)


def test_o_que_so_o_corte_mostra_e_o_unico_registro():
    _, b = _aplica(_caso())
    assert b["TERCA - 6x12-111111-Corte 3"] == 5 and b["TERCA - 6x12-111111-Corte 4"] == 3


def test_CONTROLE_o_bloco_comum_segue_a_regra_de_antes():
    _, b = _aplica(_caso())
    assert b["PIA"] == 1 and b["PAPELEIRA"] == 1


def test_CONTROLE_sem_a_familia_na_planta_nada_do_corte_sai():
    """Tirando as plantas do caso, TODO bloco de corte é o único registro."""
    so_cortes = [x for x in _caso() if "LAYOUT" not in x.name and x.name != "PIA"]
    antes = {x.name: x.count for x in so_cortes}
    _, b = _aplica(so_cortes)
    assert b == antes


# ── as três travas que o A/B do acervo pediu ─────────────────────────────────
def test_NENHUMA_contagem_sobe_o_corte_que_a_regra_antiga_ja_limpava():
    """🩸 O bloco de corte com 3 inserções fora de região de vista e 14 dentro, família só
    em corte: a regra antiga tirava as 14 (o MESMO nome é contado fora da vista). A 1ª
    versão desta régua desligava isso e a contagem ia de 3 pra 17."""
    blocos = [_bl("TAG DE REVESTIMENTO - A-1736611-CORTE EE", *([NENHUM] * 3 + [VISTA] * 14))]
    assert _base(blocos) == [3]
    _, b = _aplica(blocos)
    assert b == {"TAG DE REVESTIMENTO - A-1736611-CORTE EE": 3}


@pytest.mark.parametrize("no_corte, sai", [(1, True), (2, True), (3, False), (61, False)])
def test_a_vista_que_mostra_MAIS_do_que_ha_fora_nao_e_a_mesma_peca(no_corte, sai):
    """🩸 A elevação mostra 123 vagas de perfil e a planta delas está em OUTRO arquivo do job
    (neste só há 4): ela é o único registro das outras. O corte só repete a planta se mostra
    no máximo o que é contado fora de corte."""
    blocos = [_bl("VAGA - 5x2,5-222222-IMPLANTACAO", PLANTA, PLANTA),
              _bl("VAGA - 5x2,5-222222-FACHADA FRONTAL", *[NENHUM] * no_corte)]
    _, b = _aplica(blocos)
    assert b["VAGA - 5x2,5-222222-IMPLANTACAO"] == 2
    assert b.get("VAGA - 5x2,5-222222-FACHADA FRONTAL", 0) == (0 if sai else no_corte)


def test_a_conta_e_por_VISTA_e_nao_pela_soma_dos_cortes():
    """Cinco cortes mostrando 2 das 6 geladeiras: 10 no total, mas nenhum corte mostra mais
    que a planta — saem os cinco."""
    blocos = [_bl("GELADEIRA - 398-3878392-LAYOUT TERREO", *[PLANTA] * 6)]
    blocos += [_bl("GELADEIRA - 398-3878392-Corte %d" % i, NENHUM, NENHUM) for i in range(1, 6)]
    _, b = _aplica(blocos)
    assert b == {"GELADEIRA - 398-3878392-LAYOUT TERREO": 6}


def test_dois_ids_na_MESMA_vista_somam_antes_de_comparar():
    blocos = [_bl("GELADEIRA - 398-3878392-LAYOUT TERREO", PLANTA, PLANTA, PLANTA),
              _bl("GELADEIRA - 398-3878392-Corte 3", NENHUM, NENHUM),
              _bl("GELADEIRA - 398-4073647-V2-Corte 3", NENHUM, NENHUM)]         # 4 no Corte 3 × 3 fora
    _, b = _aplica(blocos)
    assert b == {"GELADEIRA - 398-3878392-LAYOUT TERREO": 3, "GELADEIRA - 398-3878392-Corte 3": 2,
                 "GELADEIRA - 398-4073647-V2-Corte 3": 2}


def _planta_25x8():
    """4 peças numa caixa de 2,5 × 8 dentro da planta: alcance (diagonal) = 8,38."""
    return _bl("PISO TATIL - 25x25-999999-CALCADA", (41, 1), (43.5, 1), (41, 9), (43.5, 9))


@pytest.mark.parametrize("vao, sai", [(0.0, True), (8.0, True), (8.7, True), (9.0, False), (20.7, False)])
def test_o_vao_do_corte_cabe_no_alcance_da_planta(vao, sai):
    """A quantidade cabe (3 ≤ 4) e pode ser OUTRO trecho. O corte é a planta vista de lado: o
    vão das peças nele não passa da diagonal da caixa delas na planta (com 5 % de folga)."""
    corte = _bl("PISO TATIL - 25x25-999999-FACHADA FRONTAL", (200, 5), (200 + vao / 2, 5), (200 + vao, 5))
    # outra família, com alcance de 100: o alcance que vale é o da PRÓPRIA família
    muro = _bl("MURO - 1-121212-IMPLANTACAO", (300, 0), (400, 0))
    _, b = _aplica([_planta_25x8(), corte, muro])
    assert b["PISO TATIL - 25x25-999999-CALCADA"] == 4
    assert b.get("PISO TATIL - 25x25-999999-FACHADA FRONTAL", 0) == (0 if sai else 3)


def test_o_vao_do_corte_vale_tambem_na_vertical():
    """O corte pode estar desenhado em pé: vale o maior lado da caixa das inserções dele."""
    corte = _bl("PISO TATIL - 25x25-999999-Corte 1", (200, 5), (200, 25))
    _, b = _aplica([_planta_25x8(), corte])
    assert b["PISO TATIL - 25x25-999999-Corte 1"] == 2


def test_o_alcance_e_o_de_UMA_vista_de_fora_e_nao_a_distancia_entre_duas():
    """A peça em duas plantas a 20 de distância uma da outra não tem "alcance" de 20: cada
    planta alcança 2. O corte de vão 10 é outro trecho."""
    blocos = [_bl("PISO TATIL - 25x25-999999-LAYOUT TERREO", (41, 1), (43, 1)),
              _bl("PISO TATIL - 25x25-999999-TERREO", (61, 1), (63, 1)),
              _bl("PISO TATIL - 25x25-999999-Corte 1", (200, 5), (210, 5))]
    _, b = _aplica(blocos)
    assert b["PISO TATIL - 25x25-999999-Corte 1"] == 2
    blocos[2] = _bl("PISO TATIL - 25x25-999999-Corte 1", (200, 5), (202, 5))
    _, b = _aplica(blocos)
    assert "PISO TATIL - 25x25-999999-Corte 1" not in b


def test_CONTROLE_sem_posicao_na_planta_so_o_corte_de_um_ponto_sai():
    """A planta sem todas as posições não tem caixa: não dá pra saber o alcance, e o corte
    com vão fica."""
    planta = BlockCount(name="CUBA - 1-777777-LAYOUT TERREO", count=4, positions=[PLANTA])
    _, b = _aplica([planta, _bl("CUBA - 1-777777-Corte 3", (200, 5), (203, 5))])
    assert b == {"CUBA - 1-777777-LAYOUT TERREO": 4, "CUBA - 1-777777-Corte 3": 2}


@pytest.mark.parametrize("na_fachada, sai", [(6, True), (7, False), (125, False)])
def test_a_planta_tipo_vale_pelos_andares_dela(na_fachada, sai):
    """🩸 Prédio: as fachadas e os cortes mostram todos os andares (193 pilares), a planta-tipo
    é desenhada uma vez. O "contado fora" é o que a planta VALE: 2 pilares × 3 andares = 6."""
    blocos = [_bl("PILAR - 25x25-333333-PAV TIPO", TIPO_3X, TIPO_3X),
              _bl("PILAR - 25x25-333333-Fachada Sul", *[VISTA] * na_fachada)]
    _, b = _aplica(blocos)
    assert b["PILAR - 25x25-333333-PAV TIPO"] == 6
    assert b.get("PILAR - 25x25-333333-Fachada Sul", 0) == (0 if sai else na_fachada)


def test_CONTROLE_quem_a_regua_nova_nao_tira_fica_IGUAL_a_antes():
    """Família só em corte, e corte que mostra mais que a planta: o resultado é o da regra antiga,
    posição por posição (inclusive o peso do andar de quem caiu numa planta-tipo)."""
    blocos = [_bl("PERFIL - U-666666-Corte 2", TIPO_3X, VISTA),
              _bl("CALHA - 1-888888-Corte 3", NENHUM, VISTA, VISTA, FORA),
              _bl("VAGA - 5x2,5-222222-IMPLANTACAO", PLANTA),
              _bl("VAGA - 5x2,5-222222-FACHADA FRONTAL", NENHUM, NENHUM, VISTA, CORTE_LIDO_COMO_PLANTA)]
    antes = _base(blocos)
    _, b = _aplica(blocos)
    assert [b.get(x.name, 0) for x in blocos] == antes == [3, 1, 1, 3]


# ── o que não muda ───────────────────────────────────────────────────────────
def test_CONTROLE_vista_no_nome_nao_e_corte():
    """ "-Vista 1": pode ser vista de planta. Fica com o peso da região (3 andares)."""
    _, b = _aplica([_bl("SOFA - 3L-555555-Vista 1", TIPO_3X), _bl("SOFA - 3L-555555-LAYOUT TERREO", PLANTA)])
    assert b["SOFA - 3L-555555-Vista 1"] == 3 and b["SOFA - 3L-555555-LAYOUT TERREO"] == 1


def test_CONTROLE_o_que_ja_saia_pelo_detalhe_continua_saindo_e_nao_entra_na_conta():
    """As 3 inserções do corte que estão num DETALHE já saíam: não contam como "o que o corte
    mostra" — sobram 2, que cabem nas 2 da planta."""
    blocos = [_bl("RALO - 10-444444-LAYOUT TERREO", (45, 5), (46, 5)),
              _bl("RALO - 10-444444-Corte 9", FORA, FORA, FORA, (5, 5), (5.5, 5))]
    res, b = _aplica(blocos)
    assert b == {"RALO - 10-444444-LAYOUT TERREO": 2}
    assert res["vista"]["blocos"] == 2, "as 3 do detalhe não são da regra da vista"


def test_CONTROLE_bloco_de_planta_na_regiao_de_vista_nao_usa_a_familia():
    """A comparação pela família é só pro bloco que o NOME diz ser de corte. O de nome de
    planta que caiu numa região de vista segue a regra de antes (o nome inteiro)."""
    _, b = _aplica([_bl("MESA - 1-222222-TERREO", VISTA), _bl("MESA - 1-222222-LAYOUT TERREO", PLANTA)])
    assert b == {"MESA - 1-222222-TERREO": 1, "MESA - 1-222222-LAYOUT TERREO": 1}


def test_CONTROLE_o_bloco_de_planta_na_regiao_de_vista_nao_conta_como_fora_de_corte():
    """O "contado fora de corte" é o que FICOU contado: a mesa de nome de planta dentro de uma
    região de vista não prova que a família existe em planta."""
    _, b = _aplica([_bl("MESA - 1-222222-TERREO", VISTA), _bl("MESA - 1-222222-Corte 1", NENHUM)])
    assert b == {"MESA - 1-222222-TERREO": 1, "MESA - 1-222222-Corte 1": 1}


def test_CONTROLE_corte_com_posicao_incompleta_nao_prova_a_familia():
    """O bloco de corte sem todas as posições conta como está, mas a família dele continua
    existindo SÓ em corte: o outro corte não sai por causa dele."""
    torto = BlockCount(name="CALHA - 1-888888-Corte 3", count=3, positions=[VISTA])
    _, b = _aplica([torto, _bl("CALHA - 1-888888-Corte 4", VISTA, VISTA)])
    assert b == {"CALHA - 1-888888-Corte 3": 3, "CALHA - 1-888888-Corte 4": 2}


def test_posicao_incompleta_na_planta_ainda_prova_a_familia():
    """O bloco da planta sem todas as posições conta como está — e vale pelas 4 que diz ter."""
    planta = BlockCount(name="CUBA - 1-777777-LAYOUT TERREO", count=4, positions=[PLANTA])
    _, b = _aplica([planta, _bl("CUBA - 1-777777-Corte 3", *[VISTA] * 4),
                    _bl("CUBA - 1-777777-Corte 4", *[VISTA] * 5)])
    assert b == {"CUBA - 1-777777-LAYOUT TERREO": 4, "CUBA - 1-777777-Corte 4": 5}


# ── o arquivo que só tem plantas de um andar (o corte não virou região) ──────
_SO_PLANTA = {"folhas": [{"tipo": "planta", "titulo": "LAYOUT TERREO", "caixa": (40, 0, 50, 10), "andares": 1}]}


def test_sem_regiao_de_vista_o_nome_ainda_vale():
    res, b = _aplica([_bl("GELADEIRA - 398-3878392-LAYOUT TERREO", PLANTA, PLANTA, PLANTA),
                      _bl("GELADEIRA - 398-3878392-Corte 3", NENHUM, NENHUM)], mapa=_SO_PLANTA)
    assert b == {"GELADEIRA - 398-3878392-LAYOUT TERREO": 3}
    assert res["aplicada"] is True and res["vista"]["blocos"] == 2
    assert res["antes"]["blocos"] == 5 and res["depois"]["blocos"] == 3


def test_CONTROLE_sem_regiao_de_vista_e_sem_nada_a_tirar_o_relato_e_o_de_antes():
    """Havia bloco de corte no nome, nenhum saiu: "nada muda", como sempre foi."""
    res, b = _aplica([_bl("GELADEIRA - 398-3878392-LAYOUT TERREO", PLANTA),
                      _bl("TERCA - 6x12-111111-Corte 3", NENHUM, NENHUM)], mapa=_SO_PLANTA)
    assert b == {"GELADEIRA - 398-3878392-LAYOUT TERREO": 1, "TERCA - 6x12-111111-Corte 3": 2}
    assert res["aplicada"] is False and "nada muda" in res["motivo"] and "vista" not in res


def test_CONTROLE_sem_desenho_nenhum_nada_muda():
    """Limite anotado: sem NENHUM desenho com título a leitura por folha não roda."""
    res, b = _aplica([_bl("GELADEIRA - 398-3878392-LAYOUT TERREO", PLANTA),
                      _bl("GELADEIRA - 398-3878392-Corte 3", NENHUM)], mapa={"folhas": []})
    assert b == {"GELADEIRA - 398-3878392-LAYOUT TERREO": 1, "GELADEIRA - 398-3878392-Corte 3": 1}
    assert res["aplicada"] is False
