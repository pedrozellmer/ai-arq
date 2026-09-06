# -*- coding: utf-8 -*-
"""Prancha com a escala SUSPEITA tem que avisar o cliente. Era a única muda.

🩸 CASO GABRIELLE — sabrar.com.br, 01/09/2026, job `ffac8a79`, projeto SMARTFIT.
Primeira cliente que chegou pelo ChatGPT, orçamentista, e-mail corporativo.
Cadastrou 11:50, subiu o projeto 11:52, recebeu a planilha 12:00 e avaliou a
entrega com **NOTA 1 de 5** às 12:02. Foi a primeira nota da história do produto.

O motor SABIA que a escala estava errada. O log diz, literalmente:

    declarada=Polegadas fator=0.0254 regua=nao-decidiu
    alerta=Unidade suspeita: maior elemento mede 5127m (>500m) — escala pode
           estar errada; tratar quantidades como estimado.
    ressalva=True

E fez a parte certa: rebaixou os selos. Os 88 itens que saíram MEDIDOS são
todos 'un' (contagem de bloco, que não depende de escala); tudo em ml/m² saiu
estimado. A regra dura nº1 aguentou.

🚨 O QUE FALHOU: ela nunca foi avisada. Os três avisos que ela recebeu falavam
de leitura incompleta, do leitor alternativo e da área total ausente. Nenhum
falava de escala. E o do leitor alternativo ainda dizia "as medições saíram
(88 itens medidos do CAD)", que soa tranquilizador enquanto o comprimento está
25× fora. Ela recebeu **22.332,37 ml** de duto (÷25,4 = 879 m, o plausível) sem
uma palavra. É orçamentista — bateu o olho no número impossível e acabou.

🔑 A CAUSA, e é perversa: `_resumo_escala_arquivo` classificava a prancha em
cotas / rotulo / consenso / **alerta** / sem_prova, e `_linhas_escala_projeto`
só montava linha para as PROVADAS e para as SEM_PROVA. O ramo 'alerta' caía
fora das duas listas e não gerava nada — com o comentário "já vira ressalva por
outro caminho". O outro caminho rebaixa o selo EM SILÊNCIO.

Ou seja: "não consegui provar a escala" avisava; **"a escala está suspeita" não
avisava**. O desfecho mais grave era o único mudo.
"""
import io
import os
import sys
import textwrap

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

_INI = "import re as _re_escala"
_FIM = "\ndef _regua_da_sombra("


def _fns():
    """Executa o TRECHO REAL do main.py (as duas funções e o regex delas)."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert src.count(_INI) == 1, "a âncora de início mudou"
    i = src.index(_INI)
    trecho = textwrap.dedent(src[i:src.index(_FIM, i)])
    # 🪤 O trecho usa nomes que o main.py tem no topo e este namespace não. Se
    # aparecer um nome novo na região, o teste quebra com NameError (alto, e não
    # verde de mentira) — e o conserto é acrescentar aqui, não afrouxar o teste.
    ns = {"__name__": "escala_ns", "os": os}
    exec(compile(trecho, "main_escala_slice", "exec"), ns)
    return ns["_resumo_escala_arquivo"], ns["_linhas_escala_projeto"]


# ── O metadata REAL da prancha da Gabrielle ────────────────────────────────
_MD_GABRIELLE = {
    "unidade_desenho": "Polegadas",
    "fator_para_metros": 0.0254,
    "regua_cotas_status": "nao-decidiu",
    "alerta_unidade": ("Unidade suspeita: maior elemento mede 5127m (>500m) — "
                       "escala pode estar errada; tratar quantidades como "
                       "estimado. | o cabeçalho declara Polegadas"),
}
_ARQ = "/tmp/SBRRJCCGD05-EXE-ARC-000-PROJ-R03_libredwg.slim.dxf"


def test_a_prancha_suspeita_GERA_linha_pro_cliente():
    """🩸 O que a Gabrielle NÃO recebeu."""
    resumo, linhas = _fns()
    a = resumo(_ARQ, _MD_GABRIELLE)
    assert a["status"] == "alerta", a
    out = linhas([a], n_medidos=88)
    assert out, "a prancha com escala SUSPEITA não gerou aviso nenhum — foi o bug"
    txt = " ".join(out)
    assert "ESCALA SUSPEITA" in txt, txt
    assert "SBRRJCCGD05" in txt, "não diz QUAL prancha:\n" + txt


def test_o_aviso_diz_o_MOTIVO_que_o_motor_calculou():
    """Frase genérica não convence orçamentista. '5127m (>500m)' convence."""
    resumo, linhas = _fns()
    txt = " ".join(linhas([resumo(_ARQ, _MD_GABRIELLE)], n_medidos=88))
    assert "5127m" in txt, "jogou fora o motivo que o próprio motor calculou:\n" + txt


def test_o_aviso_explica_por_que_a_CONTAGEM_continua_valendo():
    """Ela tinha 88 itens medidos em 'un' — legítimos. O aviso não pode fazer
    ela jogar fora a parte boa junto com a ruim."""
    resumo, linhas = _fns()
    txt = " ".join(linhas([resumo(_ARQ, _MD_GABRIELLE)], n_medidos=88))
    assert "un" in txt and "contar não depende de escala" in txt, txt


def test_o_aviso_diz_o_que_FAZER():
    resumo, linhas = _fns()
    txt = " ".join(linhas([resumo(_ARQ, _MD_GABRIELLE)], n_medidos=88))
    assert "área total" in txt, "não diz o que destrava:\n" + txt


def test_a_linha_de_SUSPEITA_vem_ANTES_da_de_sem_prova():
    """Gravidade manda: 'está errada' é pior que 'não consegui provar'."""
    resumo, linhas = _fns()
    a = resumo(_ARQ, _MD_GABRIELLE)
    b = {"nome": "OUTRA", "status": "sem_prova", "declarada": "Milímetros"}
    out = linhas([b, a], n_medidos=1)
    assert len(out) == 2, out
    assert "ESCALA SUSPEITA" in out[0], "a suspeita não veio primeiro: %s" % out


def test_plausibilidade_tambem_entra():
    """`unidade_corrigida_por_plausibilidade` cai no mesmo ramo."""
    resumo, linhas = _fns()
    a = resumo("/tmp/F03.dxf", {"unidade_desenho": "Milímetros",
                                "unidade_corrigida_por_plausibilidade": True})
    assert a["status"] == "alerta"
    assert "ESCALA SUSPEITA" in " ".join(linhas([a], n_medidos=0))


# ── CONTROLES: tem que RECUSAR ─────────────────────────────────────────────
def test_CONTROLE_prancha_PROVADA_nao_ganha_aviso_de_suspeita():
    """🧪 Caso cliente-23 (175 cotas batem). Se este falhar, a regra virou spam."""
    resumo, linhas = _fns()
    a = resumo("/tmp/TOP-EST-PE-116-FRM-TIP-R00.dxf",
               {"unidade_validada_por_cotas": 175, "unidade_nome_provada": "centímetros"})
    assert a["status"] == "cotas"
    txt = " ".join(linhas([a], n_medidos=0))
    assert "ESCALA SUSPEITA" not in txt, "acusou uma prancha com a escala PROVADA:\n" + txt
    assert "Escala conferida" in txt


def test_CONTROLE_sem_prova_continua_com_a_frase_ANTIGA_e_nao_a_nova():
    """🧪 São diagnósticos diferentes e precisam continuar diferentes."""
    resumo, linhas = _fns()
    a = resumo("/tmp/X.dxf", {"unidade_desenho": "Milímetros"})
    assert a["status"] == "sem_prova"
    txt = " ".join(linhas([a], n_medidos=0))
    assert "ESCALA SUSPEITA" not in txt
    assert "não conferida por cota" in txt


def test_CONTROLE_sem_pranchas_nao_inventa_aviso():
    _, linhas = _fns()
    assert linhas([], n_medidos=0) == []
    assert linhas([{"nome": "a", "status": "cotas", "n": 3}], n_medidos=5)


def test_CONTROLE_o_guarda_REPROVA_a_versao_ANTIGA():
    """🧪 Controle positivo: reproduz o comportamento antigo (o ramo 'alerta'
    devolvia só nome+status e a montagem ignorava a lista) e confere que ele
    NÃO avisa. Sem isto, os testes acima passariam com o conserto desligado."""
    _, linhas = _fns()
    antigo = {"nome": "SBRRJCCGD05", "status": "alerta"}   # sem 'declarada'/'alerta'
    out = linhas([antigo], n_medidos=88)
    # o conserto novo AINDA avisa (só perde o motivo) — é o mínimo aceitável
    assert out, "com o dict antigo o aviso sumiu de novo"
    assert "ESCALA SUSPEITA" in out[0]
    assert "5127m" not in out[0], "inventou motivo que o metadata não tinha"


def test_CONTROLE_a_lista_de_PROVADAS_nao_engole_a_suspeita():
    """Projeto misto: uma prancha provada e uma suspeita. As DUAS aparecem."""
    resumo, linhas = _fns()
    ok = resumo("/tmp/BOA.dxf", {"unidade_validada_por_cotas": 44,
                                 "unidade_nome_provada": "metros"})
    ruim = resumo(_ARQ, _MD_GABRIELLE)
    txt = " ".join(linhas([ok, ruim], n_medidos=10))
    assert "Escala conferida" in txt and "ESCALA SUSPEITA" in txt, (
        "o ✅ de uma prancha escondeu o ⚠ da outra:\n" + txt)
