# -*- coding: utf-8 -*-
"""Diagnóstico e renovação do token do Instagram.

Por que este arquivo existe: em 06/09/2026 descobriu-se que
`refresh_long_lived_token()` (a) chamava o endpoint errado e nunca funcionou, e
(b) não era chamada por ninguém. Ou seja, o token deste projeto nunca teve
renovação automática — o que dá certo até o dia em que dá muito errado, porque
token de Instagram Login que passa 60 dias sem refresh MORRE EM DEFINITIVO e só
volta com Business Login manual.

Uso:
    python token_status.py              # só olha, não muda nada
    python token_status.py --renovar    # renova e imprime o novo token

⚠ O token novo NÃO é gravado em lugar nenhum por este script, de propósito:
gravar em .env ou em banco é decisão de deploy, e um script de diagnóstico que
escreve segredo por conta própria é pior que o problema que resolve. Copie o
valor impresso para a variável META_ACCESS_TOKEN onde ela vive.
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from instagram_api import MetaGraphAPI  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--renovar", action="store_true",
                    help="renova o token (só funciona se ele ainda estiver vivo)")
    args = ap.parse_args()

    token = os.getenv("META_ACCESS_TOKEN", "")
    ig_user = os.getenv("IG_USER_ID", "")
    if not token or not ig_user:
        print("META_ACCESS_TOKEN ou IG_USER_ID ausente no ambiente.")
        return 1

    api = MetaGraphAPI(access_token=token, ig_user_id=ig_user,
                       app_secret=os.getenv("META_APP_SECRET"))

    print(f"conta ......... {ig_user}")
    print(f"token ......... …{token[-8:]}  ({len(token)} chars)")
    print(f"versão da API . {os.getenv('GRAPH_API_VERSION', 'v21.0')}"
          "   (v21.0 é desativada em 21/01/2027)")
    print()

    vivo = api.token_valido()
    print(f"token válido .. {'SIM' if vivo else 'NÃO'}")
    if not vivo:
        print("\n⚠ O token não responde. Se já passou de 60 dias sem renovação,")
        print("  ele morreu em definitivo e só um Business Login manual recupera.")
        return 2

    if not args.renovar:
        print("\nO token está vivo. Para renovar por mais 60 dias:")
        print("    python token_status.py --renovar")
        print("\nLembrete: renove a cada ~30 dias. Não existe cron fazendo isso.")
        return 0

    print("\nRenovando…")
    novo = api.refresh_long_lived_token()
    if not novo:
        print("Falhou. Veja o log acima para o motivo devolvido pela Meta.")
        return 3

    print("\nRenovado. Novo token:\n")
    print(novo)
    print("\nGrave este valor em META_ACCESS_TOKEN (Render → Environment).")
    print("O token anterior continua valendo até expirar; não há pressa de minutos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
