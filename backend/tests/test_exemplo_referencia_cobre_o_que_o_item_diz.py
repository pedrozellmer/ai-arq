# -*- coding: utf-8 -*-
"""No exemplo público, a referência SINAPI traz o que a descrição do item diz que vem junto.

🩸 27/09/2026 — A revisão do plano de outubro do Instagram (achado ESTR-05) achou no exemplo a
linha "Porta de madeira 80x210 com batente e ferragens" com a referência 91297: PORTA DE MADEIRA
FRISADA… INCLUSO DOBRADIÇAS — sem batente e sem fechadura. Quem orçasse pelo exemplo contava
batente e fechadura ZERO vez, exatamente o erro que o "Erro caro Nº 12" (27/10) ensina a evitar.
E a página ainda cortava a descrição antes do "INCLUSO DOBRADIÇAS": não dava nem pra desconfiar.

Agora a linha aponta o kit 91314 (dobradiças, batente e fechadura). O guarda cobra o
COMPORTAMENTO: se a descrição promete batente ou ferragem/fechadura, a composição escolhida
tem que trazer.
"""
import io
import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTE = os.path.join(RAIZ, "exemplos", "itens.json")

# o que a descrição do item promete  →  o que a composição tem que citar
PROMESSAS = (
    (("batente",), "BATENTE"),
    (("ferragens", "ferragem", "fechadura"), "FECHADURA"),
)


def _dados():
    with io.open(FONTE, encoding="utf-8") as f:
        return json.load(f)


def problemas_de_escopo(dados):
    probs = []
    for it in dados["itens"]:
        esc = next((c for c in it["sinapi"] if c["papel"] == "escolhido"), None)
        if not esc:
            continue
        desc, comp = it["desc"].lower(), esc["descricao"].upper()
        for palavras, exige in PROMESSAS:
            if any(p in desc for p in palavras) and exige not in comp:
                probs.append("%r promete %s e a referência %s não traz: %s…"
                             % (it["desc"], exige.lower(), esc["codigo"], esc["descricao"][:70]))
    return probs


def test_a_referencia_traz_o_que_o_item_promete():
    probs = problemas_de_escopo(_dados())
    assert not probs, "o exemplo aponta referência que conta a peça ZERO vez: " + " | ".join(probs)


def test_CONTROLE_o_guarda_REPROVA_a_porta_que_estava_no_ar():
    """🧪 A referência de 17/07 aplicada sobre os dados de hoje."""
    dados = _dados()
    porta = next(i for i in dados["itens"] if i["desc"].startswith("Porta de madeira"))
    porta["sinapi"] = [{"codigo": "91297", "papel": "escolhido", "unidade": "UN",
                        "descricao": "PORTA DE MADEIRA FRISADA, SEMI-OCA (LEVE OU MÉDIA), 80X210CM, ESPESSURA "
                                     "DE 3,5CM, INCLUSO DOBRADIÇAS - FORNECIMENTO E INSTALAÇÃO. AF_10/2025"}]
    probs = problemas_de_escopo(dados)
    assert any("batente" in p for p in probs) and any("fechadura" in p for p in probs), probs


def test_CONTROLE_o_guarda_le_as_portas_do_exemplo():
    """Guarda que não acha porta nenhuma passa verde guardando nada."""
    portas = [i for i in _dados()["itens"] if "batente" in i["desc"].lower()]
    assert portas, "o exemplo não tem mais item com batente — revise este guarda"
