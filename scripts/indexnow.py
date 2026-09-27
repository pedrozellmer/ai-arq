# -*- coding: utf-8 -*-
"""Avisa o IndexNow quando um post do blog publica (auditoria de aquisição, 26/09).

IndexNow é o protocolo aberto em que o site avisa os buscadores (Bing, Yandex,
Seznam, Naver…) de que uma URL nova existe, em vez de esperar o robô voltar.
O Bing alimenta o Copilot — e parte dos cadastros de setembro veio do bing.com.

Como funciona aqui:
- A CHAVE fica num arquivo PÚBLICO na raiz do site (`<CHAVE>.txt`, com a chave
  dentro). É assim que o protocolo prova que o domínio é nosso — por isso ela
  pode e precisa estar no repositório público. O deploy copia o arquivo (ver a
  lista de .txt em .github/workflows/deploy-pages.yml).
- O deploy roda este script DEPOIS de publicar, só na rotina diária das 06:00
  (e no disparo manual) — nunca a cada push, pra não repetir a mesma URL no dia.
- Só avisa se algum post tem `publish_date` == hoje (relógio de Brasília,
  `hoje_editorial()` do blog). Vai a URL do post e a do índice do blog.
- NUNCA derruba o deploy: falha de rede ou recusa vira aviso no log e sai 0
  (o passo também tem continue-on-error). O site já está no ar a essa altura.

Uso manual:  python scripts/indexnow.py            (avisa, se houver post hoje)
             python scripts/indexnow.py --simular  (só mostra o que mandaria)
"""
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://ai.arq.br"
HOST = "ai.arq.br"
CHAVE = "e80464316e21cbae44578ac25816c460"
ENDPOINT = "https://api.indexnow.org/indexnow"


def _blog():
    spec = importlib.util.spec_from_file_location(
        "generate_indexnow", os.path.join(RAIZ, "blog", "generate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def urls_do_dia(posts, hoje, site=SITE):
    """URLs a avisar: os posts que publicam HOJE e, se houver algum, o índice."""
    novos = [p for p in posts if p["publish_date"] == hoje]
    if not novos:
        return []
    return ["%s/blog/posts/%s.html" % (site, p["slug"]) for p in novos] + [site + "/blog/"]


def corpo(urls):
    return {"host": HOST, "key": CHAVE, "keyLocation": "%s/%s.txt" % (SITE, CHAVE), "urlList": urls}


def enviar(dados, abrir=urllib.request.urlopen):
    """POST no IndexNow. Devolve o status HTTP (200/202 = aceito)."""
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(dados).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"})
    with abrir(req, timeout=30) as r:
        return r.status


def main(argv, abrir=urllib.request.urlopen):
    blog = _blog()
    hoje = blog.hoje_editorial().isoformat()
    urls = urls_do_dia(blog.POSTS, hoje)
    if not urls:
        print("IndexNow: nenhum post publica hoje (%s) — nada a avisar" % hoje)
        return 0
    print("IndexNow: %d URL(s) de %s: %s" % (len(urls), hoje, ", ".join(urls)))
    if "--simular" in argv:
        print(json.dumps(corpo(urls), ensure_ascii=False, indent=2))
        return 0
    try:
        status = enviar(corpo(urls), abrir)
    except urllib.error.HTTPError as e:
        # 403 = chave não achada no site; 422 = URL fora do host/chave errada; 429 = excesso
        print("⚠ IndexNow recusou (HTTP %s) — o site está no ar; conferir a chave/URLs" % e.code)
        return 0
    except Exception as e:  # rede, DNS, timeout: não é motivo pra falhar o deploy
        print("⚠ IndexNow não respondeu (%s: %s) — o site está no ar" % (type(e).__name__, e))
        return 0
    print("IndexNow: HTTP %s %s" % (status, "(aceito)" if status in (200, 202) else "(inesperado)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
