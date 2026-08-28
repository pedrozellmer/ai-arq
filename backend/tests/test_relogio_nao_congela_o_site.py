# -*- coding: utf-8 -*-
"""As rotinas do relógio congelavam o site inteiro, de hora em hora.

🚨 28/08/2026. O Pedro encaminhou um e-mail de smoke test vermelho que chegou no
e-mail do trabalho dele. O smoke acusava duas coisas, e **as duas eram sintoma**:

    GET /api/instagram/scheduler/list exige admin  (HTTP 502, esperado 401/403)
    GET /api/projects/by-user — lista  (0 projetos)

Fui ao log do Render. O `/health` bate de 5 em 5 segundos, então ele funciona
como um cronômetro do servidor — e mostrou isto:

    14:59:56.917  GET /health 200
                  <<< 10 segundos SEM UMA ÚNICA LINHA >>>
    15:00:06.817  POST /api/emails/auto/tick 200
    15:00:06.917  GET /health 200          ← a fila represada desovando

    15:59:57.833  GET /health 200
                  <<< 33 segundos SEM UMA ÚNICA LINHA >>>
    16:00:30.558  POST /api/emails/auto/tick 200
    16:00:30.701  POST /api/instagram/scheduler/tick 200
    16:00:30.702  GET / 200                ← a requisição do smoke, represada

O buraco começa no instante em que o pg_cron acorda e termina no instante em que
o tick responde. **Não é coincidência de horário: é o tick.**

🔑 A CAUSA. `async def` com corpo inteiramente BLOQUEANTE. Contado no fonte:

    emails_auto_tick    416 linhas   0 await   6 chamadas HTTP síncronas
    newsletter_tick      50 linhas   0 await   2 chamadas HTTP síncronas
    scheduler_tick      229 linhas   0 await   (Graph API + Supabase)

Rota `async` roda NO laço de eventos. Enquanto ela pensa, o servidor não atende
mais ninguém — nem a sonda de vida do próprio Render.

🩸 O ESTRAGO REAL não é o smoke vermelho. É que **todo cliente que abriu o site
na virada da hora pegou o site mudo por até 33 segundos**, e a gente nunca
soube. O alarme de saúde que o Pedro recebeu hoje mais cedo é o mesmo evento.

🔧 O CONSERTO É TIRAR O `async`. Rota `def` comum o FastAPI joga sozinho num
thread separado e o laço fica livre. Zero mudança de lógica.
🪤 Só vale porque o corpo não tem `await` nenhum — `async def` sem `await` é
sempre o pior dos dois mundos: paga o preço do laço e não usa o benefício.

📌 IRMÃO DESTE ARQUIVO: `test_rota_async_nao_bloqueia.py`, do caso Maria
Victoria (27/08), que é a MESMA doença num lugar diferente — lá era a estimativa
de preço travando na mão dela. Aquele guarda vigia funções pesadas nomeadas;
este vigia o formato da rota. Nenhum dos dois pegaria o caso do outro.
"""
import ast
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# As três rotinas que o pg_cron chama sozinho, sem ninguém esperando na tela.
_DO_RELOGIO = [
    ("main.py", "emails_auto_tick"),
    ("main.py", "newsletter_tick"),
    ("instagram_webhook.py", "scheduler_tick"),
]

# 🪤 Chamada que PARA a thread até responder. Se uma dessas aparece num corpo
# sem `await`, aquela rota segura o servidor pelo tempo todo dela.
_BLOQUEANTE = re.compile(
    r"urlopen|requests\.(get|post|put|delete)|_supa_rest|_auth_admin"
    r"|time\.sleep|subprocess|smtplib")

_DECORADORES_DE_ROTA = ("get", "post", "put", "delete", "patch")


def _fonte(arq):
    return io.open(os.path.join(_BACKEND, arq), encoding="utf-8").read()


def _sem_comentarios(txt):
    """🪤 SEXTA vez em dois dias que eu preciso disto. Um teste que lê o
    comentário como se fosse código aprova (ou reprova) pelo motivo errado —
    já sabotei um `keepalive` e o teste passou VERDE lendo a palavra no
    comentário logo acima."""
    return "\n".join(l for l in txt.split("\n") if not l.strip().startswith("#"))


def _corpo_da_funcao(arq, nome):
    """Devolve (assinatura, corpo_sem_comentario). Falha se a função sumiu."""
    linhas = _fonte(arq).split("\n")
    i = None
    for k, l in enumerate(linhas):
        if re.match(r"(async )?def %s\(" % re.escape(nome), l):
            i = k
            break
    assert i is not None, "a função %s sumiu de %s" % (nome, arq)
    j = i + 1
    while j < len(linhas) and (not linhas[j] or linhas[j][0].isspace()):
        j += 1
    return linhas[i], _sem_comentarios("\n".join(linhas[i + 1:j]))


def test_as_rotinas_do_relogio_NAO_sao_async():
    """🚨 O guarda principal. Voltar o `async` devolve o congelamento de hora
    em hora — e ele é invisível: o log fica LIMPO, só some por 30 segundos."""
    culpadas = []
    for arq, nome in _DO_RELOGIO:
        assinatura, _ = _corpo_da_funcao(arq, nome)
        if assinatura.startswith("async def"):
            culpadas.append("%s:%s" % (arq, nome))
    assert not culpadas, (
        "%s voltou(aram) a ser `async def`. Com corpo bloqueante isso congela o "
        "site INTEIRO enquanto a rotina roda — foram 33 segundos mudos em "
        "28/08. Ou tire o `async`, ou ponha o trabalho em "
        "`await run_in_threadpool(...)`." % culpadas)


def test_e_continuam_sem_await_no_corpo():
    """📌 O contrato do conserto. Se um dia alguém precisar de `await` aqui
    dentro, a rota TEM que voltar a ser `async` — e aí o trabalho pesado
    precisa ir pra thread na mão. Este teste força a decisão consciente."""
    for arq, nome in _DO_RELOGIO:
        _, corpo = _corpo_da_funcao(arq, nome)
        achados = re.findall(r"(?<![\w.])await\s+\w+", corpo)
        assert not achados, (
            "%s:%s agora usa %s. Rota `def` comum não pode dar await — ou ela "
            "volta a ser `async def` (e então o trabalho bloqueante vai pra "
            "run_in_threadpool), ou esse await sai." % (arq, nome, achados[:3]))


def test_o_corpo_bloqueante_e_o_MOTIVO_do_conserto():
    """🧪 Prova que o conserto não é cosmético: as três de fato bloqueiam.
    Se um dia o corpo virar todo assíncrono, este teste avisa que o motivo
    mudou e o guarda acima precisa ser repensado."""
    for arq, nome in _DO_RELOGIO:
        _, corpo = _corpo_da_funcao(arq, nome)
        assert _BLOQUEANTE.search(corpo), (
            "%s:%s não tem mais chamada bloqueante — reveja se ainda faz "
            "sentido forçá-la a ser `def`" % (arq, nome))


def _rotas_async_que_bloqueiam(src, nome_arquivo):
    """Toda rota `async def` com chamada bloqueante e ZERO await.

    🪤 O detector precisa ignorar comentário: `main.py` tem parágrafos inteiros
    explicando `await run_in_threadpool` logo acima de rotas que não usam.
    """
    achados = []
    linhas = src.split("\n")
    for no in ast.walk(ast.parse(src)):
        if not isinstance(no, ast.AsyncFunctionDef):
            continue
        if not any(isinstance(d, ast.Call)
                   and getattr(d.func, "attr", "") in _DECORADORES_DE_ROTA
                   for d in no.decorator_list):
            continue
        fim = max(getattr(n, "lineno", no.lineno) for n in ast.walk(no))
        corpo = _sem_comentarios("\n".join(linhas[no.lineno:fim]))
        if re.search(r"(?<![\w.])await\s", corpo):
            continue
        if _BLOQUEANTE.search(corpo):
            achados.append("%s:%s" % (nome_arquivo, no.name))
    return achados


# 📉 TETO DE DÍVIDA, e ele só pode DESCER.
#
# Em 28/08, ao consertar as três do relógio, contei quantas outras rotas têm
# exatamente a mesma doença: `async def` + corpo bloqueante + zero await. Cada
# uma congela o site pelo tempo que ela roda. São curtas (a maioria é de admin),
# então o estrago é de segundos, não de 33 — mas é a MESMA doença.
#
# Não converti todas de uma vez de propósito: 61 rotas num commit é mudança que
# ninguém revisa de verdade. O teto trava o número onde está, então rota nova
# já nasce certa, e o número desce conforme a gente converte em lotes revisados.
#
# 🪤 Teto fixo envelhece quando a coisa medida CRESCE (foi o que aconteceu com o
# PISO do CI, que ficou em 700 enquanto a bancada ia a 837). Aqui é o contrário:
# o número tem que cair, e o teste reclama se ele cair sem alguém baixar o teto.
# 🧪 O número saiu ERRADO na primeira tentativa (escrevi 61) e o próprio teste
# de catraca abaixo me corrigiu: eu já tinha convertido duas do relógio, então
# o certo era 59. Um guarda que se prova na estreia vale mais que um comentário.
#
# 📉 A catraca em ação, no mesmo dia:
#     64  →  antes de tudo (28/08, ao investigar o smoke vermelho)
#     59  →  depois das 3 do relógio (o buraco de 33 s)
#     31  →  depois das 28 que o CLIENTE usa
#      1  →  depois das 30 de `/api/admin/` e `/api/debug/`
#
# 🪤 A ÚLTIMA NÃO PODE SER CONVERTIDA, e o motivo importa:
# `rebuild_planilha_from_review` é chamada com `await` por outra rota. Virar
# `def` quebraria quem chama. Ela fica `async` e o trabalho bloqueante dela é
# que precisaria ir pra `run_in_threadpool` — conserto diferente, commit
# diferente. Teto 1 é o piso honesto, não "quase zero".
#
# 🪤 `instagram_webhook.py` fica em 1 pelo mesmo tipo de motivo: `create_post`
# não é do relógio, é chamada por gente.
_TETO_DE_DIVIDA = {"main.py": 1, "instagram_webhook.py": 1}


def test_a_divida_de_rotas_bloqueantes_nao_cresce():
    """🚨 Rota NOVA com essa doença reprova aqui."""
    for arq, teto in _TETO_DE_DIVIDA.items():
        achados = _rotas_async_que_bloqueiam(_fonte(arq), arq)
        assert len(achados) <= teto, (
            "%s tem %d rotas `async` que bloqueiam o laço (teto: %d). A nova é "
            "provavelmente uma destas: %s. Escreva `def` em vez de `async def` "
            "— o FastAPI põe em thread sozinho."
            % (arq, len(achados), teto, sorted(achados)[-5:]))


def test_quando_a_divida_CAI_o_teto_tem_que_cair_junto():
    """🪤 Sem isto o teto vira letra morta: eu converteria 30 rotas, o teto
    continuaria em 61, e uma regressão de 30 passaria verde. Guarda frouxo é
    pior que guarda nenhum porque dá sensação de cobertura."""
    for arq, teto in _TETO_DE_DIVIDA.items():
        achados = _rotas_async_que_bloqueiam(_fonte(arq), arq)
        assert len(achados) >= teto, (
            "%s tem só %d rotas bloqueantes e o teto ainda diz %d. Você "
            "consertou %d — baixe o teto pra %d neste mesmo commit, senão ele "
            "para de proteger."
            % (arq, len(achados), teto, teto - len(achados), len(achados)))


def test_CONTROLE_POSITIVO_o_detector_pega_e_absolve():
    """🧪 Todo guarda tem que provar que REPROVA. Sem isto eu já deixei passar
    quatro testes inúteis num dia só."""
    ruim = (
        "@app.post('/api/x')\n"
        "async def rota_doente(request):\n"
        "    dados = _supa_rest_tudo('tabela')\n"
        "    return dados\n"
    )
    assert _rotas_async_que_bloqueiam(ruim, "t.py") == ["t.py:rota_doente"], (
        "o detector não pega o padrão que congelou o site")

    # (a) `def` comum: certo, o FastAPI põe em thread
    assert not _rotas_async_que_bloqueiam(
        ruim.replace("async def", "def"), "t.py"), "falso positivo no `def`"

    # (b) async COM await: certo, quem espera é o laço
    assert not _rotas_async_que_bloqueiam(
        "@app.post('/api/x')\n"
        "async def rota_ok(request):\n"
        "    dados = await run_in_threadpool(_supa_rest_tudo, 'tabela')\n"
        "    return dados\n", "t.py"), "falso positivo no run_in_threadpool"

    # (c) 🪤 a palavra só no COMENTÁRIO não pode absolver ninguém
    assert _rotas_async_que_bloqueiam(
        "@app.post('/api/x')\n"
        "async def rota_mentirosa(request):\n"
        "    # aqui deveria ter um await run_in_threadpool, mas nao tem\n"
        "    dados = _supa_rest_tudo('tabela')\n"
        "    return dados\n", "t.py") == ["t.py:rota_mentirosa"], (
        "o detector foi absolvido por um COMENTÁRIO — é exatamente o erro que "
        "eu cometi quatro vezes em 27/08")
