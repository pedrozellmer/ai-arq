# -*- coding: utf-8 -*-
"""Escritório — revisão de segurança de 24/09/2026 (pedido do Pedro: "isso deixa o site
muito mais sensível com infos de terceiros").

O que estes guardas provam:
  • XSS guardado: texto que vem de PESSOA (nome, título, e-mail) não entra dentro de
    atributo on*="..." — ali o esc() NÃO protege, porque o navegador desfaz &#39; em '
    ANTES de rodar o JS do atributo. O botão @menção fazia isso com o nome do colega
    (que vem do cadastro dele): um nome-armadilha rodaria JS no navegador da admin;
  • o texto do convite não carrega quebra de linha pro ASSUNTO do e-mail;
  • o convite sai pelo nosso e-mail, então tem teto por dia — e "não consegui contar"
    é 502, nunca "zero" (zero liberaria o envio justamente quando não sei);
  • a tela pede as colunas de escritorio_membros POR NOME, sem e-mail/telefone: contato
    da equipe só pelo RPC do admin.
🧪 Controles positivos: o detector de XSS reprova o trecho antigo, literal.
"""
import os
import re
import sys
import types

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))
sys.path.insert(0, os.path.dirname(_AQUI))

import escritorio as esc  # noqa: E402
from fastapi import HTTPException  # noqa: E402

PAGINAS = ("escritorio.html", "convite.html")
# dentro de um on*="..." com interpolação, só pode entrar ID (uuid), índice ou chave fixa
_ATRIB = re.compile(r'\bon[a-z]+="([^"]*\$\{[^"]*)"')
_PERIGO = re.compile(r"\$\{\s*esc\(|\$\{[^}]*\b(nome|titulo|texto|email|curto|nomeDe)\b")


def _achados(fonte: str):
    return [m.group(1)[:90] for m in _ATRIB.finditer(fonte) if _PERIGO.search(m.group(1))]


@pytest.mark.parametrize("pagina", PAGINAS)
def test_texto_de_pessoa_nao_entra_em_atributo_de_clique(pagina):
    fonte = open(os.path.join(_RAIZ, pagina), encoding="utf-8").read()
    assert not _achados(fonte), f"{pagina}: texto de pessoa dentro de on*=: {_achados(fonte)}"


def test_controle_o_detector_reprova_o_botao_antigo_da_mencao():
    antigo = """<button type="button" class="chip" onclick="mencionar('${esc(curto(m))}')">@x</button>"""
    assert _achados(antigo), "o detector não viu o XSS que existia — guarda cego"
    assert not _achados("""<button onclick="mencionar('${m.id}')">@x</button>""")


def test_a_tela_pede_membro_sem_email_nem_telefone():
    fonte = open(os.path.join(_RAIZ, "escritorio.html"), encoding="utf-8").read()
    cols = re.search(r"const COLS_MEMBRO = '([^']+)'", fonte).group(1).split(",")
    assert "email" not in cols and "telefone" not in cols and "*" not in cols
    assert "from('escritorio_membros').select('*')" not in fonte
    assert "rpc('escritorio_contatos'" in fonte


def test_quebra_de_linha_nao_chega_no_assunto():
    assert "\n" not in esc.assunto_do_convite("Fulano\nBcc: x@y.com", "Projeto")
    assert esc.texto_curto("Nome\r\nBcc: x@y.com", "nome") == "Nome Bcc: x@y.com"


# ── teto de convites ──
class _Banco:
    def __init__(self, n_convites, falha=False):
        self.n, self.falha, self.escritas = n_convites, falha, []

    def __call__(self, method, path, body=None, params=None, prefer=None, timeout=15, **_k):
        params = params or {}
        if method != "GET":
            self.escritas.append(path)
            return (201, [{"id": "m-novo"}])
        if "escritorio_projetos" in path:
            if "dono" in params:
                return (500, None) if self.falha else (200, [{"id": "p1"}, {"id": "p2"}])
            return (200, [{"id": "p1", "nome": "Projeto Exemplo", "dono": "uid-admin"}])
        if "convidado_em" in params:
            assert params["projeto_id"] == "in.(p1,p2)" and params["papel"] == "eq.freela"
            return (200, [{"id": str(i)} for i in range(self.n)])
        return (200, [])


def _montar(banco):
    esc.configurar(servico=banco, como_usuario=lambda *a, **k: (200, "dono"),
                   usuario=lambda r: {"id": "uid-admin", "email": "admin@exemplo.com"},
                   enviar=lambda *a, **k: True, moldura=lambda *a, **k: "", registrar=None)


REQ = types.SimpleNamespace(headers={"Authorization": "Bearer x"})


def test_no_teto_do_dia_o_convite_e_429_e_nada_e_escrito():
    banco = _Banco(esc.CONVITES_POR_DIA)
    _montar(banco)
    with pytest.raises(HTTPException) as e:
        esc.convidar("p1", REQ, {"email": "nova@exemplo.com"})
    assert e.value.status_code == 429 and banco.escritas == []


def test_abaixo_do_teto_passa():
    banco = _Banco(esc.CONVITES_POR_DIA - 1)
    _montar(banco)
    assert esc.convidar("p1", REQ, {"email": "nova@exemplo.com"})["ok"] is True
    assert banco.escritas


def test_nao_conseguir_contar_e_502_e_nao_zero():
    banco = _Banco(0, falha=True)
    _montar(banco)
    with pytest.raises(HTTPException) as e:
        esc.convidar("p1", REQ, {"email": "nova@exemplo.com"})
    assert e.value.status_code == 502 and banco.escritas == []
