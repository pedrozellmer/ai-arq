# -*- coding: utf-8 -*-
"""A imagem da prancha sai do Storage e chega na tela do cliente.

🩸 17/09/2026. O motor renderiza um PNG de cada prancha CAD desde 22/04 e
sobe pro Storage. **Em 5 meses, ZERO clientes conseguiram ver um.** 52 das 56
imagens do balde estavam prontas, guardadas, esperando — 33 projetos, 19
clientes — e todo clique em "Prancha" caía em 404.

Eram DOIS cortes em série, e consertar um só não entregava nada:

  1. `_find_prancha_file` só juntava candidatos `.pdf` (três lugares), então
     nunca devolvia um nome `.dwg/.dxf` — e o ramo do `/api/sheet` que servia
     o PNG era **código INALCANÇÁVEL desde que nasceu**. O docstring da rota
     afirmava que esse ramo funcionava.
  2. Quem batiza o PNG tira o sufixo `_libredwg`; o `ref_sheet` que a tela
     manda de volta GUARDA o sufixo. Duas cópias da mesma receita divergindo.

📏 Medido antes de mexer, contra o banco: casando o nome CRU, **8 dos 56**
PNGs são alcançáveis. Tirando o sufixo, **52 de 56**. Por isso um commit só.

🔑 O que estes guardas prendem é o FATO (a imagem chega, o vizinho não é
mordido, CAD cru nunca sai), não a forma de cada função — e todos CHAMAM o
código. Guarda que lê o fonte já nos traiu três vezes este mês; foi
justamente um docstring mentindo que deixou este defeito viver 5 meses.
"""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_JOB = "job-de-teste-0001"
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
_PDF = b"%PDF-1.4\n" + b"0" * 64
_CAD = b"AC1027" + b"0" * 64


# ══════════════════════════════════════════════════════════════════════════
#  O NOME: uma receita só, porque duas divergem
# ══════════════════════════════════════════════════════════════════════════
def test_o_sufixo_do_conversor_sai_do_nome():
    """O corte nº2, isolado. `planta_libredwg.dxf` vira a imagem `planta.png`
    — logo quem procura tem que perguntar por `planta`, não por
    `planta_libredwg`."""
    assert main._stem_da_prancha("planta_libredwg.dxf") == "planta"
    assert main._stem_da_prancha("planta.dxf") == "planta"
    assert main._stem_da_prancha("/tmp/x/planta_libredwg.dxf") == "planta"


def test_CONTROLE_o_splitext_CRU_nao_resolve():
    """Controle positivo do guarda acima: se `_stem_da_prancha` virar um
    `splitext` pelado, este teste tem que ficar vermelho. É ele que prova que
    a função faz alguma coisa além do óbvio."""
    cru = os.path.splitext(os.path.basename("planta_libredwg.dxf"))[0]
    assert cru == "planta_libredwg"
    assert main._stem_da_prancha("planta_libredwg.dxf") != cru, (
        "a função virou splitext cru — o corte do `_libredwg` sumiu e a "
        "imagem volta a não ser achada por ninguém")


def test_as_DUAS_pontas_derivam_o_MESMO_nome():
    """🔑 O guarda que importa: quem GRAVA a imagem e quem a PROCURA têm que
    chegar no mesmo nome. Enquanto eram duas cópias, elas divergiam por
    construção e a imagem ficava órfã.

    Encena as duas pontas como a produção faz: o motor parte do caminho do DXF
    convertido; a busca parte do `ref_sheet` que a tela devolve.
    """
    for convertido, ref_sheet in [
        ("/tmp/arq_dxf_ab12/planta_libredwg.dxf", "planta_libredwg.dxf"),
        ("/tmp/arq_dxf_ab12/ARQ-R03.dxf", "ARQ-R03.dxf"),
        ("/tmp/arq_dxf_ab12/planta baixa_libredwg.dxf", "planta baixa_libredwg.dxf"),
    ]:
        gravado = main._stem_da_prancha(convertido) + ".png"
        procurado = main._stem_da_prancha(ref_sheet) + ".png"
        assert gravado == procurado, (
            "o motor grava %r e a busca procura %r — a imagem fica órfã"
            % (gravado, procurado))


# ══════════════════════════════════════════════════════════════════════════
#  A RECEITA NÃO PODE SE DUPLICAR (guarda de DIVERGÊNCIA, pela AST)
# ══════════════════════════════════════════════════════════════════════════
def _receitas_de_nome_de_imagem(fonte):
    """Toda expressão que MONTA um nome terminado em .png, e de onde ela parte.

    🪤 Achado pela SABOTAGEM (M14, 17/09): a mutação que faz o motor voltar a
    batizar a imagem COM o `_libredwg` dentro — exatamente o defeito original —
    SOBREVIVEU a todos os outros guardas. Aquela linha mora no fundo do
    `process_job`, que nenhum teste consegue executar inteiro.

    🔑 Então o guarda mira na DIVERGÊNCIA, não no comportamento: existe UMA
    receita pro nome da imagem, e ela é `_stem_da_prancha`. Qualquer segunda
    receita (um `splitext` solto, um `rsplit('.')`) é reprovada aqui — que é a
    lição de [[feedback_a_receita_repetida_e_a_doenca]], e é declarado: este é
    um guarda de FONTE, e vale pelo que a AST prova, não por texto.
    """
    import ast
    arvore = ast.parse(fonte)

    def _da_receita(no):
        return isinstance(no, ast.Call) and getattr(no.func, "id", None) == "_stem_da_prancha"

    # 1) Toda variável que NASCE da receita única. Assim o guarda não depende de
    #    um nome combinado (`_stem_img`): ele segue a origem.
    #    🪤 A versão anterior reconhecia UM nome fixo, e reprovou código certo na
    #    primeira vez que apareceu um segundo nome legítimo.
    da_receita = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Assign) and _da_receita(no.value):
            for alvo in no.targets:
                if isinstance(alvo, ast.Name):
                    da_receita.add(alvo.id)

    def _ok(esq):
        return _da_receita(esq) or (isinstance(esq, ast.Name) and esq.id in da_receita)

    def _termina_em_png(v):
        return isinstance(v, str) and v.lower().endswith(".png")

    fora = []
    for no in ast.walk(arvore):
        ln = getattr(no, "lineno", -1)

        # 2) `<algo> + ".png"`
        if isinstance(no, ast.BinOp) and isinstance(no.op, ast.Add):
            if (isinstance(no.right, ast.Constant)
                    and _termina_em_png(no.right.value) and not _ok(no.left)):
                fora.append((ln, "concat: " + ast.dump(no.left)[:70]))

        # 3) f-string que termina em ".png" — brecha achada pela revisão
        elif isinstance(no, ast.JoinedStr) and no.values:
            ult = no.values[-1]
            if isinstance(ult, ast.Constant) and _termina_em_png(ult.value):
                anterior = [v for v in no.values if isinstance(v, ast.FormattedValue)]
                if not (anterior and _ok(anterior[-1].value)):
                    fora.append((ln, "f-string terminando em .png"))

        # 4) `"%s.png" % x` e `"{}.png".format(x)`
        elif isinstance(no, ast.BinOp) and isinstance(no.op, ast.Mod):
            if isinstance(no.left, ast.Constant) and _termina_em_png(no.left.value):
                fora.append((ln, "%-format terminando em .png"))
        elif (isinstance(no, ast.Call)
              and isinstance(no.func, ast.Attribute) and no.func.attr == "format"
              and isinstance(no.func.value, ast.Constant)
              and _termina_em_png(no.func.value.value)):
            fora.append((ln, ".format() terminando em .png"))

        # 5) 🎯 Mexer no stem DEPOIS de derivá-lo. `_stem_img += "_libredwg"` é
        #    literalmente o defeito de 5 meses voltando, e passava por tudo.
        elif isinstance(no, ast.AugAssign):
            if isinstance(no.target, ast.Name) and no.target.id in da_receita:
                fora.append((ln, "o stem foi ALTERADO depois de derivado"))

    return fora


def test_existe_UMA_receita_pro_nome_da_imagem():
    fonte = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    fora = _receitas_de_nome_de_imagem(fonte)
    assert fora == [], (
        "apareceu uma SEGUNDA receita pro nome da imagem da prancha — foi "
        "exatamente assim que a miniatura ficou 5 meses sem chegar em "
        "ninguém: %r" % (fora,))


def test_CONTROLE_o_guarda_da_receita_REPROVA_a_copia():
    """Prova que o guarda acima reprova de verdade — senão ele é decoração."""
    ruim = "x = os.path.splitext(nome)[0] + '.png'\n"
    assert _receitas_de_nome_de_imagem(ruim), "o guarda deixou passar um splitext solto"
    pior = "y = os.path.basename(p).rsplit('.', 1)[0] + '.png'\n"
    assert _receitas_de_nome_de_imagem(pior), "o guarda deixou passar um rsplit solto"
    bom = ("z = _stem_da_prancha(p) + '.png'\n"
           "_stem_img = _stem_da_prancha(q)\n"
           "w = _stem_img + '.png'\n")
    assert _receitas_de_nome_de_imagem(bom) == [], "o guarda reprovou a receita certa"
    # 🪤 O atalho por variável só vale pra variável que NASCEU da receita. Um
    # `_stem` qualquer (este arquivo tem outro, de checkpoint de página de PDF)
    # não pode ser aceito como se fosse.
    colidido = "w = _stem + '.png'\n"
    assert _receitas_de_nome_de_imagem(colidido), (
        "o guarda aceitou um `_stem` qualquer como se fosse a receita da imagem")

    # 🎯 As brechas que a revisão adversarial achou — todas passavam antes.
    brechas = {
        "f-string":  "s = _stem_da_prancha(p)\nx = f'{outro}.png'\n",
        "%-format":  "x = '%s.png' % outro\n",
        ".format()": "x = '{}.png'.format(outro)\n",
        "mexer no stem depois":
            "_stem_img = _stem_da_prancha(p)\n_stem_img += '_libredwg'\ny = _stem_img + '.png'\n",
    }
    for nome, codigo in brechas.items():
        assert _receitas_de_nome_de_imagem(codigo), (
            "o guarda deixou passar a brecha %r — era por aí que o defeito de "
            "5 meses voltava" % nome)


def test_o_stem_so_nasce_da_receita_unica():
    """A porta dos fundos do guarda acima: `_stem_img` só vale como atalho se
    ele mesmo vier de `_stem_da_prancha`."""
    import ast
    fonte = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    for no in ast.walk(ast.parse(fonte)):
        if not isinstance(no, ast.Assign):
            continue
        for alvo in no.targets:
            if isinstance(alvo, ast.Name) and alvo.id == "_stem_img":
                assert (isinstance(no.value, ast.Call)
                        and getattr(no.value.func, "id", None) == "_stem_da_prancha"), (
                    "linha %d: `_stem_img` nasceu de outra coisa que não a receita "
                    "única — o atalho do guarda virou buraco" % no.lineno)


# ══════════════════════════════════════════════════════════════════════════
#  A BUSCA: acha a imagem, e não morde o vizinho
# ══════════════════════════════════════════════════════════════════════════
def _com_listagem(monkeypatch, nomes, tmp_path=None):
    """Encena a listagem do Storage do job (e um WORK_DIR vazio)."""
    class _Resp(object):
        def __init__(self, payload):
            self._p = payload

        def read(self):
            return json.dumps(self._p).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, *a, **k):
        return _Resp([{"name": n} for n in nomes])

    monkeypatch.setattr(main.urllib.request, "urlopen", _urlopen)
    if tmp_path is not None:
        monkeypatch.setattr(main, "WORK_DIR", str(tmp_path))


def test_o_ref_de_CAD_ACHA_a_imagem_renderizada(monkeypatch, tmp_path):
    """O conserto, em uma linha: o cliente clica na prancha CAD e recebe a
    imagem que estava guardada esperando."""
    _com_listagem(monkeypatch, ["planta_libredwg.dxf", "planta.png"], tmp_path)
    achado = main._find_prancha_file(_JOB, "planta_libredwg.dxf")
    assert achado == "planta.png", (
        "a imagem estava no Storage e a busca não a achou: %r" % achado)


def test_a_imagem_AINDA_NO_DISCO_tambem_e_achada(monkeypatch, tmp_path):
    """🪤 Achado pela SABOTAGEM (M03): meus guardas encenavam só o Storage, e a
    mutação que parava de recolher PNG do disco local SOBREVIVEU.

    O caso é real e é o mais comum de todos: logo depois do job rodar, a imagem
    ainda está no disco do servidor — é dali que o primeiro cliente a abrir vai
    ser servido, sem custar uma ida ao Storage.
    """
    (tmp_path / _JOB).mkdir(parents=True, exist_ok=True)
    (tmp_path / _JOB / "planta.png").write_bytes(_PNG)
    _com_listagem(monkeypatch, [], tmp_path)   # Storage VAZIO de propósito
    achado = main._find_prancha_file(_JOB, "planta_libredwg.dxf")
    assert achado == "planta.png", (
        "a imagem estava no disco local e a busca não a achou: %r" % achado)


def test_CONTROLE_sem_a_imagem_no_balde_NAO_inventa_nada(monkeypatch, tmp_path):
    """Controle positivo: sem PNG, a busca não pode devolver coisa nenhuma —
    muito menos o CAD cru."""
    _com_listagem(monkeypatch, ["planta_libredwg.dxf"], tmp_path)
    achado = main._find_prancha_file(_JOB, "planta_libredwg.dxf")
    assert achado is None, "inventou uma prancha que não existe: %r" % achado


def test_o_VIZINHO_o_ref_de_PDF_recebe_o_MESMO_pdf(monkeypatch, tmp_path):
    """🚨 O vizinho. Uma família de cliente JÁ conseguia abrir o PDF dela hoje.
    O conserto só pode transformar 404 em imagem — nunca trocar uma entrega
    que funcionava."""
    _com_listagem(monkeypatch, ["prancha.pdf", "prancha.png"], tmp_path)
    assert main._find_prancha_file(_JOB, "prancha.pdf") == "prancha.pdf", (
        "quem nomeia um PDF passou a receber outra coisa — mordi o vizinho")


def test_a_imagem_NAO_entra_no_desempate_dos_pdfs(monkeypatch, tmp_path):
    """🔑 Os PNG moram num conjunto SEPARADO de propósito. Se entrassem na
    pontuação junto com os PDFs, um ref que nomeia um PDF poderia passar a
    receber a imagem de OUTRA prancha do mesmo projeto."""
    _com_listagem(monkeypatch,
                  ["ARQ-01 PLANTA BAIXA.pdf", "ARQ-01 PLANTA BAIXA.png",
                   "ARQ-02 CORTES.pdf", "ARQ-02 CORTES.png"], tmp_path)
    for alvo in ("ARQ-01 PLANTA BAIXA.pdf", "ARQ-02 CORTES.pdf"):
        assert main._find_prancha_file(_JOB, alvo) == alvo, (
            "%r deixou de receber o próprio PDF" % alvo)


def test_descricao_da_IA_nao_casa_com_imagem_por_ACIDENTE(monkeypatch, tmp_path):
    """🪤 O `ref_sheet` às vezes traz descrição em vez de nome de arquivo, e
    `splitext('PLANTA 1.5 - TÉRREO')` devolve 'PLANTA 1'. Sem a porta estreita
    (só .dwg/.dxf), isso casaria com a imagem de outra prancha.

    🪤 Este guarda já sobreviveu a uma sabotagem (M06, 17/09) porque o cenário
    tinha um PDF junto: com o conserto do "PDF de mesmo nome vence", a
    descrição passava a casar com o PDF e o teste seguia verde mesmo com a
    porta escancarada. O caso que REALMENTE prende a porta é o que só tem
    imagem — senão o guarda mede o conserto vizinho, não o próprio.
    """
    # 1) SÓ a imagem: é aqui que a porta estreita é a única coisa que protege.
    _com_listagem(monkeypatch, ["PLANTA 1.png"], tmp_path)
    achado = main._find_prancha_file(_JOB, "PLANTA 1.5 - TÉRREO")
    assert achado != "PLANTA 1.png", (
        "uma DESCRIÇÃO casou com a imagem de outra prancha, por acidente "
        "do splitext — é entregar desenho errado calado")

    # 2) com PDF junto, idem (e aqui quem também protege é o passo 4)
    _com_listagem(monkeypatch, ["PLANTA 1.png", "PLANTA 1.pdf"], tmp_path)
    assert main._find_prancha_file(_JOB, "PLANTA 1.5 - TÉRREO") != "PLANTA 1.png"


def test_mesma_pergunta_MESMA_resposta(monkeypatch, tmp_path):
    """🪤 O desempate por pontuação itera um `set`, cuja ordem depende do
    PYTHONHASHSEED — resposta que muda entre restarts do Render. O caminho da
    imagem é igualdade exata, então tem que ser estável em qualquer ordem."""
    respostas = set()
    for ordem in ([ "a.png", "planta.png", "z.png", "planta_libredwg.dxf"],
                  ["planta_libredwg.dxf", "z.png", "planta.png", "a.png"],
                  ["z.png", "planta.png", "planta_libredwg.dxf", "a.png"]):
        _com_listagem(monkeypatch, ordem, tmp_path)
        respostas.add(main._find_prancha_file(_JOB, "planta_libredwg.dxf"))
    assert respostas == {"planta.png"}, (
        "a mesma pergunta deu respostas diferentes conforme a ordem: %r"
        % (respostas,))


def test_a_busca_NAO_sai_do_proprio_projeto(monkeypatch, tmp_path):
    """🚨 Regra dura nº2 (isolamento). O nome devolvido tem que vir da
    listagem presa ao próprio job.

    🪤 Este guarda já nasceu frouxo: ele aceitava `None` como sucesso, então a
    sabotagem que arranca o `basename` passava por ele (quem matou aquela foi um
    guarda vizinho). O FATO certo não é "não achou" — é **o que sai tem que ser
    um nome da listagem DESTE job**, sempre.
    """
    do_job = ["planta.png", "prancha.pdf"]
    _com_listagem(monkeypatch, do_job, tmp_path)
    for veneno in ("../outro-job/planta.dxf",
                   "..%2Foutro-job%2Fplanta.dxf",
                   "/etc/passwd.dxf",
                   "..\\outro-job\\planta.dxf",
                   "C:\\Windows\\win.ini.dxf"):
        achado = main._find_prancha_file(_JOB, veneno)
        assert achado is None or achado in do_job, (
            "a busca devolveu algo que não está na listagem deste job: "
            "%r → %r" % (veneno, achado))
        if achado:
            assert "/" not in achado and "\\" not in achado, (
                "devolveu caminho, não nome: %r" % achado)


# ══════════════════════════════════════════════════════════════════════════
#  A ROTA: entrega a imagem, e NUNCA o CAD cru
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture()
def _cliente(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: "dono-1")
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path))
    return TestClient(main.app, raise_server_exceptions=False)


def test_a_ROTA_entrega_a_IMAGEM_pro_ref_de_CAD(_cliente, monkeypatch, tmp_path):
    """Ponta a ponta pela rota de verdade: ref de CAD → 200 com image/png."""
    _com_listagem(monkeypatch, ["planta_libredwg.dxf", "planta.png"], tmp_path)
    monkeypatch.setattr(main, "_supabase_storage_download_prancha",
                        lambda j, n: _PNG if n == "planta.png" else None)
    r = _cliente.get("/api/sheet/%s" % _JOB, params={"ref": "planta_libredwg.dxf"})
    assert r.status_code == 200, (r.status_code, r.text[:200])
    assert r.headers.get("content-type", "").startswith("image/png"), r.headers
    assert r.headers.get("X-Filename") == "planta.png", r.headers
    assert r.content == _PNG


def test_o_cabecalho_DIZ_o_nome_do_que_foi_entregue(_cliente, monkeypatch, tmp_path):
    """🪤 Sem `filename=` no Content-Disposition, quem baixa salva a IMAGEM com
    extensão `.dxf` — arquivo que não abre em lugar nenhum."""
    _com_listagem(monkeypatch, ["planta_libredwg.dxf", "planta.png"], tmp_path)
    monkeypatch.setattr(main, "_supabase_storage_download_prancha",
                        lambda j, n: _PNG)
    r = _cliente.get("/api/sheet/%s" % _JOB, params={"ref": "planta_libredwg.dxf"})
    cd = r.headers.get("content-disposition", "")
    assert 'filename="planta.png"' in cd, (
        "o cabeçalho não diz o nome do que veio: %r" % cd)
    assert ".dxf" not in cd, cd


def test_a_ROTA_NUNCA_entrega_CAD_cru(_cliente, monkeypatch, tmp_path):
    """🚨 A trava estrutural. Se um dia alguém alargar a busca lá em cima, esta
    rota NÃO pode passar a despejar DWG inline: medido, os PNG têm 0,04 MB em
    média e os CAD do mesmo balde chegam a 232 MB, tudo em memória.

    Controle positivo embutido: o arquivo EXISTE e o download funcionaria —
    é a rota que tem que recusar."""
    (tmp_path / _JOB).mkdir(parents=True, exist_ok=True)
    (tmp_path / _JOB / "planta.dxf").write_bytes(_CAD)
    monkeypatch.setattr(main, "_find_prancha_file", lambda j, r: "planta.dxf")
    monkeypatch.setattr(main, "_supabase_storage_download_prancha",
                        lambda j, n: _CAD)
    r = _cliente.get("/api/sheet/%s" % _JOB, params={"ref": "planta.dxf"})
    assert r.status_code == 404, (
        "a rota entregou CAD cru: %s %s" % (r.status_code,
                                            r.headers.get("content-type")))
    assert _CAD not in r.content
    assert "acad" not in r.headers.get("content-type", "")


def test_o_PDF_continua_saindo_pela_ROTA(_cliente, monkeypatch, tmp_path):
    """O vizinho, agora pela rota inteira."""
    _com_listagem(monkeypatch, ["prancha.pdf"], tmp_path)
    monkeypatch.setattr(main, "_supabase_storage_download_prancha",
                        lambda j, n: _PDF if n == "prancha.pdf" else None)
    r = _cliente.get("/api/sheet/%s" % _JOB, params={"ref": "prancha.pdf"})
    assert r.status_code == 200, (r.status_code, r.text[:200])
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content == _PDF


# ══════════════════════════════════════════════════════════════════════════
#  A TELA: diz que a imagem foi gerada por nós (regra dura nº1)
# ══════════════════════════════════════════════════════════════════════════
def _tela(nome_entregue):
    """Roda o JS DE VERDADE de visualizar-prancha.html com a resposta encenada.

    Devolve o estado dos elementos que a tela mexeu.
    """
    from _jsbancada import funcao_js, motor

    src = None
    preludio = """
    var __el = {};
    function __get(id){ if(!__el[id]) __el[id] = {hidden:true, textContent:'',
                                                  title:'', src:'',
                                                  style:{display:'none'}};
                        return __el[id]; }
    var document = { getElementById: __get, body: {}, title: '' };
    var currentBlobUrl = null, nomeEntregue = null;
    var ref = 'planta_libredwg.dxf';
    var pdfUrl = '/api/sheet/x?ref=planta_libredwg.dxf';
    function decodeURIComponent(s){ return s; }
    function showFatal(m){ __el.__fatal = {textContent: m}; }
    var URL = { createObjectURL: function(){ return 'blob:fake'; } };
    var sbClient = { auth: { getSession: function(){
        return Promise.resolve({data:{session:{access_token:'t'}}}); } } };
    var __ENTREGUE = %s;
    function fetch(){ return Promise.resolve({
        ok: true, status: 200,
        headers: { get: function(h){
            return h === 'X-Filename' ? __ENTREGUE : null; } },
        blob: function(){ return Promise.resolve({}); }
    }); }
    """ % json.dumps(nome_entregue)

    js = motor(preludio)
    js.evaljs(funcao_js("ehRender", "visualizar-prancha.html", src))
    js.evaljs(funcao_js("loadPdfIntoFrame", "visualizar-prancha.html", src))
    js.evaljs("var __P = loadPdfIntoFrame();")
    js.evaljs("null;")  # drena a fila de promessas
    return json.loads(js.evaljs("JSON.stringify(__el)"))


def test_o_SELO_nasce_escondido_pelo_ESTILO_nao_so_pelo_atributo():
    """🩸 Achado pela SABOTAGEM (M29, 17/09) — o único sobrevivente da rodada,
    e justamente o bloqueio original voltando.

    O guarda de JS fabrica o elemento, então ele nunca toca na MARCAÇÃO: com o
    `style="display:none"` arrancado do HTML, todos os testes seguiam verdes e
    o selo voltava a aparecer SEMPRE — inclusive em cima do PDF do próprio
    cliente, dizendo que fomos nós que geramos o desenho dele.

    O botão tinha esse guarda; o selo não. Falha simétrica, e foi a sabotagem
    que apontou. 🪤 Guarda de FONTE, declarado: é a marcação que ele prende.
    """
    from _jsbancada import fonte_html
    src = fonte_html("visualizar-prancha.html")
    i = src.find('id="selo-render"')
    assert i > 0, "sumiu o selo de honestidade da tela"
    tag = src[i:src.find(">", i)]
    assert "hidden" in tag, "o selo perdeu o `hidden` (leitor de tela): %r" % tag
    assert 'style="display:none"' in tag, (
        "o selo voltou a se esconder SÓ pelo atributo `hidden`, que perde pro "
        "`.flex` nesta folha — ele passa a aparecer sempre, inclusive em cima "
        "do PDF do próprio cliente: %r" % tag)


def test_a_tela_DIZ_que_a_imagem_foi_gerada_por_nos():
    """🚨 Regra dura nº1. O botão que trouxe o cliente fala em conferir a
    prancha. Entregar um desenho que NÓS renderizamos, sem dizer que foi a
    gente que renderizou, é apresentar desenho como se fosse o original."""
    el = _tela("planta.png")
    selo = el.get("selo-render", {})
    assert selo.get("hidden") is False, (
        "a imagem é um render nosso e a tela não avisou — regra nº1")
    # 🩸 E o estilo: o atributo `hidden` sozinho não esconde nem mostra nada
    # nesta folha. Cobrar só ele foi o que deixou o selo INERTE passar verde.
    assert selo.get("style", {}).get("display") == "", (
        "o selo foi 'mostrado' e continua com display:none: %r" % selo)


def test_CONTROLE_o_PDF_do_cliente_NAO_leva_o_selo():
    """A mentira ao contrário: carimbar 'gerado por nós' no PDF que o próprio
    cliente mandou também é falso, e assusta à toa."""
    el = _tela("prancha.pdf")
    selo = el.get("selo-render", {})
    # 🪤 O fato é "o selo NÃO FICA VISÍVEL" — e não existe um valor fixo pro
    # estilo: quando a tela nem toca no elemento (que é o certo aqui), ele não
    # aparece no DOM encenado. Visível = `hidden` falso E `display` liberado;
    # é essa combinação que tem que ser impossível.
    visivel = (selo.get("hidden") is False
               and selo.get("style", {}).get("display") == "")
    assert not visivel, (
        "o selo ficou VISÍVEL em cima do PDF do próprio cliente — a tela está "
        "dizendo que a gente gerou o desenho dele: %r" % selo)


def test_a_barra_mostra_o_que_CHEGOU_mesmo_quando_nao_e_render():
    """🩸 Achado pela revisão adversarial (17/09). A linha que corrige o nome na
    barra morava DENTRO do `if` do selo. Quando o servidor entrega a prancha de
    OUTRO arquivo — o casamento aproximado do backend faz isso —, o cliente via
    um desenho em tela cheia rotulado com o nome que ele tinha clicado."""
    el = _tela("outra-prancha.pdf")
    assert el.get("filename", {}).get("textContent") == "outra-prancha.pdf", (
        "a barra ficou com o nome PEDIDO enquanto a tela mostrava outro "
        "arquivo: %r" % el.get("filename"))


def test_o_arquivo_salvo_leva_o_nome_do_que_VEIO():
    """A tela passa a saber o nome verdadeiro do que chegou — é dele que sai o
    nome do download."""
    el = _tela("planta.png")
    assert el.get("filename", {}).get("textContent") == "planta.png", (
        "a barra continua mostrando o nome do CAD, não o do que foi entregue")


def test_o_botao_do_CAD_leva_pro_VISUALIZADOR_nao_pro_arquivo():
    """🚨 Regra dura nº1, do lado do `projeto.html`. O botão do DWG/DXF passou a
    se chamar "Ver desenho" (Pedro, 17/09) porque agora ele entrega a imagem
    que a gente renderizou.

    E o destino tem que casar com o rótulo: ele abre o VISUALIZADOR, que é a
    única tela que carrega o selo dizendo que o desenho é nosso. Baixar o
    arquivo cru mostraria o render sem o aviso — botão que diz "ver" e baixa
    arquivo é a mesma mentira, só menor.
    """
    from _jsbancada import funcao_js, motor
    js = motor(funcao_js("botaoDaPrancha", "projeto.html"))
    for ext in ("dwg", "dxf", "DWG", "Dxf"):
        r = json.loads(js.evaljs("JSON.stringify(botaoDaPrancha(%s))" % json.dumps(ext)))
        assert r["rotulo"] == "Ver desenho", (ext, r)
        assert r["modo"] == "visualizador", (
            "%s não vai pro visualizador — o cliente veria o render SEM o selo: %r"
            % (ext, r))
        assert r["modo"] != "baixar", (ext, r)


def test_CONTROLE_o_PDF_e_o_resto_NAO_mudaram_de_botao():
    """O vizinho, na tela: PDF continua 'Abrir' e o que não é prancha continua
    'Baixar'. Se este teste ficar vermelho, eu mexi em quem não devia."""
    from _jsbancada import funcao_js, motor
    js = motor(funcao_js("botaoDaPrancha", "projeto.html"))
    pdf = json.loads(js.evaljs("JSON.stringify(botaoDaPrancha('pdf'))"))
    assert (pdf["rotulo"], pdf["modo"]) == ("Abrir", "abrir"), pdf
    for outro in ("zip", "", None, "png"):
        r = json.loads(js.evaljs(
            "JSON.stringify(botaoDaPrancha(%s))" % json.dumps(outro)))
        assert (r["rotulo"], r["modo"]) == ("Baixar", "baixar"), (outro, r)


def test_o_modo_visualizador_aponta_pra_tela_que_tem_o_selo():
    """🪤 Guarda de FONTE, e declarado como tal: o `.map()` que monta a linha do
    arquivo é uma arrow anônima, que o motor JS não consegue recortar. O que ele
    prende é o elo que a função sozinha não prova — que o modo `visualizador`
    leva a `visualizar-prancha.html`, e não ao `/api/sheet` cru.

    🪤 E a âncora é a INSTRUÇÃO INTEIRA (`const onclickAttr = ...`), não o
    trecho `acao.modo === 'visualizador'`: esse aparece DUAS vezes — uma pra
    escolher o ícone, outra pra escolher o destino. Ancorar no pedaço fez o
    guarda medir o ternário do ícone e reprovar um código certo, que é a
    armadilha de [[feedback_ancora_de_sabotagem_e_instrucao_inteira]].
    """
    from _jsbancada import fonte_html
    src = fonte_html("projeto.html")
    i = src.find("const onclickAttr = ")
    assert i > 0, "sumiu a montagem do onclick em projeto.html"
    fim = src.find(";", src.find("downloadProtected", i))
    trecho = src[i:fim if fim > i else i + 700]
    assert "acao.modo === 'visualizador'" in trecho, (
        "o destino do CAD não é mais decidido pelo modo: %r" % trecho[:200])
    assert "visualizar-prancha.html" in trecho or "safeViewer" in trecho, (
        "o modo 'visualizador' parou de abrir a tela do selo: %r" % trecho[:200])
    # E o ramo do CAD (o VERDADEIRO do ternário) não pode ser o de baixar
    # arquivo cru. 🪤 Recorta até o `:` do else — uma janela por contagem de
    # caracteres invade o ramo vizinho e reprova código certo.
    j = trecho.find("acao.modo === 'visualizador'")
    ramo = trecho[j:]
    k = ramo.find(": `onclick=\"downloadProtected")
    ramo_cad = ramo[:k] if k > 0 else ramo
    assert "window.open" in ramo_cad and "safeViewer" in ramo_cad, (
        "o ramo do CAD não abre mais o visualizador: %r" % ramo_cad)
    assert "downloadProtected" not in ramo_cad, (
        "o CAD voltou a baixar o arquivo cru — render sem selo: %r" % ramo_cad)


# ══════════════════════════════════════════════════════════════════════════
#  SÓ OFERECE O QUE TEM (Pedro, 17/09: "só mostra o botão quando tiver imagem")
# ══════════════════════════════════════════════════════════════════════════
def test_so_entra_na_lista_a_prancha_que_TEM_imagem(monkeypatch, tmp_path):
    """📏 Medido em 17/09: só ~36% dos arquivos CAD de projetos recentes têm
    imagem. Prometer "Ver desenho" nos outros é promessa quebrada em escala."""
    _com_listagem(monkeypatch, ["planta.png", "corte_libredwg.dxf"], tmp_path)
    fora = main._refs_com_imagem(
        _JOB, ["planta_libredwg.dxf", "corte_libredwg.dxf", "fachada.dxf"])
    assert fora == ["planta_libredwg.dxf"], (
        "ofereceu prancha sem imagem, ou escondeu uma que tem: %r" % (fora,))


def test_devolve_o_nome_COMO_VEIO(monkeypatch, tmp_path):
    """🪤 Existem TRÊS receitas de 'limpar o ref_sheet' neste sistema. Se eu
    devolvesse o nome na minha forma, a tela não reconheceria o próprio arquivo
    e o botão sumiria de todos. Ecoar o que veio é imune às três."""
    _com_listagem(monkeypatch, ["planta.png"], tmp_path)
    veio = "planta_libredwg.dxf (planta baixa do térreo)"
    fora = main._refs_com_imagem(_JOB, [veio])
    assert fora == [veio], (
        "reformatei o nome e a tela não vai se reconhecer: %r" % (fora,))


def test_sem_imagem_nenhuma_NAO_oferece_nada(monkeypatch, tmp_path):
    _com_listagem(monkeypatch, ["planta_libredwg.dxf"], tmp_path)
    assert main._refs_com_imagem(_JOB, ["planta_libredwg.dxf"]) == []


def test_o_PDF_nao_entra_nessa_lista(monkeypatch, tmp_path):
    """Esta lista é só do botão do CAD. PDF tem caminho próprio e não pode ser
    escondido por ela."""
    _com_listagem(monkeypatch, ["prancha.png", "prancha.pdf"], tmp_path)
    assert main._refs_com_imagem(_JOB, ["prancha.pdf"]) == []


def test_o_PARENTESE_no_nome_do_arquivo_nao_some_com_o_botao(monkeypatch, tmp_path):
    """🩸 Achado pela revisão adversarial DO MEU PRÓPRIO CONSERTO (17/09): eu
    estava consertando um defeito causado por duas receitas divergentes de nome
    — e criei uma QUARTA no mesmo commit.

    Caso real medido: `prancha (1)_libredwg.dxf`. O "(1)" é parte do nome
    do arquivo, não um hint da IA. A busca acertava; a minha lista cortava no
    "(" seco e devolvia vazio. 41 itens, 13 medidos, imagem pronta no balde, e
    o cliente sem botão.
    """
    nome = "prancha (1)_libredwg.dxf"
    _com_listagem(monkeypatch, ["prancha (1).png"], tmp_path)
    assert main._find_prancha_file(_JOB, nome) == "prancha (1).png"
    assert main._refs_com_imagem(_JOB, [nome]) == [nome], (
        "a busca acha a imagem e a lista diz que não tem — as duas receitas "
        "de limpar o nome voltaram a divergir")


def test_o_hint_da_IA_continua_sendo_cortado(monkeypatch, tmp_path):
    """CONTROLE do guarda acima: o corte tem que continuar existindo pro hint
    de verdade, que é o que termina em ")"."""
    _com_listagem(monkeypatch, ["planta.png"], tmp_path)
    com_hint = "planta_libredwg.dxf (planta baixa do térreo)"
    assert main._find_prancha_file(_JOB, com_hint) == "planta.png"
    assert main._refs_com_imagem(_JOB, [com_hint]) == [com_hint]


def test_o_PDF_de_mesmo_nome_VENCE_a_nossa_imagem(monkeypatch, tmp_path):
    """🥇 Achado pela revisão adversarial: sem isto, um projeto que mandou
    `planta.dwg` E `planta.pdf` passava a receber o NOSSO render no lugar do
    PDF vetorial do próprio cliente — desenho aproximado substituindo a prancha
    de verdade."""
    _com_listagem(monkeypatch, ["planta.pdf", "planta.png"], tmp_path)
    assert main._find_prancha_file(_JOB, "planta_libredwg.dxf") == "planta.pdf", (
        "a nossa imagem tomou o lugar do PDF do cliente")
    # e sem o PDF, a imagem entra normalmente
    _com_listagem(monkeypatch, ["planta.png"], tmp_path)
    assert main._find_prancha_file(_JOB, "planta_libredwg.dxf") == "planta.png"


def test_a_rota_da_lista_NAO_trava_o_laco_de_eventos():
    """🧊 Guarda de FONTE, declarado: `_refs_com_imagem` lista o Storage por
    rede, e a tela chama esta rota em TODA abertura de projeto. Com
    `--workers 1`, chamar isso direto de uma rota `async` congela o site."""
    import inspect
    src = inspect.getsource(main.pranchas_com_imagem)
    assert "run_in_threadpool" in src, (
        "a rota voltou a chamar a listagem dentro do laço de eventos")
    assert "_refs_com_imagem(job_id" not in src.replace(
        "run_in_threadpool(_refs_com_imagem, job_id", ""), (
        "sobrou uma chamada direta a `_refs_com_imagem` na rota async")


def test_a_ROTA_da_lista_exige_dono(_cliente, monkeypatch, tmp_path):
    """Regra dura nº2 pela porta nova."""
    chamou = []
    def _nega(request, job_id):
        chamou.append(job_id)
        raise main.HTTPException(403, "não é seu")
    monkeypatch.setattr(main, "_require_project_owner", _nega)
    monkeypatch.setattr(main, "_refs_com_imagem",
                        lambda *a, **k: pytest.fail("rodou ANTES de checar o dono"))
    r = _cliente.post("/api/projeto/%s/pranchas-com-imagem" % _JOB,
                      json={"refs": ["planta.dxf"]})
    assert r.status_code == 403, (r.status_code, r.text[:200])
    assert chamou == [_JOB]


def test_a_ROTA_da_lista_responde_o_que_tem(_cliente, monkeypatch, tmp_path):
    _com_listagem(monkeypatch, ["planta.png"], tmp_path)
    r = _cliente.post("/api/projeto/%s/pranchas-com-imagem" % _JOB,
                      json={"refs": ["planta_libredwg.dxf", "fachada.dxf"]})
    assert r.status_code == 200, (r.status_code, r.text[:200])
    assert r.json() == {"com_imagem": ["planta_libredwg.dxf"]}, r.json()


def test_a_ROTA_falha_FECHADA(_cliente, monkeypatch, tmp_path):
    """🪤 Storage fora do ar não pode virar "mostra tudo" — seria voltar a
    prometer o que a gente não tem. Lista vazia, botão escondido."""
    def _explode(*a, **k):
        raise RuntimeError("storage fora do ar")
    monkeypatch.setattr(main, "_arquivos_do_job", _explode)
    r = _cliente.post("/api/projeto/%s/pranchas-com-imagem" % _JOB,
                      json={"refs": ["planta_libredwg.dxf"]})
    assert r.status_code == 200, (r.status_code, r.text[:200])
    assert r.json() == {"com_imagem": []}, (
        "falhou ABERTA: ofereceu o botão sem saber se existe imagem")


def test_o_botao_do_CAD_nasce_ESCONDIDO():
    """🪤 Guarda de FONTE, declarado: o `.map()` que monta a linha é uma arrow
    anônima, que o motor JS não recorta.

    O fato que ele prende é o estado INICIAL — o botão do CAD só pode aparecer
    depois que o backend confirmar que existe imagem. Se ele nascer visível, o
    conserto vira o contrário do que o Pedro pediu: promete "Ver desenho" em
    tudo e falha em 2 de 3 cliques.
    """
    from _jsbancada import fonte_html
    src = fonte_html("projeto.html")
    i = src.find("const escondeAteSaber")
    assert i > 0, "sumiu o estado inicial escondido do botão do CAD"
    trecho = src[i:src.find(";", src.find("? `", i))]
    assert "data-prancha=" in trecho, (
        "o botão do CAD parou de nascer marcado: %r" % trecho[:200])
    # 🩸 ESTILO EM LINHA, não só o atributo. O `[hidden]` sozinho NÃO esconde
    # este botão nesta folha (ver o guarda seguinte, que prova isso). Cobrar só
    # `hidden` foi o que deixou a trava inerte passar verde em 17/09.
    assert 'style="display:none"' in trecho, (
        "o botão do CAD está sendo escondido só pelo atributo `hidden`, que "
        "PERDE pro `.inline-flex` nesta folha — a trava fica inerte: %r"
        % trecho[:240])
    # e ele tem que ser REALMENTE usado no <a>, não ficar só declarado
    assert "${escondeAteSaber}" in src, (
        "a variável existe e não chega no botão — o guarda mediria nada")


def test_por_que_o_atributo_hidden_SOZINHO_nao_serve_aqui():
    """🩸 O guarda que explica o bloqueio de 17/09 — e que reprova se alguém
    "simplificar" o estilo em linha achando que `hidden` basta.

    Ele mede a FOLHA de verdade: `[hidden]{display:none}` e
    `.inline-flex{display:inline-flex}` têm a MESMA especificidade (0,1,0), e
    o botão carrega as duas. Em empate de especificidade vence a regra que vem
    DEPOIS no arquivo. Enquanto `.inline-flex` estiver depois, o atributo
    sozinho não esconde nada.

    🔑 É por isso que a solução é estilo EM LINHA: ele ganha de qualquer regra
    da folha, independente da ordem em que o Tailwind for gerado da próxima vez
    — e este build é estático (ver [[reference_tailwind_build_estatico]]).
    """
    import io as _io
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    css = _io.open(os.path.join(raiz, "tailwind.min.css"),
                   encoding="utf-8", errors="replace").read()
    i_hidden = css.find("[hidden]")
    i_flex = css.find(".inline-flex{display:inline-flex}")
    assert i_hidden >= 0 and i_flex >= 0, (i_hidden, i_flex)
    assert i_hidden < i_flex, (
        "a folha mudou de ordem: agora `[hidden]` vem DEPOIS do `.inline-flex`. "
        "O estilo em linha continua correto, mas o motivo escrito no código "
        "envelheceu — reescreva o comentário em vez de apagá-lo.")
    # E o estilo em linha só perde pra `!important`: garanta que nenhuma regra
    # de display com !important alcança este botão.
    import re as _re
    imp = _re.findall(r"([^{}]*)\{[^{}]*display\s*:[^;{}]*!important[^{}]*\}", css)
    for sel in imp:
        assert "inline-flex" not in sel and "[hidden]" not in sel, (
            "apareceu um `display:…!important` que alcança o botão (%r) — o "
            "estilo em linha deixou de bastar" % sel[:80])


def test_a_tela_so_revela_o_que_o_backend_confirmou():
    """🚨 O JS de verdade (dukpy). Fatos: revela só o que voltou na resposta, e
    em caso de erro NÃO revela nada."""
    from _jsbancada import funcao_js, motor

    def _rodar(resposta_ok, lista):
        preludio = """
        var __revelados = [];
        var __els = {};
        function __mkEl(nome){ return {hidden:true, __nome:nome,
            set _(v){}, }; }
        var document = { querySelector: function(sel){
            var m = /data-prancha="(.*)"/.exec(sel);
            var nome = m ? m[1].replace(/\\\\/g,'') : '';
            if (!__els[nome]) return null;
            return __els[nome];
        }};
        var window = {};
        function cssEscape(s){ return String(s); }
        var API_BASE = 'http://x';
        var __OK = %s, __LISTA = %s;
        function authFetch(){ return Promise.resolve({
            ok: __OK,
            json: function(){ return Promise.resolve({com_imagem: __LISTA}); }
        }); }
        __els['planta_libredwg.dxf'] = {hidden:true, style:{display:'none'}};
        __els['fachada.dxf'] = {hidden:true, style:{display:'none'}};
        var filesSet = new Map([['planta_libredwg.dxf',{}], ['fachada.dxf',{}]]);
        var proj = {job_id:'j1'};
        """ % (json.dumps(resposta_ok).replace('"', ''), json.dumps(lista))
        js = motor(preludio)
        # 🔑 O `botaoDaPrancha` REAL, não um dublê: é ele quem decide quais
        # nomes viram pergunta pro backend. Encenar essa peça deixaria o guarda
        # provando só a si mesmo.
        js.evaljs(funcao_js("botaoDaPrancha", "projeto.html"))
        js.evaljs(funcao_js("revelarPranchasComImagem", "projeto.html"))
        js.evaljs("var __P = revelarPranchasComImagem(proj, filesSet);")
        js.evaljs("null;")
        return json.loads(js.evaljs("JSON.stringify(__els)"))

    vis = _rodar(True, ["planta_libredwg.dxf"])
    alvo = vis["planta_libredwg.dxf"]
    # 🩸 OS DOIS. Soltar só o atributo `hidden` deixava o botão escondido pra
    # sempre nesta folha — foi o bloqueio que a revisão achou em 17/09. Este
    # guarda antes cobrava só o atributo, e por isso passou verde com a trava
    # inerte: provava o ingrediente, não o prato.
    assert alvo["hidden"] is False, alvo
    assert alvo["style"]["display"] == "", (
        "o botão foi 'revelado' e continua com display:none — a trava ficou "
        "inerte: %r" % alvo)
    assert vis["fachada.dxf"]["hidden"] is True, (
        "revelou uma prancha que o backend NÃO confirmou: %r" % vis)
    assert vis["fachada.dxf"]["style"]["display"] == "none", vis["fachada.dxf"]

    # CONTROLE: resposta ruim não revela nada — falha fechada.
    ruim = _rodar(False, ["planta_libredwg.dxf"])
    assert ruim["planta_libredwg.dxf"]["hidden"] is True, (
        "falhou ABERTA: revelou o botão sem confirmação do backend")
    assert ruim["planta_libredwg.dxf"]["style"]["display"] == "none", (
        "falhou ABERTA pelo estilo: %r" % ruim["planta_libredwg.dxf"])


def test_a_regua_do_render_NAO_se_engana_com_pdf():
    """A régua que decide o selo, chamada de verdade."""
    from _jsbancada import funcao_js, motor
    js = motor(funcao_js("ehRender", "visualizar-prancha.html"))
    for nome, esperado in [("a.png", True), ("a.PNG", True), ("a.jpg", True),
                           ("a.pdf", False), ("a.dxf", False), ("", False)]:
        got = js.evaljs("ehRender(%s)" % json.dumps(nome))
        assert bool(got) is esperado, (nome, got)
