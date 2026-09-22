# -*- coding: utf-8 -*-
"""Em projeto de ESTRUTURA, a prancha é lida com o prompt de ESTRUTURA.

🩸 22/09/2026 — job ee801b82 (cliente de 1 dia, NPS 2). Sete PDFs de uma
página de concreto armado: poços, caixa de válvulas, bloco de guindaste, um
pórtico pequeno. Projeto marcado "estrutura". O system era o
SYSTEM_PROMPT_ESTRUTURA ("gere quantitativo de ESTRUTURA — NÃO de
arquitetura"), mas o prompt do USUÁRIO era:

    "⚠ ESTE É UM PROJETO ESTRUTURAL…" + PROMPT_ARQUITETURA inteiro
    (alvenaria, pintura, portas, persianas) + "TIPOLOGIA: ESCRITÓRIO CORPORATIVO"

porque nenhum nome casava padrão de prancha (tipo desconhecido → fallback de
arquitetura) e a tela só oferece tipos de arquitetura. Uma prancha foi lida
como layout novo e saiu com mobilização, limpeza, administração local e
"projeto executivo complementar" — que o forçador de aço ainda virou "1 kg".
Outra respondeu só `kept_elements`, sem item nenhum, e sumiu.

🔑 O conserto: em projeto estrutural, TODA prancha usa o PROMPT_ESTRUTURA,
qualquer que seja o tipo dela, e a dica de tipologia não entra.

📊 Alcance medido em 22/09 (90 dias, sem is_eval): 8 jobs de estrutura com
PDF, 22 PDFs — todos lidos com prompt de arquitetura, porque nada no código
atribuía o tipo ESTRUTURA. Desde 06/09 foram 11 leituras de prancha em
estrutura, e 4 delas (36%) voltaram sem item nenhum, contra 28 de ~374 em
arquitetura.

🧪 O guarda captura o prompt REAL que `analyze_sheet` monta, com um cliente
falso no lugar da IA — nunca procura texto no fonte.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analyzer  # noqa: E402
from models import SheetType  # noqa: E402


class _Sheet:
    def __init__(self, sheet_type, nome="prancha-A.pdf"):
        self.text_content = ""
        self.crops = []
        self.sheet_type = sheet_type
        self.filename = nome


class _Resp:
    stop_reason = "end_turn"

    def __init__(self, texto):
        class _C:
            pass
        _c = _C()
        _c.text = texto
        self.content = [_c]


# Resposta com item: nenhuma releitura, uma chamada só.
_COM_ITEM = ('ok\n```json\n{"items": [{"item_num": "1", "description": '
             '"Concreto C30 — laje de fundo", "unit": "m³", "quantity": 1.35, '
             '"confidence": "estimado", "discipline": "Estrutura"}]}\n```')


def _chamadas(monkeypatch, sheet, **kw):
    """Roda `analyze_sheet` de verdade e devolve o que ela mandou pra IA."""
    capt = []

    def _fake_stream(*a, **k):
        capt.append(k)
        return _Resp(_COM_ITEM)
    monkeypatch.setattr(analyzer, "call_with_retry_stream", _fake_stream)
    analyzer.analyze_sheet(None, sheet, **kw)
    assert capt, "analyze_sheet não chegou a chamar o modelo"
    return capt


def _prompt(chamada):
    """O último bloco de texto do usuário é o prompt da prancha."""
    blocos = chamada["messages"][0]["content"]
    return [b["text"] for b in blocos if b.get("type") == "text"][-1]


# Marcas do que NÃO pode chegar numa prancha de estrutura.
_DE_ARQUITETURA = (
    "## PERSIANAS",                                   # PROMPT_ARQUITETURA
    "## MEDIÇÃO DE PINTURA",                          # PROMPT_ARQUITETURA
    "- Mobilização e desmobilização de obra (un: vb)",  # PROMPT_LAYOUT_NOVO
    "- Proteção de áreas sem intervenção (un: vb)",     # PROMPT_LAYOUT_NOVO
    "TIPOLOGIA DO PROJETO: ESCRITÓRIO CORPORATIVO",     # _TYPOLOGY_HINT office
)


def test_o_caso_ee801b82_nenhuma_das_7_pranchas_recebe_arquitetura(monkeypatch):
    """🩸 O envio do caso, com nomes neutros: seis pranchas que o main passa
    como ARQUITETURA (fallback do tipo desconhecido) e uma que foi lida como
    LAYOUT_NOVO — a que devolveu mobilização e limpeza. Tipologia 'office',
    que é o padrão da tela."""
    envio = [("prancha-%s.pdf" % l, SheetType.ARQUITETURA) for l in "ACDEFG"]
    envio.insert(1, ("prancha-B.pdf", SheetType.LAYOUT_NOVO))
    for nome, tipo in envio:
        ch = _chamadas(monkeypatch, _Sheet(tipo, nome), typology="office",
                       is_structural=True)
        assert len(ch) == 1
        p = _prompt(ch[0])
        for marca in _DE_ARQUITETURA:
            assert marca not in p, (
                "%s (tipo %s) em projeto de estrutura recebeu %r — voltou o "
                "prompt de arquitetura colado no de estrutura"
                % (nome, tipo.value, marca))
        assert p == analyzer.PROMPT_ESTRUTURA, (
            "%s: o prompt da prancha não é o de estrutura" % nome)
        assert ch[0]["system"] == analyzer.SYSTEM_PROMPT_ESTRUTURA


@pytest.mark.parametrize("tipo", list(SheetType))
def test_vale_pra_TODO_tipo_de_prancha_nao_so_o_desconhecido(monkeypatch, tipo):
    """🔑 A decisão: em projeto de estrutura o tipo da prancha não escolhe o
    prompt. A tela só oferece tipos de arquitetura, e nome de prancha de
    estrutura casa palavra de arquitetura ('laje do piso', 'forro')."""
    ch = _chamadas(monkeypatch, _Sheet(tipo), typology="office",
                   is_structural=True, ambiente="banheiro_social")
    assert _prompt(ch[0]) == analyzer.PROMPT_ESTRUTURA, (
        "tipo %s em projeto de estrutura não foi lido com PROMPT_ESTRUTURA"
        % tipo.value)


@pytest.mark.parametrize("tipologia", sorted(analyzer._TYPOLOGY_HINT))
def test_a_dica_de_tipologia_nao_entra_em_estrutura(monkeypatch, tipologia):
    ch = _chamadas(monkeypatch, _Sheet(SheetType.ARQUITETURA),
                   typology=tipologia, is_structural=True)
    assert analyzer._TYPOLOGY_HINT[tipologia] not in _prompt(ch[0]), (
        "a dica de tipologia %r entrou numa prancha de estrutura" % tipologia)


def test_as_irmas_continuam_avisadas_em_estrutura(monkeypatch):
    """O aviso de pranchas irmãs não é de arquitetura: segue valendo."""
    ch = _chamadas(monkeypatch, _Sheet(SheetType.ARQUITETURA),
                   is_structural=True, siblings=["prancha-B.pdf"])
    p = _prompt(ch[0])
    assert "IRMÃS DO MESMO AMBIENTE" in p and p.endswith(analyzer.PROMPT_ESTRUTURA)


def test_o_prompt_de_estrutura_pede_items_no_topo_e_as_tres_unidades():
    p = analyzer.PROMPT_ESTRUTURA
    assert '{"items": [...]' in p and "no TOPO" in p, (
        "o prompt não pede 'items' no topo — foi o aninhamento em "
        "project_data que perdeu os 6 itens de uma prancha do caso")
    for u in ('"m³"', '"m²"', '"kg"'):
        assert u in p
    assert "QUADRO DE QUANTITATIVOS" in p and "RESUMO DE AÇO" in p
    assert "TAXA TÍPICA" in p, "aço por taxa não pode virar número (regra nº3)"
    assert analyzer.PROMPTS_POR_TIPO[SheetType.ESTRUTURA] is p


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — arquitetura continua como era
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_em_arquitetura_o_prompt_e_a_dica_continuam(monkeypatch):
    """Se o ramo de estrutura virasse regra pra todo projeto, este reprova —
    e prova que as marcas acima enxergam o prompt de arquitetura quando ele
    está lá (guarda que não enxerga nada passaria verde em tudo)."""
    ch = _chamadas(monkeypatch, _Sheet(SheetType.ARQUITETURA),
                   typology="office", is_structural=False)
    p = _prompt(ch[0])
    assert analyzer.PROMPT_ARQUITETURA in p
    assert "TIPOLOGIA DO PROJETO: ESCRITÓRIO CORPORATIVO" in p
    assert "## PERSIANAS" in p
    assert ch[0]["system"] == analyzer.SYSTEM_PROMPT


def test_CONTROLE_o_layout_novo_ainda_traz_a_lista_de_preliminares(monkeypatch):
    ch = _chamadas(monkeypatch, _Sheet(SheetType.LAYOUT_NOVO),
                   is_structural=False)
    assert "- Mobilização e desmobilização de obra (un: vb)" in _prompt(ch[0])
