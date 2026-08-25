"""
Smoke test contra produção do AI.arq.

Roda em 2 níveis:
  NÍVEL 1 (sempre, sem credencial): health, endpoints públicos, sintaxe
  NÍVEL 2 (opcional, se SMOKE_USER_EMAIL+SMOKE_USER_PASSWORD setados):
    autentica via Supabase Auth, baixa planilha de um job real, valida 200.

Origem: bug de 2026-05-18 onde a Daniela tentou baixar planilha e recebeu
404 'Projeto não encontrado'. A auditoria de seg de 2026-05-13 adicionou
_require_project_owner em vários endpoints, mas a função _get_project_owner
usava anon-key e a RLS bloqueava → 404 silencioso por 5 dias. Smoke test
NÍVEL 2 cobre exatamente esse caminho.

Uso:
  python smoke_test_production.py                    # nível 1 só
  SMOKE_USER_EMAIL=x SMOKE_USER_PASSWORD=y python smoke_test_production.py

Exit code:
  0 = todos passaram
  1 = algum falhou (CI deve quebrar build)

Roda em ~10s (nível 1) ou ~25s (com nível 2).
"""
from __future__ import annotations
import os
import sys
import json
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional

API_BASE = os.environ.get("AI_ARQ_API", "https://ai-arq.onrender.com")
SITE_BASE = os.environ.get("AI_ARQ_SITE", "https://ai.arq.br")
SUPABASE_URL = "https://kqjabzwgbfuivzlcfvvu.supabase.co"
SUPABASE_ANON = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24i"
    "LCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"
)

# ANSI colors (funciona em Linux/Mac/Windows Terminal)
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

# UA de navegador: desde 23/07 o site está atrás do Cloudflare (proxy laranja),
# que devolve 403 pra User-Agent com cara de robô (ex.: 'Python-urllib'). O site
# é feito pra navegador — bloquear bot é o comportamento desejado —, então o
# smoke test se identifica como browser pra não ser barrado. (Confirmado:
# urllib→403, browser UA→200, Server: cloudflare.)
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

failures: list[str] = []
passes: list[str] = []
# 🚨 25/08/2026: coisa que o smoke NAO CONSEGUIU MEDIR nao pode virar nem
# "passou" nem "falhou". Ver `_check_site`.
inconclusivos: list[str] = []


def _e_bloqueio_do_cloudflare(status: int, headers: dict, body: bytes) -> bool:
    """O 403 veio do Cloudflare barrando o IP, ou do site?

    🚨 25/08/2026. O smoke ficou vermelho no commit 2cccde0 com tres 403 em
    ai.arq.br — e o site estava PERFEITO: do meu IP as tres davam 200 no mesmo
    minuto. O que mudou foi o IP: o runner do GitHub e datacenter, e o
    Cloudflare (proxy laranja desde 23/07) barra por reputacao, mesmo com
    User-Agent de navegador. Medido no dia: UA de robo do meu IP tambem leva
    403, UA de browser leva 200.

    🪤 Entao esse check estava medindo "o Cloudflare deixa este IP entrar", e
    nao "o site esta no ar" — e gastou uma hora minha e do Pedro achando que
    era o deploy. Nao da pra transformar em verde: seria pass silencioso, o
    pecado que esta casa persegue. Vira INCONCLUSIVO, declarado e contado.

    🚫 Falha FECHADA: so e inconclusivo com marca do Cloudflare no cabecalho.
    403 sem essas marcas continua sendo falha de verdade.
    """
    if status != 403:
        return False
    baixo = {str(k).lower(): str(v).lower() for k, v in (headers or {}).items()}
    if "cf-mitigated" in baixo or "cf-ray" in baixo:
        return True
    if "cloudflare" in baixo.get("server", ""):
        return True
    return b"cloudflare" in (body or b"").lower()[:4000]


def _check_site(name: str, url: str, marcador: bytes) -> bool:
    """Check de pagina publica, ciente de que o Cloudflare fica na frente."""
    status, body, headers = _get(url)
    if _e_bloqueio_do_cloudflare(status, headers, body):
        print(f"  {YELLOW}?{RESET} {name}  (HTTP 403 do Cloudflare — NAO MEDIDO)")
        inconclusivos.append(f"{name}: Cloudflare barrou o IP do runner (403)")
        return False
    return _check(name, status == 200 and marcador in body.lower(), f"HTTP {status}")


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
    print(f"  {mark} {name}" + (f"  ({detail})" if detail else ""))
    if ok:
        passes.append(name)
    else:
        failures.append(f"{name}: {detail or 'falhou'}")
    return ok


def _get(url: str, headers: dict | None = None, timeout: int = 60) -> tuple[int, bytes, dict]:
    """GET retorna (status, body_bytes, headers_dict)."""
    h = {"User-Agent": BROWSER_UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, method="GET", headers=h)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read(), dict(e.headers or {})
        except Exception:
            return e.code, b"", {}


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 60) -> tuple[int, bytes]:
    h = {"Content-Type": "application/json", "User-Agent": BROWSER_UA}
    if headers:
        h.update(headers)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers=h)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b""


# ═══════════════════════════════════════════════════════════════════
#  NÍVEL 1 — Sem credencial
# ═══════════════════════════════════════════════════════════════════

def nivel_1():
    print(f"\n{BLUE}━━━ NÍVEL 1 — endpoints públicos ━━━{RESET}")

    # Backend root
    status, body, _ = _get(f"{API_BASE}/")
    _check(
        "GET /",
        status == 200 and b"AI.arq API" in body,
        f"HTTP {status}",
    )

    # Site publico: passa pelo Cloudflare, entao usa o check que sabe
    # distinguir "site caiu" de "o Cloudflare barrou este IP".
    _check_site("GET ai.arq.br/", f"{SITE_BASE}/", b"<html")
    _check_site("GET sitemap.xml", f"{SITE_BASE}/sitemap.xml", b"<urlset")
    _check_site("GET faq.html", f"{SITE_BASE}/faq.html", b"<title>")

    # Instagram: a rota FICOU FECHADA em 28/07/2026 (antes qualquer um lia a
    # fila e as DMs). O teste agora confirma o oposto do que confirmava: sem
    # token tem que dar 401/403. Se voltar 200, o gate caiu — isso é a falha.
    status, body, _ = _get(f"{API_BASE}/api/instagram/scheduler/list?limit=1")
    _check(
        "GET /api/instagram/scheduler/list exige admin",
        status in (401, 403),
        f"HTTP {status} (esperado 401 ou 403)",
    )


# ═══════════════════════════════════════════════════════════════════
#  NÍVEL 2 — Com credencial (opt-in via env vars)
# ═══════════════════════════════════════════════════════════════════

def _supabase_login(email: str, password: str) -> Optional[str]:
    """Loga no Supabase Auth, retorna access_token JWT."""
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    body = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_ANON,
            "Authorization": f"Bearer {SUPABASE_ANON}",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("access_token")
    except Exception as e:
        print(f"  {RED}✗{RESET} login Supabase falhou: {e}")
        return None


def _list_user_projects(user_id: str, jwt: str) -> list:
    """Lista projetos do user pra pegar um job_id válido pra testar."""
    url = f"{API_BASE}/api/projects/by-user/{user_id}"
    status, body, _ = _get(url, headers={"Authorization": f"Bearer {jwt}"})
    if status != 200:
        return []
    try:
        data = json.loads(body)
        return data.get("projects", []) if isinstance(data, dict) else []
    except Exception:
        return []


def nivel_2():
    email = os.environ.get("SMOKE_USER_EMAIL")
    password = os.environ.get("SMOKE_USER_PASSWORD")
    if not email or not password:
        print(f"\n{YELLOW}━━━ NÍVEL 2 — skipado (SMOKE_USER_EMAIL+SMOKE_USER_PASSWORD não setados) ━━━{RESET}")
        print(f"  Pra ativar: setar essas 2 env vars com credencial de um usuário real.")
        print(f"  Esse nível pega o bug da Daniela (404 em download).")
        return

    print(f"\n{BLUE}━━━ NÍVEL 2 — com credencial de {email} ━━━{RESET}")

    # Login
    jwt = _supabase_login(email, password)
    if not _check("Login Supabase Auth", bool(jwt), "sem JWT — checar credencial"):
        return

    # Pega user_id do token (JWT payload — base64 do meio)
    import base64
    try:
        payload_b64 = jwt.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # pad
        payload = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
        user_id = payload.get("sub")
    except Exception as e:
        _check("Decodificar JWT", False, str(e))
        return
    _check("Decodificar JWT", bool(user_id), f"user_id={user_id[:8]}...")

    # Lista projetos
    projects = _list_user_projects(user_id, jwt)
    _check(
        "GET /api/projects/by-user — lista",
        len(projects) > 0,
        f"{len(projects)} projetos",
    )

    if not projects:
        print(f"  {YELLOW}!{RESET} sem projetos pra testar download — crie um e rode de novo")
        return

    # Pega o mais recente com status=done
    done_projects = [p for p in projects if p.get("status") == "done"]
    if not done_projects:
        _check("Pelo menos 1 projeto status=done", False, "nenhum projeto done")
        return
    target = done_projects[0]
    job_id = target.get("job_id")
    _check(
        "Pelo menos 1 projeto status=done",
        bool(job_id),
        f"job_id={job_id}",
    )

    # GET /api/items/{job_id} — endpoint protegido (bug da Daniela)
    status, body, _ = _get(
        f"{API_BASE}/api/items/{job_id}",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    try:
        data = json.loads(body) if body else {}
        items_count = len(data.get("items", [])) if isinstance(data, dict) else 0
    except Exception:
        items_count = 0
    _check(
        f"GET /api/items/{job_id}",
        status == 200 and items_count >= 0,
        f"HTTP {status}, {items_count} itens",
    )

    # GET /api/cronograma/{job_id} — endpoint protegido
    status, body, _ = _get(
        f"{API_BASE}/api/cronograma/{job_id}",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    _check(
        f"GET /api/cronograma/{job_id}",
        status in (200, 404),  # 404 OK se cliente nunca gerou cronograma
        f"HTTP {status}",
    )

    # GET /api/projects/{job_id}/client — endpoint protegido
    status, body, _ = _get(
        f"{API_BASE}/api/projects/{job_id}/client",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    _check(
        f"GET /api/projects/{job_id}/client",
        status == 200,
        f"HTTP {status}",
    )

    # GET /api/projects/{job_id}/quotes — endpoint protegido
    status, body, _ = _get(
        f"{API_BASE}/api/projects/{job_id}/quotes",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    _check(
        f"GET /api/projects/{job_id}/quotes",
        status == 200,
        f"HTTP {status}",
    )

    # GET /api/download/{job_id} — O TESTE QUE PEGARIA O BUG DA DANIELA
    status, body, headers_d = _get(
        f"{API_BASE}/api/download/{job_id}",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    content_type = headers_d.get("Content-Type", "") or headers_d.get("content-type", "")
    is_xlsx = "spreadsheet" in content_type or "octet-stream" in content_type
    body_preview = body[:80] if not is_xlsx else b"(binario xlsx)"
    _check(
        f"GET /api/download/{job_id} — XLSX",
        status == 200 and is_xlsx,
        f"HTTP {status}, type={content_type}, preview={body_preview!r}",
    )


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

def main() -> int:
    # Força stdout UTF-8 no Windows (default cp1252 quebra com emoji)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"\n{BLUE}>> Smoke Test AI.arq{RESET}")
    print(f"   API:  {API_BASE}")
    print(f"   Site: {SITE_BASE}")
    print(f"   {time.strftime('%Y-%m-%d %H:%M:%S')}")

    start = time.time()
    try:
        nivel_1()
        nivel_2()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}interrompido pelo usuário{RESET}")
        return 130

    elapsed = time.time() - start
    print(f"\n{BLUE}━━━ Resumo ━━━{RESET}")
    print(f"  {GREEN}{len(passes)} passou{RESET}, "
          f"{RED if failures else GREEN}{len(failures)} falhou{RESET}, "
          f"{YELLOW}{len(inconclusivos)} não medido{RESET}, "
          f"em {elapsed:.1f}s")

    # 🚨 Inconclusivo aparece SEMPRE, mesmo quando o resto passou. Sumir com
    # ele seria transformar "não consegui olhar" em "está tudo bem" — que é
    # exatamente o erro que este bloco existe pra impedir.
    if inconclusivos:
        print(f"\n{YELLOW}Não medido (o Cloudflare respondeu no lugar do site):{RESET}")
        for i in inconclusivos:
            print(f"  ? {i}")
        print(f"  {YELLOW}O site pode estar de pé ou não — deste IP não dá pra saber.")
        print(f"  Quem mede o site com navegador de verdade é o nível 3 (E2E).{RESET}")

    if failures:
        print(f"\n{RED}Falhas:{RESET}")
        for f in failures:
            print(f"  • {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
