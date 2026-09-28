# -*- coding: utf-8 -*-
"""Emagrecimento STREAMING de DXF gigante (19/07).

Problema: DWG leve explode em DXF gigante na conversão ODA
(ver caso escola 17/07 — OOM no Render 2GB), e `ezdxf.readfile`
carrega o arquivo INTEIRO na RAM. A defesa era recusar acima de 150 MB.

Solução: acima de um teto de leitura segura, um passe com
`ezdxf.addons.iterdxf` — que lê entidade por entidade, memória O(1) —
copia pra um DXF enxuto SÓ o que o motor mede/lê:

  mantém: LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE, ELLIPSE, HATCH,
          TEXT, MTEXT, INSERT, DIMENSION, POINT, SOLID, ATTRIB
  descarta: 3DSOLID, MESH, IMAGE, WIPEOUT, ACAD_PROXY_ENTITY, SPLINE,
            REGION, BODY e afins — lastro que não vira quantitativo.

O header/tables/blocks são copiados como estão (o iterdxf preserva a
estrutura), então INSERTs continuam resolvendo. Se o resultado ainda for
grande demais, o guard de 150 MB do dwg_extractor continua valendo como
backstop — recusa com mensagem clara em vez de derrubar o servidor.
"""
import os
from typing import Optional


# 🩸 03/09/2026 — ESTE NÚMERO ESTAVA 100 MB DEFASADO E RECUSAVA RESGATE BOM.
# Ele dizia "espelha _MAX_DXF_BYTES" e valia 150 MB; o `_MAX_DXF_BYTES` de
# `dwg_extractor` subiu pra 250 MB em 26/08 e este ficou pra trás. Efeito: um
# DXF de 400 MB cujo filtro textual entregaria 200 MB NÃO era resgatado
# (200 > 150), embora 200 MB passe folgado pelo teto real de 250 MB do
# `extract_from_file`. Comentário que promete espelhar e não espelha é pior
# que número solto — ele desliga a suspeita de quem lê.
#
# 🪤 Por que não importar de `dwg_extractor`: este módulo roda dentro do worker
# de extração e é de propósito leve (só `os` e `typing`). Importar o extrator
# inteiro por uma constante custa segundos em cada prancha. A igualdade fica
# travada por teste (`test_o_teto_do_emagrecedor_espelha_o_do_extrator`), que é
# onde ela deveria estar desde o começo.
_LIMITE_DURO = 250 * 1024 * 1024        # espelha dwg_extractor._MAX_DXF_BYTES

# Acima disso o readfile começa a ser arriscado no Render 2GB (o DXF em RAM
# vira ~5-10× o tamanho em disco, e ainda tem o resto do job).
LIMIAR_SLIM_MB = 60

# Tipos que alimentam medição (paredes/áreas/contagens) ou leitura (textos).
_KEEP = {
    "LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE",
    "HATCH", "TEXT", "MTEXT", "INSERT", "DIMENSION", "POINT",
    "SOLID", "ATTRIB",
}


# 🚨 SUB-ENTIDADES. No arquivo, POLYLINE é seguido de N VERTEX e um SEQEND
# como entidades SEPARADAS (o mesmo vale pros ATTRIB de um INSERT). Quem filtra
# por TEXTO tem que manter esses três, senão a POLYLINE fica sem vértice e o DXF
# vira lixo. O caminho do ezdxf não precisa disso porque lá a POLYLINE já vem
# montada com os vértices dentro — armadilha exclusiva do filtro textual.
# 📄 VIEWPORT (24/09/2026): a leitura por folha (`dwg_extractor.mapa_de_folhas`)
# precisa das janelas das folhas pra saber o que é planta, esquema e detalhe.
# As folhas INATIVAS ficam em BLOCKS (copiado intacto); as da folha ATIVA ficam
# em ENTITIES — e sem isto o emagrecido perdia justamente essas. São poucas e
# pequenas (54 num DXF de 81 MB).
_KEEP_TEXTO = _KEEP | {"VERTEX", "SEQEND", "ATTDEF", "VIEWPORT"}


def prever_ganho_textual(path: str) -> tuple:
    """Mede quanto o filtro textual encolheria — SEM ESCREVER NADA em disco.

    🚨 POR QUE EXISTE (18/08/2026, 12:45): eu tinha religado o plano B pra
    rodar sempre que o arquivo passasse da trava dura. No arquivo real do
    cliente-93 isso escreveu uma cópia de **369 MB** (e outra de 349 MB) pra ganhar
    **0,17%** — e o servidor CAIU às 12:45:26, com o disco do Render em 83%.
    Alerta do Render e tudo. Foi a segunda vez no mesmo dia que uma mudança
    minha "de graça" custou caro.

    O erro conceitual: pra saber se vale escrever, eu estava escrevendo. Uma
    varredura de leitura responde a mesma pergunta sem custar um byte de disco —
    e ler 370 MB sequencialmente é barato, memória O(1).

    Devolve (bytes_previstos, mantidas, descartadas).
    """
    keep = {t.encode("ascii") for t in _KEEP_TEXTO}
    total = 0
    mantidas = descartadas = 0
    dentro_entities = False
    esperando_nome = False
    buf_tam = None
    tipo = None

    with open(path, "rb") as fi:
        while True:
            l_cod = fi.readline()
            if not l_cod:
                break
            l_val = fi.readline()
            cod, val = l_cod.strip(), l_val.strip()
            par = len(l_cod) + len(l_val)

            if cod == b"0":
                if buf_tam is not None:
                    if tipo in keep:
                        total += buf_tam
                        mantidas += 1
                    else:
                        descartadas += 1
                    buf_tam = None
                    tipo = None
                if val == b"SECTION":
                    esperando_nome = True
                    total += par
                elif val in (b"ENDSEC", b"EOF"):
                    dentro_entities = False
                    total += par
                elif dentro_entities:
                    buf_tam = par
                    tipo = val
                else:
                    total += par
                continue

            if esperando_nome and cod == b"2":
                esperando_nome = False
                dentro_entities = (val == b"ENTITIES")
                total += par
                continue

            if buf_tam is not None:
                buf_tam += par
            else:
                total += par
        if buf_tam is not None:
            if tipo in keep:
                total += buf_tam
                mantidas += 1
            else:
                descartadas += 1
    return total, mantidas, descartadas


def emagrecer_por_texto(path: str, out: str) -> tuple:
    """Emagrece um DXF SEM ezdxf, lendo o arquivo como bytes em pares de linhas.

    🎯 Por que existe (18/08/2026, caso cliente-93): o caminho do `iterdxf` quebra
    em `AssertionError: dictionary handle #X not resolved` na hora de ESCREVER.
    Medido em 11 DXF reais convertidos por libredwg: **9 falharam**; um DXF
    escrito pelo próprio ezdxf passou (controle negativo). Ou seja, o
    emagrecedor funciona — quem quebra ele é a saída do libredwg, que é o
    caminho de TODO cliente que manda DWG (o ODA recusa quase tudo).
    Descartar o dicionário de extensão antes de escrever só salvou 3 de 11.

    Como o DXF é um formato de pares (código, valor) em linhas alternadas, dá
    pra filtrar a seção ENTITIES sem interpretar handle nenhum. Memória O(1):
    só uma entidade por vez fica no buffer.

    🪤 Trabalha em BYTES, nunca decodifica. DXF de AutoCAD antigo vem em cp1252
    e um `decode('utf-8')` estoura em acento — foi assim que um dos 11 trocou
    AssertionError por UnicodeEncodeError na tentativa anterior.

    HEADER, TABLES, BLOCKS e OBJECTS são copiados intactos, então INSERT
    continua resolvendo o bloco dele.

    Devolve (mantidas, descartadas).
    """
    keep = {t.encode("ascii") for t in _KEEP_TEXTO}
    mantidas = descartadas = 0
    dentro_entities = False
    esperando_nome = False
    buf = None
    tipo = None

    def _despeja(fo):
        nonlocal buf, tipo, mantidas, descartadas
        if buf is None:
            return
        if tipo in keep:
            fo.write(b"".join(buf))
            mantidas += 1
        else:
            descartadas += 1
        buf = None
        tipo = None

    with open(path, "rb") as fi, open(out, "wb") as fo:
        while True:
            l_cod = fi.readline()
            if not l_cod:
                break
            l_val = fi.readline()
            cod = l_cod.strip()
            val = l_val.strip()

            if cod == b"0":
                _despeja(fo)
                if val == b"SECTION":
                    esperando_nome = True
                    fo.write(l_cod); fo.write(l_val)
                elif val == b"ENDSEC":
                    dentro_entities = False
                    fo.write(l_cod); fo.write(l_val)
                elif val == b"EOF":
                    fo.write(l_cod); fo.write(l_val)
                elif dentro_entities:
                    buf = [l_cod, l_val]      # começa entidade nova
                    tipo = val
                else:
                    fo.write(l_cod); fo.write(l_val)
                continue

            if esperando_nome and cod == b"2":
                esperando_nome = False
                dentro_entities = (val == b"ENTITIES")
                fo.write(l_cod); fo.write(l_val)
                continue

            if buf is not None:
                buf.append(l_cod); buf.append(l_val)
            else:
                fo.write(l_cod); fo.write(l_val)
        _despeja(fo)
    return mantidas, descartadas


# ── RESGATE PELOS BLOCOS (28/09/2026) ──────────────────────────────────────────
# 🩸 Caso 18c57c3c: DWG de 59,7 MB (o ODA recusou, "XData size exceeded") virou
# pelo libredwg um DXF de 511 MB — e 493 MB estavam em BLOCKS, que os dois
# filtros acima copiam INTACTOS. O filtro textual previu 511 -> 502 MB e a
# prancha, única do projeto, deu erro com a mensagem "já estamos resolvendo".
# Medido no arquivo:
#   · 186 MB eram definições de bloco que o desenho NÃO insere (um PURGE tira);
#   · 103 MB de conteúdo BINÁRIO de OLE2FRAME (imagem/planilha colada — o
#     motor não lê o conteúdo; a ENTIDADE fica, ver abaixo);
#   · 38 MB de XDATA de aplicação que o motor não lê (REVIT, GUID de alteração,
#     etiqueta de representação de bloco dinâmico).
# Esvaziando só isso: 511 -> 228 MB, pico de ~1,9 GB na extração, e a extração
# saiu IDÊNTICA à do arquivo inteiro (campo a campo e o texto que vai pra IA).
# 🪤 SPLINE parece lastro (o motor não mede) mas NÃO sai daqui: a `assinatura`
# do bloco conta os tipos de dentro dele, e sem a SPLINE a assinatura muda —
# medido no mesmo arquivo (a comparação reprovou).
# 🪤 Pelo mesmo motivo o OLE2FRAME de dentro de bloco FICA, sem o binário
# (códigos 310): a assinatura conta o tipo, e o teste de laboratório pegou
# `OLE2FRAME:1` sumindo. No caso real não apareceu porque nenhum bloco com
# OLE era contado — no próximo arquivo pode ser.
# 🔑 Só age acima da trava dura: é o arquivo que HOJE dá zero. O caminho que
# funciona não muda em nada.
_XDATA_QUE_O_MOTOR_NAO_LE = {b"revit", b"acad_object_change_guid", b"acdbblockrepetag"}
# O motor LÊ: AcDbBlockRepBTag no BLOCK_RECORD (nome do dinâmico, em TABLES — que
# fica intacto) e o XDATA "ACAD" da cota (DSTYLE) — os dois ficam.


def _e_citacao(cod: bytes) -> bool:
    """Código que pode citar um bloco: nome (2) ou ponteiro (330–369)."""
    return cod == b"2" or (len(cod) == 3 and cod[:2] in (b"33", b"34", b"35", b"36"))


def _pares(fi):
    while True:
        l_cod = fi.readline()
        if not l_cod:
            return
        l_val = fi.readline()
        yield l_cod, l_val, l_cod.strip(), l_val.strip()


def alcance_dos_blocos(path: str) -> tuple:
    """Quais blocos o desenho alcança, e o tamanho que o resgate deixaria.

    Raiz: tudo em ENTITIES (modelo e folha ativa) + `*Model_Space` e todo
    `*Paper_Space*` (folhas inativas moram em BLOCKS). Um bloco alcançado
    alcança o que qualquer entidade dele CITA: por nome (código 2 — INSERT,
    cota, e até padrão de hachura que coincida com nome de bloco) ou por
    ponteiro ao BLOCK_RECORD (330–369). Na dúvida, fica — citação a mais só
    mantém bloco a mais.

    Devolve (nomes, alcançados, bytes_previstos). Lê em fluxo; a memória é a
    lista de nomes e citações, nunca a geometria.
    """
    keep = {t.encode("ascii") for t in _KEEP_TEXTO}
    nomes = set()
    handle_do_bloco = {}
    cita = {}
    raiz = set()
    conteudo = {}                 # bloco -> bytes das entidades de dentro
    tira = {}                     # bloco -> bytes que saem mesmo alcançado
    total = 0
    tira_ent = 0
    secao = None
    esperando = False
    tipo = None
    bloco = None
    em_registro = False
    reg_handle = reg_nome = None
    ent_bytes = ent_xd = ent_bin = 0
    xd_fora = False

    def _fecha():
        nonlocal tira_ent
        if tipo is None:
            return
        if secao == b"ENTITIES":
            tira_ent += ent_bytes if tipo not in keep else ent_xd
        elif tipo in (b"BLOCK", b"ENDBLK"):
            tira_ent += ent_xd                 # a definição fica; o XDATA sem uso, não
        elif secao == b"BLOCKS" and bloco is not None:
            conteudo[bloco] = conteudo.get(bloco, 0) + ent_bytes
            tira[bloco] = tira.get(bloco, 0) + ent_xd + ent_bin

    with open(path, "rb") as fi:
        for l_cod, l_val, cod, val in _pares(fi):
            par = len(l_cod) + len(l_val)
            total += par
            if cod == b"0":
                _fecha()
                if em_registro and reg_handle and reg_nome:
                    handle_do_bloco[reg_handle] = reg_nome
                em_registro = secao == b"TABLES" and val == b"BLOCK_RECORD"
                reg_handle = reg_nome = None
                tipo = None
                ent_bytes = ent_xd = ent_bin = 0
                xd_fora = False
                if val == b"SECTION":
                    esperando = True
                elif val in (b"ENDSEC", b"EOF"):
                    secao = None
                elif secao in (b"ENTITIES", b"BLOCKS"):
                    tipo = val
                    ent_bytes = par
                    if secao == b"BLOCKS" and val == b"BLOCK":
                        bloco = None
                continue
            if esperando and cod == b"2":
                secao, esperando = val, False
                continue
            if em_registro:
                if cod == b"5":
                    reg_handle = val.lower()
                elif cod == b"2":
                    reg_nome = val.lower()
                continue
            if tipo is None:
                continue
            ent_bytes += par
            if cod == b"1001":
                xd_fora = val.lower() in _XDATA_QUE_O_MOTOR_NAO_LE
            if xd_fora:
                ent_xd += par
            elif tipo == b"OLE2FRAME" and cod == b"310":
                ent_bin += par
            if tipo == b"BLOCK":
                if cod == b"2" and bloco is None:
                    bloco = val.lower()
                    nomes.add(bloco)
            elif tipo != b"ENDBLK" and _e_citacao(cod):
                if secao == b"ENTITIES":
                    raiz.add(val.lower())
                elif bloco is not None:
                    cita.setdefault(bloco, set()).add(val.lower())
        _fecha()

    def _bloco(x):
        return x if x in nomes else handle_do_bloco.get(x)

    alc = set()
    pilha = [n for n in nomes if n == b"*model_space" or n.startswith(b"*paper_space")]
    pilha += [b for b in map(_bloco, raiz) if b]
    while pilha:
        n = pilha.pop()
        if n in alc:
            continue
        alc.add(n)
        pilha.extend(b for b in map(_bloco, cita.get(n, ())) if b and b not in alc)
    previsto = (total - tira_ent
                - sum(v for b, v in conteudo.items() if b not in alc)
                - sum(v for b, v in tira.items() if b in alc))
    return nomes, alc, previsto


def emagrecer_blocos_por_texto(path: str, out: str, alcancados: set) -> dict:
    """Escreve o DXF resgatado: o filtro de ENTITIES de sempre + os blocos.

    Bloco não alcançado fica VAZIO — BLOCK/ENDBLK e o BLOCK_RECORD ficam, então
    nenhuma referência quebra; só a geometria de dentro sai. OLE2FRAME de bloco
    fica sem o conteúdo binário (310). XDATA das aplicações que o motor não lê
    sai de ENTITIES e BLOCKS. HEADER, CLASSES, TABLES e OBJECTS vão intactos.
    Bytes, nunca decode.
    """
    keep = {t.encode("ascii") for t in _KEEP_TEXTO}
    n = {"vazios": 0, "ole": 0, "xdata": 0, "entidades": 0}
    secao = None
    esperando = False
    bloco = None
    buf = None
    tipo = None

    def _despeja(fo):
        nonlocal buf, tipo
        if buf is None:
            return
        if secao == b"ENTITIES" and tipo not in keep:
            n["ole" if tipo == b"OLE2FRAME" else "entidades"] += 1
        elif (secao == b"BLOCKS" and tipo not in (b"BLOCK", b"ENDBLK")
              and bloco not in alcancados):
            n["vazios"] += 1
        else:
            fora = False
            n["ole"] += tipo == b"OLE2FRAME"
            for i in range(0, len(buf), 2):
                cod = buf[i].strip()
                if cod == b"1001":
                    fora = buf[i + 1].strip().lower() in _XDATA_QUE_O_MOTOR_NAO_LE
                    n["xdata"] += fora
                if not fora and not (tipo == b"OLE2FRAME" and cod == b"310"):
                    fo.write(buf[i]); fo.write(buf[i + 1])
        buf = None
        tipo = None

    with open(path, "rb") as fi, open(out, "wb") as fo:
        for l_cod, l_val, cod, val in _pares(fi):
            if cod == b"0":
                _despeja(fo)
                if val == b"SECTION":
                    esperando = True
                elif val in (b"ENDSEC", b"EOF"):
                    secao = None
                elif secao in (b"ENTITIES", b"BLOCKS"):
                    buf = [l_cod, l_val]
                    tipo = val
                    if secao == b"BLOCKS" and val == b"BLOCK":
                        bloco = None
                    continue
                fo.write(l_cod); fo.write(l_val)
                continue
            if esperando and cod == b"2":
                secao, esperando = val, False
                fo.write(l_cod); fo.write(l_val)
                continue
            if buf is not None:
                if tipo == b"BLOCK" and cod == b"2" and bloco is None:
                    bloco = val.lower()
                buf.append(l_cod); buf.append(l_val)
            else:
                fo.write(l_cod); fo.write(l_val)
        _despeja(fo)
    return n


def _resgate_pelos_blocos(path: str, size: int, log=None) -> Optional[str]:
    """Acima da trava dura, depois que o filtro de ENTITIES não bastou.

    Mede antes de escrever (a lição de 18/08: o servidor caiu por uma cópia de
    369 MB escrita pra ganhar 0,17%). Só escreve se a previsão cabe; só aceita
    se o escrito cabe; o original sai assim que o enxuto provou que serve.
    """
    # 🪤 O MESMO nome do enxuto de sempre: quem mostra o nome da prancha ao
    # cliente (`main._nome_prancha_bonito`) já sabe tirar `.slim.dxf`; um sufixo
    # novo apareceria na planilha. Quem chama já apagou o enxuto anterior.
    out = os.path.splitext(path)[0] + ".slim.dxf"
    try:
        nomes, alc, prev = alcance_dos_blocos(path)
        if prev > _LIMITE_DURO:
            if log is not None:
                try:
                    log("motor:dxf-slim",
                        f"arq={os.path.basename(path)} resgate pelos blocos NÃO "
                        f"cabe: {size // 1048576} MB -> {prev // 1048576} MB previstos "
                        f"({len(nomes & alc)} de {len(nomes)} blocos no desenho) — "
                        f"NADA escrito em disco")
                except Exception:
                    pass
            return None
        n = emagrecer_blocos_por_texto(path, out, alc)
        novo = os.path.getsize(out)
        if novo > _LIMITE_DURO:
            os.remove(out)
            return None
        if log is not None:
            try:
                log("motor:dxf-slim",
                    f"arq={os.path.basename(path)} RESGATE PELOS BLOCOS: "
                    f"{size // 1048576} MB -> {novo // 1048576} MB ({n['vazios']} "
                    f"entidades de {len(nomes) - len(nomes & alc)} blocos fora do "
                    f"desenho, {n['ole']} OLE, {n['xdata']} XDATA sem uso)")
            except Exception:
                pass
        try:
            os.remove(path)
        except OSError:
            pass
        return out
    except Exception as e:
        print(f"[dxf-slim] {os.path.basename(path)}: resgate pelos blocos falhou "
              f"({type(e).__name__}: {e})")
        try:
            if os.path.exists(out):
                os.remove(out)
        except OSError:
            pass
        return None


def emagrecer_dxf_se_preciso(path: str, limiar_mb: int = LIMIAR_SLIM_MB,
                             log=None) -> Optional[str]:
    """Se o DXF passa do limiar, gera `<nome>.slim.dxf` só com o que o motor
    usa e devolve o caminho novo. Devolve None quando: arquivo já é pequeno,
    o emagrecimento não rendeu (>95% do original) ou qualquer erro — nesses
    casos o chamador segue com o original (comportamento antigo).
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size <= limiar_mb * 1024 * 1024:
        return None

    out = os.path.splitext(path)[0] + ".slim.dxf"
    mantidas = descartadas = 0
    try:
        from ezdxf.addons import iterdxf
        doc = iterdxf.opendxf(path)
        try:
            exporter = doc.export(out)
            try:
                for e in doc.modelspace():
                    if e.dxftype() in _KEEP:
                        exporter.write(e)
                        mantidas += 1
                    else:
                        descartadas += 1
                # 📄 As VIEWPORTs da folha ATIVA moram em ENTITIES com
                # paperspace=1, e o `modelspace()` do iterdxf as pula. Sem elas
                # a leitura por folha perde uma folha. Falhou? Segue sem — a
                # leitura por folha só fica com as outras folhas.
                try:
                    for e in doc.load_entities(doc.sections["ENTITIES"] + 1, {"VIEWPORT"}):
                        if e.dxftype() == "VIEWPORT" and e.dxf.paperspace == 1:
                            exporter.write(e)
                            mantidas += 1
                except Exception:
                    pass
            finally:
                exporter.close()
        finally:
            doc.close()
    except Exception as exc:
        # 🔁 PLANO B: o caminho do ezdxf quebra em 9 de 11 DXF de libredwg
        # (medido 18/08/2026) — e libredwg é o caminho de TODO cliente que
        # manda DWG, porque o ODA recusa quase tudo. Cair fora aqui deixava o
        # arquivo INTEIRO ir pro extrator, sem proteção nenhuma.
        # 🪤 O ganho do filtro textual nos 11 arquivos medidos foi de só 4% de
        # disco e 0% de RAM — ele NÃO resolve estouro de memória sozinho. Vale
        # porque nunca quebra e porque 4% de proteção é mais que 0%. Quem
        # prometer que isto conserta OOM está inventando.
        # 🔑 QUANDO O ARQUIVO PASSA DA TRAVA DURA, O PLANO B É A ÚNICA SAÍDA.
        # De manhã eu pus aqui um atalho que PULAVA o plano B acima de ~156 MB,
        # com base nos 4% de ganho medidos em 11 arquivos pequenos — e com isso
        # desliguei o resgate exatamente no caso que precisava dele (cliente-93,
        # DXF de 370 MB). Os 4% valem pra arquivo que já é quase só entidade
        # útil; num DWG de AEC recusado pelo ODA, o lastro (proxy, 3DSOLID,
        # MESH, WIPEOUT) pode ser a maior parte do arquivo. Não dá pra decidir
        # por estimativa: mede.
        #
        # ✅ SEGURO PRA BLOCO, ao contrário do `dwg2dxf -m`. O filtro textual
        # copia HEADER/TABLES/BLOCKS intactos e só peneira a seção ENTITIES.
        # Medido em 5 arquivos: 56.949 entidades de dentro de bloco -> 56.949,
        # 100% preservadas, contra 0% do `-m`. É por isso que este caminho pode
        # ficar ligado e o outro não.
        #
        # 🪤 Disco: o Render estava em 83% no dia. Por isso o original é apagado
        # ASSIM QUE o enxuto prova que vale, e o enxuto é apagado na hora se
        # não valer — nunca ficam os dois grandes ao mesmo tempo por mais que
        # o instante da avaliação.
        try:
            # 🚦 MEDE ANTES DE ESCREVER. Sem isto, um arquivo de 370 MB que só
            # encolhe 0,17% gera uma cópia de 369 MB em disco pra ser apagada
            # em seguida — foi assim que o servidor caiu em 18/08 12:45:26.
            _prev, _pm, _pd = prever_ganho_textual(path)
            # 28/09 — o filtro de ENTITIES não põe abaixo da trava dura: o peso
            # pode estar nos BLOCOS, que ele copia intactos (caso 18c57c3c).
            if size > _LIMITE_DURO and _prev > _LIMITE_DURO:
                try:
                    if os.path.exists(out):
                        os.remove(out)
                except OSError:
                    pass
                _pelos_blocos = _resgate_pelos_blocos(path, size, log)
                if _pelos_blocos:
                    return _pelos_blocos
            _vale_resgate = size > _LIMITE_DURO and _prev <= _LIMITE_DURO
            _vale_economia = size <= _LIMITE_DURO and _pd > 0 and _prev < size * 0.95
            if not (_vale_resgate or _vale_economia):
                if log is not None:
                    try:
                        log("motor:dxf-slim",
                            f"arq={os.path.basename(path)} filtro textual NÃO "
                            f"compensa: {size // 1048576} MB -> "
                            f"{_prev // 1048576} MB previstos ({_pd} descartadas "
                            f"de {_pm + _pd}) — NADA escrito em disco")
                    except Exception:
                        pass
                try: os.remove(out)
                except OSError: pass
                return None
            _m, _d = emagrecer_por_texto(path, out)
            _novo = os.path.getsize(out)
            # Dois motivos DIFERENTES pra aceitar o enxuto:
            #   RESGATE — o original não passava da trava dura e o enxuto passa.
            #             É a diferença entre planilha e zero.
            #   ECONOMIA — os dois cabem, mas o enxuto poupa RAM na extração.
            _resgatou = size > _LIMITE_DURO and _novo <= _LIMITE_DURO
            _economizou = _d > 0 and _novo < size * 0.95
            if _resgatou or _economizou:
                _motivo = "RESGATE (passou a caber)" if _resgatou else "economia"
                if log is not None:
                    try:
                        log("motor:dxf-slim",
                            f"arq={os.path.basename(path)} ezdxf falhou "
                            f"({type(exc).__name__}) e o filtro TEXTUAL "
                            f"{_motivo}: {size // 1048576} MB -> "
                            f"{_novo // 1048576} MB ({_m} mantidas, "
                            f"{_d} descartadas)")
                    except Exception:
                        pass
                # 🪤 O original vai embora AGORA. São centenas de MB por prancha
                # e o disco do Render estava em 83% no dia do caso cliente-93 —
                # deixar os dois de pé é o que enche o disco de cliente.
                # Só apaga depois que o enxuto provou que serve.
                if _resgatou:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                try:
                    print(f"[dxf-slim] {os.path.basename(path)}: plano B textual "
                          f"{_motivo} {size // 1048576} MB -> {_novo // 1048576} MB")
                except Exception:
                    pass
                return out
            # Não serviu: some com a cópia na hora, não deixa lastro em disco.
            if log is not None and size > _LIMITE_DURO:
                try:
                    log("motor:dxf-slim",
                        f"arq={os.path.basename(path)} filtro textual NÃO salvou: "
                        f"{size // 1048576} MB -> {_novo // 1048576} MB, ainda "
                        f"acima do limite de {_LIMITE_DURO // 1048576} MB "
                        f"({_d} descartadas de {_m + _d}) — prancha vai falhar")
                except Exception:
                    pass
            try: os.remove(out)
            except OSError: pass
        except Exception as _e2:
            print(f"[dxf-slim] {os.path.basename(path)}: plano B textual também "
                  f"falhou ({type(_e2).__name__}: {_e2})")
            try: os.remove(out)
            except OSError: pass
        print(f"[dxf-slim] {os.path.basename(path)}: emagrecimento falhou "
              f"({type(exc).__name__}: {exc}) — segue com o original")
        # 🚨 A FALHA TEM QUE APARECER NO BANCO. Este passo existe pra evitar
        # ESTOURO DE MEMÓRIA em DXF grande (fix do OOM multi-DXF). Quando ele
        # falha, o arquivo segue INTEIRO pro extrator — ou seja, a proteção
        # some justamente no caso que ela deveria cobrir.
        # Até 11/08/2026 isto era só `print`: `error_log` tinha ZERO linha de
        # slim, e não dava pra saber a frequência. Medido no mesmo dia: falhou
        # em 4 de 4 arquivos testados (HWB e cliente-94), todos com
        # "AssertionError: dictionary handle não resolvido" — um padrão, não
        # azar. É a mesma família do preview que falhava calado.
        # 🪤 O registrador vem por PARÂMETRO, não por import de `main`: este
        # módulo também roda dentro do `dxf_extract_worker`, num subprocesso —
        # importar a app FastAPI lá seria pesado e circular. Sem `log`, cai no
        # print de sempre e nada quebra.
        if log is not None:
            try:
                log("motor:dxf-slim",
                    f"arq={os.path.basename(path)} FALHOU {type(exc).__name__}: "
                    f"{str(exc)[:160]} — segue com o arquivo INTEIRO (sem "
                    f"proteção de memória)")
            except Exception:
                pass      # log nunca pode derrubar o processamento
        try:
            if os.path.exists(out):
                os.remove(out)
        except OSError:
            pass
        return None

    try:
        novo = os.path.getsize(out)
    except OSError:
        return None
    # 28/09 — o caminho do ezdxf também só peneira o modelo: acima da trava
    # dura, o enxuto dele não serve pro extrator (que recusa) e o peso pode
    # estar nos blocos. Some com ele ANTES de escrever outro (disco, 18/08).
    if size > _LIMITE_DURO and novo > _LIMITE_DURO:
        try:
            os.remove(out)
        except OSError:
            pass
        return _resgate_pelos_blocos(path, size, log)
    # 🚨 O PRINT DE SUCESSO NÃO PODE MATAR O SUCESSO. A seta unicode aqui
    # estourava UnicodeEncodeError em stdout cp1252 — e como o print vem DEPOIS
    # do emagrecimento dar certo, a exceção subia e o arquivo emagrecido era
    # descartado. Medido em 18/08/2026: dos 11 DXF testados, os DOIS únicos em
    # que o ezdxf conseguiu emagrecer eram justamente os que morriam aqui.
    # 🪤 Mesma armadilha do preview de prancha (dxf_render), que já tinha
    # custado o mesmo diagnóstico errado: "falhou" quando na verdade funcionou.
    try:
        print(f"[dxf-slim] {os.path.basename(path)}: {size // 1048576} MB -> "
              f"{novo // 1048576} MB ({mantidas} entidades mantidas, "
              f"{descartadas} descartadas)")
    except Exception:
        pass
    if novo >= size * 0.95:
        # não rendeu — evita duplicar disco à toa
        try:
            os.remove(out)
        except OSError:
            pass
        return None
    return out
