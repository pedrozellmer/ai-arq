# -*- coding: utf-8 -*-
"""Publica o MOTIVO de um smoke vermelho onde qualquer um consiga ler.

🚨 25/08/2026. O smoke ficou vermelho no commit 2cccde0 e eu não consegui
descobrir por quê: o log do Actions exige `actions:read` de admin, e a API
devolve 403 mesmo em repositório público. As anotações públicas trazem só a
frase genérica "Smoke test falhou — verifique deploy do Render". Sobrou pedir
print pro Pedro, do celular.

🕳️ É o buraco do "evidência não sobrevive", de novo: a informação existiu por
4 segundos dentro de um runner e morreu lá. Um alarme que não diz o que houve
custa o mesmo que alarme nenhum, e ainda gasta o tempo de outra pessoa.

Aqui o resumo vira COMENTÁRIO DE COMMIT — que é público e legível pela API sem
credencial nenhuma. Fallback no resumo do job, que o Pedro vê no celular.

🚨 O repositório é PÚBLICO. O nível 2 loga com um usuário real e imprime o
e-mail dele; o nível 3 abre o site logado. Nada disso pode vazar num comentário
público, então tudo passa por `_limpar()` antes — e o teste do lado
(`test_smoke_nao_vaza_dado.py`) prova que passa.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

_LOG = os.environ.get("SMOKE_LOG", "smoke.log")
_REPO = os.environ.get("GITHUB_REPOSITORY", "")
_SHA = os.environ.get("GITHUB_SHA", "")
_TOKEN = os.environ.get("GH_TOKEN", "")
_RUN_URL = "%s/%s/actions/runs/%s" % (
    os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
    _REPO, os.environ.get("GITHUB_RUN_ID", ""))

# ── o que NUNCA pode sair daqui ────────────────────────────────────────────
_LIMPEZAS = (
    # e-mail de cliente/tester — o nível 2 imprime o do SMOKE_USER
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<email-oculto>"),
    # JWT do Supabase (3 blocos base64 separados por ponto)
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
     "<jwt-oculto>"),
    # qualquer coisa com cara de chave/token solta
    (re.compile(r"\b(?:sk|rk|pk)[-_][A-Za-z0-9_-]{16,}"), "<chave-oculta>"),
    (re.compile(r"(?i)\b(password|senha|secret|token)\s*[=:]\s*\S+"),
     r"\1=<oculto>"),
)


def _limpar(texto: str) -> str:
    for rx, troca in _LIMPEZAS:
        texto = rx.sub(troca, texto)
    return texto


def _so_o_que_interessa(bruto: str, teto: int = 60) -> str:
    """As linhas que explicam a falha, sem o ruído do resto do log."""
    # o script usa ✗ pro que falhou e imprime um bloco "Falhas:" no fim
    linhas = [l.rstrip() for l in bruto.splitlines()]
    marcados = [l for l in linhas
                if ("✗" in l or "Falhas" in l or "FALHOU" in l
                    or l.strip().startswith("- ")
                    or "Traceback" in l or "Error" in l)]
    escolhidas = marcados or linhas[-teto:]
    return "\n".join(escolhidas[-teto:])


def _comentar(corpo: str) -> bool:
    if not (_TOKEN and _REPO and _SHA):
        print("[smoke-report] sem GH_TOKEN/repo/sha — pulando comentário")
        return False
    url = "https://api.github.com/repos/%s/commits/%s/comments" % (_REPO, _SHA)
    dados = json.dumps({"body": corpo}).encode("utf-8")
    req = urllib.request.Request(url, data=dados, method="POST")
    req.add_header("Authorization", "Bearer %s" % _TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        print("[smoke-report] comentário publicado (HTTP %s)" % resp.getcode())
        return True
    except urllib.error.HTTPError as e:
        # 🪤 Se o GITHUB_TOKEN do repo estiver como read-only, isto dá 403. Não
        # pode derrubar o job: o job JÁ está vermelho pelo motivo certo, e
        # falhar aqui trocaria a causa real por "não consegui comentar".
        print("[smoke-report] não consegui comentar (HTTP %s): %s"
              % (e.code, e.read().decode("utf-8", "replace")[:200]))
    except Exception as e:
        print("[smoke-report] não consegui comentar: %s: %s" % (type(e).__name__, e))
    return False


def main() -> int:
    if not os.path.exists(_LOG):
        print("[smoke-report] sem %s — nada a relatar" % _LOG)
        return 0
    bruto = open(_LOG, encoding="utf-8", errors="replace").read()
    resumo = _limpar(_so_o_que_interessa(bruto))

    corpo = (
        "### 🚦 Smoke test vermelho\n\n"
        "O que falhou, direto do log (e-mail e token removidos):\n\n"
        "```\n%s\n```\n\n"
        "[Execução completa](%s)\n\n"
        "<sub>Publicado automaticamente porque o log do Actions exige admin e "
        "o motivo da falha morria dentro do runner.</sub>" % (resumo, _RUN_URL))

    # fallback que o Pedro vê no celular, mesmo se o comentário for barrado
    resumo_job = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo_job:
        try:
            with open(resumo_job, "a", encoding="utf-8") as fh:
                fh.write(corpo + "\n")
        except Exception as e:
            print("[smoke-report] resumo do job falhou: %s" % e)

    _comentar(corpo)
    print(resumo)
    return 0        # nunca derruba o job: a falha real já é a do smoke


if __name__ == "__main__":
    sys.exit(main())
