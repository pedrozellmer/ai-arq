# -*- coding: utf-8 -*-
"""E-mail, nome, nome do projeto e pergunta do chat NÃO vão na URL.

🩸 25/09/2026. O upload do painel montava
    POST /api/process?typology=…&project_name=…&user_id=…&user_email=…&user_name=…
e o chat montava
    POST /api/agent/ask?job_id=…&question=<o que o cliente digitou>
O uvicorn grava a URL inteira em toda requisição (e o preflight `OPTIONS` grava
de novo). Medido no log do Render: 18 linhas com e-mail em ~30 h, 8 pessoas
diferentes — e um nome de projeto que era o nome do cliente final. Qualquer
proxy no caminho guarda a mesma coisa.

🔑 O conserto tem três camadas. Este arquivo cobra a 1ª; a 2ª e a 3ª estão
em `test_o_dono_vem_do_login_e_o_log_nao_anota.py`:
  1. A TELA não põe dado pessoal na URL: o nome do projeto e a pergunta vão
     no corpo; id, e-mail e nome nem saem da tela.
  2. O SERVIDOR tira e-mail e nome do login (o token), aceita o nome do
     projeto no form e a pergunta no JSON — e ainda entende a URL velha, pra
     aba aberta antes do deploy.
  3. O LOG DE ACESSO mascara esses campos se eles chegarem mesmo assim.

🪤 A camada 1 é julgada RODANDO o JavaScript do `dashboard.html` (dukpy) e
olhando a URL que o XHR abriria — procurar texto no arquivo não vê um
`params.user_email = …` que vira URL três linhas depois. E o julgamento é pelo
VALOR (o e-mail aparece na URL?), não pelo nome da chave.
"""
import io
import json
import os
import re
import sys
from urllib.parse import unquote_plus

import dukpy  # noqa: F401  — falta dele é ERRO, nunca skip

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import log_de_acesso  # noqa: E402
from _navegador import sem_await  # noqa: E402

EMAIL = "cliente@exemplo.com"
NOME = "Cliente Exemplo"
PROJETO = "Projeto Exemplo"
UID = "00000000-0000-4000-8000-000000000001"
PERGUNTA = "quantos metros de rodapé tem na sala do Cliente Exemplo?"


def _site(nome):
    return io.open(os.path.join(_RAIZ, nome), encoding="utf-8").read()


def _vazamentos(url, valores):
    """Quais destes valores aparecem na URL — crua ou decodificada."""
    crua, lida = url or "", unquote_plus(url or "")
    return [v for v in valores if v in crua or v in lida]


# ══════════════════════════════════════════════════════════════════════════
#  1. A TELA — o JavaScript do dashboard RODA e a gente olha a URL
# ══════════════════════════════════════════════════════════════════════════
# Um navegador do tamanho do trecho: formulário preenchido, cliente logado,
# e um XHR/authFetch que só ANOTA o que o site pediu.
_STUBS = r"""
var __abriu = null, __enviou = null, __cab = {}, __chamou = null;
function FormData() { this._e = []; }
FormData.prototype.append = function (k, v) {
  this._e.push([k, (v && typeof v === 'object' && v.name) ? v.name : String(v)]);
};
function XMLHttpRequest() { this.upload = {}; }
XMLHttpRequest.prototype.open = function (m, u) { __abriu = [m, u]; };
XMLHttpRequest.prototype.setRequestHeader = function (k, v) { __cab[k] = v; };
XMLHttpRequest.prototype.send = function (b) { __enviou = b; };
function URLSearchParams(o) {
  var p = [];
  if (o && typeof o === 'object') {
    for (var k in o) p.push(encodeURIComponent(k) + '=' + encodeURIComponent(String(o[k])));
  } else if (o) { p.push(String(o).replace(/^\?/, '')); }
  this._p = p;
  this.set = function (k, v) { this._p.push(encodeURIComponent(k) + '=' + encodeURIComponent(String(v))); };
  this.append = this.set;
  this.toString = function () { return this._p.join('&'); };
}
var __campos = %(campos)s;
var document = {
  getElementById: function (id) { return (id in __campos) ? { value: __campos[id] } : null; },
  querySelectorAll: function () { return []; }
};
var window = { API_UPLOAD_BASE: 'https://api.exemplo.test', trackEvent: null,
               fmtDataBR: function () { return '25/09/2026'; } };
var trackEvent = null;
var API_BASE = 'https://api.exemplo.test';
var selectedFiles = [{ name: 'planta.dwg' }];
var accessToken = 'token-de-teste';
var currentUser = %(usuario)s;
var currentJobId = 'job0001';
var q = %(pergunta)s;
var agentConversation = [{ role: 'user', content: 'oi' }, { role: 'assistant', content: 'ola' }];
function authFetch(u, o) { __chamou = [u, o]; return { json: function () { return {}; } }; }
"""


def _stubs():
    return _STUBS % {
        "campos": json.dumps({"project-name": PROJETO,
                              "project-typology": "residential",
                              "project-type": "arquitetura",
                              "project-area": "120",
                              "project-pe-direito": "2,8"}),
        "usuario": json.dumps({"id": UID, "email": EMAIL,
                               "user_metadata": {"full_name": NOME}}),
        "pergunta": json.dumps(PERGUNTA, ensure_ascii=False),
    }


def _trecho_do_upload(site):
    """Da criação do FormData até o `xhr.send` — o envio inteiro, nada mais."""
    i = site.index("const formData = new FormData();")
    k = site.index("xhr.send(formData);", i)
    fim = site.index("});", k) + 3
    trecho = site[i:fim]
    # 🧪 controle do recorte: janela errada mediria outra coisa calada.
    assert "/api/process" in trecho and "URLSearchParams" in trecho, trecho[:300]
    assert len(trecho) < 12000, "o recorte do upload engoliu o arquivo: %d" % len(trecho)
    return trecho


def _trecho_do_chat(site):
    i = site.index("const url = `${API_BASE}/api/agent/ask")
    fim = site.index("});", i) + 3
    trecho = site[i:fim]
    assert "authFetch(url" in trecho and len(trecho) < 1500, trecho[:300]
    return trecho


def _roda_upload(trecho):
    js = "(function () { %s })();" % sem_await(trecho)
    return dukpy.evaljs([_stubs(), js,
                         "({metodo: __abriu && __abriu[0], url: __abriu && __abriu[1],"
                         " corpo: __enviou ? __enviou._e : null,"
                         " bearer: __cab['Authorization'] || ''})"])


def _roda_chat(trecho):
    js = "(function () { %s })();" % sem_await(trecho)
    return dukpy.evaljs([_stubs(), js,
                         "({url: __chamou && __chamou[0],"
                         " corpo: __chamou && __chamou[1] && __chamou[1].body})"])


def test_o_upload_nao_poe_dado_do_cliente_na_URL():
    r = _roda_upload(_trecho_do_upload(_site("dashboard.html")))
    assert r["metodo"] == "POST", r
    assert r["url"].startswith("https://api.exemplo.test/api/process"), r["url"]
    vazou = _vazamentos(r["url"], [EMAIL, NOME, PROJETO, UID])
    assert not vazou, (
        "o upload voltou a pôr dado do cliente na URL (%s): %s — isso fica "
        "gravado no log de acesso do servidor a cada projeto enviado"
        % (", ".join(vazou), r["url"]))
    # a URL ainda leva o que NÃO é pessoal: prova que o recorte viu a query
    assert "typology=residential" in r["url"], r["url"]
    assert r["bearer"] == "Bearer token-de-teste", (
        "sem o Bearer o servidor não sabe quem é o dono — e o e-mail agora vem dele")


def test_o_nome_do_projeto_vai_no_CORPO_do_upload():
    r = _roda_upload(_trecho_do_upload(_site("dashboard.html")))
    corpo = [tuple(x) for x in (r["corpo"] or [])]
    assert ("project_name", PROJETO) in corpo, (
        "o nome do projeto sumiu do envio — o servidor gravaria 'Sem nome': %r" % corpo)
    assert ("files", "planta.dwg") in corpo, corpo


def test_a_pergunta_do_chat_vai_no_CORPO_e_nao_na_URL():
    r = _roda_chat(_trecho_do_chat(_site("dashboard.html")))
    assert r["url"] == "https://api.exemplo.test/api/agent/ask?job_id=job0001", r["url"]
    assert not _vazamentos(r["url"], [PERGUNTA, "rodapé", NOME]), r["url"]
    corpo = json.loads(r["corpo"])
    assert corpo.get("question") == PERGUNTA, corpo
    assert len(corpo.get("history") or []) == 2, (
        "a pergunta foi pro corpo mas o histórico da conversa se perdeu: %r" % corpo)


# 🧪 CONTROLE POSITIVO — a tela de ANTES, no MESMO julgamento. As linhas abaixo
# são as de produção até 25/09/2026, verbatim.
_UPLOAD_DE_ANTES = (
    ("const params = { typology, project_type: projectType };",
     "const params = { typology, project_type: projectType, project_name: projectName };"
     "\n      if (currentUser?.id) {"
     "\n        params.user_id = currentUser.id;"
     "\n        if (currentUser.email) params.user_email = currentUser.email;"
     "\n        const displayName = currentUser.user_metadata?.full_name"
     "\n          || currentUser.user_metadata?.name"
     "\n          || '';"
     "\n        if (displayName) params.user_name = displayName;"
     "\n      }"),
)
_CHAT_DE_ANTES = (
    "const url = `${API_BASE}/api/agent/ask?job_id=${currentJobId}&question="
    "${encodeURIComponent(q)}`;")


def _tela_de_antes():
    site = _site("dashboard.html")
    for novo, velho in _UPLOAD_DE_ANTES:
        assert novo in site, "a linha que o controle troca sumiu: %r" % novo
        site = site.replace(novo, velho, 1)
    return site


def test_CONTROLE_a_tela_de_ANTES_REPROVA_no_mesmo_julgamento():
    r = _roda_upload(_trecho_do_upload(_tela_de_antes()))
    vazou = _vazamentos(r["url"], [EMAIL, NOME, PROJETO, UID])
    assert set(vazou) == {EMAIL, NOME, PROJETO, UID}, (
        "o julgamento não enxerga o vazamento do código de 25/09 — o teste de "
        "cima é verde falso. Achei só %r em %s" % (vazou, r["url"]))

    chat = _roda_chat(_CHAT_DE_ANTES + "\nconst res = authFetch(url, { method: 'POST' });")
    assert _vazamentos(chat["url"], [PERGUNTA]), chat["url"]


# ── A rede grossa: TODA página e script do site ─────────────────────────────
# O julgamento que roda o JS cobre as duas chamadas que vazaram. Esta peneira
# pega a PRÓXIMA — em qualquer arquivo — pela forma: chave pessoal escrita numa
# URL, ou posta num objeto que vira `new URLSearchParams(...)`.
_CHAVES = tuple(log_de_acesso.CHAVES_PESSOAIS) + (
    "nome", "full_name", "telefone", "phone", "whatsapp", "cpf", "cnpj")
_ALT = "|".join(_CHAVES)
_RE_NA_URL = re.compile(r"[?&](%s)=" % _ALT)
_RE_USP = re.compile(r"new\s+URLSearchParams\(\s*([A-Za-z_$][\w$]*)\s*\)")
_RE_USP_VAR = re.compile(r"([A-Za-z_$][\w$]*)\s*=\s*new\s+URLSearchParams\(")
_FORA = ("backend", "_archive", "node_modules", ".git", ".claude")


def _arquivos_do_site():
    for raiz, dirs, nomes in os.walk(_RAIZ):
        dirs[:] = [d for d in dirs if d not in _FORA]
        for n in nomes:
            if n.endswith((".html", ".js")):
                yield os.path.join(raiz, n)


def _peneira(src):
    """[(linha, chave)] de dado pessoal indo pra uma URL."""
    achados = []

    def _linha(pos):
        return src.count("\n", 0, pos) + 1

    for m in _RE_NA_URL.finditer(src):
        ini = src.rfind("\n", 0, m.start()) + 1
        fim = src.find("\n", m.end())
        linha = src[ini:fim if fim > 0 else None]
        # `mailto:`/WhatsApp é link pro app de e-mail/conversa do visitante,
        # não requisição ao nosso servidor.
        if "mailto:" in linha or "wa.me" in linha:
            continue
        achados.append((_linha(m.start()), m.group(1)))
    # objeto que vira query: `params.user_email = …` / `{ project_name: … }`
    for m in _RE_USP.finditer(src):
        var = re.escape(m.group(1))
        antes = src[max(0, m.start() - 4000):m.start()]
        for k in re.finditer(r"\b%s\s*\.\s*(%s)\s*=" % (var, _ALT), antes):
            achados.append((_linha(m.start()), k.group(1)))
        lit = re.search(r"\b%s\s*=\s*\{([^{}]*)\}" % var, antes)
        if lit:
            for k in re.finditer(r"\b(%s)\b" % _ALT, lit.group(1)):
                achados.append((_linha(m.start()), k.group(1)))
    # `const p = new URLSearchParams(); p.set('email', …)`
    for m in _RE_USP_VAR.finditer(src):
        var = re.escape(m.group(1))
        depois = src[m.end():m.end() + 3000]
        for k in re.finditer(r"\b%s\s*\.\s*(?:set|append)\(\s*['\"](%s)['\"]"
                             % (var, _ALT), depois):
            achados.append((_linha(m.start()), k.group(1)))
    return achados


def test_nenhuma_pagina_do_site_poe_dado_pessoal_na_URL():
    arquivos = list(_arquivos_do_site())
    assert len(arquivos) >= 20, "a peneira quase não achou arquivo: %d" % len(arquivos)
    sujos = []
    for caminho in arquivos:
        src = io.open(caminho, encoding="utf-8", errors="replace").read()
        for linha, chave in _peneira(src):
            sujos.append("%s:%d (%s)" % (os.path.relpath(caminho, _RAIZ), linha, chave))
    assert not sujos, (
        "dado pessoal indo pra URL — fica gravado no log de acesso. Mande no "
        "corpo (FormData/JSON) ou deixe o servidor tirar do login: %s" % sujos)


def test_CONTROLE_a_peneira_ACHA_as_formas_de_25_09():
    antes = _tela_de_antes()
    i = antes.index("const params = { typology")
    achou = {c for _, c in _peneira(antes[i:i + 3000])}
    assert {"project_name", "user_email", "user_name"} <= achou, achou
    assert {c for _, c in _peneira(_CHAT_DE_ANTES)} == {"question"}
    p = "const p = new URLSearchParams(); p.set('email', u.email);"
    assert {c for _, c in _peneira(p)} == {"email"}


def test_CONTROLE_a_peneira_nao_acusa_o_que_e_legitimo():
    ok = ("fetch(`${API_BASE}/api/credits/balance?days=7&limit=20`);\n"
          "const p = new URLSearchParams({ template: t });\n"
          "a.href = 'mailto:' + e + '?subject=x&body=' + encodeURIComponent('email=' + e);\n"
          "fd.append('email', e);\n")
    assert _peneira(ok) == [], _peneira(ok)
