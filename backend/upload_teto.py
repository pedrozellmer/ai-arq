# -*- coding: utf-8 -*-
"""Teto de corpo que age ENQUANTO os bytes chegam, não depois.

🚨 08/09/2026, auditoria de segurança (44 agentes, com céticos). O que a
medição mostrou, e quase tudo corrige o que eu achava:

1. 🩸 **A trava de 450 MB roda TARDE DEMAIS.** Ela está no CORPO da rota, e o
   FastAPI parseia o formulário ANTES de a função rodar (`routing.py:406`,
   `body = await request.form()`). Quando a linha do `413` executa, o multipart
   inteiro **já foi lido do socket**. O 413 não evita o consumo que ele existe
   pra evitar.

2. 🩸 **E ela FALHA ABERTA sem `Content-Length`.** A condição começa com
   `if _clen and ...`, então some inteira quando o header não vem. Não é caso
   exótico: o Starlette **nunca lê `Content-Length` de request** — `chunked` é
   o caminho normal, não um desvio. 📏 Medido contra a produção com um corpo
   minúsculo: `Transfer-Encoding: chunked` sem `Content-Length` → **200 OK**.

3. 🪤 **O estrago barato é RAM, não disco** — e era o contrário do que eu
   procurava. O Starlette derrama cada parte num
   `SpooledTemporaryFile(max_size=1MB)`: arquivo **abaixo** de 1 MB **nunca vai
   pro disco**, fica na memória. Com o default `max_files=1000`, uma requisição
   de 1000 partes de ~1 MB prende **~1 GB de RAM** — e cada arquivo passa
   folgado pelo teto de 150 MB por arquivo, que só olha o tamanho de cada um.
   Com 4 GB e `--workers 1`, poucas simultâneas dão OOM pra TODOS os clientes:
   o mesmo modo de falha do incidente de 21/07.

4. 🪤 **O Cloudflare não cobre estas rotas, de propósito.** `aiarq-utils.js:41`
   manda `/api/process`, `/api/project/{id}/add-file` e `/api/estimate-price`
   DIRETO pro Render, fora do proxy, porque o CF Free corta em 100 MB e matava
   projeto grande. Então não há teto de borda pra contar com.

🔑 UM ÚNICO LEVE FECHA OS DOIS CAMINHOS: contar os bytes do corpo enquanto eles
chegam. Não importa se vieram como 1 arquivo de 900 MB (disco) ou 1000 de 1 MB
(RAM) — o total é o mesmo, e é ele que a máquina paga.

🔒 As três rotas de upload com o teto grande (450 MB) e, desde 27/09/2026
(auditoria SI), QUALQUER outro formulário com arquivo com o teto de 60 MB — ver
`TETO_FORMULARIO`. Corpo que não é formulário (JSON das telas) segue sem contar:
contar toda requisição pagaria por nada e aumentaria o raio de um defeito meu.
"""
import os

#: 450 MB — o MESMO número que as rotas já documentam e que o frontend promete.
#: 🔑 Não é um teto novo: é o teto que já existia passando a valer de verdade.
#: Nenhum upload legítimo muda de comportamento.
TETO_PADRAO = int(os.environ.get("AIARQ_TETO_CORPO_MB", "450")) * 1024 * 1024

#: As três rotas que recebem arquivo. Sufixo, não igualdade: o `add-file` tem
#: `{job_id}` no meio.
CAMINHOS_DE_UPLOAD = ("/api/process", "/add-file", "/api/estimate-price")


#: 60 MB — o teto de QUALQUER outro formulário com arquivo (auditoria SI, 27/09/2026).
#: 🩸 O teto acima cobria só as três rotas grandes, mas o FastAPI lê o formulário
#: inteiro ANTES de a rota conferir o login — o mesmo mecanismo do item 1 lá em
#: cima valia pras outras 8 rotas que recebem arquivo (cotações, planilha revisada,
#: cliente, cashback, calibração, lote do financeiro, fotos do Escritório): qualquer
#: um, sem conta, prendia memória nelas. A maior legítima é o envio de fotos do
#: Escritório, que a própria rota limita a 40 MB; 60 MB dá folga sem abrir a porta.
#: 🔑 Pelo TIPO do corpo, não por lista: rota nova que receba arquivo já nasce coberta.
TETO_FORMULARIO = int(os.environ.get("AIARQ_TETO_FORMULARIO_MB", "60")) * 1024 * 1024


def vigiado(metodo, caminho):
    """Esta requisição entra na contagem?

    🔑 Decisão isolada de propósito, pra bancada CHAMAR — e não reimplementar.
    Hoje eu já escrevi um "controle" que refazia a régua em vez de chamá-la, e
    2 mutantes escaparam por isso.
    """
    if (metodo or "").upper() != "POST":
        return False
    c = caminho or ""
    return any(c.endswith(sufixo) for sufixo in CAMINHOS_DE_UPLOAD)


def formulario_com_arquivo(metodo, content_type):
    """Corpo `multipart/form-data` num método que carrega corpo? (é o que o parser lê antes da rota)"""
    if (metodo or "").upper() not in ("POST", "PUT", "PATCH"):
        return False
    return str(content_type or "").strip().lower().startswith("multipart/form-data")


def content_type_do_scope(scope):
    for chave, valor in scope.get("headers") or []:
        if chave.lower() == b"content-type":
            return valor.decode("latin-1")
    return ""


class Contador:
    """Soma os pedaços e diz quando estourou. Sem I/O, sem rede, sem ASGI."""

    def __init__(self, teto):
        self.teto = teto
        self.total = 0

    def somar(self, n):
        """Devolve True se ESTE pedaço fez o corpo passar do teto."""
        self.total += max(0, int(n or 0))
        return self.total > self.teto


class TetoDeCorpo:
    """Middleware ASGI puro: conta os bytes do corpo e corta no teto.

    🪤 ASGI puro, e não `@app.middleware("http")`, por um motivo concreto: o
    middleware HTTP recebe a requisição já montada e **não** consegue se meter
    entre o socket e o parser. O que precisa ser envolvido é o `receive` — é
    por ele que o parser puxa cada pedaço.

    🔑 Ao estourar, levanta `HTTPException(413)` de dentro do `receive`. Como
    quem chama o `receive` é o parser, lá no fundo da pilha da rota, a exceção
    sobe pelo `ExceptionMiddleware` do próprio app (que fica DENTRO deste
    middleware) e vira uma resposta 413 normal. O `MultiPartParser` tem
    `_files_to_close_on_error`, então os temporários já abertos são fechados.

    🔒 FALHA ABERTA em defeito MEU: se qualquer coisa inesperada acontecer na
    contagem, a requisição segue. Esta trava existe pra conter abuso, não pra
    decidir se um cliente pode trabalhar — e upload de cliente barrado por bug
    meu é pior que o abuso que ela previne. O estouro do teto, esse sim, fecha.
    """

    def __init__(self, app, teto=None, vigia=None, teto_formulario=None):
        self.app = app
        self.teto = TETO_PADRAO if teto is None else teto
        self.vigia = vigia or vigiado
        self.teto_formulario = TETO_FORMULARIO if teto_formulario is None else teto_formulario

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        try:
            entra = self.vigia(scope.get("method"), scope.get("path"))
        except Exception:
            entra = False          # falha aberta: defeito meu não barra ninguém
        teto, grande = self.teto, True
        if not entra:
            try:
                formulario = formulario_com_arquivo(scope.get("method"), content_type_do_scope(scope))
            except Exception:
                formulario = False     # falha aberta, igual ao vigia
            if not formulario:
                return await self.app(scope, receive, send)
            teto, grande = self.teto_formulario, False

        from fastapi import HTTPException
        contador = Contador(teto)
        teto_mb = teto // (1024 * 1024)

        async def receive_contando():
            msg = await receive()
            try:
                if msg.get("type") == "http.request":
                    estourou = contador.somar(len(msg.get("body") or b""))
                else:
                    estourou = False
            except Exception:
                return msg         # falha aberta
            if estourou:
                if not grande:
                    raise HTTPException(
                        413,
                        "O arquivo passou do tamanho que esta tela aceita (máx. ~%d MB "
                        "no total). Mande um arquivo menor ou em partes." % teto_mb)
                raise HTTPException(
                    413,
                    "Arquivos muito grandes (máx. ~%d MB no total). Envie as "
                    "pranchas do projeto — se for um projeto enorme, mande em "
                    "2 lotes." % teto_mb)
            return msg

        return await self.app(scope, receive_contando, send)
