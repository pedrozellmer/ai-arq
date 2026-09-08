# -*- coding: utf-8 -*-
"""Instala os hooks de git deste repositório em `.git/hooks/`.

🪤 `.git/hooks/` NÃO é versionado. Escrever o verificador e não instalar é a
diferença entre "o hook existe" e "o hook roda" — a mesma distância entre
submeter um formulário e estar cadastrado (05/09), e entre consertar o alcance
e consertar o padrão. Rode isto depois de clonar.

Idempotente: reescreve o hook e não toca em mais nada.
"""
import io
import os
import stat
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(_AQUI)

#: nome do hook -> script que ele chama
_HOOKS = {
    "commit-msg": "verificar_nome_na_mensagem.py",
}

_MOLDE = """#!/bin/sh
# Gerado por .claude/hooks/instalar.py — nao edite aqui, edite o script.
exec "{python}" "{script}" "$@"
"""


def main():
    destino = os.path.join(_RAIZ, ".git", "hooks")
    if not os.path.isdir(destino):
        print("nao achei .git/hooks — este diretorio e um clone git?")
        return 1
    for nome, script in _HOOKS.items():
        caminho_script = os.path.join(_AQUI, script)
        if not os.path.exists(caminho_script):
            print("[X] %s: script %s nao existe" % (nome, script))
            continue
        alvo = os.path.join(destino, nome)
        if os.path.exists(alvo):
            atual = io.open(alvo, encoding="utf-8", errors="replace").read()
            if script not in atual:
                # 🚨 Nao sobrescreve hook de terceiro em silencio: se alguem ja
                # tem um commit-msg proprio, apagar seria trocar um guarda por
                # outro sem avisar.
                print("[!] %s ja existe e NAO chama %s — nao vou sobrescrever.\n"
                      "    Junte os dois a mao, ou apague o antigo e rode de novo."
                      % (nome, script))
                continue
        io.open(alvo, "w", encoding="utf-8", newline="\n").write(
            _MOLDE.format(python=sys.executable.replace("\\", "/"),
                          script=caminho_script.replace("\\", "/")))
        os.chmod(alvo, os.stat(alvo).st_mode | stat.S_IEXEC)
        print("[OK] %s -> %s" % (nome, script))
    return 0


if __name__ == "__main__":
    sys.exit(main())
