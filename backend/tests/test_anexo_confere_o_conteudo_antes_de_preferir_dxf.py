# -*- coding: utf-8 -*-
"""O anexo confere o CONTEÚDO do CAD antes de deixar "DXF vencer DWG do mesmo nome".

🩸 05/09/2026, cliente-39, 3º anexo do dia (job 8b7a2b71, 19:24). O /add-file tinha
a regra "DXF vence o DWG do mesmo nome", julgada pelo NOME: um .dxf que era DWG
renomeado "venceu" o .dwg de verdade e o jogou fora. Em seguida, no process_job,
a checagem pelo conteúdo (conserto da manhã do mesmo dia) viu que o "DXF" era
DWG com o irmão .dwg no disco e descartou a cópia. Sobrou ZERO arquivo: zero
item em 0,3 s, sem erro, sem e-mail, e um aviso na tela dizendo que o arquivo
dele "não rendeu nenhum item". Duas regras certas, na ordem errada — o conserto
fechou o processamento normal e deixou a porta do anexo com a mesma doença.

Regra: no anexo, o conteúdo vem PRIMEIRO (`_escolher_cads_do_anexo`); só então
"DXF vence DWG do mesmo nome" enxerga DXF de verdade.
🧪 Controles: DXF de verdade continua vencendo o DWG (forro MEP do Pedro, 15/07);
DWG disfarçado sozinho vira .dwg e o cliente é avisado; e a ORDEM ANTIGA, rodada
sobre o mesmo par, devolve ZERO — a prova de que o defeito era a ordem.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _corpo import corpo_de  # noqa: E402

DWG = b"AC1027" + b"\x00" * 58                      # DWG do AutoCAD 2013 (cabeçalho real)
DXF = b"0\r\nSECTION\r\n2\r\nHEADER\r\n0\r\nENDSEC\r\n0\r\nEOF\r\n"


def _arq(tmp_path, nome, conteudo):
    p = tmp_path / nome
    p.write_bytes(conteudo)
    return str(p)


def _nomes(paths):
    return sorted(os.path.basename(p) for p in paths)

# ══════════════════════════════════════════════════════════════════════════
#  🧪 BANCADA QUE EXECUTA A ROTA /add-file  (conversão 06/09)
# ══════════════════════════════════════════════════════════════════════════
import asyncio          # noqa: E402
import json as _json    # noqa: E402
import threading        # noqa: E402
import urllib.request   # noqa: E402


class _UploadDeMentira:
    """O mínimo que `_stream_upload_to_disk` usa: filename, seek, read(n)."""

    def __init__(self, filename, conteudo):
        self.filename = filename
        self._b = conteudo
        self._i = 0

    async def seek(self, n):
        self._i = n

    async def read(self, n=-1):
        if n is None or n < 0:
            n = len(self._b) - self._i
        pedaco = self._b[self._i:self._i + n]
        self._i += len(pedaco)
        return pedaco


class _RequestDeMentira:
    headers = {}
    client = None
    query_params = {}


class _Anexo(object):
    def __init__(self, resposta, vai_processar, avisos, alerta):
        self.resposta = resposta
        self.vai_processar = vai_processar
        self.avisos = avisos
        self.alerta = alerta


@pytest.fixture
def anexar(monkeypatch, tmp_path):
    """Roda `main.add_file_and_reprocess` de verdade e devolve o que ela decidiu.

    🪤 O Storage é um dict {nome: bytes}. A rota fala com o Supabase por
    `urllib.request.urlopen` DIRETO (projeto + list do Storage), então é ali
    que o patch tem que entrar.
    """
    def _rodar(envio):
        storage = {}
        processou = {"file_paths": None}
        avisos = []
        alerta = {"html": None}
        pronto = threading.Event()

        monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: None)
        monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: True)
        monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
        monkeypatch.setattr(main, "WORK_DIR", str(tmp_path))
        # 🔑 zero medidos: senão o 409 da trava anti-perda esconderia o defeito
        monkeypatch.setattr(main, "_job_medidos_count", lambda *a, **k: 0)
        monkeypatch.setattr(main, "_projeto_patch", lambda *a, **k: True)

        def _sobe(caminho, job_id, nome):
            storage[nome] = open(caminho, "rb").read()
            return True
        monkeypatch.setattr(main, "_supabase_storage_upload_prancha", _sobe)
        monkeypatch.setattr(main, "_supabase_storage_download_prancha",
                            lambda job_id, nome: storage.get(nome))

        def _update(tabela, col, val, patch):
            for w in (patch or {}).get("warnings") or []:
                avisos.append(w)
            return True
        monkeypatch.setattr(main, "_supabase_update", _update)
        monkeypatch.setattr(main, "_avisos_com",
                            lambda job_id, novos: list(novos or []))

        def _notify(assunto, html):
            alerta["html"] = html
            return True
        monkeypatch.setattr(main, "_notify_admin", _notify)

        def _processa(job_id, file_paths, work_dir, **kw):
            processou["file_paths"] = list(file_paths)
            pronto.set()
        monkeypatch.setattr(main, "_process_job_throttled", _processa)

        def _urlopen(req, timeout=None, **k):
            url = getattr(req, "full_url", str(req))

            class _R:
                def read(self_):
                    if "/storage/v1/object/list/" in url:
                        return _json.dumps(
                            [{"name": n} for n in sorted(storage)]).encode("utf-8")
                    return _json.dumps(
                        [{"typology": "office", "project_type": "arquitetura",
                          "status": "done", "user_total_area": 0,
                          "user_pe_direito": 0}]).encode("utf-8")

                def __enter__(self_):
                    return self_

                def __exit__(self_, *a):
                    return False
            return _R()
        monkeypatch.setattr(urllib.request, "urlopen", _urlopen)

        ups = [_UploadDeMentira(n, c) for n, c in envio]
        resp = asyncio.run(main.add_file_and_reprocess(
            "job-anexo", _RequestDeMentira(), files=ups))
        pronto.wait(timeout=5)
        nomes = [os.path.basename(p) for p in (processou["file_paths"] or [])]
        return _Anexo(resp, nomes, avisos, alerta["html"])
    return _rodar



@pytest.fixture
def silencio(monkeypatch):
    """`_normalizar_extensao_cad` registra no error_log; aqui vira lista."""
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))
    return logs


def test_PRECONDICAO_os_fixtures_sao_lidos_como_dwg_e_dxf(tmp_path):
    assert main._formato_cad_pelo_conteudo(_arq(tmp_path, "a.bin", DWG)) == "dwg"
    assert main._formato_cad_pelo_conteudo(_arq(tmp_path, "b.bin", DXF)) == "dxf"


# ── a regra ────────────────────────────────────────────────────────────────
def test_dwg_disfarcado_de_dxf_NAO_mata_o_dwg_de_verdade(tmp_path, silencio):
    falso = _arq(tmp_path, "x.dxf", DWG)
    real = _arq(tmp_path, "x.dwg", DWG)
    cads, _avisos = main._escolher_cads_do_anexo([falso, real], "job-t")
    assert cads, "o reprocesso rodaria com ZERO arquivo — o defeito do cliente-39"
    assert _nomes(cads) == ["x.dwg"], cads


def test_dxf_de_verdade_continua_vencendo_o_dwg_do_mesmo_nome(tmp_path, silencio):
    dxf = _arq(tmp_path, "y.dxf", DXF)
    dwg = _arq(tmp_path, "y.dwg", DWG)
    cads, _ = main._escolher_cads_do_anexo([dxf, dwg], "job-t")
    assert _nomes(cads) == ["y.dxf"], "o DXF re-exportado tem que seguir vencendo o DWG que falhava"


def test_dwg_disfarcado_sozinho_vira_dwg_e_o_cliente_e_avisado(tmp_path, silencio):
    falso = _arq(tmp_path, "z.dxf", DWG)
    cads, avisos = main._escolher_cads_do_anexo([falso], "job-t")
    assert _nomes(cads) == ["z.dwg"] and os.path.exists(cads[0])
    assert len(avisos) == 1 and ".dxf" in avisos[0] and "DWG" in avisos[0], avisos


def test_lista_vazia_nao_quebra(silencio):
    assert main._escolher_cads_do_anexo([], "job-t") == ([], [])


# ── controle positivo: a ORDEM ANTIGA reproduz o zero ─────────────────────
def test_CONTROLE_a_ordem_antiga_devolvia_ZERO_no_mesmo_par(tmp_path, silencio):
    falso = _arq(tmp_path, "x.dxf", DWG)
    real = _arq(tmp_path, "x.dwg", DWG)
    # 1) pelo NOME (a regra antiga do /add-file): o .dxf "vence" e o .dwg sai
    stems = {"x"}
    depois_do_nome = [p for p in (falso, real)
                      if not (p.endswith(".dwg") and os.path.splitext(os.path.basename(p))[0] in stems)]
    assert _nomes(depois_do_nome) == ["x.dxf"]
    # 2) pelo CONTEÚDO (process_job): a cópia é descartada porque x.dwg existe no disco
    sobrou, _, _ = main._normalizar_extensao_cad(depois_do_nome, "job-t")
    assert sobrou == [], "a ordem antiga não reproduz o zero — os testes de cima não provam nada"


# ── o /add-file usa o seletor; o alerta diz a verdade ─────────────────────
def test_o_add_file_usa_o_seletor_e_nao_a_regra_pelo_nome(anexar):
    """🩸 O 3º anexo do cliente-39 (job 8b7a2b71, 19:24): ele anexou o .dwg de
    verdade num projeto que já tinha um .dxf que era DWG renomeado. A regra
    pelo NOME jogou o .dwg fora; a checagem pelo CONTEÚDO, logo depois,
    descartou a cópia — e o reprocesso rodou com ZERO arquivo.
    """
    r = anexar([("x.dxf", DWG), ("x.dwg", DWG)])
    assert r.vai_processar, (
        "o reprocesso foi disparado com ZERO arquivo — é o defeito do "
        "cliente-39 de volta: zero item em 0,3 s, sem erro e sem e-mail")
    assert r.vai_processar == ["x.dwg"], (
        "o anexo escolheu %r; o certo é o .dwg de verdade — o .dxf do envio "
        "é o MESMO DWG renomeado" % r.vai_processar)
    assert r.resposta["files_count"] == 1, r.resposta


def test_o_DXF_de_verdade_continua_vencendo_pela_rota(anexar):
    """🧪 Controle: o caso forro MEP (15/07) — DWG AEC que não abre e o DXF
    re-exportado dele. Uma rota que sempre preferisse o .dwg mataria isso."""
    r = anexar([("y.dxf", DXF), ("y.dwg", DWG)])
    assert r.vai_processar == ["y.dxf"], r.vai_processar


def test_UM_arquivo_SO_pela_rota_confere_o_conteudo_E_avisa_o_cliente(anexar):
    """🪤 06/09/2026 — O CASO MAIS COMUM DO ANEXO NUNCA ATRAVESSAVA A ROTA.

    Os dois testes de rota acima mandam sempre DOIS arquivos; o caso solitário
    (`z.dxf` que é DWG, sem irmão) só era exercitado chamando
    `_escolher_cads_do_anexo` DIRETO. Com isso dava pra pular a checagem de
    conteúdo quando há um CAD só e ficar verde: o .dxf mentiroso iria pro ezdxf
    com a extensão errada (zero item, sem erro) e o cliente não seria avisado.

    E o guarda cego que este arquivo substituiu cobrava `_avisos_com(job_id,
    _avisos_ext)` no corpo da rota; nenhum dos testes novos olhava `r.avisos`,
    então o bloco que leva o aviso à tela podia ser neutralizado em silêncio.
    Aqui a rota RODA e as duas coisas são afirmadas.
    """
    r = anexar([("z.dxf", DWG)])
    assert r.vai_processar == ["z.dwg"], (
        "o anexo mandou %r pro motor; o conteúdo é DWG e, com a extensão .dxf, "
        "o ezdxf não abre — zero item em segundos, sem erro na tela"
        % r.vai_processar)
    assert r.resposta["files_count"] == 1, r.resposta
    assert len(r.avisos) == 1, (
        "o cliente recebeu %d aviso(s) de extensão em vez de 1 — sem esse "
        "recado ele repete o mesmo export errado na próxima: %r"
        % (len(r.avisos), r.avisos))
    aviso = r.avisos[0]
    assert "z.dxf" in aviso, "o aviso não nomeia o arquivo que ele mandou: %r" % aviso
    assert ".dxf" in aviso and "DWG" in aviso, (
        "o aviso não diz o que veio nem o que a gente entendeu: %r" % aviso)

def test_o_alerta_diz_o_que_a_pessoa_anexou_E_o_que_vai_rodar():
    c = corpo_de("add_file_and_reprocess")
    assert "_enviados.append(safe_local)" in c
    assert "for n in _enviados[:4]" in c, "o alerta voltou a listar file_paths como 'anexados agora'"
    assert "Arquivos anexados agora:</b> {_novos}" in c
    assert "Vai processar:</b> {_vai}" in c
