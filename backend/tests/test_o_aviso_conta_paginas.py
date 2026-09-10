# -*- coding: utf-8 -*-
"""O aviso de prancha sem medição conta PÁGINAS e não chama de não medida a
página que foi medida.

🩸 10/09/2026 — job aec7cac2, um caderno único de 30+ páginas: a p11 estourou o
tempo, a p28 abortou (rc=-6) e a p27 foi MEDIDA com MemoryError numa etapa
posterior. O cliente leu "1 prancha(s) são densas demais (faltou memória)".
Estes guardas CHAMAM `main._avisos_da_medicao_pdfvec` e executam o bloco real
do `process_job`.
"""
import ast
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)


def _f(pagina, motivo, arquivo="caderno.pdf"):
    stem = "%s_p%d" % (arquivo.rsplit(".", 1)[0], pagina)
    return {"prancha": stem, "arquivo": arquivo, "motivo": motivo, "rc": 0,
            "pdf_path": "/tmp/" + arquivo, "pagina": pagina}


def _avisos(falhas, por_prancha=None):
    import main
    return main._avisos_da_medicao_pdfvec(falhas, por_prancha or {})


def test_o_caso_aec7cac2_tres_paginas_tres_motivos():
    falhas = [_f(11, "tempo"), _f(27, "memoria"), _f(28, "processo")]
    indice = {"caderno_p27": {"arquivo": "caderno.pdf", "pagina": 27, "rooms_m2": 94.8}}
    avisos, log = _avisos(falhas, indice)
    assert len(avisos) == 2, avisos
    nao, parte = avisos
    assert nao.startswith("⚠ 2 prancha(s) não puderam ser medidas geometricamente"), nao
    assert "caderno.pdf pág. 12" in nao and "caderno.pdf pág. 29" in nao, nao
    assert "pág. 28" not in nao, "a página MEDIDA voltou a ser anunciada como não medida"
    assert "densas demais" not in nao, (
        "frase de memória pra página que estourou o tempo e pra que abortou: %r" % nao)
    assert parte.startswith("⚠ 1 prancha(s) foram medidas"), parte
    assert "caderno.pdf pág. 28" in parte, parte
    for proibido in ("não puderam", "não deram tempo", "densas demais", "entrou na planilha"):
        assert proibido not in parte, (proibido, parte)
    assert "estimativa" in nao and "estimativa" in parte
    assert "2 prancha(s) sem medição (processo,tempo)" in log, log
    assert "1 medida(s) só em parte (memoria)" in log, log


def test_conta_PAGINAS_do_mesmo_arquivo_e_numera_a_partir_de_1():
    avisos, _ = _avisos([_f(0, "tempo"), _f(1, "tempo"), _f(2, "tempo")])
    assert len(avisos) == 1, avisos
    assert avisos[0].startswith("⚠ 3 prancha(s) não deram tempo"), avisos[0]
    for n in (1, 2, 3):
        assert "caderno.pdf pág. %d" % n in avisos[0], avisos[0]
    assert "pág. 0" not in avisos[0], avisos[0]


def test_a_mesma_pagina_registrada_duas_vezes_conta_uma():
    avisos, _ = _avisos([_f(4, "processo"), _f(4, "processo")])
    assert avisos[0].startswith("⚠ 1 prancha(s)"), avisos[0]


def test_frase_de_memoria_so_quando_TODAS_foram_memoria():
    so_memoria, _ = _avisos([_f(0, "memoria"), _f(1, "memoria")])
    assert "densas demais" in so_memoria[0], so_memoria
    misturado, _ = _avisos([_f(0, "memoria"), _f(1, "tempo")])
    assert "densas demais" not in misturado[0], misturado[0]
    assert "não puderam ser medidas geometricamente" in misturado[0], misturado[0]


def test_mais_de_3_paginas_diz_e_outras_e_conta_todas():
    avisos, _ = _avisos([_f(i, "tempo") for i in range(5)])
    assert avisos[0].startswith("⚠ 5 prancha(s)"), avisos[0]
    assert " e outras" in avisos[0], avisos[0]


def test_CONTROLE_sem_falha_ou_motivo_interno_nao_vira_aviso():
    assert _avisos([]) == ([], "")
    assert _avisos([_f(0, "curiosidade")]) == ([], "")
    assert _avisos([], {"caderno_p0": {"rooms_m2": 10.0}}) == ([], "")


def test_CONTROLE_pdf_de_uma_pagina_continua_com_a_frase_de_sempre():
    """Os 6 dos 7 avisos desde 02/09 que estavam certos não podem mudar de sentido."""
    avisos, log = _avisos([_f(0, "tempo", arquivo="planta.pdf")])
    assert avisos == ["⚠ 1 prancha(s) não deram tempo de ser medidas geometricamente "
                      "(planta.pdf pág. 1). Elas foram lidas assim mesmo, mas os itens delas "
                      "saem como estimativa — confira essas contra o projeto antes de fechar "
                      "orçamento."], avisos
    assert log == "1 prancha(s) sem medição (tempo): planta.pdf pág. 1", log


def test_o_consumidor_passa_o_INDICE_por_prancha():
    """Sem o índice, a página medida volta a ser anunciada como não medida — e a
    função pura continuaria verde."""
    from _corpo import fonte
    arvore = ast.parse(fonte("main.py"))
    chamadas = [n for n in ast.walk(arvore) if isinstance(n, ast.Call)
                and getattr(n.func, "id", None) == "_avisos_da_medicao_pdfvec"]
    assert len(chamadas) == 1, len(chamadas)
    assert [ast.unparse(a) for a in chamadas[0].args] == [
        "_pdfvec_falhas", "_pdfvec_por_prancha"], [ast.unparse(a) for a in chamadas[0].args]


def test_o_bloco_REAL_do_process_job_separa_a_pagina_medida():
    from test_medicao_de_pdf_tem_teto_de_memoria import _aviso_do_cliente
    avisos, logs = _aviso_do_cliente(
        [_f(27, "memoria"), _f(28, "processo")],
        {"caderno_p27": {"arquivo": "caderno.pdf", "pagina": 27}})
    assert len(avisos) == 2, avisos
    assert avisos[0].startswith("⚠ 1 prancha(s) não puderam ser medidas"), avisos
    assert avisos[1].startswith("⚠ 1 prancha(s) foram medidas"), avisos
    assert logs and logs[0][0][0] == "pdfvec:sem-medicao", logs
