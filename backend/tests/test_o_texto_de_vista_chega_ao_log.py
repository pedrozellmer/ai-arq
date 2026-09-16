# -*- coding: utf-8 -*-
"""O que a prancha DIZ sobre ser perfil tem que CHEGAR ao log — sem dado pessoal.

🛣️ 15/09/2026 — job b445916a (pavimentação): duas linhas "confirmado" de 221 ml
saíram do comprimento de layer de um PERFIL LONGITUDINAL. Em perfil o greide é
desenhado com escala H/V própria: o comprimento da linha não é a extensão da
rua. A regra nº1 quebrou calada.

🩸 Dois detectores foram propostos e os DOIS caíram no estudo:
- o formato real do cliente, literal na resposta da IA, era
  "ESCALA : H=250.000 / V=25.000" — nenhum dos regex (feitos pra "1:N") lia;
- os dois rebaixariam caso legítimo: planta e perfil na mesma folha, nota
  "os perfis estão em H=1:1000 V=1:100", esgoto em escala única.

🔑 O acervo não guarda os textos das pranchas, então qualquer trava hoje seria
palpite. Este passo só PUBLICA em `motor:vista-texto`, sem mexer em selo.

🩸 DUAS versões deste log foram barradas por privacidade antes de subir:
- a 1ª gravava uma JANELA em volta do que casou, e o guarda dela punha 102
  caracteres de folga entre o nome e a escala — passava por sorte; 12 de 13
  carimbos realistas vazavam nome, CPF, telefone ou e-mail;
- a 2ª mascarava por lista de formato (CPF, telefone com DDD) e deixou passar
  telefone sem DDD, RG, CEP e CPF com espaço no vão entre H e V.
Os casos abaixo são exatamente esses, com dado fictício. A regra agora é
estrutural: fica literal só o token que casou; o vão vira esqueleto.

🚨 O guarda principal roda `main.process_job` DE VERDADE num DXF sintético (sem
rede, IA falsa, freio na consolidação) e olha a linha que o motor gravou — não
o fonte. Mesmo arranjo de test_medicao_do_pdf_na_observacao.py.
"""
import json
import os
import socket
import sys
import time
import types
import urllib.request

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

ezdxf = pytest.importorskip("ezdxf")

# o formato LITERAL da escala do cliente (resposta da IA na prancha 004 do b445916a)
_ESCALA_DO_CLIENTE = "ESCALA : H=250.000 / V=25.000"
_TITULO = "PERFIL LONGITUDINAL - EIXO 1"

# dado pessoal FICTÍCIO que não pode chegar ao log
_PESSOAL = ("FULANO", "FICTICIO", "BELTRANA", "FICTICIA", "PROPRIETARIO", "CLIENTE",
            "123.456.789-09", "123 456 789", "12.345.678", "12.345.678/0001-90",
            "99999", "3333-4444", "01310", "RG", "@", "FLORES")


class _T:
    def __init__(self, text):
        self.text = text


class _Extr:
    """Só o que a função lê — de propósito, pra não amarrar no DXFExtraction."""

    def __init__(self, textos=(), attrs=()):
        self.texts = [_T(t) for t in textos]
        self.block_attributes = list(attrs)


def _vista(textos=(), attrs=()):
    import main
    return main._textos_de_vista(_Extr(textos, attrs))


# ── o formato do cliente e o que é publicado ────────────────────────────────
def test_o_formato_REAL_do_cliente_e_reconhecido():
    txt = _vista([_TITULO, _ESCALA_DO_CLIENTE])
    assert "escala_hv:txt«ESCALA : H=250.000 / V=25.000»" in txt, txt
    assert "perfil:txt«PERFIL LONGITUDINAL»" in txt, txt
    assert "vista_textos=2" in txt, txt


def test_o_trecho_publicado_e_SO_o_que_casou():
    """Nada de janela em volta: é por ela que o carimbo vazava."""
    txt = _vista(["PROPRIETARIO: FULANO FICTICIO " + _ESCALA_DO_CLIENTE + " FOLHA 03/08"])
    assert txt == " vista_textos=1 escala_hv:txt«ESCALA : H=250.000 / V=25.000»", txt


@pytest.mark.parametrize("texto", [
    "ESC. H=1:250  V=1:25",
    "ESCALA HORIZONTAL 1:1000",
    "ESC. HOR. 1:1000 / VERT. 1:100",
    "EH=1:500 EV=1:50",
    "E.H. 1:500 E.V. 1:50",
    "Esc. H 1/250 - V 1/25",
    "ESC. H - 1:1000 / V - 1:100",
    "ESC. H – 1:1000 / V – 1:100",
    "HOR.: 1/1000 VER.: 1/100",
    "1:1000 (H) / 1:100 (V)",
    "ESCALA : H=1.000 / V=100",
    "ESCALA : H=1000.000 / V=100.000",
    "ESCALA : H=2000.000 / V=200.000",
    "ESC. H=1:2500 V=1:250",
    "ESC. H=1:1.000 V=1:100",
    "PERFIL PV-01 A PV-10",
    "PERFIS DAS RUAS",
    "PERFIS DOS COLETORES",
    "PERFIL COLETOR TRONCO CT-01",
    "PERFIL DA RODOVIA",
    "PERFIL TOPOGRÁFICO",
    "PERFIL DE TERRAPLENAGEM",
    "P. LONG.",
    "HOR.: 1/1000 VER.: 1/100",
    "ESCALAS:\nH=1:1000\nV=1:100",
    "ESC. H=1:1000\nESC. V=1:100",
    "H=1:500 V=1:500",
    "EXAGERO VERTICAL 10X",
    "EXAG. VERT. 10X",
    "PERFIL DA REDE COLETORA",
    "PERFIL LONG. - EIXO 01",
    "PERF. LONGITUDINAL",
    "P. LONGITUDINAL",
    "PERFIS LONGITUDINAIS",
    "PERFIL DO COLETOR",
    "PERFIL DA RUA A",
    "PERFIL - RUA PROJETADA 1",
    "PERFIL DE DRENAGEM",
    "PERFIL PV1 - PV5",
    "PERFIL: EIXO 01",
    "EIXO 1 - PERFIL LONGITUDINAL",
    "%%UPERFIL LONGITUDINAL",
    "PERFIL\\~LONGITUDINAL",
    "GREIDE DE PROJETO",
])
def test_formatos_de_perfil_e_escala_entram(texto):
    assert _vista([texto]), "formato de perfil/escala não chegou ao log: %r" % texto


def test_escala_empilhada_e_escala_unica_tem_tipo_proprio():
    assert "escala_hv:txt«ESCALAS: H=1:1000 V=1:100»" in _vista(["ESCALAS:\nH=1:1000\nV=1:100"])
    assert "escala_hv_igual:txt«H=1:500 V=1:500»" in _vista(["H=1:500 V=1:500"])
    assert "escala_h_ou_v:txt«ESC. H=1:1000»" in _vista(["ESC. H=1:1000\nESC. V=1:100"])


def test_atributo_de_bloco_do_carimbo_tambem_entra():
    txt = _vista(attrs=[{"bloco": "CARIMBO", "layer": "0",
                         "campos": {"ESCALA": "H=1:1000 V=1:100", "FOLHA": "03"}}])
    assert "escala_hv:attr«H=1:1000 V=1:100»" in txt, txt


@pytest.mark.parametrize("texto", [
    "PORTA P1 H=2,10 V=0,80",
    "JANELA J1 H=1,20 x 1,50",
    "CAIXA 40x40 H=60 V=30",
    "TOMADA H=30 V=220",
    "DUTO 40x20 H=270 V=12 m/s",
    "L1 h=12 V10 15x40",
    "LAJE h=12cm - VIGAS V10 A V20",
    "QUADRA H 12 LOTE V 15",
    # "escala" do DETALHE antes das medidas não transforma medida em escala
    "ESCALA 1:100 - CAIXA H=60 V=30",
    "DETALHE CX. ESC 1:20 H=60 V=40",
    "ESC. 1:50 JANELA H=150 V=120",
    "QUADRO DE ESQUADRIAS S/ ESC. J1 H=150 V=120",
    "ESC. 1:25 - RESERVATÓRIO H=200 V=150",
    # H e V longe um do outro: o que houver no meio não é escala (e seria carimbo)
    "H=1:1000 PROPRIETARIO FULANO FICTICIO DE TAL - FOLHA V=1:100",
    "ESCALA 1:50",
    "ESC. 1:50 - PAINEL HORIZONTAL",
    "NOTAS: ESCALA 1:50. JUNTA VERTICAL A CADA 3M",
    "PERFIL LED LINEAR 45° - EMBUTIR",
    "PERFIL U 30x30 - DRYWALL",
    "PERFIL DE ALUMÍNIO",
    "PERFILADO 38x38",
    "PERFIL PVC 25MM",
    # "VER" sem ponto é o verbo
    "ESCALA VER 1/50",
    "VER 1:20 - DETALHE H=1:50",
    # denominador que não termina onde parece terminar
    "ESC. H=1:1000000000 V=1:100",
    "PERFIL LONGARINA W150",
    "PLANTA BAIXA - TÉRREO",
    "EST=26+12.383",
])
def test_CONTROLE_texto_que_nao_e_perfil_nem_escala_fica_de_fora(texto):
    assert _vista([texto]) == "", "entrou no log sem ser perfil/escala: %r" % texto


# ── privacidade: carimbos realistas, dado fictício ──────────────────────────
@pytest.mark.parametrize("texto", [
    "PROPRIETARIO: FULANO FICTICIO " + _ESCALA_DO_CLIENTE,
    _ESCALA_DO_CLIENTE + " PROPRIETARIO: BELTRANA FICTICIA",
    "CPF 123.456.789-09\nESCALA H=1:1000 V=1:100",
    "ESC. H=1:1000 FULANO FICTICIO V=1:100",
    "ESC. H=1:1000 123.456.789-09 V=1:100",
    "ESC. H=1:1000 TEL 99999-0000 V=1:100",
    "ESC. H=1:1000 3333-4444 V=1:100",
    "ESC RG 12.345.678-9 H=1:1000 V=1:100",
    "ESCALA : H=250.000 CEP 01310-100 / V=25.000",
    "CPF 123 456 789 09 ESC. H=1:500 V=1:50",
    "ESC H 12.345.678-9 V 10",
    "ESC H 12.345.678 V 10",
    "ESC H 01310-100 V 10",
    "ESC. H=123.456 V=1:100",
    "ESC. H=1:99999-0000",
    "ESCALA HORIZONTAL 1:99999-0000",
    "ESC. H=1:500 fulano@exemplo.com V=1:50",
    # literal DEPOIS do que casou (mutantes da revisão de 15/09 passavam sem estes)
    "EXAGERO VERTICAL 10X FULANO 99999-0000",
    "PERFIL PV 99999-0000 FULANO",
    "ESC H=99999-0000 V=10",
    "ESC H=999990000 V=10",
    "ESC. H=1:1000 PROPRIETARIO FULANO FICTICIO DE TAL - FOLHA V=1:100",
    "CLIENTE: BELTRANA FICTICIA TEL (11) 99999-0000 ESC. H=1:500 V=1:50",
    "contato fulano@exemplo.com ESCALA H=1:1000 V=1:100",
    "CNPJ 12.345.678/0001-90 PERFIL LONGITUDINAL - RUA DAS FLORES",
    "PERFIL DO EIXO 99999-0000 FAZENDA DO FULANO",
    "ESCALA: INDICADA CLIENTE: BELTRANA FICTICIA TEL (11) 99999-0000 RUA DAS FLORES JUNTA HORIZONTAL",
])
def test_carimbo_com_dado_pessoal_nao_vaza_nada(texto):
    txt = _vista([texto])
    vazou = [p for p in _PESSOAL if p in txt]
    assert not vazou, "dado pessoal chegou ao log: %r em %r" % (vazou, txt)


def test_o_vao_entre_H_e_V_vira_esqueleto_e_a_escala_sobrevive():
    txt = _vista(["ESCALA : H=250.000 CEP 01310-100 / V=25.000"])
    assert "«ESCALA : H=250.000 ~ ~-~ / V=25.000»" in txt, txt
    # "|" separa os trechos na linha gravada: dentro do vão ele também vira "~"
    txt = _vista(["ESC H=1:1000 | FULANO | V=1:100"])
    assert "«ESC H=1:1000 ~ ~ ~ V=1:100»" in txt, txt


def test_ponto_de_milhar_nos_dois_lados_vira_escala_hv():
    """Lido como decimal, "H=1:2.500 V=1:1.000" daria 2,5 e 1 e o par morria
    (revisão de 15/09). Decimal só quando os dois lados saem redondos."""
    assert "escala_hv:txt«ESC. H=1:2.500 V=1:1.000»" in _vista(["ESC. H=1:2.500 V=1:1.000"])
    assert "escala_hv:txt«ESC. H=1:25.000 V=1:2.500»" in _vista(["ESC. H=1:25.000 V=1:2.500"])


@pytest.mark.parametrize("valor", [
    "CPF 123.456.789-09 ESC H=1:500 V=1:50",
    "TEL 3333-4444 ESC H=1:500 V=1:50",
])
def test_atributo_com_documento_e_escala_no_mesmo_valor_nao_vaza(valor):
    txt = _vista(attrs=[{"bloco": "CARIMBO", "layer": "0", "campos": {"OBS": valor}}])
    assert "H=1:500 V=1:50" in txt, txt
    vazou = [p for p in _PESSOAL if p in txt]
    assert not vazou, "dado pessoal chegou ao log: %r em %r" % (vazou, txt)


# ── limites e robustez ──────────────────────────────────────────────────────
def test_no_maximo_tres_trechos_e_linha_curta():
    textos = ["ESC. H=1:%d V=1:10" % (100 + i) for i in range(40)]
    txt = _vista(textos)
    assert "vista_textos=40" in txt, txt[:80]
    assert txt.count("«") == 3, txt
    assert len(txt) < 300, len(txt)


def test_texto_patologico_nao_trava_o_motor():
    """A 1ª versão levava 34 s num MTEXT de 200 KB com 'ESCALA' repetido e 59 s
    num 'H' seguido de 32 mil espaços — dentro do job, sem teto.
    🪤 O caso que PROVA o limite é o que NÃO casa no fim ('H' + espaços + '=X'):
    com quantificador sem teto o motor de regex retrocede por todas as divisões
    dos espaços. E pares densos ('H=1 V=1' repetido) provam o laço de pares.
    🪤 O `import main` fica FORA do cronômetro: sozinho ele leva ~10 s."""
    import main
    textos = (["ESCALA " * 30000, ("H" + " " * 120 + "=X ") * 12, "PERFIL " * 20000,
               "ESC " + "H=1 " * 20000]
              + ["H=1 V=1 " * 500] * 100 + ["ESC H=1 V=1 " * 330] * 50)
    extr = _Extr(textos)
    t0 = time.perf_counter()
    main._textos_de_vista(extr)
    assert time.perf_counter() - t0 < 2.0, time.perf_counter() - t0


def test_pares_densos_de_H_e_V_nao_viram_laco_quadratico():
    """🪤 MTEXT de tabela com centenas de "H=… V=…" no mesmo texto: sem o teto
    de candidatos, o pareamento testa todo H contra todo V. Medido 15/09, com a
    máquina ocupada: 300 textos assim levaram 5,9 s sem o teto e 0,4 s com ele
    (o caso patológico acima passava nos dois — a sabotagem sobreviveu).
    O preço do teto é conhecido: escala depois do 50º "H=" do MESMO texto se perde."""
    import main
    extr = _Extr(["H=1 V=1 " * 500] * 400)
    t0 = time.perf_counter()
    main._textos_de_vista(extr)
    assert time.perf_counter() - t0 < 2.0, time.perf_counter() - t0


def test_mtext_gigante_e_cortado_antes_do_regex():
    """MTEXT de 4 MB (tabela colada no desenho): sem o corte de 4.000 caracteres
    levou 2,85 s na revisão de 15/09. O caso patológico acima não pegava a falta
    do corte — cada texto dele é pequeno ou casa cedo."""
    import main
    extr = _Extr([("H" + " " * 12 + "1234567 ") * 200000])
    t0 = time.perf_counter()
    main._textos_de_vista(extr)
    assert time.perf_counter() - t0 < 1.0, time.perf_counter() - t0


def test_CONTROLE_extracao_sem_os_campos_ou_com_lixo_nao_quebra():
    """O log de geometria roda num try: se esta função explodir lá dentro, a
    linha inteira some. Prancha de caminho antigo não tem os atributos."""
    import main

    class _Velho:
        pass

    class _Lixo:
        texts = "isto não é lista de textos"
        block_attributes = [None, {"campos": None}, {"campos": {"X": None}}]

    assert main._textos_de_vista(_Velho()) == ""
    assert main._textos_de_vista(None) == ""
    assert main._textos_de_vista(_Lixo()) == ""

    class _Explode:
        def __str__(self):
            raise RuntimeError("str quebrado")

    # valor que nem vira texto não pode apagar o que as outras fontes acharam
    assert main._textos_de_vista(_Extr([_Explode(), "PERFIL LONGITUDINAL"],
                                       [{"campos": {"X": _Explode()}}])) == \
        " vista_textos=1 perfil:txt«PERFIL LONGITUDINAL»"


def test_o_stage_e_diagnostico_e_nao_erro():
    """Fora da lista, cada prancha de perfil acenderia um erro falso no painel."""
    import main
    assert "motor:vista-texto" in main._STAGES_DIAGNOSTICO


# ── o motor GRAVA de verdade ────────────────────────────────────────────────
def _perfil_dxf(path, textos, carimbo=None):
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    greide = [(0, 36.7), (40, 35.5), (120, 33.1), (200, 40.0)]
    msp.add_lwpolyline(greide, dxfattribs={"layer": "PROJETO"})
    msp.add_lwpolyline([(x, y - 3.5) for x, y in greide], dxfattribs={"layer": "PAVIMENTO"})
    for e in range(0, 11):
        msp.add_text("EST=%d+0.000" % e,
                     dxfattribs={"layer": "F-VT-TEXTO", "insert": (e * 20, 15), "height": 1.5})
    for i, t in enumerate(textos):
        msp.add_text(t, dxfattribs={"layer": "F1-VT-TITULO", "insert": (40, 90 - 5 * i),
                                    "height": 2})
    if carimbo:
        msp.add_mtext(carimbo, dxfattribs={"layer": "CARIMBO", "insert": (150, 10),
                                           "char_height": 1.5})
    doc.saveas(path)


def _rodar_motor(monkeypatch, tmp_path, textos, nome, carimbo=None):
    """Roda `process_job` num DXF sintético e devolve as linhas `motor:vista-texto`."""
    import llm_retry
    import main

    dxf = str(tmp_path / nome)
    _perfil_dxf(dxf, textos, carimbo)
    logs = []

    def _sem_rede(*a, **k):
        raise OSError("rede bloqueada no guarda")

    class _Resp:
        def __init__(self, corpo):
            self._corpo = corpo

        def read(self, *a):
            return self._corpo

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _JobsMudo:
        def update_field(self, *a, **k):
            pass

    class _Parou(BaseException):
        """BaseException de propósito: `process_job` engole `Exception`."""

    item = {"item_num": "1", "description": "Pavimentação — greide de projeto", "unit": "ml",
            "quantity": 200.0,
            "observations": "Fonte: comprimento do layer 'PROJETO' = 200.00 m.",
            "discipline": "Complementares", "confidence": "estimado"}

    def _ia_falsa(client, **kw):
        corpo = "```json\n" + json.dumps({"project_data": {}, "items": [item]},
                                         ensure_ascii=False) + "\n```"
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(text=corpo)], stop_reason="end_turn",
            usage=types.SimpleNamespace(output_tokens=10, input_tokens=10))

    def _freia(itens):
        raise _Parou()

    monkeypatch.setattr(socket.socket, "connect", _sem_rede)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp(json.dumps(
        [{"auto_resume_count": 0, "reprocess_count": 0}]).encode("utf-8")))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-guarda-local")
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, message, *a, **k: logs.append((stage, str(message))))
    monkeypatch.setattr(main, "_supabase_update", lambda *a, **k: None)
    monkeypatch.setattr(main, "_projeto_patch", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_storage_upload_prancha", lambda *a, **k: True)
    monkeypatch.setattr(main, "_consolidate_items", _freia)
    monkeypatch.setattr(main, "jobs", _JobsMudo())
    # extração no próprio processo: o log fica no process_job, depois dela
    monkeypatch.setattr(main, "_extract_dxf_isolated",
                        lambda p, u, timeout_s=900, job_id="": main._extract_dxf_inprocess(p, u, job_id))
    monkeypatch.setattr(llm_retry, "call_with_retry_stream", _ia_falsa)
    try:
        main.process_job("guarda-vista-texto", [dxf], str(tmp_path), project_type="arquitetura")
    except _Parou:
        pass
    assert any(st == "motor:geometria" for st, _ in logs), (
        "o motor não chegou no log de geometria — o arranjo não rodou a extração, então "
        "este guarda não mediu nada: %r" % [s for s, _ in logs][:25])
    return [msg for st, msg in logs if st == "motor:vista-texto"]


def test_o_motor_GRAVA_o_perfil_no_log_sem_o_carimbo(monkeypatch, tmp_path):
    carimbo = ("PROPRIETARIO: FULANO FICTICIO\\PCPF 123.456.789-09\\P"
               "TEL (11) 99999-0000\\P" + _ESCALA_DO_CLIENTE)
    linhas = _rodar_motor(monkeypatch, tmp_path,
                          [_TITULO, "ESC. H=1:1000 TEL 99999-0000 V=1:100"],
                          "MD-XX-003-PAV_PER-R01_guarda.dxf", carimbo=carimbo)
    assert len(linhas) == 1, linhas
    assert "arq=" in linhas[0] and "PAV_PER-R01_guarda" in linhas[0], linhas[0]
    assert "H=250.000 / V=25.000" in linhas[0] and "PERFIL LONGITUDINAL" in linhas[0], linhas[0]
    assert "H=1:1000 ~ ~-~ V=1:100" in linhas[0], linhas[0]
    vazou = [p for p in _PESSOAL if p in linhas[0]]
    assert not vazou, "o motor gravou dado pessoal do carimbo: %r em %r" % (vazou, linhas[0])


def test_CONTROLE_planta_sem_perfil_nao_grava_a_linha(monkeypatch, tmp_path):
    linhas = _rodar_motor(monkeypatch, tmp_path,
                          ["PLANTA BAIXA - TÉRREO", "ESCALA 1:50", "PORTA P1 H=2,10 V=0,80",
                           "CAIXA 40x40 H=60 V=30", "ESCALA 1:100 - CAIXA H=60 V=30",
                           "PERFIL LED LINEAR 45°"],
                          "ARQ-PLANTA-BAIXA_guarda.dxf")
    assert linhas == [], linhas
