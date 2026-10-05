# -*- coding: utf-8 -*-
"""As travas por layer marcado acham o layer pelo NOME INTEIRO (as irmãs do E12).

🩸 04/10/2026 — revisão do E12, medido no acervo: as travas que rebaixam a
linha ✓ de um layer marcado — tubo/eletroduto em face dupla (H34/H75),
contorno de peça (H76), moldura ou limite (H79), rolete/travessa de esteira
(H88), parede grossa pelas faces (E12) e grade de tabela (E14) — achavam o layer só pelo leitor de
layers da observação, que corta o nome com espaço, acento, ponto, '$' ou que
começa com '-' ("BORDAS ESPESSAS" vira "BORDAS") e não vê a observação sem a
palavra "layer". Eram 53 layers do H79 em 15 jobs. Agora todas passam pela
mesma porta (`engine_rules._marcado_na_linha`): o leitor OU o nome inteiro com
borda (`_rotulo_citado`, a régua da chave do selo), e a unidade pelas duas
tabelas ("metros", "m linear"). Só rebaixa.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import engine_rules as er  # noqa: E402

# (nome, a trava, a marca que ela escreve, rebaixa m²?)
IRMAS = [
    ("H34/H75 face dupla", er.selo_apos_tubo_em_face_dupla, er.MARCA_TUBO_FACE_DUPLA, True),
    ("H76 contorno de peça", er.selo_apos_contorno_de_peca, er.MARCA_CONTORNO_DE_PECA, True),
    ("H79 moldura ou limite", er.selo_apos_moldura_ou_limite, er.MARCA_MOLDURA_OU_LIMITE, True),
    ("H88 travessa de esteira", er.selo_apos_travessa_de_esteira, er.MARCA_TRAVESSA_DE_ESTEIRA, True),
    ("E12 parede espessa", er.selo_apos_parede_espessa, er.MARCA_PAREDE_ESPESSA, False),
    ("E14 grade de tabela", er.selo_apos_grade_de_tabela, er.MARCA_GRADE_DE_TABELA, False),
]
_IDS = [i[0] for i in IRMAS]

#: nomes medidos no acervo que o leitor da observação corta ou não vê
NOMES_CORTADOS = ["BORDAS ESPESSAS", "Margem Externa", "Condulete com Rosca BSP",
                  "0000-EL-00-XYZW$0$ELE-___-DET-TAB-___-2", "ARQ-DIVISÓRIA", "- ARQ - ALVENARIA",
                  "FOLHA PADRÃO", "1_PLANTA BAIXA_1_ARQ-ALV.Soco de Alvenaria", "-DET-07"]


def _roda(trava, obs, unit, marcado):
    from main import _layers_da_obs
    return trava("confirmado", obs, unit, _layers_da_obs(obs), {marcado.strip().upper()})


@pytest.mark.parametrize("nome,trava,marca,_m2", IRMAS, ids=_IDS)
@pytest.mark.parametrize("layer", NOMES_CORTADOS)
def test_o_nome_que_o_leitor_corta_cai(nome, trava, marca, _m2, layer):
    from main import _layers_da_obs
    obs = "Fonte: comprimento do layer '%s' = 100,00 m." % layer
    assert [x.upper() for x in _layers_da_obs(obs)] != [layer.upper()], "o caso precisa ser um nome cortado"
    conf, o, reb = _roda(trava, obs, "ml", layer)
    assert reb and conf == "estimado" and marca in o, (nome, layer)


@pytest.mark.parametrize("nome,trava,marca,_m2", IRMAS, ids=_IDS)
def test_a_observacao_sem_a_palavra_layer_cai(nome, trava, marca, _m2):
    conf, _o, reb = _roda(trava, "Fonte: comprimento total do A-WALL-LIMITE = 347,90 m.", "m", "A-WALL-LIMITE")
    assert reb and conf == "estimado", nome


@pytest.mark.parametrize("nome,trava,marca,_m2", IRMAS, ids=_IDS)
@pytest.mark.parametrize("unit", ["metro", "metros", "mts", "m linear", "M", "ML", "m.l.",
                                  "m.l", "mt", "metro linear", "m lin", "m lin.", "lm"])
def test_toda_unidade_de_comprimento_cai(nome, trava, marca, _m2, unit):
    conf, _o, reb = _roda(trava, "Fonte: layer 'REDE' = 120,00 m.", unit, "REDE")
    assert reb and conf == "estimado", (nome, unit)


# ── o que FICA ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("nome,trava,marca,_m2", IRMAS, ids=_IDS)
@pytest.mark.parametrize("marcado,obs", [
    ("BORDAS ESPESSAS", "Fonte: comprimento do layer 'BORDAS' = 300,00 m."),          # outro layer, sem marca
    ("ARQ_PAREDE EQUIPAMENTOS", "Fonte: comprimento do layer 'ARQ_PAREDE' = 300,00 m."),
    ("A-WALL", "Fonte: comprimento do layer 'A-WALL-PATT' = 63,23 m."),               # a borda do nome
    ("REDE", "Fonte: comprimento do layer 'REDE-AGUA' = 63,23 m."),
])
def test_CONTROLE_outro_layer_sem_marca_fica(nome, trava, marca, _m2, marcado, obs):
    conf, _o, reb = _roda(trava, obs, "ml", marcado)
    assert not reb and conf == "confirmado", (nome, marcado, obs)


@pytest.mark.parametrize("nome,trava,marca,_m2", IRMAS, ids=_IDS)
@pytest.mark.parametrize("marcado,obs", [
    # 🩸 medido em linhas ✓ reais: o "FOLHA" marcado (H79) casava "conforme folha ELE-000"
    ("FOLHA", "Fonte: comprimento total do layer 'ELE-T-APARENTE' = 26,68 m. Bitola conforme folha ELE-000."),
    ("Alvenaria", "Fonte: layer 'PINTURA-EXT' = 120,00 m; paredes de alvenaria rebocadas."),
    ("Margem Externa", "Fonte: layer 'MURO' = 40 m, na margem externa do lote."),
])
def test_CONTROLE_nome_que_e_palavra_solta_no_texto_fica(nome, trava, marca, _m2, marcado, obs):
    conf, _o, reb = _roda(trava, obs, "ml", marcado)
    assert not reb and conf == "confirmado", (nome, marcado)


@pytest.mark.parametrize("nome,trava,marca,_m2", IRMAS, ids=_IDS)
@pytest.mark.parametrize("marcado,obs", [
    ("FOLHA", "Fonte: comprimento do layer 'FOLHA' = 120,00 m."),
    ("ALVENARIA", "Fonte: comprimento do layer 'alvenária' = 120,00 m."),       # caixa e acento
    ("Alvenaria", "Fonte: comprimento de 'ALVENARIA' = 120,00 m."),            # entre aspas
])
def test_o_nome_que_e_palavra_citado_como_layer_cai(nome, trava, marca, _m2, marcado, obs):
    conf, _o, reb = _roda(trava, obs, "ml", marcado)
    assert reb and conf == "estimado", (nome, marcado)


@pytest.mark.parametrize("nome,trava,marca,_m2", IRMAS, ids=_IDS)
@pytest.mark.parametrize("unit", ["un", "kg", "m³", "vb"])
def test_CONTROLE_outra_grandeza_fica(nome, trava, marca, _m2, unit):
    conf, _o, reb = _roda(trava, "Fonte: layer 'REDE' = 12.", unit, "REDE")
    assert not reb and conf == "confirmado", (nome, unit)


@pytest.mark.parametrize("nome,trava,marca,m2", IRMAS, ids=_IDS)
@pytest.mark.parametrize("unit", ["m²", "m2", "m2.", "m^2"])
def test_a_area_fica_como_era_em_cada_trava(nome, trava, marca, m2, unit):
    """As irmãs antigas rebaixavam m² (a tabela da chave tinha m²); o E12 não
    (a hachura da parede não conta face). Isso não muda."""
    conf, _o, reb = _roda(trava, "Fonte: layer 'REDE' = 120,00 m².", unit, "REDE")
    assert reb is m2, (nome, unit)


@pytest.mark.parametrize("nome,trava,marca,_m2", IRMAS, ids=_IDS)
def test_CONTROLE_linha_estimada_ou_sem_marca_segue(nome, trava, marca, _m2):
    assert trava("estimado", "layer 'REDE'", "ml", ["REDE"], {"REDE"}) == ("estimado", "layer 'REDE'", False)
    assert trava("confirmado", "layer 'REDE'", "ml", ["REDE"], set()) == ("confirmado", "layer 'REDE'", False)


# ── o helper ───────────────────────────────────────────────────────────────────
def test_o_leitor_vence_e_o_nome_mais_longo_vem_antes():
    assert er.layer_marcado_citado("layer 'A-WALL'", ["A-WALL"], {"A-WALL"}) == "A-WALL"
    # "ARQ_PAREDE" e "ARQ_PAREDE EQUIPAMENTOS" marcados: a obs cita o longo → acha o longo
    assert er.layer_marcado_citado("layer 'ARQ_PAREDE EQUIPAMENTOS' = 3 m", [],
                                   {"ARQ_PAREDE", "ARQ_PAREDE EQUIPAMENTOS"}) == "ARQ_PAREDE EQUIPAMENTOS"
    assert er.layer_marcado_citado("layer 'OUTRO' = 3 m", ["OUTRO"], {"REDE"}) == ""
    assert er.layer_marcado_citado("qualquer", [], set()) == ""


def test_nome_curto_demais_nao_casa_por_texto():
    """A régua da chave não aceita rótulo de menos de 3 letras ("0", "p1") — o
    layer sem nome tem trava própria."""
    assert er.layer_marcado_citado("Fonte: layer 0 = 12 m", [], {"0"}) == ""


# ── no laço de produção (H79, o furo maior) ────────────────────────────────────
def test_o_laco_de_producao_rebaixa_a_moldura_com_espaco_no_nome():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Rede de hidrantes",
            "unit": "ml", "quantity": 812.4, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'BORDAS ESPESSAS' = 812,40 m."}
    itens, _e, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"BORDAS ESPESSAS": 812.4}, extra={"_mol_ly": {"BORDAS ESPESSAS"}})
    assert itens[0].confidence.value == "estimado" and "MOLDURA OU LIMITE" in itens[0].observations


def test_CONTROLE_o_laco_sem_a_marca_segue():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Rede de hidrantes",
            "unit": "ml", "quantity": 812.4, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'BORDAS ESPESSAS' = 812,40 m."}
    itens, _e, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"BORDAS ESPESSAS": 812.4}, extra={"_mol_ly": set()})
    assert "MOLDURA OU LIMITE" not in itens[0].observations


# ── 🩸 04/10 (verificação do e8fb03c, sondas da Projetos): as formas de citar ──
CITA = [
    ("Fonte: ALVENARIA = 120 m", "ALVENARIA"),                          # nome = número
    ("comprimento em ALVENARIA: 120 m", "ALVENARIA"),                   # nome: número
    ("Margem Externa = 120 m", "MARGEM EXTERNA"),
    ("Fonte: comprimento de 'ALVENARIA' = 120 m", "ALVENARIA"),
    ("medido na camada Alvenaria: 120 m", "ALVENARIA"),
    ("layers ALVENARIA e FOLHA = 120 m", "FOLHA"),                      # (a) lista
    ("Layers: ALVENARIA, FOLHA = 120 m", "FOLHA"),
    ("layers PAREDE e ALVENARIA somam 120 m", "ALVENARIA"),
    ("layers 'PAREDE' e 'ALVENARIA' = 120 m", "ALVENARIA"),
    ("layers PAREDE/ALVENARIA = 120 m", "ALVENARIA"),
    ("layer de parede ALVENARIA = 120 m", "ALVENARIA"),                 # (b)
    ("medido no layer de parede ALVENARIA, conforme a planta", "ALVENARIA"),   # sem o "= número"
    ("layer (ALVENARIA) = 120 m", "ALVENARIA"),
    ("layer «ALVENARIA» = 120 m", "ALVENARIA"),
    ("ALVENARIA (layer) = 120 m", "ALVENARIA"),
    ("Layer: ALVENARIA = 120 m", "ALVENARIA"),
    ("layer=ALVENARIA", "ALVENARIA"),
    ('polilinhas do layer "PAREDES" somam 120 m', "PAREDES"),
    ("layer PAREDES; 120 m", "PAREDES"),
]
NAO_CITA = [
    ("layer A-WALL = 120 m, conforme folha ELE-000", "FOLHA"),
    ("layer A-WALL = 120 m (paredes de alvenaria)", "ALVENARIA"),
    ("layer ALVENARIA_EXT = 120 m", "ALVENARIA"),
    ("layer ALVENARIA-EXT = 120 m", "ALVENARIA"),
    ("layer A-WALL = 120 m ('alvenaria' de bloco)", "ALVENARIA"),
    ("camada de alvenaria do layer A-WALL = 120 m", "ALVENARIA"),
    # medido nas observações da produção: aspas soltas e caixa alta de texto citado do desenho
    ("layer A-WALL = 120 m; pontos em posição 'Parede' a altura média", "PAREDE"),
    ("layer A-WALL = 120 m. Texto 'S ABERTURA NA ALVENARIA' identificado na prancha", "ALVENARIA"),
    ("layer A-WALL = 120 m. Nota: 'OBS.: AS PAREDES ONDE TERÃO AR-CONDICIONADO'", "PAREDES"),
]


@pytest.mark.parametrize("nome,trava,marca,_m2", IRMAS, ids=_IDS)
@pytest.mark.parametrize("obs,marcado", CITA)
def test_as_formas_de_citar_o_layer_caem(nome, trava, marca, _m2, obs, marcado):
    conf, _o, reb = _roda(trava, obs, "ml", marcado)
    assert reb and conf == "estimado", (nome, obs)


@pytest.mark.parametrize("nome,trava,marca,_m2", IRMAS, ids=_IDS)
@pytest.mark.parametrize("obs,marcado", NAO_CITA)
def test_CONTROLE_o_que_nao_e_citacao_fica(nome, trava, marca, _m2, obs, marcado):
    conf, _o, reb = _roda(trava, obs, "ml", marcado)
    assert not reb and conf == "confirmado", (nome, obs)


@pytest.mark.parametrize("nome,trava,marca,_m2", IRMAS, ids=_IDS)
@pytest.mark.parametrize("obs,marcado", [
    ("layer ALVENARIA EXTERNA = 120 m", "ALVENARIA"),
    ("layer A-WALL = 120 m; camada alvenaria de vedação", "ALVENARIA"),
])
def test_CUSTO_DOCUMENTADO_nome_seguido_de_palavra_cai(nome, trava, marca, _m2, obs, marcado):
    """O leitor da observação já cortava "ALVENARIA EXTERNA" em "ALVENARIA", e
    "camada alvenaria de vedação" lê como citação: rebaixa um ✓ de outro layer
    se "ALVENARIA" estiver marcado. Custa só o ✓."""
    conf, _o, reb = _roda(trava, obs, "ml", marcado)
    assert reb, (nome, obs)


@pytest.mark.parametrize("unit", ["m.", "ml.", "M.", "ML.", "m.l.", "mt.", "metros."])
def test_o_ponto_no_fim_da_unidade_de_metro(unit):
    assert er.unidade_de_comprimento_na_trava(unit), unit


@pytest.mark.parametrize("unit", ["m2.", "m².", "un.", "kg.", "m3."])
def test_CONTROLE_o_ponto_no_fim_nao_vira_metro(unit):
    assert not er.unidade_de_comprimento_na_trava(unit), unit
