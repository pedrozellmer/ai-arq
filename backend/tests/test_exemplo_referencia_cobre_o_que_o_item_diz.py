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
        # 27/09 (Pedro liberou a troca): a alvenaria de vedação da reforma apontava 89290, ALVENARIA
        # ESTRUTURAL — serviço, consumo e custo de outra coisa. Estrutural só se o item disser.
        if "ESTRUTURAL" in comp and "estrutural" not in desc:
            probs.append("%r não diz estrutural e a referência %s é: %s…"
                         % (it["desc"], esc["codigo"], esc["descricao"][:70]))
        # 27/09: o porcelanato de 86,1 m² apontava 87261, a variante de ambiente MENOR QUE 5 M².
        # No exemplo cada linha de piso é um acabamento contínuo do escritório — linha que sozinha
        # passa de 10 m² não é ambiente pequeno.
        if ("MENOR QUE 5 M" in comp or "ENTRE 5 M" in comp) and float(it["qtd"]) >= 10:
            probs.append("%r tem %.1f m² e a referência %s é a variante de ambiente pequeno: %s"
                         % (it["desc"], float(it["qtd"]), esc["codigo"],
                            esc["descricao"][esc["descricao"].upper().find("AMBIENTES"):][:45]))
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


def test_CONTROLE_o_guarda_REPROVA_a_alvenaria_e_o_piso_que_estavam_no_ar():
    """🧪 As referências de 17/07 aplicadas sobre os dados de hoje."""
    dados = _dados()
    for it in dados["itens"]:
        if it["desc"].startswith("Alvenaria de bloco"):
            it["sinapi"] = [{"codigo": "89290", "papel": "escolhido", "unidade": "M2",
                             "descricao": "ALVENARIA ESTRUTURAL DE BLOCOS CERÂMICOS 14X19X29, (ESPESSURA DE 14 CM), "
                                          "UTILIZANDO PALHETA E ARGAMASSA DE ASSENTAMENTO COM PREPARO EM BETONEIRA. AF_03/2023"}]
        elif it["desc"].startswith("Piso porcelanato"):
            it["sinapi"] = [{"codigo": "87261", "papel": "escolhido", "unidade": "M2",
                             "descricao": "REVESTIMENTO CERÂMICO PARA PISO COM PLACAS TIPO PORCELANATO DE DIMENSÕES "
                                          "60X60 CM APLICADA EM AMBIENTES DE ÁREA MENOR QUE 5 M². AF_02/2023_PE"}]
    probs = problemas_de_escopo(dados)
    assert any("89290" in p for p in probs) and any("87261" in p for p in probs), probs


def test_CONTROLE_o_guarda_le_as_portas_do_exemplo():
    """Guarda que não acha porta nenhuma passa verde guardando nada."""
    portas = [i for i in _dados()["itens"] if "batente" in i["desc"].lower()]
    assert portas, "o exemplo não tem mais item com batente — revise este guarda"
