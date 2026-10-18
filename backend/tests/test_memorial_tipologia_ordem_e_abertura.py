# -*- coding: utf-8 -*-
"""Memorial (rascunho): tipologia em português, "serviços preliminares" sem repetição, e Preliminares
antes de Demolição.

🩸 18/10/2026 — Ao gerar o memorial do projeto fictício do /exemplo pra pôr na página, a leitura da saída
achou três defeitos que valiam pra TODO cliente:
  • a tabela "Dados da obra" dizia "Tipologia: office" — o código do banco, em inglês (os 5 valores do
    banco são códigos: office, residential, educational, retail, hospital);
  • a abertura da seção dizia "Os serviços de serviços preliminares compreendem…";
  • Demolição vinha antes de Serviços Preliminares, embora a apresentação prometa "a sequência usual das
    etapas construtivas" (Pedro, 18/10: preliminares primeiro).
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memorial as M  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _itens():
    return [
        {"item_num": "1.1", "sort_order": 1, "description": "Remoção de divisória", "unit": "m²",
         "quantity": 18.0, "discipline": "Demolição e Remoção", "confidence": "estimado", "observations": ""},
        {"item_num": "2.1", "sort_order": 2, "description": "Limpeza final da obra", "unit": "m²",
         "quantity": 118.5, "discipline": "Serviços Preliminares", "confidence": "estimado", "observations": ""},
        {"item_num": "3.1", "sort_order": 3, "description": "Porta de madeira 80x210", "unit": "un",
         "quantity": 6.0, "discipline": "Divisórias e Vidros", "confidence": "confirmado", "observations": ""},
    ]


def _tipologia(estrutura):
    for s in estrutura["secoes"]:
        for b in s["blocos"]:
            if b.get("tipo") == "tabela":
                for rotulo, valor in b.get("linhas") or []:
                    if rotulo == "Tipologia":
                        return valor
    return None


def problemas(estrutura):
    """O que está errado na estrutura (vazio = certo)."""
    achados = []
    tip = _tipologia(estrutura)
    if tip and tip.strip().lower() in M.ROTULO_TIPOLOGIA:
        achados.append("tipologia saiu como código: %r" % tip)
    for s in estrutura["secoes"]:
        for b in s["blocos"]:
            if re.search(r"servi[çc]os de servi[çc]os", b.get("texto") or "", re.I):
                achados.append("abertura repete 'serviços': %r" % b["texto"][:60])
    titulos = [s["titulo"] for s in estrutura["secoes"]]
    i_pre = next((i for i, t in enumerate(titulos) if "Serviços Preliminares" in t), None)
    i_dem = next((i for i, t in enumerate(titulos) if "Demolição" in t), None)
    if i_pre is not None and i_dem is not None and i_dem < i_pre:
        achados.append("Demolição antes de Serviços Preliminares")
    return achados


def test_o_memorial_sai_certo():
    e = M.montar_estrutura({"project_name": "Obra X", "typology": "office", "total_area": 118.5}, _itens())
    assert problemas(e) == []
    assert _tipologia(e) == "Escritório corporativo"
    textos = [b.get("texto") or "" for s in e["secoes"] for b in s["blocos"]]
    assert any(t.startswith("Os serviços preliminares compreendem") for t in textos)
    assert any(t.startswith("Os serviços de demolição e remoção compreendem") for t in textos)


def test_CONTROLE_o_guarda_REPROVA_o_memorial_como_saia_ate_18_10():
    """🧪 A estrutura como saía antes do conserto: os três defeitos têm de aparecer."""
    velho = {"secoes": [
        {"titulo": "2. Dados da obra", "blocos": [{"tipo": "tabela", "linhas": [["Tipologia", "office"]]}]},
        {"titulo": "4. Demolição e Remoção", "blocos": [{"tipo": "texto", "texto": "Os serviços de demolição e remoção compreendem…"}]},
        {"titulo": "5. Serviços Preliminares", "blocos": [{"tipo": "texto", "texto": "Os serviços de serviços preliminares compreendem…"}]},
    ]}
    achados = problemas(velho)
    assert len(achados) == 3, achados


def test_toda_tipologia_da_tela_tem_rotulo_igual_ao_da_tela():
    """Os rótulos são os do seletor da tela de envio; se a tela ganhar uma opção, o memorial acompanha."""
    tela = io.open(os.path.join(RAIZ, "dashboard.html"), encoding="utf-8").read()
    bloco = re.search(r'<select id="project-typology".*?</select>', tela, re.S).group(0)
    import html
    opcoes = {v: html.unescape(r).strip() for v, r in re.findall(r'<option value="([a-z_]+)">([^<]+)</option>', bloco)}
    assert opcoes, "não achei as opções de tipologia na tela"
    assert opcoes == M.ROTULO_TIPOLOGIA


def test_tipologia_vazia_ou_desconhecida():
    assert M._rotulo_tipologia(None) == "[A PREENCHER]"
    assert M._rotulo_tipologia("  ") == "[A PREENCHER]"
    assert M._rotulo_tipologia("Hospital") == "Hospitalar / Clínicas"
    assert M._rotulo_tipologia("galpao") == "galpao"
