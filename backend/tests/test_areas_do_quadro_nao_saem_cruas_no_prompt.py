# -*- coding: utf-8 -*-
"""As listas `areas_do_quadro_texto` e `areas_do_quadro_rotulos` não vão CRUAS pro prompt.

🩸 12/10/2026 — lendo o prompt de uma escola (planta em duas cópias): a seção
METADADOS trazia "areas_do_quadro_texto: [49.0, 63.54, 47.54, 128.0, …]" — 113
números sem nome — e "areas_do_quadro_rotulos: ['', '', '', …]" — 113 rótulos
vazios. São registro de máquina: o main usa as duas (o consenso da área total e a
régua do recorte) e continua usando. Pra IA é número com cara de resposta.
📏 No acervo (73 prompts conferidos): 16 arquivos, 1.454 números, até 436 num só
(7,9 % do prompt).

A chave AREAS_DO_QUADRO_FORA_DO_PROMPT é lida no `extract_dxf`, que deixa uma
MARCA no registro (`metadados_fora_do_prompt`); o `to_structured_prompt` só
obedece a marca — ele é refeito no servidor, onde a chave de uma avaliação não
vale.

Todo caso passa pelo `extract_dxf` (um DXF sintético de verdade).
🪤 Nomes e layers FICTÍCIOS (repositório público, regra nº6).
"""
import io
import os
import re
import sys
from collections import Counter

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import dwg_extractor as dx  # noqa: E402

CHAVE = "AREAS_DO_QUADRO_FORA_DO_PROMPT"
MARCA = "metadados_fora_do_prompt"
AS_DUAS = ["areas_do_quadro_rotulos", "areas_do_quadro_texto"]


def _planta(tmp_path, com_area=True):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 6), (0, 6)], close=True, dxfattribs={"layer": "ARQ-PAREDE"})
    msp.add_text("SALA", dxfattribs={"height": 0.2, "layer": "ARQ-TEXTO", "insert": (1, 5)})
    msp.add_text("COZINHA", dxfattribs={"height": 0.2, "layer": "ARQ-TEXTO", "insert": (6, 5)})
    if com_area:
        msp.add_text("A=12,50m²", dxfattribs={"height": 0.2, "layer": "ARQ-TEXTO", "insert": (1, 4.5)})
        msp.add_text("A=8,25m²", dxfattribs={"height": 0.2, "layer": "ARQ-TEXTO", "insert": (6, 4.5)})
        msp.add_text("ÁREA TOTAL = 60,00 m²", dxfattribs={"height": 0.2, "layer": "ARQ-TEXTO", "insert": (1, 1)})
    p = str(tmp_path / "planta.dxf")
    doc.saveas(p)
    return p


def _linhas_das_listas(prompt):
    return [l for l in prompt.splitlines() if l.strip().startswith(("areas_do_quadro_texto:", "areas_do_quadro_rotulos:"))]


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.delenv(CHAVE, raising=False)


def test_as_duas_listas_ficam_no_registro_e_fora_do_prompt(tmp_path):
    ex = dx.extract_dxf(_planta(tmp_path))
    assert ex.metadata["areas_do_quadro_texto"] == [12.5, 8.25, 60.0]
    assert ex.metadata["areas_do_quadro_rotulos"] == ["", "", "total"]        # o main continua lendo daqui
    assert ex.metadata[MARCA] == AS_DUAS
    p = ex.to_structured_prompt()
    assert _linhas_das_listas(p) == []
    assert "areas_do_quadro" not in p and MARCA not in p                      # nem a marca vai crua
    assert "METADADOS DO ARQUIVO:" in p and "A=12,50m²" in p                 # a seção e os textos continuam


def test_CONTROLE_com_a_chave_em_zero_as_listas_voltam_ao_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv(CHAVE, "0")
    ex = dx.extract_dxf(_planta(tmp_path))
    assert MARCA not in ex.metadata
    assert ex.metadata["areas_do_quadro_texto"] == [12.5, 8.25, 60.0]
    assert _linhas_das_listas(ex.to_structured_prompt()) == [
        "  areas_do_quadro_texto: [12.5, 8.25, 60.0]", "  areas_do_quadro_rotulos: ['', '', 'total']"]


def test_o_prompt_e_o_mesmo_menos_as_duas_linhas(tmp_path, monkeypatch):
    ligado = dx.extract_dxf(_planta(tmp_path)).to_structured_prompt().splitlines()
    monkeypatch.setenv(CHAVE, "0")
    desligado = dx.extract_dxf(_planta(tmp_path)).to_structured_prompt().splitlines()
    a, b = Counter(desligado), Counter(ligado)
    assert sorted((a - b).elements()) == sorted(_linhas_das_listas("\n".join(desligado))) and len(list((a - b).elements())) == 2
    assert not (b - a), "nada novo entra no prompt"
    # a ordem do resto não muda
    assert [l for l in desligado if l not in set((a - b).elements())] == ligado


def test_o_registro_e_o_mesmo_com_a_chave_ligada_ou_nao(tmp_path, monkeypatch):
    """Só a marca muda: nenhuma outra chave do registro some, aparece ou troca de valor."""
    com = dx.extract_dxf(_planta(tmp_path)).metadata
    monkeypatch.setenv(CHAVE, "0")
    sem = dx.extract_dxf(_planta(tmp_path)).metadata
    assert set(com) - set(sem) == {MARCA} and set(sem) <= set(com)
    assert all(com[k] == sem[k] for k in sem)


def test_quem_decide_e_a_extracao_nao_o_prompt(tmp_path, monkeypatch):
    """O prompt é refeito no servidor, com o ambiente DELE: a marca que o filho
    da avaliação deixou no registro é que vale, pros dois lados."""
    ex_com = dx.extract_dxf(_planta(tmp_path))
    monkeypatch.setenv(CHAVE, "0")
    assert _linhas_das_listas(ex_com.to_structured_prompt()) == []            # extraído ligado, prompt com a chave em 0
    ex_sem = dx.extract_dxf(_planta(tmp_path))
    monkeypatch.setenv(CHAVE, "1")
    assert len(_linhas_das_listas(ex_sem.to_structured_prompt())) == 2        # extraído desligado, prompt com a chave em 1


def test_a_marca_so_tira_o_que_ela_nomeia(tmp_path):
    ex = dx.extract_dxf(_planta(tmp_path))
    ex.metadata["outra_chave_qualquer"] = "fica"
    ex.metadata[MARCA] = ["areas_do_quadro_texto"]
    p = ex.to_structured_prompt()
    assert [l.strip().split(":")[0] for l in _linhas_das_listas(p)] == ["areas_do_quadro_rotulos"]
    assert "  outra_chave_qualquer: fica" in p


@pytest.mark.parametrize("torta", ["areas_do_quadro_texto", 7, {"areas_do_quadro_texto": 1}, None, ""])
def test_marca_torta_nao_esconde_nada_nem_derruba_o_prompt(tmp_path, torta):
    """A marca é uma LISTA de nomes. Qualquer outra coisa (o registro vem de um
    subprocesso) é ignorada: o prompt sai, com as duas linhas."""
    ex = dx.extract_dxf(_planta(tmp_path))
    ex.metadata[MARCA] = torta
    p = ex.to_structured_prompt()
    assert len(_linhas_das_listas(p)) == 2 and MARCA not in p


def test_sem_area_escrita_nao_ha_lista_nem_marca(tmp_path):
    ex = dx.extract_dxf(_planta(tmp_path, com_area=False))
    assert "areas_do_quadro_texto" not in ex.metadata and MARCA not in ex.metadata
    assert "areas_do_quadro" not in ex.to_structured_prompt()


def test_a_chave_e_lida_no_extrator_e_e_avaliavel():
    """Lida no `extract_dxf` (não no prompt) e aceita pela rota de avaliação —
    senão a medida com `?chaves=` seria avaliação de nada."""
    fonte = io.open(os.path.join(_BACKEND, "dwg_extractor.py"), encoding="utf-8").read()
    assert fonte.count('os.environ.get("%s"' % CHAVE) == 1
    corpo = fonte[fonte.index("    def to_structured_prompt(self)"):fonte.index("\n    def ", fonte.index("    def to_structured_prompt(self)") + 10)]
    assert "os.environ" not in corpo or CHAVE not in corpo, "a chave não pode ser lida no prompt"
    main = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    bloco = re.search(r"_CHAVES_AVALIAVEIS = frozenset\(\{(.*?)\}\)", main, re.S).group(1)
    assert '"%s"' % CHAVE in bloco
