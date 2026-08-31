#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vigia o CI de um commit e diz, sem rodeio, se passou.

Pedro, 29/08/2026: *"Vc tem que ficar de olhos nesses erros, pra eu nao
precisar ficar te mandando"*. O CI vermelho e MEU de achar.

Por que virou script: em 31/08 eu vigiei com um laco de shell improvisado. Ele
saiu na PRIMEIRA volta, sem resultado nenhum, e **terminou com codigo 0** — do
lado de fora isso e indistinguivel de "passou". Guarda que falha calado e o
defeito que a casa inteira persegue; nao da pra ter um no vigia.

Armadilhas ja pagas, todas cobertas aqui:
  - `gh` NAO existe nesta maquina (nem no bash nem no PowerShell). Usa a API
    publica do GitHub, que atende repo publico sem token.
  - `?branch=main` devolve ordem que NAO e a do push: em 31/08 trouxe um commit
    antigo no topo e eu quase li como se fosse o meu. Consulta sempre por
    `head_sha` do commit exato.
  - Run que ainda nao registrou devolve lista VAZIA — isso e "nao sei", nunca
    "passou". Sem veredito ate o fim = saida 2.

Uso:
    python scripts/vigia_ci.py              # HEAD local
    python scripts/vigia_ci.py <sha>
Saida: 0 tudo verde | 1 algum vermelho | 2 nao consegui saber (trate como 1).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

REPO = "pedrozellmer/ai-arq"
ESPERADOS = {"Bancada (pytest)", "Deploy site to GitHub Pages"}
LIMITE_S = int(os.environ.get("AIARQ_VIGIA_LIMITE_S", "900"))   # 15 min
                        # (env so pra testar o caminho "nao sei" sem esperar)
INTERVALO_S = 20

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _runs(sha):
    url = f"https://api.github.com/repos/{REPO}/actions/runs?head_sha={sha}"
    req = urllib.request.Request(url, headers={"User-Agent": "aiarq-vigia-ci",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")).get("workflow_runs", [])


def main():
    sha = sys.argv[1] if len(sys.argv) > 1 else None
    if not sha:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    sha = subprocess.check_output(["git", "rev-parse", sha], text=True).strip()
    print(f"vigiando {sha[:7]} …")

    fim = time.monotonic() + LIMITE_S
    ultimo = {}
    while time.monotonic() < fim:
        try:
            rs = _runs(sha)
        except Exception as e:
            print(f"  (API falhou: {e}; tento de novo)")
            time.sleep(INTERVALO_S)
            continue
        # ultimo run de cada workflow (a API devolve o mais novo primeiro)
        ultimo = {}
        for r in rs:
            ultimo.setdefault(r["name"], r)
        pendente = [n for n, r in ultimo.items() if r["status"] != "completed"]
        faltando = ESPERADOS - set(ultimo)
        if not pendente and not faltando:
            break
        time.sleep(INTERVALO_S)

    if not ultimo:
        print(f"\n🚦 NAO SEI se o CI passou em {sha[:7]}: nenhum run registrado "
              f"em {LIMITE_S//60} min. Isso NAO e 'passou'.")
        return 2
    faltando = ESPERADOS - set(ultimo)
    ruins, abertos = [], []
    for nome, r in sorted(ultimo.items()):
        st, cc = r["status"], r.get("conclusion")
        marca = "✓" if cc == "success" else ("…" if st != "completed" else "✗")
        print(f"  {marca} {nome}: {cc or st}")
        if st != "completed":
            abertos.append(nome)
        elif cc != "success":
            ruins.append(nome)
    if faltando:
        print(f"\n🚦 workflow esperado que nem apareceu: {', '.join(sorted(faltando))}")
    if ruins:
        print(f"\n🚨 CI VERMELHO em {sha[:7]}: {', '.join(ruins)}")
        print(f"   https://github.com/{REPO}/actions")
        return 1
    if abertos or faltando:
        print(f"\n🚦 sem veredito ({', '.join(abertos + sorted(faltando))}). Trate como vermelho.")
        return 2
    print(f"\n✓ CI verde em {sha[:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
