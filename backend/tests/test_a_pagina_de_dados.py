# -*- coding: utf-8 -*-
"""/dados é a FONTE dos números do site — e quem cita os números aponta pra ela.

📏 27/09/2026 (auditoria de aquisição, item 7, P7): o site citava "68,4% / 52,3%
/ 25,0%" em três páginas sem dizer, em lugar nenhum, como aquilo foi medido; e
números de três épocas conviviam (o guarda test_numeros_do_site_batem nasceu
disso). /dados junta os números com a data, a amostra e o método. O guarda de
números já exige que ela diga os MESMOS valores; este exige o caminho até ela.
"""
import io
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ler(rel):
    return io.open(os.path.join(_RAIZ, rel), encoding="utf-8").read()


def test_quem_cita_os_numeros_aponta_pro_dados():
    sem = [p for p in ("index.html", "faq.html", "exemplo.html") if 'href="/dados.html"' not in _ler(p)]
    assert not sem, "página cita os números de cobertura e não aponta pro /dados: %s" % sem


def test_a_pagina_diz_data_amostra_e_metodo():
    t = _ler("dados.html")
    assert re.search(r"Medição de \d{1,2} de \w+ de 20\d\d", t), "o /dados perdeu a data da medição"
    for trecho in ("154 projetos", "5.682", "5.222", "Como a gente mediu"):
        assert trecho in t, "o /dados perdeu %r" % trecho


def test_o_dados_esta_no_sitemap_e_no_llms():
    assert "<loc>https://ai.arq.br/dados.html</loc>" in _ler("sitemap.xml")
    assert "https://ai.arq.br/dados.html" in _ler("llms.txt")


def _classes_sem_css(html, css):
    classes = set()
    for m in re.finditer(r'class="([^"]+)"', html):
        classes |= set(m.group(1).split())
    return sorted(c for c in classes if "." + c.replace(":", chr(92) + ":").replace("/", chr(92) + "/") not in css)


def test_toda_classe_do_dados_existe_no_css():
    """🪤 o tailwind.min.css do site é ENXUTO: classe que ninguém usava antes não
    existe, e a página sai sem o estilo, calada (27/09: gap-x-5 nos Guias)."""
    pagina = _ler("dados.html")
    embutido = " ".join(re.findall(r"<style>(.*?)</style>", pagina, re.S))  # gradient-main etc. moram aqui
    faltam = _classes_sem_css(pagina, _ler("tailwind.min.css") + embutido)
    assert not faltam, "classe(s) sem CSS no /dados: %s" % faltam


def test_CONTROLE_classe_inexistente_e_pega():
    assert _classes_sem_css('<p class="gap-x-5 text-sm">', _ler("tailwind.min.css")) == ["gap-x-5"]
