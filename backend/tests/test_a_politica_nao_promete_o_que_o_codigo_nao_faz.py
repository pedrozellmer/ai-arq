# -*- coding: utf-8 -*-
"""A Política de Privacidade, o banner e os Termos só prometem o que o código faz.

⚖️ 28/09/2026 — parecer do jurídico sobre a política (Pedro: "todas as correções", "publicar já, advogado em
paralelo", "24 meses"). No ar desde julho: "exclusivamente no navegador… não são transmitidos aos nossos servidores"
— falso para a origem da 1ª visita (vai pra conta), o `aiarq_cid` (vai com a telemetria) e o convite. E a 1ª versão
da correção dizia que o IP do visitante "não chega até nós", mas o tick diário lê o `clientIP` do Cloudflare
(`metricas_site.coletar`, em memória; grava só totais). Cada frase aqui foi conferida no código ou no banco.
"""
import html
import io
import os
import re
import subprocess

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _texto(nome):
    return html.unescape(io.open(os.path.join(_RAIZ, nome), encoding="utf-8").read())


# frases que já foram falsas — não voltam
_FALSAS = ("exclusivamente no navegador", "não são transmitidos aos nossos servidores", "não chega até nós",
           "sob seu exclusivo controle")


def test_a_politica_e_os_termos_nao_dizem_que_nada_sai_do_navegador():
    for nome in ("privacidade.html", "termos.html"):
        t = _texto(nome)
        for frase in _FALSAS:
            assert frase not in t, "%s: %r voltou" % (nome, frase)


def test_a_politica_conta_os_dois_jeitos_de_contar_visita():
    t = _texto("privacidade.html")
    assert "Não gravamos o seu endereço IP" in t          # o registro da rede (clientIP) está dito
    assert "descarta o endereço IP" in t                   # o script do Web Analytics
    assert "legítimo interesse na segurança do site" in re.sub(r"</?em>", "", t)   # cf_clearance: não é contrato


def test_o_prazo_da_telemetria_e_o_que_o_banco_cumpre():
    t = _texto("privacidade.html")
    assert "24 meses" in re.sub(r"</?strong>", "", t)
    sql = io.open(os.path.join(_RAIZ, "backend", "migrations_pendentes",
                               "telemetria_24_meses_e_junto_com_a_conta.sql"), encoding="utf-8").read()
    assert "interval '24 months'" in sql and "after delete on auth.users" in sql
    assert "apagada junto com a conta" in t


def test_o_banner_diz_o_que_roda_sem_o_sim_e_que_o_sim_cobre_o_antes():
    cc = _texto("cookie-consent.js")
    assert "antes de responder" in cc and "antes da sua resposta" in cc
    assert "robôs" in cc and "contagem de visitas sem cookie" in cc.lower()
    assert not re.search(r"an[oô]nim", cc, re.I), "o aiarq_cid liga a visita à conta: é pseudônimo, não anônimo"


# ─── todo "Sair" apaga a fila de antes do "sim" ───────────────────────────────────────────────
_LIMPA = "removeItem('aiarq_fila_pre_sim')"


def _sairs_sem_limpar(src):
    """Posições de `auth.signOut(` sem a limpeza da fila nos ~1.500 caracteres antes (o mesmo clique)."""
    return [m.start() for m in re.finditer(r"auth\.signOut\(", src) if _LIMPA not in src[max(0, m.start() - 1500):m.start()]]


def _arquivos_com_sair():
    saida = subprocess.run(["git", "ls-files", "*.html", "*.js"], cwd=_RAIZ, capture_output=True).stdout
    nomes = saida.decode("utf-8", "replace").split()
    return [n for n in nomes if "/" not in n and "auth.signOut(" in io.open(os.path.join(_RAIZ, n), encoding="utf-8").read()]


def test_todo_sair_da_conta_apaga_a_fila_de_antes_do_sim():
    nomes = _arquivos_com_sair()
    assert len(nomes) >= 5, nomes            # dashboard, menu-lateral, escritorio, cadastro, convite (+ admin)
    for n in nomes:
        src = io.open(os.path.join(_RAIZ, n), encoding="utf-8").read()
        assert not _sairs_sem_limpar(src), "%s: Sair sem apagar a fila (a próxima conta da aba levaria os eventos)" % n


def test_CONTROLE_sem_a_limpeza_o_guarda_reprova():
    src = io.open(os.path.join(_RAIZ, "dashboard.html"), encoding="utf-8").read()
    assert not _sairs_sem_limpar(src)
    sem = src.replace("try { sessionStorage.removeItem('aiarq_fila_pre_sim'); } catch (_) {}", "")
    assert sem != src and _sairs_sem_limpar(sem)
