"""
Smoke test contra produção do AI.arq.

Roda em 2 níveis:
  NÍVEL 1 (sempre, sem credencial): health, endpoints públicos, sintaxe
  NÍVEL 2 (opcional, se SMOKE_USER_EMAIL+SMOKE_USER_PASSWORD setados):
    autentica via Supabase Auth, baixa planilha de um job real, valida 200.

Origem: bug de 2026-05-18 onde a cliente-65 tentou baixar planilha e recebeu
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


# ═══════════════════════════════════════════════════════════════════
#  RASTREADORES DE IA (11/10/2026)
# ═══════════════════════════════════════════════════════════════════
# 🔎 Estudo de SEO de 11/10: em 30 dias, 41 cadastros disseram ter vindo por IA (Google IA,
# Gemini, ChatGPT…) contra 39 da busca comum. Regra da casa: rastreador de IA NUNCA é
# bloqueado. Só que isso vivia de uma conferência à mão — e um botão no Cloudflare ("Block AI
# bots", ou o robots.txt gerenciado) desliga o canal inteiro sem ninguém ver.
# Duas medidas, porque nenhuma basta sozinha:
#   1. o robots.txt QUE ESTÁ NO AR (o Cloudflare pode servir outro, por cima do nosso) não
#      pode ter `Disallow: /` pra nenhum desses robôs — conteúdo, não depende do IP;
#   2. cada robô pede três páginas e tem que levar 200.
# 🪤 O runner do GitHub é IP de datacenter, e o Cloudflare às vezes barra TODO MUNDO que vem
# dele (25/08, ver `_e_bloqueio_do_cloudflare`). Por isso a medida 2 compara com o navegador
# na MESMA rodada: navegador 200 + robô 403 = o bloqueio é do robô (FALHA); os dois barrados
# = o IP do runner, não medido (INCONCLUSIVO). Sem a comparação isto viraria alarme falso.
ROBOS_DE_IA = {
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot",
    "OAI-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot",
    "ClaudeBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "PerplexityBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
}
PAGINAS_DOS_ROBOS = ("/", "/faq.html", "/llms.txt")
# nomes que o robots.txt usa (inclui os que não são um User-Agent de requisição, como Google-Extended)
ROBOS_NO_ROBOTS = ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User", "Claude-SearchBot",
                   "PerplexityBot", "Perplexity-User", "Google-Extended", "Applebot-Extended", "CCBot",
                   "Googlebot", "bingbot")


def robos_barrados_no_robots(texto: str, robos=ROBOS_NO_ROBOTS) -> list:
    """Quais robôs o robots.txt manda embora do site inteiro (`Disallow: /`).

    Lê por grupo, como os rastreadores: vale o grupo com o nome do robô; sem grupo próprio,
    vale o `*`. `Disallow: /blog` ou `Disallow: /_*` não contam — só o site inteiro.
    """
    grupos, agentes, regras, lendo_regras = [], [], [], False
    for linha in (texto or "").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if ":" not in linha:
            continue
        campo, valor = [p.strip() for p in linha.split(":", 1)]
        campo = campo.lower()
        if campo == "user-agent":
            if lendo_regras:                      # começou outro grupo
                grupos.append((agentes, regras))
                agentes, regras, lendo_regras = [], [], False
            agentes.append(valor.lower())
        elif campo in ("disallow", "allow"):
            lendo_regras = True
            regras.append((campo, valor))
    if agentes:
        grupos.append((agentes, regras))

    def _barra_tudo(regras_do_grupo):
        return any(c == "disallow" and v == "/" for c, v in regras_do_grupo) and \
            not any(c == "allow" and v == "/" for c, v in regras_do_grupo)

    barrados = []
    for robo in robos:
        proprios = [r for a, r in grupos if robo.lower() in a]
        gerais = [r for a, r in grupos if "*" in a]
        vale = proprios or gerais
        if any(_barra_tudo(r) for r in vale):
            barrados.append(robo)
    return barrados


def veredito_do_robo(status_navegador: int, status_robo: int, robo_barrado_pelo_cloudflare: bool) -> str:
    """'ok' | 'falha' | 'inconclusivo' — ver o comentário de ROBOS_DE_IA."""
    if status_robo == 200:
        return "ok"
    if robo_barrado_pelo_cloudflare and status_navegador != 200:
        return "inconclusivo"                     # o IP do runner está barrado pra todo mundo
    return "falha"


def _check_robos_de_ia() -> None:
    # 1. o robots.txt que está no ar
    status, body, headers = _get(f"{SITE_BASE}/robots.txt")
    if _e_bloqueio_do_cloudflare(status, headers, body):
        print(f"  {YELLOW}?{RESET} robots.txt libera os robôs de IA  (HTTP 403 do Cloudflare — NAO MEDIDO)")
        inconclusivos.append("robots.txt (robôs de IA): Cloudflare barrou o IP do runner (403)")
    elif status != 200:
        _check("robots.txt libera os robôs de IA", False, f"HTTP {status} ao ler o robots.txt")
    else:
        barrados = robos_barrados_no_robots(body.decode("utf-8", "replace"))
        _check("robots.txt libera os robôs de IA", not barrados,
               ("no ar ele barra: " + ", ".join(barrados) + " — o Cloudflare pode estar servindo um "
                "robots.txt por cima do nosso (AI Crawl Control)") if barrados else "")

    # 2. cada robô pede as páginas; o navegador pede junto, pra comparar
    for nome, ua in ROBOS_DE_IA.items():
        piores = {"ok": 0, "inconclusivo": 0, "falha": 0}
        detalhe = ""
        for pagina in PAGINAS_DOS_ROBOS:
            url = f"{SITE_BASE}{pagina}"
            st_robo, body_r, head_r = _get(url, headers={"User-Agent": ua}, tentativas=1)
            if st_robo == 200:
                piores["ok"] += 1
                continue
            st_nav, _, _ = _get(url, tentativas=1)
            v = veredito_do_robo(st_nav, st_robo, _e_bloqueio_do_cloudflare(st_robo, head_r, body_r))
            piores[v] += 1
            detalhe = f"{pagina}: robô HTTP {st_robo}, navegador HTTP {st_nav}"
        rotulo = f"{nome} recebe o site"
        if piores["falha"]:
            _check(rotulo, False, detalhe + " — o robô está barrado e o navegador não: olhe o AI Crawl "
                   "Control / 'Block AI bots' no Cloudflare")
        elif piores["inconclusivo"]:
            print(f"  {YELLOW}?{RESET} {rotulo}  ({detalhe} — NAO MEDIDO)")
            inconclusivos.append(f"{rotulo}: Cloudflare barrou o IP do runner ({detalhe})")
        else:
            _check(rotulo, True, f"{piores['ok']} páginas, HTTP 200")


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
    print(f"  {mark} {name}" + (f"  ({detail})" if detail else ""))
    if ok:
        passes.append(name)
    else:
        failures.append(f"{name}: {detail or 'falhou'}")
    return ok


def _get(url: str, headers: dict | None = None, timeout: int = 60,
         tentativas: int = 3) -> tuple[int, bytes, dict]:
    """GET retorna (status, body_bytes, headers_dict).

    🚨 28/08/2026 — O SMOKE MENTIU A CAUSA E MANDOU O PEDRO PRO LUGAR ERRADO.
    O e-mail que ele recebeu dizia duas coisas, e as duas eram sintoma:

        GET /api/instagram/scheduler/list exige admin  (HTTP 502, esperado 401)
        GET /api/projects/by-user — lista  (0 projetos)

    A segunda era MENTIRA: não eram 0 projetos, era o mesmo 502. A causa real
    (achada indo no log do Render) é que o servidor congelava por 33 s na
    virada da hora — as rotinas do relógio eram `async` com corpo bloqueante.

    🔑 Erro de TRANSPORTE não pode virar afirmação sobre o NEGÓCIO. 5xx é "o
    servidor não respondeu", nunca "o cliente não tem projeto". É a mesma
    família do achado de 05/08: 53 de 74 falhas que a gente culpava o cliente
    eram nossas.

    🪤 O retry é curto de propósito. Retry generoso vira o erro oposto — um
    smoke que fica verde escondendo instabilidade real é pior que um que grita
    errado, porque ninguém vai olhar.
    """
    h = {"User-Agent": BROWSER_UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, method="GET", headers=h)
    ultimo = (0, b"", {})
    for i in range(max(1, tentativas)):
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            try:
                ultimo = (e.code, e.read(), dict(e.headers or {}))
            except Exception:
                ultimo = (e.code, b"", {})
            # 5xx = servidor engasgado; 4xx é resposta legítima, não insiste
            if not (500 <= e.code < 600) or i == tentativas - 1:
                return ultimo
        except Exception as e:                       # timeout, DNS, conexão
            ultimo = (0, str(e).encode("utf-8", "replace"), {})
            if i == tentativas - 1:
                return ultimo
        print(f"  {YELLOW}!{RESET} {url.split('/api/')[-1][:40]}: HTTP "
              f"{ultimo[0] or 'sem resposta'} — tentando de novo "
              f"({i + 2}/{tentativas})")
        time.sleep(4 * (i + 1))
    return ultimo


def _transporte_falhou(status: int) -> str | None:
    """Devolve a explicação quando o problema é de TRANSPORTE, não de negócio.

    🚨 Existe pra impedir que 502 vire "0 projetos" de novo. Toda checagem que
    depende de uma resposta do servidor tem que passar por aqui ANTES de
    afirmar qualquer coisa sobre o conteúdo.
    """
    if status == 0:
        return "o servidor não respondeu (timeout ou conexão)"
    if 500 <= status < 600:
        return (f"o servidor devolveu HTTP {status} — ISTO NÃO É UM PROBLEMA "
                f"DE DADO, é o backend fora do ar ou travado. Olhe o log do "
                f"Render antes de procurar no banco.")
    return None


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

    # 11/10: os rastreadores de IA continuam entrando? (o canal de 41 cadastros em 30 dias)
    _check_robos_de_ia()

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


def _list_user_projects(user_id: str, jwt: str) -> tuple[list, str | None]:
    """Lista projetos do user. Devolve (projetos, motivo_da_falha).

    🚨 Antes devolvia só a lista e fazia `if status != 200: return []`. Um 502
    virava "0 projetos" e o e-mail de falha mandava procurar no lugar errado.
    Agora o motivo volta junto e quem chama decide o que dizer.
    """
    url = f"{API_BASE}/api/projects/by-user/{user_id}"
    status, body, _ = _get(url, headers={"Authorization": f"Bearer {jwt}"})
    ruim = _transporte_falhou(status)
    if ruim:
        return [], ruim
    if status != 200:
        return [], f"HTTP {status} (esperado 200)"
    try:
        data = json.loads(body)
        return (data.get("projects", []) if isinstance(data, dict) else []), None
    except Exception as e:
        return [], f"resposta não é JSON válido: {e}"


def nivel_2():
    email = os.environ.get("SMOKE_USER_EMAIL")
    password = os.environ.get("SMOKE_USER_PASSWORD")
    if not email or not password:
        print(f"\n{YELLOW}━━━ NÍVEL 2 — skipado (SMOKE_USER_EMAIL+SMOKE_USER_PASSWORD não setados) ━━━{RESET}")
        print(f"  Pra ativar: setar essas 2 env vars com credencial de um usuário real.")
        print(f"  Esse nível pega o bug da cliente-65 (404 em download).")
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
    projects, motivo = _list_user_projects(user_id, jwt)
    _check(
        "GET /api/projects/by-user — lista",
        len(projects) > 0,
        # 🔑 o motivo REAL na frente. "0 projetos" só aparece quando foi
        # mesmo 0 projetos, com o servidor tendo respondido 200.
        motivo or f"{len(projects)} projetos",
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

    # GET /api/items/{job_id} — endpoint protegido (bug da cliente-65)
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

    # GET /api/download/{job_id} — O TESTE QUE PEGARIA O BUG DA cliente-65
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
