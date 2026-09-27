# -*- coding: utf-8 -*-
"""A bancada não chama o Supabase de verdade (auditoria SI, 27/09/2026).

🩸 Sem as variáveis de ambiente, o código cai no endereço de PRODUÇÃO com a chave pública. Nem este PC nem o CI
têm as variáveis, e os logs do Supabase mostraram a bancada daqui e a do CI mandando chamadas pra produção todo
dia — recusadas só porque a chave de servidor faltava. O `conftest.py` agora barra *.supabase.co no urllib.

🔑 Os testes usam um host `supabase.co` que NÃO é o nosso projeto: se o bloqueio sumir (sabotagem), a chamada vai
pra um endereço inexistente — o teste reprova sem tocar no nosso banco.
"""
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

FORA_DO_NOSSO_PROJETO = "https://teste-inexistente-aiarq.supabase.co/rest/v1/qualquer"


def _barrado(excinfo):
    return type(excinfo.value).__name__ == "ProducaoBloqueadaNosTestes"


def test_o_endereco_que_o_codigo_usa_esta_na_regra():
    """A regra tem que cobrir o endereço de verdade do main.py e do matcher do SINAPI, não um parecido."""
    import main
    import sinapi_matcher
    from conftest import host_bloqueado
    for url in (main.SUPABASE_URL, sinapi_matcher.SUPABASE_URL):
        assert host_bloqueado(urllib.parse.urlsplit(url).hostname), "a bancada alcançaria %s" % url


def test_urlopen_para_o_supabase_e_barrado_antes_da_rede():
    with pytest.raises(urllib.error.URLError) as e:
        urllib.request.urlopen(FORA_DO_NOSSO_PROJETO, timeout=5)
    assert _barrado(e), "a chamada saiu pra rede (%s: %s)" % (type(e.value).__name__, e.value)


def test_build_opener_tambem_e_barrado():
    req = urllib.request.Request(FORA_DO_NOSSO_PROJETO, data=b"{}", method="POST")
    with pytest.raises(urllib.error.URLError) as e:
        urllib.request.build_opener().open(req, timeout=5)
    assert _barrado(e), "o build_opener passou por fora do bloqueio (%s)" % type(e.value).__name__


def test_CONTROLE_endereco_que_nao_e_do_supabase_continua_abrindo():
    """Barrar tudo seria fácil e quebraria o que não é produção. `data:` abre sem rede nenhuma."""
    assert urllib.request.urlopen("data:text/plain,ok").read() == b"ok"


def test_CONTROLE_parecido_nao_e_barrado():
    from conftest import host_bloqueado
    assert host_bloqueado("kqjabzwgbfuivzlcfvvu.supabase.co")
    assert not host_bloqueado("supabase.com.evil.example")
    assert not host_bloqueado("api.ai.arq.br")


def test_o_bloqueio_esta_INSTALADO_no_urllib():
    assert urllib.request.OpenerDirector.open.__name__ == "_abrir_sem_producao", (
        "o conftest não instalou o bloqueio: a bancada volta a alcançar a produção")
