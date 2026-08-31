#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trava de deploy: recusa o push enquanto houver projeto processando.

Pedido do Pedro em 03/08/2026: *"vamos fazer alguma trava no sistema que se
tiver projeto em andamento, nenhum deploy sobe pra travar"*.

Por que existe: push na main dispara deploy automático no Render, o servidor
reinicia e o job que estava no meio MORRE. Aconteceu com o Walter (29/07) e em
03/08 escapou por 4 minutos do projeto da Eloídes — que levou 4,4 min.

Como funciona: lê `jobs_em_curso` do /api/health (público de propósito, sem
credencial) e sai com código != 0 se houver job rodando. O git aborta o push.

🔒 Falha FECHA a porta: se o health não responder, se o campo não existir ou se
vier negativo, o push é bloqueado. "Não consegui saber" não pode virar "pode
subir" — é justamente o erro que a trava existe pra impedir.

Emergência (deploy que CONSERTA algo quebrado, quando esperar é pior):
    AIARQ_DEPLOY_FORCE=1 git push origin main

Instalar como hook:
    python scripts/guard_deploy.py --instalar
"""
import json
import os
import sys
import urllib.request

# 🪤 O console do Windows é cp1252 e explode em emoji: na 1ª execução real a
# trava bloqueou certo, mas MORREU no print e cuspiu um traceback no lugar da
# explicação. Bloquear com mensagem ilegível é quase tão ruim quanto não
# bloquear — quem lê não sabe o que fazer.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HEALTH = os.environ.get("AIARQ_HEALTH_URL",
                        "https://ai-arq.onrender.com/api/health")
TIMEOUT = 20

HOOK = """#!/bin/sh
# Trava de deploy do AI.arq — nao subir codigo com projeto processando.
# Gerado por scripts/guard_deploy.py --instalar
exec python "$(git rev-parse --show-toplevel)/scripts/guard_deploy.py"
"""


def instalar() -> int:
    import subprocess
    raiz = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True).strip()
    caminho = os.path.join(raiz, ".git", "hooks", "pre-push")
    with open(caminho, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HOOK)
    try:
        os.chmod(caminho, 0o755)
    except Exception:
        pass          # Windows ignora modo; o Git Bash executa mesmo assim
    print(f"✓ hook instalado em {caminho}")
    return 0


def main() -> int:
    if "--instalar" in sys.argv:
        return instalar()

    if os.environ.get("AIARQ_DEPLOY_FORCE") == "1":
        print("⚠ AIARQ_DEPLOY_FORCE=1 — trava ignorada de propósito. "
              "Se havia job rodando, ele vai morrer.")
        return 0

    try:
        req = urllib.request.Request(HEALTH, headers={"User-Agent": "aiarq-deploy-guard"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"\n🚦 PUSH BLOQUEADO — não consegui falar com o backend ({e}).")
        print("   Não dá pra saber se tem cliente processando agora.")
        print("   Tente de novo em 1 minuto, ou force: AIARQ_DEPLOY_FORCE=1 git push\n")
        return 1

    n = dados.get("jobs_em_curso")
    if n is None:
        print("\n🚦 PUSH BLOQUEADO — o backend no ar ainda não expõe 'jobs_em_curso'.")
        print("   (Normal só no primeiro deploy desta trava.)")
        print("   Confira o painel e force: AIARQ_DEPLOY_FORCE=1 git push\n")
        return 1

    # Uploads em curso contam como cliente ativo: o arquivo ainda está subindo e
    # a linha do projeto nem existe. Campo ausente = backend anterior à v2 da
    # trava; trata como 0 pra não bloquear tudo, mas o job já cobre o essencial.
    u = dados.get("uploads_em_curso") or 0

    if n < 0 or u < 0:
        print("\n🚦 PUSH BLOQUEADO — o backend não conseguiu contar os jobs.")
        print("   Na dúvida, não sobe.\n")
        return 1

    if n > 0 or u > 0:
        partes = []
        if n:
            partes.append(f"{n} projeto{'s' if n > 1 else ''} processando")
        if u:
            partes.append(f"{u} arquivo{'s' if u > 1 else ''} subindo agora")
        print(f"\n🚦 PUSH BLOQUEADO — {' e '.join(partes)}.")
        print("   Deploy reinicia o servidor e MATA o trabalho do cliente no meio")
        print("   (caso Walter, 29/07). Upload grande passa minutos aqui — o DXF")
        print("   de 112 MB de 03/08 levou vários. Espere e tente de novo.")
        print("   Emergência: AIARQ_DEPLOY_FORCE=1 git push origin main\n")
        return 1

    print("✓ nenhum cliente ativo (0 processando, 0 subindo) — pode subir")

    # 🔒 31/08/2026 — 2ª trava: contrato do front. Um recorte que deixou
    # uma chave pra trás matou o LOGIN em produção por 12 min, com sintaxe
    # válida e zero erro no console. Nenhum teste de fonte pega isso; só
    # carregar num browser de verdade pega. Roda só se o JS vigiado mudou.
    # 🔒 31/08/2026 — 3ª trava: as PÁGINAS carregam? O contrato do front cobre o
    # JS compartilhado, mas os HTMLs têm milhares de linhas de JS inline que
    # nenhum guarda olhava (pyflakes não vê JS; a bancada lê o FONTE). Roda só
    # se uma página vigiada mudou.
    _sub = os.path.dirname(os.path.abspath(__file__))
    for _script, _oque in (("guard_front_contrato.py", "o contrato do front"),
                           ("guard_paginas_carregam.py", "o carregamento das páginas")):
        try:
            import subprocess as _sp
            _r = _sp.run([sys.executable, os.path.join(_sub, _script)], timeout=420)
            if _r.returncode != 0:
                sys.exit(1)
        except SystemExit:
            raise
        except Exception as _e:
            print(f"\n🚦 PUSH BLOQUEADO — não consegui verificar {_oque} "
                  f"({type(_e).__name__}). Falha FECHA a porta.")
            sys.exit(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
