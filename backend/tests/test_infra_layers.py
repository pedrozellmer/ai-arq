# -*- coding: utf-8 -*-
"""Lista branca de layers de INFRA LINEAR medidos DENTRO de bloco.

Por que este teste existe: a allowlist morava DENTRO da função de extração,
onde nenhum teste a alcançava. Ela nasceu de um caso de eletroduto (Engie,
21/07/2026) e envelheceu falando só a língua da ELÉTRICA — sem ninguém notar.

Em 04/08/2026 uma cliente de climatização subiu um projeto hospitalar com os
dutos desenhados dentro de blocos. O motor achou as camadas certas e devolveu
ZERO metro em todas as redes, porque 'duto' não estava na lista e 'tubula' não
pegava as abreviações. Era exatamente a pergunta que ela tinha feito antes de
criar a conta.

🔒 Regra nº1: comprimento medido vira linha BRANCA. Termo frouxo aqui INVENTA
medição — por isso os casos negativos importam tanto quanto os positivos.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from dwg_extractor import INFRA_LINEAR_RX  # noqa: E402

_passed = 0
_failed = 0


def check(nome, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok  {nome}")
    else:
        _failed += 1
        print(f"  XX  {nome}")


# ── DEVE medir: layers reais de projeto de climatização (caso ConfortAr) ──────
for _lay in ["LCVP_DUTOS_INS", "LCVP_DUTO_RET", "LCVP_DUTO_EXAUSTAO",
             "LCVP_DUTOFLEX_INSF", "LCVP_DUTO_AREXTERIOR", "SOL_DUTOS_EX2",
             "HVAC-DUTOS-EXA-1", "LCVP_TUBUL AAG", "LCVP_TUBUL RAG",
             "LCVP_TUB_FRIG", "VAC-TUB-FRIG",
             "HVAC-TUBULAÇÕES-AGUA-GELADA-1"]:
    check(f"clima mede: {_lay}", INFRA_LINEAR_RX.search(_lay) is not None)

# ── DEVE medir: o vocabulário de elétrica/hidráulica que já funcionava ────────
for _lay in ["ELETRODUTO", "E-ELETROCALHA", "MATRIZ-CONDULETE", "CONDUITE",
             "PRUMADA-AF", "RAMAL-ESGOTO", "CANALETA-PISO", "PERFILADO",
             "BARRAMENTO-BLINDADO", "TUBULACAO-INCENDIO"]:
    check(f"infra segue medindo: {_lay}", INFRA_LINEAR_RX.search(_lay) is not None)

# ── NÃO pode medir: senão vira metro inventado em linha branca ────────────────
# 🪤 'PRODUTO' contém 'duto'. Sem o guard de "letra antes", todo layer de
# produto/mobiliário viraria infra linear medida.
for _lay in ["PRODUTOS", "ARQ-PRODUTO", "PRODUTO-ACABADO",
             "MOB-MOBILIARIO", "A-WALL", "ARQ-PISO", "PAREDE", "FORRO",
             "LEITO HOSPITALAR", "LEGENDA", "TEXTO", "COTAS",
             "LCVP_DIFUSOR_INSF", "LCVP_GRELHA_RET", "ARQ-ESQUADRIAS"]:
    check(f"NAO mede: {_lay}", INFRA_LINEAR_RX.search(_lay) is None)

print()
print(f"RESULTADO: {_passed} passaram, {_failed} falharam")
sys.exit(1 if _failed else 0)
