# -*- coding: utf-8 -*-
"""A unidade do item vem do NOME dele, não do contexto da frase.

🩸 14/09/2026 — o corte no parêntese (feito em 23/07) era pouco: o contexto
também vem depois de PREPOSIÇÃO e de TRAVESSÃO, e ali ele estava decidindo a
unidade de meio acervo. Medido em 119 trocas reais de produção:

  · "Sirene de alarme — instalada a 2,20 m DO PISO ACABADO"  un → m²
  · "Interruptor simples — instalação a 120 cm DO PISO..."   un → m²
  · "Curva vertical segmentada PARA ELETROCALHA"             un → ml
  · "Vidro temperado — painéis de JANELAS e ESQUADRIAS"      m² → un

"do piso acabado" é ALTURA DE INSTALAÇÃO e estava virando área; "para
eletrocalha" é o que o acessório serve e virava metro.

📏 Efeito medido: das 119 trocas, as que mudam de GRANDEZA — e que por isso
perdem o número (ver `quantidade_apos_troca_de_unidade`) — caem de **96 para
11, 89% menos linha zerada**. E os casos que motivaram a normalização
continuam todos passando.

🪤 Duas hipóteses minhas morreram antes desta, e as duas por medição: cortar no
travessão resolvia 1 dos 4 casos; "a palavra mais à esquerda vence" resolvia 0,
porque `cabo`, `furo` e `tubulação` não estão em lista nenhuma.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_nucleo = main._nucleo_do_item
_normaliza = main._normalize_unit_for_item


# ── as linhas que saíram ERRADAS em produção ─────────────────────────────
def test_contexto_depois_da_preposicao_nao_decide_mais_a_unidade():
    reais = [
        ("Sirene de alarme de incêndio — instalada a 2,20–3,00 m do piso acabado", "un"),
        ("Interruptor simples — instalação a 120 cm do piso acabado, 220 V", "un"),
        ("Ponto de saída de água / esgoto — h=50 cm do piso acabado", "un"),
        ("Curva vertical externa segmentada para eletrocalha", "un"),
        ("Tampa horizontal para eletrocalha 400mm — bloco s400th", "un"),
        ("Exaustor D.15 — embutido no forro do lavabo", "un"),
        ("Vidro temperado incolor E=6mm — painéis de janelas e esquadrias", "m²"),
        ("Parede de fachada FA.06 — Paredes sob peitoril de janela", "m²"),
        ("Bancada de IS em Silestone série Suede Coral Clay e=20mm", "m²"),
        ("Cabo de distribuição EVA-90° CA — circuitos de tomadas", "ml"),
    ]
    trocados = [(d, u, _normaliza(d, u)[0]) for d, u in reais
                if _normaliza(d, u)[1]]
    assert not trocados, (
        "o contexto da frase ainda está trocando a unidade destas linhas: %r"
        % trocados)


def test_a_altura_de_instalacao_nao_vira_area():
    """"do piso acabado" aparece em 36 linhas da base e, em 31 delas, uma PEÇA
    virou área. É a expressão mais cara do acervo."""
    for d in ("Sensor de presença — 2,80 m do piso acabado",
              "Sinalização de rota de fuga — altura máxima 1,80m do piso acabado",
              "Ponto de gás — saída h=0,60m do piso acabado"):
        nova, trocou = _normaliza(d, "un")
        assert nova == "un" and not trocou, (
            "altura de instalação virou unidade de área: %r → %s" % (d, nova))


# ── controle POSITIVO: a normalização ainda faz o que foi criada pra fazer ──
def test_CONTROLE_o_que_a_normalizacao_existe_para_resolver():
    """🪤 Este é o caso que impede o conserto de virar um "desliga tudo". Se
    qualquer um destes parar de passar, a régua nova não presta: a normalização
    nasceu porque a IA mandava "piso vinílico" em ml."""
    casos = [
        ("Piso vinílico em régua — sala de reunião", "ml", "m²"),
        ("Piso em porcelanato 60x60 — área social", "un", "m²"),
        ("Forro de gesso acartonado liso", "ml", "m²"),
        ("Pintura acrílica sobre massa corrida — paredes internas", "ml", "m²"),
        ("Revestimento cerâmico de parede — banheiros", "ml", "m²"),
        ("Carpete em placa 50x50 — escritório", "un", "m²"),
        ("Rodapé em poliestireno 10cm", "un", "ml"),
        ("Soleira em granito 15cm", "un", "ml"),
        ("Eletrocalha perfurada 100x50mm", "un", "ml"),
        ("Luminária de embutir LED 30x30", "m²", "un"),
        ("Porta de madeira 80x210 — folha lisa", "m²", "un"),
        ("Janela de alumínio 120x100 — correr", "m²", "un"),
        ("Tomada 2P+T 10A — bancada", "ml", "un"),
    ]
    erros = [(d, u, esp, _normaliza(d, u)[0]) for d, u, esp in casos
             if _normaliza(d, u)[0] != esp]
    assert not erros, (
        "a régua do núcleo quebrou o que a normalização existe pra fazer: %r"
        % erros)


# ── o núcleo em si ───────────────────────────────────────────────────────
def test_o_nucleo_para_na_primeira_preposicao():
    assert _nucleo("Sirene de alarme de incêndio") == "Sirene"
    assert _nucleo("Ponto de água para geladeira") == "Ponto"
    assert _nucleo("Curva vertical externa segmentada para eletrocalha") == \
        "Curva vertical externa segmentada"


def test_o_nucleo_para_no_travessao_e_na_virgula():
    assert _nucleo("Exaustor D.15 — embutido no forro") == "Exaustor D.15"
    assert _nucleo("Piso tipo P9, conforme quadro") == "Piso tipo P9"
    assert _nucleo("MONITOR/TV 42\" (visíveis na planta de forro)") == "MONITOR"


def test_verbo_de_servico_na_frente_e_pulado():
    """🪤 Orçamento começa a linha pelo SERVIÇO. Sem pular, o núcleo seria
    "Fornecimento" e a régua calaria nas linhas mais comuns da planilha."""
    assert _nucleo("Fornecimento e instalação de capacho embutido") == \
        "capacho embutido"
    assert _nucleo("Execução de diferença de nível") == "diferença"
    assert _nucleo("Conjunto de ferragens para portas internas") == "ferragens"
    # e o salto tem FIM: frase toda de serviço não entra em laço
    assert _nucleo("Fornecimento de instalação de montagem de execução") is not None


def test_CONTROLE_pintura_e_impermeabilizacao_NAO_sao_pulados():
    """Nestes o serviço É o item e tem unidade própria (m²) — se entrarem na
    lista de verbos, "Pintura acrílica de parede" vira núcleo "acrílica" e a
    linha perde a unidade certa."""
    assert _nucleo("Pintura acrílica de parede") == "Pintura acrílica"
    assert _nucleo("Impermeabilização de laje com manta") == "Impermeabilização"
    assert _normaliza("Pintura látex — paredes internas", "ml")[0] == "m²"


def test_CONTROLE_e_e_ou_nao_cortam_o_nucleo():
    """"Portas e janelas" é um item só com dois nomes — cortar no "e" perderia
    o segundo, e há linhas em que só o segundo casa a palavra-chave."""
    assert "janelas" in _nucleo("Portas e janelas internas em madeira").lower()
    assert _normaliza("Esquadrias e janelas internas", "m²")[0] == "un"


def test_CONTROLE_entrada_vazia_ou_estranha_nao_quebra():
    assert _nucleo("") == ""
    assert _nucleo(None) == ""
    assert _nucleo("—") == "—"
    assert _normaliza("", "un") == ("un", False)
    assert _normaliza(None, "m²") == ("m²", False)


def test_CONTROLE_unidade_especial_continua_intocada():
    for u in ("vb", "%", "mês", "dia", "h"):
        assert _normaliza("Piso vinílico", u) == (u, False)
