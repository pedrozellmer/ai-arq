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

import pytest

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
# O bloco que roda DEPOIS, quando `_apply_area_honesty` já devolveu `_n_fill`.
_ANCORA_DESTINO = ('        if str(getattr(project_data, "total_area_source", "")) '
                   '== "informado":')


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


def _aviso_do_destino(n_fill, source="informado", pd=None):
    """EXECUTA o bloco que roda DEPOIS de `_apply_area_honesty` decidir.

    `n_fill` é o que a função devolveu: 0 = não usou a área informada (o caso da
    cliente-31, geometria medida), >0 = usou em N itens.
    """
    pd = pd if pd is not None else _ProjectDataFake(total_area=150.0, total_area_source=source)
    antes = len(list(pd.warnings or []))
    avisos, _ = _rodar(_ANCORA_DESTINO, pd, _n_fill=int(n_fill))
    return avisos[antes:]


# 🔑 ALLOWLIST, não lista negra. O que o upload SABE é um punhado de fatos: a
# pessoa informou um número, e a planta não trazia cota nem quadro de áreas.
# Tudo o mais é destino, e destino só existe ~600 linhas depois.
#
# 🩸 Por que invertemos (06/09): a versão anterior bania 10 substrings
# ("iten", "entra", "vira", "usada", "base"…). Português tem verbo demais pra
# isso — "aplicar", "alimentar", "contar como", "levar pro", "preencher com"
# passavam todas, e o próprio autor registrou o limite. Lista negra perde pra
# paráfrase por construção; allowlist não: quem quiser prometer precisa de uma
# palavra que não está aqui.
_FATOS_DO_UPLOAD = {
    # o que a pessoa fez e o que a planta trouxe — já é fato quando o aviso sai
    "área", "áreas", "total", "informada", "informado", "informou", "você",
    "upload", "planta", "pranchas", "cota", "cotas", "quadro", "medir",
    "medição", "metros", "m", "m²",
    # gramática: ligação, negação, tempo passado/presente. Nada aqui afirma destino.
    "a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos", "das", "em",
    "no", "na", "nos", "nas", "por", "pra", "para", "pelo", "pela", "ao", "à",
    "e", "ou", "que", "com", "sem", "não", "nem", "mas", "ainda", "só",
    "este", "esta", "isso", "seu", "sua", "trazia", "tinha", "havia", "há",
    "é", "era", "está", "estava", "foi",
}


def _palavras(texto):
    import re
    return [p for p in re.findall(r"[a-zà-öø-ÿ²]+", texto.lower()) if p]


def test_o_aviso_do_upload_NAO_promete_que_vai_usar():
    """🩸 A frase que a cliente-31 leu e não se cumpriu.

    🩸 06/09: o guarda anterior bania UMA string exata do `main.py`
    ("entra como BASE pros itens de área"). Mutação que passou verde:
    acrescentar ao mesmo aviso "Ela entra como base dos itens de area." — a
    promessa volta parafraseada e a string banida continua ausente.

    A 2ª versão trocou a string por 10 substrings proibidas, e o cético mostrou
    que a paráfrase continua entrando: "a área que você aplicou", "ela alimenta
    o cálculo", "vamos contar como 150 m²" — nenhuma casa. Agora a régua é
    ALLOWLIST: o aviso do upload só pode usar as palavras dos fatos que já
    aconteceram. Palavra nova = ou é constatação (declare aqui, de propósito)
    ou é promessa feita antes da decisão.
    """
    aviso, _ = _aviso_do_upload()
    intrusas = sorted({p for p in _palavras(aviso) if p not in _FATOS_DO_UPLOAD})
    assert not intrusas, (
        "o aviso do upload usa palavra(s) que não descrevem fato do upload: %s\n"
        "  aviso: %s\n"
        "Ele é escrito ANTES de `_apply_area_honesty` decidir, e no job da "
        "cliente-31 a decisão foi NÃO usar. Se a palavra é mesmo constatação, "
        "acrescente em `_FATOS_DO_UPLOAD` de propósito; se fala do destino da "
        "área, o lugar dela é o aviso de DEPOIS." % (intrusas, aviso))


@pytest.mark.parametrize("area", [150.0, 87.0])
def test_o_aviso_do_upload_ainda_CONSTATA_o_fato(area):
    """🧪 CONTROLE POSITIVO da allowlist: aviso vazio passaria nela sem esforço.

    Tirar a promessa não pode virar silêncio — o cliente digitou um número e
    tem que ver o número DELE de volta (por isso duas áreas: uma frase fixa que
    ignorasse o `_uta` também seria silêncio, disfarçado).
    """
    aviso, pd = _aviso_do_upload(area)
    assert "%.0f m²" % area in aviso, (
        "o aviso não devolve a área que a pessoa informou: %r" % aviso)
    assert "informada por você no upload" in aviso, aviso
    assert pd.total_area == round(area, 2) and pd.total_area_source == "informado"


def test_o_destino_da_area_informada_vira_aviso_DEPOIS():
    """🔑 O resultado real (usou ou não) tem que chegar ao cliente — nos DOIS
    ramos. O da cliente-31 é o `_n_fill == 0`; era ele que faltava."""
    usou = _aviso_do_destino(4)
    assert len(usou) == 1, "o ramo 'usou' não avisou nada: %r" % (usou,)
    assert "preencheu 4 item(ns) de piso, forro ou laje" in usou[0], usou[0]

    nao_usou = _aviso_do_destino(0)
    assert len(nao_usou) == 1, (
        "o ramo 'NÃO usou' ficou mudo — é exatamente o caso da cliente-31: %r"
        % (nao_usou,))
    assert "NÃO foi usada nos itens" in nao_usou[0], nao_usou[0]

    assert usou[0] != nao_usou[0], (
        "os dois desfechos mandam a MESMA frase — o cliente não fica sabendo "
        "qual aconteceu")


@pytest.mark.parametrize("n_fill", [0, 4])
def test_o_aviso_do_upload_nao_e_DESMENTIDO_pelo_aviso_do_destino(n_fill):
    """🔑 Os dois blocos, no MESMO cenário e no mesmo `project_data`.

    O aviso do upload é escrito antes da decisão e é IDÊNTICO nos dois desfechos
    — logo, qualquer coisa que ele afirme sobre o destino está errada em um dos
    dois. Aqui a gente roda os dois e cobra isso: o aviso de cima só constata,
    e é o de baixo que conta o que aconteceu.
    """
    pd = _ProjectDataFake(total_area=0)
    _rodar(_ANCORA_UPLOAD, pd, _uta=150.0)
    de_cima = list(pd.warnings)
    assert len(de_cima) == 1, de_cima
    pd.total_area_source = "informado"
    de_baixo = _aviso_do_destino(n_fill, pd=pd)

    assert len(de_baixo) == 1, (
        "no desfecho _n_fill=%r o cliente ficou sem o aviso do destino, e o "
        "único que sobrou é o do upload — o mesmo silêncio de 02/09" % (n_fill,))
    assert list(pd.warnings) == de_cima + de_baixo
    # o de cima não pode afirmar nada que o de baixo desminta: ele nem fala de destino
    intrusas = sorted({p for p in _palavras(de_cima[0]) if p not in _FATOS_DO_UPLOAD})
    assert not intrusas, (
        "o aviso de cima fala de %s antes da decisão; embaixo, no mesmo job, o "
        "servidor diz: %r" % (intrusas, de_baixo[0]))


def test_o_aviso_do_destino_LE_o_resultado_real():
    """🪤 Tem que depender de `_n_fill`, o número que a função devolveu — não
    de uma suposição escrita antes."""
    limpo = _sem_comentarios(_main())
    i = limpo.index("preencheu %d item(ns) de piso, forro ou laje")
    trecho = limpo[max(0, i - 700):i]
    assert "if _n_fill:" in trecho, (
        "o aviso do destino não olha o resultado de `_apply_area_honesty`")


@pytest.mark.parametrize("n_fill", [0, 4])
def test_CONTROLE_o_aviso_do_destino_so_sai_pra_quem_INFORMOU(n_fill):
    """Quem não informou área nenhuma não pode receber aviso sobre isso —
    e nos DOIS desfechos, que é onde a versão anterior não olhava."""
    saiu = _aviso_do_destino(n_fill, source="")
    assert saiu == [], (
        "quem mediu a própria planta e não informou nada recebeu aviso sobre "
        "área informada: %r" % (saiu,))


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
