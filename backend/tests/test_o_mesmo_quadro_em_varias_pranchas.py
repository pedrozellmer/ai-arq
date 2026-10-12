# -*- coding: utf-8 -*-
"""O MESMO quadro com quantidade em vários arquivos do job é listado UMA vez.

🩸 12/10/2026 — 1ª avaliação com a seção QUADROS COM QUANTIDADE num job de 14
arquivos: a lista de material da entrada de energia (16 linhas) estava desenhada
em três pranchas de elétrica e saiu três vezes na planilha.

O registro de cada quadro traz a assinatura do conteúdo. O 1º arquivo que o
mostra fica com ele; nos seguintes a seção diz "o MESMO quadro já listado na
prancha X" e não repete as linhas.
"""
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import main  # noqa: E402
from engine_rules import quantidades_dos_quadros  # noqa: E402
from test_quadro_com_quantidade import CAB, LARG, LINHAS, Desenho, tabela  # noqa: E402

OUTRAS = [["L1", "Luminária de embutir", "37", "LED"],
          ["L2", "Refletor", "22", "LED"]]


@pytest.fixture(autouse=True)
def _chaves(monkeypatch):
    monkeypatch.delenv("QUADRO_COM_QUANTIDADE", raising=False)
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda etapa, msg, *a, **k: logs.append((etapa, msg)))
    return logs


def _extrai(tmp_path, nome, *quadros):
    """Um arquivo com os quadros dados, um embaixo do outro."""
    d = Desenho()
    for k, linhas in enumerate(quadros):
        tabela(d, 0, 100 - 40 * k, LARG, CAB, linhas)
    pasta = tmp_path / nome
    pasta.mkdir()
    return dx.extract_dxf(d.grava(pasta))


def _quadros(ex):
    return ex.metadata["quadros_com_quantidade"]["quadros"]


def test_o_segundo_arquivo_nao_repete_as_linhas_do_quadro(tmp_path, _chaves):
    vistos = {}
    a, b = _extrai(tmp_path, "a", LINHAS), _extrai(tmp_path, "b", LINHAS)
    ta, tb = a.to_structured_prompt(), b.to_structured_prompt()
    assert "QTD 12" in ta and "QTD 12" in tb, "os dois arquivos trazem o quadro"
    assert main._quadros_entre_pranchas(a, ta, vistos, "planta-a.dxf", "job") == ta, "o 1º fica como veio"
    novo = main._quadros_entre_pranchas(b, tb, vistos, "planta-b.dxf", "job")
    assert novo != tb
    assert "o MESMO quadro já listado na prancha «planta-a.dxf» deste projeto" in novo
    # as LINHAS do quadro não se repetem (as células seguem na lista de textos, como
    # sempre estiveram — o que some é a linha montada, com a quantidade)
    assert "QTD 12" not in novo and "←  COD: P1" not in novo and "←  COD: P1" in tb
    assert "QUADRO 1 — colunas: COD | TIPO | QTD | MATERIAL" in novo, "o quadro continua anunciado"
    assert _quadros(b)[0]["de_outra_prancha"] == "planta-a.dxf"
    assert "de_outra_prancha" not in _quadros(a)[0]
    assert [e for e, m in _chaves if e == "motor:quadro-entre-pranchas" and "planta-b.dxf: 1 quadro" in m]


def test_o_terceiro_arquivo_aponta_pro_primeiro(tmp_path):
    vistos = {}
    for nome in ("a", "b"):
        ex = _extrai(tmp_path, nome, LINHAS)
        main._quadros_entre_pranchas(ex, ex.to_structured_prompt(), vistos, nome + ".dxf")
    c = _extrai(tmp_path, "c", LINHAS)
    novo = main._quadros_entre_pranchas(c, c.to_structured_prompt(), vistos, "c.dxf")
    assert "prancha «a.dxf»" in novo and "«b.dxf»" not in novo


def test_CONTROLE_quadro_de_outro_conteudo_fica_inteiro(tmp_path, _chaves):
    vistos = {}
    a, b = _extrai(tmp_path, "a", LINHAS), _extrai(tmp_path, "b", OUTRAS)
    main._quadros_entre_pranchas(a, a.to_structured_prompt(), vistos, "a.dxf")
    tb = b.to_structured_prompt()
    assert main._quadros_entre_pranchas(b, tb, vistos, "b.dxf") == tb
    assert "QTD 37" in tb and "de_outra_prancha" not in _quadros(b)[0]
    assert not _chaves, "nada a registrar"


def test_so_o_quadro_repetido_sai_o_outro_do_mesmo_arquivo_fica(tmp_path):
    vistos = {}
    a = _extrai(tmp_path, "a", LINHAS)
    main._quadros_entre_pranchas(a, a.to_structured_prompt(), vistos, "a.dxf")
    b = _extrai(tmp_path, "b", OUTRAS, LINHAS)          # o de luminárias é novo; o de esquadrias, repetido
    novo = main._quadros_entre_pranchas(b, b.to_structured_prompt(), vistos, "b.dxf")
    assert "QTD 37" in novo and "Refletor" in novo
    assert "QTD 12" not in novo and novo.count("o MESMO quadro já listado na prancha «a.dxf»") == 1


def test_CONTROLE_a_copia_dentro_do_mesmo_arquivo_e_outra_regua(tmp_path):
    """Dois quadros iguais no MESMO arquivo: `copia_de` cuida; o servidor não marca nada."""
    vistos = {}
    a = _extrai(tmp_path, "a", LINHAS, LINHAS)
    ta = a.to_structured_prompt()
    assert main._quadros_entre_pranchas(a, ta, vistos, "a.dxf") == ta
    assert "desenhado de novo: conte UMA vez" in ta and "já listado na prancha" not in ta
    assert not any("de_outra_prancha" in q for q in _quadros(a))


def test_chamar_de_novo_na_mesma_prancha_nao_muda_nada(tmp_path):
    """A retomada lê a prancha de novo: quem já é dono do quadro continua dono."""
    vistos = {}
    a = _extrai(tmp_path, "a", LINHAS)
    ta = a.to_structured_prompt()
    assert main._quadros_entre_pranchas(a, ta, vistos, "a.dxf") == ta
    assert main._quadros_entre_pranchas(a, ta, vistos, "a.dxf") == ta
    assert "de_outra_prancha" not in _quadros(a)[0]


def test_a_quantidade_do_quadro_marcado_continua_valendo_pra_regua_do_selo(tmp_path):
    """Se a IA repetir a linha mesmo assim, o número ainda é "de quadro" neste arquivo."""
    vistos = {}
    a, b = _extrai(tmp_path, "a", LINHAS), _extrai(tmp_path, "b", LINHAS)
    main._quadros_entre_pranchas(a, a.to_structured_prompt(), vistos, "a.dxf")
    main._quadros_entre_pranchas(b, b.to_structured_prompt(), vistos, "b.dxf")
    assert quantidades_dos_quadros(b.metadata["quadros_com_quantidade"]) == [2.0, 5.0, 12.0]


@pytest.mark.parametrize("estranho", [None, {}, {"quadros_com_quantidade": None},
                                      {"quadros_com_quantidade": {"quadros": [{"linhas": []}]}}])
def test_CONTROLE_sem_registro_ou_registro_estranho_devolve_o_texto(estranho):
    class Ex:
        metadata = estranho

        def to_structured_prompt(self):
            return "REFEITO"                    # não era pra refazer o texto
    assert main._quadros_entre_pranchas(Ex(), "texto", {}, "a.dxf") == "texto"


def test_roda_depois_das_etiquetas_e_antes_do_teto_do_texto():
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    etiq = fonte.index("extraction, structured_text, _etiquetas_da_planta, _dxf_nome, job_id)")
    quad = fonte.index("extraction, structured_text, _quadros_do_job, _dxf_nome, job_id)")
    teto = fonte.index("if len(structured_text) > 300_000:", etiq)
    assert etiq < quad < teto
    assert fonte.index("_quadros_do_job: dict = {}") < etiq
