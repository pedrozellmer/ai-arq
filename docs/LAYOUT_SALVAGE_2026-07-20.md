# 🏠 Salvamento de planta de layout — caso Catarina (2026-07-20)

Registro do dia em que uma cliente nova (**Catarina / Luiza Porto Projetos**,
apê Catarina e Plínio, Itaim Bibi) subiu 3 arquivos e **todos deram erro** — e
do que a gente construiu pra resolver a classe inteira do problema.

## O que a Catarina mandou (todos "Apê novo", mesmo projeto)
1. **PDF** `LPP2613_C_LAYOUT_R00 - OPCAO 02.pdf` → erro "Nenhum item quantificável".
2. **2 DWG** `(...)LAYOUT_R00 - Copia (2).dwg` → erro AEC (não abre).

## Diagnóstico
- **Os 2 DWG são AutoCAD Architecture (AEC) de verdade** — rodei `dwg_has_aec_markers`,
  achei `AEC_VARS`/`AEC_DISP`/`AecDb` em UTF-16LE. Detecção correta, mensagem honesta.
  A cliente precisa reexportar (comando `EXPORTTOAUTOCAD` → Salvar como DXF).
- **O PDF é vetorial e completo** (53k linhas, planta inteira). A Vision LEU tudo
  (reconheceu cada cômodo), mas devolveu **0 itens** — é um **estudo de layout de
  interiores** (arrumação de móveis), sem cota de dimensão nem quadro de áreas.
- **Área NÃO é medível com honestidade aqui:** a detecção de cômodos fecha só
  ~35 m² de ~150 (os grandes não fecham polígono); convex hull dá 224 (superestima).
  Gerar "Piso = 35 m²" seria número FALSO → viola a regra dura nº1. **Não fazer.**
- **O que É extraível com honestidade:** esquadrias (as cotas `160x150/86` estão no
  texto vetorial), e contagens visuais (louças, móveis, portas).

## O que foi construído e está NO AR (20/07)
1. **Campo "Área total (m²)" no upload** — cliente informa a metragem → base pras
   áreas, rotulada "informada por você, não medida". `projects.user_total_area`,
   `ProjectData.total_area_source='informado'`. Só usa quando a planta não mediu.
2. **Salvamento de layout** no guard de 0 itens do `process_job` (`main.py`):
   - `_salvage_layout_esquadrias(file_paths)` — DETERMINÍSTICO. Lê as cotas de
     esquadria (`\d{2,3}x\d{2,3}/\d{2,3}`, forma com peitoril = inconfundível) do
     texto do PDF. No arquivo da Catarina: 4 tipos / 7 esquadrias.
   - `_salvage_layout_ai_counts(client, file_paths, crops_dir)` — ADITIVO. Passo de
     VISÃO que conta louças/metais, portas, marcenaria, mobiliário, iluminação.
     Blocklist anti-área (piso/forro/parede/pintura…), só disciplinas de contagem,
     qty em (0,500], tudo 'estimado'. Falha (render/API/JSON) → mantém só esquadrias.
   - Só roda quando: 0 itens **e** a IA não deu erro **e** não é complemento **e**
     as esquadrias acharam algo (confirma layout legível). Nunca piora projeto que
     já funciona (é o caminho que HOJE dava erro seco).
3. **DXF como formato nº1** em todo o sistema (upload, landing, FAQ, projeto,
   preços, guia de exportação) + mensagem de DWG AEC deixou de dizer "elétrica/MEP".

## ⚠ Pendências honestas (não feito ainda)
1. **Verificação adversarial do passo de visão** (`_salvage_layout_ai_counts`): hoje
   é um passo único, sem os N revisores do estudo one-off. Pode listar item a
   mais/menos. Antes de confiar amplo, **reprocessar um layout real** (ex.: projeto
   da Catarina pelo "Avaliar" do admin) e conferir as contagens.
2. **Auto-gerar itens de área** (piso/forro/pintura) a partir da área informada +
   pé-direito. Hoje a área informada entra como PREMISSA/base; não vira item de
   piso automaticamente. Precisa de pé-direito no upload e fatores por tipologia.
3. **Blog DXF-first**: os posts (inclusive "DWG ou PDF") ainda não citam DXF como
   preferido — passada de conteúdo pendente.

## Arquivos-chave
- `backend/main.py` — `_salvage_layout_esquadrias`, `_salvage_layout_ai_counts`,
  guard de 0 itens no `process_job`, `user_total_area` no `/api/process` + reprocess.
- `backend/models.py` — `ProjectData.total_area_source`.
- `backend/spreadsheet.py` — rótulo "informada por você" na premissa/resumo de área.
- `dashboard.html` — campo de área + DXF em destaque no upload.
- Migration Supabase: `projects.user_total_area`.
