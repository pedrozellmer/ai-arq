# -*- coding: utf-8 -*-
"""Upload recusado tem que deixar rastro — senão "tentou" e "nunca tentou" são a mesma coisa.

🩸 04/09/2026, investigando por que 15 de 96 contas nunca subiram projeto. A
rota `/api/process` tem SETE portas de recusa — sem login, token trocado, muitos
envios seguidos, request acima de 450 MB, nenhum arquivo, formato não aceito,
mais de 50 arquivos — e **nenhuma delas gravava nada**. A pessoa via o erro na
tela e, do nosso lado, não tinha acontecido nada.

🔑 O custo não é uma linha de log a menos: é que, no banco, **"tentou subir e a
gente recusou" fica IDÊNTICO a "nunca tentou"**. A investigação inteira dos
primeiros 10 minutos esbarrou nisso e teve que escrever "indeterminado" caso
após caso. Já existe um cliente (`cliente-01@`) que mandou o POST e
sumiu — hoje ele conta como "desistiu".

🔑 Isto não conserta o funil. Conserta a capacidade de MEDIR o funil, que é
pré-requisito de qualquer conserto seguinte. No dia em que este arquivo nasceu,
seis hipóteses minhas foram derrubadas por medição — a única defesa contra
consertar o que não está quebrado é ter o número.

🪤 O guarda é ESTRUTURAL de propósito: percorre a árvore da rota e cobra que
NENHUM `raise HTTPException` sobreviva solto ali dentro. Contar ocorrências de
texto deixaria passar a oitava porta que alguém acrescentar amanhã.
"""
import ast
import io
import os

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _rota_process(codigo=None):
    arv = ast.parse(codigo or _FONTE)
    for n in ast.walk(arv):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and n.name == "process_files":
            return n
    pytest.fail("não achei a rota `process_files` — se ela foi renomeada, este "
                "guarda parou de guardar")


def _recusas_sem_rastro(no):
    """`raise HTTPException` solto dentro da rota. [] = toda recusa registra.

    Não desce em função aninhada: o que estiver lá dentro tem a vida dele.
    """
    ruins = []

    def anda(corpo):
        for st in corpo:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(st, ast.Raise) and st.exc is not None:
                alvo = st.exc.func if isinstance(st.exc, ast.Call) else st.exc
                if getattr(alvo, "id", "") == "HTTPException":
                    ruins.append(st.lineno)
            for campo in ("body", "orelse", "finalbody"):
                anda(getattr(st, campo, None) or [])
            for h in getattr(st, "handlers", None) or []:
                anda(h.body)

    anda(no.body)
    return sorted(ruins)


def _recusas_registradas(no):
    return sorted(n.lineno for n in ast.walk(no)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "_recusa_no_upload")


# ══════════════════════════════════════════════════════════════════════════
#  O julgamento sobre o código REAL
# ══════════════════════════════════════════════════════════════════════════
def test_nenhuma_recusa_do_upload_e_muda():
    soltas = _recusas_sem_rastro(_rota_process())
    assert not soltas, (
        "há recusa no /api/process que não deixa rastro (linha %s) — quem bater "
        "nela vai contar como 'nunca tentou subir'"
        % ", ".join(str(n) for n in soltas))


def test_as_DEZ_portas_continuam_registrando():
    """Se o número cair, alguém apagou uma porta — ou o guarda cegou.

    🪤 Verde vazio é verde falso: uma rota que o guarda não encontrasse passaria
    nos dois testes sem olhar nada.

    🚨 Eram SETE quando comecei — eu tinha varrido a rota só até a linha 12920 e
    parei cedo. O guarda estrutural achou TRÊS que eu perdi, e são as mais
    valiosas das dez, porque são "tentou e falhou" de verdade: envio incompleto
    (a conexão caiu no meio), DWG pequeno demais e DWG sem assinatura. Se eu
    tivesse contado por texto, teria fechado achando que estava pronto.
    """
    n = len(_recusas_registradas(_rota_process()))
    assert n >= 10, (
        "a rota tinha 10 recusas registrando e agora tem %d" % n)


def test_o_envio_incompleto_e_registrado():
    """🔑 A recusa mais importante das dez: conexão que caiu no meio do envio.
    É literalmente o caso que ficava indistinguível de "nunca tentou"."""
    rota = ast.get_source_segment(_FONTE, _rota_process()) or ""
    assert "envio-incompleto" in rota
    assert "de %d bytes" in rota, (
        "parou de registrar QUANTO chegou de quanto — sem isso não dá pra saber "
        "se foi a rede ou o arquivo")


def test_o_registro_diz_o_MOTIVO_e_nao_so_que_recusou():
    """"Recusado" sozinho não ensina nada sobre o que a pessoa queria fazer."""
    i = _FONTE.index("def _recusa_no_upload(")
    corpo = _FONTE[i:_FONTE.index("\n@app.post", i)]
    assert "upload:recusado" in corpo, "sumiu o stage — a linha vira invisível"
    assert "motivo=%s" in corpo, "o registro parou de dizer POR QUE recusou"
    assert 'severity="warning"' in corpo, (
        "recusa virou log comum (afoga o painel) ou sumiu do radar")


def test_o_formato_recusado_e_registrado():
    """🔑 A porta mais informativa das sete: diz QUE formato a pessoa tentou.
    Se aparecer .rvt, .skp ou .ifc com frequência, isso é informação de
    PRODUTO — não de erro."""
    rota = ast.get_source_segment(_FONTE, _rota_process()) or ""
    assert "formato-nao-aceito" in rota
    assert "tentou: %s" in rota, (
        "a recusa por formato voltou a não dizer QUAL formato veio")


def test_a_recusa_SEMPRE_levanta_e_nunca_devolve_calada():
    """🪤 Se um dia ela deixar de levantar, o upload SEGUE depois da recusa —
    e aí a gente troca um silêncio por um estrago."""
    i = _FONTE.index("def _recusa_no_upload(")
    corpo = _FONTE[i:_FONTE.index("\n@app.post", i)]
    fn = [n for n in ast.walk(ast.parse(corpo.strip()))
          if isinstance(n, ast.FunctionDef)][0]
    assert any(isinstance(n, ast.Raise) for n in ast.walk(fn)), (
        "`_recusa_no_upload` parou de levantar — a rota continuaria rodando "
        "depois de uma recusa")
    assert not any(isinstance(n, ast.Return) and n.value is not None
                   for n in ast.walk(fn)), (
        "ela passou a DEVOLVER em vez de levantar; quem chama não confere "
        "retorno e o upload seguiria")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — a rota de ANTES, no MESMO julgamento
# ══════════════════════════════════════════════════════════════════════════
_ANTES = '''
async def process_files(request, files):
    jwt_user = _get_user_from_request(request)
    if not jwt_user:
        raise HTTPException(401, "Faça login para enviar um projeto.")
    if not files:
        raise HTTPException(400, "Nenhum arquivo enviado")
    if not valid_pairs:
        raise HTTPException(400, "Nenhum arquivo válido encontrado.")
'''


def test_CONTROLE_a_rota_de_ANTES_REPROVA_no_mesmo_julgamento():
    soltas = _recusas_sem_rastro(_rota_process(_ANTES))
    assert len(soltas) == 3, (
        "o julgamento não vê as recusas mudas do código antigo — ele não está "
        "julgando nada e o teste de cima é verde falso; achei %s" % soltas)
    assert not _recusas_registradas(_rota_process(_ANTES))


_DEPOIS = '''
async def process_files(request, files):
    if not files:
        _recusa_no_upload(400, "Nenhum arquivo enviado", "sem-arquivo")
'''


def test_CONTROLE_a_rota_NOVA_passa_no_mesmo_julgamento():
    assert not _recusas_sem_rastro(_rota_process(_DEPOIS)), (
        "o julgamento reprova a forma correta — está apertado demais")
    assert len(_recusas_registradas(_rota_process(_DEPOIS))) == 1
