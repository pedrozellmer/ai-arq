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
    # 03/09/2026: o alfabeto era [a-z_]+ e nao lia nome com hifen nem
    # dois-pontos. `convite-area:exibido` era INVISIVEL pros DOIS lados deste
    # guarda. O comentario sai ANTES de extrair: o bloco tem aspas dentro de
    # comentario, e sem isso texto de comentario viraria 'evento permitido'.
    corpo = chr(10).join(l for l in m.group(1).splitlines()
                         if not l.strip().startswith('#'))
    return set(re.findall(r'"([a-z0-9_:-]+)"', corpo))


def _eventos_do_front():
    nomes = set()
    # 🪤 28/08/2026 — ESTE GUARDA TINHA PONTO CEGO. Varria só a RAIZ, e o blog
    # (26 posts em `blog/posts/`) ficava de fora. Ao ligar telemetria no blog
    # escrevi um `view_blog_post` que NÃO estava na allowlist — e este teste
    # passou VERDE, porque nem olhou o arquivo. É a terceira vez no mesmo dia
    # que um guarda meu falha por olhar só metade do território.
    arquivos = (glob.glob(os.path.join(_RAIZ, "*.html"))
                + glob.glob(os.path.join(_RAIZ, "*.js"))
                + glob.glob(os.path.join(_RAIZ, "blog", "*.html"))
                + glob.glob(os.path.join(_RAIZ, "blog", "posts", "*.html")))
    for f in arquivos:
        txt = io.open(f, encoding="utf-8", errors="replace").read()
        # 🪤 25/08: a versão anterior era `trackEvent\(` e ficava CEGA pra
        # `trackEvent?.('nome')` — optional chaining, que é como se escreve
        # chamada opcional em JS moderno. Escrevi um evento novo nesse estilo,
        # rodei este teste esperando que ele reprovasse, e ele passou VERDE.
        # O guarda contra "evento descartado em silêncio" tinha ele próprio um
        # ponto cego silencioso.
        # 03/09/2026 - O QUARTO PONTO CEGO DESTE GUARDA (depois de 'so a raiz'
        # e de trackEvent?.( ): o alfabeto [a-z_]+ nao aceitava hifen nem
        # dois-pontos. Os cinco eventos convite-area:* que subiram em 02/09
        # eram DESCARTADOS pelo /api/track e este teste passou VERDE, porque
        # nem conseguia LER o nome deles.
        for n in re.findall(r"trackEvent\s*\??\.?\(\s*['\"]([a-z0-9_:-]+)['\"]", txt):
            # `trackEvent('clique:' + nome, ...)` (aiarq-utils.js:204) monta o
            # nome em tempo de execucao: o literal e PREFIXO, nao evento.
            # Nome de evento de verdade nunca termina em dois-pontos.
            if n.endswith(':'):
                continue
            nomes.add(n)
        # 🪤 06/09: `trackEvent(cond ? 'tour_pulado' : 'tour_concluido')` — nome escolhido por
        # condição. O padrão acima só lê o literal COLADO no parêntese, então esses dois pareciam
        # órfãos (e o banco prova que disparam: o cliente-39 tem tour_concluido).
        # 🪤 e o ternário tem que estar no PRIMEIRO argumento: sem essa trava, o padrão pescava
        # `{ origem: x ? 'auto' : 'regerar' }` do META e inventava 15 "eventos" que não existem —
        # guarda que acusa o que não é defeito acaba desligado.
        for a, b in re.findall(
                r"trackEvent\s*\??\.?\(\s*[^,)'\"]*\?\s*'([a-z0-9_:-]+)'\s*:\s*'([a-z0-9_:-]+)'\s*[,)]", txt):
            nomes.add(a)
            nomes.add(b)
        for slug in re.findall(r'data-track="([^"]+)"', txt):
            # 🪤 06/09: o menu lateral monta o atributo em JS (`' data-track="' + it.track + '"'`),
            # e o regex acima capturava o PEDAÇO DE CÓDIGO como se fosse o nome. Slug de verdade é
            # só letra/dígito/hífen — o resto é expressão, e os nomes dela são lidos logo abaixo.
            if re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
                nomes.add("clique:" + slug)
        # ...e a definição de onde esses slugs saem (`track: 'menu-revisao'` em menu-lateral.js):
        # assim o guarda continua VENDO cada nome, em vez de ficar cego no dinâmico.
        for slug in re.findall(r"\btrack:\s*'([a-z0-9][a-z0-9-]*)'", txt):
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


def test_CONTROLE_o_extrator_LE_nome_com_hifen_e_dois_pontos():
    """🩸 03/09/2026 — O QUARTO PONTO CEGO, e o mais caro até agora.

    Em 02/09 subiram SEIS eventos do convite da área. CINCO tinham hífen e
    dois-pontos no nome (`convite-area:exibido` e irmãos) e o `/api/track`
    DESCARTAVA os cinco — inclusive o `exibido`, que é o DENOMINADOR e a razão
    de existir da mudança inteira. Este guarda passou VERDE porque o alfabeto
    dele (`[a-z_]+`) não conseguia sequer LER aquele nome.

    🔑 Só se descobriu no dia seguinte, chamando `_track_evento_aceito` de
    verdade. Um guarda que não enxerga o formato novo não reprova nada — e o
    silêncio dele lê-se como aprovação.
    """
    achou = re.findall(r"trackEvent\s*\??\.?\(\s*['\"]([a-z0-9_:-]+)['\"]",
                       "trackEvent('convite-area:exibido', {a: 1})")
    assert achou == ["convite-area:exibido"], achou
    # e o lado da allowlist tem que ler o mesmo alfabeto
    assert re.findall(r'"([a-z0-9_:-]+)"', '    "convite-area:submit-ok",') == \
        ["convite-area:submit-ok"]


def test_CONTROLE_a_leitura_da_allowlist_IGNORA_comentario():
    """🪤 Alargar o alfabeto fez o extrator enxergar aspas dentro de
    COMENTÁRIO. O bloco tem `{"status":"ignored"}` escrito num comentário —
    sem tirar comentário, 'status' e 'ignored' virariam eventos permitidos e o
    guarda passaria a aprovar nome que o backend descarta."""
    allow = _allowlist()
    for lixo in ("status", "ignored"):
        assert lixo not in allow, (
            "%r veio de texto de comentário e entrou na allowlist lida" % lixo)
    assert "convite-area:exibido" in allow, (
        "o evento real sumiu da leitura — o filtro de comentário comeu demais")


def test_CONTROLE_o_prefixo_montado_em_runtime_NAO_vira_evento():
    """🪤 Alargar o alfabeto fez o extrator enxergar o literal `'clique:'` de
    `aiarq-utils.js:204`, que é PREFIXO concatenado com o slug em tempo de
    execução. Sem este filtro o guarda reprova um evento que não existe — e
    guarda que acusa o que não é defeito acaba desligado."""
    achou = _eventos_do_front()
    assert "clique:" not in achou, "o prefixo cru voltou a ser lido como evento"
    assert "clique:convite-area-completar" in achou, (
        "o data-track de verdade sumiu da varredura")


def test_nenhum_nome_MORTO_na_allowlist():
    """O caminho inverso: nome na allowlist que NINGUÉM dispara.

    🩸 06/09/2026. Ao instrumentar o site inteiro ("registrar TUDO", Pedro) eu pus 21 nomes novos
    na allowlist e implementei o front aos poucos — ficaram 19 entradas mortas. O próprio arquivo
    do backend já avisava, em 30/08: *"Entrada morta em whitelist não custa, mas confunde: 'existe
    na lista' lê-se como 'medido'"*. Este guarda é essa frase virada teste: quem lê a lista pra
    saber o que está medido tem que poder confiar nela.

    🪤 Se um evento sair do front de propósito, TIRE o nome daqui no mesmo commit.
    """
    allow = _allowlist()
    front = _eventos_do_front()
    # `clique:<slug>` é aceito por regex no backend, não por nome — fora desta conta.
    mortos = sorted(n for n in allow if n not in front and not n.startswith("clique:"))
    assert not mortos, (
        "Nomes na _TRACK_ALLOWLIST que nenhum arquivo do site dispara — ou implemente o disparo, "
        f"ou tire o nome da lista no mesmo commit: {mortos}"
    )
