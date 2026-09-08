# -*- coding: utf-8 -*-
"""A sondagem da derivação de escala MEDE, e não pode decidir nada.

🩸 07/09/2026 — A DERIVAÇÃO DE ESCALA POR COTA NUNCA FUNCIONOU EM PRODUÇÃO.
Medido em dois logs independentes: das **128 promoções** de escala
(`pdfvec:promo`), **0** vieram de cota — 78 de carimbo/viewport e 44 de
carimbo/viewport *validadas* por cota. Nos 187 eventos `pdfvec:shadow` o
`scale_src` é sempre `carimbo` ou `viewport`, nunca `cotas`. Cinco semanas,
143 jobs, zero.

E o mecanismo apareceu: o voto é contado POR TOKEN, e o `break` ELEGE o
primeiro vão que casa. Numa prancha real, 4 cotas com o mesmo texto "80"
casando o mesmo vão viraram 4 "votos independentes" e derivaram **1:50 numa
região que o PDF declara 1:100** — erro de 2× linear e **4× em área**. A
resposta certa estava na lista de vãos, adiante, e o `break` nunca chegou nela.

🚨 POR ISSO A RÉGUA NÃO MUDOU HOJE. A função nunca produz escala, então hoje
ela não erra — só não acerta. Qualquer mudança que a torne mais permissiva anda
na direção do erro de 4×, e a regra dura nº1 diz que número errado com cara de
medido é muito pior que linha vazia. Primeiro os números aparecem no log das
pranchas REAIS; depois se decide.

O que entrou foi SONDAGEM: `valores_distintos`, `por_valor`, `por_par`,
`candidatas` e `corte_eixo_pct` viajam no retorno e vão parar no log
`pdfvec:sem-escala`. Custo zero — os números já eram calculados e descartados.

🔑 ESTE GUARDA TRAVA O INVARIANTE QUE IMPORTA: **a decisão continua saindo só
do voto por token**. Se um dia alguém quiser que a sondagem decida, vai ter que
apagar este teste de propósito — não vai acontecer por acidente.

📏 E a sondagem já refutou o próprio conserto candidato: na prancha real de 222
cotas (verdade 1:100 pelo viewport), o voto por token dá 75:67 · 100:63 e o
voto por VALOR DISTINTO dá 75:9 · 250:9 · 500:7 — o 1:100 não aparece nem no
top 3. Trocar a contagem não conserta esta prancha.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import pdfvec_cotas as pc  # noqa: E402


def _pt(valor_m, escala):
    """Comprimento em PONTOS de um elemento de `valor_m` desenhado em 1:escala.

    🪤 A 1ª versão deste arquivo montou paredes com números redondos em pontos
    (span 100→150) e cota de 5 m: a escala implícita dava 283,5, que não é
    escala padrão, e TODOS os cenários saíam com "nenhum par caiu em escala
    padrão" — o guarda media o vazio. A geometria tem que ser calculada, não
    escolhida a olho.
    """
    return valor_m / (escala * pc.PT_TO_M)


def _parede_em(valor_m, escala, inicio, p_pt, axis="h"):
    """Parede que, na escala dada, mede `valor_m`."""
    fim = inicio + _pt(valor_m, escala)
    return {"length_m": valor_m, "axis": axis,
            "span_pt": (inicio, fim), "p_pt": p_pt}


def _token(valor_m, centro):
    return {"text": str(valor_m), "value_m": valor_m,
            "center": centro, "bbox": (centro[0] - 5, centro[1] - 3,
                                       centro[0] + 5, centro[1] + 3)}


@pytest.fixture
def sem_pdf(monkeypatch):
    """Troca a leitura do PDF por tokens de mentira — o guarda não depende de
    arquivo nenhum (os PDFs de teste não vão pro repositório)."""
    def montar(tokens):
        monkeypatch.setattr(pc, "extract_cota_tokens",
                            lambda *a, **k: list(tokens))
    return montar


def _decide(res):
    """A regra ESCRITA, aplicada ao voto por token. Se `scale` divergir disto,
    alguma coisa além do voto por token entrou na decisão."""
    if res.get("votos") is None:
        return None
    ok = (res["votos"] >= pc.MIN_VOTOS_ESCALA
          and res["votos"] >= pc.DOMINANCIA * max(res.get("segundo_lugar", 0), 1))
    if not ok:
        return None
    return float((res.get("candidatas") or [{}])[0].get("escala"))


# ══════════════════════════════════════════════════════════════════════════
#  1 · o invariante: quem decide é o voto por TOKEN, e mais nada
# ══════════════════════════════════════════════════════════════════════════
def _cenario_dominante():
    """Uma parede de 5 m desenhada em 1:100, com 6 cotas de 5 m em cima."""
    paredes = [_parede_em(5.0, 100, 100.0, 200.0)]
    tokens = [_token(5.0, (105.0 + i, 200.0)) for i in range(6)]
    return paredes, tokens


def test_a_decisao_sai_do_voto_por_token(sem_pdf):
    paredes, tokens = _cenario_dominante()
    sem_pdf(tokens)
    r = pc.derive_scale_from_cotas("x.pdf", 0, None, walls=paredes)
    assert r.get("votos"), "o cenário não produziu voto — o guarda perdeu o alvo"
    assert r.get("scale") == _decide(r), (
        "a `scale` divergiu da regra escrita sobre o voto por token: "
        "alguma coisa da sondagem entrou na decisão (%r)" % r)


def _cenario_divergente():
    """As duas contagens apontam escalas DIFERENTES.

    · 1:100 ganha POR TOKEN — uma parede com 8 cotas do MESMO valor;
    · 1:50 ganha POR VALOR  — três paredes com três valores DIFERENTES.

    🪤 Sem divergência de verdade, o guarda não prova nada: a 1ª versão usava
    duas paredes na MESMA escala, as duas contagens concordavam, e o mutante
    "a sondagem decide" passava batido.
    """
    paredes = [_parede_em(5.0, 100, 100.0, 200.0),
               _parede_em(2.0, 50, 900.0, 400.0),
               _parede_em(3.0, 50, 1400.0, 500.0),
               _parede_em(4.0, 50, 2000.0, 600.0)]
    tokens = ([_token(5.0, (105.0 + i, 200.0)) for i in range(8)]
              + [_token(2.0, (905.0, 400.0)),
                 _token(3.0, (1405.0, 500.0)),
                 _token(4.0, (2005.0, 600.0))])
    return paredes, tokens


def test_a_sondagem_discorda_e_a_decisao_NAO_muda(sem_pdf):
    """🚨 O teste que importa: as duas contagens apontam escalas diferentes."""
    paredes, tokens = _cenario_divergente()
    sem_pdf(tokens)
    r = pc.derive_scale_from_cotas("x.pdf", 0, None, walls=paredes)
    assert r.get("votos"), "cenário sem voto"
    # o cenário TEM que divergir, senão o teste não mede nada
    assert r["candidatas"][0]["escala"] != r["por_valor"][0]["escala"], (
        "as duas contagens concordaram: o cenário perdeu o propósito (%r)" % r)
    assert r.get("scale") == _decide(r), (
        "a decisão seguiu a SONDAGEM em vez do voto por token (%r)" % r)
    assert r.get("por_par"), "a sondagem por par valor×vão não saiu"


def test_a_dominancia_continua_recusando_o_quase_empate(sem_pdf):
    """A trava que segura a régua hoje — e que a sondagem não pode afrouxar.

    🪤 Nenhum teste prendia isto: a mutação que apaga a dominância passava
    batida. Com 1º e 2º quase empatados a função tem que devolver None.
    """
    paredes = ([_parede_em(5.0, 100, 100.0 + i * 400, 200.0 + i) for i in range(5)]
               + [_parede_em(2.0, 50, 3000.0 + i * 400, 800.0 + i) for i in range(4)])
    tokens = ([_token(5.0, (105.0 + i * 400, 200.0 + i)) for i in range(5)]
              + [_token(2.0, (3005.0 + i * 400, 800.0 + i)) for i in range(4)])
    sem_pdf(tokens)
    r = pc.derive_scale_from_cotas("x.pdf", 0, None, walls=paredes)
    assert r.get("votos") and r.get("segundo_lugar"), "cenário sem os dois lugares"
    assert r["votos"] < pc.DOMINANCIA * r["segundo_lugar"], (
        "o cenário não é quase-empate: %s x %s" % (r["votos"], r["segundo_lugar"]))
    assert r.get("scale") is None, (
        "quase-empate virou escala: a dominância deixou de segurar (%r)" % r)


def test_a_sondagem_conta_valor_DISTINTO_e_nao_token(sem_pdf):
    """O número que a sondagem existe pra dar: 8 tokens, 1 valor só."""
    paredes = [_parede_em(5.0, 100, 100.0, 200.0)]
    sem_pdf([_token(5.0, (105.0 + i, 200.0)) for i in range(8)])
    r = pc.derive_scale_from_cotas("x.pdf", 0, None, walls=paredes)
    assert r.get("valores_distintos") == 1, (
        "8 cotas com o MESMO valor têm que contar 1 valor distinto — é esse o "
        "número que mostra o voto inflado (%r)" % r.get("valores_distintos"))
    assert r["votos"] > r["por_valor"][0]["n"], (
        "o voto por token tem que ser MAIOR que o por valor distinto neste "
        "cenário; se forem iguais, a sondagem não está medindo o que promete")


# ══════════════════════════════════════════════════════════════════════════
#  2 · o corte espacial do MAX_PONTAS fica VISÍVEL
# ══════════════════════════════════════════════════════════════════════════
def test_o_corte_do_max_pontas_aparece_no_retorno(sem_pdf):
    """🩸 `pontas[:MAX_PONTAS]` corta uma lista ORDENADA POR COORDENADA: guarda
    os N pontos mais à esquerda e joga fora o resto da folha. Medido nos PDFs
    locais: prancha A0 perde 39,8% da largura, A1 de arquitetura perde 38,1%.

    Não conserto aqui — só faço aparecer. Consertar sem medir a produção anda
    pro lado do erro de 4×.
    """
    # paredes espalhadas ao longo de um eixo largo, mais que o teto de pontas
    n = pc.MAX_PONTAS + 60
    largura = _pt(1.0, 100)
    paredes = [_parede_em(1.0, 100, float(i) * (largura + 12.0), 100.0)
               for i in range(n)]
    # uma cota em cima da PRIMEIRA parede, pra existir voto e o retorno completo
    sem_pdf([_token(1.0, (largura / 2.0, 100.0))])
    r = pc.derive_scale_from_cotas("x.pdf", 0, None, walls=paredes)
    corte = r.get("corte_eixo_pct")
    assert corte, "o corte aconteceu e não apareceu no retorno"
    assert corte.get("h", 0) > 0, corte


def test_CONTROLE_sem_corte_o_campo_fica_vazio(sem_pdf):
    """O outro lado: prancha pequena não pode reportar corte nenhum."""
    paredes = [_parede_em(5.0, 100, 100.0, 200.0)]
    sem_pdf([_token(5.0, (110.0, 200.0))])
    r = pc.derive_scale_from_cotas("x.pdf", 0, None, walls=paredes)
    assert not r.get("corte_eixo_pct"), r.get("corte_eixo_pct")


# ══════════════════════════════════════════════════════════════════════════
#  3 · 🧪 CONTROLE POSITIVO — o guarda reprova se a sondagem decidir
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_guarda_pega_a_sondagem_decidindo(sem_pdf, monkeypatch):
    """Faz a sondagem virar a decisão e exige que `_decide` acuse."""
    # 🪤 O mutante só prova alguma coisa se as duas contagens DISCORDAREM.
    # A 1ª versão deste controle usava um cenário em que o `por_valor` apontava
    # a MESMA escala do voto por token — o mutante "decidia" e o resultado não
    # mudava, e o teste reprovava a si mesmo. Aqui:
    #   · 1:100 ganha POR TOKEN  — uma parede com 8 cotas do MESMO valor;
    #   · 1:50 ganha POR VALOR   — três paredes com três valores DIFERENTES.
    paredes = [_parede_em(5.0, 100, 100.0, 200.0),
               _parede_em(2.0, 50, 900.0, 400.0),
               _parede_em(3.0, 50, 1400.0, 500.0),
               _parede_em(4.0, 50, 2000.0, 600.0)]
    tokens = ([_token(5.0, (105.0 + i, 200.0)) for i in range(8)]
              + [_token(2.0, (905.0, 400.0)),
                 _token(3.0, (1405.0, 500.0)),
                 _token(4.0, (2005.0, 600.0))])
    sem_pdf(tokens)
    original = pc.derive_scale_from_cotas

    def mutante(*a, **k):
        r = original(*a, **k)
        # a sondagem passa a mandar: escolhe pelo ranking por valor distinto
        if r.get("por_valor"):
            r["scale"] = float(r["por_valor"][0]["escala"])
        return r

    monkeypatch.setattr(pc, "derive_scale_from_cotas", mutante)
    r = pc.derive_scale_from_cotas("x.pdf", 0, None, walls=paredes)
    assert r.get("scale") != _decide(r), (
        "o mutante não mudou a decisão — revisar o controle positivo")
