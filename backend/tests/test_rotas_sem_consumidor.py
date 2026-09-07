# -*- coding: utf-8 -*-
"""Catraca de rotas SEM consumidor no site (auditoria 30-31/08/2026).

A auditoria achou 8 rotas do backend que nenhuma página chama. Decisão
consciente: **não apagar**. Rota morta não roda, não custa e algumas nasceram
pra tela que ainda vem (a busca TCPO da revisão, por exemplo); apagar código
que funciona, sem necessidade, é risco sem retorno — e já perdemos um dia
inteiro com duas funções de mesmo nome (20/08).

O que resolve de verdade o achado é IMPEDIR QUE CRESÇA. Este guarda trava o
número onde está: rota nova sem chamador reprova aqui, e quem apagar uma
morta tem que baixar o teto no mesmo commit (senão o guarda vira letra morta —
mesma mecânica da catraca do relógio, que levou main.py de 64 a 0).

🪤 Só conta rota de CLIENTE: admin/debug/webhook/cron/health são chamados de
fora do site por definição.
"""
import io
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND = os.path.join(RAIZ, "backend")

_ROTA = re.compile(r'@app\.(get|post|put|delete|patch)\("(/api/[^"]+)"')
_IGNORA = ("/api/admin/", "/api/debug/", "/api/instagram/", "/api/whatsapp/",
           "/api/health", "/api/track", "/api/csp-report",
           "/api/emails/auto/tick", "/api/newsletter/", "/api/metricas/tick",
           "/api/public/", "/api/contact", "/api/nps")

# 📉 TETO: 7 rotas sem consumidor, MEDIDAS por este detector em 31/08/2026.
# SÓ PODE DESCER. (A auditoria contou 8: a diferença é o prefixo /api/projects,
# que este detector considera usado — prefiro subestimar a errar acusando.)
# As 7: calibration/reclassify-raws, checkout/verify, heuristics/check,
# heuristics/summary, projects-confidence, tcpo/details, tcpo/search.
#
# ⏳ 05/09/2026 — as 2 rotas do Financeiro da obra nasceram ANTES da tela (teto
# subiu pra 9 por umas horas, com prazo) e voltaram pra 7 no MESMO dia, quando
# financeiro.html passou a chamar `/api/financeiro`. A catraca funcionou como
# desenhada: `test_quando_uma_ORFA_some_o_teto_cai_junto` cobrou a volta.
_TETO_ROTAS_ORFAS = 7


def _fonte_do_site():
    """Tudo que pode CHAMAR uma rota — não só o site.

    🩸 06/09/2026 — este detector lia só HTML e JS da raiz e acusou
    `/api/token/tick` de nascer morta. Ela não nasceu morta: é chamada por um
    cron do Supabase, declarado em `backend/migrations_pendentes/*.sql`. O
    guarda media a FORMA ("o site chama?") quando o fato que ele quer é
    "alguém chama?". Rota de cron, de webhook e de CI é órfã do site por
    desenho, e acusá-las ensina a desligar o guarda.

    🪤 Continua ESTREITO de propósito: só entra quem é chamador de verdade
    (site, cron em migração, workflow). Varrer o repo inteiro absolveria
    qualquer rota citada num comentário — que é o defeito oposto.
    """
    partes = []
    for nome in os.listdir(RAIZ):
        if nome.endswith((".html", ".js")):
            partes.append(io.open(os.path.join(RAIZ, nome), encoding="utf-8",
                                  errors="replace").read())
    # cron do Supabase (pg_cron chama a rota por URL) e workflows do GitHub
    for pasta, exts in ((os.path.join(BACKEND, "migrations_pendentes"), (".sql",)),
                        (os.path.join(RAIZ, ".github", "workflows"), (".yml", ".yaml")),
                        (os.path.join(RAIZ, ".github", "scripts"), (".py",))):
        if not os.path.isdir(pasta):
            continue
        for nome in os.listdir(pasta):
            if nome.endswith(exts):
                partes.append(io.open(os.path.join(pasta, nome), encoding="utf-8",
                                      errors="replace").read())
    return "\n".join(partes)


def _orfas():
    src = io.open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
    site = _fonte_do_site()
    orfas = []
    for _metodo, rota in _ROTA.findall(src):
        if rota.startswith(_IGNORA):
            continue
        # o front chama por template: compara o PREFIXO estável (antes do 1º {})
        base = rota.split("{")[0].rstrip("/")
        if not base or base == "/api":
            continue
        if base not in site:
            orfas.append(rota)
    return sorted(set(orfas))


def test_nenhuma_rota_orfa_NOVA():
    orfas = _orfas()
    assert len(orfas) <= _TETO_ROTAS_ORFAS, (
        "%d rotas de cliente sem chamador no site (teto: %d). A nova é "
        "provavelmente uma destas: %s. Ou o front esqueceu de chamar, ou a "
        "rota nasceu morta." % (len(orfas), _TETO_ROTAS_ORFAS, orfas[-4:]))


def test_quando_uma_ORFA_some_o_teto_cai_junto():
    """🪤 Sem isto o teto vira letra morta: alguém limpa 5 rotas, o teto fica
    em 8, e 5 rotas mortas novas passariam verdes."""
    orfas = _orfas()
    assert len(orfas) >= _TETO_ROTAS_ORFAS, (
        "só %d órfãs e o teto ainda diz %d — baixe o teto pra %d neste mesmo "
        "commit." % (len(orfas), _TETO_ROTAS_ORFAS, len(orfas)))


def test_CONTROLE_POSITIVO_o_detector_acha_uma_orfa_plantada(tmp_path, monkeypatch):
    """🧪 Todo guarda prova que REPROVA."""
    import test_rotas_sem_consumidor as mod
    monkeypatch.setattr(mod, "_fonte_do_site", lambda: "nada aqui")
    orfas = mod._orfas()
    assert len(orfas) > _TETO_ROTAS_ORFAS, (
        "com o site vazio TODAS as rotas deviam parecer órfãs — o detector "
        "está cego")
