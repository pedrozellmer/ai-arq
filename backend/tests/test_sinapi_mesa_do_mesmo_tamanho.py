# -*- coding: utf-8 -*-
"""O kit de porta do TAMANHO do item tem que chegar na mesa da IA.

🩸 27/09/2026 — nas 4 buscas por texto do `candidates_for` o tamanho quase não
pesa: os ~40 kits de porta (60/70/80/90 × pintura, verniz, frisada… × com/sem
fechadura) empatam na mesma nota, e a busca de palavra-chave dá bônus a quem
COMEÇA com "PORTA" — folha avulsa, recolocação e carga e descarga passam na
frente de "KIT DE PORTA". A mesa lota antes de chegar neles. Nas 42 portas
reais, só 3 das 21 com tamanho lido tinham o kit com fechadura daquele tamanho
na mesa; com a busca pelo tamanho, 9 de 21 (as 9 cujo tamanho o SINAPI tem).
Em 48 itens reais sorteados nenhuma mesa mudou; em 40 itens com tamanho, só
o piso 45x45, que ganhou os 6 pisos cerâmicos 45x45 no lugar de gangorra e
linha de vida.

Os textos 91314/91320/90822/106140 são da base SINAPI oficial (pública). Os
que dizem "TESTE" são inventados pra armadilha. Nada aqui é texto de cliente.
"""
import os
import re
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import sinapi_matcher  # noqa: E402

KIT_COM = {"codigo": "91314", "unidade": "UN", "descricao": (
    "KIT DE PORTA DE MADEIRA PARA PINTURA, SEMI-OCA (LEVE OU MÉDIA), PADRÃO POPULAR, "
    "80X210CM, ESPESSURA DE 3,5CM, ITENS INCLUSOS: DOBRADIÇAS, MONTAGEM E INSTALAÇÃO "
    "DO BATENTE, FECHADURA COM EXECUÇÃO DO FURO - FORNECIMENTO E INSTALAÇÃO. AF_10/2025")}
KIT_SEM = {"codigo": "91320", "unidade": "UN", "descricao": (
    "KIT DE PORTA DE MADEIRA PARA PINTURA, SEMI-OCA (LEVE OU MÉDIA), PADRÃO POPULAR, "
    "80X210CM, ESPESSURA DE 3,5CM, ITENS INCLUSOS: DOBRADIÇAS, MONTAGEM E INSTALAÇÃO "
    "DO BATENTE, SEM FECHADURA - FORNECIMENTO E INSTALAÇÃO. AF_10/2025")}
FOLHA = {"codigo": "90822", "unidade": "UN", "descricao": (
    "PORTA DE MADEIRA PARA PINTURA, SEMI-OCA (LEVE OU MÉDIA), 80X210CM, ESPESSURA DE "
    "3,5CM, INCLUSO DOBRADIÇAS - FORNECIMENTO E INSTALAÇÃO. AF_10/2025")}
TRES_MEDIDAS = {"codigo": "106140", "unidade": "UN", "descricao": (
    "PORTA CORTA-FOGO 80X210X5CM COM BARRA ANTI PÂNICO - FORNECIMENTO E INSTALAÇÃO. AF_10/2025")}
OUTRO_NUMERO = {"codigo": "T0180", "unidade": "UN",
                "descricao": "PORTA DE TESTE 180X210CM - FORNECIMENTO E INSTALAÇÃO"}
OUTRA_COISA = {"codigo": "T0808", "unidade": "UN",
               "descricao": "PAINEL DE TESTE 80X210CM EM CHAPA METÁLICA"}
DO_TAMANHO = [OUTRO_NUMERO, TRES_MEDIDAS, OUTRA_COISA, FOLHA, KIT_SEM, KIT_COM]

# A linha 7.1 do exemplo público (exemplos/itens.json), cuja referência é o 91314.
ITEM = "Porta de madeira 80x210 com batente e ferragens"


def _lote(prefixo, n=60):
    """O que as 4 buscas por texto devolvem pra uma porta: a mesa inteira de outra coisa."""
    return [{"codigo": "%s%03d" % (prefixo, i), "unidade": "UN",
             "descricao": "PORTA DE TESTE %s %d - FORNECIMENTO E INSTALAÇÃO" % (prefixo, i)}
            for i in range(n)]


@pytest.fixture
def banco(monkeypatch):
    """Dublê do Supabase: as 4 buscas da produção lotadas de outra coisa, e a
    busca pelo tamanho ("80x210") com o kit no MEIO das armadilhas."""
    chamadas = []

    # 🪤 `*a, **k` de propósito: parâmetro novo no call site não pode desarmar o
    # dublê em silêncio (feedback_duble_com_assinatura_exata_desarma_calado).
    def _rpc(fname, params, *a, **k):
        chamadas.append((fname, dict(params)))
        q = params.get("p_query") or ""
        if fname == "sinapi_rescore":
            nota = {"91314": 0.354, "91320": 0.354, "90822": 0.354}
            return [{"codigo": c, "similarity": nota.get(c, 0.2)} for c in params["p_codigos"]]
        if fname == "sinapi_candidates":
            return _lote("FRASE")
        if fname == "search_sinapi" and q == "80x210":
            return [dict(r) for r in DO_TAMANHO]
        if fname == "search_sinapi" and q == ITEM:
            return []          # a frase inteira não passa no filtro do search_sinapi
        if fname == "search_sinapi" and len(q.split()) >= 3:
            return _lote("PALAVRAS")
        if fname == "search_sinapi":
            return _lote("PALAVRA")
        return []
    monkeypatch.setattr(sinapi_matcher, "_supabase_rpc", _rpc)
    return chamadas


def _mesa(descricao=ITEM):
    return {c["codigo"] for c in sinapi_matcher.candidates_for(descricao, limit=60)}


# ── O caso que abriu a investigação ─────────────────────────────────────────
def test_o_kit_com_fechadura_do_tamanho_do_item_chega_na_mesa(banco):
    mesa = _mesa()
    assert "91314" in mesa, (
        "as 4 buscas por texto lotam a mesa e o kit 80x210 com fechadura fica de "
        "fora — a IA não tem como escolhê-lo")
    assert {"91320", "90822"} <= mesa, "os outros 80x210 de porta também deviam entrar"


def test_o_tamanho_tem_que_ser_EXATO_e_de_2_medidas(banco):
    mesa = _mesa()
    assert "T0180" not in mesa, "180X210 entrou por conter '80X210'"
    assert "106140" not in mesa, "80X210X5CM tem 3 medidas e entrou"


def test_tem_que_ser_a_MESMA_coisa_do_item(banco):
    """🩸 Sem este filtro, '19x19' de um pilar trazia bloco 19X19X39 e '40x40'
    de um azulejo trazia quadro de telefone 40X40X12."""
    assert "T0808" not in _mesa(), "painel 80X210 entrou numa porta só pelo tamanho"


def test_CONTROLE_item_sem_tamanho_nao_faz_busca_por_tamanho(banco):
    _mesa("Porta de madeira semi-oca para pintura")
    por_tamanho = [p for f, p in banco if re.fullmatch(r"\d+x\d+", p.get("p_query") or "")]
    assert not por_tamanho, "item sem tamanho disparou busca por tamanho: %s" % por_tamanho


# ── A leitura do tamanho ────────────────────────────────────────────────────
@pytest.mark.parametrize("texto,esperado", [
    ("Porta de madeira 80x210 com batente", (80, 210)),
    ("Porta 80×210 cm", (80, 210)),
    ("Porta maciça 0,90x2,10m", (90, 210)),          # metro vira cm
    ("Porcelanato 60×60cm", (60, 60)),
    ("Pilar 25 cm × 80 cm", (25, 80)),
    ("Cuba inox 50x40", (50, 40)),                    # o x de "inox" é letra
    ("Placa 150×150 mm", None),                       # milímetro: o SINAPI escreve outro jeito
    ('Caixa PVC 4×2" embutir', None),                 # polegada
    ("Impressora 60×50×60 cm", None),                 # 3 medidas
    ("Bloco 9×19×19cm", None),
    ("Porta 60 x 50 x 60", None),
    ("Pastilha 7,5 × 25 cm", None),                   # cm quebrado não existe no SINAPI
    ("Porta de madeira semi-oca", None),
])
def test_tamanho_do_item(texto, esperado):
    assert sinapi_matcher._tamanho_do_item(texto) == esperado


@pytest.mark.parametrize("descricao,tamanho,esperado", [
    ("KIT DE PORTA ... 80X210CM, ESPESSURA DE 3,5CM", (80, 210), True),
    ("PISO 60 X 60 CM", (60, 60), True),
    ("PORTA 180X210CM", (80, 210), False),
    ("PORTA CORTA-FOGO 80X210X5CM", (80, 210), False),
    ("BLOCOS VAZADOS DE CONCRETO DE 19X19X39 CM", (19, 19), False),
    ("QUADRO PARA TELEFONE 40X40X12CM", (40, 40), False),
    ("CABO 5X2,5", (5, 2), False),
])
def test_tem_o_tamanho(descricao, tamanho, esperado):
    assert sinapi_matcher._tem_o_tamanho(descricao, tamanho) is esperado
