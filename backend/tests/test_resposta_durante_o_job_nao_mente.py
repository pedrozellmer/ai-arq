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
import io
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
_PROJETO = io.open(os.path.join(os.path.dirname(_BACKEND), "projeto.html"),
                   encoding="utf-8").read()


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
def test_o_patch_e_conferido():
    corpo = _sem_comentario(_rota())
    assert "_st_r, _js_r = _supa_rest_service(" in corpo, (
        "o retorno do PATCH voltou a ser jogado fora — `_supa_rest_service` "
        "NUNCA levanta, então a rota responde ok com o banco intacto")
    assert "return=representation" in corpo, (
        "sem representação não dá pra saber se alguma linha foi tocada")
    assert "not _js_r" in corpo, (
        "🪤 conferir só o status não basta: o PostgREST devolve sucesso com "
        "ZERO linhas quando o filtro não casa nada")
    assert "HTTPException(\n            502" in corpo or "502," in corpo, (
        "a falha de gravação voltou a responder 200")


def test_o_log_de_sucesso_so_roda_DEPOIS_da_conferencia():
    """🩸 O error_log afirmava "cliente respondeu" sem ninguém ter gravado."""
    corpo = _sem_comentario(_rota())
    i_check = corpo.index("if _st_r not in")
    i_log = corpo.index('"cliente respondeu durante o job')
    assert i_check < i_log, (
        "o log de 'cliente respondeu' voltou a rodar antes da conferência do "
        "PATCH — ele afirma um fato que pode não ter acontecido")


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
