# -*- coding: utf-8 -*-
"""Reprova mensagem de commit que carrega nome de cliente. Roda no `commit-msg`.

🚨 08/09/2026, auditoria de segurança. Medido em `origin/main`: **236 dos 1334
commits** amarram **56 nomes de cliente** a um incidente técnico e a uma data.
O padrão é sistemático — *"caso <NOME>"*, *"incidente <NOME>"*, *"crash do
<NOME>"*. Cada uma liga uma pessoa identificável a uma falha no projeto DELA,
publicamente e para sempre, num repositório público.

🔑 O ACHADO TEM DUAS METADES, e esta é a que não depende de ninguém decidir:
**parar o fluxo**. Limpar o passado exige reescrever histórico e forçar push
(quebra clones) — é decisão do Pedro. Impedir a próxima é um hook.

🪤 A hemorragia já tinha parado sozinha em 06/09, quando a regra nasceu — mas
por disciplina, não por guarda. Disciplina não sobrevive a um dia corrido.

🚫 NÃO reimplementa a régua: importa `_HASH_DE_NOME`, `_HASH_DE_NOME_COMPLETO` e
`_sem_acento` do próprio guarda da bancada. Duas cópias da mesma lista é como
elas divergem — foi exatamente o defeito de hoje de manhã.
"""
import io
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
# 🫤 `scripts/` de proposito, e nao `.claude/hooks/`: aquele diretorio esta no
# .gitignore, entao o hook so existiria NESTA maquina e morreria no proximo
# clone. Guarda que nao viaja com o repositorio nao guarda o repositorio.
_RAIZ = os.path.dirname(_AQUI)
_GUARDA = os.path.join(_RAIZ, "backend", "tests",
                       "test_repo_publico_nao_expoe_cliente.py")


def _carrega_guarda():
    """Importa o guarda da bancada sem passar pelo pytest."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_g_lgpd", _GUARDA)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_g_lgpd"] = mod
    spec.loader.exec_module(mod)
    return mod


def revisar(mensagem, guarda=None):
    """Devolve lista de motivos pra recusar. Vazia = pode commitar.

    🪤 Só o que a pessoa ESCREVEU: as linhas de `#` que o git acrescenta
    (status, arquivos) trazem caminhos e não são a mensagem.

    🪤 `guarda` existe pro TESTE poder injetar uma lista plantada. A 1ª versão
    não tinha, e o controle positivo do guarda tentava trocar o módulo em
    `sys.modules` — inútil, porque esta função carrega um módulo NOVO a cada
    chamada e sobrescrevia a troca. O teste passava dizendo que recusava, e
    não recusava nada.
    """
    linhas = [l for l in mensagem.splitlines() if not l.startswith("#")]
    texto = "\n".join(linhas)
    if not texto.strip():
        return []

    if guarda is not None:
        return _motivos(texto, guarda)
    try:
        g = _carrega_guarda()
    except Exception as e:
        # 🚨 FALHA FECHADA seria pior aqui: um hook que quebra o commit por
        # não conseguir se carregar vira hook que alguém desativa. Avisa alto
        # e deixa passar — a bancada continua sendo a rede.
        sys.stderr.write(
            "[nome-no-commit] NAO CONSEGUI CONFERIR (%s: %s).\n"
            "   O commit segue, mas a bancada e quem vai pegar.\n"
            % (type(e).__name__, str(e)[:120]))
        return []
    return _motivos(texto, g)


def _motivos(texto, g):
    """A decisão, separada de COMO o guarda foi carregado."""
    motivos = []
    for m in g._PALAVRA.finditer(texto):
        if g._e_nome_de_cliente(m.group(0)):
            motivos.append("nome de cliente: %r" % m.group(0))
    if g.nomes_completos_no_texto(texto):
        motivos.append("nome COMPLETO de cliente (o identificador mais forte)")
    for e in g._RE_PESSOAL.findall(texto):
        if e.lower() not in g._DO_DONO:
            motivos.append("e-mail pessoal de terceiro")
    # dedup mantendo a ordem
    vistos, fora = set(), []
    for m in motivos:
        if m not in vistos:
            vistos.add(m)
            fora.append(m)
    return fora


def main():
    if len(sys.argv) < 2:
        return 0
    try:
        msg = io.open(sys.argv[1], encoding="utf-8", errors="replace").read()
    except Exception:
        return 0
    motivos = revisar(msg)
    if not motivos:
        return 0
    sys.stderr.write(
        "\n"
        "  MENSAGEM DE COMMIT COM DADO DE CLIENTE — nao vou deixar virar historia.\n"
        "\n"
        "  Motivo(s): %s\n"
        "\n"
        "  O repositorio e PUBLICO, e mensagem de commit NAO se apaga: limpar\n"
        "  exige reescrever historico e forcar push, que quebra todo clone.\n"
        "  Ja sao 236 commits assim la atras — nao acrescente o 237.\n"
        "\n"
        "  O CASO e o que ensina, nunca a pessoa. Troque pelo rotulo estavel\n"
        "  (cliente-NN) ou pelo job_id, que ja e opaco:\n"
        "     ruim : \"conserta o crash do <NOME> (job 3eb748e3)\"\n"
        "     bom  : \"conserta o crash do job 3eb748e3 (cliente-45)\"\n"
        "\n" % "; ".join(motivos[:4]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
