# -*- coding: utf-8 -*-
"""Comprimento repartido pela proporção de etiquetas não é medida — sai em branco.

🩸 27–28/10/2026 — dois projetos de hidráulica do mesmo cliente (c6e7f0db,
58892ba1): o layer P-PIPE junta todos os tubos, e a leitura repartiu o total
entre os diâmetros por "31 de 188 etiquetas → 31/188 × 2235 ≈ 368 m". Saiu
laranja, com número. 📏 120 d de cliente: 38 linhas em 3 jobs.
🔑 RATEIO_POR_ETIQUETA_EM_BRANCO=1 deixa em branco; com 0 o motor só conta.
Os textos abaixo são os do banco (cortados), não inventados.
"""
import os
import sys
import types

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
import pytest  # noqa: E402
import engine_rules as _er  # noqa: E402

_RATEADAS = [
    # 58892ba1
    "Fonte estimada: comprimento total de eixo do layer P-PIPE ≈ 2235 m. Distribuição proporcional "
    "ao número de etiquetas 'Ø300 - PS1' (31 de 188 etiquetas no layer P-PIPE-IDEN) → 31/188 × 2235 "
    "≈ 368 m. Confirmar com medição no CAD.",
    "Estimativa proporcional: comprimento total de eixo do layer P-PIPE ≈ 1212 m (metade dos 2424,91 m "
    "de face dupla). Distribuído proporcionalmente às 26 tags 'Ø32 - PVC MARROM' de 63 tags totais no "
    "layer P-PIPE-IDEN: 26/63 × 1212 ≈ 500 m.",
    "Estimativa proporcional: 23 tags 'Ø54 - CPVC' de 63 tags totais × 1212 m eixo total ≈ 443 m. "
    "Confirmar com medição por diâmetro.",
    # c6e7f0db
    "Fonte estimada: layer P-PIPE tem comprimento de face dupla 4470,13 m → eixo total ≈ 2235 m para "
    "todos os diâmetros. Distribuição proporcional por número de rótulos P-PIPE-IDEN: Ø150 PVC SR tem "
    "49 ocorrências de 189 rótulos totais → 49/189 × 2235 ≈ 579 m.",
    "total ≈ 2235 m (P-PIPE / 2). Ø300 PS1 tem 31 rótulos de 189 totais → 31/189 × 2235 ≈ 367 m. "
    "Confirmar com medição por diâmetro.",
    "Fonte estimada: eixo total ≈ 2235 m (P-PIPE / 2). Ø150 PVC SN tem 1 rótulo de 189 totais → "
    "1/189 × 2235 ≈ 12 m. Confirmar com medição por diâmetro.",
    # 242e1ecf (sprinkler)
    "Estimativa proporcional: 21 rótulos '25 mm' de 50 rótulos totais no layer 'SP-Textos conduto' "
    "(42%) × 103,59 m total do layer 'SP-Condutos' = 43,51 m. Confirmar com isométrico da rede.",
]

_NAO_RATEADAS = [
    # 17d6e1f2: a linha do TOTAL fala das OUTRAS linhas — e é medida
    "Fonte: comprimento total do layer P-PIPE = 760,60 m (COMPRIMENTOS POR LAYER). Diâmetros "
    "identificados no layer P-PIPE-IDEN: ø100 (mais frequente), ø150. Subdividir por diâmetro nos "
    "itens 6 a 10 — as quantidades por diâmetro são estimativas proporcionais; o total confirmado é 760,60 ml.",
    # a mesma família, feita do jeito certo: conta rótulos e deixa o comprimento em branco
    "Diâmetro ø100mm é o mais frequente no layer P-PIPE-IDEN (43 rótulos 'ø100' + 14 'ø100-PVCR' = 57 "
    "rótulos). Comprimento não separável por diâmetro no layer P-PIPE.",
    # comprimento medido de layer próprio
    "Fonte: comprimento do layer 'AP-Tubos' = 76.57m. Diâmetro confirmado por 'AP-Textos tubo': ø75mm ×6.",
    # 1a2f9f03: "totais" sem contagem de etiqueta na frente
    "Contagem visual dos segmentos VC1(20×60) na planta: aproximadamente 60 a 70 vigas identificadas. "
    "Estimativa conservadora de 280 ml totais.",
    # a negação é ressalva, não procedência
    "Comprimento do layer HID-AF-25 = 48,20 m; não distribuído proporcionalmente ao número de etiquetas.",
]


@pytest.mark.parametrize("obs", _RATEADAS)
def test_o_rateio_por_etiqueta_e_reconhecido(obs):
    assert _er.comprimento_rateado_por_etiqueta(obs, "ml"), obs


@pytest.mark.parametrize("obs", _NAO_RATEADAS)
def test_CONTROLE_o_que_nao_e_rateio_passa(obs):
    assert not _er.comprimento_rateado_por_etiqueta(obs, "ml"), obs


@pytest.mark.parametrize("unidade", ["ml", "m", "M"])
def test_vale_pra_toda_unidade_de_comprimento(unidade):
    assert _er.comprimento_rateado_por_etiqueta(_RATEADAS[0], unidade)


@pytest.mark.parametrize("unidade", ["un", "m²", "vb"])
def test_CONTROLE_so_comprimento(unidade):
    # a área "proporcional" já tem régua própria (AREA_A_OLHO_NAO_PRESERVA)
    assert not _er.comprimento_rateado_por_etiqueta(_RATEADAS[0], unidade)


def test_a_linha_fica_em_branco_com_o_numero_que_a_leitura_pos():
    q, obs, achou = _er.linha_apos_rateio_por_etiqueta(_RATEADAS[0], "ml", 368)
    assert achou and q == 0.0
    assert obs.startswith(_er.MARCA_RATEIO_POR_ETIQUETA)
    assert "368,00 ml" in obs
    assert obs.endswith(_RATEADAS[0])        # a nota da leitura (com o total) continua


def test_CONTROLE_linha_sem_numero_ou_ja_avisada_nao_muda():
    assert _er.linha_apos_rateio_por_etiqueta(_RATEADAS[0], "ml", 0)[2] is False
    _, obs, _ = _er.linha_apos_rateio_por_etiqueta(_RATEADAS[0], "ml", 368)
    assert _er.linha_apos_rateio_por_etiqueta(obs, "ml", 5)[2] is False


# ── o bloco do main.py, executado de verdade ──
_INICIO = "        # 🩸 28/10/2026 — COMPRIMENTO RATEADO PELA PROPORÇÃO DE ETIQUETAS"
_FIM = "        for _fld, _reads in _area_readings.items():"


def _bloco():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read().replace("\r\n", "\n")
    i = src.index(_INICIO)
    j = src.index(_FIM, i)
    return src, i, src[i:j]


def _rodar(liga, monkeypatch):
    _, _, bloco = _bloco()
    import textwrap
    logs = []
    it = types.SimpleNamespace(description="Tubulação PS1 Ø300", unit="ml", quantity=368.0,
                               observations=_RATEADAS[0], confidence="estimado")
    medido = types.SimpleNamespace(description="Tubulação AP Ø75", unit="ml", quantity=76.57,
                                   observations=_NAO_RATEADAS[2], confidence="confirmado")
    monkeypatch.setenv("RATEIO_POR_ETIQUETA_EM_BRANCO", "1" if liga else "0")
    ns = {"all_items": [it, medido], "job_id": "teste01",
          "_log_error": lambda st, msg, job=None, severity="error": logs.append((st, msg))}
    exec(textwrap.dedent(bloco), ns)
    return it, medido, logs


def test_com_a_chave_em_0_so_conta(monkeypatch):
    it, medido, logs = _rodar(False, monkeypatch)
    assert it.quantity == 368.0 and it.observations == _RATEADAS[0]
    assert logs and logs[0][0] == "motor:rateio-por-etiqueta"
    assert "linhas=1 em_branco=0 liga=0" in logs[0][1], logs


def test_com_a_chave_em_1_fica_em_branco(monkeypatch):
    it, medido, logs = _rodar(True, monkeypatch)
    assert it.quantity == 0.0
    assert it.observations.startswith(_er.MARCA_RATEIO_POR_ETIQUETA)
    assert medido.quantity == 76.57 and medido.observations == _NAO_RATEADAS[2]
    assert "linhas=1 em_branco=1 liga=1" in logs[0][1], logs


def test_roda_depois_da_recuperacao_de_comprimento():
    # a recuperação encheria a linha em branco com o total do layer
    src, i, _ = _bloco()
    rec = src.index('_chave_do_job(job_id, "RECUPERACAO_NAO_REPETE_NUMERO")')
    assert rec < i
    # …e ANTES da fila de quem rebaixa selo, onde os guardas proíbem trocar quantidade
    assert i < src.index("from engine_rules import numero_declarado_parcial")


def test_a_chave_e_avaliavel_e_o_log_e_diagnostico():
    src, _, _ = _bloco()
    k = src.index("_CHAVES_AVALIAVEIS")
    assert '"RATEIO_POR_ETIQUETA_EM_BRANCO"' in src[k:src.index("})", k)]
    d = src.index("_STAGES_DIAGNOSTICO")
    assert '"motor:rateio-por-etiqueta"' in src[d:src.index("}", d)]
