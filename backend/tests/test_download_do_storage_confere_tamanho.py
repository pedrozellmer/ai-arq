# -*- coding: utf-8 -*-
"""Arquivo baixado pela metade não pode virar "o desenho do cliente está ruim".

🩸 03/09/2026. Achado investigando o caso FÁBIO SHIRAISHI (job `75dab573`),
cujo ODA dizia "Unexpected end of file".

🪤 E EU ATRIBUÍ O CASO DELE A ISTO, ERRADO. Com a conferência ligada, o arquivo
dele baixa INTEIRO (nenhum `storage:download-truncado` no log) e o ODA do
servidor recusa igual — lá a diferença é entre o build Windows do ODA 27.1, que
converte em 27 s, e o Linux QT6 27.1 do container, que recusa. Duas teorias
minhas caíram nesse caso: "o servidor só tem libredwg" (falso, tem ODA) e "o
download truncou" (falso, veio inteiro).

🔑 Mas o buraco daqui é real e vale por si — era uma linha:

    resp = urllib.request.urlopen(req, timeout=30)
    return resp.read()

`read()` numa conexão que fecha no meio devolve o pedaço que chegou **sem
levantar exceção**. Ninguém comparava com `Content-Length`. O pedaço era gravado
no disco com o nome do arquivo do cliente, e daí em diante tudo que acontecesse
seria debitado do desenho dele, do conversor, ou do "não-determinismo da IA".

🪤 Isto roda em TODO filhote e em todo caminho que rebaixa o original. Falha
silenciosa não produz erro — produz uma leitura PIOR, que é muito mais difícil
de rastrear que uma que quebra.
"""
import io
import os

import main

_FONTE = io.open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()


class _Resp:
    """Uma resposta HTTP que entrega MENOS do que promete."""

    def __init__(self, corpo, content_length=None):
        self._corpo = corpo
        self.headers = {} if content_length is None else {
            "Content-Length": str(content_length)}

    def read(self):
        return self._corpo


class _Headers(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


def _resp(corpo, content_length):
    r = _Resp(corpo)
    r.headers = _Headers()
    if content_length is not None:
        r.headers["Content-Length"] = str(content_length)
    return r


def _com_respostas(monkeypatch, respostas):
    """Troca o urlopen por uma fila de respostas e conta as chamadas."""
    chamadas = {"n": 0}
    fila = list(respostas)

    def _fake(req, timeout=None):
        chamadas["n"] += 1
        if not fila:
            raise AssertionError("urlopen chamado mais vezes que o previsto")
        r = fila.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", _fake)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    return chamadas


def test_arquivo_truncado_NAO_e_devolvido_como_se_fosse_o_arquivo(monkeypatch):
    """🩸 O caso do Fábio: 30% do arquivo, sem erro nenhum."""
    inteiro = b"X" * 1000
    _com_respostas(monkeypatch, [_resp(inteiro[:300], 1000)] * 3)
    assert main._supabase_storage_download_prancha("job1", "planta.dwg") is None, (
        "um pedaço do arquivo voltou a ser devolvido como se fosse o arquivo — "
        "é assim que 'unexpected end of file' vira culpa do desenho do cliente")


def test_CONTROLE_arquivo_INTEIRO_passa(monkeypatch):
    """Sem isto o conserto poderia ser 'recusar sempre'."""
    inteiro = b"X" * 1000
    _com_respostas(monkeypatch, [_resp(inteiro, 1000)])
    assert main._supabase_storage_download_prancha("job1", "planta.dwg") == inteiro


def test_ele_TENTA_DE_NOVO_antes_de_desistir(monkeypatch):
    """Truncar é falha de rede, e falha de rede costuma passar na 2ª."""
    inteiro = b"X" * 1000
    chamadas = _com_respostas(monkeypatch, [
        _resp(inteiro[:120], 1000),      # truncado
        _resp(inteiro, 1000),            # inteiro
    ])
    assert main._supabase_storage_download_prancha("job1", "planta.dwg") == inteiro
    assert chamadas["n"] == 2, "não tentou de novo depois do truncado"


def test_excecao_de_rede_tambem_tem_nova_tentativa(monkeypatch):
    inteiro = b"X" * 500
    chamadas = _com_respostas(monkeypatch, [
        OSError("connection reset by peer"),
        _resp(inteiro, 500),
    ])
    assert main._supabase_storage_download_prancha("job1", "planta.dwg") == inteiro
    assert chamadas["n"] == 2


def test_sem_Content_Length_segue_mas_nao_finge_que_conferiu(monkeypatch):
    """Resposta em chunked não traz o tamanho.

    Recusar aí quebraria download legítimo; fingir que conferiu seria pior que
    não conferir. O certo é seguir e REGISTRAR — que é o oposto de calar.
    """
    corpo = b"Y" * 77
    registros = []
    _com_respostas(monkeypatch, [_resp(corpo, None)])
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, *a, **k: registros.append(stage))
    assert main._supabase_storage_download_prancha("job1", "planta.dwg") == corpo
    assert any("sem-tamanho" in r for r in registros), (
        "seguiu sem conferir e não registrou nada — é a falha calada de novo, "
        "com outro nome")


def test_a_desistencia_deixa_RASTRO_critico(monkeypatch):
    """Descartar o arquivo em silêncio seria trocar um defeito por outro."""
    registros = []
    _com_respostas(monkeypatch, [_resp(b"Z" * 10, 1000)] * 3)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, *a, **k: registros.append((stage, k)))
    assert main._supabase_storage_download_prancha("job1", "planta.dwg") is None
    assert any(s == "storage:download-truncado" for s, _ in registros), (
        "desistiu do arquivo sem registrar — ninguém ia descobrir por quê")


def test_o_timeout_nao_voltou_a_ser_curto_demais():
    """🪤 30 s é pouco pra 44 MB em rede ruim, e o corte vira truncamento.

    O arquivo do Fábio tem 44,5 MB. Com 30 s, qualquer soluço de rede corta a
    leitura no meio — que é exatamente o defeito que este arquivo guarda.
    """
    assert "timeout=120" in _FONTE, (
        "o timeout do download do Storage voltou a ser curto: em arquivo de "
        "dezenas de MB isso reintroduz o truncamento")
