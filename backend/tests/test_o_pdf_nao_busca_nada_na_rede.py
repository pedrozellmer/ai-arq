# -*- coding: utf-8 -*-
"""O nome que o cliente digita não pode fazer o SERVIDOR buscar coisa na rede.

🚨 08/09/2026, auditoria de segurança. Gravidade ALTA, confirmada por dois
céticos e por leitura minha, ponta a ponta.

O cliente batiza o projeto (`project_name`). Esse texto entra no HTML que o
WeasyPrint renderiza **no servidor**, e o Jinja do cronograma tem
`autoescape=False` — de propósito, porque os templates espelham CSS verbatim.
Um nome de projeto assim:

    <img src="http://169.254.169.254/latest/meta-data/">

faz o NOSSO servidor buscar aquela URL enquanto gera o PDF: SSRF de dentro do
Render, alcançando o que a rede interna alcança. E o fetcher padrão também
resolve `file://` — leitura de arquivo do servidor, embutida no PDF que o
cliente baixa.

🪤 Subir o WeasyPrint NÃO fecha: a 62.3 é anterior a qualquer proteção de SSRF
(a CVE de 2025 é sobre BYPASS de uma proteção que a 62.3 nem tem).

🔑 A trava que fecha, e independe de versão: `url_fetcher` que só aceita
`data:`. 📏 Medido antes de escrever: nenhum dos 12 templates tem `url()`,
`@font-face` ou `http` — as fontes são por NOME de família, e o logo já chega
como `data:` montado de arquivo local. Bloquear a rede não tira nada de ninguém.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from pdf_seguro import (RecursoExternoBloqueado, fetcher_sem_rede,  # noqa: E402
                        recurso_permitido, _ESQUEMAS_PERMITIDOS)

# 🪤 O `weasyprint` está no requirements (logo, existe no CI) mas NÃO na máquina
# onde esta bancada é escrita. Por isso a DECISÃO (`recurso_permitido`) é
# testada sempre, e só a busca de verdade pula quando ele falta — senão a parte
# que decide segurança ficaria sem teste justamente onde eu trabalho.
try:
    import weasyprint as _wp  # noqa: F401
    _TEM_WEASY = True
except Exception:
    _TEM_WEASY = False


# ══════════════════════════════════════════════════════════════════════════
#  O ataque: tudo que sairia da máquina é RECUSADO
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",     # metadados da nuvem
    "https://exemplo.invalido/x.png",
    "HTTP://MAIUSCULA.INVALIDO/x",                  # esquema em maiúscula
    "file:///etc/passwd",                           # leitura de arquivo local
    "file://C:/Users/admin/.env",
    "ftp://x/y",
    "//exemplo.invalido/x.png",                     # protocolo relativo
    "/etc/passwd",                                  # caminho absoluto local
    "../../backend/.env",                           # subida de diretório
    "",
])
def test_recusa_tudo_que_sairia_da_maquina(url):
    with pytest.raises(RecursoExternoBloqueado):
        fetcher_sem_rede(url)


def test_a_recusa_LEVANTA_em_vez_de_devolver_vazio():
    """🪤 Devolver vazio faria o PDF sair com um recurso faltando, calado — a
    mesma família de falha silenciosa que esta casa persegue. E a mensagem tem
    que dizer QUAL url foi tentada, senão o log não ajuda a achar quem injetou.
    """
    with pytest.raises(RecursoExternoBloqueado) as e:
        fetcher_sem_rede("http://169.254.169.254/latest/meta-data/")
    assert "169.254.169.254" in str(e.value), (
        "a mensagem não diz qual url foi tentada: %s" % e.value)


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLE POSITIVO — bloquear tudo seria fácil e quebraria o logo
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("permitido", [
    "data:image/png;base64,iVBORw0KGgo=",
    "data:image/svg+xml;base64,PHN2Zy8+",
    "DATA:image/png;base64,AAAA",          # maiúscula também é `data:`
])
def test_a_DECISAO_deixa_passar_o_data_uri(permitido):
    """O logo do cliente chega como `data:` montado de arquivo local. Se isto
    cair, o PDF sai sem o logo — e guarda que quebra o produto é guarda que
    alguém desliga. 🔑 Roda SEM weasyprint: é a decisão, não a busca."""
    assert recurso_permitido(permitido), permitido


@pytest.mark.parametrize("negado", [
    "http://x/y", "file:///etc/passwd", "//x/y", "/etc/passwd", "", None,
])
def test_a_DECISAO_recusa_o_resto(negado):
    assert not recurso_permitido(negado), repr(negado)


@pytest.mark.skipif(not _TEM_WEASY, reason="weasyprint não instalado aqui (existe no CI)")
def test_o_data_uri_e_REALMENTE_buscado_quando_ha_weasyprint():
    """A ponta que só o CI exercita: decidir 'pode' não basta, o fetcher tem
    que devolver o conteúdo pro WeasyPrint."""
    png = ("data:image/png;base64,"
           "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    r = fetcher_sem_rede(png)
    assert isinstance(r, dict) and (r.get("string") or r.get("file_obj")), r


def test_a_lista_de_esquemas_e_pequena_de_proposito():
    """🪤 `file:` fora, mesmo parecendo inofensivo: é ele que transformaria a
    injeção em leitura de arquivo do servidor entregue dentro do PDF."""
    assert _ESQUEMAS_PERMITIDOS == ("data:",), (
        "alguém alargou a lista de esquemas: %r" % (_ESQUEMAS_PERMITIDOS,))


# ══════════════════════════════════════════════════════════════════════════
#  O caminho ÚNICO — as três gerações têm que passar por aqui
# ══════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════
#  A OUTRA METADE — o texto do cliente sai escapado do build_context
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("campo", [
    "project_name", "architect_name", "client_name", "company",
])
def test_o_texto_do_cliente_sai_ESCAPADO(campo):
    """🔑 Escapado no `build_context`, num lugar só — não com `|e` espalhado
    nos 12 templates. Template novo nasce protegido sem ninguém lembrar."""
    from cronograma_render import build_context
    ataque = '<img src="http://169.254.169.254/latest/meta-data/">'
    ctx = build_context({}, {campo: ataque + " Obra"}, "escuro")
    saiu = ctx["b"][campo]
    assert "<img" not in saiu, "%s saiu CRU: %r" % (campo, saiu[:80])
    assert "&lt;img" in saiu, "%s não foi escapado: %r" % (campo, saiu[:80])
    assert "Obra" in saiu, "escapar não pode comer o texto legítimo: %r" % saiu


def test_CONTROLE_o_nome_normal_continua_legivel():
    """Escapar tudo é fácil e estragaria a capa: acento e & têm que sobreviver
    de forma que o PDF mostre o que a pessoa escreveu."""
    from cronograma_render import build_context
    ctx = build_context({}, {"project_name": "Residência Açaí & Cia"}, "escuro")
    saiu = ctx["b"]["project_name"]
    assert "Residência Açaí" in saiu, saiu
    assert "&amp;" in saiu, "o & tem que virar entidade, não sumir: %r" % saiu


def test_o_nome_vazio_continua_com_o_padrao():
    from cronograma_render import build_context
    assert build_context({}, {}, "escuro")["b"]["project_name"] == "Projeto sem nome"


def test_nenhuma_geracao_de_pdf_monta_a_sua_propria():
    """🔑 Enquanto cronograma, financeiro e memorial montavam cada um o seu
    `HTML(...).write_pdf()`, bastava esquecer UM pra reabrir a porta — e os
    três estavam esquecidos. Este guarda existe pra que o próximo PDF nasça
    pelo caminho seguro."""
    # 🪤 A 1ª versão olhava só a LINHA da chamada e acusou o próprio conserto:
    # ao passar o fetcher, a chamada quebrou em duas linhas e o argumento foi
    # parar na segunda. Peneira por linha não enxerga chamada — o AST enxerga.
    import ast
    import io
    suspeitos = []
    for nome in sorted(os.listdir(_BACKEND)):
        if not nome.endswith(".py") or nome == "pdf_seguro.py":
            continue
        try:
            arvore = ast.parse(io.open(os.path.join(_BACKEND, nome),
                                       encoding="utf-8", errors="replace").read())
        except SyntaxError:
            continue
        for no in ast.walk(arvore):
            if not (isinstance(no, ast.Call) and getattr(no.func, "id", "") == "HTML"):
                continue
            chaves = {k.arg for k in no.keywords if k.arg}
            if "url_fetcher" not in chaves:
                suspeitos.append("%s:%s (argumentos: %s)"
                                 % (nome, getattr(no, "lineno", "?"),
                                    ", ".join(sorted(chaves)) or "posicionais"))
    assert not suspeitos, (
        "geração de PDF sem `url_fetcher` — o servidor volta a buscar o que o "
        "HTML mandar: %s" % suspeitos)
