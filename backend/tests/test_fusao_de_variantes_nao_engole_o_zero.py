# -*- coding: utf-8 -*-
"""Quatro linhas zeradas específicas valem mais que uma genérica zerada.

🩸 03/09/2026, caso EDVALDO (job `d2bedf82`, o maior lead B2B). Ele reprocessou
o MESMO arquivo e a entrega piorou: 11 itens viraram 7, e as quatro linhas de
concreto — Lajes, Vigas, Pilares, Escadas — viraram UMA, chamada "Concreto
estrutural fck=30MPa (várias variantes)", com quantidade 0.

📏 A verdade de campo desta casa: **87% do que o cliente corrige é PREENCHER
linha zerada** (96 correções, 6 clientes, 3 semanas). Fundir quatro zeros tira
exatamente a especificidade que ele usaria: "fôrma de pilar" ele sabe
responder; "várias variantes" não.

🔑 O QUE ESTE CASO *NÃO* FOI, e vale registrar porque eu quase afirmei errado:
a consolidação **não** comeu o número medido. A regra exige `max(qtys) < 2,0`;
se alguma das quatro tivesse os 12,72 m³ da rodada anterior, o grupo nem teria
sido fundido. O número sumiu na EXTRAÇÃO — não-determinismo da IA, que já está
medido em [[project_motor_nao_deterministico_20260808]].

🪤 E a pergunta "foi a fusão ou foi a IA?" custou uma consulta ao banco e uma
leitura de código pra responder, porque a observação dizia só o TOTAL. Agora
ela diz de ONDE veio.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main as m                                   # noqa: E402


class _It:
    def __init__(self, desc, qty, unit="m³", num="1", disc="Estrutura"):
        self.description, self.quantity, self.unit = desc, qty, unit
        self.item_num, self.discipline = num, disc
        self.observations, self.confidence, self.origem = "", "estimado", ""
        self.ref_sheet, self.marca, self.codigo_fabricante = "p.dxf", "", ""
        self.cor, self.spec_origem = "", ""


def _concretos(qtds):
    """As quatro linhas reais do job d2bedf82."""
    nomes = ["Lajes", "Vigas", "Pilares", "Escadas"]
    return [_It("Concreto estrutural fck=30MPa — %s (pavimento tipo)" % n, q,
                num=str(i + 1)) for i, (n, q) in enumerate(zip(nomes, qtds))]


# ── O conserto ─────────────────────────────────────────────────────────────
def test_quatro_linhas_ZERADAS_nao_viram_uma_generica():
    """🩸 O caso do Edvaldo."""
    saida = m._consolidate_items(_concretos([0, 0, 0, 0]))
    assert len(saida) == 4, (
        "quatro zeros específicos viraram %d linha(s) — o cliente perde a "
        "especificidade que usaria pra preencher" % len(saida))
    assert not any("várias variantes" in (i.description or "") for i in saida)


def test_CONTROLE_fusao_que_SOMA_algo_continua_acontecendo():
    """🧪 O conserto não pode desligar a consolidação: réplica por
    departamento com quantidade de verdade continua virando uma linha."""
    saida = m._consolidate_items(_concretos([0.5, 0.5, 0.5, 0.5]))
    assert len(saida) == 1, "a consolidação por variante parou de funcionar"
    assert "várias variantes" in saida[0].description
    assert saida[0].quantity == 2.0


def test_CONTROLE_um_zero_no_meio_de_numeros_nao_dispensa_a_fusao():
    """Se o total é maior que zero, funde — mesmo com zeros no grupo."""
    saida = m._consolidate_items(_concretos([1.2, 0, 0, 0]))
    assert len(saida) == 1 and saida[0].quantity == 1.2


def test_CONTROLE_grupo_com_numero_GRANDE_nunca_foi_fundido():
    """🔑 A prova de que a consolidação NÃO comeu os 12,72 do Edvaldo: a regra
    exige max < 2,0. Se este teste mudar, a minha conclusão sobre o caso dele
    deixa de valer e precisa ser refeita."""
    saida = m._consolidate_items(_concretos([12.72, 0, 0, 0]))
    assert len(saida) == 4, (
        "grupo com 12,72 passou a ser fundido — a explicação do caso Edvaldo "
        "(a IA não produziu, a fusão não comeu) precisa ser reavaliada")


# ── O rastro que faltava ───────────────────────────────────────────────────
def test_a_observacao_DIZ_de_onde_veio():
    """🩸 A pergunta 'foi a fusão ou foi a IA?' não tinha resposta na linha."""
    saida = m._consolidate_items(_concretos([0.5, 0.5, 0.5, 0.5]))
    obs = saida[0].observations
    assert "Veio de:" in obs, obs
    for nome in ("Lajes", "Vigas", "Pilares", "Escadas"):
        assert nome in obs, "o resumo não cita %r: %r" % (nome, obs)
    assert "0.5" in obs, "o resumo não traz as quantidades consumidas"


def test_o_resumo_NAO_estoura_a_observacao_com_grupo_grande():
    """🪤 Um grupo de 40 réplicas encheria a observação e empurraria o resto
    pra fora da tela. Corta e diz quantos ficaram."""
    grupo = [_It("Luminária — sala %d" % i, 0.5, unit="un", num=str(i))
             for i in range(12)]
    r = m._resumo_do_grupo(grupo)
    assert "(+8)" in r, r
    assert len(r) < 220, "resumo longo demais: %d chars" % len(r)


def test_CONTROLE_o_resumo_sobrevive_a_item_torto():
    """Item sem descrição ou com quantidade não-numérica não pode derrubar a
    consolidação inteira."""
    class _Torto:
        description = None
        quantity = "abc"
    r = m._resumo_do_grupo([_Torto(), _It("Viga", 1.0)])
    assert "?" in r and "Viga" in r
