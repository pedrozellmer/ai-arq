# -*- coding: utf-8 -*-
"""Catálogo de falhas: um tipo por problema, uma mensagem por tipo.

🩸 25/09/2026 — o e-mail de falha adivinhava o motivo farejando o texto da tela
e contradizia a tela em 8 de 17 situações reais (7× "PDF escaneado" pra quem
teve problema de servidor, de conversor ou mandou DWG). Voz do Pedro: problema
NOSSO → "não é o seu arquivo, já estamos resolvendo, você recebe reprocessado";
problema DO CLIENTE → o passo a passo. Nada interno aparece pro cliente.
Enquanto `falhas.LIGADO` for False, os modelos só aparecem na Central (em revisão).
"""
import html as _h
import os
import re
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACK = os.path.dirname(_AQUI)
sys.path.insert(0, _BACK)

import falhas  # noqa: E402
import main  # noqa: E402

_TIPOS = sorted(falhas.TIPOS)
_ARTES = os.path.join(os.path.dirname(_BACK), "assets", "email")


def _texto(tipo, projeto="Obra Exemplo", arquivo="Planta - Térreo.dwg"):
    s, html = main._build_email_de_falha(tipo, "Cliente Exemplo", projeto, arquivo, "job-1")
    # etiqueta de BLOCO vira espaço; a de linha (<b>) some — senão "<b>X</b>,"
    # viraria "X ," e a comparação com o texto da tela falharia por pontuação
    t = re.sub(r"(?i)<br\s*/?>|</?(p|div|li|ol|ul|tr|td|table)[^>]*>", " ", html)
    t = re.sub(r"<[^>]+>", "", t)
    return s, " ".join(_h.unescape(t).split())


def test_enquanto_o_pedro_nao_aprova_nada_liga():
    """Decisão do Pedro (25/09): os e-mails vão pra Central pra ele revisar
    ANTES de sair pra cliente. Ligar é mudar esta linha junto com o LIGADO."""
    assert falhas.LIGADO is False


@pytest.mark.parametrize("tipo", _TIPOS)
def test_todo_tipo_tem_o_que_precisa(tipo):
    t = falhas.TIPOS[tipo]
    assert t["quem"] in ("nosso", "cliente")
    for campo in ("rotulo", "o_que_houve", "aviso", "arte"):
        assert (t.get(campo) or "").strip(), (tipo, campo)
    if t["quem"] == "cliente":
        for campo in ("assunto", "titulo"):
            assert (t.get(campo) or "").strip(), (tipo, campo)
        assert t.get("passos"), f"{tipo}: problema do cliente sem passo a passo"
    assert os.path.exists(os.path.join(_ARTES, t["arte"])), f"{tipo}: arte {t['arte']} não existe"


@pytest.mark.parametrize("tipo", [t for t in _TIPOS if falhas.TIPOS[t]["quem"] == "nosso"])
def test_problema_NOSSO_promete_e_nao_manda_o_cliente_mexer(tipo):
    s, txt = _texto(tipo)
    assert "problema do nosso lado" in s.lower()
    assert "Não é o seu arquivo, e você não precisa fazer nada" in txt
    assert "você recebe o projeto reprocessado" in txt
    for proibido in ("precisamos de outro arquivo", "troque o arquivo", "reprocesse",
                     "reenvie", "pdf escaneado"):
        assert proibido not in txt.lower(), (tipo, proibido)


@pytest.mark.parametrize("tipo", [t for t in _TIPOS if falhas.TIPOS[t]["quem"] == "cliente"])
def test_problema_DO_CLIENTE_aponta_o_caminho(tipo):
    s, txt = _texto(tipo)
    assert "Como resolver" in txt
    for passo in falhas.TIPOS[tipo]["passos"]:
        assert falhas._sem_tags(passo) in txt, (tipo, passo[:40])
    assert "problema do nosso lado" not in s.lower()


@pytest.mark.parametrize("tipo", _TIPOS)
def test_nada_interno_chega_ao_cliente(tipo):
    """Pedro: 'crédito de IA esgotado é interno nosso'. Nem nome de ferramenta,
    nem erro técnico, nem 'caiu'."""
    s, txt = _texto(tipo)
    baixo = (s + " " + txt).lower()
    for w in falhas.PALAVRAS_INTERNAS:
        assert not re.search(r"\b" + re.escape(w) + r"\b", baixo), (tipo, w)


@pytest.mark.parametrize("tipo", [t for t in _TIPOS if not t.startswith("pdf-")])
def test_quem_nao_mandou_PDF_nao_le_PDF(tipo):
    """O defeito que abriu o caso: 'quase sempre é PDF escaneado' pra quem mandou DWG."""
    s, txt = _texto(tipo)
    assert "pdf" not in (s + " " + txt).lower(), tipo


def test_CONTROLE_o_tipo_de_PDF_fala_de_PDF():
    _, txt = _texto("pdf-escaneado", arquivo="Planta.pdf")
    assert "PDF" in txt


@pytest.mark.parametrize("tipo", _TIPOS)
def test_a_tela_conta_a_mesma_historia_do_email(tipo):
    tela = falhas.texto_da_tela(tipo, "Obra Exemplo", "Planta - Térreo.dwg")
    _, txt = _texto(tipo)
    o_que = falhas._sem_tags(falhas._preenche(falhas.TIPOS[tipo]["o_que_houve"],
                                              "Obra Exemplo", "Planta - Térreo.dwg"))
    assert o_que in tela and o_que in txt, tipo
    if falhas.TIPOS[tipo]["quem"] == "nosso":
        assert "você recebe o projeto reprocessado" in tela
    else:
        assert "Como resolver" in tela


def test_tipo_que_ninguem_previu_cai_no_desconhecido_honesto():
    s, txt = _texto("tipo-que-nao-existe")
    assert "problema do nosso lado" in s.lower() and "pdf" not in txt.lower()


@pytest.mark.parametrize("tipo", _TIPOS)
def test_todo_tipo_esta_na_Central_em_revisao(tipo):
    ficha = next((c for c in main._EMAIL_CATALOG if c["key"] == f"falha:{tipo}"), None)
    assert ficha and ficha["grupo"] == "falha", tipo
    assert "EM REVISÃO" in ficha["gatilho"]
    subj, html = main._render_email_by_type(f"falha:{tipo}")
    assert subj and len(html) > 1000


def test_a_Central_mostra_o_bloco_das_falhas():
    adm = open(os.path.join(os.path.dirname(_BACK), "admin.html"), encoding="utf-8").read()
    assert 'id="emails-falhas"' in adm
    assert "i.grupo === 'falha'" in adm and "i.grupo !== 'falha'" in adm
