# -*- coding: utf-8 -*-
"""Contagem, verba, peso e volume não dizem "medido do desenho".

🩸 22/09/2026 — job 844603fb: 1 PDF de 1 página, planta de pontos elétricos de
um residencial. 26 das 35 linhas diziam ao cliente "Medido do desenho com
escala 1:50 lida do rótulo escrito ao lado do próprio desenho — confira a
escala do seu PDF", e a MESMA célula dizia "Contagem visual estimada". No job
f8d8e6d8 (estrutura), 9 linhas de un e kg com a frase — uma é 1.850 kg de aço
por taxa de 100 kg/m³. Nenhuma foi medida: a geometria do PDF só mede m² de
ambiente e m de parede.

🔑 A frase é o molde que o NOSSO prompt manda a IA escrever — a regra não dizia
em quais itens. O conserto tem duas pontas, e as duas são chamadas aqui:
  · `_regra_da_medicao_sem_prova` — a regra do prompt diz ONDE a frase cabe;
  · `_tira_medido_do_desenho_de_quem_nao_foi_medido` — a IA não obedece
    sempre, então o texto é limpo depois, fora de m²/m.

📏 60 d, sem avaliação: 294 linhas em 16 jobs com a frase fora de m²/m.

🪤 Nomes neutros: repositório público. As observações imitam a FORMA real das
linhas (a frase, o conector, a nota que vem depois), não o texto do cliente.
"""
import ast
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")

_FRASE_VISTA = ("Medido do desenho com escala 1:50 lida do rótulo escrito ao lado "
                "do próprio desenho — confira a escala do seu PDF.")


class _It:
    """Item mínimo: só o que a limpeza lê e escreve."""

    def __init__(self, desc, unit, qty, obs, conf="estimado"):
        self.description, self.unit, self.quantity = desc, unit, qty
        self.observations, self.confidence = obs, conf


def _tem_a_frase(obs):
    return "medido do desenho com escala" in (obs or "").lower()


# ══════════════════════════════════════════════════════════════════════════
#  O caso: a planta de pontos elétricos (job 844603fb)
# ══════════════════════════════════════════════════════════════════════════
def _planilha_de_pontos():
    """35 linhas na forma do job: 24 un + 2 vb com a frase, 1 vb sem, 8 ml."""
    itens = []
    for i in range(24):
        itens.append(_It(
            "Tomada 2P+T 10A H=0,40 m — ponto %d" % i, "un", 10 + i,
            "Contagem visual estimada na planta do pavimento tipo (H=0,40m). "
            "Confirmar com quadro de cargas e projeto executivo. " + _FRASE_VISTA
            + (" | Fundido de 2 entradas com mesma qty %d.0 un — descrições "
               "similares." % (10 + i) if i % 5 == 0 else "")))
    for i in range(2):
        itens.append(_It(
            "Alimentação para equipamento — eletroduto %d" % i, "vb", 1,
            "Item indicado na planta com nota. Bitola a confirmar com diagrama "
            "unifilar. Medido do desenho com escala 1:75 lida do rótulo escrito "
            "ao lado do próprio desenho — confira a escala do seu PDF."))
    itens.append(_It("Verba de quadro", "vb", 1, "Verba sem prancha."))
    for i in range(8):
        itens.append(_It(
            "Eletroduto PVC 3/4\" — trecho %d" % i, "ml", 0,
            "Comprimento NÃO medido (lido de PDF por IA, não da geometria) — "
            "preencha a metragem."))
    return itens


def test_a_planta_de_pontos_perde_as_26_frases_falsas():
    itens = _planilha_de_pontos()
    antes = sum(1 for it in itens if _tem_a_frase(it.observations))
    assert antes == 26, "o cenário não reproduz o caso: %d linhas com a frase" % antes

    limpos = main._tira_medido_do_desenho_de_quem_nao_foi_medido(itens)

    assert limpos == 26, limpos
    sobrou = [it.description for it in itens if _tem_a_frase(it.observations)]
    assert not sobrou, "ainda dizem 'medido do desenho': %s" % sobrou[:3]


def test_o_resto_da_linha_fica_numero_unidade_selo_e_o_que_ela_diz_de_si():
    """🚫 Muda só TEXTO: a contagem continua dizendo que é contagem, a nota da
    fusão continua, e número, unidade e selo não se mexem."""
    itens = _planilha_de_pontos()
    retrato = [(it.quantity, it.unit, it.confidence) for it in itens]
    main._tira_medido_do_desenho_de_quem_nao_foi_medido(itens)

    assert [(it.quantity, it.unit, it.confidence) for it in itens] == retrato
    t0 = itens[0].observations
    assert t0.startswith("Contagem visual estimada"), t0
    assert "Confirmar com quadro de cargas e projeto executivo." in t0, t0
    assert "| Fundido de 2 entradas com mesma qty 10.0 un" in t0, t0
    assert "  " not in t0 and ". ." not in t0 and ".." not in t0, repr(t0)
    vb = itens[24].observations
    assert vb == ("Item indicado na planta com nota. Bitola a confirmar com "
                  "diagrama unifilar."), repr(vb)


def test_CONTROLE_linha_de_metro_fica_com_a_honestidade_de_area():
    """m²/m é o que a geometria do PDF mede — lá quem decide o texto é
    `_apply_area_honesty`, e esta limpeza não pode passar por cima."""
    piso = _It("Piso vinílico", "m²", 95.3,
               "Área dos ambientes medidos geometricamente: 95,3 m². "
               "Medido do desenho com escala 1:100 lida da caixa de recorte do "
               "PDF — confira a escala do seu PDF.")
    rodape = _It("Rodapé", "m", 40.0, "Perímetro. " + _FRASE_VISTA)
    obs = (piso.observations, rodape.observations)
    assert main._tira_medido_do_desenho_de_quem_nao_foi_medido([piso, rodape]) == 0
    assert (piso.observations, rodape.observations) == obs


# ══════════════════════════════════════════════════════════════════════════
#  O caso da estrutura (job f8d8e6d8): kg por taxa, minúscula, nota depois
# ══════════════════════════════════════════════════════════════════════════
def test_aco_por_taxa_deixa_de_dizer_medido_e_continua_dizendo_taxa():
    aco = _It("Armadura em aço CA-50 e CA-60 — estruturas enterradas", "kg", 1850,
              "Estimativa por taxa de consumo: ~18,5m³ × taxa 100kg/m³ = 1.850kg. "
              "Confirmar com projeto estrutural complementar. Medido do desenho "
              "com escala 1:25 lida do rótulo escrito ao lado do próprio desenho "
              "— confira a escala do seu PDF.")
    sapata = _It("Armação de aço para sapatas", "kg", 52,
                 "Estimativa: taxa de armação ≈ 20kg/m³ × 2,59m³ ≈ 52kg. Confirmar "
                 "com projeto estrutural de armação. medido do desenho com escala "
                 "1:50 lida do rótulo escrito ao lado do próprio desenho — confira "
                 "a escala do seu PDF. ⚠ Este serviço aparece em 3 pranchas do "
                 "projeto (prancha-a, prancha-b). Esta linha vem da prancha dela.")
    tampa = _It("Tampa de concreto armado para poço", "un", 1,
                "1 tampa identificada na planta. Medido do desenho com escala 1:25 "
                "lida do rótulo escrito ao lado do próprio desenho — confira a "
                "escala do seu PDF.")
    volume = _It("Concreto C30 — laje de fundo", "m³", 0,
                 "Dimensões lidas da planta. " + _FRASE_VISTA)
    itens = [aco, sapata, tampa, volume]
    assert main._tira_medido_do_desenho_de_quem_nao_foi_medido(itens) == 4
    for it in itens:
        assert not _tem_a_frase(it.observations), it.observations
    assert "taxa 100kg/m³" in aco.observations and aco.quantity == 1850
    assert "⚠ Este serviço aparece em 3 pranchas" in sapata.observations, (
        "a nota de outra frente foi junto: " + sapata.observations)
    assert sapata.observations.startswith("Estimativa: taxa de armação")


def test_a_frase_no_MEIO_da_sentenca_sai_so_a_oracao():
    """Forma real: "… na prancha — medido do desenho … PDF. Incluir …". Sai o
    trecho do meio; o ponto é da frase de fora e fica."""
    t = ("Área de parede não calculada por falta de cota de pé-direito na "
         "prancha — medido do desenho com escala 1:75 lida do carimbo — confira "
         "a escala do seu PDF. Incluir área de parede após confirmação.")
    assert main._sem_medido_do_desenho(t) == (
        "Área de parede não calculada por falta de cota de pé-direito na "
        "prancha. Incluir área de parede após confirmação.")


def test_a_frase_SEM_o_confira_para_no_ponto_e_nao_come_a_nota_seguinte():
    """Forma real (14 de 300 linhas): a IA encurta o molde e para em "lida do
    carimbo." — a limpeza tem que parar ali, sem levar o aviso que vem depois."""
    t = ("Confirmar com projeto de marcenaria. Medido do desenho com escala 1:25 "
         "lida do carimbo. ⚠ Este serviço aparece em 3 pranchas do projeto "
         "(prancha-a, prancha-b). | Fundido de 2 entradas.")
    assert main._sem_medido_do_desenho(t) == (
        "Confirmar com projeto de marcenaria. ⚠ Este serviço aparece em 3 "
        "pranchas do projeto (prancha-a, prancha-b). | Fundido de 2 entradas.")


def test_linha_que_era_SO_a_frase_diz_de_onde_veio_o_numero():
    it = _It("Verba de instalação", "vb", 1,
             "Medido do desenho com escala 1:50 lida do carimbo da prancha — "
             "confira a escala do seu PDF.")
    assert main._tira_medido_do_desenho_de_quem_nao_foi_medido([it]) == 1
    assert it.observations == main._FRASE_NUMERO_DA_LEITURA
    assert "não é medição" in it.observations


def test_CONTROLE_a_negacao_verdadeira_fica():
    """'não medido do desenho' é o que o motor escreve do pé-direito informado —
    verdade, não afirmação de medida."""
    t = ("Pé-direito informado pelo cliente — não medido do desenho com escala "
         "nenhuma. Descontar vãos.")
    it = _It("Chapisco", "un", 3, t)
    assert main._tira_medido_do_desenho_de_quem_nao_foi_medido([it]) == 0
    assert it.observations == t


# ══════════════════════════════════════════════════════════════════════════
#  A regra do prompt: onde a frase cabe
# ══════════════════════════════════════════════════════════════════════════
def _regra():
    fonte, ressalva = main._frase_da_escala_sem_prova("vista")
    return main._regra_da_medicao_sem_prova(50, fonte, ressalva), fonte


def test_a_regra_diz_EM_QUAIS_itens_a_procedencia_cabe():
    regra, _ = _regra()
    assert "Só na observação de item de ÁREA (m²) ou de COMPRIMENTO (m)" in regra, regra
    for proibido in ("contagem (un)", "verba (vb)", "peso (kg)", "volume (m³)"):
        assert proibido in regra, (proibido, regra)
    assert "NÃO escreva essa frase" in regra, regra
    # regra dura nº1 continua escrita
    assert "NUNCA 'confirmado'" in regra, regra


def test_o_molde_da_regra_e_o_mesmo_que_as_duas_limpezas_reconhecem():
    """🪤 Texto é dominó: se a regra mudar a frase, a limpeza da honestidade
    (`_limpa_afirmacao_de_medida`) e a desta frente param de reconhecer o que
    a IA escreve — calado. O molde sai da PRÓPRIA regra, não daqui."""
    regra, fonte = _regra()
    ini = regra.index("'medido do desenho")
    molde = regra[ini + 1:regra.index("'", ini + 1)]
    assert molde == ("medido do desenho com escala 1:50 lida %s — confira a "
                     "escala do seu PDF" % fonte), molde
    linha = "Contagem visual estimada. " + molde[0].upper() + molde[1:] + "."
    assert main._sem_medido_do_desenho(linha) == "Contagem visual estimada."
    assert not _tem_a_frase(main._limpa_afirmacao_de_medida(linha))


# ══════════════════════════════════════════════════════════════════════════
#  INTEGRAÇÃO — o process_job usa as duas pontas, na ordem certa
# ══════════════════════════════════════════════════════════════════════════
def _chamadas_no_process_job():
    arv = ast.parse(io.open(_MAIN_PY, encoding="utf-8").read())
    pj = next(n for n in arv.body
              if isinstance(n, ast.FunctionDef) and n.name == "process_job")
    linhas = {}
    for n in ast.walk(pj):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            linhas.setdefault(n.func.id, []).append(n.lineno)
    return pj, linhas


def test_o_process_job_monta_a_regra_pela_funcao():
    """🪤 Guarda de FONTE, assumido: prova que a regra que vai pro prompt é a
    que os testes acima executam, e que o molde antigo não voltou inline."""
    pj, linhas = _chamadas_no_process_job()
    assert "_regra_da_medicao_sem_prova" in linhas, "a regra voltou a ser montada inline"
    for n in ast.walk(pj):
        if isinstance(n, ast.JoinedStr):
            lit = "".join(p.value for p in n.values
                          if isinstance(p, ast.Constant) and isinstance(p.value, str))
            assert "escreva a procedência" not in lit, (
                "molde de procedência inline no process_job (linha %s)" % n.lineno)


def test_a_limpeza_roda_depois_da_honestidade_e_antes_do_resgate_de_comprimento():
    _, linhas = _chamadas_no_process_job()
    limpa = linhas.get("_tira_medido_do_desenho_de_quem_nao_foi_medido")
    assert limpa and len(limpa) == 1, "a limpeza não é chamada no process_job"
    honestidade = min(linhas["_apply_area_honesty"])
    resgate = min(linhas["_corrigir_comprimento_medido"])
    assert honestidade < limpa[0] < resgate, (honestidade, limpa[0], resgate)
