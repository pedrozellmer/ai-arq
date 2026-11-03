# -*- coding: utf-8 -*-
"""Bater com o layer prova que o número é do layer, não que o layer é a peça.

🩸 02/11/2026 (job 0b572906): bancada de 1,30 m saiu com 43,60 ml e ✓ MEDIDO, com
a nota dizendo que a soma cobria planta e cortes. Em 58 promoções de cliente desde
28/09, 18 traziam esse tipo de ressalva por escrito.
🔑 RESSALVA_DA_PECA_NAO_PROMOVE=1 deixa a linha estimada; com 0 o motor só conta.
"""
import ast
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
import main  # noqa: E402

_INDICE = {"comprimento": [("PEDRA", 18.89)], "area": [], "contagem": []}


def _linha(nota):
    return {"description": "Bancada", "unit": "ml", "quantity": 18.89,
            "confidence": "estimado", "origem": "dxf_geom",
            "observations": "Fonte: comprimento do layer PEDRA = 18.89 m. " + nota}


_RESSALVAS = [
    "Atenção: este comprimento inclui linhas de marcenaria em planta.",
    "Valor inclui todos os elementos do layer.",
    "Valor inclui todas as peças do layer.",
    "Layer de escada inclui degraus e espelhos.",
    "O total inclui espelhos da escada.",
    "O total inclui patamares da escada.",
    "o comprimento inclui representações do mesmo objeto.",
    "Aparece em múltiplas vistas.",
    "Aparece em múltiplos cortes.",
    "Planta repetida no arquivo.",
    "A soma pode dobrar o eixo real.",
    "Viga desenhada pelas 2 faces.",
    "Viga desenhada pelas duas faces.",
    "Este total não representa a extensão da prumada.",
    "Provavelmente fragmento de detalhe.",
    "Esta área pode ser parcial.",
    "Área estimada igual à área de piso.",
    "Layer usado como proxy para rodapé.",
    "Layer com 3 padrões diferentes.",
    "Layer com padrões mistos.",
    "Acabamentos mistos no layer.",
    "Pode representar outro pavimento.",
    "Pode corresponder ao perímetro dos ambientes.",
]

_SEM_RESSALVA = [
    "",
    "Não inclui linhas de outros layers.",
    "Sem múltiplas vistas no arquivo.",
    "Medida pelo eixo, soma das 2 bordas contada uma vez.",
    "Revestimento nas 2 faces da divisória.",
    "Confirmar material no memorial.",
]


@pytest.mark.parametrize("nota", _RESSALVAS)
def test_a_ressalva_da_peca_e_lida(nota):
    assert er.ressalva_da_peca(nota)
    prom = er.selo_com_prova_da_geometria([_linha(nota)], _INDICE)
    assert len(prom) == 1 and prom[0]["ressalva_da_peca"]


@pytest.mark.parametrize("nota", _SEM_RESSALVA)
def test_sem_ressalva_a_promocao_segue_limpa(nota):
    assert er.ressalva_da_peca(nota) == ""
    prom = er.selo_com_prova_da_geometria([_linha(nota)], _INDICE)
    assert len(prom) == 1 and prom[0]["ressalva_da_peca"] == ""


def test_ressalva_vazia_quando_a_nota_nao_existe():
    assert er.ressalva_da_peca(None) == ""


def _promovidos():
    return [{"indice": 0, "descricao": "Bancada", "ressalva_da_peca": "inclui linhas"},
            {"indice": 1, "descricao": "Rodapé", "ressalva_da_peca": ""}]


def _prepara(monkeypatch, valor):
    logs = []
    monkeypatch.setattr(main, "_chave_do_job", lambda j, n, p="0": valor if n == "RESSALVA_DA_PECA_NAO_PROMOVE" else "x")
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))
    return logs


def test_com_a_chave_em_0_nada_muda_e_o_alcance_e_contado(monkeypatch):
    logs = _prepara(monkeypatch, "0")
    assert main._tira_promocao_com_ressalva("j", _promovidos()) == _promovidos()
    assert logs == [("motor:selo-ressalva-da-peca",
                     "linhas=1 tirou=0 | Bancada (inclui linhas)", "j")]


def test_com_a_chave_em_1_so_a_linha_com_ressalva_sai(monkeypatch):
    logs = _prepara(monkeypatch, "1")
    assert [p["indice"] for p in main._tira_promocao_com_ressalva("j", _promovidos())] == [1]
    assert logs[0][1].startswith("linhas=1 tirou=1 |")


def test_sem_ressalva_nao_registra(monkeypatch):
    logs = _prepara(monkeypatch, "1")
    limpos = [_promovidos()[1]]
    assert main._tira_promocao_com_ressalva("j", limpos) == limpos
    assert logs == []


def test_o_registro_leva_no_maximo_6_linhas(monkeypatch):
    logs = _prepara(monkeypatch, "0")
    muitos = [dict(_promovidos()[0], descricao="linha-%d" % i) for i in range(8)]
    main._tira_promocao_com_ressalva("j", muitos)
    assert logs[0][1].startswith("linhas=8 ")
    assert "linha-5" in logs[0][1] and "linha-6" not in logs[0][1]


def test_chave_avaliavel_etapa_de_diagnostico_e_nasce_desligada():
    assert "RESSALVA_DA_PECA_NAO_PROMOVE" in main._CHAVES_AVALIAVEIS
    assert "motor:selo-ressalva-da-peca" in main._STAGES_DIAGNOSTICO
    assert main._chave_do_job("job-sem-avaliacao", "RESSALVA_DA_PECA_NAO_PROMOVE") == "0"


def test_a_chave_do_selo_passa_pelo_filtro_antes_de_promover():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    achados = []
    for no in ast.walk(arvore):
        if (isinstance(no, ast.Assign) and isinstance(no.targets[0], ast.Name)
                and no.targets[0].id == "_promovidos" and isinstance(no.value, ast.Call)):
            achados.append(no.value)
    assert len(achados) == 1
    chamada = achados[0]
    assert chamada.func.id == "_tira_promocao_com_ressalva"
    assert chamada.args[0].id == "job_id"
    assert chamada.args[1].func.id == "_chave_selo"
