# -*- coding: utf-8 -*-
"""A estimativa incremental (29/08/2026) — `known_pranchas`.

🎯 O caso Maria Victoria (27/08): 17 arquivos selecionados, cada mudança na
seleção re-enviava TUDO de novo (upload quadrático), pelo caminho do Cloudflare
que corta em 100 MB — acima disso a estimativa saía errada CALADA. O conserto:
o front manda só o arquivo NOVO + o total já contado (`known_pranchas`), e o
backend precifica a SOMA.

Estes testes CHAMAM o código (lição do apagão de 29h do /api/track: guarda que
lê fonte não pega argumento faltando).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pricing import calculate_price, estimate_for_files  # noqa: E402


def test_sem_arquivo_precifica_o_total_conhecido():
    """Cliente REMOVEU um arquivo: o front não re-envia nada, só reprecifica."""
    r = estimate_for_files([], extra_pranchas=7)
    assert r["total_pranchas"] == 7
    assert r["price_cents"] == calculate_price(7)
    assert r["breakdown"] == []


def test_extra_soma_com_os_arquivos_contados(tmp_path):
    """1 arquivo novo + 4 já contadas = preço de 5, não de 1."""
    # PDF mínimo de 1 página (o contador lê o /Count do PDF)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF")
    r = estimate_for_files([str(pdf)], extra_pranchas=4)
    assert r["total_pranchas"] == 5, r
    assert r["price_cents"] == calculate_price(5)
    assert len(r["breakdown"]) == 1  # breakdown é só do que foi ENVIADO


def test_extra_negativo_nao_desconta():
    """🧪 Controle de recusa: known_pranchas vem do CLIENTE — negativo não pode
    virar desconto no preço."""
    r = estimate_for_files([], extra_pranchas=-3)
    assert r["total_pranchas"] == 1  # piso, nunca 0 nem negativo
    assert r["price_cents"] == calculate_price(1)


def test_sem_extra_comportamento_antigo_intacto(tmp_path):
    """Front velho (sem o campo) não muda em NADA."""
    pdf = tmp_path / "b.pdf"
    pdf.write_bytes(
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF")
    r = estimate_for_files([str(pdf)])
    assert r["total_pranchas"] == 1
    assert r["price_cents"] == calculate_price(1)


def test_o_front_manda_pro_caminho_direto_e_com_cache():
    """O dashboard tem que: (a) chamar a estimativa por API_UPLOAD_BASE (o
    caminho do CF corta em 100 MB e erra CALADO), (b) mandar known_pranchas.
    🪤 Guarda de fonte — vale como trava de regressão do CAMINHO, não como
    prova de execução (a prova é o teste de rede ao vivo)."""
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    html = open(os.path.join(raiz, "dashboard.html"), encoding="utf-8").read()
    ini = html.index("async function _estimatePriceNow")
    trecho = html[ini:ini + 4000]
    assert "API_UPLOAD_BASE}/api/estimate-price" in trecho
    assert "known_pranchas" in trecho
    assert "${API_BASE}/api/estimate-price" not in html  # caminho velho MORTO
