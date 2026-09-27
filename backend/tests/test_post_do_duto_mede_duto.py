# -*- coding: utf-8 -*-
"""O post do duto ensina a unidade do SINAPI (m² de DUTO) e não induz a chapa mais fina.

🩸 27/09/2026 — A revisão do plano de outubro do Instagram (achados FONTE-01 e FONTE-03) achou no
post de 11/10 ("Quantitativo de duto: 4 armadilhas que erram o número" — pra onde o Erro caro Nº 10,
de 13/10, manda):
  • "Cada metro linear vale 2,00 m² de chapa" — o SINAPI mede m² de DUTO (trecho reto planificado ×
    perímetro da seção). A chapa consumida é maior: 4,5293 kg por m² de duto na bitola 26, com abas e
    sobras. Chamar a área de "chapa" leva a comprar a menos — ou a somar uma perda por fora, o Erro
    caro Nº 9 do mesmo mês;
  • logo depois do exemplo de 60 × 40, a conversão pra quilo citava SÓ a bitola 26 (4,00 kg/m²).
Conferido no Caderno Técnico SINAPI de dutos (atualização 03/2024), baixado da Caixa em 27/09.
🪤 A faixa "bitola 26 só até lado maior de 30 cm" que a revisão sugeria NÃO está nesse caderno — não
entrou no post, e este guarda impede que ela entre atribuída ao SINAPI.
"""
import io
import json
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SLUG = "quantitativo-de-duto-climatizacao-armadilhas"


def _post():
    with io.open(os.path.join(RAIZ, "blog", "posts.json"), encoding="utf-8") as f:
        dados = json.load(f)
    posts = dados["posts"] if isinstance(dados, dict) else dados
    return next(p for p in posts if p.get("slug") == SLUG)


def _texto(post):
    partes = [post.get("title", ""), post.get("description", ""), post.get("intro", ""), post.get("cta", "")]
    partes += [s.get("h2", "") + "\n" + s.get("body", "") for s in post.get("sections", [])]
    partes += [s.get("title", "") + "\n" + s.get("description", "") for s in post.get("sources", [])]
    return "\n".join(partes)


def problemas(texto):
    probs = []
    if "m² de chapa" in texto:
        probs.append("chama a medida de 'm² de chapa' — o SINAPI mede m² de DUTO")
    if "kg/m²" in texto:
        bitolas = set(re.findall(r"bitola (\d{2})", texto))
        if len(bitolas) < 2:
            probs.append("converte pra quilo com uma bitola só (%s) — induz a chapa mais fina" % sorted(bitolas))
        if "coeficiente" not in texto or not re.search(r"sobra|perda", texto):
            probs.append("converte pra quilo sem dizer que o coeficiente da composição já traz abas e sobras")
    if re.search(r"SINAPI[^.]{0,120}lado maior|lado maior[^.]{0,120}SINAPI", texto):
        probs.append("atribui ao SINAPI uma faixa de dimensão por bitola que o caderno (03/2024) não tem")
    return probs


def test_o_post_do_duto_ensina_o_que_o_sinapi_diz():
    probs = problemas(_texto(_post()))
    assert not probs, "o post do duto voltou a errar a conta: " + " | ".join(probs)


def test_CONTROLE_o_guarda_REPROVA_o_post_de_antes():
    """🧪 Os trechos que estavam no posts.json até 27/09."""
    velho = ("Na prática: um duto de 60 × 40 cm tem perímetro de 2,00 m. Cada metro linear vale 2,00 m² de "
             "chapa.\nDe m² para quilo, o peso vem da bitola da chapa, que o SINAPI declara no próprio insumo: "
             "bitola 26, espessura 0,50 mm, 4,00 kg/m².")
    probs = problemas(velho)
    assert len(probs) == 3, probs


def test_CONTROLE_o_guarda_pega_a_faixa_atribuida_ao_sinapi():
    assert problemas("No SINAPI, bitola 26 é pra duto com lado maior até 30 cm.")


def test_CONTROLE_o_guarda_le_o_post_inteiro():
    t = _texto(_post())
    assert len(t) > 5000 and "Armadilha 3" in t and "perímetro" in t, len(t)
