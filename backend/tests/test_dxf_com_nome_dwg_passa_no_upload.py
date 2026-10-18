# -*- coding: utf-8 -*-
"""DXF salvo com extensão .dwg passa no upload e segue como DXF.

🩸 17/10/2026 — um engenheiro vindo do ChatGPT escolheu 4 arquivos ".dwg" e clicou em processar. O portão do upload
olhava só a extensão: .dwg tinha de começar com "AC". O arquivo começava com `999` — o comentário que vários
exportadores escrevem no topo de um DXF. Recusa 400, com a mensagem "Arquivo corrompido — exporte como PDF". Ele tentou
mais duas vezes e desistiu; nenhum projeto foi criado.

O resto do caminho já sabia lidar com isso: o process_job farejava o conteúdo e renomeava (`_normalizar_extensao_cad`,
desde 05/09, para o caso espelho — DWG salvo como .dxf). Faltava o upload deixar passar.

A rota roda de verdade aqui (o mesmo arranjo de test_recusa_de_upload_deixa_rastro): só rede, banco e thread saem do ar.
"""
import asyncio
import io
import os
import sys
import types

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
import main  # noqa: E402

UID = "uid-do-cliente-01"
EMAIL = "cliente-01@example.com"

# o começo de um DXF ASCII com o comentário de exportador (o caso real começava com b"999\n")
DXF_COM_COMENTARIO = (b"999\ndxfrw 0.6.3\n  0\nSECTION\n  2\nHEADER\n  9\n$ACADVER\n  1\nAC1021\n"
                      b"  0\nENDSEC\n  0\nEOF\n") + b"\n" * 200
DXF_SEM_COMENTARIO = b"  0\nSECTION\n  2\nHEADER\n  0\nENDSEC\n  0\nEOF\n" + b"\n" * 200
DWG_DE_VERDADE = b"AC1032\x00\x00\x00\x00\x00\x00" + b"\x00" * 300
NEM_UM_NEM_OUTRO = b"PK" + b"z" * 300


class _ArquivoFalso:
    def __init__(self, filename, conteudo):
        self.filename = filename
        self._buf = io.BytesIO(conteudo)
        self.size = len(conteudo)

    async def seek(self, n):
        self._buf.seek(n)

    async def read(self, n=-1):
        return self._buf.read(n)


class _Pedido:
    def __init__(self):
        self.headers = {}
        self.client = types.SimpleNamespace(host="203.0.113.7")


class _Banco:
    def __init__(self):
        self.linhas = []

    def __call__(self, table, data):
        self.linhas.append((table, dict(data)))
        return None

    def recusas(self):
        return [d for t, d in self.linhas if t == "error_log" and d.get("stage") == "upload:recusado"]

    def projetos(self):
        return [d for t, d in self.linhas if t == "projects"]


@pytest.fixture
def bancada(monkeypatch, tmp_path):
    b = _Banco()
    monkeypatch.setattr(main, "_supabase_insert", b)
    monkeypatch.setattr(main, "_get_user_from_request", lambda request, tolerante=False: {"id": UID, "email": EMAIL})
    monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: True)
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_envio_recente_igual", lambda assinatura: None)
    monkeypatch.setattr(main, "_registrar_envio", lambda assinatura, job_id: None)
    monkeypatch.setattr(main, "_process_job_throttled", lambda *a, **k: None)
    monkeypatch.setattr(main, "_notify_admin", lambda *a, **k: True)
    monkeypatch.setattr(main, "_projeto_ja_enviado", lambda *a, **k: None)
    b.tmp = tmp_path
    return b


def _sobe(files):
    async def _go():
        return await main.process_files(
            request=_Pedido(), background_tasks=None, files=files, sheet_types=[], sheet_ambientes=[],
            project_name="proj-de-teste", user_email=EMAIL, user_id=UID)
    return asyncio.run(_go())


def _tipos_gravados(bancada):
    tipos = [p.get("file_types") for p in bancada.projetos() if p.get("file_types")]
    assert tipos, "o projeto não foi gravado — o envio não chegou ao fim"
    return tipos[-1]


def test_o_caso_real_quatro_dxf_com_nome_dwg_passam(bancada):
    arquivos = [_ArquivoFalso("#178247958140%d.dwg" % i, DXF_COM_COMENTARIO) for i in range(4)]
    _sobe(arquivos)
    assert bancada.recusas() == [], "o upload recusou DXF com nome .dwg: %r" % bancada.recusas()
    tipos = _tipos_gravados(bancada)
    assert tipos.get("dxf") == 4 and tipos.get("dwg", 0) == 0, (
        "o projeto tem de contar o que os arquivos SÃO (4 DXF), não o que o nome diz: %r" % tipos)


def test_dxf_sem_o_comentario_tambem_passa(bancada):
    _sobe([_ArquivoFalso("planta.dwg", DXF_SEM_COMENTARIO)])
    assert bancada.recusas() == []
    assert _tipos_gravados(bancada).get("dxf") == 1


def test_o_dwg_de_verdade_continua_dwg(bancada):
    _sobe([_ArquivoFalso("planta.dwg", DWG_DE_VERDADE)])
    assert bancada.recusas() == []
    assert _tipos_gravados(bancada).get("dwg") == 1


def test_CONTROLE_o_que_nao_e_dwg_nem_dxf_continua_recusado(bancada):
    with pytest.raises(main.HTTPException) as ex:
        _sobe([_ArquivoFalso("planta.dwg", NEM_UM_NEM_OUTRO)])
    assert ex.value.status_code == 400
    assert [r.get("message", "").split("motivo=", 1)[-1].split(" ", 1)[0] for r in bancada.recusas()] == \
        ["dwg-sem-assinatura"]


def test_a_mensagem_da_recusa_nao_manda_pro_pdf_nem_chama_de_corrompido(bancada):
    """PDF é o formato que menos mede; e um arquivo que só não é DWG não está 'corrompido'."""
    with pytest.raises(main.HTTPException) as ex:
        _sobe([_ArquivoFalso("planta.dwg", NEM_UM_NEM_OUTRO)])
    texto = str(ex.value.detail).lower()
    assert "pdf" not in texto and "corrompido" not in texto, texto
    assert "dwg ou dxf" in texto, texto


def test_CONTROLE_a_regra_antiga_recusaria_o_caso_real():
    """O que o portão antigo julgava: só os 2 primeiros bytes. O caso real reprova nele."""
    assert DXF_COM_COMENTARIO[:2] != b"AC"
    assert main._formato_cad_pelo_conteudo.__name__  # o farejo que o portão novo usa existe
