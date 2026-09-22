# -*- coding: utf-8 -*-
"""O aviso de ESTRUTURA só afirma o que é verdade NESTE job.

🩸 22/09/2026 — job `ee801b82` (cliente de 1 dia, NPS 2). Sete PDFs de uma
página cada, concreto armado de estruturas hidráulicas: poços, caixa de
válvulas, bloco, um pequeno pórtico. O topo do projeto dizia:

    "⚠ ESTRUTURA: o desenho foi lido — os elementos estruturais saíram com
     quantidade —, mas nenhum número foi MEDIDO [...] O que falta aqui não é
     a prancha: é a ALTURA. [...] O peso de aço depende do quadro de ferros,
     que é outra prancha (ARM). Dica: [...] se você reprocessar informando o
     PÉ-DIREITO (campo do envio), dá pra calcular o volume e a fôrma"

Quatro afirmações, as quatro falsas ali:
  · "saíram com quantidade" — o aviso é escrito ANTES da honestidade de área,
    que zerou 46 das 48 linhas de m³/m² logo em seguida;
  · "falta a ALTURA" — a marca veio de UMA sapata ("cota de altura não
    legível") que a IA quantificou mesmo assim (1,94 m³); as alturas dos poços
    estavam nos cortes (EL.335,60 − EL.332,70 = 2,90 m);
  · "o quadro de ferros é outra prancha (ARM)" — três das pranchas ENVIADAS
    traziam o RESUMO DE AÇO, lido em 7 linhas (582, 784,45, 1,27, 306, 432,2,
    54,6 e 199 kg);
  · "informe o pé-direito" — a conta por PD só existe pra pilar contado em
    'un' com seção "AxB cm", ou com comprimento medido de CAD. Aqui: nenhum
    pilar em 'un', e só PDF. Ela seguiria o conselho e nada mudaria.

🔑 Cada frase agora depende de um FATO do job, e o teste confere o fato e a
frase juntos. O filhote (reprocesso) roda como estrutura a partir do mesmo
job — e no job irmão `f8d8e6d8` (mesmos arquivos) a IA não escreveu marca de
altura nenhuma: sem o resumo de aço decidindo o ramo, o filhote cairia no
texto que diz "o arquivo enviado não traz [...] quadro de ferros".

🧪 Executa o TRECHO REAL do main.py (o mesmo recorte do
`test_aviso_estrutura_nao_acusa_o_arquivo`), com as duas réguas que a dica do
PD consulta tiradas do `main` de verdade. Controles positivos provam que cada
frase VOLTA quando o fato é verdade — guarda que só cala não guarda nada.
"""
import io
import os
import sys
import textwrap

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import engine_rules as er  # noqa: E402
import main  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

_INICIO = "        if is_structural and all_items:"
_FIM = "        # ── HONESTIDADE DE ÁREA (regra dura"

_FRASE_ACUSATORIA = "O arquivo enviado não traz o que a medição de estrutura precisa"
_ALTURA = "é a ALTURA"
_ARM = "outra prancha (ARM)"
_PD = "PÉ-DIREITO"


class _PD_(object):
    def __init__(self, pe_direito=0):
        self.warnings = []
        self.user_pe_direito = pe_direito


def _roda(itens, pe_direito=0):
    """O trecho real, com `_log_error` espionado e as réguas REAIS do main."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert src.count(_INICIO) == 1, "a âncora de início do trecho mudou"
    assert src.count(_FIM) == 1, "a âncora de fim do trecho mudou"
    i = src.index(_INICIO)
    trecho = textwrap.dedent(src[i:src.index(_FIM, i)])
    pd = _PD_(pe_direito)
    logs = []
    ns = {
        "is_structural": True,
        "all_items": itens,
        "project_data": pd,
        "job_id": "ee801b82",
        "_log_error": lambda *a, **k: logs.append(" ".join(str(x) for x in a)),
        "_tem_comprimento_medido": main._tem_comprimento_medido,
        "_derive_estrutura_pe_direito": main._derive_estrutura_pe_direito,
    }
    exec(compile(trecho, "main_estrutura_slice", "exec"), ns)
    return pd.warnings, " ".join(logs), ns


def _it(desc, q, unit, obs="", conf=Confidence.ESTIMADO):
    return BudgetItem(item_num="1", description=desc, unit=unit, quantity=q,
                      observations=obs, confidence=conf, origem="vision_pdf",
                      ref_sheet="DE-X")


_TAXA = ("Estimado por taxa de consumo típica de 100 kg/m³ aplicada ao volume de "
         "concreto armado. Não há quadro/resumo de aço nesta prancha. Bitolas não "
         "visíveis — confirmar com prancha de detalhamento de armadura.")


def _aco_do_resumo():
    """As 7 linhas de aço que a IA tirou do RESUMO DE AÇO das pranchas do caso."""
    return [
        _it("Armadura CA-50 ø8,0 mm — toda a estrutura", 582, "kg",
            "Peso calculado a partir do comprimento total LIDO do quadro RESUMO AÇO "
            "CA-50 da prancha: CTot(ø8mm) = 1473,3 m × 0,395 kg/m = 581,95 kg."),
        _it("Armadura CA-50 φ10 mm — estrutura E3", 784.45, "kg",
            "CTot=1271,4 m lido do RESUMO DE AÇO CA-50 da prancha (φ10 mm)."),
        _it("Armadura CA-50 φ6,3 mm — estrutura E3 (marca N16)", 1.27, "kg",
            "CTot=5,2 m lido do RESUMO DE AÇO CA-50 da prancha (lida da Lista de Ferros)."),
        _it("Aço CA-50 ø8mm — armadura total da prancha", 306, "kg",
            "Valor copiado diretamente do RESUMO AÇO CA-50 da prancha: PTot=306kg. "
            "Fonte primária: quadro de ferragens da prancha."),
        _it("Armadura CA-50 — total geral (Ø6,3 + Ø8 + Ø10mm)", 432.2, "kg",
            "Calculado a partir do RESUMO AÇO CA-50 da prancha (CTot lidos)."),
        _it("Armadura CA-60 — total geral (Ø5mm — estribos)", 54.6, "kg",
            "Calculado a partir do RESUMO AÇO CA-60 da prancha."),
        # a redação REAL da IA no job (a 1ª versão deste fixture tirou o
        # "CONFIRMADO", e a régua passou a exigir quem afirma a procedência)
        _it("Tela soldada Q335 — radier e laje", 199, "kg",
            "Peso CONFIRMADO do RESUMO TELA DE AÇO da prancha: Q335, Área = 37 m², "
            "PTot = 199 kg."),
    ]


def _itens_do_caso(com_marca_de_altura=True, com_resumo=True):
    """O job ee801b82 ANTES da honestidade de área, reduzido e com nomes neutros."""
    itens = [
        _it("Concreto estrutural C30 — estrutura E1 (paredes + lajes)", 2.94, "m³",
            "Estimado. Diâmetro externo=210cm, altura parede≈2,68m (EL.332,709–"
            "EL.329,829). Cotas lidas da prancha escala 1:25 declarada."),
        _it("Concreto estrutural C30 — estrutura E2", 4.85, "m³",
            "Altura = EL.335,60 – EL.332,70 = 2,90m, cotas lidas da prancha."),
        _it("Concreto estrutural C30 — TOTAL GERAL", 26.80, "m³",
            "Soma dos valores do quadro de quantitativos da prancha = 26,80 m³."),
        _it("Fôrma (compensado/madeira) — laje de cobertura E1", 9.05, "m²",
            "Área da laje circular pelas cotas lidas."),
        _it("Fôrma de madeira — estrutura E3", 82.7, "m²",
            "Valor lido diretamente do quadro de quantitativos da prancha."),
        _it("Armadura CA-50/CA-60 — estrutura E1", 294, "kg", _TAXA),
        _it("Armadura CA-50/CA-60 — estrutura E2", 485, "kg", _TAXA),
        _it("Armadura CA-50 e CA-60 — sapatas S1 a S4", 0, "kg",
            "O peso das armaduras das sapatas está contabilizado no RESUMO DE AÇO "
            "da prancha. Não há quadro de aço exclusivo para sapatas."),
        _it("Controle tecnológico do concreto", 1, "vb", "Verba."),
    ]
    if com_marca_de_altura:
        itens.append(_it(
            "Concreto armado — sapatas S1, S2, S3, S4 (4 unidades)", 1.94, "m³",
            "Volume estimado: 4 sapatas × 1,10m × 1,10m × 0,40m (altura estimada "
            "do degrau visível no corte — cota de altura não legível)."))
    if com_resumo:
        itens += _aco_do_resumo()
    return itens


# ══════════════════════════════════════════════════════════════════════════
#  🩸 O caso, frase por frase
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_ee801b82_nao_afirma_altura_nem_ARM_nem_pe_direito():
    """🩸 O texto que ela leu 3 minutos antes do NPS 2, no job de verdade."""
    avisos, _log, _ns = _roda(_itens_do_caso())
    assert len(avisos) == 1, "o aviso de estrutura tem que sair: nada foi medido"
    txt = avisos[0]
    assert txt.startswith("⚠ ESTRUTURA:"), (
        "a tela reconhece o aviso pelo começo 'ESTRUTURA:' — sumiu:\n" + txt)
    assert "saíram com quantidade" not in txt, (
        "voltou a afirmar quantidade num aviso escrito ANTES da honestidade, que "
        "zerou 46 de 48 linhas de m³/m²:\n" + txt)
    assert _ALTURA not in txt, (
        "afirmou que falta a ALTURA — nenhuma linha ficou sem número por falta "
        "de altura (a sapata que acendeu a marca saiu com 1,94 m³):\n" + txt)
    assert _ARM not in txt, (
        "disse que o quadro de ferros é outra prancha, com 7 linhas lidas do "
        "RESUMO DE AÇO das pranchas que ela mandou:\n" + txt)
    assert _PD not in txt, (
        "mandou informar o pé-direito num job sem pilar em 'un' e sem CAD — a "
        "conta que ele destravaria não tem alvo aqui:\n" + txt)
    assert _FRASE_ACUSATORIA not in txt, txt


def test_o_caso_diz_o_que_e_VERDADE_sobre_o_aco():
    """O lugar do ARM falso é o fato: de onde o aço saiu, e que é estimativa."""
    txt = _roda(_itens_do_caso())[0][0]
    assert "resumo de aço das próprias pranchas em 7 linha(s)" in txt, txt
    assert "estimativa" in txt, "o aço do PDF não pode soar como medido:\n" + txt


def test_o_log_guarda_o_fato_de_cada_frase():
    """Sem os números, não dá pra medir depois quantos jobs caem em cada frase."""
    _av, log, _ns = _roda(_itens_do_caso())
    for esperado in ("sem_altura=0", "aco_do_resumo=7", "pd_destrava=False",
                     "pilar_contado=False", "ramo=falta-altura"):
        assert esperado in log, "faltou %r no log: %s" % (esperado, log)


def test_o_filhote_SEM_marca_de_altura_nao_cai_no_texto_que_acusa_o_arquivo():
    """🩸 No job irmão f8d8e6d8 (mesmos 7 arquivos) a IA não escreveu marca de
    altura nenhuma. Sem o resumo de aço no ramo, o filhote leria "o arquivo
    enviado não traz [...] quadro de ferros" — tendo mandado três resumos."""
    avisos, log, _ns = _roda(_itens_do_caso(com_marca_de_altura=False))
    txt = avisos[0]
    assert _FRASE_ACUSATORIA not in txt, (
        "o resumo de aço foi lido e o aviso ainda diz que o arquivo não traz "
        "quadro de ferros:\n" + txt)
    assert "resumo de aço das próprias pranchas" in txt, txt
    assert "ramo=resumo-de-aco" in log, log


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES POSITIVOS — cada frase volta quando o fato é verdade
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_sem_resumo_lido_a_frase_do_ARM_volta():
    """Se nenhuma linha saiu do resumo, "o quadro de ferros é outra prancha" é
    o que a leitura sustenta — a frase tem que continuar lá."""
    txt = _roda(_itens_do_caso(com_resumo=False))[0][0]
    assert _ARM in txt, "o guarda calou a frase do ARM sempre:\n" + txt


def test_CONTROLE_linha_sem_numero_por_falta_de_altura_traz_a_frase_da_ALTURA():
    """Quando a IA deixou a linha SEM número dizendo que falta a altura, a
    frase é verdade e é o diagnóstico que o cliente precisa (job b5ce23ff)."""
    itens = _itens_do_caso() + [
        _it("Viga — Fôrma (faces laterais e fundo)", 0, "m²",
            "Área de fôrma de viga não calculada: altura de viga não medida.")]
    txt = _roda(itens)[0][0]
    assert _ALTURA in txt, "a frase da altura sumiu mesmo com linha travada nela:\n" + txt
    assert "2D" in txt


def _pilar_contado():
    return _it("Pilar P1 — seção 30x40 cm", 8, "un", "Contagem pela planta de fôrma.")


def _alvo_do_pilar():
    return _it("Pilar — concreto armado C30", 0, "m³",
               "Volume não calculado: falta a altura de pavimento.")


def test_CONTROLE_pilar_contado_com_secao_e_alvo_liga_a_dica_do_PD():
    """A conta existe (`_derive_estrutura_pe_direito`): seção × PD × contagem.
    Aqui o PD destrava uma linha de verdade, e a dica tem que sair."""
    txt = _roda(_itens_do_caso() + [_pilar_contado(), _alvo_do_pilar()])[0][0]
    assert _PD in txt and "reprocessar" in txt, (
        "a dica sumiu num job em que o pé-direito PREENCHE o concreto do pilar:\n" + txt)


def test_CONTROLE_com_PD_ja_informado_a_dica_nao_se_repete():
    txt = _roda(_itens_do_caso() + [_pilar_contado(), _alvo_do_pilar()],
                pe_direito=2.9)[0][0]
    assert _PD not in txt, txt


def test_CONTROLE_pilar_contado_SEM_linha_alvo_nao_liga_a_dica():
    """🪤 Pilar em 'un' sozinho não basta: sem linha de concreto/fôrma do pilar
    a conta não tem onde escrever (o gargalo medido em 14/09)."""
    txt = _roda(_itens_do_caso() + [_pilar_contado()])[0][0]
    assert _PD not in txt, (
        "prometeu o pé-direito num job em que a conta não tem alvo:\n" + txt)


def test_a_pergunta_ao_PD_nao_escreve_nos_itens_de_verdade():
    """🪤 `_derive_estrutura_pe_direito` PREENCHE o alvo. Perguntar a ela sem
    uma cópia gravaria 3,6 m³ de 'pé-direito informado por você' que ninguém
    informou — regra dura nº1 pelo avesso."""
    alvo = _alvo_do_pilar()
    obs_antes = alvo.observations
    _roda(_itens_do_caso() + [_pilar_contado(), alvo])
    assert alvo.quantity == 0, "a pergunta escreveu %r no item real" % alvo.quantity
    assert alvo.observations == obs_antes, alvo.observations
    assert alvo.confidence == Confidence.ESTIMADO


# ══════════════════════════════════════════════════════════════════════════
#  A régua do resumo de aço, chamada direto
# ══════════════════════════════════════════════════════════════════════════
def test_a_regua_conta_as_7_linhas_do_resumo_e_nao_conta_a_negacao():
    """As 2 linhas por TAXA dizem "Não há quadro/resumo de aço" e não contam;
    a de 0 kg cita o resumo sem tirar número dele e não conta."""
    assert er.linhas_de_aco_do_resumo(_itens_do_caso()) == 7
    assert er.linhas_de_aco_do_resumo([_it("Armadura", 294, "kg", _TAXA)]) == 0
    assert er.linhas_de_aco_do_resumo(
        [_it("Armadura", 50, "kg", "Sem resumo de aço na prancha; por taxa.")]) == 0


def test_CONTROLE_a_regua_conta_cada_forma_de_citar_o_quadro():
    # 22/09 (revisão): formas que AFIRMAM a procedência, como a IA escreve no
    # acervo — citar o quadro sem dizer que o número veio dele não conta mais
    # (ver test_o_aco_por_taxa_nao_vira_resumo_lido.py).
    for obs in ("lido do RESUMO DE AÇO CA-50", "copiado do RESUMO AÇO CA-60",
                "Peso CONFIRMADO do RESUMO TELA DE AÇO",
                "fonte: quadro de ferragens da prancha",
                "Marca N16: 1 barra × 520 cm (lida da Lista de Ferros)"):
        assert er.linhas_de_aco_do_resumo([_it("Aço", 10, "kg", obs)]) == 1, obs
    assert er.linhas_de_aco_do_resumo([_it("Aço", 10, "m²", "RESUMO DE AÇO")]) == 0
