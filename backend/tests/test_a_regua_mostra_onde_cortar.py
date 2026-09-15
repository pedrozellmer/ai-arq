# -*- coding: utf-8 -*-
"""O painel da régua tem que ENTREGAR na tela tudo o que a função calcula.

🩸 15/09/2026 — a função `admin_regua_cobranca` existe desde 06/09 e calcula
SETE chaves. A tela lia QUATRO. `mediana_linhas_medidas` e `total_nao_avaliadas`
eram calculadas no banco, trafegavam até o navegador e morriam lá — e a
mediana era exatamente o número que o Pedro precisava pra decidir onde cortar
a régua. Nove dias, ninguém viu, porque nada reprovava chave órfã.

É o padrão que a varredura de 14/09 achou em SETE das nove lentes: o produto
coleta o dado caro, grava, e nunca lê. Este arquivo fecha a porta neste ponto.

🪤 E o guarda não pode ler COMENTÁRIO: a explicação que acabei de escrever no
admin.html cita `mediana_linhas_medidas` pelo nome. Guarda que lê a própria
anotação aprova o defeito que ela descreve — caí nisso três vezes em 14/09.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import (corpo_js, sem_comentarios_js,  # noqa: E402
                    sem_comentarios_sql)

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)
_SQL = os.path.join(_BACKEND, "migrations_pendentes", "admin_regua_cobranca.sql")
_ADMIN = os.path.join(_RAIZ, "admin.html")


def _sql():
    assert os.path.exists(_SQL), (
        "a definição da régua sumiu do repositório — ela voltou a existir só "
        "dentro do banco, e quem quiser saber o que a tela do dinheiro calcula "
        "vai ter que perguntar ao Postgres")
    return io.open(_SQL, encoding="utf-8").read()


def _chaves_que_a_funcao_devolve():
    """As chaves do `json_build_object` — só as do nível de cima."""
    corpo = _sql()
    i = corpo.index("select json_build_object(")
    # as chaves de topo estão sempre no começo de uma linha com 2 espaços
    return [m.group(1) for m in
            re.finditer(r"^  '([a-z_]+)',", corpo[i:], re.M)]


def _bloco_da_tela():
    return sem_comentarios_js(corpo_js("_blocoRegua", "admin.html"))


def test_a_tela_LE_todas_as_chaves_que_a_funcao_calcula():
    """🚨 O guarda que teria pego o defeito de 06/09 no dia seguinte."""
    chaves = _chaves_que_a_funcao_devolve()
    assert len(chaves) >= 7, (
        "a varredura achou só %d chaves no json_build_object — o padrão de "
        "busca parou de enxergar a função: %s" % (len(chaves), chaves))
    bloco = _bloco_da_tela()
    orfas = [k for k in chaves if k not in bloco]
    assert not orfas, (
        "a função calcula estas chaves e a tela não lê nenhuma delas: %s. "
        "Dado caro coletado e jogado fora é o defeito mais repetido desta "
        "casa — ou mostre na tela, ou pare de calcular." % orfas)


def test_CONTROLE_a_varredura_ACHA_uma_chave_orfa():
    """O guarda acima só vale se souber acusar. Aqui provo que uma chave que a
    tela não lê é encontrada — e que um COMENTÁRIO citando o nome não salva."""
    chaves = _chaves_que_a_funcao_devolve()
    falso = "function _blocoRegua(){ /* usa " + chaves[0] + " */ return d.por_mes; }"
    limpo = sem_comentarios_js(falso)
    assert chaves[0] not in limpo, (
        "`sem_comentarios_js` deixou passar o nome escrito no comentário — o "
        "guarda passaria a aprovar chave órfã que eu mesmo documentei")


def test_a_divisao_por_zero_esta_protegida_no_SQL():
    """🪤 Existe projeto com `linhas_total = 0`. Divisão por zero aqui não
    derruba só a faixa nova — derruba a FUNÇÃO INTEIRA, e o painel perde junto
    os números que já funcionavam."""
    sql = _sql()
    i = sql.index("as fracao")
    linha = sql[max(0, i - 160):i]
    assert "nullif(linhas_total, 0)" in linha, (
        "a fração perdeu o `nullif` — um projeto com linhas_total=0 derruba a "
        "régua toda: %r" % linha)


def test_o_SQL_do_repo_NUNCA_manda_dropar_a_funcao():
    """🪤 `DROP FUNCTION` apagaria o `proacl` (service_role=X) e a régua sumiria
    da tela EM SILÊNCIO: `_regua_cobranca_resumo` engole o erro e devolve None.
    A função é RETURNS json (escalar), então CREATE OR REPLACE sempre basta."""
    # 🪤 15/09: este guarda reprovou o arquivo CORRETO na primeira execução,
    # porque o cabeçalho que eu tinha acabado de escrever EXPLICA, em
    # português, por que nunca se deve dropar esta função. Quarta vez no
    # mesmo dia que um guarda meu lê a minha própria anotação.
    sql = sem_comentarios_sql(_sql()).lower()
    assert "drop function" not in sql, (
        "o arquivo da régua ganhou um DROP FUNCTION — o REPLACE basta, e o "
        "DROP leva junto a permissão do service_role")
    assert "create or replace function" in sql


# ─────────────────────────────────────────────────────────────────────────────
#  A tela RODANDO — não o fonte dela
#
#  🩸 15/09/2026. A primeira versão destes dois guardas procurava TEXTO no
#  corpo de `_blocoRegua` ("tem a palavra faixas? tem rotulo?") e a mutação
#  provou os dois cegos:
#    • `if (n === 0) return '';` dentro do laço — a faixa vazia sumia da tela
#      e todas as palavras que o guarda cobrava continuavam lá;
#    • tirar o `${corte}` do template — o bloco inteiro deixava de ser
#      inserido, e o código que o MONTA seguia no arquivo, intacto.
#  Guarda que confere ingrediente não sabe se o prato chegou à mesa.
# ─────────────────────────────────────────────────────────────────────────────

_REGUA_FALSA = """
var COSTS_REGUA = {
  preco_base: 97,
  por_mes: [{mes:'2026-09', entregas:39, cobraveis:15, nao_avaliadas:0, receita_a_97:1455}],
  total_entregas: 164, total_cobraveis: 66, total_nao_avaliadas: 2,
  mediana_linhas_medidas: 0,
  mediana_linhas_cobravel: 14.5, mediana_pct_cobravel: 27.1,
  cobraveis_ate_2_linhas: 8,
  faixas: [{ordem:1, rotulo:'ate 10%', n:6}, {ordem:2, rotulo:'10 a 25%', n:21},
           {ordem:3, rotulo:'25 a 50%', n:30}, {ordem:4, rotulo:'mais de 50%', n:9},
           {ordem:5, rotulo:'sem base', n:0}]
};
function costFmt(v){ return 'R$ ' + Number(v).toFixed(2); }
"""


def _html_da_regua(regua_js=_REGUA_FALSA):
    from _jsbancada import funcao_js, motor
    js = motor(regua_js + funcao_js("_blocoRegua", "admin.html"))
    return js.evaljs("_blocoRegua()")


def test_a_faixa_de_corte_SAI_no_html():
    """O bloco do corte tem que chegar ao HTML que a tela devolve — não basta
    existir no arquivo."""
    html = _html_da_regua()
    assert "Onde cortar" in html, (
        "o bloco do corte não saiu no HTML: o painel voltou a mostrar só a "
        "tabela, e a decisão do corte volta a ser no escuro")
    for rotulo in ("ate 10%", "10 a 25%", "25 a 50%", "mais de 50%"):
        assert rotulo in html, "a faixa %r não foi desenhada: %s" % (rotulo, html[:300])
    assert "14.5" in html and "27.1" in html, (
        "a mediana das cobráveis não chegou na tela — é o número que decide "
        "onde cortar")
    assert ">8<" in html or " 8 " in html or ">8 " in html, (
        "o aviso dos projetos que mediram 2 linhas ou menos sumiu")


def test_a_faixa_VAZIA_continua_na_tela():
    """🚨 Faixa com zero caso tem que aparecer. Some quem tem 0 e a distribuição
    passa a mentir por omissão sobre onde NÃO há caso — ausência virando
    afirmação, que é a regra dura nº1 em outra roupa."""
    html = _html_da_regua()
    assert "sem base" in html, (
        "a faixa de zero caso foi escondida — quem olhar vai concluir que "
        "aquela faixa não existe, em vez de que ela está vazia")


def test_CONTROLE_sem_faixa_nenhuma_a_tela_NAO_inventa_bloco():
    """O outro lado: se a função não devolver faixas (RPC velha, leitura
    falhada), a tela não pode desenhar uma distribuição vazia como se fosse
    medição. Sem medição, o bloco não aparece."""
    sem = _REGUA_FALSA.replace("faixas: [{ordem:1", "faixas: [].concat([]), _ig: [{ordem:1")
    html = _html_da_regua(sem)
    assert "Onde cortar" not in html, (
        "sem faixas a tela desenhou o bloco do corte assim mesmo — "
        "distribuição vazia lida como 'não há casos' é afirmação falsa")
    assert "Régua de cobrança" in html, (
        "a tabela de sempre sumiu junto: a falta da faixa nova não pode levar "
        "embora o que já funcionava")
