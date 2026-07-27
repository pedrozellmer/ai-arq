"""
Smoke test E2E (browser real, headless) — pega bugs que o smoke HTTP NÃO pega.

Cenário que esse teste cobre e o smoke HTTP (smoke_test_production.py) NÃO pega:
  Endpoint protegido com `_require_project_owner` + frontend baixando arquivo via
  <a href>, window.open() ou window.location.href. Browsers NÃO enviam o header
  Authorization em navegação direta — só em fetch() explícito. Resultado: backend
  retorna 401 mesmo com sessão válida. Smoke HTTP testa o endpoint com Bearer
  manual e fica verde, mas o usuário real não consegue baixar.

Esse caso aconteceu com a Daniela Teixeira (DTZ Arquitetura) entre 13/05 e 18/05.
Ela ficou 5 dias clicando em "Baixar XLSX" e recebendo
  {"detail":"Autenticação requerida para acessar este projeto"}
porque o frontend usava `window.location.href = .../api/download/...` (sem JWT).

Esse teste teria pegado isso na 1ª execução. Por isso ele existe.

Fluxo:
  1. Loga no site via Supabase Auth (mesmo caminho do usuário real).
  2. Vai pra "Meus projetos", pega o 1º projeto da conta.
  3. Abre `projeto.html?job_id=...`, espera o botão "Baixar XLSX" habilitar.
  4. Clica e captura o download. Valida que veio XLSX > 500 bytes.

Skip silencioso se SMOKE_USER_EMAIL/PASSWORD não setados (cron público sem
credencial vira nível 1 só).
"""
import os
import sys

try:
    from playwright.sync_api import sync_playwright
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("[skip-e2e] playwright não instalado — pulando E2E", flush=True)
    sys.exit(0)


SITE = os.getenv("SMOKE_SITE_BASE", "https://ai.arq.br").rstrip("/")
EMAIL = os.getenv("SMOKE_USER_EMAIL", "").strip()
PASSWORD = os.getenv("SMOKE_USER_PASSWORD", "").strip()


def main() -> int:
    if not EMAIL or not PASSWORD:
        print("[skip-e2e] SMOKE_USER_EMAIL/PASSWORD não setados — pulando E2E", flush=True)
        return 0

    failures: list[str] = []

    with sync_playwright() as p:
        # Desde 23/07 o site está atrás do Cloudflare (Fase 2). O CF injeta em
        # TODA página o script de desafio invisível (/cdn-cgi/challenge-platform/
        # scripts/jsd/main.js + window.__CF$cv$params) — comprovado 27/07 baixando
        # a login.html com UA de HeadlessChrome. Pra gente ele roda em silêncio;
        # pra browser automatizado ele detecta a automação e ATRASA/segura a
        # página, então o #login-email não fica pronto e o fill estourava em 30s.
        # Mitigação: UA de Chrome normal (sem "HeadlessChrome") + flags que
        # escondem os sinais óbvios de automação. Não burla proteção nenhuma —
        # é o nosso próprio site, só evita que o CF trate o teste como bot.
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            accept_downloads=True,
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
            locale="pt-BR",
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()

        # ── 1. Login ─────────────────────────────────────────────
        print(f"[e2e] abrindo {SITE}/login.html", flush=True)
        try:
            page.goto(f"{SITE}/login.html", wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeoutError:
            failures.append(f"não carregou login.html em 30s ({SITE})")
            return _close_and_report(browser, failures)

        # Espera o campo ficar PRONTO antes de preencher. O desafio invisível do
        # Cloudflare pode atrasar a página alguns segundos no browser automatizado;
        # sem essa espera, o fill estourava em 30s e o teste falhava sem o site
        # ter problema nenhum (falso-positivo 25-27/07).
        try:
            page.wait_for_selector("#login-email", state="visible", timeout=60_000)
        except PlaywrightTimeoutError:
            body_txt = ""
            try:
                body_txt = page.locator("body").inner_text()[:200].replace("\n", " ")
            except Exception:
                pass
            failures.append(
                f"#login-email não ficou visível em 60s — possível desafio do "
                f"Cloudflare segurando a página. URL={page.url} | corpo='{body_txt}'"
            )
            return _close_and_report(browser, failures)

        try:
            page.fill("#login-email", EMAIL)
            page.fill("#login-password", PASSWORD)
            page.click('button[type="submit"]')
        except Exception as e:
            failures.append(f"erro ao preencher login: {e}")
            return _close_and_report(browser, failures)

        try:
            page.wait_for_url("**/dashboard.html*", timeout=20_000)
            print("[e2e] login OK, chegou no dashboard", flush=True)
        except PlaywrightTimeoutError:
            failures.append(f"login não redirecionou pra dashboard em 20s; URL final={page.url}")
            return _close_and_report(browser, failures)

        # ── 2. Pegar 1º projeto na aba "Meus projetos" do dashboard ───────
        # meus-projetos.html é só um redirect legado — a lista de projetos é
        # uma ABA dentro do dashboard, e os cards são carregados via fetch
        # async (não basta networkidle; é preciso esperar o seletor surgir).
        try:
            page.goto(f"{SITE}/dashboard.html#meus-projetos", wait_until="networkidle", timeout=30_000)
        except PlaywrightTimeoutError:
            print("[e2e] dashboard demorou; tentando seguir", flush=True)

        proj_selector = 'a[href*="projeto.html?job_id="]'
        try:
            # Espera os cards de projeto renderizarem (fetch ao backend pode
            # demorar se o Render estava dormindo).
            page.wait_for_selector(proj_selector, timeout=30_000)
        except PlaywrightTimeoutError:
            failures.append(
                "nenhum projeto apareceu no dashboard em 30s — a conta de "
                "teste precisa de ao menos 1 projeto processado, ou o "
                "carregamento da lista quebrou"
            )
            return _close_and_report(browser, failures)

        first = page.locator(proj_selector).first
        if first.count() == 0:
            failures.append("seletor de projeto não encontrou nenhum card no dashboard")
            return _close_and_report(browser, failures)

        href = first.get_attribute("href") or ""
        if href.startswith("projeto.html"):
            href = f"{SITE}/{href}"
        elif href.startswith("/"):
            href = f"{SITE}{href}"
        job_id = href.split("job_id=")[-1].split("&")[0]
        print(f"[e2e] abrindo projeto {job_id}", flush=True)
        try:
            page.goto(href, wait_until="networkidle", timeout=30_000)
        except PlaywrightTimeoutError:
            failures.append(f"projeto.html?job_id={job_id} não carregou em 30s")
            return _close_and_report(browser, failures)

        # ── 3. Esperar btn-download habilitar (JS remove pointer-events:none) ──
        try:
            page.wait_for_function(
                """() => {
                    const b = document.getElementById('btn-download');
                    if (!b) return false;
                    const cs = window.getComputedStyle(b);
                    return cs.pointerEvents !== 'none';
                }""",
                timeout=20_000,
            )
        except PlaywrightTimeoutError:
            failures.append("#btn-download nunca habilitou (pointer-events ficou em 'none')")
            return _close_and_report(browser, failures)

        # ── 4. Clicar e capturar o download ──────────────────────
        try:
            with page.expect_download(timeout=45_000) as dl_info:
                page.click("#btn-download")
            dl = dl_info.value
        except PlaywrightTimeoutError:
            # Tentar capturar o que apareceu — pode ter sido alert/erro inline
            page_url_now = page.url
            failures.append(
                f"clicar em #btn-download NÃO disparou download em 45s "
                f"(provável 401 ou 404 do backend); URL atual={page_url_now}"
            )
            return _close_and_report(browser, failures)

        # ── 5. Validar arquivo baixado ───────────────────────────
        suggested = dl.suggested_filename or ""
        tmp_path = dl.path()
        size = os.path.getsize(tmp_path) if tmp_path else 0
        print(f"[e2e] download capturado: {suggested} ({size} bytes)", flush=True)

        if size < 500:
            failures.append(f"XLSX baixado muito pequeno: {size} bytes (esperado > 500)")
        if not suggested.endswith(".xlsx"):
            failures.append(f"arquivo baixado não é .xlsx: {suggested}")

        return _close_and_report(browser, failures)


def _close_and_report(browser, failures: list[str]) -> int:
    try:
        browser.close()
    except Exception:
        pass
    if failures:
        print(f"\n[FAIL E2E] {len(failures)} problema(s):", flush=True)
        for f in failures:
            print(f"  - {f}", flush=True)
        return 1
    print("[ok-e2e] download via browser real funcionou", flush=True)
    return 0


if __name__ == "__main__":
    # stdout UTF-8 (Windows usa cp1252 default → quebra com emoji/acento)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    # RETRY 1x: desde 23/07 o site está atrás do Cloudflare (Fase 2). O runner
    # do GitHub Actions usa IP compartilhado no mundo inteiro — às vezes um IP
    # com reputação ruim (usado por outro CI em outro lugar) leva um desafio
    # automático do Cloudflare, sem relação com bug real (site/API testados na
    # mão continuam saudáveis nesses casos). Rodar 2x antes de alarmar reduz
    # falso-positivo sem esconder regressão de verdade (se falhar as 2, é sinal
    # forte). Ver memória: falhas 25-26/07 no mesmo commit que passou 23-24/07.
    import time
    rc = main()
    if rc != 0:
        print("\n[retry] 1ª tentativa falhou — pode ser desafio de rede transitório "
              "(IP do runner CI). Aguardando 20s e tentando de novo antes de alarmar...",
              flush=True)
        time.sleep(20)
        rc = main()
        if rc == 0:
            print("[retry] 2ª tentativa passou — confirma que foi transitório.", flush=True)
    sys.exit(rc)
