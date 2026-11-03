# -*- coding: utf-8 -*-
"""A área TOTAL informada pelo cliente só vai pra superfície do imóvel.

🩸 03/11/2026 (job e21652dc): a cliente confirmou 118,74 m² e o número foi pra
"Piso do elevador social", cuja observação dizia 18,74 m² (3 cabines). Em 90
dias, das 8 linhas que herdaram a área informada, também o deck e o forro de
madeira que NÓS tínhamos deixado em branco de propósito, e o isolamento de dutos
"entre-forro".
🔑 AREA_INFORMADA_SO_SUPERFICIE_GERAL=1 recusa; com 0 o motor só conta.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine_rules as er  # noqa: E402
import main  # noqa: E402

_CHAVE = "AREA_INFORMADA_SO_SUPERFICIE_GERAL"
_MARCA = "⚠ Deixamos esta linha EM BRANCO de propósito: outra linha já traz quantidade."


@pytest.mark.parametrize("desc,obs,motivo", [
    ("Piso do elevador social em quartzito",
     "Somatório das cabines: 6,15 + 6,44 + 6,15 = 18,74 m².", "próprio tamanho (18,74 m²)"),
    ("Área gourmet — piso a definir (18,05 m²)", "", "próprio tamanho (18,05 m²)"),
    ("Piso da varanda", "Área de 12.5 m2 lida da planta.", "próprio tamanho (12.5 m²)"),
    ("Deck de madeira — piso item 4", _MARCA, "em branco de propósito"),
    ("Isolamento térmico de dutos — aplicação no entre-forro", "", "não é a superfície"),
    ("Forro no entreforro técnico", "", "não é a superfície"),
    ("Isolamento de dutos de ar condicionado", "", "não é a superfície"),
    ("Forro do entre-forro técnico", "", "não é a superfície"),
    ("Forro entre forro e laje", "", "não é a superfície"),
])
def test_linha_que_nao_e_a_superficie_do_imovel(desc, obs, motivo):
    assert motivo in er.area_informada_nao_e_desta_linha(desc, obs, 118.74)


@pytest.mark.parametrize("desc,obs", [
    ("Piso porcelanato 60x60 em todos os ambientes", ""),
    ("Contrapiso de regularização", "Área total do pavimento: 118,74 m²."),
    ("Forro de gesso", "Cerca de 110 m² de forro."),
    ("Piso vinílico", ""),
    ("Piso vinílico", "Juntei 3 linhas com a mesma quantidade (0 m²) e ficou esta."),
])
def test_superficie_do_imovel_pode_receber(desc, obs):
    assert er.area_informada_nao_e_desta_linha(desc, obs, 118.74) == ""


def test_m2_por_caixa_tambem_recusa_e_erra_pra_menos():
    """Controle honesto: '2,5 m²/cx' conta como tamanho próprio. Recusar devolve a
    linha vazia — o erro é pra menos, nunca um número inventado."""
    assert er.area_informada_nao_e_desta_linha("Piso cerâmico", "2,5 m²/cx", 118.74)


def test_milhar_com_ponto_e_lido_como_milhar():
    assert "(1.092,18 m²)" in er.area_informada_nao_e_desta_linha(
        "Piso do salão", "Ambiente de 1.092,18 m² no quadro.", 2000)
    assert er.area_informada_nao_e_desta_linha(
        "Piso do salão", "Ambiente de 1.092,18 m² no quadro.", 1200) == ""


def test_numero_colado_em_outro_numero_nao_conta():
    assert er.area_informada_nao_e_desta_linha("Piso", "cota 1,20x3,5m2x", 118.74) == ""
    assert er.area_informada_nao_e_desta_linha("Piso", "ref 4418,74 m²", 118.74) == ""


def test_total_invalido_nao_recusa_por_tamanho():
    assert er.area_informada_nao_e_desta_linha("Piso", "18,74 m²", None) == ""
    assert er.area_informada_nao_e_desta_linha("Piso", "18,74 m²", "x") == ""


def test_a_marca_e_a_mesma_frase_que_o_motor_escreve():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "main.py"), encoding="utf-8") as f:
        assert ('" | ⚠ ' + er.MARCA_EM_BRANCO_DE_PROPOSITO + ': "') in f.read()


class _Item:
    def __init__(self, desc, obs="", qty=0):
        self.description = desc
        self.unit = "m²"
        self.quantity = qty
        self.ref_sheet = "planta cliente-nn.pdf"
        self.observations = obs
        self.origem = ""
        self.confidence = "estimado"


def _roda(itens, apenas=False):
    main._apply_area_honesty(itens, total_area=118.74, total_area_source="informado",
                             apenas_preencher=apenas, job_id="job-de-teste")
    return main._apply_area_honesty.ultimo_recusa_informada


@pytest.mark.parametrize("apenas", [False, True])
def test_com_a_chave_em_0_preenche_como_antes_e_conta(monkeypatch, apenas):
    monkeypatch.setenv(_CHAVE, "0")
    elev = _Item("Piso do elevador social", "Cabines: 18,74 m².")
    recusas, liga = _roda([elev], apenas)
    assert elev.quantity == 118.74 and liga is False
    assert recusas == ["Piso do elevador social (a linha diz o próprio tamanho (18,74 m²))"]


@pytest.mark.parametrize("apenas", [False, True])
def test_com_a_chave_em_1_a_linha_da_peca_fica_vazia_e_a_geral_recebe(monkeypatch, apenas):
    monkeypatch.setenv(_CHAVE, "1")
    elev = _Item("Piso do elevador social", "Cabines: 18,74 m².")
    geral = _Item("Piso porcelanato dos ambientes")
    recusas, liga = _roda([elev, geral], apenas)
    assert elev.quantity == 0 and geral.quantity == 118.74 and liga is True
    assert len(recusas) == 1


def test_sem_recusa_a_lista_vem_vazia(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    geral = _Item("Piso porcelanato dos ambientes")
    assert _roda([geral]) == ([], True) and geral.quantity == 118.74


def _prepara_log(monkeypatch, valor):
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))
    monkeypatch.setattr(main._apply_area_honesty, "ultimo_recusa_informada", valor,
                        raising=False)
    return logs


def test_o_registro_conta_e_leva_no_maximo_6(monkeypatch):
    logs = _prepara_log(monkeypatch, (["l%d (x)" % i for i in range(8)], False))
    main._registra_recusa_da_informada("j")
    assert logs[0][0] == "motor:area-informada-recusada"
    assert logs[0][1].startswith("linhas=8 liga=0 | l0 (x)") and "l6" not in logs[0][1]


def test_sem_recusa_nao_registra(monkeypatch):
    logs = _prepara_log(monkeypatch, ([], True))
    main._registra_recusa_da_informada("j")
    assert logs == []


def test_falha_do_registro_nao_derruba(monkeypatch):
    logs = _prepara_log(monkeypatch, None)
    main._registra_recusa_da_informada("j")
    assert logs[0][1].startswith("FALHOU")


def test_os_dois_caminhos_registram():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "main.py"), encoding="utf-8") as f:
        fonte = f.read()
    assert fonte.count("_registra_recusa_da_informada(job_id)") == 3   # a def + 2 chamadas
    assert "apenas_preencher=True, job_id=job_id)\n    _registra_recusa_da_informada(job_id)" \
        in fonte.replace("\r\n", "\n")


def test_chave_avaliavel_etapa_de_diagnostico_e_nasce_desligada():
    assert _CHAVE in main._CHAVES_AVALIAVEIS
    assert "motor:area-informada-recusada" in main._STAGES_DIAGNOSTICO
    assert main._chave_do_job("job-sem-avaliacao", _CHAVE) == "0"
