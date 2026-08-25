# -*- coding: utf-8 -*-
"""Todo botão do site chama a rota com o MÉTODO que ela aceita.

🚨 25/08/2026. O Pedro clicou em "Quantos itens têm marca/código escrito" e
levou **"Method Not Allowed"**. A rota é `@app.post` e o `authFetch` manda GET
por padrão — eu simplesmente esqueci o `method`.

🪤 O que torna isso repetível: a rota e o botão nasceram em commits DIFERENTES
(a rota primeiro, o botão horas depois, porque eu tinha feito rota sem tela).
Nada no caminho conferia que os dois combinavam, e teste nenhum pegava — só um
humano clicando. Foi a segunda vez em dois dias que o Pedro foi o detector.

Este guarda cruza os dois lados em TODO o site (não só no admin: um 405 na cara
do cliente é pior que na minha). Para cada `authFetch` de cada .html/.js da
raiz, confere que o método usado é um que o backend declara para aquela rota.

🪤 Duas armadilhas que me pegaram escrevendo ESTE arquivo:
 1. o site chama de dois jeitos (crase com `${API_BASE}` e concatenação com
    `+`); a 1ª versão só lia o primeiro e ficava cega em 3 chamadas do
    coerencia.js sem reclamar;
 2. casar o caminho com a PRIMEIRA rota que bate dá falso positivo —
    `/quotes/compare` casava com `/quotes/{quote_id}` (DELETE) antes da rota
    certa. Tem que escolher a rota MAIS ESPECÍFICA, como o servidor escolhe.
"""
import io
import os
import re

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)

# quem chama o backend pelo authFetch
_ARQUIVOS = ("admin.html", "admin-usuario.html", "dashboard.html", "projeto.html",
             "revisao.html", "memorial.html", "feedback.html", "cronograma.html",
             "aiarq-utils.js", "coerencia.js", "menu-lateral.js")

_CURINGA = "\x01"          # marca de "aqui entra um valor" nos dois lados


# ══════════════════════════════════════════════════════════════════════════
#  Lado do backend
# ══════════════════════════════════════════════════════════════════════════
def _rotas_do_backend(src=None):
    """{caminho: {métodos aceitos}} a partir dos decoradores do FastAPI."""
    if src is None:
        src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    rotas = {}
    for m in re.finditer(r'@app\.(get|post|put|patch|delete)\(\s*"([^"]+)"', src):
        rotas.setdefault(m.group(2), set()).add(m.group(1).upper())
    return rotas


# ══════════════════════════════════════════════════════════════════════════
#  Lado do site
# ══════════════════════════════════════════════════════════════════════════
def _argumentos(src, i):
    """Devolve o texto entre os parênteses da chamada que começa em `i`
    (índice logo APÓS o `authFetch(`), respeitando aspas e aninhamento."""
    prof, j, aspas = 1, i, None
    while j < len(src) and prof:
        c = src[j]
        if aspas:
            if c == "\\":
                j += 1
            elif c == aspas:
                aspas = None
        elif c in "'\"`":
            aspas = c
        elif c in "([{":
            prof += 1
        elif c in ")]}":
            prof -= 1
        j += 1
    return src[i:j - 1]


def _caminho(arg):
    """Transforma o 1º argumento do authFetch no caminho da rota, com
    `_CURINGA` no lugar de cada valor interpolado.

    None quando não dá pra saber (a URL foi montada numa variável antes)."""
    arg = arg.strip()
    if arg.startswith("`"):                                   # crase
        fim = arg.index("`", 1) if "`" in arg[1:] else len(arg)
        corpo = re.sub(r"\$\{[^}]*\}", _CURINGA, arg[1:fim])
    else:                                                     # concatenação
        partes, resto = [], arg
        while resto:
            lit = re.match(r"\s*(['\"])((?:\\.|(?!\1).)*)\1", resto)
            if lit:
                partes.append(lit.group(2))
                resto = resto[lit.end():]
            else:                          # variável: vira curinga
                partes.append(_CURINGA)
                m = re.search(r"\+", resto)
                resto = resto[m.end():] if m else ""
                continue
            m = re.search(r"\+", resto)
            resto = resto[m.end():] if m else ""
        corpo = "".join(partes)
    if "/api/" not in corpo:
        return None
    return corpo[corpo.index("/api/"):].split("?")[0]


def _chamadas(src, arquivo="?"):
    """[(arquivo, caminho, método)] de cada authFetch de um fonte."""
    saida = []
    for m in re.finditer(r"authFetch\(", src):
        args = _argumentos(src, m.end())
        # o 1º argumento vai até a vírgula de topo; o resto traz as opções
        prof, corte, aspas = 0, len(args), None
        for k, c in enumerate(args):
            if aspas:
                if c == "\\":
                    continue
                if c == aspas:
                    aspas = None
            elif c in "'\"`":
                aspas = c
            elif c in "([{":
                prof += 1
            elif c in ")]}":
                prof -= 1
            elif c == "," and prof == 0:
                corte = k
                break
        caminho = _caminho(args[:corte])
        if not caminho or not caminho.startswith("/api/"):
            continue
        met = re.search(r"method\s*:\s*['\"](\w+)['\"]", args[corte:])
        saida.append((arquivo, caminho, (met.group(1) if met else "GET").upper()))
    return saida


def _chamadas_do_site():
    saida = []
    for nome in _ARQUIVOS:
        caminho = os.path.join(_RAIZ, nome)
        if os.path.exists(caminho):
            saida += _chamadas(io.open(caminho, encoding="utf-8").read(), nome)
    return saida


# ══════════════════════════════════════════════════════════════════════════
#  Casamento — a rota MAIS ESPECÍFICA, como o servidor faz
# ══════════════════════════════════════════════════════════════════════════
def _casa(caminho, rotas):
    if caminho in rotas:
        return rotas[caminho]
    chamados = caminho.split("/")
    melhor, nota = None, None
    for padrao, metodos in rotas.items():
        pedacos = padrao.split("/")
        if len(pedacos) != len(chamados):
            continue
        fixos, frouxos, ok = 0, 0, True
        for esperado, veio in zip(pedacos, chamados):
            if esperado.startswith("{") and esperado.endswith("}"):
                continue                      # curinga da rota: aceita tudo
            if veio == _CURINGA:
                frouxos += 1                  # o site pôs valor onde a rota quer texto fixo
                continue
            if esperado != veio:
                ok = False
                break
            fixos += 1
        # menos "frouxo" primeiro, depois mais pedaços literais: é a rota que
        # o servidor escolheria. 🪤 sem o "frouxo", /quotes/{id} perdia pra
        # /quotes/upload e o guarda acusava bug que não existe.
        candidata = (-frouxos, fixos)
        if ok and (nota is None or candidata > nota):
            melhor, nota = metodos, candidata
    return melhor


# ══════════════════════════════════════════════════════════════════════════
#  🧪 Controles: os dois lados precisam ser lidos de verdade
# ══════════════════════════════════════════════════════════════════════════
def test_controle_acha_as_rotas_do_backend():
    r = _rotas_do_backend()
    assert len(r) > 50, "só achei %d rotas — o parser do backend quebrou" % len(r)
    assert "/api/admin/spec-backfill" in r


def test_controle_acha_as_chamadas_do_site():
    c = _chamadas_do_site()
    assert len(c) > 80, "só achei %d chamadas — o parser do site quebrou" % len(c)
    assert len({a for a, _, _ in c}) >= 8, "só li %s" % {a for a, _, _ in c}


def _fora_do_alcance():
    """Chamadas que o parser não resolve: a URL foi montada numa variável antes
    (`authFetch(url)`). Não são bug — são o limite honesto do guarda."""
    soltas = []
    for nome in _ARQUIVOS:
        caminho = os.path.join(_RAIZ, nome)
        if not os.path.exists(caminho):
            continue
        src = io.open(caminho, encoding="utf-8").read()
        for m in re.finditer(r"authFetch\(", src):
            arg = _argumentos(src, m.end()).split(",")[0]
            if _caminho(arg) is None:
                soltas.append("%s: %s" % (nome, arg.strip()[:40]))
    return soltas


def test_controle_o_guarda_ALCANCA_quase_toda_chamada():
    """🪤 Parser que resolve 3 de 98 chamadas passa VERDE e não guarda nada.

    Foi o que aconteceu na 1ª versão deste arquivo: só entendia a chamada com
    crase e ficava cega nas 3 do coerencia.js, que concatenam com `+` — sem
    reclamar de nada. Aqui eu conto quanto do site o guarda REALMENTE cobre."""
    total = 0
    for nome in _ARQUIVOS:
        caminho = os.path.join(_RAIZ, nome)
        if os.path.exists(caminho):
            total += len(re.findall(r"authFetch\(",
                                    io.open(caminho, encoding="utf-8").read()))
    soltas = _fora_do_alcance()
    assert total > 90, "só achei %d chamadas no site" % total
    assert len(soltas) <= 4, (
        "%d de %d chamadas ficaram fora do alcance do guarda: %s"
        % (len(soltas), total, soltas))


def test_controle_entende_os_DOIS_jeitos_de_chamar():
    crase = "await authFetch(`${API_BASE}/api/items/${jobId}/finalize`, {method: 'POST'})"
    mais = "await window.authFetch(window.API_BASE + '/api/items/' + jobId + '/finalize', { method: 'POST' })"
    for src in (crase, mais):
        assert _chamadas(src) == [("?", "/api/items/%s/finalize" % _CURINGA, "POST")], src


def test_controle_escolhe_a_rota_MAIS_ESPECIFICA():
    """🪤 O falso positivo que me pegou: `/quotes/compare` casava primeiro com
    `/quotes/{quote_id}` (DELETE) e o guarda acusava um bug que não existe."""
    rotas = {"/api/projects/{job_id}/quotes/{quote_id}": {"DELETE"},
             "/api/projects/{job_id}/quotes/compare": {"GET"}}
    assert _casa("/api/projects/%s/quotes/compare" % _CURINGA, rotas) == {"GET"}
    assert _casa("/api/projects/%s/quotes/%s" % (_CURINGA, _CURINGA), rotas) == {"DELETE"}


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO: o guarda tem que REPROVAR o código quebrado
# ══════════════════════════════════════════════════════════════════════════
_BACKEND_FALSO = '''
@app.post("/api/admin/spec-backfill")
async def spec_backfill(dry: int = 1):
    pass
'''

_ADMIN_QUEBRADO = (
    "const res = await authFetch(`${API_BASE}/api/admin/spec-backfill?dry=1`,"
    " {timeoutMs: 180000});")

_ADMIN_CERTO = (
    "const res = await authFetch(`${API_BASE}/api/admin/spec-backfill?dry=1`,"
    " {method: 'POST', timeoutMs: 180000});")


def _erros(admin_src):
    rotas = _rotas_do_backend(_BACKEND_FALSO)
    fora = []
    for _, caminho, metodo in _chamadas(admin_src):
        aceitos = _casa(caminho, rotas)
        if aceitos and metodo not in aceitos:
            fora.append((caminho, metodo))
    return fora


def test_controle_positivo_o_guarda_PEGA_o_bug_real():
    """Este é o código exato que o Pedro clicou e levou Method Not Allowed."""
    assert _erros(_ADMIN_QUEBRADO), (
        "o guarda NÃO reprova o bug de 25/08 — então ele não guarda nada")


def test_controle_negativo_o_guarda_APROVA_o_conserto():
    """E não pode reclamar do código consertado, senão vira ruído."""
    assert not _erros(_ADMIN_CERTO)


# ══════════════════════════════════════════════════════════════════════════
#  O guarda
# ══════════════════════════════════════════════════════════════════════════
def test_todo_botao_usa_o_metodo_que_a_rota_aceita():
    """🚨 O caso real: botão em GET numa rota POST = 'Method Not Allowed'."""
    rotas = _rotas_do_backend()
    erros = []
    for arquivo, caminho, metodo in _chamadas_do_site():
        aceitos = _casa(caminho, rotas)
        if aceitos is None:
            continue          # rota de outro serviço — não é este guarda
        if metodo not in aceitos:
            erros.append("%s: %s chamado em %s, mas a rota aceita %s"
                         % (arquivo, caminho.replace(_CURINGA, "{}"),
                            metodo, "/".join(sorted(aceitos))))
    assert not erros, (
        "botão e rota não combinam — o clique devolve Method Not Allowed:\n  "
        + "\n  ".join(erros))


def test_toda_rota_chamada_pelo_site_EXISTE_no_backend():
    """🪤 O irmão do bug: chamar rota que não existe devolve 404 e, pra quem
    está olhando a tela, parece 'não fez nada'."""
    rotas = _rotas_do_backend()
    sumidas = []
    for arquivo, caminho, _ in _chamadas_do_site():
        if _casa(caminho, rotas) is None:
            sumidas.append("%s: %s" % (arquivo, caminho.replace(_CURINGA, "{}")))
    assert not sumidas, "o site chama rota que não existe no backend: %s" % sumidas


@pytest.mark.parametrize("rota,metodo", [
    ("/api/admin/spec-backfill", "POST"),
    ("/api/admin/selo-historico", "GET"),
])
def test_as_duas_contagens_novas_batem(rota, metodo):
    """As duas do dia, explicitamente — foram elas que quebraram."""
    assert metodo in (_rotas_do_backend().get(rota) or set())
    chamadas = {c: m for _, c, m in _chamadas_do_site()}
    assert chamadas.get(rota) == metodo, (
        "o botão de %s chama em %s" % (rota, chamadas.get(rota)))
