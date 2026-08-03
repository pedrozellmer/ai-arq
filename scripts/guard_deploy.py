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

    if n < 0:
        print("\n🚦 PUSH BLOQUEADO — o backend não conseguiu contar os jobs.")
        print("   Na dúvida, não sobe.\n")
        return 1

    if n > 0:
        plural = "projeto" if n == 1 else "projetos"
        print(f"\n🚦 PUSH BLOQUEADO — {n} {plural} processando agora.")
        print("   Deploy reinicia o servidor e MATA o job do cliente no meio")
        print("   (caso Walter, 29/07). Espere terminar — costuma levar ~5 min.")
        print("   Emergência: AIARQ_DEPLOY_FORCE=1 git push origin main\n")
        return 1

    print("✓ nenhum projeto processando — pode subir")
    return 0


if __name__ == "__main__":
    sys.exit(main())
