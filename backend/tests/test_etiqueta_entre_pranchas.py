# -*- coding: utf-8 -*-
"""Etiqueta que a planta de OUTRA prancha do mesmo job já contou sai do ×N.

🩸 25/09/2026 — job `53f0483f` (subestação): "TH-90°" ×18 na planta (folha
2/4) e de novo ×12 e ×14 nas pranchas só de corte (3/4 e 4/4). O aviso "não
some com a planta de outra prancha" foi ignorado pela IA em duas releituras.
O motor lê um DXF por vez; agora o laço do job guarda o que as pranchas com
planta contaram e, na prancha só de corte, tira isso do ×N antes da IA ler.
🪤 Depende da ordem: corte lido ANTES da planta não é pego (controle abaixo).
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import main as M  # noqa: E402
import test_desenho_no_modelo as tdm  # noqa: E402


def _t(msp, texto, x, y):
    msp.add_text(texto, dxfattribs={"height": 0.1, "insert": (x, y), "layer": "ETIQUETA"})


def _planta(tmp_path):
    d = tmp_path / "planta"
    d.mkdir()
    p = tdm._folha(d, titulo_detalhe='%%UDETALHE "D"')
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()
    for x in (6, 7):
        _t(msp, "TH-90", x, 25)
    for x in (6, 7, 8, 9, 10):
        _t(msp, "1", x, 23)                  # número solto não é etiqueta de peça
    doc.saveas(p)
    return dx.extract_dxf(p)


def _so_corte(tmp_path):
    d = tmp_path / "corte"
    d.mkdir()
    p = tdm._folha(d, titulo_detalhe='%%UCORTE "A-A"', titulo_planta=None)
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()
    for x in (5, 6, 7):
        _t(msp, "TH-90", x, 11)
    for x in (5, 6):
        _t(msp, "NICHO", x, 9)
    doc.saveas(p)
    return dx.extract_dxf(p)


@pytest.fixture(autouse=True)
def _sem_log(monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    monkeypatch.setattr(M, "_log_error", lambda *a, **k: None)


def _linha(txt, comeco):
    return next((l.strip() for l in txt.splitlines() if l.strip().startswith(comeco)), "")


def test_quem_e_prancha_so_de_corte(tmp_path):
    assert dx.prancha_so_de_vista(_so_corte(tmp_path)) is True
    assert dx.prancha_so_de_vista(_planta(tmp_path)) is False


def test_CONTROLE_planta_com_corte_no_mesmo_arquivo_nao_e_so_corte(tmp_path):
    d = tmp_path / "mista"
    d.mkdir()
    ex = dx.extract_dxf(tdm._folha(d, titulo_detalhe='%%UCORTE "A-A"'))
    assert any(x.get("tipo") == "vista" for x in ex.folhas["desenhos_lista"])
    assert dx.prancha_so_de_vista(ex) is False


def test_a_planta_alimenta_e_o_corte_nao_conta_de_novo(tmp_path):
    acc = {}
    pl = _planta(tmp_path)
    t_pl = pl.to_structured_prompt()
    assert M._etiquetas_entre_pranchas(pl, t_pl, acc, "FOLHA-2", "") == t_pl
    assert "th-90" in acc and "1" not in acc, acc
    co = _so_corte(tmp_path)
    t_co = co.to_structured_prompt()
    assert _linha(t_co, "TH-90").endswith("×3"), "sem o job, o corte conta sozinho"
    novo = M._etiquetas_entre_pranchas(co, t_co, acc, "FOLHA-3", "")
    assert not _linha(novo, "TH-90").endswith("×3"), _linha(novo, "TH-90")
    assert "JÁ CONTADAS NA PLANTA da prancha FOLHA-2" in novo


def test_o_que_a_planta_nao_mostra_continua_contado(tmp_path):
    acc = {}
    pl = _planta(tmp_path)
    M._etiquetas_entre_pranchas(pl, pl.to_structured_prompt(), acc, "FOLHA-2", "")
    co = _so_corte(tmp_path)
    novo = M._etiquetas_entre_pranchas(co, co.to_structured_prompt(), acc, "FOLHA-3", "")
    assert _linha(novo, "NICHO").endswith("×2"), _linha(novo, "NICHO")


def test_CONTROLE_corte_lido_antes_da_planta_fica_como_era(tmp_path):
    """Limite conhecido: a ordem importa."""
    acc = {}
    co = _so_corte(tmp_path)
    t_co = co.to_structured_prompt()
    assert M._etiquetas_entre_pranchas(co, t_co, acc, "FOLHA-3", "") == t_co
    assert acc == {}, "prancha só de corte não alimenta"


def test_CONTROLE_etiqueta_diferente_nao_mexe(tmp_path):
    co = _so_corte(tmp_path)
    t_co = co.to_structured_prompt()
    acc = {"ch-90": ("CH-90", 6, "FOLHA-2")}
    assert M._etiquetas_entre_pranchas(co, t_co, acc, "FOLHA-3", "") == t_co


def test_falha_nunca_derruba():
    assert M._etiquetas_entre_pranchas(object(), "texto", {}, "X", "") == "texto"


def test_o_laco_do_job_chama_antes_do_teto_do_texto():
    """O passo tem que rodar no laço dos DXF, antes do teto de 300 mil e da IA."""
    src = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    i = src.index("structured_text = _etiquetas_entre_pranchas(")
    j = src.index("if len(structured_text) > 300_000:")
    k = src.index('dxf_prompt = f"""Analise os dados extraídos de um arquivo DXF')
    assert i < j < k
