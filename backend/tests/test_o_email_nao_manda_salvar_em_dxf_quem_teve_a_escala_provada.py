# -*- coding: utf-8 -*-
"""O e-mail "leu, mas não mediu" não culpa a escala nem pede DXF a quem teve a
escala do CAD conferida.

🩸 13/10/2026: um DWG lido inteiro, escala provada por 200 cotas, nenhuma linha
com selo. O cliente leu "o motivo costuma ser escala: sem cota, sem carimbo
confiável e sem viewport" e "o que resolve: mande a mesma planta em DXF" — e, na
página do projeto, "✅ Escala conferida pelo próprio desenho". Reenviar em DXF
não muda nada: o DWG vira DXF aqui dentro. Em 60 dias, 4 dos 23 e-mails "sem
quantidade medida do CAD" saíram assim.

Roda a fatia REAL do fim do `process_job` com o resumo de escala no lugar onde o
laço dos CAD o deixa. Controles: sem a prova (ou com UM arquivo sem ela) o texto
é o de antes; só-PDF e DWG que não abriu continuam com o motivo deles.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402
from _fim_do_job import roda_ate_o_email  # noqa: E402
from test_o_email_do_pdf_nao_promete_o_que_o_pdf_nao_da import _itens_do_caso  # noqa: E402

_COSTUMA_SER_ESCALA = "O motivo costuma ser escala"
_MANDE_EM_DXF = "mande a mesma planta em <b>DXF</b>"
_NAO_E_ESCALA = "O motivo não é a escala nem o formato do arquivo"
_NAO_PRECISA = "Não precisa reenviar em outro formato"

_PROVADA = {"nome": "planta-geral", "status": "cotas", "n": 200, "digitadas": 7,
            "unidade": "metros", "corrigida": True}
_SEM_PROVA = {"nome": "detalhes", "status": "sem_prova", "declarada": "Milímetros"}
_SUSPEITA = {"nome": "detalhes", "status": "alerta", "declarada": "Milímetros",
             "alerta": "Unidade suspeita"}


def _email(escala, **kw):
    kw.setdefault("project_type", "arquitetura")
    kw.setdefault("n_pdf", 0)
    kw.setdefault("n_cad", 1)
    d = roda_ate_o_email(_itens_do_caso(), nome_projeto="Projeto 13/10/2026",
                         job_id="job-escala",
                         antes_do_email=(None if escala is None else {"_escala_arqs": escala}),
                         **kw)
    e = d["emails"][-1]
    assert e["kind"] == "leu_sem_medir", e["kind"]
    return e


def test_o_caso_escala_provada_o_motivo_nao_e_escala_e_ninguem_pede_dxf():
    html = _email([_PROVADA])["html"]
    assert _NAO_E_ESCALA in html and _NAO_PRECISA in html, html[:2500]
    assert _COSTUMA_SER_ESCALA not in html and _MANDE_EM_DXF not in html, html[:2500]
    assert "DXF 2013" not in html and "Se só existe o PDF" not in html


def test_o_assunto_e_o_fato_continuam_os_do_CAD():
    e = _email([_PROVADA])
    assert e["assunto"].endswith("sem quantidade medida do CAD"), e["assunto"]
    assert "nenhuma quantidade foi medida do CAD" in e["html"]


def test_com_DWG_e_PDFs_no_mesmo_envio_vale_a_escala_do_CAD():
    # o caso: 1 DWG + 8 PDFs
    html = _email([_PROVADA], n_pdf=8)["html"]
    assert _NAO_E_ESCALA in html and _MANDE_EM_DXF not in html, html[:2500]


def test_CONTROLE_sem_prova_de_escala_o_texto_e_o_de_antes():
    html = _email([_SEM_PROVA])["html"]
    assert _COSTUMA_SER_ESCALA in html and _MANDE_EM_DXF in html, html[:2500]
    assert _NAO_E_ESCALA not in html and _NAO_PRECISA not in html


def test_CONTROLE_um_arquivo_sem_prova_basta_pra_nao_afirmar():
    for outro in (_SEM_PROVA, _SUSPEITA):
        html = _email([_PROVADA, outro], n_cad=2)["html"]
        assert _COSTUMA_SER_ESCALA in html and _NAO_E_ESCALA not in html, outro


def test_CONTROLE_sem_o_resumo_de_escala_nada_e_afirmado():
    # a fatia sem o laço dos CAD (o nome nem existe) e a lista vazia
    for escala in (None, []):
        html = _email(escala)["html"]
        assert _COSTUMA_SER_ESCALA in html and _NAO_E_ESCALA not in html, escala


def test_CONTROLE_as_outras_provas_de_escala_tambem_valem():
    for status in ("rotulo", "consenso", "nota"):
        html = _email([dict(_PROVADA, status=status)])["html"]
        assert _NAO_E_ESCALA in html, status


def test_CONTROLE_o_montador_sozinho_so_pdf_e_dwg_que_nao_abriu_seguem_com_o_motivo_deles():
    args = ("Fulano", "Projeto", "job-x", 100, 40)
    _s, pdf = main._build_leu_sem_medir_email(*args, so_pdf=True, cad_com_escala_provada=True)
    assert "uma regra nossa, não um defeito do seu arquivo" in pdf
    assert _NAO_E_ESCALA not in pdf and _MANDE_EM_DXF in pdf
    _s, dwg = main._build_leu_sem_medir_email(*args, dwg_nao_abriu=True, cad_com_escala_provada=True)
    assert "O motivo é o arquivo DWG que não abriu" in dwg
    assert _NAO_E_ESCALA not in dwg and _NAO_PRECISA not in dwg
    _s, padrao = main._build_leu_sem_medir_email(*args)
    assert _COSTUMA_SER_ESCALA in padrao and _MANDE_EM_DXF in padrao
