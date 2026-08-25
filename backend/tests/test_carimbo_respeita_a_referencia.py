# -*- coding: utf-8 -*-
"""O carimbo do motor não pode fechar uma marca que o projeto deixou aberta.

🚨 25/08/2026, achado horas DEPOIS de eu dar a feature por pronta. O
`_carimbar_spec` — o carimbo que roda no processamento e alimenta a planilha
que o cliente baixa — escrevia `it.spec_origem = "lido"` **chapado**, jogando
fora o retorno de `spec_origem(sp)`.

Efeito medido, com o extrator real:

    "Chapa de gesso acartonado Performa — Knauf/Placo ou similar"
      com o bug  → planilha escreve "Knauf/Placo"
      correto    → planilha escreve "Knauf/Placo (ou similar)"

São **73 itens** no acervo marcados `lido:referencia`. Todos sairiam no
PRIMEIRO .xlsx entregue como decisão fechada do arquiteto — fechando a
concorrência que ele deixou aberta de propósito, no documento que ele assina.

🪤 E o mesmo projeto teria DUAS VERDADES: o .xlsx reconstruído depois da
revisão reidrata as colunas do banco e sai certo. Só o primeiro mente.

🪤 A causa é a de sempre neste arquivo: valor calculado de um lado, ignorado
do outro. Eu escrevi `spec_origem()` de manhã e não liguei no carimbo —
terceira vez (antes foram o `origem` e o `_spec_campos`, no mesmo dia).

E a guarda de "já veio preenchido do banco" olhava só marca/código, deixando
de fora quem tem **só cor** — **222 dos 556** itens do acervo. Agora quem manda
é o `spec_origem`, que é o campo que de fato diz "esta linha já tem
especificação" — e que amanhã vai valer `cliente`.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import so_o_que_roda  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)


def _carimbar():
    """A função REAL, executada — não o texto dela."""
    corpo = so_o_que_roda("_carimbar_spec")
    ns = {"print": lambda *a, **k: None}
    exec("def _carimbar_spec(itens) -> int:\n" + corpo.split("\n", 1)[1], ns)
    return ns["_carimbar_spec"]


class _It:
    """Objeto no formato que a planilha lê."""
    def __init__(self, descricao, **kw):
        self.description = descricao
        self.marca = kw.get("marca", "")
        self.codigo_fabricante = kw.get("codigo_fabricante", "")
        self.cor = kw.get("cor", "")
        self.spec_origem = kw.get("spec_origem", "")


# ══════════════════════════════════════════════════════════════════════════
#  O caso real: "ou similar" tem que sobreviver até a planilha
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("descricao", [
    "Chapa de gesso acartonado Performa (PER) 12,5 mm — Knauf/Placo ou similar",
    "Split hi-wall 12000 BTUs — Carrier ou similar",
    "Cuba de apoio oval pequena — ref. Deca Oval L56.17 ou equivalente",
])
def test_marca_em_aberto_chega_na_planilha_como_referencia(descricao):
    """🚨 Sem isto, o 1º .xlsx fecha a concorrência do arquiteto."""
    import spec_extract
    if not spec_extract.LIBERADO_PRO_CLIENTE:
        pytest.skip("carimbo desligado pro cliente")
    it = _It(descricao)
    assert _carimbar()([it]) == 1
    assert it.spec_origem == "lido:referencia", (
        "carimbou %r — a planilha vai escrever a marca como decisão fechada"
        % it.spec_origem)


def test_controle_positivo_marca_fechada_continua_lido():
    """🧪 Se TUDO virasse referência, o rótulo "(ou similar)" não diria nada —
    e este teste passaria com a função sabotada pra sempre devolver
    'lido:referencia'."""
    import spec_extract
    if not spec_extract.LIBERADO_PRO_CLIENTE:
        pytest.skip("carimbo desligado pro cliente")
    it = _It("Torneira de mesa bica móvel cromado 1167.C.LNK Deca")
    assert _carimbar()([it]) == 1
    assert it.spec_origem == "lido"
    assert (it.marca, it.codigo_fabricante) == ("Deca", "1167.C.LNK")


def test_o_carimbo_nao_pode_ter_o_valor_chapado():
    """🪤 O defeito era uma string literal. Guarda de texto aqui é legítimo:
    é exatamente a forma do erro."""
    corpo = so_o_que_roda("_carimbar_spec")
    assert 'spec_origem = "lido"' not in corpo, (
        "voltou o valor chapado — o retorno de spec_origem() está sendo "
        "jogado fora e o 'ou similar' morre antes da planilha")
    assert "spec_origem(sp)" in corpo or "= origem" in corpo


# ══════════════════════════════════════════════════════════════════════════
#  🚨 Não pisar no que já está no banco — inclusive quem tem SÓ COR
# ══════════════════════════════════════════════════════════════════════════
def test_nao_pisa_em_item_que_ja_tem_so_a_cor():
    """222 dos 556 itens do acervo têm especificação com marca e código
    VAZIOS — só cor. A guarda antiga não via esses."""
    it = _It("Pintura acrílica cor Azul Munsell", cor="Azul Munsell",
             spec_origem="lido")
    assert _carimbar()([it]) == 0
    assert it.cor == "Azul Munsell"


def test_nao_pisa_no_que_o_CLIENTE_escreveu():
    """🚨 Regra nº7, pro dia em que a tela do caderno existir. `cliente` é o
    valor que `models.py` já documenta pro que vem do usuário."""
    it = _It("Torneira de mesa 1167.C.LNK Deca", marca="Docol",
             spec_origem="cliente")
    assert _carimbar()([it]) == 0
    assert it.marca == "Docol", "o motor sobrescreveu a escolha do cliente"


def test_controle_positivo_item_vazio_AINDA_e_carimbado():
    """🧪 O outro lado da guarda: se ela barrasse tudo, o carimbo nunca
    rodaria e os testes de cima passariam sem medir nada."""
    import spec_extract
    if not spec_extract.LIBERADO_PRO_CLIENTE:
        pytest.skip("carimbo desligado pro cliente")
    it = _It("Torneira de mesa bica móvel cromado 1167.C.LNK Deca")
    assert _carimbar()([it]) == 1, "a guarda ficou larga demais e barra tudo"
