# -*- coding: utf-8 -*-
""""1.200" vale MIL E DUZENTOS. Uma régua só, no servidor, pras três portas.

🩸 08/09/2026 (auditoria) — O CAMPO DE ÁREA ACEITAVA NÚMERO ERRADO CALADO.

As três portas que escrevem `user_total_area` faziam `float(...)` no que
chegava — e `float` é régua INGLESA. Medido no Chrome, na réplica exata do
campo do convite:

    "120"     ->  120     ok
    "120 m2"  -> 1202     10× errado, ACEITO em silêncio
    "1.200"   ->    1,2   1000× errado, ACEITO em silêncio

E o teto de 100.000 m² não pega nenhum dos dois: 1202 passa e 1,2 passa.

🚨 O destino desse número é `_apply_area_honesty`, que preenche piso/forro/laje
e carimba **"estimado — informado por você"**. Ou seja: o erro de digitação do
cliente sairia na planilha com a NOSSA assinatura de procedência. É a regra
dura nº1 quebrada pela via mais silenciosa que existe.

🍀 Não chegou a morder: `motor:informou-depois` tem ZERO linhas — ninguém nunca
completou o envio pelo convite. Sorte, não guarda.

🔑 NÃO NASCEU PARSER NOVO. A régua de "1.234 é mil" já existia, nasceu do MESMO
erro no financeiro e está testada (`financeiro_lote.valor_do_texto`).
`_area_do_texto` compõe: tira a unidade colada, chama o parser, aplica a banda
de área. [[feedback_nao_reimplemente_a_regua_pergunte_ao_guarda]]

🪤 E o conserto tinha que ir até a TELA: enquanto o campo fosse `type="number"`
e o JS mandasse `parseFloat`, o texto original morria na fronteira e nenhuma
régua do servidor alcançava. Por isso os testes de tela aqui embaixo.
"""
import io
import os
import re
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_MAIN = os.path.join(_BACKEND, "main.py")


def _regua():
    """Executa só o trecho da régua — importar main.py conecta em Supabase."""
    src = io.open(_MAIN, encoding="utf-8").read()
    ini = "_RX_UNIDADE_AREA = None"
    fim = "\ndef _dxf_grande_pode_seguir"
    assert src.count(ini) == 1, "a âncora de início mudou"
    i = src.index(ini)
    ns = {"__name__": "area_ns", "_AREA_PLAUSIVEL_MAX": 100_000}
    exec(compile(src[i:src.index(fim, i)], "main_area_slice", "exec"), ns)
    return ns["_area_do_texto"]


# ══════════════════════════════════════════════════════════════════════════
#  O defeito medido — os dois casos que passavam calados
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("digitado,esperado", [
    ("1.200", 1200.0),        # 🩸 float() dava 1.2 — mil vezes menor
    ("120 m2", 120.0),        # 🩸 o campo number dava 1202 — dez vezes maior
    ("1.200,50", 1200.5),
    ("120m²", 120.0),
    ("120 metros quadrados", 120.0),
])
def test_o_que_o_brasileiro_digita_e_lido_certo(digitado, esperado):
    f = _regua()
    val, err = f(digitado)
    assert err is None, "%r foi recusado: %s" % (digitado, err)
    assert val == esperado, "%r virou %r, esperado %r" % (digitado, val, esperado)


def test_o_separador_de_milhar_nao_vira_decimal():
    """CONTROLE que fixa a régua pt-BR: com vírgula, a vírgula é o decimal."""
    f = _regua()
    assert f("1.200")[0] == 1200.0
    assert f("1200")[0] == 1200.0
    assert f("1200,5")[0] == 1200.5
    assert f("1.200,50")[0] == 1200.5
    # e o ponto com 1 ou 2 casas continua sendo decimal (uso comum de teclado)
    assert f("120.5")[0] == 120.5


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLE POSITIVO — recusar tudo passaria em tudo acima
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("digitado", ["120", "120,5", "0,5", "99999"])
def test_area_valida_continua_passando(digitado):
    f = _regua()
    val, err = f(digitado)
    assert err is None and val and val > 0, (digitado, val, err)


@pytest.mark.parametrize("digitado,marca", [
    ("abc", "não parece"),
    ("0", "maior que zero"),
    ("-5", "negativ"),
    ("999999", "acima"),
    ("m²", "faltou"),
])
def test_o_que_nao_da_pra_ler_e_RECUSADO_com_motivo(digitado, marca):
    """Recusar com motivo é sempre melhor que adivinhar: o número vira
    procedência carimbada na planilha do cliente."""
    f = _regua()
    val, err = f(digitado)
    assert val is None, "%r devia ser recusado e virou %r" % (digitado, val)
    assert err and marca in err.lower(), "%r → motivo pobre: %r" % (digitado, err)


@pytest.mark.parametrize("numero,esperado", [
    (120, 120.0), (120.5, 120.5), (1200, 1200.0), (0.5, 0.5),
])
def test_a_regua_aceita_NUMERO_tambem_nao_so_texto(numero, esperado):
    """🩸 A 1ª versão deste conserto tipou o payload como SÓ texto, e a bancada
    reprovou em 7 testes.

    Não era chatice de teste: é QUEBRA DE CONTRATO. Durante o deploy, uma
    página já aberta no navegador continua mandando `parseFloat` — número. Com
    `area: str` ela tomaria 422 no meio do clique, em vez de completar a
    planilha. Trocar a régua não pode derrubar quem está no meio do caminho.
    """
    f = _regua()
    val, err = f(numero)
    assert err is None, "%r foi recusado: %s" % (numero, err)
    assert val == esperado


def test_o_payload_do_convite_aceita_os_DOIS_formatos():
    """CONTROLE de contrato, no tipo declarado: número E texto entram."""
    src = io.open(_MAIN, encoding="utf-8").read()
    i = src.index("class InformAreaPayload")
    corpo = src[i:src.index("\n\n\n", i)]
    linha = [l for l in corpo.splitlines() if l.strip().startswith("area:")]
    assert linha, "não achei a declaração do campo `area`"
    decl = linha[0]
    assert "str" in decl, "sem `str` o texto morre na fronteira: " + decl
    assert ("float" in decl or "int" in decl), (
        "sem número, a página antiga toma 422 durante o deploy: " + decl)


@pytest.mark.parametrize("vazio", ["", "   ", None])
def test_campo_vazio_e_AUSENCIA_nao_erro_e_nao_zero(vazio):
    """O campo é opcional. Vazio não pode virar erro na cara do cliente nem
    zero no banco — zero é um número, e número vira procedência."""
    f = _regua()
    assert f(vazio) == (None, None)


# ══════════════════════════════════════════════════════════════════════════
#  UMA RÉGUA SÓ — as três portas têm que chamar a mesma
# ══════════════════════════════════════════════════════════════════════════
def test_as_tres_portas_chamam_a_regua():
    """🩸 O comentário de 03/09 já registra o custo de consertar UMA porta de
    três: 'conserto que cobre uma porta de três é conserto que engana quem o
    leu'. Upload, /inform-area e /respostas-processamento escrevem o MESMO
    campo."""
    src = io.open(_MAIN, encoding="utf-8").read()
    assert src.count("_area_do_texto(") >= 4, (
        "esperado: a definição + as 3 portas — achei %d"
        % src.count("_area_do_texto("))

    # 🪤 A 1ª versão deste guarda varria o arquivo INTEIRO e acusou um float()
    # legítimo dentro do process_job — ali o valor vem do BANCO, já passado pela
    # régua na entrada. Converter número que já é número não é o defeito.
    # O defeito é converter o que o CLIENTE mandou. Então a peneira olha só as
    # três funções que recebem da requisição.
    import ast

    _PORTAS = {"process_files", "inform_project_area", "respostas_processamento"}
    arvore = ast.parse(src)
    ruins = []
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if no.name not in _PORTAS:
            continue
        for c in ast.walk(no):
            if not (isinstance(c, ast.Call) and getattr(c.func, "id", "") == "float"):
                continue
            alvo = ast.unparse(c)
            if any(k in alvo for k in ("payload.area", "user_total_area",
                                       "area_total", 'body.get("area')):
                # float(_area_val or 0) é o resultado JÁ passado pela régua
                if "_area_val" in alvo or "_ar_v" in alvo:
                    continue
                ruins.append("%s:%s %s" % (no.name, c.lineno, alvo[:70]))
    assert not ruins, (
        "porta convertendo o texto do cliente com float() em vez da régua: %s"
        % ruins)


def test_a_regua_nao_foi_reescrita_aqui():
    """🪤 Guarda de causa-raiz: se alguém reimplementar a conversão dentro de
    `_area_do_texto` em vez de chamar o parser do financeiro, as duas réguas
    voltam a poder divergir — que é como o bug do financeiro nasceu."""
    src = io.open(_MAIN, encoding="utf-8").read()
    i = src.index("def _area_do_texto")
    corpo = src[i:src.index("\ndef ", i + 10)]
    assert "valor_do_texto" in corpo, "a régua canônica não está sendo chamada"
    assert 'replace(".", "")' not in corpo and "rpartition" not in corpo, (
        "a lógica de milhar foi copiada pra cá em vez de chamada")


# ══════════════════════════════════════════════════════════════════════════
#  A TELA — o texto tem que CHEGAR no servidor
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("arquivo,campo", [
    ("dashboard.html", "project-area"),
    ("revisao.html", "convite-area-input"),
])
def test_o_campo_nao_e_type_number(arquivo, campo):
    """🪤 `type="number"` MUTILA antes de qualquer régua: o navegador entrega
    "1202" pra quem digitou "120 m2". Nenhum conserto de servidor alcança o que
    o campo já destruiu."""
    html = io.open(os.path.join(_RAIZ, arquivo), encoding="utf-8").read()
    m = re.search(r"<input[^>]*id=\"%s\"[^>]*>" % re.escape(campo), html)
    assert m, "não achei o campo %s em %s" % (campo, arquivo)
    tag = m.group(0)
    assert 'type="number"' not in tag, tag
    assert 'inputmode="decimal"' in tag, (
        "sem inputmode o celular abre teclado de letras: " + tag)


@pytest.mark.parametrize("arquivo,trecho", [
    ("dashboard.html", "params.user_total_area"),
    ("revisao.html", "body: JSON.stringify({ area:"),
])
def test_a_tela_manda_TEXTO_nao_numero(arquivo, trecho):
    """CONTROLE da causa: converter no JS é converter com régua inglesa —
    parseFloat('1.200') = 1.2 e o servidor nunca fica sabendo."""
    html = io.open(os.path.join(_RAIZ, arquivo), encoding="utf-8").read()
    # 🪤 TIRA OS COMENTÁRIOS ANTES DE OLHAR. A 1ª versão reprovou por causa do
    # comentário que eu mesmo escrevi explicando por que parseFloat saiu — foi
    # a terceira vez no dia que um guarda meu confundiu texto citado com código.
    codigo = re.sub(r"//[^\n]*", "", html)
    i = codigo.index(trecho)
    # 🪤 Só o que vem ANTES do envio. A 2ª versão pegava 400 caracteres pra
    # frente também e reprovou por causa do `parseFloat` do PÉ-DIREITO, que é
    # outro campo e está certo: a faixa dele é 1,8 a 8 m, onde não existe
    # separador de milhar. Peneira larga acusa o inocente e treina a ignorar.
    volta = codigo[max(0, i - 400):i + len(trecho)]
    assert "parseFloat" not in volta, (
        "a tela ainda converte a ÁREA antes de mandar:\n" + volta[-280:])
