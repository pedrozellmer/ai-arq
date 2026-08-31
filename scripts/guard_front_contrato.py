#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trava de deploy nº2: recusa o push se o JS compartilhado quebrar o contrato.

🩸 POR QUE EXISTE (31/08/2026): eu quebrei o LOGIN em produção por 12 minutos.
Consertando a captura de origem, recortei um trecho de `aiarq-utils.js` por
índice de string e deixei o `};` final pra trás. A função ficou ABERTA e
engoliu o resto do arquivo — inclusive `window.sbClient = _sbClient`. Sintaxe
100% VÁLIDA, zero erro no console, e o login simplesmente não existia mais:
"Cannot read properties of undefined (reading 'auth')". Nenhum teste da bancada
pegou (todos leem o FONTE), o pyflakes não vê JS, e o smoke E2E só roda DEPOIS
do deploy — ou seja, depois do site já estar fora.

Pedro, 31/08: *"Não podemos ter esses erros, site não pode ficar fora nunca"*.

O QUE ESTE GUARDA FAZ: carrega o JS num Chrome headless de verdade, em duas
páginas — uma COM o supabase-js (login/dashboard) e uma SEM (o blog) — e cobra
o contrato mínimo de cada uma. Se faltar, o push é RECUSADO antes de subir.

Contratos cobrados:
  página COM sdk  → window.sbClient existe e tem .auth   (login vivo)
  página SEM sdk  → window.trackEvent, window.aiArqSource (telemetria viva)
  as duas         → zero erro de execução no carregamento

🔒 Falha FECHA a porta, igual à trava de jobs: se o Chrome não abrir, se o
servidor local não subir ou se der timeout, o push é bloqueado. "Não consegui
verificar" nunca pode virar "pode subir" — foi exatamente assim que o login
morreu (eu vi `sbClient: undefined` num teste e segui mesmo assim).

🪤 Só roda quando um dos arquivos vigiados MUDOU no push — commit de blog ou
de backend não paga o custo (~6 s).

Emergência (mesmo escape da outra trava):
    AIARQ_DEPLOY_FORCE=1 git push origin main
"""
import http.server
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
# arquivos cujo estrago é global: todo HTML do site depende deles
VIGIADOS = ("aiarq-utils.js",)
PORTA = int(os.environ.get("AIARQ_GUARD_PORTA", "8813"))
CHROMES = (
    os.environ.get("AIARQ_CHROME", ""),
    r"C:/Program Files/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
)

_PAG_COM_SDK = """<html><head><meta charset="utf-8">
<script>window.__e=[];window.onerror=function(m){window.__e.push(String(m));return true;};</script>
<script>window.supabase={createClient:function(){return {auth:{getSession:function(){
  return Promise.resolve({data:{session:null}});}}};}};</script>
<script src="%s" charset="utf-8"></script></head><body><script>
document.title = JSON.stringify({
  sbClient: typeof window.sbClient,
  temAuth: !!(window.sbClient && window.sbClient.auth),
  track: typeof window.trackEvent,
  srcFn: typeof window.aiArqSource,
  erros: window.__e.join(' ; ')
});
</script></body></html>"""

_PAG_SEM_SDK = """<html><head><meta charset="utf-8">
<script>window.__e=[];window.onerror=function(m){window.__e.push(String(m));return true;};</script>
<script src="%s" charset="utf-8"></script></head><body><script>
document.title = JSON.stringify({
  track: typeof window.trackEvent,
  srcFn: typeof window.aiArqSource,
  guardouOrigem: !!localStorage.getItem('aiarq_src'),
  erros: window.__e.join(' ; ')
});
</script></body></html>"""


def _chrome():
    for c in CHROMES:
        if c and os.path.isfile(c):
            return c
    achado = shutil.which("google-chrome") or shutil.which("chromium")
    return achado


def _mudou_arquivo_vigiado():
    """True se algum arquivo vigiado difere do que já está no remoto."""
    try:
        alvo = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=RAIZ, capture_output=True, text=True, timeout=30)
        mudados = (alvo.stdout or "")
        # inclui também o que está staged/local pra não passar batido
        alvo2 = subprocess.run(["git", "diff", "--name-only", "HEAD"],
                               cwd=RAIZ, capture_output=True, text=True, timeout=30)
        mudados += (alvo2.stdout or "")
        return any(v in mudados for v in VIGIADOS)
    except Exception:
        return True   # na dúvida, verifica (falha fecha a porta)


def _serve(dir_):
    class Quieto(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=dir_, **kw)

        def log_message(self, *a):
            pass
    srv = socketserver.TCPServer(("127.0.0.1", PORTA), Quieto)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _roda(chrome, perfil, url):
    out = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
         f"--user-data-dir={perfil}", "--virtual-time-budget=8000",
         "--dump-dom", url],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=90)
    m = re.search(r"<title>(.*?)</title>", out.stdout or "", re.DOTALL)
    if not m:
        return None
    import json
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def _barra(motivo, detalhe=""):
    print("\n🚦 PUSH BLOQUEADO — o JS compartilhado quebrou o contrato do front.")
    print(f"   {motivo}")
    if detalhe:
        print(f"   {detalhe}")
    print("   Em 31/08 um recorte deixou uma chave pra trás, o `window.sbClient`")
    print("   parou de ser criado e NINGUÉM conseguia entrar no site por 12 min.")
    print("   Sintaxe válida não prova nada: o contrato é carregar e funcionar.")
    print("   Emergência: AIARQ_DEPLOY_FORCE=1 git push origin main\n")
    sys.exit(1)


def main():
    if os.environ.get("AIARQ_DEPLOY_FORCE") == "1":
        return
    if not _mudou_arquivo_vigiado():
        return
    chrome = _chrome()
    if not chrome:
        _barra("Chrome/Chromium não encontrado pra verificar o contrato.",
               "Instale o Chrome ou aponte AIARQ_CHROME=<caminho>.")
    tmp = tempfile.mkdtemp(prefix="aiarq-guard-")
    try:
        for v in VIGIADOS:
            shutil.copy(os.path.join(RAIZ, v), os.path.join(tmp, v))
        open(os.path.join(tmp, "com_sdk.html"), "w", encoding="utf-8").write(
            _PAG_COM_SDK % VIGIADOS[0])
        open(os.path.join(tmp, "sem_sdk.html"), "w", encoding="utf-8").write(
            _PAG_SEM_SDK % VIGIADOS[0])
        srv = _serve(tmp)
        perfil = os.path.join(tmp, "perfil")
        try:
            com = _roda(chrome, perfil, f"http://127.0.0.1:{PORTA}/com_sdk.html")
            sem = _roda(chrome, perfil, f"http://127.0.0.1:{PORTA}/sem_sdk.html")
        finally:
            srv.shutdown()
        if com is None or sem is None:
            _barra("Não consegui medir o contrato (Chrome não devolveu resultado).")
        # ── página COM supabase-js: o login precisa existir ──
        if com.get("sbClient") != "object" or not com.get("temAuth"):
            _barra("window.sbClient NÃO foi criado numa página com supabase-js "
                   "— é o login do site.", f"medido: {com}")
        # ── página SEM supabase-js (o blog): telemetria e origem ──
        if sem.get("track") != "function" or sem.get("srcFn") != "function":
            _barra("trackEvent/aiArqSource não existem em página estática "
                   "(o blog) — telemetria e atribuição morrem lá.",
                   f"medido: {sem}")
        for nome, r in (("com sdk", com), ("sem sdk", sem)):
            if r.get("erros") and r["erros"] != "(nenhum)":
                _barra(f"erro de execução ao carregar o JS ({nome}).",
                       f"erro: {r['erros'][:160]}")
        print("✓ contrato do front ok (login vivo com sdk; telemetria viva sem sdk)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
