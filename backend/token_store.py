# -*- coding: utf-8 -*-
"""Onde o token do Instagram mora de verdade.

🚨 O PROBLEMA QUE ESTE ARQUIVO RESOLVE

Até 06/09/2026 o token vinha só de `os.getenv("META_ACCESS_TOKEN")`. Isso torna
a renovação automática impossível, e não por falta de código: um processo não
consegue alterar de forma durável a própria variável de ambiente. Um cron que
renovasse guardaria o token novo em memória e o perderia no próximo restart —
e o Render reinicia a cada deploy. Na volta, o processo leria de novo a env var
antiga, que a essa altura pode já estar morta.

Ou seja: sem persistência, o cron seria teatro.

A ordem de leitura é DB → env, e a env continua sendo a semente: na primeira
execução não há linha no banco, então lê-se a env e grava-se. Depois disso o
banco manda. Falha de banco NUNCA quebra publicação — cai para a env e segue.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kqjabzwgbfuivzlcfvvu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

TABELA = "meta_token"
CONTA_PADRAO = "aiarq"  # o mesmo store serve o @dizemfontes com outra conta


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SERVICE_ROLE or SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }


def _req(url: str, metodo: str = "GET", corpo: Optional[list | dict] = None,
         timeout: int = 15):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    r = urllib.request.Request(url, data=dados, method=metodo)
    for k, v in _headers().items():
        r.add_header(k, v)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        bruto = resp.read().decode("utf-8")
    return json.loads(bruto) if bruto.strip() else []


def ler(conta: str = CONTA_PADRAO) -> dict:
    """Devolve {token, expira_em, origem}. Nunca levanta.

    `origem` diz de onde veio — é o que se olha no diagnóstico quando o
    comportamento não bate com o esperado.
    """
    env = os.getenv("META_ACCESS_TOKEN", "")
    try:
        linhas = _req(f"{SUPABASE_URL}/rest/v1/{TABELA}"
                      f"?conta=eq.{conta}&select=token,expira_em&limit=1")
        if linhas:
            exp = linhas[0].get("expira_em")
            return {
                "token": linhas[0]["token"],
                "expira_em": datetime.fromisoformat(exp.replace("Z", "+00:00")) if exp else None,
                "origem": "banco",
            }
    except Exception as e:  # noqa: BLE001 — banco fora do ar não pode parar post
        print(f"[token_store] leitura falhou, caindo para env: {type(e).__name__}: {e}")
    return {"token": env, "expira_em": None, "origem": "env"}


def gravar(token: str, expires_in: Optional[int] = None,
           conta: str = CONTA_PADRAO) -> bool:
    """Persiste o token renovado. Devolve se conseguiu."""
    agora = datetime.now(timezone.utc)
    expira = agora + timedelta(seconds=int(expires_in)) if expires_in else None
    corpo = [{
        "conta": conta,
        "token": token,
        "expira_em": expira.isoformat() if expira else None,
        "renovado_em": agora.isoformat(),
    }]
    try:
        _req(f"{SUPABASE_URL}/rest/v1/{TABELA}?on_conflict=conta", "POST", corpo)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[token_store] gravação FALHOU: {type(e).__name__}: {e}")
        return False


def dias_restantes(conta: str = CONTA_PADRAO) -> Optional[int]:
    """Quantos dias faltam para o token expirar. None = desconhecido.

    Desconhecido é o estado normal antes da primeira renovação pelo cron: a env
    var não carrega data de emissão. Nesse caso o tick renova assim que rodar,
    o que também serve para descobrir a validade real.
    """
    est = ler(conta)
    if not est["expira_em"]:
        return None
    return (est["expira_em"] - datetime.now(timezone.utc)).days
