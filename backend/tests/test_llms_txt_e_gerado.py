# -*- coding: utf-8 -*-
"""O /llms.txt é GERADO com o blog — e cada post tem a sua linha curada.

🩸 27/09/2026 (auditoria de aquisição, item 3): escrito à mão, o llms.txt
listava 16 dos 24 posts publicados. Oito posts inteiros — BDI, NBR 9050,
memorial para CAU, quadro de áreas, financiamento Caixa… — não existiam para
quem lê o site pelo llms.txt, que é justamente o leitor de IA.

Desde então `blog/generate.py` escreve o arquivo a partir de
`blog/gerar_llms.py` (cabeçalho + uma linha curada por post), pela mesma regra
de data do sitemap, e o deploy diário o regenera. Este guarda exige:
- o arquivo commitado = o que o gerador produz hoje;
- linha curada para TODO post do posts.json, inclusive os agendados — assim
  o post que vence de madrugada entra com texto escrito, e o CI não fica
  vermelho por causa da data.
"""
import importlib.util
import io
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BLOG = os.path.join(_RAIZ, "blog")


def _carregar(nome):
    spec = importlib.util.spec_from_file_location(nome + "_sob_teste", os.path.join(_BLOG, nome + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GEN = _carregar("generate")
LL = _carregar("gerar_llms")
HOJE = GEN.hoje_editorial().isoformat()
_URL = re.compile(r"\]\(https://ai\.arq\.br/blog/posts/([a-z0-9-]+)\.html\)")


def _slugs_no_texto(txt):
    return _URL.findall(txt)


def test_o_llms_commitado_e_o_que_o_gerador_produz():
    no_repo = io.open(os.path.join(_RAIZ, "llms.txt"), encoding="utf-8").read().replace("\r\n", "\n")
    assert no_repo == GEN.render_llms().replace("\r\n", "\n"), (
        "llms.txt difere do que blog/generate.py produz hoje — rode "
        "`python blog/generate.py` (e, se mudou o texto, mude em blog/gerar_llms.py)")


def _sem_linha(posts):
    return [p["slug"] for p in posts if p["slug"] not in LL.LINHAS]


def test_todo_post_tem_linha_curada_inclusive_os_agendados():
    falta = _sem_linha(GEN.POSTS)
    assert not falta, (
        "post sem linha no blog/gerar_llms.py (LINHAS): %s — ele entraria no "
        "llms.txt com a description crua, em 'Outros artigos'" % falta)
    orfas = sorted(set(LL.LINHAS) - {p["slug"] for p in GEN.POSTS})
    assert not orfas, "linha curada de post que não existe mais no posts.json: %s" % orfas


def test_toda_linha_esta_numa_secao_conhecida_e_tem_texto():
    for slug, (secao, titulo, resumo) in LL.LINHAS.items():
        assert secao in LL.SECOES + ["Optional"], (slug, secao)
        assert titulo.strip() and len(resumo) >= 40, (slug, titulo, resumo)


def test_publicado_aparece_uma_vez_e_agendado_nao_aparece():
    txt = LL.montar(GEN.POSTS, HOJE)
    slugs = _slugs_no_texto(txt)
    publicados = {p["slug"] for p in GEN.POSTS if p["publish_date"] <= HOJE}
    agendados = {p["slug"] for p in GEN.POSTS if p["publish_date"] > HOJE}
    assert len(publicados) >= 24, "piso: eram 24 publicados em 27/09; achei %d" % len(publicados)
    assert sorted(slugs) == sorted(publicados), (
        "faltando: %s | sobrando: %s" % (sorted(publicados - set(slugs)), sorted(set(slugs) - publicados)))
    assert not agendados & set(slugs), "post agendado vazou pro llms.txt: %s" % (agendados & set(slugs))


def test_optional_e_a_ultima_secao():
    txt = LL.montar(GEN.POSTS, HOJE)
    secoes = re.findall(r"^## (.+)$", txt, re.M)
    assert secoes[-1] == "Optional", secoes
    assert secoes[0] == "Comece por aqui", secoes


def test_a_data_do_arquivo_acompanha_o_conteudo():
    txt = LL.montar(GEN.POSTS, HOJE)
    m = re.search(r"Última atualização deste arquivo: (\d{4}-\d{2}-\d{2})\.", txt)
    assert m, "sumiu a data de atualização do cabeçalho"
    publicados = [p for p in GEN.POSTS if p["publish_date"] <= HOJE]
    esperado = max([LL.REVISADO_EM] + [p.get("update_date") or p.get("updated") or p["publish_date"]
                                      for p in publicados])
    assert m.group(1) == esperado and esperado <= HOJE, (m.group(1), esperado, HOJE)


# ── CONTROLES ────────────────────────────────────────────────────────────────

def _post_falso(slug, data):
    return {"slug": slug, "title": "Post falso " + slug, "description": "descrição do post falso",
            "publish_date": data}


def test_CONTROLE_post_de_amanha_nao_entra():
    txt = LL.montar(GEN.POSTS + [_post_falso("post-do-futuro", "2999-01-01")], HOJE)
    assert "post-do-futuro" not in txt


def test_CONTROLE_post_sem_linha_entra_em_outros_e_o_guarda_acusa():
    falso = _post_falso("post-sem-linha", "2000-01-01")
    txt = LL.montar(GEN.POSTS + [falso], HOJE)
    assert "## Outros artigos" in txt and "post-sem-linha" in txt
    assert _sem_linha(GEN.POSTS + [falso]) == ["post-sem-linha"]
