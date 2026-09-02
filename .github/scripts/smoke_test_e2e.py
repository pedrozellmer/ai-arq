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
        # ── Testar o ORIGIN, contornando o Cloudflare (sem enfraquecer nada) ──
        # Desde 23/07 o site está atrás do CF (Fase 2) com Bot Fight Mode ligado.
        # O BFM serve um interstitial ("Executando verificação de segurança") pro
        # browser automatizado — a login.html nem chega, então o teste morria.
        # E a doc oficial é clara: BFM NÃO é bypassável (skip/allow/WAF não têm
        # efeito). A alternativa a DESLIGAR a proteção é apontar o browser direto
        # pro servidor de origem: mesmo conteúdo, mesmo backend, cert válido,
        # sem passar pelo CF. Verificado 27/07 com curl --resolve:
        #   ai.arq.br     → GitHub Pages : 200, cert OK, #login-email presente
        #   api.ai.arq.br → Render       : 200, cert OK
        # 🪤 A camada Cloudflare continua coberta pelo NÍVEL 1 (que bate em
        # ai.arq.br através do CF). Aqui o alvo é o fluxo do cliente (bug Daniela).
        # IPs resolvidos em runtime (não hardcode) — se a resolução falhar, cai
        # no caminho normal e o skip do BFM abaixo evita alarme falso.
        import socket

        def _resolve(host: str):
            try:
                return socket.gethostbyname(host)
            except Exception:
                return None

        # Só o SITE vai por IP (GitHub Pages tem IP estável e documentado).
        # A API NÃO: o IP do Render rotaciona (vi .8/.9 → .15 → .7 no mesmo dia)
        # e mapear por IP quebrou o CORS dentro do Chromium ("Response to
        # preflight request doesn't pass" + ERR_FAILED, run 9bf2b24) mesmo com o
        # preflight respondendo 200 no curl. Pra API uso REESCRITA DE URL
        # (page.route) pro hostname real do Render — nome real, cert real,
        # DNS real, sem passar pelo nosso Cloudflare. Ver _reroute_api abaixo.
        _rules = []
        _pages_ip = _resolve("pedrozellmer.github.io")   # origem do site
        if _pages_ip:
            _rules.append(f"MAP ai.arq.br {_pages_ip}")
            _rules.append(f"MAP www.ai.arq.br {_pages_ip}")

        _args = ["--disable-blink-features=AutomationControlled"]
        if _rules:
            _args.append("--host-resolver-rules=" + ",".join(_rules))
            print(f"[e2e] testando o ORIGIN direto (contorna Cloudflare/BFM): {_rules}",
                  flush=True)
        else:
            print("[e2e] não resolvi os IPs de origem — seguindo pelo Cloudflare",
                  flush=True)

        browser = p.chromium.launch(headless=True, args=_args)
        context = browser.new_context(
            accept_downloads=True,
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
            locale="pt-BR",
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()

        # ── API: reescreve api.ai.arq.br → ai-arq.onrender.com ───────────────
        # O site em produção chama a API em api.ai.arq.br, que passa pelo nosso
        # Cloudflare — e o Bot Fight Mode derruba essas chamadas no browser
        # automatizado (comprovado run 9bf2b24: "blocked by CORS policy:
        # Response to preflight request doesn't pass" + ERR_FAILED em TODAS:
        # /notify/welcome, /credits/balance, /projects/by-user; a tela mostrou
        # "Erro ao carregar: Failed to fetch"). Aqui trocamos o hostname pelo
        # endereço direto do Render: MESMO backend, cert real, DNS real, sem CF.
        # Funciona pro CORS porque o backend responde 'access-control-allow-
        # origin: *' (verificado no curl). É o mesmo alvo que o nível 2 já usa.
        _rerouted = {"n": 0}

        def _reroute_api(route):
            try:
                _u = route.request.url
                if "api.ai.arq.br" in _u:
                    _rerouted["n"] += 1
                    route.continue_(url=_u.replace("https://api.ai.arq.br",
                                                   "https://ai-arq.onrender.com"))
                else:
                    route.continue_()
            except Exception:
                try:
                    route.continue_()
                except Exception:
                    pass

        page.route("https://api.ai.arq.br/**", _reroute_api)

        # Diagnóstico: guarda erro de console e requisição que FALHOU. Sem isso,
        # "nenhum projeto apareceu" não diz se foi a chamada da API que quebrou,
        # JS com erro, ou só a aba que não abriu (investigação 27/07).
        console_errs: list[str] = []
        failed_reqs: list[str] = []
        page.on("console", lambda m: (
            console_errs.append(f"{m.type}: {m.text[:160]}")
            if m.type == "error" else None))
        page.on("requestfailed", lambda r: failed_reqs.append(
            f"{r.method} {r.url[:110]} :: {r.failure}"))

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
                body_txt = page.locator("body").inner_text()[:300].replace("\n", " ")
            except Exception:
                pass

            # BOT FIGHT MODE (Cloudflare Free): se o que veio foi a tela de
            # "verificação de segurança", o teste NÃO conseguiu nem começar —
            # não é falha do produto. Comprovado 27/07: corpo = "Executando
            # verificação de segurança ... verifica se você não é um bot".
            # A doc oficial diz que BFM NÃO é bypassável (skip/allow/WAF não têm
            # efeito) — só desligando em Security → Settings → Bot traffic.
            # Enquanto estiver ligado, SKIPA com aviso em vez de falhar: alarme
            # diário que sempre é falso-positivo treina a gente a ignorar e-mail
            # de smoke test — e aí o dia que quebrar de verdade passa batido.
            # Qualquer OUTRA falha (login, projeto, download) segue alarmando.
            low = body_txt.lower()
            if any(s in low for s in ("verificação de segurança", "verificacao de seguranca",
                                      "just a moment", "checking your browser",
                                      "não é um bot", "nao e um bot", "security check")):
                print("::warning::Smoke E2E pulado: Cloudflare Bot Fight Mode "
                      "bloqueou o browser de teste (não é problema do site). "
                      "Pra restaurar: Cloudflare → Security → Settings → Bot traffic "
                      "→ desligar Bot fight mode.", flush=True)
                print(f"[skip-e2e] tela de desafio do Cloudflare: '{body_txt[:160]}'", flush=True)
                try:
                    browser.close()
                except Exception:
                    pass
                return 0

            failures.append(
                f"#login-email não ficou visível em 60s. URL={page.url} | corpo='{body_txt}'"
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
            # Captura o que a TELA disse — a msg de erro do login aparece em
            # #email-login-error. Sem isso a falha vira "não redirecionou" e não
            # dá pra saber se foi credencial, rate-limit do Supabase ou rede.
            _err_txt = ""
            try:
                _el = page.locator("#email-login-error")
                if _el.count() and _el.first.is_visible():
                    _err_txt = _el.first.inner_text()[:200]
            except Exception:
                pass
            if not _err_txt:
                try:
                    _err_txt = page.locator("body").inner_text()[:200].replace("\n", " ")
                except Exception:
                    pass
            failures.append(
                f"login não redirecionou pra dashboard em 20s; URL final={page.url} "
                f"| msg da tela='{_err_txt}'"
            )
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
            # Diagnóstico rico: separa "link existe mas está escondido" (aba não
            # abriu) de "a lista nem carregou" (chamada da API falhou).
            _n_dom = 0
            try:
                _n_dom = page.locator(proj_selector).count()
            except Exception:
                pass
            _body = ""
            try:
                _body = " ".join(page.locator("body").inner_text()[:220].split())
            except Exception:
                pass
            failures.append(
                f"nenhum projeto VISÍVEL no dashboard em 30s "
                f"(links no DOM={_n_dom} → {'escondido/aba fechada' if _n_dom else 'lista não carregou'}); "
                f"chamadas de API reescritas p/ Render={_rerouted['n']}; "
                f"URL={page.url} | tela='{_body}'"
            )
            if failed_reqs:
                failures.append("requisições que falharam: " + " || ".join(failed_reqs[:4]))
            if console_errs:
                failures.append("erros de console: " + " || ".join(console_errs[:4]))
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
        # 🩸 02/09/2026 — ESTE PASSO PINTOU O CI DE VERMELHO SEM DEFEITO NENHUM.
        # Ele esperava `networkidle` e falhava DURO no timeout. Só que um push que
        # toca `backend/main.py` reinicia o Render, e o smoke roda logo em
        # seguida: os fetches da página ficam pendurados, a rede nunca fica
        # quieta, e 30 s depois o build ficava vermelho com a mensagem
        # "projeto.html não carregou em 30s" — enquanto a página, medida na mão
        # no mesmo minuto, respondia em 0,45 s.
        # 📏 Medido: 1 falha em 40 runs do smoke, e foi exatamente essa.
        # 🪤 A incoerência estava escrita duas telas acima: o passo do dashboard
        # JÁ tolera o mesmo atraso ("fetch ao backend pode demorar se o Render
        # estava dormindo") e segue em frente. Aqui a mesma causa era fatal.
        # 🔑 `networkidle` é contrato errado pra uma página que consulta o
        # backend: a prova de que ela carregou não é a rede calar, é o botão
        # "Baixar XLSX" ficar clicável — e o passo 3 já cobra exatamente isso,
        # com mensagem própria. Aqui basta abrir a página.
        try:
            page.goto(href, wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeoutError:
            failures.append(f"projeto.html?job_id={job_id} não abriu em 30s")
            return _close_and_report(browser, failures)
        # Folga pra a página se acalmar, sem transformar backend frio em falha.
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except PlaywrightTimeoutError:
            print("[e2e] projeto.html ainda com rede ativa; sigo pro botão",
                  flush=True)

        # ── 2b. ABRIR A VISTA DO QUANTITATIVO ────────────────────
        # 🚨 Em 04/08/2026 a página do projeto foi dividida em 4 VISTAS e o
        # #btn-download passou a morar dentro de <div class="vista"
        # data-vista="quantitativo" hidden>. A vista que abre por padrão é a
        # 'visao', então o botão EXISTE no DOM e está invisível: o clique do
        # bloco 4 estourava por falta de visibilidade e a mensagem de falha
        # acusava "provável 401 ou 404 do backend" — diagnóstico errado, num
        # alarme que passaria a soar a cada push. Alarme que é sempre falso é
        # alarme que se aprende a ignorar.
        # De quebra, agora o teste cobre a navegação por vistas — justamente o
        # que quebrou naquela noite.
        try:
            page.evaluate(
                """() => {
                    if (typeof window.mostrarVista === 'function') {
                        window.mostrarVista('quantitativo');
                    } else {
                        location.hash = '#quantitativo';
                    }
                }"""
            )
        except Exception as e:
            failures.append(f"não consegui abrir a vista 'quantitativo': {e}")
            return _close_and_report(browser, failures)

        # ── 3. Esperar btn-download habilitar E ficar VISÍVEL ────
        # `state="visible"` é o ponto: sem ele, o teste aprovava um botão dentro
        # de uma vista escondida e só quebrava no clique, com a mensagem errada.
        try:
            page.wait_for_selector("#btn-download", state="visible", timeout=20_000)
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
            failures.append(
                "#btn-download não ficou clicável: ou continua invisível (a vista "
                "'quantitativo' não abriu) ou o pointer-events ficou em 'none'"
            )
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
            # Emite também como ANNOTATION do Actions (::error::). Motivo prático:
            # baixar o LOG do job exige permissão de admin no repo, mas as
            # annotations são legíveis pela API pública (/check-runs/{id}/
            # annotations). Assim o diagnóstico chega sem depender de print
            # manual — foi o que travou a investigação de 25-27/07.
            _one = " ".join(str(f).split())[:400]
            print(f"::error::[E2E] {_one}", flush=True)
        return 1
    print("[ok-e2e] download via browser real funcionou", flush=True)
    return 0


if __name__ == "__main__":
    # stdout UTF-8 (Windows usa cp1252 default → quebra com emoji/acento)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    # Sem retry: tentei (26/07) e NÃO ajuda — as 2 tentativas rodam na mesma
    # máquina/sessão do runner, então repetem exatamente o mesmo resultado
    # (medido: 142s = 60s + 20s + 60s, as duas falhando igual). O tratamento
    # certo é o skip explícito do Bot Fight Mode acima, não repetir o erro.
    sys.exit(main())
