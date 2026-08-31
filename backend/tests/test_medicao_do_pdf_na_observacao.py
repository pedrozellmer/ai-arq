# -*- coding: utf-8 -*-
"""O motor mediu o PDF, escreveu o número na linha e deixou a quantidade zero.

🚨 26/08/2026, caso **Construtora Mr** — cliente do dia, primeiro projeto,
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
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine_rules import quantidade_medida_pelo_pdf as q  # noqa: E402

# o que o motor vetorial mediu no PDF do Construtora Mr
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


def test_o_piso_do_Construtora_Mr_para_de_sair_zerado():
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
    Construtora Mr a área (13,6) e o comprimento (38,8) são diferentes, então a
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


def test_o_call_site_do_PDF_usa_isso():
    """🪤 Guarda de CALL SITE: a função pode estar certa e nunca ser chamada.

    O laço de itens do PDF é OUTRO, separado do laço do DXF — foi por isso que
    o primeiro conserto do dia (que ligou o resgate no laço do DXF) não pegou
    o caso do Construtora Mr.
    """
    import io
    _b = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fonte = io.open(os.path.join(_b, "main.py"), encoding="utf-8").read()
    corpo = chr(10).join(l for l in fonte.split(chr(10))
                         if not l.strip().startswith("#"))
    assert "_quantidade_medida_pelo_pdf(" in corpo, (
        "a função existe e nunca é chamada no caminho do PDF")
    i = corpo.find("_quantidade_medida_pelo_pdf(")
    # 🪤 A janela olha ANTES e DEPOIS da chamada: os alvos por prancha são
    # montados nas linhas acima dela. Uma janela só pra frente não os vê e o
    # guarda reprova código certo (aconteceu comigo em 31/08).
    # 🪤 DUAS janelas, de propósito. A de trás vê os alvos por prancha, que são
    # montados nas linhas acima da chamada. A da frente é a que checa "o resgate
    # não encosta no selo" — e ela TEM que continuar sendo só pra frente:
    # alargar pra trás faz ela pegar o `conf = "estimado"` do código anterior e
    # reprovar código certo (aconteceu comigo em 31/08).
    antes = corpo[max(0, i - 700):i]
    janela = corpo[i:i + 420]
    assert "area_pdf=" in janela and "comprimento_pdf=" in janela, (
        "chamada sem as medições do vetorial — sem elas não há o que conferir "
        "e a função viraria confiança no texto")
    # 🩸 31/08 (passo 6): os alvos passaram a ser as medições POR PRANCHA. A
    # soma do job não corresponde a nada físico em projeto multi-página (mesma
    # casa contada em cada disciplina), e comparar contra ela fazia a régua
    # NUNCA casar — o caso Flavio fechou com `resgate_pdf=0` tendo medição.
    # O assert antigo cobrava a string `area_pdf=_pdfvec_area_m2`; agora cobra
    # o que importa: que os valores por prancha cheguem à régua.
    assert "_pdfvec_por_prancha" in antes or "_pdfvec_por_prancha" in janela, (
        "a régua voltou a comparar só contra a SOMA do job — em multi-página "
        "ela nunca casa, e o resgate morre em silêncio")
    assert "_pdfvec_area_m2" in janela and "_pdfvec_compr_m" in janela, (
        "sumiu a soma da lista de alvos — ela ainda vale pro job de 1 página")
    assert "conf" not in janela.replace("comprimento_pdf", ""), (
        "o resgate está encostando no selo — preencher quantidade e carimbar "
        "'medido' são passos diferentes (regra dura nº1)")


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
        "escala sem prova) — o caso do Construtora Mr é o segundo")


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
# 31/08/2026 — A RÉGUA COMPARAVA CONTRA A SOMA DO JOB (caso Flavio)
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
    """O caso perigoso do Construtora Mr: a IA escreve '38,8 m de paredes' num
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
