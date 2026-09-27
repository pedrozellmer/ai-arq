# -*- coding: utf-8 -*-
"""A mesma peça com selo em várias pranchas: o selo fica numa linha só.

🩸 27/09/2026 — triagem de 20–27/09: 287 linhas com selo e o aviso "aparece em
N pranchas". Restaurante de um andar em 11 DWG do Revit: a porta veneziana (4
reais) com selo em 5 plantas temáticas; o portão PPT03 — o mesmo elemento do
Revit — com selo em 4 pranchas. 🔑 Andar diferente é quantidade de verdade
(decisão de 06/09): só sai o selo, e só com prova de que é a MESMA peça.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from engine_rules import (  # noqa: E402
    MARCA_MESMA_PECA, PREFIXO_SELO_DA_CHAVE, ids_de_elemento_citados,
    mesmo_pavimento_entre_pranchas, selos_da_mesma_peca)
from models import BudgetItem, Confidence  # noqa: E402


def _ln(prancha, q, texto, servico="porta", unidade="un", selo="confirmado",
        origem="dxf_geom"):
    return {"prancha": prancha, "servico": servico, "unidade": unidade,
            "quantidade": q, "texto": texto, "selo": selo, "origem": origem}


_PPT03 = "Fonte: bloco 'pnl - PORTÃO DE ABRIR 01 - 2 FOLHAS1 - PPT03-4728387' — 1 un."


def test_o_mesmo_elemento_do_revit_em_4_pranchas_fica_com_um_selo():
    linhas = [_ln(p, 1, _PPT03, servico="portao") for p in (
        "ARQ01 - IMPLANTACAO.dwg", "ARQ02 - DETALHES CONSTRUCOES.dwg",
        "ARQ05 - PLANTA BAIXA - SUPERIOR.dwg", "ARQ07 - PLANTA LAYOUT - SUPERIOR.dwg")]
    saem = selos_da_mesma_peca(linhas)
    assert sorted(s["indice"] for s in saem) == [1, 2, 3], saem
    assert all(s["prancha_da_outra"] == "ARQ01 - IMPLANTACAO.dwg" for s in saem)
    assert "4728387" in saem[0]["motivo"]


def test_id_escrito_em_prosa_pela_ia_tambem_vale():
    assert ids_de_elemento_citados(
        "Fonte: 4 INSERTs do bloco 'HTB' (IDs 454096, 2314776, V21, 456232)"
    ) == {"454096", "2314776", "456232"}
    assert ids_de_elemento_citados("bloco 'PORTA 2FL' (ID: 2329765)") == {"2329765"}
    linhas = [_ln("FL02-PLANTA LAYOUT.dxf", 4, "IDs 454096, 2314776, V21, 456232"),
              _ln("FL10-PLANTA DE REVESTIMENTOS.dxf", 4, "IDs 2314776, 454096, V61, 456232")]
    assert [s["indice"] for s in selos_da_mesma_peca(linhas)] == [1]


def test_fica_o_selo_da_linha_de_maior_quantidade():
    # a planta de pisos contou 3 (e um deles é outra porta); a de revestimentos, 4
    a = _ln("FL04-PLANTA DE PISOS.dxf", 3,
            "blocos 'HTB - PORTA VENEZIANA - 0_70x2_10-2314776-PLANTA DE PISO' + "
            "'HTB - PORTA VENEZIANA - 0_70x2_10-456232-PLANTA DE PISO'")
    b = _ln("FL05-PLANTA DE REVESTIMENTOS.dxf", 4,
            "bloco 'HTB - PORTA VENEZIANA - 0_70x2_10-2314776' + "
            "'HTB - PORTA VENEZIANA - 0_70x2_10-456232' = 4 un")
    assert [s["indice"] for s in selos_da_mesma_peca([a, b])] == [0]
    assert [s["indice"] for s in selos_da_mesma_peca([b, a])] == [1]


def test_mesmo_bloco_mesma_quantidade_no_mesmo_pavimento():
    linhas = [_ln("ARQ05 - PLANTA BAIXA - SUPERIOR.dwg", 10,
                  "Fonte: bloco 'chuveiro quadrado_growarq' — 10 un", servico="chuveiro"),
              _ln("ARQ07 - PLANTA LAYOUT - SUPERIOR.dwg", 10,
                  "CONTAGEM DE BLOCOS — 'chuveiro quadrado_growarq': 10 un",
                  servico="chuveiro")]
    saem = selos_da_mesma_peca(linhas)
    assert [s["indice"] for s in saem] == [1]
    assert "mesmo pavimento" in saem[0]["motivo"]


def test_CONTROLE_andar_diferente_com_a_mesma_contagem_continua_somando():
    # decisão de 06/09: térreo e superior são quantidade de verdade
    for t1, t2 in (("ARQ06 - PLANTA LAYOUT - TERREO.dwg", "ARQ07 - PLANTA LAYOUT - SUPERIOR.dwg"),
                   ("BLOCO A - LAYOUT.dwg", "BLOCO B - LAYOUT.dwg"),
                   ("1 PAV - LAYOUT.dwg", "2 PAV - LAYOUT.dwg")):
        linhas = [_ln(t1, 10, "bloco 'Mesa LerHamn 2': 10 un", servico="mesa"),
                  _ln(t2, 10, "bloco 'Mesa LerHamn 2': 10 un", servico="mesa")]
        assert selos_da_mesma_peca(linhas) == [], (t1, t2)


def test_CONTROLE_quantidade_diferente_ou_prancha_nao_tematica():
    dif = [_ln("ARQ04 - PLANTA BAIXA - TERREO.dwg", 3, "bloco 'chuveiro q'", servico="chuveiro"),
           _ln("ARQ06 - PLANTA LAYOUT - TERREO.dwg", 4, "bloco 'chuveiro q'", servico="chuveiro")]
    assert selos_da_mesma_peca(dif) == []
    nt = [_ln("FL08-CORTES.dxf", 2, "bloco 'porta p1'"),
          _ln("FL09-FACHADAS.dxf", 2, "bloco 'porta p1'")]
    assert selos_da_mesma_peca(nt) == []


def test_CONTROLE_id_em_outro_servico_na_mesma_prancha_ou_sem_selo():
    base = _ln("FL02-PLANTA LAYOUT.dxf", 1, "bloco 'P-1893887'")
    # a tela anti-praga cita a porta: serviço diferente
    assert selos_da_mesma_peca([base, _ln("FL05-PLANTA DE REVESTIMENTOS.dxf", 1,
                                          "da porta 'P-1893887'", servico="tela")]) == []
    # a mesma prancha: não é "várias pranchas"
    assert selos_da_mesma_peca([base, _ln("FL02-PLANTA LAYOUT.dxf", 1, "bloco 'P-1893887'")]) == []
    # a outra está laranja, ou é a revisão do cliente
    assert selos_da_mesma_peca([base, _ln("FL05-X.dxf", 1, "bloco 'P-1893887'",
                                          selo="estimado")]) == []
    assert selos_da_mesma_peca([_ln("FL05-X.dxf", 1, "bloco 'P-1893887'",
                                    origem="revisao_cliente"), base]) == []


def test_CONTROLE_data_no_nome_do_bloco_nao_e_id():
    assert ids_de_elemento_citados(
        "bloco '94-Equipafacil-Forno-venamico-digitop-eletrico-5-esteiras-04112022'") == set()
    assert ids_de_elemento_citados("bloco 'X-20260919'") == set()
    assert ids_de_elemento_citados("SINAPI 106463") == set()


def test_mesmo_pavimento_entre_pranchas():
    assert mesmo_pavimento_entre_pranchas("1026.ARR.500.PONTOS.00", "1026.ARR.700.FORRO.00")
    assert mesmo_pavimento_entre_pranchas("ARQ04 - PLANTA BAIXA - TERREO", "ARQ11 - PLANTA DE FORRO - TERREO")
    assert not mesmo_pavimento_entre_pranchas("ARQ04 - PLANTA BAIXA - TERREO", "ARQ05 - PLANTA BAIXA - SUPERIOR")
    assert not mesmo_pavimento_entre_pranchas("FL02-PLANTA LAYOUT", "FL07-PLANTA DE COBERTURA")
    assert not mesmo_pavimento_entre_pranchas("FL08-CORTES", "FL09-FACHADAS")


def _item(ref, obs, q=1, conf="confirmado", desc="Portão de abrir 2 folhas PPT03"):
    return BudgetItem(item_num="1", description=desc, unit="un", quantity=q,
                      observations=obs, ref_sheet=ref, confidence=Confidence(conf),
                      origem="dxf_geom")


def test_o_caso_a_linha_fica_o_numero_fica_sai_o_selo_e_o_medido():
    a = _item("ARQ05 - PLANTA BAIXA - SUPERIOR.dwg", _PPT03)
    b = _item("ARQ07 - PLANTA LAYOUT - SUPERIOR.dwg",
              PREFIXO_SELO_DA_CHAVE + "contagem conferida. " + _PPT03)
    assert main._tira_selo_da_mesma_peca([a, b]) == 1
    assert a.confidence == Confidence("confirmado")
    assert b.confidence == Confidence("estimado") and b.quantity == 1
    assert b.observations.startswith(MARCA_MESMA_PECA), b.observations
    assert "ARQ05 - PLANTA BAIXA - SUPERIOR" in b.observations
    assert PREFIXO_SELO_DA_CHAVE not in b.observations, "diz MEDIDO numa linha estimada"
    assert _PPT03 in b.observations, "a observação da leitura sumiu"


def test_o_process_job_tira_o_selo_depois_das_portas_e_antes_dos_avisos():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "main.py"), encoding="utf-8").read()
    ini = src.index("\ndef process_job(")
    fim = src.index("\ndef ", ini + 10)
    corpo = src[ini:fim]
    assert corpo.count("_tira_selo_da_mesma_peca(all_items)") == 1, "não é chamada (ou 2×)"
    aqui = corpo.index("_tira_selo_da_mesma_peca(all_items)")
    assert corpo.index("_chave_tabela(_linhas_tab, _nums_tab)") < aqui, \
        "roda antes da tabela impressa — ela devolveria o selo"
    assert corpo.index("_chave_selo(all_items, _idx_selo)") < aqui, \
        "roda antes da chave — ela devolveria o selo"
    assert aqui < corpo.index("# 🚨 AQUI é o fim da fila de quem rebaixa selo"), \
        "roda depois dos avisos que contam o selo"
