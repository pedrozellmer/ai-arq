# -*- coding: utf-8 -*-
"""Resumo diário das @menções do Escritório (27/09/2026 — Pedro escolheu "Resumo diário").

  • um e-mail por pessoa por dia, a partir das 18 h de Brasília, com as menções de ontem 18 h até hoje 18 h;
  • só o que a pessoa vê no quadro: equipe tudo, fornecedor só nas tarefas dele, cliente nunca;
  • 🔒 id de menção de OUTRO projeto (a tela grava a lista; o banco não confere) não leva o texto pra fora;
  • a marca do dia vem ANTES do envio: marca que já existe ou que não gravou = não manda;
  • leitura que falha = ninguém recebe (e nada é marcado).
🧪 O banco falso só aceita LEITURA e filtra como o PostgREST (eq, in, gte por data de verdade).
"""
import os
import sys
from datetime import datetime, timezone

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import escritorio as esc  # noqa: E402
import escritorio_mencoes as em  # noqa: E402

PROJ = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OUTRO = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
M_DONO, M_EQ, M_FORN, M_CLI = ("00000000-0000-4000-8000-00000000000%d" % i for i in range(1, 5))
M_EQ_OUTRO, M_DE_FORA = "00000000-0000-4000-8000-000000000005", "00000000-0000-4000-8000-000000000006"
T1, T2, T3 = ("tttttttt-tttt-4ttt-8ttt-00000000000%d" % i for i in range(1, 4))
AGORA = datetime(2026, 9, 27, 21, 30, tzinfo=timezone.utc)          # 18h30 em Brasília
DENTRO = "2026-09-27T12:00:00+00:00"


def _data(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


class Banco:
    def __init__(self):
        self.t = {k: [] for k in ("escritorio_comentarios", "escritorio_membros", "escritorio_tarefas",
                                  "escritorio_projetos", "escritorio_tarefa_pessoas")}
        self.falhar = set()

    @staticmethod
    def casa(linha, params):
        for k, v in (params or {}).items():
            if k in ("select", "order", "limit"):
                continue
            atual = linha.get(k)
            if v.startswith("eq."):
                ok = str(atual) == v[3:]
            elif v.startswith("in.("):
                ok = str(atual) in v[4:-1].split(",")
            elif v.startswith("gte."):
                ok = _data(atual) >= _data(v[4:])
            else:
                raise AssertionError("filtro não previsto: %s=%s" % (k, v))
            if not ok:
                return False
        return True

    def __call__(self, method, path, body=None, params=None, prefer=None, **_k):
        assert method == "GET", "o resumo só LÊ o banco: " + method
        path = path.lstrip("/")
        if path in self.falhar:
            return 500, None
        return 200, [dict(x) for x in self.t[path] if self.casa(x, params)]


@pytest.fixture(autouse=True)
def _pecas():
    nomes = ("_SERVICO", "_ENVIAR", "_MOLDURA", "_REGISTRAR")
    antes = {n: getattr(esc, n) for n in nomes}
    yield
    for n, v in antes.items():
        setattr(esc, n, v)


def _m(mid, pid, papel, uid, email, nome, status="ativo"):
    return {"id": mid, "projeto_id": pid, "papel": papel, "status": status, "user_id": uid, "email": email,
            "email_conta": email, "nome": nome}


class Cena:
    def __init__(self):
        self.b, self.enviados, self.marcas, self.registros = Banco(), [], {}, []
        esc._SERVICO = self.b
        esc._ENVIAR = lambda para, assunto, html, texto="", **k: self.enviados.append(
            {"para": para, "assunto": assunto, "html": html, "texto": texto, "kind": k.get("log_kind")}) or True
        esc._MOLDURA = lambda titulo, corpo, **k: "<h1>%s</h1>%s<a href='%s'>" % (titulo, corpo, k.get("cta_url"))
        esc._REGISTRAR = lambda stage, msg, **k: self.registros.append((stage, msg))
        b = self.b
        b.t["escritorio_projetos"] += [{"id": PROJ, "nome": "Casa Exemplo"}, {"id": OUTRO, "nome": "Loja Exemplo"}]
        b.t["escritorio_membros"] += [
            _m(M_DONO, PROJ, "dono", "uid-dona", "dona@exemplo.com", "Admin Exemplo"),
            _m(M_EQ, PROJ, "freela", "uid-eq", "equipe@exemplo.com", "Bia Equipe"),
            _m(M_FORN, PROJ, "fornecedor", "uid-forn", "forn@exemplo.com", "Marcenaria Exemplo"),
            _m(M_CLI, PROJ, "cliente", "uid-cli", "cli@exemplo.com", "Cliente Exemplo"),
            _m(M_EQ_OUTRO, OUTRO, "freela", "uid-eq", "equipe@exemplo.com", "Bia Equipe"),   # a mesma pessoa
            _m(M_DE_FORA, OUTRO, "freela", "uid-fora", "fora@exemplo.com", "Fora Exemplo")]
        b.t["escritorio_tarefas"] += [{"id": T1, "projeto_id": PROJ, "titulo": "Marcenaria da cozinha"},
                                      {"id": T2, "projeto_id": PROJ, "titulo": "Luminotécnico"},
                                      {"id": T3, "projeto_id": OUTRO, "titulo": "Fachada"}]
        b.t["escritorio_tarefa_pessoas"].append({"tarefa_id": T1, "membro_id": M_FORN, "projeto_id": PROJ})

    def comentario(self, tarefa, mencoes, texto="Pode olhar?", projeto=PROJ, autor="uid-dona", quando=DENTRO):
        self.b.t["escritorio_comentarios"].append({
            "id": "c%d" % len(self.b.t["escritorio_comentarios"]), "tarefa_id": tarefa, "projeto_id": projeto,
            "autor": autor, "texto": texto, "mencoes": list(mencoes), "criado_em": quando})

    def marcar(self, ref):
        if ref in self.marcas:
            return False
        self.marcas[ref] = True
        return True

    def rodar(self, agora=AGORA, dry=False, marcar=None):
        return em.rodada(agora, marcar or self.marcar, dry=dry)

    def para(self, email):
        return [e for e in self.enviados if e["para"] == email]


def test_a_equipe_mencionada_leva_um_resumo_com_projeto_tarefa_autor_e_texto_escapado():
    c = Cena()
    c.comentario(T2, [M_EQ], texto="Confere a <b>sanca</b> da sala?")
    r = c.rodar()
    assert r == {"status": "ok", "enviados": 1, "ja_tinham": 0, "falhas": 0}
    (e,) = c.enviados
    assert e["para"] == "equipe@exemplo.com" and e["kind"] == "escritorio_mencoes"
    assert e["assunto"] == "1 menção pra você no Escritório do AI.arq" and len(e["assunto"]) <= esc.TETO_ASSUNTO
    for trecho in ("Casa Exemplo", "Luminotécnico", "Admin Exemplo", "Oi, Bia!"):
        assert trecho in e["html"], trecho
    assert "<b>sanca</b>" not in e["html"] and "&lt;b&gt;sanca" in e["html"]
    assert "https://ai.arq.br/escritorio.html#/p/%s/tarefas" % PROJ in e["html"]
    assert c.marcas == {"2026-09-27:uid-eq": True}


def test_o_fornecedor_so_leva_mencao_das_tarefas_dele():
    c = Cena()
    c.comentario(T1, [M_FORN], texto="Medida do nicho confirmada")      # ele está nesta tarefa
    c.comentario(T2, [M_FORN], texto="Segredo da iluminação")            # nesta não: o banco não mostra
    c.rodar()
    (e,) = c.para("forn@exemplo.com")
    assert "nicho" in e["html"] and "Segredo" not in e["html"] and e["assunto"].startswith("1 menção")


def test_cliente_mencionado_nao_leva():
    c = Cena()
    c.comentario(T1, [M_CLI])
    assert c.rodar()["enviados"] == 0 and not c.enviados and not c.marcas


def test_id_de_mencao_de_outro_projeto_nao_leva_o_comentario_pra_fora():
    c = Cena()
    c.comentario(T2, [M_DE_FORA], texto="Valor combinado com o cliente")
    c.rodar()
    assert not c.enviados


def test_quem_saiu_e_quem_se_mencionou_nao_levam():
    c = Cena()
    c.b.t["escritorio_membros"][1]["status"] = "removido"            # a equipe saiu
    c.comentario(T2, [M_EQ, M_DONO], autor="uid-dona")               # e a dona se mencionou
    assert c.rodar()["enviados"] == 0 and not c.enviados


def test_controle_menção_valida_de_cada_papel_que_ve():
    c = Cena()
    c.comentario(T1, [M_DONO, M_EQ, M_FORN, M_CLI], autor="uid-eq")
    c.rodar()
    assert sorted(e["para"] for e in c.enviados) == ["dona@exemplo.com", "forn@exemplo.com"]   # a equipe é a autora


def test_so_as_mencoes_da_janela_de_ontem_18h_ate_hoje_18h():
    c = Cena()
    for quando, texto in (("2026-09-26T20:59:59+00:00", "cedo-demais"), ("2026-09-26T21:00:00+00:00", "no-inicio"),
                          ("2026-09-27T20:59:00+00:00", "no-fim"), ("2026-09-27T21:00:00+00:00", "de-amanha")):
        c.comentario(T2, [M_EQ], texto=texto, quando=quando)
    c.rodar()
    (e,) = c.enviados
    assert "no-inicio" in e["html"] and "no-fim" in e["html"]
    assert "cedo-demais" not in e["html"] and "de-amanha" not in e["html"]


def test_antes_das_18h_nao_roda_e_a_noite_ainda_e_o_dia_de_hoje():
    c = Cena()
    c.comentario(T2, [M_EQ])
    assert c.rodar(agora=datetime(2026, 9, 27, 20, 59, tzinfo=timezone.utc)) == {"status": "fora_da_hora"}
    assert not c.enviados
    c.rodar(agora=datetime(2026, 9, 28, 1, 0, tzinfo=timezone.utc))      # 22 h do dia 27 em Brasília
    assert list(c.marcas) == ["2026-09-27:uid-eq"]


def test_uma_vez_por_dia_mesmo_com_o_tick_das_19h_e_das_20h():
    c = Cena()
    c.comentario(T2, [M_EQ])
    c.rodar()
    r = c.rodar(agora=datetime(2026, 9, 27, 22, 30, tzinfo=timezone.utc))
    assert r["enviados"] == 0 and r["ja_tinham"] == 1 and len(c.enviados) == 1


def test_marca_que_nao_grava_nao_manda():
    c = Cena()
    c.comentario(T2, [M_EQ])
    r = c.rodar(marcar=lambda ref: None)
    assert r["enviados"] == 0 and r["falhas"] == 1 and not c.enviados

    def _cai(ref):
        raise RuntimeError("banco fora")
    assert c.rodar(marcar=_cai)["enviados"] == 0 and not c.enviados


@pytest.mark.parametrize("tabela", ["escritorio_comentarios", "escritorio_membros", "escritorio_tarefas",
                                    "escritorio_projetos", "escritorio_tarefa_pessoas"])
def test_leitura_que_falha_ninguem_recebe_e_nada_e_marcado(tabela):
    c = Cena()
    c.comentario(T1, [M_EQ, M_FORN])
    c.b.falhar.add(tabela)
    assert c.rodar() == {"status": "erro"}
    assert not c.enviados and not c.marcas and c.registros and c.registros[0][0] == "escritorio:mencoes"


def test_dry_so_conta():
    c = Cena()
    c.comentario(T2, [M_EQ])
    assert c.rodar(dry=True) == {"status": "dry", "pessoas": 1} and not c.enviados and not c.marcas


def test_a_mesma_pessoa_em_dois_projetos_leva_um_email_so():
    c = Cena()
    c.comentario(T2, [M_EQ], texto="da-casa")
    c.comentario(T3, [M_EQ_OUTRO], texto="da-loja", projeto=OUTRO, autor="uid-fora")
    c.rodar()
    (e,) = c.enviados
    assert e["assunto"].startswith("2 menções") and "da-casa" in e["html"] and "da-loja" in e["html"]
    assert "Loja Exemplo" in e["html"] and "Fora Exemplo" in e["html"]
    assert "href='https://ai.arq.br/escritorio.html'" in e["html"]            # o botão abre a lista, não um projeto


def test_muitas_mencoes_param_no_teto_e_dizem_quantas_faltam():
    c = Cena()
    for i in range(em.TETO_ITENS + 5):
        c.comentario(T2, [M_EQ], texto="mencao-%02d" % i)
    c.rodar()
    (e,) = c.enviados
    assert "mencao-%02d" % (em.TETO_ITENS - 1) in e["html"] and "mencao-%02d" % em.TETO_ITENS not in e["html"]
    assert "E mais 5 menções no quadro." in e["html"] and e["assunto"].startswith("%d menções" % (em.TETO_ITENS + 5))


def test_comentario_longo_e_cortado():
    c = Cena()
    c.comentario(T2, [M_EQ], texto="palavra " * 100)
    c.rodar()
    trecho = c.enviados[0]["html"].split("“", 1)[1].split("”", 1)[0]
    assert len(trecho) <= em.TETO_TEXTO and trecho.endswith("…")


def test_envio_que_falha_nao_derruba_a_rodada_e_fica_registrado():
    c = Cena()
    c.comentario(T1, [M_EQ, M_FORN])

    def _envia(para, *a, **k):
        if para == "equipe@exemplo.com":
            raise RuntimeError("smtp fora")
        return True
    esc._ENVIAR = _envia
    r = c.rodar()
    assert r["enviados"] == 1 and r["falhas"] == 1
    assert any("uid-eq" in msg for _, msg in c.registros)
