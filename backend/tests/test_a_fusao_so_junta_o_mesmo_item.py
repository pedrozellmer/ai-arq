# -*- coding: utf-8 -*-
"""A fusão que fica com a quantidade de UMA linha só junta o MESMO item.

🩸 22/09/2026 — dois casos no mesmo dia, a mesma doença.

- Job 844603fb (planta de pontos de elétrica, 1 página). A passada 2 do
  `_consolidate_items` fundiu 3 tipos de INTERRUPTOR com 3 tipos de TOMADA (as
  descrições dividiam "simples monopolar") e ficou com a quantidade de uma linha
  só. A passada 1 fundiu "Ponto de tomada — H=1,80m" com "— H=1,30m": a chave
  corta tudo depois do " — ". Dos 67 interruptores que a IA contou, a planilha
  ficou com 10; sumiram 5 linhas e 61 un.
- Job f8d8e6d8 (estrutura, 7 pranchas). O concreto 8,5 m³ do poço de sucção
  sumiu dentro do concreto do poço com depósito de areia (pranchas diferentes);
  o 5,6 m³ do radier EL.332.70 dentro do da laje EL.335.60; a fôrma 22 m² de um
  poço dentro da do outro.

📏 Replay nas respostas da IA de 60 dias (llm_cache, 33 jobs de cliente, sem
rede): a passada 2 fazia 435 fusões e 365 delas deixam de acontecer — 103 com
substantivo diferente (massa corrida × pintura, porta × ferragem, piso ×
rejunte), 123 com nomes que se excluem (interruptor duplo × intermediário,
portão de acesso × de saída), 43 com código de legenda diferente (DI.02 ×
DI.08, PA02 × PA04). Das 70 que continuam, a conferência à mão (a do conserto
e a da revisão) acha na maioria a mesma linha lida em duas pranchas ("Forro —
Varanda — a confirmar" × "Forro de gesso liso — Varanda (37,98 m²)"), e deixa
pelo menos 4 em dúvida: ponto de TV × ponto TV+RJ45, administração local de
dois blocos, um perfil de acabamento com nome de produto × o mesmo perfil
chamado só de "strip", o rejunte de mesma referência em duas áreas. Uma 5ª,
errada (bloqueio de madeira da posição 1 × posição 2), a revisão pegou e virou
régua — ver `test_a_fusao_nao_esconde_o_que_juntou.py`.

🔑 A régua (`engine_rules.motivo_para_nao_fundir` + `prova_de_mesmo_item`):
nada pode diferenciar os dois E alguma coisa tem que provar que são o mesmo. Na
dúvida ficam duas linhas — duplicar é um erro que o arquiteto VÊ; apagar, não.

Estes guardas CHAMAM `_consolidate_items` e as réguas de verdade.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import BudgetItem, Confidence  # noqa: E402
from main import _consolidate_items, _apply_post_consolidation_rules  # noqa: E402
from engine_rules import (motivo_para_nao_fundir, prova_de_mesmo_item,  # noqa: E402
                          perfil_de_fusao, assinatura_de_atributos)

_ELE = "Instalações Elétricas e Dados"
_PLANTA = "planta-eletrica.pdf (Planta Baixa — Pavimento Tipo)"
_TECNICA = "planta-eletrica.pdf (Planta Baixa — Área Técnica)"
_CX = "250VCA, em caixa 4x2\""


def mk(desc, qty, unit="un", disc=_ELE, ref=_PLANTA, num="", medido=False):
    return BudgetItem(item_num=num, description=desc, unit=unit, quantity=qty,
                      observations="", ref_sheet=ref,
                      confidence=Confidence("confirmado" if medido else "estimado"),
                      discipline=disc, origem="dxf_geom" if medido else "vision_pdf")


def _planta_de_pontos():
    """As 14 linhas da IA que a fusão do 844603fb misturou (texto da leitura)."""
    return [
        mk("Tomada simples monopolar hexagonal 2P+T-20A Universal, %s — H=0,40m — "
           "conforme legenda de pontos" % _CX, 30, num="1"),
        mk("Tomada simples monopolar hexagonal 2P+T-10A Universal, %s — H=0,40m — "
           "conforme legenda de pontos" % _CX, 40, num="2"),
        mk("Tomada simples monopolar hexagonal 2P+T-10A Universal, %s — H=1,20m — "
           "conforme legenda de pontos" % _CX, 35, num="3"),
        mk("Tomada simples monopolar hexagonal 2P+T-10A Universal, %s — H=2,20m — "
           "conforme legenda de pontos" % _CX, 10, num="4"),
        mk("Tomada simples monopolar hexagonal 2P+T-10A Universal, %s — H=0,40m (dupla "
           "seta — tomada dupla) — conforme legenda de pontos" % _CX, 15, num="5"),
        mk("Interruptor pulsador campainha monopolar 1 tecla, 10A, %s — H=1,20m — "
           "conforme legenda de pontos" % _CX, 4, num="8"),
        mk("Interruptor simples monopolar 1 tecla, 10A, %s — H=1,20m — conforme "
           "legenda de pontos" % _CX, 30, num="10"),
        mk("Interruptor paralelo monopolar 1 tecla, 10A, %s — H=1,20m — conforme "
           "legenda de pontos" % _CX, 15, num="11"),
        mk("Interruptor simples monopolar 2 teclas, 10A, %s — H=1,20m — conforme "
           "legenda de pontos" % _CX, 12, num="12"),
        mk("Interruptor simples monopolar 3 teclas, 10A, %s — H=1,20m — conforme "
           "legenda de pontos" % _CX, 6, num="13"),
        mk("Tomada simples monopolar hexagonal 2P+T-10A, 250VCA, uso em caixa 4x2\", para "
           "luminária de emergência (LE) — conforme legenda de pontos (símbolo LE)", 12,
           num="14"),
        mk("Ponto de tomada para equipamento de TV — CP.01 — H=0,40m — conforme indicação "
           "na planta da área técnica", 2, ref=_TECNICA, num="32"),
        mk("Ponto de tomada — H=1,80m — conforme indicação na planta da área técnica "
           "(\"CP.01 – H=1,80m\")", 2, ref=_TECNICA, num="33"),
        mk("Ponto de tomada — H=1,30m — conforme indicação na planta da área técnica "
           "(\"H=1,30m\")", 2, ref=_TECNICA, num="34"),
    ]


def _q(saida, comeco):
    return sum(i.quantity for i in saida if (i.description or "").startswith(comeco))


# ── 844603fb: a planta de pontos ───────────────────────────────────────────
def test_os_67_interruptores_do_844603fb_continuam_na_planilha():
    entrada = _planta_de_pontos()
    saida = _consolidate_items(entrada)
    assert _q(saida, "Interruptor") == 67, [(i.description[:40], i.quantity) for i in saida]
    assert len(saida) == len(entrada), "nenhuma destas 14 linhas é repetição de outra"
    assert sum(i.quantity for i in saida) == sum(i.quantity for i in entrada)
    assert not any("Fundido" in (i.observations or "") for i in saida)


def test_ponto_de_tomada_a_1_80_e_a_1_30_sao_duas_linhas():
    """A passada 1 (a chave corta tudo depois do " — ") fundia os dois."""
    saida = _consolidate_items(_planta_de_pontos()[-2:])
    alturas = sorted(i.description.split("H=")[1][:4] for i in saida)
    assert alturas == ["1,30", "1,80"], [i.description for i in saida]
    assert [i.quantity for i in saida] == [2, 2]


def test_a_chave_da_passada_1_nao_soma_alturas_diferentes_como_variantes():
    """Sem a altura na chave, as 4 linhas (1 un cada) viravam uma réplica
    "(várias variantes)" de 4 un e as duas alturas sumiam da planilha."""
    entrada = [mk("Tomada 2P+T 10A — H=0,40m — conforme legenda", 1, ref="a.pdf"),
               mk("Tomada 2P+T 10A — H=0,40m — conforme legenda", 1, ref="b.pdf"),
               mk("Tomada 2P+T 10A — H=1,20m — conforme legenda", 1, ref="a.pdf"),
               mk("Tomada 2P+T 10A — H=1,20m — conforme legenda", 1, ref="b.pdf")]
    saida = _consolidate_items(entrada)
    assert not any("variantes" in i.description for i in saida), \
        [(i.description, i.quantity) for i in saida]
    assert sorted(i.description.split("H=")[1][:4] for i in saida) == ["0,40", "1,20"]


def test_demolicao_do_forro_de_dois_banheiros_sao_duas_linhas():
    """Mesma chave, mesma quantidade: a passada 1 ficava com UMA."""
    saida = _consolidate_items([
        mk("Demolição de forro existente (tipo não especificado) — WC Hóspedes", 4, "m²",
           "Demolição e Remoção", "demol.pdf"),
        mk("Demolição de forro existente (tipo não especificado) — WC Bebê", 4, "m²",
           "Demolição e Remoção", "demol.pdf"),
    ])
    assert len(saida) == 2 and sum(i.quantity for i in saida) == 8, \
        [(i.description, i.quantity) for i in saida]


def test_a_altura_entra_na_chave_da_passada_1():
    a = assinatura_de_atributos("Ponto de tomada — H=1,80m — conforme indicação")
    b = assinatura_de_atributos("Ponto de tomada — H=1,30m — conforme indicação")
    assert a != b and ("altura", ("180",)) in a and ("altura", ("130",)) in b, (a, b)


# ── f8d8e6d8: estruturas com nome ──────────────────────────────────────────
_EST = "Complementares"


def _estrutura():
    return [
        mk("Concreto estrutural C30 (fck ≥ 30 MPa), classe de agressividade ambiental "
           "III, relação A/C < 0,55 — fornecimento, lançamento, adensamento e cura — "
           "parede circular do poço de sucção", 8.5, "m³", _EST, "de-004.pdf (Poço)", "1"),
        mk("Concreto estrutural C30 (fck ≥ 30 MPa, relação a/c < 0,55) — para parede "
           "cilíndrica do poço com depósito de areia e bloco para guindaste giratório, "
           "incluindo lançamento, adensamento e cura", 8.5, "m³", _EST,
           "de-005.pdf (Poço com Depósito)", "2"),
        mk("Forma de madeira compensada resinada — fornecimento, montagem, escoramento e "
           "desmontagem — parede circular do poço de sucção (faces interna e externa)",
           22, "m²", _EST, "de-004.pdf (Poço)", "3"),
        mk("Forma de madeira compensada resinada para estruturas circulares — parede "
           "cilíndrica do poço (faces interna e externa) e laje El.236,89, incluindo "
           "escoramento, montagem e desmontagem", 22, "m²", _EST,
           "de-005.pdf (Parede Planta)", "4"),
        mk("Concreto estrutural para radier EL.332.70 — concreto armado fck conforme "
           "projeto estrutural, lançamento e adensamento inclusos", 5.6, "m³", _EST,
           "de-007.pdf (EL.332.70 – PLANTA)", "5"),
        mk("Concreto estrutural para laje EL.335.60 — concreto armado fck conforme "
           "projeto estrutural, lançamento e adensamento inclusos", 5.6, "m³", _EST,
           "de-007.pdf (EL.335.60 – PLANTA)", "6"),
    ]


def test_os_dois_pocos_e_o_radier_do_f8d8_continuam_separados():
    entrada = _estrutura()
    saida = _consolidate_items(entrada)
    assert len(saida) == 6, [(i.description[:50], i.quantity) for i in saida]
    assert round(sum(i.quantity for i in saida if i.unit == "m³"), 2) == 28.2
    assert sum(i.quantity for i in saida if i.unit == "m²") == 44


def test_poco_sem_nome_em_OUTRA_prancha_nao_prova_ser_o_poco_de_succao():
    _, _, forma_a, forma_b, _, _ = _estrutura()
    pa = perfil_de_fusao(forma_a.description, "m²", forma_a.ref_sheet)
    pb = perfil_de_fusao(forma_b.description, "m²", forma_b.ref_sheet)
    assert "succao" in motivo_para_nao_fundir(pa, pb)
    # 🔑 e na MESMA prancha, "o poço" é o da própria folha: aí não bloqueia
    pb_mesma = perfil_de_fusao(forma_b.description, "m²", forma_a.ref_sheet)
    assert "succao" not in motivo_para_nao_fundir(pa, pb_mesma)


# ── as réguas, peça por peça ───────────────────────────────────────────────
def test_cada_regua_reprova_o_par_que_ela_existe_pra_separar():
    pares = {
        "substantivo": ("Massa corrida PVA em paredes internas — 2 demãos",
                        "Pintura látex acrílica em paredes internas — 2 demãos"),
        "corrente": ("Tomada 2P+T 20A em caixa 4x2", "Tomada 2P+T 10A em caixa 4x2"),
        "teclas": ("Interruptor simples 1 tecla 10A", "Interruptor simples 2 teclas 10A"),
        "nivel": ("Concreto — laje EL.332.70", "Concreto — laje EL.335.60"),
        "codigo": ("Divisória interna DI.02 — parede dupla", "Divisória interna DI.08 — parede dupla"),
        "nomes": ("Portão de acesso de veículos — metálico", "Portão de saída de veículos — metálico"),
        "lados": ("Massa corrida — paredes internas", "Massa corrida — paredes externas"),
        "elementos": ("Concreto estrutural — radier", "Concreto estrutural — laje"),
        "ambiente": ("Demolição de forro — WC Hóspedes", "Demolição de forro — WC Bebê"),
        "ambientes": ("Piso — Varanda — a definir", "Piso — Lavabo — a definir"),
        "numeros": ("Circulação 01 — revestimento de piso", "Circulação 03 — revestimento de piso"),
        "rotulo": ("Piso — Banheiro 01 — a definir", "Piso — Banheiro 02 — a definir"),
        "aparelhos": ("Ponto de esgoto para mictório", "Ponto de esgoto — para bacia e lavatório"),
        "cores": ("Pintura acrílica externa — cor CAMURÇA", "Pintura acrílica externa — cor AREIA"),
    }
    for regua, (a, b) in pares.items():
        motivo = motivo_para_nao_fundir(a, b)
        assert motivo.startswith(regua), (regua, motivo, a, b)


def test_um_codigo_em_comum_nao_esconde_o_codigo_que_difere():
    """O modelo "RX-24" dos dois filtros não faz o FX1 virar o FX2."""
    motivo = motivo_para_nao_fundir("Filtro de pressão para piscina — modelo FX1 — RX-24",
                                    "Filtro de pressão para piscina — modelo FX2 — RX-24")
    assert motivo.startswith("codigo"), motivo
    # e com número solto é igual: o "1" em comum não junta o ambiente 9 com o 105
    motivo = motivo_para_nao_fundir("Luminária tipo 1 — ambiente 9 — conforme legenda",
                                    "Luminária tipo 1 — ambiente 105 — conforme legenda")
    assert motivo.startswith("numeros"), motivo


def test_poco_de_succao_e_poco_com_deposito_se_excluem_ate_na_mesma_prancha():
    concreto_a, concreto_b = _estrutura()[:2]
    pa = perfil_de_fusao(concreto_a.description, "m³", "x.pdf")
    pb = perfil_de_fusao(concreto_b.description, "m³", "x.pdf")
    assert motivo_para_nao_fundir(pa, pb).startswith("poco"), motivo_para_nao_fundir(pa, pb)


def test_CONTROLE_a_mesma_linha_lida_duas_vezes_nao_tem_motivo_e_tem_prova():
    vaga = perfil_de_fusao("Forro — Varanda — tipo e acabamento a confirmar com projeto", "m²")
    completa = perfil_de_fusao("Forro de gesso liso com pé solto de 3 cm — Varanda (37,98 m²) "
                               "— com aplicação de pintura látex", "m²")
    assert motivo_para_nao_fundir(vaga, completa) == ""
    assert prova_de_mesmo_item(vaga, completa)


def test_CONTROLE_a_mesma_medida_em_unidade_trocada_prova_sozinha():
    """As palavras aqui NÃO bastam (cobertura 0,4): quem prova é a unidade trocada."""
    a = perfil_de_fusao("Fita de LED tipo A — perfil embutido em sanca", "m²")
    b = perfil_de_fusao("Fita de LED tipo A — linha contínua no forro", "ml")
    c = perfil_de_fusao("Fita de LED tipo A — linha contínua no forro", "m²")
    assert motivo_para_nao_fundir(a, b) == "" and prova_de_mesmo_item(a, b)
    assert not prova_de_mesmo_item(a, c), "sem a troca de unidade, isto não prova nada"
    saida = _consolidate_items([
        mk("Fita de LED tipo A — perfil embutido em sanca", 222.11, "m²", "Iluminação"),
        mk("Fita de LED tipo A — linha contínua no forro", 222.11, "ml", "Iluminação"),
    ])
    assert len(saida) == 1 and saida[0].unit == "ml", [(i.description, i.unit) for i in saida]
    # 🪤 "6 m²" de armário × "6 un" de módulo não é troca de unidade
    assert not prova_de_mesmo_item(perfil_de_fusao("Marcenaria — armário de cozinha", "m²"),
                                   perfil_de_fusao("Marcenaria — módulo MO.AR.01", "un"))


def test_CONTROLE_sem_prova_nao_funde_mesmo_sem_motivo():
    a = perfil_de_fusao("Ponto de detecção de incêndio — acionador manual / sirene")
    b = perfil_de_fusao("Ponto de detecção de incêndio — sensor/detector de fumaça")
    assert motivo_para_nao_fundir(a, b) == ""
    assert not prova_de_mesmo_item(a, b)


# ── o que continua fundindo, e o que a linha diz ───────────────────────────
def test_CONTROLE_a_duplicata_de_verdade_continua_virando_uma_linha():
    saida = _consolidate_items([
        mk("Forro de gesso liso com pé solto de 3 cm — Varanda (37,98 m²) — com aplicação "
           "de pintura látex PVA", 37.98, "m²", "Forros", "forro.pdf (Planta de Forro)"),
        mk("Forro — Varanda — tipo e acabamento a confirmar com projeto de forro", 37.98,
           "m²", "Forros", "revest.pdf (Planta de Revestimento)"),
    ])
    assert len(saida) == 1 and saida[0].quantity == 37.98, [i.description for i in saida]
    assert saida[0].description.startswith("Forro de gesso liso")


def test_a_linha_que_fica_diz_o_que_absorveu():
    saida = _consolidate_items([
        mk("Forro de gesso liso com pé solto de 3 cm — Varanda (37,98 m²)", 37.98, "m²",
           "Forros", "forro.pdf (Planta de Forro)"),
        mk("Forro — Varanda — tipo e acabamento a definir com projeto de forro", 37.98,
           "m²", "Forros", "revest.pdf (Planta de Revestimento)"),
    ])
    obs = saida[0].observations or ""
    assert "Fundido de 2 entradas" in obs, obs          # a marca que a regra 🅓 lê
    assert "absorveu: «Forro — Varanda" in obs and "(revest.pdf)" in obs, obs
    assert "descrições similares" not in obs, obs
    # 🪤 a citação não leva "a definir" pra linha que fica (🅒 e a passada 5 leem isso)
    assert "a definir" not in obs.lower(), obs


def test_a_passada_1_escreve_quantas_vezes_a_linha_apareceu_sem_rebaixar_a_medida():
    saida = _consolidate_items([
        mk("Ralo sifonado 100mm", 7, disc="Instalações Hidráulicas", ref="a.dxf", medido=True),
        mk("Ralo sifonado 100mm", 7, disc="Instalações Hidráulicas", ref="b.dxf", medido=True),
    ])
    assert len(saida) == 1, [i.description for i in saida]
    obs = saida[0].observations or ""
    outra = ({"a.dxf", "b.dxf"} - {saida[0].ref_sheet}).pop()
    assert "apareceu 2 vezes" in obs and ("As outras: %s" % outra) in obs, obs
    assert "fundido de" not in obs.lower() and "consolidado de" not in obs.lower(), obs
    _apply_post_consolidation_rules(saida)
    assert saida[0].confidence == Confidence("confirmado"), saida[0].observations
    # consolidar de novo a mesma linha não repete a nota (a outra cópia vem de uma
    # prancha que ordena ANTES, pra que a linha que fica seja a mesma de novo)
    de_novo = _consolidate_items(saida + [mk("Ralo sifonado 100mm", 7, disc="Instalações "
                                             "Hidráulicas", ref="0.dxf", medido=True)])
    assert len(de_novo) == 1 and de_novo[0] is saida[0], [i.ref_sheet for i in de_novo]
    assert (saida[0].observations or "").count("apareceu") == 1, saida[0].observations


def test_linha_vaga_nao_faz_ponte_entre_dois_interruptores_diferentes():
    saida = _consolidate_items([
        mk("Interruptor 10A — conforme legenda", 6),
        mk("Interruptor duplo 10A — embutido na parede", 6),
        mk("Interruptor intermediário 10A — embutido na parede", 6),
    ])
    descs = [i.description for i in saida]
    assert any("duplo" in d for d in descs) and any("intermediário" in d for d in descs), descs


def test_a_ordem_das_pranchas_nao_muda_o_resultado():
    base = _planta_de_pontos() + _estrutura()
    esperado = sorted((i.description, i.quantity) for i in _consolidate_items(list(base)))
    for semente in (1, 2, 3):
        embaralhado = list(_planta_de_pontos() + _estrutura())
        random.Random(semente).shuffle(embaralhado)
        obtido = sorted((i.description, i.quantity) for i in _consolidate_items(embaralhado))
        assert obtido == esperado, semente


def test_duas_somas_de_variantes_com_o_mesmo_total_nao_viram_uma():
    """A linha "(várias variantes)" perde o código (EQc.01 × EQc.02) na descrição."""
    entrada = ([mk("Frigorífico combinado de encastrar — código EQc.01", 0.75,
                   disc="Complementares", ref="p%d.pdf" % k) for k in range(4)]
               + [mk("Frigorífico de encastrar — código EQc.02", 0.75,
                     disc="Complementares", ref="p%d.pdf" % k) for k in range(4)])
    saida = _consolidate_items(entrada)
    assert sorted(i.quantity for i in saida) == [3.0, 3.0], \
        [(i.description, i.quantity) for i in saida]


def test_as_tres_montagens_de_led_nao_viram_uma_linha():
    """A versão de abril de `test_residuo_3_ledline` fundia as três (regra nº4)."""
    saida = _consolidate_items([
        mk("LED LINE pendurada tipo A", 222.11, "m²", "Iluminação"),
        mk("LED LINE tipo A encastrada", 222.11, "m²", "Iluminação"),
        mk("LED LINE linear tipo A", 222.11, "ml", "Iluminação"),
    ])
    assert len(saida) == 3, [(i.description, i.unit) for i in saida]
