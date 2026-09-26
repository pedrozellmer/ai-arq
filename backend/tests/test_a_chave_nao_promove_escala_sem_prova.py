# -*- coding: utf-8 -*-
"""A chave do selo não sobe comprimento nem área de prancha com escala sem prova.

🩸 26/09/2026 — job 32a27efc (muro de arrimo, 7 DXF). Cada prancha é a folha
A1 inteira desenhada no MODELO, em mm de papel, com vistas em escalas
diferentes. O motor leu uma prancha em 0,001 (cabeçalho, sem prova) e seis em
0,1 por PLAUSIBILIDADE — que não é prova, e por isso a trava de procedência
rebaixa as linhas delas. Só que:

  1. o cofre da chave (`_indice_geom`, no `process_job`) guardava comprimento
     e área de TODA prancha, com ou sem ressalva de escala;
  2. a chave roda no fim, depois de todas as travas, e promovia a "✓ MEDIDO"
     a linha que citasse o layer com o número batendo — e bate, porque foi
     medido na mesma escala sem prova;
  3. a trava de escala divergente rebaixa a linha da prancha que discorda, e a
     chave, que roda depois dela, não sabia disso.

📏 No acervo: 13 das 28 promoções da chave (3 jobs) saíram de prancha com
ressalva de escala — todas por plausibilidade. Entre elas um tubo de gás de
1.088 m (0a999117), que o filhote remediu em 535 m.

🔑 A chave não sobe o que a procedência rebaixaria: a MESMA régua
(`caveat_atinge_unidade`) decide quem entra no cofre. Contagem continua
entrando — contar bloco não depende de escala.
"""
import os
import sys
import types

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import _executa  # noqa: E402
from engine_rules import (  # noqa: E402
    MARCA_ESCALA_DIVERGENTE,
    selo_com_prova_da_geometria as chave,
)

#: O que o `dwg_extractor` grava quando a régua da plausibilidade decide a
#: escala (ver `_dim_status == "corrigida_plausibilidade"`): é o caso.
_RESSALVA_PLAUSIBILIDADE = {
    "regua_cotas_status": "corrigida_plausibilidade",
    "unidade_corrigida_por_plausibilidade": "unidade corrigida por PLAUSIBILIDADE",
    "alerta_unidade": "unidade corrigida por PLAUSIBILIDADE: com milímetros o "
                      "desenho inteiro mediria 0.29×0.19 m (impossível)",
}

#: Prancha com escala provada pela régua das cotas: o controle.
_SEM_RESSALVA = {"regua_cotas_status": "validada", "unidade_validada_por_cotas": 75}


class _Extracao:
    """O que o cofre lê da extração — os quatro resumos e o metadata."""

    def __init__(self, metadata):
        self.metadata = metadata

    def get_walls_by_layer(self):
        return {"Rampa": 90.85, "VIGA_BALDRAME": 42.3}

    def get_areas_by_layer(self):
        return {"HACHURA-LAJE": 55.2}

    def get_polygon_areas_by_layer(self):
        return {"CONTORNO-MURO": 120.4}

    def get_block_summary(self):
        return {"PILAR-19x30": 32}


def _escopo_do_main(**kw):
    import main
    escopo = dict(vars(main))      # os colaboradores de módulo, de verdade
    escopo.update(kw)
    return escopo


def _cofre_de_producao(metadata):
    """Roda o statement REAL do `process_job` que enche o cofre da chave
    (recortado por AST — ver `_executa`) e devolve o cofre."""
    cofre = {"comprimento": [], "area": [], "contagem": []}
    _executa.roda("process_job", "[selo:indice]",
                  _escopo_do_main(extraction=_Extracao(metadata),
                                  _indice_geom=cofre,
                                  dxf_path="/work/j/p0003.dxf"),
                  tamanho=1)
    return cofre


def _linha(obs, q=90.85, unit="m", conf="estimado"):
    return {"description": "Meio-fio de concreto — rampa", "unit": unit,
            "quantity": q, "confidence": conf, "origem": "dxf_geom",
            "observations": obs}


_CITA_RAMPA = "Fonte: comprimento total do layer 'Rampa' = 90,85 m."


# ══════════════════════════════════════════════════════════════════════════
#  1) O cofre não guarda comprimento nem área de prancha com escala sem prova
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_prancha_por_plausibilidade_nao_entra_no_cofre():
    cofre = _cofre_de_producao(_RESSALVA_PLAUSIBILIDADE)
    assert cofre["comprimento"] == [], cofre
    assert cofre["area"] == [], cofre


def test_a_outra_ressalva_de_escala_tambem_nao_entra():
    """`unidade_suspeita` é a outra chave de escala que a procedência lê."""
    cofre = _cofre_de_producao({"unidade_suspeita": "maior elemento 19 mm"})
    assert cofre["comprimento"] == [] and cofre["area"] == [], cofre


def test_CONTROLE_prancha_com_escala_provada_entra_inteira():
    """Sem este, "não entrou" passaria com o statement quebrado (o `except`
    engole o erro e o cofre fica vazio pra qualquer prancha)."""
    cofre = _cofre_de_producao(_SEM_RESSALVA)
    assert ("Rampa", 90.85) in cofre["comprimento"], cofre
    assert ("VIGA_BALDRAME", 42.3) in cofre["comprimento"], cofre
    assert ("HACHURA-LAJE", 55.2) in cofre["area"], cofre
    assert ("CONTORNO-MURO", 120.4) in cofre["area"], cofre


def test_CONTROLE_prancha_sem_metadata_entra():
    cofre = _cofre_de_producao({})
    assert ("Rampa", 90.85) in cofre["comprimento"], cofre


def test_CONTROLE_a_CONTAGEM_da_prancha_com_ressalva_continua_entrando():
    """Contar bloco não depende de escala (17/08): 32 pilares são 32 INSERTs,
    meça-se em milímetro ou em milha."""
    cofre = _cofre_de_producao(_RESSALVA_PLAUSIBILIDADE)
    assert cofre["contagem"] == [("PILAR-19x30", 32)], cofre


# ══════════════════════════════════════════════════════════════════════════
#  2) Do cofre à chave: a linha do caso não sobe; a mesma, com prova, sobe
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_linha_estimada_citando_o_layer_nao_sobe():
    cofre = _cofre_de_producao(_RESSALVA_PLAUSIBILIDADE)
    assert chave([_linha(_CITA_RAMPA)], cofre) == []


def test_CONTROLE_a_mesma_linha_em_prancha_com_escala_provada_sobe():
    cofre = _cofre_de_producao(_SEM_RESSALVA)
    prom = chave([_linha(_CITA_RAMPA)], cofre)
    assert [p["indice"] for p in prom] == [0], prom


# ══════════════════════════════════════════════════════════════════════════
#  3) A chave não desfaz a trava de escala divergente
# ══════════════════════════════════════════════════════════════════════════
_CITA_VIGA = "comprimento medido no layer 'VIGA_BALDRAME' = 42,30 m"
_COFRE_VIGA = {"comprimento": [("VIGA_BALDRAME", 42.3)], "area": [], "contagem": []}


def test_linha_com_o_aviso_da_escala_divergente_nao_sobe():
    obs = MARCA_ESCALA_DIVERGENTE + " e esta é uma das divergentes. " + _CITA_VIGA
    assert chave([_linha(obs, q=42.3)], _COFRE_VIGA) == []


def test_CONTROLE_sem_o_aviso_a_mesma_linha_sobe():
    prom = chave([_linha(_CITA_VIGA, q=42.3)], _COFRE_VIGA)
    assert [p["indice"] for p in prom] == [0], prom


def _trava_divergente_de_producao(itens, escalas):
    """Roda o statement REAL da trava de escala divergente do `process_job`."""
    logs = []
    pd = types.SimpleNamespace(warnings=[])
    _executa.roda("process_job", "_esc_div(_escala_por_prancha)",
                  _escopo_do_main(
                      _escala_por_prancha=escalas, all_items=itens,
                      project_data=pd, job_id="job-teste",
                      _log_error=lambda stage, msg, *a, **k: logs.append((stage, msg))),
                  tamanho=1)
    return logs


_DUAS_ESCALAS = [
    {"prancha": "p0001.dxf", "fator": 0.001, "regua": "nao-decidiu"},
    {"prancha": "p0003.dxf", "fator": 0.1, "regua": "corrigida_plausibilidade"},
]


def _item_confirmado(obs):
    from models import BudgetItem, Confidence
    return BudgetItem(item_num="1", description="Viga baldrame — comprimento",
                      unit="m", quantity=42.3, observations=obs,
                      ref_sheet="p0003.dxf", confidence=Confidence.CONFIRMADO,
                      origem="dxf_geom")


def test_pela_esteira_a_trava_rebaixa_e_a_chave_nao_promove_de_volta():
    """O fluxo do job, na ordem do job: a trava divergente (código real)
    rebaixa, e a chave, que roda depois, não desfaz. Se alguém mudar a
    redação do aviso sem mudar a marca, este teste pega."""
    it = _item_confirmado(_CITA_VIGA)
    logs = _trava_divergente_de_producao([it], _DUAS_ESCALAS)
    assert str(getattr(it.confidence, "value", it.confidence)) == "estimado", logs
    assert MARCA_ESCALA_DIVERGENTE in it.observations, it.observations
    assert chave([it], _COFRE_VIGA) == []


def test_a_IA_escrevendo_escalas_diferentes_nao_tira_a_marca():
    """🪤 A checagem de "já avisei" era `"escalas diferentes" not in obs`: a
    linha cuja observação da IA dizia isso era rebaixada SEM a marca — e a
    chave a promovia de volta."""
    obs = "Vistas em escalas diferentes (1:25 e 1:125). " + _CITA_VIGA
    it = _item_confirmado(obs)
    _trava_divergente_de_producao([it], _DUAS_ESCALAS)
    assert MARCA_ESCALA_DIVERGENTE in it.observations, it.observations
    assert chave([it], _COFRE_VIGA) == []


def test_CONTROLE_o_aviso_nao_se_repete_na_mesma_linha():
    obs = (MARCA_ESCALA_DIVERGENTE + " e esta é uma das divergentes; o número "
           "pode estar 1000× fora. Confira contra a prancha. " + _CITA_VIGA)
    it = _item_confirmado(obs)
    _trava_divergente_de_producao([it], _DUAS_ESCALAS)
    assert it.observations.count(MARCA_ESCALA_DIVERGENTE) == 1, it.observations


def test_CONTROLE_projeto_de_uma_escala_so_nao_ganha_o_aviso():
    """Sem divergência a trava não toca a linha — e a marca não aparece."""
    it = _item_confirmado(_CITA_VIGA)
    _trava_divergente_de_producao([it], [
        {"prancha": "p0001.dxf", "fator": 0.001, "regua": "validada"},
        {"prancha": "p0003.dxf", "fator": 0.001, "regua": "validada"}])
    assert str(getattr(it.confidence, "value", it.confidence)) == "confirmado"
    assert MARCA_ESCALA_DIVERGENTE not in it.observations
