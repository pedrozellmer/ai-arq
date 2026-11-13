# -*- coding: utf-8 -*-
"""PDF anexado a projeto que já tem CAD: fica fora da leitura, e o cliente sabe.

🩸 13/11/2026 — a cliente mandou o DWG e, 17 minutos depois, anexou 12 PDF das
pranchas (uma por bloco). O /add-file refez SÓ com o DWG — certo: o DWG já
tinha os 12 desenhos, e ler os dois contaria cada serviço duas vezes — e ela
recebeu a MESMA planilha sem uma palavra sobre os 12 arquivos.
📏 90 dias: 4 projetos com PDF anexado depois do CAD, os 4 descartados calados.

🔑 Chave AVISO_PDF_DO_ANEXO nasce em 0: desligada, só registra
`anexo:pdf-nao-lido`. Só os PDF DESTE pedido entram — o PDF antigo de um
projeto que começou em PDF e recebeu o CAD depois é o descarte desejado.

Os testes rodam o TRECHO REAL da rota, não uma cópia.
"""
import io
import os
import textwrap

from engine_rules import aviso_pdf_do_anexo_nao_lido

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _trecho():
    i = _FONTE.index("_enviados_set = set(_enviados)")
    i = _FONTE.rindex("\n", 0, i) + 1
    j = _FONTE.index("file_paths = _cads + _pdfs_ficam", i)
    return textwrap.dedent(_FONTE[i:j])


def _roda(file_paths, enviados, pdfs_ficam=(), liga=False, trecho=None):
    logs = []
    ns = {"file_paths": list(file_paths), "_enviados": list(enviados),
          "_pdfs_ficam": list(pdfs_ficam), "_avisos_ext": [], "job_id": "teste",
          "_log_error": lambda etapa, msg, job, severity=None: logs.append((etapa, msg))}
    antes = os.environ.get("AVISO_PDF_DO_ANEXO")
    os.environ["AVISO_PDF_DO_ANEXO"] = "1" if liga else "0"
    try:
        exec(compile("import os\n" + (trecho or _trecho()), "<anexo-pdf>", "exec"), ns)
    finally:
        if antes is None:
            os.environ.pop("AVISO_PDF_DO_ANEXO", None)
        else:
            os.environ["AVISO_PDF_DO_ANEXO"] = antes
    return ns["_avisos_ext"], logs


_W = "/tmp/aiarq_jobs/j"
_PDFS = ["ARQ_%02d_BLOCO.pdf" % i for i in range(2, 14)]


def _caso():
    paths = [_W + "/projeto.dwg"] + [_W + "/" + p for p in _PDFS]
    return paths, list(_PDFS)


def test_DESLIGADA_so_registra():
    paths, env = _caso()
    av, logs = _roda(paths, env, liga=False)
    assert av == [], "com a chave em 0 nada muda pro cliente"
    assert [e for e, _ in logs] == ["anexo:pdf-nao-lido"]
    assert "12 PDF" in logs[0][1] and "liga=0" in logs[0][1]


def test_LIGADA_o_cliente_le_o_aviso():
    paths, env = _caso()
    av, logs = _roda(paths, env, liga=True)
    assert len(av) == 1 and "Os 12 PDF que você anexou" in av[0], av
    assert "e mais 8" in av[0] and "contaria cada serviço duas vezes" in av[0]
    assert "liga=1" in logs[0][1]


def test_PDF_antigo_do_projeto_nao_e_noticia():
    """Projeto começou em PDF; agora chegou o DWG: o PDF fora é o desejado."""
    paths = [_W + "/planta.pdf", _W + "/planta.dwg"]
    av, logs = _roda(paths, ["planta.dwg"], liga=True)
    assert av == [] and logs == []


def test_PDF_de_outra_disciplina_que_fica_nao_entra():
    paths = [_W + "/arq.dwg", _W + "/eletrica.pdf"]
    av, logs = _roda(paths, ["eletrica.pdf"], pdfs_ficam=[_W + "/eletrica.pdf"], liga=True)
    assert av == [] and logs == []


def test_CONTROLE_sem_o_filtro_do_pedido_o_PDF_antigo_virava_aviso():
    t = _trecho()
    alvo = "and os.path.basename(p) in _enviados_set"
    assert alvo in t
    sem = t.replace(alvo, "", 1)
    paths = [_W + "/planta.pdf", _W + "/planta.dwg"]
    av, _ = _roda(paths, ["planta.dwg"], liga=True, trecho=sem)
    assert av, "a mutação não reproduziu o erro — o controle não prova nada"


def test_texto_singular_e_vazio():
    assert aviso_pdf_do_anexo_nao_lido([]) == ""
    um = aviso_pdf_do_anexo_nao_lido(["DET-005.pdf"])
    assert um.startswith("ℹ O PDF que você anexou (DET-005.pdf) não foi lido")


def test_o_nome_local_e_o_mesmo_que_subiu():
    """O filtro compara o nome local (sanitizado de novo na listagem) com o que
    subiu (já sanitizado): a sanitização tem que ser estável."""
    from main import _safe_local_filename as _s
    for n in ("ARQ_02_BLOCO_A.pdf", "PRJ_R00 AGO 2026 (1).pdf",
              "Planta Baixa — Térreo.pdf", "0000-ELE-PL-005-DET-R00.pdf"):
        assert _s(_s(n)) == _s(n), n


def test_as_duas_etapas_novas_sao_diagnostico_nao_erro():
    import main
    assert "anexo:pdf-nao-lido" in main._STAGES_DIAGNOSTICO
    assert "motor:parede-minimo-linha-m2" in main._STAGES_DIAGNOSTICO
