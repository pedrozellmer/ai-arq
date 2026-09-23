# -*- coding: utf-8 -*-
"""As três abas do filhote: A definir · Enviado pro cliente · Arquivado.

Pedido do Pedro em 23/09/2026, com as palavras dele:

  *"cria três abas dentro dessa aba filhote: enviado para o cliente, a definir
    e arquivado"*

  *"pra mim arquivado é: a gente fez, ficou ruim, ficou pior do que o original
    e a gente arquivou. Só que o banco consegue ler de fato ainda se a gente
    precisar."*

🔑 ARQUIVAR NÃO GANHOU COLUNA. O estado do filhote já é um histórico de atos no
`error_log` (stage `admin:filhote`): `liberado` e `revogado` moram lá desde
08/08, e a RPC `admin_filhotes` os lê de lá. Arquivar é mais um ato no mesmo
lugar — marca em vez de apagar, guarda QUANDO e POR QUÊ, e desfaz com
`desarquivado`. Exatamente o que ele pediu.

🪤 Antes eram SEIS filtros (Vale liberar · Só estimado · Segurados · Liberados
· Liberados sem aviso · Todos) — seis recortes da mesma pilha, nenhum dizendo
o que já tinha sido DECIDIDO.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _corpo import corpo_de  # noqa: E402
from _jsbancada import fonte_html, funcao_js, motor  # noqa: E402

_ADMIN = "admin.html"


def _js():
    js = motor("null;")
    js.evaljs(funcao_js("_filAba", _ADMIN))
    return js


def _aba(js, **campos):
    return json.loads(js.evaljs(
        "JSON.stringify(_filAba(%s))" % json.dumps(campos)))


# ══════════════════════════════════════════════════════════════════════════
#  A CLASSIFICAÇÃO — função pura, é o que o guarda CHAMA
# ══════════════════════════════════════════════════════════════════════════
def test_filhote_novo_espera_decisao():
    js = _js()
    assert _aba(js, job_id="ev1", liberado=False, ja_liberado=False) == "definir"


def test_filhote_liberado_vai_pra_ENVIADO():
    js = _js()
    assert _aba(js, liberado=True) == "enviado"
    assert _aba(js, ja_liberado=True) == "enviado"


def test_filhote_arquivado_vai_pra_ARQUIVADO():
    js = _js()
    assert _aba(js, arquivado=True) == "arquivado"


def test_ARQUIVADO_vence_liberado():
    """Ordem importa: quem foi arquivado sai da fila, mesmo com histórico."""
    js = _js()
    assert _aba(js, arquivado=True, liberado=True, ja_liberado=True) == "arquivado"


def test_DESARQUIVAR_devolve_pra_fila_de_decisao():
    """🔑 A RPC usa o ato ATUAL, não 'já foi arquivado um dia'. Se usasse
    `max(arquivado_em)`, desarquivar não traria o filhote de volta e o botão
    seria decorativo."""
    js = _js()
    assert _aba(js, arquivado=False, liberado=False) == "definir"


def test_as_tres_abas_cobrem_TODO_filhote():
    """Nenhum pode sumir das três — some da tela é some do trabalho."""
    js = _js()
    casos = [
        {}, {"liberado": False}, {"liberado": True}, {"arquivado": True},
        {"ja_liberado": True}, {"arquivado": True, "liberado": True},
        {"status": "error"}, {"melhorou": False}, {"mediu_menos": True},
    ]
    for c in casos:
        assert _aba(js, **c) in ("definir", "enviado", "arquivado"), c


def test_filhote_nulo_nao_quebra_a_tela():
    js = _js()
    assert json.loads(js.evaljs("JSON.stringify(_filAba(null))")) == "definir"
    assert json.loads(js.evaljs("JSON.stringify(_filAba(undefined))")) == "definir"


# ══════════════════════════════════════════════════════════════════════════
#  A FRASE QUE VIRA O ESTADO — lida pela RPC
# ══════════════════════════════════════════════════════════════════════════
def _frase():
    ns = {"__name__": "arq_ns"}
    exec(compile(corpo_de("frase_do_arquivamento"), "main_slice", "exec"), ns)
    return ns["frase_do_arquivamento"]


frase_do_arquivamento = _frase()


def test_a_frase_COMECA_com_o_ato():
    """🪤 A RPC casa `message ilike 'arquivado%'` — a primeira palavra É o
    estado. Enfeitar o começo (ex.: 'admin arquivou…') quebraria a leitura
    sem quebrar teste nenhum do backend."""
    assert frase_do_arquivamento("ev1", "pai1").startswith("arquivado ")
    assert frase_do_arquivamento("ev1", "pai1", desarquivar=True).startswith("desarquivado ")


def test_desarquivado_NAO_casa_o_padrao_de_arquivado():
    """Os dois convivem no mesmo log; `ilike 'arquivado%'` exige COMEÇAR."""
    d = frase_do_arquivamento("ev1", "pai1", desarquivar=True)
    assert not d.lower().startswith("arquivado"), d


def test_a_frase_leva_os_DOIS_ids():
    f = frase_do_arquivamento("ev123", "pai456")
    assert "ev123" in f and "pai456" in f, f


def test_o_motivo_entra_quando_existe():
    f = frase_do_arquivamento("ev1", "pai1", motivo="mediu menos que o original")
    assert "motivo=mediu menos que o original" in f, f


def test_motivo_vazio_nao_deixa_sujeira():
    for vazio in ("", None, "   ", "\n\t "):
        f = frase_do_arquivamento("ev1", "pai1", motivo=vazio)
        assert "motivo=" not in f, (vazio, f)


def test_motivo_gigante_nao_estoura_o_log():
    f = frase_do_arquivamento("ev1", "pai1", motivo="x" * 900)
    assert len(f) < 300, len(f)


def test_quebra_de_linha_no_motivo_vira_espaco():
    """🪤 A RPC lê UMA linha; `\\n` no meio partiria a mensagem."""
    f = frase_do_arquivamento("ev1", "pai1", motivo="ficou\nruim\tmesmo")
    assert "\n" not in f and "\t" not in f, repr(f)
    assert "ficou ruim mesmo" in f


# ══════════════════════════════════════════════════════════════════════════
#  A TELA — os botões e as abas existem de verdade
# ══════════════════════════════════════════════════════════════════════════
def test_a_tela_tem_as_TRES_abas_e_so_elas():
    src = fonte_html(_ADMIN)
    import re
    abas = re.findall(r'data-fil="([a-z]+)"', src)
    assert abas == ["definir", "enviado", "arquivado"], abas


def test_os_contadores_das_tres_abas_existem_no_HTML():
    """🪤 Guarda que só lê o JS não vê botão que sumiu do HTML."""
    src = fonte_html(_ADMIN)
    for _id in ("fil-definir-n", "fil-enviado-n", "fil-arq-n"):
        assert ('id="%s"' % _id) in src, _id


def test_nao_sobrou_referencia_aos_filtros_ANTIGOS():
    """Contador de botão que não existe mais é código morto."""
    src = fonte_html(_ADMIN)
    for morto in ("fil-vale-n", "fil-est-n", "fil-seg-n", "fil-mudos-n"):
        assert morto not in src, morto


def test_o_card_tem_botao_de_arquivar_E_de_desarquivar():
    src = fonte_html(_ADMIN)
    assert "arquivarFilhote('${f.job_id}', false)" in src, "falta Arquivar"
    assert "arquivarFilhote('${f.job_id}', true)" in src, "falta Desarquivar"


def test_o_botao_diz_que_NAO_apaga():
    """O Pedro pediu explicitamente que desse pra recuperar."""
    src = fonte_html(_ADMIN)
    i = src.index("arquivarFilhote('${f.job_id}', false)")
    trecho = src[max(0, i - 400):i + 200].lower()
    assert "apaga" in trecho, "o title do botão tem que dizer que não apaga"


def test_a_rota_existe_no_backend():
    fonte = corpo_de("admin_arquivar_filhote")
    assert "desarquivar" in fonte
    assert "is_eval" in fonte, "tem que recusar job que não é filhote"
    assert "409" in fonte, "tem que recusar arquivar filhote já liberado"


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLES
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_sem_o_campo_arquivado_tudo_cairia_em_definir():
    """Prova que a aba Arquivado depende do campo novo da RPC."""
    js = _js()
    assert _aba(js, liberado=False) == "definir"
    assert _aba(js, arquivado=True) == "arquivado", (
        "o controle parou de provar: sem ler `arquivado` não há 3ª aba")


def test_CONTROLE_uma_frase_que_nao_comeca_com_o_ato_seria_lida_como_LIBERADO():
    """🩸 A RPC faz `else 'liberado'`: frase que não casa vira LIBERADO.
    Arquivar um filhote e ele aparecer como enviado pro cliente é o pior
    resultado possível."""
    ruim = "filhote ev1 foi arquivado pelo admin"
    assert not ruim.lower().startswith(("arquivado", "desarquivado", "revogado"))
    boa = frase_do_arquivamento("ev1", "pai1")
    assert boa.lower().startswith("arquivado"), boa
