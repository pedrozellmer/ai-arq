# -*- coding: utf-8 -*-
"""O painel admin não renderiza dado do cliente cru dentro de innerHTML.

🚨 06/09/2026 — achado da auditoria total. O NOME DO PROJETO é escolhido pelo
cliente e gravado verbatim (backend/main.py:13885), ao contrário do nome de
ARQUIVO, que passa por `_sanitize_filename_for_storage`. No estudo de merge
(admin.html) esse nome entrava cru num `innerHTML`.

Um projeto batizado com uma tag de imagem e um handler de erro executaria
código na sessão do ADMIN, na origem ai.arq.br — onde mora o token do Supabase
que alcança as 117 contas e os 330 projetos. E a CSP não segura: `script-src`
tem 'unsafe-inline' (autoriza o handler) e `connect-src` tem o curinga
`*.supabase.co` (qualquer um cria um projeto grátis e ganha um destino de
exfiltração autorizado).

🪤 Era o ÚNICO dos seis lugares que renderizam `project_name` sem escapar — os
outros cinco já usavam `esc()`. Esquecimento isolado, não doença sistêmica.

🔑 Buraco VAZIO, não sangramento: SQL em produção no dia do achado mostrou 0 de
330 projetos com sinal de payload no nome. Ninguém plantou nada — foi por isso
que entrou como SÉRIO e não como CRÍTICO.
"""
import io
import os
import re

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))
_ADMIN = os.path.join(_RAIZ, "admin.html")


def _fonte():
    return io.open(_ADMIN, encoding="utf-8").read()


def _sem_comentarios(src):
    """🪤 Tira comentário HTML e JS antes de procurar.

    Três vezes hoje um guarda meu acusou o MEU PRÓPRIO comentário, escrito pra
    explicar por que o defeito não deve existir. Aqui o comentário do conserto
    cita a interpolação antiga de propósito — sem esta limpeza, este guarda
    reprovaria o código correto.
    """
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return src


# Campos que vêm do CLIENTE e aparecem no painel. `nome` e `dono` são o
# project_name e o e-mail; ambos chegam ao admin pela rota de merge-preview.
_CAMPOS_DO_CLIENTE = ("d.original.nome", "d.original.dono")


def test_o_estudo_de_merge_escapa_nome_e_email_do_cliente():
    src = _sem_comentarios(_fonte())
    for campo in _CAMPOS_DO_CLIENTE:
        # toda interpolação `${... campo ...}` tem que passar por esc(
        for m in re.finditer(r"\$\{([^}]*" + re.escape(campo) + r"[^}]*)\}", src):
            trecho = m.group(1)
            assert "esc(" in trecho, (
                "dado do cliente entra cru no innerHTML do admin: ${%s}\n"
                "Use esc() — a função já existe no mesmo arquivo." % trecho.strip())


def test_a_funcao_de_escape_existe():
    """Guarda do guarda: se `esc` sumir, o teste acima passaria vazio."""
    assert re.search(r"function esc\s*\(", _fonte()), (
        "a função esc() sumiu do admin.html — os escapes acima viraram erro de "
        "JavaScript em tempo de execução")


def test_CONTROLE_a_peneira_ACHA_a_interpolacao_crua():
    """O guarda só vale se souber acusar. Aqui rodo a peneira contra a linha
    exata que existia até hoje."""
    antiga = "<p>${d.original.nome || ''} &middot; ${d.original.dono || ''}</p>"
    achou = []
    for campo in _CAMPOS_DO_CLIENTE:
        for m in re.finditer(r"\$\{([^}]*" + re.escape(campo) + r"[^}]*)\}", antiga):
            if "esc(" not in m.group(1):
                achou.append(m.group(1))
    assert len(achou) == 2, (
        "a peneira parou de reconhecer a versão crua — o controle positivo "
        "deixou de provar qualquer coisa: %r" % achou)


def test_CONTROLE_a_peneira_APROVA_a_versao_escapada():
    nova = "<p>${esc(d.original.nome || '')} &middot; ${esc(d.original.dono || '')}</p>"
    for campo in _CAMPOS_DO_CLIENTE:
        for m in re.finditer(r"\$\{([^}]*" + re.escape(campo) + r"[^}]*)\}", nova):
            assert "esc(" in m.group(1)


def test_CONTROLE_a_limpeza_de_comentario_funciona():
    """🪤 Prova que o próprio comentário do conserto não derruba o guarda —
    foi o erro que eu cometi três vezes hoje."""
    com_comentario = ("<!-- aqui entrava ${d.original.nome || ''} sem escapar -->\n"
                      "<p>${esc(d.original.nome || '')}</p>")
    limpo = _sem_comentarios(com_comentario)
    assert "sem escapar" not in limpo, "o comentário sobreviveu à limpeza"
    assert "esc(d.original.nome" in limpo, "a limpeza comeu o código junto"
