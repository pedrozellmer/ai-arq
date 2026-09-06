# -*- coding: utf-8 -*-
"""Os avisos do projeto COMBINADO nao podem se contradizer na cara do cliente.

🚨 Auditoria de 25/08/2026. O projeto combinado que o cliente-19 RECEBEU saiu com 11
avisos, sendo 6 em pares que se contradiziam:

    "li 162 itens"   x   "li 112 itens"      (a MESMA prancha)
    "94 medidos"     x   "157 medidos"       (e o real do merge e 179)
    a escala da 4366-IH-E, duas vezes, uma delas incompleta

E um deles dizia "Nao encontramos a area total do projeto" numa tela que mostra
496,42 m².

A causa: eu montava os avisos do merge como a UNIAO dos dois jobs, com dedup por
TEXTO EXATO. Cada leitura escreve o mesmo fato com numeros diferentes, entao os
dois passavam. Dedup por texto so funciona quando o texto e igual.

🪤 E o conselho VELHO viajava junto: os jobs de origem foram gerados antes do
conserto de 24/08 e ainda diziam "Reprocessar pode completar a planilha" — o
conselho que gasta o unico reprocesso gratis do cliente por nada.
"""
import io
import os
import re
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)


def _carrega():
    """Carrega as duas funcoes sem subir o app inteiro."""
    def _nome_prancha_bonito(c):
        n = os.path.basename(c or "")
        for suf in (".slim.dxf", "_libredwg.dxf", "_libredwg", ".dxf", ".dwg"):
            if n.endswith(suf):
                n = n[:-len(suf)]
        return n.replace("_libredwg", "").strip() or "prancha"
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    ns = {"_re": re, "_nome_prancha_bonito": _nome_prancha_bonito}
    for fn in ("_merge_familia_aviso", "_merge_avisos"):
        i = src.index("def %s(" % fn)
        j = min(x for x in (src.find(chr(10) + "def ", i + 10),
                            src.find(chr(10) + "@app.", i + 10)) if x > 0)
        exec(compile(src[i:j], fn, "exec"), ns)
    return ns


NS = _carrega()

_PLANO = {"pranchas": [
    {"prancha": "4366-EL-E_libredwg.dxf", "lado": "pai"},
    {"prancha": "4366-LO-E_libredwg.dxf", "lado": "filho"},
]}


def _rodar(avisos_pai, avisos_filho, medidos=179, tem_area=True, plano=None):
    return NS["_merge_avisos"](
        {"warnings": avisos_pai}, {"warnings": avisos_filho},
        plano or _PLANO, medidos, tem_area, "PROCEDENCIA", [])


# ══════════════════════════════════════════════════════════════════════════
#  Os pares que se contradiziam
# ══════════════════════════════════════════════════════════════════════════
def test_o_mesmo_corte_da_MESMA_prancha_sai_UMA_vez():
    """🚨 O caso literal do cliente-19: 162 e 112 pra 4366-EL-E."""
    r = _rodar(
        ["A leitura de '4366-EL-E_libredwg.dxf' pode estar INCOMPLETA (a resposta "
         "da IA foi cortada por tamanho — li 162 itens, mas pode faltar algum)."],
        ["A leitura de '4366-EL-E_libredwg.dxf' pode estar INCOMPLETA (a resposta "
         "da IA foi cortada por tamanho — li 112 itens, mas pode faltar algum)."])
    cortes = [a for a in r if "INCOMPLETA" in a]
    assert len(cortes) == 1, cortes
    assert "162" in cortes[0], "veio do lado que NAO venceu a prancha"


def test_a_contagem_global_vira_a_do_MERGE_nao_a_copiada():
    """94 e 157 estao os dois errados: o merge mede 179."""
    r = _rodar(
        ["7 arquivo(s) precisaram do leitor alternativo (plano B): X.dwg. As "
         "medições saíram (94 item(ns) medido(s) do CAD), mas vale conferir."],
        ["7 arquivo(s) precisaram do leitor alternativo (plano B): X.dwg. As "
         "medições saíram (157 item(ns) medido(s) do CAD), mas vale conferir."],
        medidos=179)
    pb = [a for a in r if "plano B" in a]
    assert len(pb) == 1, pb
    assert "179 item(ns)" in pb[0], pb[0]
    assert "94" not in pb[0] and "157" not in pb[0]


def test_a_escala_sai_na_versao_mais_completa():
    curta = "✅ Escala conferida pelo próprio desenho — 4366-IH-E: 7 cotas batem."
    longa = ("✅ Escala conferida pelo próprio desenho — 3073-AQ-E: 144 cotas "
             "batem — unidade corrigida; 4366-IH-E: 7 cotas batem.")
    r = _rodar([curta], [longa])
    esc = [a for a in r if a.startswith("✅")]
    assert len(esc) == 1 and esc[0] == longa


def test_aviso_de_prancha_faltando_MORRE_no_merge():
    """O merge tem todas as pranchas que qualquer leitura conseguiu ler."""
    r = _rodar(["⚠ 3 prancha(s)/arquivo(s) não entraram nesta planilha."], [])
    assert not [a for a in r if "não entraram" in a]


def test_aviso_de_area_MORRE_quando_o_merge_TEM_area():
    """🚨 A mesma tela dizia que não havia área e mostrava 496,42 m²."""
    r = _rodar(["⚠ Não encontramos a área total do projeto — a prancha não trazia "
                "quadro de áreas legível."], [], tem_area=True)
    assert not [a for a in r if "área total" in a]


def test_mas_o_aviso_de_area_SOBREVIVE_quando_nao_ha_area():
    """Controle negativo: a regra não pode calar um aviso verdadeiro."""
    r = _rodar(["⚠ Não encontramos a área total do projeto."], [], tem_area=False)
    assert [a for a in r if "área total" in a]


def test_aviso_de_UMA_prancha_vem_de_quem_VENCEU_aquela_prancha():
    """Se a 4366-LO-E veio da releitura, o aviso sobre ela tem que ser o da
    releitura — o do pai descreve uma leitura que não está na planilha."""
    r = _rodar(
        ["4366-LO-E_libredwg.dxf: não consegui ler geometria mensurável (PAI)."],
        ["4366-LO-E_libredwg.dxf: não consegui ler geometria mensurável (FILHO)."])
    g = [a for a in r if "geometria mensur" in a]
    assert len(g) == 1 and "FILHO" in g[0], g


def test_o_conselho_VELHO_e_corrigido_na_passagem():
    """🪤 Os jobs de origem são anteriores ao conserto de 24/08 e ainda dizem
    'Reprocessar pode completar a planilha'. Copiar isso seria reintroduzir o
    conselho que gasta o reprocesso grátis do cliente por nada."""
    r = _rodar(
        ["A leitura de '4366-EL-E_libredwg.dxf' pode estar INCOMPLETA (cortada "
         "por tamanho — li 162 itens). Reprocessar pode completar a planilha."],
        [])
    corte = [a for a in r if "INCOMPLETA" in a][0]
    assert "Reprocessar pode completar a planilha." not in corte
    assert "NÃO resolve" in corte


# ══════════════════════════════════════════════════════════════════════════
#  O que NÃO pode ter sido perdido
# ══════════════════════════════════════════════════════════════════════════
def test_a_procedencia_por_prancha_e_sempre_o_primeiro():
    r = _rodar([], [])
    assert r[0] == "PROCEDENCIA"


def test_avisos_diferentes_continuam_TODOS():
    """Controle: a dedup por família não pode engolir aviso de tipo diferente."""
    r = _rodar(["4366-EL-B_libredwg.dxf: não consegui ler geometria mensurável."],
               ["Escala não conferida por cota em 4366-VA-E."])
    assert len([a for a in r if a != "PROCEDENCIA"]) == 2


def test_familia_reconhece_os_tipos_reais():
    f = NS["_merge_familia_aviso"]
    assert f("⚠ 3 prancha(s) não entraram nesta planilha") == "pranchas_faltando"
    assert f("7 arquivo(s) precisaram do leitor alternativo (plano B): X") == "plano_b"
    assert f("⚠ Não encontramos a área total do projeto") == "sem_area"
    assert f("✅ Escala conferida pelo próprio desenho — X") == "escala_ok"
    assert f("Escala não conferida por cota em X") == "escala_sem_cota"
    assert f("A leitura de 'X.dxf' pode estar INCOMPLETA (cortada por tamanho)").startswith("corte")


# ══════════════════════════════════════════════════════════════════════════
#  🚨 A quantidade tem que andar colada na SUA prancha
# ══════════════════════════════════════════════════════════════════════════
def test_cada_quantidade_sai_com_a_prancha_certa():
    """🚨 Auditoria de 25/08. As quantidades saiam de `linhas` (ordenadas por
    TAMANHO) e as pranchas de `pranchas` (ordem ALFABETICA), e as duas listas
    eram juntadas por POSICAO. No projeto do cliente-19 saiu:

        "CFTV (17 + 13 + 1 em 3073-AQ-E, 4366-EL-E e 4366-LO-E)"

    quando o 17 e da EL-E e o 13 e da AQ-E. Trocado — e o e-mail dele ja tinha
    saido assim, mandando conferir o numero errado na prancha errada.

    Duas listas so podem ser emparelhadas por posicao se forem ordenadas pelo
    MESMO criterio. Aqui nao eram."""
    sob = [{"codigo": "CFTV", "unidade": "un",
            "pranchas": ["3073-AQ-E_libredwg.dxf", "4366-EL-E_libredwg.dxf",
                         "4366-LO-E_libredwg.dxf"],
            "linhas": [{"prancha": "4366-EL-E_libredwg.dxf", "quantidade": 17},
                       {"prancha": "3073-AQ-E_libredwg.dxf", "quantidade": 13},
                       {"prancha": "4366-LO-E_libredwg.dxf", "quantidade": 1}]}]
    aviso = NS["_merge_avisos"]({"warnings": []}, {"warnings": []},
                                {"pranchas": []}, 179, True, "P", sob)[1]
    assert "17 em 4366-EL-E" in aviso, aviso
    assert "13 em 3073-AQ-E" in aviso, aviso
    assert "1 em 4366-LO-E" in aviso, aviso
    # e o formato antigo, que junta tudo e depois lista as pranchas, morreu
    assert "17 + 13 + 1 em" not in aviso


def test_o_aviso_usa_nome_de_prancha_legivel():
    """O cliente enviou .dwg; '_libredwg.dxf' e artefato NOSSO de conversao."""
    sob = [{"codigo": "IVP", "unidade": "un",
            "pranchas": ["4366-EL-E_libredwg.dxf"],
            "linhas": [{"prancha": "4366-EL-E_libredwg.dxf", "quantidade": 22}]}]
    aviso = NS["_merge_avisos"]({"warnings": []}, {"warnings": []},
                                {"pranchas": []}, 179, True, "P", sob)[1]
    assert "_libredwg" not in aviso
