# -*- coding: utf-8 -*-
"""Número que o próprio motor diz ser PARCIAL não pode levar selo BRANCO.

🩸 05/09/2026 — MEDIDO na base: 4 itens com "✓ MEDIDO do CAD" cuja observação,
na mesma linha, admite que o número é um pedaço:

    "Fonte: comprimento total do layer SAN = 1,42 m. Valor provavelmente parcial"
    "Fonte: layer 'A-DUTO-E' = 3,93 m. ... trecho parcial representado nesta prancha"

A geometria FOI medida — por isso o `selos_sem_geometria` os absolve, e com
razão. O defeito é outro: mediu-se um PEDAÇO e carimbou-se como se fosse o item
inteiro. O cliente vê 1,42 m de esgoto num prédio e um selo de confiança.
Regra dura nº1: "medido" quer dizer que a medição é DO ITEM.

🚫 SÓ REBAIXA. Não corrige o número (regra nº3): corrigir seria inventar o resto
que ninguém mediu. E não promove nada, nunca.

🩸 A 1ª VERSÃO DESTE CRITÉRIO TINHA 80% DE PRECISÃO E EU SÓ VI MEDINDO.
Ela casava "parcial" e descontava quando vinha depois de palavra de desenho.
Rodada nos 6 brancos reais que contêm a palavra, acertou 4 e errou 1: o job
`66ebe2d9` diz "(comprimentos PARCIAIS em cm)" falando das barras individuais de
uma tabela de aço, não do total. Virou lista POSITIVA de frases — falha pra
menos, nunca pra mais, que é o lado certo de errar quando se mexe no selo.
Ver [[feedback_alarme_sem_controle_20260826]].

📏 Taxa de disparo medida ANTES de ligar: 4 em 1.313 brancos = 0,3%.
"""
import ast
import io
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from _corpo import fonte  # noqa: E402
from engine_rules import numero_declarado_parcial as _parcial  # noqa: E402
from models import Confidence  # noqa: E402

# ── Textos REAIS da base (05/09), integrais ────────────────────────────────
_DEVE_DISPARAR = {
    "tubulacao SAN (aed78b12)":
        "Fonte: comprimento total do layer SAN = 1,42 m. Valor provavelmente "
        "parcial (representacao em escala). Confirmar com projeto complementar.",
    "ripas (aed78b12)":
        "Fonte: comprimento total do layer Ripas = 1,18 m. Valor provavelmente "
        "parcial (representacao em escala na prancha).",
    "duto exaustao (b5693ca6)":
        "Fonte: comprimento do layer 'A-DUTO-E' = 3,93 m. Trecho curto — "
        "provavel detalhe de conexao ou trecho parcial representado nesta prancha.",
    "duto climatizacao (b5693ca6)":
        "Fonte: comprimento do layer 'A-DUTO-VC' = 5,17 m. Trecho curto — "
        "provavel detalhe de conexao ou trecho parcial representado nesta prancha.",
    "forro com pares nao listados":
        "Fonte: hachura com rotulo 'PCF01' (1 ocorrencia listada: 9.71 m2). "
        "Parcial — existem +229 pares nao listados.",
}

_NAO_PODE_DISPARAR = {
    # 🩸 O falso positivo que derrubou a 1a versao do criterio.
    "quadro de aco (66ebe2d9)":
        "Fonte: texto '91.7' (kg) no layer TEXTO_TABELAS, linha 8.0 da tabela de "
        "quantitativos. Comprimento total: 960 m. Barras de reforco — ver layer "
        "DT-Relacao do aco com valores '1092', '1376' etc. (comprimentos parciais em cm).",
    "blocos listados (e4954250)":
        "Fonte: 10 blocos distintos com 1 INSERT cada. Listados individualmente: "
        "A8ET4ES65RG46SDRG (1), AERGESRG (1), fdret (1).",
    "planta parcial": "Fonte: hachura na planta parcial do 2o pavimento = 48,5 m2",
    "vista parcial": "Fonte: vista parcial da fachada norte",
    "medicao limpa": "Fonte: area hachurada do layer PISO = 120 m2",
    "vazio": "",
}


def test_dispara_no_que_o_motor_declarou_parcial():
    for nome, obs in _DEVE_DISPARAR.items():
        assert _parcial(obs), (
            "não pegou %r — o motor diz que mediu um pedaço e o selo branco "
            "fica de pé" % nome)


def test_NAO_dispara_em_item_sao():
    """🪤 Alarme que acusa medição legítima perde crédito e é desligado."""
    for nome, obs in _NAO_PODE_DISPARAR.items():
        assert not _parcial(obs), (
            "acusou %r — rebaixaria o selo de um item correto" % nome)


def test_aguenta_None():
    assert not _parcial(None)


# ══════════════════════════════════════════════════════════════════════════
#  O MOTOR APLICA — E SÓ REBAIXA
# ══════════════════════════════════════════════════════════════════════════
def _fonte():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _bloco_da_aplicacao(src):
    i = src.index("from engine_rules import numero_declarado_parcial")
    return src[i:src.index("# 🚨 AQUI é o fim da fila de quem rebaixa selo", i)]


_OBS_PARCIAL = _DEVE_DISPARAR["tubulacao SAN (aed78b12)"]
_OBS_PARCIAL_RIPAS = _DEVE_DISPARAR["ripas (aed78b12)"]
_OBS_PARCIAL_DUTO = _DEVE_DISPARAR["duto exaustao (b5693ca6)"]
_OBS_ACO = _NAO_PODE_DISPARAR["quadro de aco (66ebe2d9)"]
_OBS_SA = "Fonte: area hachurada do layer PISO = 120 m2"
_AVISO = ("⚠ O número mede só PARTE deste item — o próprio levantamento diz "
          "isso na observação abaixo. Não leve como quantidade fechada: cobre "
          "só parte do que existe. ")


class _Item:
    """Item de mentira com a mesma superfície que o bloco toca."""

    def __init__(self, desc, selo, obs, qtd=1.42):
        self.description = desc
        self.confidence = selo
        self.observations = obs
        self.quantity = qtd


# ══════════════════════════════════════════════════════════════════════════
#  A FATIA QUE RODA — os DOIS rebaixamentos finais, inteiros
# ══════════════════════════════════════════════════════════════════════════
# 🪤 06/09/2026 — O RECORTE ANTERIOR PARAVA NO `_n_par += 1`, a última linha do
# corpo do laço. Tudo o que viesse depois — mais uma linha dentro do mesmo laço,
# o `if _n_par:` do aviso interno, o `except` — ficava FORA do que o guarda
# rodava. Uma promoção de volta a CONFIRMADO uma linha abaixo desfazia o
# rebaixamento inteiro em produção com o teste verde.
# 🔑 Agora a fatia vai do `try` do rebaixamento anterior (selo-sem-medida) até o
# fim do `except` do parcial. Com isso:
#   · promoção depois do `_n_par += 1` é vista (o item volta a CONFIRMADO);
#   · matar o `if _n_par:` é visto (o log interno some);
#   · `if False:` no `try` do parcial, ou um `return` entre os dois blocos, é
#     visto (o bloco não roda / a fatia nem compila).
# 🪤 O `try/except` de produção entra na fatia — mas o `_log_error` é espionado
# e o teste REPROVA se aparecer "FALHOU", que é como o bloco vira silêncio.
_INI_FATIA = ("        try:\n"
              "            from models import Confidence as _Conf3\n"
              "            _sem_medida = _selos_sem_medida(all_items)")
_FIM_FATIA = "        # 🚨 AQUI é o fim da fila de quem rebaixa selo"


def _fatia_dos_rebaixamentos():
    src = fonte("main.py")
    assert src.count(_INI_FATIA) == 1, "âncora de início não é única"
    a = src.index(_INI_FATIA)
    assert src.count(_FIM_FATIA, a) >= 1, "âncora de fim não achada"
    fatia = textwrap.dedent(src[a:src.index(_FIM_FATIA, a)])
    # 🪤 SÓ os marcos de ALCANCE da fatia (onde começa, onde termina). O que o
    # bloco FAZ é julgado pelos testes que o rodam — pôr `_n_par += 1` ou
    # `if _n_par:` aqui faria o guarda reprovar dizendo "o recorte mudou" em vez
    # de "o motor parou de rebaixar", que é mensagem errada pro defeito certo.
    for marca in ("_selos_sem_medida(all_items)", "_e_parcial(_ob)",
                  "except Exception as _epar:"):
        assert marca in fatia, (
            "a fatia não contém %r — o recorte parou de pegar do rebaixamento "
            "anterior até o fim do parcial, e voltaria a ser cego" % marca)
    return fatia


def _rodar_os_rebaixamentos(itens, job_id="job-teste"):
    """RODA os dois blocos finais de produção. Devolve (_n_par, logs)."""
    from engine_rules import selos_sem_medida as _ssm
    logs = []
    ns = {"all_items": itens, "_selos_sem_medida": _ssm, "job_id": job_id,
          "_log_error": lambda *a, **k: logs.append(
              " ".join(str(x) for x in a))}
    exec(compile(_fatia_dos_rebaixamentos(), "rebaixa-selo", "exec"), ns)
    assert not [l for l in logs if "FALHOU" in l], (
        "o bloco estourou e o `except` engoliu — o rebaixamento não aconteceu "
        "em job nenhum: %r" % logs)
    return ns.get("_n_par"), logs


def _bancada():
    """SETE itens, não um. 🪤 Com um item só, `all_items[:1]`, um `break` depois
    do primeiro casamento e um laço que só olha o primeiro ficavam VERDES — e a
    planilha real tem dezenas de linhas."""
    return [
        _Item("Tubulação SAN", Confidence.CONFIRMADO, _OBS_PARCIAL, 1.42),
        _Item("Piso cerâmico", Confidence.CONFIRMADO, _OBS_SA, 120.0),
        _Item("Ripas do forro", Confidence.CONFIRMADO, _OBS_PARCIAL_RIPAS, 1.18),
        _Item("Duto de exaustão", Confidence.CONFIRMADO, _OBS_PARCIAL_DUTO, 3.93),
        _Item("Quadro de aço", Confidence.CONFIRMADO, _OBS_ACO, 91.7),
        _Item("Alvenaria", Confidence.ESTIMADO, _OBS_PARCIAL, 45.0),
        # já veio com o aviso: a planilha é refeita (regra nº7)
        _Item("Duto reprocessado", Confidence.CONFIRMADO,
              _AVISO + _OBS_PARCIAL_DUTO, 3.93),
    ]


_PARCIAIS = ("Tubulação SAN", "Ripas do forro", "Duto de exaustão",
             "Duto reprocessado")


def test_o_motor_REBAIXA_o_branco_cujo_numero_e_parcial():
    """🚨 EXECUTA o bloco. O guarda antigo procurava, na árvore sintática, uma
    chamada chamada `_e_parcial` — trocar o laço por `for _it in []:` mantinha a
    chamada no fonte e a regra deixava de rodar em job nenhum."""
    itens = _bancada()
    n, _logs = _rodar_os_rebaixamentos(itens)
    assert n == 4, (
        "o motor rebaixou %r item(ns); os parciais desta bancada são 4 — se "
        "rebaixou menos, o laço para no meio e o resto da planilha fica com "
        "selo branco mentindo" % n)
    por_desc = {i.description: i for i in itens}
    for d in _PARCIAIS:
        assert por_desc[d].confidence == Confidence.ESTIMADO, (
            "%r continuou com selo MEDIDO depois do rebaixamento" % d)


def test_NADA_e_promovido_nem_depois_do_contador():
    """🚨 A regra dura nº1, EXECUTADA. Uma promoção de volta a CONFIRMADO uma
    linha abaixo do `_n_par += 1` desfazia o rebaixamento inteiro — e o recorte
    antigo terminava justamente naquela linha, então não via nada."""
    itens = _bancada()
    _rodar_os_rebaixamentos(itens)
    por_desc = {i.description: i for i in itens}
    assert por_desc["Alvenaria"].confidence == Confidence.ESTIMADO, (
        "o bloco PROMOVEU um item que já estava laranja — regra dura nº1")
    for d in _PARCIAIS:
        assert por_desc[d].confidence != Confidence.CONFIRMADO, (
            "%r voltou a CONFIRMADO depois de ser rebaixado" % d)


def test_NAO_toca_em_medicao_legitima():
    """🧪 Controle positivo dentro da execução: o quadro de aço (66ebe2d9) e o
    piso hachurado são medições boas e têm que sair CONFIRMADO."""
    itens = _bancada()
    _rodar_os_rebaixamentos(itens)
    por_desc = {i.description: i for i in itens}
    for d in ("Piso cerâmico", "Quadro de aço"):
        assert por_desc[d].confidence == Confidence.CONFIRMADO, (
            "%r perdeu o selo MEDIDO sem motivo — alarme que acusa medição "
            "legítima perde crédito e acaba desligado" % d)
        assert "cobre só parte" not in (por_desc[d].observations or ""), (
            "%r recebeu o aviso de parcial sem ser parcial" % d)


def test_o_numero_NAO_muda_em_item_nenhum():
    """Regra nº3, EXECUTADA: corrigir seria inventar o resto que ninguém mediu."""
    itens = _bancada()
    antes = [i.quantity for i in itens]
    _rodar_os_rebaixamentos(itens)
    assert [i.quantity for i in itens] == antes, (
        "o bloco mexeu na quantidade de algum item — ele só rebaixa selo")


def test_o_aviso_chega_ao_cliente_UMA_vez_so():
    """Regra nº7: a planilha é refeita, e o item que já traz o aviso não pode
    recebê-lo de novo. 🪤 O guarda antigo só procurava o `if ... not in _ob:` no
    fonte; aqui o item reprocessado passa pelo bloco de verdade."""
    itens = _bancada()
    _rodar_os_rebaixamentos(itens)
    por_desc = {i.description: i for i in itens}
    novo = por_desc["Tubulação SAN"].observations
    assert novo.count("cobre só parte") == 1, (
        "o aviso não saiu ou saiu repetido: %r" % novo[:200])
    assert _OBS_PARCIAL in novo, "o aviso comeu a observação original do motor"
    refeito = por_desc["Duto reprocessado"].observations
    assert refeito.count("cobre só parte") == 1, (
        "a planilha refeita empilhou o aviso de novo: %r" % refeito[:250])


def test_o_aviso_INTERNO_conta_os_rebaixados():
    """O `if _n_par:` ficava fora do recorte antigo — dava pra apagar o log e
    ninguém aqui saberia que o motor parou de registrar o que rebaixou."""
    _n, logs = _rodar_os_rebaixamentos(_bancada())
    parciais = [l for l in logs if "selo-parcial-rebaixado" in l]
    assert len(parciais) == 1, (
        "o motor registrou %d aviso(s) de selo-parcial; esperado exatamente 1 "
        "com a contagem: %r" % (len(parciais), logs))
    assert "4 item(ns)" in parciais[0], (
        "o aviso interno não diz quantos foram rebaixados: %r" % parciais[0])


def test_o_bloco_DE_CIMA_continua_rodando_na_mesma_fatia():
    """🔑 A fatia começa no rebaixamento anterior de propósito: assim um `return`
    ou um `if False:` colocado ENTRE os dois blocos deixa de ser invisível.
    Este item (branco com quantidade ZERO) é rebaixado lá em cima e, por isso,
    NÃO pode ser contado de novo pelo parcial."""
    zero = _Item("Forro sem quantidade", Confidence.CONFIRMADO, _OBS_PARCIAL, 0.0)
    itens = [zero, _Item("Tubulação SAN", Confidence.CONFIRMADO, _OBS_PARCIAL, 1.42)]
    n, _logs = _rodar_os_rebaixamentos(itens)
    assert zero.confidence == Confidence.ESTIMADO, (
        "o rebaixamento de quem saiu SEM QUANTIDADE parou de rodar")
    assert "NÃO MEDIDO" in (zero.observations or ""), zero.observations[:120]
    assert n == 1, (
        "o parcial contou %d; o item já rebaixado lá em cima não é mais branco "
        "e não pode entrar na conta de novo" % n)

def test_so_mexe_em_quem_esta_BRANCO():
    """Se tocasse em laranja, seria trabalho à toa; se promovesse, seria nº1."""
    bloco = _bloco_da_aplicacao(_fonte())
    assert 'if _cf != "confirmado":' in bloco and "continue" in bloco, (
        "o guarda não filtra pelo selo branco antes de agir")


def test_NUNCA_promove():
    """🚫 A linha da regra dura nº1. Este guarda só escreve ESTIMADO."""
    bloco = _bloco_da_aplicacao(_fonte())
    atribs = [n for n in ast.walk(ast.parse("if 1:\n" + "\n".join(
        " " + l for l in bloco.splitlines() if l.strip().startswith("_it.confidence"))))
        if isinstance(n, ast.Assign)]
    assert atribs, "não achei atribuição de selo no bloco — o guarda cegou"
    for a in atribs:
        alvo = ast.unparse(a.value)
        assert "ESTIMADO" in alvo, (
            "o guarda escreve %r no selo — ele só pode REBAIXAR" % alvo)


def test_NAO_mexe_no_numero():
    """Regra nº3: corrigir seria inventar o resto que ninguém mediu."""
    bloco = _bloco_da_aplicacao(_fonte())
    assert "_it.quantity" not in bloco, (
        "o guarda mexe na quantidade — ele só rebaixa selo")


def test_o_cliente_e_avisado_e_o_aviso_NAO_duplica():
    bloco = _bloco_da_aplicacao(_fonte())
    assert "mede só PARTE deste item" in bloco, (
        "rebaixa o selo e não explica ao cliente por quê")
    assert 'if "cobre só parte" not in _ob:' in bloco, (
        "sem guarda de idempotência: a planilha é refeita (regra nº7) e o "
        "aviso entraria duas vezes")


def test_roda_ANTES_do_retrato_do_selo():
    """O retrato tem que fotografar o estado FINAL, senão conta brancos que
    este guarda ainda vai derrubar."""
    src = _fonte()
    assert src.index("_e_parcial(_ob)") < src.index("_rs = _retrato(all_items)")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — o critério de ANTES, no MESMO julgamento
# ══════════════════════════════════════════════════════════════════════════
def _criterio_de_antes(obs):
    """A 1ª versão: casa "parcial" salvo depois de palavra de desenho."""
    import re
    baixo = str(obs or "").lower()
    if re.search(r"(?:n[ãa]o\s+list|sem\s+list)", baixo):
        return True
    for m in re.finditer(r"parcia(?:l|is)", baixo):
        janela = baixo[max(0, m.start() - 25):m.start()]
        if any(p in janela for p in ("planta", "vista", "prancha", "corte")):
            continue
        return True
    return False


def test_CONTROLE_o_criterio_de_ANTES_erra_no_quadro_de_aco():
    """Sem este controle eu não saberia que o critério novo conserta alguma
    coisa — e foi este caso, medido na base, que me fez trocar de abordagem."""
    aco = _NAO_PODE_DISPARAR["quadro de aco (66ebe2d9)"]
    assert _criterio_de_antes(aco), (
        "o controle está mal montado — a versão antiga deveria errar aqui")
    assert not _parcial(aco), (
        "a versão nova erra igual: a troca não consertou nada")


def test_CONTROLE_as_duas_versoes_concordam_nos_verdadeiros():
    """A troca não podia custar sensibilidade: os 4 casos reais continuam."""
    for nome, obs in _DEVE_DISPARAR.items():
        assert _criterio_de_antes(obs) and _parcial(obs), (
            "a versão nova perdeu o caso %r que a antiga pegava" % nome)
