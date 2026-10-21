# -*- coding: utf-8 -*-
"""A área que a própria leitura diz ter estimado a olho não é preservada.

🩸 20/10/2026 — paginação de piso em 4 PDFs. A planilha saiu com 280, 180,
120 m² de porcelanato e carpete, e cada linha dizia "Área estimada
proporcionalmente" ou "Área estimada por leitura visual do polígono do
ambiente". O ramo "cabe na geometria" da honestidade de área preservou os
números: ele só confere se a quantidade não passa de 1,3× a área medida da
maior prancha — e uma prancha "mediu" 5.588 m² com escala 1:1000 tirada da
caixa de recorte. Regra dura nº1: nunca estimar.

📏 120 dias (projetos de cliente): 515 linhas preservadas por "cabe na
geometria"; 26 delas, em 6 projetos (618 m²), confessam o chute. Lidas uma a
uma, 25 confessam a ÁREA; a que sobra fala da COR do piso.

🔑 Com AREA_A_OLHO_NAO_PRESERVA=1 a linha que confessa sai do ramo e segue a
cadeia (zera, com a frase de sempre). 🛑 Nasce desligada: muda número.

Roda a `_apply_area_honesty` REAL pela fatia de `test_area_medida_do_pdf_nao_e_apagada`.
🪤 Frases de leitura reescritas sem nome de cliente (o repositório é público).
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

from engine_rules import confessa_area_a_olho  # noqa: E402
import test_area_medida_do_pdf_nao_e_apagada as _base  # noqa: E402

_CHAVE = "AREA_A_OLHO_NAO_PRESERVA"

#: as formas que a leitura escreveu de verdade nos 120 dias
_CONFISSOES = [
    "Tag 3 identificada na rouparia. Área estimada proporcionalmente para os ambientes marcados.",
    "Símbolo 1 na suíte. Área estimada por leitura visual do polígono do ambiente. Confirmar.",
    "Área estimada visualmente. Confirmar com quadro de áreas.",
    "Área estimada visualmente ~22 m² (planta cortada; confirmar).",
    "Zonas externas. Área estimada pela leitura visual das zonas externas delimitadas.",
    "Área estimada para estar/jantar integrado com base na composição visual da planta.",
    "Área estimada pela extensão visual dos boxes com desnível.",
    "Tag 1 nas suítes. Área estimada com base na leitura proporcional da planta.",
    "Estimativa visual da área de bloquete indicada na planta (acesso veicular).",
    "Sem área na legenda. Estimativa baseada na leitura visual da região indicada na planta.",
]

#: o que NÃO é confissão de área a olho
_INOCENTES = [
    # a única falsa do levantamento: fala da COR, e a frase seguinte não confessa
    "Piso de tom bege identificado visualmente em todos os ambientes secos. "
    "Área estimada para ambientes secos.",
    "Área conforme rótulo da planta: 12,50 m².",
    "Área medida na geometria do PDF (escala conferida por cota).",
    "Área não é estimativa visual: soma dos rótulos dos ambientes.",
    # casa a régua E é negada: só a trava da negação a separa
    "Não é área estimada visualmente: soma dos rótulos dos ambientes.",
    "Padrão do piso estimado visualmente; área do quadro de acabamentos.",
    "",
    None,
]


@pytest.mark.parametrize("obs", _CONFISSOES)
def test_a_confissao_e_reconhecida(obs):
    assert confessa_area_a_olho(obs), obs


@pytest.mark.parametrize("obs", _INOCENTES)
def test_CONTROLE_o_que_nao_e_confissao(obs):
    assert not confessa_area_a_olho(obs), obs


def _caso(obs, q=120.0):
    piso = _base._Item("Piso em porcelanato 120×120 cm — legenda 3", "m²", q, obs)
    # o número CABE na geometria (área medida de 667 m² na prancha): sem a régua
    # nova, este é exatamente o item que o ramo "cabe na geometria" preserva
    h = _base._fatia()["_apply_area_honesty"]
    h([piso], total_area=0, total_area_source="", pe_direito=0, pdfvec_m2=667.0)
    return piso, h


def test_CONTROLE_desligada_o_chute_confessado_segue_preservado(monkeypatch):
    """Chave em 0 (o padrão): nada muda — é o comportamento de hoje."""
    monkeypatch.delenv(_CHAVE, raising=False)
    piso, h = _caso(_CONFISSOES[0])
    assert _base._valor(piso) == 120.0, "a chave desligada mudou número"
    assert getattr(h, "ultimo_a_olho", None) == 0


def test_ligada_o_chute_confessado_nao_e_preservado(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    piso, h = _caso(_CONFISSOES[1])
    assert _base._valor(piso) == 0, (
        "a área que a leitura diz ter estimado a olho seguiu com número: %r"
        % piso.observations)
    assert getattr(h, "ultimo_a_olho", None) == 1


def test_CONTROLE_ligada_o_numero_sem_confissao_segue_preservado(monkeypatch):
    """A régua é a confissão, não o teto: sem ela, o ramo de sempre vale."""
    monkeypatch.setenv(_CHAVE, "1")
    piso, h = _caso("Piso dos ambientes secos conforme legenda 3.")
    assert _base._valor(piso) == 120.0
    assert getattr(h, "ultimo_a_olho", None) == 0


def test_a_avaliacao_liga_so_para_ela(monkeypatch):
    """O caminho de PRODUÇÃO (main importado, com `_chave_do_job`): a avaliação
    que pediu a chave liga a régua só pra ela; o servidor segue desligado."""
    import main
    monkeypatch.delenv(_CHAVE, raising=False)
    monkeypatch.setitem(main._CHAVES_DA_AVALIACAO, "evteste1", {_CHAVE: "1"})

    def _roda(job):
        piso = _base._Item("Piso em porcelanato 120×120 cm — legenda 3", "m²", 120.0,
                           _CONFISSOES[2])
        main._apply_area_honesty([piso], total_area=0, total_area_source="",
                                 pe_direito=0, pdfvec_m2=667.0, job_id=job)
        return _base._valor(piso)

    assert _roda("evteste1") == 0, "a avaliação pediu a chave e a régua não ligou"
    assert _roda("abc12345") == 120.0, "projeto de cliente ligou a régua com o servidor em 0"


def test_a_chave_e_avaliavel_e_lida_pelo_job():
    import io
    src = io.open(os.path.join(_base._BACKEND, "main.py"), encoding="utf-8").read()
    assert '_chave_do_job(job_id, "%s")' % _CHAVE in src
    assert '"%s"' % _CHAVE in src[src.index("_CHAVES_AVALIAVEIS = frozenset"):][:3000], (
        "a chave não entrou em _CHAVES_AVALIAVEIS: a avaliação não conseguiria ligá-la")
    assert "job_id=job_id," in src[src.index("_n_fill, _blanked = _apply_area_honesty("):][:400], (
        "o process_job deixou de passar o job à honestidade: a chave por avaliação não vale")
