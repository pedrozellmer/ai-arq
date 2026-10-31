# -*- coding: utf-8 -*-
"""A mesma tabela de esquadrias lida em várias pranchas não soma.

🩸 31/10/2026 (01e6bfad): a tabela vinha em cada pavimento com o total do prédio.
"PS-02, QNT=352" saiu em 3 linhas, com descrições diferentes, e a fusão só junta
descrição parecida. 📏 60 dias: só este job, 53 códigos, 73 linhas, 1.393 de 2.459 un.
🪤 Mesma quantidade não prova: "4 por pavimento" é contagem, e somar é o certo.
🔑 TABELA_REPETIDA_UMA_LINHA=1 deixa uma linha; com 0 o motor só conta.
As observações abaixo são as do banco (cortadas).
"""
import os
import sys
import textwrap

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
import pytest  # noqa: E402
import main  # noqa: E402
from engine_rules import grupos_da_tabela_repetida as _grupos  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402


def _it(d, q=352, obs="Quantidade confirmada pelo quadro de esquadrias (coluna QNT = 352).",
        folha="ARQ-003.pdf", unit="un", cf="estimado", origem="vision_pdf"):
    return BudgetItem(item_num="1", description=d, unit=unit, quantity=q, observations=obs,
                      ref_sheet=folha + " (planta baixa)", confidence=Confidence(cf),
                      discipline="Portas e Ferragens", origem=origem)


def _caso():
    return [
        _it("Shaft PS-02 — MDF amadeirado ou equivalente — 70×170cm",
            obs="Quantidade extraída da Tabela de Esquadria - Shafts: PS-02, QNT=352."),
        _it("Porta tipo PS-02 — MDF amadeirado ou equivalente, dimensões 70×170cm",
            folha="ARQ-009.pdf"),
        _it("Shaft de MDF amadeirado ou equivalente — tipo PS-02 — dimensão 70x170cm",
            folha="ARQ-007.pdf", obs="Tabela de Esquadrias - Shafts. QNT explícita = 352."),
    ]


def test_o_caso_vira_um_grupo():
    g = _grupos(_caso() + [_it("Porta PA-02 — alumínio", q=168, obs="QNT: 168", folha="B.pdf")])
    assert len(g) == 1 and len(g[0]) == 3


@pytest.mark.parametrize("obs", ["QNT=352", "QNT = 352", "QNT: 352", "QNT explícita = 352",
                                 "QTD 352", "Qtd. 352", "Qt 352", "coluna QNT = 352."])
def test_as_formas_de_dizer_que_leu(obs):
    assert _grupos([_it("Porta PS-02", obs=obs), _it("Shaft PS-02", obs=obs, folha="B.pdf")])


def test_codigo_sem_hifen_e_com_letra():
    a, b = _it("Porta P02", obs="QNT=352"), _it("Porta tipo P02", obs="QNT=352", folha="B.pdf")
    assert _grupos([a, b])
    a, b = _it("Porta PA-01a", obs="QNT=352"), _it("Porta tipo PA-01a", obs="QNT=352", folha="B.pdf")
    assert _grupos([a, b])


def test_CONTROLE_contagem_por_pavimento_nao_e_tabela():
    obs = "Contagem visual na planta: 2 por unidade × 2 unidades = 4 por pavimento."
    assert not _grupos([_it("Janela J01", q=4, obs=obs), _it("Janela J01", q=4, obs=obs, folha="B.pdf")])


def test_CONTROLE_citar_o_quadro_sem_ler_o_numero_nao_vale():
    obs = "Confirmar com quadro de esquadrias."
    assert not _grupos([_it("Porta P1", q=4, obs=obs), _it("Porta P1", q=4, obs=obs, folha="B.pdf")])


def test_CONTROLE_contagem_visual_que_cita_qnt_nao_vale():
    obs = "Contagem visual, QNT=352 a conferir."
    assert not _grupos([_it("Porta PS-02", obs=obs), _it("Porta PS-02", obs=obs, folha="B.pdf")])


def test_CONTROLE_o_numero_lido_tem_de_ser_o_da_linha():
    assert not _grupos([_it("Porta PA-12", q=4, obs="QNT=1"), _it("Porta PA-12", q=4, obs="QNT=1", folha="B.pdf")])


def test_CONTROLE_quantidades_diferentes_nao_juntam():
    assert not _grupos([_it("Porta PS-02", q=2, obs="QNT=2"), _it("Porta PS-02", q=3, obs="QNT=3", folha="B.pdf")])


def test_CONTROLE_codigos_diferentes_nao_juntam():
    assert not _grupos([_it("Porta PS-02", obs="QNT=352"), _it("Porta PS-03", obs="QNT=352", folha="B.pdf")])


def test_CONTROLE_a_letra_do_codigo_e_outra_porta():
    assert not _grupos([_it("Porta PA-01", obs="QNT=352"), _it("Porta PA-01a", obs="QNT=352", folha="B.pdf")])


def test_CONTROLE_na_mesma_prancha_nao_junta():
    assert not _grupos([_it("Porta PS-02", obs="QNT=352"), _it("Shaft PS-02", obs="QNT=352")])


def test_CONTROLE_folha_e_a_parte_antes_do_parentese():
    a, b = _it("Porta PS-02", obs="QNT=352"), _it("Shaft PS-02", obs="QNT=352")
    b.ref_sheet = "ARQ-003.pdf (outra vista)"
    assert not _grupos([a, b])


def test_CONTROLE_so_peca_contada():
    assert not _grupos([_it("Porta PS-02", obs="QNT=352", unit="m²"),
                        _it("Shaft PS-02", obs="QNT=352", unit="m²", folha="B.pdf")])


def test_CONTROLE_linha_zerada_nao_entra():
    assert not _grupos([_it("Porta PS-02", q=0, obs="QNT=0"), _it("Shaft PS-02", q=0, obs="QNT=0", folha="B.pdf")])


def test_CONTROLE_o_que_o_cliente_escreveu_nao_se_mexe():
    assert not _grupos([_it("Porta PS-02", obs="QNT=352", origem="revisao_cliente"),
                        _it("Shaft PS-02", obs="QNT=352", folha="B.pdf")])


def test_so_conta_nao_mexe_em_nada():
    itens = _caso()
    obs = [i.observations for i in itens]
    r, n = main._junta_tabela_repetida(itens, so_conta=True)
    assert n == 2 and r is itens and [i.observations for i in itens] == obs


def test_ligada_fica_uma_linha_com_o_total():
    r, n = main._junta_tabela_repetida(_caso())
    assert n == 2 and len(r) == 1 and r[0].quantity == 352


def test_a_linha_diz_o_que_saiu():
    o = main._junta_tabela_repetida(_caso())[0][0].observations
    assert "se repete em 3 pranchas" in o and "352 un" in o and "As outras:" in o and "Shaft" in o
    assert o.startswith("Quantidade extraída") or o.startswith("Tabela") or o.startswith("Quantidade confirmada")


def test_o_selo_da_linha_lida_fica():
    itens = _caso()
    itens[1].confidence = Confidence("confirmado")
    r = main._junta_tabela_repetida(itens)[0]
    assert r == [itens[1]] and r[0].confidence == Confidence("confirmado")


def test_quem_nao_e_do_grupo_fica_na_ordem():
    fora = _it("Porta P9", q=7, obs="sem número", folha="Z.pdf")
    r = main._junta_tabela_repetida([fora] + _caso())[0]
    assert r[0] is fora and len(r) == 2


def test_sem_grupo_devolve_a_mesma_lista():
    itens = [_it("Porta P9", q=7, obs="sem número")]
    assert main._junta_tabela_repetida(itens) == (itens, 0)


# ── o bloco do process_job, executado de verdade ──
_INICIO = "        # 🩸 31/10: a tabela de esquadrias repetida nas pranchas"
_FIM = "motor:tabela-repetida\", f\"FALHOU: {_etr}\", job_id,\n                       severity=\"warning\")\n"


def _bloco():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read().replace("\r\n", "\n")
    i = src.index(_INICIO)
    return src[i:src.index(_FIM, i) + len(_FIM)]


def _rodar(monkeypatch=None, liga=False, chave=None):
    logs = []
    ns = {"all_items": _caso(), "job_id": "t1", "_junta_tabela_repetida": main._junta_tabela_repetida,
          "_log_error": lambda st, msg, job=None, severity="error": logs.append((st, msg))}
    if chave is not None:
        ns["_chave_do_job"] = lambda job, nome: chave
    else:
        monkeypatch.setenv("TABELA_REPETIDA_UMA_LINHA", "1" if liga else "0")
    exec(textwrap.dedent(_bloco()), ns)
    return ns["all_items"], logs


def test_com_a_chave_em_0_so_registra(monkeypatch):
    r, logs = _rodar(monkeypatch, False)
    assert len(r) == 3 and logs == [("motor:tabela-repetida", "linhas=2 liga=0")]


def test_com_a_chave_em_1_fica_uma(monkeypatch):
    r, logs = _rodar(monkeypatch, True)
    assert len(r) == 1 and logs == [("motor:tabela-repetida", "linhas=2 liga=1")]


@pytest.mark.parametrize("valor,linhas", [("1", 1), ("0", 3)])
def test_a_chave_vem_do_job(valor, linhas):
    # é o caminho de produção: a avaliação isolada liga a chave só naquele job
    assert len(_rodar(chave=valor)[0]) == linhas


def test_roda_depois_da_consolidacao_e_antes_de_validar():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read()
    i = src.index(_INICIO)
    assert src.index("all_items = _consolidate_by_type_code(all_items, project_data)") < i
    assert i < src.index("# Validar qty/unit após consolidação")


def test_a_chave_e_avaliavel_e_o_log_e_diagnostico():
    assert "TABELA_REPETIDA_UMA_LINHA" in main._CHAVES_AVALIAVEIS
    assert "motor:tabela-repetida" in main._STAGES_DIAGNOSTICO
