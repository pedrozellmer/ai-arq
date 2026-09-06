# -*- coding: utf-8 -*-
"""O repositório é PÚBLICO: nenhum comentário identifica um cliente.

🚨 06/09/2026 — o segundo CRÍTICO da auditoria total, e o mais constrangedor:
comentários e docstrings de teste identificavam titulares reais pelo e-mail
inteiro, e ainda contavam um fato sobre eles — quantas devoluções a caixa de
e-mail teve, o que a pessoa perguntou no chat, a que horas subiu o projeto,
quantos projetos tinha. Tudo em github.com/pedrozellmer/ai-arq, que é público.

Foram 5 e-mails completos e 12 apelidos únicos (a parte antes do @), em 19
arquivos, amarrados a job_id e horário.

🔑 O VALOR DO COMENTÁRIO É O CASO, NUNCA A PESSOA. "cliente-02 16/06: só
funcionou na 4ª tentativa manual" ensina exatamente o mesmo que o nome ensinava,
e o rótulo é estável — o mesmo cliente mantém o mesmo número em todos os
arquivos, então a história continua rastreável sem identificar ninguém.

🪤 O e-mail do PEDRO fica: ele é o dono, e `ADMIN_EMAIL` é configurável por
variável de ambiente — está no código como default, não como dado de terceiro.

⏭️ Isto limpa o HEAD. O HISTÓRICO do git ainda tem tudo, e removê-lo de verdade
exige reescrever o histórico e forçar o push (quebra clones). Essa decisão é do
Pedro; este guarda impede que volte daqui pra frente.
"""
import glob
import io
import os
import re

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)

# Domínios de e-mail pessoal. @ai.arq.br e example.com são nossos e podem ficar.
_RE_PESSOAL = re.compile(
    r"[A-Za-z0-9._%+-]+@(?:gmail|outlook|hotmail|yahoo|uol|bol|terra|live|icloud|"
    r"protonmail|me|msn)\.com(?:\.br)?", re.I)

# 🔑 A exceção é UMA e é explícita: os e-mails DO DONO. Não são dado de
# terceiro — são o admin (`ADMIN_EMAIL`), o destino das notificações internas
# (`NOTIFY_EMAIL`) e a conta de smoke test, todos do Pedro, e os dois primeiros
# são apenas o DEFAULT de uma variável de ambiente.
# 🪤 Lista fechada de propósito: uma peneira que dispensasse "qualquer e-mail
# que apareça em comentário" deixaria passar exatamente o defeito que este
# arquivo existe pra pegar.
_DO_DONO = {
    "zarelalopes@gmail.com",        # ADMIN_EMAIL (main.py:107)
    "pedro.zellmer@gmail.com",      # NOTIFY_EMAIL (main.py:3010)
    "zarelalopes+smoke@gmail.com",  # conta de smoke test (main.py:28157) — alias do próprio admin
}


def _fontes():
    alvos = []
    for padrao in ("backend/**/*.py", "*.html", "*.js", "blog/*.py"):
        alvos += glob.glob(os.path.join(_RAIZ, padrao), recursive=True)
    for f in sorted(set(alvos)):
        if "__pycache__" in f or os.path.basename(f) == os.path.basename(__file__):
            continue
        try:
            yield f, io.open(f, encoding="utf-8", errors="replace").read()
        except Exception:
            continue


def test_nenhum_email_pessoal_de_terceiro_no_codigo():
    """🚨 O repo é público. E-mail de cliente em comentário é dado pessoal
    publicado — e vem acompanhado de um fato sobre a pessoa, o que é pior."""
    achados = []
    for f, src in _fontes():
        for m in _RE_PESSOAL.finditer(src):
            if m.group(0).lower() in _DO_DONO:
                continue        # e-mail do proprio dono, nao de terceiro
            linha = src[:m.start()].count(chr(10)) + 1
            achados.append("%s:%d" % (os.path.relpath(f, _RAIZ), linha))
    assert not achados, (
        "e-mail pessoal de terceiro no repositório PÚBLICO: %s\n"
        "Troque por um rótulo estável (cliente-NN) ou pelo job_id, que já é "
        "opaco. O valor do comentário é o CASO, não a pessoa." % achados)


def test_nenhum_apelido_de_cliente_sobreviveu():
    """A parte ANTES do @ identifica igual — e escapa do regex de e-mail. Estes
    doze estavam espalhados por 16 arquivos, cada um amarrado a um caso."""
    apelidos = ["ivaldogss", "jssoliveira88", "thallisson.producao", "eng.kovatch",
                "kasavitski", "rafaelcmnz", "humberto.oliveira", "marcioeng72",
                "valimduda", "lpleonardo", "v.anjos.ia.81", "diana.golin",
                "alansilvacosta", "ialves943", "estudosmaraligrupo",
                "professormoabgarcia", "adn.arquiteturadinamica"]
    achados = []
    for f, src in _fontes():
        for a in apelidos:
            if a in src:
                achados.append("%s: %s" % (os.path.relpath(f, _RAIZ), a[:4] + "***"))
    assert not achados, (
        "apelido de cliente ainda no repositório público: %s" % achados)


def test_o_rotulo_opaco_continua_ENSINANDO_o_caso():
    """🔑 Anonimizar não pode custar a lição. Se o rótulo entrou, a história
    tem que ter ficado — senão trocamos um problema de privacidade por uma
    perda de conhecimento."""
    achou_caso = False
    for f, src in _fontes():
        if "cliente-02" in src and "4ª tentativa" in src:
            achou_caso = True
    assert achou_caso, (
        "o caso do retry (que justifica o backoff de ~5min em llm_retry.py) "
        "perdeu o contexto na anonimização — o rótulo tem que substituir o "
        "nome, não apagar a história")


def test_CONTROLE_o_padrao_ACHA_um_email_plantado():
    """O guarda só vale se souber acusar."""
    falso = '# 🚨 caso maria.silva@gmail.com — 3 devoluções'
    m = _RE_PESSOAL.search(falso)
    assert m and m.group(0) == "maria.silva@gmail.com", (
        "o padrão parou de reconhecer e-mail pessoal")


def test_CONTROLE_o_padrao_NAO_acusa_o_que_e_nosso():
    """contato@ai.arq.br e example.com são nossos e precisam continuar
    passando — guarda que acusa o certo acaba desligado."""
    for ok in ("contato@ai.arq.br", "cliente1@example.com",
               "noreply@mail.app.supabase.io"):
        assert not _RE_PESSOAL.search(ok), ok


def test_CONTROLE_as_excecoes_sao_POUCAS_e_do_dono():
    """Prova que a exceção é uma lista fechada e que ela realmente casaria com
    o padrão — senão vira letra morta e qualquer e-mail passa."""
    assert len(_DO_DONO) <= 3, (
        "a lista de exceção cresceu: %d. Cada e-mail a mais é um dado pessoal "
        "que passou a ser tolerado no repo público" % len(_DO_DONO))
    for e in _DO_DONO:
        assert _RE_PESSOAL.search(e), (
            "%s não casa com o padrão — está na lista de exceção à toa, e a "
            "peneira pode ter parado de funcionar" % e)


# ─────────────────────────────────────────────────────────────────────────────
#  NOME também identifica (06/09/2026 — Pedro: "LGPD sempre forte")
# ─────────────────────────────────────────────────────────────────────────────
# 🩸 A primeira limpeza tirou e-mail e apelido, e eu disse ao Pedro que estava
# resolvido. Ele perguntou: "o nome dos clientes deixou de ser exposto?" — e a
# resposta era NÃO. Sobravam 269 menções de 23 nomes, em 79 arquivos. Várias
# escritas por mim no mesmo dia, nos comentários dos consertos.
#
# Nome sozinho talvez não identifique. Nome + job_id + horário + o que a pessoa
# perguntou no chat, num repositório público, identifica — e era assim que eles
# apareciam.
_NOMES_DE_CLIENTE = [
    "Marcelo", "Affonso", "Flavio", "Hermolin", "Devair", "Amanda", "Paranhos",
    "Alan", "Eduarda", "Catarina", "Caroline", "Edvaldo", "Thamiry", "Tammyres",
    "Karina", "Arthur", "Adriano", "Walter", "Luana", "Yuri", "Wilker", "Weslei",
    "Leonardo", "Daniela", "William", "Osorio", "Osório", "Rafael", "Natália",
]

_FRONTEIRA = chr(92) + "b"   # \b sem passar por escape de shell


def test_nenhum_NOME_de_cliente_no_repositorio():
    """🚨 A REGRA: no repositório público, cliente é rótulo — nunca nome.

    🪤 "Pedro" fica: é o dono falando de si mesmo, e ele assina os commits.
    """
    achados = []
    for f, src in _fontes():
        for nome in _NOMES_DE_CLIENTE:
            padrao = _FRONTEIRA + re.escape(nome) + _FRONTEIRA
            for m in re.finditer(padrao, src):
                linha = src[:m.start()].count(chr(10)) + 1
                achados.append("%s:%d (%s)" % (os.path.relpath(f, _RAIZ), linha,
                                               nome[:3] + "***"))
    assert not achados, (
        "nome de cliente no repositorio PUBLICO: %s — use um rotulo estavel "
        "(cliente-NN) ou o job_id. O caso e o que ensina; o nome nao acrescenta "
        "nada e e dado pessoal." % achados[:8])


def test_CONTROLE_o_padrao_de_nome_usa_FRONTEIRA_de_palavra():
    """Sem fronteira, "Ana" pegaria "Analisar" e "Rafael" pegaria "Rafaela" —
    o guarda viraria ruído e alguém o desligaria no primeiro dia."""
    p_ana = _FRONTEIRA + "Ana" + _FRONTEIRA
    assert not re.search(p_ana, "Analisar a planilha do projeto")
    p_walter = _FRONTEIRA + "Walter" + _FRONTEIRA
    assert re.search(p_walter, "o caso Walter de 30/07")


def test_CONTROLE_o_dono_NAO_e_acusado():
    """O Pedro é citado em centenas de comentários. Se o guarda reclamasse
    dele, seria desligado antes de pegar qualquer cliente."""
    for texto in ("decisão do Pedro, 06/09", "Pedro Zellmer", "o Pedro pediu"):
        for nome in _NOMES_DE_CLIENTE:
            padrao = _FRONTEIRA + re.escape(nome) + _FRONTEIRA
            assert not re.search(padrao, texto), (
                "%r foi acusado em %r" % (nome, texto))

# ─────────────────────────────────────────────────────────────────────────────
#  NOME também identifica (06/09/2026, Pedro: "LGPD sempre forte")
# ─────────────────────────────────────────────────────────────────────────────
# 🩸 A primeira limpeza tirou e-mail e apelido e eu disse ao Pedro que estava
# resolvido. Ele perguntou "o nome dos clientes deixou de ser exposto?" — e a
# resposta era NÃO: sobravam 269 menções de 23 nomes, em 79 arquivos. Vários
# escritos por mim naquele mesmo dia.
#
# Nome sozinho pode não identificar. Nome + job_id + horário + o que a pessoa
