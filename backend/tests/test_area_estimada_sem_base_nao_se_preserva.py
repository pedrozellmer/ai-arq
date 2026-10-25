# -*- coding: utf-8 -*-
""""Área estimada" sem nenhuma base medida citada não é preservada.

🩸 25/10/2026 — avaliação ev4ed8f6 (AREA_A_OLHO_NAO_PRESERVA ligada): dos chutes
de um projeto só-PDF passaram "Porcelanato … 120 m² — área estimada; confirmar
delimitação" e "… 80 m² — Área estimada para ambientes com este revestimento".
A régua irmã pede visual/proporcional/a olho; aqui a leitura escreveu só "área
estimada".

📏 120 dias (preservadas pelo "cabe na geometria", clientes): 118 linhas com
"área estimada" fora da régua irmã. Metade cita a BASE medida (fica); a outra
metade não cita nenhuma: 68 linhas em 14 projetos, 1.732 m².

🔑 AREA_ESTIMADA_SEM_BASE_NAO_PRESERVA=1 liga (Render ou avaliação). 🛑 Nasce em 0.
Roda a `_apply_area_honesty` REAL pela fatia de `test_area_medida_do_pdf_nao_e_apagada`.
🪤 Frases reescritas sem nome de cliente (o repositório é público).
"""
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

from engine_rules import confessa_area_estimada_sem_base  # noqa: E402
import test_area_medida_do_pdf_nao_e_apagada as _base  # noqa: E402

_CHAVE = "AREA_ESTIMADA_SEM_BASE_NAO_PRESERVA"
#: as duas formas que `_nota_cabe_na_geometria` escreve (main.py) — ambas têm
#: palavra de base ("medidos", "cota"); por isso a régua corta antes delas
_MARCA = ("Quantidade atribuída pela IA a esta linha — não conferimos item a item "
          "(a escala desta prancha foi conferida por cota). Única checagem, na "
          "geometria do PDF: não passa de 30% acima da área dos ambientes medidos "
          "na Prancha 2 (412.00 m²). Confira antes de orçar.")
_MARCA_GERAL = ("Quantidade atribuída pela IA a esta linha — não conferimos item a item "
                "(as pranchas em que medimos ambientes têm escala conferida por cota). "
                "Única checagem, na geometria do PDF: não passa de 30% acima da área "
                "dos ambientes que medimos nas pranchas. Confira antes de orçar.")

#: as formas reais (reescritas) que NÃO citam base nenhuma
_SEM_BASE = [
    "Área estimada",
    "Área estimada para a plateia do auditório (descontando palco e circulações).",
    "Área estimada para ambientes com indicação ②.",
    "Calçada identificada no carimbo. Área estimada — confirmar com planta de implantação.",
    "Área impermeável estimada pela leitura da planta de permeabilidade (região cinza).",
    "Piso concreto polido. Área estimada por analogia com câmaras adjacentes.",
    "Área estimada por simetria com o pavimento inferior.",
    # os dois que passaram na avaliação de 25/10
    "Cozinha fechada e living — área estimada; confirmar delimitação por ambiente na legenda.",
    "Área estimada para ambientes com este revestimento identificados na legenda.",
]

#: o que fica: conta sobre medição, ou nem é "área estimada"
_COM_BASE = [
    "Área de forro estimada igual à área de piso medida (61,5 m²).",
    "Área estimada com base nos ambientes medidos geometricamente (117,8 m² totais).",
    "Área estimada a partir das cotas lidas na prancha: 22,50 m × 14,71 m = 330,98 m².",
    "Área estimada a partir das medições vetoriais fornecidas (20 ambientes, 115,2 m²).",
    "Área conforme rótulo da planta: 12,50 m².",
    "Não é área estimada: soma dos rótulos dos ambientes.",
    "Piso do salão — não é área estimada, vem da planta de layout.",   # negada, sem palavra de base
    _MARCA,     # a frase da própria honestidade não é confissão da leitura
    "",
    None,
]


@pytest.mark.parametrize("obs", _SEM_BASE)
def test_area_estimada_sem_base_e_reconhecida(obs):
    assert confessa_area_estimada_sem_base(obs), obs


@pytest.mark.parametrize("obs", _COM_BASE)
def test_CONTROLE_com_base_ou_sem_confissao_fica(obs):
    assert not confessa_area_estimada_sem_base(obs), obs


@pytest.mark.parametrize("marca", [_MARCA, _MARCA_GERAL])
def test_a_marca_da_honestidade_NAO_vira_base(marca):
    """🪤 A frase que a honestidade escreve tem "medidos" e "cota": lida junto,
    toda linha pareceria ter base. Medido 25/10 — sem cortar, 0 de 118."""
    obs = "Área estimada para os ambientes secos. | " + marca
    assert confessa_area_estimada_sem_base(obs)


def _caso(obs, q=120.0):
    piso = _base._Item("Piso em porcelanato 120×120 cm — legenda 3", "m²", q, obs)
    h = _base._fatia()["_apply_area_honesty"]
    h([piso], total_area=0, total_area_source="", pe_direito=0, pdfvec_m2=667.0)
    return piso, h


def test_CONTROLE_desligada_o_chute_segue_preservado(monkeypatch):
    monkeypatch.delenv(_CHAVE, raising=False)
    piso, h = _caso(_SEM_BASE[7])
    assert _base._valor(piso) == 120.0, "a chave desligada mudou número"
    assert getattr(h, "ultimo_sem_base", None) == 0


def test_ligada_o_chute_sem_base_nao_e_preservado(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    piso, h = _caso(_SEM_BASE[7])
    assert _base._valor(piso) == 0, "área estimada sem base seguiu com número"
    assert getattr(h, "ultimo_sem_base", None) == 1


def test_CONTROLE_ligada_a_conta_sobre_medicao_segue_preservada(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    piso, h = _caso(_COM_BASE[1])
    assert _base._valor(piso) == 120.0
    assert getattr(h, "ultimo_sem_base", None) == 0


#: 🩸 25/10 (ev3c2a63) — a frase que o PRÓPRIO prompt manda a IA escrever, e que
#: o ramo apaga logo depois (`_limpa_afirmacao_de_medida`): não é base
_FRASE_DA_IA = "Medido do desenho com escala 1:1000 lida do carimbo."


@pytest.mark.parametrize("obs", [
    "Tag ⑩ listada na legenda; ambiente não identificado. Área estimada. " + _FRASE_DA_IA,
    "Área estimada para a sala de cinema. | Área NÃO medida — informe a área no upload.",
])
def test_ligada_a_frase_que_o_ramo_apaga_NAO_vira_base(monkeypatch, obs):
    monkeypatch.setenv(_CHAVE, "1")
    piso, h = _caso(obs)
    assert _base._valor(piso) == 0, "a frase apagada logo depois contou como base"
    assert getattr(h, "ultimo_sem_base", None) == 1


def test_CONTROLE_ligada_base_de_verdade_junto_da_frase_da_ia_fica(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    piso, h = _caso("Área estimada a partir das cotas lidas na prancha. " + _FRASE_DA_IA)
    assert _base._valor(piso) == 120.0
    assert getattr(h, "ultimo_sem_base", None) == 0


def test_a_avaliacao_liga_so_para_ela(monkeypatch):
    import main
    monkeypatch.delenv(_CHAVE, raising=False)
    monkeypatch.setitem(main._CHAVES_DA_AVALIACAO, "evsemb01", {_CHAVE: "1"})

    def _roda(job):
        piso = _base._Item("Piso em porcelanato 120×120 cm — legenda 3", "m²", 120.0, _SEM_BASE[8])
        main._apply_area_honesty([piso], total_area=0, total_area_source="",
                                 pe_direito=0, pdfvec_m2=667.0, job_id=job)
        return _base._valor(piso)

    assert _roda("evsemb01") == 0
    assert _roda("abc12345") == 120.0


def test_a_chave_e_avaliavel_e_lida_pelo_job():
    src = io.open(os.path.join(_base._BACKEND, "main.py"), encoding="utf-8").read()
    assert '_chave_do_job(job_id, "%s")' % _CHAVE in src
    assert '"%s"' % _CHAVE in src[src.index("_CHAVES_AVALIAVEIS = frozenset"):][:4000]
    assert "sem_base={getattr(_apply_area_honesty, 'ultimo_sem_base', 0)}" in src
