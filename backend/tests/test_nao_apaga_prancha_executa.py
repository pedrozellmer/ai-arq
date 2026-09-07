# -*- coding: utf-8 -*-
"""O consolidador RODA e nenhuma prancha e apagada (caso cliente-14).

Guarda por EXECUCAO: a versao de fonte (no arquivo irmao) so procurava as
palavras `losers` e `winner = max(group` no corpo da passada 6.

🔬 07/09/2026 — LACUNA FECHADA. A passada 6 tem SEIS saidas
`pass6.extend(group); continue`, e este arquivo exercitava so a ULTIMA (tres
itens, mesma unidade m2, mesma descricao). Trocar `extend` por `extend(group[:1])`
em qualquer uma das outras cinco apagava prancha do mesmo jeito com o guarda
verde — e as outras cinco sao onde moram os dois casos de cliente que deram
nome a este arquivo:

  · grandeza  → cliente-14: metro LINEAR venceu metro QUADRADO e tres pranchas
                (DEMOLIR-CONSTRUIR, LAYOUT, LEVANTAMENTO) sumiram da planilha;
  · _pode_fundir → cliente-20: 2 pranchas x 6 bitolas = 3.028 kg viravam 508 kg,
                porque o Ø16 sempre vencia por ter a maior quantidade.

Agora cada saida tem o seu caso, e o teste distingue POR QUAL delas o grupo
saiu: so a ultima escreve a observacao "aparece em N pranchas". Sem isso, seis
fixtures poderiam estar todas caindo na mesma porta.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from models import BudgetItem, Confidence  # noqa: E402
from main import _consolidate_items  # noqa: E402

# A descricao real do caso cliente-14 (job d5e073cf).
ALVENARIA = "Alvenaria de vedação — levantamento de parede"

#: A frase que SO a ultima saida escreve — e o carimbo da porta.
_AVISO_DA_ULTIMA = "aparece em"


def _it(desc, unit, qty, prancha, conf="confirmado", disc="Alvenaria", obs=""):
    return BudgetItem(item_num="", description=desc, unit=unit, quantity=qty,
                      observations=obs, ref_sheet=prancha,
                      confidence=Confidence(conf), discipline=disc)


def _tres_pavimentos():
    """MESMA grandeza, três pranchas — o grupo que chega até o fim da passada."""
    return [_it(ALVENARIA, "m²", 819.06, "DEMOLIR-CONSTRUIR"),
            _it(ALVENARIA, "m²", 810.36, "LAYOUT"),
            _it(ALVENARIA, "m²", 73.05, "PAV-SUPERIOR")]


#: (rótulo da saída, itens de entrada, a última saída marcou a observação?)
_CASOS = [
    # ── saída 1: grupo de um só (noun diferente) ───────────────────────────
    ("grupo de um item só", [
        _it("Alvenaria de vedação — parede", "m²", 100.0, "ARQ-01"),
        _it("Contrapiso regularizado", "m²", 50.0, "ARQ-02", disc="Pisos"),
    ], False),

    # ── saída 2: `len(ref_sheets) < 2` — tudo na MESMA prancha ─────────────
    ("mesma prancha", [
        _it("Alvenaria de vedacao bloco ceramico", "m²", 100.0, "LAYOUT"),
        _it("Alvenaria estrutural bloco concreto", "m²", 55.5, "LAYOUT"),
    ], False),

    # ── saída 3: `not sig_common` — mesmo substantivo, nada mais em comum ──
    # 🪤 Duas esquadrias com código próprio: "porta" é a única palavra que as
    # une, e duas portas de pranchas diferentes são duas portas.
    ("sem palavra significativa em comum", [
        _it("P01 - porta de madeira 80x210", "un", 12.0, "ARQ-01",
            disc="Esquadrias"),
        _it("P02 - porta de correr em vidro", "un", 3.0, "ARQ-02",
            disc="Esquadrias"),
    ], False),

    # ── saída 4: `_pode_fundir` — o aço da cliente-20 ──────────────────────
    # 🩸 3.028 kg viravam 508 kg: o Ø16 vencia por ter a maior quantidade.
    ("atributo que identifica (bitola)", [
        _it("Armadura CA-50 bitola 8.0mm", "kg", 508.0, "EST-01",
            disc="Estrutura"),
        _it("Armadura CA-50 bitola 16.0mm", "kg", 2520.0, "EST-02",
            disc="Estrutura"),
    ], False),

    # ── saída 5: grandeza — o caso cliente-14 ──────────────────────────────
    # 🩸 metro LINEAR venceu metro QUADRADO; grandezas que nem deveriam disputar.
    ("grandezas diferentes (m² × m)", [
        _it(ALVENARIA, "m²", 819.06, "DEMOLIR-CONSTRUIR"),
        _it(ALVENARIA, "m", 255.06, "LEVANTAMENTO"),
    ], False),

    # ── saída 6: a última — mantém tudo E avisa o cliente ──────────────────
    ("três pavimentos, mesma grandeza", _tres_pavimentos(), True),
]


def _digital(itens):
    """(prancha, unidade, quantidade) de cada linha — o que não pode sumir."""
    return sorted((i.ref_sheet or "", (i.unit or "").lower(),
                   round(float(i.quantity or 0), 2)) for i in itens)


@pytest.mark.parametrize("rotulo,entrada,marca_a_observacao",
                         _CASOS, ids=[c[0] for c in _CASOS])
def test_NENHUMA_saida_da_passada_6_apaga_prancha(rotulo, entrada,
                                                  marca_a_observacao):
    """🚨 O invariante central, nas SEIS portas: nenhuma leitura é apagada."""
    entrada = list(entrada)
    antes = _digital(entrada)
    saida = _consolidate_items(list(entrada))
    assert len(saida) == len(entrada), (
        "saída %r: %d de %d linhas sobreviveram — a passada voltou a eleger "
        "vencedor e apagar prancha" % (rotulo, len(saida), len(entrada)))
    assert _digital(saida) == antes, (
        "saída %r: as linhas mudaram.\n  antes: %s\n  depois: %s"
        % (rotulo, antes, _digital(saida)))

    # 🔑 A porta por onde o grupo saiu: só a ÚLTIMA escreve a observação. Sem
    # esta metade, as seis fixtures poderiam estar caindo todas na mesma porta
    # e a cobertura seria imaginária.
    marcadas = [i for i in saida if _AVISO_DA_ULTIMA in (i.observations or "")]
    if marca_a_observacao:
        assert len(marcadas) == len(saida), (
            "saída %r: %d de %d linhas receberam o aviso de repetição — o "
            "cliente precisa saber que o serviço aparece em mais de uma prancha"
            % (rotulo, len(marcadas), len(saida)))
    else:
        assert not marcadas, (
            "saída %r: o grupo desceu até a última porta (recebeu o aviso de "
            "repetição) em vez de sair pela sua — a fixture parou de cobrir o "
            "que dizia cobrir" % rotulo)


def test_a_passada_6_NAO_elege_vencedor_nem_descarta():
    """🚨 O caso cliente-14 escrito por extenso: três pavimentos, três linhas."""
    entrada = _tres_pavimentos()
    saida = _consolidate_items(entrada)
    assert len(saida) == 3, (
        "%d de 3 linhas sobreviveram — a passada voltou a eleger vencedor e "
        "apagar pavimento" % len(saida))
    qtds = sorted(round(float(i.quantity), 2) for i in saida)
    assert qtds == [73.05, 810.36, 819.06], (
        "as quantidades mudaram: %s — alguma medição foi perdida ou somada" % qtds)
    assert {i.ref_sheet for i in saida} == {"DEMOLIR-CONSTRUIR", "LAYOUT",
                                            "PAV-SUPERIOR"}, (
        "uma prancha inteira sumiu da planilha")


def test_o_aviso_da_ultima_saida_NOMEIA_as_pranchas():
    """Conteúdo, não presença: o aviso serve pro arquiteto conferir se são
    trechos diferentes da obra — sem os nomes das pranchas ele não confere
    nada."""
    saida = _consolidate_items(_tres_pavimentos())
    obs = saida[0].observations or ""
    assert "3 pranchas" in obs, obs
    for prancha in ("DEMOLIR-CONSTRUIR", "LAYOUT", "PAV-SUPERIOR"):
        assert prancha in obs, (
            "o aviso não cita a prancha %s: %r" % (prancha, obs))


def test_CONTROLE_o_guarda_REPROVA_uma_saida_que_descarta():
    """🧪 Controle positivo na própria régua: se `_consolidate_items` devolvesse
    só o primeiro de cada grupo, `_digital` acusaria — não é uma comparação
    que passa por vacuidade."""
    entrada = _tres_pavimentos()
    assert _digital(entrada[:1]) != _digital(entrada)
    assert len(_digital(entrada)) == 3
