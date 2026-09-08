# -*- coding: utf-8 -*-
"""Gerar PDF sem deixar o SERVIDOR buscar coisa na rede.

🚨 08/09/2026, auditoria de segurança — SSRF a partir de dentro do Render.

O cliente batiza o projeto. Esse texto entra no HTML que o WeasyPrint renderiza
**no servidor**, e o `Environment` do Jinja tem `autoescape=False` (de propósito
— os templates espelham CSS verbatim). Um nome de projeto assim:

    <img src="http://169.254.169.254/latest/meta-data/">

faz o NOSSO servidor buscar aquela URL durante a geração do PDF, alcançando o
que a rede interna do Render alcança. E o fetcher padrão do WeasyPrint também
resolve `file://`, o que embutiria conteúdo de arquivo local no PDF que o
cliente baixa.

🪤 A versão do WeasyPrint não resolve isso: a 62.3 é ANTERIOR a qualquer
proteção de SSRF (a CVE-2025-68616 é sobre BYPASS de uma proteção que a 62.3
nem tem). Subir ajuda; não fecha.

🔑 ESTA é a trava que fecha, e ela independe de versão: um `url_fetcher` que
recusa TUDO que não seja `data:`. Medido antes de escrever — nenhum dos 12
templates tem `url()`, `@font-face` ou `http`; as fontes são referenciadas por
NOME de família e resolvidas do sistema, não buscadas. A única coisa externa
legítima é o logo, e ele já chega como `data:` montado de arquivo local
(`_logo_data_uri`). Ou seja: bloquear a rede inteira não tira nada de ninguém.

🚫 Escapar o texto do cliente continua sendo necessário (e é feito no
`build_context`), mas sozinho não bastaria: bastaria UM campo novo esquecido
num template futuro. As duas defesas somam — esta é a que não depende de
alguém lembrar.
"""
from typing import Optional

#: 🪤 `data:` é o ÚNICO esquema que não sai da máquina. `file:` fica de fora de
#: propósito, mesmo parecendo inofensivo: é ele que transformaria a injeção em
#: leitura de arquivo do servidor entregue dentro do PDF.
_ESQUEMAS_PERMITIDOS = ("data:",)


class RecursoExternoBloqueado(Exception):
    """Levantada quando o HTML tenta buscar algo fora. Não é erro do cliente:
    é o guarda funcionando, e o log precisa dizer QUAL url foi tentada."""


def recurso_permitido(url) -> bool:
    """A DECISÃO, separada da busca — e sem depender do WeasyPrint.

    🪤 Existe separada por um motivo medido: o `weasyprint` está no
    requirements (logo, existe no CI) mas NÃO na máquina onde esta bancada é
    escrita. Se a decisão morasse dentro do fetcher, o caminho PERMITIDO só
    seria exercitado no CI — e a parte que decide segurança ficaria sem teste
    justamente onde eu trabalho.
    Ver [[feedback_medir_com_ferramenta_que_a_producao_nao_tem]].
    """
    return str(url or "").lower().startswith(_ESQUEMAS_PERMITIDOS)


def fetcher_sem_rede(url: str):
    """`url_fetcher` do WeasyPrint que recusa tudo que sairia da máquina.

    Levanta em vez de devolver vazio: PDF que sai com um recurso faltando,
    calado, é a mesma família de falha silenciosa que esta casa persegue — o
    cliente receberia um documento incompleto sem ninguém saber.
    """
    u = str(url or "")
    if recurso_permitido(u):
        from weasyprint import default_url_fetcher
        return default_url_fetcher(u)
    raise RecursoExternoBloqueado(
        "o documento tentou buscar %r — só `data:` é permitido. Se isto "
        "apareceu num PDF de cliente, alguém injetou uma tag pelo texto."
        % u[:120])


def gerar_pdf(html: str, base_url: Optional[str] = None) -> bytes:
    """Renderiza HTML em PDF SEM acesso à rede. Use sempre esta, nunca a
    `HTML(...).write_pdf()` crua.

    🔑 Existe pra ser o ÚNICO caminho: enquanto as três chamadas
    (cronograma, financeiro, memorial) montavam cada uma a sua, bastava
    esquecer uma pra reabrir a porta — e as três estavam esquecidas.
    """
    from weasyprint import HTML
    return HTML(string=html, base_url=base_url,
                url_fetcher=fetcher_sem_rede).write_pdf()
