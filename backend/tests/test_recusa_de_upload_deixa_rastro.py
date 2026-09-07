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
import asyncio
import io
import os
import sys
import types

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

sys.path.insert(0, _BACKEND)
import main  # noqa: E402

HTTPException = main.HTTPException

# 🔒 regra dura nº6: rótulo, nunca pessoa. `example.com` é domínio reservado.
UID = "uid-do-cliente-01"
EMAIL = "cliente-01@example.com"


# ══════════════════════════════════════════════════════════════════════════
#  A BANCADA QUE EXECUTA — a rota de verdade, o banco de mentira
# ══════════════════════════════════════════════════════════════════════════
# 🩸 06/09/2026. Os quatro guardas críticos deste arquivo eram CEGOS: liam o
# fonte. Provado com mutação — embrulhar o `_log_error` de `_recusa_no_upload`
# num `if False:` deixava as DEZ portas mudas de novo e a bancada seguia verde,
# porque o julgamento só cobrava que a rota não tivesse `raise HTTPException`
# solto, e o `_recusa_no_upload` continuava lá, escrito, sem gravar nada.
# 🔑 Agora a rota RODA. O que se confere é a LINHA QUE IRIA PRO BANCO.
class _ArquivoFalso:
    """O que o Starlette entrega pro `_stream_upload_to_disk` (que roda de verdade)."""

    def __init__(self, filename, conteudo=b"", size=None):
        self.filename = filename
        self._buf = io.BytesIO(conteudo)
        # `size` diferente do conteúdo = conexão que caiu no meio do envio.
        self.size = len(conteudo) if size is None else size

    async def seek(self, n):
        self._buf.seek(n)

    async def read(self, n=-1):
        return self._buf.read(n)


class _Pedido:
    def __init__(self, content_length=None):
        self.headers = {}
        if content_length is not None:
            self.headers["content-length"] = str(content_length)
        self.client = types.SimpleNamespace(host="203.0.113.7")


class _Banco:
    """Fake do `_supabase_insert` — guarda TODA linha que o código gravaria.

    🔑 Interceptar aqui (e não o `_log_error`) faz o `_log_error` REAL rodar:
    o `severity`, o corte de 80/2000 e o texto do `motivo=` são os de produção.
    """

    def __init__(self):
        self.linhas = []

    def __call__(self, table, data):
        self.linhas.append((table, dict(data)))
        return None

    def recusas(self):
        return [d for t, d in self.linhas
                if t == "error_log" and d.get("stage") == "upload:recusado"]

    def motivos(self):
        fora = []
        for d in self.recusas():
            m = str(d.get("message") or "")
            fora.append(m.split("motivo=", 1)[-1].split(" ", 1)[0] if "motivo=" in m
                        else "?")
        return fora


@pytest.fixture
def bancada(monkeypatch, tmp_path):
    """Só rede/banco/thread saem do ar. A rota é a de produção, inteira."""
    b = _Banco()
    monkeypatch.setattr(main, "_supabase_insert", b)
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda request, tolerante=False: {"id": UID, "email": EMAIL})
    monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: True)
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_envio_recente_igual", lambda assinatura: None)
    monkeypatch.setattr(main, "_registrar_envio", lambda assinatura, job_id: None)
    monkeypatch.setattr(main, "_process_job_throttled", lambda *a, **k: None)
    monkeypatch.setattr(main, "_notify_admin", lambda *a, **k: True)
    monkeypatch.setattr(main, "_projeto_ja_enviado", lambda *a, **k: None)
    return b


def _sobe(files, content_length=None, user_id=UID):
    """Chama `/api/process` DE VERDADE. Devolve o dict ou levanta HTTPException."""
    async def _go():
        return await main.process_files(
            request=_Pedido(content_length), background_tasks=None, files=files,
            sheet_types=[], sheet_ambientes=[], project_name="proj-de-teste",
            user_email=EMAIL, user_id=user_id)

    return asyncio.run(_go())


def _pdf(nome="prancha.pdf", conteudo=b"%PDF-1.4 conteudo de prancha"):
    return _ArquivoFalso(nome, conteudo)


# As DEZ portas, cada uma com a entrada que a abre de verdade.
# 🪤 A entrada é entrada; o julgamento é o que sai (status + linha gravada).
def _abre_a_porta(motivo, monkeypatch):
    if motivo == "sem-login":
        monkeypatch.setattr(main, "_get_user_from_request",
                            lambda request, tolerante=False: None)
        return lambda: _sobe([_pdf()])
    if motivo == "token-nao-bate":
        return lambda: _sobe([_pdf()], user_id="uid-de-outra-pessoa")
    if motivo == "muitos-envios":
        monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: False)
        return lambda: _sobe([_pdf()])
    if motivo == "request-grande":
        return lambda: _sobe([_pdf()], content_length=451 * 1024 * 1024)
    if motivo == "sem-arquivo":
        return lambda: _sobe([])
    if motivo == "formato-nao-aceito":
        return lambda: _sobe([_ArquivoFalso("modelo.rvt", b"nao aceitamos isso")])
    if motivo == "muitos-arquivos":
        return lambda: _sobe([_pdf("p%02d.pdf" % i) for i in range(51)])
    if motivo == "envio-incompleto":
        # a conexão caiu: chegaram 10 bytes de 999.999 prometidos
        return lambda: _sobe([_ArquivoFalso("prancha.pdf", b"1234567890",
                                            size=999999)])
    if motivo == "dwg-pequeno-demais":
        return lambda: _sobe([_ArquivoFalso("planta.dwg", b"AC1032")])
    if motivo == "dwg-sem-assinatura":
        return lambda: _sobe([_ArquivoFalso("planta.dwg", b"PK" + b"z" * 300)])
    pytest.fail("porta desconhecida: %s" % motivo)


PORTAS = [
    ("sem-login", 401), ("token-nao-bate", 403), ("muitos-envios", 429),
    ("request-grande", 413), ("sem-arquivo", 400), ("formato-nao-aceito", 400),
    ("muitos-arquivos", 400), ("envio-incompleto", 400),
    ("dwg-pequeno-demais", 400), ("dwg-sem-assinatura", 400),
]


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
@pytest.mark.parametrize("motivo,status", PORTAS)
def test_nenhuma_recusa_do_upload_e_muda(bancada, monkeypatch, motivo, status):
    """RODA a rota em cada porta e confere a LINHA QUE IRIA PRO BANCO.

    🩸 A versão anterior lia o fonte: só cobrava que nenhum `raise HTTPException`
    ficasse solto na rota. Embrulhar o `_log_error` de `_recusa_no_upload` num
    `if False:` deixava as dez portas mudas — "tentou e a gente recusou" voltava
    a ser idêntico a "nunca tentou" — e o guarda continuava verde.
    """
    chama = _abre_a_porta(motivo, monkeypatch)
    with pytest.raises(HTTPException) as erro:
        chama()
    assert erro.value.status_code == status, (
        "a porta %s mudou de status: %s" % (motivo, erro.value.status_code))

    gravadas = bancada.recusas()
    assert len(gravadas) == 1, (
        "a porta %s recusou e NÃO gravou nada (%d linhas de recusa) — quem "
        "bater nela vai contar como 'nunca tentou subir'"
        % (motivo, len(gravadas)))
    linha = gravadas[0]
    assert ("motivo=%s" % motivo) in linha["message"], (
        "a linha gravada não diz o motivo: %r" % linha["message"])
    assert ("http=%d" % status) in linha["message"]
    assert linha["severity"] == "warning", (
        "recusa virou log comum (afoga o painel) ou subiu pra erro do motor: %r"
        % linha["severity"])
    assert EMAIL in linha["message"], (
        "a linha não diz QUEM tentou — sem isso não dá pra ligar a recusa à "
        "conta que sumiu do funil")


def test_a_rota_nao_tem_porta_de_recusa_muda_alem_das_dez():
    """🪤 Guarda ESTRUTURAL, e só pra isto: a 11ª porta que alguém acrescentar
    amanhã com `raise HTTPException` solto. As dez de hoje são julgadas
    EXECUTANDO, ali em cima."""
    soltas = _recusas_sem_rastro(_rota_process())
    assert not soltas, (
        "há recusa no /api/process que não deixa rastro (linha %s) — quem bater "
        "nela vai contar como 'nunca tentou subir'"
        % ", ".join(str(n) for n in soltas))


def test_as_DEZ_portas_continuam_registrando(bancada, monkeypatch):
    """As dez portas, uma atras da outra, NA MESMA bancada — e as dez GRAVAM.

    🩸 A versao anterior contava chamadas de `_recusa_no_upload` no AST. Contava
    10 enquanto ZERO delas registrava (`_log_error` sob `if False:`) e contava
    10 tambem com a porta do envio incompleto desligada (`if False and ...`).
    Contar o que esta ESCRITO nao e contar o que ACONTECE.

    🚨 Eram SETE quando este arquivo nasceu — as tres que faltavam sao as mais
    valiosas, porque sao "tentou e falhou" de verdade: envio incompleto (a
    conexao caiu no meio), DWG pequeno demais e DWG sem assinatura.
    """
    esperados = []
    for motivo, status in PORTAS:
        chama = _abre_a_porta(motivo, monkeypatch)
        with pytest.raises(HTTPException) as erro:
            chama()
        assert erro.value.status_code == status, (
            "porta %s devolveu status %s" % (motivo, erro.value.status_code))
        esperados.append(motivo)
        # 🪤 Devolve o ambiente ao normal: as duas portas que mexem em
        # dependencia (sem-login, muitos-envios) contaminariam as seguintes.
        monkeypatch.setattr(main, "_get_user_from_request",
                            lambda request, tolerante=False: {"id": UID,
                                                              "email": EMAIL})
        monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: True)

    assert bancada.motivos() == esperados, (
        "as dez portas recusaram, mas o banco recebeu %s" % bancada.motivos())
    assert len(bancada.recusas()) >= 10, (
        "a rota tinha 10 recusas REGISTRANDO e agora tem %d"
        % len(bancada.recusas()))


def test_o_envio_incompleto_e_registrado(bancada):
    """🔑 A recusa mais importante das dez: conexao que caiu no meio do envio.
    E literalmente o caso que ficava indistinguivel de "nunca tentou".

    🩸 A versao anterior lia `"envio-incompleto" in fonte_da_rota`. Desligar a
    porta com `if False and upload_file.size and n_written != upload_file.size:`
    mantinha as duas strings no fonte, e o guarda passava — com o truncamento
    por conexao caida deixando de ser detectado.
    """
    # 10 bytes chegaram; o navegador prometeu 999.999 — a conexao caiu.
    truncado = _ArquivoFalso("prancha.pdf", b"1234567890", size=999999)
    with pytest.raises(HTTPException) as erro:
        _sobe([truncado])
    assert erro.value.status_code == 400
    assert "incompleto" in str(erro.value.detail).lower(), (
        "o cliente nao foi avisado de que o arquivo chegou pela metade: %r"
        % erro.value.detail)

    gravadas = bancada.recusas()
    assert len(gravadas) == 1, (
        "o envio truncado nao deixou rastro (%d linhas) — a recusa mais "
        "importante das dez voltou a ser identica a 'nunca tentou'"
        % len(gravadas))
    msg = gravadas[0]["message"]
    assert "motivo=envio-incompleto" in msg, msg
    assert "10 de 999999 bytes" in msg, (
        "parou de registrar QUANTO chegou de quanto — sem isso nao da pra "
        "saber se foi a rede ou o arquivo: %r" % msg)

    # 🧪 CONTROLE POSITIVO: o mesmo arquivo COMPLETO passa pela porta.
    bancada.linhas.clear()
    inteiro = _ArquivoFalso("prancha.pdf", b"1234567890")   # size == conteudo
    saida = _sobe([inteiro])
    assert saida["status"] == "queued", saida
    assert not bancada.recusas(), (
        "a porta esta apertada demais: recusou um envio completo")


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


def test_a_recusa_SEMPRE_levanta_e_nunca_devolve_calada(bancada):
    """🪤 Se um dia ela deixar de levantar, o upload SEGUE depois da recusa —
    e ai a gente troca um silencio por um estrago.

    🩸 A versao anterior olhava o AST de `_recusa_no_upload`: achava UM
    `ast.Raise` e nenhum `return` com valor, e aprovava. Basta condicionar o
    raise (`if motivo != "formato-nao-aceito": raise ...`) pra UMA porta voltar
    a devolver calada — e o guarda velho passava. Agora ela e CHAMADA, motivo
    por motivo.
    """
    for motivo, status in PORTAS:
        devolveu = "<nao devolveu>"
        try:
            devolveu = main._recusa_no_upload(
                status, "mensagem pro cliente", motivo,
                detalhe="detalhe do caso", quem=EMAIL)
        except HTTPException as e:
            assert e.status_code == status
            continue
        pytest.fail(
            "`_recusa_no_upload` NAO levantou no motivo %r (devolveu %r) — a "
            "rota seguiria rodando depois da recusa" % (motivo, devolveu))

    assert bancada.motivos() == [m for m, _ in PORTAS], (
        "levantou, mas nao gravou tudo: %s" % bancada.motivos())

    # 🧪 CONTROLE POSITIVO na PORTA: se ela devolvesse em vez de levantar, o
    # upload de formato nao aceito seguiria e viraria job. Aqui ele NAO vira.
    bancada.linhas.clear()
    with pytest.raises(HTTPException):
        _sobe([_ArquivoFalso("modelo.rvt", b"nao aceitamos isso")])
    assert not [t for t, _ in bancada.linhas if t == "projects"], (
        "a recusa nao interrompeu o upload: um projeto foi criado mesmo assim")


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
