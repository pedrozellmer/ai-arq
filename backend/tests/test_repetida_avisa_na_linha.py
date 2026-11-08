# -*- coding: utf-8 -*-
"""O mesmo serviço com o mesmo número duas vezes ganha aviso na linha.

🩸 07/11/2026 (a8688985): "Eletroduto rígido — alimentação geral" e
"Eletroduto rígido de PVC pesado — alimentação", 123,32 ml cada, e mais três
pares assim. O aviso "⚠ Este serviço aparece em N pranchas" só vale ENTRE
pranchas; na mesma prancha o dobro saía calado.
📏 30 dias (08/11, regra rodada sobre as linhas do banco): 13 grupos em 9 de
127 jobs, ~12 deles dobro real; o cliente apagou 0. A 1ª versão pegava 20, e
os 7 a mais eram dois tubos de Ø diferentes, dois geradores GMG-1/GMG-2 e dois
cômodos com a mesma área (cortados pelos controles abaixo).
🔑 REPETIDA_AVISA_NA_LINHA=1 escreve o aviso; com 0 o motor só conta. Nunca
apaga nem junta linha. As descrições abaixo são as do banco (cortadas).
"""
import os
import sys
import textwrap

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
import pytest  # noqa: E402
import main  # noqa: E402
from engine_rules import MARCA_MESMO_NUMERO, linhas_de_mesmo_numero  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402


def _it(desc, q, unit="ml", obs=""):
    return BudgetItem(item_num="1", description=desc, unit=unit, quantity=q,
                      confidence=Confidence.ESTIMADO, observations=obs)


_DOBROS = [
    ("ml", 123.32,
     "Eletroduto rígido de PVC pesado ou aço galvanizado — alimentação geral (diâmetros variados conforme legenda: Ø1\", Ø1.1/4\", Ø2\")",
     "Eletroduto rígido — alimentação elétrica geral de garagem (bitolas conforme projeto: Ø1\", Ø1.1/4\", Ø2\", Ø4\")"),
    ("kg", 8.8, "Aço CA-50 — barra ø6,3 mm — fornecimento, corte, dobramento",
     "Aço CA-50 — barra ø6,3 mm — corte, dobramento e colocação"),
    ("m²", 5.89, "Fornecimento e assentamento de piso P1 — especificação não informada",
     "Fornecimento e assentamento de piso — referência P1, especificação a confirmar"),
    ("ml", 4.8, "Estrutura de cobertura — perfil metálico ou madeira, a especificar",
     "Estrutura metálica de cobertura — perfis e vigas — seção e tipo a confirmar"),
    ("kg", 107.0, "Armadura CA-50 Ø6,3 mm — Sapatas de Divisa (posições N4 e N5)",
     "Armadura CA — Ø 6,3 mm — Base 1 / Sapatas Divisa — posições"),
    ("m2", 65.47, "Laje técnica para condensadoras — área de projeção",
     "Laje técnica de concreto armado — condensadoras"),
]


@pytest.mark.parametrize("un,q,a,b", _DOBROS)
def test_o_dobro_real_e_achado(un, q, a, b):
    assert linhas_de_mesmo_numero([_it(a, q, un), _it("Pintura de teto", 30.5, "m²"),
                                   _it(b, q, un)]) == [[0, 2]]


_CONTROLES = [
    # dois tubos de diâmetro diferente com o mesmo comprimento
    [_it("Eletroduto de aço galvanizado — Ø 50 mm — Energia Estabilizada", 364.01),
     _it("Eletroduto de aço galvanizado — Ø 25 mm — Energia Essencial", 364.01)],
    [_it("Tubulação PS1 — Ø200mm — esgoto sanitário", 367.0),
     _it("Tubulação PS1 — Ø300mm — esgoto sanitário", 367.0)],
    # duas peças iguais com código numerado
    [_it("Base de concreto para geradores (GMG-1)", 13.02, "m²"),
     _it("Base de concreto para geradores (GMG-2)", 13.02, "m²")],
    # dois cômodos com a mesma área escrita na linha
    [_it("Piso em porcelanato — Varanda (A=4,60 m²)", 4.6, "m²"),
     _it("Piso em porcelanato — Lavanderia (A=4,60 m²)", 4.6, "m²")],
    # pavimentos tipo: somam
    [_it("Vigas — área de fôrma — Pavimento TIPO-002", 261.73, "m²"),
     _it("Vigas — área de fôrma — Pavimento TIPO-003", 261.73, "m²")],
    # número redondo pequeno coincide à toa
    [_it("Piso em quartzito Da Vinci", 15.0, "m²"), _it("Piso em carpete Orlean", 15.0, "m²")],
    # já tem o aviso de N pranchas
    [_it("Rodapé em porcelanato P3", 73.55, obs="⚠ Este serviço aparece em 2 pranchas do projeto"),
     _it("Rodapé em porcelanato P3 — altura 7 cm", 73.55)],
    # zerada, unidade de contagem, serviço diferente
    [_it("Rodapé de madeira", 0.0), _it("Rodapé de madeira", 0.0)],
    [_it("Tomada 2P+T", 12.5, "un"), _it("Tomada 2P+T", 12.5, "un")],
    [_it("Alvenaria de vedação", 231.91, "m²"), _it("Pintura acrílica em paredes", 231.91, "m²")],
    # "Fornecimento e…" não é o serviço: porcelanato e piso emborrachado são dois
    [_it("Fornecimento e assentamento de porcelanato Posto 10", 12.34, "m²"),
     _it("Fornecimento e instalação de piso emborrachado preto", 12.34, "m²")],
]


@pytest.mark.parametrize("itens", _CONTROLES)
def test_CONTROLE_o_que_nao_e_dobro(itens):
    assert linhas_de_mesmo_numero(itens) == []


def test_aceita_dict_como_o_banco_devolve():
    a, b = _DOBROS[1][2], _DOBROS[1][3]
    linhas = [{"description": a, "unit": "kg", "quantity": 8.8},
              {"description": b, "unit": "kg", "quantity": 8.80}]
    assert linhas_de_mesmo_numero(linhas) == [[0, 1]]


# ── o bloco do process_job, executado de verdade ──
_INICIO = "        # 🩸 08/11: o MESMO serviço com o MESMO número duas vezes na planilha"
_FIM = "motor:repetida-na-linha\", f\"FALHOU: {_erep}\", job_id,\n                       severity=\"warning\")\n"


def _bloco():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read().replace("\r\n", "\n")
    i = src.index(_INICIO)
    return src[i:src.index(_FIM, i) + len(_FIM)]


def _rodar(valor, itens=None):
    logs = []
    un, q, a, b = _DOBROS[0]
    itens = itens or [_it(a, q, un, obs="Fonte: layer 'ELETRODUTO'"), _it(b, q, un)]
    ns = {"all_items": itens, "job_id": "t1",
          "_chave_do_job": lambda job, chave: valor if chave == "REPETIDA_AVISA_NA_LINHA" else "0",
          "_observacao_que_cabe": main._observacao_que_cabe,
          "_log_error": lambda st, msg, job=None, severity="error": logs.append(
              (st, msg.split(" | ")[0]))}
    exec(textwrap.dedent(_bloco()), ns)
    return itens, logs


def test_a_chave_em_0_so_registra():
    itens, logs = _rodar("0")
    assert not any(MARCA_MESMO_NUMERO in (i.observations or "") for i in itens)
    assert logs == [("motor:repetida-na-linha", "grupos=1 linhas=2 liga=0")]


def test_a_chave_em_1_avisa_as_duas_linhas_e_nao_apaga_nada():
    itens, logs = _rodar("1")
    assert len(itens) == 2 and all(i.quantity == 123.32 for i in itens)
    assert itens[0].observations.startswith(MARCA_MESMO_NUMERO), itens[0].observations
    assert "Eletroduto rígido — alimentação" in itens[0].observations, "não citou a outra linha"
    assert "Fonte: layer 'ELETRODUTO'" in itens[0].observations, "a fonte original sumiu"
    assert itens[1].observations.startswith(MARCA_MESMO_NUMERO)
    assert logs == [("motor:repetida-na-linha", "grupos=1 linhas=2 liga=1")]


def test_a_planilha_refeita_nao_repete_o_aviso():
    itens, _ = _rodar("1")
    itens, _ = _rodar("1", itens)
    assert all(i.observations.count(MARCA_MESMO_NUMERO) == 1 for i in itens)


def test_nasce_desligada_e_avaliavel():
    assert "REPETIDA_AVISA_NA_LINHA" in main._CHAVES_AVALIAVEIS
    assert "motor:repetida-na-linha" in main._STAGES_DIAGNOSTICO


def test_o_bloco_roda_antes_da_planilha():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read()
    i = src.index(_INICIO)
    assert i < src.index("generate_spreadsheet(project_data, all_items, output_path, typology=typology)", i)
