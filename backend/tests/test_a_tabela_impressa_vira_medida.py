# -*- coding: utf-8 -*-
"""A tabela impressa: contagem lida de tabela sai MEDIDA, com prova no texto.

⏭️ Decisão do Pedro, 21/09/2026: *"se você conseguiu ver numa tabela… tem que
colocar como medido — independente se é PDF ou CAD"*; e em 22/09, vendo o
alcance: *"bora ampliar então"*.

🩸 O caso. Cliente de 22/09 às 17:57 (16 PDFs, nenhum CAD): 537 linhas, ZERO
medidas. 86 delas dizem *"Quantidade conforme TABELA DE EQUIPAMENTOS da
prancha"* e saem carimbadas *"Estimativa: lido de PDF, não medido em
geometria"*. O nível 1 já existia — mas com o gatilho preso ao vocabulário
"quadro de quantitativos", que é como ESTRUTURA escreve.

📊 Medido antes de escrever (90 dias, 7.628 linhas com número, não medidas,
sem CAD): "quadro de quantitativos" alcança **24 linhas**; "tabela"+"legenda"+
"quadro" alcançam **2.888**. Dessas, **1.859 são CONTAGEM** em 134 projetos,
350 kg, e só **247 m²**.

🔑 POR QUE SÓ CONTAGEM: a auditoria de 19/09 mediu que a IA acerta 20–29%
contando símbolo e 2–9% medindo área/comprimento. E área lida de legenda é
exatamente o vazamento que a rede de 24/08 existe pra pegar (61 itens em 19
projetos, 33.962 m² apresentados como medidos).

🪤 A TRAVA ANTI-ACASO: contagem é número pequeno e inteiro — "7" aparece em
qualquer prancha, e uma prova de UMA linha seria coincidência com cara de
medição. Só promove quando a MESMA prancha tem três números distintos, de
três linhas que dizem ter lido da tabela, todos achados no texto do PDF.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from engine_rules import (  # noqa: E402
    afirma_tabela_impressa,
    selo_da_tabela_impressa as promove,
)

_PRANCHA = ("prancha-eletrica.pdf", 3)


def _cent(*valores):
    return frozenset(int(round(v * 100)) for v in valores)


def _l(q, obs="Quantidade conforme tabela de equipamentos da prancha.",
       unidade="un", selo="estimado", origem="vision_pdf",
       arquivo=_PRANCHA[0], pagina=_PRANCHA[1], desc="Item"):
    return {"arquivo": arquivo, "pagina": pagina, "unidade": unidade,
            "quantidade": q, "texto": obs, "descricao": desc,
            "selo": selo, "origem": origem}


def _mapa(*valores):
    return {_PRANCHA: _cent(*valores)}


# ── o caso real ────────────────────────────────────────────────────────────
def test_a_contagem_lida_da_TABELA_com_o_numero_no_texto_sobe():
    linhas = [_l(76), _l(9), _l(8), _l(4)]
    achados = promove(linhas, _mapa(76, 9, 8, 4))
    assert len(achados) == 4, achados
    assert all("no texto do PDF" in a["motivo"] for a in achados)


@pytest.mark.parametrize("obs", [
    "Quantidade conforme tabela de equipamentos da prancha.",
    "Conforme legenda de luminárias da prancha.",
    "Lido no quadro de esquadrias.",
    "Segundo a planilha de pontos elétricos.",
    "De acordo com a relação de aparelhos.",
    "Consta na lista de equipamentos.",
])
def test_o_vocabulario_cobre_como_cada_disciplina_ESCREVE(obs):
    """🔑 Foi o vocabulário estreito que deixou o nível 1 em 24 de 2.888."""
    assert afirma_tabela_impressa(obs) is True, obs
    linhas = [_l(76, obs), _l(9, obs), _l(8, obs)]
    assert len(promove(linhas, _mapa(76, 9, 8))) == 3


# ── a trava anti-acaso ─────────────────────────────────────────────────────
def test_UMA_linha_provada_sozinha_NAO_sobe():
    """🪤 "7" aparece em qualquer prancha. Uma prova só é coincidência."""
    linhas = [_l(7), _l(12), _l(30)]
    assert promove(linhas, _mapa(7)) == [], (
        "promoveu com uma prova só — é o acaso passando por medição")


def test_DUAS_provas_ainda_nao_bastam():
    linhas = [_l(7), _l(12), _l(30)]
    assert promove(linhas, _mapa(7, 12)) == []


def test_TRES_provas_na_mesma_prancha_liberam_as_tres():
    linhas = [_l(7), _l(12), _l(30)]
    assert len(promove(linhas, _mapa(7, 12, 30))) == 3


def test_a_trava_conta_por_PRANCHA_nao_pelo_projeto():
    """Três provas espalhadas em três pranchas não provam tabela nenhuma."""
    linhas = [_l(7, arquivo="a.pdf", pagina=1),
              _l(12, arquivo="b.pdf", pagina=1),
              _l(30, arquivo="c.pdf", pagina=1)]
    mapa = {("a.pdf", 1): _cent(7), ("b.pdf", 1): _cent(12),
            ("c.pdf", 1): _cent(30)}
    assert promove(linhas, mapa) == []


# ── controles positivos ────────────────────────────────────────────────────
@pytest.mark.parametrize("unidade", ["m²", "m2", "m", "ml", "m³", "kg", "vb"])
def test_CONTROLE_so_CONTAGEM_sobe_por_esta_regua(unidade):
    """🚨 Área lida de legenda é o vazamento de 24/08 — 33.962 m² como
    medidos. Esta régua não encosta em m², m, m³ nem kg."""
    linhas = [_l(76, unidade=unidade), _l(9, unidade=unidade),
              _l(8, unidade=unidade)]
    assert promove(linhas, _mapa(76, 9, 8)) == [], unidade


def test_CONTROLE_numero_que_NAO_esta_no_texto_nao_sobe():
    # Quatro linhas dizem ter lido da tabela; três números estão no texto
    # e o quarto não. A prancha TEM tabela (3 provas), mas a linha sem
    # prova própria continua laranja.
    linhas = [_l(76), _l(9), _l(30), _l(8)]
    achados = promove(linhas, _mapa(76, 9, 30))       # o 8 fica de fora
    assert len(achados) == 3, achados
    provados = {a["indice"] for a in achados}
    assert 3 not in provados, "o 8 não estava no texto e subiu assim mesmo"


@pytest.mark.parametrize("obs, porque", [
    ("A tabela NÃO traz a quantidade deste item.", "negação"),
    ("Sem legenda na prancha; contagem visual.", "negação"),
    ("Quantidade adotada por analogia à tabela da prancha anterior.", "adoção"),
    ("Conforme tabela; quantidade aproximada.", "adoção"),
    ("Estimativa baseada na relação de equipamentos típica.", "adoção"),
])
def test_CONTROLE_negacao_e_adocao_nao_sobem(obs, porque):
    linhas = [_l(76, obs), _l(9, obs), _l(8, obs)]
    assert promove(linhas, _mapa(76, 9, 8)) == [], porque


def test_CONTROLE_quem_ja_esta_medido_nao_e_tocado():
    linhas = [_l(76, selo="confirmado"), _l(9, selo="confirmado"),
              _l(8, selo="confirmado")]
    assert promove(linhas, _mapa(76, 9, 8)) == []


def test_CONTROLE_item_de_CAD_nao_passa_por_aqui():
    """O CAD tem a prova da geometria, que é mais forte."""
    linhas = [_l(76, origem="dxf_geom"), _l(9, origem="dxf_geom"),
              _l(8, origem="dxf_geom")]
    assert promove(linhas, _mapa(76, 9, 8)) == []


def test_CONTROLE_quantidade_FRACIONADA_nao_e_contagem():
    linhas = [_l(7.5), _l(12.5), _l(30.5)]
    assert promove(linhas, _mapa(7.5, 12.5, 30.5)) == []


def test_CONTROLE_sem_o_mapa_do_texto_nao_promove_nada():
    linhas = [_l(76), _l(9), _l(8)]
    assert promove(linhas, None) == []
    assert promove(linhas, {}) == []


def test_CONTROLE_observacao_que_nao_cita_tabela_nao_sobe():
    obs = "Contagem visual dos símbolos na planta."
    linhas = [_l(76, obs), _l(9, obs), _l(8, obs)]
    assert promove(linhas, _mapa(76, 9, 8)) == []
