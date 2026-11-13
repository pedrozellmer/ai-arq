# -*- coding: utf-8 -*-
"""O aviso de PAREDE INCOMPLETA tem que enxergar a parede que a linha m² usou.

🩸 12 e 13/11/2026 — dois projetos seguidos. O topo do projeto dizia
"PAREDE INCOMPLETA: a leitura achou 32,0 m de parede" (e 21,1 m no outro), e a
linha de alvenaria da MESMA planilha dizia:

    "Fonte: comprimento layer A-WALL = 736.86 m … × pé-direito 3.00 m"
    "Cálculo: comprimento pelo eixo (layer A-PAREDE) = 294,11 m × …"

`comprimento_de_parede_na_observacao` só conhece "comprimento TOTAL DO layer
X = N m". Sem a parede de verdade, o guarda ficou com o que sobrou em metro
dentro de Fechamentos Verticais: escada + guarda-corpo (32,03 m) e muro +
cobogó (21,10 m) — e carimbou "trate como piso" na escada e no guarda-corpo.

📏 90 dias: 29 alarmes em cliente, 4 com a parede da linha m² acima do mínimo.

🔑 A leitura nova é fonte a mais no `max`: só CALA. Nasce com a chave
PAREDE_MINIMO_LE_LINHA_M2 em 0 — desligada, só registra quando calaria.

Os testes rodam o TRECHO REAL do motor (de `_paredes_ml = [` até o
rebaixamento), não uma cópia da regra.
"""
import io
import os
import textwrap
from types import SimpleNamespace as _It

from engine_rules import (comprimento_de_parede_na_observacao,
                          comprimento_na_linha_de_parede_m2,
                          parede_abaixo_do_minimo)

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

# Observações REAIS (sem o aviso que o próprio guarda prefixou depois).
_OBS_PREDIO = ("Fonte: comprimento layer A-WALL = 736.86 m (medição direta do CAD, "
             "pelo eixo) × pé-direito 3.00 m (informado pelo cliente) = 2.210,58 m². "
             "Não foram descontados vãos de portas e janelas. Pé-direito informado "
             "por você; conta: 736.86 × 3.00 = 2.210,58 m².")
_OBS_ESCOLA = ("Cálculo: comprimento pelo eixo (layer A-PAREDE) = 294,11 m × "
               "pé-direito informado = 3,00 m = 882,33 m². Pé-direito informado pelo "
               "cliente no upload. Fonte: comprimento layer 'A-PAREDE' = 294,11 m; "
               "pé-direito informado = 3,00 m.")


def _it(disc, unit, qtd, desc, obs=""):
    return _It(discipline=disc, unit=unit, quantity=qtd, description=desc,
               observations=obs)


def _predio():
    return [
        _it("Fechamentos Verticais", "m²", 2210.58,
            "Alvenaria / divisória — paredes internas e externas", _OBS_PREDIO),
        _it("Fechamentos Verticais", "ml", 22.72,
            "Escada de concreto armado — degraus, espelho e patamares",
            "Fonte: comprimento do layer S-STRS = 22.72 m (medição direta do CAD)."),
        _it("Fechamentos Verticais", "ml", 9.31,
            "Guarda-corpo de escada — estrutura e montantes",
            "Fonte: comprimento do layer S-STRS-MBND = 9.31 m."),
    ]


def _escola():
    return [
        _it("Fechamentos Verticais", "m²", 882.33,
            "Alvenaria de bloco cerâmico — paredes internas e externas", _OBS_ESCOLA),
        _it("Fechamentos Verticais", "ml", 11.1, "Muro externo de divisa — alvenaria",
            "Layer 'MURO' = 11,10 m de comprimento. Fonte: comprimento layer 'MURO' = 11,10 m."),
        _it("Fechamentos Verticais", "ml", 10.0, "Cobogó em concreto 40×40 cm — H=1,20 m",
            "Total: 5 × 2,00 m = 10,00 ml. Fonte: texto layer 'ARQ-TXT-1_100'."),
    ]


def _trecho():
    i = _FONTE.index("_paredes_ml = [")
    i = _FONTE.rindex("\n", 0, i) + 1
    j = _FONTE.index("            if _impossivel:\n                _maior = max(_paredes_ml)", i)
    return textwrap.dedent(_FONTE[i:j])


def _roda(itens, area, liga, trecho=None):
    logs = []
    ns = {"all_items": itens, "_area_ref": area,
          "_compr_obs": comprimento_de_parede_na_observacao,
          "_par_min": parede_abaixo_do_minimo, "job_id": "teste",
          "_log_error": lambda etapa, msg, job, severity=None: logs.append((etapa, msg))}
    antes = os.environ.get("PAREDE_MINIMO_LE_LINHA_M2")
    os.environ["PAREDE_MINIMO_LE_LINHA_M2"] = "1" if liga else "0"
    try:
        exec(compile("import os\n" + (trecho or _trecho()), "<parede-m2>", "exec"), ns)
    finally:
        if antes is None:
            os.environ.pop("PAREDE_MINIMO_LE_LINHA_M2", None)
        else:
            os.environ["PAREDE_MINIMO_LE_LINHA_M2"] = antes
    return ns["_impossivel"], logs


# ── a leitura ──────────────────────────────────────────────────────────────
def test_le_as_duas_frases_reais():
    assert comprimento_na_linha_de_parede_m2(_predio()[0]) == 736.86
    assert comprimento_na_linha_de_parede_m2(_escola()[0]) == 294.11


def test_CONTROLE_a_leitura_antiga_nao_via_nenhuma():
    """Prova a causa: a frase velha não casa com nenhuma das duas."""
    assert comprimento_de_parede_na_observacao(_OBS_PREDIO) is None
    assert comprimento_de_parede_na_observacao(_OBS_ESCOLA) is None


def test_nunca_le_area_nem_volume():
    o = "comprimento equivalente = 882,33 m² ; comprimento útil = 12 m³"
    assert comprimento_na_linha_de_parede_m2(
        _it("Fechamentos Verticais", "m²", 1, "Alvenaria", o)) is None


def test_milhar_com_ponto_vira_numero_certo():
    o = "comprimento layer PAR = 1.234,50 m × 3,00 m"
    assert comprimento_na_linha_de_parede_m2(
        _it("Fechamentos Verticais", "m²", 1, "Alvenaria", o)) == 1234.5


def test_milhar_SEM_virgula_tambem():
    """🪤 O `_numero_br` antigo do módulo leria "1.234" como 1,234 m."""
    o = "comprimento layer PAR = 1.234 m × 3,00 m"
    assert comprimento_na_linha_de_parede_m2(
        _it("Fechamentos Verticais", "m²", 1, "Alvenaria", o)) == 1234.0


def test_so_linha_de_parede_em_m2():
    o = "comprimento layer X = 500 m"
    fora = [
        _it("Demolição e Remoção", "m²", 1, "Alvenaria a demolir", o),
        _it("Fechamentos Verticais", "m²", 1, "Demolição de alvenaria existente", o),
        _it("Fechamentos Verticais", "ml", 500, "Alvenaria", o),
        _it("Fechamentos Verticais", "m²", 1, "Cobogó em concreto", o),
        _it("Revestimentos de Parede", "m²", 1, "Pintura de parede", o),
    ]
    for f in fora:
        assert comprimento_na_linha_de_parede_m2(f) is None, f


# ── o motor ────────────────────────────────────────────────────────────────
def test_DESLIGADA_o_motor_continua_igual_e_so_registra():
    for itens, area in ((_predio(), 1348.44), (_escola(), 234.3)):
        imp, logs = _roda(itens, area, liga=False)
        assert imp, "com a chave em 0 nada pode mudar na planilha"
        assert [e for e, _ in logs] == ["motor:parede-minimo-linha-m2"], logs
        assert "liga=0" in logs[0][1]


def test_LIGADA_os_dois_casos_param_de_acusar():
    for itens, area in ((_predio(), 1348.44), (_escola(), 234.3)):
        imp, logs = _roda(itens, area, liga=True)
        assert not imp, "737 m / 294 m de parede na linha e o aviso ainda acusa"
        assert "liga=1" in logs[0][1]


def test_CONTROLE_sem_a_leitura_nova_LIGADA_ainda_acusaria():
    """Mutação: tira a fonte nova do trecho — o caso tem que voltar a disparar."""
    t = _trecho()
    alvo = "_paredes_m2_escrito = [_c for _c in"
    assert alvo in t
    sem = t.replace(alvo, "_paredes_m2_escrito = [] and [_c for _c in", 1)
    imp, logs = _roda(_predio(), 1348.44, liga=True, trecho=sem)
    assert imp and logs == [], "a mutação não reproduziu o caso"


def test_nunca_CRIA_alarme():
    """Linha m² com comprimento CURTO e nada em metro: antes não acusava
    (sem fonte), e a fonte nova não pode passar a acusar."""
    o = "comprimento layer PAREDES = 5,00 m × 2,60 = 13 m²"
    itens = [_it("Fechamentos Verticais", "m²", 13, "Alvenaria", o)]
    imp, logs = _roda(itens, 500.0, liga=True)
    assert not imp and logs == []


def test_CONTROLE_alarme_verdadeiro_continua():
    """Parede curta de verdade, também na linha m²: o guarda segue acusando."""
    o = "comprimento layer PAREDES = 17,18 m × pé-direito 2,60 m = 44,67 m²"
    itens = [_it("Fechamentos Verticais", "m²", 44.67, "Alvenaria de vedação", o),
             _it("Fechamentos Verticais", "ml", 17.18, "Alvenaria de vedação",
                 "comprimento layer PAREDES = 17,18 m")]
    imp, logs = _roda(itens, 46.79, liga=True)
    assert imp and logs == []
