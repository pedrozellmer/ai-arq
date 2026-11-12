# -*- coding: utf-8 -*-
""""Quais itens estão em laranja e por quê?" conta a planilha INTEIRA.

🩸 11/11/2026 — a pergunta é BOTÃO do próprio chat. Numa planilha de 113
linhas o agente chamou `list_items` (corta em 8.000 caracteres) e respondeu
ao cliente: "A lista veio incompleta (a planilha tem 113 itens e o retorno
cortou no meio)". Mesma falha em 22/04. O resumo por disciplina já tinha sido
curado disto em 23/09 (`test_o_resumo_da_planilha_nao_vem_cortado.py`).
📏 No job real (110 linhas, 105 laranjas): 6.516 caracteres, 9 motivos.
🔑 `itens_em_laranja` agrupa aqui, sem IA, pelo aviso que o motor escreveu.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import (  # noqa: E402
    TOOLS,
    _SEM_AVISO_COM_NUMERO,
    _SEM_AVISO_SEM_NUMERO,
    _TETO_RESULTADO_FERRAMENTA,
    _conteudo_da_ferramenta,
    _dispatch_tool,
    _motivo_do_laranja,
    itens_em_laranja,
)
from models import SELO_ESTIMADO, SELO_MEDIDO  # noqa: E402

_ANOT = ("⚠ FONTE = ANOTAÇÃO DO DESENHO (texto/cota/legenda/hachura), não elemento "
         "construído — a linha vem de uma anotação do desenho")
_MOVEL = ("⚠ MÓVEL/EQUIPAMENTO — confirme o escopo: móveis e equipamentos (cadeira, "
          "mesa, fogão, geladeira, TV…) costumam ficar fora da obra")


def _l(num, obs="", selo="estimado", qty=10.0):
    _p = SELO_MEDIDO if selo == "medido" else SELO_ESTIMADO
    return {"item_num": num, "description": "Item " + num, "unit": "m²",
            "quantity": qty, "selo": selo,
            "observations": f"{_p}. {obs}" if obs else _p}


def _grupo(r, inicio):
    gs = [g for g in r["motivos"] if g["motivo"].startswith(inicio)]
    assert len(gs) == 1, (inicio, [g["motivo"] for g in r["motivos"]])
    return gs[0]


# ── o motivo é o aviso que o MOTOR escreveu ─────────────────────────────────
def test_motivo_e_o_nome_do_aviso():
    assert _motivo_do_laranja(SELO_ESTIMADO + ". " + _ANOT) == "FONTE = ANOTAÇÃO DO DESENHO"
    assert _motivo_do_laranja(SELO_ESTIMADO + ". " + _MOVEL) == "MÓVEL/EQUIPAMENTO"
    assert _motivo_do_laranja("ℹ BASE DE MEDIÇÃO DIFERENTE: a gente levantou em un") \
        == "BASE DE MEDIÇÃO DIFERENTE"
    assert _motivo_do_laranja("⚠ SOMA, não leitura direta — a quantidade veio") == "SOMA"


def test_ESTIMADO_repetido_pega_a_frase_seguinte():
    m = _motivo_do_laranja("⚠ ESTIMADO — este número foi LIDO de um texto da prancha. x")
    assert m == "este número foi LIDO de um texto da prancha", m


def test_sem_marcador_nao_inventa_motivo():
    r = itens_em_laranja([_l("1.1", "Fonte: inferência de boa prática."),
                          _l("1.2", "Rodapé não especificado.", qty=0)])
    assert {g["motivo"] for g in r["motivos"]} == {_SEM_AVISO_COM_NUMERO,
                                                   _SEM_AVISO_SEM_NUMERO}


# ── a conta ────────────────────────────────────────────────────────────────
def test_conta_so_os_laranja_e_agrupa():
    linhas = [_l("0.1", selo="metadado"), _l("1.1", selo="medido"),
              _l("1.2", _ANOT), _l("1.3", _ANOT, qty=0), _l("2.1", _MOVEL),
              _l("2.2", "sem aviso nenhum")]
    r = itens_em_laranja(linhas)
    assert r["total_laranja"] == 4 and r["sem_quantidade"] == 1
    a = _grupo(r, "FONTE = ANOTAÇÃO")
    assert (a["n"], a["sem_quantidade"], a["itens"]) == (2, 1, "1.2, 1.3")
    assert sum(g["n"] for g in r["motivos"]) == r["total_laranja"]
    # os grupos sem aviso vão pro fim
    assert r["motivos"][-1]["motivo"] in (_SEM_AVISO_COM_NUMERO, _SEM_AVISO_SEM_NUMERO)


def test_o_exemplo_nao_repete_o_selo():
    r = itens_em_laranja([_l("1.1", _ANOT)])
    ex = r["motivos"][0]["exemplos"][0]["observacao"]
    assert not ex.startswith(SELO_ESTIMADO) and ex.startswith("⚠ FONTE")


def test_mais_de_10_motivos_nada_some():
    linhas = [_l("1.%d" % i, "⚠ AVISO NUMERO %d: x" % i) for i in range(1, 16)]
    r = itens_em_laranja(linhas)
    assert len(r["motivos"]) == 10
    assert sum(g["n"] for g in r["motivos"]) == 15
    assert r["motivos"][-1]["motivo"].startswith("outros 6 motivos")


# ── cabe no teto ───────────────────────────────────────────────────────────
def _planilha(n):
    obs = [_ANOT, _MOVEL, "⚠ SOMA, não leitura direta — " + "x" * 300,
           "Fonte: inferência " + "y" * 600]
    return [_l("%d.%d" % (1 + i // 60, 1 + i % 60), obs[i % 4],
               qty=0 if i % 5 == 0 else 3.0) for i in range(n)]


def test_609_linhas_cabem_sem_corte():
    r = itens_em_laranja(_planilha(609))
    assert r["total_laranja"] == 609
    assert "[RESULTADO CORTADO" not in _conteudo_da_ferramenta(r)


def test_6000_linhas_encolhem_dizendo_e_a_conta_fica():
    r = itens_em_laranja(_planilha(6000))
    assert len(json.dumps(r, ensure_ascii=False)) < _TETO_RESULTADO_FERRAMENTA
    assert "encolhido" in r and r["total_laranja"] == 6000
    assert sum(g["n"] for g in r["motivos"]) == 6000


def test_CONTROLE_planilha_pequena_nao_encolhe():
    r = itens_em_laranja(_planilha(20))
    assert "encolhido" not in r
    assert all(len(g["exemplos"]) >= 1 for g in r["motivos"])


# ── a ferramenta existe e o list_items aponta pra ela ──────────────────────
def test_ferramenta_registrada_e_despachada(monkeypatch):
    import agent
    nomes = [t["name"] for t in TOOLS]
    assert "itens_em_laranja" in nomes
    lst = [t for t in TOOLS if t["name"] == "list_items"][0]
    assert "itens_em_laranja" in lst["description"]
    monkeypatch.setattr(agent, "tool_itens_em_laranja", lambda j: {"ok": j})
    assert _dispatch_tool("itens_em_laranja", "abc", {}) == {"ok": "abc"}
