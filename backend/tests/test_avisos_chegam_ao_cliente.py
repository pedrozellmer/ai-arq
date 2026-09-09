# -*- coding: utf-8 -*-
"""O aviso que explica a falha tem que CHEGAR — e ser verdade.

🚨 24/08/2026, caso cliente-19 (job e1c48ed7). Pedro perguntou: *"e quando morrer,
temos que explicar isso para os clientes né"*. A gente explicava. Mal.

Ele mandou 7 pranchas; 3 morreram (as DUAS de arquitetura entre elas). O motor
gerou 7 avisos. Três defeitos, todos confirmados no banco:

 1. O e-mail mandava `warnings[:2]` — os dois PRIMEIROS, na ordem em que o motor
    calhou de gerar. Saíram "leitura incompleta" e "usamos o leitor alternativo".
    O terceiro, que nunca saiu, era "⚠ 3 prancha(s) não entraram nesta planilha".
    O aviso que explicava metade do projeto sumido ficou só na tela — e só 1 de
    44 clientes volta ao site (medido em 08/08).

 2. O aviso do corte dizia "Reprocessar pode completar a planilha". Conselho
    IMPOSSÍVEL: na prancha de elétrica dele o corte aconteceu nas 3 leituras
    (162, 156, 112 itens). O reprocesso muda ONDE o corte cai, não SE cai — e a
    terceira deu MENOS. Gastaria o único reprocesso grátis dele por nada.

 3. Os avisos citavam '4366-EL-E_libredwg.dxf'. Ele enviou '4366-EL-E.dwg'. O
    "_libredwg" é artefato NOSSO. Ele procuraria na pasta um arquivo inexistente.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import re

import pytest  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, _BACKEND)

import main  # noqa: E402


_AVISOS_DO_CLIENTE_19 = [
    "A leitura da prancha '4366-EL-E.dwg' ficou INCOMPLETA: ela tem itens demais",
    "Usamos o leitor alternativo nesta prancha",
    "⚠ 3 prancha(s) não entraram nesta planilha",
    "Escala assumida por padrão em 1 prancha",
    "⚠ 2 itens sem unidade reconhecida",
    "Blocos repetidos foram agrupados",
    "✅ Escala conferida pelas cotas",
]


class _ItemFalso(object):
    """O minimo que `_build_reading_diagnostic` le de um item."""

    def __init__(self, confianca):
        self.confidence = confianca
        self.origem = "cad"


def _diagnostico_com(avisos):
    """Monta o bloco 'Como lemos o seu projeto' - a funcao REAL do e-mail."""
    from models import Confidence as _Conf
    itens = [_ItemFalso(_Conf.CONFIRMADO), _ItemFalso(_Conf.ESTIMADO)]
    projeto = type("ProjetoFalso", (), {"warnings": list(avisos)})()
    bloco = main._build_reading_diagnostic(itens, 0, 1, "arquitetura", projeto)
    assert bloco, "o bloco de diagnostico nem foi montado - o e-mail saiu mudo"
    return bloco


def _avisos_no_email(bloco):
    """Os avisos que o cliente REALMENTE le, na ordem em que sairam."""
    import html as _hd
    saiu = []
    for pedaco in bloco.split("<br>&bull;")[1:]:
        texto = pedaco.split("</div>")[0].strip()
        if texto.startswith("<i>e mais"):
            continue
        saiu.append(_hd.unescape(texto))
    return saiu


def _e_mais_no_email(bloco):
    """Quantos avisos o e-mail ANUNCIOU que ficaram de fora — None se nao anunciou."""
    m = re.search(r"e mais (\d+) aviso\(s\)", bloco)
    return int(m.group(1)) if m else None


# Avisos neutros de enchimento, pra a fixture VARIAR de tamanho: o teto de 6 so
# aparece em len==7, e 3/4/5/6 avisos (a faixa comum) nao eram testados por
# ninguem neste arquivo.
_NEUTROS_EXTRA = [
    "Camada 'COTAS' foi ignorada na prancha %d" % k for k in (1, 2, 3, 4, 5)
]
_POOL_12 = _AVISOS_DO_CLIENTE_19 + _NEUTROS_EXTRA

_TETO = 6



def _main():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _sem_o_que_e_removido(src: str) -> str:
    """Tira as strings que o código está REMOVENDO, não enviando.

    🪤 3ª vez hoje que um guarda meu tropeça em contexto: primeiro a docstring
    que CITA a frase proibida pra explicar por que ela saiu; depois o prompt do
    chat que a PROÍBE; agora o `.replace("<frase velha>", "<frase nova>")` que a
    apaga dos avisos herdados de jobs antigos.

    Em todos os três, a frase está no arquivo justamente porque alguém a está
    combatendo. Um guarda que não distingue isso me empurra a apagar a defesa
    pra calar o alarme — o oposto do que ele existe pra fazer."""
    import re as _re
    # 🪤 `\s` ja casa quebra de linha — nao preciso de escape nenhum aqui,
    # e foi justamente um escape que quebrou este arquivo na 1a tentativa.
    return _re.sub(r'\.replace\(\s*"[^"]*"', '.replace(<removida>', src)


def _sem_comentarios(src: str) -> str:
    """🪤 O primeiro teste destes reprovou por um motivo bobo e revelador: eu
    CITEI a frase errada dentro do comentário que explica por que ela saiu. Um
    guarda que não separa comentário de mensagem viva ou dá alarme falso, ou
    (pior) me faria apagar a documentação pra calar o alarme."""
    _NL = chr(10)
    return _NL.join(
        l for l in src.splitlines() if not l.strip().startswith("#"))


# ══════════════════════════════════════════════════════════════════════════
#  1. Nada de aviso descartado calado no e-mail
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("quantos", [1, 3, 4, 5, 6, 7, 12])
def test_o_email_nao_corta_mais_nos_dois_primeiros(quantos):
    """🩸 O defeito de 24/08 em pessoa: com os 7 avisos do cliente-19, o e-mail
    mandava os DOIS PRIMEIROS na ordem crua do motor.

    🪤 06/09/2026 — ESTE GUARDA ERA CEGO. Ele proibia a string `or [])[:2]:`.
    Reescrevi o mesmo corte com `or list()` no lugar de `or []`: o cliente
    voltava a receber 2 avisos de 7, sem anúncio nenhum, e ele passou verde.
    Agora monta o e-mail e conta o que saiu.

    🪤 07/09/2026 — e AINDA era fixture de ponto único: só `len(avisos)==7`, o
    único tamanho em que o teto de 6 aparece. Um corte em `[:1]`, `[:3]` ou um
    `break` no primeiro aviso passava verde para 3, 4, 5 e 6 avisos — que é a
    faixa comum. Agora o tamanho é a dimensão que varia, e o guarda cobra
    `min(len, 6)` mais o anúncio do que não coube.
    """
    avisos = _POOL_12[:quantos]
    bloco = _diagnostico_com(avisos)
    saiu = _avisos_no_email(bloco)

    assert len(saiu) == min(quantos, _TETO), (
        "o e-mail levou %d dos %d avisos (o esperado é %d) — voltou o corte "
        "cego: %r" % (len(saiu), quantos, min(quantos, _TETO), saiu))
    assert len(set(saiu)) == len(saiu), "o e-mail repetiu aviso: %r" % (saiu,)
    assert set(saiu) <= set(avisos), (
        "o e-mail inventou aviso que o motor não gerou: %r"
        % (set(saiu) - set(avisos),))

    # o que não coube é ANUNCIADO, com o número certo — nunca sumido calado
    anunciados = _e_mais_no_email(bloco)
    if quantos > _TETO:
        assert anunciados == quantos - _TETO, (
            "com %d avisos o e-mail anunciou %r que ficaram de fora (era pra "
            "ser %d) — voltou o descarte calado"
            % (quantos, anunciados, quantos - _TETO))
    else:
        assert anunciados is None, (
            "com %d avisos nada ficou de fora, mas o e-mail anunciou %r"
            % (quantos, anunciados))

    if "⚠ 3 prancha(s) não entraram nesta planilha" in avisos:
        assert any("não entraram" in a for a in saiu), (
            "o aviso '3 prancha(s) não entraram' NÃO saiu no e-mail — é o de "
            "24/08 de novo: metade do projeto sumido e o cliente só sabendo "
            "pela tela, que 43 de 44 nunca reabrem. Saiu: %r" % (saiu,))


def _rodado(lista, k):
    return list(lista[k:]) + list(lista[:k])


# 🪤 A ordem CRUA do caso real já traz "INCOMPLETA" antes de "leitor
# alternativo", e o `list.sort` do Python é ESTÁVEL: a asserção de posição
# continuava verdadeira mesmo com os dois PESANDO IGUAL. O guarda media a
# ordem de ENTRADA, não a régua de gravidade. Por isso a ordem crua agora é a
# dimensão que varia.
_ORDENS_CRUAS = (
    [("crua", _AVISOS_DO_CLIENTE_19),
     ("invertida", list(reversed(_AVISOS_DO_CLIENTE_19)))]
    + [("rodada-%d" % k, _rodado(_AVISOS_DO_CLIENTE_19, k)) for k in range(1, 7)]
)


@pytest.mark.parametrize(
    "arranjo,avisos", _ORDENS_CRUAS, ids=[n for n, _ in _ORDENS_CRUAS])
def test_o_email_ordena_por_gravidade_e_prancha_faltando_vem_primeiro(
        arranjo, avisos):
    """🪤 06/09/2026 — o guarda antigo conferia as strings `_avisos.sort(...)` e
    `def _peso_aviso` no fonte. Inverti a condição DENTRO do `_peso_aviso`
    (`in` → `not in`, com a frase e o `return 0` intactos no corpo) e ele
    passou: o aviso de prancha faltando caía pro 7º lugar e era cortado pelo
    teto de 6. Agora a ordem é lida no e-mail montado.

    🪤 07/09/2026 — mas com UMA ordem crua só, e justo a que já vinha ordenada:
    ordenação estável faz o guarda passar com a régua de gravidade toda
    achatada. Agora as 8 ordens cruas têm que dar o MESMO e-mail."""
    saiu = _avisos_no_email(_diagnostico_com(avisos))
    assert "não entraram" in saiu[0], (
        "prancha inteira faltando não é o 1º aviso do e-mail (ordem crua %s) — "
        "a ordem voltou a ser a que o motor calhou de gerar. Saiu: %r"
        % (arranjo, saiu))
    pos = {a: i for i, a in enumerate(saiu)}
    incompleta = next(i for a, i in pos.items() if "INCOMPLETA" in a)
    for neutro in ("leitor alternativo", "Escala assumida", "Blocos repetidos"):
        i_neutro = next((i for a, i in pos.items() if neutro in a), None)
        assert i_neutro is not None, (
            "o aviso neutro %r sumiu do e-mail com a ordem crua %s: %r"
            % (neutro, arranjo, saiu))
        assert incompleta < i_neutro, (
            "'leitura incompleta' saiu DEPOIS do aviso neutro %r (ordem crua "
            "%s) — foi um neutro que ocupou a vaga do aviso grave em 24/08. "
            "Saiu: %r" % (neutro, arranjo, saiu))


def test_o_grave_sobrevive_ao_teto_mesmo_chegando_por_ultimo():
    """🩸 O caso que a ordem crua do cliente-19 escondia: 8 avisos com os
    NEUTROS na frente e o 'leitura INCOMPLETA' no fim da fila do motor.

    Se os pesos empatarem, o grave cai pro 7º lugar, o teto de 6 o corta, e o
    cliente nunca fica sabendo que a prancha veio pela metade."""
    avisos = _NEUTROS_EXTRA + [
        "Usamos o leitor alternativo nesta prancha",
        "Blocos repetidos foram agrupados",
        "A leitura da prancha '4366-EL-E.dwg' ficou INCOMPLETA: ela tem itens demais",
    ]
    assert len(avisos) == 8, "a fixture tem que passar do teto de 6"
    saiu = _avisos_no_email(_diagnostico_com(avisos))
    assert len(saiu) == _TETO, saiu
    assert any("INCOMPLETA" in a for a in saiu), (
        "o aviso GRAVE chegou por último na fila do motor e o teto de 6 o "
        "cortou — a régua de gravidade parou de valer. Saiu: %r" % (saiu,))

def test_o_que_nao_couber_e_anunciado_nunca_sumido():
    """Trocar um corte cego por outro não seria conserto."""
    src = _main()
    assert "e mais {len(_avisos) - _TETO_EMAIL} aviso(s)" in src, (
        "o e-mail volta a descartar avisos em silêncio quando passam do teto")


def test_boa_noticia_vai_por_ultimo():
    """'✅ Escala conferida' é ótimo, mas não pode empurrar 'faltou prancha'
    pra fora do e-mail.

    🪤 07/09/2026 — este guarda procurava `return 9` no FONTE do `_peso_aviso`.
    Agora ele põe a boa notícia na FRENTE da fila crua e cobra o comportamento:
    ela vai pro fim, e é ela que o teto corta."""
    boa = "✅ Escala conferida pelas cotas"
    # a boa notícia PRIMEIRO na ordem crua do motor, e mais 5 avisos comuns
    avisos = [boa] + _NEUTROS_EXTRA
    saiu = _avisos_no_email(_diagnostico_com(avisos))
    assert saiu[-1] == boa, (
        "a boa notícia não foi pro fim do e-mail — ela ocupa vaga de aviso que "
        "explica problema. Saiu: %r" % (saiu,))
    # e com o pacote cheio do cliente-19 (7 avisos, teto 6) é ela que sobra fora
    saiu7 = _avisos_no_email(_diagnostico_com(_AVISOS_DO_CLIENTE_19))
    assert boa not in saiu7, (
        "o teto de 6 cortou um aviso de problema e manteve o '✅' — foi assim "
        "que o aviso de prancha faltando sumiu em 24/08. Saiu: %r" % (saiu7,))


# ══════════════════════════════════════════════════════════════════════════
#  2. Conselho impossível
# ══════════════════════════════════════════════════════════════════════════
def test_o_aviso_de_corte_nao_manda_mais_reprocessar():
    """🩸 09/09/2026 — ESTE GUARDA ERA CEGO E O DEFEITO VIVEU 16 DIAS.

    Ele ancorava no texto do caminho DXF (`"INCOMPLETA: ela tem itens demais"`)
    e depois proibia a variante LONGA `"Reprocessar pode completar a planilha"`.
    Só que o caminho do PDF produzia a variante CURTA, `"Reprocessar pode
    completar."`, e essa passava. O conselho aposentado em 24/08 continuou
    saindo pro cliente de PDF — e o saneador do merge errava pelo MESMO motivo:
    também procurava a string longa.

    🚨 O custo é dinheiro do cliente: o corte vem da DENSIDADE da prancha, então
    reprocessar corta no mesmo lugar. Na elétrica do cliente-19 cortou 3 de 3
    vezes, e a 3ª deu MENOS itens.

    🔑 Agora o guarda CHAMA a régua em vez de ler o fonte.
    """
    from engine_rules import aviso_de_leitura_cortada
    for frase in (aviso_de_leitura_cortada("x.pdf"),
                  aviso_de_leitura_cortada("x.dxf", 87)):
        assert "Reprocessar normalmente NÃO" in frase, frase
        assert "Reprocessar pode completar" not in frase, (
            "o conselho aposentado voltou: %r" % frase)


@pytest.mark.parametrize("velho", [
    "Reprocessar pode completar a planilha.",   # variante do DXF, já morta
    "Reprocessar pode completar.",              # 🩸 a do PDF — a que escapava
])
def test_o_saneador_do_merge_pega_AS_DUAS_variantes(velho):
    """🧪 Controle positivo da rede de segurança. Ela existe pro caso de um
    aviso GRAVADO antes do conserto voltar pelo merge — e errava a curta."""
    import main as M
    src = _main()
    i = src.index('for _velho in ("Reprocessar pode completar a planilha."')
    trecho = src[i:i + 260]
    assert velho in trecho, (
        "o saneador do merge não remove a variante %r — foi exatamente assim "
        "que o conselho velho atravessou o merge inteiro" % velho)
    assert hasattr(M, "app")


def test_os_DOIS_caminhos_vivos_usam_a_MESMA_regua_de_corte():
    """🪤 O defeito nasceu de duas cópias da mesma frase, e só uma consertada.
    Ancorado na AST: comentário citando a frase não pode fazer isto passar."""
    import ast
    arvore = ast.parse(_main())
    chamadas = [n for n in ast.walk(arvore)
                if isinstance(n, ast.Call)
                and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
                == "aviso_de_leitura_cortada"]
    assert len(chamadas) >= 2, (
        "o main.py chama a régua do aviso de corte %d vez(es); são DOIS "
        "caminhos (DXF/DWG e PDF) e os dois precisam chamar — senão volta a "
        "divergir, que é como o conselho velho sobreviveu 16 dias"
        % len(chamadas))


def test_o_aviso_de_corte_diz_o_que_o_cliente_PODE_fazer():
    """Tirar o conselho errado sem pôr o certo deixa o cliente sem saída.

    🔑 09/09: passou a CHAMAR a régua. Lia o fonte do main.py e quebrou quando a
    frase mudou de arquivo — guarda que lê fonte mede onde o texto MORA, não o
    que o cliente RECEBE."""
    from engine_rules import aviso_de_leitura_cortada
    for frase in (aviso_de_leitura_cortada("x.pdf"),
                  aviso_de_leitura_cortada("x.dxf", 87)):
        assert "exporte-a em partes" in frase, frase
        assert "fale com a gente" in frase, frase
        # 🪤 A mutação pegou este buraco: tirar o EXEMPLO deixava "exporte-a em
        # partes" no lugar e o teste passava — mas "em partes" COMO? Conselho
        # sem exemplo concreto é conselho que o cliente não consegue seguir, e
        # foi o vazio disso que criou o "reprocessar" em primeiro lugar.
        assert ("pavimento" in frase and "disciplina" in frase), (
            "o aviso diz 'exporte em partes' e não diz em que partes: %r" % frase)


def test_o_aviso_de_corte_nao_assusta_sobre_o_que_veio():
    """Os itens lidos ANTES do corte estão certos. Não dizer isso faria o
    cliente desconfiar da planilha inteira."""
    from engine_rules import aviso_de_leitura_cortada
    assert "os que vieram estão certos" in aviso_de_leitura_cortada("x.dxf", 87)
    # e no caminho sem contagem a frase tem que seguir tranquilizando
    assert "estão certos" in aviso_de_leitura_cortada("x.pdf")


# ══════════════════════════════════════════════════════════════════════════
#  3. Nome de arquivo interno não vaza
# ══════════════════════════════════════════════════════════════════════════
def test_o_aviso_de_corte_usa_o_nome_real_da_prancha():
    src = _main()
    i = src.index("_rules_corte.aviso_de_leitura_cortada(")
    trecho = src[i:i + 220]
    assert "_nome_prancha_bonito(dxf_path)" in trecho, (
        "voltou o os.path.basename cru — o cliente lê '_libredwg.dxf', que ele "
        "nunca enviou")


def test_a_lista_de_pranchas_que_faltaram_usa_o_nome_real():
    src = _main()
    assert "_nome_prancha_bonito(e.split(\":\")[0])" in src, (
        "a lista 'Faltaram: ...' voltou a mostrar nome interno de conversão")


# (enviado pelo cliente, caminho interno que o motor cria, nome que ele lê)
_NOMES_DE_PRANCHA = [
    # 1 sufixo: DWG convertido pelo ODA
    ("4366-EL-E.dwg", "/tmp/w/4366-EL-E.dxf", "4366-EL-E"),
    # 1 sufixo: DWG convertido pelo plano B (dwg_extractor.py:1828)
    ("4366-EL-E.dwg", "/tmp/w/4366-EL-E_libredwg.dxf", "4366-EL-E"),
    # 1 sufixo: DXF do cliente emagrecido (dxf_slim.py:232)
    ("3073-AQ-E.dxf", "/tmp/w/3073-AQ-E.slim.dxf", "3073-AQ-E"),
    # 🩸 DOIS sufixos: DWG convertido pelo libredwg E DEPOIS emagrecido.
    #    É a forma real do acervo (ex.: ...R03_libredwg.slim.dxf) e a única que
    #    precisa de mais de uma passada pela lista de sufixos.
    ("4366-EL-E.dwg", "/tmp/w/4366-EL-E_libredwg.slim.dxf", "4366-EL-E"),
    ("PLANTA BAIXA.DWG", "/tmp/w/PLANTA BAIXA_libredwg.slim.dxf", "PLANTA BAIXA"),
    # o cliente que mandou DXF direto
    ("planta.dxf", "/tmp/w/planta.dxf", "planta"),
    # maiúsculas, que o motor não normaliza
    ("PLANTA.DWG", "/tmp/w/PLANTA.DWG", "PLANTA"),
    # caminho vazio não pode virar string vazia no meio da frase
    ("(nada)", "", "prancha"),
]


@pytest.mark.parametrize(
    "enviado,interno,esperado", _NOMES_DE_PRANCHA,
    ids=[c[1] or "vazio" for c in _NOMES_DE_PRANCHA])
def test_o_helper_de_nome_bonito_tira_mesmo_o_sufixo_interno(
        enviado, interno, esperado):
    """Controle positivo do helper — se ele não limpar, os dois testes acima
    passam e o cliente continua vendo o nome errado.

    🪤 07/09/2026 — este guarda lia o FONTE (`corpo_de`) e só conferia que as
    duas strings de sufixo apareciam nele. Agora EXECUTA, e a tabela inclui o
    caminho com DOIS sufixos (`_libredwg.slim.dxf`), que é o único que exige
    mais de uma passada pela lista — nenhum caso anterior exigia."""
    lido = main._nome_prancha_bonito(interno)
    assert lido == esperado, (
        "o cliente enviou %r, o motor guardou %r e o aviso vai citar %r — ele "
        "vai procurar na pasta um arquivo que não existe (defeito nº3 do "
        "cliente-19)" % (enviado, interno, lido))
    for interno_nosso in ("_libredwg", ".slim", ".dxf", ".dwg"):
        assert interno_nosso.lower() not in lido.lower(), (
            "vazou artefato NOSSO (%r) no nome que o cliente lê: %r"
            % (interno_nosso, lido))


# ══════════════════════════════════════════════════════════════════════════
#  Controle: o resto do e-mail não pode ter sido derrubado junto
# ══════════════════════════════════════════════════════════════════════════
def test_o_email_continua_montando_o_bloco_de_diagnostico():
    src = _main()
    assert "Como lemos o seu projeto" in src
    assert "_hd.escape(w)" in src, "sumiu o escape de HTML dos avisos"
