# -*- coding: utf-8 -*-
"""Dois consertos de 22–23/10, os dois nascendo DESLIGADOS (mudam número).

1) PINTURA_DE_PISO_NAO_TRAVA_PD — a pintura derivada do pé-direito era pulada
   por "já existe pintura com número", e a pintura com número era SINALIZAÇÃO
   DE PISO (faixa de pedestres 253,9 m², piso epóxi). 📏 120 d: 2 casos com
   parede em metro.

2) PERIMETRO_DE_TERRENO_NAO_E_PAREDE — o perímetro de um largo (layer
   CONTORNO, 174,2 m) virou 522,6 m² de parede, 522,6 m² de revestimento e
   174,2 m de rodapé. 📏 História inteira: 3 linhas, todas desse caso.

🚨 Os guardas CHAMAM o código (a derivação real; as réguas puras). A chave é
lida pelo `_chave_do_job` — vale por avaliação.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from engine_rules import (  # noqa: E402
    layer_e_limite_de_terreno, parede_tirada_do_limite_do_terreno,
    pintura_e_de_piso_ou_sinalizacao)


# ══════════════════════════════════════════════════════════════════════════
#  1) a pintura de piso não trava a pintura derivada
# ══════════════════════════════════════════════════════════════════════════
class _It:
    def __init__(self, desc, unit, qty, obs=""):
        self.description, self.unit, self.quantity = desc, unit, qty
        self.observations, self.ref_sheet = obs, "planta.dxf"
        self.origem, self.confidence = "", "estimado"


def _caso():
    parede = _It("Alvenaria de vedação em bloco cerâmico", "ml", 487.8,
                 "Fonte: comprimento total do layer A-WALL = 487,8 m.")
    faixa = _It("Faixa de pedestres (zebrada) — sinalização horizontal em pintura "
                "acrílica para piso", "m²", 253.9)
    alvo = _It("Pintura látex em paredes internas", "m²", 0, "Requer pé-direito.")
    return [parede, faixa, alvo], alvo


def _deriva(monkeypatch, liga, job=""):
    if liga:
        monkeypatch.setenv("PINTURA_DE_PISO_NAO_TRAVA_PD", "1")
    else:
        monkeypatch.delenv("PINTURA_DE_PISO_NAO_TRAVA_PD", raising=False)
    itens, alvo = _caso()
    n = main._derive_pintura_pe_direito(itens, 3.05, 0.0, job_id=job)
    return n, alvo, main._derive_pintura_pe_direito.ultimo_motivo


def test_CONTROLE_desligada_a_faixa_segue_travando(monkeypatch):
    n, alvo, motivo = _deriva(monkeypatch, liga=False)
    assert n == 0 and alvo.quantity == 0
    assert motivo == "já existe pintura com número", motivo


def test_ligada_a_faixa_nao_trava_e_a_parede_e_pintada(monkeypatch):
    n, alvo, motivo = _deriva(monkeypatch, liga=True)
    assert n == 1, motivo
    assert alvo.quantity == round(487.8 * 3.05 * 2, 1), alvo.quantity


def test_CONTROLE_ligada_pintura_de_PAREDE_com_numero_segue_travando(monkeypatch):
    monkeypatch.setenv("PINTURA_DE_PISO_NAO_TRAVA_PD", "1")
    itens, alvo = _caso()
    itens[1] = _It("Pintura acrílica em paredes externas", "m²", 300.0)
    n = main._derive_pintura_pe_direito(itens, 3.05, 0.0)
    assert n == 0 and alvo.quantity == 0


def test_ligada_a_faixa_ZERADA_nao_vira_o_alvo(monkeypatch):
    """A linha de pintura zerada que a derivação preenche é a de PAREDE."""
    monkeypatch.setenv("PINTURA_DE_PISO_NAO_TRAVA_PD", "1")
    parede = _It("Alvenaria de vedação", "ml", 100.0,
                 "Fonte: comprimento total do layer A-WALL = 100 m.")
    faixa0 = _It("Pintura de demarcação de vagas — tinta acrílica", "m²", 0)
    alvo = _It("Pintura látex em paredes internas", "m²", 0)
    n = main._derive_pintura_pe_direito([parede, faixa0, alvo], 2.8, 0.0)
    assert n == 1
    assert faixa0.quantity == 0, "a faixa de vaga recebeu a pintura de parede"
    assert alvo.quantity == round(100 * 2.8 * 2, 1)


def test_a_avaliacao_liga_so_para_ela(monkeypatch):
    monkeypatch.delenv("PINTURA_DE_PISO_NAO_TRAVA_PD", raising=False)
    monkeypatch.setitem(main._CHAVES_DA_AVALIACAO, "evpint01",
                        {"PINTURA_DE_PISO_NAO_TRAVA_PD": "1"})
    assert _deriva(monkeypatch, liga=False, job="evpint01")[0] == 1
    assert _deriva(monkeypatch, liga=False, job="abc12345")[0] == 0


@pytest.mark.parametrize("desc", [
    "Faixa de pedestres (zebrada) — sinalização horizontal",
    "Piso com pintura epóxi de alta espessura — fornecimento",
    "Pintura de demarcação de vagas — tinta acrílica",
    "Sinalização horizontal de sentido de tráfego pintura de seta",
    "Pintura termoplástica de faixa de estacionamento",
])
def test_pintura_de_piso_e_reconhecida(desc):
    assert pintura_e_de_piso_ou_sinalizacao(desc)


@pytest.mark.parametrize("desc", [
    "Pintura látex em paredes internas",
    "Pintura acrílica em fachada — cor a definir",
    "Forro de gesso com pintura látex — pintar até o piso do mezanino",
    "",
    None,
])
def test_CONTROLE_pintura_de_parede_ou_teto_nao_e_de_piso(desc):
    assert not pintura_e_de_piso_ou_sinalizacao(desc)


# ══════════════════════════════════════════════════════════════════════════
#  2) o perímetro do terreno não vira parede
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("lay", ["CONTORNO", "TERRENO", "LOTE", "DIVISAS", "Perimetro real",
                                 "UR - Terreno", "LIMITE_LOTE", "POLIGONAL", "TOPOGRAFIA"])
def test_layer_de_limite_de_terreno(lay):
    assert layer_e_limite_de_terreno(lay), lay


@pytest.mark.parametrize("lay", ["IFC-Parede-Contorno", "ALV-DIVISA", "PAREDE_LIMITE_LOTE",
                                 "SAP_CONTORNO", "Contornos de Zona Archicad",
                                 "P-CONTORNO4", "A-WALL", "ARQ-ALV", "PAREDES", "DIVISORIA",
                                 "Muro de divisa", "", None])
def test_CONTROLE_o_que_nao_e_limite_de_terreno(lay):
    # "Muro de divisa": o layer tem DIVISA, mas o teste da LINHA (abaixo) é que
    # protege o muro; aqui só se prova que parede no nome não cai
    if lay == "Muro de divisa":
        pytest.skip("coberto pelo teste da linha")
    assert not layer_e_limite_de_terreno(lay), lay


def test_o_caso_as_tres_linhas_do_perimetro_caem():
    for disc, desc in [("Fechamentos Verticais", "Fechamento de parede — alvenaria ou divisória"),
                       ("Revestimentos", "Revestimento de parede — tipo a definir"),
                       ("Pisos e Rodapés", "Rodapé — tipo e material a definir")]:
        assert parede_tirada_do_limite_do_terreno(disc, desc, ["CONTORNO"]), desc


def test_CONTROLE_muro_de_divisa_e_obra_e_fica():
    assert not parede_tirada_do_limite_do_terreno(
        "Fechamentos Verticais", "Muro de divisa em bloco de concreto", ["DIVISA"])


def test_CONTROLE_linha_que_cita_TAMBEM_layer_de_parede_fica():
    assert not parede_tirada_do_limite_do_terreno(
        "Fechamentos Verticais", "Alvenaria", ["CONTORNO", "A-WALL"])


def test_CONTROLE_outra_disciplina_fica():
    assert not parede_tirada_do_limite_do_terreno(
        "Complementares", "Cerca viva no limite", ["TERRENO"])


def test_o_layer_do_caso_e_lido_da_observacao_como_o_motor_le():
    obs = ("Fonte: comprimento do layer CONTORNO = 174.20 m × pé-direito informado "
           "pelo cliente = 3.00 m → 522,60 m².")
    assert main._layers_da_obs(obs) == ["CONTORNO"], main._layers_da_obs(obs)


def test_a_chave_nasce_desligada_e_e_avaliavel():
    import io
    src = io.open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    for k in ("PERIMETRO_DE_TERRENO_NAO_E_PAREDE", "PINTURA_DE_PISO_NAO_TRAVA_PD"):
        assert '_chave_do_job(job_id, "%s") == "1"' % k in src, k
        assert '"%s"' % k in src[src.index("_CHAVES_AVALIAVEIS = frozenset"):][:3500], k
    assert "job_id=job_id)" in src[src.index("_pintou = _derive_pintura_pe_direito("):][:200]


# ══════════════════════════════════════════════════════════════════════════
#  2b) o TRECHO REAL do motor (do laço dos itens), executado
# ══════════════════════════════════════════════════════════════════════════
def _trecho_do_motor():
    import io
    import textwrap
    src = io.open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    i = src.index("# 🩸 22/10/2026 — PERÍMETRO DE TERRENO NÃO É PAREDE")
    i = src.rindex("\n", 0, i) + 1
    j = src.index('job_id, severity="info")', i) + len('job_id, severity="info")')
    return textwrap.dedent(src[i:j])


def _roda_trecho(liga, desc="Fechamento de parede — alvenaria ou divisória",
                 disc="Fechamentos Verticais", lys=("CONTORNO",), qty=522.6):
    logs = []
    ns = {"qty": qty, "item_data": {"discipline": disc}, "desc": desc,
          "_lys": list(lys), "conf": "estimado", "obs_raw": "Fonte: layer CONTORNO.",
          "_rebaixado_pela_fonte": False, "job_id": "abc12345",
          "_chave_do_job": lambda j, k: "1" if liga else "0",
          "_log_error": lambda *a, **k: logs.append(a)}
    exec(compile(_trecho_do_motor(), "<perimetro>", "exec"), ns)
    return ns, logs


def test_motor_ligado_o_perimetro_fica_em_branco_com_o_motivo():
    ns, logs = _roda_trecho(liga=True)
    assert ns["qty"] == 0
    assert ns["obs_raw"].startswith("⚠ FONTE = LIMITE DO TERRENO (layer CONTORNO)")
    assert ns["_rebaixado_pela_fonte"] is True
    assert logs and logs[0][0] == "motor:parede-do-terreno"


def test_CONTROLE_motor_desligado_nao_muda_numero_mas_registra():
    ns, logs = _roda_trecho(liga=False)
    assert ns["qty"] == 522.6 and ns["obs_raw"] == "Fonte: layer CONTORNO."
    assert logs and "ligada=0" in logs[0][1]


def test_CONTROLE_motor_ligado_parede_de_verdade_fica():
    ns, logs = _roda_trecho(liga=True, lys=("A-WALL",))
    assert ns["qty"] == 522.6 and not logs


# ══════════════════════════════════════════════════════════════════════════
#  2c) as duas brechas que a avaliação ev771a95 (23/10) mostrou
# ══════════════════════════════════════════════════════════════════════════
def test_brecha_1_parede_que_cita_o_contorno_E_as_cotas_cai():
    """A linha citava CONTORNO e MEDIDAS (as cotas que somam o perímetro)."""
    assert parede_tirada_do_limite_do_terreno(
        "Fechamentos Verticais", "Parede/fechamento perimetral", ["CONTORNO", "MEDIDAS"])


def test_CONTROLE_piso_do_lote_nao_e_rodape_e_fica():
    assert not parede_tirada_do_limite_do_terreno(
        "Pisos e Rodapés", "Piso externo intertravado — área do lote", ["TERRENO"])


def test_brecha_2_a_recuperacao_respeita_a_marca_do_terreno():
    from engine_rules import corrigir_comprimento_medido, MARCA_LIMITE_DO_TERRENO
    obs = (MARCA_LIMITE_DO_TERRENO + " (layer CONTORNO) — é o perímetro do lote. "
           "Fonte: comprimento total do layer CONTORNO = 174.20 ml.")
    assert corrigir_comprimento_medido("Rodapé perimetral", "ml", 0, obs) == {}, (
        "a recuperação devolveu o perímetro do lote ao rodapé")


def test_CONTROLE_sem_a_marca_a_recuperacao_segue_valendo():
    from engine_rules import corrigir_comprimento_medido
    obs = "Fonte: comprimento total do layer A-FLOR = 54,49 m."
    assert corrigir_comprimento_medido("Rodapé", "ml", 0, obs).get("quantity") == 54.49


def test_o_motor_escreve_a_MESMA_marca_que_a_recuperacao_procura():
    from engine_rules import MARCA_LIMITE_DO_TERRENO
    ns, _ = _roda_trecho(liga=True)
    assert ns["obs_raw"].startswith(MARCA_LIMITE_DO_TERRENO)


# ══════════════════════════════════════════════════════════════════════════
#  1b) a meia-parede (avaliação evf20fdf, 23/10)
# ══════════════════════════════════════════════════════════════════════════
def _meia_caso():
    meia = _It("Execução de meia-parede (alvenaria baixa) em bloco cerâmico", "ml", 71.56,
               "Fonte: comprimento total do layer ARQ-ALV-BX = 71,56 m.")
    epoxi = _It("Piso com pintura epóxi de alta espessura", "m²", 7.92)
    alvo = _It("Pintura látex em paredes internas", "m²", 0)
    return [meia, epoxi, alvo], alvo


def test_ligada_meia_parede_nao_vira_parede_inteira(monkeypatch):
    """O caso: sem a exclusão, 71,56 × 2,80 × 2 = 400,7 m² de pintura."""
    monkeypatch.setenv("PINTURA_DE_PISO_NAO_TRAVA_PD", "1")
    itens, alvo = _meia_caso()
    n = main._derive_pintura_pe_direito(itens, 2.8, 0.0)
    assert n == 0 and alvo.quantity == 0, alvo.quantity
    assert main._derive_pintura_pe_direito.ultimo_motivo == "sem comprimento de parede"


def test_ligada_meia_parede_sai_mas_a_parede_cheia_fica(monkeypatch):
    monkeypatch.setenv("PINTURA_DE_PISO_NAO_TRAVA_PD", "1")
    itens, alvo = _meia_caso()
    itens.insert(0, _It("Alvenaria de vedação em bloco cerâmico", "ml", 100.0,
                        "Fonte: comprimento total do layer A-WALL = 100 m."))
    n = main._derive_pintura_pe_direito(itens, 2.8, 0.0)
    assert n == 1 and alvo.quantity == round(100 * 2.8 * 2, 1), alvo.quantity


def test_CONTROLE_desligada_nada_muda_na_meia_parede(monkeypatch):
    """Desligada a chave, a derivação é a de antes (trava pela pintura de piso)."""
    monkeypatch.delenv("PINTURA_DE_PISO_NAO_TRAVA_PD", raising=False)
    itens, alvo = _meia_caso()
    n = main._derive_pintura_pe_direito(itens, 2.8, 0.0)
    assert n == 0 and main._derive_pintura_pe_direito.ultimo_motivo == "já existe pintura com número"


@pytest.mark.parametrize("desc", ["Meia-parede em bloco cerâmico", "Alvenaria baixa — h=1,10 m",
                                  "Mureta de contenção", "Peitoril em alvenaria",
                                  "Guarda-corpo em alvenaria", "Platibanda em alvenaria",
                                  "Muro de divisa em bloco de concreto"])
def test_parede_de_meia_altura_e_reconhecida(desc):
    from engine_rules import parede_de_meia_altura
    assert parede_de_meia_altura(desc)


@pytest.mark.parametrize("desc", ["Alvenaria de vedação em bloco cerâmico",
                                  "Parede drywall — montante 70 mm, até a laje",
                                  "Alvenaria de vedação — com peitoril de granito nas janelas", "", None])
def test_CONTROLE_parede_cheia_nao_e_meia_altura(desc):
    from engine_rules import parede_de_meia_altura
    assert not parede_de_meia_altura(desc)


def test_CONTROLE_desligada_e_sem_pintura_nenhuma_a_conta_antiga_segue_igual(monkeypatch):
    """Produção hoje: chave em 0 e nenhuma pintura com número → a derivação roda
    como sempre rodou (a exclusão da meia-parede só vem com a chave)."""
    monkeypatch.delenv("PINTURA_DE_PISO_NAO_TRAVA_PD", raising=False)
    meia = _It("Execução de meia-parede (alvenaria baixa) em bloco cerâmico", "ml", 71.56,
               "Fonte: comprimento total do layer ARQ-ALV-BX = 71,56 m.")
    alvo = _It("Pintura látex em paredes internas", "m²", 0)
    n = main._derive_pintura_pe_direito([meia, alvo], 2.8, 0.0)
    assert n == 1 and alvo.quantity == round(71.56 * 2.8 * 2, 1), alvo.quantity
