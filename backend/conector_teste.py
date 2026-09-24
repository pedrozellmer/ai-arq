# -*- coding: utf-8 -*-
"""PROVA do conector do AI.arq no Claude — Fase 0 (21/09/2026).

Um servidor MCP de TESTE em `/mcp-teste`, com um login de mentira (um botão
"Permitir", sem conta) e UMA ferramenta, `teste_de_conexao`, que não lê banco
nenhum. Existe pra responder, com o Claude de verdade do Pedro (web, desktop e
celular), as 6 perguntas que decidem se o conector de verdade vale a pena:

  1. a chave chega em cada chamada?  (issue anthropics/claude-ai-mcp#1038,
     aberta em 15/09/2026: o claude.ai troca o código pela chave e depois
     chama o servidor SEM ela — se acontecer aqui, PARA TUDO);
  2. que versão do protocolo o Claude fala?
  3. que client_id (documento CIMD) o Claude web/desktop/celular apresenta?
  4. a borda deixa passar a chamada do Claude (faixa 160.79.104.0/21)?
  5. a renovação da chave funciona?
  6. que cabeçalho Origin chega?

🔑 DOIS endereços, de propósito (21/09, medido): a zona ai.arq.br do
Cloudflare devolve 403 pra ClaudeBot, GPTBot, anthropic-ai e PerplexityBot — e
bloqueio de robô de IA na borda é a causa COMPROVADA de "o login completa e
nenhuma chamada autenticada chega" (claude-ai-mcp #968, #1061). Então:
  · https://api.ai.arq.br/mcp-teste      — o caminho real, pela zona ai.arq.br;
  · https://ai-arq.onrender.com/mcp-teste — FORA da zona ai.arq.br (o Render
    também fica atrás de um Cloudflare, mas o DELE, sem as nossas regras).
Se o 2º funciona e o 1º não, a culpa é das regras da nossa zona, não do Claude
nem nossa. Os dois têm emissor, chaves e descoberta próprios (a chave de um não
vale no outro), porque o Claude guarda a descoberta por URL e a "era" do
protocolo por ORIGEM.

🔑 Emissor SEM caminho (a raiz do host), com /authorize e /token na raiz: há
issues abertas (#962, #846, #984, #341) do Claude ignorando os endpoints
anunciados e indo direto em `<origem>/authorize` e `<origem>/token`. Na raiz,
os dois comportamentos caem no mesmo lugar.

Tudo o que acontece vai pro error_log com stage `conector-teste:*`
(severity "info"), por uma fila COM TETO e com freio por IP pra quem não vem
da faixa do Claude (descarte contado, nunca calado). Nunca vai chave, código,
verificador nem IP pro log.

🔒 Por que pode ficar aberto: não há dado atrás. A chave é um sorteio guardado
na MEMÓRIA deste processo (não é JWT do Supabase), só abre a ferramenta que
responde "conectado" e não vale em nenhuma rota /api. Um redeploy apaga todas
as chaves: o Claude pede login de novo — aceitável numa prova. Tudo o que é
guardado tem tamanho e quantidade limitados, e cheio RECUSA o novo em vez de
despejar o que ainda vale.
⏳ Desliga sozinha em `PROVA_ATE`; `CONECTOR_TESTE=0` no ambiente desliga
antes. No fim da Fase 0 este arquivo é APAGADO (e as linhas dele no main.py).

⏭️ A Fase 1 (login de verdade) NÃO herda sem mexer (revisão de 21/09):
exigir o documento CIMD (200, JSON, client_id igual à URL, retorno dentro de
`redirect_uris`); token de formulário na tela; pares em tabela só com hash.
"""
import asyncio
import base64
import collections
import hashlib
import html
import ipaddress
import json
import os
import queue
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

router = APIRouter(tags=["Conector (prova)"])

#: os ÚNICOS hosts servidos. O endereço anunciado sai desta lista, nunca do
#: cabeçalho Host cru: um Host forjado não pode mudar pra onde a chave é
#: anunciada nem o que o PRM declara (tem que bater BYTE A BYTE com a URL que
#: o Pedro cola no Claude).
HOSTS = ("api.ai.arq.br", "ai-arq.onrender.com")
HOST_PADRAO = HOSTS[0]
CAMINHO_MCP = "/mcp-teste"
NOME = "AI.arq (teste)"

SOBRE = ("Quantitativo de obra a partir de PDF, DWG e DXF. Ambiente de TESTE: nao le projeto nem dado de ninguem.")

# 23/09: o Claude mostrava o conector com um icone generico. O nosso mora
# em ai.arq.br (GitHub Pages) e o host do backend nao serve favicon; pior,
# a zona ai.arq.br bloqueia crawler de TREINO. A spec 2025-11-25 resolve
# pelo caminho certo: `Implementation extends BaseMetadata, Icons`, entao o
# serverInfo anuncia `icons` -- e `src` aceita `data:` URI, que nao depende
# de rota nova, de DNS nem de passar pelo Cloudflare.
#
# 🎨 Desenho pedido pelo Pedro: "AI" grande e "AI.Arq" pequeno embaixo.
# 🪤 O nome SO entra no 128: em 32x32 ele teria ~4 px de altura e viraria
# uma mancha. Cada tamanho mostra o que cabe -- por isso sao DOIS icones,
# e o cliente escolhe pelo `sizes`.
_ICONE_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAACXElEQVR4nGNkwAK8A5/+/8/E"
    "wPCfiZGBgRlEQzAyG10OVR673JF6CUZ0uxiROT7+MIupbzlMDkQfrxSH28tEb8tBfIuel/9R"
    "HOBDR8thcuYTIY5gAhH0thzGBqcBWiU4QpbD5JgG0nIQn2kgLQeHwEBajhQFA2M5CLOQYjkX"
    "FxPD+jpRBjYWSDlSt+ojw/4bP1As6A8XYDBXZGO4/foPQ+zyd3gtB6cBUnzuZMgBtxwE3A04"
    "MCyAl62M+H0O4TMiooCYYHc35gSbffruLzBtrsLOwMfDjKoWqXAnZDnObIjNcilRZgYdOVaw"
    "wQuPfGX4/fc/AwsTA4OLNjtqnCMBQpZjzYa4EpyHEcT3rz/9Zbjw+BfDhUe/IdGgA4sGzCgg"
    "ZDlGNsRlOYh2M+AAm3vk9i+w3FFoNGhLsjLICjOjFK/IIYDPcpRsiC+rGSixMUgIgLzHwHD0"
    "zk+w2JH7P+EWeWghJUZoCIBoQpbDsyGhfO5hCPE9CPSEC6C3KRg8NDgYZpz5BjEHJRHitxya"
    "BvBbzsHByOCgiXAANiDFx8ygJ8UKSQPIgIDlIDkWQiWcvTY7AycbxFvduz8zrLv0HS6nJcnK"
    "MC9UECznpc7BcOHtb7RygArZ0FMPkvq///7PsBNa6sHkrrz+w3DrzR+wvIsSOwMLC64owG45"
    "CDPal774T82ynZhgR0kDDANoOd5sSA/LURwwEJZjzYb0tBxcGw6k5eBcAMouVq0v/w+E5bct"
    "hRnB1cdAWA7mMyAVG6DuEj0tv2MuzIjROQV1l+hpOYYDYMBk+iscpSPlcY5uFwBHMt3pEFUB"
    "9gAAAABJRU5ErkJggg=="
)
_ICONE_128_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAANc0lEQVR4nO2da2wU1xXH/7M7"
    "3ocdMLYBm0fNw4CxAUMgfgAJlBBsA1UKUVUh0kaq1Kr90KqfovQRlUZV06RNSqLQpPlG2yiK"
    "1ESt0iqt2jTmDYE0AVqg2A5ggsEQwBhssy97qjuzszuz89yHzZ2Z+5esmR3P3Dk7v3POvXPn"
    "3lkOY6hNj/UK4JIfFEuB47TbMj7L64LO8antett0yhGN0LMD6nPp2pGy2cQOjc1cAWxObzvw"
    "TJX834KroAVv3torWF9IBh9ZwNdzzoM/KZxDFKSgzVvUkc7goyCRb5WtDj6dvyPkVcDmLyfB"
    "M/godNq3rqrS1dqhH1fmzJHLGbyuUSztjzd85fLQD7N3BF+2BzD4oBI+KXvlc1elwBwrB2Dw"
    "QS18eX3l89k5ga2U8aVHewW92x2W9kEV/MxzHnnSukqwzAAMPhwR+XrnbHnBOhuYOgCDD8fC"
    "l8tpedHcCUwdgKV9OBq+alu2DsAafHAN/OadxllA1wEYfLgGvvy5+SV9J9A4AIMP18GXl00v"
    "a51AvwrQGGXwBdiDHTgFvsphjRyA9e3DlZGvtLnpFXUWUGcAFvmuhm+aAdgjXXgDPgc07rom"
    "aDMAq/PhBfiqc8oOwEbywHPwG1+VsoAqA7DWPjwBX1mO5AAMPrwS+SqbZQdgkQ/vwZdrPDZ0"
    "G56FT5Y+faM44y+Vh1FuHbcPh8JXtQHSRjH48Ah8TQZg8OEp+ILqLoBFPrwGP5UBGHx4Er7o"
    "AAw+PAtfvxGocwGyNYq19uEI+KkqgMGH5yJfkwFY5MNz8IVUIzDzQJb24QX4RLxb4G9ZVYzv"
    "b50IK128nsDXd97Iu8G364kyLKsOGJ7nLyfv4hd/v2Nqs2bbOMPXdgU7FD5R64ow7Kh6Mo/a"
    "mUWFiXw7ohi++i7AwfBnTuVRV52EakOty0IMvioDOBg+6cdoXW4v+mWtXxKCz5dH5HPOj3z5"
    "OvucDp/0YG9YHkI2KrvPhxU1gbGDD2fATw8IcSh8ooY5AVSV+ZGtWpeG87/VsyOK4ZN1n5Ph"
    "k8+tJtF/486o4f/W1AURCnCehq/bFewk+AGewxcbjB3g/RMRw/+FAxxW1wZzg6/cx0yUwxcz"
    "gFPhE61eFERJyJhEx3+NHYCobWkov04eh8PXZAAnwSfLNpP03/N5Aqd74+i7NWK4T1NNEKUl"
    "vsLDhzPgk2vqcyr8SSU+NC4IwkgHzkTF5ZHOmOE+fh+wrj6UPXwbTpCae0UxfPVdgIPgEz28"
    "LCQCNFLHqai4b8dpi2qgIVRw+HAI/PRdgMPgCxbp/0r/CDqvxMX9j/fE0D9kfDeweGYRppPb"
    "yBwe7DgdvugAToQ/q5JH7Qzjrt+OU5GUHaMCsC9ZHRhpw+JQYeHDGfD1G4GUwyfrbfeb9/zt"
    "ORVV2WFVDbQuDudmsw3RDN+6K5hC+GLXL3mYYyDS6j9zOa46/pMLMQwMG1cDsyr8qK3is7fZ"
    "4fDNu4IphE+0bG4AU0v9lulfeTxBv/d/5tVA2+JQQeHrHU8bfOOuYErh20n/HaeToDPs6zhj"
    "Xg08skh6QpiNzU6Hr98VTDH8YBGHtYss0n9vXNe+j3tiGLhrXA1UlPiwYnagMPDhDPhiBnAK"
    "fKIHFwVRHOTMo9/A5pFRYP9Zi2pgUcZAEatHunZEMXzNiCCa4Yv3/svMB36kWvsGNn9gcTu4"
    "dkEQQZ7zDPz0XYAD4JNBHI1kEIeBrg6k079R3/5HPTHcNqkGigMcHpoftIZv0wloh0/WeSfA"
    "l8fxicO4DFRZ6sf+HZXIV231QfzzbMT2hTQW/fCJfE6ATz6TETzjoeY5QZSGfXnChyPgG78h"
    "hDL4cyp5zJ/GYzzE+4D1ioEiht/PTmGUwzefHEoJfKJ2k56/sVA7eURsdSHtiHL4mgxAI3xS"
    "7z/SMD7pX9aS6UWYNslvbbPD4Qu6k0Mpgk+Wy2sCmDIx6583zFutCw36BGxGvxPgK+4C6IRP"
    "/tosGn/kWf/uA0NSGcrjZSk/K8re3liMqonGzxTaFwax++iQ+YW0I4rhqyeHUgg/GOCwts54"
    "2BfRgc4o3vloOOvn+ZUT/Xi8sdiw3NnlPGoreZy9ljC8kE6Hr5kaRhN8YsfaesXYfQMd6Irm"
    "NEV7f7d5ryBRe20od/igH37aAYx2sDRKXZjG0Dzgk2WbReMvEhdw7Hw8J5v/cyWOWya9gkQb"
    "ahWdT6rrxLkCvn4j0LZR6sI0huYJf/IEH1bMNe76JTp2PoboiJCTzQT9wXPGI4aJJpf48MDM"
    "gLpsZbZxOPxUBqANPtGGhjB8FheapP98bN73qXU10FYbynlyKO3wiXw0wifLdnnWjoHIYM+D"
    "3bE8bAY+7IkhmjDv01tXExTHIeQ0P5By+KkMYN8odWEaQwsEf34Vj7lTzbt+T/XG0S+P88sB"
    "PlFkRMCxi+bVQEmAw4Oz1XMIbTmAA+AbvCz63sInsrr3z0z/ucBPVQPnzB2AaKOiGtDYbCbK"
    "4YtJ7eHvXRFogq/a7qK3cYFC+OT7+XK7kAw+XABf8bJoBh8ei3x5H/M3hGiMYpEPF8E3f0MI"
    "gw83R768zXxyKIt8uBm++eRQBh9uhy/I4wGcAP+1x8uwNPmK15O9cXznzX6NzT/dOBFtddI9"
    "+7rffI67ccHyQr7+WBmWTZPKPdEXx7f+fMv1ad98ciiF8KeV+tEgv9+XDNmaUYQq5ZCtzONg"
    "70JWTeCxNAmfqKGqCFUT/LZtdjp87V0AhfDlKVtk9eLNETGqyfqGhcnu2Uw7YPdCcti4MChu"
    "6rk1grsJqdy25MQQL8An4mmHT9bbkxNCj/XEUF3uR+OsgJjqf39sWG1Hhqx6+DYukMo9eimG"
    "WZP8aJoZQPu8IHYfH1bZ/N72Ckwt8eHo5Rg+vBzHE0vC2P9ZDDv23xH32VYXxrb6MKpK/Pj0"
    "VgJvd97F0y0TxCKePzaItzojVMJHqg1AMfy6aUUidKJ/dUZQXcaLDjB3Mo95U3h0XU+oj7cJ"
    "v34qL0Inev9cFNVJB6gp5zG/nEdXf0Jjc20Fj6bp0hiFgF8q5xsNxfju8pLUeReW8/hBkwRf"
    "7/rQBD/jDSH0wSeSo//60ChOXIpjT3dUnOmbGrmrPF4ps4sDYFPyAc/14VEc74uj43wsVS6p"
    "BjQ2AygN+rDr30NY88Z1vPTRIO4LcPhmgzSu8OrQKLb9tR8b/ngDxz+Pa22hEL6iEUgnfL8/"
    "WdeT9/50RsVRPAOR0dQjXPI/2XQrJ1CeUyx3nlTuB+ei4tiCgegojvZK5bbVhKRyM8okkHef"
    "HMZQQhDXl1YWIURmEwP4w5lhdPYncCM6it+eGNK1gzb4ZJ2nFT5ZNs8OYFKx1FXxlfvD4p9S"
    "pMW+dEYRjpN3AmW2BUzO2VIdQBmZ/wfgq4vD4p+q3Pt84q3hJ32K8YYALt0ZUdlZkSyD6LPb"
    "I6l9b8YER8Av0Muixwa+Mv2bSa4GdBuCBg92NiUbf2Zqr1EMAklqREiPPyTn64+kB5VOSToq"
    "CagZJer5BrTCFzMArfDDQQ4PJdP0vu4onnp3QLXv77aXo3Yqj/Xzg3hx7x1oRnaRL+fn8OvN"
    "pVhSVYSXDw3iT2ciCBdxWDNLasjtuRDFk/+4rbL5ja1lWFjB45E5QfzqyCDiOuXKdnQPjIjH"
    "kY9fqy/G0WsJxEcFfDvZLhCvneI42uDn+bLosYNPtj8sv60DwOELMc2+h3ukEUGlIR9aZulN"
    "HuEwp5xH8xcCKC7isLVe+oGI9TWKcj+LaWw+dCmWavC1kBHBGVLacXlwBO+dk27xZk/0491H"
    "y/C3LeWoJp1JalOohJ9xF0AP/Mz0f7gnptmXOIWsNuV7/2VxwLmbCfEefzgu4J3TdzXp//Cl"
    "uMZm2QFEG+Yq5gdmlC0vnz06iLe7IhiICogkBOztjWHHh8mfi6Mcvvhx7VN9Am3wleU4cTBH"
    "XQWPN1snievPfTyIt7ojVMLP4WXRDL4V/Ox7Je8dfNEBGHwULPI1+1IOP4uXRbPIzxU+KIYv"
    "FrvmR33ieRl8FC7yldsphi9YvyyaRb6b4YttAAYfnox83TYAi3x4Cr6YARh8eDLytRmA1fnw"
    "Gvz07wYy+PAi/FQVwFr78CR88zeE6Bbmzb59waXwUxnAzoVk8OE6+Fm8LJpFvhvhixngwDNV"
    "0kcGH15J+/Kyc1UFZ/GyaBb5boUvD1WTngXoFsbguxq+pg3A4MMLaV+1r3J19c/6RBtZ5MMT"
    "8LtWVohr6ZkNDD48E/l6GYBo1c+vCvkYxTp54Aj4XS1S9BNpf4uFwYerI18V8pqPwKpnr0pt"
    "ARb5cCP8ruZ09BtmAAYfroSvJ93NK5+TsoCVUazOh6PgZ0a/oQOITvB82gkYfLgSvqkDiE7w"
    "y6vStLGMwljkwxXwiUx/kZHBh+MjP1W2gSz+DbS8YFAVZH4Bs4ujMIoN5sC4wu9uMo5+Ww4g"
    "OsGLGVUBgw83wLftALKad6p7ClnkwxgopXV+Xg5A1PyS5AQMPoyBOgS+sois1PSytp+A1flw"
    "HHxlMTmp6ZV0lcAafLhn8HMBXxAHkNW465o6I7DWPsb7qd49dQBZja9KjsBu9TAugzkKoYI6"
    "QKYeeP2aoorQXgAiNmkDlvDJ6N2xYvR/GRyOin+xbSgAAAAASUVORK5CYII="
)
_ICONES = [{"src": "data:image/png;base64," + _ICONE_B64,
            "mimeType": "image/png", "sizes": ["32x32"]},
           {"src": "data:image/png;base64," + _ICONE_128_B64,
            "mimeType": "image/png", "sizes": ["128x128"]}]

#: a prova se desliga sozinha: depois disto, tudo aqui responde 404
# 23/09: era 05/10 (prova de 1–2 dias). A prova PASSOU em 23/09 — chave chega,
# protocolo 2025-11-25, CIMD, renovação rotativa e chamada real do celular —
# e o Pedro decidiu: *"esquece 05/10, vamos fazer no nosso tempo"*.
# 🪤 A trava FICA, só com folga: a tela de permissão ainda NÃO pede conta
# (quem tem o link recebe um token), então uma validade é o que garante que
# isto morre sozinho se a gente esquecer. Some junto quando a Fase 1 entrar.
PROVA_ATE = datetime(2026, 12, 31, 3, 0, tzinfo=timezone.utc)  # 31/12 00:00 Brasília

#: versões da era 2025 (com initialize). 2025-03-26 fica de fora: aceitá-la
#: traz junto a obrigação de aceitar lote JSON-RPC (removido na 2025-06-18).
VERSOES = ("2025-11-25", "2025-06-18")
VERSAO_PADRAO = VERSOES[0]

#: onde o Claude recebe o código. Web, desktop e celular usam o 1º (é o que
#: está no documento CIMD publicado em claude.ai/oauth/mcp-oauth-client-metadata,
#: lido em 21/09); o Claude Code usa loopback de porta aleatória (RFC 8252).
RETORNOS_CLAUDE = ("https://claude.ai/api/mcp/auth_callback",
                   "https://claude.com/api/mcp/auth_callback")
_RE_LOOPBACK = re.compile(r"http://(localhost|127\.0\.0\.1)(:\d{1,5})?/callback")
#: só buscamos documento CIMD nestes hosts e sob /oauth/ (URL qualquer = SSRF)
HOSTS_CIMD = ("claude.ai", "claude.com")
#: faixa de saída do Claude (claude.com/docs/connectors/building/authentication)
FAIXA_CLAUDE = ipaddress.ip_network("160.79.104.0/21")

VIDA_CODIGO = 600            # 10 min
VIDA_CHAVE = 600             # 10 min — curta de propósito: o Claude renova até 5 min
                             # antes de vencer, então a renovação acontece na prova (pergunta 5)
VIDA_RENOVACAO = 7 * 86400
JANELA_REPETICAO = 60        # a mesma renovação repetida em 60 s devolve o mesmo par
MARGEM_VENCIDA = 86400       # chave vencida fica 24 h, pra o log dizer "vencida" e não "invalida"
#: teto de QUANTIDADE (o de TAMANHO é o formato: client_id ≤ 512, desafio = 43)
TETO_GUARDADOS = 20000
TAM_CLIENT_ID = 512
_RE_DESAFIO = re.compile(r"[A-Za-z0-9_-]{43}")               # S256 sempre dá 43
_RE_VERIFICADOR = re.compile(r"[A-Za-z0-9._~-]{43,128}")      # RFC 7636 §4.1
TETO_CORPO_TOKEN = 16384
TETO_CORPO_MCP = 262144
#: freios por IP (o IP só vive na memória, nunca no log). NUNCA no /token nem
#: no /mcp-teste: todo o Claude sai da mesma faixa 160.79.104.0/21.
CODIGOS_POR_IP = (20, 600)   # POST /authorize: 20 a cada 10 min (é o navegador do usuário)
LOG_POR_IP = (60, 600)       # linhas de log de quem NÃO vem da faixa do Claude
FILA_LOG = 500

_PROCESSO_DESDE = time.time()

# ── ganchos (o main.py liga) ───────────────────────────────────────────────
_REGISTRAR = None            # `_log_error` do main — best-effort, nunca levanta
_EXEC_REDE = ThreadPoolExecutor(max_workers=2, thread_name_prefix="conector-rede")
_SEMAFORO_REDE = threading.BoundedSemaphore(2)   # cheio = não espera, anota "fila cheia"


def configurar(registrar=None):
    global _REGISTRAR
    _REGISTRAR = registrar


def _agora() -> float:
    return time.time()


def ligado() -> bool:
    if os.environ.get("CONECTOR_TESTE", "1") == "0":
        return False
    return datetime.fromtimestamp(_agora(), timezone.utc) < PROVA_ATE


# ── freio por chave (memória limitada) ─────────────────────────────────────
_FREIOS: "collections.OrderedDict" = collections.OrderedDict()
_TRAVA_FREIO = threading.Lock()


def _passa(chave: str, limite: tuple) -> bool:
    """True se ainda cabe na janela. Guarda no máximo 5000 chaves."""
    n, janela = limite
    agora = _agora()
    with _TRAVA_FREIO:
        fila = _FREIOS.get(chave)
        if fila is None:
            fila = _FREIOS[chave] = collections.deque()
            while len(_FREIOS) > 5000:
                _FREIOS.popitem(last=False)
        while fila and fila[0] < agora - janela:
            fila.popleft()
        if len(fila) >= n:
            return False
        fila.append(agora)
        return True


# ── o log: fila com teto, 1 thread, descarte CONTADO ───────────────────────
_FILA: "queue.Queue" = queue.Queue(maxsize=FILA_LOG)
_DESCARTADOS = {"n": 0}
_TRAVA_LOG = threading.Lock()
_CONSUMIDOR = {"thread": None}


def _gravar(item) -> None:
    fn = _REGISTRAR
    if fn is None:
        return
    with _TRAVA_LOG:
        n, _DESCARTADOS["n"] = _DESCARTADOS["n"], 0
    try:
        if n:
            fn("conector-teste:descartados", json.dumps({"n": n}), None, "info")
        fn(item[0], item[1], None, "info")
    except Exception:
        pass


def _consumir() -> None:
    while True:
        _gravar(_FILA.get())


def _garantir_consumidor() -> None:
    # daemon: um deploy não espera a fila (é log de prova, não dado)
    with _TRAVA_LOG:
        t = _CONSUMIDOR["thread"]
        if t is None or not t.is_alive():
            t = threading.Thread(target=_consumir, name="conector-log", daemon=True)
            _CONSUMIDOR["thread"] = t
            t.start()


def _registrar(etapa: str, dados: dict, ip: str = "") -> None:
    """Nunca espera rede (rota async no laço de eventos = site inteiro, 27/08).
    Quem não vem da faixa do Claude tem freio por IP; fila cheia descarta e
    CONTA — a próxima linha gravada diz quantas se perderam."""
    if _REGISTRAR is None:
        return
    if dados.get("faixa_claude") is not True and ip and not _passa("log:" + ip, LOG_POR_IP):
        with _TRAVA_LOG:
            _DESCARTADOS["n"] += 1
        return
    dados = dict(dados, t=int(_agora()))
    item = ("conector-teste:" + etapa, json.dumps(dados, ensure_ascii=False, sort_keys=True)[:1900])
    try:
        _FILA.put_nowait(item)
    except queue.Full:
        with _TRAVA_LOG:
            _DESCARTADOS["n"] += 1
        return
    _garantir_consumidor()


# ── endereços, por host ────────────────────────────────────────────────────
def _host(request: Request) -> str:
    h = (request.headers.get("host") or "").split(":")[0].strip().lower()
    return h if h in HOSTS else HOST_PADRAO


def _base(host: str) -> str:
    return "https://" + host


def _recurso(host: str) -> str:
    return _base(host) + CAMINHO_MCP


def _url_prm(host: str) -> str:
    return _base(host) + "/.well-known/oauth-protected-resource" + CAMINHO_MCP


# ── guardados (memória do processo) ────────────────────────────────────────
_TRAVA = threading.Lock()
_CODIGOS: dict = {}          # código -> pedido aprovado
_CHAVES: dict = {}           # sha256(chave) -> {exp, client_id, escopo, host, concessao, geracao}
_RENOVACOES: dict = {}       # sha256(renovação) -> {exp, ..., trocada_em}
_REPETICOES: dict = {}       # sha256(renovação trocada) -> {exp: +60 s, par} — o par em claro
                             # vive só a janela de repetição (revisão de 21/09)
_REVOGADAS: dict = {}        # concessão -> {exp}: chaves e renovações dela não valem mais
_CIMD_CACHE: dict = {}       # client_id -> (quando, resultado) — só sucesso
_ULTIMA_CHAVE_EMITIDA: dict = {}   # host -> quando (a assinatura da #1038 é POR host)


def _h(segredo: str) -> str:
    return hashlib.sha256(segredo.encode("utf-8")).hexdigest()


def _podar(guardado: dict, limite: float) -> None:
    """Tira SÓ o que venceu antes de `limite`. Nunca despeja o que ainda vale:
    cheio, quem chama RECUSA o novo (revisão de 21/09 — despejar o mais antigo
    deixava qualquer um derrubar a chave do Pedro cunhando 2001 pares)."""
    for k in [k for k, v in guardado.items() if v.get("exp", 0) < limite]:
        guardado.pop(k, None)


def _pkce_s256(verificador: str) -> str:
    d = hashlib.sha256(verificador.encode("ascii", "replace")).digest()
    return base64.urlsafe_b64encode(d).rstrip(b"=").decode("ascii")


def _mesmo_recurso(r: str, host: str) -> str:
    """"exato" | "barra" (só a barra final difere) | "" (outro recurso)."""
    if r == _recurso(host):
        return "exato"
    if r.rstrip("/") == _recurso(host):
        return "barra"
    return ""


def _retorno_permitido(uri: str) -> bool:
    return uri in RETORNOS_CLAUDE or bool(_RE_LOOPBACK.fullmatch(uri or ""))


def _ip(request: Request) -> str:
    return (request.headers.get("cf-connecting-ip")
            or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            or (request.client.host if request.client else ""))


def _quem(request: Request) -> dict:
    """De onde veio a chamada — perguntas 4 e 6. O IP NÃO vai pro log (o do
    Pedro abrindo a tela é dado pessoal); vai só se está na faixa do Claude.
    `cf_ray` é pra cruzar com os Security Events do Cloudflare; ele aparece nos
    DOIS hosts (o Render também passa por um Cloudflare), então quem diz se
    passou pelas NOSSAS regras é `zona_ai_arq`."""
    try:
        na_faixa = ipaddress.ip_address(_ip(request)) in FAIXA_CLAUDE
    except ValueError:
        na_faixa = None
    host = _host(request)
    return {"host": host,
            "zona_ai_arq": host == "api.ai.arq.br",
            "cf_ray": (request.headers.get("cf-ray") or "")[:40],
            "faixa_claude": na_faixa,
            "ua": (request.headers.get("user-agent") or "")[:120],
            "origin": (request.headers.get("origin") or "")[:120],
            "barra": request.url.path.endswith("/") and request.url.path != "/"}


def _sem_cache(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    return resp


def _nao_existe():
    return JSONResponse({"detail": "Not Found"}, status_code=404)


async def _corpo_limitado(request: Request, teto: int):
    """Lê o corpo contando os bytes ENQUANTO chegam; passou do teto, para e
    devolve None (o `[:N]` depois de `body()` já tinha o corpo inteiro na RAM)."""
    partes, n = [], 0
    async for pedaco in request.stream():
        n += len(pedaco)
        if n > teto:
            return None
        partes.append(pedaco)
    return b"".join(partes)


# ═══════════════════════════ descoberta ════════════════════════════════════
def _prm(host: str) -> dict:
    return {"resource": _recurso(host),
            "authorization_servers": [_base(host)],
            "scopes_supported": ["teste"],
            "bearer_methods_supported": ["header"],
            "resource_name": NOME}


# O Claude tenta primeiro o PRM com o caminho do recurso e cai pra raiz.
@router.get("/.well-known/oauth-protected-resource" + CAMINHO_MCP)
@router.get("/.well-known/oauth-protected-resource")
async def metadados_do_recurso(request: Request):
    if not ligado():
        return _nao_existe()
    _registrar("descoberta-recurso", dict(_quem(request), caminho=request.url.path), _ip(request))
    return JSONResponse(_prm(_host(request)))


def _metadados_emissor(host: str) -> dict:
    b = _base(host)
    return {
        "issuer": b,
        "authorization_endpoint": b + "/authorize",
        "token_endpoint": b + "/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        # as DUAS marcas: sem qualquer uma o Claude cai pro DCR, que nem
        # anunciamos (o erro fica à vista em vez de um 2º caminho calado)
        "token_endpoint_auth_methods_supported": ["none"],
        "client_id_metadata_document_supported": True,
        "scopes_supported": ["teste", "offline_access"],
        "authorization_response_iss_parameter_supported": True,
    }


@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/openid-configuration")
async def metadados_do_emissor(request: Request):
    if not ligado():
        return _nao_existe()
    _registrar("descoberta-emissor", dict(_quem(request), caminho=request.url.path), _ip(request))
    return JSONResponse(_metadados_emissor(_host(request)))


# ═══════════════════════════ CIMD ══════════════════════════════════════════
class _NaoSegue(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None           # o 3xx volta como HTTPError e vira "erro" no log


_SEM_REDIRECT = urllib.request.build_opener(_NaoSegue)


def _cimd_buscavel(client_id: str) -> str:
    """"" se pode buscar; senão o motivo."""
    try:
        u = urllib.parse.urlsplit(client_id)
        porta = u.port
    except ValueError:
        return "client_id ilegível"
    if (u.scheme != "https" or (u.hostname or "") not in HOSTS_CIMD or porta not in (None, 443)
            or u.username or u.password or not u.path.startswith("/oauth/")):
        return "host fora da lista"
    return ""


def _buscar_cimd(client_id: str) -> dict:
    """Busca o documento CIMD — SÓ em claude.ai/claude.com sob /oauth/, sem
    seguir redirect, com teto de tempo e de tamanho. Devolve o que achou, sem
    levantar (pergunta 3). Na prova só ANOTA; quem barra é a lista de
    retornos. A Fase 1 passa a exigir."""
    motivo = _cimd_buscavel(client_id)
    if motivo:
        return {"buscado": False, "motivo": motivo}
    with _TRAVA:
        em_cache = _CIMD_CACHE.get(client_id)
    if em_cache and _agora() - em_cache[0] < 300:       # o documento vem com max-age=300
        return em_cache[1]
    r = {"buscado": True}
    try:
        req = urllib.request.Request(client_id, headers={"Accept": "application/json",
                                                         "User-Agent": "AI.arq-conector-teste"})
        with _SEM_REDIRECT.open(req, timeout=5) as resp:
            r["http"] = resp.status
            bruto = resp.read(8193)
        if r["http"] != 200:
            r["erro"] = "status %s" % r["http"]
        elif len(bruto) > 8192:
            r["erro"] = "documento maior que 8 KB"
        else:
            doc = json.loads(bruto.decode("utf-8"))
            r["client_id_confere"] = doc.get("client_id") == client_id
            r["client_name"] = str(doc.get("client_name") or "")[:80]
            r["redirect_uris"] = [str(x)[:120] for x in (doc.get("redirect_uris") or [])][:10]
            r["auth_method"] = str(doc.get("token_endpoint_auth_method") or "")[:40]
    except Exception as e:
        r["erro"] = type(e).__name__ + ": " + str(e)[:160]
    if "erro" not in r:                                   # erro não vai pro cache
        with _TRAVA:
            _CIMD_CACHE[client_id] = (_agora(), r)
            while len(_CIMD_CACHE) > 50:
                _CIMD_CACHE.pop(next(iter(_CIMD_CACHE)))
    return r


def _buscar_cimd_com_vaga(client_id: str) -> dict:
    """Roda na thread de rede. Sem vaga, NÃO espera: anota "fila cheia"."""
    if not _SEMAFORO_REDE.acquire(blocking=False):
        return {"buscado": False, "motivo": "fila cheia"}
    try:
        return _buscar_cimd(client_id)
    finally:
        _SEMAFORO_REDE.release()


async def _cimd_sem_prender_a_tela(client_id: str) -> dict:
    try:
        return await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(_EXEC_REDE, _buscar_cimd_com_vaga, client_id), 3)
    except asyncio.TimeoutError:
        return {"buscado": True, "erro": "passou de 3 s — a tela não esperou"}


# ═══════════════════════════ autorizar ═════════════════════════════════════
_CAMPOS_AUTORIZAR = ("response_type", "client_id", "redirect_uri", "state", "scope",
                     "code_challenge", "code_challenge_method", "resource")


def _pagina(titulo: str, corpo_html: str, status: int = 200) -> HTMLResponse:
    r = HTMLResponse(
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(titulo)}</title>"
        "<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;"
        "background:#f5f6fb;color:#0f172a;margin:0;padding:24px 16px}"
        "main{max-width:440px;margin:40px auto;background:#fff;border:1px solid #e2e5f0;"
        "border-radius:12px;padding:24px}h1{font-size:20px;margin:0 0 12px}"
        "p{line-height:1.5;margin:0 0 12px}.t{font-size:13px;color:#475569}"
        "button{background:#4f46e5;color:#fff;border:0;border-radius:8px;padding:12px 18px;"
        "font-size:16px;cursor:pointer;width:100%}button:focus-visible{outline:3px solid #22d3ee}"
        "</style></head><body><main>" + corpo_html + "</main></body></html>",
        status_code=status)
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    return _sem_cache(r)


def _validar_cliente(p: dict) -> str:
    """1º portão: client_id e retorno. Falhou aqui, o erro fica na TELA e
    nunca redireciona — mandar erro pra um redirect_uri não conferido é
    redirecionamento aberto (OAuth 2.1 §4.1.2.1)."""
    if not p.get("client_id"):
        return "client_id ausente"
    if len(p["client_id"]) > TAM_CLIENT_ID:
        return "client_id longo demais"
    if not _retorno_permitido(p.get("redirect_uri", "")):
        return "endereço de retorno fora da lista do Claude"
    return ""


def _validar_resto(p: dict, host: str):
    """2º portão, com o retorno já conferido: o erro VOLTA pro Claude por
    redirect (error, state, iss). Devolve (código, motivo) ou None."""
    if p.get("response_type") != "code":
        return ("unsupported_response_type", "response_type tem que ser code")
    if p.get("code_challenge_method") != "S256" or not _RE_DESAFIO.fullmatch(p.get("code_challenge") or ""):
        return ("invalid_request", "PKCE S256 é obrigatório")
    if p.get("resource") and not _mesmo_recurso(p["resource"], host):
        return ("invalid_target", "resource aponta pra outro servidor")
    return None


def _volta_com_erro(p: dict, host: str, erro: tuple) -> Response:
    q = {"error": erro[0], "error_description": erro[1], "iss": _base(host)}
    if p.get("state"):
        q["state"] = p["state"]
    sep = "&" if "?" in p["redirect_uri"] else "?"
    return _sem_cache(RedirectResponse(p["redirect_uri"] + sep + urllib.parse.urlencode(q),
                                       status_code=302))


def _host_de(url: str) -> str:
    """O HOST de uma URL, que é o que a tela mostra (o nome no documento CIMD
    quem escreve é o próprio cliente)."""
    try:
        return urllib.parse.urlsplit(url).hostname or "(desconhecido)"
    except ValueError:
        return "(desconhecido)"


@router.get("/authorize")
async def autorizar_tela(request: Request):
    if not ligado():
        return _nao_existe()
    host = _host(request)
    p = {k: request.query_params.get(k, "") for k in _CAMPOS_AUTORIZAR}
    motivo = _validar_cliente(p)
    resto = None if motivo else _validar_resto(p, host)
    info = dict(_quem(request), client_id=p["client_id"][:200],
                retorno=urllib.parse.urlsplit(p["redirect_uri"]).netloc[:80],
                tem_resource=bool(p["resource"]),
                resource=_mesmo_recurso(p["resource"], host) if p["resource"] else "",
                escopo=p["scope"][:80], tem_state=bool(p["state"]),
                recusado=motivo or (resto[1] if resto else ""))
    # só busca o CIMD de pedido que PASSOU (revisão de 21/09: pedido inválido
    # de qualquer um fazia o servidor buscar e segurava a tela do Pedro)
    if not motivo and not resto and p["client_id"].startswith("https://"):
        info["cimd"] = await _cimd_sem_prender_a_tela(p["client_id"])
    _registrar("autorizar", info, _ip(request))
    if motivo:
        return _pagina("Pedido recusado", f"<h1>Pedido recusado</h1><p>{html.escape(motivo)}.</p>", 400)
    if resto:
        return _volta_com_erro(p, host, resto)
    ocultos = "".join(f"<input type='hidden' name='{k}' value='{html.escape(p[k], quote=True)}'>"
                      for k in _CAMPOS_AUTORIZAR)
    volta = ("este computador (localhost)" if _RE_LOOPBACK.fullmatch(p["redirect_uri"])
             else _host_de(p["redirect_uri"]))
    return _pagina(
        "Conectar o Claude ao AI.arq (teste)",
        "<h1>Conectar o Claude ao AI.arq — TESTE</h1>"
        f"<p class='t'>Pedido feito por: <b>{html.escape(_host_de(p['client_id']))}</b><br>"
        f"O acesso volta para: <b>{html.escape(volta)}</b></p>"
        "<p>Isto é só um teste de conexão. <b>Nenhum projeto nem dado seu é lido</b>: "
        "o Claude só vai conseguir perguntar se a conexão funciona.</p>"
        "<p class='t'>Só continue se você acabou de clicar em Conectar no seu Claude.</p>"
        f"<form method='post' action='{html.escape(_base(host) + '/authorize', quote=True)}'>{ocultos}"
        "<button type='submit'>Permitir</button></form>")


@router.post("/authorize")
async def autorizar_permitir(request: Request):
    if not ligado():
        return _nao_existe()
    host = _host(request)
    ip = _ip(request)
    # teto por CAMPO antes de ler: o state do Claude volta nos campos ocultos,
    # então não pode ser apertado demais (16 KB); o que é GUARDADO tem formato
    form = await request.form(max_files=0, max_fields=16, max_part_size=16384)
    p = {k: str(form.get(k) or "") for k in _CAMPOS_AUTORIZAR}
    motivo = _validar_cliente(p)
    if motivo:
        _registrar("permitir-recusado", dict(_quem(request), motivo=motivo), ip)
        return _pagina("Pedido recusado", f"<h1>Pedido recusado</h1><p>{html.escape(motivo)}.</p>", 400)
    resto = _validar_resto(p, host)
    if resto:
        _registrar("permitir-recusado", dict(_quem(request), motivo=resto[1]), ip)
        return _volta_com_erro(p, host, resto)
    if ip and not _passa("codigo:" + ip, CODIGOS_POR_IP):
        _registrar("permitir-recusado", dict(_quem(request), motivo="muitos pedidos deste IP"), ip)
        return _pagina("Muitas tentativas", "<h1>Muitas tentativas</h1>"
                       "<p>Espere alguns minutos e tente de novo.</p>", 429)
    codigo = secrets.token_urlsafe(32)
    agora = _agora()
    with _TRAVA:
        _podar(_CODIGOS, agora)
        cheio = len(_CODIGOS) >= TETO_GUARDADOS
        if not cheio:
            _CODIGOS[codigo] = {"exp": agora + VIDA_CODIGO, "client_id": p["client_id"],
                                "redirect_uri": p["redirect_uri"], "desafio": p["code_challenge"],
                                "host": host, "usado": False, "concessao": secrets.token_hex(8)}
    if cheio:
        _registrar("permitir-recusado", dict(_quem(request), motivo="teto de códigos"), ip)
        return _volta_com_erro(p, host, ("temporarily_unavailable", "tente de novo em alguns minutos"))
    _registrar("permitiu", dict(_quem(request), client_id=p["client_id"][:200]), ip)
    q = {"code": codigo, "iss": _base(host)}
    if p["state"]:
        q["state"] = p["state"]
    sep = "&" if "?" in p["redirect_uri"] else "?"
    # 302 (nunca 307): é a navegação do navegador voltando pro Claude
    return _sem_cache(RedirectResponse(p["redirect_uri"] + sep + urllib.parse.urlencode(q),
                                       status_code=302))


# ═══════════════════════════ token ═════════════════════════════════════════
def _erro_oauth(erro: str, descricao: str, status: int = 400) -> Response:
    return _sem_cache(JSONResponse({"error": erro, "error_description": descricao},
                                   status_code=status))


def _emitir_com_trava_na_mao(client_id: str, escopo: str, host: str, agora: float,
                             concessao: str, geracao: int):
    """Quem chama SEGURA `_TRAVA` (a renovação precisa trocar e emitir num
    passo só). Toda chave e renovação carrega a CONCESSÃO (o "Permitir" que a
    originou): revogar a concessão derruba a família inteira. Cheio → None
    (recusa o novo; nunca despeja o que vale)."""
    _podar(_CHAVES, agora - MARGEM_VENCIDA)
    _podar(_RENOVACOES, agora)
    _podar(_REPETICOES, agora)
    _podar(_REVOGADAS, agora)
    if len(_CHAVES) >= TETO_GUARDADOS or len(_RENOVACOES) >= TETO_GUARDADOS:
        return None
    chave, renov = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    _CHAVES[_h(chave)] = {"exp": agora + VIDA_CHAVE, "client_id": client_id, "escopo": escopo,
                          "host": host, "concessao": concessao, "geracao": geracao}
    _RENOVACOES[_h(renov)] = {"exp": agora + VIDA_RENOVACAO, "client_id": client_id,
                              "escopo": escopo, "host": host, "concessao": concessao,
                              "geracao": geracao, "trocada_em": None}
    _ULTIMA_CHAVE_EMITIDA[host] = agora
    return {"access_token": chave, "token_type": "Bearer", "expires_in": VIDA_CHAVE,
            "refresh_token": renov, "scope": escopo}


def _revogar_com_trava_na_mao(concessao: str, agora: float) -> None:
    # a revogação vive tanto quanto a renovação mais longa que ela derruba
    _REVOGADAS[concessao] = {"exp": agora + VIDA_RENOVACAO}


@router.post("/token")
async def token(request: Request):
    if not ligado():
        return _nao_existe()
    host = _host(request)
    quem = _quem(request)
    ip = _ip(request)
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype != "application/x-www-form-urlencoded":
        _registrar("token", dict(quem, ok=False, motivo="content-type " + ctype[:60]), ip)
        return _erro_oauth("invalid_request", "use application/x-www-form-urlencoded")
    corpo = await _corpo_limitado(request, TETO_CORPO_TOKEN)
    if corpo is None:
        _registrar("token", dict(quem, ok=False, motivo="corpo grande demais"), ip)
        return _erro_oauth("invalid_request", "corpo grande demais", 413)
    listas = urllib.parse.parse_qs(corpo.decode("utf-8", "replace"), keep_blank_values=True)
    if any(len(v) > 1 for v in listas.values()):
        # parâmetro repetido = invalid_request (OAuth 2.1 §3.2)
        _registrar("token", dict(quem, ok=False, motivo="parâmetro repetido"), ip)
        return _erro_oauth("invalid_request", "parâmetro repetido")
    # parâmetro vazio conta como ausente
    f = {k: v[0] for k, v in listas.items() if v[0] != ""}
    tipo = f.get("grant_type", "")
    if tipo == "authorization_code":
        r = _trocar_codigo(f, host)
    elif tipo == "refresh_token":
        r = _renovar(f, host)
    else:
        r = ("unsupported_grant_type", "grant_type não suportado")
    if isinstance(r, tuple):
        _registrar("token", dict(quem, grant=tipo[:30], ok=False, motivo=r[1]), ip)
        if r[0] == "temporarily_unavailable":
            return _erro_oauth(r[0], r[1], 503)
        return _erro_oauth(r[0], r[1])
    info = r.pop("_log")
    _registrar("token", dict(quem, grant=tipo, ok=True, expires_in=r["expires_in"],
                             client_id=f.get("client_id", "")[:200],
                             tem_resource=bool(f.get("resource")),
                             escopo_pedido=f.get("scope", "")[:80], **info), ip)
    return _sem_cache(JSONResponse(r))


def _trocar_codigo(f: dict, host: str):
    codigo = f.get("code", "")
    agora = _agora()
    with _TRAVA:
        c = _CODIGOS.get(codigo)
        if not c or c["exp"] < agora:
            return ("invalid_grant", "código inválido ou vencido")
        # os parâmetros são conferidos ANTES de olhar se o código já foi usado:
        # replay com parâmetro errado só é negado; replay VÁLIDO revoga tudo
        if c["host"] != host:
            return ("invalid_grant", "código emitido por outro endereço")
        if f.get("client_id", "") != c["client_id"]:
            return ("invalid_grant", "client_id diferente do pedido")
        if "redirect_uri" in f and f["redirect_uri"] != c["redirect_uri"]:
            return ("invalid_grant", "redirect_uri diferente do pedido")
        v = f.get("code_verifier", "")
        if not _RE_VERIFICADOR.fullmatch(v) or _pkce_s256(v) != c["desafio"]:
            return ("invalid_grant", "verificador PKCE não confere")
        if f.get("resource") and not _mesmo_recurso(f["resource"], host):
            return ("invalid_target", "resource aponta pra outro servidor")
        if c["usado"]:
            # o MESMO código, válido, pela 2ª vez: alguém tem uma cópia dele.
            # As chaves que ele já rendeu morrem junto (OAuth 2.1 §4.1.3).
            _revogar_com_trava_na_mao(c["concessao"], agora)
            return ("invalid_grant", "código já usado — conexão revogada")
        novo = _emitir_com_trava_na_mao(c["client_id"], "teste", host, agora, c["concessao"], 1)
        if novo is None:
            return ("temporarily_unavailable", "tente de novo em alguns minutos")
        c["usado"] = True
    novo["_log"] = {"geracao": 1, "repetida": False}
    return novo


def _renovar(f: dict, host: str):
    # o pedido de renovação pode vir sem scope ou com escopos OIDC (#840):
    # não se exige nem se confere scope aqui
    renov = f.get("refresh_token", "")
    agora = _agora()
    with _TRAVA:
        r = _RENOVACOES.get(_h(renov))
        if not r or r["exp"] < agora:
            return ("invalid_grant", "renovação inválida ou vencida")
        if r["concessao"] in _REVOGADAS:
            return ("invalid_grant", "conexão revogada")
        if r["host"] != host:
            return ("invalid_grant", "renovação de outro endereço")
        if f.get("client_id") and f["client_id"] != r["client_id"]:
            return ("invalid_grant", "client_id diferente")
        if r["trocada_em"] is not None:
            # a MESMA renovação de novo: dentro da janela devolve o mesmo par
            # (retry de rede não derruba ninguém); fora, é reuso de papel já
            # trocado — alguém tem uma cópia: a conexão inteira morre
            # (OAuth 2.1 §4.3.1)
            rep = _REPETICOES.get(_h(renov))
            if rep and rep["exp"] >= agora:
                par = dict(rep["par"])
                par["_log"] = {"geracao": r["geracao"] + 1, "repetida": True}
                return par
            _revogar_com_trava_na_mao(r["concessao"], agora)
            return ("invalid_grant", "renovação reaproveitada — conexão revogada")
        novo = _emitir_com_trava_na_mao(r["client_id"], r["escopo"], host, agora,
                                        r["concessao"], r["geracao"] + 1)
        if novo is None:
            return ("temporarily_unavailable", "tente de novo em alguns minutos")
        r["trocada_em"] = agora
        # o par em claro só vive a janela; depois some sozinho no _podar
        _REPETICOES[_h(renov)] = {"exp": agora + JANELA_REPETICAO, "par": dict(novo)}
    novo["_log"] = {"geracao": r["geracao"] + 1, "repetida": False}
    return novo


# ═══════════════════════════ o servidor MCP ════════════════════════════════
def _forma(valor: str) -> str:
    """Que CARA tem a credencial que não valeu — sem o segredo (a #1038 pode
    chegar como "Bearer undefined", e isso tem que se distinguir de chave velha)."""
    v = valor.strip()
    if v.lower() in ("", "undefined", "null", "none"):
        return "palavra"
    if v.count(".") == 2:
        return "jwt"
    if re.fullmatch(r"[A-Za-z0-9_-]{43}", v):
        return "nossa"
    return "outra"


def _chave_valida(request: Request, host: str):
    """(estado, dados, detalhe): estado ∈ sem-cabecalho | outro-esquema | invalida |
    revogada | vencida | outro-host | ok."""
    a = request.headers.get("authorization") or ""
    if not a:
        return "sem-cabecalho", None, {}
    esquema, _, valor = a.partition(" ")
    detalhe = {"forma": _forma(valor), "tam": len(valor.strip())}
    if esquema.lower() != "bearer" or not valor.strip():
        return "outro-esquema", None, detalhe
    hv = _h(valor.strip())
    with _TRAVA:
        d = _CHAVES.get(hv)
        revogada = bool(d) and d["concessao"] in _REVOGADAS
        detalhe["e_renovacao"] = hv in _RENOVACOES
    if not d:
        return "invalida", None, detalhe
    if revogada:
        return "revogada", None, detalhe
    if d["exp"] < _agora():
        return "vencida", None, detalhe
    if d["host"] != host:
        return "outro-host", None, detalhe     # a chave é presa ao recurso que a pediu
    return "ok", d, detalhe


def _pede_chave(estado: str, host: str) -> Response:
    """401 SEMPRE (403 comum é erro terminal pro Claude — #430), com o
    WWW-Authenticate que aponta a descoberta. O corpo é só informativo."""
    www = f'Bearer resource_metadata="{_url_prm(host)}", scope="teste"'
    if estado not in ("sem-cabecalho",):
        www += ', error="invalid_token"'
    r = JSONResponse({"error": "invalid_token",
                      "error_description": "Autenticação necessária"}, status_code=401)
    r.headers["WWW-Authenticate"] = www
    return r


def _ferramenta():
    return {
        "name": "teste_de_conexao",
        "title": "Teste de conexão do AI.arq",
        "description": ("Confere se a conexão com o AI.arq funciona. Ambiente de teste: "
                        "não lê projetos nem dados de ninguém."),
        "inputSchema": {"type": "object", "additionalProperties": False},
        # destructiveHint e openWorldHint valem TRUE se omitidos: explícitos
        "annotations": {"title": "Teste de conexão do AI.arq", "readOnlyHint": True,
                        "destructiveHint": False, "idempotentHint": True,
                        "openWorldHint": False},
    }


def _hora_br(ts: float) -> str:
    return (datetime.fromtimestamp(ts, timezone.utc) - timedelta(hours=3)).strftime("%H:%M")


def _responder(msg: dict, chave: dict, versao: str):
    """Uma mensagem JSON-RPC -> resposta (ou None se for notificação ou
    resposta do cliente). O `id` volta com o MESMO tipo que chegou."""
    metodo = msg.get("method")
    if not isinstance(metodo, str) or "id" not in msg:
        return None
    mid = msg.get("id")

    def ok(res):
        return {"jsonrpc": "2.0", "id": mid, "result": res}

    def erro(cod, texto):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": cod, "message": texto}}

    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    if metodo == "initialize":
        # versão que não atendemos NÃO é erro: responde a nossa (lifecycle)
        pedida = str(params.get("protocolVersion") or "")
        return ok({"protocolVersion": pedida if pedida in VERSOES else VERSAO_PADRAO,
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "aiarq-teste", "title": NOME,
                                  "version": "0.1.0",
                                  "description": SOBRE,
                                  "websiteUrl": "https://ai.arq.br",
                                  "icons": _ICONES}})
    if metodo == "ping":
        return ok({})
    if metodo == "tools/list":
        return ok({"tools": [_ferramenta()]})
    if metodo == "tools/call":
        nome = str(params.get("name") or "")
        if nome != "teste_de_conexao":
            return erro(-32602, "Unknown tool: " + nome[:64])
        texto = ("✅ Conectado ao AI.arq (ambiente de TESTE).\n"
                 f"Protocolo em uso: {versao or 'não informado'}.\n"
                 f"A chave chegou nesta chamada e vale até {_hora_br(chave['exp'])} (Brasília).\n"
                 "Este teste não lê nenhum projeto nem dado de ninguém.")
        return ok({"content": [{"type": "text", "text": texto}], "isError": False})
    # na era 2025, método desconhecido = HTTP 200 com -32601 (404 seria "sessão encerrada")
    return erro(-32601, "Method not found")


def _pedido_de_2026(msg: dict, versao_cab: str) -> bool:
    """Pedido da spec 2026-07-28 (sem initialize). Qualquer método pode ser o
    1º: server/discover é opcional no HTTP. O initialize negocia pelo corpo,
    não pelo cabeçalho (que ele nem precisa mandar)."""
    if msg.get("method") == "initialize":
        return False
    if msg.get("method") == "server/discover":
        return True
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    if "io.modelcontextprotocol/protocolVersion" in meta:
        return True
    return bool(versao_cab) and versao_cab not in VERSOES


@router.post(CAMINHO_MCP)
@router.post(CAMINHO_MCP + "/")     # sem 307: o Claude segue o 3xx e perde a chave (#1056)
async def mcp(request: Request):
    if not ligado():
        return _nao_existe()
    host = _host(request)
    quem = _quem(request)
    ip = _ip(request)
    versao_cab = (request.headers.get("mcp-protocol-version") or "")[:40]
    estado, chave, detalhe = _chave_valida(request, host)
    bruto = await _corpo_limitado(request, TETO_CORPO_MCP)
    try:
        corpo = json.loads(bruto or b"null") if bruto is not None else None
    except (ValueError, RecursionError):       # JSON fundo demais não vira 500
        corpo = None
    msg = corpo if isinstance(corpo, dict) else {}
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    info_cli = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
    base_log = dict(quem, metodo=str(msg.get("method") or "")[:40],
                    versao_cabecalho=versao_cab,
                    versao_pedida=str(params.get("protocolVersion") or "")[:40] if msg.get("method") == "initialize" else "",
                    cliente=(str(info_cli.get("name") or "")[:40] + " " + str(info_cli.get("version") or "")[:20]).strip(),
                    tem_meta=isinstance(params.get("_meta"), dict),
                    mcp_method=(request.headers.get("mcp-method") or "")[:40],
                    tem_sessao=bool(request.headers.get("mcp-session-id")),
                    chave=estado, **detalhe)
    if estado != "ok":
        # 🚨 a assinatura da #1038: chave emitida há pouco NESTE host e a chamada
        # chega sem ela. A sonda de cadastro (initialize via python-httpx, antes
        # do login) é legítima e não conta.
        t = _ULTIMA_CHAVE_EMITIDA.get(host)
        seg = int(_agora() - t) if t else None
        base_log["seg_desde_ultima_chave_deste_host"] = seg
        base_log["processo_desde_seg"] = int(_agora() - _PROCESSO_DESDE)
        base_log["suspeita_1038"] = bool(seg is not None and seg < 1800
                                         and not quem["ua"].lower().startswith("python-httpx"))
        _registrar("mcp-sem-chave" if estado == "sem-cabecalho" else "mcp-chave-recusada", base_log, ip)
        return _pede_chave(estado, host)
    base_log["geracao"] = chave.get("geracao")
    base_log["resta_s"] = int(chave["exp"] - _agora())
    if bruto is None:
        _registrar("mcp", dict(base_log, http=413, motivo="corpo grande demais"), ip)
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32600, "message": "Request too large"}}, status_code=413)
    if isinstance(corpo, list):
        # lote saiu na 2025-06-18; não negociamos a 2025-03-26
        _registrar("mcp", dict(base_log, http=400, motivo="lote"), ip)
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32600, "message": "Batch not supported"}},
                            status_code=400)
    if not isinstance(corpo, dict):
        _registrar("mcp", dict(base_log, http=400, motivo="corpo ilegível"), ip)
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "Parse error"}}, status_code=400)
    if _pedido_de_2026(msg, versao_cab):
        # 🔑 400 com corpo VAZIO: é o sinal sem ambiguidade pra o cliente 2026
        # voltar ao initialize. Corpo com -32022/-32020/-32601 faz ele concluir
        # que o servidor é moderno e NÃO voltar (spec 2026-07-28, streamable-http,
        # "Backward Compatibility"). E nunca Mcp-Session-Id aqui.
        _registrar("mcp", dict(base_log, http=400, motivo="era 2026 — pedindo a volta"), ip)
        return Response(status_code=400)
    resposta = _responder(msg, chave, versao_cab or base_log["versao_pedida"])
    _registrar("mcp", dict(base_log, http=200 if resposta else 202), ip)
    if resposta is None:
        return Response(status_code=202)       # notificação: 202 SEM corpo
    return JSONResponse(resposta)


@router.get(CAMINHO_MCP)
@router.get(CAMINHO_MCP + "/")
@router.delete(CAMINHO_MCP)
@router.delete(CAMINHO_MCP + "/")
async def mcp_sem_post(request: Request):
    if not ligado():
        return _nao_existe()
    # o Claude abre um GET de SSE depois do initialized e segue com 405 (#1013)
    estado, _, detalhe = _chave_valida(request, _host(request))
    _registrar("mcp-get", dict(_quem(request), metodo_http=request.method, chave=estado, **detalhe),
               _ip(request))
    r = Response(status_code=405)
    r.headers["Allow"] = "POST"
    return r
