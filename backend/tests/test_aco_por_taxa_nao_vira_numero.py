# -*- coding: utf-8 -*-
"""Peso de aço calculado por TAXA (kg/m³, kg/m²) não entra como número.

🩸 22/09/2026 — job ee801b82 (7 PDFs de estrutura, cliente de 1 dia). Numa
prancha SEM quadro de ferros, a IA escreveu 294 + 215 + 485 + 751 = 1.745 kg
"estimado por taxa de consumo típica de 100 kg/m³ aplicada ao volume de
concreto" — o mesmo aço que as listas de ferros das outras pranchas já traziam
(1.573,8 kg lidos), e 100 vezes um volume que o próprio motor zerou. No dia
seguinte, os mesmos arquivos (f8d8e6d8) deram mais 2.114 kg assim, com a frase
"Medido do desenho com escala 1:25" colada. kg não passa pela honestidade de
área, então nada tocava nessas linhas: 53% do aço com número era índice.

🔑 Regra nº3: razão típica ALERTA, nunca vira número. O CONSERTO: a linha fica
em branco (continua estimada), e a frase diz por quê e qual era a conta.

🪤 A menção à taxa NÃO basta. "Soma dos quadros de ferragens … Taxa média
ponderada ≈ 141,71 kg/m³" é aço de LISTA com a taxa como conferência — zerar
isso seria apagar leitura legítima. O controle abaixo cobra.

📏 Alcance medido (22/09, 90 dias, sem avaliação, kg fora do CAD): 22 linhas
com número em 7 jobs citam taxa/índice/consumo; 14 fora deste caso.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_REF = "prancha-B.pdf (DE-X)"


class _Item:
    def __init__(self, desc, unit, qty, obs="", origem="vision_pdf"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.observations = obs
        self.ref_sheet = _REF
        self.origem = origem
        self.confidence = "estimado"


def _taxa(qty, vol):
    return _Item("Armadura CA-50/CA-60 — Estrutura", "kg", qty,
                 "Estimado por taxa de consumo típica de 100 kg/m³ aplicada ao "
                 "volume de concreto armado (%sm³). Não há quadro/resumo de aço "
                 "nesta prancha." % vol)


def _listas_do_caso():
    """O aço de LISTA do ee801b82 — o que tem que sobrar."""
    return [
        _Item("Armadura CA-50 ø8,0 mm — estrutura", "kg", 582,
              "Peso calculado a partir do comprimento total LIDO do quadro RESUMO AÇO "
              "CA-50 da prancha: CTot(ø8mm) = 1473,3 m × 0,395 kg/m = 581,95 kg."),
        _Item("Aço CA-50 ø8mm — armadura total da prancha", "kg", 306,
              "Valor copiado diretamente do RESUMO AÇO CA-50 da prancha: bitola 8mm, "
              "CTot=764,9m, PTot=306kg."),
        _Item("Armadura CA-50 — total geral (Ø6,3 + Ø8 + Ø10mm)", "kg", 432.2,
              "Calculado a partir do RESUMO AÇO CA-50 da prancha (CTot lidos)."),
        _Item("Armadura CA-60 — total geral (Ø5mm — estribos)", "kg", 54.6,
              "CTot = 354,4m × 0,154 = 54,6kg. CTot lido do quadro."),
        _Item("Tela soldada Q335", "kg", 199, "RESUMO TELA DE AÇO: Área=37 m², PTot=199 kg."),
    ]


def test_o_caso_os_1745_kg_por_taxa_ficam_em_branco_e_as_listas_ficam():
    taxa = [_taxa(294, "2,94"), _taxa(215, "2,15"), _taxa(485, "4,85"), _taxa(751, "7,51")]
    listas = _listas_do_caso()
    n = main._zera_peso_por_taxa(taxa + listas)
    assert n == 4
    assert [t.quantity for t in taxa] == [0, 0, 0, 0]
    assert round(sum(i.quantity for i in listas), 1) == 1573.8, (
        "o aço de LISTA não pode ser tocado: %r" % [i.quantity for i in listas])
    t = taxa[0]
    assert str(getattr(t.confidence, "value", t.confidence)) == "estimado"
    assert t.observations.startswith("Em branco: peso por TAXA"), t.observations[:80]
    assert "294,00 kg" in t.observations, "a conta da leitura tem que ficar escrita"
    assert "taxa de consumo típica de 100 kg/m³" in t.observations, (
        "o texto da IA fica: é a procedência da conta")


def test_a_taxa_do_dia_seguinte_perde_tambem_o_medido_do_desenho():
    """f8d8e6d8: a mesma taxa, e o nosso prompt fez a IA escrever 'Medido do
    desenho com escala 1:25' numa conta de tabela."""
    it = _Item("Armadura das estruturas", "kg", 1850,
               "Estimativa por taxa de consumo: volume total de concreto estrutural "
               "estimado ~18,5m³ × taxa 100kg/m³ = 1.850kg. Taxa de 100kg/m³ é "
               "referência de livro. Medido do desenho com escala 1:25 lida do rótulo "
               "escrito ao lado do próprio desenho — confira a escala do seu PDF.")
    assert main._zera_peso_por_taxa([it]) == 1
    assert it.quantity == 0
    assert "medido do desenho" not in it.observations.lower()
    for obs, q in (("Estimativa: taxa de armação ≈ 60kg/m³ para viga × (1,46+1,46)m³ ≈ 175kg.", 175),
                   ("ESTIMADO. Não há quadro de aço nestas pranchas. Taxa 80 kg/m³ adotada.", 2000),
                   ("ESTIMADO. Calculado pela taxa típica de 10 kg/m² aplicada à área.", 29250)):
        it = _Item("Armadura", "kg", q, obs)
        assert main._zera_peso_por_taxa([it]) == 1, obs
        assert it.quantity == 0


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES POSITIVOS — o que NÃO pode ser zerado
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_aco_de_LISTA_que_cita_a_taxa_como_conferencia_fica():
    it = _Item("Armadura total — pilares", "kg", 472.9,
               "Soma confirmada dos quadros de ferragens (com +10%): G1 = 102,8 kg + "
               "G2 = 102,8 kg + G3 = 267,3 kg. Total = 472,9 kg. Taxa média ponderada: "
               "G1/G2 ≈ 141,71 kg/m³; G3 ≈ 220,40 kg/m³.")
    # 🪤 esta cita a taxa com o verbo de adoção — só a prova de LISTA a salva
    conf = _Item("Armadura das sapatas", "kg", 500,
                 "Peso lido do quadro de aço da prancha: 500 kg. Taxa resultante "
                 "85 kg/m³ adotada só como conferência.")
    assert main._zera_peso_por_taxa([it, conf]) == 0
    assert it.quantity == 472.9 and conf.quantity == 500


def test_CONTROLE_numero_do_cliente_e_outra_unidade_nao_se_tocam():
    cli = _Item("Armadura", "kg", 900, "Estimado por taxa de 100 kg/m³.",
                origem="revisao_cliente")
    vol = _Item("Concreto", "m³", 8.5, "Estimado por taxa de consumo típica.")
    assert main._zera_peso_por_taxa([cli, vol]) == 0
    assert cli.quantity == 900 and vol.quantity == 8.5


def test_rodar_de_novo_nao_empilha_a_frase():
    it = _taxa(294, "2,94")
    main._zera_peso_por_taxa([it])
    antes = it.observations
    assert main._zera_peso_por_taxa([it]) == 0
    assert it.observations == antes


# ══════════════════════════════════════════════════════════════════════════
#  O CALL SITE: a régua certa que ninguém chama não conserta nada
# ══════════════════════════════════════════════════════════════════════════
def _fatia_do_aco():
    """Do fim da chamada da honestidade até o fim do bloco das réguas do aço —
    o trecho REAL do `process_job`, recortado por âncora."""
    import io
    import textwrap
    _backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    linhas = io.open(os.path.join(_backend, "main.py"), encoding="utf-8").read().splitlines(True)
    ini = [k for k, l in enumerate(linhas)
           if l.rstrip("\n") == "            medicao_incompleta=bool(_pdfvec_falhas_flag))"]
    fim = [k for k, l in enumerate(linhas) if 'f"FALHOU: {_eam}"' in l]
    assert len(ini) == 1 and len(fim) == 1 and fim[0] > ini[0], (ini, fim)
    return textwrap.dedent("".join(linhas[ini[0] + 1:fim[0] + 2]))


def test_o_process_job_CHAMA_as_duas_reguas_do_aco_na_ordem():
    """Taxa primeiro (linha zerada não é conferida), massa nominal depois — e os
    dois logs saem como diagnóstico."""
    taxa = _taxa(751, "7,51")
    cortado = _Item("Aço CA-50 ø8,0mm", "kg", 58,
                    "bitola ø8mm, CTot = 1473,3m, PTot ≈ 58kg (lido como '58').")
    logs = []
    ns = {"__name__": "aco_ns", "all_items": [taxa, cortado], "job_id": "f8d8e6d8",
          "_zera_peso_por_taxa": main._zera_peso_por_taxa,
          "_confere_peso_de_aco": main._confere_peso_de_aco,
          "_log_error": lambda st, msg, job=None, severity="error": logs.append((st, severity))}
    exec(compile(_fatia_do_aco(), "aco", "exec"), ns)
    assert taxa.quantity == 0
    assert abs(cortado.quantity - 581.8) < 0.2
    assert ("motor:aco-por-taxa", "info") in logs, logs
    assert ("motor:aco-massa-nominal", "info") in logs, logs
