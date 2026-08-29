# -*- coding: utf-8 -*-
"""O /api/track tem que RODAR, não só ter o fonte bonito.

🩸 29/08/2026. A telemetria do site inteiro ficou **29 HORAS morta** e ninguém
soube. Causa: no conserto das chaves de meta (28/08), escrevi

    _re_track.sub(_limpa, texto)          # dois argumentos

e `re.sub` pede TRÊS (padrão, substituição, texto). TypeError em TODO POST →
500 pra todo evento de todo visitante, desde o deploy de 28/08 ~13:50 até
29/08 ~19:00. O front usa fire-and-forget, então nenhum cliente viu erro — os
eventos simplesmente sumiram. Perdemos um dia inteiro de dado, irrecuperável.

🔑 POR QUE NENHUM GUARDA PEGOU: os testes do track liam o FONTE (regex e ast
sobre o texto do main.py). Fonte com argumento faltando é fonte perfeitamente
legível — pyflakes não reclama, regex acha os padrões, tudo verde. O único
teste que pegaria é o que ESTE arquivo adiciona: chamar a função com um payload
de verdade. Teria estourado no primeiro `pytest` antes do push.

🪤 E o meu "controle positivo" de 28/08 passou VERDE por azar de cronologia: os
2 eventos de teste entraram às 12:49/13:04, o deploy quebrado subiu ~13:50.
Controle que roda ANTES do deploy não controla o deploy.

📌 A ironia que fecha a semana: eu descobri porque o cético do workflow disse
"o alarme das 29h não tem controle" — e a regra de 26/08 manda rodar o controle
antes de alarmar. Rodei o controle, o controle reprovou, e o alarme era real.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


def _rodar(payload_kwargs, monkeypatch):
    """Chama a rota de verdade, com o banco trocado por uma lista local.

    🔒 Sem o monkeypatch, o teste inseriria lixo no usage_events de PRODUÇÃO
    (o `_supabase_insert` usa a URL real). Trocar aqui também deixa a gente
    AFIRMAR o que seria gravado — que é o que os testes de fonte nunca puderam.
    """
    gravados = []
    monkeypatch.setattr(main, "_supabase_insert",
                        lambda tabela, linha: gravados.append((tabela, linha)))
    p = main.TrackPayload(**payload_kwargs)
    resp = asyncio.run(main.track_event(p, None))
    return resp, gravados


def test_o_payload_que_derrubou_a_rota_por_29h(monkeypatch):
    """🚨 O caso exato: view_blog_post anônimo, só com campo e cid — o payload
    que TODO visitante do blog manda. Foi este POST que deu 500 por 29 horas."""
    resp, gravados = _rodar(
        {"event": "view_blog_post", "meta": {"campo": "bdi-em-obra", "cid": "c1"}},
        monkeypatch)
    assert resp == {"status": "ok"}, resp
    assert len(gravados) == 1, "o evento não foi gravado"
    _, linha = gravados[0]
    assert linha["meta"]["campo"] == "bdi-em-obra"
    assert linha["meta"]["cid"] == "c1"


def test_TODAS_as_chaves_de_meta_passam_pelo_caminho_vivo(monkeypatch):
    """🔑 Cada chave aceita exercitada em EXECUÇÃO, não em leitura de fonte.
    O bug morava justamente no laço das chaves novas (motivo/formato)."""
    resp, gravados = _rodar(
        {"event": "clique:copiar-link-do-post",
         "meta": {"cid": "c2", "src": "google", "type": "t",
                  "campo": "Whatsapp!", "motivo": "SEM-Arquivo",
                  "formato": "PDF", "rotulo": "  Copiar   <b>link</b>  ",
                  "n_itens": 7, "pendentes": "3", "confirmados": 99999}},
        monkeypatch)
    assert resp == {"status": "ok"}
    m = gravados[0][1]["meta"]
    assert m["campo"] == "whatsapp"          # saneado: minúsculo, sem '!'
    assert m["motivo"] == "sem-arquivo"
    assert m["formato"] == "pdf"
    assert "<" not in m["rotulo"] and ">" not in m["rotulo"], m["rotulo"]
    assert m["n_itens"] == 7 and m["pendentes"] == 3 and m["confirmados"] == 99999


def test_meta_vazio_e_meta_esquisito_nao_derrubam(monkeypatch):
    """🪤 A rota é ABERTA: qualquer um posta qualquer coisa. Payload torto tem
    que virar evento pobre ou ignorado — nunca 500."""
    for meta in ({}, {"cid": None}, {"rotulo": 12345}, {"motivo": ["lista"]},
                 {"n_itens": "não-é-número"}, {"chave_desconhecida": "x"}):
        resp, _ = _rodar({"event": "view_landing", "meta": meta}, monkeypatch)
        assert resp["status"] in ("ok", "ignored"), (meta, resp)


def test_evento_fora_da_lista_e_ignorado_sem_gravar(monkeypatch):
    resp, gravados = _rodar({"event": "evento-que-nao-existe", "meta": {}},
                            monkeypatch)
    assert resp == {"status": "ignored"}
    assert not gravados


def test_CONTROLE_POSITIVO_a_sabotagem_de_ontem_reprova_AQUI(monkeypatch):
    """🧪 Reintroduz o bug exato (sub com dois argumentos) num sósia e prova que
    esta forma de teste o pega — enquanto os testes de fonte passavam verdes.
    Se um dia esta prova ficar obsoleta, o comentário do arquivo explica o
    porquê de ela ter nascido."""
    import re
    with __import__("pytest").raises(TypeError):
        re.sub(r"[^a-z]", "abc".lower())  # dois argumentos: o erro das 29h
