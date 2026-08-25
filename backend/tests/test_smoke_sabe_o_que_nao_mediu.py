# -*- coding: utf-8 -*-
"""O smoke tem que saber a diferença entre "o site caiu" e "não consegui olhar".

🚨 25/08/2026. O smoke ficou vermelho no commit `2cccde0` com três 403 em
`ai.arq.br` — e o site estava **perfeito**: do meu IP as três davam 200 no
mesmo minuto, e o nível 2 (o que loga, lê itens e BAIXA A PLANILHA) passou
9 de 9. O que mudou foi o IP: o runner do GitHub é datacenter, e o Cloudflare
(proxy laranja desde 23/07) barra por reputação mesmo com User-Agent de
navegador.

Custou uma hora minha e do Pedro procurando um bug de deploy que não existia.
E o motivo real não chegava em mim: o log do Actions exige admin e a API
devolve 403 até em repositório público — as anotações públicas só trazem
"Smoke test falhou".

Duas correções, e este arquivo guarda a primeira:

  1. 403 COM marca do Cloudflare vira **INCONCLUSIVO** — nem passa, nem falha.
     🚫 Falha fechada: 403 SEM essas marcas continua sendo falha de verdade,
     senão eu teria trocado um alarme falso por um silêncio perigoso.
  2. `smoke_report_failure.py` publica o motivo como comentário de commit,
     que é público e legível pela API sem credencial.

🪤 O risco desta mudança é óbvio e é por isso que ela tem controle positivo: se
o classificador ficar largo demais, o smoke passa a engolir 403 de verdade e
vira decoração. Os testes abaixo cobrem os dois lados.
"""
import io
import os
import types

import pytest

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPT = os.path.join(_RAIZ, ".github", "scripts", "smoke_test_production.py")
_REPORT = os.path.join(_RAIZ, ".github", "scripts", "smoke_report_failure.py")


def _carrega(caminho, nome):
    if not os.path.exists(caminho):
        pytest.skip("%s não está nesta cópia" % nome)
    mod = types.ModuleType(nome)
    mod.__dict__["__name__"] = nome
    exec(compile(io.open(caminho, encoding="utf-8").read(), caminho, "exec"),
         mod.__dict__)
    return mod


@pytest.fixture(scope="module")
def smoke():
    return _carrega(_SCRIPT, "smoke_prod")


@pytest.fixture(scope="module")
def report():
    return _carrega(_REPORT, "smoke_report")


# ══════════════════════════════════════════════════════════════════════════
#  O caso real de 25/08
# ══════════════════════════════════════════════════════════════════════════
def test_403_do_cloudflare_e_INCONCLUSIVO(smoke):
    """Foi este o vermelho: Server: cloudflare + CF-RAY, 403, site no ar."""
    assert smoke._e_bloqueio_do_cloudflare(
        403, {"Server": "cloudflare", "CF-RAY": "a30b973f3fc91dd0-GRU"}, b"")


@pytest.mark.parametrize("cabecalhos", [
    {"Server": "cloudflare"},
    {"CF-RAY": "abc-GRU"},
    {"cf-mitigated": "challenge"},
    {"server": "CLOUDFLARE"},          # caixa não pode importar
])
def test_qualquer_marca_do_cloudflare_serve(smoke, cabecalhos):
    assert smoke._e_bloqueio_do_cloudflare(403, cabecalhos, b"")


def test_corpo_com_cloudflare_tambem_conta(smoke):
    corpo = b"<html><head><title>Attention Required! | Cloudflare</title>"
    assert smoke._e_bloqueio_do_cloudflare(403, {}, corpo)


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO: o classificador tem que REPROVAR o resto
# ══════════════════════════════════════════════════════════════════════════
def test_403_SEM_cloudflare_continua_sendo_falha(smoke):
    """🚨 O perigo da correção: se tudo virar inconclusivo, o smoke vira
    decoração. 403 do próprio site é falha e tem que continuar sendo."""
    assert not smoke._e_bloqueio_do_cloudflare(
        403, {"Server": "GitHub.com"}, b"<html>Forbidden</html>")


@pytest.mark.parametrize("status", [200, 301, 404, 500, 502, 503])
def test_nenhum_outro_status_vira_inconclusivo(smoke, status):
    """Só 403 pode ser bloqueio de bot. 404 é página que sumiu — falha."""
    assert not smoke._e_bloqueio_do_cloudflare(
        status, {"Server": "cloudflare", "CF-RAY": "x"}, b"")


def test_inconclusivo_nao_entra_como_passou(smoke):
    """🪤 A tentação era contar como pass e ficar verde. Aí "não consegui
    olhar" viraria "está tudo bem" — o pecado que esta casa persegue."""
    smoke.passes.clear()
    smoke.failures.clear()
    smoke.inconclusivos.clear()
    smoke._get = lambda url, headers=None, timeout=60: (
        403, b"", {"Server": "cloudflare", "CF-RAY": "z"})
    smoke._check_site("GET ai.arq.br/", "https://ai.arq.br/", b"<html")
    assert smoke.inconclusivos and not smoke.passes and not smoke.failures


def test_site_fora_do_ar_ainda_reprova(smoke):
    """🧪 O outro lado do mesmo controle, pelo caminho real do check."""
    smoke.passes.clear()
    smoke.failures.clear()
    smoke.inconclusivos.clear()
    smoke._get = lambda url, headers=None, timeout=60: (503, b"", {})
    smoke._check_site("GET ai.arq.br/", "https://ai.arq.br/", b"<html")
    assert smoke.failures and not smoke.inconclusivos


# ══════════════════════════════════════════════════════════════════════════
#  🚨 O relatório é PÚBLICO — não pode vazar dado de cliente
# ══════════════════════════════════════════════════════════════════════════
def test_o_relatorio_esconde_email_e_token(report):
    """O repositório é público e o nível 2 imprime o e-mail do usuário real.

    🪤 As iscas são MONTADAS em pedaços, de propósito. A 1ª versão escrevia
    `sk_live_...` inteiro no arquivo e o **push protection do GitHub barrou o
    push**, lendo como chave da Stripe de verdade. Estava certo em barrar: um
    scanner não tem como saber que aquilo era cenário de teste. Escrever a
    isca por partes prova a mesma coisa sem plantar algo com cara de segredo
    num repositório público — e sem me ensinar a clicar em "permitir mesmo
    assim", que é o hábito que um dia deixa o segredo real passar."""
    chave_falsa = "sk" + "_live_" + ("a" * 24)
    jwt_falso = "eyJ" + "a" * 20 + "." + "eyJ" + "b" * 20 + "." + "c" * 30
    email_falso = "fulano.tester" + "@" + "exemplo-que-nao-existe.com"
    bruto = ("NÍVEL 2 — com credencial de %s\n"
             "jwt=%s\npassword: segredo123\nSUPABASE_TOKEN=%s\n"
             % (email_falso, jwt_falso, chave_falsa))
    limpo = report._limpar(bruto)
    for proibido in (email_falso, "segredo123", chave_falsa, jwt_falso):
        assert proibido not in limpo, "vazou %r no comentário público" % proibido
    assert "<email-oculto>" in limpo


def test_controle_o_limpador_nao_apaga_o_diagnostico(report):
    """🧪 Limpador que apaga tudo protege e não informa — o comentário existe
    justamente pra dizer O QUE quebrou."""
    bruto = "✗ GET sitemap.xml: HTTP 403\n✗ GET faq.html: HTTP 403\n"
    limpo = report._limpar(bruto)
    assert "sitemap.xml" in limpo and "403" in limpo


def test_o_relatorio_escolhe_as_linhas_que_explicam(report):
    bruto = "\n".join(["linha de ruido"] * 50
                      + ["  ✗ GET faq.html  (HTTP 403)", "Falhas:", "  • GET faq.html: HTTP 403"])
    resumo = report._so_o_que_interessa(bruto)
    assert "faq.html" in resumo
    assert "linha de ruido" not in resumo


def test_o_relatorio_nunca_derruba_o_job(report):
    """🪤 Se o GITHUB_TOKEN estiver read-only, comentar dá 403. Falhar aqui
    trocaria a causa real do vermelho por 'não consegui comentar'."""
    corpo = io.open(_REPORT, encoding="utf-8").read()
    assert "return 0" in corpo.split("def main")[1]
