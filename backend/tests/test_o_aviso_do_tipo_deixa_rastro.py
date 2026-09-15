# -*- coding: utf-8 -*-
"""O cliente VIU o aviso do tipo de projeto? Até 15/09 não dava pra saber.

🎯 15/09/2026 — o estudo do tipo trocado (12 projetos, 9 desenhos em 2,5 meses)
mediu 0 de 5 trocas de tipo depois de aviso NÃO bloqueante, e parou aí: nenhum
dos avisos envolvidos deixava rastro de exibição. "Ninguém agiu" e "ninguém
viu" liam igual. O Pedro escolheu medir antes de mudar texto ou travar o envio.

O que este arquivo cobra — sempre RODANDO as telas, nunca procurando palavra:
  · o despacho REAL do envio (dashboard) com cada aviso da resposta → o evento
    DAQUELE tipo, com o job e a tela;
  · o `renderWarnings` REAL do projeto com as frases que o MOTOR escreve —
    lidas do main.py, não copiadas aqui → um evento por tipo, UMA vez por carga,
    e só com a "Visão geral" (onde o aviso mora) à vista;
  · cada evento que as telas dispararam passa pelo /api/track de verdade e é
    GRAVADO, não descartado calado (o defeito de 23/08 e de 02/09).

🪤 "Exibido" é DESENHADO NA TELA, não "lido". É o denominador.
🩸 A primeira versão contava o aviso com a vista escondida (quem chega por
`#quantitativo`) e este guarda passava verde: ele montava só as duas caixas,
sem a vista em volta. A revisão adversarial de 15/09 achou antes de subir.
"""
import asyncio
import io
import json
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

from _corpo import fonte  # noqa: E402
from _navegador import (atributos, bloco_a_partir_de, elementos,  # noqa: E402
                        montar, rodar, sem_await)

_RAIZ = os.path.dirname(os.path.dirname(_AQUI))
_JOB_TOPO = "ab12cd34"
_META_TOPO = {"job_id": _JOB_TOPO, "tela": "projeto"}


def _site(nome):
    return io.open(os.path.join(_RAIZ, nome), encoding="utf-8").read()


def _frases_do_motor():
    """As frases de aviso de TIPO que o motor grava, tiradas do main.py.

    🪤 Copiar a frase aqui deixaria o guarda verde justamente no dia em que ele
    serve: o motor muda o texto, a tela para de reconhecer, e a cópia do teste
    continua casando com a tela."""
    src = fonte("main.py")
    arq = re.findall(r'_warn_tipo = \("([^"]+)"', src)
    est = re.findall(r'_aviso_estrut = \(\s*"([^"]+)"', src)
    assert len(arq) == 1, (
        "a frase 'parece ser de ARQUITETURA' sumiu ou duplicou no motor: %r" % arq)
    assert len(est) == 2, (
        "os DOIS ramos do aviso de estrutura sem medida deviam aparecer: %r" % est)
    return {"parece-arquitetura": arq, "estrutura-sem-medida": est}


# ── O topo do projeto ─────────────────────────────────────────────────────

def _topo(avisos, telemetria=True, vezes=1, visao_escondida=False, depois=""):
    """Roda o `renderWarnings` de verdade, dentro da ÁRVORE real do HTML.

    `elementos` traz os ancestrais que o projeto.html declara — é assim que a
    vista "Visão geral" entra no teste pelo arquivo, e não por invenção minha.
    `depois` roda JS depois do render (ex.: o cliente abrir a Visão geral)."""
    site = _site("projeto.html")
    specs = elementos(site, ["proj-warnings", "proj-warnings-list"])
    visao = [s["id"] for s in specs
             if s["attrs"].get("data-vista") == "visao"
             and "vista" in (s["attrs"].get("class") or "").split()]
    assert len(visao) == 1, (
        "o #proj-warnings saiu de dentro da vista 'Visão geral' — a regra de só "
        "contar com essa vista à vista precisa ser revista: %r" % visao)
    js = [montar(specs),
          "_ligarTelemetria();" if telemetria else "",
          "var jobId = '%s';" % _JOB_TOPO,
          "function esc(s) { return String(s == null ? '' : s); }",
          "var VISTAS_PROJETO = ['visao', 'quantitativo'];",
          "var history = { replaceState: function () {} };",
          "window.scrollTo = function () {};",
          bloco_a_partir_de(site, "function mostrarVista(", "projeto.html", fecho=""),
          bloco_a_partir_de(site, "function renderWarnings(", "projeto.html", fecho=""),
          bloco_a_partir_de(site, "function _contarAvisoDoTopo(", "projeto.html", fecho=""),
          ("document.getElementById('%s').hidden = true;" % visao[0]) if visao_escondida else "",
          "var AVISOS = %s;" % json.dumps(avisos, ensure_ascii=False),
          "for (var __i = 0; __i < %d; __i++) renderWarnings(AVISOS);" % vezes,
          "var __antes = __eventos.length;",
          depois]
    return rodar(js, "({ev: __eventos, antes: __antes,"
                     " html: document.getElementById('proj-warnings-list').innerHTML})")


def test_o_aviso_PARECE_ARQUITETURA_do_motor_vira_evento():
    for frase in _frases_do_motor()["parece-arquitetura"]:
        r = _topo([frase], vezes=2)
        assert r["ev"] == [["aviso-topo:parece-arquitetura", _META_TOPO]], r["ev"]
        assert "ARQUITETURA" in r["html"], "o evento saiu e o aviso não foi desenhado"


def test_os_DOIS_ramos_do_aviso_de_ESTRUTURA_viram_evento():
    """O ramo 'falta altura' e o ramo 'falta prancha' começam igual; o segundo é
    o que sugere 'Ler como Arquitetura'. Os dois têm que contar — com o meta
    conferido INTEIRO (a revisão de 15/09 achou a tela trocada passando verde)."""
    for frase in _frases_do_motor()["estrutura-sem-medida"]:
        r = _topo(["Escala conferida pelo desenho", frase], vezes=2)
        assert r["ev"] == [["aviso-topo:estrutura-sem-medida", _META_TOPO]], (
            frase[:50], r["ev"])


def test_conta_UMA_vez_por_carga_mesmo_com_a_tela_redesenhando():
    """🪤 Contar a cada redesenho transforma o denominador em "quantas vezes a
    função rodou" — número que parece medir gente e mede código."""
    f = _frases_do_motor()
    r = _topo([f["parece-arquitetura"][0], f["estrutura-sem-medida"][0]], vezes=3)
    assert sorted(r["ev"]) == sorted([["aviso-topo:parece-arquitetura", _META_TOPO],
                                      ["aviso-topo:estrutura-sem-medida", _META_TOPO]]), r["ev"]


def test_aberto_em_OUTRA_vista_so_conta_quando_a_Visao_geral_aparece():
    """🩸 Quem chega por `projeto.html#quantitativo` carrega a página com a
    Visão geral escondida. O aviso NÃO foi visto — não conta. Quando o cliente
    abre a Visão geral, aí conta; e ir e voltar entre as vistas não conta de
    novo."""
    f = _frases_do_motor()
    r = _topo([f["parece-arquitetura"][0]], visao_escondida=True,
              depois="mostrarVista('visao'); mostrarVista('quantitativo'); mostrarVista('visao');")
    assert r["antes"] == 0, (
        "contou o aviso com a Visão geral escondida — denominador falso: %r" % r["ev"])
    assert r["ev"] == [["aviso-topo:parece-arquitetura", _META_TOPO]], (
        "abrir a Visão geral devia contar o aviso UMA vez: %r" % r["ev"])


def test_CONTROLE_visao_escondida_e_nunca_aberta_nao_conta_nada():
    f = _frases_do_motor()
    r = _topo([f["estrutura-sem-medida"][0]], visao_escondida=True,
              depois="mostrarVista('quantitativo');")
    assert r["ev"] == [], r["ev"]
    assert "ESTRUTURA" in r["html"], "a lista de avisos deixou de ser desenhada"


def test_CONTROLE_aviso_de_outro_assunto_NAO_conta():
    """O guarda acima só vale se a tela souber NÃO contar. A palavra ESTRUTURA
    no meio de outra frase não é o aviso; 'arquitetura' em minúscula também não."""
    outros = ["⚠ Pé-direito de 2,70 m INFORMADO POR VOCÊ",
              "✅ escala confirmada por 244 cotas",
              "Conferir a ESTRUTURA: metálica da cobertura",
              "Revisado: Este arquivo parece ser de ARQUITETURA",
              "O arquivo tem cara de arquitetura"]
    r = _topo(outros, depois="mostrarVista('visao');")
    assert r["ev"] == [], r["ev"]
    assert "Pé-direito" in r["html"], "a lista de avisos deixou de ser desenhada"


def test_CONTROLE_sem_telemetria_a_lista_continua_na_tela():
    """Sem consentimento o `trackEvent` não existe. Contar é acessório: a lista
    de avisos não pode sumir por causa dele."""
    f = _frases_do_motor()
    r = _topo([f["parece-arquitetura"][0]], telemetria=False,
              depois="mostrarVista('visao');")
    assert r["ev"] == [], r["ev"]
    assert "ARQUITETURA" in r["html"]


# ── A resposta do envio ───────────────────────────────────────────────────

_RESPOSTA = {
    "job_id": "cd34ef56",
    "aviso_aec": {"titulo": "t-aec", "texto": "a", "arquivos": ["x.dwg"]},
    "aviso_estrutural": {"titulo": "t-est", "texto": "b", "arquivos": ["y.pdf"]},
    "aviso_repetido": {"titulo": "t-rep", "texto": "c"},
    "aviso_area": {"titulo": "t-area", "texto": "d"},
}


def _envio(resposta, com_caixa=True):
    """Roda o despacho REAL da resposta do upload + o `mostrarAvisoAec`."""
    site = _site("dashboard.html")
    k = site.index("currentJobId = data.job_id;")
    i = site.rindex("const data = await res.json();", 0, k)
    fim = site.index("\n", site.index("if (data.aviso_area)", k))
    despacho = site[i:fim]
    # 🧪 controle do recorte: janela errada mediria outra coisa em silêncio.
    assert "aviso_estrutural" in despacho and len(despacho) < 3000, despacho[:200]
    caixa = atributos(site, "aviso-aec")
    assert caixa, "o id 'aviso-aec' sumiu do dashboard — o JS escreve nele"
    specs = ([{"id": "aviso-aec", "tag": caixa["tag"], "attrs": caixa["attrs"],
               "html": ""}] if com_caixa else [])
    js = [montar(specs),
          "_ligarTelemetria();",
          "var currentJobId = null, userCreditsCents = 0;",
          "var params = { project_type: 'arquitetura' };",
          "var DADOS = %s;" % json.dumps(resposta, ensure_ascii=False),
          "var res = { json: function () { return DADOS; } };",
          bloco_a_partir_de(site, "function mostrarAvisoAec(", "dashboard.html", fecho=""),
          "(function () { %s })();" % sem_await(despacho)]
    return rodar(js, "({ev: __eventos,"
                     " html: (document.getElementById('aviso-aec') || {}).innerHTML || ''})")


def _avisos(ev):
    return [e for e in ev if e[0].startswith("aviso-")]


def test_cada_chave_da_resposta_vira_o_SEU_evento():
    """🔑 Uma chave por vez: é o que pega o tipo trocado numa chamada — com as
    quatro juntas, dois tipos invertidos ainda somariam o conjunto certo."""
    for chave, tipo in (("aviso_aec", "aec"), ("aviso_estrutural", "estrutural"),
                        ("aviso_repetido", "repetido"), ("aviso_area", "area")):
        r = _envio({"job_id": "cd34ef56", chave: _RESPOSTA[chave]})
        assert _avisos(r["ev"]) == [["aviso-envio:" + tipo,
                                     {"job_id": "cd34ef56", "tela": "envio"}]], (
            chave, r["ev"])
        assert _RESPOSTA[chave]["titulo"] in r["html"], (
            "o evento saiu e o aviso %s não foi desenhado" % chave)


def test_os_quatro_juntos_contam_quatro():
    r = _envio(_RESPOSTA)
    assert sorted(e[0] for e in _avisos(r["ev"])) == [
        "aviso-envio:aec", "aviso-envio:area",
        "aviso-envio:estrutural", "aviso-envio:repetido"], r["ev"]


def test_CONTROLE_sem_a_caixa_na_tela_NAO_conta():
    """Aviso que não foi desenhado não pode entrar no denominador."""
    r = _envio(_RESPOSTA, com_caixa=False)
    assert _avisos(r["ev"]) == [], r["ev"]


def test_CONTROLE_resposta_sem_aviso_nao_inventa_evento():
    r = _envio({"job_id": "cd34ef56"})
    assert _avisos(r["ev"]) == [], r["ev"]
    # 🧪 controle do instrumento: o despacho rodou mesmo (senão "0 evento" é vazio lido como verde)
    assert any(e[0] == "upload_ok" for e in r["ev"]), (
        "o recorte do despacho parou de rodar: %r" % r["ev"])


# ── O servidor ────────────────────────────────────────────────────────────

def test_cada_evento_que_as_telas_disparam_e_GRAVADO_pelo_track(monkeypatch):
    """🩸 Duas vezes nesta casa o front disparou e o /api/track jogou fora calado
    (23/08, 9 eventos; 02/09, 5 do convite da área). Aqui os eventos não são uma
    lista escrita no teste: são os que as telas ACABARAM de disparar."""
    import main
    f = _frases_do_motor()
    disparados = _avisos(_envio(_RESPOSTA)["ev"]) + _avisos(
        _topo([f["parece-arquitetura"][0], f["estrutura-sem-medida"][0]])["ev"])
    assert len(disparados) == 6, disparados
    gravados = []
    monkeypatch.setattr(main, "_supabase_insert",
                        lambda tabela, linha: gravados.append((tabela, linha)))
    for nome, meta in disparados:
        p = main.TrackPayload(event=nome, job_id=meta.get("job_id", ""), meta=meta)
        resp = asyncio.run(main.track_event(p, None))
        assert resp == {"status": "ok"}, (nome, resp)
    assert [linha["event"] for _, linha in gravados] == [n for n, _ in disparados]
    # a TELA amarrada ao prefixo do nome: `aviso-envio:` só do envio, `aviso-topo:` só do projeto
    tela_do_prefixo = {"aviso-envio": ("envio", "cd34ef56"), "aviso-topo": ("projeto", _JOB_TOPO)}
    for _, linha in gravados:
        tela, job = tela_do_prefixo[linha["event"].split(":")[0]]
        assert linha["meta"].get("tela") == tela, linha
        assert linha["job_id"] == job, linha
