# -*- coding: utf-8 -*-
"""O farol do site guarda QUANTOS erros, não só "teve erro".

🩸 17/09/2026, Pedro olhando o painel: **"6 dias com erro"** em vermelho. Fui
investigar e descobri que a pergunta não tem resposta possível hoje: a série
guarda só um `site_ok` booleano, então **um único 5xx em 800 requisições pinta o
dia exatamente igual a uma queda de uma hora**. Seis dias vermelhos podem ser
seis soluços de um segundo ou seis quedas — e o dado pra decidir foi jogado fora
na hora de gravar. É o mesmo padrão que a gente passou dois dias consertando: o
sistema mede e descarta.

📏 Medido antes de mexer: os dias vermelhos foram 31/08, 03/09, 05/09, 09/09,
12/09 e 15/09. A hipótese óbvia — "é o deploy do site" — morreu no dado:
**12/09 não teve NENHUM commit** e ficou vermelho, e 04/09 teve 24 commits e
ficou verde.

🩸 E o buraco que apareceu lendo o código: `site_ok` só virava `None` quando a
consulta LEVANTAVA exceção. Uma resposta de ERRO do GraphQL (que vem com HTTP
200 e um campo `errors`) caía no `.get("data") or {}`, virava lista vazia, somava
zero e acendia o farol **VERDE sem ter medido nada** — exatamente a doença de
02/09 que o comentário daquela função promete nunca mais repetir.

🔑 E as duas respostas passam a sair da MESMA régua: `site_ok` é DERIVADO da
contagem, não medido em paralelo. Dois campos independentes sobre o mesmo fato
divergem — foi o defeito do retry que a gente consertou em 16/09.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import metricas_site as ms  # noqa: E402


def _resposta(grupos):
    return {"data": {"viewer": {"zones": [{"httpRequestsAdaptiveGroups": grupos}]}}}


def _com(monkeypatch, resposta):
    if isinstance(resposta, Exception):
        def _g(*a, **k):
            raise resposta
    else:
        def _g(*a, **k):
            return resposta
    monkeypatch.setattr(ms, "_graphql", _g)


# ── a contagem ─────────────────────────────────────────────────────────────
def test_devolve_QUANTOS_erros(monkeypatch):
    _com(monkeypatch, _resposta([{"count": 3}, {"count": 14}]))
    assert ms.erros_5xx_do_dia("a", "b") == 17


def test_dia_limpo_devolve_ZERO_e_zero_nao_e_nulo(monkeypatch):
    """🔑 'Medi e não houve' é 0. 'Não consegui medir' é None. Confundir os dois
    foi o defeito de 02/09."""
    _com(monkeypatch, _resposta([]))
    assert ms.erros_5xx_do_dia("a", "b") == 0


def test_consulta_que_EXPLODE_devolve_nao_sei(monkeypatch):
    _com(monkeypatch, RuntimeError("cloudflare fora do ar"))
    assert ms.erros_5xx_do_dia("a", "b") is None


def test_ERRO_do_graphql_dentro_de_um_200_tambem_e_nao_sei(monkeypatch):
    """🩸 O buraco achado em 17/09: o GraphQL reporta falha com HTTP 200 e um
    campo `errors`. O código antigo lia isso como 'nenhum erro' e acendia o
    farol VERDE sem ter medido nada."""
    _com(monkeypatch, {"errors": [{"message": "authentication error"}], "data": None})
    assert ms.erros_5xx_do_dia("a", "b") is None


def test_erro_do_graphql_COM_DADO_PARCIAL_tambem_e_nao_sei(monkeypatch):
    """🩸 Achado pela SABOTAGEM (F02, 17/09): meu primeiro guarda testava só a
    resposta de erro SEM dado, e essa a rede seguinte já pegava — a mutação que
    removia a checagem de `errors` sobrevivia.

    O caso que só ela segura é este: o GraphQL responde com `errors` E com dado
    PARCIAL. Sem a checagem, o parcial é somado como se fosse a verdade e o
    farol acende VERDE — medindo errado, que é pior que não medir.
    """
    _com(monkeypatch, {"errors": [{"message": "rate limited"}],
                       "data": {"viewer": {"zones": [
                           {"httpRequestsAdaptiveGroups": [{"count": 0}]}]}}})
    assert ms.erros_5xx_do_dia("a", "b") is None, (
        "dado PARCIAL com erro virou medição — o farol acenderia verde sem ter "
        "medido o dia inteiro")


def test_resposta_sem_o_formato_esperado_e_nao_sei(monkeypatch):
    for r in ({}, {"data": {}}, {"data": {"viewer": None}}, {"data": {"viewer": {"zones": []}}}):
        _com(monkeypatch, r)
        assert ms.erros_5xx_do_dia("a", "b") is None, r


# ── uma régua só ───────────────────────────────────────────────────────────
def test_o_site_ok_e_DERIVADO_da_contagem(monkeypatch):
    """🔑 Nunca dois campos independentes sobre o mesmo fato. Se o farol e a
    contagem forem medidos separados, um dia discordam — e aí o painel afirma
    uma coisa e o número diz outra."""
    casos = [(0, True), (1, False), (57, False), (None, None)]
    for n, esperado in casos:
        assert ms.site_ok_da_contagem(n) is esperado, (n, esperado)


def test_IMPOSSIVEL_ter_farol_verde_com_erro_contado():
    """O guarda que trava a contradição, em qualquer número."""
    for n in range(0, 40):
        ok = ms.site_ok_da_contagem(n)
        assert ok == (n == 0), n
        assert not (ok and n > 0), "farol verde com %d erro(s)" % n


# ── o que chega na série ───────────────────────────────────────────────────
def test_a_foto_do_dia_leva_a_contagem_junto(monkeypatch):
    """Guarda de CHAMADA: a função pode estar certa e `coletar` não usá-la."""
    monkeypatch.setattr(ms, "erros_5xx_do_dia", lambda *a, **k: 4)
    monkeypatch.setattr(ms, "_graphql", lambda *a, **k: {"data": None})
    monkeypatch.setattr(ms, "requisicoes_do_dia", lambda *a, **k: ([], 0, 0, 0),
                        raising=False)
    from datetime import date
    try:
        foto = ms.coletar(date(2026, 9, 12), ips_da_casa=set())
    except Exception as e:                      # rede/credencial: o guarda ainda vale
        import pytest
        pytest.skip("coletar não roda isolado aqui: %s" % e)
    assert foto.get("erros_5xx") == 4, foto
    assert foto.get("site_ok") is False, (
        "a foto gravou farol e contagem discordando: %r" % foto)


# ── o painel (guarda de FONTE, e assumido como tal) ────────────────────────
def test_o_painel_mostra_QUANTOS_erros():
    """🪤 Guarda de FONTE, declarado: o bloco do farol vive dentro de uma função
    grande do `admin.html` que mexe em muito DOM. O que ele prende é que a tela
    LÊ a contagem e mostra o pior dia — sem isso o Pedro volta a ver só
    "6 dias com erro" e a pergunta seguinte fica sem resposta, que foi o que
    abriu esta investigação.
    """
    import io
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    src = io.open(os.path.join(raiz, "admin.html"), encoding="utf-8").read()
    assert "erros_5xx" in src, "o painel não lê a contagem"
    assert "const pior = comConta.reduce(" in src, (
        "sumiu o pior dia — 6 soluços e 6 quedas voltam a ter a mesma cara")
    assert "' · pior: '" in src, "o número não chega ao texto do farol"
    assert "typeof x.erros_5xx === 'number'" in src, (
        "dia SEM a contagem (linha antiga) precisa ficar de fora da soma, "
        "não virar zero")
