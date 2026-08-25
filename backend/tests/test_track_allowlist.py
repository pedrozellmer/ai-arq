"""Todo evento que o front dispara tem que estar na allowlist do /api/track.

🎯 23/08/2026: o board do site achou 9 eventos (open_memorial, view_revisao,
indicou_whatsapp…) e todos os cliques data-track sendo descartados em silêncio
pelo backend há semanas — e a gente concluindo "memorial 0 aberturas" em cima
disso. Este teste lê o FONTE (não importa o main.py, que liga em serviços) e
falha se aparecer um nome novo no front sem entrada na lista.
"""
import io
import os
import re
import glob

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)


def _allowlist():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    m = re.search(r"_TRACK_ALLOWED\s*=\s*\{(.*?)\n\}", src, re.S)
    assert m, "_TRACK_ALLOWED não encontrada em main.py"
    return set(re.findall(r'"([a-z_]+)"', m.group(1)))


def _eventos_do_front():
    nomes = set()
    arquivos = glob.glob(os.path.join(_RAIZ, "*.html")) + glob.glob(os.path.join(_RAIZ, "*.js"))
    for f in arquivos:
        txt = io.open(f, encoding="utf-8", errors="replace").read()
        # 🪤 25/08: a versão anterior era `trackEvent\(` e ficava CEGA pra
        # `trackEvent?.('nome')` — optional chaining, que é como se escreve
        # chamada opcional em JS moderno. Escrevi um evento novo nesse estilo,
        # rodei este teste esperando que ele reprovasse, e ele passou VERDE.
        # O guarda contra "evento descartado em silêncio" tinha ele próprio um
        # ponto cego silencioso.
        for n in re.findall(r"trackEvent\s*\??\.?\(\s*['\"]([a-z_]+)['\"]", txt):
            nomes.add(n)
        for slug in re.findall(r'data-track="([^"]+)"', txt):
            nomes.add("clique:" + slug)
    return nomes


def test_todo_evento_do_front_esta_na_allowlist():
    allow = _allowlist()
    clique = re.compile(r"^clique:[a-z0-9][a-z0-9-]{0,39}$")
    faltando = sorted(
        n for n in _eventos_do_front()
        if n not in allow and not clique.match(n)
    )
    assert not faltando, (
        "Eventos disparados pelo front que o /api/track DESCARTA em silêncio: "
        f"{faltando} — adicione em _TRACK_ALLOWED (main.py) no mesmo commit."
    )


def test_allowlist_nao_vazia():
    assert len(_allowlist()) >= 13
