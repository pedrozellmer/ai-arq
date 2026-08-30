# -*- coding: utf-8 -*-
"""O número de RAM que a gente olhava era do host, não do container.

🚨 26/08/2026, 10:19. O Render matou o serviço por estouro de memória no
segundo em que uma cliente subiu um arquivo — e eu passei a manhã inteira
olhando "RAM 86%" no /api/health sem entender o que tinha acontecido.

O 86% era do **host**. `psutil.virtual_memory()` dentro de um container enxerga
a máquina inteira: o health reportava **61,4 GB de total** enquanto o container
do plano Pro tem **4 GB**. O único número que a gente tinha sobre memória não
tinha nenhuma relação com o limite que dispara o OOM.

Cego com o instrumento na mão — o mesmo erro do "subiu ou não subiu" de ontem,
que só acabou quando o commit passou a aparecer no health.

Agora lê o cgroup, que é o limite de verdade:
    v2 -> /sys/fs/cgroup/memory.max        + memory.current
    v1 -> .../memory/memory.limit_in_bytes + memory.usage_in_bytes

🪤 Os dois números ficam, com nomes diferentes. Trocar em silêncio faria a série
histórica mentir sem ninguém perceber.

Estes guardas RODAM a função com o cgroup simulado — na máquina do Pedro
(Windows) esses arquivos não existem.
"""
import io
import os
import sys


_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import asyncio
import inspect
import main   # noqa: E402


def _chamar_rota(fn, *a, **kw):
    """Chama a rota sem assumir se ela e `def` ou `async def`.

    🪤 28/08/2026: `health` deixou de ser `async def` (rota async com corpo
    bloqueante congelava o servidor inteiro — foram 33 s mudos na virada das
    16h UTC). Estes testes quebraram com "a coroutine was expected", e a rota
    estava CERTA: quem estava errado era a forma de chamar.
    🔑 Por isso o ajudante aceita as duas: o teste passa a medir o RESULTADO da
    rota, nao o jeito como ela foi declarada. Se amanha ela voltar a ser async
    (porque ganhou um `await` de verdade), nada aqui precisa mudar.
    """
    r = fn(*a, **kw)
    return asyncio.run(r) if inspect.isawaitable(r) else r


class _FakeReq:
    """Request mínimo pro health: só precisa de .headers e .client."""
    def __init__(self, headers=None):
        self.headers = headers or {}
        self.client = None


def _req_admin(monkeypatch):
    """Faz o health enxergar um admin logado (sem tocar no Supabase)."""
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda *a, **k: {"id": "x", "email": main.ADMIN_EMAIL})
    return _FakeReq()


def _req_anon(monkeypatch):
    monkeypatch.setattr(main, "_get_user_from_request", lambda *a, **k: None)
    return _FakeReq()

_MB = 1024 * 1024


def _cgroup_falso(monkeypatch, arquivos):
    """Faz io.open devolver conteúdo só para os caminhos do cgroup."""
    real = io.open

    def _fake(caminho, *a, **k):
        nome = str(caminho)
        if nome in arquivos:
            return real(os.devnull, "r") if arquivos[nome] is None else _Texto(arquivos[nome])
        if nome.startswith("/sys/fs/cgroup"):
            raise FileNotFoundError(nome)
        return real(caminho, *a, **k)

    monkeypatch.setattr(io, "open", _fake)


class _Texto:
    def __init__(self, s):
        self._s = s

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._s


def test_le_o_limite_do_cgroup_v2(monkeypatch):
    _cgroup_falso(monkeypatch, {
        "/sys/fs/cgroup/memory.max": str(4 * 1024 * _MB),        # 4 GB
        "/sys/fs/cgroup/memory.current": str(3 * 1024 * _MB),    # 3 GB usados
    })
    m = main._memoria_do_container()
    assert m["dentro_de_container"] is True
    assert m["cgroup"] == "v2"
    assert m["limite_mb"] == 4096, m
    assert m["usado_mb"] == 3072, m
    assert m["usado_pct"] == 75.0, m
    assert m["livre_mb"] == 1024, m


def test_cai_pro_cgroup_v1_quando_o_v2_nao_existe(monkeypatch):
    _cgroup_falso(monkeypatch, {
        "/sys/fs/cgroup/memory/memory.limit_in_bytes": str(2 * 1024 * _MB),
        "/sys/fs/cgroup/memory/memory.usage_in_bytes": str(512 * _MB),
    })
    m = main._memoria_do_container()
    assert m["dentro_de_container"] is True and m["cgroup"] == "v1", m
    assert m["limite_mb"] == 2048 and m["usado_mb"] == 512, m


def test_sem_limite_NAO_finge_que_esta_em_container(monkeypatch):
    """'max' no cgroup significa sem teto — reportar isso como limite seria pior
    que não reportar nada."""
    _cgroup_falso(monkeypatch, {
        "/sys/fs/cgroup/memory.max": "max",
        "/sys/fs/cgroup/memory.current": str(100 * _MB),
    })
    assert main._memoria_do_container() == {"dentro_de_container": False}


def test_numero_gigante_do_v1_nao_vira_limite(monkeypatch):
    """🪤 cgroup v1 usa 9223372036854771712 pra 'sem limite'. Se isso passasse,
    o health diria '8 exabytes de RAM' e o uso apareceria como 0%."""
    _cgroup_falso(monkeypatch, {
        "/sys/fs/cgroup/memory/memory.limit_in_bytes": "9223372036854771712",
        "/sys/fs/cgroup/memory/memory.usage_in_bytes": str(100 * _MB),
    })
    assert main._memoria_do_container() == {"dentro_de_container": False}


def test_fora_de_container_diz_isso_em_vez_de_estourar():
    """Na máquina do Pedro (Windows) esses arquivos não existem."""
    m = main._memoria_do_container()
    assert m["dentro_de_container"] is False, m


def test_a_ROTA_health_devolve_o_campo(monkeypatch):
    """🪤 Guarda que só testa a função não vê o CALL SITE — e o call site é o
    que o hook e o Pedro olham."""
    r = _chamar_rota(main.health, _req_admin(monkeypatch))
    assert "memoria_container" in r, "a rota parou de reportar a memória do container"
    assert "system" in r, "o número do host sumiu — os dois têm que ficar"


def test_controle_positivo_o_host_MENTE_sobre_o_container(monkeypatch):
    """Prova que o campo novo não é redundante.

    Se o número do host fosse igual ao do container, todo este trabalho seria
    inútil. Aqui o container tem 4 GB e o host 61 GB — 15× de diferença, que é
    exatamente o tamanho do engano que me custou a manhã.
    """
    _cgroup_falso(monkeypatch, {
        "/sys/fs/cgroup/memory.max": str(4 * 1024 * _MB),
        "/sys/fs/cgroup/memory.current": str(3800 * _MB),   # quase estourando
    })
    cont = main._memoria_do_container()
    host_total_mb = 61 * 1024                               # o que o Render reportava
    assert cont["limite_mb"] < host_total_mb / 10, (
        "o container tem que ser MUITO menor que o host — se não for, o campo "
        "novo não acrescenta nada")
    assert cont["usado_pct"] > 90, (
        "container a 93%% deveria acender alarme; pelo host isso apareceria "
        "como uso irrelevante")
