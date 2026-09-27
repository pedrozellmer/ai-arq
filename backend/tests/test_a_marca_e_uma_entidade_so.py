# -*- coding: utf-8 -*-
"""A marca é UMA entidade nos dados estruturados — e não arrasta pessoa junto.

🔗 26/09/2026 (auditoria de aquisição, item 2): a home, o índice do blog e os 31
posts declaravam cada um a sua "Organization AI.arq" solta — com logos
diferentes (og-image 1200×630 na home, favicon 32×32 no blog, abaixo do mínimo
de 112 px que o Google pede) e sem nada que dissesse que era a mesma. O `@id`
(`https://ai.arq.br/#org`) é o que amarra: o nó completo (sameAs, e-mail, logo)
mora no publisher do index.html, e todo o resto aponta pra ele.

🚫 Pessoa fica FORA. Pedro, 26/09: *"só não quero vincular ao meu perfil
ainda"*. O rodapé já identifica o prestador do serviço (obrigação legal), mas
`founder`/`Person` nos dados estruturados é outra coisa: liga pessoa e empresa
explicitamente pro Google e pras IAs. Mudar isso é decisão dele — se ele pedir,
este guarda muda junto, com a data.
"""
import glob
import io
import json
import os
import re
import struct

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITE = "https://ai.arq.br"
ORG = SITE + "/#org"
_RE_LD = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)


def _ler(rel):
    return io.open(os.path.join(_RAIZ, rel), encoding="utf-8").read()


def _paginas_com_dados():
    """Toda página servida que carrega JSON-LD: raiz + blog."""
    fora = [os.path.basename(p) for p in glob.glob(os.path.join(_RAIZ, "*.html"))]
    fora += [os.path.relpath(p, _RAIZ).replace(os.sep, "/")
             for p in glob.glob(os.path.join(_RAIZ, "blog", "**", "*.html"), recursive=True)]
    return [p for p in sorted(fora) if _RE_LD.search(_ler(p))]


def _blocos(texto):
    return [json.loads(b) for b in _RE_LD.findall(texto)]


def _nos(obj):
    """Todos os dicionários de um JSON-LD, em qualquer profundidade."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _nos(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _nos(v)


def _png_lado(rel):
    with open(os.path.join(_RAIZ, rel), "rb") as f:
        cab = f.read(24)
    assert cab[:8] == b"\x89PNG\r\n\x1a\n", "%s não é PNG" % rel
    return struct.unpack(">II", cab[16:24])


def _org_da_home():
    blocos = _blocos(_ler("index.html"))
    assert blocos[0].get("@type") == "SoftwareApplication", \
        "o SoftwareApplication tem que continuar o 1º bloco (guarda do público da landing lê o 1º)"
    pub = blocos[0].get("publisher") or {}
    assert pub.get("@id") == ORG, "o publisher da home perdeu o @id %s" % ORG
    return pub


def test_a_home_define_a_organizacao_completa():
    pub = _org_da_home()
    assert pub.get("@type") == "Organization" and pub.get("name") == "AI.arq", pub
    assert pub.get("url") == SITE + "/", pub.get("url")
    assert pub.get("email") == "contato@ai.arq.br", pub.get("email")
    assert "https://www.linkedin.com/company/aiarq/" in (pub.get("sameAs") or []), pub.get("sameAs")


def test_o_logo_da_marca_existe_e_passa_do_minimo_do_google():
    logo = (_org_da_home().get("logo") or {})
    url = logo.get("url") or ""
    assert url.startswith(SITE + "/"), url
    rel = url[len(SITE) + 1:]
    w, h = _png_lado(rel)
    assert w == h and w >= 112, "logo %s tem %dx%d — o Google pede ≥112 px" % (rel, w, h)
    assert (logo.get("width"), logo.get("height")) == (w, h), \
        "o JSON-LD declara %sx%s e o arquivo tem %dx%d" % (logo.get("width"), logo.get("height"), w, h)


def _orgs_divergentes(textos_por_pagina):
    """Organization chamada AI.arq sem o @id da marca, ou com logo diferente do da home."""
    logo_home = (_org_da_home().get("logo") or {}).get("url")
    ruins = []
    for p, texto in textos_por_pagina:
        for bloco in _blocos(texto):
            for n in _nos(bloco):
                if n.get("@type") == "Organization" and n.get("name") == "AI.arq":
                    if n.get("@id") != ORG:
                        ruins.append("%s: Organization AI.arq sem @id %s" % (p, ORG))
                    elif "logo" in n and (n["logo"] or {}).get("url") != logo_home:
                        ruins.append("%s: logo da marca diferente do da home" % p)
    return ruins


def test_toda_organization_ai_arq_e_a_mesma():
    paginas = _paginas_com_dados()
    assert len(paginas) >= 30, "piso: home + FAQ + blog tinham 34 páginas com JSON-LD em 26/09; achei %d" % len(paginas)
    ruins = _orgs_divergentes([(p, _ler(p)) for p in paginas])
    assert not ruins, "\n".join(ruins)


def _ids_quebrados(textos_por_pagina):
    """@id do nosso domínio que é referenciado ({"@id": ...} sozinho) e não é
    definido (nó com @id E @type) em página nenhuma."""
    definidos, usados = set(), []
    for p, texto in textos_por_pagina:
        for bloco in _blocos(texto):
            for n in _nos(bloco):
                i = n.get("@id")
                if not isinstance(i, str) or not i.startswith(SITE + "/#"):
                    continue
                if "@type" in n:
                    definidos.add(i)
                else:
                    usados.append((p, i))
    return ["%s aponta pra %s, que nenhuma página define" % (p, i) for p, i in usados if i not in definidos]


def test_todo_id_referenciado_existe():
    textos = [(p, _ler(p)) for p in _paginas_com_dados()]
    ruins = _ids_quebrados(textos)
    assert not ruins, "\n".join(ruins)


def _pessoas(textos_por_pagina):
    ruins = []
    for p, texto in textos_por_pagina:
        for bloco in _blocos(texto):
            for n in _nos(bloco):
                if n.get("@type") == "Person" or any(k in n for k in ("founder", "founders", "employee", "employees")):
                    ruins.append(p)
    return sorted(set(ruins))


def test_nenhum_dado_estruturado_liga_pessoa_a_marca():
    ruins = _pessoas([(p, _ler(p)) for p in _paginas_com_dados()])
    assert not ruins, (
        "JSON-LD com Person/founder em %s — o Pedro pediu em 26/09 pra não vincular "
        "o perfil dele à empresa ainda. Só muda com o ok dele." % ruins)


def test_a_pagina_sobre_esta_no_sitemap_no_llms_e_no_rodape():
    assert "<loc>%s/sobre.html</loc>" % SITE in _ler("sitemap.xml")
    assert "%s/sobre.html" % SITE in _ler("llms.txt")
    assert 'href="sobre.html"' in _ler("index.html"), "a home não linka o /sobre"
    assert 'href="/sobre.html"' in _ler("blog/index.html"), "o rodapé do blog não linka o /sobre"


# ── CONTROLES: o mesmo julgamento nos casos ruins ──────────────────────────────

def test_CONTROLE_id_com_erro_de_digitacao_e_pego():
    home = _ler("index.html")
    ruim = '<script type="application/ld+json">{"@type":"Article","publisher":{"@id":"%s/#orgs"}}</script>' % SITE
    assert _ids_quebrados([("index.html", home), ("post.html", ruim)]) == \
        ["post.html aponta pra %s/#orgs, que nenhuma página define" % SITE]


def test_CONTROLE_fundador_e_pego():
    ruim = ('<script type="application/ld+json">{"@type":"Organization","@id":"%s",'
            '"name":"AI.arq","founder":{"@type":"Person","name":"Fulano"}}</script>' % ORG)
    assert _pessoas([("x.html", ruim)]) == ["x.html"]


def test_CONTROLE_organizacao_solta_e_pega():
    ruim = '<script type="application/ld+json">{"@type":"Blog","publisher":{"@type":"Organization","name":"AI.arq"}}</script>'
    assert _orgs_divergentes([("blog.html", ruim)]) == \
        ["blog.html: Organization AI.arq sem @id %s" % ORG]
