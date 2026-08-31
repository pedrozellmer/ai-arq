# -*- coding: utf-8 -*-
"""Job retomado não pode perder a medição vetorial das pranchas.

🩸 31/08/2026 — ACHADO PELA AUDITORIA ADVERSARIAL DO MESMO DIA. Todo o bloco de
medição vetorial do PDF mora dentro do `else` de `if _ck_key in _ckpt_cache:`.
Num job retomado depois de crash (auto_resume), cada prancha com análise salva
pulava a medição — e com ela sumiam, calados:
  • o índice por prancha (então os passos 6 e 7 não preenchem nada);
  • o log `pdfvec:por-prancha`;
  • o aviso "⚠ N prancha(s) não foram medidas" — e a prancha que estourou o
    tempo na 1ª tentativa é JUSTAMENTE uma das que ficam salvas, porque o
    checkpoint é gravado sempre que a IA não deu erro, e ela não deu: a prancha
    só foi pra IA sem geometria.

🪤 A ironia que mais dói: o job pesado é o que trava e retoma — e era exatamente
ele que MENOS avisava. Quem mais precisa do aviso era quem nunca o recebia.

🔑 O conserto: a medição (ou a falha) viaja DENTRO do checkpoint e é restaurada
na retomada. Este teste prova o vai-e-volta pelo serializador real.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_MEDICAO = {"arquivo": "PLANTA.pdf", "pagina": 0, "rooms_m2": 80.5, "n_rooms": 10,
            "walls_m": 74.6, "n_walls": 42, "grupo_maior_m2": 80.5, "scale": 50,
            "scale_src": "cotas", "escala_validada": True, "cotas_batem": 29}


def test_a_medicao_sobrevive_ao_serializador_do_checkpoint(monkeypatch):
    """O checkpoint vai pro Storage como JSON. Se a medição não sobreviver a
    json.dumps/loads, a retomada volta sem ela e ninguém percebe."""
    enviado = {}

    class _Resp:
        def read(self): return b"{}"
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _fake_urlopen(req, timeout=None):
        try:
            enviado["body"] = req.data
        except Exception:
            pass
        return _Resp()
    monkeypatch.setattr(main.urllib.request, "urlopen", _fake_urlopen)

    result = {"items": [{"description": "Piso"}], "_pdfvec_medicao": dict(_MEDICAO)}
    main._ckpt_save("job-1", "PLANTA_p0", result)
    assert enviado.get("body"), "o checkpoint não chegou a ser enviado"
    volta = json.loads(enviado["body"].decode("utf-8"))
    assert "_pdfvec_medicao" in volta, (
        "a medição não entrou no checkpoint — a retomada vai perder tudo de novo")
    assert volta["_pdfvec_medicao"]["rooms_m2"] == 80.5
    assert volta["_pdfvec_medicao"]["escala_validada"] is True
    assert volta["_pdfvec_medicao"]["arquivo"] == "PLANTA.pdf"


def test_a_falha_da_prancha_tambem_viaja_no_checkpoint(monkeypatch):
    """🚨 O caso que mais importa: a prancha que ESTOUROU o tempo é uma das
    salvas. Sem a falha viajando junto, o aviso do cliente some na retomada —
    justo no job pesado."""
    enviado = {}

    class _Resp:
        def read(self): return b"{}"
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(main.urllib.request, "urlopen",
                        lambda req, timeout=None: (enviado.update(body=req.data), _Resp())[1])

    result = {"items": [], "_pdfvec_falhou": {"prancha": "PLANTA_p0",
                                              "arquivo": "PLANTA.pdf",
                                              "motivo": "tempo"}}
    main._ckpt_save("job-1", "PLANTA_p0", result)
    volta = json.loads(enviado["body"].decode("utf-8"))
    assert volta.get("_pdfvec_falhou", {}).get("motivo") == "tempo", (
        "a falha não viaja no checkpoint — na retomada o cliente perde o aviso")


def test_CONTROLE_checkpoint_sem_medicao_nao_quebra(monkeypatch):
    """Job antigo, gravado antes deste conserto, não tem a chave nova."""
    enviado = {}

    class _Resp:
        def read(self): return b"{}"
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(main.urllib.request, "urlopen",
                        lambda req, timeout=None: (enviado.update(body=req.data), _Resp())[1])
    main._ckpt_save("job-1", "PLANTA_p0", {"items": []})
    volta = json.loads(enviado["body"].decode("utf-8"))
    assert volta.get("_pdfvec_medicao") is None
    assert (volta or {}).get("_pdfvec_medicao") in (None, {}), "chave fantasma"


def test_CONTROLE_a_medicao_nao_atrapalha_os_itens():
    """A chave nova convive com o que o checkpoint já guardava."""
    result = {"items": [{"description": "Piso"}], "error": None,
              "_pdfvec_medicao": dict(_MEDICAO)}
    volta = json.loads(json.dumps(result, ensure_ascii=False, default=str))
    assert len(volta["items"]) == 1
    assert volta["items"][0]["description"] == "Piso"
