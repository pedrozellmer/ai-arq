# -*- coding: utf-8 -*-
"""O log de acesso do uvicorn não guarda dado pessoal que venha na URL.

🩸 25/09/2026. O upload do painel mandava e-mail, nome completo e nome do
projeto do cliente na QUERY STRING do `POST /api/process`, e o chat mandava a
pergunta digitada na query do `/api/agent/ask`. O uvicorn grava a URL inteira
em toda requisição — e o preflight `OPTIONS` grava de novo. Medido no log do
Render (tipo "app"): 18 linhas com e-mail em ~30 h, 8 pessoas diferentes, e um
nome de projeto que era o nome do cliente final.

🔑 O conserto de verdade é a tela não pôr o dado na URL (`dashboard.html`).
Este filtro é a SEGUNDA camada, e existe por dois motivos:
  · a aba que o cliente deixou aberta antes do deploy continua mandando a URL
    velha até ele recarregar a página — o servidor aceita, mas não anota;
  · a próxima rota que escorregar e puser um desses campos na URL também não
    vaza pro log.

🪤 uvicorn 0.30 (h11_impl, o que roda no Render) chama
    access_logger.info('%s - "%s %s HTTP/%s" %d',
                       cliente, método, CAMINHO_COM_QUERY, versão, status)
e o `AccessFormatter` DESEMPACOTA os 5 argumentos. O filtro troca só o 3º e
devolve sempre 5 — mexer no tamanho da tupla quebra a formatação da linha.

🪤 Filtro que levanta exceção sobe até o `logger.info` dentro do protocolo HTTP
e derruba a resposta. Aqui NUNCA levanta: na dúvida, a linha sai como veio.

🪤 Instalado na importação do `main`: o uvicorn configura o log ANTES de
importar o app (`uvicorn main:app`), então o filtro não é apagado depois.
"""
import logging
import re

# Os campos que já vazaram (os quatro primeiros) + `email`, a forma genérica.
# 🪤 Nome de ARQUIVO (`ref=` do /api/sheet, `nome=` do download do admin) fica
# de fora de propósito: é o que se lê pra saber qual prancha falhou, e decidir
# isso é outra conversa.
CHAVES_PESSOAIS = ("user_email", "user_name", "project_name", "question", "email")

_CHAVE_NA_QUERY = re.compile(
    r"([?&])(" + "|".join(CHAVES_PESSOAIS) + r")=[^&#\s]*", re.IGNORECASE)

OMITIDO = "<omitido>"


def mascarar_query(caminho: str) -> str:
    """`/x?a=1&user_email=fulano%40d.com` → `/x?a=1&user_email=<omitido>`.

    Só o VALOR sai; a chave fica, pra quem lê o log saber que a aba velha
    ainda anda por aí."""
    if "?" not in caminho:
        return caminho
    return _CHAVE_NA_QUERY.sub(
        lambda m: "%s%s=%s" % (m.group(1), m.group(2), OMITIDO), caminho)


class SemDadoPessoalNaUrl(logging.Filter):
    """Filtro do logger `uvicorn.access`. Sempre deixa a linha passar."""

    marca_aiarq_sem_dado_pessoal = True

    def filter(self, record):
        try:
            a = record.args
            if isinstance(a, tuple) and len(a) >= 3 and isinstance(a[2], str):
                novo = mascarar_query(a[2])
                if novo != a[2]:
                    record.args = a[:2] + (novo,) + a[3:]
        except Exception:
            pass
        return True


def instalar(nome_do_logger: str = "uvicorn.access") -> logging.Logger:
    """Põe o filtro no logger (uma vez só, mesmo que o módulo seja recarregado)."""
    lg = logging.getLogger(nome_do_logger)
    if not any(getattr(f, "marca_aiarq_sem_dado_pessoal", False) for f in lg.filters):
        lg.addFilter(SemDadoPessoalNaUrl())
    return lg
