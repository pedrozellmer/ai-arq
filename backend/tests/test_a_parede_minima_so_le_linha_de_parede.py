# -*- coding: utf-8 -*-
"""O aviso de PAREDE INCOMPLETA só lê o comprimento de linha de PAREDE.

🩸 19/10/2026 — projeto de um posto de parada numa rodovia (5 DWG). A
alvenaria saiu em m², com a conta escrita assim:

    "Cálculo: (AR-ALV-CTE 117,40 m + A-WALL 19,21 m + I-WALL 8,64 m)
     = 145,25 m × 3,08 m PD"

e o guarda do mínimo de parede (`test_parede_menor_que_o_perimetro_possivel`)
procurava "comprimento total do layer X = N m" em QUALQUER linha da planilha.
A única que tinha a frase era um ELETRODUTO da prancha elétrica:

    "comprimento total do layer E-POWR-CNDT = 27,53 m"

27,53 m contra um mínimo de 75,2 m para 353 m²: o cliente leu "a leitura achou
27.5 m de parede … falta parede", e as três linhas de parede ganharam a nota
"trate este número como piso" — com 145 m de parede medidos.

📏 120 dias (banco): a frase estava em 268 linhas fora de Fechamentos
Verticais (elétrica 89, complementares 43, hidráulica 40, incêndio 27…). Dos
13 alarmes em projeto de cliente, 3 tiraram o número de linha que não era
parede: este eletroduto e duas DEMOLIÇÕES (224,61 m e 7,67 m — parede que sai,
não a que fica).

🔑 O conserto é o mesmo filtro que a outra fonte (itens em metro) já usava:
só linha de Fechamentos Verticais. Erra pro lado de calar, que é o lado que o
guarda escolheu desde 04/09 (`max` das fontes).

Os testes rodam o TRECHO REAL do motor (do `_paredes_ml = [` até a chamada
`_par_min`), não uma cópia da regra.
"""
import io
import os
import re
import textwrap
from types import SimpleNamespace as _It

from engine_rules import comprimento_de_parede_na_observacao

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

_OBS_ELETRODUTO = ("Fonte: comprimento total do layer E-POWR-CNDT = 27,53 m. "
                   "Diâmetros identificados nos textos do layer E-POWR-CNDT-IDEN.")
_OBS_ALVENARIA = ("Cálculo: (AR-ALV-CTE 117,40 m + A-WALL 19,21 m + I-WALL 8,64 m) "
                  "= 145,25 m × 3,08 m PD (informado por você) = 447,37 m² bruto.")
_OBS_DEMOLICAO = "comprimento total do layer DEMOLIR = 224,61 m (paredes a demolir)"
_OBS_PAREDE_M2 = ("Estimativa: comprimento total do layer PAREDES = 17,18 m "
                  "(confirmado) × pé-direito estimado 2,60 m = 44,67 m².")


def _trecho():
    i = _FONTE.index("_paredes_ml = [")
    i = _FONTE.rindex("\n", 0, i) + 1
    j = _FONTE.index("_impossivel, _min_per = _par_min(", i)
    return textwrap.dedent(_FONTE[i:j])


def _fontes(itens, trecho=None):
    """O `_paredes_ml` que o motor monta com estas linhas."""
    ns = {"all_items": itens, "_compr_obs": comprimento_de_parede_na_observacao}
    exec(compile(trecho or _trecho(), "<parede-minima>", "exec"), ns)
    return ns["_paredes_ml"]


def _item(disc, unit, qtd, obs=""):
    return _It(discipline=disc, unit=unit, quantity=qtd, observations=obs)


def test_o_caso_o_eletroduto_nao_vira_parede():
    itens = [
        _item("Fechamentos Verticais", "m²", 361.59, _OBS_ALVENARIA),
        _item("Instalações Elétricas e Dados", "ml", 27.53, _OBS_ELETRODUTO),
    ]
    assert _fontes(itens) == [], (
        "o comprimento do eletroduto voltou a contar como parede: %r" % _fontes(itens))


def test_demolicao_nao_vira_parede():
    itens = [_item("Demolição e Remoção", "m²", 600.0, _OBS_DEMOLICAO)]
    assert _fontes(itens) == []


def test_CONTROLE_a_parede_em_m2_continua_lida_da_observacao():
    """O motivo da 2ª fonte (04/09): a mesma casa sai em m² numa rodada."""
    itens = [_item("Fechamentos Verticais", "m²", 44.67, _OBS_PAREDE_M2),
             _item("Instalações Elétricas e Dados", "ml", 27.53, _OBS_ELETRODUTO)]
    assert _fontes(itens) == [17.18], _fontes(itens)


def test_CONTROLE_a_parede_em_metro_continua_contando():
    itens = [_item("Fechamentos Verticais", "ml", 17.18),
             _item("Fechamentos Verticais", "m²", 44.67, _OBS_PAREDE_M2)]
    assert sorted(_fontes(itens)) == [17.18, 17.18]


def test_CONTROLE_sem_o_filtro_o_eletroduto_virava_parede():
    """Prova que o teste do caso REPROVA o motor de antes: tira o filtro do
    laço da observação e o eletroduto volta a ser a única "parede"."""
    t = _trecho()
    filtro = re.search(
        r'\n( +)if str\(getattr\(_it, "discipline", ""\) or ""\) != '
        r'"Fechamentos Verticais":\n\1    continue\n', t)
    assert filtro, "o filtro de disciplina sumiu do laço da observação"
    sem = t[:filtro.start()] + "\n" + t[filtro.end():]
    assert sem != t
    itens = [_item("Fechamentos Verticais", "m²", 361.59, _OBS_ALVENARIA),
             _item("Instalações Elétricas e Dados", "ml", 27.53, _OBS_ELETRODUTO)]
    assert _fontes(itens, sem) == [27.53], (
        "a mutação não reproduziu o caso — o controle não prova nada")


# ══════════════════════════════════════════════════════════════════════════
#  22/10: parede separada por TIPO, uma linha por layer
# ══════════════════════════════════════════════════════════════════════════
def _dry(qtd, layer, desc="Divisória em drywall — fornecimento e execução"):
    return _It(discipline="Fechamentos Verticais", unit="ml", quantity=qtd,
               description=desc,
               observations="Fonte: comprimento layer %s = %s m." % (layer, qtd))


def _lais():
    return [_dry(65.12, "ARQ-DIV"), _dry(42.27, "FLH-CHA-ACUSTICA"),
            _dry(17.9, "ARQ-CHA"), _dry(16.28, "FLH-CHA-vermelho")]


def test_o_caso_parede_por_tipo_SOMA_os_layers():
    from engine_rules import parede_abaixo_do_minimo
    f = _fontes(_lais())
    assert max(f) == 141.57, f
    impossivel, minimo = parede_abaixo_do_minimo(max(f), 1000.0)
    assert round(minimo, 1) == 126.5
    assert not impossivel, "141,6 m de parede em 4 layers e o aviso ainda diria que falta"


def test_CONTROLE_sem_a_soma_o_alarme_falso_DISPARA():
    """Prova que o caso reprova: só o maior (o comportamento de antes) dispara."""
    from engine_rules import parede_abaixo_do_minimo
    impossivel, _ = parede_abaixo_do_minimo(65.12, 1000.0)
    assert impossivel


def test_CONTROLE_o_MESMO_layer_duas_vezes_nao_soma():
    f = _fontes([_dry(65.12, "ARQ-DIV"), _dry(60.0, "arq-div")])
    assert max(f) == 65.12, f


def test_CONTROLE_demolicao_nao_entra_na_soma():
    """(A linha em metro sozinha já entrava antes, pela fonte de sempre; o que
    se prova aqui é que a SOMA não a junta à parede que fica.)"""
    f = _fontes([_dry(65.12, "ARQ-DIV"),
                 _dry(300.0, "DEMOLIR", desc="Demolição de divisória existente")])
    assert 365.12 not in f, f


def test_CONTROLE_linha_sem_layer_citado_nao_entra_na_soma():
    sem = _It(discipline="Fechamentos Verticais", unit="ml", quantity=80.0,
              description="Divisória", observations="Medido no desenho.")
    f = _fontes([_dry(65.12, "ARQ-DIV"), sem])
    assert max(f) == 80.0 and 145.12 not in f, f


def test_CONTROLE_outra_disciplina_nao_entra_na_soma():
    ele = _It(discipline="Instalações Elétricas e Dados", unit="ml", quantity=90.0,
              description="Eletroduto", observations="comprimento layer E-CNDT = 90 m")
    f = _fontes([_dry(65.12, "ARQ-DIV"), ele])
    assert max(f) == 65.12, f


def test_o_mesmo_layer_repetido_entre_pranchas_conta_UMA_vez_na_soma():
    """A divisória repetida em duas pranchas é a mesma parede: entra pelo maior."""
    f = _fontes([_dry(65.12, "ARQ-DIV"), _dry(65.12, "ARQ-DIV"),
                 _dry(42.27, "FLH-CHA-ACUSTICA")])
    assert 107.39 in f and 172.51 not in f, f
