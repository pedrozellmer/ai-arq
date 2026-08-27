# -*- coding: utf-8 -*-
"""O site mandou o mesmo arquivo duas vezes e derrubou o servidor.

🚨 26/08/2026, caso **AMANDA** — a cliente que se cadastrou às 08:19 e mandou o
primeiro projeto 4 minutos depois. Às 10:18 ela reenviou, e o site mandou o
MESMO arquivo DUAS VEZES, com 1 segundo de diferença:

    13:18:47  POST /api/process -> b249f3e4
    13:18:48  POST /api/process -> 58bc66c7    (mesmo DWG, mesmo nome de projeto)

Os dois entraram em processamento. A memória do Render (métrica lida direto no
conector, 26/08 à noite):

    10:17:00    287 MB
    10:18:00    938 MB
    10:18:30   1,65 GB
    10:19:00   3,81 GB   <- teto 4,29 GB
    10:19:08   INSTÂNCIA REINICIADA

Ela levou DOIS erros seguidos na cara e **nunca mais enviou nada**.

🪤 A trava de 3 s do `dashboard.html` (`_ultimoEnvioMs`) EXISTE, tem um listener
só, e mesmo assim os dois passaram: ela é **por aba**. Não cobre duas abas, nem
retry do XHR, nem chamada direta na API. Trava de tela nunca vai cobrir a
origem toda — a do servidor cobre.

🔑 **Não é rate-limit.** O `_rate_limit_ok` da mesma rota deixa 12 projetos em
10 minutos de propósito: um humano manda vários projetos DIFERENTES numa
sessão. Esta trava barra só o MESMO envio repetido em segundos, e devolve o job
que já existe — pro cliente parece que funcionou, que é o que ele queria (UM
projeto processando).

📌 A subida NÃO é o que consome RAM (desde 21/07 vai pra disco em pedaços,
~1 MB por arquivo). Quem consome é o PROCESSAMENTO — por isso impedir o job
duplicado resolve o estouro.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main as M  # noqa: E402


class _FakeUpload:
    """UploadFile o suficiente pra assinatura (nome + tamanho)."""

    def __init__(self, filename, size):
        self.filename = filename
        self.size = size


def _limpar():
    with M._ENVIOS_LOCK:
        M._ENVIOS_RECENTES.clear()


def _par(nome, tam):
    return (_FakeUpload(nome, tam), "", "")


def test_o_caso_da_AMANDA_o_segundo_envio_devolve_o_PRIMEIRO_job():
    """O teste que define o commit."""
    _limpar()
    pares = [_par("ARQ_HARMONIA_R02.dwg", 41_000_000)]
    a = M._assinatura_do_envio("u-amanda", "Harmonia - 9º Pavimentos", pares)

    assert M._envio_recente_igual(a) is None, "não havia envio anterior"
    M._registrar_envio(a, "b249f3e4")

    b = M._assinatura_do_envio("u-amanda", "Harmonia - 9º Pavimentos", pares)
    assert M._envio_recente_igual(b) == "b249f3e4", (
        "o segundo envio criaria um job novo — foi assim que a memória dobrou "
        "e a instância reiniciou")


def test_projeto_DIFERENTE_do_mesmo_cliente_PASSA():
    """🧪 Controle negativo. Se a trava pegasse aqui, ela quebraria o uso
    normal: um humano manda vários projetos diferentes na mesma sessão."""
    _limpar()
    a = M._assinatura_do_envio("u1", "Casa A", [_par("planta.dwg", 100)])
    M._registrar_envio(a, "job-A")
    b = M._assinatura_do_envio("u1", "Casa B", [_par("planta.dwg", 100)])
    assert M._envio_recente_igual(b) is None, (
        "projeto com outro NOME foi barrado — a trava está larga demais")


def test_arquivo_DIFERENTE_no_mesmo_projeto_PASSA():
    _limpar()
    a = M._assinatura_do_envio("u1", "Casa A", [_par("planta.dwg", 100)])
    M._registrar_envio(a, "job-A")
    b = M._assinatura_do_envio("u1", "Casa A", [_par("eletrica.dwg", 100)])
    assert M._envio_recente_igual(b) is None
    c = M._assinatura_do_envio("u1", "Casa A", [_par("planta.dwg", 999)])
    assert M._envio_recente_igual(c) is None, (
        "mesmo nome com TAMANHO outro é reenvio corrigido, tem que passar")


def test_OUTRO_cliente_com_arquivo_de_mesmo_nome_PASSA():
    """🚨 Isolamento entre clientes (regra dura nº2). "planta.dwg" é o nome mais
    comum do mundo — se dois clientes colidissem, um perderia o envio."""
    _limpar()
    a = M._assinatura_do_envio("u1", "Reforma", [_par("planta.dwg", 100)])
    M._registrar_envio(a, "job-do-u1")
    b = M._assinatura_do_envio("u2", "Reforma", [_par("planta.dwg", 100)])
    assert M._envio_recente_igual(b) is None, (
        "🚨 VAZAMENTO ENTRE CLIENTES: o u2 receberia o job do u1")


def test_a_ORDEM_dos_arquivos_nao_muda_a_assinatura():
    """🪤 O navegador não garante ordem entre dois envios. Sem ordenar, a mesma
    seleção geraria assinaturas diferentes e a trava não pegaria nada — eu só
    descobriria em produção, com outro cliente."""
    _limpar()
    p1 = [_par("a.dwg", 1), _par("b.dwg", 2), _par("c.dwg", 3)]
    p2 = [_par("c.dwg", 3), _par("a.dwg", 1), _par("b.dwg", 2)]
    assert (M._assinatura_do_envio("u1", "P", p1)
            == M._assinatura_do_envio("u1", "P", p2))


def test_depois_da_JANELA_o_reenvio_PASSA():
    """Reenviar o mesmo projeto meia hora depois é intenção real (corrigiu o
    arquivo). A janela é curta de propósito."""
    _limpar()
    a = M._assinatura_do_envio("u1", "Casa", [_par("p.dwg", 10)])
    with M._ENVIOS_LOCK:
        M._ENVIOS_RECENTES[a] = ("job-velho",
                                 time.time() - (M._ENVIO_JANELA_S + 5))
    assert M._envio_recente_igual(a) is None, (
        "envio antigo ainda barra — o cliente não conseguiria reenviar nunca")


def test_a_janela_e_curta():
    assert 30 <= M._ENVIO_JANELA_S <= 300, (
        "janela fora do razoável (%ss): curta demais não pega o clique duplo, "
        "longa demais impede reenvio legítimo" % M._ENVIO_JANELA_S)


def test_o_dicionario_NAO_cresce_pra_sempre():
    """🪤 Memória — e o bug que a gente está consertando é justamente de
    memória. Seria irônico vazar aqui."""
    _limpar()
    velho = time.time() - (M._ENVIO_JANELA_S + 60)
    with M._ENVIOS_LOCK:
        for i in range(500):
            M._ENVIOS_RECENTES["velho-%d" % i] = ("j%d" % i, velho)
    M._envio_recente_igual("qualquer-coisa")
    with M._ENVIOS_LOCK:
        assert len(M._ENVIOS_RECENTES) == 0, (
            "entradas vencidas ficaram: %d" % len(M._ENVIOS_RECENTES))


def test_a_rota_USA_a_trava_antes_de_criar_o_job():
    """🪤 Guarda de CALL SITE: a função pode estar certa e nunca ser chamada.
    E a ordem importa — depois do `job_id = uuid` não adianta nada."""
    import io
    _b = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    corpo = io.open(os.path.join(_b, "main.py"), encoding="utf-8").read()
    i_chk = corpo.find("_envio_recente_igual(_assinatura_envio)")
    i_job = corpo.find("job_id = str(uuid.uuid4())[:8]")
    assert i_chk > 0, "a trava não é chamada no /api/process"
    assert i_chk < i_job, (
        "a checagem vem DEPOIS de criar o job — o job duplicado já nasceu")
    assert "_registrar_envio(_assinatura_envio, job_id)" in corpo, (
        "o envio não é registrado — a trava nunca teria o que comparar")


def test_a_resposta_do_duplicado_tem_os_campos_QUE_O_SITE_LE():
    """🪤 O site lê `data.job_id` e ramifica em `data.aviso_aec` /
    `data.aviso_estrutural`. Resposta curta demais quebraria o cliente no
    caminho que a gente está tentando consertar."""
    import io
    _b = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    corpo = io.open(os.path.join(_b, "main.py"), encoding="utf-8").read()
    i = corpo.find('"duplicado": True')
    assert i > 0, "a rota não devolve o marcador de duplicado"
    janela = corpo[max(0, i - 500):i + 60]
    for campo in ('"job_id"', '"status"', '"file_types"', '"typology"',
                  '"project_type"', '"files_received"'):
        assert campo in janela, (
            "a resposta do duplicado não tem %s — formato diferente do normal"
            % campo)
