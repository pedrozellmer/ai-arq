# -*- coding: utf-8 -*-
"""Cache por conteúdo: o carimbo tem que mudar quando a RESPOSTA mudaria.

🎯 28/08/2026. Toda leitura de prancha custa uma chamada de IA, e a mesma
prancha é lida de novo em três situações: o cliente reprocessa, o job cai e
retoma sozinho, e a bancada roda o mesmo arquivo dezenas de vezes. Além do
custo, o motor não é determinístico — a mesma prancha já deu 22 e 34 itens.

🔑 O DESENHO: carimbar o PAYLOAD que vai pra API, não uma lista de ingredientes
mantida à mão. Mexeu no SYSTEM_PROMPT, na diretiva de pé-direito, na env do
modelo ou na temperatura → a chave muda sozinha.

🪤 A ARMADILHA JÁ EXISTE NO REPO, e é ela que este arquivo existe pra impedir
de se repetir: `pdfvec_carimbo.py:220` cacheia por
`sha256(arquivo):página:_PROMPT_VERSION`, com `_PROMPT_VERSION = "v3"` bumpado
NA MÃO e **sem o modelo na chave**. Trocar Haiku por Sonnet ali serve a
resposta do modelo velho, calada. A própria skill do projeto
(`content-hash-cache-pattern`) avisa disso em "when NOT to use".

📌 A pergunta que cada teste abaixo responde é sempre a mesma: **se a resposta
da IA mudaria, a chave muda?** Guarda que só testa "mesmo payload dá hit" é
inútil — o dano mora do outro lado.

✅ Payload estável foi MEDIDO antes de construir: 4 extrações do mesmo DXF de
24 MB, em subprocessos separados (`PYTHONHASHSEED` diferente em cada), deram
sha256 idêntico. Sem isso o cache nasceria com 0% de acerto.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import llm_cache  # noqa: E402


def _payload(**mudanca):
    """Um payload representativo do caminho DXF, com um campo trocável."""
    base = {
        "tag": "dxf:prancha.dxf",
        "model": "claude-sonnet-4-6",
        "max_tokens": 32000,
        "temperature": 0.7,
        "cache_system": True,
        "system": "Você lê pranchas de arquitetura e devolve JSON.",
        "messages": [{"role": "user", "content": "PÉ-DIREITO: 2.80 m\nLAYERS: ..."}],
    }
    base.update(mudanca)
    return base


# ───────────────────────── o lado que importa: MUDOU → MISS ──────────────────

def test_mudar_UM_CARACTERE_do_system_muda_a_chave():
    """🚨 O teste da armadilha. É esta a diferença entre o cache novo e o
    `pdfvec_carimbo`: lá o prompt só invalida se alguém lembrar de bumpar uma
    string à mão. Aqui é mecânico."""
    a = llm_cache.carimbo(_payload())
    b = llm_cache.carimbo(_payload(
        system="Você lê pranchas de arquitetura e devolve JSON!"))
    assert a != b, (
        "mudei o SYSTEM_PROMPT e a chave ficou igual — todo conserto de prompt "
        "passaria a servir a resposta ANTERIOR, e a gente pararia de ver o "
        "conserto funcionar")


def test_mudar_o_MODELO_muda_a_chave():
    """🪤 Exatamente o buraco do `pdfvec_carimbo`, que não tem o modelo na
    chave. `DXF_EXTRACT_MODEL` é env do Render e troca SEM deploy — carimbo
    baseado em git sha não pegaria."""
    assert llm_cache.carimbo(_payload()) != llm_cache.carimbo(
        _payload(model="claude-opus-4-8")), "trocar de modelo não invalidou"


def test_mudar_a_TEMPERATURA_muda_a_chave():
    """`DXF_EXTRACT_TEMP` também é env do Render (default 0,7). Foi ela que
    custou a prancha da cliente-16 em 26/08 quando estava em 0."""
    assert llm_cache.carimbo(_payload()) != llm_cache.carimbo(
        _payload(temperature=0.0)), "trocar a temperatura não invalidou"


def test_mudar_o_PE_DIREITO_do_cliente_muda_a_chave():
    """O pé-direito informado entra no prompt (`_pd_directive`). Se ele não
    invalidasse, o cliente informaria a altura e receberia de volta a leitura
    feita SEM ela — e concluiria que informar não adianta nada."""
    outro = _payload()
    outro["messages"] = [{"role": "user", "content": "PÉ-DIREITO: 3.50 m\nLAYERS: ..."}]
    assert llm_cache.carimbo(_payload()) != llm_cache.carimbo(outro)


def test_kwarg_DESCONHECIDO_entra_no_hash_por_padrao():
    """🔒 LISTA NEGRA, nunca lista branca. Parâmetro novo que alguém acrescentar
    amanhã tem que invalidar por padrão.

    Foi lista BRANCA que matou o instrumento do cadastro em 27/08: a chave
    `campo` era descartada calada porque não estava numa lista. Aqui o custo de
    errar pra esse lado é servir resposta velha — pior."""
    a = llm_cache.carimbo(_payload())
    b = llm_cache.carimbo(_payload(parametro_que_ninguem_previu="x"))
    assert a != b, (
        "kwarg desconhecido NÃO entrou no hash — o carimbo virou lista branca "
        "e passa a ignorar tudo que for inventado depois")


# ───────────────────── o outro lado: NÃO-semântico → mesma chave ─────────────

def test_cache_system_NAO_muda_a_chave():
    """`cache_system` liga o prompt caching da Anthropic: muda o CUSTO, não a
    resposta. Se invalidasse, o cache nunca acertaria entre uma chamada com e
    outra sem — que é o que acontece quando `LLM_PROMPT_CACHE=0`."""
    assert llm_cache.carimbo(_payload(cache_system=True)) == \
           llm_cache.carimbo(_payload(cache_system=False))


def test_a_TAG_e_a_politica_de_retry_NAO_mudam_a_chave():
    """`tag` é rótulo de log e traz o NOME DO ARQUIVO. Se entrasse na chave,
    dois arquivos de conteúdo idêntico com nomes diferentes nunca se
    aproveitariam — e renomear um arquivo invalidaria o cache dele."""
    assert llm_cache.carimbo(_payload(tag="dxf:outro-nome.dxf")) == \
           llm_cache.carimbo(_payload())
    assert llm_cache.carimbo(_payload(max_retries=3)) == \
           llm_cache.carimbo(_payload())


def test_a_ORDEM_das_chaves_nao_muda_a_chave():
    """Dicionário reordenado é o mesmo payload. Sem `sort_keys` o cache
    acertaria por acaso."""
    a = _payload()
    b = {k: a[k] for k in reversed(list(a.keys()))}
    assert llm_cache.carimbo(a) == llm_cache.carimbo(b)


# ─────────────────────────── o que NÃO pode ser gravado ──────────────────────

class _Resp:
    class _B:
        def __init__(self, t):
            self.text = t
    def __init__(self, texto, stop="end_turn"):
        self.content = [self._B(texto)]
        self.stop_reason = stop


def test_resposta_CORTADA_no_teto_nao_pode_ser_gravada():
    """🚨 A trava que mais importa. Medido em 24/08: `stop_reason='max_tokens'`
    acontece em ~22% das leituras de DXF. Gravar uma dessas congelaria a leitura
    MUTILADA e ela voltaria pra sempre — inclusive depois de a gente consertar o
    corte. É o pior estrago possível aqui: bug antigo servido como resposta boa.
    """
    pode, motivo = llm_cache.pode_gravar(_Resp('{"items": [', stop="max_tokens"))
    assert not pode, "resposta cortada no teto seria gravada e servida pra sempre"
    assert "max_tokens" in motivo


def test_resposta_VAZIA_nao_pode_ser_gravada():
    """Planilha vazia é sempre falha (armadilha nº10 do CLAUDE.md). Cachear
    uma transformaria uma falha momentânea em falha permanente."""
    assert not llm_cache.pode_gravar(_Resp(""))[0]
    assert not llm_cache.pode_gravar(_Resp("   \n  "))[0]


def test_resposta_COMPLETA_pode():
    """🧪 Controle positivo: sem isto, `pode_gravar` retornando sempre False
    passaria nos dois testes acima e o cache nunca gravaria nada."""
    pode, motivo = llm_cache.pode_gravar(_Resp('{"items": [{"d": "parede"}]}'))
    assert pode, "resposta boa foi recusada: %s" % motivo


# ─────────────────────────────── o modo de operação ──────────────────────────

def test_o_default_e_SOMBRA(monkeypatch):
    """🪤 O default NÃO serve do cache. Calcula a chave e loga acerto/erro, e é
    isso — pra medir a taxa real antes de mudar a leitura de um cliente sequer.

    O único jeito de pegar cedo o caso "payload instável = 0% de acerto" sem
    estragar a leitura de ninguém. Provei estabilidade em UM arquivo; sombra é
    o que cobre os outros."""
    monkeypatch.delenv("LLM_CACHE", raising=False)
    assert llm_cache._modo() == "sombra"


@pytest.mark.parametrize("valor", ["off", "OFF", " Off ", "\toFF\n", "Off"])
def test_o_kill_switch_funciona(monkeypatch, valor):
    """`LLM_CACHE=off` desliga sem deploy — rede de segurança pro caminho que
    gera a planilha.

    🪤 PARAMETRIZADO DE PROPÓSITO. A versão anterior só escrevia `off` em
    minúsculo, então a normalização (`.strip().lower()`) nunca era exercitada:
    ela podia cair e o kill switch deixaria de existir pra quem digitasse
    `OFF` ou ` Off ` no painel do Render — sem erro, sem log, servindo resposta
    velha e escrevendo no banco enquanto o operador acha que desligou. Quem
    aperta o botão de emergência às 3h da manhã não digita com cuidado.
    """
    monkeypatch.setenv("LLM_CACHE", valor)
    assert llm_cache._modo() == "off", (
        "LLM_CACHE=%r não foi entendido como desligado: a trava virou enfeite "
        "e o kill switch não desliga nada" % valor)
    assert llm_cache.ler("qualquer") is None
    assert llm_cache.gravar("qualquer", _Resp("x"), {}) is False


@pytest.mark.parametrize("valor,esperado", [
    # 🧪 CONTROLE POSITIVO da normalização: sem estes casos, um `_modo()` que
    # devolvesse "off" pra tudo passaria no teste de cima.
    ("on", "on"), ("ON", "on"), (" On ", "on"),
    ("sombra", "sombra"), ("SOMBRA", "sombra"), (" Sombra\n", "sombra"),
    # e errar o valor não pode LIGAR o cache por acidente
    ("sim", "sombra"), ("SIM", "sombra"), ("ligado", "sombra"),
    ("", "sombra"), ("   ", "sombra"), ("of", "sombra"),
])
def test_a_env_do_cache_e_normalizada_nos_DOIS_sentidos(monkeypatch, valor,
                                                        esperado):
    """Errar o valor da env cai pra SOMBRA; acertar em QUALQUER caixa vale."""
    monkeypatch.setenv("LLM_CACHE", valor)
    assert llm_cache._modo() == esperado, (
        "LLM_CACHE=%r virou %r, esperava %r"
        % (valor, llm_cache._modo(), esperado))


# ────────────────────────── a lista negra é decisão de gente ─────────────────

def test_a_LISTA_NEGRA_nao_cresce_sozinha():
    """🚨 Cada nome aqui é um parâmetro que o carimbo IGNORA. Acrescentar um por
    engano faz o cache servir resposta velha quando não devia — e isso é
    silencioso. Se este teste falhar, a pergunta é: esse parâmetro realmente
    não muda a RESPOSTA da IA?"""
    assert llm_cache._NAO_SEMANTICO == frozenset({
        "tag", "max_retries", "base_delay", "max_delay",
        "cache_system", "cache", "extra_headers", "stream", "timeout",
    }), ("a lista do que o carimbo ignora mudou: %s. Justifique cada nome novo "
         "— o custo de errar aqui é servir leitura velha, calado."
         % sorted(llm_cache._NAO_SEMANTICO))


# ─────────── a ponte: do banco até o `cache=` que a chamada de IA recebe ─────

def _main_src():
    import io
    return io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()


def _process_job_ast(src):
    import ast
    fn = [n for n in ast.walk(ast.parse(src))
          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
          and n.name == "process_job"]
    assert len(fn) == 1, "process_job sumiu ou virou duas definições"
    return fn[0]


class _Qualquer(object):
    """Preenchimento pros nomes do call site que não interessam a este guarda.

    🪤 De propósito NÃO responde `== 0` como verdadeiro: se alguém trocar
    `_reproc_atual` por outra variável no `cache=`, ela cai aqui e o CONTROLE
    (`cache` tem que ser True na 1ª leitura) reprova.
    """
    def __getattr__(self, _n):
        return _Qualquer()

    def __call__(self, *a, **k):
        return _Qualquer()

    def __contains__(self, _o):
        return False

    def __iter__(self):
        return iter(())


def _kwargs_que_chegam_na_IA(ns):
    """Executa os statements REAIS que montam e entregam os kwargs da chamada
    de IA, dentro do namespace `ns` que a fatia de produção produziu.

    🔑 É AQUI QUE ESTÁ A PONTE. A versão anterior deste guarda tinha duas
    metades soltas: uma rodava o bloco que lê o `reprocess_count` do banco, a
    outra avaliava a expressão do `cache=` com um valor injetado NA MÃO. Entre
    as duas não havia nada — e o que decide a vida do cliente é justamente o
    encontro delas.

    Também não basta olhar o `dict(...)`: `_dxf_kwargs["cache"] = True` uma
    linha abaixo reabriria o defeito com a expressão original intacta. Por isso
    o que se captura é o que o **call site da IA** recebe, depois de todos os
    statements que mexem nesse dicionário.
    """
    import ast

    src = _main_src()
    fn = _process_job_ast(src)

    pais = {}
    for n in ast.walk(fn):
        for f in ast.iter_child_nodes(n):
            pais[f] = n

    def _stmt_de(no):
        while no is not None and not isinstance(no, ast.stmt):
            no = pais.get(no)
        return no

    montagem = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                and any(kw.arg == "cache" for kw in n.keywords)]
    assert len(montagem) == 1, (
        "esperava UMA chamada de IA passando `cache=` no process_job, achei %d "
        "— o cache por conteúdo saiu (ou se multiplicou) no caminho do cliente "
        "sem ninguém notar" % len(montagem))
    st_montagem = _stmt_de(montagem[0])
    assert isinstance(st_montagem, ast.Assign) and len(st_montagem.targets) == 1 \
        and isinstance(st_montagem.targets[0], ast.Name), (
        "o `cache=` deixou de ser montado num dicionário nomeado; este guarda "
        "precisa ser reescrito, não afrouxado")
    alvo = st_montagem.targets[0].id

    # todo statement do process_job que MEXE nesse dicionário, em ordem
    passos = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and n.id == alvo:
            st = _stmt_de(n)
            if st is not None and st.lineno >= st_montagem.lineno:
                passos[(st.lineno, st.col_offset)] = st
    passos = [passos[k] for k in sorted(passos)]
    assert passos and passos[0] is st_montagem

    # o último é a entrega: `..._llm_retry(cliente, **_dxf_kwargs)`. Trocamos só
    # a função por uma captura — os argumentos continuam sendo os de produção.
    entrega = [n for st in passos for n in ast.walk(st)
               if isinstance(n, ast.Call)
               and any(kw.arg is None and isinstance(kw.value, ast.Name)
                       and kw.value.id == alvo for kw in n.keywords)]
    assert len(entrega) == 1, (
        "não achei UMA chamada que repasse `**%s` pra IA (achei %d) — os "
        "kwargs montados podem não ser os que a IA recebe" % (alvo, len(entrega)))
    entrega[0].func = ast.Name(id="_CAPTURA_IA", ctx=ast.Load())

    capturado = {}

    def _captura(*a, **k):
        capturado.update(k)
        return _Qualquer()

    assert "_reproc_atual" in ns, (
        "a fatia real do process_job não produziu `_reproc_atual` — a ponte "
        "entre o que o banco diz e o que a IA recebe está rompida")

    g = dict(ns)
    g["_CAPTURA_IA"] = _captura
    g.setdefault("os", os)
    g.setdefault("dxf_path", "/tmp/prancha-de-teste.dxf")
    fonte = ""
    for st in passos:
        fonte += ast.unparse(ast.fix_missing_locations(st)) + "\n"
    import builtins
    for n in ast.walk(ast.parse(fonte)):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) \
                and n.id not in g and not hasattr(builtins, n.id):
            assert n.id != "_reproc_atual", (
                "o `cache=` olha um `_reproc_atual` que a fatia do banco não "
                "produziu")
            g[n.id] = _Qualquer()
    exec(compile(fonte, "call_site_da_ia", "exec"), g)
    assert capturado, "a chamada de IA não recebeu kwargs nenhum"
    return alvo, capturado


def _ns_do_bloco_de_reprocesso(reprocess_count):
    """Roda o pedaço REAL que lê `reprocess_count` e devolve o NAMESPACE dele.

    🪤 Este bloco fala com o banco por `urllib.request.urlopen` DIRETO, sem o
    helper — quem patchar `_supa_rest_service` não intercepta nada e vê zero
    parecendo zero de verdade."""
    import json as _j
    import textwrap
    import urllib.request
    src = _main_src()
    linhas = src.splitlines(True)
    fn = _process_job_ast(src)
    corpo = "".join(linhas[fn.lineno - 1:fn.end_lineno])
    a = "_reproc_atual = 0\n"
    z = 'print(f"[ckpt] cache indisponível (segue do zero): {_cke}")'
    assert corpo.count(a) == 1 and corpo.count(z) == 1, (
        "as âncoras do bloco que lê o reprocess_count deixaram de ser únicas")
    i = corpo.rfind("\n", 0, corpo.index(a)) + 1
    j = corpo.index("\n", corpo.index(z, i)) + 1
    fatia = textwrap.dedent(corpo[i:j])

    class _R(object):
        def read(self):
            return _j.dumps([{"reprocess_count": reprocess_count,
                              "auto_resume_count": 0}]).encode("utf-8")

    ns = {"__name__": "cache_ns", "_json": _j, "job_id": "job-teste",
          "SUPABASE_URL": "https://exemplo.invalid",
          "SUPABASE_KEY": "anon-de-mentira",
          "SUPABASE_SERVICE_ROLE_KEY": "service-de-mentira",
          "_ckpt_load_all": lambda j: {}}
    real = urllib.request.urlopen
    urllib.request.urlopen = lambda req, **k: _R()
    try:
        exec(compile(fatia, "reproc_atual", "exec"), ns)
    finally:
        urllib.request.urlopen = real
    return ns


def _reproc_atual_lido_do_banco(reprocess_count):
    return _ns_do_bloco_de_reprocesso(reprocess_count)["_reproc_atual"]


@pytest.mark.parametrize("reproc", [1, 2, 7, 126])
def test_o_reprocesso_do_cliente_NAO_le_do_cache(reproc):
    """🪤 Quem clica "reprocessar" quer leitura NOVA. Com temperatura 0,7 uma
    rodada nova é justamente a chance de consertar a prancha — servir o cache
    ali mataria a saída de emergência dele.

    Guarda do CALL SITE, e ligado ao banco de ponta a ponta: já passei verde
    duas vezes testando a função e não quem chama, uma terceira procurando a
    string `_reproc_atual == 0` numa expressão que sempre dava True, e uma
    quarta avaliando essa expressão com um número que eu mesmo tinha inventado.
    """
    ns = _ns_do_bloco_de_reprocesso(reproc)
    assert ns["_reproc_atual"] == reproc, (
        "o motor deixou de ler o reprocess_count do projeto — a decisão de "
        "cache passa a ser tomada sobre zero")
    alvo, kwargs = _kwargs_que_chegam_na_IA(ns)
    assert "cache" in kwargs, (
        "a chamada de IA não recebe mais `cache=` — o cache por conteúdo saiu "
        "do caminho do cliente")
    assert kwargs["cache"] is False, (
        "com reprocess_count=%d a chamada de IA ainda serve cache "
        "(%s['cache'] = %r) — a saída de emergência do cliente devolve a "
        "leitura anterior" % (reproc, alvo, kwargs["cache"]))


def test_CONTROLE_a_PRIMEIRA_leitura_continua_podendo_usar_o_cache():
    """O outro lado: desligar o cache sempre custaria uma chamada de IA em todo
    job, e o guarda de cima passaria igual. Sem este controle ele exigiria só
    'nunca cacheie'.

    🧪 E é este controle que amarra a ponte na variável CERTA: se o `cache=`
    passar a olhar outra coisa que não o `_reproc_atual` lido do banco, ela
    chega aqui como preenchimento e o valor deixa de ser True."""
    ns = _ns_do_bloco_de_reprocesso(0)
    assert ns["_reproc_atual"] == 0
    alvo, kwargs = _kwargs_que_chegam_na_IA(ns)
    assert kwargs.get("cache") is True, (
        "a 1ª leitura do projeto deixou de poder usar o cache: %s['cache'] = %r"
        % (alvo, kwargs.get("cache")))


def test_o_cache_DA_SINAL_DE_VIDA_no_boot():
    """🩺 Sem isto o cache pode estar MORTO e o log fica idêntico ao de um cache
    que só não acertou ainda — porque tudo aqui é best-effort e silencioso.

    Foi assim que o `signup_saiu_da_tela` viveu um dia inteiro sem gravar o
    `campo` em 27/08: o instrumento existia, chegava ao banco, e perdia a única
    informação pra qual foi feito. Uma linha no boot responde antes de qualquer
    cliente chegar.
    """
    import io
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    i = src.find('@app.on_event("startup")')
    assert i > 0, "sumiu o hook de startup"
    j = src.find("\n@app.", i + 10)
    bloco = src[i:j if j > 0 else i + 20000]
    assert "boot:llm-cache" in bloco, (
        "o cache não deixa mais sinal de vida no boot — se ele morrer, a "
        "medição de sombra dá ZERO por motivo errado e ninguém saberia")
    # 🪤 E o sinal tem que provar a GRAVAÇÃO, não só a leitura. A 1ª versão só
    # lia; descobri o furo tentando gravar da minha máquina e levando 42501 do
    # RLS. Em modo sombra nada grava até um cliente processar um projeto, então
    # sem isto um cache que não escreve passaria semanas parecendo um cache que
    # só não acertou ainda.
    assert "checar_no_boot" in bloco, (
        "o sinal de boot voltou a testar só a leitura — gravação continuaria "
        "sem prova nenhuma")
    # e o sinal tem que distinguir vivo de morto, não só 'passei por aqui'
    assert "MORTO" in bloco and "VIVO" in bloco, (
        "o sinal de boot não separa vivo de morto")
    assert 'severity="error"' in bloco, (
        "a falha do cache no boot entra como info — ela some no meio do log")


def test_a_sentinela_do_boot_prova_a_IDA_E_A_VOLTA():
    """🚨 O que faltava. Gravar e não conseguir ler de volta, ou ler valor
    VELHO, tem que reprovar — não basta a chamada não estourar."""
    import io
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "llm_cache.py"), encoding="utf-8").read()
    i = src.find("def checar_no_boot")
    j = src.find("\ndef ", i + 10)
    corpo = "\n".join(l for l in src[i:j].split("\n")
                      if not l.strip().startswith("#"))
    assert "merge-duplicates" in corpo, (
        "voltou a usar ignore-duplicates: aí a gravação só seria exercitada no "
        "PRIMEIRO boot da vida e nunca mais")
    assert "ler(" in corpo, "grava e não confere se conseguiu ler de volta"
    assert "VELHO" in corpo or "!=" in corpo, (
        "não compara o que leu com o que escreveu — leria a linha do boot "
        "anterior e daria tudo certo com a gravação quebrada")
