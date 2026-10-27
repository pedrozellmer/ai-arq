# -*- coding: utf-8 -*-
"""O envio que cai antes do primeiro byte diz o que costuma resolver.

🩸 27/10/2026 — cliente novo apertou "Processar" e o envio morreu em 1 s: o
servidor viu só o OPTIONS do `/api/process`, nenhum byte do arquivo chegou, e a
tela dizia "Falha de rede — confira a conexão". Erro logo no começo, sem nada
enviado, é o jeito de arquivo que o navegador não lê (aberto no AutoCAD, pasta
de nuvem não baixada, pasta de rede) — ou queda de conexão naquele instante.
📏 90 d: 4 pessoas com `upload_erro` de rede; só 1 enviou depois.

Roda o `startProcessing` REAL no motor JS (a encenação do teste do anexo
recusado) e a receita REAL de `aiarq-utils.js`.
"""
import json
import os
import sys
import time

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

from _jsbancada import motor, rodar  # noqa: E402
import test_o_anexo_recusado_nao_vira_projeto_sozinho as _anexo  # noqa: E402

_QUEDA = "if (r.rede) { x.onerror(); return; }"
_MSG_ANTES = "O envio caiu antes de o arquivo começar a subir."


def _preludio():
    p = _anexo._PRELUDIO
    assert p.count(_QUEDA) == 1, "a encenação do XHR mudou: ajuste a queda"
    # `meio`: a queda vem DEPOIS de metade do arquivo ter subido
    return p.replace(_QUEDA, "if (r.rede) { if (r.meio && x.upload.onprogress) "
                             "x.upload.onprogress({lengthComputable: true, loaded: 500, total: 1000}); "
                             "x.onerror(); return; }")


def _envio(resposta):
    _site, fonte = _anexo._fonte_das_funcoes()
    js = motor(_preludio())
    js.evaljs(fonte + "\n;1;")
    js.evaljs("_soPdfNoEnvio = function () { return false; };"
              "var selectedFiles = [{ name: 'planta.dwg', size: 2356211 }]; __candidatos = [];"
              "accessToken = 'jwt'; 1;")
    js.evaljs("sbClient = { auth: { getSession: function () { return Promise.resolve({ data: "
              "{ session: { access_token: 'jwt', expires_at: %d } } }); } } }; 1;"
              % (int(time.time()) + 3000))
    js.evaljs("__respProcess = %s; 1;" % json.dumps(resposta))
    rodar(js, "startProcessing()")
    return json.loads(js.evaljs("JSON.stringify({erro: errorMessage.textContent, ev: __ev})"))


def _erros(tela):
    return [m for nome, m in tela["ev"] if nome == "upload_erro"]


def test_o_caso_nada_saiu_e_a_tela_nao_culpa_so_a_conexao():
    tela = _envio({"rede": True})
    assert _MSG_ANTES in tela["erro"], tela["erro"]
    ev = _erros(tela)
    assert len(ev) == 1 and ev[0]["type"] == "rede", ev
    # o registro agora mede: quanto saiu, de quanto, em quanto tempo
    assert ev[0]["bytes"] == 0 and ev[0]["total"] == 2356211 and "ms" in ev[0], ev


def test_CONTROLE_caiu_no_meio_segue_a_mensagem_de_conexao():
    tela = _envio({"rede": True, "meio": True})
    assert "Falha de rede no envio" in tela["erro"], tela["erro"]
    assert _MSG_ANTES not in tela["erro"]
    assert _erros(tela)[0]["bytes"] == 500, _erros(tela)


# ── o servidor GRAVA a medida (o /api/track descarta chave que não conhece) ────
def test_o_track_grava_bytes_total_e_ms(monkeypatch):
    import test_track_meta_allowlist as _trk
    meta = _trk.meta_gravado({"type": "rede", "bytes": 0, "total": 450_000_000, "ms": 900_000},
                             monkeypatch, event="upload_erro")
    assert meta.get("bytes") == 0 and meta.get("total") == 450_000_000 and meta.get("ms") == 900_000, meta


def test_CONTROLE_o_track_recusa_numero_absurdo_ou_bool(monkeypatch):
    import test_track_meta_allowlist as _trk
    meta = _trk.meta_gravado({"type": "rede", "bytes": True, "total": -5, "ms": 10 ** 12},
                             monkeypatch, event="upload_erro")
    assert "bytes" not in meta and "total" not in meta and "ms" not in meta, meta


# ── a receita (o que a tela do painel mostra embaixo da mensagem) ──────────────
@pytest.fixture(scope="module")
def pagina():
    from _bancada_js import Pagina
    return Pagina(("aiarq-utils.js",))


def test_a_receita_mostra_os_passos_sem_afirmar_a_causa(pagina):
    txt = pagina.eval("window.aiArqErroComReceita(%s)" % json.dumps(_MSG_ANTES))
    for k in ("AutoCAD", "OneDrive", "pasta de rede", "conexão"):
        assert k in txt, (k, txt)
    assert "<b>" not in txt, "o painel mostra texto puro"


def test_CONTROLE_a_queda_no_meio_nao_ganha_a_receita(pagina):
    msg = "Falha de rede no envio — confira a conexão e tente de novo."
    assert pagina.eval("window.aiArqErroComReceita(%s)" % json.dumps(msg)) == msg
