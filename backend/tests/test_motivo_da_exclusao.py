# -*- coding: utf-8 -*-
"""A exclusao do cliente passa a dizer POR QUE.

🩸 15/11/2026. Em 90 dias, 1.269 exclusoes de cliente e nenhuma servia de
gabarito: "a leitura inventou", "existe mas nao entra no meu orcamento" e "esta
repetido" chegavam como a mesma linha. A tela pergunta no mesmo clique que ja
confirmava a exclusao, e o codigo vai em `edits['_motivo']`.

O que este arquivo sustenta:
  - motivo conhecido entra na linha da exclusao; desconhecido ou vazio NAO
    entra e NAO muda mais nada (a exclusao nunca e barrada por causa dele);
  - motivo so existe na exclusao: aprovar e editar ignoram;
  - nao vai em `comment` (texto ali e recado de gente e toca a campainha);
  - os codigos da tela sao os mesmos do servidor.
"""
import os
import re
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main                                                    # noqa: E402

_ID = "11111111-2222-3333-4444-555555555555"
_ANTES = {"description": "Item generico", "unit": "un", "quantity": 3}


def _linha(action, motivo="", edits=None):
    return main.monta_linha_de_revisao("job-x", _ID, action, edits, dict(_ANTES),
                                       "", "alguem", motivo=motivo)


@pytest.mark.parametrize("motivo", sorted(main.MOTIVOS_DA_EXCLUSAO))
def test_motivo_conhecido_entra_na_exclusao(motivo):
    linha = _linha("reject", motivo)
    assert linha["edits"]["_motivo"] == motivo
    # o que a exclusao ja guardava continua la
    assert linha["edits"]["_item_id"] == _ID and linha["edits"]["_antes"] == _ANTES
    assert linha["item_id"] is None


def test_motivo_e_normalizado_antes_de_comparar():
    assert _linha("reject", "  Repetido ")["edits"]["_motivo"] == "repetido"


@pytest.mark.parametrize("motivo", ["", None, "qualquer coisa", "<b>x</b>", "nao_existe; drop"])
def test_motivo_ausente_ou_desconhecido_nao_entra_e_nao_muda_o_resto(motivo):
    com = _linha("reject", motivo)
    sem = main.monta_linha_de_revisao("job-x", _ID, "reject", None, dict(_ANTES), "", "alguem")
    assert "_motivo" not in com["edits"]
    assert com == sem, "motivo invalido tem que deixar a linha IGUAL a de antes"


@pytest.mark.parametrize("action", ["approve", "edit"])
def test_so_a_exclusao_guarda_motivo(action):
    linha = _linha(action, "repetido", edits={"quantity": 5})
    assert "_motivo" not in (linha["edits"] or {})


def test_o_motivo_nao_vai_pro_campo_de_recado():
    linha = _linha("reject", "fora_do_escopo")
    assert linha["comment"] == "", "texto em `comment` e recado de gente e toca a campainha"
    assert main.recado_digitado(linha["comment"]) == ""


def test_o_payload_da_rota_aceita_o_motivo_e_ele_e_opcional():
    assert main.ReviewPayload(action="reject", motivo="repetido").motivo == "repetido"
    assert (main.ReviewPayload(action="reject").motivo or "") == ""


def test_os_codigos_da_tela_sao_os_do_servidor():
    """A tela manda o codigo; o servidor so grava o que conhece. Se os dois se
    separam, a exclusao continua funcionando e o motivo some CALADO."""
    html = open(os.path.join(os.path.dirname(_BACKEND), "revisao.html"), encoding="utf-8").read()
    bloco = re.search(r"const MOTIVOS_DA_EXCLUSAO = \[(.*?)\];", html, re.S)
    assert bloco, "a lista de motivos saiu da tela de revisao"
    da_tela = set(re.findall(r"\['([a-z_]+)'\s*,", bloco.group(1)))
    assert da_tela == set(main.MOTIVOS_DA_EXCLUSAO)


def test_as_duas_exclusoes_da_tela_mandam_o_motivo():
    """A de um item e a da secao inteira: as duas passam pela pergunta."""
    html = open(os.path.join(os.path.dirname(_BACKEND), "revisao.html"), encoding="utf-8").read()
    assert html.count("await perguntaMotivoDaExclusao(") == 2
    assert "motivo: _motivo }" in html and "motivo: _motivoDoLote }" in html
