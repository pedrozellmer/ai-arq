# -*- coding: utf-8 -*-
"""A rede INTEIRA de tubo ao lado das linhas por diâmetro ganha o aviso "não some".

🩸 05/11/2026 (job 4e260fd6): a mesma leitura trouxe a lista por diâmetro (PVC
ø25 18,92 m, ø32 9,52 m…) e "Rede geral de tubulação de água fria — todos os
diâmetros" 145,57 m. `linhas_pai_e_filho` só reconhece "total" — passou calada.
🛑 REDE_INTEIRA_NAO_SOMA=1 põe o aviso; com 0 a etapa só anota.
🪤 Arquivos FICTÍCIOS (repositório público, regra nº6).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine_rules as er  # noqa: E402

ARQ = "hidraulica-pav.dxf"
DISC = "Instalações Hidráulicas"


def _l(desc, q, unit="ml", disc=DISC, ref=ARQ):
    return {"description": desc, "unit": unit, "quantity": q, "discipline": disc,
            "ref_sheet": ref}


def _caso_real():
    return [
        _l("Tubulação de água fria — PVC rígido soldável ø25 mm — ramal de distribuição", 18.92),
        _l("Tubulação de água quente — PEX monocamada ø22 mm com tubo bainha", 18.92),
        _l("Tubulação de água fria — PVC rígido soldável ø32 mm — ramal de distribuição", 9.52),
        _l("Tubulação de água fria — PVC rígido soldável ø20 mm — ramal de distribuição", 2.97),
        _l("Tubulação de água quente — PEX monocamada ø25 mm com tubo bainha", 20.86),
        _l("Tubulação de água fria — PVC rígido soldável ø22 mm — ramal de distribuição", 1.66),
        _l("Rede geral de tubulação de água fria — todos os diâmetros — pavimento tipo", 145.57),
        _l("Rede geral de tubulação de água quente — todos os diâmetros — pavimento tipo", 92.62),
        _l("Ramal de alimentação predial — tubulação PVC rígido ø32 mm — pavimento", 101.44),
        _l("Tubo bainha corrugado — proteção de tubulação PEX — água quente", 0.38),
    ]


def _por_indice(achados):
    return {a["indice"]: a for a in achados}


def test_o_caso_real_marca_as_duas_redes_cada_uma_com_o_proprio_sistema():
    ach = _por_indice(er.linhas_de_rede_inteira(_caso_real()))
    assert set(ach) == {6, 7}
    fria, quente = ach[6], ach[7]
    assert fria["indices_partes"] == [0, 2, 3, 5], "fria só com fria (sem a alimentação)"
    assert fria["soma_partes"] == 33.07 and fria["fecha"] is False
    assert quente["indices_partes"] == [1, 4], "quente só com quente; bainha sem ø fica fora"
    assert quente["soma_partes"] == 39.78


def test_sem_linhas_por_diametro_nao_ha_aviso():
    itens = [_l("Rede geral de tubulação de água fria — todos os diâmetros", 145.57),
             _l("Registro de gaveta — água fria", 3, unit="un")]
    assert er.linhas_de_rede_inteira(itens) == []


def test_outro_sistema_nao_conta_como_parte():
    itens = [_l("Rede geral de esgoto — todos os diâmetros", 80),
             _l("Tubulação de água fria PVC ø25 mm", 20)]
    assert er.linhas_de_rede_inteira(itens) == []


def test_rede_sem_sistema_nao_e_comparada():
    itens = [_l("Rede geral de tubulação — todos os diâmetros", 80),
             _l("Tubulação de água fria PVC ø25 mm", 20)]
    assert er.linhas_de_rede_inteira(itens) == []


def test_so_metro_o_aco_de_todas_as_bitolas_fica_de_fora():
    itens = [_l("Dobramento e montagem de armação CA-50 — todas as bitolas", 587.6, unit="kg"),
             _l("Armadura CA-50 ø10 mm", 300, unit="kg"),
             _l("Armadura CA-50 ø8 mm", 287.6, unit="kg")]
    assert er.linhas_de_rede_inteira(itens) == []


def test_outra_prancha_e_outra_disciplina_nao_sao_partes():
    itens = [_l("Rede geral de água fria — todos os diâmetros", 50),
             _l("Tubulação de água fria PVC ø25 mm", 20, ref="outra-prancha.dxf"),
             _l("Tubulação de água fria PVC ø32 mm", 10, disc="Outra")]
    assert er.linhas_de_rede_inteira(itens) == []


def test_linha_que_o_pai_e_filho_ja_marcou_nao_repete():
    itens = _caso_real()
    assert {a["indice"] for a in er.linhas_de_rede_inteira(itens, ja_marcadas=[6])} == {7}


def test_linha_com_total_fica_com_a_trava_antiga():
    itens = [_l("Total da rede geral de água fria — todos os diâmetros", 30),
             _l("Tubulação de água fria PVC ø25 mm", 20),
             _l("Tubulação de água fria PVC ø32 mm", 10)]
    assert er.linhas_de_rede_inteira(itens) == []
    assert len(er.linhas_pai_e_filho(itens)) == 1


def test_quando_fecha_o_achado_diz():
    itens = [_l("Rede geral de água fria — todos os diâmetros", 31),
             _l("Tubulação de água fria PVC ø25 mm", 20),
             _l("Tubulação de água fria PVC ø32 mm", 10)]
    (a,) = er.linhas_de_rede_inteira(itens)
    assert a["fecha"] is True and a["soma_partes"] == 30


def test_nao_altera_os_itens():
    itens = _caso_real()
    antes = [dict(i) for i in itens]
    er.linhas_de_rede_inteira(itens)
    assert itens == antes


# ══════════════════════════════════════════════════════════════════════════
#  Guardas do fonte
# ══════════════════════════════════════════════════════════════════════════
_SRC = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "main.py"), encoding="utf-8").read()


def test_a_chave_nasce_desligada_e_avaliavel():
    import main
    assert "REDE_INTEIRA_NAO_SOMA" in main._CHAVES_AVALIAVEIS
    assert "motor:rede-inteira-e-diametros" in main._STAGES_DIAGNOSTICO
    assert '_chave_do_job(job_id, "REDE_INTEIRA_NAO_SOMA") == "1"' in _SRC


def test_o_aviso_so_entra_com_a_chave_e_o_log_sai_sempre():
    i_aviso = _SRC.index("if _redes and _rede_liga:")
    i_log = _SRC.index('_log_error("motor:rede-inteira-e-diametros",\n')
    assert i_aviso < i_log
    assert "esta linha é a REDE INTEIRA" in _SRC[i_aviso:i_log]


def test_roda_antes_da_fusao_da_revisao_do_cliente():
    """A revisão do cliente sobrescreve a observação; o aviso vem ANTES (regra nº7)."""
    i_rede = _SRC.index("_redes = _rede_inteira(all_items")
    i_pf = _SRC.index("_paifilho = _linhas_pai_e_filho(all_items)")
    assert i_pf < i_rede
    assert i_rede < _SRC.index("_fundir_revisoes_do_cliente(", i_rede)
