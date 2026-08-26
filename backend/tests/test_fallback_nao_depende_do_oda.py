# -*- coding: utf-8 -*-
"""O plano B nao pode depender do plano A existir.

🚨 Achado em 25/08/2026, puxando um fio do Pedro: "a gente tem usado mais o
conversor secundario que o primario". Ele estava certo, e por muito. Dos 26 DWGs
de cliente que abriram nos 22 dias anteriores, **23 vieram do libredwg e 3 do
ODA** — o "principal" so e principal no papel.

Olhando o caminho, apareceu um defeito estrutural: `convert_dwg_to_dxf` fazia

    oda_exe = _find_oda_converter()
    if oda_exe is None:
        return None            # <- e o plano B nunca era chamado

Ou seja: o fallback so rodava se o ODA estivesse instalado E falhasse. Se o ODA
sumisse do container — e o risco de licenca esta aberto, US$ 7.500/ano pra rodar
como SaaS — o DWG morreria inteiro com o dwg2dxf instalado do lado, sem nunca
ser chamado. Um fallback que exige o principal vivo nao e fallback.

🩤 Este guarda RODA a funcao com as dependencias trocadas. Ler o fonte nao
serviria: eu ja errei 8 vezes num dia lendo texto (janela de N caracteres e
comentario lido como codigo). E ele testa as DUAS portas de saida — o ODA
ausente e o executavel que nao roda —, porque consertar uma so ja me enganou
antes.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import dwg_extractor as dx


@pytest.fixture
def dwg_falso(tmp_path):
    """Nao precisa ser DWG de verdade: a funcao so checa que o arquivo existe."""
    p = tmp_path / "prancha.dwg"
    p.write_bytes(b"AC1032" + bytes(64))
    return str(p)


def _plano_b_espiao(chamadas, devolve="/tmp/saida_libredwg.dxf"):
    def _fake(dwg_path, output_dir):
        chamadas.append({"dwg": dwg_path, "out": output_dir})
        return devolve
    return _fake


def test_sem_oda_instalado_ainda_tenta_o_libredwg(dwg_falso, monkeypatch):
    """ODA ausente: tem que cair no plano B, nao desistir."""
    chamadas = []
    monkeypatch.setattr(dx, "_find_oda_converter", lambda: None)
    monkeypatch.setattr(dx, "_try_libredwg_convert", _plano_b_espiao(chamadas))

    saida = dx.convert_dwg_to_dxf(dwg_falso)

    assert chamadas, (
        "REGRESSAO: o ODA nao esta instalado e o libredwg NAO foi chamado. "
        "O plano B voltou a depender do plano A existir."
    )
    assert saida == "/tmp/saida_libredwg.dxf", (
        "o libredwg converteu mas a funcao nao devolveu o DXF dele"
    )
    assert chamadas[0]["dwg"] == os.path.abspath(dwg_falso)
    assert chamadas[0]["out"], "o plano B precisa de um diretorio de saida real"
    assert os.path.isdir(chamadas[0]["out"]), (
        "o diretorio de saida passado pro libredwg nem existe"
    )


def test_executavel_do_oda_nao_roda_ainda_tenta_o_libredwg(dwg_falso, monkeypatch):
    """ODA achado no disco mas que nao executa: mesma causa, mesmo remedio.

    🩤 Este e o buraco irmao. Consertei so o primeiro na primeira passada e
    o caminho continuava morrendo por aqui.
    """
    chamadas = []
    monkeypatch.setattr(dx, "_find_oda_converter", lambda: "/opt/ODAFileConverter")
    # shutil e importado DENTRO da funcao, entao nao e atributo do modulo:
    # trocar no shutil de verdade. Sem isto, xvfb-run entra no comando.
    import shutil as _sh
    monkeypatch.setattr(_sh, "which", lambda _n: None)

    def _explode(*a, **k):
        raise FileNotFoundError("Executavel nao acessivel")
    monkeypatch.setattr(dx.subprocess, "run", _explode)
    monkeypatch.setattr(dx, "_try_libredwg_convert", _plano_b_espiao(chamadas))

    saida = dx.convert_dwg_to_dxf(dwg_falso)

    assert chamadas, (
        "REGRESSAO: o executavel do ODA nao rodou e o libredwg NAO foi chamado."
    )
    assert saida == "/tmp/saida_libredwg.dxf"


def test_quando_o_libredwg_tambem_falha_devolve_nada(dwg_falso, monkeypatch):
    """Controle negativo: os dois falharem TEM que continuar devolvendo None.

    Sem isto, o guarda passaria verde com um conserto que devolvesse qualquer
    coisa nao-nula — e main.py trataria lixo como DXF convertido.
    """
    monkeypatch.setattr(dx, "_find_oda_converter", lambda: None)
    monkeypatch.setattr(dx, "_try_libredwg_convert", lambda *a, **k: None)
    assert dx.convert_dwg_to_dxf(dwg_falso) is None


def test_controle_positivo_a_versao_ANTIGA_reprova(dwg_falso, monkeypatch):
    """Prova que este guarda REPROVA de verdade.

    Sem isto eu nao sei se os testes acima passariam de qualquer jeito. Aqui a
    versao antiga (`return None` sem tentar o plano B) e colocada no lugar e o
    guarda TEM que acusar.
    """
    chamadas = []

    def _versao_antiga(dwg_path):
        dwg_path = os.path.abspath(dwg_path)
        if not os.path.isfile(dwg_path):
            return None
        if dx._find_oda_converter() is None:
            return None          # <- o defeito, tal como era
        return "/tmp/nunca_chega_aqui.dxf"

    monkeypatch.setattr(dx, "_find_oda_converter", lambda: None)
    monkeypatch.setattr(dx, "_try_libredwg_convert", _plano_b_espiao(chamadas))
    monkeypatch.setattr(dx, "convert_dwg_to_dxf", _versao_antiga)

    saida = dx.convert_dwg_to_dxf(dwg_falso)

    # As MESMAS afirmacoes dos testes de cima, agora tendo que falhar.
    assert not chamadas, "controle positivo furado: a versao antiga chamou o plano B"
    assert saida is None, "controle positivo furado: a versao antiga devolveu DXF"
