# -*- coding: utf-8 -*-
"""Um PDF de 2,63 MB derrubou o servidor de TODOS os clientes.

🩸 03/09/2026, caso EDVALDO (job `7ddbccc1`), o maior lead B2B, avaliando o
produto no mesmo dia. Medido no Render (memory_usage, resolução 30 s):

    12:30:30 UTC ...... 94,6 MB
    12:31:00 .......... 350,7 MB
    12:31:30 ......... 1.366,7 MB
    12:32:00 ......... 3.107,8 MB   (72% do teto de 4 GiB — última amostra viva)
    12:33 e 12:34 .... instance_count = 0   ← o site ficou FORA por 2 minutos

Quem estivesse no site nesses dois minutos levou erro. Não foi só o job dele.

🔑 A CAUSA: o processo filho que mede a geometria do PDF rodava **sem teto de
memória**. O único freio era um cronômetro de 75 s — e cronômetro não limita
memória. Nessa rodada ele perdeu a corrida pro estouro por ~20 segundos; na
tentativa seguinte, ganhou por acaso (o filho morreu de timeout às 12:39:11 e a
memória caiu 2,25 GB de uma vez, SEM reinício de contêiner — que é a prova de
que os GB moravam no filho, não no servidor).

📏 A amplificação é o que assusta: **2,63 MB de arquivo viraram ~2,7 GB de RAM
(≈500×)**. Memória aqui não é proporcional a bytes, é proporcional a quantos
elementos vetoriais a prancha tem. Por isso o teto de 12 MB por arquivo que
existia não protege nada — este PDF tem 4,6× MENOS que ele.

🪤 TETO DE 2 GB, NÃO 1,5. A auditoria propôs 1,5 GB. Não medimos ainda o pico
das 109 medições que DÃO certo, e teto apertado mata trabalho legítimo. 2 GB já
teria impedido as duas quedas de hoje e deixa 2 GB de folga. Apertar depois,
com dado — nunca no chute.

🪤 `resource` é módulo só de Unix: em produção (Linux) o teto vale, no Windows o
try/except deixa passar. Sem isso, TODA medição de PDF morreria de ImportError
em desenvolvimento. Por isso o teste de comportamento abaixo só roda em Linux —
no CI, que é ubuntu.
"""
import os
import subprocess
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

from _corpo import fonte, sem_comentarios          # noqa: E402

_SRC = sem_comentarios(fonte("main.py"))

# o prefixo que o filho executa, reproduzido aqui pro teste de comportamento
_PREFIXO = ("try:\n    import resource; resource.setrlimit("
            "resource.RLIMIT_AS, (2_000_000_000, 2_000_000_000))\n"
            "except Exception:\n    pass\n")


# ── O comportamento, no sistema que importa ────────────────────────────────
@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="RLIMIT_AS só existe no Unix; produção é Linux")
def test_o_filho_MORRE_em_vez_de_derrubar_o_servidor():
    """🩸 O teste que vale. Alocar acima do teto tem que matar o FILHO."""
    r = subprocess.run(
        [sys.executable, "-c", _PREFIXO + "x = bytearray(3_000_000_000)"],
        capture_output=True, text=True, timeout=120)
    assert r.returncode != 0, (
        "o filho alocou 3 GB sem morrer — o teto não está valendo, e o próximo "
        "PDF denso derruba o servidor de todos os clientes de novo")
    assert "MemoryError" in (r.stderr or ""), r.stderr[-300:]


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="RLIMIT_AS só existe no Unix")
def test_CONTROLE_o_teto_NAO_atrapalha_medicao_normal():
    """🧪 Teto que mata trabalho legítimo é pior que teto nenhum. 50 MB é a
    ordem de grandeza de uma prancha comum e tem que passar."""
    r = subprocess.run(
        [sys.executable, "-c", _PREFIXO + "x = bytearray(50_000_000); print(len(x))"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-300:]
    assert "50000000" in r.stdout


def test_CONTROLE_o_prefixo_NAO_estoura_em_sistema_sem_resource():
    """🪤 No Windows `import resource` levanta ImportError. Se o try/except
    sumir, toda medição de PDF morre em desenvolvimento."""
    r = subprocess.run([sys.executable, "-c", _PREFIXO + "print('vivo')"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "vivo" in r.stdout, r.stderr[-200:]


# ── O código de produção ───────────────────────────────────────────────────
def test_a_chamada_de_medicao_LEVA_o_teto():
    assert "resource.RLIMIT_AS, (2_000_000_000, 2_000_000_000)" in _SRC, (
        "a medição do PDF voltou a rodar sem teto de memória — é o caminho "
        "que derrubou o site por 2 minutos em 03/09")
    i = _SRC.find("_cmd = [_sysv.executable")
    assert i > 0
    assert "RLIMIT_AS" in _SRC[i:i + 600], (
        "o teto saiu de dentro do comando que o filho executa")


def test_o_teto_e_TOLERANTE_a_plataforma():
    i = _SRC.find("_cmd = [_sysv.executable")
    trecho = _SRC[i:i + 600]
    assert "try:" in trecho and "except Exception" in trecho, (
        "o import de `resource` ficou sem proteção — quebra em Windows")


def test_o_ramo_que_AVISA_o_cliente_continua_de_pe():
    """🔑 O conserto não precisou de tratamento novo justamente porque este
    ramo já existia: filho com rc≠0 vira log + aviso ao cliente."""
    assert "if _pr.returncode != 0:" in _SRC
    assert '"pdfvec:filho-morreu"' in _SRC
    assert "_pdfvec_falhas.append(" in _SRC


def test_o_cronometro_NAO_foi_subido_junto():
    """🚨 A ordem importa e a auditoria foi explícita: subir o timeout ANTES
    do teto de memória PIORA — foram os 75 s que impediram a segunda queda,
    às 12:39. Só depois deste teto estar rodando em produção é que dá pra
    discutir tempo maior."""
    assert "timeout=75" in _SRC, (
        "o cronômetro da medição mudou no mesmo commit do teto de memória — "
        "as duas coisas juntas não dá pra atribuir efeito a nenhuma")


def test_CONTROLE_a_checagem_do_teto_sabe_REPROVAR():
    falso = '_cmd = [_sysv.executable, "-c", ("import sys, json; ...")]'
    assert "RLIMIT_AS" not in falso
