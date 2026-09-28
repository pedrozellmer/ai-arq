# -*- coding: utf-8 -*-
"""A seção "raio-x" da home não promete mais do que a planilha de verdade entrega.

🩸 27/09/2026 — O estudo de posicionamento achou na home, logo abaixo da maquete da planilha:
  • "Em CAD, 1 em cada 4 linhas já vem conferida" e "o que você pode usar sem conferir" — o selo diz
    de onde veio o número, não que ele foi conferido (nunca foi comparado com gabarito);
  • "o motor mede o desenho" — palavra de dentro de casa (o /exemplo já não usa);
  • "Os melhores modelos de IA do mundo acertam entre 40% e 55%" — o estudo acadêmico mediu os
    modelos que TESTOU, não "os melhores do mundo";
e na maquete, "Parede de alvenaria 128 m²" e "Piso porcelanato 96 m²" com ✓ medido. Na base real
(127 projetos em CAD, 27/09), área sai medida em 1,8% das linhas; contagem, em 40,5%.

Pedro liberou as correções. O guarda cobra o TEXTO visível da home (sem comentário e sem script).
"""
import io
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGINA = os.path.join(RAIZ, "index.html")

FRASES_PROIBIDAS = ("vem conferida", "sem conferir", "melhores modelos", "o motor mede")


def _texto(html):
    """O que o visitante lê: sem comentário HTML e sem <script>."""
    t = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    return re.sub(r"<script.*?</script>", " ", t, flags=re.S | re.I)


def problemas_da_home(html):
    t = _texto(html)
    probs = ["a home diz %r" % f for f in FRASES_PROIBIDAS if f in t.lower()]
    m = re.search(r'<section id="raio-x".*?</table>', t, re.S)
    if not m:
        return probs + ["não achei a maquete da planilha na seção #raio-x"]
    for linha in re.findall(r"<tr.*?</tr>", m.group(0), re.S):
        if re.search(r"m²|m&sup2;", linha) and "medido" in linha and "estimativa" not in linha:
            probs.append("a maquete sela área em m² como medida: %s"
                         % re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", linha)).strip()[:60])
    return probs


def test_a_home_nao_promete_mais_que_a_base():
    probs = problemas_da_home(io.open(PAGINA, encoding="utf-8").read())
    assert not probs, "a home voltou a prometer demais: " + " | ".join(probs)


def test_CONTROLE_o_guarda_REPROVA_a_home_que_estava_no_ar():
    """🧪 A maquete e as frases que estavam no ar até 27/09."""
    velho = ('<section id="raio-x"><table><tbody>'
             '<tr><td>Parede de alvenaria</td><td>128 m²</td><td><span>&#10003; medido</span></td></tr>'
             '<tr><td>Porta P1</td><td>12 un</td><td><span>&#10003; medido</span></td></tr>'
             '</tbody></table>'
             '<p>Em CAD, 1 em cada 4 linhas já vem conferida. O que você pode usar <em>sem conferir</em>. '
             'O motor mede o desenho. Os melhores modelos de IA do mundo acertam entre 40% e 55%.</p></section>')
    probs = problemas_da_home(velho)
    for pedaco in ("vem conferida", "sem conferir", "melhores modelos", "o motor mede", "Parede de alvenaria"):
        assert any(pedaco in p for p in probs), (pedaco, probs)
    assert not any("Porta P1" in p for p in probs), "contagem medida é legítima e não pode reprovar"


def test_CONTROLE_o_guarda_le_a_home_de_verdade():
    t = _texto(io.open(PAGINA, encoding="utf-8").read())
    assert len(t) > 20000, "a home tem só %d caracteres — o guarda não está lendo a página" % len(t)
    assert '<section id="raio-x"' in t and "Porta P1" in t, "sumiu a maquete da planilha da home"
