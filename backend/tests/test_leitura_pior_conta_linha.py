# -*- coding: utf-8 -*-
"""A releitura que traz MENOS linha também tem que avisar.

🚨 25/08/2026, ao vivo. O cliente recebeu a planilha com **0 medido** e o aviso
"o arquivo não traz o que a medição de estrutura precisa — envie a prancha de
fôrma/armação". **Ele leu e fez exatamente isso**: anexou os 2 DWG do
estrutural.

A releitura foi de **208 itens para 15**. Noventa e três por cento a menos. E
o aviso de "esta leitura veio pior" **não disparou**, porque ele só olhava
MEDIDOS:

    perdeu = max(0, antes_med - n_medidos)   # 0 - 0 = 0
    if perdeu > 0:                           # nunca entra

Com zero medido dos dois lados, o guarda fica mudo — justo no caso em que o
cliente FEZ o que a gente pediu e recebeu menos.

🪤 O pior detalhe: a função já recebia `n_itens`, já calculava `antes_itens` e
já imprimia os dois no log — **mas só dentro do `if perdeu > 0`**. O dado
estava na mão e não era usado.

Medido no acervo (as 4 releituras com histórico de versão):

    208 → 15   (93% a menos)  0 → 0 medidos   ← passava batido
     58 → 41   (29% a menos)  0 → 0 medidos   ← passava batido
    102 → 90   (12% a menos) 24 → 25 medidos  ← não é caso: mediu MAIS
    119 → 147  (cresceu)     80 → 92          ← melhorou

Daí o limiar: **≥20% E ≥10 linhas**.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import corpo_de  # noqa: E402


def _comparar(linhas_da_versao):
    """Roda a função REAL com o banco injetado."""
    import json as _js

    class _Resp:
        def __init__(self, payload):
            self._p = _js.dumps(payload).encode("utf-8")

        def read(self):
            return self._p

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _UR:
        Request = staticmethod(lambda *a, **k: type("R", (), {"add_header": lambda s, *x: None})())

        @staticmethod
        def urlopen(req, timeout=15):
            return _Resp(linhas_da_versao)

    ns = {"SUPABASE_URL": "http://x", "SUPABASE_KEY": "k",
          "SUPABASE_SERVICE_ROLE_KEY": "k", "print": lambda *a, **k: None,
          "_log_error": lambda *a, **k: None, "__import__": __import__}
    corpo = corpo_de("_comparar_com_versao_anterior")
    corpo = corpo.replace("import urllib.request as _ur, json as _js", "pass")
    ns["_ur"], ns["_js"] = _UR, _js
    exec(compile(corpo, "cmp", "exec"), ns)
    return ns["_comparar_com_versao_anterior"]


def _versao(n_itens, n_medidos, versao=1):
    return ([{"versao": versao, "confidence": "confirmado"}] * n_medidos
            + [{"versao": versao, "confidence": "estimado"}] * (n_itens - n_medidos))


# ══════════════════════════════════════════════════════════════════════════
#  O caso real de hoje
# ══════════════════════════════════════════════════════════════════════════
def test_208_para_15_com_zero_medido_AVISA():
    """🚨 O cliente mandou o CAD que a gente pediu e recebeu 93% menos."""
    fn = _comparar(_versao(208, 0))
    r = fn("6e9649a7", 0, 15)
    assert r["frase"], (
        "208 itens viraram 15 e o cliente não foi avisado — foi exatamente "
        "isto que aconteceu hoje ao vivo")
    assert "15" in r["frase"] and "208" in r["frase"]
    assert r["perdeu_itens"] == 193


def test_58_para_41_tambem_avisa():
    """O outro caso do acervo: 29% a menos, zero medido dos dois lados."""
    fn = _comparar(_versao(58, 0))
    assert fn("70556e26", 0, 41)["frase"]


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE: não pode virar ruído
# ══════════════════════════════════════════════════════════════════════════
def test_queda_pequena_NAO_avisa():
    """102 → 90 (12%) com os medidos SUBINDO de 24 pra 25 não é piora."""
    fn = _comparar(_versao(102, 24))
    assert not fn("e4954250", 25, 90)["frase"]


def test_leitura_que_melhorou_NAO_avisa():
    fn = _comparar(_versao(119, 80))
    assert not fn("e1c48ed7", 92, 147)["frase"]


def test_poucas_linhas_a_menos_NAO_avisa():
    """Queda de 3 linhas num projeto de 12 é 25%, mas 3 linhas não assusta
    ninguém — o piso de 10 linhas existe pra isso."""
    fn = _comparar(_versao(12, 0))
    assert not fn("x", 0, 9)["frase"]


# ══════════════════════════════════════════════════════════════════════════
#  O aviso antigo (medidos) continua funcionando
# ══════════════════════════════════════════════════════════════════════════
def test_perder_MEDIDO_continua_avisando():
    """Caso Amanda (10/08): 47 medidos viraram 28 e o e-mail dizia
    'planilha atualizada'."""
    fn = _comparar(_versao(102, 47))
    r = fn("349e75a5", 28, 100)
    assert "A MENOS" in r["frase"] and "28" in r["frase"] and "47" in r["frase"]
    assert r["perdeu_medidos"] == 19


def test_perder_medido_E_linha_diz_as_duas_coisas():
    """🪤 Um aviso só, com os dois fatos — em vez de dois avisos disputando
    espaço no e-mail (que tem teto de 6)."""
    fn = _comparar(_versao(200, 40))
    r = fn("x", 10, 100)
    assert "medi" in r["frase"].lower()
    assert "linhas a menos" in r["frase"]


@pytest.mark.parametrize("antes,depois", [(0, 0), (5, 5)])
def test_sem_versao_anterior_nao_inventa_aviso(antes, depois):
    fn = _comparar([])
    assert fn("x", depois, antes) == {}
