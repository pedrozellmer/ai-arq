# -*- coding: utf-8 -*-
"""O e-mail de REPROCESSO fala a mesma língua dos outros dois: não promete medida.

🩸 18/09/2026. Existem TRÊS portas de entrega — primeira entrega, complemento e
reprocesso. As duas primeiras conferem se algo foi medido antes de escrever.
A terceira escrevia o texto na mão, e o texto era o de boa notícia SEMPRE:

    "Reprocessamos o projeto X com o motor mais recente e a planilha atualizada
     ficou pronta, com 37 itens de quantitativo. (...) Cada item vem marcado
     como medido (direto do CAD) ou estimativa (pra você conferir)."

Medido no banco: dos **8 reprocessos avisados a cliente, 4 (3 contas) saíram
com ZERO medida** — 50%. E no job 788d0270 (17/09) o próprio motor registrou,
no mesmo processamento, `motor:leitura-pior: v1: medidos 4 -> 0 (itens 13 ->
37)`. A gente sabia que a releitura tinha ficado PIOR e mandou a frase boa.

🔑 O conserto não é régua nova: `voz_do_email_de_reprocesso` existe desde
06/09, leva o nome DESTE caminho e nasceu deste mesmo defeito — mas quem a
chamava era só o complemento. Ver [[feedback_consertar_o_alcance_nao_o_padrao]].

🚨 POR QUE ESTES GUARDAS EXECUTAM. A docstring da própria função conta que o
guarda anterior lia o FONTE, achava as frases de medição no ramo certo e nunca
perguntava EM QUE CONDIÇÃO o ramo roda — passou verde com a condição trocada.
Aqui a fatia real do `process_job` roda com `reprocess_count=1` e o que se
confere é o e-mail montado.

🚫 O QUE ESTES GUARDAS NÃO COBREM:
  · se o cliente ABRE o e-mail, ou se a planilha está certa;
  · a redação exata — de propósito. Um guarda que fixasse a frase congelaria a
    copy (foi o que `"71%" in caixa` fez em 02fe3d5, segurando frase falsa no
    ar). Cobra-se o que precisa SER DITO e o que não pode ser afirmado;
  · o ramo de piora só é exercitado com a comparação injetada: quem produz a
    frase é `_comparar_com_versao_anterior`, que fala com o banco;
  · **DWG que não abriu ainda conta como CAD.** `_n_cad_r` olha a EXTENSÃO do
    arquivo, então um `.dwg` que o conversor recusou faz o e-mail dizer "o CAD
    do projeto" e, pior, CALA o pedido de mandar DWG/DXF (no ramo `_e_cad` o
    pedido é vazio). MEDIDO em 18/09 antes de decidir: 20 jobs de cliente
    tiveram DWG que não abriu (11 contas), mas só **2** receberam e-mail de
    reprocesso ou complemento — alcance pequeno demais pra justificar um 4º
    mecanismo neste commit. O sinal certo já existe no escopo: `dwg_failed`.
    (No mesmo período, **61 jobs foram SALVOS pelo fallback libredwg** — DWG
    que o ODA recusa não é o fim da linha.)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _fim_do_job import roda_ate_o_email  # noqa: E402


class _It(object):
    def __init__(self, conf="estimado"):
        self.description = "alvenaria de vedacao"
        self.unit = "m2"
        self.quantity = 12.0
        self.confidence = conf
        self.discipline = "Paredes"
        self.origem = "geometria" if conf == "confirmado" else "ia"


def _reprocesso(itens, piora="", **kw):
    """Roda a fatia real no ramo do reprocesso e devolve (e-mail, diário).

    🪤 `_comparar_com_versao_anterior` é injetada pelo harness como `{}`
    (ela fala com o banco). Pra exercitar o ramo de piora, entra por
    `antes_do_email`, que o harness aplica no namespace ANTES do exec.
    """
    extra = dict(kw.pop("antes_do_email", None) or {})
    if piora:
        extra["_comparar_com_versao_anterior"] = (
            lambda *a, **k: {"versao": 1, "antes_itens": 13,
                             "antes_medidos": 4, "perdeu_medidos": 4,
                             "frase": piora})
    diario = roda_ate_o_email(itens, reprocess_count=1,
                              antes_do_email=extra, **kw)
    enviados = [e for e in diario["emails"] if e.get("kind") == "reprocesso_pronto"]
    assert len(enviados) == 1, (
        "o ramo do reprocesso não rodou (ou rodou duas vezes): kinds=%r"
        % [e.get("kind") for e in diario["emails"]])
    return enviados[0], diario


def _afirmacoes_de_medida(email):
    """Tudo que o cliente lê como 'a gente mediu' — assunto, selo e corpo.

    🪤 A 1ª lista era frágil de dois jeitos, e a revisão adversarial mostrou os
    dois: cobria UMA grafia do ✓ (a entidade HTML, não o caractere), e usava
    "entrou na conta." com PONTO FINAL — o que prendia a pontuação da copy e
    ainda por cima não é afirmação de medida nenhuma ("o arquivo entrou na
    conta" diz que ele foi considerado, não que mediu). Fora daqui.

    🩸 E a 2ª lista errou pro outro lado: pus `✓ medido` como agulha e ela
    casou com a frase de NEGAÇÃO — *"Nenhum item saiu com o selo ✓ MEDIDO do
    desenho desta vez"*. Procurar a palavra acha o aviso do próprio sistema.
    Ver [[feedback_procurei_a_palavra_nao_o_comportamento]].

    🔑 Por isso o SELO não é conferido por texto aqui: quem cuida dele é
    `test_o_selo_de_AVISO_nao_sai_na_pilula_VERDE`, pela COR (âmbar × verde),
    que é imune a grafia e a entidade HTML. Aqui ficam só frases que não
    existem em forma negada.

    🚫 Não cobre o bloco "o que a gente mediu no seu PDF", que é afirmação
    sobre a PRANCHA e não sobre linha — ele não aparece nos cenários deste
    arquivo porque nenhum passa `pdfvec_por_prancha`.
    """
    texto = (email["assunto"] + " " + email["html"]).lower()
    agulhas = ("medimos", "medindo pelo", "medidos do desenho")
    return [f for f in agulhas if f in texto]


# ── o defeito ───────────────────────────────────────────────────────────────

def test_o_reprocesso_com_ZERO_medido_NAO_afirma_medicao():
    """🚨 Regra dura nº1 dentro do e-mail: nada de 'medimos' sem medida."""
    email, _ = _reprocesso([_It(), _It(), _It()])
    achadas = _afirmacoes_de_medida(email)
    assert not achadas, (
        "o e-mail de reprocesso afirma medição com ZERO itens medidos: %r\n"
        "assunto: %s" % (achadas, email["assunto"]))


def test_o_reprocesso_com_ZERO_medido_DIZ_que_nao_mediu():
    """🪤 A outra metade: guarda que só proíbe fica verde no silêncio — foi o
    defeito de `fa4ae77` hoje de manhã. O e-mail tem que DIZER."""
    email, _ = _reprocesso([_It(), _It(), _It()])
    baixo = email["html"].lower()
    assert "nenhum item saiu com o selo" in baixo, (
        "o e-mail não conta que nada foi medido — só evitou mentir")
    # 🪤 `"3 itens" in html` sozinho é satisfeito por qualquer outro bloco que
    # cite o mesmo número. O que prova que o e-mail carrega ESTA entrega é a
    # diferença: mudou a contagem, mudou o texto.
    e9, _ = _reprocesso([_It()] * 9)
    assert "3 itens" in email["html"] and "9 itens" in e9["html"], (
        "o tamanho da entrega sumiu do texto")
    assert "9 itens" not in email["html"], (
        "o número no e-mail não acompanha a entrega — veio de outro lugar")


def test_CONTROLE_o_reprocesso_que_MEDIU_continua_dizendo_quantos():
    """Controle positivo: sem ele, um e-mail mudo passaria em tudo acima."""
    email, _ = _reprocesso([_It("confirmado"), _It("confirmado"), _It()])
    assert _afirmacoes_de_medida(email), (
        "reprocesso que mediu 2 de 3 parou de dizer que mediu")
    assert "2</b> medidos" in email["html"] or "2 medidos" in email["html"], \
        email["html"][:400]


def test_o_reprocesso_que_leu_PIOR_avisa_em_vez_de_comemorar():
    """🩸 O caso real de 17/09: `medidos 4 -> 0`, e o cliente leu 'ficou pronta'."""
    frase = "esta releitura mediu MENOS que a anterior (4 → 0 itens medidos)"
    email, _ = _reprocesso([_It(), _It()], piora=frase)
    assert frase in email["html"], "a frase de piora não chegou ao corpo"
    assert "mudou" in email["assunto"].lower(), email["assunto"]
    assert not _afirmacoes_de_medida(email), _afirmacoes_de_medida(email)


def test_o_reprocesso_de_quem_mandou_PDF_nao_diz_CAD():
    """🩸 16/09: dizer 'o CAD que você anexou' a quem mandou PDF CONFIRMA pro
    cliente que ele mandou o arquivo certo — e ele reenvia PDF de novo."""
    email, _ = _reprocesso([_It(), _It()], n_pdf=1, n_cad=0)
    inteiro = email["assunto"] + " " + email["html"]
    assert "CAD que você anexou" not in inteiro, inteiro[:400]
    assert "O CAD entrou na conta" not in inteiro, (
        "o preheader ainda diz CAD fixo — é o pedaço que 16/09 esqueceu")
    assert "DWG" in inteiro and "DXF" in inteiro, (
        "não diz o caminho pra sair medida")


def _preheader(html):
    """O texto que aparece na CAIXA DE ENTRADA, recortado como ele existe.

    🩸 A 1ª versão deste guarda procurava a palavra "preheader" no HTML — que
    NUNCA aparece — caía no `else`, olhava 800 caracteres quaisquer e procurava
    "medimos", que também nunca aparece nesse e-mail. Passava sempre, contra
    qualquer código. `_email_wrap` põe o preheader num div seguido de 30
    `&zwnj;&nbsp;`; a âncora é esse espaçador, que É o mecanismo.
    """
    i = html.find("&zwnj;")
    assert i > 0, "o espaçador do preheader sumiu do _email_wrap — âncora morta"
    return html[:i]


def test_o_preheader_NAO_contradiz_o_corpo():
    """🩸 03/09: o cliente lê o preheader ANTES de abrir. Ele dizia 'nenhuma
    quantidade saiu da geometria' e o corpo, três linhas abaixo, o contrário."""
    email, _ = _reprocesso([_It(), _It()])
    pre = _preheader(email["html"])
    assert pre.strip(), "o preheader saiu vazio"
    assert not _afirmacoes_de_medida({"assunto": "", "html": pre}), pre
    assert "nenhuma quantidade" in pre.lower() or "nada ganhou o selo" in pre.lower(), (
        "o preheader não conta o que aconteceu: %r" % pre)


def test_CONTROLE_o_preheader_de_quem_MEDIU_e_outro():
    """Controle positivo do recorte: se `_preheader` pegasse o HTML inteiro, ou
    sempre a mesma coisa, este teste e o de cima não podiam ser ambos verdes."""
    email, _ = _reprocesso([_It("confirmado"), _It()])
    pre = _preheader(email["html"])
    assert "nenhuma quantidade" not in pre.lower(), pre
    assert len(pre) < len(email["html"]), "o recorte pegou o e-mail inteiro"


def test_o_selo_de_AVISO_nao_sai_na_pilula_VERDE():
    """🩸 18/09: `_email_wrap` pinta de verde por padrão. O selo '⚠ Sem medida
    do desenho' saía no chip de sucesso — a cor desmentindo o texto na primeira
    olhada, que é a única que muita gente dá."""
    import main
    email, _ = _reprocesso([_It(), _It()])
    assert main.cor_do_selo("&#9888; Sem medida do desenho") == "amber"
    assert main.cor_do_selo("&#10003; Medido") == "green"
    # verde do _email_wrap = #dcfce7; âmbar = #fef3c7
    assert "#fef3c7" in email["html"], (
        "o selo de aviso continua na pílula verde")
    e_ok, _ = _reprocesso([_It("confirmado"), _It()])
    assert "#dcfce7" in e_ok["html"], "quem mediu perdeu o verde"


def test_o_reprocesso_NAO_diz_que_o_cliente_anexou_arquivo():
    """🚨 O ramo só roda com `not is_complement`: aqui NINGUÉM anexou nada — o
    cliente clicou "reprocessar", ou fomos nós. A voz nasceu no complemento, que
    é literalmente "o cliente anexou um arquivo novo", e afirmava o anexo nas
    três falas. Ligar o reprocesso sem isto trocaria uma frase falsa por outra.
    """
    for itens, piora in (([_It(), _It()], ""),
                         ([_It("confirmado"), _It()], ""),
                         ([_It(), _It()], "a releitura mediu MENOS (4 → 0)")):
        email, _ = _reprocesso(itens, piora=piora)
        inteiro = (email["assunto"] + " " + email["html"]).lower()
        assert "que você anexou" not in inteiro, inteiro[:400]
        assert "que você mandou" not in inteiro, inteiro[:400]


def test_CONTROLE_o_COMPLEMENTO_continua_dizendo_que_anexou():
    """🚫 O complemento é o caminho de quem REALMENTE anexou — lá a frase é
    verdadeira e não pode ter sido levada junto no conserto."""
    d = roda_ate_o_email([_It(), _It()], is_complement=True)
    e = [x for x in d["emails"] if x.get("kind") == "complemento_pronto"][-1]
    assert "que você anexou" in e["html"], (
        "o conserto do reprocesso apagou a frase verdadeira do complemento")


def test_o_reprocesso_diz_que_a_versao_anterior_continua_no_painel():
    """🪤 O texto antigo dizia "Ela substitui a versão anterior — abra pra
    revisar e baixar", e a voz do complemento não diz isso (lá nem sempre há
    versão anterior). Para quem reprocessou, sempre há — e perder a informação
    seria regressão escondida dentro de um conserto."""
    for itens in ([_It(), _It()], [_It("confirmado"), _It()]):
        email, _ = _reprocesso(itens)
        assert "versão anterior continua no painel" in email["html"], (
            "o cliente não fica sabendo que a versão velha sobrevive")


# ── a doença é a receita repetida: o guarda mira na DIVERGÊNCIA ─────────────

def test_o_reprocesso_e_o_complemento_dao_a_MESMA_voz():
    """🧬 As três portas de entrega são a mesma decisão. Enquanto o reprocesso
    escrevia texto próprio, ele divergiu por 12 dias sem ninguém ver.
    Ver [[feedback_a_receita_repetida_e_a_doenca]]."""
    itens = [_It(), _It(), _It()]
    e_rep, _ = _reprocesso(list(itens))
    d_comp = roda_ate_o_email(list(itens), is_complement=True)
    e_comp = [e for e in d_comp["emails"]
              if e.get("kind") == "complemento_pronto"][-1]
    assert e_rep["assunto"] == e_comp["assunto"], (
        "reprocesso e complemento voltaram a divergir:\n  rep : %s\n  comp: %s"
        % (e_rep["assunto"], e_comp["assunto"]))
    assert bool(_afirmacoes_de_medida(e_rep)) == bool(_afirmacoes_de_medida(e_comp))


def test_as_CINCO_saidas_da_voz_chegam_ao_email():
    """🪤 Eu liguei a abertura e o assunto e quase deixei título, selo e
    preheader fixos no `_email_wrap`. Guarda que só olha 'não mentiu' não pega
    isso: 'Atualizado' não afirma medida — só desmonta a voz por dentro."""
    import main
    itens = [_It(), _It(), _It()]
    email, _ = _reprocesso(list(itens))
    n_geo, frase_origem = main._origem_das_quantidades(itens)
    _abre, _subj, titulo, selo, pre = main.voz_do_email_de_reprocesso(
        "projeto de teste", "projeto de teste", len(itens), 0, n_geo,
        anexo="CAD", frase_piora="", frase_origem=frase_origem)
    inteiro = email["html"]
    for nome, esperado in (("titulo", titulo), ("selo", selo), ("preheader", pre)):
        assert esperado in inteiro, (
            "o %s não veio da voz — ficou fixo no e-mail: esperava %r"
            % (nome, esperado))


def test_o_log_diz_qual_voz_saiu():
    """🔬 Foi log de estágio que deixou este defeito visível. Sem ele eu
    precisaria reconstruir a decisão de fora, que é como errei hoje 3×."""
    _, diario = _reprocesso([_It("confirmado"), _It()])
    linhas = [l for l in diario["logs"] if "motor:voz-do-reprocesso" in l]
    assert linhas, "o motor não registra qual voz saiu: %r" % diario["logs"][-5:]
    assert "medidos=1" in linhas[-1] and "itens=2" in linhas[-1], linhas[-1]
    assert "piora=nao" in linhas[-1], linhas[-1]


def test_quando_o_email_falha_fica_RASTRO_no_log():
    """🩸 O `except` do bloco de e-mail era só um `print`: falhou ali, o cliente
    ficava sem aviso nenhum e não sobrava linha no `error_log` — "não recebi
    e-mail" viraria investigação do zero.

    🔑 Este guarda existe porque o defeito aconteceu COMIGO nesta sessão: um
    `NameError` meu derrubou o e-mail e o único sinal foi um teste reclamando.
    Em produção não haveria nem isso.
    """
    def _explode(*a, **k):
        raise RuntimeError("SMTP caiu")
    diario = roda_ate_o_email([_It(), _It()], reprocess_count=1,
                              exige_email=False,
                              antes_do_email={"_send_email_smtp": _explode})
    assert not diario["emails"], "o dublê não derrubou o envio"
    rastro = [l for l in diario["logs"] if "email:fim-de-job-falhou" in l]
    assert rastro, ("o e-mail falhou e não deixou rastro no log: %r"
                    % diario["logs"][-4:])
    assert "RuntimeError" in rastro[-1] and "SMTP caiu" in rastro[-1], rastro[-1]


def test_CONTROLE_sem_reprocesso_este_email_NAO_sai():
    """O ramo é exclusivo: primeira entrega continua no caminho dela."""
    diario = roda_ate_o_email([_It(), _It()], reprocess_count=0)
    kinds = [e.get("kind") for e in diario["emails"]]
    assert "reprocesso_pronto" not in kinds, kinds
