# -*- coding: utf-8 -*-
"""Três painéis do admin punham texto do CLIENTE cru no innerHTML (auditoria SI, 27/09/2026).

- Filhotes: o nome do projeto (o dono digita no envio) e o e-mail do dono.
- "Onde o motor erra": a descrição que o cliente digita na revisão (`edits`, gravada como veio).
- Escolha de pranchas (merge): nome da prancha, motivo da juíza, itens deixados de fora, código,
  unidade e os bloqueios.

O resto do admin já passava tudo por `_escHtml` (ver test_o_que_o_cliente_digita_nao_vira_html_no_admin);
estes três ficaram de fora. A sessão que abre esses painéis é a do admin.

🔑 O guarda EXECUTA as funções de verdade do admin.html num duktape, com um texto marcado em cada
campo, e olha o HTML que sai. Ler o fonte só provaria que a palavra `_escHtml` existe em algum lugar.
"""
import io
import json
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from _bancada_js import Pagina  # noqa: E402

_ADMIN = os.path.join(os.path.dirname(os.path.dirname(_AQUI)), "admin.html")

MARCA = '<b data-teste="x">MARCA</b>'
ESCAPADA = "&lt;b data-teste=&quot;x&quot;&gt;MARCA&lt;/b&gt;"


def _fonte():
    return io.open(_ADMIN, encoding="utf-8").read()


def _funcao(src, nome):
    """O texto de `function nome(...) { ... }`, pelas chaves (o corpo destas funções não tem chave solta em string)."""
    i = src.index("function %s(" % nome)
    j = src.index("{", src.index(")", i))
    prof = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            prof += 1
        elif src[k] == "}":
            prof -= 1
            if prof == 0:
                return src[i:k + 1]
    raise AssertionError("não achei o fim de %s" % nome)


def _constante(src, nome):
    """O texto de `const nome = { ... };` (tabela de rótulos que os painéis leem)."""
    i = src.index("const %s = {" % nome)
    return src[i:src.index("\n};", i) + 3]


_FUNCOES = ("_escHtml", "esc", "_dataCurta", "_filSituacao", "temMergeMelhor",
            "renderOndeErra", "renderFilhotes", "mergeHtml")
_CONSTANTES = ("_FIL_MOTIVO",)


def _pagina():
    src = _fonte()
    p = Pagina(arquivos=(), prelude_extra="var _filhotes = []; window.fmtBR = function (x) { return String(x || ''); }; 1;")
    for nome in _CONSTANTES:
        p.eval(_constante(src, nome).replace("const ", "var ", 1) + "\n;1;")
    for nome in _FUNCOES:
        p.eval(_funcao(src, nome) + "\n;1;")
    return p


def _html(p, chamada):
    saiu = p.eval(chamada)
    assert isinstance(saiu, str) and saiu, "a função não devolveu HTML: %r" % (saiu,)
    return saiu


def _confere(saiu, onde):
    assert MARCA not in saiu, "texto do cliente saiu CRU em %s" % onde
    assert ESCAPADA in saiu, "o texto sumiu em vez de aparecer escapado em %s (controle de legibilidade)" % onde


def test_onde_o_motor_erra_escapa_descricao_e_padrao():
    d = {"total_edicoes": 1, "com_antes": 1, "sem_antes": 0,
         "padroes": [{"padrao": MARCA, "n": 1}],
         "exemplos": [{"item": MARCA, "motor_disse": 1, "cliente_disse": 2}]}
    saiu = _html(_pagina(), "renderOndeErra(%s)" % json.dumps(d))
    _confere(saiu, "Onde o motor erra")
    assert saiu.count(ESCAPADA) >= 2, "padrão E descrição têm que sair escapados"


def test_filhotes_escapa_nome_do_projeto_e_email_do_dono():
    f = {"job_id": "ev123456", "parent_job_id": "ab12cd34", "status": "done",
         "projeto": MARCA, "cliente": MARCA,
         "antes": {"itens": 1, "medidos": 0}, "depois": {"itens": 2, "medidos": 1},
         "area_antes": None, "area_depois": None}
    saiu = _html(_pagina(), "renderFilhotes([%s])" % json.dumps(f))
    _confere(saiu, "Filhotes")
    assert saiu.count(ESCAPADA) >= 2, "nome do projeto E e-mail têm que sair escapados"


def test_escolha_de_pranchas_escapa_prancha_motivo_itens_codigo_e_bloqueio():
    d = {"merge": {"medidos": 3, "itens": 5}, "original": {"medidos": 1, "itens": 4, "nome": "p", "dono": "d"},
         "releitura": {"medidos": 2, "itens": 5}, "juiza_usada": True,
         "plano": [{"prancha": MARCA + ".dwg", "lado": "filho", "discordam": False,
                    "pai": {"medidos": 1, "itens": 2}, "filho": {"medidos": 2, "itens": 3},
                    "juiza": {"motivo": MARCA, "perdas": [MARCA]}}],
         "sobreposicoes": [{"codigo": MARCA, "unidade": MARCA, "soma_se_somar": 2, "maior_sozinho": 1,
                            "linhas": [{"quantidade": 1, "prancha": MARCA, "linhas": 1}]}],
         "bloqueios": [MARCA]}
    saiu = _html(_pagina(), "mergeHtml(%s, 'mg123456')" % json.dumps(d))
    _confere(saiu, "Escolha de pranchas")
    assert saiu.count(ESCAPADA) >= 7, (
        "prancha, motivo, item perdido, código, unidade, prancha da sobreposição e bloqueio: "
        "todos escapados (saíram %d)" % saiu.count(ESCAPADA))


def test_CONTROLE_texto_normal_continua_igual():
    """Escapar demais estraga o painel: nome comum tem que sair como está."""
    d = {"total_edicoes": 1, "com_antes": 1, "sem_antes": 0, "padroes": [],
         "exemplos": [{"item": "Alvenaria de bloco 14cm", "motor_disse": 3, "cliente_disse": 4}]}
    saiu = _html(_pagina(), "renderOndeErra(%s)" % json.dumps(d))
    assert "Alvenaria de bloco 14cm" in saiu
