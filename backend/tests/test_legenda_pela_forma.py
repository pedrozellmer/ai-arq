# -*- coding: utf-8 -*-
"""A coluna de legenda SEMEADA PELA FORMA: o símbolo é amostra mesmo quando o
rótulo não repete o nome do bloco.

🩸 12/10/2026 (fila de 07/10, item j). A guarda só provava a amostra quando o
rótulo ao lado repetia o nome do bloco, e a coluna de símbolos só nascia de 3
provadas assim. Legenda de bloco anônimo, de sigla ou de nome sem relação com o
rótulo ("QZA" ao lado de "Extintor de água pressurizada") escapava inteira: cada
símbolo virava uma peça contada.
📏 178 DXF do acervo com título de legenda: 617 → 757 amostras, +140 em 12
arquivos de 10 jobs e nenhuma a menos; 61 blocos só existiam na legenda.

A régua é estreita de propósito — marcar peça de verdade como legenda é pior
que deixar o símbolo contado. A medida derrubou no caminho: só "rótulos
distintos" (entrava a etiqueta de nível em corte, o mesmo bloco 17 vezes) e
"nomes e rótulos distintos" (entrava a vaga de estacionamento numerada, de bloco
único por inserção, com o número dentro da caixa).

🪤 Nomes e layers FICTÍCIOS (repositório público, regra nº6).
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402

PASSO = 0.45
INCENDIO = [("QZA", "Extintor de água pressurizada"), ("QZ", "Extintor de pó químico"),
            ("QZB", "Hidrante simples"), ("QZAD", "Acionador de bomba"), ("QZKH", "Registro de recalque")]


def _linha(nome, y, rotulo=None, x=0.0, h=0.1, xr=0.40, meia=0.1):
    """Um símbolo (caixa de lado 2·meia em (x, y)) e o rótulo dele começando em xr."""
    ins = (nome, (x - meia, y - meia, x + meia, y + meia), (x, y))
    tx = [(rotulo, xr, y - h / 2, h)] if rotulo else []
    return ins, tx


def _coluna(pares, y0=0.0, passo=PASSO, **kw):
    ins, tx = [], []
    for k, (nome, rotulo) in enumerate(pares):
        a, b = _linha(nome, y0 - k * passo, rotulo, **kw)
        ins.append(a)
        tx += b
    return ins, tx


def _amostras(out):
    return {n: sorted(ps) for n, ps in out.items()}


@pytest.fixture(autouse=True)
def _chaves(monkeypatch):
    monkeypatch.delenv("LEGENDA_PELA_FORMA", raising=False)
    monkeypatch.delenv("LEGENDA_POR_COLUNA", raising=False)


# ── a legenda que o nome não prova ──────────────────────────────────────────
def test_legenda_de_bloco_cujo_nome_nao_esta_no_rotulo():
    ins, tx = _coluna(INCENDIO)
    out = dx.amostras_de_legenda(ins, tx)
    assert _amostras(out) == {n: [(0.0, -k * PASSO)] for k, (n, _r) in enumerate(INCENDIO)}


def test_CONTROLE_sem_a_regra_nenhum_e_amostra(monkeypatch):
    monkeypatch.setenv("LEGENDA_PELA_FORMA", "0")
    ins, tx = _coluna(INCENDIO)
    assert dx.amostras_de_legenda(ins, tx) == {}


def test_as_pecas_da_planta_nao_viram_amostra():
    ins, tx = _coluna(INCENDIO)
    ins += [("QZA", (49.9, 49.9, 50.1, 50.1), (50.0, 50.0)), ("QZA", (59.9, 49.9, 60.1, 50.1), (60.0, 50.0)),
            ("QZB", (-0.1, -30.1, 0.1, -29.9), (0.0, -30.0))]
    out = dx.amostras_de_legenda(ins, tx)
    assert out["QZA"] == [(0.0, 0.0)] and out["QZB"] == [(0.0, -2 * PASSO)]


def test_tres_simbolos_nao_semeiam():
    ins, tx = _coluna(INCENDIO[:3])
    assert dx.amostras_de_legenda(ins, tx) == {}


def test_CONTROLE_quatro_simbolos_semeiam():
    ins, tx = _coluna(INCENDIO[:4])
    assert sorted(dx.amostras_de_legenda(ins, tx)) == sorted(n for n, _r in INCENDIO[:4])


# ── o que tem a forma e NÃO é legenda ───────────────────────────────────────
def test_o_mesmo_bloco_repetido_nao_e_legenda():
    # a etiqueta de nível em corte: o MESMO bloco, um rótulo diferente em cada
    niveis = [("NIVEL", "Cobertura acabada"), ("NIVEL", "Cobertura osso"), ("NIVEL", "Tipo sete acabado"),
              ("NIVEL", "Tipo sete osso"), ("NIVEL", "Tipo seis acabado")]
    assert dx.amostras_de_legenda(*_coluna(niveis)) == {}


def test_um_nome_repetido_entre_cinco_ja_nao_semeia():
    pares = INCENDIO[:4] + [("QZA", "Extintor sobre rodas")]
    assert dx.amostras_de_legenda(*_coluna(pares)) == {}


def test_rotulo_repetido_nao_e_legenda():
    pares = [(n, "Ponto de força" if k in (1, 3) else r) for k, (n, r) in enumerate(INCENDIO)]
    assert dx.amostras_de_legenda(*_coluna(pares)) == {}


#: a vaga de estacionamento: bloco de nome único por inserção ("BX-107": nenhuma palavra que o
#: rótulo possa repetir) e um texto com palavra em cada uma
_VAGAS = [("BX-%d" % k, "Coberta numero %d" % k) for k in range(107, 112)]


def test_o_rotulo_dentro_da_caixa_e_a_vaga_numerada():
    # o texto fica DENTRO da caixa da vaga (começa no meio dela)
    ins, tx = _coluna(_VAGAS, passo=1.1, meia=0.5, xr=0.0)
    assert dx.amostras_de_legenda(ins, tx) == {}


def test_CONTROLE_o_mesmo_rotulo_a_direita_da_caixa_semeia():
    ins, tx = _coluna(_VAGAS, passo=1.1, meia=0.5, xr=0.8)
    assert len(dx.amostras_de_legenda(ins, tx)) == 5


def test_o_rotulo_que_comeca_meia_altura_antes_da_borda_ainda_e_a_direita():
    # a folga é de meia altura do rótulo: x1 = 0,5 e h = 0,1 → 0,46 passa, 0,44 não
    assert len(dx.amostras_de_legenda(*_coluna(_VAGAS, passo=1.1, meia=0.5, xr=0.46))) == 5
    assert dx.amostras_de_legenda(*_coluna(_VAGAS, passo=1.1, meia=0.5, xr=0.44)) == {}


def test_rotulo_que_e_so_codigo_nao_semeia():
    # o equipamento com a etiqueta de circuito ao lado
    tags = [("FLP-A", "Q.3.1-4"), ("PNL-B", "Q.3.1-5"), ("CX-C", "Q.3.1-6"), ("FLP-D", "Q.3.1-8"), ("PNL-E", "107")]
    assert dx.amostras_de_legenda(*_coluna(tags)) == {}


def test_CONTROLE_metade_dos_rotulos_com_palavra_basta():
    mistos = [("FLP-A", "Q.3.1-4"), ("PNL-B", "Painel metálico"), ("CX-C", "Q.3.1-6"), ("FLP-D", "Eletrocalha")]
    assert len(dx.amostras_de_legenda(*_coluna(mistos))) == 4


def test_simbolos_que_nao_se_empilham_nao_semeiam():
    # os rótulos estão em coluna, mas os símbolos alternam entre dois x que não se encostam
    ins, tx = [], []
    for k, (nome, rotulo) in enumerate(INCENDIO):
        a, b = _linha(nome, -k * PASSO, rotulo, x=(0.0 if k % 2 == 0 else 1.0), h=0.2, xr=1.6)
        ins.append(a)
        tx += b
    assert dx.amostras_de_legenda(ins, tx) == {}


def test_simbolo_mais_largo_que_doze_alturas_nao_semeia():
    # a mesma janela da guarda: desenho com mais de 12 alturas de rótulo de largura não é símbolo de legenda
    # (letra 0,1: 1,4 de largura passa de 12 alturas, 1,1 não; o passo de 1,4 mantém a coluna de rótulos)
    assert dx.amostras_de_legenda(*_coluna(_VAGAS, passo=1.4, meia=0.7, xr=0.9)) == {}
    assert len(dx.amostras_de_legenda(*_coluna(_VAGAS, passo=1.4, meia=0.55, xr=0.9))) == 5


def test_rotulo_a_mais_de_dez_alturas_do_simbolo_nao_e_dele():
    # o símbolo acaba em 0,1 e a letra é 0,1: até 1,1 o rótulo é dele; em 1,3 não
    assert dx.amostras_de_legenda(*_coluna(INCENDIO, xr=1.3)) == {}
    assert len(dx.amostras_de_legenda(*_coluna(INCENDIO, xr=1.0))) == 5


def test_dois_pares_de_simbolos_longe_um_do_outro_nao_sao_uma_coluna():
    # 2 + 2 símbolos no mesmo x, com 20 alturas de vão entre os dois grupos: a coluna de rótulos parte
    a, ta = _coluna(INCENDIO[:2])
    b, tb = _coluna(INCENDIO[2:4], y0=-PASSO - 2.0)
    assert dx.amostras_de_legenda(a + b, ta + tb) == {}


def test_rotulos_de_letras_diferentes_nao_sao_uma_coluna():
    ins, tx = [], []
    for k, (nome, rotulo) in enumerate(INCENDIO[:4]):
        a, b = _linha(nome, -k * PASSO, rotulo, h=(0.1 if k < 2 else 0.16))
        ins.append(a)
        tx += b
    assert dx.amostras_de_legenda(ins, tx) == {}


def test_entre_dois_simbolos_na_mesma_linha_vale_o_mais_perto_do_rotulo():
    # à esquerda de cada símbolo da legenda há outro desenho (a MESMA moldura em toda linha), também
    # dentro da janela do rótulo: o símbolo do rótulo é o que encosta nele
    ins, tx = _coluna(INCENDIO)
    ins += [("MOLDURA", (-0.6, -k * PASSO - 0.1, -0.4, -k * PASSO + 0.1), (-0.5, -k * PASSO)) for k in range(5)]
    out = dx.amostras_de_legenda(ins, tx)
    assert sorted(n for n in out if n != "MOLDURA") == sorted(n for n, _r in INCENDIO)


# ── um símbolo, várias linhas de rótulo ─────────────────────────────────────
def test_simbolo_com_duas_linhas_de_rotulo_conta_uma_vez():
    ins, tx = _coluna(INCENDIO[:3])
    tx.append(("com mangueira de 30 m", 0.40, -2 * PASSO - 0.05 - 0.12, 0.1))     # 2ª linha do 3º rótulo
    # 4 rótulos na coluna, mas só 3 inserções diferentes: não semeia
    assert dx.amostras_de_legenda(ins, tx) == {}


def test_CONTROLE_quatro_insercoes_com_uma_de_duas_linhas_semeiam():
    ins, tx = _coluna(INCENDIO[:4])
    tx.append(("com mangueira de 30 m", 0.40, -2 * PASSO - 0.05 - 0.12, 0.1))
    out = dx.amostras_de_legenda(ins, tx)
    assert _amostras(out) == {n: [(0.0, -k * PASSO)] for k, (n, _r) in enumerate(INCENDIO[:4])}


# ── as sementes entram na coluna de símbolos (d), e a regra só acrescenta ───
def test_a_semente_puxa_o_vizinho_de_coluna_sem_rotulo():
    ins, tx = _coluna(INCENDIO[:4] + [("LUM SOM", None)])
    out = dx.amostras_de_legenda(ins, tx)
    assert out.get("LUM SOM") == [(0.0, -4 * PASSO)]


def test_CONTROLE_sem_a_coluna_de_simbolos_o_vizinho_fica(monkeypatch):
    monkeypatch.setenv("LEGENDA_POR_COLUNA", "0")
    ins, tx = _coluna(INCENDIO[:4] + [("LUM SOM", None)])
    out = dx.amostras_de_legenda(ins, tx)
    assert "LUM SOM" not in out and len(out) == 4


def _coluna_esparsa():
    """3 símbolos provados pelo NOME a cada 2,0 (linhas 0, −2, −4), 2 de nome sem relação entre eles
    (linhas −1, −3) e um símbolo sem rótulo a 2,9 abaixo do último. Hoje a coluna (d) tem passo 2,0 e
    alcança o de baixo (1,5 × 2,0 = 3,0); semeada, o passo cai pra 1,0 e o alcance pra 1,5."""
    pares = [("TOMADA ALTA", "TOMADA ALTA"), ("QZA", "Extintor de água"), ("TOMADA BAIXA", "TOMADA BAIXA"),
             ("QZB", "Hidrante simples"), ("TOMADA DE PISO", "TOMADA DE PISO")]
    # letra de 0,2: a coluna de rótulos (c) pede 2 vizinhos a até 15 alturas (3,0), e o passo é 1,0
    ins, tx = _coluna(pares, passo=1.0, h=0.2)
    ins.append(("SEM ROTULO", (-0.1, -7.0, 0.1, -6.8), (0.0, -6.9)))
    return ins, tx


def test_so_acrescenta_o_que_a_coluna_de_hoje_alcanca_nao_se_perde(monkeypatch):
    ins, tx = _coluna_esparsa()
    monkeypatch.setenv("LEGENDA_PELA_FORMA", "0")
    hoje = dx.amostras_de_legenda(ins, tx)
    assert hoje.get("SEM ROTULO") == [(0.0, -6.9)], "o cenário: hoje a coluna alcança o de baixo"
    monkeypatch.delenv("LEGENDA_PELA_FORMA")
    out = dx.amostras_de_legenda(ins, tx)
    assert out.get("SEM ROTULO") == [(0.0, -6.9)]
    assert all(out.get(n) == ps for n, ps in hoje.items())


def test_a_amostra_que_ja_era_nao_sai_duas_vezes():
    # as linhas −1 e −3 são alcançadas pela coluna de hoje E são semente: uma vez só cada
    out = dx.amostras_de_legenda(*_coluna_esparsa())
    assert out["QZA"] == [(0.0, -1.0)] and out["QZB"] == [(0.0, -3.0)]
    assert all(len(ps) == 1 for ps in out.values())


def test_duas_insercoes_no_mesmo_ponto_continuam_duas():
    # a mesma peça inserida duas vezes no mesmo ponto (cópia sobreposta) vizinha da coluna
    ins, tx = _coluna(INCENDIO[:4] + [("LUM SOM", None)])
    ins.append(ins[-1])
    out = dx.amostras_de_legenda(ins, tx)
    assert out.get("LUM SOM") == [(0.0, -4 * PASSO)] * 2


# ── pelo extract_dxf ────────────────────────────────────────────────────────
def _dxf_com_legenda(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "ARQ-PAREDE"})
    for nome, _r in INCENDIO:
        b = doc.blocks.new(name=nome)
        b.add_lwpolyline([(-0.1, -0.1), (0.1, -0.1), (0.1, 0.1), (-0.1, 0.1)], close=True)
    for k, (nome, rotulo) in enumerate(INCENDIO):
        msp.add_blockref(nome, (30.0, 20.0 - k * PASSO), dxfattribs={"layer": "INC-SIMB"})
        msp.add_text(rotulo, dxfattribs={"height": 0.1, "layer": "INC-TEXTO",
                                         "insert": (30.4, 20.0 - k * PASSO - 0.05)})
    for x in (2.0, 5.0, 8.0):                            # 3 extintores na planta
        msp.add_blockref("QZA", (x, 3.0), dxfattribs={"layer": "INC-SIMB"})
    p = str(tmp_path / "legenda.dxf")
    doc.saveas(p)
    return p


def test_pelo_extract_dxf_a_amostra_chega_ao_bloco_e_ao_prompt(tmp_path):
    ex = dx.extract_dxf(_dxf_com_legenda(tmp_path))
    por_nome = {b.name: b for b in ex.blocks}
    assert por_nome["QZA"].count == 4 and por_nome["QZA"].amostras_legenda == 1
    assert all(por_nome[n].amostras_legenda == 1 for n, _r in INCENDIO)
    assert ex.metadata["blocos_da_legenda"] == {n: 1 for n, _r in INCENDIO}
    assert ex.to_structured_prompt().count("[ao menos 1 delas = símbolo desenhado na LEGENDA, não peça]") == 5


def test_pelo_extract_dxf_a_chave_desliga(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGENDA_PELA_FORMA", "0")
    ex = dx.extract_dxf(_dxf_com_legenda(tmp_path))
    assert all(b.amostras_legenda == 0 for b in ex.blocks)
    assert "blocos_da_legenda" not in (ex.metadata or {})
    assert "símbolo desenhado na LEGENDA" not in ex.to_structured_prompt()
