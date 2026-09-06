# -*- coding: utf-8 -*-
"""O aviso do plano B não pode afirmar medição que os guardas já derrubaram.

🩸 CASO TIAGO — METAL-AR ENGENHARIA, 01/09/2026, job `2a42f7ec`.
18 pranchas de climatização, todas recusadas pelo ODA e abertas pelo libredwg.
Ele recebeu, literalmente:

    "18 arquivo(s) precisaram do leitor alternativo (plano B): ...
     As medições saíram (2 item(ns) medido(s) do CAD), mas vale conferir
     2-3 medidas-chave contra o projeto antes de fechar orçamento."

A planilha tem **ZERO de 132 medidos** (conferido no banco).

🔑 POR QUE: o bloco que monta este aviso roda ~180 linhas ANTES do guarda
`selos_sem_geometria`. Os 2 itens eram gás refrigerante em kg, e o guarda os
rebaixou logo depois por terem procedência só de texto. O guarda de LINHA
funcionou; o texto do PROJETO nunca foi recomputado.

🚨 É a regra dura nº1 no nível do projeto — e no pior parágrafo possível, o que
manda o cliente "conferir 2-3 medidas-chave antes de fechar orçamento". Medidas
que não existem.

🪤 O conserto reescreve por ÍNDICE, não procurando a frase antiga. Guarda que
casa string de aviso para de achar quando alguém muda uma palavra, sem quebrar
nada e sem avisar ninguém.
"""
import io
import os
import sys
import textwrap

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

# 🪤 04/09/2026 — a âncora era `"        if _aviso_lw_idx is not None:"` (8
# espaços). Quando o bloco virou função, essa linha passou a ter 12 espaços — e
# a âncora de 8 CASOU COMO SUBSTRING dentro dela. O recorte saiu sem a linha
# `def` e com a chamada no fim: `NameError` em 12 testes de uma vez, e nenhum
# deles falando de âncora.
# 🔑 Ancorar no `def` resolve e ainda melhora: o teste passa a exercitar a
# função inteira, que é o que roda em produção.
_INI = "        def _recontar_aviso_planob():"
_FIM = "        try:\n            _n_med_esc = -1"

_CAB = ("18 arquivo(s) precisaram do leitor alternativo (plano B): "
        "CBS-PRO-IAC-EX-F01-GER-SJ-R01.DWG. ")
_TEXTO_QUE_O_TIAGO_RECEBEU = _CAB + (
    "As medições saíram (2 item(ns) medido(s) do CAD), mas vale conferir "
    "2-3 medidas-chave contra o projeto antes de fechar orçamento.")


class _Item:
    # 🩸 03/09/2026 — este item só tinha `confidence`, e por isso NENHUM teste
    # daqui exercia o ramo novo de ORIGEM: com observação vazia a contagem dá 0
    # e o aviso cai sempre no mesmo texto. Guarda que não exerce o ramo não é
    # guarda dele. Agora carrega quantidade e observação, que é o que o critério
    # de `engine_rules` lê.
    def __init__(self, confidence="estimado", quantity=0, observations=""):
        self.confidence = confidence
        self.quantity = quantity
        self.observations = observations


class _PD:
    def __init__(self, warnings):
        self.warnings = list(warnings)


def _roda(itens, warnings, idx=0, cab=_CAB):
    """Executa O TRECHO REAL do main.py."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert src.count(_INI) == 1, "a âncora de início do trecho mudou"
    assert src.count(_FIM) == 1, "a âncora de fim do trecho mudou"
    # 🪤 CASAMENTO PARCIAL: âncora indentada casa DENTRO de uma linha mais
    # indentada ainda, e o recorte sai mutilado sem ninguém perceber. Foi
    # exatamente o que quebrou 12 testes em 04/09. Exigir que ela comece logo
    # depois de uma quebra de linha fecha isso.
    assert ("\n" + _INI) in src, (
        "a âncora de início casou no meio de uma linha mais indentada — o "
        "recorte sairia mutilado")
    i = src.index(_INI)
    trecho = textwrap.dedent(src[i:src.index(_FIM, i)])
    pd = _PD(warnings)
    logs = []
    # 🪤 O trecho real chama `_origem_das_quantidades` (a frase da origem mora
    # num lugar só). Sem ela no namespace dá NameError, o `except` do main
    # engole calado e o aviso fica com o TEXTO VELHO — verde falso pelo pior
    # caminho possível. É a dependência real do bloco; entra de verdade.
    import main as _m_planob
    ns = {"_aviso_lw_idx": idx, "_aviso_lw_cab": cab,
          "project_data": pd, "all_items": itens, "job_id": "teste",
          "_origem_das_quantidades": _m_planob._origem_das_quantidades,
          "_log_error": lambda *a, **k: logs.append(a)}
    exec(compile(trecho, "main_planob_slice", "exec"), ns)
    return pd.warnings, logs


def test_zero_medidos_no_fim_APAGA_a_afirmacao_de_medicao():
    """🩸 O que o Tiago leu."""
    avisos, _ = _roda([_Item() for _ in range(132)], [_TEXTO_QUE_O_TIAGO_RECEBEU])
    assert "As medições saíram" not in avisos[0], (
        "o aviso ainda afirma medição numa planilha sem nenhum medido:\n" + avisos[0])
    assert "nenhum item saiu com o selo" in avisos[0], avisos[0]
    assert "2 item(ns)" not in avisos[0], "o número velho sobreviveu"


def test_o_cabecalho_com_os_nomes_dos_arquivos_e_PRESERVADO():
    """A parte verdadeira do aviso (quais DWG precisaram do plano B) não pode
    sumir junto com a parte falsa."""
    avisos, _ = _roda([_Item()], [_TEXTO_QUE_O_TIAGO_RECEBEU])
    assert avisos[0].startswith(_CAB), avisos[0]
    assert "CBS-PRO-IAC-EX-F01-GER-SJ-R01.DWG" in avisos[0]


def test_a_recontagem_deixa_RASTRO_quando_muda():
    """Sem log, ninguém descobre em quantos jobs isto vinha mentindo."""
    _, logs = _roda([_Item() for _ in range(10)], [_TEXTO_QUE_O_TIAGO_RECEBEU])
    assert logs, "mudou o texto e não registrou nada"
    assert "aviso-planob-recontado" in str(logs[0])


def test_projeto_que_MEDIU_de_verdade_mantem_a_contagem():
    """Controle: quando há medido no fim, o aviso continua dizendo quantos."""
    itens = [_Item("confirmado")] * 27 + [_Item()] * 5
    avisos, _ = _roda(itens, [_TEXTO_QUE_O_TIAGO_RECEBEU])
    assert "27 item(ns) medido(s) do CAD" in avisos[0], avisos[0]
    assert "nenhum item saiu com o selo" not in avisos[0]


def test_quando_a_contagem_NAO_muda_nao_gera_log():
    """Não poluir o log de quem estava certo desde o começo."""
    certo = _CAB + ("As medições saíram (3 item(ns) medido(s) do CAD), mas vale "
                    "conferir 2-3 medidas-chave contra o projeto antes de fechar "
                    "orçamento.")
    _, logs = _roda([_Item("confirmado")] * 3, [certo])
    assert not logs, "logou uma mudança que não houve: %s" % logs


# ── CONTROLES ──────────────────────────────────────────────────────────────
def test_CONTROLE_sem_plano_B_o_trecho_nao_toca_em_nada():
    """idx=None significa que não houve aviso de plano B neste job."""
    outros = ["⚠ Não encontramos a área total do projeto"]
    avisos, logs = _roda([_Item()], outros, idx=None)
    assert avisos == outros and not logs


def test_CONTROLE_indice_fora_da_lista_nao_quebra_nem_inventa():
    avisos, _ = _roda([_Item()], ["um aviso só"], idx=7)
    assert avisos == ["um aviso só"]


def test_CONTROLE_nao_encosta_nos_OUTROS_avisos():
    outros = ["⚠ aviso A", _TEXTO_QUE_O_TIAGO_RECEBEU, "⚠ aviso C"]
    avisos, _ = _roda([_Item()] * 3, outros, idx=1)
    assert avisos[0] == "⚠ aviso A" and avisos[2] == "⚠ aviso C"
    assert "nenhum item saiu com o selo" in avisos[1]


def test_CONTROLE_o_teste_REPROVA_o_comportamento_ANTIGO():
    """🧪 Controle positivo: o comportamento antigo era simplesmente NÃO
    recontar. Reproduzo isso (não rodar o trecho) e confiro que a asserção
    principal acusa. Sem isto, o teste passaria com o conserto desligado."""
    antigo = [_TEXTO_QUE_O_TIAGO_RECEBEU]          # ninguém recontou
    assert "As medições saíram" in antigo[0], (
        "o texto de partida não reproduz o caso real — o teste inteiro estaria "
        "guardando um problema que não existe")
    assert "nenhuma quantidade foi medida da geometria" not in antigo[0]


def test_CONTROLE_enum_de_confidence_e_contado_certo():
    """🪤 Duas vezes o motor já errou aqui: `str(enum)` dá 'Confidence.CONFIRMADO'
    e o contador via zero. A comparação direta funciona porque o enum herda de
    str — este teste existe pra a terceira vez não passar batida."""
    from models import Confidence
    itens = [_Item(Confidence.CONFIRMADO), _Item(Confidence.CONFIRMADO), _Item()]
    avisos, _ = _roda(itens, [_TEXTO_QUE_O_TIAGO_RECEBEU])
    assert "2 item(ns) medido(s)" in avisos[0], (
        "com o enum real a contagem saiu errada:\n" + avisos[0])


def test_selo_zero_COM_geometria_nao_acusa_a_planilha_de_ser_texto():
    """🩸 O que o EDVALDO leu — job b5ce23ff, maior lead B2B, 03/09/2026.

    O aviso dizia "nenhuma quantidade foi medida da geometria — o que saiu na
    planilha veio de texto lido das pranchas". A planilha dele tinha 90,86 m² de
    laje vindos de HACHURA do layer LAJE e 169,83 m de viga vindos do
    COMPRIMENTO das linhas do layer VIGA.

    Selo zero e origem-texto são dois fatos. Este teste trava os dois separados.
    """
    itens = [
        _Item(quantity=90.86,
              observations="Fonte: área hachurada do layer 'LAJE' = 90.86 m² (10 hachuras)"),
        _Item(quantity=169.83,
              observations="Fonte: comprimento total de linhas do layer 'VIGA' = 339.66 m"),
        _Item(quantity=0, observations="Área de fôrma de viga não calculada"),
    ]
    avisos, _ = _roda(itens, [_TEXTO_QUE_O_TIAGO_RECEBEU])
    assert "nenhum item saiu com o selo" in avisos[0], avisos[0]
    assert "O que saiu na planilha veio de texto lido das pranchas." not in avisos[0], (
        "o aviso ainda acusa a planilha de ser transcrição de legenda, com "
        "duas quantidades vindas da geometria:\n" + avisos[0])
    assert "tirada da geometria do desenho" in avisos[0], avisos[0]


def test_CONTROLE_selo_zero_SEM_geometria_continua_dizendo_que_veio_de_texto():
    """Sem este controle o teste acima seria satisfeito apagando a frase.

    Quando a origem É texto mesmo, o cliente TEM que ler isso — é a informação
    que evita ele tratar legenda como levantamento.
    """
    itens = [
        _Item(quantity=264.54,
              observations="Fonte: texto layer 'ARQ-TEXTO 1': 'AREA TOTAL = 264,54 m2'"),
        _Item(quantity=12, observations="Conforme legenda da prancha, quadro de esquadrias"),
    ]
    avisos, _ = _roda(itens, [_TEXTO_QUE_O_TIAGO_RECEBEU])
    assert "veio de texto lido das pranchas" in avisos[0], avisos[0]
    assert "tirada da geometria" not in avisos[0], avisos[0]


def test_CONTROLE_linha_ZERADA_que_cita_hachura_nao_conta_como_medida():
    """Observação que CITA geometria numa linha sem quantidade não é medição.

    O item "Escada — Fôrma" do job do cliente-23 diz "área hachurada" e, na frase
    seguinte, "NÃO calculada". Contar isso seria inventar procedência na outra
    direção — o mesmo vício que este conserto existe pra tirar.
    """
    itens = [_Item(quantity=0,
                   observations="Fonte: área hachurada do layer 'LAJE' = 90.86 m²")]
    avisos, _ = _roda(itens, [_TEXTO_QUE_O_TIAGO_RECEBEU])
    assert "veio de texto lido das pranchas" in avisos[0], avisos[0]
    assert "tirada da geometria" not in avisos[0], avisos[0]
