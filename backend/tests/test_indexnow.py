# -*- coding: utf-8 -*-
"""IndexNow: a chave vai pro ar, o aviso sai depois do deploy e nunca o derruba.

27/09/2026 (auditoria de aquisição, item 4). O script avisa Bing & cia. no dia
em que um post publica. Três jeitos de ele falhar calado, que este guarda fecha:
1. a chave existe no repo mas não vai pro ar (o deploy só copia .txt de uma
   lista explícita — mesma armadilha do llms.txt em 31/08) → IndexNow responde
   403 pra sempre;
2. o passo roda ANTES da publicação, ou a cada push (a mesma URL várias vezes
   no dia), ou derruba o deploy quando a rede falha;
3. a regra de data escorrega e avisa post agendado (fura o calendário) ou
   nenhum.
"""
import importlib.util
import io
import json
import os
import re
import urllib.error

import pytest

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_YML = os.path.join(_RAIZ, ".github", "workflows", "deploy-pages.yml")

_spec = importlib.util.spec_from_file_location("indexnow_sob_teste", os.path.join(_RAIZ, "scripts", "indexnow.py"))
IX = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(IX)


def _yml_sem_comentarios():
    return "\n".join(l for l in io.open(_YML, encoding="utf-8").read().splitlines()
                     if not l.lstrip().startswith("#"))


def test_a_chave_esta_na_raiz_com_o_nome_e_o_conteudo_certos():
    assert re.fullmatch(r"[a-zA-Z0-9-]{8,128}", IX.CHAVE), "chave fora do formato do IndexNow"
    arq = os.path.join(_RAIZ, IX.CHAVE + ".txt")
    assert os.path.isfile(arq), "o arquivo da chave sumiu da raiz: %s.txt" % IX.CHAVE
    assert io.open(arq, encoding="utf-8").read().strip() == IX.CHAVE
    assert IX.corpo([])["keyLocation"] == "https://ai.arq.br/%s.txt" % IX.CHAVE


def test_o_deploy_copia_a_chave():
    y = _yml_sem_comentarios()
    assert re.search(r"for f in [^;]*\b%s\.txt\b" % IX.CHAVE, y), (
        "a chave saiu da lista de .txt copiados — daria 404 e o IndexNow recusaria (403) calado")


def _passos():
    """(nome, bloco de texto) de cada passo do job, na ordem."""
    y = _yml_sem_comentarios()
    partes = re.split(r"\n      - name: ", y)
    return [(p.split("\n", 1)[0].strip(), p) for p in partes[1:]]


def test_o_aviso_sai_depois_do_deploy_so_na_rotina_e_sem_derrubar_nada():
    passos = _passos()
    nomes = [n for n, _ in passos]
    i_deploy = nomes.index("Deploy to GitHub Pages")
    aviso = [(i, b) for i, (n, b) in enumerate(passos) if "scripts/indexnow.py" in b]
    assert len(aviso) == 1, "o passo do IndexNow sumiu ou está duplicado"
    i, bloco = aviso[0]
    assert i > i_deploy, "o aviso roda ANTES da publicação — a URL ainda não existe"
    assert "continue-on-error: true" in bloco, "falha do IndexNow não pode derrubar o deploy"
    assert "github.event_name == 'schedule'" in bloco, "tem que rodar na rotina diária"
    assert "'push'" not in bloco, "a cada push a mesma URL seria avisada várias vezes no dia"


def _p(slug, data):
    return {"slug": slug, "publish_date": data}


def test_so_avisa_o_post_que_publica_hoje_e_o_indice():
    posts = [_p("ontem", "2026-09-26"), _p("hoje", "2026-09-27"), _p("amanha", "2026-09-28")]
    assert IX.urls_do_dia(posts, "2026-09-27") == [
        "https://ai.arq.br/blog/posts/hoje.html", "https://ai.arq.br/blog/"]


def test_sem_post_hoje_nao_avisa_nada():
    assert IX.urls_do_dia([_p("ontem", "2026-09-26")], "2026-09-27") == []


class _Resposta:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_o_envio_e_um_POST_json_no_endpoint():
    visto = {}

    def abrir(req, timeout=None, **k):
        visto["url"], visto["metodo"] = req.full_url, req.get_method()
        visto["tipo"] = req.get_header("Content-type")
        visto["corpo"] = json.loads(req.data.decode("utf-8"))
        return _Resposta(202)

    dados = IX.corpo(["https://ai.arq.br/blog/"])
    assert IX.enviar(dados, abrir) == 202
    assert visto["url"] == "https://api.indexnow.org/indexnow" and visto["metodo"] == "POST"
    assert visto["tipo"].startswith("application/json")
    assert visto["corpo"] == {"host": "ai.arq.br", "key": IX.CHAVE,
                              "keyLocation": "https://ai.arq.br/%s.txt" % IX.CHAVE,
                              "urlList": ["https://ai.arq.br/blog/"]}


@pytest.mark.parametrize("erro", [
    urllib.error.HTTPError("https://api.indexnow.org/indexnow", 403, "Forbidden", {}, None),
    urllib.error.URLError("sem rede"),
    TimeoutError("demorou"),
])
def test_falha_do_indexnow_vira_aviso_e_sai_zero(erro, monkeypatch, capsys):
    """O deploy já publicou; recusa ou rede fora não pode virar deploy vermelho."""
    monkeypatch.setattr(IX, "urls_do_dia", lambda *a, **k: ["https://ai.arq.br/blog/"])

    def abrir(req, timeout=None, **k):
        raise erro

    assert IX.main([], abrir) == 0
    assert "⚠" in capsys.readouterr().out


def test_CONTROLE_simular_nao_manda_nada(monkeypatch, capsys):
    monkeypatch.setattr(IX, "urls_do_dia", lambda *a, **k: ["https://ai.arq.br/blog/"])

    def abrir(req, timeout=None, **k):
        raise AssertionError("--simular não pode enviar")

    assert IX.main(["--simular"], abrir) == 0
    assert '"urlList"' in capsys.readouterr().out
