# -*- coding: utf-8 -*-
"""A lista de chaves de `meta` matava instrumento novo — calada.

🚨 27/08/2026, achado na auditoria do próprio dia. Uma hora depois de subir o
`signup_saiu_da_tela` — o evento que grava EM QUE CAMPO a pessoa parou no
cadastro — fui conferir se ele estava gravando. Estava. E o `campo` não:

    {"cid": "cmrmo1hoqp3q7xegu", "src": "direto"}

O `/api/track` tem uma lista fechada de chaves de `meta` (`cid`, `type`, `src`)
e **descarta o resto sem avisar**. O instrumento nasceu, chegou ao banco, e
perdeu a única informação pra qual foi feito.

🪤 **Existia guarda pro NOME do evento** (`test_track_allowlist`) — e foi ele que
me barrou o commit hoje de manhã, salvando o instrumento de nascer morto.
**Não existia guarda pras CHAVES de meta.** Por isso este passou.

É a mesma família do achado de 23/08, quando 9 eventos que o front disparava há
semanas eram descartados com `200 {"status":"ignored"}`.

🔒 A lista fechada existe por SEGURANÇA e continua: nada de HTML/JS arbitrário
chega ao painel admin. O que este teste cobra é que ela seja mantida em dia com
o que o front realmente manda.
"""
import asyncio
import io
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)

_MAIN = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

import main  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
#  🚨 06/09/2026 — POR QUE ESTES GUARDAS PASSARAM A CHAMAR A ROTA
# ══════════════════════════════════════════════════════════════════════════
# Cinco guardas deste arquivo liam o FONTE (pela árvore `ast` ou por janela de
# caracteres) e a mutação passou por cima dos cinco:
#
#   • `if _campo:` -> `if False and _campo:` — a atribuição continua no fonte,
#     o `ast` continua vendo a chave, e o dado para de ser gravado;
#   • uma linha de saneamento a MAIS depois da boa (`_campo = str(...)[:200]`),
#     com o regex e o `[:40]` ainda dentro da janela de 260 caracteres;
#   • `_meta.update({"valor": ...})` no fim do bloco — o detector de chaves só
#     olhava `_meta[...] = ...`, então a chave proibida entrava invisível;
#   • `_s = ""` / `_rot = ""` depois do saneamento — a chave continua na lista,
#     o valor sai vazio e some.
#
# 🔑 É a mesma lição das 29 HORAS de 29/08, escrita no comentário da própria
# rota: guarda que lê o fonte não pega argumento faltando, nem ramo morto, nem
# reatribuição. Agora a rota é CHAMADA e o julgamento é sobre a linha que ela
# manda pro banco.
class _Req:
    """Request de mentira. A rota só toca nele quando o corpo AFIRMA identidade."""
    headers = {"Authorization": "Bearer jwt-de-teste"}
    client = None


# 🚨 06/09/2026, 2ª revisão — OS GUARDAS SÓ ANDAVAM POR METADE DA ROTA.
# `track_event` bifurca perto do fim:
#
#     if (payload.user_id or payload.user_email):
#         _u_track = _get_user_from_request(request, tolerante=True)
#
# e o corpo anônimo nunca entra nesse `if`. Ou seja: poda, troca ou perda de
# `meta` no ramo COM identidade — que é por onde passa o evento de quem já está
# logado, inclusive o `signup_saiu_da_tela` de quem voltou pela sessão — era
# invisível pra todo mundo aqui. Agora cada guarda de `meta` roda nos DOIS.
IDENTIDADES = ["anonimo", "identificado"]
_DO_TOKEN = {"id": "uid-do-token", "email": "arquiteta@example.com"}


def gravar(meta, event="signup_saiu_da_tela", monkeypatch=None, quem="anonimo"):
    """Chama a rota /api/track de VERDADE e devolve a linha que ela gravaria.

    `quem="identificado"` faz o corpo AFIRMAR identidade — é o único jeito de
    a rota entrar no ramo do `_get_user_from_request`.
    """
    linhas = []
    alvo = monkeypatch
    antes = main._supabase_insert
    alvo.setattr(main, "_supabase_insert",
                 lambda tabela, row: linhas.append((tabela, row)))
    corpo = {"event": event, "meta": meta}
    if quem == "identificado":
        # 🪤 o que o CLIENTE afirma ser — de propósito diferente do token
        corpo["user_id"] = "uid-que-o-cliente-inventou"
        corpo["user_email"] = "outra.pessoa@example.com"
        alvo.setattr(main, "_get_user_from_request",
                     lambda request, tolerante=False: dict(_DO_TOKEN))
    try:
        resp = asyncio.run(main.track_event(main.TrackPayload(**corpo), _Req()))
    finally:
        alvo.setattr(main, "_supabase_insert", antes)
    assert resp == {"status": "ok"}, resp
    assert len(linhas) == 1 and linhas[0][0] == "usage_events", linhas
    row = linhas[0][1]
    if quem == "identificado":
        # o conserto de 09/08 no mesmo caminho: identidade vem do TOKEN
        assert row["user_id"] == _DO_TOKEN["id"], (
            "o /api/track gravou a identidade que o CORPO afirmou (%r) em vez "
            "da que o token provou — dá pra encher a atividade de qualquer "
            "cliente com evento inventado" % row["user_id"])
        assert row["user_email"] == _DO_TOKEN["email"], row["user_email"]
    else:
        assert row["user_id"] == "" and row["user_email"] == "", (
            "evento anônimo saiu com identidade: %r" % row)
    return row


def meta_gravado(meta, monkeypatch, event="signup_saiu_da_tela", quem="anonimo"):
    return gravar(meta, event=event, monkeypatch=monkeypatch, quem=quem)["meta"]


def _rota_track():
    """A função `track_event` INTEIRA, achada pela estrutura do código.

    🪤 As duas versões anteriores deste helper recortavam `_MAIN[i:i+5000]` — um
    número mágico. Hoje (28/08) a rota passou de 5.000 caracteres ao ganhar três
    chaves novas, e DOIS testes deste arquivo passaram a reprovar acusando
    justamente as chaves que eu tinha acabado de aceitar. É o mesmo erro da
    janela de 2.500 no teste do `keepalive`, em 27/08: janela curta reprova o
    código certo, janela longa aprova o errado. A estrutura não tem esse
    problema — o `ast` sabe onde a função acaba.
    """
    import ast
    for no in ast.walk(ast.parse(_MAIN)):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and no.name == "track_event":
            return no
    raise AssertionError("não achei a função da rota /api/track")



def _trecho_da_rota():
    """O TEXTO da rota /api/track, do 1º ao último caractere da função.

    🪤 Para os testes que precisam olhar o texto (saneamento, regex usado) sem
    voltar a chutar um `+4000` que envelhece junto com a função.
    """
    rota = _rota_track()
    linhas = _MAIN.split(chr(10))
    fim = max(getattr(n, "lineno", rota.lineno) for n in __import__("ast").walk(rota))
    return chr(10).join(linhas[rota.lineno - 1:fim])

def _chaves_aceitas_no_backend():
    """As chaves que o /api/track realmente grava.

    🪤 TRÊS formas diferentes no código, e cada versão deste detector enxergava
    só as que existiam quando ela foi escrita — acusando como "perdidas" chaves
    recém-aceitas:
      (a) `_meta["cid"] = ...`                        → nome literal
      (b) `for _k in ("a", "b"): _meta[_k] = ...`     → tupla simples
      (c) `for _k, _limpa, _teto in (("motivo", ...), ...)` → tupla de tuplas
    Detector que vê só parte acusa errado, e guarda que acusa errado é ignorado
    — pior que guarda nenhum. Lendo pelo `ast` as três caem no mesmo caso.
    """
    import ast
    rota = _rota_track()
    chaves = set()
    for sub in ast.walk(rota):
        # (a) atribuição direta com nome literal
        if isinstance(sub, ast.Assign):
            for alvo in sub.targets:
                if isinstance(alvo, ast.Subscript) \
                        and getattr(alvo.value, "id", None) == "_meta" \
                        and isinstance(alvo.slice, ast.Constant) \
                        and isinstance(alvo.slice.value, str):
                    chaves.add(alvo.slice.value)
        # (b) e (c): laço cujo corpo escreve em `_meta[...]`
        if isinstance(sub, ast.For):
            escreve = any(
                isinstance(x, ast.Subscript)
                and getattr(x.value, "id", None) == "_meta"
                for n in ast.walk(sub) if isinstance(n, ast.Assign)
                for x in n.targets)
            if not escreve or not isinstance(sub.iter, (ast.Tuple, ast.List)):
                continue
            for item in sub.iter.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    chaves.add(item.value)                       # (b)
                elif isinstance(item, (ast.Tuple, ast.List)) and item.elts:
                    p = item.elts[0]
                    if isinstance(p, ast.Constant) and isinstance(p.value, str):
                        chaves.add(p.value)                      # (c)
    return chaves


def _so_codigo(txt):
    """Apaga strings e COMENTÁRIOS virando espaço, preservando os offsets.

    🪤 Preservar offset importa: é o que deixa contar a linha depois. E apagar
    comentário importa porque eu já escrevi QUATRO testes num dia só que liam
    o comentário como se fosse código — num deles sabotei o `keepalive` e o
    teste passou VERDE lendo a palavra no comentário logo acima.
    """
    out = list(txt)
    i, n = 0, len(txt)
    while i < n:
        c = txt[i]
        if c in "'\"`":                       # string: aspa simples, dupla ou crase
            q, j = c, i + 1
            while j < n and txt[j] != q:
                if txt[j] == "\\":
                    out[j] = " "
                    j += 1
                if j < n:
                    out[j] = " "
                j += 1
            out[i] = " "
            if j < n:
                out[j] = " "
            i = j + 1
        elif c == "/" and i + 1 < n and txt[i + 1] == "/":      # // até o fim da linha
            while i < n and txt[i] != "\n":
                out[i] = " "
                i += 1
        elif c == "/" and i + 1 < n and txt[i + 1] == "*":      # /* ... */
            j = txt.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if txt[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


# 🪤 `trackEvent?.(` — optional chaining. O guarda IRMÃO (test_track_allowlist)
# já tinha consertado isto em 25/08, com comentário explicando. Este arquivo
# nasceu em 27/08 e NÃO copiou: por isso o `motivo` do `processar_bloqueado`
# passou batido. Regressão dentro de casa, entre dois arquivos vizinhos.
_CHAMADA = re.compile(r"trackEvent\s*\??\.?\(")


def _segundo_argumento(codigo, abre):
    """Anda contando parêntese até o 2º argumento. Devolve (tipo, ini, fim).

    Regex não serve aqui: `{...}` aninhado e vírgula dentro de sub-chamada
    quebram qualquer expressão. Contar é chato e é o que funciona.
    """
    i, prof, arg2, n = abre, 0, None, len(codigo)
    while i < n:
        ch = codigo[i]
        if ch in "([{":
            prof += 1
        elif ch in ")]}":
            prof -= 1
            if prof == 0:
                return ("sem_2o_arg", None, None)
        elif ch == "," and prof == 1:
            arg2 = i + 1
            break
        i += 1
    if arg2 is None:
        return ("sem_2o_arg", None, None)
    j = arg2
    while j < n and codigo[j] in " \t\r\n":
        j += 1
    if j < n and codigo[j] == "{":
        prof, k = 0, j
        while k < n:
            if codigo[k] == "{":
                prof += 1
            elif codigo[k] == "}":
                prof -= 1
                if prof == 0:
                    return ("literal", j, k + 1)
            k += 1
        return ("literal", j, n)
    m = re.match(r"[A-Za-z_$][\w$]*", codigo[j:])
    return ("variavel", j, j + (m.end() if m else 0))


def _chaves_do_literal(corpo):
    """Chaves de `{ a: 1, b }`. Devolve None se houver objeto aninhado.

    🪤 `{ job_id, formato }` é atalho do ES6 e NÃO tem dois-pontos — o detector
    velho exigia `(\\w+)\\s*:` e por isso ficou cego pro `formato` do memorial.
    🪤 Aninhado: RECUSA em vez de adivinhar. Detector que chuta acusa errado, e
    guarda que acusa errado é ignorado — pior que guarda nenhum.
    """
    dentro = corpo[1:-1]
    if "{" in dentro:
        return None
    chaves = []
    for frag in dentro.split(","):
        m = re.match(r"\s*(\w+)\s*(:|$)", frag)
        if m:
            chaves.append(m.group(1))
    return chaves


# 🪤 Call site que o detector NÃO consegue resolver sozinho tem que estar aqui,
# com motivo escrito. Sem esta lista o teste estrutural abaixo não tem como
# distinguir "não sei ler" de "não tem chave" — e "não sei ler" calado é
# exatamente a doença que este arquivo existe pra curar.
_OPACOS_REGISTRADOS = {
    ("aiarq-utils.js", "q"): (
        "replay da fila de consentimento: retransmite chamadas que JÁ foram "
        "contadas na origem, então não introduz chave nova"),
}


def _varrer_o_front():
    """Devolve (chaves, opacos, aninhados) lendo todo call site de trackEvent."""
    import glob as _glob
    # 🪤 28/08: varria só a RAIZ e ficava cego pro blog — 26 posts que agora
    # mandam `campo`. Mesmo ponto cego do `test_track_allowlist`.
    caminhos = (_glob.glob(os.path.join(_RAIZ, "*.html"))
                + _glob.glob(os.path.join(_RAIZ, "*.js"))
                + _glob.glob(os.path.join(_RAIZ, "blog", "*.html"))
                + _glob.glob(os.path.join(_RAIZ, "blog", "posts", "*.html")))
    chaves, opacos, aninhados = {"cid", "src"}, [], []
    for caminho in sorted(set(caminhos)):
        try:
            bruto = io.open(caminho, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        arq = os.path.basename(caminho)
        cod = _so_codigo(bruto)
        for m in _CHAMADA.finditer(cod):
            linha = cod.count("\n", 0, m.start()) + 1
            tipo, a, b = _segundo_argumento(cod, m.end() - 1)
            if tipo == "sem_2o_arg":
                continue
            if tipo == "literal":
                ks = _chaves_do_literal(cod[a:b])
                if ks is None:
                    aninhados.append((arq, linha))
                else:
                    chaves.update(ks)
                continue
            # ── 2º argumento é uma VARIÁVEL (o caso do `rotulo`) ──
            nome = cod[a:b]
            if not nome or "." in bruto[a:b]:
                opacos.append((arq, linha, bruto[a:b] or "?"))
                continue
            decl = None
            for dm in re.finditer(
                    r"\b(?:var|let|const)\s+%s\s*=\s*\{" % re.escape(nome),
                    cod[:m.start()]):
                decl = dm
            if decl is None:
                opacos.append((arq, linha, nome))
                continue
            janela = cod[decl.start():m.start()]
            achou = set(re.findall(r"\b%s\.(\w+)\s*=(?!=)" % re.escape(nome), janela))
            fecha = cod.find("}", decl.end() - 1)
            achou.update(_chaves_do_literal(cod[decl.end() - 1:fecha + 1]) or [])
            if not achou:
                opacos.append((arq, linha, nome))
                continue
            chaves.update(achou)
    return chaves, opacos, aninhados


def _chaves_enviadas_pelo_front():
    return _varrer_o_front()[0]


def test_toda_chave_que_o_front_manda_o_backend_ACEITA():
    """🚨 O guarda que faltava. Chave nova no front sem linha aqui = dado
    descartado calado, exatamente como aconteceu com o `campo`."""
    front = _chaves_enviadas_pelo_front()
    backend = _chaves_aceitas_no_backend()
    # 🪤 `job_id` NÃO é perda: o payload tem coluna própria pra ele
    # (`usage_events.job_id`), e o front manda nos dois lugares. Se eu não
    # excluísse, o guarda acusaria falso positivo pra sempre — e guarda que
    # acusa errado é ignorado, que é pior que guarda nenhum.
    front = front - {"job_id"}
    perdidas = sorted(front - backend)
    assert not perdidas, (
        "o front manda %s e o /api/track descarta CALADO. Ou acrescente a "
        "chave no bloco `_meta` (saneada!), ou pare de mandar." % perdidas)


@pytest.mark.parametrize("quem", IDENTIDADES)
def test_o_campo_do_cadastro_sobrevive(monkeypatch, quem):
    """O caso concreto que motivou este arquivo.

    🚨 06/09/2026 — a versão antiga perguntava ao `ast` se a rota ATRIBUI
    `_meta["campo"]`. Embrulhar em `if False and _campo:` deixa a atribuição no
    fonte e mata a gravação: o guarda ficava verde e o instrumento voltava a
    nascer morto, que é exatamente o defeito que este arquivo documenta.
    Agora a rota é chamada e o guarda olha a linha que vai pro banco.
    """
    meta = meta_gravado({"cid": "cmrmo1hoqp3q7xegu", "src": "direto",
                         "campo": "whatsapp"}, monkeypatch, quem=quem)
    assert meta.get("campo") == "whatsapp", (
        "o `campo` voltou a ser descartado — o `signup_saiu_da_tela` deixa de "
        "responder ONDE a pessoa parou, que é a única coisa que ele faz. "
        "Gravado: %r" % meta)
    assert meta.get("cid") and meta.get("src"), meta


@pytest.mark.parametrize("quem", IDENTIDADES)
def test_o_campo_e_SANEADO_e_nao_entra_cru(monkeypatch, quem):
    """🔒 A lista fechada existe por segurança. Chave nova não pode virar porta
    de HTML/JS pro painel admin.

    🚨 06/09/2026 — a versão antiga lia 260 caracteres depois de `_campo = ` e
    conferia se o regex e o `[:40]` estavam ali. Uma linha a MAIS logo depois
    (`_campo = str(payload.meta.get("campo") or "")[:200]`) desfazia o
    saneamento sem sair da janela: o guarda ficava verde com HTML cru entrando.
    Agora o guarda manda o payload malicioso pela rota e olha o que sobrou.
    """
    sujo = '<img src=x onerror="alert(1)">CAMPO/Whats App;drop' + ("z" * 200)
    meta = meta_gravado({"campo": sujo}, monkeypatch, quem=quem)
    gravado = meta.get("campo", "")
    assert gravado, "o campo sumiu por inteiro — o saneamento virou descarte"
    assert re.fullmatch(r"[a-z0-9_-]*", gravado), (
        "o `campo` entrou sem lista branca de caracteres: %r" % gravado)
    assert len(gravado) <= 40, "o `campo` entrou sem teto de tamanho: %d" % len(gravado)
    for perigoso in ("<", ">", '"', "'", "&", "/", ";", " "):
        assert perigoso not in gravado, (
            "o caractere %r atravessou o saneamento: %r" % (perigoso, gravado))


@pytest.mark.parametrize("quem", IDENTIDADES)
def test_o_backend_NAO_grava_o_valor_digitado(monkeypatch, quem):
    """🔒 A tela de cadastro tem WhatsApp e nome. Se algum dia alguém mandar
    `valor` junto, o backend não pode aceitar.

    🚨 06/09/2026 — a versão antiga perguntava ao `ast` quais chaves a rota
    escreve, e ele só entendia `_meta[...] = ...`. Um
    `_meta.update({"valor": ...})` no fim do bloco gravava o conteúdo digitado
    pelo cliente sem aparecer pro detector. Agora o guarda MANDA o valor e
    confere que ele não chega ao banco.
    """
    proibidas = {"valor": "(11) 90000-0000", "value": "Fulana de Tal",
                 "conteudo": "rua tal, 100", "texto": "meu telefone",
                 "telefone": "11900000000", "whatsapp": "11900000000",
                 "email_digitado": "alguem@example.com"}
    meta = meta_gravado(dict(proibidas, cid="abc123", campo="whatsapp"),
                        monkeypatch, quem=quem)
    vazou = sorted(k for k in proibidas if k in meta)
    assert not vazou, (
        "o /api/track passou a gravar %s — isso é conteúdo digitado pelo "
        "cliente. Linha: %r" % (vazou, meta))
    achados = [v for v in proibidas.values() if v in str(meta)]
    assert not achados, (
        "o valor digitado pelo cliente chegou ao banco por outra chave: %r" % meta)
    assert meta.get("campo") == "whatsapp", (
        "controle: o que É pra passar tem que passar — senão este teste é "
        "verde por a rota não gravar nada. Linha: %r" % meta)


def test_CONTROLE_POSITIVO_o_detector_pega_chave_orfa():
    """🧪 Sem isto, o teste principal passaria verde com um detector quebrado —
    foi assim que eu deixei passar guarda inútil quatro vezes hoje."""
    front_falso = {"cid", "src", "campo", "chave_que_ninguem_aceita"}
    backend = _chaves_aceitas_no_backend()
    assert sorted(front_falso - backend) == ["chave_que_ninguem_aceita"], (
        "o cruzamento não detecta chave órfã")


def test_nenhum_call_site_fica_SEM_CLASSIFICAR():
    """🚨 O guarda estrutural — o que fecha a classe inteira em vez de tapar
    o buraco de hoje.

    Todo `trackEvent(...)` do site tem que terminar em uma destas gavetas:
    literal lido, sem 2º argumento, variável resolvida, ou opaco REGISTRADO
    com motivo. Call site novo que o detector não sabe ler reprova aqui e
    aparece — em vez de sumir calado, que é como o `rotulo`, o `motivo` e o
    `formato` viveram até hoje.
    """
    _, opacos, aninhados = _varrer_o_front()
    nao_registrados = [o for o in opacos
                       if (o[0], o[2]) not in _OPACOS_REGISTRADOS]
    assert not nao_registrados, (
        "call site de trackEvent que o detector não consegue ler: %s. Use um "
        "objeto literal ({chave: valor}) na chamada, ou registre em "
        "_OPACOS_REGISTRADOS explicando por que ele não traz chave nova."
        % nao_registrados)
    assert not aninhados, (
        "objeto de meta com `{}` aninhado em %s — o detector RECUSA adivinhar. "
        "Achate o objeto: o backend só grava chave rasa mesmo." % aninhados)


@pytest.mark.parametrize("quem", IDENTIDADES)
def test_as_TRES_chaves_achadas_em_28_08_sobrevivem(monkeypatch, quem):
    """📌 Os casos concretos, um por ponto cego do detector velho.
    Cada um morreu por um motivo de sintaxe DIFERENTE.

    🚨 06/09/2026 — a versão antiga perguntava ao `ast` se a chave está na
    lista. Um `_s = ""` dentro do laço (ou `_rot = ""` depois do saneamento)
    mantém as três na lista e faz as três chegarem VAZIAS ao banco — que é
    idêntico, pro painel, a nunca terem chegado. Agora o guarda manda um valor
    real e cobra o valor real de volta.
    """
    meta = meta_gravado({"rotulo": "Baixar XLSX", "motivo": "sem-arquivo",
                         "formato": "docx", "tela": "revisao",
                         "origem": "quantitativo"},
                        monkeypatch, event="clique:baixar-xlsx", quem=quem)
    for chave, esperado, onde in (
            ("rotulo", "Baixar XLSX", "aiarq-utils.js — meta como variável"),
            ("motivo", "sem-arquivo", "dashboard.html — trackEvent?.()"),
            ("formato", "docx", "memorial.html — atalho ES6 {job_id, formato}")):
        assert meta.get(chave) == esperado, (
            "o `%s` voltou a ser descartado calado (%s) — gravado: %r"
            % (chave, onde, meta))
    # os dois que nasceram depois, pelo mesmo caminho
    assert meta.get("tela") == "revisao" and meta.get("origem") == "quantitativo", meta


@pytest.mark.parametrize("quem", IDENTIDADES)
def test_o_rotulo_e_TEXTO_e_por_isso_o_saneamento_e_mais_duro(monkeypatch, quem):
    """🔒 `rotulo` é o único que carrega texto livre da página. A rota /api/track
    é ABERTA — qualquer um posta nela — então isto não pode virar porta pro
    painel admin.

    🚨 06/09/2026 — a versão antiga lia 400 caracteres depois de `_rot = ` e
    conferia a lista branca e o `[:60]`. Uma linha inserida logo ANTES do
    `if _rot:` (`_rot = str(payload.meta.get("rotulo") or "")[:300]`) desfazia
    tudo sem sair da janela — texto cru do visitante ia direto pro painel e o
    guarda ficava verde. Agora o guarda POSTA o ataque e olha o que sobrou.
    """
    ataque = ('<img src=x onerror="alert(document.cookie)"> Baixar & '
              "compartilhar / relatório " + "A" * 120)
    meta = meta_gravado({"rotulo": ataque}, monkeypatch,
                        event="clique:baixar-xlsx", quem=quem)
    rot = meta.get("rotulo", "")
    assert rot, "o rótulo sumiu por inteiro — o saneamento virou descarte"
    assert len(rot) <= 60, "o `rotulo` entra sem teto de tamanho: %d" % len(rot)
    for perigoso in ("<", ">", "&", '"', "'", "/", "="):
        assert perigoso not in rot, (
            "o caractere %r atravessou a lista branca do rótulo: %r" % (perigoso, rot))
    assert re.fullmatch(r"[0-9A-Za-zÀ-ÿ ._-]*", rot), (
        "o `rotulo` deixou de usar lista BRANCA de caracteres: %r" % rot)
    # 🧪 controle: o rótulo LEGÍTIMO tem que atravessar inteiro, com acento e
    # espaço — senão o saneamento certo seria "apagar tudo".
    bom = meta_gravado({"rotulo": "Baixar relatório em PDF"}, monkeypatch,
                       event="clique:baixar-xlsx", quem=quem)
    assert bom.get("rotulo") == "Baixar relatório em PDF", bom


def test_CONTROLE_POSITIVO_os_tres_pontos_cegos_do_detector_velho():
    """🧪 Os três casos que passavam batido. Sem isto eu não teria como saber
    se o detector novo realmente enxerga — e passaria verde de novo."""
    import tempfile
    casos = {
        # (a) optional chaining — o caso do `motivo`
        "a.html": "window.trackEvent?.('x', { motivo: 'termos' });",
        # (b) atalho ES6 sem dois-pontos — o caso do `formato`
        "b.html": "trackEvent('y', { job_id: j, formato });",
        # (c) meta como variável — o caso do `rotulo`
        "c.js": ("var meta = {};\n"
                 "meta.rotulo = txt;\n"
                 "window.trackEvent('clique:' + nome, meta);"),
        # (d) 🪤 a palavra só no COMENTÁRIO não pode virar chave
        "d.html": "// trackEvent('z', { chave_fantasma: 1 })\ntrackEvent('z');",
    }
    esperado = {"a.html": "motivo", "b.html": "formato", "c.js": "rotulo"}
    with tempfile.TemporaryDirectory() as tmp:
        global _RAIZ
        antes = _RAIZ
        try:
            for nome, conteudo in casos.items():
                io.open(os.path.join(tmp, nome), "w", encoding="utf-8").write(conteudo)
            _RAIZ = tmp
            chaves, opacos, _ = _varrer_o_front()
        finally:
            _RAIZ = antes
    for arq, chave in esperado.items():
        assert chave in chaves, (
            "o detector continua cego pro caso de %s (chave %r) — chaves "
            "vistas: %s" % (arq, chave, sorted(chaves)))
    assert "chave_fantasma" not in chaves, (
        "o detector leu um COMENTÁRIO como código — é o erro que eu cometi "
        "quatro vezes em 27/08")
    assert not opacos, "o caso da variável devia ter sido RESOLVIDO, não opaco"
