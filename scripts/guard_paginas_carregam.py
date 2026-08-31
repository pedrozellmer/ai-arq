#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trava de deploy no3: as paginas editadas CARREGAM sem erro de JavaScript.

Por que existe (31/08/2026): em 31/08 pela manha um recorte em `aiarq-utils.js`
deixou uma chave pra tras, o `window.sbClient` parou de ser criado e NINGUEM
conseguiu entrar no site por 12 minutos — com sintaxe valida e zero erro no
console daquele arquivo. Nasceu dali o `guard_front_contrato.py`, que cobre o
JS COMPARTILHADO. Mas os HTMLs tem milhares de linhas de JS INLINE que nenhum
guarda olhava: pyflakes nao ve JS, e todo teste da bancada le o FONTE.

Este guarda carrega cada pagina vigiada num Chrome headless de verdade e cobra:
  - zero erro de execucao no carregamento (SyntaxError inclusive);
  - as funcoes que a pagina PROMETE existir realmente existem depois do load.

Nao substitui o teste de tela (arquivo certo != tela certa): so prova que a
pagina nao nasce quebrada. E ja e mais do que tinhamos.

Falha FECHA a porta: sem Chrome, sem servidor ou com timeout, o push e barrado.
Emergencia: AIARQ_DEPLOY_FORCE=1 git push origin main
"""
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTA = int(os.environ.get("AIARQ_GUARD_PORTA_PAG", "8814"))

# pagina -> (query string, funcoes que precisam existir em window apos o load)
# 🪤 A QUERY IMPORTA: sem `?job_id=`, projeto.html nao chega a rodar o seu JS e
# a pagina termina em login.html — o guarda acusava "sonda ilegivel" com o
# codigo perfeitamente bom. Pagina que exige parametro tem que ser carregada
# COM o parametro, senao o guarda mede outra pagina.
VIGIADAS = {
    "admin-usuario.html": ("?id=00000000-0000-0000-0000-000000000000",
                           ["carregarFicha", "renderFicha", "renderChips",
                            "loadUserPage", "checkAdminAccess"]),
    "projeto.html": ("?job_id=teste",
                     ["postNps", "sendFeedback", "sendFeedbackComment",
                      "maybeShowFeedback", "_fbSalvaAntesDeSair"]),
    "dashboard.html": ("", ["__maybeShowNPS"]),
    "admin.html": ("", ["switchTab", "loadUsers", "renderUsers",
                        "loadEmailCatalog", "enviarEmailTeste",
                        "openEmailPreview"]),
    # Página que recebe o clique do e-mail. Não tem função global (o script é
    # uma IIFE): o contrato aqui é só "carrega sem erro" — que já é o que teria
    # pegado o apagão do login. A query imita um link real de e-mail.
    "obrigado.html": ("?tipo=projeto&k=teste&e=a%40b.com&n=4&t=xxx", []),
}

CHROMES = (
    os.environ.get("AIARQ_CHROME", ""),
    r"C:/Program Files/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
)

# Coletor injetado ANTES de tudo: pega erro de parse dos <script> seguintes.
_COLETOR = """<script>
window.__erros = [];
window.onerror = function (m, u, l) {
  window.__erros.push(String(m) + ' @' + String(u).split('/').pop() + ':' + l);
  return true;
};
window.addEventListener('unhandledrejection', function (e) {
  window.__erros.push('promise: ' + String((e.reason && e.reason.message) || e.reason));
});
window.fetch = function () { return Promise.resolve({
  ok: false, status: 0, json: function () { return Promise.resolve({}); },
  text: function () { return Promise.resolve(''); } }); };
</script>"""


# 🪤 Este duble SUBSTITUI a tag do supabase-js vinda do CDN. Injetar antes dela
# nao adianta: o UMD do CDN sobrescreve `window.supabase`, o aiarq-utils.js cria
# um cliente DE VERDADE, `getSession()` volta sem sessao e a pagina redireciona
# pro login — foi exatamente o que aconteceu nas 2 primeiras versoes deste
# guarda (o titulo dumpado vinha "Entrar — AI.arq").
# Sessao FALSA de proposito: sem ela nenhuma pagina logada chega a rodar.
_SUPA_STUB = """<script>
window.__sessaoFalsa = { access_token: 'tok-teste', user: {
  id: '00000000-0000-0000-0000-000000000000', email: 'teste@guarda.local',
  user_metadata: { full_name: 'Guarda Teste' } } };
window.supabase = { createClient: function () {
  var _q = { select: function(){ return _q; }, eq: function(){ return _q; },
             order: function(){ return _q; }, limit: function(){ return _q; },
             single: function(){ return Promise.resolve({ data: null, error: null }); },
             then: function(r){ return Promise.resolve({ data: [], error: null }).then(r); } };
  return { auth: {
    getSession: function () { return Promise.resolve({ data: { session: window.__sessaoFalsa } }); },
    getUser: function () { return Promise.resolve({ data: { user: window.__sessaoFalsa.user } }); },
    onAuthStateChange: function () { return { data: { subscription: { unsubscribe: function(){} } } }; },
    signOut: function () { return Promise.resolve({}); } },
    from: function () { return _q; },
    storage: { from: function () { return {
      download: function(){ return Promise.resolve({ data: null, error: null }); },
      createSignedUrl: function(){ return Promise.resolve({ data: null, error: null }); } }; } },
    rpc: function () { return Promise.resolve({ data: [], error: null }); },
    channel: function () { return { on: function(){ return this; },
                                    subscribe: function(){ return this; } }; } };
} };
</script>"""

_RE_SUPA_CDN = re.compile(
    r'<script src="https://cdn\.jsdelivr\.net/npm/@supabase/[^>]*></script>')


# Neutraliza o portao de admin: sem isto a pagina manda pro dashboard e a sonda
# nao roda. Nao afrouxa nada em producao — e injetado so na copia temporaria.
_ABRE_PORTAO = """<script>
window.aiarqEmailMatches = function () { return Promise.resolve(true); };
</script>"""


def injeta_sonda(html: str, sonda: str) -> str:
    """Poe a sonda antes do ULTIMO `</body>`.

    🪤 O PRIMEIRO `</body>` do arquivo pode estar DENTRO DE UMA STRING JS. Em
    admin.html existe um `document.write('…</body>')`: injetar ali metia um
    <script> no meio de uma string e QUEBRAVA a sintaxe da pagina. O guarda
    acusava "Uncaught SyntaxError" num arquivo perfeitamente bom e teria
    bloqueado todo push que tocasse o admin. Falso positivo em guarda e pior
    que guarda nenhum: ensina a usar o AIARQ_DEPLOY_FORCE.
    """
    i = html.rfind("</body>")
    return (html[:i] + sonda + html[i:]) if i >= 0 else html + sonda


def _chrome():
    for c in CHROMES:
        if c and os.path.isfile(c):
            return c
    return shutil.which("google-chrome") or shutil.which("chromium")


def _mudou():
    """True se alguma pagina vigiada mudou no push (ou na duvida)."""
    try:
        a = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"],
                           cwd=RAIZ, capture_output=True, text=True, timeout=30)
        b = subprocess.run(["git", "diff", "--name-only", "HEAD"],
                           cwd=RAIZ, capture_output=True, text=True, timeout=30)
        # 🪤 PAGINA NOVA NAO APARECE EM `git diff`: arquivo nao-rastreado nao
        # e "modificado". Sem esta terceira consulta, uma pagina recem-criada
        # — justamente a que tem mais chance de nascer quebrada — passaria
        # direto pelo guarda. Peguei isso com a obrigado.html, em 31/08.
        c = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"],
                           cwd=RAIZ, capture_output=True, text=True, timeout=30)
        muda = (a.stdout or "") + (b.stdout or "") + (c.stdout or "")
        return [p for p in VIGIADAS if p in muda]
    except Exception:
        return list(VIGIADAS)


def _serve(dir_):
    class Quieto(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=dir_, **kw)

        def log_message(self, *a):
            pass
    srv = socketserver.TCPServer(("127.0.0.1", PORTA), Quieto)
    srv.allow_reuse_address = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _barra(pagina, motivo, detalhe=""):
    print(f"\n🚦 PUSH BLOQUEADO — {pagina} nao carrega limpo.")
    print(f"   {motivo}")
    if detalhe:
        print(f"   {detalhe}")
    print("   Em 31/08 um recorte com sintaxe VALIDA matou o login por 12 min.")
    print("   Carregar num browser de verdade e a unica prova que vale.")
    print("   Emergencia: AIARQ_DEPLOY_FORCE=1 git push origin main\n")
    sys.exit(1)


def main():
    if os.environ.get("AIARQ_DEPLOY_FORCE") == "1":
        return
    alvos = _mudou()
    if not alvos:
        return
    chrome = _chrome()
    if not chrome:
        _barra("(setup)", "Chrome/Chromium nao encontrado.",
               "Instale o Chrome ou aponte AIARQ_CHROME=<caminho>.")

    tmp = tempfile.mkdtemp(prefix="aiarq-pag-")
    try:
        # copia o site inteiro (as paginas puxam aiarq-utils.js, css, etc.)
        for nome in os.listdir(RAIZ):
            o = os.path.join(RAIZ, nome)
            if os.path.isfile(o) and nome.rsplit(".", 1)[-1].lower() in (
                    "html", "js", "css", "png", "jpg", "jpeg", "svg", "ico", "webp"):
                shutil.copy(o, tmp)

        srv = _serve(tmp)
        perfil = os.path.join(tmp, "perfil")
        try:
            for pagina in alvos:
                orig = os.path.join(RAIZ, pagina)
                html = open(orig, encoding="utf-8").read()
                # coletor logo apos <head> (antes de qualquer script da pagina)
                if re.search(r"<head[^>]*>", html):
                    html = re.sub(r"(<head[^>]*>)", r"\1" + _COLETOR, html, count=1)
                else:
                    html = _COLETOR + html
                # troca o supabase-js do CDN pelo duble (ver comentario em _SUPA_STUB)
                html, _n = _RE_SUPA_CDN.subn(_SUPA_STUB, html, count=1)
                if not _n:
                    # Pagina publica (obrigado.html) nao carrega supabase-js e
                    # nem precisa. So barra se a pagina TEM area logada — que e
                    # onde o duble e obrigatorio pra sonda chegar a rodar.
                    if VIGIADAS[pagina][1]:
                        _barra(pagina, "nao achei a tag do supabase-js pra dublar.",
                               "sem duble a pagina logada redireciona pro login e "
                               "o guarda vira teatro — falha FECHA a porta.")
                    html = html.replace("<head>", "<head>" + _SUPA_STUB, 1)
                # o portao de admin so pode ser neutralizado DEPOIS que
                # aiarq-utils.js definiu `aiarqEmailMatches` (scripts sao
                # sincronos no <head>, sem defer) — senao o override e
                # sobrescrito e a pagina redireciona pro dashboard.
                html = html.replace(
                    '<script src="aiarq-utils.js"></script>',
                    '<script src="aiarq-utils.js"></script>' + _ABRE_PORTAO, 1)
                query, funcs = VIGIADAS[pagina]
                sonda = ("<script>document.title = JSON.stringify({erros: window.__erros, "
                         "faltando: " + json.dumps(funcs) +
                         ".filter(function(f){return typeof window[f] !== 'function';})});</script>")
                # 🪤 O PRIMEIRO `</body>` DO ARQUIVO PODE ESTAR DENTRO DE UMA
                # STRING JS. Em admin.html existe um `document.write('…</body>')`
                # na linha 4239: injetar a sonda ali metia um <script> no meio de
                # uma string e QUEBRAVA a sintaxe da pagina — o guarda acusava
                # "Uncaught SyntaxError" num arquivo perfeitamente bom e teria
                # bloqueado todo push que tocasse o admin. Falso positivo em
                # guarda e pior que guarda nenhum: ensina a usar o
                # AIARQ_DEPLOY_FORCE. Usa o ULTIMO `</body>`, que e o de verdade.
                html = injeta_sonda(html, sonda)
                alvo = os.path.join(tmp, "_t_" + pagina)
                open(alvo, "w", encoding="utf-8").write(html)

                out = subprocess.run(
                    [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                     f"--user-data-dir={perfil}", "--virtual-time-budget=9000",
                     "--dump-dom", f"http://127.0.0.1:{PORTA}/_t_{pagina}{query}"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=120)
                m = re.search(r"<title>(.*?)</title>", out.stdout or "", re.DOTALL)
                if not m:
                    _barra(pagina, "Chrome nao devolveu resultado (a sonda nem rodou).")
                try:
                    r = json.loads(m.group(1))
                except Exception:
                    _barra(pagina, "sonda ilegivel", (m.group(1) or "")[:200])

                erros = [e for e in (r.get("erros") or [])
                         # ruido conhecido: extensao/CSP local, nao e a pagina
                         if "cookieManager" not in e]
                if erros:
                    _barra(pagina, "erro de JavaScript ao carregar.",
                           " | ".join(erros)[:300])
                if r.get("faltando"):
                    _barra(pagina,
                           "funcao que a pagina promete NAO existe depois do load: "
                           + ", ".join(r["faltando"]),
                           "sintaxe valida nao prova nada — foi assim que o "
                           "window.sbClient sumiu em 31/08.")
                print(f"✓ {pagina}: carrega limpo, {len(funcs)} funcoes vivas")
        finally:
            srv.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
