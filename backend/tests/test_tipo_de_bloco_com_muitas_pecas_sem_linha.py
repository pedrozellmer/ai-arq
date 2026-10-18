# -*- coding: utf-8 -*-
"""Tipo de bloco com muitas peças que nenhuma linha da planilha cita: o motor avisa.

🩸 18/10/2026 — avaliação de um elétrico de galpão: nas duas rodadas com a base
contada uma vez, a IA não fez linha pra cadeiras e sofá de uma prancha, com os
blocos no texto que ela leu. Ninguém olhava se o que o desenho tem com muitas
peças chegou à planilha. SÓ AVISA (chave BLOCO_SEM_LINHA, padrão desligada); o
registro vai sempre pro log. Projeto de estrutura fica de fora.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
import main  # noqa: E402

CHAVE = "BLOCO_SEM_LINHA"


def test_o_caso_cadeira_e_sofa_sem_linha_aparecem():
    blocos = {"AB_móveis_cadeira fixa_planta": 40, "Sofá Três Lugares  planta": 12,
              "Armario Alto 80x45": 22}
    textos = ["Armário alto 80×45 — fornecimento (bloco 'Armario Alto 80x45') 22 INSERTs"]
    assert er.blocos_sem_linha(blocos, textos) == [
        ("AB_móveis_cadeira fixa_planta", 40), ("Sofá Três Lugares  planta", 12)]


@pytest.mark.parametrize("nome", [
    "Seta", "_1F+N+T", "Cond-Terra", "Cond-Neutro", "RET-FASE", "AB_anotação_chamada_vista",
    "View Reference", "Floor Plan", "SIMB_CORTE(4)", "AG_SMB_Paginação", "YOUCON-SMB-Norte",
    "PLANT HATCH2", "ARVORE_1", "11111", "CHAMADA DETALHE-NOVA", "P_70_15"])
def test_CONTROLE_anotacao_do_desenho_nao_e_acusada(nome):
    assert er.bloco_e_anotacao_pelo_nome(nome), nome
    assert er.blocos_sem_linha({nome: 50}, []) == []


@pytest.mark.parametrize("nome", [
    "Caixa de inspeção de terra", "COBOGO", "Mesa Refeitório", "Lum-Indust_V-Sodio-N",
    "Condulete_Embutido", "Cotovelo 90 PVC", "QDLF"])
def test_CONTROLE_peca_nao_e_anotacao(nome):
    assert not er.bloco_e_anotacao_pelo_nome(nome), nome


@pytest.mark.parametrize("pecas,acusa", [(4, False), (5, True)])
def test_o_minimo_de_pecas(pecas, acusa):
    assert bool(er.blocos_sem_linha({"Banco de madeira": pecas}, ["outra coisa"])) is acusa


def test_casa_sem_acento_e_com_pontuacao():
    """'COBOGO' no desenho e 'Cobogó' na linha são o mesmo; '_' e '-' viram espaço."""
    assert er.blocos_sem_linha({"COBOGO": 15}, ["Elemento vazado — Cobogó cerâmico 15 un"]) == []
    assert er.blocos_sem_linha({"Foto-Celula": 6}, ["Fotocélula — bloco 'Foto Celula'"]) == []


def test_CONTROLE_palavra_inteira_nao_casa_pedaco():
    """'mesa' dentro de 'mesanino' não cita o bloco."""
    assert er.blocos_sem_linha({"Mesa": 8}, ["Laje do mesanino"]) == [("Mesa", 8)]


def test_a_familia_do_revit_e_o_tipo():
    nome = "Rectangular Mullion - montante 40x40mm-5306176-FACH 01"
    assert er.familia_do_bloco_para_aviso(nome) == "Rectangular Mullion"
    assert er.familia_do_bloco_para_aviso("Sofá Le Corbusier  planta") == "Sofá Le Corbusier  planta"
    # " - " sem o número da peça do Revit não é família
    assert er.familia_do_bloco_para_aviso("Porta - madeira") == "Porta - madeira"


def test_o_aviso_diz_o_que_e_e_manda_conferir():
    av = er.aviso_de_blocos_sem_linha([("Cadeira fixa", 40), ("Sofá", 12)])
    assert "'Cadeira fixa' (40)" in av and "'Sofá' (12)" in av and "confira" in av, av
    assert er.aviso_de_blocos_sem_linha([]) == ""
    muitos = [("T%d" % i, 10) for i in range(11)]
    av_muitos = er.aviso_de_blocos_sem_linha(muitos)
    assert "e mais 3 tipo(s)" in av_muitos and "'T7'" in av_muitos and "'T8'" not in av_muitos


def test_a_chave_e_avaliavel_e_desligada_por_padrao(monkeypatch):
    assert CHAVE in main._CHAVES_AVALIAVEIS
    monkeypatch.delenv(CHAVE, raising=False)
    assert main._chave_do_job("abc12345", CHAVE) == "0"
    monkeypatch.setitem(main._CHAVES_DA_AVALIACAO, "ev123456", {CHAVE: "1"})
    assert main._chave_do_job("ev123456", CHAVE) == "1"
    # job de cliente nunca lê a chave de uma avaliação
    monkeypatch.setitem(main._CHAVES_DA_AVALIACAO, "abc12345", {CHAVE: "1"})
    assert main._chave_do_job("abc12345", CHAVE) == "0"


def test_o_process_job_avisa_so_com_a_chave_e_nunca_em_estrutura():
    with open(main.__file__, encoding="utf-8") as f:
        src = f.read()
    assert 'if _bl_av and not is_structural:' in src
    assert '_chave_do_job(job_id, "BLOCO_SEM_LINHA") == "1"' in src
    assert '"motor:bloco-sem-linha"' in src
