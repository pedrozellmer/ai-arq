# -*- coding: utf-8 -*-
"""Aviso não promete o que não aconteceu — e quem espera na fila sabe disso.

🩸 DOIS CASOS REAIS DE 02/09/2026, do mesmo dia.

**(1) O aviso que prometia.** cliente-31 Oliveira (job `bf72d192`) informou 150 m² no
upload e recebeu: *"Área total de 150 m² foi INFORMADA POR VOCÊ… **Ela entra
como BASE pros itens de área** — confira antes de orçar."*

Conferido no banco: **zero itens com 150**, **zero itens dizendo "informado por
você"**, e o log do motor com `preenchidos=0`. A área dela não entrou em lugar
nenhum.

🔑 A causa: o aviso é escrito ANTES de `_apply_area_honesty` decidir, e aquele
ramo exige `pdfvec_m2 <= 0` — ou seja, só usa a área informada quando a gente
NÃO mediu. As 10 pranchas dela mediram, então nunca ia usar. O aviso prometia
um resultado que a própria regra impedia.

Agora o aviso de cima só CONSTATA o fato (você informou X), e o destino vira
aviso DEPOIS, quando existir: usou em N itens, ou não usou e por quê.

**(2) A fila muda.** cliente-19 chegou enquanto o job dela rodava. O servidor
processa um por vez (semáforo posto depois do caso cliente-29, 16/06, quando 2-3
simultâneos somavam picos de RAM e derrubavam a instância). Ele ficou **12
minutos** com o status `queued` — e a tela do cliente só sabia desenhar
`current_step`, que num job em fila ainda não existe. Barra parada perto de
zero, nenhuma palavra. O admin já mostrava "Na fila"; o cliente não.

🪤 SEM CONTAGEM e SEM ESTIMATIVA, por decisão do Pedro e por medição: "3 na
frente" vira ansiedade e muda enquanto ele olha; tempo seria número inventado —
a mediana é 8 min, e os dois jobs de hoje levaram 23 e 14.

📏 E a fila é rara: em 158 projetos desde 01/06, só **10 pares** eram de
clientes DIFERENTES esperando um pelo outro. Por isso o conserto é o aviso, não
a capacidade — subir pra 2 simultâneos levaria a memória a 3,81 GB de 4,29 GB
(medido no caso cliente-16, 26/08) e o freio de 85% abortaria job de cliente.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _corpo import bloco_desde  # noqa: E402


def _main():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _sem_comentarios(txt):
    return "\n".join(l for l in txt.splitlines() if not l.lstrip().startswith("#"))


# ── (1) o aviso da área informada ──────────
_ANCORA_UPLOAD = '        if _uta > 0 and not (project_data.total_area or 0):'


class _ProjectDataFake:
    def __init__(self, total_area=0, total_area_source=""):
        self.total_area = total_area
        self.total_area_source = total_area_source
        self.warnings = None


def _rodar(ancora, project_data, **extras):
    """EXECUTA o bloco real do `process_job` e devolve os avisos do cliente."""
    logs = []
    ns = {
        "project_data": project_data,
        "job_id": "job-de-teste",
        "_log_error": lambda stage, msg, job=None, **k: logs.append((stage, str(msg))),
        "print": lambda *a, **k: None,
    }
    ns.update(extras)
    exec(compile(bloco_desde(ancora), "<main:%s>" % ancora[:24], "exec"), ns, ns)
    return list(project_data.warnings or []), logs


def _aviso_do_upload(area_informada=150.0):
    """O cenário da cliente-31 no momento do upload: ela informou, a planta não
    trouxe quadro de áreas ainda."""
    pd = _ProjectDataFake(total_area=0)
    avisos, _ = _rodar(_ANCORA_UPLOAD, pd, _uta=float(area_informada))
    assert len(avisos) == 1, (
        "esperava UM aviso no ramo da área informada, veio %r" % (avisos,))
    return avisos[0], pd


# Palavras que só cabem em quem já SABE o destino. No momento do upload a
# decisão ainda não foi tomada — `_apply_area_honesty` roda ~600 linhas depois.
_PROMESSAS = ("iten", "item", "entra", "vira", "será", "sera", "serve",
              "usada", "usar", "base")


def test_o_aviso_do_upload_NAO_promete_que_vai_usar():
    """🩸 A frase que a cliente-31 leu e não se cumpriu.

    🩸 06/09: o guarda anterior bania UMA string exata do `main.py`
    ("entra como BASE pros itens de área"). Mutação que passou verde:
    acrescentar ao mesmo aviso "Ela entra como base dos itens de area." — a
    promessa volta parafraseada e a string banida continua ausente.

    Agora o teste lê o aviso RENDERIZADO e cobra a regra, não a frase: no
    upload a gente só pode CONSTATAR. Qualquer palavra que fale de destino
    (itens, entra, vira, usada, base…) é promessa feita antes da decisão.
    """
    aviso, _ = _aviso_do_upload()
    baixo = aviso.lower()
    achadas = [p for p in _PROMESSAS if p in baixo]
    assert not achadas, (
        "o aviso do upload voltou a falar do DESTINO da área (%s) — ele é "
        "escrito antes de `_apply_area_honesty` decidir, e no job da "
        "cliente-31 a decisão foi NÃO usar:\n  %s" % (achadas, aviso))


def test_o_aviso_do_upload_ainda_CONSTATA_o_fato():
    """🧪 CONTROLE: tirar a promessa não pode virar silêncio. O cliente
    informou um número e tem que ver que a gente recebeu."""
    limpo = _sem_comentarios(_main())
    assert "informada por você no upload" in limpo, (
        "sumiu o aviso de que a área foi informada — o cliente digita e não "
        "vê sinal nenhum")


def test_o_destino_da_area_informada_vira_aviso_DEPOIS():
    """🔑 O resultado real (usou ou não) tem que chegar ao cliente."""
    limpo = _sem_comentarios(_main())
    assert "preencheu %d item(ns) de piso, forro ou laje" in limpo, (
        "não avisa quando a área informada FOI usada")
    assert "NÃO foi usada nos itens" in limpo, (
        "não avisa quando a área informada NÃO foi usada — que é o caso da "
        "cliente-31 e o que gerou a contradição")


def test_o_aviso_do_destino_LE_o_resultado_real():
    """🪤 Tem que depender de `_n_fill`, o número que a função devolveu — não
    de uma suposição escrita antes."""
    limpo = _sem_comentarios(_main())
    i = limpo.index("preencheu %d item(ns) de piso, forro ou laje")
    trecho = limpo[max(0, i - 700):i]
    assert "if _n_fill:" in trecho, (
        "o aviso do destino não olha o resultado de `_apply_area_honesty`")


def test_CONTROLE_o_aviso_do_destino_so_sai_pra_quem_INFORMOU():
    """Quem não informou área nenhuma não pode receber aviso sobre isso."""
    limpo = _sem_comentarios(_main())
    i = limpo.index("preencheu %d item(ns) de piso, forro ou laje")
    trecho = limpo[max(0, i - 900):i]
    assert 'total_area_source", "")) == "informado"' in trecho, (
        "o aviso do destino sai pra todo mundo, inclusive quem não informou nada")


# ── (2) o aviso de fila ────────────────────────────────────────────────────
def _dashboard():
    return io.open(os.path.join(_RAIZ, "dashboard.html"), encoding="utf-8").read()


def test_a_tela_do_cliente_conta_que_ele_esta_na_FILA():
    """🩸 Os 12 minutos do cliente-19 olhando barra parada.

    🪤 A 1ª versão deste teste procurava `status === 'queued'` e "Na fila" no
    arquivo INTEIRO — e passava mesmo com o conserto desligado, porque a LISTA
    de projetos já tinha um selo "⏳ Na fila" (linha ~4659) e outro trecho já
    comparava com 'queued'. Guarda que acha o que quer em qualquer lugar do
    arquivo não guarda nada. Ancora no `processingStep`, que é a tela onde o
    cliente-19 de fato estava: a do progresso, logo depois do upload.
    """
    js = _sem_comentarios(_dashboard())
    i = js.index("processingStep.textContent = (status")
    trecho = js[i:i + 320]
    assert "'queued'" in trecho, (
        "a tela de PROGRESSO continua sem saber o que é estar na fila")
    assert "Na fila" in trecho, "não escreve nada sobre fila na tela de progresso"


def test_CONTROLE_a_fila_NAO_mostra_contagem_nem_estimativa():
    """🪤 Decisão do Pedro, e medida: contagem vira ansiedade e muda enquanto
    ele olha; tempo seria inventado (mediana 8 min, jobs de hoje 23 e 14)."""
    js = _sem_comentarios(_dashboard())
    i = js.index("status === 'queued'")
    trecho = js[i:i + 400]
    for proibido in ("na frente", "minuto", "posição", "posicao", "fila de "):
        assert proibido not in trecho.lower(), (
            "o aviso de fila voltou a dar número: %r" % proibido)


def test_CONTROLE_quem_NAO_esta_na_fila_ve_o_passo_normal():
    """O conserto não pode engolir o texto de progresso de quem já está
    processando."""
    js = _sem_comentarios(_dashboard())
    i = js.index("status === 'queued'")
    assert "cleanStep" in js[i:i + 400], (
        "quem está processando perdeu o texto do passo atual")
