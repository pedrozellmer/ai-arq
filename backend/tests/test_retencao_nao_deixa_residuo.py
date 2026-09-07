# -*- coding: utf-8 -*-
"""A retenção de 90 dias não deixa arquivo pra trás — nem quando falha.

🩸 07/09/2026 — O CONSERTO DA URL NÃO CUMPRIU A PROMESSA SOZINHO.
Em 06/09 corrigi `_supabase_storage_delete` (espaço no nome ia cru pra URL) e o
cron da madrugada seguinte apagou 19 arquivos. Mas ao CONFERIR, um dia depois:

    31 arquivos, 18 projetos, 65,7 MB, todos com mais de 90 dias, TODOS de
    projeto já marcado como `archived = true`.

A causa não era mais a URL. É que o cron **arquiva o projeto mesmo quando a
exclusão falha** — e a RPC `list_expired_projects` filtra `archived = false`.
Uma falha de uma noite virava resíduo PERMANENTE: o cron nunca mais voltava
naquele projeto. Arquivo de cliente que a política de privacidade promete
apagar, parado há mais de três meses.

Dois consertos, dois invariantes aqui:
  1. **Falhou uma exclusão → NÃO arquiva.** O projeto fica na fila e a rodada
     seguinte tenta de novo. Não apagar é reversível; sumir da fila não é.
  2. **Varredura de resgate.** Uma RPC olha o STORAGE (não a lista de projetos)
     e devolve o que sobrou de qualquer rodada passada; o cron apaga. Fica
     vazia sozinha quando a limpeza terminar.

🪤 E a listagem também mentia: `_supabase_storage_list` devolvia `[]` tanto pra
"pasta vazia" quanto pra "não consegui listar" — segundo caminho silencioso pro
mesmo resíduo, porque zero arquivo pra apagar é zero falha e o projeto era
arquivado como se estivesse limpo. Agora existe `_supabase_storage_list_ou_falha`.

🧪 Os controles positivos ficam no fim: cada invariante tem um mutante que o
reprova.
"""
import json
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

JOB = "abc12345"
DONO = "cliente@exemplo.test"          # 🔒 nº6: domínio de teste, nunca cliente real


class _Nuvem:
    """Supabase de mentira: Storage + as RPCs que o cron chama.

    Guarda o que foi apagado e o que foi arquivado — é isso que os testes leem.
    """

    def __init__(self, arquivos=None, sobras=None, delete_falha=(),
                 lista_quebra=False, expirados=None):
        self.arquivos = list(arquivos if arquivos is not None else ["Planta 1 - terreo.pdf"])
        self.sobras = list(sobras or [])
        self.delete_falha = set(delete_falha)
        self.lista_quebra = lista_quebra
        self.expirados = expirados if expirados is not None else [{"job_id": JOB}]
        self.apagados = []
        self.arquivados = []

    def urlopen(self, req, timeout=None):
        url = getattr(req, "full_url", str(req))
        metodo = getattr(req, "get_method", lambda: "GET")()
        corpo = getattr(req, "data", None)
        corpo = json.loads(corpo.decode("utf-8")) if corpo else {}

        def _resp(payload):
            dados = json.dumps(payload).encode("utf-8")
            return type("R", (), {"read": lambda s: dados,
                                  "__enter__": lambda s: s,
                                  "__exit__": lambda s, *a: False})()

        if "/rpc/list_expired_projects" in url:
            return _resp(self.expirados)
        if "/rpc/list_expired_storage_leftovers" in url:
            return _resp(self.sobras)
        if "/rpc/mark_project_archived" in url:
            self.arquivados.append(corpo.get("p_job_id"))
            return _resp([])
        if "/object/list/" in url:
            if self.lista_quebra:
                raise OSError("storage fora do ar")
            return _resp([{"name": n} for n in self.arquivos])
        if metodo == "DELETE" and "/object/" in url:
            # 🪤 a URL vem percent-encoded (é o conserto de 06/09): comparar o
            # marcador contra "Planta%201" nunca casa, e o cenário de falha
            # deixa de reproduzir falha. O controle positivo pegou isto.
            import urllib.parse
            caminho = urllib.parse.unquote(url.split("/object/", 1)[1])
            if any(m in caminho for m in self.delete_falha):
                import urllib.error
                raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)
            self.apagados.append(caminho)
            return _resp([])
        return _resp([])


@pytest.fixture
def nuvem(monkeypatch):
    """Monta o cenário e devolve uma fábrica: `nuvem(...)` → (_Nuvem, stats)."""
    import urllib.request

    def montar(dono=(200, [{"user_email": DONO}]), **kw):
        # 🪤 o dono entra AQUI, não num monkeypatch do teste: a fábrica roda
        # depois e sobrescreveria — dois testes passaram a apagar o que deviam
        # proteger porque a ordem estava invertida.
        n = _Nuvem(**kw)
        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: n.urlopen(req, timeout))
        monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
        monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)
        monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: None)
        monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: dono)
        monkeypatch.setattr(main, "CLEANUP_SECRET", "segredo")
        req = type("Req", (), {"headers": {"X-Cleanup-Secret": "segredo"},
                               "query_params": {}})()
        return n, main.cleanup_old_projects(req)

    return montar


def _caminhos(n):
    """Só a parte 'bucket/arquivo' das URLs de DELETE, já decodificada."""
    import urllib.parse
    return [urllib.parse.unquote(c) for c in n.apagados]


# ══════════════════════════════════════════════════════════════════════════
#  1 · o caminho feliz continua funcionando
# ══════════════════════════════════════════════════════════════════════════
def test_projeto_vencido_perde_os_arquivos_e_e_arquivado(nuvem):
    n, stats = nuvem()
    assert f"aiarq-pranchas/{JOB}/Planta 1 - terreo.pdf" in _caminhos(n)
    assert f"aiarq-planilhas/{JOB}.xlsx" in _caminhos(n)
    assert n.arquivados == [JOB], "apagou tudo e não arquivou"
    assert stats["archived"] == 1 and stats["files_deleted"] == 2


# ══════════════════════════════════════════════════════════════════════════
#  2 · 🚨 falhou uma exclusão → NÃO arquiva (a causa raiz do resíduo)
# ══════════════════════════════════════════════════════════════════════════
def test_exclusao_que_falha_NAO_arquiva_o_projeto(nuvem):
    """O invariante que faltava.

    Arquivar com arquivo pra trás tira o projeto da fila PRA SEMPRE: a RPC
    `list_expired_projects` filtra `archived = false`. Foi assim que 65,7 MB
    ficaram órfãos.
    """
    n, stats = nuvem(delete_falha=["Planta 1"])
    assert n.arquivados == [], (
        "🚨 arquivou com arquivo pra trás — o cron nunca mais volta neste projeto")
    assert stats["archived"] == 0
    assert stats["errors"], "a falha não apareceu no relatório da rodada"
    assert "fila" in json.dumps(stats["errors"], ensure_ascii=False), \
        "o erro não diz que o projeto continua na fila"


def test_listagem_que_falha_NAO_arquiva_o_projeto(nuvem):
    """🪤 O segundo caminho silencioso.

    Lista falhou → zero arquivo pra apagar → zero falha → o projeto era
    arquivado como se estivesse limpo. "Não consegui ver" não é "está vazio".
    """
    n, stats = nuvem(lista_quebra=True)
    assert n.arquivados == [], (
        "🚨 arquivou sem conseguir listar: não dá pra saber o que ficou lá")
    assert stats["archived"] == 0


def test_a_listagem_diz_quando_nao_conseguiu(monkeypatch):
    """O helper honesto, medido direto."""
    import urllib.request
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("fora")))
    assert main._supabase_storage_list_ou_falha("aiarq-pranchas", "x/") == (False, [])
    # e o helper antigo continua devolvendo só os nomes, pros 5 chamadores dele
    assert main._supabase_storage_list("aiarq-pranchas", "x/") == []


def test_lote_cheio_da_listagem_conta_como_falha(monkeypatch):
    """🪤 Teto de 500 é cap silencioso: projeto com mais de 500 arquivos ficaria
    com o resto pra trás e seria arquivado como limpo."""
    import urllib.request
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    cheio = json.dumps([{"name": f"f{i}.pdf"} for i in range(main._STORAGE_LIST_TETO)]).encode()
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: type("R", (), {"read": lambda s: cheio})())
    ok, nomes = main._supabase_storage_list_ou_falha("aiarq-pranchas", "x/")
    assert ok is False, "lote no teto passou como listagem completa"
    assert len(nomes) == main._STORAGE_LIST_TETO, "os nomes lidos não podem ser jogados fora"


# ══════════════════════════════════════════════════════════════════════════
#  3 · a varredura de resgate alcança o que já ficou pra trás
# ══════════════════════════════════════════════════════════════════════════
SOBRAS = [
    {"bucket_id": "aiarq-pranchas", "object_name": "78d0fab4/UFOP CENTRO-HID03.dwg"},
    {"bucket_id": "aiarq-pranchas", "object_name": "7ae23214/Planta 2 - cobertura.pdf"},
]


def test_resgate_apaga_o_que_sobrou_de_projeto_JA_arquivado(nuvem):
    """Os 31 arquivos de 18 projetos arquivados — o passo 2 não os alcança."""
    n, stats = nuvem(expirados=[], sobras=SOBRAS)
    apagados = _caminhos(n)
    for s in SOBRAS:
        assert f"{s['bucket_id']}/{s['object_name']}" in apagados, \
            f"o resgate não apagou {s['object_name']}"
    assert stats["resgatados"] == 2 and stats["resgate_falhou"] == 0


def test_resgate_conta_a_falha_em_vez_de_dar_por_feito(nuvem):
    n, stats = nuvem(expirados=[], sobras=SOBRAS, delete_falha=["UFOP"])
    assert stats["resgatados"] == 1 and stats["resgate_falhou"] == 1, \
        "falha do resgate virou sucesso"


def test_resgate_recusa_balde_que_nao_e_nosso(nuvem):
    """🔒 A RPC já filtra, mas o cliente não confia de graça: o que decide o
    que pode ser apagado nunca é só o que veio pela rede."""
    n, stats = nuvem(expirados=[], sobras=[
        {"bucket_id": "avatars", "object_name": "qualquer/coisa.png"},
        {"bucket_id": "aiarq-pranchas", "object_name": ""},
    ])
    assert _caminhos(n) == [], "apagou em bucket que não é da retenção"
    assert stats["resgatados"] == 0


def test_resgate_que_nao_consegue_listar_nao_derruba_a_rodada(monkeypatch):
    """🚨 O resgate é acessório: se a RPC não responde, o cleanup normal do dia
    tem que acontecer do mesmo jeito."""
    import urllib.request

    n = _Nuvem()
    original = n.urlopen

    def urlopen(req, timeout=None):
        if "list_expired_storage_leftovers" in getattr(req, "full_url", ""):
            raise OSError("rpc fora")
        return original(req, timeout)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (200, [{"user_email": DONO}]))
    monkeypatch.setattr(main, "CLEANUP_SECRET", "segredo")
    req = type("Req", (), {"headers": {"X-Cleanup-Secret": "segredo"}, "query_params": {}})()
    stats = main.cleanup_old_projects(req)
    assert stats["archived"] == 1, "a RPC do resgate caiu e levou o cleanup junto"
    assert stats["resgatados"] == 0


# ══════════════════════════════════════════════════════════════════════════
#  4 · a fixture de smoke continua fora (incidente de 20/08)
# ══════════════════════════════════════════════════════════════════════════
def test_conta_de_smoke_continua_intocada(nuvem):
    n, stats = nuvem(dono=(200, [{"user_email": "zarelalopes+smoke@gmail.com"}]))
    assert _caminhos(n) == [] and n.arquivados == [], \
        "a fixture permanente do smoke foi apagada — o teste de produção morre amanhã"


def test_dono_ilegivel_nao_apaga_no_escuro(nuvem):
    """Na dúvida, PULA: não apagar é reversível; apagar não."""
    n, stats = nuvem(dono=(500, None))
    assert _caminhos(n) == [] and n.arquivados == []


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES POSITIVOS — cada invariante tem um mutante que o reprova
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_cenario_de_falha_realmente_falha(nuvem):
    """Sem isto, `delete_falha` poderia não estar mordendo e os testes de cima
    passariam por engano."""
    n, _ = nuvem(delete_falha=["Planta 1"])
    assert f"aiarq-pranchas/{JOB}/Planta 1 - terreo.pdf" not in _caminhos(n), \
        "o cenário de falha não reproduz falha nenhuma"
    # e o outro arquivo, que NÃO falha, foi apagado — senão o teste passaria
    # com um storage totalmente quebrado
    assert f"aiarq-planilhas/{JOB}.xlsx" in _caminhos(n)


def test_CONTROLE_sem_sobras_o_resgate_nao_apaga_nada(nuvem):
    """O outro lado do resgate: RPC vazia é dia limpo, não licença pra apagar."""
    n, stats = nuvem(expirados=[], sobras=[])
    assert _caminhos(n) == [] and stats["resgatados"] == 0
