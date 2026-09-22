# -*- coding: utf-8 -*-
"""As três cópias de "a área informada chegaria numa linha?" respondem igual.

🩸 22/09/2026 — revisão adversária do conserto do job `ee801b82`. A pergunta
"se o cliente informar a área total, ela vira número em alguma linha?" mora
agora em TRÊS lugares:

  1. `_area_informada_alcancaria`, local dentro de `_apply_area_honesty` —
     decide a frase da linha zerada ("informe a área no upload");
  2. o aviso de projeto "Não encontramos a área total" — `_alcanca` (piso/
     forro/laje) e, desde o conserto, `if _alcanca and _pv_alc <= 0` (medição
     vetorial) decidem o convite "reenvie informando a área total";
  3. `engine_rules.area_informada_mudaria_a_planilha` — decide o convite do
     e-mail leu_sem_medir.

A docstring da 3ª dizia que o aviso aplicava as duas travas "no próprio
`_alcanca`", e a trava da medição ficou no `if` — fora do que o guarda de
09/09 lê pela AST. Três cópias sem guarda que as compare é exatamente o
padrão que a docstring de `_area_informada_alcancaria` descreve como causa de
conselho recusado: "enquanto eram duas cópias, a frase prometia uma coisa que
a régua recusava".

🔑 Este guarda EXECUTA as três — a do e-mail chamada direto, a do aviso pelo
trecho real do main.py (o recorte de `test_o_conselho_da_area_respeita_a_medicao`),
a local pela `_apply_area_honesty` real, lendo a frase que ela escreve na
linha — nos mesmos itens, com e sem medição vetorial, e exige a mesma
resposta. 🚫 Não junta as três numa só: a 1ª é local de propósito e o guarda
de 09/09 ancora a 2ª na AST.

🧪 Controle: a grade tem respostas SIM e NÃO (três réguas que sempre dizem
"não" também concordariam).
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
import main  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402
from test_o_conselho_da_area_respeita_a_medicao import _roda as _roda_aviso  # noqa: E402

_CONVITE_DO_AVISO = "reenvie informando a área total"
_CONVITE_DA_LINHA = "informe a área no upload"

_DESCRICOES = ("Piso cerâmico esmaltado", "Fôrma — laje de cobertura circular",
               "Forro de gesso acartonado", "Alvenaria — paredes internas",
               "Pintura acrílica de parede")
#: 0 = sem medição vetorial; 278,8 m² = o pavimento do caso da linha zerada
_PDFVEC = (0.0, 278.8)


def _item(desc):
    # 5.000 m² lidos pela IA num PDF: a honestidade de área zera a linha e
    # escreve a frase (o cenário que o comentário da linha zerada descreve)
    return BudgetItem(item_num="1", description=desc, unit="m²", quantity=5000,
                      observations="lido da prancha", confidence=Confidence.ESTIMADO,
                      origem="vision_pdf", ref_sheet="DE-X")


def _local(desc, pv):
    itens = [_item(desc)]
    main._apply_area_honesty(itens, pdfvec_m2=pv)
    obs = itens[0].observations or ""
    assert "Área NÃO medida" in obs, (
        "a linha não passou pela frase da área zerada — este guarda não estaria "
        "perguntando nada à régua local: %r" % obs)
    return _CONVITE_DA_LINHA in obs


def _aviso(desc, pv):
    return _CONVITE_DO_AVISO in _roda_aviso([_item(desc)], pdfvec_m2=pv)


def _email(desc, pv):
    return er.area_informada_mudaria_a_planilha([_item(desc)], pv)


def test_as_tres_reguas_respondem_igual_em_cada_linha():
    divergencias = []
    for desc in _DESCRICOES:
        for pv in _PDFVEC:
            r = (_local(desc, pv), _aviso(desc, pv), _email(desc, pv))
            if len(set(r)) != 1:
                divergencias.append((desc, pv, dict(zip(
                    ("linha zerada", "aviso de projeto", "e-mail"), r))))
    assert not divergencias, (
        "as réguas da área informada divergiram — um lugar convida e outro "
        "recusa: %s" % divergencias)


def test_CONTROLE_a_grade_tem_SIM_e_NAO():
    respostas = {_email(d, pv) for d in _DESCRICOES for pv in _PDFVEC}
    assert respostas == {True, False}, (
        "a grade só produz %r — três réguas caladas também concordam" % respostas)


def test_o_aviso_e_o_email_concordam_no_job_inteiro():
    """Aviso e e-mail perguntam pelo JOB (qualquer linha); a mistura de piso e
    parede do caso tem que dar a mesma resposta nos dois."""
    itens = [_item("Fôrma — laje de cobertura circular"),
             _item("Alvenaria — paredes internas")]
    for pv in _PDFVEC:
        assert (_CONVITE_DO_AVISO in _roda_aviso(itens, pdfvec_m2=pv)) == \
            er.area_informada_mudaria_a_planilha(itens, pv), pv
