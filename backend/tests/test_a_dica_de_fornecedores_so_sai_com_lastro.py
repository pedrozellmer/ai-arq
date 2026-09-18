# -*- coding: utf-8 -*-
"""A dica "±X% entre fornecedores" só sai quando a base tem MAIS DE UM projeto.

🩸 18/09/2026. Medido no banco antes de escrever qualquer linha:

  · "💡 Itens dessa categoria variam ±115% entre fornecedores — pedir 3
    orçamentos" estava em **3.873 linhas (36,7%) de 66 jobs, 50 contas**, de
    maio até hoje (a fila dizia 35,5% — número velho);
  · a base INTEIRA (`market_heuristics`) vem de UM comparativo: 3 fornecedores
    de um escritório corporativo, ingerido em 23/04;
  · o "±X%" de cada categoria é a média do coeficiente de variação de **1 a 5
    itens com 2-3 cotações** — piso: 1 item, 2 cotações → "±124%";
  · 2.283 dessas linhas eram a categoria "outros" — o pega-tudo do
    `categorize_item`, "itens dessa categoria" sem categoria nenhuma;
  · só dispara em `office`, que é a PRIMEIRA opção do select (o default de quem
    não escolhe) — inclusive 116 linhas de projetos de ESTRUTURA.

Decisão do Pedro (18/09): **desligar até ter base; o código fica**. A frase
volta sozinha quando o segundo comparativo for ingerido — e volta dizendo o
tamanho da base ("Em N comparativos…"), pra nunca mais soar como estatística de
mercado quando é a média de meia dúzia de cotações.

🔑 Uma régua pros TRÊS consumidores — a planilha (`check_item_anomaly`), o chat
(`tool_check_market_heuristics`) e a API (`/api/heuristics/check`): antes cada
um montava a própria resposta, e os três entregavam "±X%" de um projeto só.

🚫 Não cobre: as 3.873 linhas já gravadas ("daqui pra frente", como na soma);
planilhas já baixadas; o texto do FAQ (que não promete esse número).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import market_heuristics as mh  # noqa: E402


def _fetch_com(n_fontes, category="demolicao", cv=1.03, cobertura=1):
    """Um `_fetch` dublado com N projetos-fonte DISTINTOS (fonte-0, fonte-1…)."""
    def linha(htype, metric, valor, k, **extra):
        d = {"heuristic_type": htype, "typology": "office", "category": category,
             "metric_name": metric, "metric_value": valor, "stddev": 0,
             "n_observations": 2, "source_anonimo": "fonte-%d" % k}
        d.update(extra)
        return d
    rows = []
    for k in range(n_fontes):
        rows.append(linha("dispersion", "cv_total", cv, k))
        rows.append(linha("coverage_pattern", "cobertura_completa", cobertura, k,
                          n_observations=3))
        rows.append(linha("mat_mo_share", "share_mat", 0.4, k, stddev=0.1))
    def fetch(htype, typology="office"):
        return [r for r in rows if r["heuristic_type"] == htype and r["typology"] == typology]
    return fetch


def _com_base(monkeypatch, n_fontes, **kw):
    monkeypatch.setattr(mh, "_fetch", _fetch_com(n_fontes, **kw))
    monkeypatch.setattr(mh, "_CACHE", {})


_ITEM = {"description": "demolicao de drywall", "unit": "m2"}


# ── a planilha: o que `check_item_anomaly` devolve pro motor anexar ──────────

def test_com_UM_projeto_fonte_nenhuma_dica_sai(monkeypatch):
    """🩸 O estado da base hoje. Era isto que virava "±115%" em 3.873 linhas."""
    _com_base(monkeypatch, 1)
    assert mh.check_item_anomaly(_ITEM) == []


def test_com_lastro_a_dica_volta_DIZENDO_o_tamanho_da_base(monkeypatch):
    """Controle positivo, e a 2ª metade: não basta calar — quando fala, diz
    de quantos comparativos veio, pra o N pequeno ser lido como N pequeno."""
    _com_base(monkeypatch, 2)
    alertas = mh.check_item_anomaly(_ITEM)
    assert alertas, "com lastro a dica sumiu — o gate virou desligamento"
    disp = [a for a in alertas if "±" in a]
    assert disp and "2 comparativos" in disp[0] and "±103%" in disp[0], alertas


def test_a_categoria_SEM_IDENTIDADE_nunca_ganha_dica(monkeypatch):
    """2.283 das 3.873 linhas eram "outros" — 'itens dessa categoria' sem
    categoria. Mesmo com lastro, não."""
    _com_base(monkeypatch, 2, category="outros")
    assert mh.categorize_item("coisa sem palavra-chave nenhuma") == "outros"
    assert mh.check_item_anomaly({"description": "coisa sem palavra-chave nenhuma",
                                  "unit": ""}) == []


def test_a_cobertura_segue_a_MESMA_regua(monkeypatch):
    """A irmã "costuma ser omitida" (970 linhas) tem a mesma base de um projeto."""
    _com_base(monkeypatch, 1, cobertura=1)
    assert mh.check_item_anomaly(_ITEM) == []
    _com_base(monkeypatch, 2, cobertura=1)
    cov = [a for a in mh.check_item_anomaly(_ITEM) if a.startswith("⚠")]
    assert cov and "2 comparativos" in cov[0] and "demolicao" in cov[0], cov


def test_CONTROLE_cobertura_completa_nao_gera_aviso_mesmo_com_lastro(monkeypatch):
    _com_base(monkeypatch, 2, cobertura=3)
    assert not [a for a in mh.check_item_anomaly(_ITEM) if a.startswith("⚠")]


# ── a base: fontes DISTINTAS, e a borda do piso ─────────────────────────────

def test_a_base_conta_projetos_DISTINTOS_nao_linhas(monkeypatch):
    """🪤 Uma base de 5 linhas do MESMO comparativo é uma base de 1."""
    def fetch(htype, typology="office"):
        return [{"heuristic_type": htype, "typology": "office", "category": "piso",
                 "metric_name": "cv_total", "metric_value": 1.2, "n_observations": 2,
                 "source_anonimo": "o-mesmo-comparativo"} for _ in range(5)]
    monkeypatch.setattr(mh, "_fetch", fetch)
    monkeypatch.setattr(mh, "_CACHE", {})
    b = mh.base_da_tipologia("office", "dispersion")
    assert b["n_fontes"] == 1 and b["lastro"] is False, b


def test_a_borda_do_piso_e_a_do_proprio_piso(monkeypatch):
    """Não pina o valor do piso (seria 'o piso que eu escolhi'): cobra que a
    borda esteja onde a constante diz, qualquer que seja ela."""
    _com_base(monkeypatch, mh._MINIMO_DE_FONTES - 1)
    assert mh.base_da_tipologia("office", "dispersion")["lastro"] is False
    _com_base(monkeypatch, mh._MINIMO_DE_FONTES)
    assert mh.base_da_tipologia("office", "dispersion")["lastro"] is True


def test_fonte_vazia_nao_conta_como_projeto(monkeypatch):
    def fetch(htype, typology="office"):
        return [{"heuristic_type": htype, "typology": "office", "category": "piso",
                 "metric_name": "cv_total", "metric_value": 1.2, "n_observations": 2,
                 "source_anonimo": s} for s in ("", None, "  ", "fonte-1")]
    monkeypatch.setattr(mh, "_fetch", fetch)
    monkeypatch.setattr(mh, "_CACHE", {})
    assert mh.base_da_tipologia("office", "dispersion")["n_fontes"] == 1


# ── o chat e a API: a MESMA régua, e a base sempre à vista ──────────────────

def test_o_chat_nao_entrega_numero_sem_lastro_mas_entrega_a_base(monkeypatch):
    import agent
    _com_base(monkeypatch, 1)
    r = agent.tool_check_market_heuristics("demolicao de drywall")
    assert r["alertas"] == []
    assert r["dispersao_mercado"] is None and r["cobertura_tipica"] is None \
        and r["share_mat_mo_tipico"] is None, r
    assert r["base"]["dispersao"]["n_fontes"] == 1, r["base"]
    assert "não invente" in r["obs"].lower() or "nao invente" in r["obs"].lower(), r["obs"]


def test_CONTROLE_o_chat_entrega_os_numeros_com_lastro(monkeypatch):
    import agent
    _com_base(monkeypatch, 2)
    r = agent.tool_check_market_heuristics("demolicao de drywall")
    assert r["dispersao_mercado"] and abs(r["dispersao_mercado"]["cv_medio"] - 1.03) < 1e-9
    assert r["base"]["dispersao"]["n_fontes"] == 2
    assert "2 projeto" in r["obs"], r["obs"]


def test_a_descricao_da_ferramenta_manda_dizer_o_tamanho_da_base():
    """A instrução que o modelo lê antes de responder: sem lastro, não inventa."""
    import agent
    tool = next(t for t in agent.TOOLS if t["name"] == "check_market_heuristics")
    d = tool["description"].lower()
    assert "lastro" in d and "base" in d, d
    assert "agregada de orçamentos reais" not in d, "voltou a afirmar base plural"


def test_a_API_segue_a_mesma_regua(monkeypatch):
    import main
    _com_base(monkeypatch, 1)
    r = asyncio.run(main.heuristics_check("demolicao de drywall"))
    assert r["alertas"] == [] and r["metrics"]["dispersion"] is None, r
    assert r["base"]["dispersao"]["n_fontes"] == 1
    _com_base(monkeypatch, 2)
    r2 = asyncio.run(main.heuristics_check("demolicao de drywall"))
    assert r2["metrics"]["dispersion"] and r2["alertas"], r2


def test_planilha_chat_e_API_concordam_sobre_a_MESMA_base(monkeypatch):
    """🧬 Três consumidores, uma régua: mira na divergência."""
    import agent
    import main
    for n in (1, 2):
        _com_base(monkeypatch, n)
        planilha = bool(mh.check_item_anomaly(_ITEM))
        chat = agent.tool_check_market_heuristics("demolicao de drywall")
        api = asyncio.run(main.heuristics_check("demolicao de drywall"))
        assert planilha == bool(chat["alertas"]) == bool(api["alertas"]) == (n >= 2), (n, planilha, chat["alertas"], api["alertas"])
        assert (chat["dispersao_mercado"] is None) == (api["metrics"]["dispersion"] is None) == (n < 2)
