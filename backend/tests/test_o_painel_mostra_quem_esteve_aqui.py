# -*- coding: utf-8 -*-
"""A lista de usuários tem que responder "quem esteve aqui", não só "quem chegou".

🩸 08/09/2026 — O PEDRO OLHOU O PAINEL E DISSE "TEM NINGUÉM". ESTAVA CERTO.

O lead mais forte da semana (duas contas em 04/09, a corporativa destravada na
mão) voltou hoje 08:23, entrou pela primeira vez e completou a ficha às 08:24.
No painel ele aparecia em **7º lugar, carimbado com 04/09** — porque a lista
ordenava por `auth_created_at` e por mais nada. Quem volta afunda com a data
velha, e quem volta é o sinal mais raro que a gente tem.

📏 Medido antes de mexer, sem inflar: **10 das 120 contas** já estiveram aqui
num dia diferente do dia em que chegaram. É pouca gente — e é justamente a
que importa. 🪤 É PISO: `last_sign_in_at` só muda em login novo; sessão
retomada não conta.

🪤 A ARMADILHA QUE ESTE GUARDA FECHA: usar só `last_sign_in_at` como "atividade"
deixa de fora quem trabalhou hoje numa sessão que já estava aberta — o campo não
se mexe. Por isso a atividade é o MAIOR entre login, último projeto e a chegada.
Guarda que só olhasse o login recriaria o defeito com outra roupa.

Este arquivo RODA o JS do painel num duktape — ler o texto do `admin.html`
provaria que a linha existe, não que ela ordena.
"""
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from _bancada_js import Pagina  # noqa: E402

_ADMIN = os.path.join(_RAIZ, "admin.html")

# Stubs do que a fatia usa e que mora fora dela. Nada aqui decide ordem —
# a ordem é do código de produção.
_PRELUDIO = r"""
var allUsers = [];
var activeUsersFilter = 'todos';
window.__renderizado = null;
function _userMatchesFilter(u, f) { return true; }
function renderUsers(list) { window.__renderizado = list; }
document.getElementById = function (id) {
  if (id === 'search-users') return { value: '' };
  return null;
};
1;
"""
# 🪤 o `1;` no fim não é enfeite: o dukpy serializa o valor da ÚLTIMA expressão,
# e atribuição de função não vira JSON — sem ele, "Invalid Result Value" e os
# 10 testes morrem antes de exercitar uma linha do painel.


def _fatia_da_ordem():
    """Do bloco da ordem até o fim de applyUsersView — o caminho real."""
    src = io.open(_ADMIN, encoding="utf-8").read()
    i = src.index("// ── Ordem da lista")
    j = src.index("// A busca compoe com o chip ativo", i)
    return src[i:j]


def _pagina():
    p = Pagina(arquivos=(), prelude_extra=_PRELUDIO)
    p.eval(_fatia_da_ordem() + "\n;1;")
    return p


def _semeia(p, usuarios):
    import json
    p.eval("allUsers = " + json.dumps(usuarios) + "; 1;")


def _ordem_visivel(p):
    import json
    return json.loads(p.eval(
        "JSON.stringify((window.__renderizado || []).map(function(u){return u.email;}))"))


# Três pessoas, o caso real de 08/09 em miniatura.
_CHEGOU_HOJE_CEDO = {"email": "a@x", "auth_created_at": "2026-09-08T11:20:56Z",
                     "last_sign_in_at": "2026-09-08T11:20:56Z"}
_CHEGOU_HOJE_TARDE = {"email": "b@x", "auth_created_at": "2026-09-08T11:52:52Z",
                      "last_sign_in_at": "2026-09-08T11:52:52Z"}
_VOLTOU_HOJE = {"email": "voltou@x", "auth_created_at": "2026-09-04T19:02:41Z",
                "last_sign_in_at": "2026-09-08T11:23:15Z"}
_TRIO = [_CHEGOU_HOJE_CEDO, _CHEGOU_HOJE_TARDE, _VOLTOU_HOJE]


# ══════════════════════════════════════════════════════════════════════════
#  O defeito
# ══════════════════════════════════════════════════════════════════════════
def test_quem_voltou_hoje_nao_fica_atras_de_quem_chegou_antes_dele():
    p = _pagina()
    _semeia(p, _TRIO)
    p.chama("applyUsersView(); 1;")
    ordem = _ordem_visivel(p)

    assert ordem[0] == "b@x", "o mais recente de todos continua em 1º"
    assert ordem.index("voltou@x") < ordem.index("a@x"), (
        "quem esteve aqui às 11:23 tem que vir antes de quem esteve às 11:20;\n"
        "ordenando pela CONTA, ele afunda pra última posição: " + str(ordem))


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLE POSITIVO — a outra ordem tem que continuar existindo e funcionando
# ══════════════════════════════════════════════════════════════════════════
def test_ordenar_por_chegada_continua_disponivel_e_afunda_quem_voltou():
    p = _pagina()
    _semeia(p, _TRIO)
    p.chama("setUsersOrder('chegada'); 1;")
    ordem = _ordem_visivel(p)

    assert ordem[-1] == "voltou@x", (
        "'chegou na plataforma' tem que ordenar pela CONTA — se as duas opções\n"
        "derem a mesma lista, o seletor é enfeite: " + str(ordem))


def test_o_seletor_volta_pra_atividade():
    p = _pagina()
    _semeia(p, _TRIO)
    p.chama("setUsersOrder('chegada'); setUsersOrder('atividade'); 1;")
    ordem = _ordem_visivel(p)
    assert ordem.index("voltou@x") < ordem.index("a@x")


def test_valor_desconhecido_no_seletor_e_normalizado():
    """🪤 A 1ª versão deste teste olhava a LISTA e não podia falhar.

    Com `usersOrder = v` cru, 'xpto' cai no mesmo ramo do ternário e a ordem
    sai idêntica — mutante EQUIVALENTE, não guarda cego. O que a linha de
    saneamento protege é o ESTADO: se amanhã existir uma terceira ordem, um
    valor solto passa a decidir. É o estado que este teste olha.
    """
    p = _pagina()
    _semeia(p, _TRIO)
    p.chama("setUsersOrder('xpto'); 1;")
    assert p.eval("usersOrder") == "atividade"
    assert _ordem_visivel(p)[0] == "b@x", "e a lista continua ordenada"


# ══════════════════════════════════════════════════════════════════════════
#  A armadilha: atividade não é só login
# ══════════════════════════════════════════════════════════════════════════
def test_projeto_de_hoje_conta_como_atividade_mesmo_sem_login_novo():
    """🪤 `last_sign_in_at` não se mexe em sessão retomada. Quem entrou ontem e
    trabalhou hoje some da lista se a atividade for só o login."""
    p = _pagina()
    trabalhou = {"email": "trabalhou@x", "auth_created_at": "2026-09-01T12:00:00Z",
                 "last_sign_in_at": "2026-09-07T12:00:00Z",
                 "ultimo_projeto": "2026-09-08T13:00:00Z"}
    _semeia(p, [_CHEGOU_HOJE_TARDE, trabalhou])
    p.chama("applyUsersView(); 1;")
    ordem = _ordem_visivel(p)
    assert ordem[0] == "trabalhou@x", (
        "subiu projeto às 13h e ficou atrás de quem só entrou às 11h52: a\n"
        "atividade está olhando só o login. " + str(ordem))


def test_quem_nunca_entrou_nao_some_da_lista():
    """Cadastro incompleto tem `last_sign_in_at` nulo — não pode virar ordem 0
    e desaparecer no fim junto com o lixo."""
    p = _pagina()
    nunca = {"email": "nunca@x", "auth_created_at": "2026-09-08T11:59:00Z",
             "last_sign_in_at": None}
    _semeia(p, [_VOLTOU_HOJE, nunca])
    p.chama("applyUsersView(); 1;")
    ordem = _ordem_visivel(p)
    assert ordem[0] == "nunca@x", (
        "sem login, a chegada é a atividade mais recente que existe: " + str(ordem))


# ══════════════════════════════════════════════════════════════════════════
#  O selo "voltou" — o que explica a posição
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("u,esperado", [
    (_VOLTOU_HOJE, True),
    (_CHEGOU_HOJE_CEDO, False),
    ({"email": "n@x", "auth_created_at": "2026-09-08T11:00:00Z",
      "last_sign_in_at": None}, False),
])
def test_o_selo_voltou_diz_a_verdade(u, esperado):
    import json
    p = _pagina()
    r = p.eval("_voltouDepois(" + json.dumps(u) + ") ? 1 : 0")
    assert bool(r) == esperado, (
        "o selo 'voltou' tem que marcar dia DIFERENTE do dia da chegada, e só")


def test_a_lista_original_nao_e_reordenada():
    """🪤 `allUsers` é lido por outras partes do painel que não pediram ordem
    nenhuma (origem, detalhe do usuário). Ordenar no lugar as contamina."""
    p = _pagina()
    _semeia(p, _TRIO)
    p.chama("applyUsersView(); 1;")
    import json
    original = json.loads(p.eval(
        "JSON.stringify(allUsers.map(function(u){return u.email;}))"))
    assert original == ["a@x", "b@x", "voltou@x"], (
        "applyUsersView reordenou allUsers no lugar: " + str(original))
