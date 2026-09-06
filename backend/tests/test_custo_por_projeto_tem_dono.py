# -*- coding: utf-8 -*-
"""Todo gasto de IA tem dono, e toda chamada deixa exatamente uma linha.

🚨 06/09/2026 — o Pedro perguntou "quanto custa processar um projeto" e não
havia resposta. O único registro que existia (error_log stage='llm:cache', 990
linhas desde 24/08) não dizia QUAL MODELO gastou nem DE QUEM foi o gasto:
· sem modelo não vira reais (o mesmo milhão de tokens de saída custa 5× mais no
  Sonnet que no Haiku);
· sem job_id não dá pra separar cliente de bancada — e na janela medida havia
  MAIS avaliação nossa (38) do que projeto de cliente (39), então dividir a
  fatura pelos projetos de cliente inflava o custo em ~2×.

Este arquivo guarda os dois invariantes que sustentam a medição:
  (1) ISOLAMENTO — o dono de um projeto nunca vaza pro projeto seguinte;
  (2) UMA LINHA SEMPRE — chamada que falhou, que veio sem `usage` ou que foi
      servida pelo cache também deixam rastro. Linha ausente, somada por SUM e
      dividida por projeto, é indistinguível de custo baixo.
"""
import io
import os
import re
import sys
import threading

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import llm_retry  # noqa: E402
from llm_retry import escopo_job, _JOB_ATUAL, _etapa_e_escopo, _ETAPAS  # noqa: E402


class _Uso:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _Resp:
    def __init__(self, usage=None, model=None):
        self.usage = usage
        self.model = model
        self.content = []
        self.stop_reason = "end_turn"


def _capturar(monkey_alvo=None):
    """Troca o gravador por um coletor. Devolve (linhas, restaurar)."""
    linhas = []
    original = llm_retry._gravar_uso

    def _falso(**kw):
        linhas.append(kw)
    llm_retry._gravar_uso = _falso
    return linhas, (lambda: setattr(llm_retry, "_gravar_uso", original))


# ─────────────────────────────────────────────────────────────────────────────
#  (1) ISOLAMENTO — regra dura nº2
# ─────────────────────────────────────────────────────────────────────────────

def test_o_dono_nao_vaza_entre_projetos_paralelos():
    """Dois jobs em threads paralelas: cada um lê o SEU id, nunca o do outro."""
    lidos = {}
    barreira = threading.Barrier(2)

    def _trabalho(nome):
        with escopo_job(nome):
            barreira.wait(timeout=5)   # força a sobreposição real
            lidos[nome] = _JOB_ATUAL.get()

    ts = [threading.Thread(target=_trabalho, args=(n,)) for n in ("aaa111", "bbb222")]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=10)

    assert lidos == {"aaa111": "aaa111", "bbb222": "bbb222"}, lidos


def test_CONTROLE_uma_variavel_de_modulo_VAZARIA_no_mesmo_teste():
    """🔑 Controle positivo: o teste acima só vale se souber reprovar.

    Aqui a mesma coreografia roda com uma variável de módulo no lugar da
    ContextVar — e ela TEM que embaralhar os donos. Se um dia este teste passar
    a dar 'não vazou', o teste de cima virou decoração.
    """
    estado = {"job": None}
    lidos = {}
    barreira = threading.Barrier(2)

    def _trabalho(nome):
        estado["job"] = nome              # exatamente o que a global faria
        barreira.wait(timeout=5)
        lidos[nome] = estado["job"]

    ts = [threading.Thread(target=_trabalho, args=(n,)) for n in ("aaa111", "bbb222")]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=10)

    assert lidos["aaa111"] == lidos["bbb222"], (
        "a variável de módulo NÃO embaralhou os donos — o controle positivo "
        "parou de provar o vazamento que justifica a ContextVar")


def test_a_thread_da_sombra_nao_herda_o_dono_do_job_que_a_criou():
    """🩸 A sombra do PDF é o motivo de tudo isto existir.

    Ela é disparada DENTRO do process_job (main.py:12664), dorme 8s
    (pdf_vector.py:405) e trabalha por até 180s (pdf_vector.py:32): atravessa o
    semáforo de 1 job (main.py:6198) e roda junto com o PRÓXIMO projeto. Se
    herdasse o contexto, o custo do carimbo do projeto A cairia no projeto B.
    """
    visto = {}

    def _sombra():
        visto["dentro"] = _JOB_ATUAL.get()

    with escopo_job("aaa111"):
        t = threading.Thread(target=_sombra)
        t.start()
        t.join(timeout=5)

    assert visto["dentro"] is None, (
        "a thread nova herdou o dono — o custo da sombra seria carimbado no "
        "projeto errado")


def test_o_escopo_sempre_devolve_o_valor_anterior():
    assert _JOB_ATUAL.get() is None
    with escopo_job("aaa111"):
        assert _JOB_ATUAL.get() == "aaa111"
        with escopo_job("bbb222"):
            assert _JOB_ATUAL.get() == "bbb222"
        assert _JOB_ATUAL.get() == "aaa111"
    assert _JOB_ATUAL.get() is None


def test_so_o_escopo_job_pode_carimbar_o_dono():
    """🪤 O invariante certo NÃO é 'proibir escopo_job dentro de pool'.

    Medido em Python 3.13: `escopo_job` (set + reset no finally) dentro de um
    worker de pool é SEGURO — a tarefa seguinte naquele worker lê None. O que
    vaza é um `.set()` solto, sem reset. Então o guarda persegue o `.set()`,
    não o `with`.
    """
    fonte = io.open(os.path.join(_BACKEND, "llm_retry.py"), encoding="utf-8").read()
    # tira o corpo do próprio escopo_job, que é o único lugar autorizado
    corpo = fonte.split("def escopo_job(", 1)
    assert len(corpo) == 2, "escopo_job sumiu de llm_retry.py"
    antes, resto = corpo[0], corpo[1]
    depois = resto.split("\n_ETAPAS", 1)
    assert len(depois) == 2, "o catálogo _ETAPAS mudou de lugar; ajuste o recorte"
    fora = antes + depois[1]
    achados = re.findall(r"_JOB_ATUAL\s*\.\s*set\s*\(", fora)
    assert not achados, (
        "há %d `_JOB_ATUAL.set(` fora do escopo_job — um set sem reset vaza o "
        "dono pra tarefa seguinte no mesmo worker de pool" % len(achados))


# ─────────────────────────────────────────────────────────────────────────────
#  (2) UMA LINHA SEMPRE — "vazio não é falhou"
# ─────────────────────────────────────────────────────────────────────────────

def test_chamada_sem_usage_GRAVA_linha_em_vez_de_sumir():
    """🪤 Antes isto era `return` puro: a chamada acontecia, era COBRADA, e
    sumia do registro — e o projeto parecia mais barato do que foi."""
    linhas, restaurar = _capturar()
    try:
        llm_retry._registrar_uso("sinapi_pick", _Resp(usage=None), False,
                                 model="claude-haiku-4-5-20251001", job_id="aaa111")
    finally:
        restaurar()
    assert len(linhas) == 1, linhas
    assert linhas[0]["resultado"] == "sem_usage"
    assert linhas[0]["erro"] == "usage_ausente"
    assert linhas[0]["job_id"] == "aaa111"
    # e os tokens NÃO podem ter virado zero: "não sei" ≠ "custou zero"
    assert linhas[0].get("novo") is None, linhas[0]


def test_usage_zerado_tambem_grava_linha():
    linhas, restaurar = _capturar()
    try:
        u = _Uso(input_tokens=0, output_tokens=0,
                 cache_read_input_tokens=0, cache_creation_input_tokens=0)
        llm_retry._registrar_uso("classifier", _Resp(usage=u), False,
                                 model="claude-haiku-4-5-20251001")
    finally:
        restaurar()
    assert len(linhas) == 1 and linhas[0]["erro"] == "usage_zerado", linhas


def test_chamada_boa_grava_os_quatro_contadores_e_o_modelo_da_RESPOSTA():
    """O modelo do DXF muda por variável de ambiente SEM deploy (main.py:2498):
    quem responde é a resposta, não o kwargs."""
    linhas, restaurar = _capturar()
    try:
        u = _Uso(input_tokens=100, output_tokens=7,
                 cache_read_input_tokens=5, cache_creation_input_tokens=3)
        llm_retry._registrar_uso("dxf:PLANTA DO CLIENTE.dxf",
                                 _Resp(usage=u, model="claude-sonnet-4-6"), True,
                                 model="modelo-do-kwargs", job_id="aaa111")
    finally:
        restaurar()
    assert len(linhas) == 1
    L = linhas[0]
    assert L["modelo"] == "claude-sonnet-4-6", "prevaleceu o kwargs sobre a resposta"
    assert (L["novo"], L["out"], L["le"], L["esc"]) == (100, 7, 5, 3), L
    assert L["cache_marcado"] is True


def test_CONTROLE_o_coletor_enxerga_a_ausencia_de_linha():
    """Se o gravador voltar a ser um `return` mudo, os testes acima têm que cair.
    Aqui provo que o coletor NÃO inventa linha sozinho."""
    linhas, restaurar = _capturar()
    try:
        pass  # ninguém chamou nada
    finally:
        restaurar()
    assert linhas == []


# ─────────────────────────────────────────────────────────────────────────────
#  Catálogo, escopo e nome de arquivo do cliente
# ─────────────────────────────────────────────────────────────────────────────

def test_o_nome_do_arquivo_do_cliente_NAO_entra_na_tabela_de_dinheiro():
    """🪤 A tag de produção carrega o nome do arquivo (analyzer.py:1243,
    main.py:9391). Isso torna o agrupamento impossível E põe dado de cliente
    numa tabela interna (regra nº6)."""
    etapa, escopo = _etapa_e_escopo("analyzer:CASA DO JOÃO - PLANTA BAIXA.pdf")
    assert etapa == "prancha", etapa
    assert escopo == "projeto"
    etapa2, _ = _etapa_e_escopo("dxf:280-PE-ARQ-CASA 02 DORMIT.dxf")
    assert etapa2 == "dxf"
    etapa3, _ = _etapa_e_escopo("agent:job=aaa111")
    assert etapa3 == "agent"


def test_etapa_fora_do_catalogo_NAO_e_lavada_como_plataforma():
    """🚨 Se `escopo` saísse da presença do job_id ('tem dono? então projeto'),
    toda chamada órfã viraria 'plataforma' e o guarda de órfãos daria 0 pra
    sempre — lavando exatamente o defeito que ele procura."""
    etapa, escopo = _etapa_e_escopo("etapa-que-ninguem-declarou")
    assert escopo == "desconhecido", (
        "etapa nova foi carimbada como %r — o gasto sumiria da conta sem "
        "ninguém ver" % escopo)


def test_toda_tag_de_producao_esta_no_catalogo():
    """Guarda de cobertura: call site novo sem entrada no catálogo grava
    'desconhecido' e some da conta do cliente. Aqui ele é pego na bancada."""
    import glob
    faltando = set()
    for arq in glob.glob(os.path.join(_BACKEND, "*.py")):
        if os.path.basename(arq) in ("llm_retry.py",):
            continue
        txt = io.open(arq, encoding="utf-8", errors="replace").read()
        for tag in re.findall(r'tag=(?:f)?["\']([^"\'{]+)', txt):
            base = tag.split(":", 1)[0].strip()
            etapa = llm_retry._PREFIXO_ETAPA.get(base, base)
            if etapa and etapa not in _ETAPAS:
                faltando.add((os.path.basename(arq), etapa))
    assert not faltando, (
        "tags de produção fora do catálogo _ETAPAS (llm_retry.py) — declare o "
        "escopo delas no mesmo commit: %s" % sorted(faltando))


def test_CONTROLE_o_varredor_de_tags_ACHA_uma_etapa_intrusa():
    """O guarda acima só vale se souber acusar. Aqui provo que a peneira pega."""
    achados = re.findall(r'tag=(?:f)?["\']([^"\'{]+)', 'x = _cwr(c, tag="etapa-intrusa", model="m")')
    assert achados == ["etapa-intrusa"], achados
    assert "etapa-intrusa" not in _ETAPAS


# ─────────────────────────────────────────────────────────────────────────────
#  A régua do job_id
# ─────────────────────────────────────────────────────────────────────────────

def test_a_regua_do_dono_aceita_os_formatos_REAIS_de_job_id():
    """🩸 job_id NÃO é UUID: nasce `str(uuid.uuid4())[:8]` (main.py:13604), e
    avaliação/merge ganham prefixo — 'ev'+6 (main.py:24035) e 'mg'+6
    (main.py:25570). A régua de `_COST_UUID_RE` exige 32-40 caracteres e
    rejeitaria TODOS: o carimbo nasceria morto, em silêncio."""
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    m = re.search(r'_JOB_ID_RE\s*=\s*__import__\("re"\)\.compile\(r"([^"]+)"\)', fonte)
    assert m, "_JOB_ID_RE sumiu de main.py"
    regua = re.compile(m.group(1))
    for bom in ("a1b2c3d4", "ev12ab34", "mg9f8e7d", "0f1e2d3c"):
        assert regua.match(bom), "a régua recusou um job_id real: %r" % bom
    for ruim in ("", "abc", "job com espaço", "x" * 40):
        assert not regua.match(ruim), "a régua aceitou lixo como dono: %r" % ruim

    # e o controle: a régua de CUSTO, se reusada, mataria o carimbo
    m2 = re.search(r'_COST_UUID_RE\s*=\s*__import__\("re"\)\.compile\(r"([^"]+)"\)', fonte)
    assert m2, "_COST_UUID_RE sumiu — o controle deste teste perdeu o alvo"
    assert not re.compile(m2.group(1)).match("a1b2c3d4"), (
        "a régua de custo passou a aceitar job_id de 8 caracteres; o alerta "
        "deste teste perdeu o sentido — reveja qual régua o carimbo usa")


# ─────────────────────────────────────────────────────────────────────────────
#  Token virando real
# ─────────────────────────────────────────────────────────────────────────────

def _com_precos(mapa):
    original = llm_retry._precos
    llm_retry._precos = lambda: mapa
    return lambda: setattr(llm_retry, "_precos", original)


def test_um_milhao_de_tokens_de_entrada_no_haiku_da_um_dolar():
    restaurar = _com_precos({
        "claude-haiku-4-5-20251001": ("claude-haiku-4-5-20251001@2026-01-01",
                                      1.0, 5.0, 0.10, 1.25)})
    try:
        custo, ver = llm_retry._custo_usd("claude-haiku-4-5-20251001",
                                          1_000_000, 0, 0, 0)
    finally:
        restaurar()
    assert custo == 1.0, custo
    assert ver == "claude-haiku-4-5-20251001@2026-01-01"


def test_o_desconto_do_cache_entra_na_conta():
    """Leitura de cache custa 10% do input; escrita custa 125%."""
    restaurar = _com_precos({"m": ("m@2026-01-01", 1.0, 5.0, 0.10, 1.25)})
    try:
        custo, _ = llm_retry._custo_usd("m", 0, 1_000_000, 1_000_000, 0)
    finally:
        restaurar()
    assert custo == 1.35, custo   # 0,10 (leitura) + 1,25 (escrita)


def test_CONTROLE_mudar_o_preco_muda_o_custo():
    """Se o preço estivesse chumbado no código, este teste não veria diferença."""
    r1 = _com_precos({"m": ("m@v1", 1.0, 5.0, 0.1, 1.25)})
    try:
        barato, _ = llm_retry._custo_usd("m", 1_000_000, 0, 0, 0)
    finally:
        r1()
    r2 = _com_precos({"m": ("m@v2", 3.0, 15.0, 0.3, 3.75)})
    try:
        caro, ver = llm_retry._custo_usd("m", 1_000_000, 0, 0, 0)
    finally:
        r2()
    assert (barato, caro) == (1.0, 3.0), (barato, caro)
    assert ver == "m@v2", "o custo não carrega QUAL preço foi aplicado"


def test_modelo_sem_preco_da_custo_DESCONHECIDO_nunca_zero():
    """🚨 Regra dura nº1. O modelo do DXF muda por variável de ambiente SEM
    deploy (main.py:2498): basta um id novo pra etapa mais cara (44% do gasto)
    passar a somar zero em silêncio. NULL é 'não sei'; zero é uma mentira."""
    restaurar = _com_precos({"outro": ("outro@v1", 1.0, 5.0, 0.1, 1.25)})
    try:
        custo, ver = llm_retry._custo_usd("modelo-que-ninguem-cadastrou",
                                          9_999_999, 0, 0, 9_999_999)
    finally:
        restaurar()
    assert custo is None and ver is None, (custo, ver)


def test_a_BANCADA_nao_escreve_na_conta_de_custo_de_producao():
    """🩸 06/09/2026 — descoberto durante esta própria sessão.

    `test_cache_telemetria.py` chama `_registrar_uso` com resposta falsa. Assim
    que ele passou a gravar de verdade, cada rodada da suíte inseria linha de
    mentira em `llm_uso` — a tabela que o Pedro vai usar pra decidir preço. Só
    apareceu porque a sequence da tabela pulou pra 13 sem ninguém ter subido
    nada. Custo inventado é pior que custo ausente: tem cara de fato.
    """
    chamou = []
    import main as _main
    orig = _main._supabase_insert
    _main._supabase_insert = lambda t, d: chamou.append((t, d))
    try:
        # roda EXATAMENTE como a suíte roda (PYTEST_CURRENT_TEST está setada)
        llm_retry._gravar_uso(tag="sinapi_pick", resultado="api",
                              modelo="claude-haiku-4-5-20251001",
                              job_id="aaa111", novo=1, le=0, esc=0, out=1)
    finally:
        _main._supabase_insert = orig
    assert chamou == [], (
        "a bancada gravou em llm_uso: %r — a suíte estaria inventando custo na "
        "conta de produção a cada rodada" % (chamou,))


def test_CONTROLE_sem_a_trava_de_pytest_a_gravacao_ACONTECERIA(monkeypatch):
    """O guarda acima só vale se souber acusar. Aqui tiro a trava e a gravação
    tem que voltar a acontecer — provando que é a trava que segura, e não um
    caminho quebrado que não gravaria de qualquer jeito."""
    chamou = []
    import main as _main
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(_main, "_supabase_insert", lambda t, d: chamou.append(t))
    monkeypatch.setattr(llm_retry, "_precos", lambda: {})
    llm_retry._gravar_uso(tag="sinapi_pick", resultado="api", modelo="m",
                          job_id="aaa111", novo=1, le=0, esc=0, out=1)
    assert chamou == ["llm_uso"], (
        "sem a trava a gravação NÃO aconteceu — o teste de cima está passando "
        "por um motivo errado")
