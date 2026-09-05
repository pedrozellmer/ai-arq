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

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from engine_rules import numero_declarado_parcial as _parcial  # noqa: E402

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


def test_o_motor_CHAMA_a_regra():
    chamadas = [n for n in ast.walk(ast.parse(_fonte()))
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_e_parcial"]
    assert chamadas, "a regra existe e ninguém a chama — não roda em job nenhum"


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
