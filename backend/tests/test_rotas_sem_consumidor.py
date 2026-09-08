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
           # 🪤 08/09/2026 — entra aqui, com os irmãos, e NÃO por um arquivo de
           # migração pendente. Este guarda mede "o SITE chama?"; cron nunca é
           # chamado pelo site. Mas atenção: estar no _IGNORA NÃO prova que o
           # cron existe — e o de token NÃO existe (`cron.job` não tem job de
           # token; medido em 08/09). Quem prova isso é uma consulta ao banco.
           "/api/token/tick",
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
    `/api/token/tick` de nascer morta. Eu tratei como falso-positivo e alarguei
    a função pra ler `backend/migrations_pendentes/*.sql` como se fosse
    chamador.

    🚨 08/09/2026 — ISSO ESTAVA ERRADO, E O GUARDA ESTAVA CERTO. Migração
    PENDENTE é intenção, não chamador. Medido no banco de produção:
    `cron.job` tem 4 jobs (ig_scheduler, metricas, newsletter, emails-auto) e
    NENHUM de token; a tabela `meta_token` existe mas está VAZIA — ou seja, a
    migração 002 rodou pela METADE (o bloco de cima criou a tabela, o
    `cron.schedule` de baixo nunca foi aplicado). A rota nunca foi chamada uma
    vez, e os 4 `_log_error` dentro dela são inalcançáveis.

    🪤 A LIÇÃO: eu ALARGUEI UM GUARDA PRA CALAR UM ACHADO VERDADEIRO. Absolver
    por um arquivo cujo nome diz "pendente" é o oposto de medir. E o preço é
    real — a renovação do token do Instagram continua não existindo (ver o
    aviso ao lado de `/api/token/tick` em main.py).

    🔑 O tratamento certo é o mesmo dos irmãos: rota de cron entra no `_IGNORA`,
    porque este guarda mede "o SITE chama?" e cron nunca é chamado pelo site.
    Quem tem que provar que o cron existe é uma consulta ao `cron.job`, não um
    teste que lê arquivo.
    """
    partes = []
    for nome in os.listdir(RAIZ):
        if nome.endswith((".html", ".js")):
            partes.append(io.open(os.path.join(RAIZ, nome), encoding="utf-8",
                                  errors="replace").read())
    # workflows e scripts do GitHub CHAMAM rota de verdade (o CI roda).
    # 🚫 `migrations_pendentes` NÃO entra: ver o 🚨 de 08/09 acima.
    for pasta, exts in ((os.path.join(RAIZ, ".github", "workflows"), (".yml", ".yaml")),
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
