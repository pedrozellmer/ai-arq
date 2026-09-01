# -*- coding: utf-8 -*-
"""O aviso de ESTRUTURA não pode AFIRMAR o que o arquivo do cliente é.

🚨 CASO EDVALDO — Racional, 01/09/2026, job `b5ce23ff`.

Coordenador de estrutura de uma construtora grande, primeiro projeto, nome
"TESTE" — uma avaliação. Ele mandou `TOP-EST-PE-116-FRM-TIP-R00.dwg`:
**FRM = fôrma, TIP = pavimento tipo.** O motor abriu, validou a escala com
**175 cotas** batendo com a geometria (centímetros, `regua=validada`,
`ressalva=False`), leu os layers `LAJE`, `VIGA`, `S-COLS-IDEN`, `S-BEAM-IDEN`,
mediu **90,86 m² de laje** da hachura e **339,66 m de viga**, e extraiu as
seções de mais de 50 pilares ("150×19", "14/63").

E o aviso de topo que ele leu dizia:

    "O arquivo enviado não traz o que a medição de estrutura precisa
     (planta de fôrma, detalhamento de armação ou quadro de ferros)."

Ou seja: a gente disse a um coordenador de estrutura que ele mandou o arquivo
errado — sendo que ele mandou exatamente o certo, e a gente tinha acabado de
ler o desenho inteiro. A frase era uma AFIRMAÇÃO sobre o arquivo dele, feita
sem nunca olhar o arquivo. É a família do "erro que mentia"
([[project_mensagens_erro_20260805]]: 53 de 74 falhas eram NOSSAS).

🔑 Numa planta de fôrma 2D o que falta NÃO é a prancha — é a **ALTURA**.
Pé-direito do pavimento e altura de viga não existem em planta, e sem altura
não fecham m³ de concreto nem m² de fôrma. São dois diagnósticos OPOSTOS e o
motor só sabia dar o primeiro.

🪤 SEGUNDO FURO, no mesmo bloco: a dica "reprocesse informando o pé-direito"
só disparava se houvesse item de pilar CONTADO em 'un'. A IA do Edvaldo dobrou
os 50+ pilares dentro da linha de fôrma em m², então a dica não apareceu —
justo pra quem ela foi escrita. O pé-direito é o campo que corta o branco de
59,5% pra 27,3% ([[project_verdade_de_campo_20260826]]).

🧪 O teste que importa aqui é o de RECUSA: um guarda que sempre deixa passar
não guarda nada. `test_CONTROLE_*` prova que o ramo novo NÃO é sempre-ligado.
"""
import io
import os
import sys
import textwrap

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

_INICIO = "        if is_structural and all_items:"
_FIM = "        # ── HONESTIDADE DE ÁREA (regra dura"


class _Item:
    def __init__(self, description="", quantity=0, unit="m²",
                 confidence="estimado", observations=""):
        self.description = description
        self.quantity = quantity
        self.unit = unit
        self.confidence = confidence
        self.observations = observations


class _PD:
    def __init__(self, pe_direito=0):
        self.warnings = []
        self.user_pe_direito = pe_direito


def _roda(itens, pe_direito=0, is_structural=True):
    """Executa O TRECHO REAL do main.py, não uma cópia dele.

    🪤 Reimplementar a lógica aqui seria testar a minha cópia — foi o vício
    que a auditoria de 31/08 pegou (um teste chamava uma função que eu tinha
    INVENTADO e caía num fallback que reimplementava o código). O trecho é
    recortado por duas âncoras que existem UMA vez só no arquivo; se alguma
    sumir, o teste quebra alto em vez de passar verde de mentira.
    """
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert src.count(_INICIO) == 1, "a âncora de início do trecho mudou"
    assert src.count(_FIM) == 1, "a âncora de fim do trecho mudou"
    i = src.index(_INICIO)
    trecho = textwrap.dedent(src[i:src.index(_FIM, i)])
    pd = _PD(pe_direito)
    chamadas = []
    ns = {
        "is_structural": is_structural,
        "all_items": itens,
        "project_data": pd,
        "job_id": "teste",
        "_log_error": lambda *a, **k: chamadas.append((a, k)),
    }
    exec(compile(trecho, "main_estrutura_slice", "exec"), ns)
    return pd.warnings, ns, chamadas


# ── O caso real do Edvaldo, item por item como saiu no banco ────────────────
def _itens_edvaldo():
    return [
        _Item("Concreto estrutural Fck=30 MPa — especificação confirmada", 0, "m³",
              observations="Volume não calculado: altura de pavimento e seções não "
                           "foram medidas no CAD 2D."),
        _Item("Laje — Fôrma (compensado/madeira) — fundo de laje", 90.86, "m²",
              observations="Fonte: área hachurada do layer 'LAJE' = 90.86 m² "
                           "(10 hachuras, padrão SOLID único)."),
        _Item("Laje — Concreto armado Fck=30 MPa — volume por área × espessura", 0, "m³",
              observations="Área de projeção horizontal = 90.86 m² (layer 'LAJE'). "
                           "Espessuras lidas nos textos: H=10 cm, H=12 cm, H=14 cm."),
        _Item("Viga — Comprimento total de eixo (planta de fôrma típica)", 169.83, "m",
              observations="Fonte: comprimento total de linhas do layer 'VIGA' = 339.66 m."),
        _Item("Viga — Fôrma (compensado/madeira) — faces laterais e fundo", 0, "m²",
              observations="Área de fôrma de viga não calculada: altura de viga não "
                           "medida no CAD 2D. Seções '14/63' e '19/63'."),
        _Item("Pilar — Fôrma — perímetro da seção × altura de pavimento", 0, "m²",
              observations="Área de fôrma de pilar não calculada: altura de pavimento "
                           "(pé-direito estrutural) não foi medida no CAD 2D."),
        _Item("Escada — Fôrma (compensado/madeira)", 1.57, "m²",
              observations="Referência de área hachurada do layer S-STRS."),
        _Item("Armadura CA-50 / CA-60 — Aço para lajes, vigas e pilares", 0, "kg",
              observations="NÃO há quadro/resumo de aço (quadro de ferragens)."),
    ]


_FRASE_ACUSATORIA = "O arquivo enviado não traz o que a medição de estrutura precisa"


def test_planta_de_forma_NAO_e_acusada_de_nao_ser_planta_de_forma():
    """🩸 O que o Edvaldo leu. Este é o teste do dia."""
    avisos, _, _ = _roda(_itens_edvaldo())
    assert len(avisos) == 1, "o aviso de estrutura tem que sair (nada foi medido)"
    txt = avisos[0]
    assert _FRASE_ACUSATORIA not in txt, (
        "a gente ainda está dizendo a um coordenador de estrutura que ele mandou "
        "o arquivo errado, num arquivo que É a planta de fôrma:\n" + txt)
    assert "ALTURA" in txt, (
        "o aviso não diz qual é o buraco de verdade (a altura):\n" + txt)


def test_o_aviso_novo_explica_POR_QUE_a_altura_falta():
    txt = _roda(_itens_edvaldo())[0][0]
    assert "2D" in txt, "não explica que planta é 2D e por isso não tem altura"
    for esperado in ("pé-direito", "altura de viga"):
        assert esperado in txt, "faltou citar " + esperado + ":\n" + txt


def test_a_dica_do_pe_direito_dispara_SEM_pilar_contado_em_un():
    """🪤 O 2º furo: nenhum item do Edvaldo é pilar em 'un'."""
    itens = _itens_edvaldo()
    assert not any(i.unit == "un" for i in itens), (
        "o caso real não tem pilar contado em 'un' — se tivesse, este teste "
        "estaria guardando outra coisa")
    txt = _roda(itens, pe_direito=0)[0][0]
    assert "PÉ-DIREITO" in txt, "a dica que destrava o volume não apareceu:\n" + txt
    assert "reprocessar" in txt


def test_com_pe_direito_informado_a_dica_NAO_se_repete():
    """Controle negativo: quem já informou não precisa ouvir de novo."""
    txt = _roda(_itens_edvaldo(), pe_direito=2.9)[0][0]
    assert "PÉ-DIREITO" not in txt, "repetiu a dica pra quem já informou:\n" + txt


# ── CONTROLES POSITIVOS: o guarda tem que REPROVAR ──────────────────────────
def test_CONTROLE_arquivo_que_REALMENTE_nao_serve_recebe_o_aviso_antigo():
    """🧪 Se o ramo novo fosse sempre-ligado, ele não guardaria nada.

    Aqui o cliente mandou uma prancha que não entrega elemento estrutural
    nenhum com grandeza — o diagnóstico certo continua sendo "falta a prancha".
    """
    itens = [
        _Item("Concreto estrutural Fck=25 MPa — especificação", 0, "m³",
              observations="Especificação lida do texto. Volume não calculado."),
        _Item("Serviços preliminares", 1, "vb", observations="Verba."),
    ]
    txt = _roda(itens)[0][0]
    assert _FRASE_ACUSATORIA in txt, (
        "o ramo antigo sumiu — projeto que de fato não trouxe a prancha deixou "
        "de ser avisado:\n" + txt)
    assert "ALTURA" not in txt


def test_CONTROLE_os_dois_ramos_produzem_avisos_DIFERENTES():
    """🧪 Prova que o discriminador discrimina. Se os dois textos fossem
    iguais, todos os testes acima passariam e nada teria sido consertado."""
    com_forma = _roda(_itens_edvaldo())[0][0]
    sem_forma = _roda([_Item("Concreto Fck=30", 0, "m³", observations="sem dados")])[0][0]
    assert com_forma != sem_forma, "os dois ramos dão o MESMO texto — nada mudou"


def test_CONTROLE_so_elemento_estrutural_com_grandeza_liga_o_ramo_novo():
    """🪤 Um item de fôrma zerado NÃO é prova de que o desenho foi lido.
    Sem isto o ramo novo ligaria em qualquer projeto de estrutura."""
    itens = [
        _Item("Laje — Fôrma", 0, "m²",
              observations="altura de pavimento não medida"),
        _Item("Viga — Fôrma", 0, "m²",
              observations="altura de viga não medida"),
    ]
    txt = _roda(itens)[0][0]
    assert _FRASE_ACUSATORIA in txt, (
        "ligou o ramo 'falta altura' num projeto onde NADA saiu com grandeza — "
        "aí a gente estaria afirmando que leu o desenho sem ter lido:\n" + txt)


def test_CONTROLE_falta_altura_sozinho_nao_basta():
    """O elemento tem que ter grandeza E o motor tem que ter dito que falta
    altura. Só a marca de altura, sem leitura, não liga."""
    _, ns, _ = _roda([_Item("Laje — Fôrma", 90.86, "m²",
                            observations="Fonte: área hachurada = 90.86 m².")])
    assert ns["_leu_estrutura"] is True
    assert ns["_falta_altura"] is False, (
        "achou marca de altura onde não há — o discriminador está solto")
    assert _FRASE_ACUSATORIA in _roda(
        [_Item("Laje — Fôrma", 90.86, "m²",
               observations="Fonte: área hachurada = 90.86 m².")])[0][0]


def test_projeto_que_MEDIU_nao_recebe_aviso_nenhum():
    """Controle de silêncio: 1 item confirmado com grandeza já basta."""
    itens = _itens_edvaldo() + [
        _Item("Pilar — concreto", 12.5, "m³", confidence="confirmado",
              observations="medido do bloco"),
    ]
    avisos, _, _ = _roda(itens)
    assert avisos == [], "poluiu um projeto que mediu de verdade: " + str(avisos)


def test_confirmado_em_unidade_SEM_grandeza_nao_cala_o_aviso():
    """🪤 Caso Allan (20/08): o único 'confirmado' era '1 vb — Especificação de
    concreto', e ele suprimia o aviso num projeto todo zerado."""
    itens = _itens_edvaldo() + [
        _Item("Especificação de concreto", 1, "vb", confidence="confirmado"),
    ]
    avisos, _, _ = _roda(itens)
    assert len(avisos) == 1, "uma verba carimbada calou o aviso de novo"


def test_o_log_registra_qual_ramo_saiu():
    """Sem isto não dá pra medir depois quantos projetos caem em cada ramo —
    é a família do 'gravação que falha calada'."""
    _, _, chamadas = _roda(_itens_edvaldo())
    assert chamadas, "o log não foi chamado"
    msg = " ".join(str(a) for a, _ in chamadas)
    assert "ramo=falta-altura" in msg, msg
    assert "leu_estrutura=True" in msg and "falta_altura=True" in msg


def test_nao_estrutural_nao_dispara_nada():
    """🪤 Só project_type=estrutura. Não generalizar sem medir."""
    avisos, _, _ = _roda(_itens_edvaldo(), is_structural=False)
    assert avisos == []
