#!/usr/bin/env python3
"""Confere se alguma página do site está quebrada — nos DOIS níveis.

Por que existe: em 13/08/2026 eu quebrei o admin com um `const` duplicado. A
página respondia **HTTP 200** e estava **completamente em branco** — erro de
sintaxe derruba o <script> inteiro e o navegador não mostra nada. Só o Pedro
percebeu, testando na mão.

Nível 1  — a página responde? (pega 404, deploy que não subiu)
Nível 2  — o JavaScript dela COMPILA? (pega o caso acima, que o nível 1 ignora)

🪤 `application/ld+json` NÃO é JavaScript. É o dado estruturado do Google, e
compilar como JS dá "Unexpected token ':'" — falso positivo em faq/index/precos.
Esses blocos são validados como JSON.

Uso:  python scripts/checa_paginas.py [--local]
      --local usa http://localhost:8090 (preview) em vez do site no ar.
"""
import glob
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

# 🪤 Console do Windows é cp1252 e MORRE no emoji — o script já quebrou assim na
# estreia (mesmo tropeço do guard_deploy em 03/08). Sem isto, um alerta legítimo
# vira traceback e ninguém lê o resultado.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "http://localhost:8090" if "--local" in sys.argv else "https://ai.arq.br"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXTRA = ["blog/index.html", "sitemap.xml", "robots.txt"]


def _http(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "aiarq-checa/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return f"ERRO {type(e).__name__}", ""


def _blocos_script(html):
    """(tipo, conteudo) de cada <script> SEM src."""
    out = []
    for m in re.finditer(r"<script([^>]*)>(.*?)</script>", html, re.S | re.I):
        attrs, corpo = m.group(1), m.group(2)
        if re.search(r"\bsrc\s*=", attrs, re.I):
            continue
        t = re.search(r'type\s*=\s*["\']([^"\']+)', attrs, re.I)
        out.append(((t.group(1) if t else "javascript").lower(), corpo))
    return out


def _js_compila(codigo):
    """True se o JS compila. Usa node se existir; senão devolve None (pulou)."""
    try:
        p = subprocess.run(["node", "--check", "-"], input=codigo, text=True,
                           capture_output=True, timeout=30)
        return p.returncode == 0, (p.stderr or "").strip()[:160]
    except FileNotFoundError:
        return None, "node ausente"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def main():
    paginas = sorted(os.path.basename(p) for p in glob.glob(os.path.join(RAIZ, "*.html")))
    alvos = paginas + EXTRA
    print(f"Conferindo {len(alvos)} endereços em {BASE}\n")

    quebradas, js_ruim, json_ruim, pulados = [], [], [], 0

    for p in alvos:
        status, html = _http(f"{BASE}/{p}")
        if status != 200:
            print(f"  🚨 {status}  {p}")
            quebradas.append(p)
            continue
        if not p.endswith(".html"):
            print(f"  ok   {p}")
            continue

        n_js = n_json = 0
        for tipo, corpo in _blocos_script(html):
            if not corpo.strip():
                continue
            if "json" in tipo:
                n_json += 1
                try:
                    json.loads(corpo)
                except Exception as e:
                    json_ruim.append((p, str(e)[:90]))
            else:
                n_js += 1
                ok, msg = _js_compila(corpo)
                if ok is None:
                    global _sem_node
                    _sem_node = True
                elif not ok:
                    js_ruim.append((p, msg))
        print(f"  ok   {p:26} {n_js} js · {n_json} json-ld")

    print("\n" + "=" * 58)
    print(f"  fora do ar        : {len(quebradas)}")
    print(f"  JS que não compila: {len(js_ruim)}")
    print(f"  JSON-LD inválido  : {len(json_ruim)}")
    for p, m in js_ruim:
        print(f"    🚨 {p}: {m}")
    for p, m in json_ruim:
        print(f"    🚨 {p} (json-ld): {m}")
    if quebradas or js_ruim or json_ruim:
        return 1

    # 🚨 "Não consegui checar" NUNCA pode virar "está tudo certo" — é a mesma
    # regra do guard de deploy. Sem node, o nível 2 não roda, e é ELE que pega
    # o caso do admin em branco respondendo 200. Sai com código 2 pra não ser
    # confundido com sucesso.
    if globals().get("_sem_node"):
        print("\n  ⚠ ATENÇÃO: node não encontrado — a checagem de JAVASCRIPT")
        print("    foi PULADA. O nível 1 (página responde) passou, mas ele NÃO")
        print("    pega página em branco por erro de sintaxe. Confira no")
        print("    navegador antes de dizer que está tudo certo.")
        return 2
    print("\n  tudo certo: páginas no ar E JavaScript compilando.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
