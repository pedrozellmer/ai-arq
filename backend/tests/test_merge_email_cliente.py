# -*- coding: utf-8 -*-
"""Como o merge chega no cliente — e por que não pode usar o e-mail do filhote.

Pedro, 24/08/2026: *"e como esse merge aparecia pro cliente? vai um email
automático tb pra ele explicando? acho que vale hein"*.

Vale, e o e-mail tinha que ser OUTRO. O do filhote diz "melhoramos o motor e
REFIZEMOS a leitura do seu projeto". Num merge isso é falso: a gente não releu
nada — juntou, prancha por prancha, o melhor de duas leituras que já existiam.
Mandar o texto errado ensina o cliente a desconfiar do que a gente escreve.

A pergunta que um orçamentista faz no segundo em que ouve "juntamos duas
planilhas" é *"então está contado em dobro?"*. O e-mail responde isso antes de
ele perguntar.
"""
import html as _hu
import io
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from _corpo import corpo_de, ENVIO_E_BUILDER  # noqa: E402
import _merge_bancada as _mb  # noqa: E402
import main as _m  # noqa: E402


def _main():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _corpo(nome, tam=12000):
    """🪤 A 1ª versão disto cortava no próximo `@app.` e engolia a função
    SEGUINTE inteira — dois testes mediram o corpo errado e um deles passou
    verde por causa de texto que nem era da função em teste.

    O fim de uma função é o próximo `def` na coluna zero, não o próximo
    decorador."""
    src = _main()
    i = src.index("def " + nome)
    nl = chr(10)
    marcas = [src.find(m, i + 10)
              for m in (nl + "def ", nl + "@app.", nl + "async def ")]
    marcas = [m for m in marcas if m > 0]
    corpo = src[i:min(marcas) if marcas else i + tam]
    # 05/09: o e-mail virou envio + builder (ver ENVIO_E_BUILDER em _corpo.py) —
    # o texto que o cliente lê mora no builder; medir só o envio é meia leitura.
    _b = ENVIO_E_BUILDER.get(nome)
    if _b and ("def " + _b) in src:
        corpo += _corpo(_b, tam)
    return corpo


def _sem_comentarios(src):
    _NL = chr(10)
    return _NL.join(l for l in src.splitlines() if not l.strip().startswith("#"))


def _so_o_que_o_cliente_le(nome):
    """🪤 Dois enganos que este arquivo cometeu antes de acertar:

    1. o guarda lia a DOCSTRING, onde eu cito a frase errada exatamente pra
       explicar por que ela não pode aparecer. Um guarda assim ou dá alarme
       falso, ou me faz apagar a documentação pra calar o alarme;
    2. o guarda procurava uma frase inteira que, no código, está QUEBRADA em
       duas linhas — e acusava falta do que estava lá.

    3. (31/08) o guarda lia o COMENTÁRIO. Eu documentei um bug do teto semanal
       citando a frase "refizemos a leitura" pra explicar o estrago, e o teste
       acusou o e-mail do merge de dizer o que ele não diz. É o engano nº1 de
       novo, em outra roupa — e é o erro assinatura desta casa: ler comentário
       como código.

    🪤 NÃO dá pra cortar todo "#": o HTML do e-mail é cheio de cor (#FFFBEB).
    Só sai a linha cujo primeiro caractere não-branco é "#" — que é como os
    comentários deste arquivo são escritos.

    Aqui saem a docstring e os comentários; o espaço em branco vira simples."""
    corpo = _corpo(nome)
    aspas = corpo.find('"""')
    if aspas > 0:
        fim = corpo.find('"""', aspas + 3)
        if fim > 0:
            corpo = corpo[:aspas] + corpo[fim + 3:]
    linhas = [ln for ln in corpo.splitlines() if not ln.lstrip().startswith("#")]
    return " ".join(" ".join(linhas).split())


# ══════════════════════════════════════════════════════════════════════════
#  🧪 A BANCADA QUE EXECUTA (06/09/2026)
# ══════════════════════════════════════════════════════════════════════════
#
# 🩸 Nove guardas deste arquivo passavam com o defeito ABERTO. Prova: no envio,
# troquei `_build_leitura_combinada_email(...)` por `_build_leitura_nova_email(
# nome, proj, merge_job, antes, depois)`. O cliente do merge passa a receber
# literalmente "Refizemos a leitura do seu projeto" — a mentira que este arquivo
# inteiro existe pra impedir — e os 38 testes ficaram VERDES, porque o fonte do
# builder da combinada continua lá: intacto, correto e nunca chamado.
#
# 🔑 Guarda que lê fonte prova que o TEXTO existe. Só executar prova que ele
# CHEGA no cliente. Daqui pra baixo a função real é chamada, com o banco e o
# SMTP na mão, e o guarda confere a SAÍDA: o HTML que sairia, a linha que seria
# gravada, o e-mail que seria escolhido.

# O placar do caso cliente-19 (24/08): +87 medidos no total e, ao mesmo tempo,
# a prancha de elétrica CAINDO de 30 pra 12 — é o que faz o corpo do e-mail
# passar por todos os blocos (ganho, o que piorou, procedência, sobreposição).
_ANTES = {"medidos": 92, "itens": 147, "pranchas": 4,
          "por_prancha": {"4366-EL-E": {"itens": 40, "medidos": 30}}}
_DEPOIS = {"medidos": 179, "itens": 263, "pranchas": 7,
           "por_prancha": {"4366-EL-E": {"itens": 38, "medidos": 12}}}
_AVISOS_DO_COMBINADO = [
    "Esta planilha junta as DUAS leituras do seu projeto, prancha por prancha "
    "— ficou com a versão mais completa de cada uma. Nenhuma prancha entrou "
    "duas vezes.",
    "⚠ CONFERIR ANTES DE SOMAR: 2 código(s) aparecem em mais de uma prancha.",
]

# O que `_email_wrap` põe no HTML e o `<div>` cru NÃO tem. As duas últimas são
# o rodapé de LGPD (regra dura nº6) — o custo real de 24/08, quando TRÊS
# clientes receberam o e-mail sem ele.
_MARCAS_DA_MOLDURA = (
    "https://ai.arq.br/email-logo.png",
    "linear-gradient(90deg,#4F46E5,#22D3EE)",
    "https://ai.arq.br/privacidade.html",
    "Para remover seus dados, é só responder este e-mail.",
)
_PREHEADER = '<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">'


class _Req:
    """O pedaço de `Request` que estas rotas realmente leem."""

    def __init__(self, **qp):
        self.query_params = dict(qp)
        self.headers = {"user-agent": "pytest"}


class _ThreadNaHora:
    """O envio do e-mail vai em thread desde 23/08 (o SMTP síncrono segurava a
    resposta e o navegador via erro de rede). Aqui roda na hora — senão o guarda
    mede antes de a coisa acontecer e dá verde por corrida."""

    def __init__(self, target=None, daemon=None, args=(), kwargs=None, **_kw):
        self._t, self._a, self._k = target, args, kwargs or {}

    def start(self):
        self._t(*self._a, **self._k)

    def join(self, *a, **k):
        pass


# 🪤 07/09 (cético): aqui moravam `_intercepta_o_smtp` e `_monta_o_email`, que
# chamavam o BUILDER direto. Os dois foram apagados junto com os guardas que os
# usavam: builder certo com envio que ignora o builder é exatamente o defeito
# que esta bancada existe pra pegar, e helper que atalha o envio convida o
# próximo guarda a nascer cego. Quem quer o e-mail agora usa `_email_que_saiu`,
# que passa pela ROTA e lê o que saiu pelo `_send_email_smtp`.


# ══════════════════════════════════════════════════════════════════════════
#  O e-mail como o CLIENTE lê — e saindo pela porta do SMTP
# ══════════════════════════════════════════════════════════════════════════
def _texto_do_email(html):
    """O HTML virando o texto que o cliente lê: sem tag, sem entidade.

    🪤 07/09 (cético): a peneira era substring literal no HTML. 'refizemos a
    leitura' com uma tag ou uma entidade no meio passava batido — e o corpo
    destes e-mails é feito exatamente disso (`<b>`, `&ecirc;`, `&atilde;`).
    Procurar no HTML é procurar na marcação; o cliente lê o texto."""
    t = re.sub(r"<[^>]+>", " ", html or "")
    t = _hu.unescape(t).replace(chr(0x200C), " ").replace(chr(0xA0), " ")
    return " ".join(t.split()).lower()


def _preheader_do(html):
    """O TEXTO do preheader — não a presença da `<div>` que o carrega.

    🪤 Preheader vazio-mas-presente passa em qualquer guarda de presença, e é
    justamente ele que some quando alguém mexe no builder."""
    i = (html or "").find(_PREHEADER)
    if i < 0:
        return None
    j = html.index("</div>", i)
    return _texto_do_email(html[i + len(_PREHEADER):j])


def _badge_do(html):
    """O TEXTO do selo colorido do topo (🧩 Combinada / ✓ Atualizado)."""
    marca = 'padding:4px 10px;border-radius:20px;">'
    i = (html or "").find(marca)
    if i < 0:
        return None
    j = html.index("</span>", i)
    return _texto_do_email(html[i + len(marca):j])


_PAI_ID = "aa11bb22"
_PAI_EMAIL = "cliente-01@example.com"


def _banco_de_liberacao(job_filho):
    """Original + filhote prontos pro Liberar, com o placar do caso cliente-19:
    +87 medidos no total e a prancha de elétrica CAINDO de 30 pra 12 (é o que
    faz o corpo do e-mail passar por todos os blocos)."""
    projetos = {
        _PAI_ID: {"job_id": _PAI_ID, "user_id": "u-cliente-01",
                  "user_email": _PAI_EMAIL, "user_name": "Cliente Um",
                  "project_name": "Obra do cliente-01", "status": "done",
                  "typology": "office", "project_type": "arquitetura",
                  "created_at": "2026-08-20T19:37:48+00", "warnings": []},
        job_filho: {"job_id": job_filho, "parent_job_id": _PAI_ID, "is_eval": True,
                    "status": "done", "user_id": "eval",
                    "project_name": "[TESTE] Obra do cliente-01 — avaliação",
                    "created_at": "2026-08-24T19:37:48+00",
                    "warnings": list(_AVISOS_DO_COMBINADO)},
    }
    itens = {
        _PAI_ID: (_mb.itens("4366-EL-E", 40, 30, rotulo="orig")
                  + _mb.itens("ARQ-01", 107, 62, rotulo="orig")),
        job_filho: (_mb.itens("4366-EL-E", 38, 12, rotulo="rel")
                    + _mb.itens("ARQ-01", 225, 167, rotulo="rel")),
    }
    return _mb.Banco(projetos, itens)


def _email_que_saiu(monkeypatch, job_filho):
    """Roda `admin_liberar_filhote` DE VERDADE e devolve o e-mail que passou
    pela ÚNICA porta de saída da casa (`_send_email_smtp`).

    🔑 É a diferença entre "o builder monta certo" e "o cliente recebe certo".
    Trocar o builder no envio deixa o fonte do builder certo intacto — e foi
    assim que nove guardas deste arquivo ficaram verdes com a mentira no ar."""
    b = _banco_de_liberacao(job_filho)
    _mb.instalar(monkeypatch, b)
    _m.admin_liberar_filhote(job_filho, _mb.Req())
    assert len(b.emails) == 1, (
        "o Liberar de %s não mandou exatamente um e-mail: %r"
        % (job_filho, [e["tipo"] for e in b.emails]))
    return b.emails[0]


def _liberar_de_verdade(monkeypatch, job_filho, medidos_depois=3):
    """Roda `admin_liberar_filhote` DE VERDADE, com o banco na mão.

    Devolve (resposta, patches_gravados, emails_escolhidos). O `patches` é o que
    iria pro PATCH em `projects`; o `emails` é qual dos dois builders foi
    chamado, com os argumentos.

    🪤 Nada de patchar `_supa_rest_service` e achar que cobriu: esta rota lê
    `projects` por `_supa_rows` e `project_items`/`item_reviews` pelo
    `_supa_rest_service`. Faltar um dos dois derruba a rota em 404/502 e o
    guarda mede o erro, não o comportamento.
    """
    import threading as _thr

    PAI = _PAI_ID
    projetos = {
        PAI: {"job_id": PAI, "user_id": "u-cliente-01",
              "user_email": "cliente-01@example.com", "user_name": "Cliente Um",
              "project_name": "Obra do cliente-01"},
        job_filho: {"job_id": job_filho, "parent_job_id": PAI, "is_eval": True,
                    "status": "done", "user_id": "eval", "warnings": [],
                    "project_name": "[TESTE] Obra do cliente-01 — avaliação"},
    }
    itens = {
        PAI: [{"confidence": "confirmado", "ref_sheet": "ARQ-01"},
              {"confidence": "estimado", "ref_sheet": "ARQ-01"}],
        job_filho: ([{"confidence": "confirmado", "ref_sheet": "ARQ-01"}]
                    * medidos_depois
                    + [{"confidence": "estimado", "ref_sheet": "EL-02"}]),
    }
    patches, emails = [], []

    def _rows(method, path, **kw):
        params = kw.get("params") or {}
        jid = str(params.get("job_id", "")).replace("eq.", "")
        if path == "projects" and jid in projetos:
            return [dict(projetos[jid])]
        return []

    def _svc(method, path, body=None, params=None, **kw):
        params = params or {}
        jid = str(params.get("job_id", "")).replace("eq.", "")
        if method == "GET" and path == "project_items":
            return 200, [dict(x) for x in itens.get(jid, [])]
        if method == "GET" and path == "item_reviews":
            return 200, []
        if method == "PATCH" and path == "projects":
            patches.append({"job": jid, "body": dict(body or {})})
            return 200, []
        return 200, []

    monkeypatch.setattr(_m, "_require_admin", lambda r: None)
    monkeypatch.setattr(_m, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(_m, "_supa_rows", _rows)
    monkeypatch.setattr(_m, "_supa_rest_service", _svc)
    monkeypatch.setattr(_m, "_email_auto_recente", lambda *a, **k: False)
    monkeypatch.setattr(_m, "_email_leitura_combinada",
                        lambda *a: emails.append({"qual": "combinada", "args": a}) or True)
    monkeypatch.setattr(_m, "_email_leitura_nova",
                        lambda *a: emails.append({"qual": "releitura", "args": a}) or True)
    monkeypatch.setattr(_thr, "Thread", _ThreadNaHora)

    resp = _m.admin_liberar_filhote(job_filho, _Req())
    return resp, patches, emails

# ══════════════════════════════════════════════════════════════════════════
#  O e-mail certo pra cada caso
# ══════════════════════════════════════════════════════════════════════════
def test_existe_um_email_proprio_pro_merge():
    assert "def _email_leitura_combinada" in _main()


def test_o_email_do_merge_NAO_diz_que_refizemos_a_leitura(monkeypatch):
    """A frase do filhote seria mentira aqui — a gente não releu nada.

    🩸 06/09: a versão anterior deste guarda lia o FONTE de
    `_email_leitura_combinada`. Trocando, no envio, o builder da combinada pelo
    da releitura, o cliente do merge recebia literalmente "Refizemos a leitura
    do seu projeto" e o guarda continuava verde — o fonte que ele lia estava
    intacto e nunca era chamado.

    🪤 07/09 (cético): a versão seguinte chamava `_email_leitura_combinada`
    DIRETO. Nunca passava pela ROTA que ESCOLHE entre os dois e-mails (o
    ternário do `_e_merge`, em `admin_liberar_filhote`) — que é onde a mentira
    de 24/08 nasce. O arquivo inteiro ficava verde com a rota mandando o
    e-mail da releitura pro merge. E a peneira era substring no HTML: qualquer
    tag no meio da frase escapava. Agora a ROTA é chamada e a busca é no texto
    que o cliente lê."""
    saiu = _email_que_saiu(monkeypatch, "mg634d18")
    texto = _texto_do_email(saiu["html"])
    assert "refizemos a leitura" not in texto, (
        "o cliente do MERGE recebeu o texto da releitura — a gente não releu "
        "nada, juntou duas leituras que já existiam")
    assert "refizemos a leitura" not in saiu["assunto"].lower()
    assert "melhoramos o motor" not in texto
    # 🧪 controle positivo: é o e-mail da COMBINADA que saiu, não um vazio
    assert "versão combinada" in texto
    assert "nenhuma prancha entrou duas vezes" in texto
    assert saiu["tipo"] == "leitura_combinada"
    assert saiu["para"] == _PAI_EMAIL, (
        "o e-mail do merge foi pra %r — o dono vem do PAI, nunca do filhote"
        % saiu["para"])


def test_CONTROLE_a_peneira_ACHA_a_frase_quando_ela_esta_la(monkeypatch):
    """🧪 O outro lado do guarda acima, e sem ele aquele é vácuo: a mesma ROTA,
    com um job de RELEITURA, tem que entregar a frase — se a peneira parasse de
    achar 'refizemos a leitura' em lugar nenhum, o guarda do merge passaria
    para sempre, inclusive com a mentira no ar."""
    saiu = _email_que_saiu(monkeypatch, "ev597afa")
    texto = _texto_do_email(saiu["html"])
    assert "refizemos a leitura do seu projeto" in texto, (
        "a peneira não acha a frase nem no e-mail que a diz — o guarda do "
        "merge virou vácuo. Saiu: %r" % texto[:300])
    assert saiu["tipo"] == "leitura_nova"


def test_o_email_do_merge_explica_o_que_e():
    corpo = _corpo("_email_leitura_combinada")
    assert "duas vezes" in corpo
    assert "combinada" in corpo


def test_o_email_responde_a_pergunta_da_dobra_sem_ser_perguntado():
    """🚨 'Juntaram duas planilhas' faz qualquer orçamentista pensar em dobra.
    Se o e-mail não responde, ele desconfia da planilha inteira."""
    corpo = _corpo("_email_leitura_combinada")
    assert "Nenhuma prancha entrou duas vezes" in corpo


def test_o_email_diz_onde_conferir_a_procedencia_linha_a_linha():
    corpo = _so_o_que_o_cliente_le("_email_leitura_combinada")
    assert "de qual leitura ela veio" in corpo


def test_o_email_carrega_o_aviso_de_sobreposicao_quando_existe():
    """O merge APONTA código repetido em duas pranchas; o cliente tem que ver
    isso no e-mail, não só se abrir a planilha."""
    corpo = _corpo("_email_leitura_combinada")
    assert "CONFERIR ANTES DE SOMAR" in corpo


def test_o_aviso_de_sobreposicao_so_sai_quando_ha_sobreposicao():
    """Controle negativo — alarme que sai sempre vira ruído ignorado.

    🪤 A 1ª versão deste guarda checava `sobre_html = ""`, o NOME de uma
    variável. Reescrevi o e-mail montando o bloco inline e o teste quebrou sem
    que nada de comportamento mudasse. Guarda tem que medir a condição, não a
    forma de escrever."""
    corpo = _corpo("_email_leitura_combinada")
    # 🪤 25/08 (auditoria): a versao anterior era TAUTOLOGICA — `i_cond < i_texto
    # or corpo.index("_sobre = next(") < i_cond`. A 1a clausula ja era FALSA
    # (o texto procurado esta na BUSCA, la em cima; a condicao vem depois) e a 2a
    # e sempre verdadeira, porque em Python a variavel tem que ser definida antes
    # de usada. O guarda nao garantia nada.
    #
    # O que importa e outra coisa: o que VAI PRO E-MAIL (`_hc.escape(_sobre)`)
    # tem que estar debaixo do `if _sobre:`. Sem alarme, nada e mostrado.
    i_cond = corpo.index("if _sobre:")
    i_render = corpo.index("_hc.escape(_sobre)")
    assert i_cond < i_render, (
        "o quadro de sobreposicao e montado fora da condicao — sairia sempre, "
        "inclusive em projeto sem sobreposicao nenhuma")


def test_o_email_reusa_o_aviso_ja_gravado_em_vez_de_recalcular():
    """Recalcular a mesma coisa em dois lugares é um lugar a mais pra divergir."""
    corpo = _corpo("_email_leitura_combinada")
    assert 'filho.get("warnings")' in corpo


def test_o_email_diz_que_a_versao_dele_continua():
    """Regra dura nº7: nunca dar a entender que a nova substitui a dele."""
    corpo = _corpo("_email_leitura_combinada")
    assert "continua no painel" in corpo


# ══════════════════════════════════════════════════════════════════════════
#  O Liberar tem que saber distinguir merge de releitura
# ══════════════════════════════════════════════════════════════════════════
def test_o_liberar_reconhece_o_merge_pelo_prefixo():
    corpo = _corpo("admin_liberar_filhote", tam=9000)
    assert '_e_merge = str(eval_job_id).startswith("mg")' in corpo


def test_o_merge_ganha_nome_proprio_no_painel_do_cliente():
    """Chamar merge de 'nova leitura (motor atualizado)' seria mentir no título."""
    corpo = _corpo("admin_liberar_filhote", tam=9000)
    assert "versão combinada (o melhor das duas leituras)" in corpo


# 🪤 07/09 (cético): a versão anterior deste guarda usava UM job_id fixo
# ('mg634d18') e só registrava QUAL builder foi chamado. Dois furos com a mesma
# causa: nada amarrava o prefixo a mais de um id (bastava `startswith("mg6")`
# pra ele continuar verde e todo merge de verdade descer a rota errada), e nada
# olhava os ARGUMENTOS além do job. Trocar `pai` por `filho` na chamada manda o
# e-mail pro endereço errado — que num filhote é vazio, ou seja, ninguém recebe.
_IDS_DE_LIBERACAO = [
    # formato real do gerador: "mg" + 6 hex de uuid4
    ("mg74fa5d", "combinada"),
    ("mg0a1b2c", "combinada"),
    ("mgff00aa", "combinada"),
    ("ev597afa", "releitura"),
    ("ev1c03c1", "releitura"),
]


@pytest.mark.parametrize("job,qual", _IDS_DE_LIBERACAO)
def test_o_liberar_escolhe_o_email_certo(monkeypatch, job, qual):
    """O e-mail do filhote diz "refizemos a leitura". Num merge isso é falso —
    e quem escolhe entre os dois é o `_e_merge` desta rota."""
    _resp, patches, emails = _liberar_de_verdade(monkeypatch, job)
    assert len(emails) == 1, "o Liberar de %s não avisou o cliente: %r" % (job, emails)
    assert emails[0]["qual"] == qual, (
        "o job %s desceu pela rota da %s" % (job, emails[0]["qual"]))

    args = emails[0]["args"]
    assert args[0]["job_id"] == _PAI_ID, (
        "quem recebe o e-mail tem que vir do PAI (o filhote não tem e-mail); "
        "chegou %r" % (args[0].get("job_id"),))
    if qual == "combinada":
        assert args[1]["job_id"] == job, (
            "os avisos da planilha combinada vêm do FILHO; chegou %r"
            % (args[1].get("job_id"),))
        assert args[2] == job, "o CTA apontaria pro projeto %r" % (args[2],)
        antes, depois = args[3], args[4]
    else:
        assert args[1] == job, "o CTA apontaria pro projeto %r" % (args[1],)
        antes, depois = args[2], args[3]
    assert (antes["medidos"], depois["medidos"]) == (1, 3), (
        "o placar que vai no e-mail não é o dos dois lados: %r → %r"
        % (antes, depois))

    nome = patches[-1]["body"]["project_name"]
    esperado = (" — versão combinada (o melhor das duas leituras)"
                if qual == "combinada" else " — nova leitura (motor atualizado)")
    assert nome.endswith(esperado), (
        "o job %s chegou ao painel do cliente como %r" % (job, nome))


def test_revogar_devolve_o_nome_de_teste_certo():
    """🪤 Em 23/08 o revogar gravava de volta o nome JÁ renomeado e o job ficava
    marcado como liberado mesmo depois de recolhido. Agora tem que funcionar
    pros DOIS sufixos."""
    corpo = _corpo("admin_liberar_filhote", tam=9000)
    assert "_nome_filho.endswith(_SUFIXO)" in corpo
    assert '" — combinada" if _e_merge else " — avaliação"' in corpo


# ══════════════════════════════════════════════════════════════════════════
#  Cada linha da planilha combinada diz de qual leitura veio
# ══════════════════════════════════════════════════════════════════════════
def test_a_linha_do_merge_carrega_a_leitura_de_origem():
    """Pedro, 24/08: "sempre coloca a fonte na planilha". Numa planilha
    COMBINADA a fonte tem uma camada a mais: de QUAL leitura a linha veio."""
    corpo = _corpo("admin_merge_criar", tam=12000)
    assert '"Veio da " + _sel' in corpo
    assert "_merge_data_curta" in corpo


def test_o_carimbo_de_leitura_nao_apaga_a_observacao_que_ja_existia():
    """A observação carrega a Fonte: da medição — perder isso seria trocar uma
    procedência por outra."""
    corpo = _corpo("admin_merge_criar", tam=12000)
    assert '(_obs + " | " if _obs else "")' in corpo


def test_data_ruim_nao_vira_carimbo_errado():
    """Melhor sem carimbo do que com data errada."""
    corpo = _corpo("_merge_data_curta", tam=1200)
    assert "return None" in corpo
    assert "except Exception" in corpo


# ══════════════════════════════════════════════════════════════════════════
#  ⏱️ O 1º uso real: o estudo parecia travado
# ══════════════════════════════════════════════════════════════════════════
#
# 24/08, Pedro clicando pela 1ª vez: *"não fez nada, ele tá rolando a página pra
# baixo e não fazendo nada"*. O backend TINHA respondido — a juíza rodou, está
# no log llm:cache. Três defeitos empilhados:
#
#   1. as juízas rodavam UMA DEPOIS DA OUTRA: ~21 s só de IA (4 pranchas),
#      mais carregar 410 itens — na borda dos 45 s que o authFetch corta;
#   2. a rota não estava na lista de "rotas lentas" do authFetch, então herdava
#      o teto de 45 s em vez dos 180 s;
#   3. a caixa de espera não tinha cronômetro, então "está pensando" e "morreu"
#      eram a MESMA tela — ele esperou, achou que tinha morrido, clicou de novo
#      (o log mostra os dois cliques, com 30 s de intervalo).


def test_as_juizas_rodam_em_paralelo():
    src = _main()
    i = src.index("def _merge_montar")
    j = src.index("@app.get(\"/api/admin/merge-preview", i)
    montar = src[i:j]
    assert "ThreadPoolExecutor" in montar, (
        "as juízas voltaram a rodar em sequência — o tempo vira a SOMA das "
        "pranchas em vez da mais lenta")
    assert "_ex.map(" in montar


# As quatro pranchas da disputa. 🪤 07/09 (cético): a bancada anterior tinha 4
# pranchas com EXATAMENTE 1 item confirmado cada — empatadas em `medidos` e em
# `itens`. Como o sort do Python é estável, qualquer reordenação por métrica era
# um no-op naquele fixture. Aqui cada prancha tem contagem própria, e os nomes
# estão fora da ordem alfabética de propósito.
_DISPUTA = {                    # (itens_pai, medidos_pai, itens_filho, medidos_filho)
    "ZZ-COBERTURA": (3, 1, 9, 7),
    "AA-TERREO": (20, 15, 5, 2),
    "MM-ELETRICA": (12, 8, 12, 9),
    "BB-HIDRAULICA": (7, 3, 8, 3),
}
# O veredito da juíza, um DIFERENTE por prancha — é o que permite dizer se ele
# chegou na prancha certa. Em três delas ela CONTRARIA a contagem (que daria
# filho, pai, filho, filho); na MM-ELETRICA ela concorda.
_VEREDITO = {"ZZ-COBERTURA": "pai", "AA-TERREO": "filho",
             "MM-ELETRICA": "filho", "BB-HIDRAULICA": "pai"}
_CONTAGEM = {"ZZ-COBERTURA": "filho", "AA-TERREO": "pai",
             "MM-ELETRICA": "filho", "BB-HIDRAULICA": "filho"}


def _banco_da_disputa():
    projetos = {
        _PAI_ID: {"job_id": _PAI_ID, "user_id": "u-cliente-01",
                  "user_email": _PAI_EMAIL, "user_name": "Cliente Um",
                  "project_name": "Obra do cliente-01", "status": "done",
                  "typology": "office", "project_type": "arquitetura",
                  "created_at": "2026-08-20T19:37:48+00", "warnings": []},
        "ev597afa": {"job_id": "ev597afa", "parent_job_id": _PAI_ID, "is_eval": True,
                     "status": "done", "user_id": "eval", "warnings": [],
                     "project_name": "[TESTE] Obra do cliente-01 — avaliação",
                     "created_at": "2026-08-24T19:37:48+00"},
    }
    ip, if_ = [], []
    for prancha, (ia, ma, if_n, mf) in _DISPUTA.items():
        ip += _mb.itens(prancha, ia, ma, rotulo="orig")
        if_ += _mb.itens(prancha, if_n, mf, rotulo="rel")
    return _mb.Banco(projetos, {_PAI_ID: ip, "ev597afa": if_})


def test_o_paralelo_preserva_a_ordem_das_pranchas(monkeypatch):
    """🪤 `executor.map` devolve na ordem da entrada; um `as_completed` embaralharia
    e o veredito iria pra a prancha errada — o pior tipo de bug, porque a tela
    continuaria bonita.

    🪤 07/09 (cético): o guarda anterior lia `zip(_disputadas, _vs)` no fonte, e
    a bancada de antes empatava as quatro pranchas em tudo — reordenar não
    mudava nada. Aqui cada prancha tem número próprio, a juíza carimba o NOME
    da prancha que leu, e o guarda cobra o veredito de cada uma no lugar dela.
    """
    b = _banco_da_disputa()

    def _juiza(prancha, ip, if_):
        return {"lado": _VEREDITO[prancha], "motivo": "juíza leu %s" % prancha}
    chamadas = _mb.instalar(monkeypatch, b, juiza=_juiza)

    _pai, _filho, ip, if_, plano, _rev = _m._merge_montar("ev597afa", com_juiza=True)

    # 1. a juíza leu as QUATRO, cada uma uma vez
    assert sorted(c["prancha"] for c in chamadas) == sorted(_DISPUTA), (
        "a juíza não leu as quatro pranchas disputadas: %r"
        % [c["prancha"] for c in chamadas])

    # 2. e recebeu as DUAS listas certas — mandar a do pai duas vezes daria um
    #    veredito plausível e sempre a favor de um lado só.
    for c in chamadas:
        assert len(c["pai"]) == len(ip) and len(c["filho"]) == len(if_), (
            "a juíza de %s recebeu %d/%d linhas, não %d/%d"
            % (c["prancha"], len(c["pai"]), len(c["filho"]), len(ip), len(if_)))
        assert all("orig" in str(x.get("description")) for x in c["pai"]), (
            "a juíza de %s recebeu a leitura errada como 'pai'" % c["prancha"])
        assert all("rel" in str(x.get("description")) for x in c["filho"]), (
            "a juíza de %s recebeu a leitura errada como 'filho'" % c["prancha"])

    # 3. o veredito de cada prancha ficou NA prancha dela
    for p in plano["pranchas"]:
        nome = p["prancha"]
        assert p["motivo"] == "juíza leu %s" % nome, (
            "a prancha %s ficou com o veredito de OUTRA: %r — a planilha do "
            "cliente sai montada com o lado errado" % (nome, p["motivo"]))
        assert p["lado"] == _VEREDITO[nome], (
            "%s ficou com o lado %r, a juíza escolheu %r"
            % (nome, p["lado"], _VEREDITO[nome]))
        assert p["discordam"] is (_VEREDITO[nome] != _CONTAGEM[nome]), (
            "%s: 'a juíza discordou da contagem?' saiu %r" % (nome, p["discordam"]))

    # 4. e o placar do plano é a soma dos lados ESCOLHIDOS (28 itens, 15 medidos)
    esperado_itens = sum(_DISPUTA[n][0] if _VEREDITO[n] == "pai" else _DISPUTA[n][2]
                         for n in _DISPUTA)
    esperado_med = sum(_DISPUTA[n][1] if _VEREDITO[n] == "pai" else _DISPUTA[n][3]
                       for n in _DISPUTA)
    assert (plano["total_itens"], plano["total_medidos"]) == (esperado_itens,
                                                              esperado_med), (
        "o placar do plano (%s/%s) não bate com os lados escolhidos (%s/%s)"
        % (plano["total_itens"], plano["total_medidos"], esperado_itens, esperado_med))


def test_o_teto_de_tempo_da_tela_e_explicito():
    import io as _io
    import os as _os
    admin = _io.open(_os.path.join(_os.path.dirname(_BACKEND), "admin.html"),
                     encoding="utf-8").read()
    i = admin.index("/api/admin/merge-preview/")
    assert "timeoutMs: 180000" in admin[i:i + 300], (
        "a rota do estudo voltou a herdar o teto de 45 s do authFetch")
    j = admin.index("/api/admin/merge-criar/")
    assert "timeoutMs: 180000" in admin[j:j + 300]


def test_a_caixa_de_espera_mostra_o_tempo():
    """Sem cronômetro, esperar e travar são indistinguíveis pra quem olha."""
    import io as _io
    import os as _os
    admin = _io.open(_os.path.join(_os.path.dirname(_BACKEND), "admin.html"),
                     encoding="utf-8").read()
    assert 'id="merge-cron"' in admin
    assert "clearInterval(_cron)" in admin


def test_montar_a_tela_esta_dentro_de_try():
    """🚨 Era o que matava tudo em silêncio: erro ao desenhar não era pego, a
    função morria e a caixa 'Lendo...' ficava pra sempre."""
    import io as _io
    import os as _os
    admin = _io.open(_os.path.join(_os.path.dirname(_BACKEND), "admin.html"),
                     encoding="utf-8").read()
    i = admin.index("_mergeUltimo = d;")
    trecho = admin[i:i + 1400]
    i_try = trecho.index("try {")
    i_html = trecho.index("mergeHtml(d, jobId)")
    assert i_try < i_html, "a montagem da tela voltou a ficar fora do try"
    assert "falhei ao desenhar a tela" in trecho
    assert "JSON.stringify(d" in trecho, (
        "sem o resultado cru na tela, o próximo erro me faz adivinhar de novo")


# ══════════════════════════════════════════════════════════════════════════
#  🚨 Duas linhas do MESMO projeto, o mesmo botao azul
# ══════════════════════════════════════════════════════════════════════════
#
# 24/08, depois que o merge do cliente-19 nasceu: a aba Filhotes passou a ter DUAS
# linhas do projeto dele — a releitura (ev597afa, 92→151) e a combinada
# (mg634d18, 92→179). As duas "concluído", as duas marcadas "melhorou", as duas
# com o mesmo botao azul "Liberar pro cliente".
#
# Clicar na errada entrega ao cliente a versao que PERDE as 38 portas dele. E o
# clique errado manda e-mail: nao da pra desfazer o que ele leu.
def _admin():
    import io as _io
    import os as _os
    return _io.open(_os.path.join(_os.path.dirname(_BACKEND), "admin.html"),
                    encoding="utf-8").read()


def test_a_linha_da_combinada_tem_selo_proprio():
    src = _admin()
    assert "COMBINADA &mdash; a melhor prancha de cada leitura" in src
    assert "String(f.job_id).startsWith('mg')" in src


def _filhote_da_tela(job_id, medidos, liberado=False, itens=200):
    """Uma linha da aba Filhotes como a rota /api/admin/filhotes devolve."""
    return {"job_id": job_id, "parent_job_id": _PAI_ID,
            "projeto": "Obra do cliente-01", "cliente": _PAI_EMAIL,
            "status": "done", "melhorou": True, "liberado": liberado,
            "antes": {"medidos": 92, "itens": 147},
            "depois": {"medidos": medidos, "itens": itens}}


def _linha_renderizada(pagina, todas, alvo):
    """O HTML da linha `alvo`, com a aba inteira carregada em `_filhotes` —
    porque é de lá que `temMergeMelhor` procura a combinada."""
    import json as _j
    pagina.eval("_filhotes = %s; 1;" % _j.dumps(todas))
    return pagina.eval("renderFilhotes(%s)" % _j.dumps([alvo]))


def test_a_releitura_avisa_quando_existe_combinada_melhor():
    """O aviso vai na linha PERIGOSA, nao na certa — quem esta prestes a errar
    e quem precisa ler.

    🪤 07/09 (cético): o guarda anterior lia o fonte de `admin.html` — contava
    a declaração da função e procurava a frase em QUALQUER lugar do arquivo,
    comentário incluído. Ele não via o CALL SITE (que é quem faz o aviso
    existir) nem redefinição por atribuição (`temMergeMelhor = function(){...}`
    depois da declaração — em JS vale o último). Aqui a tela é DESENHADA num
    motor JS e o guarda lê o HTML que o Pedro veria."""
    from _bancada_js import Pagina
    p = Pagina(("aiarq-utils.js", "admin.html"))
    releitura = _filhote_da_tela("ev597afa", 151)
    combinada = _filhote_da_tela("mg634d18", 179)

    html = _linha_renderizada(p, [releitura, combinada], releitura)
    assert "Libere a combinada" in html, (
        "a linha da RELEITURA saiu sem o aviso de que existe uma combinada "
        "melhor — o clique errado entrega a versão pior e manda e-mail, e "
        "e-mail lido não se desfaz. Saiu: %s" % html[:400])
    assert "179 medidos" in html and "contra 151" in html, (
        "o aviso não diz os DOIS números (o da combinada e o desta) — sem "
        "eles não dá pra decidir: %s" % html[:400])

    # o aviso vai na linha perigosa, NÃO na certa
    html_mg = _linha_renderizada(p, [releitura, combinada], combinada)
    assert "Libere a combinada" not in html_mg, (
        "a combinada está avisando de si mesma")
    assert "COMBINADA &mdash; a melhor prancha de cada leitura" in html_mg, (
        "a linha da combinada perdeu o selo que a distingue da releitura")

    # 🧪 controles negativos — alarme que sai sempre vira ruído ignorado
    liberada = _filhote_da_tela("mg634d18", 179, liberado=True)
    assert "Libere a combinada" not in _linha_renderizada(
        p, [releitura, liberada], releitura), (
        "avisou pra liberar uma combinada que JÁ está com o cliente")
    pior = _filhote_da_tela("mg634d18", 90)
    assert "Libere a combinada" not in _linha_renderizada(
        p, [releitura, pior], releitura), (
        "avisou pra liberar a combinada que mediu MENOS que esta releitura")
    assert "Libere a combinada" not in _linha_renderizada(
        p, [releitura], releitura), (
        "avisou de uma combinada que não existe")


def test_o_aviso_so_aparece_se_a_combinada_for_melhor_E_nao_liberada():
    """Controle negativo: aviso que sai sempre vira ruido ignorado."""
    src = _admin()
    i = src.index("function temMergeMelhor")
    corpo = src[i:i + 700]
    assert "!x.liberado" in corpo
    assert "> Number(f.depois?.medidos || 0)" in corpo


def test_a_combinada_nunca_avisa_de_si_mesma():
    src = _admin()
    i = src.index("function temMergeMelhor")
    corpo = src[i:i + 400]
    assert "if (!f || String(f.job_id).startsWith('mg')) return 0;" in corpo


def test_o_confirm_do_liberar_diz_QUAL_versao_esta_indo():
    """Ultima chance antes do e-mail sair."""
    src = _admin()
    i = src.index("async function liberarFilhote")
    corpo = src[i:i + 1600]
    assert "Vers" in corpo and "COMBINADA (" in corpo
    assert "RELEITURA (" in corpo


def test_o_resultado_do_merge_rola_ate_onde_a_pessoa_esta_olhando():
    """🚨 3 cliques do Pedro terminaram em tela vazia. Na 3ª o merge FOI criado
    (10s, no log) e a mensagem nasceu ACIMA do que ele via: o painel do estudo
    tem ~2000px e o resultado ~150px, entao a pagina encolhe embaixo dos pes de
    quem estava no fim. Acao que nao termina com algo visivel ONDE a pessoa
    esta olhando e indistinguivel de acao que nao aconteceu."""
    src = _admin()
    i = src.index("async function mergeCriar")
    # 🪤 Janela FIXA corta função e mede o pedaço errado — me pegou 2x hoje.
    # O fim é a próxima função no nível zero.
    j = src.find(chr(10) + "async function ", i + 10)
    k = src.find(chr(10) + "function ", i + 10)
    fins = [x for x in (j, k) if x > 0]
    corpo = src[i:min(fins) if fins else i + 4000]
    assert corpo.count("scrollIntoView") >= 2, (
        "o sucesso E o erro precisam rolar ate a vista — nao adianta so um")
    assert "N&atilde;o criei o projeto combinado" in corpo or "criei o projeto combinado" in corpo


# ══════════════════════════════════════════════════════════════════════════
#  🎨 O e-mail tem que PARECER do AI.arq (e o rodape nao e enfeite)
# ══════════════════════════════════════════════════════════════════════════
#
# Pedro, 24/08: "o texto do email vai explicativo ne? (...) e vai na formatacao
# de ia arq ne? temos alguma foto legal nesse email?"
#
# Nao ia. A 1a versao saia como <div> cru: sem logo, sem a barra indigo->cyan,
# sem CTA padrao e — o que importa de verdade — SEM O RODAPE, que e onde moram o
# link de privacidade e o "responda pra remover seus dados". Ele notou pelo
# visual; o custo real era de LGPD (regra dura nº6).
def test_o_email_do_merge_usa_a_moldura_da_marca(monkeypatch):
    """🪤 07/09 (cético): a versão anterior provava que o builder CHAMA
    `_email_wrap` — não que a moldura CHEGA no cliente. Tudo entre o builder e
    o SMTP era cego. Agora o guarda procura as marcas no HTML que passou pela
    porta de saída, e o custo real de 24/08 (TRÊS clientes sem o rodapé de
    LGPD, regra dura nº6) é conferido marca por marca."""
    html = _email_que_saiu(monkeypatch, "mg634d18")["html"]
    for marca in _MARCAS_DA_MOLDURA:
        assert marca in html, (
            "o e-mail do merge saiu SEM %r — voltou a ser <div> cru: sem logo, "
            "sem CTA e sem o rodapé de privacidade (LGPD, regra dura nº6)"
            % marca)


def test_tem_imagem_com_alt_que_se_sustenta_sozinho():
    """O Gmail bloqueia imagem por padrao. Se o alt nao disser nada, o cliente
    ve um retangulo vazio no meio do e-mail."""
    corpo = _corpo("_email_leitura_combinada")
    assert "_email_img(" in corpo
    i = corpo.index("_email_img(")
    trecho = corpo[i:i + 320]
    assert "medidos do CAD" in trecho, "o alt da imagem nao carrega a mensagem"


def test_tem_preheader():
    """Preheader e a 2a linha que aparece na caixa de entrada ANTES de abrir.
    Quem nao tem esta jogando fora espaco gratis."""
    corpo = _corpo("_email_leitura_combinada")
    assert "preheader=" in corpo


def test_o_assunto_NAO_leva_entidade_html():
    """🪤 A 1a versao tinha 'vers&atilde;o' no subject com um .replace() pra
    consertar. Entidade HTML nao e decodificada no cabecalho do e-mail — o
    cliente leria o codigo na caixa de entrada."""
    corpo = _corpo("_email_leitura_combinada")
    i = corpo.index("subject = ")
    linha = corpo[i:corpo.index(chr(10), i)]
    assert "&" not in linha, "entidade HTML vazando pro assunto: %s" % linha


def test_o_CTA_aponta_pro_projeto_COMBINADO():
    """Mandar pro dashboard generico faz o cliente procurar; mandar pro projeto
    errado e pior ainda."""
    corpo = _corpo("_email_leitura_combinada")
    assert "job_id=%s" in corpo and "merge_job" in corpo


def test_o_email_da_RELEITURA_tambem_usa_a_moldura(monkeypatch):
    """🚨 A auditoria dos 17 e-mails (24/08) achou que eu tinha consertado o do
    merge e deixado o IRMAO pra tras. `_email_leitura_nova` ainda saia como
    <div> cru — sem logo, sem CTA e SEM o rodape de privacidade (regra dura
    nº6). TRES clientes ja tinham recebido assim.

    🪤 07/09 (cético): este guarda chamava o BUILDER (ou lia o fonte dele) e
    nunca perguntava o que sai pela única porta de e-mail da casa. Builder
    certo + envio que ignora o builder = cliente sem rodapé de LGPD, bancada
    verde. Agora ele passa pela ROTA, igual ao irmão do merge."""
    saiu = _email_que_saiu(monkeypatch, "ev597afa")
    for marca in _MARCAS_DA_MOLDURA:
        assert marca in saiu["html"], (
            "o e-mail da RELEITURA saiu SEM %r — foi exatamente assim que TRÊS "
            "clientes receberam em 24/08" % marca)
    pre = _preheader_do(saiu["html"])
    assert pre and len(pre) >= 20, (
        "preheader vazio-mas-presente: %r — é a linha que aparece na caixa de "
        "entrada antes de abrir" % pre)


def test_os_DOIS_emails_de_versao_nova_tem_o_mesmo_padrao(monkeypatch):
    """Guarda de simetria: e facil consertar um e esquecer o outro — foi
    exatamente o que aconteceu, DUAS vezes no mesmo par.

    🪤 07/09 (cético): a versão anterior media PRESENÇA de marcador no fonte
    (`"preheader=" in c`). Preheader vazio-mas-presente, signoff ausente e
    badge trocado são assimetrias reais que passavam — e, como ela chamava o
    builder, o envio podia estar mandando o e-mail errado sem este guarda
    tocar no caminho. Agora os dois saem pela ROTA e o que se compara é
    CONTEÚDO: o texto do preheader, o texto do selo, a assinatura, o rodapé."""
    saiu = {}
    for job, tipo in (("mg634d18", "leitura_combinada"), ("ev597afa", "leitura_nova")):
        e = _email_que_saiu(monkeypatch, job)
        assert e["tipo"] == tipo, (
            "o Liberar de %s mandou o e-mail %r" % (job, e["tipo"]))
        saiu[tipo] = e

    for tipo, e in saiu.items():
        html, texto = e["html"], _texto_do_email(e["html"])
        for marca in _MARCAS_DA_MOLDURA:
            assert marca in html, "%s sem %r na moldura" % (tipo, marca)
        pre = _preheader_do(html)
        assert pre and len(pre) >= 20, "%s: preheader vazio ou ausente: %r" % (tipo, pre)
        assert "92" in pre and "179" in pre, (
            "%s: o preheader não leva o placar (92 → 179 medidos) — é o espaço "
            "grátis da caixa de entrada indo pro lixo: %r" % (tipo, pre))
        assert "um abraço, pedro" in texto, (
            "%s perdeu a assinatura — o rodapé solto vira '•••' no Gmail" % tipo)
        assert "sua versão original continua no painel" in texto, (
            "%s não diz que a versão dele fica (regra dura nº7)" % tipo)
        assert "&" not in e["assunto"], (
            "%s: entidade HTML vazando pro assunto (%r) — cabeçalho de e-mail "
            "não decodifica entidade, o cliente lê o código" % (tipo, e["assunto"]))
        assert _badge_do(html), "%s ficou sem selo no topo" % tipo

    # e o selo tem que DISTINGUIR os dois: badge igual nos dois é a assimetria
    # ao contrário — o cliente não sabe qual versão chegou.
    assert _badge_do(saiu["leitura_combinada"]["html"]) \
        != _badge_do(saiu["leitura_nova"]["html"]), (
        "os dois e-mails saíram com o MESMO selo (%r) — 'combinada' e "
        "'refizemos a leitura' viram a mesma coisa na caixa de entrada"
        % _badge_do(saiu["leitura_nova"]["html"]))


# ══════════════════════════════════════════════════════════════════════════
#  🚨 Simetria: consertar um e esquecer o irmao ja aconteceu DUAS vezes
# ══════════════════════════════════════════════════════════════════════════
def test_os_DOIS_emails_contam_o_que_PIOROU():
    """25/08 (auditoria): o e-mail do merge PERDEU o quadro do que piorou quando
    eu o reescrevi pra entrar na moldura da marca. O irmao tinha; este ficou sem.

    E a SEGUNDA vez no mesmo par: antes fora a moldura em si (consertei o do
    merge e deixei o da releitura como <div> cru). Par de funcoes que faz quase
    a mesma coisa precisa de guarda de simetria, nao de disciplina."""
    for nome in ("_email_leitura_combinada", "_email_leitura_nova"):
        c = corpo_de(nome)
        assert "_piores" in c, "%s nao calcula o que piorou" % nome
        assert "piorou" in c.lower(), "%s nao mostra o que piorou" % nome
        assert "if _piores:" in c, "%s mostra o alarme sem condicao" % nome


# Duas linhas MEDIDAS cuja procedência é só um texto lido da prancha — o caso
# de 24/08 ("AREA TOTAL CLINICA = 264,54 m²" colado na linha do piso). A rede da
# regra dura nº1 tem que rebaixar AS DUAS.
_PROCEDENCIA_DE_TEXTO = ("Fonte: texto do carimbo da prancha: "
                         "'AREA TOTAL = 264,54 m2'")
_SO_TEXTO = [
    ("Piso — revestimento de piso interno", 264.54),
    ("Forro — placa mineral removivel", 198.30),
]
_COM_MARCA = "Piso vinilico Tarkett ref. 24003 cor Carvalho Natural"


def _banco_com_selo_de_texto():
    """ARQ-01 fica com o PAI (6 medidos × 3) e é lá que moram as duas linhas de
    procedência só-de-texto; EL-02 fica com o filho (5 × 2)."""
    projetos = {
        _PAI_ID: {"job_id": _PAI_ID, "user_id": "u-cliente-01",
                  "user_email": _PAI_EMAIL, "user_name": "Cliente Um",
                  "project_name": "Obra do cliente-01", "status": "done",
                  "typology": "office", "project_type": "arquitetura",
                  "created_at": "2026-08-20T19:37:48+00", "warnings": []},
        "ev597afa": {"job_id": "ev597afa", "parent_job_id": _PAI_ID, "is_eval": True,
                     "status": "done", "user_id": "eval", "warnings": [],
                     "project_name": "[TESTE] Obra do cliente-01 — avaliação",
                     "created_at": "2026-08-24T19:37:48+00"},
    }
    pai = _mb.itens("ARQ-01", 8, 4, rotulo="orig") + _mb.itens("EL-02", 8, 2, rotulo="orig")
    for desc, qtd in _SO_TEXTO:
        pai.append(_mb.item("ARQ-01", descricao=desc, confidence="confirmado",
                            unit="m²", quantity=qtd,
                            observations=_PROCEDENCIA_DE_TEXTO))
    pai.append(_mb.item("ARQ-01", descricao=_COM_MARCA, unit="m²", quantity=40))
    filho = (_mb.itens("ARQ-01", 10, 3, rotulo="rel")
             + _mb.itens("EL-02", 8, 5, rotulo="rel"))
    return _mb.Banco(projetos, {_PAI_ID: pai, "ev597afa": filho})


def test_o_merge_roda_a_rede_do_selo_e_o_extrator(monkeypatch):
    """🚨 O merge grava project_items POR FORA do motor, entao pulava as duas
    passadas que todo item normal atravessa: a rede da REGRA DURA Nº1 e o
    extrator de especificacao. "Os itens ja passaram" nao vale — a rede nasceu
    em 24/08 e os jobs de origem podem ser anteriores.

    🪤 07/09 (cético): a versão anterior lia o fonte, e a que veio depois tinha
    UMA linha de procedência só-de-texto — a rede só precisava acertar o
    primeiro achado. `_rebaixados[:1]`, um `break`, `_ssg_m(...)[:1]`: tudo
    passava verde, e num merge real (várias linhas seladas '✓ MEDIDO do CAD'
    sobre texto de prancha) todas menos uma continuavam saindo MEDIDAS. Aqui
    são DUAS, e as DUAS são cobradas."""
    b = _banco_com_selo_de_texto()
    _mb.instalar(monkeypatch, b)
    r = _m.admin_merge_criar("ev597afa", _mb.Req())
    gravadas = b.itens_do(r["job_id"])
    assert gravadas, "o merge não gravou item nenhum"

    por_desc = {str(x.get("description")): x for x in gravadas}
    for desc, _q in _SO_TEXTO:
        assert desc in por_desc, "a linha %r não foi gravada no merge" % desc
        linha = por_desc[desc]
        assert linha["confidence"] == "estimado", (
            "%r saiu do merge com selo '✓ MEDIDO do CAD' tendo como fonte só "
            "um texto da prancha — regra dura nº1" % desc)
        obs = str(linha["observations"])
        assert "LIDO de um texto da prancha, não medido da geometria" in obs, (
            "%r foi rebaixada sem dizer POR QUE: %r" % (desc, obs))
        assert _PROCEDENCIA_DE_TEXTO in obs, (
            "%r perdeu a procedência que já tinha ao ser rebaixada: %r"
            % (desc, obs))

    # 🧪 controle: o rebaixamento não pode ser geral — medição de verdade fica
    confirmados = [x for x in gravadas if x["confidence"] == "confirmado"]
    assert len(confirmados) == 9, (
        "esperava 9 medidos depois do rebaixamento (4 da ARQ-01 do pai + 5 da "
        "EL-02 do filho), vieram %d" % len(confirmados))
    assert r["medidos"] == 9, (
        "o placar que vai no e-mail não foi recalculado depois do "
        "rebaixamento: %r" % r["medidos"])

    # e o extrator de especificação rodou nas linhas do merge
    spec = por_desc[_COM_MARCA]
    assert (spec.get("marca"), spec.get("codigo_fabricante"), spec.get("cor")) \
        == ("Tarkett", "24003", "Carvalho Natural"), (
        "o merge gravou o item sem marca/código/cor — o caderno de acabamentos "
        "sai vazio pra planilha combinada: %r"
        % {k: spec.get(k) for k in ("marca", "codigo_fabricante", "cor")})


def test_o_rebaixamento_do_merge_corrige_o_PLACAR():
    """Se a rede rebaixa item no merge, o numero de medidos muda — e e esse
    numero que vai no e-mail. Rebaixar e mandar o placar velho seria mentir."""
    c = corpo_de("admin_merge_criar")
    i = c.index("_rebaixados = _ssg_m(")
    assert "med_merge = sum(" in c[i:i + 1400], (
        "o placar nao e recalculado depois do rebaixamento")


def test_CONTROLE_o_filtro_de_comentario_nao_cegou_o_guarda():
    """🧪 31/08 — depois de ensinar o helper a ignorar comentário, ele podia ter
    virado cego. Prova nos dois sentidos, sem tocar em arquivo nenhum."""
    def _limpa(txt):
        linhas = [ln for ln in txt.splitlines() if not ln.lstrip().startswith("#")]
        return " ".join(" ".join(linhas).split())

    # a frase num COMENTÁRIO não é achado (era o alarme falso)
    assert "refizemos a leitura" not in _limpa(
        '    # o filhote diz "refizemos a leitura"\n'
        '    corpo = "Combinamos as duas leituras"').lower()
    # a frase no TEXTO DO CLIENTE continua sendo achado
    assert "refizemos a leitura" in _limpa(
        '    # comentário inocente\n'
        '    corpo = "Refizemos a leitura do seu projeto"').lower()
    # e a cor do HTML não pode ser comida pelo filtro
    assert "#FFFBEB" in _limpa('    corpo = "background:#FFFBEB;padding:10px"')
