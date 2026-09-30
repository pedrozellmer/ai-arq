# -*- coding: utf-8 -*-
"""Marca de condutor (fase, neutro, terra, retorno) desenhada em traços é anotação.

🩸 30/09/2026 — H29 do estudo do acervo. Em produção, conta de casa de 22/07:
"símbolo de condutor FASE 109 un CONFIRMADO", mais NEUTRO 14, TERRA 24 e
RETORNO 16. São as marquinhas que a planta elétrica põe em cada trecho de
eletroduto pra dizer quais fios passam ali — FASE e RETORNO com 1 traço,
NEUTRO e TERRA com 2. Anotação do desenho, não peça.

A regra de 29/09 (WN, W-FFF) só marcava SIGLA sem palavra de ≥ 4 letras; a
função do condutor no nome escapava. Agora: nome = a função (com "cond" ou
"condutor" na frente, singular ou plural) E desenho só de 1–3 LINE.

Guardas:
- as marcas de condutor viram anotação, com o aviso próprio;
- caixa de terra, haste (círculo), 4+ traços, nome que não é SÓ a função:
  continuam peça;
- a IA recebe o aviso na linha do bloco;
- a linha "FASE 109 un" que é a contagem do bloco sai do laço.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402


@pytest.mark.parametrize("nome,assin", [
    ("fase", "LINE:1|bb:0.1x0.1"),
    ("RETORNO", "LINE:1|bb:0.1x0.1"),
    ("NEUTRO", "LINE:2|bb:0.1x0.1"),
    ("Terra", "LINE:2|bb:0.1x0.1"),
    ("FASES", "LINE:1|bb:0.1x0.1"),
    ("COND-FASE", "LINE:1|bb:0.1x0.1"),
    ("condutor terra", "LINE:2|bb:0.1x0.1"),
    ("CONDUTORES_NEUTRO", "LINE:2|bb:0.1x0.1"),
    ("PROTEÇÃO", "LINE:3|bb:0.1x0.1"),
])
def test_marca_de_condutor_e_anotacao(nome, assin):
    nota = er.nota_de_bloco_de_anotacao(nome, assin)
    assert "MARCA DE CONDUTOR" in nota and "MARCA DE ANOTAÇÃO" in nota, nota


@pytest.mark.parametrize("nome,assin", [
    ("TERRA", "LWPOLYLINE:1|bb:0.3x0.3"),           # caixa de terra: retângulo
    ("TERRA", "CIRCLE:1|LINE:2|bb:0.1x0.1"),        # haste: tem círculo
    ("FASE", "LINE:4|bb:0.1x0.1"),                  # mais de 3 traços
    ("CAIXA DE TERRA", "LINE:3|bb:0.3x0.3"),        # o nome é peça, não só a função
    ("HASTE TERRA", "LINE:2|bb:0.1x2.0"),
    ("QUADRO FASE A", "LINE:3|bb:0.5x0.5"),
    ("Eixos do pilar", "LINE:2|bb:1x1"),            # a varredura do estudo: fica
    ("CONDU. C", "LINE:3|bb:0.2x0.2"),
    ("*U12", "LINE:1|bb:0.1x0.1"),                   # anônimo
])
def test_CONTROLE_peca_ou_nome_que_nao_e_so_a_funcao_fica(nome, assin):
    assert er.nota_de_bloco_de_anotacao(nome, assin) == ""


def test_CONTROLE_a_regra_da_sigla_de_29_09_continua():
    assert "SÓ TRAÇOS e sigla" in er.nota_de_bloco_de_anotacao("WN", "LINE:2|bb:0.1x0.1")


def test_a_ia_recebe_o_aviso_na_linha_do_bloco(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    fase = doc.blocks.new("FASE")
    fase.add_line((0, 0), (0.1, 0.1))
    neutro = doc.blocks.new("NEUTRO")
    neutro.add_line((0, 0), (0.1, 0.1))
    neutro.add_line((0.05, 0), (0.15, 0.1))
    tom = doc.blocks.new("TOMADA")
    tom.add_circle((0, 0), 0.1)
    msp = doc.modelspace()
    for i in range(6):
        msp.add_blockref("FASE", (i * 2, 0))
        msp.add_blockref("NEUTRO", (i * 2, 1))
        msp.add_blockref("TOMADA", (i * 2, 5))
    msp.add_line((0, -5), (20, -5))
    p = str(tmp_path / "condutor.dxf")
    doc.saveas(p)
    txt = dx.extract_from_file(p).to_structured_prompt()
    linhas = {l.split(":")[0].strip(): l for l in txt.splitlines() if l.startswith("  ") and " un" in l}
    assert "MARCA DE CONDUTOR" in linhas.get("FASE", ""), linhas
    assert "MARCA DE CONDUTOR" in linhas.get("NEUTRO", ""), linhas
    assert "⚠" not in linhas.get("TOMADA", "x"), linhas


def test_a_linha_FASE_109_un_sai_do_laco():
    """O par que a saída do laço exige: bloco de anotação E a quantidade igual."""
    blocos = {"fase": 109, "NEUTRO": 14}
    anot = {n: c for n, c in blocos.items()
            if er.nota_de_bloco_de_anotacao(n, "LINE:1|bb:0.1x0.1" if n == "fase" else "LINE:2|bb:0.1x0.1")}
    assert anot == blocos
    obs = "Fonte: 109 INSERTs do bloco 'fase' na contagem de blocos."
    assert er.contagem_de_bloco_citada(obs, 109, "un", anot, todos=blocos) == "fase"
