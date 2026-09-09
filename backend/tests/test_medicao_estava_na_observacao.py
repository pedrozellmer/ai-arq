# -*- coding: utf-8 -*-
"""A medição estava escrita na linha e a quantidade vinha ZERO.

🚨 26/08/2026, caso **cliente-19** (job de 24/08 21:39, 307 itens). De 73 linhas de
área e comprimento, **31 saíram com quantidade zero** — e várias delas traziam
o número medido escrito na própria observação:

    "Forro de gesso acartonado"    qtd 0   "área hachurada do layer -TEFOR
                                            = 26.54 m² (17 hachuras)"
    "Revestimento de parede"       qtd 0   "área hachurada do layer '-TEPAR'
                                            = 268.39 m² (soma de 8 hachuras)"
    "Execução de parede nova"      qtd 0   "comprimento do layer '-TEPAR'
                                            = 302.14 m"

O motor mediu, a IA citou o layer e o valor, e a coluna de quantidade veio
vazia. 268,39 m² de revestimento e 302,14 m de parede nova são as linhas mais
caras do levantamento dele.

Medido no acervo: **126 de 1.579** linhas zeradas de área/comprimento (8,0%)
carregam um número medido na observação.

🔑 ISTO NÃO CONFIA NO TEXTO — e essa é a diferença que faz a coisa ser segura.
A observação só diz ONDE olhar; quem decide é a extração. O valor citado tem
que bater (±1%) com `get_areas_by_layer()` / `get_walls_by_layer()` do MESMO
layer. Layer inexistente, número que não confere ou unidade trocada → a linha
continua zerada.

🪤 **O CAMINHO FÁCIL JÁ FOI TESTADO E REPROVADO.** Em 25/08, proibir
`quantity=0` no prompt destravou 30 de 31 linhas — com **chute redondo** (50,
80, 40, 25, 45 m²), e só 2 a 5 de 30+ batiam com alguma área da prancha.
"Zero pelo menos não mente." Ver [[project_resolucao_espremida_pdf_20260825]].
O que muda aqui é que o número não é da IA: é NOSSO, e é conferido.

🚫 E não promove nada: quem chama mantém o `confidence` que a IA deu. Preencher
a quantidade e carimbar 'medido' são passos diferentes (regra dura nº1).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine_rules import quantidade_da_procedencia as q  # noqa: E402

# a extração REAL da prancha do cliente-19, do jeito que o motor devolve
AREAS = {"-TEFOR": 26.54, "-TEPAR": 268.39, "-TEDUTO": 12.0}
COMPR = {"-TEPAR": 302.14, "-TEDUTO": 199.08}


def test_o_forro_do_Cliente_12_para_de_sair_zerado():
    obs = "Fonte: área hachurada do layer -TEFOR = 26.54 m² (17 hachuras). Pode ser acaba"
    assert q(obs, "m²", AREAS, COMPR) == 26.54


def test_o_revestimento_com_layer_entre_aspas():
    obs = ("Fonte: área hachurada do layer '-TEPAR' = 268.39 m² (soma de 8 "
           "hachuras). Pode ser acabamento misto.")
    assert q(obs, "m²", AREAS, COMPR) == 268.39, (
        "layer entre aspas não foi reconhecido — é o formato que a IA usa na "
        "maior parte das linhas")


def test_o_comprimento_da_parede_nova():
    obs = "Fonte: comprimento do layer '-TEPAR' = 302.14 m. Inclui paredes novas."
    assert q(obs, "ml", AREAS, COMPR) == 302.14


def test_layer_que_NAO_EXISTE_na_extracao_continua_zerado():
    """🚨 A trava principal. Se o layer não está na extração, o número é da IA."""
    assert q("área hachurada do layer -INVENTADO = 99.90 m²", "m²", AREAS, COMPR) is None


def test_numero_que_NAO_CONFERE_continua_zerado():
    """🚨 A IA cita o layer certo e um valor errado — não entra.

    Sem isto, bastaria a IA escrever o nome de um layer real pra colar qualquer
    número na planilha.
    """
    assert q("área hachurada do layer -TEFOR = 500.00 m²", "m²", AREAS, COMPR) is None
    assert q("área hachurada do layer -TEFOR = 30.00 m²", "m²", AREAS, COMPR) is None


def test_tolerancia_de_1pct_aceita_o_arredondamento_da_IA():
    """26.54 impresso contra 26.5401 medido tem que passar; 10% não."""
    assert q("área hachurada do layer -TEFOR = 26.60 m²", "m²",
             {"-TEFOR": 26.54}, COMPR) == 26.60
    assert q("área hachurada do layer -TEFOR = 29.00 m²", "m²",
             {"-TEFOR": 26.54}, COMPR) is None


def test_unidade_trocada_nao_cola():
    """🪤 Área citada num item de metro linear (e vice-versa) não serve.

    O -TEPAR tem 268,39 m² de hachura E 302,14 m de comprimento. Cruzar os dois
    entregaria m² no lugar de metro.
    """
    obs_area = "área hachurada do layer '-TEPAR' = 268.39 m²"
    obs_comp = "comprimento do layer '-TEPAR' = 302.14 m"
    assert q(obs_area, "ml", AREAS, COMPR) is None, "área virou metro linear"
    assert q(obs_comp, "m²", AREAS, COMPR) is None, "comprimento virou área"
    # e cada um no seu lugar continua funcionando
    assert q(obs_area, "m²", AREAS, COMPR) == 268.39
    assert q(obs_comp, "ml", AREAS, COMPR) == 302.14


def test_layer_com_caixa_diferente_ainda_casa():
    """O nome do layer varia de caixa entre o CAD e o texto da IA."""
    assert q("área hachurada do layer -tefor = 26.54 m²", "m²", AREAS, COMPR) == 26.54


def test_observacao_sem_medicao_devolve_nada():
    """Controle negativo: a maioria dos zeros é HONESTA e tem que continuar zero.

    Dos 1.579 zerados, 92% são assim — "comprimento não extraído", "extração
    geométrica vazia". Transformar esses em número é o erro de 25/08.
    """
    for obs in ("Texto 'AE-10x15' identificado ×6 no layer -tetextos. "
                "Comprimento não extraído da geometria.",
                "Fonte: layer BARRAMENTO identificado no arquivo. Extração "
                "geométrica vazia — verificar em campo.",
                "Item de práxis: administração local de obra.",
                ""):
        assert q(obs, "m²", AREAS, COMPR) is None, (
            "inventou número numa linha honestamente zerada: %r" % obs)


def test_extracao_vazia_nao_quebra_nem_preenche():
    assert q("área hachurada do layer -TEFOR = 26.54 m²", "m²", {}, {}) is None
    assert q("área hachurada do layer -TEFOR = 26.54 m²", "m²", None, None) is None


class _ExtracaoSemRessalva:
    """A prancha do cliente-19 sem ressalva de escala — o caso normal."""
    metadata = {}


def _laco_de_itens_de_producao(items, areas=None, compr=None):
    """Roda o LAÇO INTEIRO `for item_data in result.get("items", [])` de
    `process_job` — código de produção recortado por AST — e devolve
    `(dxf_items, escopo, logs)`.

    🚨 06/09/2026, 2ª rodada. A fatia anterior parava no fim do `if qty == 0:`
    e afirmava sobre a variável solta `qty`. Nada provava que aquele `qty` era o
    que ia parar no `BudgetItem(...)`: qualquer coisa entre os dois (o `qty = 1`
    defensivo do `confirmado`, uma normalização que reescrevesse o número)
    devolvia planilha zerada com o guarda VERDE. Agora o recorte vai até o
    `dxf_items.append(item)` e o que se afirma é `item.quantity` — o número que
    o cliente vê.

    🔑 E roda com MAIS DE UM item: a prancha real do cliente-19 tinha 307
    linhas. Com um item só, `items[:1]` ou um `break` passavam verdes.

    🪤 Os auxiliares (`sf`, `_XCHECK_ON`, os imports) também são recortados do
    `main.py` — nenhum deles é cópia escrita aqui.
    """
    _aqui = os.path.dirname(os.path.abspath(__file__))
    if _aqui not in sys.path:
        sys.path.insert(0, _aqui)
    import _executa
    import main

    logs = []
    escopo = dict(vars(main))          # os colaboradores de módulo, de verdade
    escopo.update({
        "result": {"items": list(items)},
        "extraction": _ExtracaoSemRessalva(),
        "_areas_ly": dict(AREAS if areas is None else areas),
        "_compr_ly": dict(COMPR if compr is None else compr),
        "_n_resgate_proc": 0,
        "_n_item_perdido": 0,
        "dxf_items": [],
        "_dxf_nome": "PRANCHA-01",
        "_dxf_sem_procedencia": False,
        "_hard_area_by_cat": {}, "_hard_len_by_cat": {},
        "_multi_hatch_sums": set(),
        "_log_error": lambda stage, msg, *a, **k: logs.append((stage, msg)),
        "os": os,
        "dxf_path": "/work/j/prancha.dxf",
        "job_id": "job-teste",
    })
    _executa.roda("process_job",
                  "from analyzer import _normalize_br_number as _norm_br", escopo)
    _executa.roda("process_job",
                  "from models import SheetInfo, SheetType, ProjectData, "
                  "BudgetItem, Confidence", escopo)
    _executa.roda("process_job", "def sf(v):", escopo)
    _executa.roda("process_job", "_XCHECK_ON = os.environ.get(", escopo)
    # tamanho=3 é o `for item_data ...` inteiro (0=a chamada, 1=o `if qty == 0:`,
    # 2=o `try:` — que sozinho nem compila, tem `continue` dentro).
    _executa.roda("process_job", "_q_proc = _quantidade_da_procedencia(",
                  escopo, tamanho=3)
    assert escopo["_n_item_perdido"] == 0, (
        "item morreu dentro do laço de produção — o guarda não mediu nada: %s"
        % (logs,))
    return escopo["dxf_items"], escopo, logs


def test_o_call_site_usa_isso_e_NAO_mexe_no_selo():
    """🪤 Guarda de CALL SITE + regra nº1 no mesmo teste.

    A função pode estar perfeita e nunca ser chamada; e se ela mexesse no
    `confidence`, viraria promoção por texto — que é exatamente o que a regra
    nº1 proíbe.

    🚨 06/09/2026 — ESTE GUARDA ERA CEGO. Ele lia uma janela de 420 caracteres
    do fonte em volta da chamada. Provado por mutação: `if _q_proc:` virando
    `if False and _q_proc:` — a chamada continua acontecendo, o resultado é
    jogado fora e a quantidade fica ZERO — e ele passou VERDE. Ou seja: passava
    com o defeito de 26/08 reaberto, exatamente o que ele existe pra impedir.

    🔑 Agora ele EXECUTA o laço de itens inteiro de `process_job` e afirma sobre
    o `BudgetItem` que SAI — três linhas de uma vez: a de m², a de metro linear
    e uma honestamente zerada.
    """
    itens, escopo, _ = _laco_de_itens_de_producao([
        {"item_num": "1", "description": "Revestimento de parede",
         "unit": "m²", "quantity": 0, "confidence": "estimado",
         "observations": ("Fonte: área hachurada do layer '-TEPAR' = 268.39 "
                          "m² (soma de 8 hachuras). Pode ser acabamento misto.")},
        {"item_num": "2", "description": "Execução de parede nova",
         "unit": "ml", "quantity": 0, "confidence": "estimado",
         "observations": "Fonte: comprimento do layer '-TEPAR' = 302.14 m."},
        {"item_num": "3", "description": "Pintura látex sobre reboco",
         "unit": "m²", "quantity": 0, "confidence": "estimado",
         "observations": "Extração geométrica vazia — verificar em campo."},
    ])

    assert len(itens) == 3, (
        "o laço de produção perdeu linha pelo caminho (%d de 3) — na prancha "
        "real do cliente-19 eram 307" % len(itens))
    saida = [(i.description, i.unit, i.quantity, i.confidence.value)
             for i in itens]
    assert saida == [
        ("Revestimento de parede", "m²", 268.39, "estimado"),
        ("Execução de parede nova", "ml", 302.14, "estimado"),
        ("Pintura látex sobre reboco", "m²", 0.0, "estimado"),
    ], (
        "as linhas mais caras do cliente-19 voltaram a sair ZERADAS com a "
        "medição escrita nelas mesmas — ou o resgate não roda, ou o número não "
        "chega no BudgetItem que vira planilha: %s" % (saida,))
    assert escopo["_n_resgate_proc"] == 2, (
        "o contador do resgate diz %r e foram 2 linhas resgatadas — sem o "
        "contador certo o conserto é invisível no log"
        % escopo["_n_resgate_proc"])
    # regra dura nº1: preencher quantidade ≠ carimbar 'medido'
    assert [i.confidence.value for i in itens] == ["estimado"] * 3, (
        "o resgate promoveu o selo — preencher quantidade e carimbar 'medido' "
        "são passos diferentes (regra dura nº1): %s"
        % [i.confidence.value for i in itens])


def test_o_call_site_NAO_inventa_quando_a_extracao_nao_confirma():
    """🧪 Controle positivo do mesmo laço: com o layer inventado E com o número
    que não confere, o código real tem que deixar as duas linhas zeradas. Sem
    isto, o teste acima passaria com um `qty = 268.39` fixo no lugar do
    resgate."""
    itens, escopo, _ = _laco_de_itens_de_producao([
        {"item_num": "1", "description": "Revestimento de parede",
         "unit": "m²", "quantity": 0, "confidence": "estimado",
         "observations": "área hachurada do layer -INVENTADO = 99.90 m²"},
        {"item_num": "2", "description": "Forro de gesso acartonado",
         "unit": "m²", "quantity": 0, "confidence": "estimado",
         "observations": "área hachurada do layer -TEFOR = 500.00 m²"},
    ])
    assert [(i.description, i.quantity) for i in itens] == [
        ("Revestimento de parede", 0.0),
        ("Forro de gesso acartonado", 0.0),
    ], (
        "colou um número da IA numa linha honestamente zerada — é o "
        "experimento REPROVADO de 25/08 voltando pela porta dos fundos: %s"
        % [(i.description, i.quantity) for i in itens])
    assert escopo["_n_resgate_proc"] == 0, escopo["_n_resgate_proc"]


def test_o_resgate_VIRA_linha_de_log():
    """Conserto invisível é o defeito que custou o dia de 26/08 três vezes.

    Executa o `_log_error` de verdade do fim do laço da prancha e lê a mensagem
    que sai — não o texto dela no fonte.
    """
    _aqui = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _aqui)
    import _executa

    linhas = []

    class _Resp:
        stop_reason = "end_turn"

    escopo = {
        "_log_error": lambda stage, msg, *a, **k: linhas.append((stage, msg)),
        "os": os,
        "dxf_path": "/work/j/4366-EL-E.dxf",
        "result": {"items": [1, 2, 3]},
        "_n_item_perdido": 0,
        "response": _Resp(),
        "_dxf_truncado": False,
        "_n_resgate_proc": 31,          # os 31 zeros do cliente-19
        "text": "x" * 100,
        "job_id": "job-teste",
    }
    _executa.roda("process_job", "resgate_procedencia={_n_resgate_proc}", escopo)
    assert linhas, "o log da prancha não saiu"
    stage, msg = linhas[0]
    assert stage == "motor:prancha-itens", stage
    assert "resgate_procedencia=31" in msg, (
        "o resgate não aparece no log da prancha — ninguém consegue medir se "
        "ele está acontecendo: %s" % msg)
