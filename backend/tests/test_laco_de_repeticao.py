# -*- coding: utf-8 -*-
"""A prancha sumia da planilha e o log dizia que não tinha perdido nada.

🚨 26/08/2026, caso cliente-16 (job 43a799c0, "Harmonia - 9º Pavimentos"). De 4
pranchas, 1 chegou. Duas devolveram ZERO item com `stop=max_tokens`, e a linha
de log era `itens=0 perdidos=0` — ou seja, o motor afirmava não ter perdido
nada enquanto entregava metade do projeto a menos.

O que a IA estava escrevendo (ninguém tinha aberto o texto até hoje):

    RACIOCÍNIO: Passo 1 — Inventário de layers: … [15 mil chars corretos]
    +1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1
    [até esgotar os 32.000 tokens — nunca emite o JSON]

Ela soma bloco a bloco porque o conversor dá um nome por INSTÂNCIA (1.570 nomes
para 1.570 peças), e `temperature=0` — decodificação gulosa — não deixa escapar.

🔑 DOIS SINAIS, porque um só engana:
  1. DENSIDADE. "+1" é UM token de dois caracteres, então a resposta fica com
     ~1,05 caractere por token contra 2,5-3,0 de texto normal.
     Medido nos textos reais: laço 1,03/1,05/1,06/1,08 | normal 2,46/2,47/2,53.
  2. REPETIÇÃO LITERAL no fim do texto, que é onde o laço mora.

🪤 Densidade sozinha não basta (resposta cheia de número também tokeniza denso)
e repetição sozinha também não (lista JSON repete estrutura por natureza).

🪤 E a prancha 04 repetia "+2", não "+1". Um detector que procurasse a string
literal "+1+1+1" perderia metade dos casos reais. Foi a densidade que salvou.

Este guarda NÃO testa se o laço foi consertado — testa se ele fica VISÍVEL.
O defeito viveu desde 24/08 porque era invisível.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from engine_rules import detectar_laco_repeticao   # noqa: E402


def _resposta_com_laco(padrao="+1", cabeca=15000, repeticoes=1500):
    """Imita a resposta real: raciocínio válido e depois o laço."""
    return ("RACIOCÍNIO:\nPasso 1 — Inventário de layers:\n"
            + ("- A-WALL: comprimentos — 737.99 m — paredes\n" * (cabeca // 45))
            + padrao * repeticoes)


def _resposta_normal(n=400):
    linhas = []
    for i in range(n):
        linhas.append('{"item_num":"%d","description":"Alvenaria de vedação em '
                      'bloco cerâmico %d×19×19 cm com reboco","unit":"m2",'
                      '"quantity":%.2f,"confidence":"estimado"}' % (i, 9 + i % 5, 12.5 + i))
    return '{"items":[' + ",".join(linhas) + "]}"


def test_pega_o_laco_que_custou_as_pranchas_da_Amanda():
    t = _resposta_com_laco("+1")
    d = detectar_laco_repeticao(t, tokens_saida=32000)
    assert d["laco"] is True, (
        "o laço que custou 2 pranchas da cliente-16 passaria despercebido: %s" % d)
    assert d["repeticoes"] >= 60, d
    assert d["densidade"] <= 1.8, d


def test_pega_padrao_DIFERENTE_de_mais_um():
    """🪤 A prancha 04 dela repetia '+2'. Detector ancorado em '+1' perderia."""
    d = detectar_laco_repeticao(_resposta_com_laco("+2"), tokens_saida=32000)
    assert d["laco"] is True, "só pegou o '+1' — o caso real da prancha 04 escapa"


def test_resposta_NORMAL_nao_e_acusada():
    """Controle negativo. Lista JSON repete estrutura por natureza — se isso
    acusar, o alarme toca em todo job e vira ruído que ninguém lê."""
    t = _resposta_normal()
    d = detectar_laco_repeticao(t, tokens_saida=int(len(t) / 2.6))
    assert d["laco"] is False, (
        "acusou resposta legítima de 400 itens: %s" % d)


def test_resposta_curta_nao_e_avaliada():
    """Texto curto não dá pra julgar — e julgar dá falso positivo."""
    assert detectar_laco_repeticao("+1" * 50, tokens_saida=100)["laco"] is False


def test_densidade_sozinha_NAO_condena():
    """🪤 Resposta densa em número (coordenada, código) sem repetição não é laço."""
    import random
    random.seed(7)
    denso = " ".join("%d.%d" % (random.randint(1000, 9999), random.randint(10, 99))
                     for _ in range(4000))
    d = detectar_laco_repeticao(denso, tokens_saida=int(len(denso) / 1.2))
    assert d["laco"] is False, (
        "texto denso mas SEM repetição foi acusado — exigir os dois sinais é "
        "o que separa: %s" % d)


# ══════════════════════════════════════════════════════════════════════════
#  O CALL SITE, EXECUTADO
#
#  🚨 06/09/2026 — POR QUE MUDOU. O guarda antigo conferia que
#  `_detectar_laco(text`, a string `"motor:laco-repeticao"` e a ORDEM entre as
#  duas existiam no fonte de `main.py`. Provado cego: trocando
#  `if _laco.get("laco"):` por `if False:` — com o `_log_error` ainda escrito
#  logo abaixo, morto — o guarda passava 7/7 e o laço voltava a ser INVISÍVEL,
#  que é o único propósito declarado deste arquivo.
#
#  🪤 `process_job` tem ~3.900 linhas e não roda em bancada. Então usa-se o
#  padrão da casa (mesmo de `test_aviso_planob_conta_medidos_no_fim`): recorta
#  o TRECHO REAL do arquivo por âncora e o EXECUTA. Não é leitura de string —
#  é o código do call site rodando, com a dependência de verdade
#  (`_detectar_laco` do main) no namespace.
#  🚫 Sem recorte por tamanho fixo: o fim do trecho é achado pela estrutura
#  (os dois try/except), não por `src[i:i+900]`.
# ══════════════════════════════════════════════════════════════════════════
_ANCORA = '_out_tok = int(getattr(getattr(response, "usage", None),'


def _fatia_do_call_site():
    """O trecho REAL de main.py que detecta o laço e o registra."""
    import io as _io
    import textwrap
    src = _io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert src.count(_ANCORA) == 1, (
        "a âncora do call site do laço mudou (%d ocorrências) — o recorte "
        "sairia errado" % (src.count(_ANCORA),))
    i = src.index(_ANCORA)
    ini = src.rfind(chr(10), 0, src.rfind(chr(10), 0, i)) + 1
    assert src[ini:src.index(chr(10), ini)].strip() == "try:", (
        "o call site não começa mais num `try:` — recorte precisa ser refeito")
    base = len(src[ini:]) - len(src[ini:].lstrip(" "))
    saida, excepts = [], 0
    for l in src[ini:].splitlines(True):
        if not l.strip():
            saida.append(l)
            continue
        ind = len(l) - len(l.lstrip(" "))
        cab = l.strip().split()[0].rstrip(":")
        if ind <= base:
            if excepts >= 2:
                break
            if cab not in ("try", "except", "else", "finally"):
                break
        saida.append(l)
        if ind == base and cab == "except":
            excepts += 1
    return textwrap.dedent("".join(saida))


class _Uso:
    def __init__(self, n):
        self.output_tokens = n


class _Resposta:
    def __init__(self, tokens, stop="max_tokens"):
        self.usage = _Uso(tokens)
        self.stop_reason = stop


def _rodar_o_call_site(texto, tokens, itens=0):
    """Executa o trecho real e devolve as linhas de log que ele escreveu."""
    import main as _m
    logs = []
    ns = {
        "os": os,
        "text": texto,
        "response": _Resposta(tokens),
        "result": {"items": [{}] * itens},
        "dxf_path": "/tmp/PRANCHA-04.dxf",
        "job_id": "job-laco-01",
        "_n_item_perdido": 0,
        "_dxf_truncado": False,
        "_n_resgate_proc": 0,
        # 🪤 A dependência REAL entra de verdade. Se faltasse, o `except` do
        # próprio trecho engoliria o NameError e `_laco` viraria
        # {"laco": False} — verde falso pelo pior caminho possível, que é o
        # jeito exato como este guarda estava mentindo antes.
        "_detectar_laco": _m._detectar_laco,
        "_log_error": lambda stage, msg, job=None, **k: logs.append((stage, msg)),
    }
    exec(compile(_fatia_do_call_site(), "main_laco_slice", "exec"), ns)
    return logs


def test_a_ROTA_registra_o_laco_no_log():
    """O laço tem que virar LINHA DE LOG quando acontece — é o único propósito
    deste arquivo. Aqui o call site de `main.py` é executado de verdade."""
    logs = _rodar_o_call_site(_resposta_com_laco("+1"), tokens=32000, itens=0)
    stages = [s for s, _ in logs]

    assert "motor:prancha-itens" in stages, (
        "a ficha da prancha não saiu — o trecho não chegou a executar, e o "
        "resto deste guarda não prova nada. Logs: %r" % (stages,))
    assert "motor:laco-repeticao" in stages, (
        "a IA queimou 32.000 tokens em laço e NÃO saiu linha de log — a "
        "prancha some da planilha em silêncio, que é o defeito que viveu "
        "desde 24/08. Logs: %r" % (stages,))

    msg = next(m for s, m in logs if s == "motor:laco-repeticao")
    assert "'+1'" in msg, (
        "a linha de log não diz QUAL padrão a IA repetiu — sem isso não dá "
        "pra reconhecer o caso: %r" % (msg,))
    assert "PRANCHA-04" in msg, (
        "a linha não diz de qual prancha se trata: %r" % (msg,))


def test_a_ROTA_nao_acusa_laco_em_prancha_boa():
    """🧪 CONTROLE POSITIVO do guarda de cima. Se o call site registrasse
    SEMPRE, o teste anterior passaria com o `if` arrancado — e o alarme viraria
    ruído em todo job, que ninguém lê."""
    boa = _resposta_normal(400)
    logs = _rodar_o_call_site(boa, tokens=int(len(boa) / 2.6), itens=400)
    stages = [s for s, _ in logs]
    assert "motor:prancha-itens" in stages, (
        "nem a ficha saiu — o trecho não executou: %r" % (stages,))
    assert "motor:laco-repeticao" not in stages, (
        "acusou laço numa prancha que entregou 400 itens — alarme em todo job "
        "é ruído que ninguém lê")


def test_o_call_site_recortado_e_o_do_main_de_verdade():
    """🪤 Guarda do guarda: se o recorte pegar o pedaço errado (ou vazio), os
    dois testes acima passariam sem nunca ter tocado no código de produção."""
    fatia = _fatia_do_call_site()
    assert "_detectar_laco(text, _out_tok)" in fatia, (
        "o recorte não contém a CHAMADA do detector — está medindo outra coisa")
    assert '"motor:laco-repeticao"' in fatia, (
        "o recorte não contém o registro do laço")
    # 🚫 Nada de afirmar sobre a DECISÃO por string: é justamente isso que
    # deixava o guarda cego. Quem prova a decisão são os dois testes de cima,
    # que executam o trecho com e sem laço.
    compile(fatia, "main_laco_slice", "exec")


# ── e o trecho tem que estar num caminho VIVO ────────────────────────────────
#
# 🚨 06/09/2026, 2ª volta. Executar o trecho recortado prova que ELE funciona —
# não prova que o `process_job` chega nele. Tornar o bloco MORTO (embrulhar o
# `try:` num `if False:`, ou pôr um `continue` antes dele) não mexe na âncora,
# não muda uma vírgula do que o recorte executa, e o laço volta a ser
# INVISÍVEL — que é o único propósito declarado deste arquivo — com os dois
# testes de cima verdes.
#
# 🚫 Isto não substitui a execução, soma a ela: a execução prova o COMPORTAMENTO
#    do trecho, esta parte prova que o trecho é ALCANÇÁVEL.

def _no_falso_de_verdade(no):
    """A condição é comprovadamente falsa em tempo de compilação?"""
    import ast
    if isinstance(no, ast.Constant):
        return not bool(no.value)
    if isinstance(no, ast.BoolOp) and isinstance(no.op, ast.And):
        return any(_no_falso_de_verdade(v) for v in no.values)
    if isinstance(no, ast.BoolOp) and isinstance(no.op, ast.Or):
        return all(_no_falso_de_verdade(v) for v in no.values)
    if isinstance(no, ast.UnaryOp) and isinstance(no.op, ast.Not):
        return _no_verdade_de_verdade(no.operand)
    if isinstance(no, (ast.List, ast.Tuple, ast.Set)) and not no.elts:
        return True
    if isinstance(no, ast.Dict) and not no.keys:
        return True
    return False


def _no_verdade_de_verdade(no):
    """A condição é comprovadamente verdadeira em tempo de compilação?"""
    import ast
    if isinstance(no, ast.Constant):
        return bool(no.value)
    if isinstance(no, ast.BoolOp) and isinstance(no.op, ast.And):
        return all(_no_verdade_de_verdade(v) for v in no.values)
    if isinstance(no, ast.BoolOp) and isinstance(no.op, ast.Or):
        return any(_no_verdade_de_verdade(v) for v in no.values)
    if isinstance(no, ast.UnaryOp) and isinstance(no.op, ast.Not):
        return _no_falso_de_verdade(no.operand)
    if isinstance(no, (ast.List, ast.Tuple, ast.Set)) and no.elts:
        return True
    return False


def _arvore_do_process_job():
    import ast
    import io as _io
    src = _io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    fn = [n for n in ast.walk(ast.parse(src))
          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
          and n.name == "process_job"]
    assert len(fn) == 1, "process_job sumiu ou virou duas definições"
    pais = {}
    for n in ast.walk(fn[0]):
        for f in ast.iter_child_nodes(n):
            pais[f] = n
    return fn[0], pais


def _cadeia(no, pais, ate):
    """Do nó até a função, de dentro pra fora."""
    saida = []
    while no is not ate:
        saida.append(no)
        no = pais[no]
    return saida


def _suite_de(no, pais):
    """(lista de statements, índice) da suíte que contém `no`."""
    import ast
    p = pais[no]
    for _campo, valor in ast.iter_fields(p):
        if isinstance(valor, list) and any(x is no for x in valor):
            return valor, [i for i, x in enumerate(valor) if x is no][0]
    raise AssertionError("nó fora de qualquer suíte")


def test_o_registro_do_laco_esta_num_caminho_VIVO_do_process_job():
    """🩸 A LACUNA QUE ISTO FECHA: bloco MORTO passava verde.

    Prova três coisas sobre o caminho até o `_log_error("motor:laco-repeticao")`:

      1. ele é IRMÃO (mesma suíte, e DEPOIS) da chamada de IA que produziu a
         resposta — não mora num ramo paralelo nem num helper esquecido;
      2. nenhum `if`/`while` entre a suíte comum e ele é falso em tempo de
         compilação (`if False:`, `if ... and False:`, `while 0:`);
      3. nenhum `return`/`raise`/`continue`/`break` INCONDICIONAL vem antes
         dele nas suítes desse caminho.
    """
    import ast
    fn, pais = _arvore_do_process_job()

    log = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
           and isinstance(n.func, ast.Name) and n.func.id == "_log_error"
           and n.args and isinstance(n.args[0], ast.Constant)
           and n.args[0].value == "motor:laco-repeticao"]
    assert len(log) == 1, (
        "esperava UM registro de `motor:laco-repeticao` no process_job, achei "
        "%d — se ele sumiu, o laço voltou a ser invisível" % len(log))

    ia = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
          and isinstance(n.func, ast.Name) and n.func.id == "_llm_retry"]
    assert len(ia) == 1, (
        "esperava UMA chamada de IA (`_llm_retry`) no process_job, achei %d — "
        "o guarda de alcance precisa saber de qual resposta o laço veio" % len(ia))

    c_log = _cadeia(log[0], pais, fn)
    c_ia = _cadeia(ia[0], pais, fn)

    # 1) a suíte comum mais funda: o ancestral-statement do log que é IRMÃO do
    #    ancestral-statement da chamada de IA
    suites_ia = {}
    for n in c_ia:
        if isinstance(n, ast.stmt):
            lista, idx = _suite_de(n, pais)
            suites_ia.setdefault(id(lista), (lista, idx))
    irmao_log = irmao_ia = None
    for n in c_log:
        if not isinstance(n, ast.stmt):
            continue
        lista, idx = _suite_de(n, pais)
        if id(lista) in suites_ia:
            irmao_log, irmao_ia = (n, idx), suites_ia[id(lista)]
            break
    assert irmao_log is not None, (
        "o registro do laço não compartilha suíte nenhuma com a chamada de IA "
        "— ele saiu do caminho da leitura da prancha")
    assert irmao_log[1] > irmao_ia[1], (
        "o registro do laço passou a vir ANTES da chamada de IA na mesma "
        "suíte (posições %d e %d) — ele nunca veria a resposta"
        % (irmao_log[1], irmao_ia[1]))

    # 2) nenhum ramo morto entre a suíte comum e o registro
    for filho in c_log:
        pai = pais[filho]
        if isinstance(pai, ast.If):
            if any(x is filho for x in pai.body):
                assert not _no_falso_de_verdade(pai.test), (
                    "o registro do laço ficou dentro de um `if` FALSO em "
                    "tempo de compilação (linha %d: `%s`) — o bloco está "
                    "morto e o laço volta a ser invisível, com os testes de "
                    "execução deste arquivo verdes"
                    % (pai.lineno, ast.unparse(pai.test)))
            elif any(x is filho for x in pai.orelse):
                assert not _no_verdade_de_verdade(pai.test), (
                    "o registro do laço ficou no `else` de um `if` sempre "
                    "VERDADEIRO (linha %d) — bloco morto" % pai.lineno)
        if isinstance(pai, ast.While) and any(x is filho for x in pai.body):
            assert not _no_falso_de_verdade(pai.test), (
                "o registro do laço ficou num `while` que nunca roda "
                "(linha %d)" % pai.lineno)
        if isinstance(pai, ast.For) and any(x is filho for x in pai.body):
            assert not _no_falso_de_verdade(pai.iter), (
                "o registro do laço ficou num `for` sobre coleção vazia "
                "(linha %d)" % pai.lineno)

    # 3) nada corta o caminho antes dele
    _cortes = (ast.Return, ast.Raise, ast.Continue, ast.Break)
    for n in c_log:
        if not isinstance(n, ast.stmt):
            continue
        lista, idx = _suite_de(n, pais)
        for anterior in lista[:idx]:
            assert not isinstance(anterior, _cortes), (
                "um `%s` incondicional na linha %d vem antes do registro do "
                "laço na mesma suíte — o bloco virou código morto"
                % (type(anterior).__name__.lower(), anterior.lineno))
        if n is irmao_log[0]:
            break


def test_controle_positivo_o_detector_ANTIGO_nao_via_nada():
    """Prova que o guarda reprova mesmo: antes, o único sinal era o stop_reason,
    e ele não distingue 'cortou no fim' de 'queimou tudo em laço'."""
    from engine_rules import response_truncated
    assert response_truncated("max_tokens") is True
    # ...mas isso vale IGUAL pra uma leitura boa que só encostou no teto:
    # em 24/08 três pranchas deram stop=max_tokens e entregaram 112, 156 e 162
    # itens. Ou seja, o sinal antigo não separava os dois casos.
    boa = _resposta_normal(600)
    assert detectar_laco_repeticao(boa, tokens_saida=int(len(boa) / 2.6))["laco"] is False, (
        "controle positivo furado: o detector novo tem que distinguir "
        "'cortou no teto entregando itens' de 'queimou tudo em laço'")
