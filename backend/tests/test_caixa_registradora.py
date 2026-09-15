# -*- coding: utf-8 -*-
"""A caixa registradora: processar é livre, o ENTREGÁVEL é que se paga.

🚨 06/09/2026 — desenho escolhido pelo Pedro depois da auditoria de prontidão:
PROCESSA PRIMEIRO, COBRA PRA BAIXAR. O cliente sobe, a gente processa, ele vê o
Raio-X ("medimos 34 de 51 linhas") e paga pra baixar. Se a régua reprovou
(nenhuma linha medida do CAD), o download sai de graça.

Por que esta ordem venceu: o cliente vê ANTES de pagar, então o reembolso quase
não existe — e a régua de cobrança vira automática, sem estorno. De quebra, o
preço passa a ser contado pelo servidor DEPOIS do processamento, quando já se
sabe quantas pranchas existem. Hoje `num_pranchas` chega por parâmetro de URL e
ninguém reconta (main.py:19760 e 19787): dá pra pagar R$97 num projeto de R$447.

O que este arquivo guarda:
  (1) a trava NASCE DESLIGADA — o beta segue grátis até o Pedro ligar;
  (2) TODA rota que entrega arquivo do cliente passa pela caixa;
  (3) a régua manda: entrega que não mediu nada não se cobra, logo não se tranca;
  (4) a trava falha ABERTA — nunca tranca o arquivo de quem pagou.
"""
import io
import os
import re
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402
from _corpo import so_o_que_roda  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
#  (1) Nasce desligada
# ─────────────────────────────────────────────────────────────────────────────

def test_a_cobranca_nasce_DESLIGADA(monkeypatch):
    """🚨 O beta é promessa pública ("grátis e ilimitado") e integra o contrato
    pelo art. 30 do CDC. Enquanto o Pedro não ligar, nada muda pro cliente."""
    monkeypatch.delenv("COBRANCA_LIGADA", raising=False)
    assert main._cobranca_ligada() is False
    liberado, motivo = main._entregavel_liberado("qualquer")
    assert liberado is True and motivo == "cobranca_desligada"


def test_o_interruptor_mora_no_SERVIDOR_nao_no_JavaScript():
    """🪤 O paywall de hoje é `const BETA_FREE = true` (dashboard.html:3517) —
    JavaScript servido estático pelo GitHub Pages, editável no navegador de
    quem quiser. A trava nova tem que ser variável de AMBIENTE."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("def _cobranca_ligada(")
    corpo = src[i:src.index("\ndef ", i + 10)]
    assert "os.getenv" in corpo and "COBRANCA_LIGADA" in corpo, corpo
    assert '"0"' in corpo, "o default deixou de ser DESLIGADO"


def test_ligada_e_sem_pagar_a_porta_fecha(monkeypatch):
    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, [{"pagamento": None, "cobravel": True}]))
    liberado, motivo = main._entregavel_liberado("aaa111")
    assert liberado is False and motivo == "aguardando_pagamento"


def test_pago_abre_todos_os_entregaveis(monkeypatch):
    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, [{"pagamento": "pago", "cobravel": True}]))
    liberado, _ = main._entregavel_liberado("aaa111")
    assert liberado is True


# ─────────────────────────────────────────────────────────────────────────────
#  (2) A régua manda
# ─────────────────────────────────────────────────────────────────────────────

def test_entrega_que_NAO_MEDIU_sai_de_graca(monkeypatch):
    """🔑 O elo entre a régua e a caixa. Não cobramos por entrega vazia — então
    também não a trancamos. É o que torna o reembolso desnecessário no caso
    comum: 44% das entregas desde 01/08 saíram sem uma linha medida."""
    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, [{"pagamento": None, "cobravel": False}]))
    liberado, motivo = main._entregavel_liberado("aaa111")
    assert liberado is True and motivo == "regua_reprovou"


def test_cobravel_NULL_nao_e_permissao(monkeypatch):
    """🚨 `cobravel` tem TRÊS estados. NULL quer dizer "não avaliado" — não é
    autorização pra nada. Só o false EXPLÍCITO libera; senão, um carimbo que
    falhou (a gravação é best-effort) viraria download grátis em silêncio."""
    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, [{"pagamento": None, "cobravel": None}]))
    liberado, motivo = main._entregavel_liberado("aaa111")
    assert liberado is False, (
        "cobravel NULL liberou o download — 'não avaliado' virou permissão")
    assert motivo == "aguardando_pagamento"


# ─────────────────────────────────────────────────────────────────────────────
#  (3) Falha ABERTA
# ─────────────────────────────────────────────────────────────────────────────

def test_banco_ilegivel_LIBERA_em_vez_de_trancar(monkeypatch):
    """🚨 Decisão consciente: trancar o arquivo de quem PAGOU por causa de um
    soluço de rede é pior, e mais caro em confiança, do que deixar escapar um
    download num minuto ruim. Mesma escolha da lista de supressão de e-mail."""
    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (500, None))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    liberado, motivo = main._entregavel_liberado("aaa111")
    assert liberado is True and motivo == "leitura_falhou"


def test_excecao_na_leitura_tambem_LIBERA(monkeypatch):
    monkeypatch.setenv("COBRANCA_LIGADA", "1")

    def _explode(*a, **k):
        raise RuntimeError("rede caiu")
    monkeypatch.setattr(main, "_supa_rest_service", _explode)
    # 🪤 14/09: desde que este caminho passou a AVISAR, o teste que não
    # silencia `_log_error` manda uma linha pro error_log de PRODUÇÃO a cada
    # execução da bancada. Hoje não vaza só porque a máquina de teste não tem
    # credencial do Supabase e a gravação falha calada — sorte, não desenho.
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    liberado, motivo = main._entregavel_liberado("aaa111")
    assert liberado is True and motivo == "excecao"


def test_a_falha_aberta_AVISA_em_vez_de_passar_batido(monkeypatch):
    """Falhar aberto é a escolha certa, mas silenciosa seria a errada: sem
    aviso, a cobrança poderia estar liberando tudo por semanas."""
    avisos = []
    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (500, None))
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, *a, **k: avisos.append(stage))
    main._entregavel_liberado("aaa111")
    assert "cobranca:leitura" in avisos, avisos


# ─────────────────────────────────────────────────────────────────────────────
#  (4) COBERTURA — o guarda mais importante deste arquivo
# ─────────────────────────────────────────────────────────────────────────────

# Rotas que devolvem arquivo mas NÃO são entregável do cliente. Lista DECLARADA,
# com motivo: exceção implícita é porta aberta que ninguém lembra de fechar.
_NAO_SAO_ENTREGAVEL = {
    "_cronograma_preview_png_impl": "PNG de PREVIEW da própria tela — é o que faz "
                                    "o cliente querer o cronograma; trancar seria "
                                    "esconder a vitrine",
}


# 🩸 14/09/2026 — a trava passou a ter DOIS invólucros (o síncrono e o
# `_async`, que roda a mesma decisão fora do laço de eventos). O guarda de
# cobertura procurava o literal `_require_entregavel_pago(` e, com o `_async`,
# `pago` passa a ser seguido de `_` em vez de `(`: as 8 rotas async teriam
# saído da varredura CALADAS — o guarda continuaria verde acusando ninguém.
# Ancorar no FATO ("passa pela caixa"), não na forma de uma das chamadas.
_CHAMA_A_CAIXA = re.compile(r"_require_entregavel_pago(?:_async)?\(")


def _rotas_que_entregam_arquivo(src):
    """(nome_da_funcao, trecho) de toda rota que devolve FileResponse com job_id."""
    achadas = []
    for m in re.finditer(r"^@app\.(?:get|post)\((.*?)\)\s*$", src, re.M):
        cabeca = m.group(1)
        if "{job_id}" not in cabeca:
            continue
        # 🪤 O recorte tem que parar na PRÓXIMA função de topo, não no próximo
        # @app. — senão o corpo engole as funções auxiliares que vêm entre as
        # duas rotas, e um `FileResponse` delas acusa uma rota que devolve JSON.
        # Foi o que aconteceu com `get_cronograma_full`: falso positivo, e
        # guarda que acusa o que não é defeito acaba desligado.
        corpo = src[m.end():]
        mf = re.match(r"\s*(?:async )?def (\w+)\(", corpo)
        if not mf:
            continue
        nome = mf.group(1)
        fim = re.search(r"\n(?:@app\.|(?:async )?def )", corpo[mf.end():])
        corpo = corpo[:mf.end() + fim.start()] if fim else corpo
        if "FileResponse(" not in corpo:
            continue
        achadas.append((nome, corpo))
    return achadas


def test_toda_rota_de_entregavel_passa_pela_caixa():
    """🚨 Porta esquecida é a trava inteira perdida — e o vazamento é
    SILENCIOSO: ninguém reclama de receber de graça. Este guarda é o que
    impede a 11ª rota de nascer aberta."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    rotas = _rotas_que_entregam_arquivo(src)
    assert len(rotas) >= 8, (
        "a varredura achou só %d rotas de entregável — o padrão de busca "
        "parou de enxergar o código" % len(rotas))
    sem_trava = [n for n, corpo in rotas
                 if not _CHAMA_A_CAIXA.search(corpo)
                 and n not in _NAO_SAO_ENTREGAVEL]
    assert not sem_trava, (
        "estas rotas entregam arquivo do cliente sem passar pela caixa "
        "registradora: %s — ou chame _require_entregavel_pago(job_id), ou "
        "declare a exceção em _NAO_SAO_ENTREGAVEL com o motivo" % sem_trava)


def test_CONTROLE_a_varredura_ACHA_uma_rota_sem_trava():
    """O guarda acima só vale se souber acusar. Aqui monto uma rota nova, sem
    trava, e exijo que a peneira a encontre."""
    falso = (
        '@app.get("/api/coisa/{job_id}/export/xlsx")\n'
        'async def exporta_coisa(job_id: str, request: Request):\n'
        '    _require_project_owner(request, job_id)\n'
        '    return FileResponse(caminho, media_type="x")\n'
        '@app.get("/outra")\n')
    achadas = _rotas_que_entregam_arquivo(falso)
    assert [n for n, _ in achadas] == ["exporta_coisa"], achadas
    assert not _CHAMA_A_CAIXA.search(achadas[0][1]), (
        "a peneira parou de distinguir rota travada de rota aberta")


def test_CONTROLE_a_varredura_APROVA_uma_rota_travada():
    """E o outro lado: rota com a trava não pode ser acusada."""
    ok = (
        '@app.get("/api/coisa/{job_id}/export/xlsx")\n'
        'async def exporta_coisa(job_id: str, request: Request):\n'
        '    _require_project_owner(request, job_id)\n'
        '    _require_entregavel_pago(job_id)\n'
        '    return FileResponse(caminho, media_type="x")\n'
        '@app.get("/outra")\n')
    achadas = _rotas_que_entregam_arquivo(ok)
    assert _CHAMA_A_CAIXA.search(achadas[0][1])


def test_CONTROLE_a_peneira_ENXERGA_a_forma_async():
    """🩸 O controle que faltava. Quando a trava ganhou o invólucro `_async`, a
    peneira antiga (`"_require_entregavel_pago(" in corpo`) parava de casar —
    porque em `..._pago_async(` o que vem depois de `pago` é `_`, não `(`. As 8
    rotas async sairiam da cobertura sem uma linha vermelha."""
    ok_async = (
        '@app.get("/api/coisa/{job_id}/export/xlsx")\n'
        'async def exporta_coisa(job_id: str, request: Request):\n'
        '    _require_project_owner(request, job_id)\n'
        '    await _require_entregavel_pago_async(job_id)\n'
        '    return FileResponse(caminho, media_type="x")\n'
        '@app.get("/outra")\n')
    achadas = _rotas_que_entregam_arquivo(ok_async)
    assert _CHAMA_A_CAIXA.search(achadas[0][1]), (
        "a peneira não reconhece a forma async da trava — as rotas async "
        "sairiam da cobertura caladas")


def test_a_trava_vem_DEPOIS_do_guarda_de_dono():
    """🪤 Ordem importa: quem NÃO é dono tem que levar 401/403, não 402. Dizer
    "pague" pra alguém que nem é dono do projeto vaza a existência dele."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    vistas = 0
    for nome, corpo in _rotas_que_entregam_arquivo(src):
        m = _CHAMA_A_CAIXA.search(corpo)
        if not m:
            continue
        vistas += 1
        i_dono = corpo.find("_require_project_owner(")
        assert i_dono >= 0, "%s trava pagamento mas não confere dono" % nome
        assert i_dono < m.start(), (
            "%s pergunta o pagamento ANTES de saber se é o dono" % nome)
    # 🪤 Sem esta linha o guarda vira verde-por-vazio: bastaria a peneira parar
    # de casar a chamada pra ele aprovar zero rota e não dizer nada.
    assert vistas >= 8, (
        "o guarda da ORDEM olhou só %d rotas — a peneira deixou de enxergar "
        "as chamadas da caixa" % vistas)


def test_a_trava_devolve_402_e_nao_403(monkeypatch):
    """402 Payment Required é o código honesto: o problema não é permissão, é
    pagamento. A tela precisa distinguir os dois pra dar a resposta certa."""
    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, [{"pagamento": None, "cobravel": True}]))
    try:
        main._require_entregavel_pago("aaa111")
    except main.HTTPException as e:
        assert e.status_code == 402, e.status_code
        return
    raise AssertionError("a trava não levantou nada com projeto não pago")


# ─────────────────────────────────────────────────────────────────────────────
#  (5) A trava não pode CONGELAR O SERVIDOR — 14/09/2026
# ─────────────────────────────────────────────────────────────────────────────

def test_rota_async_nao_trava_o_laco():
    """🩸 `_entregavel_liberado` lê o Supabase com `urllib` (timeout 15 s).
    Chamada de dentro de um `async def`, essa leitura roda NO LAÇO DE EVENTOS:
    enquanto não volta, o servidor (`--workers 1`) não atende mais ninguém —
    nem quem está baixando, nem quem está subindo arquivo.

    🪤 Hoje isso NÃO acontece, e é justamente o que torna o defeito traiçoeiro:
    `_cobranca_ligada()` devolve False e a função sai na primeira linha, sem
    tocar na rede. O congelamento nasce no INSTANTE em que o Pedro ligar a
    cobrança — com a bancada verde e nenhum aviso.
    """
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    culpadas = []
    for nome, corpo in _rotas_que_entregam_arquivo(src):
        if not corpo.lstrip().startswith("async def"):
            continue
        if not _CHAMA_A_CAIXA.search(corpo):
            continue
        if not re.search(r"await\s+_require_entregavel_pago_async\(", corpo):
            culpadas.append(nome)
    assert not culpadas, (
        "estas rotas são `async` e chamam a trava SÍNCRONA — a leitura do "
        "pagamento vai rodar no laço de eventos e congelar o servidor inteiro "
        "quando a cobrança ligar: %s. Use "
        "`await _require_entregavel_pago_async(job_id)`." % culpadas)


def test_CONTROLE_o_guarda_do_laco_ACUSA_uma_rota_async_sincrona():
    """O guarda acima só vale se souber acusar. Monto a rota errada e exijo
    que a peneira a encontre — inclusive a armadilha do `_async` SEM `await`,
    que devolve uma corrotina nunca esperada: a trava sairia DESLIGADA, e em
    silêncio, que é o pior jeito de uma trava falhar."""
    for corpo_errado, apelido in (
        ('async def x(job_id: str, request: Request):\n'
         '    _require_entregavel_pago(job_id)\n', "forma síncrona"),
        ('async def x(job_id: str, request: Request):\n'
         '    _require_entregavel_pago_async(job_id)\n', "sem await"),
    ):
        assert _CHAMA_A_CAIXA.search(corpo_errado), apelido
        assert not re.search(r"await\s+_require_entregavel_pago_async\(",
                             corpo_errado), (
            "o guarda do laço aprovaria a rota errada (%s)" % apelido)


def test_o_involucro_async_DELEGA_em_vez_de_repetir_a_regra():
    """🔑 Duas cópias da mesma decisão é a receita repetida que já nos custou
    caro: o dia em que uma das duas mudar, a outra fica mentindo. O invólucro
    async não pode ter 402 próprio nem reimplementar os motivos."""
    # 🪤 `so_o_que_roda` tira docstring E comentário. Sem isso o guarda leria a
    # minha própria explicação — que cita "402" e o nome da função síncrona — e
    # aprovaria um invólucro que duplicasse a regra. Terceira vez que caio nisso.
    corpo = so_o_que_roda("_require_entregavel_pago_async")
    assert "run_in_threadpool(_require_entregavel_pago," in corpo, (
        "o invólucro async parou de delegar na trava síncrona: %r" % corpo)
    assert "402" not in corpo, (
        "o invólucro async escreveu um 402 próprio — a decisão tem que "
        "continuar num lugar só: %r" % corpo)
    assert "cobravel" not in corpo and "pagamento" not in corpo, (
        "o invólucro async reimplementou os motivos: %r" % corpo)


# ─────────────────────────────────────────────────────────────────────────────
#  (6) A trava deixa RASTRO — 14/09/2026
# ─────────────────────────────────────────────────────────────────────────────

def test_a_trava_que_FECHA_deixa_rastro(monkeypatch):
    """🩸 O motivo era calculado na linha de cima e jogado fora. No dia em que
    a chave virar, "quantas pessoas bateram na trava?" não teria onde ser
    respondida — nem no banco, nem no log do Render."""
    rastro = []
    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, [{"pagamento": None, "cobravel": True}]))
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, *a, **k: rastro.append((stage, msg)))
    try:
        main._require_entregavel_pago("aaa111")
    except main.HTTPException:
        pass
    assert [s for s, _ in rastro if s == "cobranca:trava"], rastro
    assert any("aguardando_pagamento" in m for _, m in rastro), (
        "o rastro saiu sem o MOTIVO — é o motivo que distingue "
        "'não pagou' de 'a régua reprovou' quando a trava mudar: %s" % rastro)


def test_CONTROLE_a_trava_que_ABRE_nao_polui_o_registro(monkeypatch):
    """O outro lado: quem passa não pode gerar linha. Sem este controle, o
    guarda de cima passaria com um log em TODA chamada — e o registro viraria
    ruído no primeiro dia de cobrança."""
    rastro = []
    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, [{"pagamento": "pago", "cobravel": True}]))
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, *a, **k: rastro.append((stage, msg)))
    main._require_entregavel_pago("aaa111")
    assert not [s for s, _ in rastro if s == "cobranca:trava"], rastro


def test_a_EXCECAO_na_checagem_tambem_avisa(monkeypatch):
    """🩸 A falha aberta por exceção só fazia `print`, que no Render morre no
    stdout e some no restart. A IRMÃ dela — a leitura com status >= 400 — grava
    no error_log desde o primeiro dia. Se o `_supa_rest_service` passar a
    ESTOURAR em vez de devolver >= 400, a cobrança libera tudo, para sempre,
    sem uma linha em lugar nenhum."""
    rastro = []

    def _explode(*a, **k):
        raise RuntimeError("conexao caiu")

    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service", _explode)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, *a, **k: rastro.append((stage, msg)))
    liberado, motivo = main._entregavel_liberado("aaa111")
    assert (liberado, motivo) == (True, "excecao"), (liberado, motivo)
    assert [s for s, _ in rastro if s == "cobranca:excecao"], rastro


def test_a_excecao_NAO_e_rebaixada_a_diagnostico():
    """🪤 `_log_error` rebaixa a `info` todo stage que estiver em
    `_STAGES_DIAGNOSTICO` — foi assim que `cobranca:regua` ocupou 13 das 40
    linhas do painel sem ninguém agir. Falha ABERTA é o contrário: tem que
    aparecer. Já `cobranca:trava` é bookkeeping e PRECISA estar na lista, ou
    entope o painel no primeiro dia de cobrança."""
    assert "cobranca:excecao" not in main._STAGES_DIAGNOSTICO
    assert "cobranca:leitura" not in main._STAGES_DIAGNOSTICO
    assert "cobranca:trava" in main._STAGES_DIAGNOSTICO


def test_o_involucro_async_AINDA_TRANCA(monkeypatch):
    """🚨 O guarda funcional, e o mais importante dos três. Mover a decisão pra
    um thread pode engolir a exceção no caminho — e uma trava que para de
    trancar falha do jeito mais caro que existe: em silêncio, entregando de
    graça, sem ninguém reclamar. Aqui a trava async é EXECUTADA de verdade,
    dentro de um laço de eventos, e tem que levantar o mesmo 402."""
    import asyncio
    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, [{"pagamento": None, "cobravel": True}]))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    try:
        asyncio.run(main._require_entregavel_pago_async("aaa111"))
    except main.HTTPException as e:
        assert e.status_code == 402, e.status_code
        return
    raise AssertionError(
        "a trava async NÃO levantou 402 — o invólucro está entregando de graça")


def test_o_involucro_async_LIBERA_quem_pagou(monkeypatch):
    """CONTROLE do de cima: o guarda só vale se a trava também souber ABRIR.
    Senão 'sempre levanta 402' passaria — e ninguém baixaria nada."""
    import asyncio
    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, [{"pagamento": "pago", "cobravel": True}]))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    asyncio.run(main._require_entregavel_pago_async("aaa111"))
