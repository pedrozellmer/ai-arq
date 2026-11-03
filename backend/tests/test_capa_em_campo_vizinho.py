# -*- coding: utf-8 -*-
"""Nome, endereço e arquiteto que a leitura traz com outro nome de campo.

🩸 03/11/2026: nas 1.805 leituras guardadas com `project_data`, o nome veio só em
campo vizinho em 893, o endereço em 216 e o arquiteto em 152 — e a capa da
planilha saía sem as três linhas.
🔑 CAPA_EM_CAMPO_VIZINHO=1 leva pra capa; com 0 o motor só conta.
"""
import ast
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
import main  # noqa: E402
from models import ProjectData  # noqa: E402


@pytest.mark.parametrize("campo,vizinho", [
    (c, v) for c, vs in er._CAPA_EM_OUTRO_NOME.items() for v in vs])
def test_cada_nome_vizinho_e_lido(campo, vizinho):
    assert er.capa_em_campo_vizinho({vizinho: "Valor X"}) == {campo: (vizinho, "Valor X")}


@pytest.mark.parametrize("fora", ["client", "owner", "proprietario", "author", "autor",
                                  "cliente", "responsible", "sheet_title", "title"])
def test_quem_nao_e_capa_fica_de_fora(fora):
    assert er.capa_em_campo_vizinho({fora: "Fulano"}) == {}


def test_o_nome_certo_na_leitura_manda():
    pd = {"name": "Certo", "project_name": "Vizinho", "endereco": "Rua A, 1"}
    assert er.capa_em_campo_vizinho(pd) == {"address": ("endereco", "Rua A, 1")}


def test_o_que_a_capa_ja_tem_nao_e_trocado():
    destino = ProjectData(address="Rua Antiga, 9")
    pd = {"location": "Rua Nova, 2", "arquiteto": "Arq. B"}
    assert er.capa_em_campo_vizinho(pd, destino) == {"architect": ("arquiteto", "Arq. B")}


def test_ordem_da_lista_decide_entre_dois_vizinhos():
    pd = {"project": "Segundo", "project_name": "Primeiro"}
    assert er.capa_em_campo_vizinho(pd)["name"] == ("project_name", "Primeiro")


@pytest.mark.parametrize("vazio", ["", "   ", "Não indicado na prancha", "não informado",
                                   "Nao identificado", "N/A", "NA", "null", "None",
                                   "desconhecido", "-", "—"])
def test_valor_que_diz_que_nao_tem_nao_entra(vazio):
    assert er.capa_em_campo_vizinho({"arquiteto": vazio}) == {}


@pytest.mark.parametrize("nome", ["Natureza Arquitetura", "Nanquim Arquitetos",
                                  "Desconhecido Arquitetura Ltda", "- Arq. Exemplo -x",
                                  "Não Me Toque Arquitetura"])
def test_nome_que_so_comeca_parecido_com_vazio_entra(nome):
    assert er.capa_em_campo_vizinho({"arquiteto": nome}) == {"architect": ("arquiteto", nome)}


def test_nome_certo_em_branco_nao_barra_o_vizinho():
    assert er.capa_em_campo_vizinho({"name": "  ", "project_name": "Casa"}) == {
        "name": ("project_name", "Casa")}


def test_lista_de_arquitetos_vira_texto_e_o_que_nao_e_texto_sai():
    assert er.capa_em_campo_vizinho({"architects": ["Arq. A", " Arq. B ", 3]}) == {
        "architect": ("architects", "Arq. A, Arq. B")}
    assert er.capa_em_campo_vizinho({"location": {"cidade": "X"}, "local": 12}) == {}


def test_espacos_juntados_e_teto_de_240():
    achado = er.capa_em_campo_vizinho({"endereco": "Rua  A,\n 1 " + "x" * 300})
    assert achado["address"][1].startswith("Rua A, 1 x") and len(achado["address"][1]) == 240


def test_leitura_que_nao_e_dict():
    assert er.capa_em_campo_vizinho(None) == {} and er.capa_em_campo_vizinho([1]) == {}


def _prepara(monkeypatch, valor):
    logs = []
    monkeypatch.setattr(main, "_chave_do_job", lambda j, n, p="0": valor if n == "CAPA_EM_CAMPO_VIZINHO" else "x")
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))
    main._CAPA_VIZINHA_CONTADA.clear()
    return logs


def test_com_a_chave_em_0_a_capa_nao_muda_e_conta_uma_vez(monkeypatch):
    logs = _prepara(monkeypatch, "0")
    destino = ProjectData()
    for _ in range(3):
        main._colhe_capa_em_campo_vizinho("j", destino, {"endereco": "Rua A, 1"})
    assert destino.address == ""
    assert logs == [("motor:capa-em-campo-vizinho", "campo=address lido=endereco liga=0", "j")]


def test_com_a_chave_em_1_a_capa_ganha_o_valor(monkeypatch):
    logs = _prepara(monkeypatch, "1")
    destino = ProjectData()
    main._colhe_capa_em_campo_vizinho("j", destino, {"project_name": "Casa", "arquiteto": "Arq. C"})
    assert (destino.name, destino.architect) == ("Casa", "Arq. C")
    assert sorted(l[1] for l in logs) == ["campo=architect lido=arquiteto liga=1",
                                          "campo=name lido=project_name liga=1"]
    main._colhe_capa_em_campo_vizinho("j", destino, {"project_name": "Outra"})
    assert destino.name == "Casa"


def test_leitura_sem_nada_nao_registra(monkeypatch):
    logs = _prepara(monkeypatch, "1")
    main._colhe_capa_em_campo_vizinho("j", ProjectData(), {"name": "Ok"})
    assert logs == []


def test_falha_vira_registro_e_nao_derruba(monkeypatch):
    logs = _prepara(monkeypatch, "1")
    monkeypatch.setattr(er, "capa_em_campo_vizinho", lambda *a: 1 / 0)
    main._colhe_capa_em_campo_vizinho("j", ProjectData(), {"endereco": "x"})
    assert logs[0][0] == "motor:capa-em-campo-vizinho" and logs[0][1].startswith("FALHOU")


def test_chave_avaliavel_etapa_de_diagnostico_e_nasce_desligada():
    assert "CAPA_EM_CAMPO_VIZINHO" in main._CHAVES_AVALIAVEIS
    assert "motor:capa-em-campo-vizinho" in main._STAGES_DIAGNOSTICO
    assert main._chave_do_job("job-sem-avaliacao", "CAPA_EM_CAMPO_VIZINHO") == "0"


def test_os_dois_lacos_colhem_logo_depois_da_mescla():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    chamadas = [no for no in ast.walk(arvore) if isinstance(no, ast.Call)
                and getattr(no.func, "id", "") == "_colhe_capa_em_campo_vizinho"]
    assert len(chamadas) == 2
    for c in chamadas:
        assert [getattr(a, "id", None) for a in c.args] == ["job_id", "project_data", "pd"]
    mesclas = [no.lineno for no in ast.walk(arvore) if isinstance(no, ast.Call)
               and getattr(no.func, "id", "") == "_mescla_pd"]
    assert sorted(c.lineno for c in chamadas) > sorted(mesclas)
    assert all(0 < c - m < 6 for c, m in zip(sorted(x.lineno for x in chamadas), sorted(mesclas)))
