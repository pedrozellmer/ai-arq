# -*- coding: utf-8 -*-
"""O campo que mais muda a planilha só podia ser informado ANTES — e no upload
o cliente ainda não viu o problema.

🎯 26/08/2026. A rota `/api/project/{job}/inform-area` existe desde o caso
cliente-21: o cliente informa DEPOIS do processamento e a planilha é refeita na
hora, sem reprocessar e sem custo de IA. Só que ela aceitava **apenas a ÁREA** —
e a própria docstring dela sempre disse: *"itens que não escalam com piso
(pintura de parede, rodapé) NÃO são preenchidos"*.

Medido em 45 dias, % de linhas de área/comprimento que saem EM BRANCO:

    não informou nada .......... 93 projetos, 1.767 itens ... 59,5%
    informou só a ÁREA .......... 7 projetos,   177 itens ... 64,4%   <- não ajuda
    informou só o PÉ-DIREITO .... 5 projetos,    33 itens ... 27,3%
    informou os dois ............ 5 projetos,    72 itens ... 29,2%

**O pé-direito corta a linha em branco pela metade. A área sozinha não muda
nada** — e isso é o controle: não é só "cliente engajado preenche campo".
Mesmo assim, o mecanismo pós-fato existia para a área e não para o pé-direito.

🔑 POR QUE ISSO IMPORTA: a verdade de campo (96 correções de 6 clientes reais,
3 semanas) diz que **87% do que o cliente corrige é PREENCHER linha zerada**,
não consertar número errado. Ver [[project_verdade_de_campo_20260826]].

🔑 E POR QUE DEPOIS É MELHOR QUE ANTES: no upload ele ainda não viu o problema.
Na tela do projeto ele está olhando a linha em branco.

Alvo medido no acervo (134 projetos concluídos):
    44 com pintura de parede em branco
    15 mostrariam o convite (têm parede MEDIDA — dá pra completar)
    29 ficam calados (pintura vazia mas sem parede medida — pedir não resolve)
    10 já informaram
Os 15 guardam 38.223 m de parede medida.
"""
import io
import json
import os
import sys
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)

import main  # noqa: E402


def _corpo(caminho):
    txt = io.open(caminho, encoding="utf-8").read()
    return chr(10).join(l for l in txt.split(chr(10))
                        if not l.strip().startswith(("#", "//")))


_MAIN = _corpo(os.path.join(_BACKEND, "main.py"))
_PROJ = io.open(os.path.join(_RAIZ, "projeto.html"), encoding="utf-8").read()


# ══════════════════════════════════════════════════════════════════════════
#  BANCADA QUE EXECUTA A ROTA
#
#  🚨 06/09/2026 — POR QUE ISTO EXISTE. Os quatro guardas críticos deste
#  arquivo liam o FONTE de `main.py` e afirmavam por string. Provado cego:
#  trocando `pe_dir = round(float(payload.pe_direito or 0), 2)` por
#  `pe_dir = 0 * round(...)` — com o campo `pe_direito: float = 0` ainda
#  declarado no payload e a chamada de `_derive_pintura_pe_direito` ainda
#  ESCRITA na rota — os quatro seguiam verdes enquanto o pé-direito informado
#  era jogado fora: não derivava pintura, não era gravado e não virava aviso.
#  Agora a rota RODA de verdade; só rede, banco e disco são dublados.
# ══════════════════════════════════════════════════════════════════════════
JOB = "job-pe-direito-01"


class _RespRPC:
    """Resposta mínima de `urllib.request.urlopen` — a rota lê os itens pela
    RPC `list_project_items` com urlopen DIRETO, sem passar por helper."""

    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _linhas_do_caso():
    """O caso real: parede MEDIDA em metro linear + pintura de parede ZERADA.

    É a situação dos 15 projetos do acervo que mostrariam o convite — a linha
    em branco que o pé-direito fecha (Σ comprimento × altura × 2 faces)."""
    return [
        {"item_num": "1.1",
         "description": "Parede de alvenaria de blocos ceramicos e=14cm",
         "unit": "m", "quantity": 100.0, "confidence": "confirmado",
         "observations": "Fonte: comprimento total do layer A-WALL = 100,00 m",
         "ref_sheet": "PRANCHA-01", "origem": "cad", "discipline": "Arquitetura"},
        {"item_num": "1.2",
         "description": "Pintura latex acrilica em paredes internas",
         "unit": "m2", "quantity": 0.0, "confidence": "estimado",
         "observations": "requer pe-direito", "ref_sheet": "", "origem": "",
         "discipline": "Arquitetura"},
        {"item_num": "1.3", "description": "Piso em porcelanato esmaltado",
         "unit": "m2", "quantity": 0.0, "confidence": "estimado",
         "observations": "", "ref_sheet": "", "origem": "",
         "discipline": "Arquitetura"},
    ]


def _projeto_com_area_medida():
    return {"job_id": JOB, "project_name": "Projeto cliente-NN",
            "typology": "office", "total_area": 300.0,
            "total_area_source": "medido", "warnings": [], "user_pe_direito": 0,
            "layout_area": 0, "address": "", "user_total_area": 0}


def _bancada(monkeypatch, tmp_path, proj=None, rows=None):
    """Liga a rota REAL. Devolve o registrador do que ela produziu:
    `planilha` (ProjectData + itens que vão pro .xlsx), `persist` (itens
    regravados), `update` (patch de `projects`), `patch` (`_projeto_patch`)."""
    proj = _projeto_com_area_medida() if proj is None else proj
    rows = _linhas_do_caso() if rows is None else rows
    reg = {"planilha": [], "persist": [], "update": [], "patch": [], "log": []}

    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: None)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job=None, **k: reg["log"].append((stage, msg)))
    monkeypatch.setattr(main, "_supa_rest_as_user", lambda *a, **k: (200, [dict(proj)]))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _RespRPC(rows))
    import spreadsheet
    monkeypatch.setattr(
        spreadsheet, "generate_spreadsheet",
        lambda pd, items, path, **k: (reg["planilha"].append((pd, list(items))),
                                      io.open(path, "wb").write(b"xlsx"))[0])
    monkeypatch.setattr(main, "_supabase_storage_upload", lambda *a, **k: True)
    monkeypatch.setattr(
        main, "_persist_items_to_supabase",
        lambda job, items: (reg["persist"].append(list(items)), len(items))[1])
    monkeypatch.setattr(main, "_carimbar_planilha", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_update",
                        lambda t, f, v, data: reg["update"].append(dict(data)))
    monkeypatch.setattr(main, "_projeto_patch",
                        lambda job, campos: (reg["patch"].append(dict(campos)), True)[1])
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path))
    return reg


def _informar(monkeypatch, tmp_path, area=0, pe=0, proj=None, rows=None):
    reg = _bancada(monkeypatch, tmp_path, proj=proj, rows=rows)
    r = main.inform_project_area(
        JOB, main.InformAreaPayload(area=area, pe_direito=pe), request=None)
    return r, reg


def _item(items, pedaco):
    return next(i for i in items if pedaco in (i.description or "").lower())


def test_a_rota_aceita_o_pe_direito(monkeypatch, tmp_path):
    """🪤 ACEITAR NÃO É USAR. O campo pode estar declarado no payload e a rota
    jogar o valor fora: o cliente digita 2,70, recebe 200 OK e nada acontece.
    Aqui o pé-direito informado tem que CHEGAR nos três lugares onde ele vale:
    a resposta, o que é gravado no projeto e o aviso que a tela lê."""
    r, reg = _informar(monkeypatch, tmp_path, area=200, pe=2.7)

    assert r["pe_direito"] == 2.7, (
        "a rota aceitou o pé-direito e devolveu %r — o valor informado foi "
        "jogado fora no caminho" % (r["pe_direito"],))
    gravado = [p for p in reg["patch"] if "user_pe_direito" in p]
    assert gravado and gravado[0]["user_pe_direito"] == 2.7, (
        "o pé-direito não foi gravado por `_projeto_patch` (veio %r) — some no "
        "próximo reprocesso e a pintura desaparece de novo" % (reg["patch"],))
    avisos = " | ".join(reg["update"][0]["warnings"]) if reg["update"] else ""
    assert "Pé-direito de 2,70 m" in avisos.replace(".", ","), (
        "o pé-direito informado não virou aviso no projeto — a trava da tela "
        "lê essa frase e o convite passa a aparecer pra quem já informou. "
        "Avisos escritos: %r" % (avisos,))


def test_area_deixou_de_ser_obrigatoria(monkeypatch, tmp_path):
    """Informar SÓ o pé-direito tem que passar.

    🪤 A versão antiga procurava a string `"Informe a área total (m²) ou o
    pé-direito (m)."` no fonte. Ela continua lá mesmo quando o pé-direito é
    descartado antes da validação — e aí é justamente ESSA mensagem que o
    cliente leva na cara, com o guarda verde."""
    r, _ = _informar(monkeypatch, tmp_path, area=0, pe=2.7)
    assert r["status"] == "ok" and r["pe_direito"] == 2.7, (
        "quem informa só o pé-direito não conseguiu concluir: %r" % (r,))


def test_so_a_area_tambem_continua_passando(monkeypatch, tmp_path):
    """Controle do guarda de cima: a porta velha (só área) não pode fechar."""
    r, _ = _informar(monkeypatch, tmp_path, area=200, pe=0,
                     proj=dict(_projeto_com_area_medida(), total_area=0,
                               total_area_source=""))
    assert r["status"] == "ok" and r["area"] == 200


def test_vazio_dos_dois_lados_continua_recusado(monkeypatch, tmp_path):
    """🚨 CONTROLE POSITIVO. Sem isto, um guarda que só exige 200 OK ficaria
    verde se a validação inteira sumisse."""
    _bancada(monkeypatch, tmp_path)
    with pytest.raises(main.HTTPException) as e:
        main.inform_project_area(
            JOB, main.InformAreaPayload(area=0, pe_direito=0), request=None)
    assert e.value.status_code == 400


def test_pe_direito_fora_da_faixa_e_recusado():
    """🚨 Um pé-direito errado multiplica a pintura INTEIRA.

    Mesma faixa do campo do upload (1,8 a 8 m). Digitar 27 no lugar de 2,7 daria
    uma pintura 10× maior com a conta escrita parecendo legítima.
    """
    assert "1.8 <= pe_dir <= 8" in _MAIN, (
        "a faixa do pé-direito sumiu — 27 m viraria pintura 10× maior")


def test_a_derivacao_da_pintura_e_CHAMADA_na_rota(monkeypatch, tmp_path):
    """🪤 Guarda de CALL SITE. A derivação já existia e essa rota nunca a
    chamava — era exatamente o buraco.

    🚨 A versão antiga só conferia que `_derive_pintura_pe_direito(items` estava
    ESCRITO no trecho da rota. Basta o `if _pd_efetivo > 0:` ficar falso (o
    pé-direito descartado antes) pra chamada virar código morto: o guarda segue
    verde e a rota volta a salvar deixando a linha em branco. Agora a prova é a
    LINHA: 100 m de parede × 2,70 m × 2 faces = 540 m².
    """
    r, reg = _informar(monkeypatch, tmp_path, area=200, pe=2.7)

    assert r["pintura_derivada"] == 1, (
        "a rota não derivou a pintura (pintura_derivada=%r) — o cliente "
        "informa o pé-direito e a linha continua em branco, que é o defeito "
        "de origem" % (r["pintura_derivada"],))
    pintura = _item(reg["persist"][0], "pintura")
    assert abs(pintura.quantity - 540.0) < 1.0, (
        "a linha de pintura foi regravada com %r m² — esperava 540 m² "
        "(100 m de parede × 2,70 m × 2 faces)" % (pintura.quantity,))
    # 🚫 Regra nº1: conta escrita e nunca 'confirmado'.
    assert str(getattr(pintura.confidence, "value", pintura.confidence)) == "estimado"
    assert "2.70" in (pintura.observations or "") or "2,70" in (pintura.observations or ""), (
        "a observação não mostra a conta com o pé-direito informado: %r"
        % (pintura.observations,))
    # E a mesma linha tem que chegar na PLANILHA, não só no banco.
    assert abs(_item(reg["planilha"][0][1], "pintura").quantity - 540.0) < 1.0


def test_informar_SO_o_pe_direito_nao_apaga_a_area_medida(monkeypatch, tmp_path):
    """🚨 Regra nº1: trocar medição por rótulo de estimativa sem pedir.

    Se `area` vem 0, a área que o projeto já tinha não pode virar 0 nem ser
    marcada como 'informado por você'.

    🪤 A versão antiga procurava três âncoras no fonte (`_area_ja_tinha`,
    `if area > 0:`, `pd.total_area_source = "informado"`). Todas continuam na
    janela mesmo depois de trocar o `else` por `= "informado"` e o
    `total_area=(area or _area_ja_tinha)` por `total_area=area`: a área MEDIDA
    pela planta era zerada e carimbada "informado por você", com o guarda verde.
    Agora a prova é o ProjectData que vai pra CAPA da planilha entregue.
    """
    _, reg = _informar(monkeypatch, tmp_path, area=0, pe=2.7)
    pd, _itens = reg["planilha"][0]

    assert pd.total_area == 300.0, (
        "a área que a planta mediu virou %r na capa da planilha só porque o "
        "cliente informou a altura" % (pd.total_area,))
    assert pd.total_area_source != "informado", (
        "área MEDIDA carimbada 'informado por você' sem o cliente ter "
        "informado área nenhuma — regra dura nº1")
    assert pd.total_area_source == "medido", (
        "a procedência da área medida foi perdida: %r" % (pd.total_area_source,))
    assert "total_area" not in (reg["update"][0] if reg["update"] else {}), (
        "a rota regravou `total_area` num fluxo onde o cliente não informou área")


def test_o_pe_direito_e_PERSISTIDO_no_projeto():
    """🪤 Mesma armadilha do `user_total_area`: campo que não existe na RPC
    `update_project_status` é descartado em SILÊNCIO. Sem gravar, um reprocesso
    futuro perde o pé-direito e a pintura some de novo."""
    i = _MAIN.find("def inform_project_area")
    t = _MAIN[i:i + 9000]
    assert '"user_pe_direito"' in t and "_projeto_patch" in t, (
        "o pé-direito informado não é gravado por `_projeto_patch` — some no "
        "próximo reprocesso")


def test_o_convite_da_tela_nao_pergunta_o_que_nao_resolve():
    """🚨 A 3ª condição é a que separa 'dá pra completar' de 'pedir por pedir'.

    Medido: das 44 telas com pintura em branco, 29 NÃO têm parede medida em
    metro linear. Nessas, informar a altura não completa nada — e pedir dado
    que não resolve queima a confiança do cliente.
    """
    assert "function maybeShowPeDireitoPrompt" in _PROJ, "o convite sumiu"
    i = _PROJ.find("function maybeShowPeDireitoPrompt")
    t = _PROJ[i:i + 1800]
    # 🪤 A 1ª versão deste teste só procurava a PALAVRA `paredeMedida` — e a
    # declaração da variável continuava lá mesmo com o `return` removido, então
    # a sabotagem passou VERDE. Procurar o identificador não é conferir a
    # decisão: o que tem que existir é o `return`.
    assert "if (!paredeMedida) return;" in t, (
        "o convite parou de SAIR quando não há parede medida — apareceria nos "
        "29 projetos onde informar a altura não completa nada")
    assert "if (!pinturaVazia) return;" in t, (
        "parou de sair quando a pintura já tem número")
    assert "'teto'" in t and "'forro'" in t, (
        "parou de excluir teto/forro: a conta comprimento × altura é de PAREDE")


def test_a_trava_de_ja_informou_le_um_campo_que_EXISTE():
    """🪤 A ARMADILHA QUE QUASE PASSOU. A RPC `list_user_projects` NÃO devolve
    `user_pe_direito` (conferido no banco em 26/08: devolve job_id,
    project_name, typology, status, total_area, warnings, …).

    Ler o campo inexistente dá `undefined`, a trava nunca fecha, e o convite
    aparece pra quem já informou. Guarda que sempre passa é pior que guarda
    nenhum — é o mesmo erro do `hover:` que eu contei errado em 24/08.
    """
    i = _PROJ.find("function maybeShowPeDireitoPrompt")
    t = _PROJ[i:i + 1800]
    assert "proj.user_pe_direito" not in t, (
        "a trava voltou a ler `proj.user_pe_direito`, que a RPC não devolve — "
        "sempre undefined, sempre passa")
    assert "proj.warnings" in t and "pé-direito de" in t.lower(), (
        "a trava não lê o aviso, que é o único sinal que a RPC entrega")


def test_o_backend_escreve_o_aviso_que_a_tela_le():
    """As duas pontas: se o backend parar de escrever a frase, a trava da tela
    deixa de funcionar em silêncio."""
    assert "INFORMADO POR VOCÊ" in _MAIN
    i = _MAIN.find("def inform_project_area")
    t = _MAIN[i:i + 9000]
    assert "Pé-direito de" in t, (
        "o backend parou de escrever o aviso do pé-direito nos warnings — a "
        "trava da tela lê essa frase e vai passar a mostrar o convite sempre")


def test_o_caminho_da_AREA_continua_igual():
    """Regressão: o caso cliente-21 não pode quebrar."""
    i = _MAIN.find("def inform_project_area")
    t = _MAIN[i:i + 9000]
    assert "_apply_area_honesty(" in t and "apenas_preencher=True" in t, (
        "o preenchimento por área informada mudou de forma")
    assert '"user_total_area"' in t, "parou de gravar a área informada"


def test_o_log_conta_o_que_aconteceu():
    assert '"motor:informou-depois"' in _MAIN, (
        "informar depois não deixa rastro — não dá pra saber se o convite novo "
        "está sendo usado nem se ele completa alguma coisa")
    assert '"motor:informou-depois",' in _MAIN[:_MAIN.find("async def")], (
        "o stage não foi registrado na lista de stages conhecidos do log")
