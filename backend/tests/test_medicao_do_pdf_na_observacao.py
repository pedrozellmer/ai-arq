# -*- coding: utf-8 -*-
"""O motor mediu o PDF, escreveu o número na linha e deixou a quantidade zero.

🚨 26/08/2026, caso **cliente-41** — cliente do dia, primeiro projeto,
baixou a planilha às 13:20 com nove quantidades em branco.

Depois do primeiro conserto do dia, rodamos o projeto dele em **avaliação
isolada** (`eve9afae`) pra ver o que realmente mudava. Mudou UMA linha de nove.
E o log da avaliação mostrou por quê — o padrão se repetia:

    "Piso cerâmico/porcelanato"  qtd 0
        obs: "Área total medida vetorialmente: 13,6 m² (3 ambientes)"
    "Rodapé em cerâmica"         qtd 0
        obs: "perímetro total de paredes medido vetorialmente (38,8 m)"

O motor mediu **13,6 m² de ambiente e 38,8 m de parede** no PDF dele. Os dois
números estão escritos nas linhas. As duas linhas saem vazias.

🪤 E o 38,8 só ficou visível porque, MESMA TARDE, o log do `pdfvec:promo` passou
a gravar `paredes_m=`. Antes ele só dizia `ambientes=` e `m2=`, e a pergunta
"o motor mediu parede nesse PDF?" não tinha resposta.

🔑 A PROVA NÃO É O TEXTO, É A IGUALDADE. Só preenche quando o número citado bate
(±1%) com um valor que NÓS medimos nesta leitura. Não casa a frase — casa o
NÚMERO. Por isso não importa como a IA escreveu.

🚨 O CASO PERIGOSO, do mesmo cliente e na mesma planilha:

    "Parede de alvenaria"  qtd 0
        obs: "38,8 m de paredes medidas vetorialmente × pé-direito 2,70 m
              = 104,8 m² bruto"

A IA **inventou o pé-direito de 2,70 m** — ninguém informou. O 38,8 está lá e
bate com a nossa medição, mas é COMPRIMENTO num item de m². E o 104,8 não bate
com medição nenhuma. Essa linha tem que continuar zerada: não medimos altura.
É a trava de FAMÍLIA DE UNIDADE que segura isso, e ela tem teste próprio aqui.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine_rules import quantidade_medida_pelo_pdf as q  # noqa: E402

# o que o motor vetorial mediu no PDF do cliente-41
AREA = 13.6      # 3 ambientes
COMPR = 38.8     # 89 segmentos de parede

# observações REAIS da avaliação isolada eve9afae
OBS_PISO = "Área total medida vetorialmente: 13,6 m² (3 ambientes). Inclui banheiros/vestiários identificados"
OBS_RODAPE = ("Comprimento estimado igual ao perímetro total de paredes medido "
              "vetorialmente (38,8 m), descontando vãos")
OBS_PAREDE = ("Estimativa: 38,8 m de paredes medidas vetorialmente × pé-direito "
              "2,70 m = 104,8 m² bruto; desconta vãos")
OBS_PINTURA = ("Área estimada: 38,8 m de paredes × 2,70 m pé-direito = 104,8 m² "
               "bruto; descontando vãos estimados")


def test_o_piso_do_cliente_41_para_de_sair_zerado():
    assert q(OBS_PISO, "m²", AREA, COMPR) == 13.6


def test_o_rodape_pega_o_perimetro_medido():
    assert q(OBS_RODAPE, "ml", AREA, COMPR) == 38.8


def test_a_PAREDE_com_pe_direito_INVENTADO_continua_zerada():
    """🚨 O teste que mais importa.

    A IA assumiu 2,70 m de pé-direito sozinha. Se o 38,8 colasse num item de m²,
    a gente entregaria 104,8 m² de alvenaria com uma altura que ninguém mediu —
    e com cara de medição, porque a conta está escrita na linha.
    """
    assert q(OBS_PAREDE, "m²", AREA, COMPR) is None, (
        "o comprimento de parede virou área — a planilha sairia com m² baseado "
        "num pé-direito que a IA inventou")
    assert q(OBS_PINTURA, "m²", AREA, COMPR) is None, (
        "mesma coisa na pintura")


def test_a_trava_de_UNIDADE_vale_sozinha_quando_os_numeros_COINCIDEM():
    """🪤 ESTE TESTE EXISTE PORQUE O ANTERIOR NÃO PROVAVA NADA.

    Sabotei a trava de família de unidade e a bateria passou VERDE: no caso do
    cliente-41 a área (13,6) e o comprimento (38,8) são diferentes, então a
    conferência de igualdade já rejeitava sozinha. A trava de unidade só carrega
    peso quando os dois números COINCIDEM — e aí ela é a única coisa entre a
    planilha e um metro linear virando metro quadrado.

    Cenário: uma prancha onde o motor mede 38,8 m² de ambiente E 38,8 m de
    parede. A observação cita "38,8 m" (comprimento) num item de m².
    """
    igual = 38.8
    assert q("perímetro medido vetorialmente (38,8 m)", "m²", igual, igual) is None, (
        "um COMPRIMENTO de 38,8 m virou 38,8 m² só porque os dois números "
        "batem — é a trava de família de unidade que impede isso")
    assert q("área medida vetorialmente: 38,8 m²", "ml", igual, igual) is None, (
        "uma ÁREA virou metro linear pelo mesmo motivo")
    # e cada um no seu lugar segue funcionando
    assert q("área medida vetorialmente: 38,8 m²", "m²", igual, igual) == 38.8
    assert q("perímetro medido vetorialmente (38,8 m)", "ml", igual, igual) == 38.8


def test_numero_que_NAO_bate_com_a_medicao_nao_entra():
    """Se bastasse ter número com unidade, qualquer palpite colaria."""
    assert q("Área estimada da legenda: 50,0 m²", "m²", AREA, COMPR) is None
    assert q("Perímetro aproximado: 60 m", "ml", AREA, COMPR) is None


def test_tolerancia_de_1pct_e_apertada():
    """13,6 impresso contra 13,6 medido passa; 15 não."""
    assert q("medida: 13,7 m²", "m²", AREA, COMPR) == 13.7
    assert q("medida: 15,0 m²", "m²", AREA, COMPR) is None


def test_sem_medicao_do_PDF_nao_preenche_nada():
    """Job de DXF puro, ou PDF onde o vetorial não mediu: nada muda."""
    assert q(OBS_PISO, "m²", 0, 0) is None
    assert q(OBS_RODAPE, "ml", 0, 0) is None


def test_unidade_fora_de_area_e_comprimento_nao_entra():
    """Contagem, verba e peso não têm o que casar com ambiente ou parede."""
    for u in ("un", "vb", "kg", "mês", ""):
        assert q(OBS_PISO, u, AREA, COMPR) is None, u


def test_observacao_sem_numero_devolve_nada():
    assert q("Tipo de drywall (ST/RU/RF) não especificado na legenda visível.",
             "m²", AREA, COMPR) is None
    assert q("", "m²", AREA, COMPR) is None


# ═══════════════════════════════════════════════════════════════════════
#  O CALL SITE — RODANDO O MOTOR DE VERDADE
# ═══════════════════════════════════════════════════════════════════════
# 🪤 06/09/2026 — ESTE GUARDA ERA CEGO E FOI PROVADO CEGO.
# A versão anterior lia `main.py` como TEXTO e conferia seis substrings ao
# redor da chamada (`area_pdf=`, `comprimento_pdf=`, `_pdfvec_por_prancha`,
# `_stem`, ausência de `conf`). Trocando `if _q_pdf:` por `if False:` no laço
# de itens do PDF, as seis substrings continuam no fonte — `qty = _q_pdf` e
# `_n_resgate_pdf += 1` ficam lá, mortos — e a bancada fechava **19/19 verde**
# com o resgate desligado. O caso do cliente-41 voltaria a sair com nove
# linhas em branco e nenhum teste reclamaria.
#
# 🔑 Agora o guarda CHAMA `main.process_job` e olha a quantidade que saiu na
# linha. Sem rede: o único caminho de fora é o checkpoint da retomada (que
# alimenta `_pdfvec_por_prancha` direto), então nada de IA, crops, subprocess
# de medição ou banco. O motor roda até a consolidação, onde a gente para.


class _ParouNaConsolidacao(BaseException):
    """Freio pra colher `all_items` sem rodar planilha, e-mail e gravação.

    🪤 Herda de BaseException DE PROPÓSITO: `process_job` embrulha tudo num
    `except Exception`, então um freio comum seria engolido e viraria "job com
    erro" em vez de devolver os itens.
    """
    def __init__(self, itens):
        BaseException.__init__(self)
        self.itens = list(itens)


def _item_da_ia(desc, unidade, obs):
    """Uma linha como a IA devolve: quantidade ZERO e o número na observação."""
    return {"item_num": "1", "description": desc, "unit": unidade,
            "quantity": 0, "observations": obs,
            "discipline": "Complementares", "confidence": "estimado"}


def _motor_de_pdf(paginas):
    """Roda `process_job` de verdade num PDF de N páginas e devolve os itens.

    `paginas` = lista de {"medicao": {"rooms_m2":…, "walls_m":…},
                          "items": [_item_da_ia(...), …]}
    Devolve {description: BudgetItem}.
    """
    import json
    import tempfile
    import urllib.request

    import main
    import processor

    _tmp = tempfile.mkdtemp(prefix="guarda_resgate_pdf_")
    _pdf = os.path.join(_tmp, "PRANCHA.pdf")
    io.open(_pdf, "wb").write(b"%PDF-1.4" + bytes([10]))

    # O checkpoint é a única porta que entrega análise + medição por prancha
    # sem rede. `_stem` do laço é "<nome sem extensão>_p<índice da página>".
    _cache = {}
    for _i, _pg in enumerate(paginas):
        _k = main._sanitize_filename_for_storage("PRANCHA_p%d" % _i)
        _cache[_k] = {"items": [dict(x) for x in _pg["items"]],
                      "_pdfvec_medicao": dict(_pg["medicao"])}

    class _JobsMudo:
        def update_field(self, key, **kw):
            pass

    class _Resposta:
        def __init__(self, corpo):
            self._corpo = corpo

        def read(self):
            return self._corpo

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, *a, **kw):
        # a única consulta que importa aqui: "este job auto-retomou?" — é ela
        # que liga a leitura dos checkpoints
        return _Resposta(json.dumps(
            [{"auto_resume_count": 1, "reprocess_count": 0}]).encode("utf-8"))

    def _freia(itens):
        raise _ParouNaConsolidacao(itens)

    _velhos = {}
    for _nome, _novo in (("_ckpt_load_all", lambda job_id: _cache),
                         ("_supabase_storage_upload_prancha", lambda *a, **k: True),
                         ("_supabase_update", lambda *a, **k: None),
                         ("_log_error", lambda *a, **k: None),
                         ("_projeto_patch", lambda *a, **k: None),
                         ("_consolidate_items", _freia),
                         ("jobs", _JobsMudo())):
        _velhos[_nome] = getattr(main, _nome)
        setattr(main, _nome, _novo)
    _pgc = processor.pdf_page_count
    processor.pdf_page_count = lambda p: len(paginas)
    _uo = urllib.request.urlopen
    urllib.request.urlopen = _urlopen
    _chave = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = _chave or "sk-ant-guarda-local"

    _saida = None
    try:
        main.process_job("job-guarda-resgate-pdf", [_pdf], _tmp)
    except _ParouNaConsolidacao as _p:
        _saida = _p.itens
    finally:
        for _nome, _v in _velhos.items():
            setattr(main, _nome, _v)
        processor.pdf_page_count = _pgc
        urllib.request.urlopen = _uo
        if _chave is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = _chave

    assert _saida is not None, (
        "o motor não chegou na consolidação — o laço de itens do PDF não rodou, "
        "então este guarda não mediu nada. Conserte o arranjo antes de confiar.")
    return {getattr(_it, "description", ""): _it for _it in _saida}


# Prancha 1: os dois números REAIS do cliente-41 (13,6 m² e 38,8 m).
# Prancha 2: outro imóvel do mesmo job, pra provar que o alvo é POR PRANCHA.
_PAG_1 = {
    "medicao": {"rooms_m2": 13.6, "walls_m": 38.8},
    "items": [
        _item_da_ia("Piso ceramico porcelanato", "m²",
                    "Área total medida vetorialmente: 13,6 m² (3 ambientes)"),
        _item_da_ia("Rodape em ceramica", "ml",
                    "Comprimento estimado igual ao perímetro total de paredes "
                    "medido vetorialmente (38,8 m), descontando vãos"),
        _item_da_ia("Parede de alvenaria", "m²",
                    "Estimativa: 38,8 m de paredes medidas vetorialmente × "
                    "pé-direito 2,70 m = 104,8 m² bruto"),
    ],
}
_PAG_2 = {
    "medicao": {"rooms_m2": 99.9, "walls_m": 0},
    "items": [
        _item_da_ia("Forro de gesso", "m²",
                    "Área medida da geometria do PDF: 99,9 m²"),
        _item_da_ia("Pintura de teto", "m²",
                    "Área medida vetorialmente: 13,6 m²"),
        _item_da_ia("Impermeabilizacao", "m²",
                    "Área medida vetorialmente: 113,5 m²"),
    ],
}


def test_o_call_site_do_PDF_usa_isso():
    """🪤 Guarda de CALL SITE: a função pode estar certa e nunca ser chamada.

    O laço de itens do PDF é OUTRO, separado do laço do DXF — foi por isso que
    o primeiro conserto do dia (que ligou o resgate no laço do DXF) não pegou
    o caso do cliente-41.

    Aqui o motor RODA. Cada asserto abaixo morre com uma mutação diferente:
    desligar o `if _q_pdf:`, tirar `comprimento_pdf=`, carimbar o selo no
    resgate, ou voltar a mirar na soma do job / em todas as pranchas.
    """
    itens = _motor_de_pdf([_PAG_1, _PAG_2])

    _piso = itens["Piso ceramico porcelanato"]
    assert _piso.quantity == 13.6, (
        "a linha de piso saiu com %r — o resgate pelo PDF não rodou no laço de "
        "itens do PDF. É o caso do cliente-41 de volta: o motor mediu 13,6 "
        "m², escreveu na observação e entregou a quantidade em branco."
        % _piso.quantity)

    _rodape = itens["Rodape em ceramica"]
    assert _rodape.quantity == 38.8, (
        "a linha de rodapé saiu com %r — a medição de COMPRIMENTO não chega na "
        "régua (`comprimento_pdf=`). Só a área é resgatada e todo item linear "
        "continua zerado." % _rodape.quantity)

    # 🚨 O CASO PERIGOSO, do mesmo cliente: o 38,8 existe e foi medido, mas é
    # comprimento num item de m², e o 104,8 vem de um pé-direito que a IA
    # inventou. Esta linha tem que sair zerada mesmo com o resgate ligado.
    assert itens["Parede de alvenaria"].quantity == 0, (
        "a alvenaria foi preenchida — um COMPRIMENTO virou m² e a planilha "
        "entrega área baseada num pé-direito que ninguém mediu")

    # 🩸 Regra dura nº1: preencher quantidade e carimbar "medido" são passos
    # diferentes. O resgate não pode encostar no selo.
    assert _piso.confidence.value == "estimado", (
        "o resgate promoveu o selo pra %r — quantidade preenchida por "
        "conferência de texto NÃO é medição do CAD" % _piso.confidence.value)
    assert _piso.origem == "vision_pdf", (
        "o resgate mexeu na origem (%r) — origem de geometria é o que acende "
        "o selo branco '✓ MEDIDO do CAD'" % _piso.origem)

    # 🩸 31/08 (caso cliente-14): o alvo é a medição da prancha DESTE item.
    assert itens["Forro de gesso"].quantity == 99.9, (
        "a prancha 2 mediu 99,9 m² e o item dela saiu com %r — a régua não está "
        "recebendo a medição da prancha do item"
        % itens["Forro de gesso"].quantity)
    assert itens["Pintura de teto"].quantity == 0, (
        "um item da prancha 2 foi preenchido com 13,6 m², que é a medição da "
        "prancha 1 — a régua voltou a mirar em TODAS as pranchas e preenche "
        "com o número da prancha errada, atropelando o passo 7")
    assert itens["Impermeabilizacao"].quantity == 0, (
        "um item foi preenchido com 113,5 m², que é a SOMA do job (13,6 + "
        "99,9) — número que não corresponde a nada físico voltou pra lista de "
        "alvos")


def test_sem_medicao_no_PDF_o_call_site_nao_inventa():
    """🧪 CONTROLE do guarda acima: com o resgate ligado e ZERO medição, as
    mesmas observações não podem encher linha nenhuma.

    Sem este controle, "quantidade preenchida" poderia vir de qualquer coisa —
    e o guarda de cima passaria a aprovar um motor que chuta.
    """
    _sem = {"medicao": {"rooms_m2": 0, "walls_m": 0},
            "items": _PAG_1["items"]}
    itens = _motor_de_pdf([_sem])
    for _desc, _it in itens.items():
        assert _it.quantity == 0, (
            "%r saiu com %r sem medição nenhuma do vetorial — o resgate virou "
            "confiança no texto da IA" % (_desc, _it.quantity))


def test_o_comprimento_medido_no_PDF_e_ACUMULADO():
    """🪤 O acumulador de área existia desde cedo; o de comprimento não.

    Sem ele, `comprimento_pdf` chega 0 e o rodapé nunca enche.
    """
    import io
    _b = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    corpo = io.open(os.path.join(_b, "main.py"), encoding="utf-8").read()
    assert "_pdfvec_compr_m = 0.0" in corpo, "o acumulador do comprimento sumiu"
    assert corpo.count("_pdfvec_compr_m += float(_vm.get(\"walls_m\") or 0)") >= 2, (
        "a soma não cobre os DOIS ramos da promoção (escala provada por cota e "
        "escala sem prova) — o caso do cliente-41 é o segundo")


def test_o_log_conta_o_resgate_e_nao_mente_mais_no_nome():
    """🪤 `preservados_por_pe_direito=1` foi impresso na avaliação `eve9afae`
    para um item preservado pela GEOMETRIA do PDF, com pé-direito ZERO."""
    import io
    _b = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    corpo = io.open(os.path.join(_b, "main.py"), encoding="utf-8").read()
    assert "resgate_pdf=" in corpo, "o resgate pelo PDF não vira linha de log"
    assert "preservados_por_pe_direito={" not in corpo, (
        "o rótulo mentiroso voltou: ele diz 'pé-direito' para preservação que "
        "veio da geometria do PDF")


# ═══════════════════════════════════════════════════════════════════════
# 31/08/2026 — A RÉGUA COMPARAVA CONTRA A SOMA DO JOB (caso cliente-14)
# ═══════════════════════════════════════════════════════════════════════
# `area_pdf` recebia `_pdfvec_area_m2`, que acumula página a página. Num
# projeto de 16 pranchas do MESMO imóvel (alvenaria, layout, forro e
# climatização do mesmo pavimento) isso é a mesma casa contada várias vezes:
# 741,8 m² num imóvel de 400, com a prancha de alvenaria medindo 80,5.
# A observação do item cita o número DA PRANCHA dele. 80,5 nunca bate ±1% com
# 741,8 — e o log fechou `resgate_pdf=0`, que se lê como "não havia o que
# resgatar" quando a verdade era "a régua media a coisa errada".

_OBS_FLAVIO = "Área medida da geometria do PDF: 80,5 m² (13 ambientes)"
_POR_PRANCHA = [107.7, 80.5, 166.1, 77.1, 112.0, 198.4]   # as 6 pranchas reais


def _q(**kw):
    from engine_rules import quantidade_medida_pelo_pdf
    return quantidade_medida_pelo_pdf(**kw)


def test_a_SOMA_do_job_nao_casa_com_a_prancha():
    """Reproduz o bug: é o comportamento de antes, e tem que continuar sendo
    None — o conserto não é fazer a soma casar, é oferecer o alvo certo."""
    assert _q(observacao=_OBS_FLAVIO, unidade="m²", area_pdf=741.8) is None


def test_a_medicao_POR_PRANCHA_casa():
    """O conserto: com os valores por prancha na lista, o 80,5 é resgatado."""
    assert _q(observacao=_OBS_FLAVIO, unidade="m²", area_pdf=_POR_PRANCHA) == 80.5


def test_numero_que_NAO_medimos_continua_recusado():
    """🧪 O controle que impede o conserto de virar 'aceita qualquer número'.
    Mais alvos já aumenta a chance de casar por coincidência — a tolerância de
    ±1% e a família de unidade NÃO podem ser afrouxadas junto."""
    assert _q(observacao="Área estimada: 55 m²", unidade="m²",
              area_pdf=_POR_PRANCHA) is None


def test_comprimento_num_item_de_area_continua_recusado():
    """O caso perigoso do cliente-41: a IA escreve '38,8 m de paredes' num
    item de m². O número existe e foi medido — mas é de outra família."""
    assert _q(observacao="38,8 m de paredes medidas vetorialmente", unidade="m²",
              area_pdf=_POR_PRANCHA, comprimento_pdf=[38.8]) is None


def test_fora_da_tolerancia_de_1_por_cento_continua_recusado():
    assert _q(observacao="Área: 82,0 m²", unidade="m²", area_pdf=[80.5]) is None


def test_numero_solto_continua_funcionando():
    """CONTROLE de compatibilidade: quem passa float (job de 1 página) segue
    valendo — a mudança é aditiva."""
    assert _q(observacao=_OBS_FLAVIO, unidade="m²", area_pdf=80.5) == 80.5


def test_sem_alvo_nenhum_nao_inventa():
    assert _q(observacao=_OBS_FLAVIO, unidade="m²", area_pdf=[]) is None
    assert _q(observacao=_OBS_FLAVIO, unidade="m²", area_pdf=None) is None
