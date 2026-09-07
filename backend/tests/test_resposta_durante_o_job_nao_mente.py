# -*- coding: utf-8 -*-
"""A rota que recebe as respostas durante o job mentia de três jeitos.

🩸 04/09/2026, varredura adversarial. `/api/project/{job}/respostas-processamento`
é o card que aparece ENQUANTO o projeto processa, pedindo pé-direito, área total
e prazo. Três defeitos nas mesmas dez linhas:

1. **A faixa anunciada era a velha.** O 400 dizia `area_total 5–1.000.000 m²`,
   escrito à mão, e a banda real virou 100.000 em 03/09. Quem digitasse 500.000
   levava um erro dizendo que 500.000 está dentro da faixa.

2. **Área implausível sumia calada.** Digitou 880.000 JUNTO com o pé-direito?
   `_ar` virava None, a área não entrava no patch e a rota devolvia **200**, sem
   aviso pro cliente e sem registro pra nós. As duas portas irmãs que escrevem o
   MESMO campo já avisavam: o upload devolve `aviso_area` e loga
   `upload:area-implausivel`; o `/inform-area` levanta 400 e loga. Só esta
   calava — é o furo do Fábio (880.000 m²) na terceira porta.

3. **O PATCH não era conferido.** `_supa_rest_service` **nunca levanta**: erro
   devolve `(code, None)`, falha total devolve `(0, None)`. O retorno não era
   amarrado, então a rota respondia `{"ok": true}` — e o error_log afirmava
   "cliente respondeu" — com o banco intacto.

🪤 E conferir só o status não bastava: o PostgREST devolve sucesso com ZERO
linhas quando o filtro não casa nada, que é justamente o caso de "gravou nada".
Por isso o conserto pede `return=representation` e exige linha de volta.

🪤 O aviso não pode morrer no JSON. Foi o que aconteceu em 03/09 com o
`aviso_area` do upload: o backend montava e NENHUMA tela lia a chave. Aqui o
`projeto.html` mantém o card e mostra o aviso — e há teste pra isso.
"""
import ast
import asyncio
import io
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
_PROJETO = io.open(os.path.join(os.path.dirname(_BACKEND), "projeto.html"),
                   encoding="utf-8").read()


sys.path.insert(0, _BACKEND)
import main  # noqa: E402

HTTPException = main.HTTPException
JOB = "job-de-teste-01"


# ══════════════════════════════════════════════════════════════════════════
#  A BANCADA QUE EXECUTA — a rota de verdade, o PostgREST de mentira
# ══════════════════════════════════════════════════════════════════════════
# 🩸 06/09/2026. Os dois guardas do PATCH liam o fonte e passavam CEGOS:
#   • trocar `or not _js_r` por `and not _js_r` fazia a rota responder
#     {"ok": true} com o banco INTACTO (200 + zero linhas = "gravou nada") e as
#     quatro strings cobradas continuavam todas lá;
#   • trocar `raise HTTPException(` por `_erro_502 = HTTPException(` deixava o
#     objeto ser construído e nunca levantado — a rota logava "PATCH NÃO gravou"
#     como critical e, LOGO EM SEGUIDA, "cliente respondeu durante o job".
# 🔑 Agora a rota RODA e o que se confere é o que ela DEVOLVE e o que ela GRAVA.
class _Pedido:
    """`await request.json()` é tudo que a rota usa do request."""

    def __init__(self, corpo):
        self._corpo = corpo
        self.headers = {"Authorization": "Bearer jwt-do-cliente"}

    async def json(self):
        return dict(self._corpo)


class _Postgrest:
    """Fake do `_supa_rest_service`. Devolve o par (status, json) combinado.

    🪤 O de verdade NUNCA levanta: erro vira (code, None) e falha total vira
    (0, None). É por isso que o retorno TEM que ser amarrado.
    """

    def __init__(self, resposta):
        self.resposta = resposta
        self.chamadas = []

    def __call__(self, method, path, body=None, params=None, prefer=None,
                 timeout=15):
        self.chamadas.append({"m": method, "path": path, "body": body,
                              "params": params, "prefer": prefer})
        return self.resposta


class _Registro:
    """Fake do `_log_error`: guarda o que iria pro error_log, em ORDEM."""

    def __init__(self):
        self.linhas = []

    def __call__(self, stage, message, job_id=None, severity="error"):
        self.linhas.append({"stage": stage, "message": str(message),
                            "job_id": job_id, "severity": severity})

    def diz(self, trecho):
        return [l for l in self.linhas if trecho in l["message"]]


def _responde(monkeypatch, resposta_do_banco, corpo=None):
    """Chama a rota DE VERDADE. Devolve (saida, banco, registro) ou levanta."""
    banco = _Postgrest(resposta_do_banco)
    registro = _Registro()
    monkeypatch.setattr(main, "_require_project_owner",
                        lambda request, job_id: "uid-do-cliente-01")
    monkeypatch.setattr(main, "_supa_rest_service", banco)
    monkeypatch.setattr(main, "_log_error", registro)
    corpo = {"pe_direito": "2,80"} if corpo is None else corpo
    saida = asyncio.run(main.respostas_processamento(JOB, _Pedido(corpo)))
    return saida, banco, registro



def _rota():
    """O corpo da rota, pelo nome da função (não por busca de texto)."""
    for n in ast.walk(ast.parse(_FONTE)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and "respostas_processamento" in n.name:
            return ast.get_source_segment(_FONTE, n) or ""
    # o nome pode mudar; cai pra âncora do log, que é única
    i = _FONTE.index('"motor:respostas-processamento"')
    return _FONTE[max(0, i - 4000):i + 1500]


def _sem_comentario(txt):
    """🪤 Os comentários do conserto CITAM o defeito pra explicar por que ele
    saiu — acusar isso seria acusar a própria lápide."""
    return "\n".join(l for l in txt.splitlines()
                     if not l.strip().startswith("#"))


# ══════════════════════════════════════════════════════════════════════════
#  (1) A faixa anunciada tem que sair da constante
# ══════════════════════════════════════════════════════════════════════════
def test_a_faixa_anunciada_sai_da_constante():
    corpo = _sem_comentario(_rota())
    assert "1.000.000 m²" not in corpo, (
        "a mensagem de erro voltou a anunciar a faixa velha de 1 km² — o "
        "cliente lê que 500.000 é válido e leva 400 mesmo assim")
    assert "_AREA_PLAUSIVEL_MAX" in corpo, (
        "a faixa voltou a ser um número escrito à mão; ela envelhece calada")


def test_a_tela_nao_repete_a_faixa_velha():
    """🪤 A mesma regra copiada pra prosa do front envelheceu junto."""
    assert "área 5–1M m²" not in _PROJETO, (
        "o comentário do card ainda anuncia a faixa velha")


# ══════════════════════════════════════════════════════════════════════════
#  (2) Área descartada não pode sumir calada
# ══════════════════════════════════════════════════════════════════════════
def test_a_area_descartada_AVISA_o_cliente():
    corpo = _sem_comentario(_rota())
    assert '_resp["aviso_area"]' in corpo, (
        "a rota voltou a devolver 200 sem contar que a área foi descartada — "
        "o cliente vai embora achando que ela entrou na conta")
    assert "respostas:area-implausivel" in corpo, (
        "sumiu o registro; ninguém saberia quantas vezes isso acontece")


def test_o_aviso_CHEGA_na_tela_e_nao_morre_no_JSON():
    """🩸 A armadilha de 03/09: backend monta o aviso e nenhuma tela lê.

    E mais: o card NÃO pode virar "✓ Valeu!" quando parte foi descartada.
    """
    assert "b.aviso_area" in _PROJETO, (
        "`projeto.html` não lê `aviso_area` — o aviso é montado e jogado fora, "
        "que é a mesma falha silenciosa um degrau adiante")
    i = _PROJETO.index("if (b.aviso_area)")
    j = _PROJETO.index("pp_respondido_", i)
    trecho = _PROJETO[i:j]
    assert "return" in trecho, (
        "o caminho do aviso não sai antes de marcar o card como respondido — "
        "o cliente vê '✓ Valeu!' com a área descartada")


# ══════════════════════════════════════════════════════════════════════════
#  (3) O PATCH tem que ser conferido — status E linhas
# ══════════════════════════════════════════════════════════════════════════
def test_o_patch_e_conferido(monkeypatch):
    """RODA a rota com o banco falhando de tres jeitos. Nenhum pode virar 200.

    🩸 A versao anterior cobrava quatro strings no fonte. Trocar `or not _js_r`
    por `and not _js_r` deixava as quatro no lugar e a rota respondia
    {"ok": true} com o banco INTACTO — a armadilha que a docstring do arquivo
    nomeia: o PostgREST devolve 200 com ZERO linhas quando o filtro nao casa
    nada, que e exatamente o caso de "gravou nada".
    """
    falhas = [
        ((200, []), "200 com ZERO linhas (o filtro nao casou nada)"),
        ((200, None), "200 sem corpo"),
        ((500, None), "erro do banco"),
        ((0, None), "falha total de rede"),
    ]
    for resposta, rotulo in falhas:
        with pytest.raises(HTTPException) as erro:
            _responde(monkeypatch, resposta)
        assert erro.value.status_code == 502, (
            "%s virou HTTP %s — a rota afirmou sucesso com o banco intacto"
            % (rotulo, erro.value.status_code))

    # 🪤 E o PATCH tem que PEDIR a linha de volta; sem representacao nao da
    # pra distinguir "gravou" de "nao casou nada".
    banco = _Postgrest((200, []))
    monkeypatch.setattr(main, "_supa_rest_service", banco)
    monkeypatch.setattr(main, "_require_project_owner", lambda r, j: "uid")
    monkeypatch.setattr(main, "_log_error", _Registro())
    with pytest.raises(HTTPException):
        asyncio.run(main.respostas_processamento(JOB, _Pedido({"pe_direito": "2,80"})))
    assert banco.chamadas, "a rota nem chamou o banco"
    assert "return=representation" in str(banco.chamadas[0]["prefer"]), (
        "o PATCH nao pede a linha de volta: prefer=%r"
        % banco.chamadas[0]["prefer"])

    # 🧪 CONTROLE POSITIVO: com linha de volta, a resposta e 200 de verdade.
    saida, banco, _ = _responde(monkeypatch, (200, [{"job_id": JOB}]))
    assert saida["ok"] is True and saida["salvo"] == ["user_pe_direito"], saida
    assert banco.chamadas[0]["body"] == {"user_pe_direito": 2.8}, banco.chamadas


def test_o_log_de_sucesso_so_roda_DEPOIS_da_conferencia(monkeypatch):
    """🩸 O error_log afirmava "cliente respondeu" sem ninguem ter gravado.

    A versao anterior comparava a POSICAO das duas frases no fonte. Trocar
    `raise HTTPException(` por `_erro_502 = HTTPException(` mantinha a ordem
    intacta — o objeto era construido e nunca levantado — e a rota logava
    "PATCH NAO gravou" como critical e, LOGO EM SEGUIDA, "cliente respondeu
    durante o job", devolvendo 200.
    """
    registro = _Registro()
    banco = _Postgrest((0, None))          # falha TOTAL de gravacao
    monkeypatch.setattr(main, "_require_project_owner", lambda r, j: "uid")
    monkeypatch.setattr(main, "_supa_rest_service", banco)
    monkeypatch.setattr(main, "_log_error", registro)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(main.respostas_processamento(
            JOB, _Pedido({"pe_direito": "2,80", "prazo_meses": "12"})))
    assert erro.value.status_code == 502

    assert registro.diz("PATCH NÃO gravou"), (
        "a falha de gravacao nao deixou rastro: %s" % registro.linhas)
    assert registro.diz("PATCH NÃO gravou")[0]["severity"] == "critical"
    assert not registro.diz("cliente respondeu durante o job"), (
        "a rota registrou 'cliente respondeu durante o job' DEPOIS de saber "
        "que o PATCH nao gravou — o error_log afirma um fato que nao "
        "aconteceu: %s" % registro.linhas)

    # 🧪 CONTROLE POSITIVO: quando grava mesmo, a linha de sucesso SAI.
    saida, _, ok = _responde(monkeypatch, (200, [{"job_id": JOB}]))
    assert saida["ok"] is True
    assert ok.diz("cliente respondeu durante o job"), (
        "o guarda esta apertado demais: nem no sucesso a linha sai")
    assert not ok.diz("PATCH NÃO gravou")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — a rota de ANTES, nas MESMAS conferências
# ══════════════════════════════════════════════════════════════════════════
_ANTES = '''
    if not patch:
        raise HTTPException(400, "Nenhuma resposta válida (pe_direito 1,8–8 m; "
                                 "area_total 5–1.000.000 m²; prazo_meses 1–120).")
    _supa_rest_service("PATCH", "projects", body=patch,
                       params={"job_id": f"eq.{job_id}"})
    _log_error("motor:respostas-processamento",
               f"cliente respondeu durante o job: {patch}", job_id)
    return {"ok": True, "salvo": sorted(patch.keys())}
'''


def test_CONTROLE_a_rota_de_ANTES_falha_nas_tres_conferencias():
    """Cada defeito tem que ser visível no código antigo, um por um."""
    faltas = []
    if "1.000.000 m²" in _ANTES:
        faltas.append("anuncia a faixa velha")
    if '_resp["aviso_area"]' not in _ANTES:
        faltas.append("não avisa da área descartada")
    if "_st_r, _js_r = _supa_rest_service(" not in _ANTES:
        faltas.append("não confere o PATCH")
    assert len(faltas) == 3, (
        "o julgamento não vê os três defeitos no código de antes — achei %s"
        % faltas)
    # e o de hoje não falha em nenhuma
    hoje = _sem_comentario(_rota())
    assert "1.000.000 m²" not in hoje
    assert '_resp["aviso_area"]' in hoje
    assert "_st_r, _js_r = _supa_rest_service(" in hoje
