# -*- coding: utf-8 -*-
"""A fusão por quantidade igual — o que a revisão de 22/09 achou na 1ª versão do conserto.

🩸 22/09/2026 — revisão do conserto dos jobs 844603fb e f8d8e6d8 (a fusão que fica
com a quantidade de UMA linha só junta o MESMO item). Replay offline da
`_consolidate_items` sobre as respostas da IA de 60 dias (llm_cache, 33 jobs de
cliente, 7.455 itens crus, sem is_eval):

- F1. A nota nova da passada 1 dizia "Esta linha apareceu N vezes... As outras:
  <prancha>" — e a passada 1 agrupa pela CHAVE (o começo da descrição), não pela
  descrição: 157 das 163 fusões dela têm texto diferente. Quando a fusão era
  errada ("Ralo — Lavabo 01" × "Ralo — Banho de Serviço", 5a19e1b8; "Comando 1a"
  × "Comando 1b", 5ef3fc6d), a nota afirmava que era a mesma linha e escondia o
  item que sumiu.
- F2. Efeito indireto na passada 5 (bf72d192): separar PA01/PA02 aumentou o balde
  das portas da passada 3, a fração com "a definir" caiu abaixo dos 60%, o balde
  saiu da proteção e a passada 5 engoliu portas específicas (cor, tipo de folha)
  numa linha "Itens de portas e ferragens a especificar".
- F3. A assinatura na chave partia um grupo de 4+ linhas ZERADAS (que a regra de
  03/09 mantém inteiro) em pedaços menores, e cada pedaço fundia: 15 fusões e 16
  linhas zeradas a menos no replay — a linha que o cliente preenche.
- F4. "posição 1" × "posição 2" de um bloqueio de madeira (os números soltos se
  cancelavam) e a medida métrica entre colchetes ("[762mm]" × "[775mm]").
- F5. Sete sabotagens do revisor sobreviviam: o limiar 0,60, a citação levando
  "medido", a altura "a X m do piso", a escolha da linha que fica na passada 1,
  "algum par prova" × "todos", o guarda antigo em todo grupo.
- F6. O `:g` da nota arredondava: "mesma quantidade (13851 m²)" numa linha de
  13.850,95.

Estes guardas CHAMAM `_consolidate_items` e as réguas de verdade, com nomes neutros.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import BudgetItem, Confidence  # noqa: E402
from main import _consolidate_items, _apply_post_consolidation_rules, _qtd_na_nota  # noqa: E402
from engine_rules import (motivo_para_nao_fundir, prova_de_mesmo_item,  # noqa: E402
                          perfil_de_fusao, cobertura_fusao)


def mk(desc, qty, unit="un", disc="Forros", ref="a.pdf", medido=False):
    return BudgetItem(item_num="", description=desc, unit=unit, quantity=qty,
                      observations="", ref_sheet=ref,
                      confidence=Confidence("confirmado" if medido else "estimado"),
                      discipline=disc, origem="dxf_geom" if medido else "vision_pdf")


def _descs(saida):
    return [(i.description, i.unit, i.quantity) for i in saida]


# ── F1: a nota da passada 1 diz o que juntou ───────────────────────────────
def _forro_lido_duas_vezes(medido=False):
    """Mesma chave ("Forro de gesso"), textos diferentes, a mesma quantidade."""
    return [
        mk("Forro de gesso — Varanda — tipo e acabamento a confirmar com o projeto de forro",
           37.98, "m²", ref="revest.pdf (p2 · Revestimentos)", medido=medido),
        mk("Forro de gesso — Varanda, liso com tabica metálica", 37.98, "m²",
           ref="forro.pdf (p1 · Forro)", medido=medido),
    ]


def test_a_passada_1_com_texto_diferente_diz_o_que_juntou():
    saida = _consolidate_items(_forro_lido_duas_vezes(medido=True))
    assert len(saida) == 1, _descs(saida)
    obs = saida[0].observations or ""
    assert "Juntei 2 linhas com a mesma quantidade (37,98 m²)" in obs, obs
    assert "«Forro de gesso — Varanda — tipo e acabamento a confirmar" in obs, obs
    assert "(revest.pdf)" in obs and "Confira se era o mesmo item" in obs, obs
    # 🪤 só com texto IDÊNTICO a nota pode dizer que a linha "apareceu N vezes"
    assert "apareceu" not in obs, obs
    # e sem as marcas que a regra 🅓 lê: a medição que ficou não é rebaixada
    assert "fundido de" not in obs.lower() and "consolidado de" not in obs.lower(), obs
    _apply_post_consolidation_rules(saida)
    assert saida[0].confidence == Confidence("confirmado"), saida[0].observations


def test_consolidar_de_novo_nao_repete_a_nota_de_texto_diferente():
    saida = _consolidate_items(_forro_lido_duas_vezes())
    de_novo = _consolidate_items(saida + [_forro_lido_duas_vezes()[0]])
    assert len(de_novo) == 1 and de_novo[0] is saida[0], _descs(de_novo)
    assert (de_novo[0].observations or "").count("Juntei") == 1, de_novo[0].observations


def test_a_passada_1_fica_com_a_linha_que_diz_mais_do_item():
    """A mais LONGA é a vaga ("tipo e acabamento a confirmar com o projeto")."""
    saida = _consolidate_items(_forro_lido_duas_vezes())
    assert len(saida) == 1 and saida[0].description.startswith(
        "Forro de gesso — Varanda, liso"), _descs(saida)


def test_ralo_do_lavabo_e_do_banho_de_servico_sao_duas_linhas():
    """5a19e1b8: mesma chave ("Ralo linear"), 1 un cada — ficava UMA, e a nota escondia a outra."""
    saida = _consolidate_items([
        mk("Ralo linear — Lavabo 01 — fornecimento e instalação", 1,
           disc="Instalações Hidráulicas", ref="h.pdf"),
        mk("Ralo linear — Banho de Serviço — fornecimento e instalação", 1,
           disc="Instalações Hidráulicas", ref="h.pdf"),
    ])
    assert len(saida) == 2, _descs(saida)
    assert motivo_para_nao_fundir("Ralo linear — Lavabo 01", "Ralo linear — Banho de Serviço") \
        .startswith("ambientes")
    # CONTROLE: "banho" e "banheiro" são o MESMO cômodo — o sinônimo não vira conflito
    assert motivo_para_nao_fundir("Ralo linear — Banho social — fornecimento",
                                  "Ralo linear — Banheiro social — fornecimento") == ""


def test_comando_1a_e_comando_1b_sao_dois_equipamentos():
    """5ef3fc6d: "1a" × "1b" de um sistema DALI, 1 un cada, fundiam."""
    saida = _consolidate_items([
        mk("Controle de iluminação — Comando 1a (16S) — sistema DALI", 1,
           disc="Iluminação", ref="e.pdf"),
        mk("Controle de iluminação — Comando 1b (6S) — sistema DALI", 1,
           disc="Iluminação", ref="e.pdf"),
    ])
    assert len(saida) == 2, _descs(saida)
    # CONTROLE: o ordinal "1ª categoria" (um lado só) não é rótulo — c378477f, a
    # mesma escavação lida em duas pranchas, deixava de fundir com a 1ª versão disto
    a = perfil_de_fusao("Escavação manual de cavas para sapatas — solo de 1ª categoria", "m³")
    b = perfil_de_fusao("Escavação manual de cavas para sapatas — 20 sapatas (P1 a P20)", "m³")
    assert motivo_para_nao_fundir(a, b) == "" and prova_de_mesmo_item(a, b)


# ── F4: posição e medida entre colchetes ───────────────────────────────────
def test_o_bloqueio_da_posicao_1_e_o_da_posicao_2_sao_duas_linhas():
    assert motivo_para_nao_fundir("Bloqueio de madeira para armário — posição 1",
                                  "Bloqueio de madeira para armário — posição 2").startswith("rotulo")
    assert motivo_para_nao_fundir("Bloqueio de madeira para armário — altura 2'-6\" [762mm]",
                                  "Bloqueio de madeira para armário — altura 2'-6 1/2\" [775mm]") \
        .startswith("medida_mm")
    saida = _consolidate_items([
        mk("Bloqueio de madeira para fixação de armário à parede; posição 1: altura 2'-6\" "
           "[762mm]", 2, "ml", "Marcenaria", "d.pdf (p15 · Elevações)"),
        mk("Bloqueio de madeira para fixação de armário à parede; posição 2: altura 2'-6 1/2\" "
           "[775mm]", 2, "ml", "Marcenaria", "d.pdf (p15 · Elevações)"),
    ])
    assert len(saida) == 2 and sum(i.quantity for i in saida) == 4, _descs(saida)


# ── F3: zero igual não é prova de dobro (regra de 03/09) ───────────────────
def _pinturas(q):
    return [
        mk("Pintura acrílica fosca — teto sobre rebaixo de drywall", q, "m²", "Revestimentos", "m.pdf"),
        mk("Pintura acrílica fosca — teto sobre laje", q, "m²", "Revestimentos", "m.pdf"),
        mk("Pintura acrílica fosca — parede H=2,80m", q, "m²", "Revestimentos", "m.pdf"),
        mk("Pintura acrílica fosca — parede H=3,00m", q, "m²", "Revestimentos", "m.pdf"),
    ]


def test_quatro_linhas_zeradas_da_mesma_chave_ficam_as_quatro():
    """A assinatura (H=2,80 × H=3,00) partia o grupo e as duas de teto fundiam."""
    saida = _consolidate_items(_pinturas(0))
    assert len(saida) == 4, _descs(saida)
    assert not any("mesma quantidade" in (i.observations or "") for i in saida)


def test_CONTROLE_as_mesmas_pinturas_com_quantidade_as_de_teto_viram_uma():
    """Prova que o cenário funde se não for zero — a régua acha que é a mesma linha."""
    saida = _consolidate_items(_pinturas(5))
    assert len(saida) == 3, _descs(saida)


# ── F2: a passada 5 não engole porta de balde com atributo em conflito ─────
_PF = "Portas e Ferragens"


def _porta(desc):
    return mk(desc, 1, "un", _PF, "portas.pdf (p1 · Planta)")


def test_as_portas_especificas_do_bf72d192_nao_viram_itens_a_especificar():
    """PA01/PA02 separados, 7 portas no balde da passada 3: 3 de 7 com "a definir"
    (< 60%) tirava o balde da proteção, e a passada 5 engolia as três."""
    saida = _consolidate_items([
        _porta("Porta de entrada social — folha dupla, cor azul — ferragem a definir"),
        _porta("Porta de serviço — folha simples, cor azul — ferragem a definir"),
        _porta("Porta de garagem — folha dupla, cor azul — a definir"),
        _porta("Porta de alumínio de correr 2 folhas, acabamento branco — PA01 — 1,68 × 2,14 m"),
        _porta("Porta de alumínio de correr 2 folhas, acabamento branco — PA02 — 1,68 × 2,14 m"),
        _porta("Porta de madeira PM-01 — folha lisa"),
        _porta("Porta de madeira PM-02 — folha lisa"),
    ])
    descs = [i.description for i in saida]
    assert len(saida) == 7, descs
    assert not any(d.startswith("Itens de portas") for d in descs), descs
    assert sum(i.quantity for i in saida) == 7


def test_CONTROLE_sem_atributo_em_conflito_a_passada_5_segue_juntando_o_vago():
    saida = _consolidate_items([
        _porta("Porta de madeira PM-01 — folha lisa"),
        _porta("Porta de madeira — folha lisa, batente de madeira"),
        _porta("Porta de alumínio de correr — 2 folhas, acabamento branco"),
        _porta("Porta de entrada social — folha dupla, cor azul — ferragem a definir"),
        _porta("Porta de serviço — folha simples, cor azul — ferragem a definir"),
    ])
    descs = [i.description for i in saida]
    assert any(d.startswith("Itens de portas e ferragens a especificar") for d in descs), descs


# ── F5: o que a sabotagem do revisor mostrou que não estava preso ──────────
def test_o_limiar_de_cobertura_separa_0_57_de_0_71():
    """📏 Replay: abaixo de 0,60 começam os pares diferentes que nenhuma outra régua
    pega (acionador manual × detector, 0,57); entre 0,60 e 0,75, dobros de verdade."""
    a = perfil_de_fusao("Ponto de detecção de incêndio — acionador manual endereçável de vidro")
    b = perfil_de_fusao("Ponto de detecção de incêndio — detector óptico de fumaça endereçável")
    assert 0.55 <= cobertura_fusao(a, b) < 0.60 and motivo_para_nao_fundir(a, b) == ""
    assert not prova_de_mesmo_item(a, b)
    c = perfil_de_fusao("Transporte de material excedente (bota-fora) — caçamba estacionária", "m³")
    d = perfil_de_fusao("Transporte de material excedente (bota-fora) — caminhão basculante", "m³")
    assert 0.60 <= cobertura_fusao(c, d) < 0.75 and motivo_para_nao_fundir(c, d) == ""
    assert prova_de_mesmo_item(c, d)
    incendio = _consolidate_items([
        mk(a["desc"], 6, disc="Incêndio e Segurança", ref="i.pdf"),
        mk(b["desc"], 6, disc="Incêndio e Segurança", ref="j.pdf"),
    ])
    assert len(incendio) == 2, _descs(incendio)
    bota_fora = _consolidate_items([
        mk(c["desc"], 12, "m³", "Serviços Preliminares", "k.pdf"),
        mk(d["desc"], 12, "m³", "Serviços Preliminares", "l.pdf"),
    ])
    assert len(bota_fora) == 1, _descs(bota_fora)


def test_a_citacao_do_absorvido_nao_leva_medido_pra_linha_estimada():
    """Regra nº1: a linha fundida é ESTIMADA; "medido" da outra não viaja pra observação."""
    saida = _consolidate_items([
        mk("Forro de gesso liso com pé solto de 3 cm — Varanda (37,98 m²)", 37.98, "m²",
           ref="forro.pdf"),
        mk("Forro — Varanda — medido na planta", 37.98, "m²", ref="revest.pdf"),
    ])
    assert len(saida) == 1, _descs(saida)
    obs = saida[0].observations or ""
    assert "absorveu: «Forro — Varanda" in obs, obs
    assert "medid" not in obs.lower(), obs


def test_tomada_a_0_30_e_a_1_10_do_piso_sao_duas_linhas():
    assert motivo_para_nao_fundir("Tomada 2P+T 10A a 0,30 m do piso",
                                  "Tomada 2P+T 10A a 1,10 m do piso").startswith("altura")
    saida = _consolidate_items([
        mk("Tomada 2P+T 10A a 0,30 m do piso", 12, disc="Instalações Elétricas e Dados"),
        mk("Tomada 2P+T 10A a 1,10 m do piso", 12, disc="Instalações Elétricas e Dados"),
    ])
    assert len(saida) == 2, _descs(saida)


def test_tres_leituras_da_mesma_linha_viram_uma_quando_a_do_meio_prova():
    """Basta ALGUM par provar (e nenhum par ter motivo): a vaga não cabe na completa,
    mas as duas cabem na do meio."""
    a, b, c = (mk("Forro — Varanda", 37.98, "m²", ref="a.pdf"),
               mk("Forro de gesso — Varanda — liso com tabica", 37.98, "m²", ref="b.pdf"),
               mk("Forro de gesso liso com tabica e sanca — pintura látex PVA", 37.98, "m²",
                  ref="c.pdf"))
    pa, pc = perfil_de_fusao(a.description, "m²"), perfil_de_fusao(c.description, "m²")
    assert not prova_de_mesmo_item(pa, pc), "o cenário exige um par SEM prova"
    saida = _consolidate_items([a, b, c])
    assert len(saida) == 1 and "Fundido de 3 entradas" in (saida[0].observations or ""), \
        _descs(saida)


def test_o_guarda_antigo_nao_segura_o_dobro_do_lado_que_nao_conflita():
    """fck 25 × fck 30 na mesma chave: o fck 25 fica, e o fck 30 lido em duas pranchas
    vira uma linha (antes o grupo inteiro ficava, com o dobro).
    🪤 1,5 m³ de propósito: com 2 ou mais a passada 2 tira o dobro de novo e o guarda
    antigo da passada 1 não faz diferença — foi assim que a 1ª versão deste teste
    deixou a sabotagem viver."""
    saida = _consolidate_items([
        mk("Concreto para vigas — fck 25 MPa", 1.5, "m³", "Estrutura", "a.pdf"),
        mk("Concreto para vigas — fck 30 MPa", 1.5, "m³", "Estrutura", "a.pdf"),
        mk("Concreto para vigas — fck 30 MPa", 1.5, "m³", "Estrutura", "b.pdf"),
    ])
    assert sorted(i.description for i in saida) == ["Concreto para vigas — fck 25 MPa",
                                                     "Concreto para vigas — fck 30 MPa"], \
        _descs(saida)


# ── F6: a quantidade da nota não arredonda ─────────────────────────────────
def test_a_quantidade_da_nota_sai_inteira_e_em_pt_br():
    assert _qtd_na_nota(13850.95) == "13.850,95"
    assert _qtd_na_nota(1000000.0) == "1.000.000"
    assert _qtd_na_nota(30.0) == "30" and _qtd_na_nota(0.75) == "0,75"
    saida = _consolidate_items([
        mk("Contrapiso — térreo", 13850.95, "m²", "Pisos e Rodapés", "a.pdf"),
        mk("Contrapiso de argamassa — térreo", 13850.95, "m²", "Pisos e Rodapés", "b.pdf"),
    ])
    assert len(saida) == 1, _descs(saida)
    assert "(13.850,95 m²)" in (saida[0].observations or ""), saida[0].observations
    igual = _consolidate_items([mk("Contrapiso — térreo", 13850.95, "m²", "Pisos e Rodapés", r)
                                for r in ("a.pdf", "b.pdf")])
    assert "(13.850,95 m²)" in (igual[0].observations or ""), igual[0].observations
