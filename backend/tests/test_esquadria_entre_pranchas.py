# -*- coding: utf-8 -*-
"""A mesma esquadria (mesmo código) contada em mais de uma prancha ganha aviso.

🩸 13/11/2026, dois projetos no mesmo dia. Um mandou DWG + PDF das mesmas
pranchas (mapa de esquadrias e fachadas) e uma veneziana saiu em 4 linhas
(8 + 8 + 8 + 6 = 30, onde há 8). Outro mandou uma casa em PDF e cada porta saiu
2× — 1 da planta baixa, 1 do mapa de esquadrias. A passada 6 ("aparece em N
pranchas") agrupa pelo SUBSTANTIVO e calava; aqui o agrupamento é pelo CÓDIGO.

🔑 Só AVISA (chave ESQUADRIA_ENTRE_PRANCHAS_AVISA nasce em 0). Código só em
plantas de andares diferentes não entra. Dados sintéticos, na FORMA dos casos.
"""
import os
import textwrap
from types import SimpleNamespace

import main
from engine_rules import (MARCA_MESMA_ESQUADRIA, aviso_da_mesma_esquadria,
                          esquadria_em_varias_pranchas)

_AQUI = os.path.dirname(os.path.abspath(__file__))


def _it(desc, ref, q=1, un="un", disc="Portas e Ferragens", obs=""):
    return SimpleNamespace(description=desc, ref_sheet=ref, quantity=q, unit=un,
                           discipline=disc, observations=obs)


_PLANTA = "PEA 1 Planta Baixa.pdf (Planta Baixa Térreo)"
_MAPA = "PEC 9 Mapa de Esquadrias.pdf (Mapa de Esquadrias)"


def _casa():
    return [
        _it("Porta P01 — Abrir Simples — 90×210 cm — Material: Alumínio, Vidro, "
            "Soleira de Pedra", _PLANTA),
        _it("Porta P01 — Esquadria de alumínio preto com vidro opaco, dimensões "
            "0,90×2,10m, soleira de pedra", _MAPA),
        _it("Porta P03 — Abrir Simples — 80×210 cm — Material: Madeira", _PLANTA),
        _it("Porta P03 — Semi-sólida de madeira, dimensões 0,80×2,10m", _MAPA),
    ]


# ── a regra ──────────────────────────────────────────────────────────────────
def test_planta_e_mapa_de_esquadrias():
    g = esquadria_em_varias_pranchas(_casa())
    assert [x["codigo"] for x in g] == ["P01", "P03"]
    assert g[0]["indices"] == [0, 1]


def test_soleira_no_meio_da_linha_nao_faz_da_porta_um_acessorio():
    """🩸 A 1ª versão procurava 'soleira' em qualquer lugar e calava o caso
    inteiro que motivou a regra."""
    assert esquadria_em_varias_pranchas(_casa()[:2])


def test_dwg_e_pdf_da_mesma_folha_mesmo_sem_palavra_de_mapa():
    itens = [_it("Veneziana VZ07 — 200×140", "0000-ARQ-PE-200-PLANTA-R02.dxf", q=8),
             _it("Veneziana VZ07 — 2,00×1,40 m", "0000-ARQ-PE-200-PLANTA-R02 (1).pdf (Planta)", q=8)]
    assert [x["codigo"] for x in esquadria_em_varias_pranchas(itens)] == ["VZ07"]


def test_fachada_reconta_a_janela_da_planta():
    itens = [_it("Janela J02 — correr 120×100", "04 - PL BAIXA 3o PVTO.dxf", q=4,
                 disc="Esquadrias"),
             _it("Janela de correr — código J02 — 120×100", "14 - FACHADA 04.dxf", q=5,
                 disc="Esquadrias")]
    assert esquadria_em_varias_pranchas(itens)


def test_so_plantas_de_andares_diferentes_nao_avisa():
    itens = [_it("Porta P01 — 80×210", "01 TERREO.pdf (Planta Térreo)", q=4),
             _it("Porta P01 — 80×210", "02 SUPERIOR.pdf (Planta Superior)", q=3)]
    assert esquadria_em_varias_pranchas(itens) == []


def test_duas_paginas_do_mesmo_pdf_nao_sao_cad_e_pdf():
    itens = [_it("Porta P01 — 80×210", "proj.pdf (p1 · Planta Térreo)", q=4),
             _it("Porta P01 — 80×210", "proj.pdf (p2 · Planta Superior)", q=3)]
    assert esquadria_em_varias_pranchas(itens) == []


def test_mesmo_codigo_com_medidas_diferentes_e_outra_peca():
    itens = [_it("Porta P2 — alumínio, 170×240 cm", "F07 - PRÉDIO A.pdf (Quadro de Esquadrias)", q=4),
             _it("Porta P2 — alumínio, dimensões 0,80 × 2,10 m", "F08 - PRÉDIO B.pdf (Quadro de Esquadrias)")]
    assert esquadria_em_varias_pranchas(itens) == []


def test_mesmo_codigo_com_materiais_que_nao_se_cruzam_e_outra_peca():
    itens = [_it("Porta P1 — madeira, 80×210 cm", "F07 - PRÉDIO A.pdf (Quadro de Esquadrias)", q=3),
             _it("Porta P1 — veneziana de alumínio, 0,80 × 2,10 m", "F08 - PRÉDIO B.pdf (Quadro de Esquadrias)", q=2)]
    assert esquadria_em_varias_pranchas(itens) == []


def test_acessorio_demolicao_e_zerada_nao_entram():
    base = _casa()[:1]
    for extra in (_it("Conjunto de ferragens para porta P01 — fechadura e dobradiças", _MAPA),
                  _it("Barra antipânico para porta P01", _MAPA),
                  _it("Demolição de porta P01 existente", _MAPA),
                  _it("Porta P01 — 0,90×2,10m", _MAPA, q=0)):
        assert esquadria_em_varias_pranchas(base + [extra]) == [], extra.description


def test_texto_corrido_minusculo_nao_e_codigo():
    itens = [_it("Porta de abrir p/ 2 folhas — 80×210", _PLANTA),
             _it("Porta de abrir p/ 2 folhas — 80×210", _MAPA)]
    assert esquadria_em_varias_pranchas(itens) == []


def test_aceita_dict_como_o_banco_devolve():
    itens = [vars(x) for x in _casa()]
    assert [g["codigo"] for g in esquadria_em_varias_pranchas(itens)] == ["P01", "P03"]


def test_o_aviso_cita_o_codigo_e_a_outra_prancha_e_e_condicional():
    t = aviso_da_mesma_esquadria("VZ07", [_MAPA])
    assert t.startswith(MARCA_MESMA_ESQUADRIA)
    assert "VZ07" in t and "Mapa de Esquadrias" in t
    assert "não some" in t and "outro prédio ou pavimento, soma" in t


# ── o bloco do process_job, executado de verdade ─────────────────────────────
_INICIO = "        # 🩸 14/11: a MESMA esquadria (mesmo código) contada na planta e de novo"
_FIM = ("motor:esquadria-entre-pranchas\", f\"FALHOU: {_eesq2}\", job_id,\n"
        "                       severity=\"warning\")\n")


def _bloco():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read().replace("\r\n", "\n")
    i = src.index(_INICIO)
    return src[i:src.index(_FIM, i) + len(_FIM)]


def _rodar(valor, itens=None, bloco=None):
    logs = []
    itens = itens or _casa()
    ns = {"all_items": itens, "job_id": "t1",
          "_chave_do_job": lambda job, chave: valor if chave == "ESQUADRIA_ENTRE_PRANCHAS_AVISA" else "0",
          "_observacao_que_cabe": main._observacao_que_cabe,
          "_log_error": lambda st, msg, job=None, severity="error": logs.append(
              (st, msg.split(" | ")[0]))}
    exec(textwrap.dedent(bloco or _bloco()), ns)
    return itens, logs


def test_a_chave_em_0_so_registra():
    itens, logs = _rodar("0")
    assert not any(MARCA_MESMA_ESQUADRIA in (i.observations or "") for i in itens)
    assert logs == [("motor:esquadria-entre-pranchas", "codigos=2 linhas=4 liga=0")]


def test_a_chave_em_1_avisa_cada_linha_citando_a_OUTRA_prancha():
    itens, logs = _rodar("1")
    assert [i.quantity for i in itens] == [1, 1, 1, 1], "mexeu no número"
    assert len(itens) == 4, "apagou linha"
    assert itens[0].observations.startswith(MARCA_MESMA_ESQUADRIA)
    assert "Mapa de Esquadrias" in itens[0].observations
    assert "Planta Baixa" in itens[1].observations
    assert logs == [("motor:esquadria-entre-pranchas", "codigos=2 linhas=4 liga=1")]


def test_a_planilha_refeita_nao_repete_o_aviso():
    itens, _ = _rodar("1")
    itens, _ = _rodar("1", itens)
    assert all(i.observations.count(MARCA_MESMA_ESQUADRIA) == 1 for i in itens)


def test_CONTROLE_sem_a_trava_de_medida_os_dois_predios_disparavam():
    """Mutação: tira o `continue` das medidas diferentes — o caso dos dois
    prédios tem de voltar a disparar (prova que o teste reprova sem a trava)."""
    import engine_rules
    import inspect
    fonte = inspect.getsource(engine_rules.esquadria_em_varias_pranchas)
    alvo = "        if len(dims) > 1:\n            continue\n"
    assert alvo in fonte.replace("\r\n", "\n")
    mutada = textwrap.dedent(fonte.replace("\r\n", "\n").replace(alvo, ""))
    ns = dict(vars(engine_rules))
    exec(mutada, ns)
    itens = [_it("Porta P2 — alumínio, 170×240 cm", "F07 - PRÉDIO A.pdf (Quadro de Esquadrias)", q=4),
             _it("Porta P2 — alumínio, dimensões 0,80 × 2,10 m", "F08 - PRÉDIO B.pdf (Quadro de Esquadrias)")]
    assert ns["esquadria_em_varias_pranchas"](itens), "a mutação não reproduziu o caso"


def test_nasce_desligada_e_avaliavel():
    assert "ESQUADRIA_ENTRE_PRANCHAS_AVISA" in main._CHAVES_AVALIAVEIS
    assert "motor:esquadria-entre-pranchas" in main._STAGES_DIAGNOSTICO


def test_o_bloco_roda_antes_da_planilha():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read()
    i = src.index(_INICIO)
    assert i < src.index("generate_spreadsheet(project_data, all_items, output_path, typology=typology)", i)
