# -*- coding: utf-8 -*-
"""Esquadria que saiu só com o código vira PEDIDO, não linha morta.

🩸 23/09/2026 — MEDIDO no acervo. **85 projetos** têm linha de esquadria "a
confirmar com quadro de esquadrias" (**444 linhas**), e **47 deles (55%)
mandaram UM arquivo só**: o quadro não veio no envio, não há o que ler.

🔬 Conferido no arquivo REAL (`a298b4e5`): baixei o PDF e ele traz `PA01`–
`PA07`, `PM02`–`PM08`, `VF`, `JA` na planta — e **a palavra "quadro" não
aparece no texto da página**. O motor criou 21 linhas "a confirmar", que o
orçamentista não consegue precificar e apaga.

🔑 O motor JÁ SABE: escreve "(não apresentado nesta prancha)" e "quadro
completo não visível nesta prancha". Faltava virar pedido ao cliente — que é
o que funcionou hoje com o cliente do ArchiCAD: a gente disse exatamente o que
faltava, ele mandou outro arquivo, e o projeto mediu.

🪤 Todos os textos abaixo são descrições REAIS do banco, não inventadas.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _corpo import corpo_de  # noqa: E402


def _carrega():
    """Executa só o pedaço do main.py — importar o módulo conecta em Supabase."""
    import re as _re
    ns = {"__name__": "esq_ns", "_re": _re}
    for nome in ("_RE_E_ESQUADRIA", "_RE_PEDE_O_QUADRO", "_RE_TEM_DIMENSAO",
                 "_RE_CODIGO_ESQUADRIA"):
        exec(compile(_linha_da_constante(nome), "main_slice", "exec"), ns)
    exec(compile(corpo_de("esquadrias_sem_o_quadro"), "main_slice", "exec"), ns)
    return ns["esquadrias_sem_o_quadro"]


def _linha_da_constante(nome):
    import io
    import re
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    m = re.search(r"^%s\s*=\s*_re\.compile\(.*?\)\s*$" % re.escape(nome),
                  src, re.M | re.S)
    assert m, "não achei a constante %s" % nome
    return m.group(0)


esquadrias_sem_o_quadro = _carrega()


class _It:
    def __init__(self, description):
        self.description = description


# Descrições REAIS, copiadas do banco.
_SEM_ESPEC = [
    "Porta PA01 — tipo, dimensão e material conforme quadro de esquadrias "
    "(código PA01 identificado na planta baixa)",
    "Porta de acesso — guarita/escritório — tipo, dimensão e material a "
    "confirmar com quadro de esquadrias (não apresentado nesta prancha)",
    "Janela J02 — conforme quadro de esquadrias (dimensão e material a "
    "confirmar com quadro completo não visível nesta prancha)",
    "Porta P05 — conforme quadro de esquadrias (dimensão e material a "
    "confirmar com quadro completo de esquadrias não visível nesta prancha)",
    "Portas hospitalares — demais tipos e dimensões — material, ferragens e "
    "quantidade a confirmar com quadro de esquadrias completo",
    "Janela/esquadria VF02 — tipo, dimensão e material conforme quadro de "
    "esquadrias (código VF02 identificado)",
]

# Estas TÊM a especificação — não podem entrar no pedido.
_COMPLETAS = [
    "Janela de correr 4 folhas, caixilho de alumínio veneziana na cor branco, "
    "1,42×0,50 m, peitoril H=1,80 m — conforme quadro de esquadrias",
    "Porta P01 — 250×210 cm (L×A), conforme indicação na planta baixa. "
    "Material e acabamento a confirmar em quadro de esquadrias ou prancha",
    "Porta P10 — Porta tipo abrir em alumínio anodizado branco, palheta sem "
    "ventilação, trinco tipo alavanca, soleira em granito verde",
    "Porta de madeira PM04 — porta interna de madeira 0,80 x 2,10 m",
]


# ══════════════════════════════════════════════════════════════════════════
#  PEGA O QUE FALTA
# ══════════════════════════════════════════════════════════════════════════
def test_pega_as_seis_descricoes_REAIS_sem_especificacao():
    r = esquadrias_sem_o_quadro([_It(d) for d in _SEM_ESPEC])
    assert r["n"] == 6, (r["n"], r["linhas"])


def test_reconhece_o_motor_dizendo_que_o_quadro_NAO_VEIO():
    """"(não apresentado nesta prancha)" é o motor avisando — e ninguém ouvia."""
    for d in ("Porta X — a confirmar com quadro (não apresentado nesta prancha)",
              "Janela Y — quadro completo não visível nesta prancha",
              "Porta Z — quadro de esquadrias não consta no envio"):
        assert esquadrias_sem_o_quadro([_It(d)])["n"] == 1, d


def test_junta_os_codigos_pra_dizer_ao_cliente_QUAIS_faltam():
    r = esquadrias_sem_o_quadro([_It(d) for d in _SEM_ESPEC])
    assert "PA01" in r["codigos"], r["codigos"]
    assert "J02" in r["codigos"] or "P05" in r["codigos"], r["codigos"]
    assert "VF02" in r["codigos"], r["codigos"]


def test_nao_repete_codigo():
    r = esquadrias_sem_o_quadro([
        _It("Porta PA01 — a confirmar com quadro de esquadrias"),
        _It("Porta PA01 — a confirmar com quadro de esquadrias"),
    ])
    assert r["codigos"] == ["PA01"], r["codigos"]
    assert r["n"] == 2, "as DUAS linhas contam; só o código não repete"


# ══════════════════════════════════════════════════════════════════════════
#  NÃO PEDE O QUE JÁ TEM
# ══════════════════════════════════════════════════════════════════════════
def test_linha_COM_dimensao_fica_de_fora():
    """🪤 Pedir o quadro pra uma linha já especificada é pedir o que temos."""
    r = esquadrias_sem_o_quadro([_It(d) for d in _COMPLETAS])
    assert r["n"] == 0, (r["n"], r["linhas"])


def test_a_janela_1_42x0_50_do_banco_NAO_entra():
    """O contraexemplo que me impediu de errar: cita o quadro E está completa."""
    d = ("Janela de correr 4 folhas, caixilho de alumínio veneziana na cor "
         "branco, 1,42×0,50 m, peitoril H=1,80 m — conforme quadro de esquadrias")
    assert esquadrias_sem_o_quadro([_It(d)])["n"] == 0


def test_reconhece_dimensao_em_varios_formatos():
    for d in ("Porta P1 — 0,90 x 2,10 m a confirmar",
              "Porta P2 — 250×210 cm a confirmar",
              "Janela J1 — 1.42 X 0.50 a confirmar",
              "Porta P3 — 80x210cm a confirmar"):
        assert esquadrias_sem_o_quadro([_It(d)])["n"] == 0, d


def test_item_que_NAO_e_esquadria_nao_entra():
    for d in ("Piso cerâmico — tipo a confirmar com legenda de acabamentos",
              "Forro de gesso — acabamento a definir",
              "Pintura — cor a confirmar em memorial"):
        assert esquadrias_sem_o_quadro([_It(d)])["n"] == 0, d


def test_esquadria_COMPLETA_sem_pedir_nada_nao_entra():
    d = "Porta de madeira maciça 0,80 m, batente de aluminio, fechadura"
    assert esquadrias_sem_o_quadro([_It(d)])["n"] == 0


def test_lista_vazia_e_lixo_nao_quebram():
    for ruim in ([], None, [_It("")], [_It(None)]):
        assert esquadrias_sem_o_quadro(ruim)["n"] == 0, ruim


def test_o_retorno_e_curto_pro_log():
    r = esquadrias_sem_o_quadro([_It("Porta P%d — a confirmar com quadro" % i)
                                 for i in range(1, 60)])
    assert r["n"] == 59, "conta TODAS"
    assert len(r["codigos"]) <= 12, "mas a lista sai curta pro log/aviso"
    assert len(r["linhas"]) <= 6


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLES
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_sem_o_filtro_de_dimensao_pediria_o_que_ja_tem():
    """Prova que o filtro não é decorativo: 4 linhas completas entrariam."""
    import re
    ingenuo = [d for d in _COMPLETAS
               if re.search(r"esquadria|porta|janela", d, re.I)
               and re.search(r"a confirmar|a definir", d, re.I)]
    assert ingenuo, (
        "o controle parou de provar: alguma COMPLETA tem que citar 'a confirmar'")
    assert esquadrias_sem_o_quadro([_It(d) for d in ingenuo])["n"] == 0, (
        "o nosso tem que recusar todas elas")


def test_CONTROLE_sem_o_filtro_de_esquadria_pegaria_piso_e_forro():
    """Sem exigir que seja esquadria, o aviso sairia pra meio quantitativo."""
    import re
    outros = ["Piso cerâmico — tipo a confirmar", "Forro — acabamento a definir"]
    assert all(re.search(r"a confirmar|a definir", d, re.I) for d in outros)
    assert esquadrias_sem_o_quadro([_It(d) for d in outros])["n"] == 0


# ══════════════════════════════════════════════════════════════════════════
#  O TEXTO QUE O CLIENTE LÊ — escolhido pelo Pedro (opção A, com códigos)
# ══════════════════════════════════════════════════════════════════════════
def _carrega_aviso():
    """O texto E o piso, lidos do main.py.

    🪤 O piso sai do FONTE, nunca cravado aqui: constante que o teste declara
    e constante que o teste nao testa — foi assim que a trava de clique duplo
    passou verde com a janela zerada, hoje de manha.
    """
    import io
    import re
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    m = re.search(r"^_MINIMO_ESQUADRIAS_PRA_AVISAR\s*=\s*(\d+)\s*$", src, re.M)
    assert m, "nao achei o piso do aviso em main.py"
    ns = {"__name__": "aviso_ns",
          "_MINIMO_ESQUADRIAS_PRA_AVISAR": int(m.group(1))}
    exec(compile(corpo_de("aviso_da_esquadria_sem_quadro"), "s", "exec"), ns)
    return ns["aviso_da_esquadria_sem_quadro"], ns["_MINIMO_ESQUADRIAS_PRA_AVISAR"]


aviso_da_esquadria_sem_quadro, PISO_AVISO = _carrega_aviso()


def test_o_aviso_diz_QUANTAS_e_QUAIS():
    """A opção A: citar o código prova que a gente leu o projeto dele."""
    t = aviso_da_esquadria_sem_quadro(
        {"n": 27, "codigos": ["J11", "J12", "J13", "JJ02", "P13"]})
    assert "27 esquadria" in t, t
    assert "J11" in t and "P13" in t, t
    assert "QUADRO DE ESQUADRIAS" in t, t


def test_o_aviso_termina_em_CONVITE_sem_prometer():
    """🚨 23/09, mesmo dia: o texto dizia "Mande a prancha e eu DETALHO essas
    linhas" — promessa. Fui medir e não achei base: só **2 projetos** em todo o
    acervo mandaram a prancha de esquadrias, com 14,9% de especificação contra
    24,8% de quem não mandou. Com 2 amostras não se promete nada.

    🔑 O convite fica; a garantia de resultado sai."""
    t = aviso_da_esquadria_sem_quadro({"n": 27, "codigos": ["J11"]})
    assert "mande junto" in t, t
    assert "é a fonte" in t, t


def test_sem_codigo_legivel_o_aviso_ainda_sai():
    t = aviso_da_esquadria_sem_quadro({"n": 29, "codigos": []})
    assert t and "29 esquadria" in t
    assert "QUADRO DE ESQUADRIAS" in t


def test_poucas_esquadrias_NAO_interrompem_o_cliente():
    """1 ou 2 sem detalhe ele resolve olhando a própria planta."""
    for n in range(0, PISO_AVISO):
        assert aviso_da_esquadria_sem_quadro({"n": n, "codigos": ["X1"]}) is None, n
    assert aviso_da_esquadria_sem_quadro({"n": PISO_AVISO, "codigos": ["X1"]})


def test_o_piso_nao_corta_nenhum_caso_REAL():
    """📊 Os jobs afetados têm 21, 23, 27, 29 e 39 linhas."""
    for n in (21, 23, 27, 29, 39):
        assert aviso_da_esquadria_sem_quadro({"n": n, "codigos": ["A1"]}), n


def test_a_lista_de_codigos_nao_vira_paredao():
    t = aviso_da_esquadria_sem_quadro(
        {"n": 40, "codigos": ["C%02d" % i for i in range(1, 13)]})
    # 6 códigos = 5 vírgulas na lista; o resto do texto tem as suas.
    trecho = t[t.index("(") + 1:t.index(")")]
    assert trecho.count(",") <= 5, "cortar em 6 códigos: " + trecho
    assert "…" in t


def test_achado_vazio_ou_lixo_nao_gera_aviso():
    for ruim in ({}, None, {"n": 0}, {"n": None}):
        assert aviso_da_esquadria_sem_quadro(ruim) is None, ruim


def test_o_aviso_NAO_PROMETE_resultado():
    """🚨 REGRA: dizer o que falta é fato; garantir que mandar resolve é
    afirmação sem dado — e se o cliente mandar e nada melhorar, a culpa vira
    nossa. Medido: só 2 projetos mandaram a prancha, e não deu pra concluir.
    """
    t = aviso_da_esquadria_sem_quadro({"n": 27, "codigos": ["J11"]})
    for promessa in ("eu detalho", "vou detalhar", "eu completo", "resolve",
                     "garanto", "e eu meço", "eu meço"):
        assert promessa not in t.lower(), (
            "o aviso voltou a PROMETER (%r): %s" % (promessa, t))


def test_CONTROLE_o_texto_PROMETIDO_seria_reprovado():
    """Prova que o guarda acima não é decorativo: o texto que subiu às 19h
    (commit aa78642) seria pego por ele."""
    antigo = ("27 esquadria(s) ficaram sem especificação. Mande a prancha de "
              "esquadrias e eu detalho essas linhas.")
    assert any(p in antigo.lower() for p in ("eu detalho", "vou detalhar")), (
        "o controle parou de provar: o texto antigo TINHA a promessa")
    t = aviso_da_esquadria_sem_quadro({"n": 27, "codigos": ["J11"]})
    assert "eu detalho" not in t.lower(), "e o novo NÃO pode ter"


def test_o_aviso_continua_dizendo_o_QUE_falta_e_POR_QUE():
    """Tirar a promessa não pode virar aviso vago."""
    t = aviso_da_esquadria_sem_quadro({"n": 27, "codigos": ["J11", "P13"]})
    assert "27 esquadria" in t, t
    assert "J11" in t and "P13" in t, t
    assert "QUADRO DE ESQUADRIAS" in t, t
    assert "dimensão, material e tipo" in t, t
