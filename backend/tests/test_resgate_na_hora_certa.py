# -*- coding: utf-8 -*-
"""O resgate da medição do PDF é consultado NA HORA DE ZERAR, não antes.

🩸 07/09/2026 — `resgate_pdf=0` em 28 de 28 jobs desde 26/08. Nunca disparou.

A régua (`engine_rules.quantidade_medida_pelo_pdf`) está CERTA — medido:
ela casa "Área total medida vetorialmente: 13,6 m²" num item de m² quando a
gente mediu 13,6, e RECUSA "49,9 m de parede × pé-direito estimado de 2,70 m =
134,7 m²" num item de m², porque ninguém mediu altura (regra dura nº1).

O que está errado é a ORDEM. O resgate mora no laço de páginas, dentro de
`if qty == 0` — ou seja, só olha item que a IA já devolveu zerado. Quem zera de
verdade é `_apply_area_honesty`, que roda DEPOIS, na consolidação.

Sequência real, job `ev3e2880` (05/09), lida no `error_log`:
    18:47:55  pdfvec:promo          medimos a prancha: m2=9.0 paredes_m=49.9
              a IA recebe os números, escreve "9,0 m²" na observação
              e devolve quantidade ≠ 0  →  o resgate é PULADO pelo guarda
    18:49:33  _apply_area_honesty   ZERA o item (m² sem prova não vira número)
              sai `zerados=6 resgate_pdf=0`, com a NOSSA medição no texto

O cliente recebe uma linha vazia cujo próprio texto diz que a gente mediu.

🔑 Consertar NÃO afrouxa a proteção: só preenche quando o número escrito na
observação bate ±1% com o que NÓS medimos NAQUELA prancha, com a família de
unidade certa. Item zerado porque o número da IA era grande demais passa a ser
repreenchido com o número NOSSO, e segue ESTIMADO (laranja) — nunca confirmado.

🪤 Só resgata quando a prancha do item é INEQUÍVOCA (job de uma prancha só, ou
`ref_sheet` com a página). Passar todas as pranchas como alvo foi o erro de
31/08: a cobertura do espaço de números plausíveis vai de 0,38% pra 2,64%, e a
régua deixa de perguntar "é a medição DESTA prancha?" pra perguntar "parece
alguma medição de alguma prancha?".

MEDIDO na base antes de mexer: 29 itens em 14 jobs saem zerados carregando a
nossa medição no texto. Nenhum é a maior parte do problema (3.484 zerados no
total, 607 dizendo "NÃO medida" = o problema da escala). Isto aqui é conserto
de CREDIBILIDADE: o produto se contradizendo na cara do cliente.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402
from engine_rules import quantidade_medida_pelo_pdf  # noqa: E402


class _Item:
    """Mímico do item do motor — só os campos que a função toca."""

    def __init__(self, **kw):
        self.description = kw.get("description", "")
        self.unit = kw.get("unit", "m2")
        self.quantity = kw.get("quantity", 0)
        self.observations = kw.get("observations", "")
        self.ref_sheet = kw.get("ref_sheet", "")
        self.origem = kw.get("origem", "")
        self.confidence = kw.get("confidence", "estimado")


# Números reais do job ev3e2880 (05/09): a prancha mediu 9,0 m² e 49,9 m.
OBS_AREA = ("Área de ambientes internos medida geometricamente: 9,0 m² (3 ambientes "
            "somados). Medido do desenho com escala 1:10 lida do viewport — confira "
            "a escala do seu PDF.")
OBS_LINEAR = ("Comprimento total de paredes medido geometricamente: 49,9 m "
              "(20 segmentos). Descontar vãos de portas.")
# 🚨 O caso PERIGOSO: comprimento medido × pé-direito INVENTADO pela IA.
OBS_PD_INVENTADO = ("Comprimento de paredes medido geometricamente: 49,9 m × "
                    "pé-direito estimado de 2,70 m = 134,7 m² bruto.")
OBS_CHUTE = "Área estimada visualmente: 31,5 m² — confirmar em obra."

PRANCHA = {"rooms_m2": 9.0, "n_rooms": 3, "walls_m": 49.9, "n_walls": 20,
           "arquivo": "prancha.pdf", "pagina": 0, "grupo_maior_m2": 9.0,
           "scale": 10, "scale_src": "viewport", "escala_validada": False,
           "cotas_batem": 0}
PP = {"prancha_p0": dict(PRANCHA)}


def _roda(qty_da_ia, obs, unidade, desc="Piso cerâmico dos ambientes internos",
          pp=None, ref="prancha.pdf"):
    it = _Item(description=desc, unit=unidade, quantity=qty_da_ia,
               observations=obs, ref_sheet=ref)
    n_fill, blanked = main._apply_area_honesty(
        [it], total_area=0, total_area_source="", pe_direito=0,
        pdfvec_m2=9.0, pdfvec_por_prancha=dict(PP if pp is None else pp))
    return it, n_fill, blanked


def _q(it):
    return float(it.quantity or 0)


# ══════════════════════════════════════════════════════════════════════════
#  1 · o defeito: a linha era zerada com a NOSSA medição escrita nela
# ══════════════════════════════════════════════════════════════════════════
def test_area_com_a_nossa_medicao_no_texto_nao_sai_zerada():
    """🩸 O invariante. A IA devolve um chute alto; a função zera; e a nossa
    medição (9,0 m²) estava escrita na linha o tempo todo."""
    it, _, _ = _roda(25.0, OBS_AREA, "m2")
    assert _q(it) == pytest.approx(9.0), (
        "a linha saiu com %r — a nossa medição de 9,0 m² estava no texto dela"
        % it.quantity)


def test_linear_com_a_nossa_medicao_no_texto_nao_sai_zerada():
    """O mesmo do outro lado da régua: comprimento medido, item em ml.

    🪤 Este NÃO é o caso proibido de 01/09. Lá o erro seria preencher o rodapé
    com o `walls_m` medido POR CONTA PRÓPRIA — comprimento de parede não é
    perímetro de rodapé. Aqui é diferente: a IA JÁ escreveu o número dela na
    linha, e ele é IGUAL ao nosso. O que a gente faz é parar de jogar fora.
    """
    it, _, _ = _roda(60.0, OBS_LINEAR, "ml", desc="Rodapé em porcelanato")
    assert _q(it) == pytest.approx(49.9)


def test_linear_zerado_pela_ia_tambem_e_resgatado():
    """🪤 O passo 7 só CRIA área. Linear com quantidade 0 nunca era resgatado
    dentro desta função, nem antes nem depois — buraco medido em 07/09."""
    it, _, _ = _roda(0, OBS_LINEAR, "ml", desc="Rodapé em porcelanato")
    assert _q(it) == pytest.approx(49.9)


def test_o_resgate_conta_no_log():
    """O número tem que aparecer: `resgate_pdf=0` por 28 jobs foi lido como
    'não havia o que resgatar'. Instrumento que nasce morto não vale nada."""
    _roda(25.0, OBS_AREA, "m2")
    assert int(getattr(main._apply_area_honesty, "ultimo_resgatados", 0) or 0) >= 1, \
        "o resgate aconteceu e não deixou contador"


# ══════════════════════════════════════════════════════════════════════════
#  1b · 🚨 AS TRÊS TRAVAS — achadas pela revisão adversarial de 07/09
#
#  A 1ª versão deste ramo CRIAVA NÚMERO sem nenhuma das travas que os ramos
#  vizinhos têm. Os três buracos foram reproduzidos rodando a função real.
# ══════════════════════════════════════════════════════════════════════════
def test_item_de_PAREDE_nao_recebe_a_area_do_PISO():
    """🚨 Trava 1. `rooms_m2` é área de CHÃO. "Pintura látex sobre parede" em
    m² citando 9,0 m² recebia os 9,0 do piso — atribuição errada com cara de
    medição. `is_floor_surface_para_criar` é a função cuja docstring diz "use
    onde o motor vai ESCREVER um número que não existia"."""
    it, _, _ = _roda(300.0, OBS_AREA, "m2", desc="Pintura látex sobre parede")
    assert _q(it) == 0, (
        "🚨 item de parede recebeu a área de piso medida (saiu %r)" % it.quantity)


def test_quatro_lineares_nao_recebem_TODOS_o_mesmo_comprimento():
    """🚨 Trava 2. `walls_m` é UMA medição. Rodapé, soleira, perfil de LED e
    dreno recebiam os mesmos 49,9 m — a mesma medição contada 4× no total da
    obra. Empate na família deixa todos vazios (trava 4 do passo 7)."""
    itens = [_Item(description=d, unit="ml", quantity=100.0,
                   observations=OBS_LINEAR, ref_sheet="prancha.pdf")
             for d in ("Rodapé em porcelanato", "Soleira de granito",
                       "Perfil de LED embutido", "Dreno de ar-condicionado")]
    main._apply_area_honesty(itens, pdfvec_m2=9.0, pdfvec_por_prancha=dict(PP))
    preenchidos = [i.description for i in itens if _q(i)]
    assert not preenchidos, (
        "🚨 %d itens lineares receberam a MESMA medição: %r"
        % (len(preenchidos), preenchidos))


def test_item_de_arquivo_que_ninguem_mediu_nao_resgata():
    """🚨 Trava 3. Com UMA prancha medida, o `ref_sheet` era ignorado e um item
    de arquivo que nunca foi medido levava o número dela."""
    it, _, _ = _roda(300.0, OBS_AREA, "m2", ref="OUTRO ARQUIVO.pdf")
    assert _q(it) == 0, (
        "🚨 item de arquivo não medido recebeu a medição de outro (saiu %r)"
        % it.quantity)


def test_item_sem_ref_sheet_nao_resgata():
    """Sem dizer de qual prancha veio, não há atribuição honesta."""
    it, _, _ = _roda(300.0, OBS_AREA, "m2", ref="")
    assert _q(it) == 0


def test_CONTROLE_o_unico_da_familia_continua_sendo_resgatado():
    """O outro lado das três travas: elas não podem matar o caso legítimo."""
    it, _, _ = _roda(300.0, OBS_AREA, "m2",
                     desc="Piso cerâmico dos ambientes internos")
    assert _q(it) == pytest.approx(9.0)
    it2, _, _ = _roda(300.0, OBS_LINEAR, "ml", desc="Rodapé em porcelanato")
    assert _q(it2) == pytest.approx(49.9)


def test_piso_e_forro_da_MESMA_prancha_sao_familias_diferentes():
    """A trava conta por FAMÍLIA: um piso e um forro não competem entre si."""
    itens = [_Item(description="Piso cerâmico", unit="m2", quantity=300.0,
                   observations=OBS_AREA, ref_sheet="prancha.pdf"),
             _Item(description="Forro de gesso", unit="m2", quantity=300.0,
                   observations=OBS_AREA, ref_sheet="prancha.pdf")]
    main._apply_area_honesty(itens, pdfvec_m2=9.0, pdfvec_por_prancha=dict(PP))
    assert [_q(i) for i in itens] == [pytest.approx(9.0), pytest.approx(9.0)]


def test_dois_PISOS_da_mesma_prancha_deixam_os_dois_vazios():
    """E dentro da MESMA família, empate = ninguém. Atribuir a área do
    pavimento a dois pisos é o erro do 'somado em dobro' (28/08)."""
    itens = [_Item(description="Piso cerâmico da sala", unit="m2", quantity=300.0,
                   observations=OBS_AREA, ref_sheet="prancha.pdf"),
             _Item(description="Piso vinílico dos quartos", unit="m2", quantity=300.0,
                   observations=OBS_AREA, ref_sheet="prancha.pdf")]
    main._apply_area_honesty(itens, pdfvec_m2=9.0, pdfvec_por_prancha=dict(PP))
    assert [_q(i) for i in itens] == [0, 0]


# ══════════════════════════════════════════════════════════════════════════
#  2 · 🚨 o que NÃO pode acontecer (regra dura nº1)
# ══════════════════════════════════════════════════════════════════════════
def test_comprimento_medido_vezes_pe_direito_INVENTADO_continua_zerado():
    """🚨 O caso perigoso, e o motivo de a régua exigir a família da unidade.

    A IA multiplica um comprimento que a gente mediu por uma altura que ela
    inventou. O 49,9 existe e bate com a nossa medição — mas é COMPRIMENTO
    num item de m². Ninguém mediu altura: a linha fica vazia, e isso é o certo.
    """
    it, _, _ = _roda(134.7, OBS_PD_INVENTADO, "m2", desc="Parede de alvenaria")
    assert _q(it) == 0, (
        "🚨 preencheu m² a partir de comprimento medido × pé-direito inventado: "
        "é a regra dura nº1 pelo avesso (saiu %r)" % it.quantity)


def test_numero_que_a_ia_inventou_continua_zerado():
    """Controle negativo: número na observação que NÃO é nosso não resgata."""
    it, _, _ = _roda(25.0, OBS_CHUTE, "m2")
    assert _q(it) == 0


def test_o_resgate_nunca_promove_o_selo():
    """Escala de PDF vem do carimbo/viewport; carimbo é declaração, não prova.
    Resgatado segue LARANJA (estimado), como tudo que vem de PDF."""
    it, _, _ = _roda(25.0, OBS_AREA, "m2")
    assert _q(it) == pytest.approx(9.0)
    assert str(getattr(it.confidence, "value", it.confidence)) == "estimado"


def test_a_linha_resgatada_diz_de_onde_veio_o_numero():
    """O cliente tem que conseguir conferir de onde saiu o número.

    🪤 A 1ª versão deste teste procurava "medi"/"prancha" na observação — e as
    duas palavras JÁ ESTAVAM no texto que a IA escreveu. Ele passava com a
    procedência apagada; a mutação pegou. Agora compara com o texto ANTES.
    """
    it, _, _ = _roda(25.0, OBS_AREA, "m2")
    obs = it.observations or ""
    assert "não medida" not in obs.lower(), "resgatou e ainda disse que não mediu"
    assert len(obs) > len(OBS_AREA), "a observação não ganhou nada — cadê a procedência?"
    acrescentado = obs[len(OBS_AREA):].lower()
    assert "preenchida com a medição desta prancha" in acrescentado, (
        "a linha foi preenchida e não diz por quê: %r" % acrescentado)


def test_numero_em_m2_que_e_a_nossa_medicao_de_PAREDE_nao_resgata():
    """🚨 O cruzamento perigoso entre as duas famílias.

    A observação cita "49,9 m²" — com unidade de ÁREA — e 49,9 é o que a gente
    mediu de PAREDE (comprimento), não de ambiente. Se os alvos de área e de
    comprimento forem misturados, isso vira área medida. Não é.

    🪤 A descrição TEM que ser superfície de chão ("Piso cerâmico"), senão a
    trava 1 recusa antes e o teste mede outra coisa — foi o que aconteceu na
    1ª versão, com "Pintura de parede": ele passava sem nunca exercitar a
    família de unidade, e a mutação que as misturava passou batida.
    """
    obs = "Área dos ambientes: 49,9 m² conforme medição da prancha."
    it, _, _ = _roda(300.0, obs, "m2", desc="Piso cerâmico dos ambientes")
    assert _q(it) == 0, (
        "🚨 preencheu ÁREA com o número que a gente mediu de COMPRIMENTO "
        "(saiu %r)" % it.quantity)


# ══════════════════════════════════════════════════════════════════════════
#  3 · 🪤 a prancha tem que ser INEQUÍVOCA (a lição de 31/08)
# ══════════════════════════════════════════════════════════════════════════
DUAS = {"a_p0": dict(PRANCHA, arquivo="a.pdf", pagina=0, rooms_m2=9.0),
        "b_p0": dict(PRANCHA, arquivo="b.pdf", pagina=0, rooms_m2=80.5)}
#: 🪤 Com DUAS pranchas o teto vira a MAIOR (80,5 m²), e um número da IA que
#: CABE nele (25) é PRESERVADO por um ramo anterior — nem chega no que zera.
#: A primeira versão destes três testes usava 25 e media outra coisa: o
#: controle positivo é que mostrou. Acima do teto (1,3 × 80,5 = 104,65) o item
#: é zerado de verdade, que é o cenário do resgate.
ACIMA_DO_TETO = 500.0


#: 🪤 Dois nomes em que UM É PREFIXO DO OUTRO — o caso que a trava do
#: "casamento mais longo" existe pra resolver (31/08: com "PLANTA BAIXA.pdf" e
#: "PLANTA BAIXA 2 PAVIMENTO.pdf", quem decidia era a ordem de processamento).
PREFIXO = {"planta_p0": dict(PRANCHA, arquivo="planta.pdf", pagina=0, rooms_m2=9.0),
           "planta2_p0": dict(PRANCHA, arquivo="planta 2.pdf", pagina=0, rooms_m2=80.5)}


def test_nome_ambiguo_entre_duas_pranchas_nao_resgata():
    """🚨 O `ref_sheet` casa com os DOIS arquivos e não há página pra desempatar.

    Sem a trava, o resgate pegaria um dos dois pela ordem do dicionário — e
    preencheria afirmando a procedência da prancha errada.
    """
    it, _, _ = _roda(ACIMA_DO_TETO, OBS_AREA, "m2", pp=PREFIXO, ref="planta 2.pdf")
    # "planta" e "planta 2" casam os dois; o mais longo ("planta 2", 80,5 m²)
    # vence, e 9,0 não é a medição dele → não resgata.
    assert _q(it) == 0


def test_o_nome_mais_longo_vence_e_resgata_a_prancha_certa():
    """O outro lado: quando o mais longo É o dono, o resgate acontece."""
    it, _, _ = _roda(ACIMA_DO_TETO,
                     OBS_AREA.replace("9,0 m²", "80,5 m²"), "m2",
                     pp=PREFIXO, ref="planta 2.pdf")
    assert _q(it) == pytest.approx(80.5)


#: 🪤 EMPATE DE VERDADE: dois nomes do MESMO comprimento, os dois contidos no
#: `ref_sheet`. "planta 2" ganhando de "planta" não exercita a trava — o
#: desempate por comprimento já resolve. Só um empate exato prova que a trava
#: existe; a mutação passou batido até este cenário entrar.
EMPATE = {"abc_p0": dict(PRANCHA, arquivo="abc.pdf", pagina=0, rooms_m2=9.0),
          "bcd_p0": dict(PRANCHA, arquivo="bcd.pdf", pagina=0, rooms_m2=80.5)}


def test_empate_exato_de_nome_nao_resgata_nenhum():
    """🚨 Sem a trava, quem vence é a ordem do dicionário — e a linha sairia
    preenchida afirmando a procedência de uma prancha escolhida a esmo."""
    it, _, _ = _roda(ACIMA_DO_TETO, OBS_AREA, "m2", pp=EMPATE, ref="abcd.pdf")
    assert _q(it) == 0, (
        "resgatou com dois arquivos igualmente plausíveis (saiu %r)" % it.quantity)


def test_com_duas_pranchas_e_sem_pagina_no_ref_nao_resgata():
    """🪤 Passar todas as pranchas como alvo leva a régua a perguntar 'parece
    alguma medição de alguma prancha?' em vez de 'é a medição DESTA?'.
    Cobertura do espaço de números plausíveis: 0,38% → 2,64% (31/08).
    Sem saber de qual prancha o item veio, a linha fica vazia."""
    it, _, _ = _roda(ACIMA_DO_TETO, OBS_AREA, "m2", pp=DUAS, ref="c.pdf")
    assert _q(it) == 0, "resgatou sem saber de qual prancha o item veio"


def test_com_a_pagina_no_ref_sheet_resgata_a_prancha_certa():
    """Quando o item diz de qual prancha veio, a atribuição é honesta."""
    it, _, _ = _roda(ACIMA_DO_TETO, OBS_AREA, "m2", pp=DUAS, ref="a.pdf (p1)")
    assert _q(it) == pytest.approx(9.0)


def test_a_pagina_errada_nao_resgata_com_o_numero_da_outra():
    """🚨 O pior modo de falha: preencher com a medição da prancha ERRADA e
    ainda afirmar a procedência. O item aponta pra prancha b (80,5 m²) e o
    texto dele traz 9,0 — que é da prancha a. Não casa: fica vazio."""
    it, _, _ = _roda(ACIMA_DO_TETO, OBS_AREA, "m2", pp=DUAS, ref="b.pdf (p1)")
    assert _q(it) == 0


# ══════════════════════════════════════════════════════════════════════════
#  4 · o que NÃO pode ter mudado
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_sem_medicao_nenhuma_tudo_continua_zerando():
    """Job sem PDF vetorial medido: o comportamento é o de antes."""
    it, _, blanked = _roda(25.0, OBS_AREA, "m2", pp={})
    assert _q(it) == 0 and blanked == 1


def test_CONTROLE_item_do_CAD_continua_intocado():
    """`origem='dxf_geom'` é medição de verdade — esta função não encosta."""
    it = _Item(description="Piso cerâmico", unit="m2", quantity=123.4,
               observations=OBS_AREA, ref_sheet="prancha.pdf", origem="dxf_geom")
    main._apply_area_honesty([it], pdfvec_m2=9.0, pdfvec_por_prancha=dict(PP))
    assert _q(it) == pytest.approx(123.4)


def test_CONTROLE_a_regua_sozinha_continua_certa():
    """Se a régua mudar, os testes de cima passam a medir outra coisa."""
    assert quantidade_medida_pelo_pdf(OBS_AREA, "m2", area_pdf=[9.0],
                                      comprimento_pdf=[49.9]) == pytest.approx(9.0)
    assert quantidade_medida_pelo_pdf(OBS_PD_INVENTADO, "m2", area_pdf=[9.0],
                                      comprimento_pdf=[49.9]) is None
    assert quantidade_medida_pelo_pdf(OBS_CHUTE, "m2", area_pdf=[9.0],
                                      comprimento_pdf=[49.9]) is None
