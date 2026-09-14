# -*- coding: utf-8 -*-
"""O nome do layer que a allowlist de área recusou tem que CHEGAR ao log.

🩸 14/09/2026 — MEDIDO em 60 dias (259 pranchas, 94 jobs): o motor aceita 183
polígonos e recusa 3.158, e **2.800 dessas recusas (88,7%) são
`fora_da_allowlist`** — pelo NOME do layer, não pela geometria. É 1 polígono
aceito a cada 18, e a área é onde a planilha mais cala (3,1% das linhas em m²
saem medidas, contra 42,2% das de peça).

🔑 `dwg_extractor` coletava os nomes desde 09/09 em `poly_layers_recusados`,
sob o comentário "🚫 NÃO ampliar a lista antes de ter o número". O campo
viajava dentro do `DXFExtraction` e NINGUÉM lia — nem o motor, nem um teste.
O número existia e era descartado a cada job.

🪤 Este guarda protege o INSTRUMENTO, não a allowlist. Publicar o nome não
muda o que é aceito; é o que permite ampliar a lista depois com prova — token
a token, porque no acervo real o nome engana (`arq-pis-hum` é piso; o
`...-inc-pis` de hidráulica termina igual e é cano).
"""
import ast
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_MAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "main.py")


class _Extr:
    """Só o que a função lê — de propósito, pra não amarrar no DXFExtraction."""

    def __init__(self, recusados):
        self.poly_layers_recusados = recusados


def test_o_nome_do_layer_recusado_sai_no_texto():
    txt = main._descarte_de_poligonos(_Extr({"ARQ-PIS-HUM": 12, "G-ARQU1": 3}))
    assert "poly_layers_recusados=" in txt, (
        "o sufixo não identifica o que está reportando: %r" % txt)
    assert "ARQ-PIS-HUM" in txt, (
        "o NOME do layer não chega ao log — sem ele, 'recusado por nome' e "
        "'o desenho não tem' viram a mesma ausência: %r" % txt)
    assert "12" in txt, ("a contagem por layer sumiu: %r" % txt)


def test_ordena_pelo_que_mais_recusou():
    """Quem recusa 40 vezes decide a próxima palavra da allowlist; quem recusa
    1 é ruído. Se a ordem for a de inserção, o teto de 5 corta justo o maior."""
    txt = main._descarte_de_poligonos(_Extr({
        "RUIDO-A": 1, "RUIDO-B": 1, "RUIDO-C": 1, "RUIDO-D": 1,
        "RUIDO-E": 1, "O-QUE-MAIS-RECUSA": 40,
    }))
    assert "O-QUE-MAIS-RECUSA" in txt, (
        "o layer campeão de recusa ficou de fora do corte: %r" % txt)
    assert txt.index("O-QUE-MAIS-RECUSA") < txt.index("RUIDO"), (
        "não está ordenado por quantidade: %r" % txt)


def test_nao_estoura_o_log_com_acervo_grande():
    """Prancha de acervo grande tem centenas de layers. O log é lido por humano
    e o insert tem teto — o sufixo não pode crescer sem limite."""
    txt = main._descarte_de_poligonos(
        _Extr({("LAYER-%03d" % i): (200 - i) for i in range(180)}))
    assert txt.count("|") <= 4, ("passou de 5 layers no sufixo: %r" % txt)
    assert len(txt) < 240, ("sufixo longo demais para o log: %d" % len(txt))


def test_nome_absurdamente_longo_e_cortado():
    gigante = "ARQ_" + ("X" * 400) + "_PISO"
    txt = main._descarte_de_poligonos(_Extr({gigante: 5}))
    assert len(txt) < 120, ("nome gigante não foi cortado: %d" % len(txt))


# ── controles: quando o sufixo tem que ficar VAZIO ───────────────────────
def test_CONTROLE_sem_recusa_nao_polui_o_log():
    assert main._descarte_de_poligonos(_Extr({})) == ""
    assert main._descarte_de_poligonos(_Extr(None)) == ""


def test_CONTROLE_extracao_sem_o_campo_nao_quebra():
    """Prancha de PDF e caminhos antigos não têm o atributo. O log de geometria
    roda dentro de um try que, se explodir, apaga TODO o resto da linha."""
    class _Velho:
        pass

    assert main._descarte_de_poligonos(_Velho()) == ""


def test_CONTROLE_campo_com_lixo_nao_derruba_o_job():
    class _Lixo:
        poly_layers_recusados = "isto não é um dicionário"

    assert main._descarte_de_poligonos(_Lixo()) == ""


# ── o motor CHAMA a função (senão o instrumento nasce morto de novo) ─────
def test_o_log_de_geometria_CHAMA_a_funcao():
    """🪤 Foi exatamente isto que falhou em 09/09: o dado era coletado e nunca
    lido. Um guarda que só testasse a função repetiria o mesmo erro — o que
    precisa estar provado é o PONTO DE CHAMADA."""
    arv = ast.parse(io.open(_MAIN, encoding="utf-8").read())
    chamadas = [n for n in ast.walk(arv)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_descarte_de_poligonos"]
    assert chamadas, ("ninguém chama `_descarte_de_poligonos` — o nome do layer "
                      "recusado continua sendo jogado fora")

    # 🪤 Ancorar no FATO, não na distância em linhas: a 1ª versão deste guarda
    # olhava 22 linhas acima da chamada e REPROVOU o conserto certo, porque a
    # mensagem do log tem mais comentário que código no meio. O fato é
    # "a chamada é argumento de um _log_error cujo stage é motor:geometria" —
    # e isso a AST responde sem contar linha.
    def _stage_do_log_que_contem(alvo):
        for n in ast.walk(arv):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "_log_error"):
                continue
            if any(d is alvo for a in n.args for d in ast.walk(a)):
                prim = n.args[0] if n.args else None
                if isinstance(prim, ast.Constant):
                    return prim.value
                return "(stage não é literal)"
        return None

    stages = {_stage_do_log_que_contem(c) for c in chamadas}
    assert "motor:geometria" in stages, (
        "a chamada não é argumento do log `motor:geometria` — o nome do layer "
        "não chega onde alguém lê. Stages encontrados: %r" % (stages,))


def test_o_stage_de_geometria_continua_sendo_diagnostico():
    """O sufixo novo engorda uma linha que é MIGALHA, não erro. Se
    `motor:geometria` sair da lista, ela volta a empurrar erro de verdade pra
    fora das 40 linhas do painel — foi o que aconteceu em 14/09 com a régua."""
    assert "motor:geometria" in main._STAGES_DIAGNOSTICO
