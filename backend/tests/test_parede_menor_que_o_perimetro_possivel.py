# -*- coding: utf-8 -*-
"""O motor mediu MENOS parede do que a geometria permite — e não disse nada.

🩸 04/09/2026, no PRIMEIRO projeto da Caroline (Bolognesi, "Parque Aurora").
O motor apurou **17,18 m** de parede numa casa de **46,79 m²**, e daí saíram a
alvenaria (44,67 m² = 17,18 × 2,60), o chapisco, o reboco e o rodapé dela.

🔑 Entre todos os retângulos de mesma área, o QUADRADO tem o menor perímetro.
Logo nenhuma edificação pode ter menos parede que `4·√área`:

        4 · √46,79  =  27,36 m        contra        17,18 m medidos

Faltam **59%** — e isso IGNORANDO as paredes internas, que só aumentam o
mínimo. Não é regra de bolso nem benchmark de obra (que a regra dura nº3
proíbe usar pra corrigir): é geometria. O limite é uma impossibilidade, não uma
expectativa.

🔑 MEDIDO na base antes de escrever: dos **19** projetos de cliente em que a
gente mede parede em metro, **3 (16%)** estão abaixo do mínimo —
`humberto.oliveira@` 88% abaixo (25/06), `marcioeng72@` 42% (30/08) e a
Caroline 59% (hoje). **Onze itens BRANCOS** saíram desses três.

🪤 SÓ APONTA e REBAIXA. Não corrige o número: inventar a parede que falta seria
exatamente o que a regra nº3 proíbe. O que muda é o selo (número que não pode
estar certo não é "✓ MEDIDO") e o aviso, que agora diz onde procurar — a
parede quase sempre está num layer que o motor não reconheceu.
"""
import ast
import io
import os

import pytest

from engine_rules import parede_abaixo_do_minimo as _abaixo

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

# Os TRÊS casos reais medidos no banco em 04/09/2026.
_REAIS = [
    ("caroline.passos (Parque Aurora)", 17.18, 46.79),
    ("humberto.oliveira", 34.65, 264.54),
    ("marcioeng72", 49.51, 309.75),
]


@pytest.mark.parametrize("quem,parede,area", _REAIS)
def test_os_casos_REAIS_sao_pegos(quem, parede, area):
    impossivel, minimo = _abaixo(parede, area)
    assert impossivel, (
        "%s deixou de ser acusado: %.2f m de parede numa área de %.2f m² "
        "(mínimo %.2f m)" % (quem, parede, area, minimo))
    assert minimo > parede


def test_projeto_com_parede_farta_NAO_e_acusado():
    """CONTROLE: acusar quem está certo é pior que não acusar ninguém."""
    for parede, area in ((60.0, 46.79), (120.0, 264.54), (200.0, 309.75)):
        impossivel, _ = _abaixo(parede, area)
        assert not impossivel, (
            "%.1f m de parede em %.1f m² é folgado e foi acusado" % (parede, area))


def test_o_minimo_e_o_perimetro_do_quadrado():
    """A conta tem que ser essa, e não um palpite calibrado."""
    _, minimo = _abaixo(1.0, 100.0)
    assert abs(minimo - 40.0) < 0.01, (
        "o mínimo de uma área de 100 m² é 4×√100 = 40 m; veio %.2f" % minimo)
    _, m2 = _abaixo(1.0, 46.79)
    assert abs(m2 - 27.36) < 0.01


def test_a_folga_existe_e_e_pequena():
    """🪤 O limite é exato só pro quadrado perfeito SEM parede interna, e
    medição tem ruído. Sem folga, planta quase quadrada viraria alarme falso."""
    area = 46.79
    _, minimo = _abaixo(1.0, area)
    assert not _abaixo(minimo, area)[0], "no mínimo exato não pode acusar"
    assert not _abaixo(minimo * 0.96, area)[0], "4% abaixo ainda é ruído"
    assert _abaixo(minimo * 0.90, area)[0], "10% abaixo TEM que acusar"
    # e a folga não salva nenhum dos casos reais
    for _quem, parede, ar in _REAIS:
        assert _abaixo(parede, ar)[0]


def test_nao_avalia_o_que_nao_da_pra_avaliar():
    for parede, area in ((0, 46.79), (17.18, 0), (None, None), ("x", "y"),
                         (-5, 46.79), (17.18, -1)):
        assert _abaixo(parede, area) == (False, 0.0) or not _abaixo(parede, area)[0]


# ══════════════════════════════════════════════════════════════════════════
#  O motor tem que APLICAR — e só rebaixar
# ══════════════════════════════════════════════════════════════════════════
def _bloco():
    i = _FONTE.index("from engine_rules import (parede_abaixo_do_minimo")
    return _FONTE[i:i + 3800]


def test_o_motor_consulta_a_regra():
    chamou = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "_par_min"
                 for n in ast.walk(ast.parse(_FONTE)))
    assert chamou, "o motor parou de conferir o mínimo de parede"


def test_o_motor_REBAIXA_o_selo():
    b = _bloco()
    assert "_CfP.ESTIMADO" in b, (
        "item derivado de parede impossível voltou a poder sair com ✓ MEDIDO")
    assert 'if _cfp == "confirmado":' in b


def test_o_motor_NUNCA_corrige_o_numero():
    """🚨 Regra nº3: ratio/benchmark só ALERTA. Inventar a parede que falta
    seria o defeito que esta regra existe pra denunciar."""
    b = _bloco()
    for proibido in (".quantity =", ".quantity=", "quantity = _min_per",
                     "quantity = _maior"):
        assert proibido not in b, (
            "o bloco passou a ESCREVER quantidade (%r) — ele só pode apontar"
            % proibido)


def test_o_cliente_e_avisado_na_LINHA_e_no_projeto():
    b = _bloco()
    assert "menos parede do que o mínimo" in b, (
        "sumiu o aviso na linha — é onde o cliente lê o número")
    assert "PAREDE INCOMPLETA" in b, "sumiu o aviso de topo do projeto"
    assert "layer" in b, (
        "o aviso parou de dizer ONDE procurar; sem isso ele é só má notícia")


def test_o_alarme_e_CRITICO():
    b = _bloco()
    assert 'severity="critical"' in b, (
        "parede impossível virou log comum — some no meio do bookkeeping")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — antes não havia julgamento nenhum
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_sem_a_regra_os_tres_casos_passavam():
    def _regra_ANTIGA(_parede, _area):
        return False, 0.0        # não existia conferência

    passavam = [q for q, p, a in _REAIS if not _regra_ANTIGA(p, a)[0]]
    assert len(passavam) == 3, "controle mal montado"
    pega = [q for q, p, a in _REAIS if _abaixo(p, a)[0]]
    assert len(pega) == 3, (
        "a regra de hoje não cobre os três casos reais que a motivaram — "
        "escapariam %s" % [q for q, p, a in _REAIS if not _abaixo(p, a)[0]])
