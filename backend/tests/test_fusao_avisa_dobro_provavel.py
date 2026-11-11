# -*- coding: utf-8 -*-
"""Correção do cliente que não casa pelo NOME avisa a provável linha irmã.

🩸 11/11/2026: o cliente corrigiu 14 linhas lidas do PDF e depois anexou o DWG.
A releitura reescreveu os nomes, casou 0 de 14 e acrescentou as 14 no fim com
"a leitura nova não achou esta linha" — falso: pintura 1.732 + 440 m², telhado
354,8 + 1 m², rodapé 309 + 10 m lado a lado. 📏 120 d: 1 de 24 casou.
🔑 FUSAO_AVISO_DOBRO=1 troca a frase e aponta a irmã; com 0 o texto é o de antes.
Nunca junta nem apaga: só avisa.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_fusao_revisao import _carrega, _rev, _linha_pai  # noqa: E402


def _leitura_nova():
    """Os nomes que a leitura do DWG deu no caso real (encurtados)."""
    from models import BudgetItem, Confidence
    d = [("Pintura interna — tinta acrílica (cor e fabricante por definir)", "m²", 1732.3),
         ("Cobertura em telha cerâmica colonial — inclinação 29% a 35%", "m²", 354.81),
         ("Estrutura de madeira para telhado — caibros, ripas e terças", "m²", 354.81),
         ("Rodapé — cerâmico ou madeira (especificação por definir)", "ml", 309.34),
         ("Revestimento cerâmico de parede — banheiros e áreas molhadas", "m²", 88.6),
         ("Piso cerâmico/porcelanato — área interna (especificação por definir)", "m²", 88.6),
         ("Porta de madeira de abrir — folha simples 0,80×2,10 m", "un", 9.0)]
    return [BudgetItem(item_num=str(i), description=a, unit=u, quantity=q,
                       confidence=Confidence.ESTIMADO) for i, (a, u, q) in enumerate(d, 1)]


_CORRECOES = [  # (descrição do pai, unidade, número digitado, irmã esperada ou None)
    ("Pintura látex acrílica em paredes internas — cor e fabricante não especificados", "m²", 440, "Pintura interna"),
    ("Telhado cerâmico colonial — telha cerâmica tipo colonial, inclinação 35%", "m²", 1, "Cobertura em telha"),
    ("Estrutura de madeira para telhado — caibros, ripas, terças e tesouras", "m²", 1, "Estrutura de madeira"),
    ("Rodapé em cerâmica/porcelanato — especificação por definir", "ml", 10, "Rodapé"),
    ("Revestimento cerâmico em paredes de banheiros e cozinhas — especificação", "m²", 6.47, "Revestimento cerâmico de parede"),
    ("Piso cerâmico/porcelanato em banheiro suíte 1 — especificação por definir", "m²", 30, "Piso cerâmico"),
    # 🧪 CONTROLE: mesmo verbo, serviço diferente — NÃO pode apontar irmã
    ("Pintura acrílica em fachadas externas — cor e fabricante não especificados", "m²", 150, None),
    ("Selador acrílico em fachadas externas — uma demão", "m²", 650, None),
    ("Massa corrida PVA em paredes internas — duas demãos", "m²", 200, None),
    ("Calha e rufos em chapa galvanizada — calha meia-cana", "ml", 16, None),
    # 🧪 CONTROLE: nome igual mas unidade de outra família não é irmã
    ("Porta de abrir em madeira 80x210 (P1)", "m²", 15, None),
]


def _roda(monkeypatch, liga):
    revs = [_rev("id-%d" % i) for i in range(len(_CORRECOES))]
    pai = [_linha_pai("id-%d" % i, d, u, q) for i, (d, u, q, _) in enumerate(_CORRECOES)]
    f, _, _ = _carrega(revs=revs, itens_do_pai=pai)
    if liga:
        return f(_leitura_nova(), "pai123", aviso_dobro=True)
    return f(_leitura_nova(), "pai123")      # padrão = desligada


@pytest.mark.parametrize("k", range(len(_CORRECOES)))
def test_com_a_chave_aponta_so_a_irma_certa(monkeypatch, k):
    itens, resumo = _roda(monkeypatch, True)
    desc, _, q, irma = _CORRECOES[k]
    linha = [x for x in itens if x.origem == "revisao_cliente" and x.quantity == q
             and x.description == desc][0]
    if irma:
        assert "PODE REPETIR" in linha.observations and irma in linha.observations
        assert "não achou esta linha" not in linha.observations
    else:
        assert "PODE REPETIR" not in linha.observations
        assert "a leitura nova não tem linha com este nome." in linha.observations


def test_com_a_chave_nada_some_e_nenhum_numero_muda(monkeypatch):
    itens, resumo = _roda(monkeypatch, True)
    assert resumo["acrescentadas"] == len(_CORRECOES) and resumo["casadas"] == 0
    assert resumo["dobro_avisado"] == sum(1 for c in _CORRECOES if c[3])
    assert len(itens) == len(_leitura_nova()) + len(_CORRECOES)
    assert [x.quantity for x in itens[:7]] == [x.quantity for x in _leitura_nova()]


def test_com_a_chave_em_0_o_texto_e_o_de_antes(monkeypatch):
    itens, resumo = _roda(monkeypatch, False)
    rev = [x for x in itens if x.origem == "revisao_cliente"]
    assert len(rev) == len(_CORRECOES) and "dobro_avisado" not in resumo
    assert all("a leitura nova não achou esta linha." in x.observations for x in rev)
    assert not any("PODE REPETIR" in x.observations for x in rev)


def test_a_linha_do_proprio_cliente_nao_vira_irma(monkeypatch):
    """Duas correções parecidas: a 2ª não pode apontar a 1ª (que já é REV.)."""
    revs = [_rev("a"), _rev("b")]
    pai = [_linha_pai("a", "Calha meia-cana galvanizada fachada norte", "ml", 5),
           _linha_pai("b", "Calha meia-cana galvanizada fachada sul", "ml", 7)]
    f, _, _ = _carrega(revs=revs, itens_do_pai=pai)
    itens, resumo = f(_leitura_nova(), "pai123", aviso_dobro=True)
    assert resumo.get("dobro_avisado", 0) == 0


def test_chave_avaliavel_e_registrada():
    import main
    assert "FUSAO_AVISO_DOBRO" in main._CHAVES_AVALIAVEIS
    with open(main.__file__, encoding="utf-8") as fh:
        fonte = fh.read()
    assert "dobro_avisado={int(_fz.get('dobro_avisado') or 0)} " in fonte
    # a avaliação manda: a chave é lida por `_chave_do_job`, não pelo ambiente
    assert '_chave_do_job(job_id, "FUSAO_AVISO_DOBRO") == "1"' in fonte
    assert 'aviso_dobro=_liga_dobro)' in fonte
