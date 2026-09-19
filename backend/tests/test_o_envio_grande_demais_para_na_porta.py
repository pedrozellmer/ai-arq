# -*- coding: utf-8 -*-
"""O envio absurdo para antes de gastar IA — e TODO envio real continua entrando.

🚨 19/09/2026. Um cliente de primeira viagem subiu o PACOTE DE LICITAÇÃO inteiro:
27 PDFs, nenhum CAD — edital assinado de 31 páginas, termo de referência,
memorial descritivo, duas memórias de cálculo, cronograma, BDI, matriz de riscos
e as pranchas no meio. 131 páginas, 93 minutos, US$ 6,96 de IA.

🩸 E ELE NÃO FRACASSOU — foi isso que derrubou a primeira versão deste guarda.
A régua ia nascer em 80 páginas para barrar exatamente esse envio. Ele terminou
com **500 itens**, e **305 deles (61%) saíram dos documentos que a régua ia
recusar**: termo de referência e memória de cálculo trazem quadros de
quantitativos, e a IA leu. Um teto em 80 teria trocado 500 linhas por uma tela
de erro, no primeiro envio de um cliente novo.

🪤 TRÊS ARMADILHAS DE MEDIÇÃO, uma atrás da outra:

1. "O maior envio que já deu certo tem 40 páginas" era TAUTOLOGIA. O log de
   páginas nasce de `page_units`, montado com `range(min(_npg, 40))` — nenhum
   job pode registrar mais de 40 páginas por arquivo, porque 40 é a régua da
   própria casa. As duas fontes que pareciam independentes nasciam as duas dali.
2. Corrigido o viés, o maior envio real de cliente virou 47 e o teto foi pra 80.
   Aí o caso de hoje terminou, com 131 páginas e 500 itens, e mostrou que o
   critério estava errado: em 189 jobs medidos, NENHUM envio grande fracassou
   por ser grande. Envio grande custa tempo e dinheiro, não entrega.
3. A régua contava as páginas do ARQUIVO, e o motor lê no máximo 40 de cada um.
   Ela recusaria por 190 páginas um envio de que o motor leria 40 — e caderno
   único é justamente o formato que mais entrega aqui. Agora ela conta o que
   vai ser LIDO.

🔑 Por isso o teto é PROTEÇÃO DE ÚLTIMA INSTÂNCIA (200 páginas de leitura) e não
curadoria. Quem cuida do tempo é o aviso na tela, que informa e não impede. Os
controles positivos abaixo são os envios reais da casa: se alguém apertar o teto
de volta, eles reprovam.

🪤 O guarda EXECUTA `_process_job_throttled`, a porta única dos seis disparos.
"""
import io
import os
import re
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
import main  # noqa: E402

TETO = 200         # default de `AIARQ_TETO_PAGINAS`
POR_PDF = 40       # `PAGINAS_LIDAS_POR_PDF`: o que o motor lê de CADA PDF
JOB = "job12345"   # 🔒 regra dura nº6: rótulo, nunca pessoa


# ══════════════════════════════════════════════════════════════════════════
#  PDF DE VERDADE, com o número de páginas que a gente pedir
# ══════════════════════════════════════════════════════════════════════════
# 🪤 Um `b"%PDF-1.4 blá"` faria `pdf_page_count` devolver 1 em TODO arquivo, e o
# guarda passaria a medir o fallback de erro em vez da contagem real. Estes PDFs
# abrem no pypdfium2 — o mesmo motor que a produção usa.
def _pdf_com_paginas(n: int) -> bytes:
    n = max(1, int(n))
    objetos = [b"<< /Type /Catalog /Pages 2 0 R >>",
               ("<< /Type /Pages /Kids [%s] /Count %d >>"
                % (" ".join("%d 0 R" % (3 + i) for i in range(n)), n)).encode()]
    objetos += [b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>"] * n

    saida = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, corpo in enumerate(objetos, start=1):
        offsets.append(len(saida))
        saida += ("%d 0 obj\n" % i).encode() + corpo + b"\nendobj\n"
    inicio = len(saida)
    saida += ("xref\n0 %d\n" % (len(objetos) + 1)).encode() + b"0000000000 65535 f \n"
    for off in offsets:
        saida += ("%010d 00000 n \n" % off).encode()
    saida += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
              % (len(objetos) + 1, inicio)).encode()
    return bytes(saida)


def _escreve(tmp_path, nome, paginas):
    p = tmp_path / nome
    p.write_bytes(_pdf_com_paginas(paginas))
    return str(p)


def _cad(tmp_path, nome):
    p = tmp_path / nome
    p.write_bytes(b"AC1032" + b"z" * 400)
    return str(p)


def test_CONTROLE_o_gerador_faz_pdf_que_a_producao_consegue_contar(tmp_path):
    """🧪 Sem isto, todo teste abaixo poderia estar medindo o fallback de erro
    (que devolve 1) — e um teto quebrado passaria despercebido."""
    from processor import pdf_page_count
    for n in (1, 2, 31, 47, 131):
        lido = pdf_page_count(_escreve(tmp_path, "com_%d.pdf" % n, n))
        assert lido == n, (
            "o PDF de teste com %d páginas foi lido como %d — o gerador quebrou "
            "e os guardas deste arquivo pararam de medir a contagem real"
            % (n, lido))


# ══════════════════════════════════════════════════════════════════════════
#  A BANCADA QUE EXECUTA — a porta única de verdade, o resto de mentira
# ══════════════════════════════════════════════════════════════════════════
class _Espiao:
    """Guarda o que o código faria: rodou o motor? gravou o quê? avisou quem?"""

    def __init__(self):
        self.rodou_motor = []
        self.updates = []
        self.logs = []
        self.emails = []
        self.ordem = []          # sequência de eventos, pra provar quem vem antes
        self.update_devolve = True
        self.base_tem_itens = False


@pytest.fixture
def bancada(monkeypatch):
    e = _Espiao()

    # 🪤 TODO dublê leva **k. Em 16 e 18/09 dublê com assinatura exata desarmou
    # guarda em silêncio — em 18/09 derrubou 12 de uma vez.
    def _motor(*a, **k):
        e.rodou_motor.append(a[0] if a else k.get("job_id"))
        e.ordem.append("motor")

    def _update(table, campo, valor, data, *a, **k):
        e.updates.append((table, campo, valor, dict(data)))
        return e.update_devolve

    def _log(stage, message, job_id=None, severity="error", *a, **k):
        e.logs.append({"stage": stage, "message": message, "job_id": job_id,
                       "severity": severity})

    def _email(job_id, reprocessavel=True, culpa_nossa=False, *a, **k):
        e.emails.append({"job_id": job_id, "reprocessavel": reprocessavel,
                         "culpa_nossa": culpa_nossa})
        return True

    def _esperar(*a, **k):
        e.ordem.append("fila")

    def _tem_itens(job_id, *a, **k):
        return e.base_tem_itens

    monkeypatch.setattr(main, "process_job", _motor)
    monkeypatch.setattr(main, "_supabase_update", _update)
    monkeypatch.setattr(main, "_log_error", _log)
    monkeypatch.setattr(main, "_email_falha_cliente", _email)
    monkeypatch.setattr(main, "_esperar_vaga", _esperar)
    monkeypatch.setattr(main, "_liberar_vaga", lambda *a, **k: None)
    monkeypatch.setattr(main, "_complement_base_has_items", _tem_itens)
    return e


def _dispara(paths, work_dir="/tmp/qualquer"):
    """Chama a PORTA ÚNICA com o mesmo contrato posicional dos seis disparos."""
    main._process_job_throttled(JOB, list(paths), work_dir)


def _absurdo(tmp_path, n_arquivos=6, paginas=45):
    """Um envio acima do teto de LEITURA (cada PDF vale no máximo 40)."""
    return [_escreve(tmp_path, "caderno-%02d.pdf" % i, paginas)
            for i in range(n_arquivos)]


def _erro_gravado(espiao):
    for _t, _c, _v, data in espiao.updates:
        if _t == "projects" and data.get("status") == "error":
            return data
    return None


def _logs_de(espiao, stage):
    return [x for x in espiao.logs if x["stage"] == stage]


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — TODO envio real da casa continua entrando
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_pacote_de_licitacao_de_hoje_continua_entrando(bancada, tmp_path):
    """19/09/2026, o caso que originou tudo: 131 páginas, 500 itens entregues.

    🩸 A primeira versão desta régua barrava exatamente este envio. 305 dos 500
    itens saíram dos documentos que ela ia recusar. Se este teste reprovar,
    alguém voltou a tratar envio grande como envio ruim.
    """
    envio = [_escreve(tmp_path, "edital.pdf", 31),
             _escreve(tmp_path, "termo-referencia.pdf", 27),
             _escreve(tmp_path, "memorial.pdf", 17),
             _escreve(tmp_path, "memoria-calculo-a.pdf", 9),
             _escreve(tmp_path, "memoria-calculo-b.pdf", 8),
             _escreve(tmp_path, "matriz-riscos.pdf", 8),
             _escreve(tmp_path, "mapa-riscos.pdf", 7),
             _escreve(tmp_path, "bdi.pdf", 6)]
    envio += [_escreve(tmp_path, "prancha-%02d.pdf" % i, 1) for i in range(18)]
    _dispara(envio)                                       # 131 páginas
    assert bancada.rodou_motor == [JOB], (
        "o envio de 131 páginas que ENTREGOU 500 itens foi barrado — a régua "
        "voltou a confundir envio grande com envio ruim")
    assert not _erro_gravado(bancada)


def test_CONTROLE_o_maior_projeto_da_casa_continua_entrando(bancada, tmp_path):
    """08/09/2026: UM arquivo de 47 páginas reais, 1.044 itens."""
    _dispara([_escreve(tmp_path, "caderno-executivo.pdf", 47)])
    assert bancada.rodou_motor == [JOB], (
        "a régua barrou o projeto com mais itens que a casa já entregou")


def test_CONTROLE_o_envio_de_24_arquivos_continua_entrando(bancada, tmp_path):
    """17/09/2026: 24 arquivos de 1 página, 609 itens."""
    _dispara([_escreve(tmp_path, "prancha-%02d.pdf" % i, 1) for i in range(24)])
    assert bancada.rodou_motor == [JOB], (
        "a régua barrou o segundo maior projeto da casa (24 arquivos de 1 "
        "página) — ela voltou a contar arquivo em vez de página")


def test_CONTROLE_o_envio_exatamente_no_teto_entra(bancada, tmp_path):
    """🪤 Piso é a mínima que resolve: exatamente 200 NÃO passa de 200."""
    _dispara([_escreve(tmp_path, "caderno-%d.pdf" % i, POR_PDF) for i in range(5)])
    assert bancada.rodou_motor == [JOB], (
        "o envio de exatamente %d páginas de leitura foi barrado — a comparação "
        "virou >= quando devia ser >" % TETO)


def test_CONTROLE_o_envio_comum_de_uma_prancha_entra(bancada, tmp_path):
    _dispara([_escreve(tmp_path, "planta.pdf", 1)])
    assert bancada.rodou_motor == [JOB]
    assert not bancada.emails, "mandou e-mail de falha num envio que passou"


def test_CONTROLE_o_caderno_gigante_de_um_arquivo_so_nunca_e_barrado(bancada, tmp_path):
    """🩸 A régua contava as páginas do ARQUIVO; o motor lê no máximo 40 de cada
    um. Um caderno único de 500 páginas custa 40 páginas de leitura, e caderno
    único é o formato do projeto com mais itens da casa. Sozinho, ele jamais
    pode bater no teto."""
    _dispara([_escreve(tmp_path, "caderno-de-500.pdf", 500)])
    assert bancada.rodou_motor == [JOB], (
        "um caderno único foi barrado pelo teto — a régua voltou a contar as "
        "páginas do arquivo em vez das que o motor lê")
    linha = _logs_de(bancada, "motor:paginas-do-envio")[0]["message"]
    assert "a_ler=%d" % POR_PDF in linha, (
        "o rastro não diz que só %d páginas serão lidas: %r" % (POR_PDF, linha))
    assert "/500" in linha, (
        "o rastro perdeu o tamanho REAL do arquivo — é ele que explica por que "
        "a planilha sai incompleta: %r" % linha)


# ══════════════════════════════════════════════════════════════════════════
#  A REGRA — o absurdo para antes de gastar IA
# ══════════════════════════════════════════════════════════════════════════
def test_o_envio_absurdo_para_antes_de_gastar_ia(bancada, tmp_path):
    """🧪 CONTROLE POSITIVO da regra inteira: se a régua sumir, isto reprova."""
    _dispara(_absurdo(tmp_path))                          # 6 × 40 = 240
    assert not bancada.rodou_motor, (
        "o motor rodou num envio de 240 páginas de leitura — a régua não está "
        "no caminho")
    erro = _erro_gravado(bancada)
    assert erro, "o job não foi marcado como erro: %r" % (bancada.updates,)
    assert "240" in erro["error_message"], (
        "a mensagem não diz QUANTAS páginas seriam lidas: %r"
        % erro["error_message"])


def test_a_regua_roda_ANTES_de_esperar_vaga(bancada, tmp_path):
    """🔑 Com `JOBS_SIMULTANEOS=1` um job já esperou 58 min por 2 min de máquina
    (18/09). Recusar depois da fila faria o cliente esperar uma hora para
    descobrir que não ia rodar — e prenderia a vaga de quem ia rodar."""
    _dispara(_absurdo(tmp_path))
    assert "fila" not in bancada.ordem, (
        "a régua recusou DEPOIS de esperar vaga: %r" % bancada.ordem)

    bancada.ordem.clear()
    _dispara([_escreve(tmp_path, "planta.pdf", 1)])
    assert bancada.ordem == ["fila", "motor"], (
        "🧪 controle: um envio que PASSA tem que esperar vaga antes do motor — "
        "se isto falhar, o teste acima passa por acidente: %r" % bancada.ordem)


def test_nada_de_ia_e_gasto_quando_a_regua_recusa(bancada, tmp_path):
    _dispara(_absurdo(tmp_path, n_arquivos=10))
    assert not bancada.rodou_motor, "gastou IA num envio que ia ser recusado"


def test_a_mensagem_diz_o_numero_o_limite_e_a_saida(bancada, tmp_path):
    """🔑 Recusa sem caminho de saída espanta cliente novo. E no MESMO dia a
    casa mandou um cliente trocar um arquivo que estava certo — o sujeito da
    frase tem que ser a casa, não ele."""
    envio = _absurdo(tmp_path, n_arquivos=5) + [
        _escreve(tmp_path, "edital-gordo.pdf", 60)]        # 5×40 + 40 = 240
    _dispara(envio)
    msg = _erro_gravado(bancada)["error_message"]

    assert "240" in msg, "não diz quantas páginas seriam lidas: %r" % msg
    assert str(TETO) in msg, "não diz qual é o limite: %r" % msg
    assert "edital-gordo.pdf" in msg, (
        "não aponta o arquivo mais gordo — a pessoa não sabe qual tirar: %r" % msg)
    assert re.search(r"dois projetos separados", msg, re.I), (
        "não oferece a saída que NÃO perde nada: %r" % msg)

    # 🩸 AS DUAS FRASES QUE A REVISÃO DERRUBOU, ambas por serem falsas.
    assert not re.search(r"n[ãa]o sai item|n[ãa]o s[ãa]o lidos|n[ãa]o lemos",
                         msg, re.I), (
        "a mensagem promete que edital/memorial não geram item — o próprio caso "
        "de 19/09 mediu 61% dos itens vindo deles: %r" % msg)
    assert not re.search(r"continuam guardados|nada se perdeu", msg, re.I), (
        "a mensagem promete que os arquivos ficaram guardados, mas a régua roda "
        "ANTES de qualquer upload pro Storage: %r" % msg)


def test_a_conta_e_de_PAGINA_e_nao_de_ARQUIVO(bancada, tmp_path):
    """🩸 A sabotagem W03 sobreviveu à primeira versão deste arquivo.

    Trocar `sum(páginas)` por `len(arquivos)` passava verde, porque todos os
    casos tinham arquivo e página andando juntos. As duas contas divergem nos
    dois sentidos, e os dois estão aqui.
    """
    _dispara(_absurdo(tmp_path))                     # 6 arquivos, 240 páginas
    assert not bancada.rodou_motor, (
        "seis arquivos somando 240 páginas de leitura passaram — a régua está "
        "contando ARQUIVO (6) em vez de PÁGINA (240)")

    bancada.rodou_motor.clear()
    bancada.updates.clear()
    _dispara([_escreve(tmp_path, "fina-%03d.pdf" % i, 1) for i in range(150)])
    assert bancada.rodou_motor == [JOB], (
        "150 pranchas de uma página foram barradas — a régua está contando "
        "ARQUIVO em vez de PÁGINA (150 cabem em 200)")


def test_o_rastro_traz_a_conta_por_arquivo_mesmo_quando_passa(bancada, tmp_path):
    """🔑 Até hoje o número real de páginas só existia pra quem estourava o
    corte de 40 — foi essa cegueira que produziu o 'recorde de 40 páginas' e
    quase fez o teto nascer errado."""
    _dispara([_escreve(tmp_path, "planta.pdf", 3)])
    linhas = _logs_de(bancada, "motor:paginas-do-envio")
    assert linhas, (
        "um envio que PASSOU não registrou a contagem — a casa continua sem "
        "saber quantas páginas os clientes mandam")
    assert "a_ler=3" in linhas[0]["message"], linhas[0]["message"]
    assert "planta.pdf=3/3" in linhas[0]["message"], (
        "o rastro não diz o tamanho de cada arquivo: %r" % linhas[0]["message"])


def test_o_email_avisa_que_reprocessar_nao_resolve(bancada, tmp_path):
    """🪤 Reprocessar roda o MESMO envio e bate no mesmo teto."""
    _dispara(_absurdo(tmp_path))
    assert bancada.emails, "o cliente não foi avisado de nada"
    assert bancada.emails[0]["reprocessavel"] is False, (
        "o e-mail ofereceu reprocessar, que cai no mesmo teto: %r"
        % bancada.emails[0])


def test_a_RECUSA_tem_stage_proprio_e_nao_e_rebaixada_a_migalha():
    """🪤 `_log_error` rebaixa a `info` todo stage que está em
    `_STAGES_DIAGNOSTICO` — inclusive quem pediu `warning`. A casa põe nomes
    nessa lista sempre que um stage fala demais, e a CONTAGEM fala em todo
    envio. Com um stage só para contar e para recusar, o dia em que alguém
    calasse a contagem calaria a recusa junto, em silêncio.
    """
    assert "motor:paginas-do-envio" in _FONTE and "motor:paginas-acima-do-teto" in _FONTE, (
        "os dois stages (contagem e recusa) precisam existir separados")
    assert "motor:paginas-acima-do-teto" not in main._STAGES_DIAGNOSTICO, (
        "a recusa por teto de páginas entrou na lista de diagnóstico — ela "
        "vira 'info' e some do painel de avisos do motor")
    assert "motor:paginas-gravacao-perdida" not in main._STAGES_DIAGNOSTICO, (
        "a falha de gravação do erro entrou na lista de diagnóstico — o "
        "projeto preso em processando deixa de aparecer como erro")


def test_a_recusa_e_a_contagem_saem_com_severidades_diferentes(bancada, tmp_path):
    """A contagem é diagnóstico (info, todo envio); a recusa é aviso."""
    _dispara(_absurdo(tmp_path))
    contagem = _logs_de(bancada, "motor:paginas-do-envio")
    recusa = _logs_de(bancada, "motor:paginas-acima-do-teto")
    assert contagem and contagem[0]["severity"] == "info", contagem
    assert recusa and recusa[0]["severity"] == "warning", recusa
    assert "recusado" in recusa[0]["message"], (
        "a linha da recusa não diz que o projeto foi recusado: %r" % recusa[0])

    # 🧪 CONTROLE POSITIVO: envio que passa registra a contagem e NÃO a recusa.
    bancada.logs.clear()
    _dispara([_escreve(tmp_path, "planta.pdf", 2)])
    assert _logs_de(bancada, "motor:paginas-do-envio")
    assert not _logs_de(bancada, "motor:paginas-acima-do-teto"), (
        "gritou recusa num envio que passou")


# ══════════════════════════════════════════════════════════════════════════
#  O QUE A REVISÃO ADVERSARIAL DERRUBOU
# ══════════════════════════════════════════════════════════════════════════
def test_projeto_que_JA_ENTREGOU_nao_vira_erro_pelo_teto(bancada, tmp_path):
    """🩸 O `/add-file` monta `file_paths` com o acervo INTEIRO do projeto — os
    anexos novos mais os antigos. Um anexo pequeno pode empurrar a soma acima
    do teto, e marcar erro aí sumiria a planilha da tela (o selo vira "NÃO
    GERADA") e mandaria e-mail de falha pra quem não perdeu nada. É o mesmo
    padrão que custou o caso de 19/09.

    🪤 A âncora é o FATO (a base já tem itens), não a flag `is_complement`: a
    retomada depois de um restart perde a flag e mantém o fato.
    """
    bancada.base_tem_itens = True
    _dispara(_absurdo(tmp_path))
    assert bancada.rodou_motor == [JOB], (
        "um complemento sobre projeto que já entregou foi barrado")
    assert not _erro_gravado(bancada), (
        "marcou erro num projeto com planilha entregue — ela some da tela")
    assert not bancada.emails, (
        "mandou e-mail de falha pra quem está com a planilha na mão")
    avisos = [x for x in _logs_de(bancada, "motor:paginas-acima-do-teto")
              if "JÁ tem planilha" in x["message"]]
    assert avisos, (
        "deixou passar em SILÊNCIO — sem rastro, ninguém descobre que o "
        "complemento passou por cima do teto")
    assert avisos[0]["severity"] == "warning", avisos[0]

    # 🧪 CONTROLE POSITIVO: o MESMO envio, em projeto SEM planilha, é recusado.
    bancada.base_tem_itens = False
    bancada.rodou_motor.clear()
    bancada.updates.clear()
    _dispara(_absurdo(tmp_path))
    assert not bancada.rodou_motor, (
        "sem a base entregue, o mesmo envio tinha que ser recusado — este "
        "controle prova que o teste acima não passa com a régua desligada")


def test_gravacao_perdida_do_erro_NAO_e_silenciosa(bancada, tmp_path):
    """🩸 `_supabase_update` não levanta quando falha: devolve False, inclusive
    em zero linhas afetadas. Engolir o retorno deixaria o projeto preso em
    "processando" pra sempre e o e-mail sem a âncora do texto — em silêncio."""
    bancada.update_devolve = False
    _dispara(_absurdo(tmp_path))
    perdidas = _logs_de(bancada, "motor:paginas-gravacao-perdida")
    assert perdidas, (
        "a gravação do erro falhou e ninguém ficou sabendo — o projeto fica "
        "preso em processando")
    assert perdidas[0]["severity"] == "error", (
        "a falha de gravação entrou como migalha: %r" % perdidas[0])

    # 🧪 CONTROLE POSITIVO: quando a gravação DÁ certo, não há alarme falso.
    bancada.update_devolve = True
    bancada.logs.clear()
    _dispara(_absurdo(tmp_path))
    assert not _logs_de(bancada, "motor:paginas-gravacao-perdida"), (
        "gritou 'gravação perdida' numa gravação que funcionou")


def test_o_teto_e_LIDO_da_variavel_e_nao_esta_chumbado(bancada, tmp_path):
    """🩸 O guarda antigo só conferia se a string "AIARQ_TETO_PAGINAS" existia
    no fonte. Isso passa mesmo com o valor chumbado logo abaixo. Aqui o teto é
    trocado em memória e o comportamento TEM que mudar junto."""
    envio = [_escreve(tmp_path, "prancha-%02d.pdf" % i, 1) for i in range(30)]
    _dispara(envio)
    assert bancada.rodou_motor == [JOB], "30 páginas não deviam ser barradas"

    bancada.rodou_motor.clear()
    original = main.TETO_PAGINAS_DO_ENVIO
    try:
        main.TETO_PAGINAS_DO_ENVIO = 10
        _dispara(envio)
    finally:
        main.TETO_PAGINAS_DO_ENVIO = original
    assert not bancada.rodou_motor, (
        "baixei o teto pra 10 e um envio de 30 páginas continuou passando — o "
        "valor está chumbado em algum lugar, e mexer na env não resolve nada")


# ══════════════════════════════════════════════════════════════════════════
#  AS BORDAS
# ══════════════════════════════════════════════════════════════════════════
def test_pdf_que_nao_abre_conta_como_uma_pagina_e_nao_barra(bancada, tmp_path):
    """🪤 A porta erra para o lado de DEIXAR PASSAR. Se um PDF ilegível
    contasse como o teto inteiro, um arquivo corrompido derrubaria um envio
    legítimo — trocaríamos um silêncio por um estrago."""
    ruins = []
    for i in range(40):
        p = tmp_path / ("quebrado-%02d.pdf" % i)
        p.write_bytes(b"%PDF-1.4 isto nao abre")
        ruins.append(str(p))
    _dispara(ruins)
    assert bancada.rodou_motor == [JOB], (
        "40 PDFs ilegíveis (1 página cada) foram barrados pelo teto")
    linhas = _logs_de(bancada, "motor:paginas-do-envio")
    assert linhas and "=1/1" in linhas[0]["message"], (
        "o PDF que não abre não aparece no rastro — vira silêncio")


def test_cad_nao_entra_na_conta_de_paginas(bancada, tmp_path):
    """CAD não tem página. Quem cobre envio de muito CAD é o teto de 50
    arquivos, que já existia no upload."""
    cad = [_cad(tmp_path, "planta-%03d.dwg" % i) for i in range(170)]
    pdfs = [_escreve(tmp_path, "caderno-%d.pdf" % i, POR_PDF) for i in range(5)]
    _dispara(cad + pdfs)                       # 200 de PDF + 170 CAD
    assert bancada.rodou_motor == [JOB], (
        "170 DWG entraram na conta de páginas: 200 de PDF cabem no teto, e só "
        "somando o CAD é que o envio estoura")


def test_envio_so_de_cad_nao_registra_nem_barra(bancada, tmp_path):
    """Sem PDF nenhum não há o que contar: a régua sai de cena inteira."""
    p = tmp_path / "planta.dxf"
    p.write_bytes(b"0\nSECTION\n")
    _dispara([str(p)])
    assert bancada.rodou_motor == [JOB]
    assert not _logs_de(bancada, "motor:paginas-do-envio")


def test_disparo_fora_do_contrato_nao_derruba_o_motor(bancada, tmp_path):
    """🪤 O contrato posicional é implícito. Se um disparo novo mandar outra
    forma no lugar de `file_paths`, a régua tem que sair de cena — nunca barrar
    um projeto por não ter entendido a chamada.

    🩸 A primeira versão passava uma string qualquer e a sabotagem sobreviveu,
    porque aquilo não terminava em .pdf e a conta dava zero de qualquer jeito.
    Agora vai uma TUPLA de arquivos acima do teto: quem aceitar qualquer
    iterável barra o job, e reprova aqui.
    """
    main._process_job_throttled(JOB, tuple(_absurdo(tmp_path)), "/tmp/x")
    assert bancada.rodou_motor == [JOB], (
        "um disparo fora do contrato foi barrado pela régua — ela passou a "
        "adivinhar a forma da chamada em vez de sair de cena")


# ══════════════════════════════════════════════════════════════════════════
#  O E-MAIL — a frase que liga a recusa ao conselho certo
# ══════════════════════════════════════════════════════════════════════════
def test_o_email_do_teto_nao_cai_no_balde_do_arquivo(bancada, tmp_path):
    """🩸 Sem o ramo próprio, esta falha cai no `else` e o cliente recebe "seu
    PDF é uma imagem escaneada, reenvie em DXF" — conselho falso E acusando o
    arquivo dele, no mesmo dia em que a casa já fez isso uma vez.

    🪤 `error_hint` é o `error_message` gravado, NÃO o `current_step`. Este
    guarda executa os DOIS lados: gera a mensagem real e passa ela pro montador
    do e-mail. Se alguém mudar uma frase e esquecer a outra, reprova aqui.
    """
    _dispara(_absurdo(tmp_path))
    msg = _erro_gravado(bancada)["error_message"]

    montado = main._build_falha_email(
        "cliente-01", "proj-de-teste", False, error_hint=msg, job_id=JOB)
    corpo = " ".join(str(x) for x in (montado if isinstance(montado, (list, tuple))
                                      else [montado]))
    assert re.search(r"pranchas de desenho|dois projetos", corpo, re.I), (
        "o e-mail não deu o conselho do teto de páginas — caiu em outro ramo")
    assert not re.search(r"imagem escaneada|fotografada", corpo, re.I), (
        "o e-mail acusou o arquivo do cliente de ser escaneado, que é falso "
        "neste caso e é o conselho do balde genérico")
    assert not re.search(r"n[ãa]o sai item|n[ãa]o s[ãa]o lidos", corpo, re.I), (
        "o e-mail repetiu a promessa falsa de que edital/memorial não geram "
        "item — 61% dos itens do caso de 19/09 vieram deles")


# ══════════════════════════════════════════════════════════════════════════
#  A TELA
# ══════════════════════════════════════════════════════════════════════════
def _painel():
    return io.open(os.path.join(_RAIZ, "dashboard.html"), encoding="utf-8").read()


def test_o_motor_e_a_tela_leem_o_mesmo_numero_de_paginas_por_pdf():
    """🪤 `PAGINAS_LIDAS_POR_PDF` e o `MAX_PAGES_PER_PDF` de dentro do
    `process_job` têm que ser o MESMO valor — se divergirem, a régua recusa por
    um trabalho que o motor não vai fazer."""
    assert "PAGINAS_LIDAS_POR_PDF = %d" % POR_PDF in _FONTE, (
        "a constante de páginas lidas por PDF sumiu ou mudou de valor")
    assert "MAX_PAGES_PER_PDF = PAGINAS_LIDAS_POR_PDF" in _FONTE, (
        "o process_job voltou a ter a própria cópia do limite de páginas — as "
        "duas divergem em silêncio")


def test_o_aviso_da_tela_vem_ANTES_do_teto_do_motor():
    """🪤 O aviso e o teto são coisas diferentes, de propósito: a tela informa
    quem ainda pode escolher, o motor só barra o absurdo. Mas o aviso precisa
    vir ANTES — avisar depois que o motor já parou não avisa nada."""
    m_tela = re.search(r"TETO_PAGINAS_ENVIO\s*=\s*(\d+)", _painel())
    assert m_tela, "o aviso de páginas sumiu do dashboard.html"
    m_srv = re.search(r'AIARQ_TETO_PAGINAS["\']\s*,\s*["\'](\d+)["\']', _FONTE)
    assert m_srv, "o default do teto sumiu do main.py"
    aviso, teto = int(m_tela.group(1)), int(m_srv.group(1))
    assert teto == TETO, (
        "o teto do motor mudou para %d e este guarda não sabia" % teto)
    assert aviso < teto, (
        "a tela avisa em %d páginas e o motor para em %d — o aviso chega "
        "depois da porta fechada" % (aviso, teto))


def test_o_aviso_da_tela_nao_ameaca_recusar():
    """🔑 O aviso fala de TEMPO, não de recusa: em 189 jobs medidos nenhum
    envio grande fracassou por ser grande."""
    painel = _painel()
    i = painel.find("function avisaSeOEnvioTemPaginasDemais")
    assert i > 0, "a função do aviso sumiu do dashboard.html"
    corpo = painel[i:i + 3000]
    assert "_warnToast(" in corpo, "o aviso sumiu"
    assert not re.search(r"vai ser recusado|ser[áa] recusado|n[ãa]o ser[áa] aceito",
                         corpo, re.I), (
        "o aviso ameaça recusar um envio que a casa processa — o caso de "
        "19/09 tinha 131 páginas e entregou 500 itens")


# ── A tela RODANDO, não lida ────────────────────────────────────────────
# 🩸 A primeira versão destes três guardas lia o fonte do `dashboard.html`
# procurando trechos de texto. A revisão derrubou: a função podia estar
# definida, com todas as palavras certas dentro, e nunca ser chamada — ou ser
# chamada com a conta errada. O motor JS da casa (dukpy) executa o código de
# verdade, e é ele que responde o que a pessoa VÊ.
def _bancada_da_tela():
    from _jsbancada import funcao_js, motor
    painel = _painel()
    # 🪤 `_ehPdf` é arrow function; `funcao_js` só acha `function nome(`. Puxa
    # a linha REAL do fonte para não testar contra uma cópia que diverge.
    m = re.search(r"const _ehPdf = ([^\n]+);", painel)
    assert m, "a régua que separa PDF de CAD sumiu da tela"
    prelu = (
        "var TETO_PAGINAS_ENVIO = %s;\n"
        "var selectedFiles = [];\n"
        "var _paginasDoArquivo = new Map();\n"
        "var _ultimaSomaAvisada = 0;\n"
        "var _avisos = []; var _eventos = [];\n"
        "function _warnToast(m){ _avisos.push(m); }\n"
        "function trackEvent(n, meta){ _eventos.push([n, meta]); }\n"
        "var _ehPdf = %s;\n"
        % (re.search(r"TETO_PAGINAS_ENVIO\s*=\s*(\d+)", painel).group(1),
           m.group(1)))
    return motor(prelu
                 + funcao_js("_somaDasPaginasDoEnvio", "dashboard.html", painel)
                 + funcao_js("avisaSeOEnvioTemPaginasDemais", "dashboard.html",
                             painel))


def _na_tela(js, escolhidos, contados):
    """Encena a escolha de arquivos e devolve o que a tela fez."""
    from _jsbancada import rodar
    arquivos = "[" + ",".join("{name:'%s'}" % n for n in escolhidos) + "]"
    conta = ";".join("_paginasDoArquivo.set('%s',%d)" % (n, p)
                     for n, p in contados.items()) or ";"
    saida = rodar(js, """(function(){
        selectedFiles = %s; %s;
        var r = _somaDasPaginasDoEnvio();
        avisaSeOEnvioTemPaginasDemais();
        return {soma: r.soma, faltam: r.faltam,
                avisos: _avisos.slice(), eventos: _eventos.slice()};
    })()""" % (arquivos, conta))
    assert saida.get("ok"), saida
    return saida["valor"]


def test_a_tela_conta_so_PDF_igual_ao_servidor():
    """🩸 A tela contava DWG/DXF como "1 página" cada, e o servidor não conta
    CAD nenhum. O número divergente ia junto pro evento de telemetria."""
    js = _bancada_da_tela()
    r = _na_tela(js, ["a.pdf", "b.pdf", "c.dwg", "d.dxf"],
                 {"a.pdf": 50, "b.pdf": 30})
    assert r["soma"] == 80, (
        "a tela somou %s em vez de 80 — o CAD entrou na conta de páginas"
        % r["soma"])
    assert r["faltam"] == 0, r


def test_a_tela_nao_avisa_com_a_conta_pela_metade():
    """🩸 A contagem é assíncrona (pdf.js abre um arquivo por vez). O aviso
    disparava no primeiro número acima do limite e nunca mais se atualizava:
    a tela mostrava, e o evento registrava, menos páginas do que o envio tinha.
    """
    js = _bancada_da_tela()
    # 70 já passa de 60, mas falta contar um arquivo: ninguém avisa ainda.
    r = _na_tela(js, ["a.pdf", "b.pdf", "grande.pdf"],
                 {"a.pdf": 40, "b.pdf": 30})
    assert r["faltam"] == 1 and not r["avisos"], (
        "avisou com a conta pela metade: %r" % r)

    # Agora o último chega, e o aviso sai com o número CHEIO.
    r = _na_tela(js, ["a.pdf", "b.pdf", "grande.pdf"],
                 {"a.pdf": 40, "b.pdf": 30, "grande.pdf": 25})
    assert len(r["avisos"]) == 1, r
    assert "95" in r["avisos"][0], (
        "o aviso mostrou um número que não é a soma real: %r" % r["avisos"][0])
    assert r["eventos"] and r["eventos"][0][1]["paginas"] == 95, (
        "o evento registrou um número diferente do que a tela mostrou: %r"
        % (r["eventos"],))


def test_a_tela_avisa_de_novo_quando_o_envio_CRESCE(tmp_path):
    """🩸 O aviso travava na primeira soma e nunca mais falava, mesmo o envio
    dobrando de tamanho depois."""
    js = _bancada_da_tela()
    r = _na_tela(js, ["a.pdf", "b.pdf"], {"a.pdf": 40, "b.pdf": 30})
    assert len(r["avisos"]) == 1, r
    r = _na_tela(js, ["a.pdf", "b.pdf", "c.pdf"],
                 {"a.pdf": 40, "b.pdf": 30, "c.pdf": 60})
    assert len(r["avisos"]) == 2, (
        "o envio foi de 70 pra 130 páginas e a tela não avisou de novo: %r" % r)
    assert "130" in r["avisos"][-1], r["avisos"][-1]


def test_CONTROLE_a_tela_fica_CALADA_no_envio_normal():
    """🧪 Sem isto, um aviso que dispara sempre passaria em todos os testes
    acima — e todo cliente veria um alarme que não tem motivo."""
    js = _bancada_da_tela()
    r = _na_tela(js, ["planta.pdf", "corte.pdf", "modelo.dwg"],
                 {"planta.pdf": 1, "corte.pdf": 1})
    assert not r["avisos"] and not r["eventos"], (
        "a tela alarmou num envio de 2 páginas: %r" % r)


def test_a_funcao_do_aviso_e_mesmo_CHAMADA_na_tela():
    """🪤 Guarda irmão dos de cima: eles provam que a função faz a coisa certa
    QUANDO chamada. Este prova que ela é chamada — nos três pontos em que o
    envio muda de tamanho."""
    painel = _painel()
    chamadas = painel.count("avisaSeOEnvioTemPaginasDemais()")
    assert chamadas >= 3, (
        "a função do aviso é chamada em %d lugar(es); precisa dos três — ao "
        "adicionar arquivo, ao remover, e quando o pdf.js termina de contar"
        % chamadas)


def test_o_aviso_da_tela_e_medido():
    """🚨 14/09: os avisos que a tela dispara sozinha ao escolher arquivo eram
    invisíveis, e é ali que os cadastros completos desistiam."""
    assert "'aviso_envio_paginas_demais'" in _painel(), (
        "o aviso de páginas demais não registra evento — não dá pra saber se "
        "quem viu tirou o edital e seguiu, ou fechou a aba")
    assert '"aviso_envio_paginas_demais"' in _FONTE, (
        "o evento não está na allowlist do /api/track — o backend descarta "
        "calado e o aviso volta a ser invisível")


def test_o_NUMERO_do_aviso_chega_junto_com_o_evento():
    """🩸 Liberar o NOME do evento e esquecer a CHAVE do meta: o evento chega,
    vazio, e o painel parece estar medindo. Aconteceu em 14/09 com `chars`,
    `n` e `restam` — e aconteceu de novo aqui, com `paginas`. Nas duas vezes
    quem pegou foi a bancada, na véspera do push.

    🔑 Sem o número, o evento não responde a única pergunta que ele existe para
    responder: quem viu o aviso tirou o edital e seguiu, ou fechou a aba?
    """
    i = _FONTE.find('"status", "chars", "n", "restam"')
    assert i > 0, (
        "a allowlist numérica do /api/track mudou de forma — conferir se "
        "`paginas` continua saneada como número")
    assert '"paginas"' in _FONTE[i - 200:i + 200], (
        "a chave `paginas` não está na allowlist numérica do /api/track: o "
        "backend descarta o número CALADO e o evento chega vazio")
