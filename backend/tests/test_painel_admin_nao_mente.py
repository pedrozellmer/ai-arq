# -*- coding: utf-8 -*-
"""O painel do admin parou de responder uma pergunta e mostrar outra.

🎯 02/09/2026, sete queixas do Pedro de uma vez: *"acho que tem coisa sem nexo,
eu vejo erros 2h x clientes em 7 dias e 13 incompletos (nao fala do prazo)"*,
*"a taxa de sucesso em 30 dias podia ter isso em media movel ne? ver a evolução
do sistema de fato, sem erros em projetos"*, *"operação agora tem projetos hoje e
erros em 24 hs, nao faz muito sentido"*, *"na pagina de projetos nao consigo
abrir da mesma forma que abro indo na pagina do cliente"*.

🔑 O fio que liga TODAS elas: nenhum número estava errado de conta. Cada um
respondia uma pergunta diferente da que o rótulo prometia — e dois números que
respondem perguntas diferentes, encostados um no outro, convidam a uma
comparação que não existe. É a mesma família do "arquivo correto não é tela
correta": o dado estava certo no banco e mentia na tela.

📌 MEDIDO antes de mexer (02/09, banco de produção):
  · `cadastros`: a coluna NUNCA era gravada pelo tick. O painel somava 7 dias e
    mostrava 5; tinham entrado 14 pessoas. Os 3 dias automáticos eram NULL e o
    JS fazia `Number(null) || 0`.
  · `site_ok`: 11 de 11 dias NULL, e o farol dizia "sim" em VERDE todo dia
    porque o teste era `=== false` e NULL não é false. Zero medição atrás.
  · "Taxa de Sucesso 93%": dos 57 concluídos de 30 dias, **26 não têm um único
    item medido do CAD**. A taxa contava os 26 como sucesso.
  · aba Projetos: o job_id era texto puro; só a linha de TESTE tinha link.
"""
import io
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)

import main as _m           # noqa: E402
import metricas_site as ms  # noqa: E402

_MAIN = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
_MS = io.open(os.path.join(_BACKEND, "metricas_site.py"), encoding="utf-8").read()


def _admin_html():
    return io.open(os.path.join(_RAIZ, "admin.html"), encoding="utf-8").read()


# ─────────── 1) a coluna `cadastros` volta a ser gravada ────────────────────

def test_o_tick_GRAVA_cadastros_e_nao_so_projetos():
    """🚨 O painel mostrava 5 cadastros numa semana em que entraram 14. A coluna
    existia, a tela lia, e NINGUÉM escrevia — o backfill de 29/08 preencheu 8
    dias à mão, o tick assumiu depois e essa coluna ficou pra trás."""
    i = _MAIN.find('@app.post("/api/metricas/tick")')
    assert i > 0, "sumiu o tick"
    fim = _MAIN.find("\n@app.", i + 10)
    bloco = _MAIN[i:fim if fim > 0 else len(_MAIN)]
    assert '"cadastros"' in bloco, (
        "o tick voltou a nao gravar `cadastros` - a coluna fica NULL e a tela "
        "soma zero no lugar das pessoas que entraram")
    assert '_contar_do_dia("profiles"' in bloco, (
        "a contagem de cadastro saiu do lugar; sem ela a coluna volta a ficar vazia")


def test_contar_do_dia_ACEITA_profiles_e_nao_manda_is_eval_nela():
    """🪤 `profiles` não tem a coluna `is_eval`. Mandar o filtro devolveria 400
    do PostgREST e a contagem viraria None todo dia — a coluna continuaria vazia
    com outra desculpa, que é o modo mais caro de "consertar"."""
    i = _MAIN.find("def _contar_do_dia")
    fim = _MAIN.find("\ndef ", i + 10)
    corpo = _MAIN[i:fim if fim > 0 else i + 2000]
    assert '"profiles"' in corpo, "voltou a recusar tudo que nao seja `projects`"
    assert 'if o_que == "projects":' in corpo, (
        "o `is_eval` voltou a ser mandado pra qualquer tabela - em `profiles` "
        "isso e 400 e a contagem vira None calada")


def test_CONTROLE_falha_de_rede_continua_virando_NULO_e_nao_zero():
    """🧪 Controle positivo do conserto acima: o caminho novo não pode ter
    trazido de volta o zero-por-falha. Zero é a afirmação "não entrou
    ninguém"; falha de rede não pode virar afirmação."""
    def _explode(*a, **k):
        raise RuntimeError("rede caiu")
    _orig = _m._supa_rest_service
    try:
        _m._supa_rest_service = _explode
        assert _m._contar_do_dia("profiles", date(2026, 9, 1)) is None
        assert _m._contar_do_dia("projects", date(2026, 9, 1)) is None
    finally:
        _m._supa_rest_service = _orig


# ─────────── 2) o farol "site no ar" passa a medir alguma coisa ─────────────

def test_o_coletor_MEDE_o_site_no_ar_em_vez_de_deixar_nulo():
    """🚨 `site_ok` era LIDA pelo painel e escrita por ninguém: 11 de 11 dias
    NULL. E o teste na tela era `=== false`, então NULL virava "sim" em verde.
    Farol verde sem medição atrás é pior que farol nenhum — é a primeira coisa
    que o Pedro olha."""
    i = _MS.find("def coletar")
    fim = _MS.find("\ndef ", i + 10)
    corpo = _MS[i:fim if fim > 0 else len(_MS)]
    assert '"site_ok": site_ok' in corpo, (
        "o coletor voltou a nao devolver site_ok - a coluna fica NULL e o farol "
        "volta a dizer 'sim' sem ter medido nada")
    assert "edgeResponseStatus_geq: 500" in corpo, (
        "sumiu a pergunta de erro 5xx; sem ela `site_ok` seria um chute")


def test_a_medida_do_site_e_uma_consulta_PROPRIA_e_nao_o_topo_de_400():
    """🪤 A consulta principal tem `limit: 400` ordenado por contagem. Um 5xx
    raro ficaria FORA do topo e o dia passaria por "site ok" — teto não serve
    de prova de ausência. Por isso a pergunta de erro é uma consulta separada."""
    i = _MS.find("def coletar")
    corpo = _MS[i:_MS.find("\ndef ", i + 10)]
    assert corpo.count("_graphql(") >= 3, (
        "a medicao de 5xx voltou a depender da consulta com limite - 5xx fora "
        "do top 400 viraria 'site ok'")


def test_CONTROLE_se_a_pergunta_do_5xx_falhar_o_farol_fica_SEM_RESPOSTA():
    """🧪 O outro lado. "Não consegui medir" é uma resposta; "está tudo bem"
    não é. Se a consulta explodir, site_ok tem que ficar None — nunca True."""
    i = _MS.find("site_ok = None")
    assert i > 0, "o padrao do site_ok deixou de ser 'nao sei'"
    corpo = _MS[i:i + 900]
    assert "except Exception:" in corpo and "pass" in corpo, (
        "a falha da consulta de 5xx deixou de virar None - vai virar 'site ok'")
    assert "site_ok = (erros_5xx == 0)" in corpo, (
        "o veredito do farol saiu do lugar")


# ─────────── 3) o aviso de coleta olha a DATA, não a configuração ───────────

def test_o_aviso_acende_quando_a_serie_PAROU_mesmo_com_o_token_no_lugar():
    """🚨 O único critério era "a variável CLOUDFLARE_API_TOKEN existe". A
    coleta ficou 3 dias e 7 horas sem gravar nada e o painel manteve a cara
    normal, porque o token estava lá o tempo todo. Guarda que confere a
    CONFIGURAÇÃO e não o RESULTADO não é guarda.

    🩸 02/09/2026, CI VERMELHO: este teste montava a série com `date.today()`,
    que é UTC no runner, e comparava com a função, que conta em BRASÍLIA desde
    o conserto da manhã. Entre 21h e meia-noite de Brasília o UTC já virou o
    dia seguinte, e os 5 dias viravam 4 (`assert 4 == 5`). Passava sempre aqui
    (fuso local = Brasília) e falhava lá só numa janela de 3 horas por dia.
    🔑 O teste tem que usar o MESMO relógio da função que ele mede — ver
    [[feedback_tz_nao_move_date_today_no_windows]]."""
    hoje = _m._hoje_br()
    parada = [{"dia": str(hoje - timedelta(days=5))}]
    r = _m._saude_da_coleta(parada, True)
    assert r["aviso"], "serie parada ha 5 dias e o painel nao avisa nada"
    assert "PAROU" in r["aviso"]
    assert r["atraso_dias"] == 5


def test_CONTROLE_o_fuso_so_se_prova_FALSIFICANDO_o_relogio():
    """🧪 Rodar isto na minha máquina não prova nada: o fuso local É Brasília,
    então o certo e o errado dão o mesmo número — foi por isso que o CI ficou
    vermelho e a bancada local, verde.

    Reproduz o instante exato do incidente: 02/09/2026 20h56 em Brasília, que é
    23h56 UTC — o runner já virou o dia 03, Brasília ainda está no dia 02.
    O segundo `assert` é o controle: ele exige que o jeito ERRADO continue
    dando 4. Se um dia parar de dar, este teste deixou de provar fuso.
    """
    import datetime as _dt
    br = _dt.datetime(2026, 9, 2, 20, 56)      # relógio de Brasília
    utc_hoje = _dt.date(2026, 9, 3)            # o que `date.today()` daria no CI
    _orig = _m._agora_br_fn
    try:
        _m._agora_br_fn = lambda: br
        certo = _m._saude_da_coleta(
            [{"dia": str(br.date() - _dt.timedelta(days=5))}], True)
        assert certo["atraso_dias"] == 5, (
            "a função parou de contar o atraso pelo relógio de Brasília")
        errado = _m._saude_da_coleta(
            [{"dia": str(utc_hoje - _dt.timedelta(days=5))}], True)
        assert errado["atraso_dias"] == 4, (
            "o controle deixou de reproduzir o erro do CI — sem ele este "
            "arquivo volta a passar verde com o fuso trocado")
    finally:
        _m._agora_br_fn = _orig


def test_CONTROLE_serie_em_dia_NAO_acende_alarme_falso():
    """🧪 O outro lado, e ele é essencial: o tick grava sempre `today - 1`, então
    a série estar UM dia atrás é o estado SAUDÁVEL. Um alarme que acende todo
    dia é um alarme que o Pedro aprende a ignorar — e aí o dia que importa passa
    batido.

    🪤 Mesmo relógio da função (Brasília), não `date.today()` — ver o teste
    acima: o descompasso de fuso reprovava o CI só entre 21h e meia-noite."""
    hoje = _m._hoje_br()
    for atras in (0, 1):
        r = _m._saude_da_coleta([{"dia": str(hoje - timedelta(days=atras))}], True)
        assert r["aviso"] is None, (
            "alarme falso com a serie %d dia(s) atras, que e o normal" % atras)


def test_sem_token_o_aviso_continua_falando_do_token():
    """🪤 Três estados, não dois: desligada, atrasada e ok. Trocar um pelo outro
    mandaria o Pedro conferir o agendamento quando o problema é a variável."""
    r = _m._saude_da_coleta([{"dia": str(_m._hoje_br())}], False)
    assert "CLOUDFLARE_API_TOKEN" in (r["aviso"] or "")


# ─────────── 4) a frase para de chamar de "hoje" um dia que é ontem ─────────

def test_a_frase_do_topo_diz_a_DATA_e_nunca_hoje():
    """🚨 O tick grava sempre `today - 1/2/3` (o Cloudflare fecha o dia depois),
    então o dia mais novo da série NUNCA é o de hoje. Em 21 das 24 horas a frase
    estava falando de ontem chamando de hoje — e num buraco de coleta chamaria
    de "hoje" um número de três dias atrás."""
    base = [{"dia": "2026-08-01", "ips_gente": 60},
            {"dia": "2026-08-08", "ips_gente": 72},
            {"dia": "2026-08-15", "ips_gente": 55}]
    for n in (12, 61, 200):
        f = ms.veredito(base + [{"dia": "2026-08-22", "ips_gente": n}])["frase"]
        assert "hoje tem" not in f, "a frase voltou a chamar ontem de hoje: %r" % f
        assert "22/08" in f, "a frase nao diz de que dia esta falando: %r" % f


def test_CONTROLE_a_frase_continua_saindo_em_portugues_correto():
    """🧪 Mexer no texto já custou três frases tortas ("acima DA MAIS CHEIO").
    O controle de concordância continua valendo depois do conserto."""
    sab = [{"dia": d, "ips_gente": n} for d, n in
           [("2026-08-01", 60), ("2026-08-08", 72), ("2026-08-15", 55)]]
    for n in (12, 62, 99):
        f = ms.veredito(sab + [{"dia": "2026-08-29", "ips_gente": n}])["frase"]
        for torto in ("a menor sábado", "acima d mais", "da mais cheio",
                      "do mais cheia", "a mais fraco", "o mais fraca", "d mais"):
            assert torto not in f, "frase torta: %r em %r" % (torto, f)


# ─────────── 5) as queixas de janela e de navegação, na tela ────────────────

def test_operacao_agora_NAO_encosta_hoje_em_24h():
    """🚨 Queixa literal: "operação agora tem projetos hoje e erros em 24 hs,
    nao faz muito sentido". Dois números lado a lado que medem períodos
    diferentes convidam a uma comparação que não existe."""
    h = _admin_html()
    i = h.find("Opera&#231;&#227;o agora")
    assert i > 0, "sumiu o cartao de operacao"
    bloco = h[i:i + 2000]
    assert "Erros (24h)" not in bloco, (
        "o cartao voltou a encostar erro de 24h em concluido de hoje")
    assert "Projetos com erro hoje" in bloco and "Conclu&#237;dos hoje" in bloco, (
        "os dois contadores de movimento sairam da mesma janela")
    assert "errHoje" in h, "sumiu a contagem de erro do dia"


def test_todo_numero_do_quadro_de_clientes_DIZ_a_janela():
    """🚨 "13 incompletos (nao fala do prazo)". Encostado num número de 7 dias,
    parecia fila da semana — é o acumulado desde que o site existe."""
    h = _admin_html()
    i = h.find("Cadastros incompletos (desde o")
    assert i > 0, (
        "o numero de incompletos voltou a aparecer sem janela nenhuma, "
        "encostado num de 7 dias")
    assert "maisVelhoIncompleto" in h, "sumiu a idade do mais antigo"


def test_a_aba_projetos_ABRE_o_projeto_igual_a_pagina_do_cliente():
    """🚨 "na pagina de projetos nao consigo abrir da mesma forma que abro indo
    na pagina do cliente". Era o único lugar do painel onde o job_id era texto
    puro — só a linha de TESTE tinha link."""
    h = _admin_html()
    i = h.find("font-mono text-xs\">' + (jid ?")
    assert i > 0, (
        "a celula do job_id na aba Projetos voltou a ser texto puro - nao da "
        "pra abrir o projeto de la")
    assert "projeto.html?adm=1&job_id=" in h[i:i + 400], (
        "o link perdeu o adm=1 e a barra de voltar pro admin nao aparece la dentro")


def test_a_evolucao_da_entrega_usa_a_RPC_que_JA_existia():
    """🔑 O dado que ele pediu já estava pronto e escondido na aba Motor. Fazer
    conta nova criaria uma QUARTA definição de sucesso no mesmo painel."""
    h = _admin_html()
    assert "desenharEvolucaoDaEntrega" in h, "sumiu a evolucao"
    i = h.find("async function desenharEvolucaoDaEntrega")
    corpo = h[i:i + 3000]
    assert "/api/admin/qualidade-semanal" in corpo, (
        "a evolucao parou de usar a RPC existente - numero novo, definicao nova")
    # 🪤 A 1ª versão deste guarda só procurava `w.mediu` em qualquer lugar do
    # corpo — e passou verde numa sabotagem que trocou a CONTA da barra por
    # `(fin - erro) / fin`, deixando `w.mediu` intacto lá no texto do hover.
    # Guarda que confere presença de palavra não confere comportamento: o que
    # importa é de onde sai a ALTURA da barra.
    assert "const pct = fin ? Math.round((w.mediu || 0) / fin * 100) : 0;" in corpo, (
        "a altura da barra parou de sair de `mediu` - voltou a desenhar "
        "'o job terminou' com outro nome")


def test_CONTROLE_a_evolucao_NAO_desenha_meia_serie_quando_a_leitura_falha():
    """🧪 Meia evolução é pior que nenhuma: ele leria a barra que faltou como
    queda de verdade."""
    h = _admin_html()
    i = h.find("async function desenharEvolucaoDaEntrega")
    corpo = h[i:i + 3000]
    assert "catch" in corpo and "box.innerHTML = ''" in corpo, (
        "falha de leitura voltou a poder desenhar serie incompleta")


# ─────────── 6) na TELA, "não medi" para de ter cara de zero e de verde ─────

def test_o_farol_do_site_NAO_diz_sim_quando_nunca_mediu():
    """🚨 O farol dizia "sim" em VERDE todo dia desde que nasceu, com 11 de 11
    dias sem medição. O teste era `=== false`, e NULL não é false. Três estados,
    não dois: medido-ok, medido-caiu e não-medi."""
    h = _admin_html()
    i = h.find("const saude = document.getElementById('mov-saude')")
    assert i > 0, "sumiu o farol"
    corpo = h[i:i + 1800]
    assert "sem medição" in corpo, (
        "o farol voltou a ter só dois estados - dia sem medicao vira 'sim' verde")
    assert "x.site_ok === true" in corpo, (
        "voltou a olhar so o `=== false`, e ai NULL passa por 'site no ar'")


def test_a_soma_de_7_dias_NAO_trata_dia_sem_medicao_como_zero():
    """🚨 `Number(null) || 0` mostrava "5 cadastros" numa semana de 14 pessoas.
    Zero é a afirmação "não entrou ninguém"; buraco não é zero."""
    h = _admin_html()
    i = h.find("const soma = (k) =>")
    assert i > 0, "sumiu a soma dos 7 dias"
    corpo = h[i:i + 1200]
    assert "faltam" in corpo, (
        "a soma voltou a engolir dia sem medicao como zero - o numero na tela "
        "fica MENOR que a verdade e nada avisa")
    assert "x[k] !== null" in corpo, "voltou a somar NULL como zero"


# ─────────── 7) o numero na tela para de ser o LIMITE da consulta ───────────

def test_a_aba_projetos_diz_o_total_do_BANCO_e_nao_o_limite_da_consulta():
    """🚨 MEDIDO em 02/09: 288 projetos no banco e a tela dizia "200 de 200
    total". O rótulo dizia "total" e mostrava o teto da consulta. Mesma doença
    do teto de mil linhas do PostgREST — o corte chega como resposta normal."""
    h = _admin_html()
    i = h.find("async function loadProjects")
    assert i > 0, "sumiu loadProjects"
    corpo = h[i:i + 3000]
    # 🪤 A 1ª versão deste guarda procurava só `count: 'exact'` — e passou VERDE
    # com a consulta sabotada, porque essa expressão também aparece no
    # COMENTÁRIO logo acima dela. Guarda que casa palavra solta lê comentário
    # como código; o que prova é a CHAMADA inteira.
    assert ".select('*', { count: 'exact' })" in corpo, (
        "a consulta parou de pedir o total real ao banco - o rotulo 'total' "
        "volta a mostrar o limite da consulta")
    assert "totalNoBanco" in h, "sumiu o total de verdade"
    assert "allProjects.length} total" not in h, (
        "o rotulo voltou a chamar o tamanho da pagina de 'total'")


def test_a_tela_AVISA_quando_a_lista_nao_alcanca_tudo():
    """🪤 Saber o total não basta: se a lista mostra 200 de 288, quem olha
    precisa saber que está vendo um pedaço. Silêncio aqui é o mesmo erro com
    outra roupa."""
    h = _admin_html()
    assert "_naoCoube" in h, "sumiu a conta do que nao coube"
    assert "mais recentes" in h, (
        "a tela voltou a mostrar um pedaco da lista sem dizer que e um pedaco")


def test_os_KPIs_de_30_dias_pedem_pela_JANELA_e_nao_por_um_teto():
    """🚨 Era `.limit(300)` com 288 no banco — 12 projetos pra estourar calado.
    Aumentar o teto só adia; o conserto é pedir pela janela que os cartões
    usam."""
    h = _admin_html()
    i = h.find("const _colunas =")
    assert i > 0, "sumiu a busca dos projetos do dashboard"
    corpo = h[i:i + 2500]
    assert ".gte('created_at', _desde30)" in corpo, (
        "os KPIs voltaram a depender de um teto de linhas em vez da janela de "
        "30 dias - quando passar do teto o numero encolhe calado")
    assert ".in('status', ['queued', 'processing'])" in corpo, (
        "sumiu a busca dos ativos de qualquer data - job travado ha 40 dias "
        "sumiria de 'Em curso', que e justo o que precisa de acao")
    assert ".gte('completed_at'" in corpo, (
        "sumiu a busca dos concluidos hoje de qualquer data - reprocesso de "
        "projeto velho some do movimento do dia")


def test_CONTROLE_o_mesmo_projeto_nao_conta_DUAS_vezes():
    """🧪 O outro lado do conserto acima: três consultas que se sobrepõem. Um
    job ativo criado esta semana vem em duas delas. Sem deduplicar, o conserto
    de um número errado criaria outro número errado."""
    h = _admin_html()
    i = h.find("const _vistos = new Set();")
    assert i > 0, (
        "sumiu a deduplicacao - o mesmo projeto passa a contar em dobro em "
        "'Em curso'")
    corpo = h[i:i + 500]
    assert "_vistos.has(_k)" in corpo and "continue" in corpo, (
        "a deduplicacao parou de descartar repetido")


# ─────────── 8) o guarda que teria pego o erro que a bancada deixou passar ──

def test_a_contagem_pede_uma_coluna_que_EXISTE_em_cada_tabela():
    """🩸 02/09/2026 — O CONSERTO DO `cadastros` NASCEU MORTO E A BANCADA PASSOU
    VERDE. Escrevi `select=id` pra `profiles`, e essa tabela não tem coluna
    `id`: a chave é `user_id`. O PostgREST devolve 400, o `st == 200` falha, a
    contagem vira None — e a coluna continuaria vazia, com outra desculpa.

    🔑 Por que os outros testes não pegaram: eles leem o FONTE, e o fonte não
    sabe que coluna existe no banco. Só apareceu porque rodei o tick em
    produção e OLHEI O BANCO depois.

    🧪 Este aqui não lê texto: ele INTERCEPTA a chamada e confere o que foi
    pedido de verdade. Colunas conferidas no information_schema em 02/09.
    """
    reais = {"profiles": {"user_id", "full_name", "email", "created_at"},
             "projects": {"job_id", "status", "created_at", "is_eval"}}
    pedidos = {}

    def _espiao(metodo, tabela, params=None, **k):
        pedidos[tabela] = params or {}
        return 200, []

    _orig = _m._supa_rest_service
    try:
        _m._supa_rest_service = _espiao
        for tabela in ("profiles", "projects"):
            _m._contar_do_dia(tabela, date(2026, 9, 1))
            col = (pedidos[tabela].get("select") or "").split(",")[0].strip()
            assert col in reais[tabela], (
                "a contagem pede a coluna %r em `%s`, que NAO existe la - o "
                "PostgREST devolve 400 e a contagem vira None calada" % (col, tabela))
        # 🪤 `profiles` não tem `is_eval`; mandar o filtro é 400 na certa.
        assert "is_eval" not in pedidos["profiles"], (
            "voltou a mandar is_eval pra `profiles`, que nao tem essa coluna")
        assert "is_eval" in pedidos["projects"], (
            "parou de tirar as avaliacoes da contagem de projetos de cliente")
    finally:
        _m._supa_rest_service = _orig


# ─────────── 9) o bloco "Falhas recentes" para de mostrar o LIMITE da RPC ──

def test_a_idade_da_falha_e_CALCULADA_da_data_e_nao_chutada():
    """🚨 MEDIDO 02/09: a falha mais antiga em tela era de 20/07 (43 dias) e o
    botão Avisar não sabia. A RPC não mandava created_at. Este guarda CHAMA a
    normalização com relógio fixo e confere o número."""
    from datetime import datetime, timezone
    agora = datetime(2026, 9, 2, 9, 29, tzinfo=timezone.utc)
    d = _m._ops_normalizar({"recent_failures": [
        {"created_at": "2026-07-06T04:40:24.328101+00:00"},
        {"created_at": "2026-09-02T08:00:00+00:00"},
        {"created_at": None},
    ]}, agora=agora)
    f = d["recent_failures"]
    assert f[0]["idade_dias"] == 58, "falha de 06/07 tem que dar 58 dias em 02/09"
    assert f[1]["idade_dias"] == 0
    # 🪤 sem data NÃO é zero: zero é "hoje", e isso liberaria o Avisar sem aviso.
    assert f[2]["idade_dias"] is None


def test_contagem_que_NAO_veio_vira_NULO_e_nunca_o_tamanho_da_lista():
    """🚨 O bug era exatamente `.length` no lugar do total. Se a RPC do banco
    ainda for a versão velha, o campo tem que vir None e a tela diz que não
    veio — nunca 25."""
    d = _m._ops_normalizar({"recent_failures": [{}] * 25, "motor_errors": [{}] * 40})
    assert d["contagens_faltando"] is True
    assert d["contagens"]["recent_failures_total"] is None
    assert d["contagens"]["motor_errors_total"] is None
    # e quando VEM, passa inteiro
    d2 = _m._ops_normalizar({"contagens": {"recent_failures_total": 39, "motor_errors_total": "x"}})
    assert d2["contagens"]["recent_failures_total"] == 39
    assert d2["contagens"]["motor_errors_total"] is None
    assert d2["janela"]["recent_failures_dias"] == 60


def test_o_endpoint_de_operacao_PASSA_pela_normalizacao(monkeypatch):
    """🧪 Intercepta a chamada à RPC e confere que o que sai do endpoint tem
    `contagens`, `janela` e `idade_dias` — prova que a função é USADA, não só
    existe."""
    import io as _io
    import json as _j
    import urllib.request as _ur

    class _Resp(_io.BytesIO):
        pass

    def _falso(req, timeout=0):
        return _Resp(_j.dumps({"recent_failures": [{"created_at": "2026-07-06T04:40:24+00:00", "user_email": "a@b.c"}],
                               "motor_errors": [], "motor_diag": [], "pdf_only": []}).encode("utf-8"))
    monkeypatch.setattr(_ur, "urlopen", _falso)
    monkeypatch.setattr(_m, "_require_admin", lambda r: None)
    out = _m.admin_ops_panel(request=None)
    assert "contagens" in out and "janela" in out
    assert isinstance(out["recent_failures"][0]["idade_dias"], int)
    assert out["recent_failures"][0]["idade_dias"] >= 58


def test_a_tela_de_falhas_diz_JANELA_e_MOSTRANDO_de_TOTAL():
    """🚨 `(${falhas.length}) — recuperar 1-a-1` mostrava 25 com 39 no banco e
    chamava 60 dias de 'recentes'. Guarda de fonte (não há node aqui): casa a
    CHAMADA inteira, não palavra solta — comentário não passa."""
    h = _admin_html()
    i = h.find("function renderOps")
    assert i > 0
    corpo = h[i:i + 9000]
    assert "(${falhas.length}) — recuperar 1-a-1" not in corpo, (
        "o contador de falhas voltou a ser o tamanho da lista cortada")
    assert "opsDeTotal(falhas.length, cont.recent_failures_total, 'últimos ' + _diasFalhas + ' dias')" in corpo
    assert "opsDeTotal(erros.length, cont.motor_errors_total" in corpo
    assert "opsDeTotal(diag.length, cont.motor_diag_total" in corpo
    assert "opsDeTotal(pdfOnly.length, cont.pdf_only_total" in corpo
    assert "o total não veio do banco" in corpo, (
        "contagem ausente voltou a ter cara de número")


def test_o_botao_avisar_passa_pela_CONFIRMACAO_com_a_idade():
    """🚨 Dava pra avisar hoje um cliente sobre falha de julho. O botão tem que
    chamar opsAvisar, e opsAvisar tem que confirmar dizendo a idade."""
    h = _admin_html()
    i = h.find("function opsAvisar(i){")
    assert i > 0, "sumiu a confirmacao do Avisar"
    corpo = h[i:h.find(chr(10) + "}", i) + 2]
    assert "idade >= OPS_AVISAR_DIAS_CONFIRMA" in corpo
    assert "return confirm(`Essa falha é de ${f.quando || '?'} — há ${idade} dia(s)." in corpo
    assert 'onclick="return opsAvisar(${falhas.indexOf(f)})"' in h, (
        "o link de Avisar deixou de passar pela confirmacao")
    assert "${f.is_eval" in h, "falha de avaliacao interna voltou a ter botao de e-mail"


# ─────────── 9) custo por projeto divide pelos projetos de CLIENTE ──────────

def test_o_custo_por_projeto_divide_por_projeto_de_CLIENTE_e_nao_por_avaliacao():
    """🩸 02/09/2026 — MEDIDO: 98 concluídos em 30 dias, 41 eram avaliação
    NOSSA (is_eval). O divisor contava os 98 e o custo por projeto saía 42%
    mais barato do que é.

    🧪 Este guarda INTERCEPTA a chamada ao Supabase e olha o filtro que foi
    pedido de verdade — não procura palavra no fonte (passaria cego com a
    palavra num comentário, como aconteceu 2x hoje)."""
    chamadas = []

    def _espiao(metodo, tabela, params=None, **k):
        p = dict(params or {})
        chamadas.append((tabela, p))
        if p.get("is_eval") == "not.is.true":
            return 200, [{"job_id": "c1"}, {"job_id": "c2"}, {"job_id": "c3"}]
        if p.get("is_eval") == "is.true":
            return 200, [{"job_id": "e1"}, {"job_id": "e2"}]
        return 200, [{"job_id": "x"}] * 5   # sem filtro: os 5 misturados

    _orig = _m._supa_rest_service
    try:
        _m._supa_rest_service = _espiao
        r = _m._projetos_para_custo_30d()
    finally:
        _m._supa_rest_service = _orig
    assert chamadas and all(t == "projects" for t, _ in chamadas), chamadas
    filtros = {p.get("is_eval") for _, p in chamadas}
    assert "not.is.true" in filtros, (
        "a contagem de cliente voltou a NAO filtrar is_eval - avaliacao nossa "
        "entra no divisor e o custo por projeto sai mais barato do que e")
    assert all(p.get("status") == "eq.done" and str(p.get("created_at", "")).startswith("gte.")
               for _, p in chamadas), chamadas
    assert r["cliente"] == 3, r
    assert r["avaliacoes"] == 2, r


def test_CONTROLE_custo_por_projeto_falha_de_contagem_vira_NULO_e_nao_zero():
    """🧪 Zero é afirmação ("nenhum projeto de cliente"); falha de rede ou HTTP
    500 não pode virar afirmação — a tela mostraria '—' com cara de '0'."""
    def _explode(*a, **k):
        raise RuntimeError("rede caiu")

    def _http500(*a, **k):
        return 500, None

    _orig = _m._supa_rest_service
    try:
        _m._supa_rest_service = _explode
        r = _m._projetos_para_custo_30d()
        assert r["cliente"] is None and r["avaliacoes"] is None, r
        _m._supa_rest_service = _http500
        r = _m._projetos_para_custo_30d()
        assert r["cliente"] is None and r["avaliacoes"] is None, r
    finally:
        _m._supa_rest_service = _orig


def test_a_tela_do_custo_le_o_campo_de_CLIENTE_e_nao_engole_nulo_como_zero():
    """A tela lê `projetos_30d_cliente` (não o nome antigo, que misturava) e
    nulo fica nulo. Guarda de fonte, mas com os comentários `//` ARRANCADOS
    antes de procurar, pra não passar cego com a palavra num comentário."""
    import re as _re
    h = _admin_html()
    i = h.find("async function loadCosts(){")
    assert i > 0, "sumiu loadCosts"
    fim = h.find("\nfunction ", i + 10)
    corpo = _re.sub(r"//[^\n]*", "", h[i:fim])
    assert "d.projetos_30d_cliente" in corpo, (
        "a tela voltou a ler o numero que mistura avaliacao com cliente")
    assert "d.projetos_30d ||" not in corpo and "projetos_30d_cliente || 0" not in corpo, (
        "voltou a fazer `|| 0`: falha de contagem vira 'zero projetos'")
    j = h.find("function renderCostTotals(){")
    assert j > 0, "sumiu renderCostTotals"
    fj = h.find("\nfunction ", j + 10)
    tela = _re.sub(r"//[^\n]*", "", h[j:fj])
    assert "projeto de <b>cliente</b>" in tela and "30 dias" in tela, (
        "o rotulo parou de dizer que o divisor e projeto de CLIENTE nos ultimos 30 dias")
