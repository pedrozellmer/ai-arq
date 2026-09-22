# -*- coding: utf-8 -*-
"""`email_sent_log` não sabia de qual JOB o e-mail tinha saído.

🩸 18/09/2026. Fui auditar uma pergunta simples — "o que o cliente recebeu
quando a entrega não mediu nada?" — e descobri que não dava pra responder. O
registro de envio guarda e-mail, tipo, assunto e hora, e mais nada. Pra ligar
um envio a uma entrega só restava cruzar por **endereço + janela de tempo**.

📏 O que esse cruzamento me disse, e quanto dele era mentira: ele acusou SETE
casos de "o mesmo job mandou dois e-mails". Fui conferir um a um: **SEIS eram
artefato** — o cliente tinha dois jobs terminando dentro da mesma janela, e
cada e-mail casava com os dois. Um método que erra 6 de 7 não mede nada, e eu
já tinha repassado dois achados errados ao Pedro em cima dele.

🔑 A memória de 16/09 já registrava isso como o que MAIS limitou cinco
medições daquele dia: "depois que o job termina, não dá pra provar o que o
motor fez; email_sent_log não tem job_id". Ficou registrado e continuou doendo.

🪤 A coluna é ANULÁVEL de propósito: boas-vindas, resposta de contato e alerta
interno não nascem de job nenhum. O que não pode é string vazia fingindo
vínculo — por isso a chave só entra quando há job de verdade.
"""
import ast
import io
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

#: tipos de e-mail que SEMPRE nascem de um job — estes têm que carregar o job_id
_KINDS_DE_JOB = {
    "planilha_pronta", "leu_sem_medir", "sem_medida", "complemento_pronto",
    "reprocesso_pronto", "erro_reprocessar", "erro_trocar",
    "leitura_combinada", "leitura_nova",
    # 21/09: o anexo que não mudou a planilha também diz de qual job veio
    "complemento_sem_resultado",
}


class _SMTPFalso:
    """Um servidor que aceita tudo e não toca em rede."""
    enviados = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, *a):
        pass

    def sendmail(self, de, para, msg):
        _SMTPFalso.enviados.append((de, para))


@pytest.fixture
def porta_de_email(monkeypatch):
    """Roda `_send_email_smtp` DE VERDADE, sem rede e sem banco."""
    import smtplib
    import main

    del _SMTPFalso.enviados[:]
    gravadas = []

    monkeypatch.setattr(smtplib, "SMTP", _SMTPFalso)
    monkeypatch.setattr(main, "_supabase_insert",
                        lambda tabela, linha: gravadas.append((tabela, linha)))
    # sem consultar supressão nem decidir "interno" por rede
    monkeypatch.setattr(main, "_email_suprimido", lambda *a, **k: "")
    monkeypatch.setattr(main, "_email_eh_interno", lambda *a, **k: False)
    monkeypatch.setattr(main, "_marcar_links_do_email", lambda html, kind: html)
    for var, valor in (("SMTP_HOST", "smtp.exemplo.test"), ("SMTP_USER", "u"),
                       ("SMTP_PASSWORD", "p"), ("SMTP_PORT", "587")):
        monkeypatch.setenv(var, valor)
    return main, gravadas


def _linha_do_log(gravadas):
    fichas = [linha for tabela, linha in gravadas if tabela == "email_sent_log"]
    assert fichas, "nenhuma ficha foi gravada em email_sent_log"
    return fichas[-1]


# ══════════════════════════════════════════════════════════════════════════
#  O julgamento: rodar a porta de saída e ler o que foi gravado
# ══════════════════════════════════════════════════════════════════════════

def test_o_job_chega_ao_registro_de_envio(porta_de_email):
    """O caso que a auditoria de 18/09 não conseguiu responder."""
    main, gravadas = porta_de_email
    ok = main._send_email_smtp("cliente@exemplo.test", "assunto", "<p>oi</p>",
                               log_kind="planilha_pronta", job_id="abc12345")
    assert ok is True, "o envio falhou — o guarda não mediu nada"
    linha = _linha_do_log(gravadas)
    assert linha.get("job_id") == "abc12345", (
        "o job não chegou ao email_sent_log: %r" % linha)
    assert linha.get("kind") == "planilha_pronta"


def test_email_SEM_job_nao_grava_vinculo_falso(porta_de_email):
    """🪤 Boas-vindas não nasce de job. Vazio tem que virar AUSENTE, não ''.

    String vazia entraria no índice e fingiria um vínculo que não existe — e
    quem consultasse depois contaria e-mails de um job chamado "".
    """
    main, gravadas = porta_de_email
    main._send_email_smtp("cliente@exemplo.test", "bem-vindo", "<p>oi</p>",
                          log_kind="boas_vindas")
    linha = _linha_do_log(gravadas)
    assert "job_id" not in linha, (
        "e-mail sem job gravou a chave mesmo assim: %r" % linha)


def test_espaco_em_branco_nao_vira_job(porta_de_email):
    """🪤 `job_id="  "` é a mesma mentira com outra roupa."""
    main, gravadas = porta_de_email
    main._send_email_smtp("cliente@exemplo.test", "x", "<p>x</p>",
                          log_kind="nps_relacional", job_id="   ")
    assert "job_id" not in _linha_do_log(gravadas)


def test_o_registro_continua_com_o_que_ja_tinha(porta_de_email):
    """Controle de vizinhança: a coluna nova não pode ter comido as antigas."""
    main, gravadas = porta_de_email
    main._send_email_smtp("cliente@exemplo.test", "um assunto qualquer",
                          "<p>oi</p>", log_kind="complemento_pronto", job_id="j1")
    linha = _linha_do_log(gravadas)
    for campo in ("email", "kind", "subject"):
        assert linha.get(campo), "o campo %s sumiu da ficha: %r" % (campo, linha)


# ══════════════════════════════════════════════════════════════════════════
#  A costura: todo e-mail que NASCE de job tem que passar o job
# ══════════════════════════════════════════════════════════════════════════

def _chamadas_de_envio():
    """Cada `_send_email_smtp(...)` do main.py, com o kind e se passa job_id."""
    arvore = ast.parse(_FONTE)
    fora = []
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
                and no.func.id == "_send_email_smtp"):
            continue
        kinds, tem_job = set(), False
        for kw in no.keywords:
            if kw.arg == "job_id":
                tem_job = True
            elif kw.arg == "log_kind":
                # o kind pode ser literal ou um if/else de dois literais
                for sub in ast.walk(kw.value):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        kinds.add(sub.value)
        fora.append((no.lineno, kinds, tem_job))
    return fora


def test_TODO_email_que_nasce_de_job_carrega_o_job():
    """🔑 O guarda que impede o buraco de voltar por uma porta nova.

    Ancorado no FATO (o tipo do e-mail), não em número de linha: quem
    acrescentar amanhã um envio de `planilha_pronta` sem passar o job cai aqui.
    """
    chamadas = _chamadas_de_envio()
    assert len(chamadas) >= 10, (
        "achei só %d chamadas de _send_email_smtp — o leitor de AST quebrou e "
        "este guarda pararia de medir" % len(chamadas))
    faltando = [(ln, sorted(k)) for ln, k, tem in chamadas
                if (k & _KINDS_DE_JOB) and not tem]
    assert not faltando, (
        "e-mail que nasce de um job e NÃO registra de qual "
        "(linha, kinds): %r" % faltando)


def test_CONTROLE_o_leitor_de_AST_enxerga_os_kinds():
    """🧪 Guarda que lê AST e não acha nada passa verde guardando nada."""
    chamadas = _chamadas_de_envio()
    vistos = set()
    for _ln, kinds, _t in chamadas:
        vistos |= kinds
    assert _KINDS_DE_JOB <= vistos, (
        "o leitor não enxergou estes kinds no fonte: %r"
        % sorted(_KINDS_DE_JOB - vistos))


def test_TODO_duble_da_porta_de_email_aceita_parametro_novo():
    """🩸 SEGUNDA VEZ que isto morde — 16/09 e 18/09.

    Ao ligar o `job_id`, 12 guardas ficaram VERMELHOS de uma vez, e a mensagem
    não dizia nada sobre parâmetro: dizia "o Liberar não mandou exatamente um
    e-mail: []". Três dublês de `_send_email_smtp` tinham assinatura EXATA
    (`to_email, subject, html_body, text_body="", log_kind="email"`), então a
    chamada nova virou TypeError — engolido pelo `try/except` da produção — e
    o teste passou a medir ZERO e-mail.

    🪤 A sorte foi a chamada acontecer dentro de um bloco que o teste conferia.
    Num guarda que só olhasse "não deu erro", o dublê quebrado passaria VERDE
    para sempre, medindo nada. Ver
    [[feedback_duble_com_assinatura_exata_desarma_calado]].

    Este guarda cobra o freio: todo dublê da porta única de e-mail tem que
    aceitar `**kwargs`. É barato e vale para o parâmetro que ainda não existe.
    """
    import glob
    pasta = os.path.dirname(os.path.abspath(__file__))
    frouxos = []
    for caminho in glob.glob(os.path.join(pasta, "*.py")):
        fonte = io.open(caminho, encoding="utf-8").read()
        if '"_send_email_smtp"' not in fonte:
            continue
        arvore = ast.parse(fonte)
        # nomes trocados por dublê: setattr(alvo, "_send_email_smtp", NOME)
        nomes = set()
        for no in ast.walk(arvore):
            if (isinstance(no, ast.Call) and getattr(no.func, "attr", "") == "setattr"
                    and len(no.args) >= 3):
                chave = no.args[1]
                if isinstance(chave, ast.Constant) and chave.value == "_send_email_smtp":
                    if isinstance(no.args[2], ast.Name):
                        nomes.add(no.args[2].id)
                    elif isinstance(no.args[2], ast.Lambda):
                        if not no.args[2].args.kwarg:
                            frouxos.append((os.path.basename(caminho), "<lambda>"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.FunctionDef) and no.name in nomes:
                if not no.args.kwarg:
                    frouxos.append((os.path.basename(caminho), no.name))
    assert not frouxos, (
        "dublê de _send_email_smtp com assinatura EXATA — quando a produção "
        "ganhar um parâmetro novo, vira TypeError engolido e o guarda passa a "
        "medir zero e-mail, verde. Ponha `**k`: %r" % frouxos)


def test_CONTROLE_a_costura_REPROVA_quem_esquece():
    """🧪 Prova que morde, sem tocar no arquivo: um envio de job sem job_id."""
    falso = ast.parse('_send_email_smtp(e, s, h, log_kind="planilha_pronta")')
    chamada = falso.body[0].value
    kinds = {sub.value for kw in chamada.keywords if kw.arg == "log_kind"
             for sub in ast.walk(kw.value)
             if isinstance(sub, ast.Constant) and isinstance(sub.value, str)}
    tem_job = any(kw.arg == "job_id" for kw in chamada.keywords)
    assert (kinds & _KINDS_DE_JOB) and not tem_job, (
        "a costura não reprovaria uma chamada que esquece o job")
