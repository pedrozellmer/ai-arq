# -*- coding: utf-8 -*-
"""O aviso "estas pranchas já passaram por aqui" conta ARQUIVO, e só dá o
conselho que vale pro tipo das pranchas.

🩸 22/09/2026 — job ee801b82 (tipo estrutura, 7 PDFs de uma página de concreto
armado: poços, caixa de válvulas, bloco de guindaste, um pórtico) e, no dia
seguinte, job f8d8e6d8 com os MESMOS 7 arquivos (sha256 idêntico), criado como
arquitetura porque o anexo foi recusado e o dashboard caiu no upload normal.

O aviso do envio disse "5 dos 7 arquivos deste envio são os mesmos". Eram 7 de
7. A conta era feita pelos `ref_sheet` dos ITENS do projeto anterior, e 2 das 7
pranchas não tinham gerado item nenhum (a resposta da IA veio num formato que
o parser não pega). Prancha sem item não existia pra conta.

E o conselho era o da arquitetura — "informe o PÉ-DIREITO (parede, pintura e
rodapé)", "informe a ÁREA TOTAL (piso, forro e laje)" — pra pranchas de
estrutura. 📏 Medido em 22/09 (90 d, sem eval): em estrutura, pé-direito
informado nunca preencheu linha, e área informada preencheu 0 linhas em 4 jobs.

📏 Alcance do número: em 90 dias o aviso saiu 1 vez — este caso —, e o número
estava errado. Na mesma janela, 5 reenvios de caderno repetido (pela lista do
Storage); a conta pelos itens teria perdido 1 (um DXF de estrutura com todas as
linhas num `ref_sheet` só) e errado o número de outro.

Os testes RODAM `_projeto_ja_enviado` e a rota de upload; banco e Storage são
dublados.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

#: os 7 arquivos do caso, com nome neutro
_SETE = ["prancha-%s.pdf" % letra for letra in "ABCDEFG"]
_ANTERIOR = "ee801b82"


def _banco(monkeypatch, storage, refs, tipo="estrutura", pd=None, area=None,
           files_count=7):
    """`storage` = o que a lista do Storage devolve (None = não consegui
    listar); `refs` = os `ref_sheet` dos itens do projeto anterior;
    `files_count` = quantos arquivos o projeto anterior recebeu."""
    chamadas = []

    def _rows(metodo, caminho, **k):
        chamadas.append(caminho)
        if caminho.startswith("/projects?"):
            return [{"job_id": _ANTERIOR, "project_name": "Projeto cliente-nn",
                     "created_at": "2026-09-21T20:07:31Z", "project_type": tipo,
                     "user_pe_direito": pd, "user_total_area": area,
                     "files_count": files_count}]
        if caminho.startswith("/project_items?"):
            return [{"ref_sheet": r} for r in refs]
        return []

    def _lista(job_id, **k):
        chamadas.append("storage:" + job_id)
        if storage is None:
            return None
        return [("%s" % n, 1000 + i) for i, n in enumerate(storage)]
    monkeypatch.setattr(main, "_supa_rows", _rows)
    monkeypatch.setattr(main, "_pranchas_com_tamanho", _lista)
    return chamadas


#: no projeto anterior só 5 das 7 pranchas geraram item — DE-004 e DE-006 do
#: caso, aqui prancha-D e prancha-F —, e cada item carrega o hint da IA.
_REFS_SEM_D_E_F = ["%s (VISTA %d – PLANTA)" % (n, i)
                   for i, n in enumerate(_SETE) if n not in ("prancha-D.pdf", "prancha-F.pdf")]


# ── a conta ─────────────────────────────────────────────────────────────────
def test_o_caso_7_de_7_pela_lista_do_storage(monkeypatch):
    """🩸 O caso: a conta pelos itens dava 5; os arquivos eram 7 de 7."""
    chamadas = _banco(monkeypatch, _SETE, _REFS_SEM_D_E_F)
    r = main._projeto_ja_enviado("u1", set(_SETE), 0, 0)
    assert "storage:" + _ANTERIOR in chamadas, "a lista do Storage nem foi pedida"
    assert r and r["n_iguais"] == 7 and r["n_novos"] == 7, (
        "o aviso contou as pranchas pelos itens, não pelos arquivos: %r" % r)
    assert r["contagem_exata"] is True


def test_CONTROLE_pelos_itens_a_conta_e_5_e_nao_se_diz_exata(monkeypatch):
    """🧪 O mesmo projeto com o Storage MUDO: a conta cai nos itens, dá 5, e a
    função diz que não é exata — o texto vai dizer "pelo menos"."""
    _banco(monkeypatch, None, _REFS_SEM_D_E_F)
    r = main._projeto_ja_enviado("u1", set(_SETE), 0, 0)
    assert r and r["n_iguais"] == 5, r
    assert r["contagem_exata"] is False


def test_storage_vazio_nao_vira_zero_arquivos(monkeypatch):
    """🪤 Lista vazia (arquivo que a retenção apagou) não é "o projeto não tinha
    nada": cai na conta pelos itens em vez de calar o aviso."""
    _banco(monkeypatch, [], _REFS_SEM_D_E_F)
    r = main._projeto_ja_enviado("u1", set(_SETE), 0, 0)
    assert r and r["n_iguais"] == 5 and r["contagem_exata"] is False, r


def test_o_storage_so_conta_desenho(monkeypatch):
    """Miniatura e pasta no mesmo prefixo não são arquivo do cliente: um
    prefixo só com eles não é "lista exata" — cai na conta pelos itens."""
    _banco(monkeypatch, ["_thumbs", "prancha-A.png"], _REFS_SEM_D_E_F)
    r = main._projeto_ja_enviado("u1", set(_SETE), 0, 0)
    assert r and r["n_iguais"] == 5 and r["contagem_exata"] is False, r
    # 🪤 22/09 (revisão): com a régua do `files_count`, miniatura contada como
    # desenho completaria a conta — 5 desenhos + 2 miniaturas "cobririam" os 7
    # e o Storage parcial viraria exato
    so_ate_e = [n for n in _SETE if n[-5] in "ABCDE"]
    _banco(monkeypatch, so_ate_e + ["_thumbs", "prancha-F.png"], _REFS_SEM_D_E_F)
    r = main._projeto_ja_enviado("u1", set(_SETE), 0, 0)
    assert r and r["contagem_exata"] is False, r


def test_storage_PARCIAL_nao_e_conta_exata(monkeypatch):
    """🩸 22/09/2026 (revisão): o upload ao Storage é best-effort, e uma lista
    PARCIAL era tratada como exata — o texto afirmaria "5 dos 7". 📏 90 d: 2 de
    165 projetos concluídos têm menos desenho no Storage que `files_count`.
    Aqui o Storage perdeu F e G e os itens perderam D e F: juntos, os dois
    pisos dão 6 — e o texto diz "pelo menos"."""
    so_ate_e = [n for n in _SETE if n[-5] in "ABCDE"]
    _banco(monkeypatch, so_ate_e, _REFS_SEM_D_E_F, files_count=7)
    r = main._projeto_ja_enviado("u1", set(_SETE), 0, 0)
    assert r and r["contagem_exata"] is False, r
    assert r["n_iguais"] == 6, "não juntou o Storage parcial com os itens: %r" % r


def test_CONTROLE_storage_que_cobre_o_envio_e_exato(monkeypatch):
    """🧪 A lista que cobre o `files_count` (ou passa dele — anexo no mesmo
    prefixo) continua sendo a conta exata."""
    _banco(monkeypatch, _SETE + ["anexo.pdf"], _REFS_SEM_D_E_F, files_count=7)
    r = main._projeto_ja_enviado("u1", set(_SETE), 0, 0)
    assert r and r["contagem_exata"] is True and r["n_iguais"] == 7, r


def test_CONTROLE_caderno_diferente_continua_sem_aviso(monkeypatch):
    _banco(monkeypatch, _SETE, _REFS_SEM_D_E_F)
    outros = {"casa-%d.pdf" % i for i in range(7)}
    assert main._projeto_ja_enviado("u1", outros, 0, 0) is None


# ── o texto, pela rota de upload de verdade ─────────────────────────────────
class _Upload(object):
    def __init__(self, filename):
        self.filename = filename
        self._c = b"%PDF-1.4 prancha de mentira\n"
        self.size = len(self._c)
        self._i = 0

    async def seek(self, n):
        self._i = n

    async def read(self, n=-1):
        if n is None or n < 0:
            n = len(self._c) - self._i
        pedaco = self._c[self._i:self._i + n]
        self._i += len(pedaco)
        return pedaco


class _ReqUpload(object):
    headers = {}
    client = None


def _envia(monkeypatch, tmp_path, tipo_agora, pd=0, area=0):
    """Roda o /api/process de verdade e devolve o aviso de reenvio."""
    import asyncio
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda req, tolerante=False, **k: {"id": "u1",
                                                           "email": "cliente-nn@example.com"})
    monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: True)
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: None)
    monkeypatch.setattr(main, "_process_job_throttled", lambda *a, **k: None)
    monkeypatch.setattr(main, "_notify_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_ENVIOS_RECENTES", {})
    resp = asyncio.run(main.process_files(
        _ReqUpload(), None, files=[_Upload(n) for n in _SETE],
        sheet_types=[], sheet_ambientes=[],
        project_name="cliente-nn", user_id="u1", user_email="cliente-nn@example.com",
        user_total_area=area, user_pe_direito=pd, project_type=tipo_agora))
    av = resp.get("aviso_repetido")
    assert av, "o aviso de reenvio não saiu: %r" % sorted(resp)
    return av["texto"]


def test_o_caso_o_texto_afirma_7_de_7_e_nao_da_conselho_de_arquitetura(
        monkeypatch, tmp_path):
    """🩸 O envio de 22/09: pranchas de ESTRUTURA reenviadas em modo
    arquitetura. O texto diz o número certo, aponta a troca de tipo e não
    manda informar pé-direito nem área, que não mudam nada aqui."""
    _banco(monkeypatch, _SETE, _REFS_SEM_D_E_F, tipo="estrutura")
    texto = _envia(monkeypatch, tmp_path, "arquitetura")
    assert texto.startswith("7 dos 7 arquivos"), texto
    assert "ESTRUTURA" in texto and "ARQUITETURA" in texto, (
        "o aviso não disse que da outra vez as pranchas foram lidas como "
        "estrutura: %r" % texto)
    assert "PÉ-DIREITO" not in texto and "ÁREA TOTAL" not in texto, (
        "conselho de arquitetura pra prancha de estrutura: %r" % texto)
    assert "DXF" in texto and "comprimento de PDF" not in texto, texto
    # 🩸 22/09 (revisão): com o tipo trocado, "mandar de novo não muda o
    # motivo" é falso na direção de correção — e o texto tem que dizer como
    # consertar sem reenviar
    assert "não muda o motivo" not in texto, texto
    assert "Reprocessar escolhendo o tipo certo" in texto, texto


def test_CONTROLE_sem_troca_de_tipo_o_aviso_diz_que_nao_muda_o_motivo(
        monkeypatch, tmp_path):
    """🧪 O mesmo caderno, no mesmo tipo: aí sim a causa das linhas em branco
    é a mesma, e o aviso diz isso."""
    _banco(monkeypatch, _SETE, _REFS_SEM_D_E_F, tipo="arquitetura")
    texto = _envia(monkeypatch, tmp_path, "arquitetura")
    assert "não muda o motivo" in texto and "Reprocessar" not in texto, texto


def test_em_projeto_estrutura_so_o_conselho_que_vale(monkeypatch, tmp_path):
    """Reenvio em estrutura, de pranchas lidas como estrutura: sem troca de
    tipo pra apontar, e o único conselho que vale em só-PDF é o CAD."""
    _banco(monkeypatch, _SETE, _REFS_SEM_D_E_F, tipo="estrutura")
    texto = _envia(monkeypatch, tmp_path, "estrutura")
    assert "PÉ-DIREITO" not in texto and "ÁREA TOTAL" not in texto, texto
    assert "da outra vez" not in texto, texto
    assert "DXF" in texto and "não vira quantidade medida" in texto, texto


def test_CONTROLE_em_arquitetura_o_conselho_de_arquitetura_continua(
        monkeypatch, tmp_path):
    """🧪 O outro lado: caderno de arquitetura reenviado em arquitetura segue
    recebendo as três alavancas — o conserto não pode calar o aviso."""
    _banco(monkeypatch, _SETE, _REFS_SEM_D_E_F, tipo="arquitetura")
    texto = _envia(monkeypatch, tmp_path, "arquitetura")
    for alavanca in ("PÉ-DIREITO", "ÁREA TOTAL", "DXF"):
        assert alavanca in texto, (alavanca, texto)
    assert "da outra vez" not in texto, texto


def test_sem_conta_exata_o_texto_diz_pelo_menos(monkeypatch, tmp_path):
    """Sem a lista do Storage o número é piso — e o texto diz isso."""
    _banco(monkeypatch, None, _REFS_SEM_D_E_F, tipo="estrutura")
    texto = _envia(monkeypatch, tmp_path, "estrutura")
    assert texto.startswith("Pelo menos 5 dos 7 arquivos"), texto
