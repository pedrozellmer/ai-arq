# -*- coding: utf-8 -*-
"""O exemplo público não promete mais do que a planilha de verdade entrega.

🩸 27/09/2026 — O estudo de posicionamento achou o exemplo (1º link da bio do Instagram a partir de
01/10) mostrando 18 de 25 itens medidos (72%), 8 de 11 áreas em m² seladas como medidas, nenhuma
linha em branco e toda linha com a origem escrita — e a frase "Não é que a IA não leia o PDF: ela lê
e mede". Na base real, medida no mesmo dia (127 projetos em CAD, linha a linha):
    contagem (un)     40,5% medida
    comprimento (m)   22,9% medida
    área (m²)          1,8% medida  — e só 34% das linhas de área voltam com quantidade
Quem chegasse pelo exemplo esperaria área medida e planilha cheia, e receberia outra coisa.

Pedro liberou a correção: as áreas saem estimadas com a conta escrita, três linhas em branco, uma
linha sem origem, e o PDF descrito como estimativa. O guarda cobra o COMPORTAMENTO nos dados do
exemplo (exemplos/itens.json — a planilha e a página saem dele) e o texto da página.
⏭️ Se a base remedida mostrar área saindo medida de verdade, revise a regra da área aqui.
"""
import copy
import io
import json
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTE = os.path.join(RAIZ, "exemplos", "itens.json")
PAGINA = os.path.join(RAIZ, "exemplo.html")

#: frases que diziam mais do que o produto faz
FRASES_PROIBIDAS = ("do jeito que sai", "lê e mede", "l&ecirc; e mede", "quantitativo de verdade")


def _dados():
    with io.open(FONTE, encoding="utf-8") as f:
        return json.load(f)


def _pagina():
    return io.open(PAGINA, encoding="utf-8").read()


def problemas_da_vitrine(dados, html):
    """Lista do que promete demais (vazia = certo)."""
    itens = dados["itens"]
    probs = []
    areas = [i["desc"] for i in itens if i["medido"] and i["un"] in ("m²", "m2")]
    if areas:
        probs.append("área em m² selada como medida (na base, 1,8%% das áreas saem medidas): %s" % areas)
    if not any(not i["medido"] and not i["qtd"] for i in itens):
        probs.append("nenhuma linha em branco (na base, 31,6% das linhas em CAD voltam sem quantidade)")
    # sem observação NENHUMA (não basta faltar o "Fonte:": várias estimativas explicam sem ele)
    if not any(not i["medido"] and not (i.get("obs") or "").strip() for i in itens):
        probs.append("toda linha diz de onde veio o número — na planilha de verdade, parte não diz")
    medidos = sum(1 for i in itens if i["medido"])
    if 2 * medidos > len(itens):
        probs.append("metade ou mais dos itens medidos (%d de %d) — na base, 25,0%% das linhas em CAD"
                     % (medidos, len(itens)))
    texto = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    probs += ["a página diz %r" % f for f in FRASES_PROIBIDAS if f in texto]
    return probs


def test_o_exemplo_nao_promete_mais_que_a_base():
    probs = problemas_da_vitrine(_dados(), _pagina())
    assert not probs, "o exemplo público voltou a prometer demais: " + " | ".join(probs)


def test_CONTROLE_o_guarda_REPROVA_o_exemplo_que_estava_no_ar():
    """🧪 Os selos e a frase que estavam no ar até 27/09, aplicados sobre os dados de hoje."""
    velho = copy.deepcopy(_dados())
    selados_em_17_07 = ("Limpeza final", "Remoção de divisória", "Alvenaria de bloco", "Divisória em drywall",
                        "Contrapiso", "Piso porcelanato", "Piso vinílico", "Forro de gesso")
    for i in velho["itens"]:
        if i["desc"].startswith(selados_em_17_07):
            i["medido"] = True
        if not i["qtd"]:
            i["qtd"] = 1.0
        if not i["obs"]:
            i["obs"] = "Fonte: layer 'ARQ-SOLEIRA'"
    html_velho = _pagina() + "<p>Não é que a IA não leia o PDF: ela lê e mede.</p>"
    probs = problemas_da_vitrine(velho, html_velho)
    for pedaco in ("área em m²", "nenhuma linha em branco", "toda linha diz", "metade ou mais", "lê e mede"):
        assert any(pedaco in p for p in probs), (pedaco, probs)


def test_CONTROLE_o_guarda_le_os_dados_de_verdade():
    """Guarda que não acha item nenhum passa verde guardando nada."""
    itens = _dados()["itens"]
    assert len(itens) >= 20, len(itens)
    assert any(i["medido"] and i["un"] == "un" for i in itens), "o exemplo não tem mais contagem medida"
    assert "Raio-X da leitura" in _pagina()
