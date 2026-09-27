# -*- coding: utf-8 -*-
"""O exemplo público não compra piso pela área construída.

🩸 27/09/2026 — O "Erro caro Nº 8" do Instagram (29/09) ensina: "comprar piso, contrapiso e
argamassa usando a área construída da capa" é o erro — ela conta a espessura das paredes; o certo
é somar ambiente por ambiente e separar por acabamento. E o exemplo público, destino de quase toda
chamada de outubro, fazia exatamente isso: contrapiso de 118,5 m² = a área construída pelo
perímetro externo da laje, e porcelanato + vinílico somando os mesmos 118,5 m² (achado ESTR-15 da
revisão do plano de outubro). Quem lesse o post e abrisse o exemplo cinco dias depois via a gente
fazendo o que acabou de condenar.

Agora: área de piso 108,3 m² (a diferença, 10,2 m², é parede), contrapiso = porcelanato + vinílico.
O guarda cobra o COMPORTAMENTO nos dados do exemplo (exemplos/itens.json — a planilha e a página
saem dele, e o test_exemplo_publico_bate_com_o_gerador garante isso), não os números.
"""
import io
import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTE = os.path.join(RAIZ, "exemplos", "itens.json")


def _dados():
    with io.open(FONTE, encoding="utf-8") as f:
        return json.load(f)


def problemas_do_piso(dados):
    """Lista do que está errado no piso do exemplo (vazia = certo)."""
    construida = float(dados["projeto"]["total_area"])
    pisos = [i for i in dados["itens"] if i["disc"] == "Pisos e Rodapés" and i["un"] == "m²"]
    contrapiso = [i for i in pisos if "contrapiso" in i["desc"].lower()]
    acabamentos = [i for i in pisos if "contrapiso" not in i["desc"].lower()]
    if len(contrapiso) != 1 or not acabamentos:
        return ["não achei o contrapiso e os acabamentos de piso no exemplo (%d contrapiso, %d acabamentos)"
                % (len(contrapiso), len(acabamentos))]
    cp = contrapiso[0]
    soma = sum(float(i["qtd"]) for i in acabamentos)
    probs = []
    if float(cp["qtd"]) >= construida:
        probs.append("contrapiso de %.1f m² não é menor que a área construída (%.1f m²) — a área "
                     "construída conta a espessura das paredes" % (float(cp["qtd"]), construida))
    if soma >= construida:
        probs.append("os acabamentos de piso somam %.1f m², não menos que a área construída (%.1f m²)"
                     % (soma, construida))
    if abs(soma - float(cp["qtd"])) > 0.05:
        probs.append("os acabamentos somam %.1f m² e o contrapiso tem %.1f m² — o contrapiso vai sob "
                     "todo acabamento de piso" % (soma, float(cp["qtd"])))
    for i in contrapiso + acabamentos:
        if "perímetro externo" in i.get("obs", ""):
            probs.append("%r diz que veio do perímetro externo — isso é a área construída" % i["desc"])
    return probs


def test_o_piso_do_exemplo_e_a_soma_dos_ambientes():
    probs = problemas_do_piso(_dados())
    assert not probs, "o exemplo voltou a comprar piso pela área construída: " + " | ".join(probs)


def test_CONTROLE_o_guarda_REPROVA_o_exemplo_de_17_07():
    """🧪 Os números que estavam no ar até 27/09, aplicados sobre os dados de hoje."""
    velho = _dados()
    for i in velho["itens"]:
        if i["desc"].startswith("Contrapiso"):
            i["qtd"] = 118.5
            i["obs"] = "Fonte: área da polilinha do perímetro externo, layer 'ARQ-AREA' = 118,50 m²"
        elif i["desc"].startswith("Piso porcelanato"):
            i["qtd"] = 96.3
    probs = problemas_do_piso(velho)
    assert any("não é menor que a área construída" in p for p in probs), probs
    assert any("perímetro externo" in p for p in probs), probs


def test_CONTROLE_o_guarda_pega_contrapiso_que_nao_cobre_o_acabamento():
    dados = _dados()
    for i in dados["itens"]:
        if i["desc"].startswith("Contrapiso"):
            i["qtd"] = float(i["qtd"]) - 10
    assert any("o contrapiso vai sob" in p for p in problemas_do_piso(dados))
