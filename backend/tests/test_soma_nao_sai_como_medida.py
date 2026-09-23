# -*- coding: utf-8 -*-
"""Quantidade que veio de SOMA não sai carimbada como medida (regra dura nº1).

🩸 18/09/2026. O prompt do motor manda, com todas as letras:

    "A quantidade do item TEM que bater com o número extraído. Se você
     multiplicou, somou ou fez qualquer cálculo além de copiar o valor,
     NÃO é confirmado."

E o modelo, a temperature 0.7, obedece mais ou menos metade das vezes. Ficaram
na planilha de gente linhas dizendo "✓ MEDIDO" com a própria observação
declarando "Fonte: soma dos INSERTs: tipo1=5 + tipo2=1 = 6 un".

🩸🩸 E ESTE ARQUIVO JÁ NASCEU ERRADO UMA VEZ. A revisão adversarial achou dois
defeitos na 1ª versão, e os dois são de método:

  1. **A régua prendia a ORDEM DAS PALAVRAS, não o fato.** Exigia "soma"
     grudado no "Fonte:" — e quem escolhe a ordem das palavras é o mesmo modelo,
     no mesmo sorteio. "Fonte: soma de todos os tipos..." caía;
     "Fonte: CONTAGEM DE BLOCOS — soma de todos os tipos..." escapava. Mesma
     peça, mesmo desenho, duas rodadas. Eu não tinha matado o sorteio: tinha
     mudado ele de lugar. Medido: pegava 89 e deixava passar 57 — 39% da
     população real. A régua nova pega 161.

  2. **Nenhum teste EXECUTAVA o rebaixamento.** Os seis guardas do lado do motor
     liam `main.py` como texto ou como AST. A revisão provou o buraco movendo o
     bloco pra depois de o item ser montado — código morto, e os 19 guardas
     seguiram verdes. É a doença da miniatura: cinco meses de código
     inalcançável atrás de um docstring que jurava funcionar.

🔑 Por isso agora a decisão inteira mora em `engine_rules.selo_apos_regra_da_soma`,
que o guarda CHAMA — e o que sobra no `main.py` é uma linha, cuja POSIÇÃO é
cobrada à parte (`test_a_trava_roda_ANTES_de_o_item_ser_montado`).

⏭️ Decisão do Pedro (18/09): vale DAQUI PRA FRENTE. O que já foi entregue fica.
"""
import ast
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine_rules import (  # noqa: E402
    a_fonte_declarada_e_uma_soma as fonte_e_soma,
    selo_apos_regra_da_soma as aplicar,
)

_FONTE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "main.py")


# ══════════════════════════════════════════════════════════════════════════
#  1. O REBAIXAMENTO, EXECUTADO — o que faltava na 1ª versão
# ══════════════════════════════════════════════════════════════════════════
def test_soma_carimbada_como_medida_e_REBAIXADA_de_verdade():
    """Roda a decisão inteira e olha o que sai. Não lê fonte, não lê AST."""
    conf, obs, mexeu = aplicar(
        "confirmado",
        "Fonte: soma dos INSERTs dos blocos 'Cap' tipos 1 a 4: "
        "tipo1=2, tipo2=2, tipo3=1, tipo4=1 = 6 un total.")
    assert conf == "estimado", "a soma continuou saindo como medida"
    assert mexeu is True
    assert obs.startswith("⚠ SOMA, não leitura direta"), \
        "o cliente não fica sabendo por que a linha caiu"
    assert "tipo1=2" in obs, "a observação original foi perdida no caminho"


def test_contagem_DIRETA_sai_intacta():
    """O outro lado: a trava não pode roubar selo legítimo. Devolve tudo igual,
    inclusive sem encostar na observação."""
    original = "Fonte: 24 INSERTs do bloco 'Caixa Sifonada Montada_150x150x50'"
    conf, obs, mexeu = aplicar("confirmado", original)
    assert (conf, obs, mexeu) == ("confirmado", original, False)


def test_a_trava_NUNCA_promove():
    """Item que já era estimado sai estimado, mesmo declarando soma. Promover é
    o pior modo de errar na regra nº1 — ontem a promoção automática teria
    carimbado BRANCO no número ERRADO (169 em vez de 171)."""
    for obs in ("Fonte: soma dos INSERTs: tipo1=5 + tipo2=1 = 6 un",
                "Fonte: 24 INSERTs do bloco X"):
        conf, _o, mexeu = aplicar("estimado", obs)
        assert conf == "estimado", "a trava PROMOVEU um item"
        assert mexeu is False, "mexeu em quem já estava estimado"


def test_a_observacao_de_quem_JA_era_estimado_nao_e_poluida():
    """Há muito mais item estimado-com-soma do que confirmado-com-soma. Prefixar
    o aviso neles encheria a planilha de ⚠ onde a regra já foi obedecida."""
    original = "Fonte: soma dos INSERTs: tipo1=5 + tipo2=1 = 6 un"
    _c, obs, _m = aplicar("estimado", original)
    assert obs == original


# ══════════════════════════════════════════════════════════════════════════
#  2. A RÉGUA PEGA O FATO, não a ordem das palavras
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("obs", [
    # o que a régua ESTREITA já pegava
    "Fonte: soma dos INSERTs dos blocos 'Cap' tipos 1 a 4: tipo1=2, tipo2=2 = 6 un.",
    "Fonte: somatório de esquadrias POR_ELEVADOR 80x210cm e 90x210cm",
    # 🩸 o que ela DEIXAVA PASSAR — todos reais, todos em confirmado
    "Fonte: CONTAGEM DE BLOCOS — soma de todos os tipos de 'Montante retangular': "
    "tipo1(124)+tipo2(109)+tipo3(87)",
    "Fonte: blocos 'Sifão de Uso Geral' tipo 1 (2 un) + tipo 2 (2 un) = 4 un.",
    "Fonte: textos de ambiente do layer 'TEXTO': ESTAR 18,65 + 20,10 + 28,95 = 172,10 m².",
    "Fonte: 8 INSERTs do bloco DECA_CUBA: IDs 544699(4) + 547524(3) + 547520(1) = 8 un.",
    "Fonte: bloco 'Árvore nova': IDs 1255699(4) + V53(1) = 5 un.",
    "Fonte: 60 INSERTs do bloco 'Árvores de Folhas Caducas 26' (40+10+7+3)",
    # 🩸 este estava em `confirmado` no banco e a régua NÃO pegava: depois do
    # "+" vem aspa e o número seguinte fica longe da janela. São dois blocos
    # DIFERENTES (PISCINA e FACHADA) somados — exatamente o caso que a regra
    # existe pra pegar.
    "Fonte: bloco 'PORTA - PADRÃO-2100514-PISCINA' (1 un) + "
    "'PORTA - PADRÃO-2100514-FACHADA' (1 un) = 2 un.",
    "Fonte: áreas dos ambientes (Mesão 40,32 + Sala de Espera 17,37 + Copa 9,80)",
])
def test_a_regua_pega_a_SOMA_em_qualquer_redacao(obs):
    """O fato é o mesmo; o que muda é como o modelo escreveu. Prender a redação
    seria trocar um sorteio por outro."""
    assert fonte_e_soma(obs) is True


@pytest.mark.parametrize("obs", [
    "Fonte: 24 INSERTs do bloco 'Caixa Sifonada Montada_150x150x50_7 Entradas'",
    "Fonte: 156 INSERTs do bloco 'TA2FN110'. Atributos indicam circuitos W1.3",
    "Fonte: 698 INSERTs do bloco 'Forro' no DXF. Nome do bloco é genérico",
    "Peso lido diretamente do quadro de ferragens da prancha (MEDIDO)",
    "",
    None,
])
def test_contagem_direta_NAO_e_confundida_com_soma(obs):
    assert fonte_e_soma(obs) is False


@pytest.mark.parametrize("obs,porque", [
    ("Fonte: comprimento total do layer 'AR-ALV' = 177.26 m. Verificar "
     "sobreposição com demais layers de alvenaria antes de somar ao total.",
     "a palavra está numa RESSALVA, depois do ponto — não é a procedência"),
    ("Fonte: comprimento do layer 'W-ELETRODUTO' = 1,38 m (fragmento de "
     "detalhe — não somado para evitar dupla contagem).",
     "diz explicitamente que NÃO somou"),
    ("Fonte: 3 INSERTs do bloco '1 tomada monofásica 2P+T 10A (2.2m)'",
     "'2P+T' é nome de produto, não adição"),
    ("Fonte: variação de nível na laje (cotas +792.63, +795.57, +796.21)",
     "'+792.63' é sinal de cota, não parcela somada"),
    # 🩸 vindo da sabotagem S09: sem exigir número dos DOIS lados, um "+" que
    # faz parte de nomenclatura elétrica viraria soma. Real: os blocos de tomada
    # do acervo citam "2P+T" e "3P+N+T".
    ("Fonte: 4 INSERTs do bloco '1 tomada trifásica 3P+N+T 20A (parede)'",
     "'3P+N+T' é nomenclatura elétrica — não há número depois do '+'"),
    # 🩸 vindo da S04: a palavra de soma numa ressalva que NÃO está negada, mas
    # está fora da oração da fonte (depois do ponto).
    ("Fonte: 12 INSERTs do bloco 'QF6'. A soma das áreas do layer de hachura "
     "serve só de referência cruzada.",
     "a palavra está numa frase POSTERIOR — a fonte declarada é a contagem"),
    # 🩸 22/09/2026, job 64fa324b — A GEOMETRIA ELEMENTAR DERRUBAVA O SELO.
    # O cliente mandou 1 DWG de estrutura e informou o pé-direito. O motor
    # mediu (3.716 m de parede, 207,84 m² de área, pilar por retângulo
    # fechado) e a planilha saiu com 24 linhas COM número e ZERO medidas.
    # Uma das travas era esta régua: o "+" que ela lia como parcela é o do
    # PERÍMETRO. As parcelas aqui são LADOS DA MESMA PEÇA, não itens contados.
    ("Estimado. 1 pilar × perímetro 2×(0,46+0,46) m × 3,20 m = 5,89 m². "
     "Fonte: geometria layer FO-Pilares (1 retângulo 46×46 cm medido).",
     "o '+' é a fórmula do perímetro — medir É fazer conta"),
    ("Fôrma por metro linear = fundo + 2 faces = 0,14 + 2×0,40 = 0,94 m/m",
     "'fundo + 2 faces' é a seção da viga, não duas parcelas contadas"),
    ("Área de parede = perímetro (3,50 + 4,20) × 2 × pé-direito 2,80 m",
     "perímetro de ambiente multiplicado pelo pé-direito informado"),
])
def test_o_que_PARECE_soma_e_nao_e(obs, porque):
    """🪤 Os quatro padrões de falso positivo que sobraram depois de conferir
    14 amostras reais uma a uma. Cada um custaria um selo legítimo."""
    assert fonte_e_soma(obs) is False, porque


def test_a_excecao_vale_por_OCORRENCIA_e_nao_pela_observacao():
    """Um item que cita 'tomada 2P+T' E soma tipos de verdade tem que cair
    mesmo assim — senão o nome do produto vira escudo pra soma."""
    assert fonte_e_soma(
        "Fonte: blocos '1 tomada 2P+T 10A': tipo1=4 + tipo2=2 = 6 un.") is True


# ══════════════════════════════════════════════════════════════════════════
#  3. A LIGAÇÃO no motor — e a POSIÇÃO dela
# ══════════════════════════════════════════════════════════════════════════
def _process_job():
    arv = ast.parse(io.open(_FONTE, encoding="utf-8").read())
    return next(n for n in ast.walk(arv)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == "process_job")


def test_o_motor_CHAMA_a_regra():
    chamadas = {c.func.id for c in ast.walk(_process_job())
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "_regra_soma" in chamadas, "o motor parou de aplicar a regra da soma"


def test_a_trava_roda_ANTES_de_o_item_ser_montado():
    """🚨 O guarda que a revisão adversarial provou que faltava.

    Ela moveu o bloco pra depois de `dxf_items.append(item)` — mesma função,
    mesmo texto, byte a byte — e os 19 guardas ficaram VERDES. A partir dali
    `conf` e `obs_raw` já foram copiados pro item: a trava roda, rebaixa
    variáveis mortas, e a linha sai ✓ MEDIDO com a soma declarada na observação.

    🔑 Presença não é consequência. O que prende o defeito é a ORDEM.

    🪤 Duas armadilhas que este guarda já caiu enquanto era escrito:

      · comparar com o PRIMEIRO `dxf_items.append` da função reprova à toa — o
        primeiro é a retomada por CHECKPOINT (restaura item de uma rodada
        anterior, sem passar por IA), e esse não deve mesmo passar pela trava;
      · comparar com o PRÓXIMO `BudgetItem` depois da trava é frouxo — movendo
        a trava pra depois do item do CAD, o "próximo" vira o do PDF, 1.000
        linhas abaixo, e a asserção passa com o defeito presente.

    Por isso ele cobra o BLOCO: o item protegido tem que nascer na mesma lista
    de instruções em que a trava roda, e DEPOIS dela.

    🩸🩸 E A 2ª REVISÃO DERRUBOU ESTE GUARDA TAMBÉM, com três mutações que
    passaram VERDES nos 31 testes — todas deixando a trava presente, alcançável
    e INÓCUA:

      · `_c2, _o2, _somou = _regra_soma(conf, obs_raw)` — retorno no lixo;
      · a trava envolvida num `if os.getenv(...)`, "pra medir antes";
      · uma chamada-ISCA cedo e a de verdade depois do item (o `min()` mascarava).

    O controle (apagar a trava) reprovava. Ou seja: a bancada pegava AUSÊNCIA, e
    só isso. Presença não é consequência — de novo, e agora em três formas.
    Por isso este guarda passou a cobrar QUATRO coisas: uma única chamada, o
    retorno indo para `conf`/`obs_raw`, a chamada INCONDICIONAL, e a ordem.
    """
    fn = _process_job()

    def _usa_a_decisao(no):
        return (isinstance(no, ast.Call) and getattr(no.func, "id", "") == "BudgetItem"
                and {"conf", "obs_raw"} <= {n.id for n in ast.walk(no)
                                            if isinstance(n, ast.Name)})

    def _contem(no, teste):
        return any(teste(x) for x in ast.walk(no))


    travas = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
              and getattr(n.func, "id", "") == "_regra_soma"]
    assert travas, "a trava sumiu de process_job"
    assert len(travas) == 1, (
        "há mais de uma chamada da trava — uma delas pode ser isca, e a que "
        "vale pode estar depois do item")
    linha_trava = max(t.lineno for t in travas)

    # (1) o RETORNO tem que ir pra `conf` e `obs_raw`, senão a trava decide no vácuo
    destinos = [a for a in ast.walk(fn) if isinstance(a, ast.Assign)
                and isinstance(a.value, ast.Call)
                and getattr(a.value.func, "id", "") == "_regra_soma"]
    assert destinos, "a trava não é atribuída a nada — o resultado morre ali"
    alvos = set()
    for a in destinos:
        for t in a.targets:
            alvos |= {n.id for n in ast.walk(t) if isinstance(n, ast.Name)}
    assert {"conf", "obs_raw"} <= alvos, (
        "o retorno da trava não volta pra `conf`/`obs_raw` — ela roda, decide, "
        f"e o item é montado com o selo velho (foi para {sorted(alvos)})")

    # (2) a chamada tem que ser INCONDICIONAL dentro do laço: um `if` em volta
    #     (env, flag, "só pra medir") desliga a regra dura nº1 sem deixar rastro
    # 🪤 "estar dentro de um if" não serve como régua: numa função de 3.000
    # linhas TUDO está. O que denuncia um gate de flag é um `if` que envolve a
    # TRAVA e NÃO envolve o item — o item continua sendo montado, a trava é que
    # fica opcional.
    gates = [n for n in ast.walk(fn) if isinstance(n, ast.If)
             and _contem(n, lambda x: x is destinos[0])
             and not _contem(n, _usa_a_decisao)]
    assert not gates, (
        "a trava está atrás de um `if` que não cobre o item (linha %d) — regra "
        "dura nº1 não pode ficar atrás de flag: quem rodar sem ela entrega soma "
        "como medida" % gates[0].lineno if gates else "")

    # o laço MAIS INTERNO que contém a trava — é dentro dele que o item nasce
    lacos = [n for n in ast.walk(fn) if isinstance(n, (ast.For, ast.While))
             and _contem(n, lambda x: x in travas)]
    assert lacos, "a trava não está dentro do laço que processa os itens"
    laco = min(lacos, key=lambda n: (n.end_lineno or 0) - n.lineno)

    itens = [n.lineno for n in ast.walk(laco) if _usa_a_decisao(n)]
    assert itens, ("a trava roda num laço que não monta item nenhum — ela está "
                   "rebaixando variável que ninguém lê")
    assert all(li > linha_trava for li in itens), (
        "o item é montado ANTES da trava (trava na linha %d, item na %d): ela "
        "rebaixa variável morta e o selo errado vai pro banco"
        % (linha_trava, min(itens)))


def test_o_selo_rebaixado_NAO_e_re_promovido_pelo_cross_check():
    """🪤 A armadilha que o próprio código documenta: o cross-check opt-in
    promove estimado → confirmado, e sem a marca ele desfaria este conserto no
    MESMO laço. Duas regras brigando já custou um conserto à casa.

    🩸 A 1ª versão media PROXIMIDADE DE TEXTO: pegava o índice da chamada e
    exigia a marca nos 200 caracteres seguintes. Isso prova que as duas frases
    estão perto no arquivo — não que a marca CHEGA VIVA no `if` que promove. A
    revisão adversarial derrubou com uma mutação que nem é bug, é arrumação:
    mover o bloco da trava 50 linhas pra cima (byte a byte igual, e legal,
    porque `obs_raw` já existe lá). A partir dali o `_rebaixado_pela_fonte =
    False` roda DEPOIS e apaga a marca — e o cross-check re-promove justamente
    o item que a trava rebaixou. 31 testes verdes. Hoje o dano é latente (o
    cross-check é opt-in, desligado); o guarda é que era cego.

    🔑 Agora a ordem é cobrada em AST, nas três pontas: zerar a marca ANTES de
    marcar, e marcar ANTES de ler."""
    fn = _process_job()

    def _linhas(teste):
        return sorted(n.lineno for n in ast.walk(fn) if teste(n))

    def _atribui(valor):
        return lambda n: (isinstance(n, ast.Assign)
                          and isinstance(n.value, ast.Constant)
                          and n.value.value is valor
                          and any(getattr(t, "id", "") == "_rebaixado_pela_fonte"
                                  for t in n.targets))

    zera = _linhas(_atribui(False))
    marca = _linhas(_atribui(True))
    le = _linhas(lambda n: isinstance(n, ast.Name)
                 and n.id == "_rebaixado_pela_fonte" and isinstance(n.ctx, ast.Load))
    trava = _linhas(lambda n: isinstance(n, ast.Call)
                    and getattr(n.func, "id", "") == "_regra_soma")

    assert zera and marca and le and trava, (
        "sumiu alguma ponta: zera=%s marca=%s lê=%s trava=%s"
        % (bool(zera), bool(marca), bool(le), bool(trava)))
    assert max(zera) < min(marca), (
        "o `_rebaixado_pela_fonte = False` roda DEPOIS de alguém marcar — a "
        "marca é apagada (zera na %d, marca na %d)" % (max(zera), min(marca)))
    assert max(marca) < min(le), (
        "alguém LÊ a marca antes de a trava poder marcá-la — o cross-check "
        "re-promove o item rebaixado (marca na %d, lê na %d)"
        % (max(marca), min(le)))
    assert max(zera) < min(trava) < min(le), (
        "a trava está fora da janela em que a marca vale: ela tem que rodar "
        "DEPOIS do zera e ANTES de quem lê (zera %d, trava %d, lê %d)"
        % (max(zera), min(trava), min(le)))

    # 🩸 E tem que ser a NOSSA marca. A 1ª versão deste bloco só exigia que
    # ALGUÉM marcasse — e há outras marcações no mesmo laço (as regras de
    # carimbo e de anotação). Apagar justamente a da soma passava verde: a
    # sabotagem S16 sobreviveu por isso. Agora o `if _somou:` tem que marcar.
    ramos = [n for n in ast.walk(fn) if isinstance(n, ast.If)
             and isinstance(n.test, ast.Name) and n.test.id == "_somou"]
    assert ramos, "sumiu o `if _somou:` que liga a trava à marca"
    assert any(_atribui(True)(x) for r in ramos for x in ast.walk(r)), (
        "o ramo `if _somou:` não marca `_rebaixado_pela_fonte` — o cross-check "
        "re-promove exatamente o item que a trava acabou de rebaixar")


def test_a_regra_NAO_foi_reimplementada_no_motor():
    """A decisão mora em engine_rules. Uma segunda cópia aqui divergiria com o
    tempo — é o defeito das duas réguas do retry (16/09)."""
    fn = _process_job()
    corpo = "".join(ast.dump(n) for n in fn.body)
    assert "SOMA, não leitura direta" not in corpo, \
        "o texto do aviso voltou pro motor — régua duplicada"


# ══════════════════════════════════════════════════════════════════════════
#  22/09/2026 — a fórmula de dimensão não é soma de parcelas
#  🔑 O que separa as duas é a MULTIPLICAÇÃO COLADA no termo somado. Os
#     controles positivos abaixo não têm multiplicação nenhuma e continuam
#     caindo: sem eles, a exceção viraria porta aberta pra qualquer "+".
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("obs, porque", [
    ("ESTAR 18,65 + 20,10 + 12,30 = 51,05 m²",
     "áreas de AMBIENTES somadas — parcelas de verdade, sem multiplicação"),
    ("Fonte: soma dos INSERTs: tipo1=5 + tipo2=1 = 6 un",
     "contagem montada de duas parcelas, não leitura direta"),
    ("Fonte: (1 un) + 'PORTA - PADRÃO-2100514-FACHADA'",
     "parcelas de contagem com nome de bloco no meio"),
])
def test_CONTROLE_soma_SEM_multiplicacao_continua_caindo(obs, porque):
    assert fonte_e_soma(obs) is True, porque


def test_o_selo_do_pilar_medido_SOBREVIVE_a_regra_da_soma():
    """Ponta a ponta: o item que o motor mediu por geometria sai MEDIDO.

    🩸 Era esta linha que chegava laranja ao cliente do job 64fa324b, com a
    conta inteira escrita na observação e o retângulo do pilar medido no
    layer. A trava da soma a derrubava pelo '+' do perímetro."""
    obs = ("Estimado. 1 pilar × perímetro 2×(0,46+0,46) m × 3,20 m = 5,89 m². "
           "Pé-direito informado por você = 3,20 m. Fonte: geometria layer "
           "FO-Pilares (1 retângulo 46×46 cm medido).")
    conf, nova_obs, rebaixou = aplicar("confirmado", obs)
    assert rebaixou is False, "geometria medida não pode cair pela régua da soma"
    assert conf == "confirmado"
    assert "SOMA, não leitura direta" not in nova_obs, (
        "a observação do cliente não pode ganhar o aviso de soma")
