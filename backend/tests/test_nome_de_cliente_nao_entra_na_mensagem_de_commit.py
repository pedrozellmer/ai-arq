# -*- coding: utf-8 -*-
"""Nome de cliente não pode virar mensagem de commit — porque isso não se apaga.

🚨 08/09/2026, auditoria de segurança. Medido em `origin/main`: **236 dos 1334
commits** amarram **56 nomes de cliente** a um incidente técnico e a uma data.
O padrão é sistemático — *"caso <NOME>"*, *"incidente <NOME>"*, *"crash do
<NOME>"*. Cada um liga uma pessoa identificável a uma falha no projeto DELA,
publicamente e para sempre.

🔑 O achado tem DUAS METADES. Limpar o passado exige reescrever histórico e
forçar push (quebra todo clone) — decisão do Pedro. **Parar o fluxo é um hook**,
e é isso que este arquivo protege.

🪤 A hemorragia já tinha parado em 06/09, quando a regra nasceu — mas por
DISCIPLINA, não por guarda. Disciplina não sobrevive a um dia corrido, e o
custo aqui é permanente.

🚫 O hook não reimplementa a régua: importa `_HASH_DE_NOME`,
`nomes_completos_no_texto` e `_RE_PESSOAL` do guarda da bancada. Duas cópias da
mesma lista é como elas divergem — foi o defeito de hoje de manhã.
"""
import io
import os
import subprocess
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)
# 🫤 `scripts/` e nao `.claude/hooks/`: aquele diretorio esta no .gitignore.
# O hook morava la e teria morrido no proximo clone — guarda que nao viaja
# com o repositorio nao guarda o repositorio.
_HOOK = os.path.join(_RAIZ, "scripts", "verificar_nome_na_mensagem.py")


def _revisor():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_h_msg", _HOOK)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_h_msg"] = mod
    spec.loader.exec_module(mod)
    return mod.revisar


def test_o_hook_existe_e_carrega():
    assert os.path.exists(_HOOK), "o verificador de mensagem sumiu"
    assert callable(_revisor())


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLE POSITIVO — ele tem que RECUSAR de verdade
# ══════════════════════════════════════════════════════════════════════════
def _guarda_com_nome_plantado(monkeypatch, palavra=b"jose"):
    """O guarda de verdade, com UMA palavra plantada na lista.

    🪤 A 1ª versão deste controle trocava o módulo em `sys.modules` — e não
    funcionava: o hook carrega um módulo NOVO a cada chamada e sobrescrevia a
    troca. O teste dizia que recusava e não recusava nada. Foi por isso que o
    `revisar` passou a aceitar o guarda INJETADO.
    """
    import hashlib
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_g_ctrl", os.path.join(_AQUI, "test_repo_publico_nao_expoe_cliente.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    monkeypatch.setattr(g, "_HASH_DE_NOME",
                        frozenset({hashlib.md5(palavra).hexdigest()}))
    return g


def test_RECUSA_mensagem_com_nome_de_cliente(monkeypatch):
    """🧪 Com nome plantado na lista, o hook precisa barrar. Sem este controle,
    um revisor que sempre devolvesse [] passaria em todos os outros testes."""
    g = _guarda_com_nome_plantado(monkeypatch)
    motivos = _revisor()("conserta o crash do Jose (job 3eb748e3)", guarda=g)
    assert motivos, "passou nome de cliente na mensagem de commit"
    assert any("nome de cliente" in m for m in motivos), motivos


def test_CONTROLE_a_injecao_do_guarda_MUDA_o_resultado(monkeypatch):
    """🧪 Prova que o parâmetro não é enfeite: com a lista plantada recusa, e
    sem ela a MESMA mensagem passa."""
    g = _guarda_com_nome_plantado(monkeypatch)
    msg = "conserta o crash do Jose (job 3eb748e3)"
    assert _revisor()(msg, guarda=g)
    assert not _revisor()(msg), (
        "a mensagem foi recusada pelo guarda REAL — escolha outra palavra "
        "plantada, senão este controle não prova nada")


def test_RECUSA_email_de_terceiro():
    revisar = _revisor()
    motivos = revisar("responde o cliente em fulano.detal@gmail.com")
    assert motivos and any("mail" in m for m in motivos), motivos


def test_ACEITA_o_email_do_DONO():
    """CONTROLE: o e-mail do Pedro é default de variável de ambiente e aparece
    legitimamente. Barrar ele viraria hook que alguém desativa."""
    revisar = _revisor()
    assert not revisar("ajusta o ADMIN_EMAIL padrao (zarelalopes@gmail.com)")


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLE POSITIVO ao contrário — não pode barrar o commit legítimo
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("msg", [
    "Conserta a paginacao acima de mil itens (job aec7cac2)",
    "Caso cliente-45: a area de 880.000 passava pelo teto",
    "Motor: o resgate por medicao nao casava em 3 jobs seguidos",
    "",
    "# On branch main\n# Changes to be committed:\n#\tmodified: main.py",
])
def test_ACEITA_mensagem_limpa(msg):
    assert not _revisor()(msg), msg


def test_as_linhas_de_COMENTARIO_do_git_sao_ignoradas(monkeypatch):
    """🪤 O git acrescenta `# modified: <caminho>` ao editor. Se o hook lesse
    essas linhas, um caminho de arquivo com nome dentro barraria o commit — e
    a pessoa não teria como consertar, porque não escreveu aquilo."""
    g = _guarda_com_nome_plantado(monkeypatch)
    assert not _revisor()("conserta o teto\n#\tmodified: docs/jose.md\n", guarda=g)
    # CONTROLE: fora do comentário, a MESMA palavra barra
    assert _revisor()("conserta o teto do jose\n", guarda=g)


# ══════════════════════════════════════════════════════════════════════════
#  Ele tem que estar INSTALADO — script no repo não roda sozinho
# ══════════════════════════════════════════════════════════════════════════
def test_o_hook_esta_INSTALADO_no_git():
    """🪤 Guarda de instalação, e é o que separa "escrevi o hook" de "o hook
    roda". `.git/hooks/` não é versionado: quem clonar precisa instalar.

    🚫 Pula em vez de reprovar fora de um clone git — o CI roda em checkout e
    não é ele que faz commit.
    """
    hooks = os.path.join(_RAIZ, ".git", "hooks")
    if not os.path.isdir(hooks):
        pytest.skip("fora de um clone git")
    alvo = os.path.join(hooks, "commit-msg")
    if not os.path.exists(alvo):
        pytest.skip("hook não instalado NESTA máquina (instale com "
                    "`python scripts/instalar_hooks.py`) — o guarda de conteúdo "
                    "acima continua valendo")
    conteudo = io.open(alvo, encoding="utf-8", errors="replace").read()
    assert "verificar_nome_na_mensagem" in conteudo, (
        "existe um commit-msg instalado que NÃO chama o verificador")


def test_o_hook_roda_de_verdade_como_processo(tmp_path):
    """Executa o hook como o git executaria: argv[1] = arquivo da mensagem."""
    p = tmp_path / "COMMIT_EDITMSG"
    p.write_text("Conserta a paginacao (job aec7cac2)", encoding="utf-8")
    r = subprocess.run([sys.executable, _HOOK, str(p)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout, r.stderr)
