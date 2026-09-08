#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""O `requirements.txt` RESOLVE? Guarda de pre-push.

🩸 POR QUE EXISTE — 08/09/2026. Subi `pdfplumber` de 0.11.0 pra 0.11.10 por
segurança e derrubei o CI **e** o build do Render de uma vez:

    pdfplumber 0.11.10 depends on pypdfium2>=5.9.0
    The user requested pypdfium2==4.30.0
    ERROR: ResolutionImpossible

🔑 O BURACO NÃO FOI O PIN, FOI A CEGUEIRA. A bancada local passou com 3166
testes verdes — porque ela **nunca instala do `requirements.txt`**: roda contra
o que já está na máquina. Um arquivo que não resolve é, pra ela, invisível por
construção. É a mesma doença de [[feedback_medir_com_ferramenta_que_a_producao_nao_tem]],
só que pior: aqui o arquivo não era nem lido.

🚫 E não adianta pôr isso na bancada: `pip` precisa de REDE, e teste que depende
de rede fica intermitente — vermelho que não é defeito ensina a ignorar
vermelho. O lugar certo é o push, que já precisa de rede de qualquer jeito.

🔑 Roda SÓ se o `requirements.txt` mudou — senão todo push pagaria ~40s por um
arquivo que ninguém tocou.

🔒 Falha FECHA a porta, como as outras travas deste diretório. "Não consegui
saber se resolve" não pode virar "pode subir": foi exatamente esse otimismo que
mandou o pin quebrado pro ar.

Emergência: AIARQ_DEPLOY_FORCE=1 git push origin main   (pula TODAS as travas)
"""
import os
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(_AQUI)
ALVO = "backend/requirements.txt"
TIMEOUT = 300

#: 🔑 As marcas que o pip usa pra dizer "não resolve". Ficam aqui, nomeadas,
#: porque a DECISÃO tem que ser testável sem rede — a bancada chama
#: `veredito()` com saída gravada de verdade, e prova que ela REPROVA.
_MARCAS_DE_CONFLITO = (
    "ResolutionImpossible",
    "conflicting dependencies",
    "Cannot install",
    "no matching distribution",
    "could not find a version that satisfies",
)

OK, CONFLITO, NAO_SEI = "ok", "conflito", "nao_sei"


def veredito(saida, returncode):
    """Decide a partir da saída do `pip`. Sem rede, sem efeito colateral.

    🪤 Não basta olhar o `returncode`: o pip sai != 0 por rede caída, por
    proxy, por disco cheio — e isso é "não sei", não "conflito". Tratar os dois
    igual faria o guarda gritar "conflito de dependência" num aeroporto com
    wi-fi ruim, e aí alguém desativa o guarda. Distinguir é o que o mantém vivo.
    """
    texto = (saida or "").lower()
    if any(m.lower() in texto for m in _MARCAS_DE_CONFLITO):
        return CONFLITO
    if returncode == 0:
        return OK
    return NAO_SEI


def linhas_do_conflito(saida, limite=12):
    """As linhas que EXPLICAM o conflito, pra mensagem não ser um muro de log."""
    uteis, pegando = [], False
    for ln in (saida or "").splitlines():
        seco = ln.strip()
        if not seco:
            continue
        if "conflict is caused by" in seco.lower():
            pegando = True
        if pegando or any(m.lower() in seco.lower() for m in _MARCAS_DE_CONFLITO):
            uteis.append(seco)
        if len(uteis) >= limite:
            break
    return uteis


def mudou():
    """True se o requirements.txt entra NESTE push (ou na dúvida)."""
    try:
        vistas = []
        for cmd in (["git", "diff", "--name-only", "origin/main...HEAD"],
                    ["git", "diff", "--name-only", "HEAD"],
                    ["git", "ls-files", "--others", "--exclude-standard"]):
            r = subprocess.run(cmd, cwd=RAIZ, capture_output=True,
                               text=True, timeout=30)
            vistas.append(r.stdout or "")
        return ALVO in "".join(vistas)
    except Exception:
        return True          # na dúvida, confere


def main():
    if not mudou():
        return 0

    caminho = os.path.join(RAIZ, ALVO.replace("/", os.sep))
    if not os.path.exists(caminho):
        print("\n🚦 PUSH BLOQUEADO — não achei %s." % ALVO)
        return 1

    print("→ conferindo se o %s resolve (o pin quebrado de 08/09 passou por "
          "aqui)…" % ALVO)
    try:
        # 🪤 `--ignore-installed` é o que importa: sem ele o pip aceita o que já
        # está na máquina e o conflito some — o guarda ficaria verde pelo mesmo
        # motivo que a bancada ficou.
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--dry-run",
             "--ignore-installed", "-r", caminho],
            cwd=RAIZ, capture_output=True, text=True, timeout=TIMEOUT)
        saida = (r.stdout or "") + "\n" + (r.stderr or "")
        v = veredito(saida, r.returncode)
    except Exception as e:
        print("\n🚦 PUSH BLOQUEADO — não consegui rodar o pip (%s)."
              % type(e).__name__)
        print("   Falha FECHA a porta. Emergência: AIARQ_DEPLOY_FORCE=1 git push\n")
        return 1

    if v == OK:
        print("✓ %s resolve — o install do CI e do Render não vai quebrar" % ALVO)
        return 0

    if v == CONFLITO:
        print("\n🚦 PUSH BLOQUEADO — o %s NÃO RESOLVE." % ALVO)
        print("   O CI e o build do Render quebram no passo de INSTALAR, antes")
        print("   de qualquer teste rodar. Foi assim em 08/09 com o pdfplumber.\n")
        for ln in linhas_do_conflito(saida):
            print("   %s" % ln)
        print("\n   🔑 Pacote pinado costuma prender OUTRO pacote com `==`.")
        print("   Procure o degrau de versão que sobe o que você quer sem")
        print("   arrastar o resto: no caso do pdfplumber era o 0.11.9.\n")
        return 1

    print("\n🚦 PUSH BLOQUEADO — não deu pra saber se o %s resolve." % ALVO)
    print("   (rede? proxy? o pip saiu %s sem falar em conflito)" % r.returncode)
    print("   Tente de novo, ou force: AIARQ_DEPLOY_FORCE=1 git push\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
