# -*- coding: utf-8 -*-
"""A promessa dos 90 dias vale para arquivo com ESPAÇO no nome.

🩸 07/09/2026 — MEDIDO NO STORAGE, e a assinatura é perfeita:

    1.282 arquivos no total
    32 passaram dos 90 dias
    32 desses têm ESPAÇO no nome
     0 sem espaço

Quem não tem espaço é apagado direitinho — sobra zero. Quem tem, **nunca** é
apagado. São 66 MB de arquivo de cliente que a política de privacidade promete
apagar em 90 dias e que estão lá há mais de três meses. Achado nº59/73 da
auditoria de 06/09, CRÍTICO.

A CAUSA: `_supabase_storage_delete` punha o caminho CRU na URL. Espaço não é
caractere válido em URL — a requisição saía malformada e o Storage recusava.

🪤 E O SILÊNCIO ERA DUPLO: o `except Exception: return False` engolia o erro
sem rastro, e o chamador contava `files_ok` como se tivesse apagado. O painel
dizia "arquivos removidos" enquanto eles continuavam lá.

🚫 NÃO É DÍVIDA ANTIGA. O sanitizador de nomes PERMITE espaço de propósito
(`c in " ._-()"`, main.py:2239) pra preservar o nome que o cliente reconhece —
e essa decisão está certa. Medido: **341 dos 1.282 arquivos têm espaço, 183
entraram nos últimos 30 dias, 70 nos últimos 7, o mais recente hoje.** Os 32
vencidos são só a ponta que já cruzou os 90 dias; os outros 309 vão cruzar.

🔑 Por isso o conserto é CODIFICAR A URL, não mutilar o nome do arquivo.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

#: Nomes reais do storage, na forma em que estão lá.
_COM_ESPACO = "job123/UFOP-CENTRO CONVERGENCIA-REVITALIZACAO PE-HID03.dwg"
_SEM_ESPACO = "job123/planta_terreo.dxf"
_COM_PARENTESES = "job123/Planta 1 - Galpao (rev 2).pdf"


@pytest.fixture
def storage(monkeypatch):
    """Storage de mentira: guarda a URL que o DELETE tentou."""
    import urllib.error
    import urllib.request

    chamadas = []

    def _urlopen(req, timeout=None):
        url = getattr(req, "full_url", str(req))
        chamadas.append(url)
        # 🔑 O Storage recusa URL com espaço cru — é isso que acontecia em
        # produção. Reproduzir a recusa é o que torna este guarda honesto.
        if " " in url:
            raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)
        return type("R", (), {"read": lambda s: b"", "__enter__": lambda s: s,
                              "__exit__": lambda s, *a: False})()

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    return chamadas


# ═══════════════════════════════════════════════════════════════════════════
#  O apagar funciona nos dois casos
# ═══════════════════════════════════════════════════════════════════════════

def test_apaga_arquivo_com_ESPACO_no_nome(storage):
    """🚨 O invariante. Eram 32 arquivos, 66 MB, todos com espaço."""
    assert main._supabase_storage_delete("aiarq-pranchas", _COM_ESPACO) is True, (
        "o arquivo com espaço no nome NÃO foi apagado — é a promessa dos 90 "
        "dias da política de privacidade descumprida")
    assert storage, "nem chegou a chamar o storage"
    assert " " not in storage[-1], (
        "a URL saiu com espaço CRU: %r" % storage[-1])
    assert "%20" in storage[-1], (
        "o espaço não foi codificado — a requisição vai malformada")


def test_apaga_nome_com_PARENTESES_e_hifen(storage):
    """O sanitizador permite ` ._-()` de propósito. Todos precisam funcionar."""
    assert main._supabase_storage_delete("aiarq-pranchas", _COM_PARENTESES) is True
    assert " " not in storage[-1]


def test_CONTROLE_o_arquivo_SEM_espaco_continua_apagando(storage):
    """O outro lado: o conserto não pode quebrar o que já funcionava — eram
    esses que sumiam certo (zero sobrando no storage)."""
    assert main._supabase_storage_delete("aiarq-pranchas", _SEM_ESPACO) is True
    assert "job123/planta_terreo.dxf" in storage[-1], (
        "o caminho sem espaço foi alterado à toa: %r" % storage[-1])


def test_a_BARRA_de_pasta_NAO_pode_virar_por_cento_2F(storage):
    """🪤 `quote(safe="/")`. Se a barra fosse codificada, o job_id e o nome do
    arquivo virariam UM nome só, e o delete erraria o alvo em 100% dos casos —
    trocando um defeito parcial por um total."""
    main._supabase_storage_delete("aiarq-pranchas", _COM_ESPACO)
    assert "%2F" not in storage[-1].upper(), (
        "a barra virou %%2F: o caminho deixou de ser pasta/arquivo — %r"
        % storage[-1])
    assert "/job123/" in storage[-1]


# ═══════════════════════════════════════════════════════════════════════════
#  A falha não pode ser calada
# ═══════════════════════════════════════════════════════════════════════════

def test_falha_de_verdade_DEIXA_RASTRO(monkeypatch):
    """🪤 O `except Exception: return False` engolia o erro, e o chamador
    contava como apagado. O painel dizia 'arquivos removidos' e eles estavam
    lá. Promessa de privacidade descumprida em silêncio é o pior caso."""
    import urllib.request

    logs = []
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("rede fora")))
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job=None, **k: logs.append((stage, msg, k.get("severity"))))
    assert main._supabase_storage_delete("aiarq-pranchas", _SEM_ESPACO) is False
    assert logs, "a falha sumiu sem rastro nenhum"
    stage, msg, sev = logs[0]
    assert "storage" in stage and sev == "error", (stage, sev)
    assert "CONTINUA no storage" in msg, (
        "o log não diz o que importa: que o arquivo ficou lá")


def test_CONTROLE_o_404_continua_sendo_SUCESSO(monkeypatch):
    """Arquivo que já não existe é objetivo cumprido, não falha. Sem isto o
    cleanup viraria uma parede de erro falso a cada rodada."""
    import urllib.error
    import urllib.request

    logs = []
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            urllib.error.HTTPError("u", 404, "Not Found", {}, None)))
    monkeypatch.setattr(main, "_log_error",
                        lambda *a, **k: logs.append(a))
    assert main._supabase_storage_delete("aiarq-pranchas", _SEM_ESPACO) is True
    assert not logs, "404 virou log de erro — vira ruído a cada rodada"


# ═══════════════════════════════════════════════════════════════════════════
#  🧪 O controle que reproduz o defeito
# ═══════════════════════════════════════════════════════════════════════════

def test_CONTROLE_a_versao_ANTIGA_falharia_com_espaco(storage):
    """Prova que o cenário do teste reproduz o defeito real: montar a URL SEM
    codificar, como estava em produção, é recusado pelo storage de mentira do
    mesmo jeito que era pelo de verdade."""
    import urllib.error
    import urllib.request

    url_crua = "https://x/storage/v1/object/aiarq-pranchas/%s" % _COM_ESPACO
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(urllib.request.Request(url_crua, method="DELETE"))
