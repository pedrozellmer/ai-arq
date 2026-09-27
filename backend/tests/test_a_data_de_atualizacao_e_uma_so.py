# -*- coding: utf-8 -*-
"""A data de atualização de um post é UMA só: tela, JSON-LD e sitemap.

🩸 26/09/2026 — auditoria de aquisição (SEO/IA). O `generate.py` lia DOIS
campos: o JSON-LD usava `update_date`, o sitemap usava `updated`, e o
"Última atualização" do rodapé usava a data de publicação. O post "DWG, DXF
ou PDF" mostrava três datas ao mesmo tempo (tela 31/08, dateModified 23/08,
lastmod 22/07), e o post do memorial — o que mais cresce na IA do Google —
parecia parado desde 26/04. Dado estruturado que contradiz a tela é o que faz
o Google (e a IA que lê o Google) tratar a página como velha.

Estes testes RODAM o gerador (render_post_html e render_sitemap), não leem o
fonte: é a saída que o robô recebe que tem que concordar.
"""
import json
import os
import re
import sys
from datetime import datetime

import pytest

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_RAIZ, "blog"))

import generate  # noqa: E402

_LD_RX = re.compile(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', re.S)
_RODAPE_RX = re.compile(r"Última atualização: (\d{2}/\d{2}/\d{4})")
_NOTA_RX = re.compile(r"Atualizado em (\d{2}/\d{2}/\d{4})")


def _artigo(html):
    for bloco in _LD_RX.findall(html):
        try:
            dado = json.loads(bloco)
        except ValueError:
            continue
        if isinstance(dado, dict) and dado.get("@type") == "Article":
            return dado
    raise AssertionError("post sem JSON-LD Article")


def _lastmods(xml):
    pares = re.findall(r"<loc>[^<]*/blog/posts/([^<]+)\.html</loc>\s*<lastmod>([^<]+)</lastmod>", xml)
    return dict(pares)


def _br(iso):
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y")


def _publicados():
    hoje = generate.hoje_editorial().isoformat()
    return [p for p in generate.POSTS if p["publish_date"] <= hoje]


def test_tela_json_ld_e_sitemap_dizem_a_mesma_data():
    lastmods = _lastmods(generate.render_sitemap())
    conferidos = 0
    for p in _publicados():
        esperado = generate.data_de_atualizacao(p) or p["publish_date"]
        html = generate.render_post_html(dict(p))
        assert _artigo(html)["dateModified"][:10] == esperado, p["slug"]
        assert lastmods.get(p["slug"]) == esperado, p["slug"]
        rodape = _RODAPE_RX.search(html)
        if p.get("sources"):
            # post com fontes TEM o rodapé — sem esta linha, trocar a frase do
            # rodapé fazia a conferência abaixo passar vazia
            assert rodape, "post com fontes sem 'Última atualização': " + p["slug"]
        if rodape:
            assert rodape.group(1) == _br(esperado), p["slug"]
        conferidos += 1
    assert conferidos >= 20, "o teste quase não conferiu post nenhum: %d" % conferidos


def _iso(br):
    return datetime.strptime(br, "%d/%m/%Y").date().isoformat()


def test_a_nota_de_atualizacao_nunca_e_mais_nova_que_a_data():
    """Quem escreve "Atualizado em dd/mm/aaaa" na nota tem que ter um
    `update_date` igual ou POSTERIOR — foi a divergência do post DWG×PDF (nota
    31/08, dateModified 23/08: o dado estruturado dizia que a página era mais
    velha do que a própria tela). Uma edição depois da nota é legítima."""
    conferidas = 0
    for p in generate.POSTS:
        nota = _NOTA_RX.search(p.get("update_note") or "")
        if nota:
            assert generate.data_de_atualizacao(p), p["slug"]
            assert _iso(nota.group(1)) <= generate.data_de_atualizacao(p), p["slug"]
            conferidas += 1
    assert conferidas >= 1, "nenhuma nota 'Atualizado em dd/mm/aaaa' conferida — o formato mudou?"


def test_CONTROLE_a_nota_mais_nova_que_a_data_e_reprovada(monkeypatch):
    """Chama o teste DE VERDADE com o caso de antes (nota 31/08, data 23/08)."""
    p = {"slug": "x", "update_note": "<strong>Atualizado em 31/08/2026:</strong> x", "update_date": "2026-08-23"}
    monkeypatch.setattr(generate, "POSTS", [p])
    with pytest.raises(AssertionError):
        test_a_nota_de_atualizacao_nunca_e_mais_nova_que_a_data()


def test_a_data_de_atualizacao_fica_entre_a_publicacao_e_hoje():
    """dateModified antes de datePublished (post agendado com update_date) ou
    lastmod no futuro são sinais falsos pro Google."""
    hoje = generate.hoje_editorial().isoformat()
    for p in generate.POSTS:
        d = generate.data_de_atualizacao(p)
        if d:
            assert p["publish_date"] <= d <= hoje, (p["slug"], p["publish_date"], d, hoje)


def test_CONTROLE_update_date_em_post_agendado_e_reprovado(monkeypatch):
    p = {"slug": "agendado", "publish_date": "2099-01-01", "update_date": "2026-09-26"}
    monkeypatch.setattr(generate, "POSTS", [p])
    with pytest.raises(AssertionError):
        test_a_data_de_atualizacao_fica_entre_a_publicacao_e_hoje()


def test_o_post_do_memorial_nao_parece_parado_desde_abril():
    p = [x for x in generate.POSTS if x["slug"] == "memorial-descritivo-de-obra-modelo-pdf-docx"][0]
    assert (generate.data_de_atualizacao(p) or "") > "2026-04-26"


def test_updated_continua_aceito_como_apelido():
    assert generate.data_de_atualizacao({"updated": "2026-01-02"}) == "2026-01-02"
    assert generate.data_de_atualizacao({"update_date": "2026-03-04", "updated": "2026-01-02"}) == "2026-03-04"
    assert generate.data_de_atualizacao({}) is None


def test_CONTROLE_post_so_com_o_apelido_sai_igual_nos_tres(monkeypatch):
    """Prova que o teste de cima reprova a divergência: um post que só declara
    `updated` (o campo que o sitemap lia antes) tem que sair com a MESMA data no
    JSON-LD — antes sairia com a data de publicação."""
    base = dict(_publicados()[0])
    base.pop("update_date", None)
    base["updated"] = "2026-09-20"
    base["publish_date"] = "2026-01-10"
    monkeypatch.setattr(generate, "POSTS", [base])
    html = generate.render_post_html(dict(base))
    assert _artigo(html)["dateModified"][:10] == "2026-09-20"
    assert _lastmods(generate.render_sitemap()).get(base["slug"]) == "2026-09-20"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
