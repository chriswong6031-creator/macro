# Finviz themes tree — fresh extraction vs committed snapshot

* OLD (committed): `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/gmi-theme-graph-w3-f12a28/data/themes_heatmap/themes_tree.json`
* NEW (extracted): `/private/tmp/claude-501/-Users-chriswong-Documents-Cluade-Macro-Dashboard--claude-worktrees-gmi-theme-graph-w3-f12a28/8489d6cf-bc30-4339-a5f8-6ea78e751674/scratchpad/finviz_w3a/extracted_tree.json`

## Counts

| metric | old | new | delta |
|---|---:|---:|---:|
| themes | 40 | 40 | +0 |
| subthemes | 268 | 268 | +0 |
| memberships | 2356 | 2339 | -17 |
| unique_tickers | 941 | 924 | -17 |

## Themes

* added: none
* removed: none
* order changed: False
* rename detection: theme `key` == theme `theme` in both trees, so a rename is indistinguishable from add+remove; matching by key and by name gives identical results.

## Subthemes

* added (new key, no name match): none
* removed (key gone, no name match): none
* moved between themes: none
* key stable, displayName changed: 0
* displayName stable, key changed: 0
* description changed: 0 (none)
* subsector order changed within theme: none

## Members

* subthemes with any member change: **32** / 268
* memberships added: **9**, removed: **26**
* pure-reorder-only subthemes: 0

### All subthemes with membership changes (by churn)

| subtheme key | theme | name | old | new | net | added | removed |
|---|---|---|---:|---:|---:|---|---|
| `bigdatainfrastructure` | Big Data | Infrastructure | 16 | 16 | +0 | SNDK | PSTG |
| `consumerfarmdirect` | Consumer Goods | Farm-Direct | 8 | 6 | -2 | — | FDP, CVGW |
| `hardwarestorage` | Hardware | Storage | 7 | 7 | +0 | SNDK | PSTG |
| `agricultureindoorfarming` | Agriculture & FoodTech | Indoor Farming | 4 | 3 | -1 | — | UGRO |
| `aidata` | Artificial Intelligence | Data | 13 | 14 | +1 | SNDK | — |
| `clouddatabases` | Cloud Computing | Databases | 9 | 8 | -1 | — | CFLT |
| `commagrisofts` | Commodities Agriculture | Softs | 6 | 5 | -1 | — | FDP |
| `commenergygaslng` | Commodities Energy | Gas & LNG | 12 | 11 | -1 | — | CTRA |
| `commmetalssilver` | Commodities Metals | Silver | 7 | 6 | -1 | — | DVS |
| `educationcurriculum` | Education Technology | Curriculum | 11 | 10 | -1 | — | UDMY |
| `educationplatforms` | Education Technology | Platforms | 6 | 5 | -1 | — | UDMY |
| `educationworkforce` | Education Technology | Workforce | 10 | 9 | -1 | — | UDMY |
| `energycleanhydrogen` | Energy Renewable | Hydrogen | 9 | 8 | -1 | — | GTLS |
| `environmentalagriculture` | Environmental Sustainability | Agriculture | 13 | 12 | -1 | — | ORGN |
| `environmentalairquality` | Environmental Sustainability | Air Quality | 10 | 9 | -1 | — | GTLS |
| `environmentalclimate` | Environmental Sustainability | Climate | 13 | 12 | -1 | — | ORGN |
| `environmentalwaste` | Environmental Sustainability | Waste | 10 | 9 | -1 | — | MEG |
| `evsfleets` | Electric Vehicles | Fleets | 8 | 7 | -1 | — | NVVE |
| `fintechlending` | FinTech | Lending | 6 | 5 | -1 | — | LC |
| `hardwaredatacenters` | Hardware | Data Centers | 6 | 7 | +1 | SNDK | — |
| `hardwareelectronics` | Hardware | Electronics | 7 | 8 | +1 | SNDK | — |
| `hardwareindustrialiot` | Hardware | Industrial IoT | 11 | 12 | +1 | SNDK | — |
| `hardwarepcsdevices` | Hardware | PCs & Devices | 10 | 11 | +1 | SNDK | — |
| `healthcarediagnostics` | Healthcare & Biotech | Diagnostics | 12 | 11 | -1 | — | EXAS |
| `iothardware` | Internet of Things | Hardware | 7 | 8 | +1 | SNDK | — |
| `nanotechproducts` | Nanotechnology | Products | 7 | 6 | -1 | — | SEE |
| `nutritionaltprotein` | Healthy Food & Nutrition | Alt Protein | 10 | 9 | -1 | — | STKL |
| `semismemory` | Semiconductors | Memory | 4 | 5 | +1 | SNDK | — |
| `spacesatellites` | Space Tech | Satellites | 6 | 5 | -1 | — | SATS |
| `telecomsatcom` | Telecommunications | Satcom | 7 | 6 | -1 | — | SATS |
| `wearablesmedical` | Wearables | Medical | 8 | 7 | -1 | — | MASI |
| `wearablessmartwatches` | Wearables | Smartwatches | 4 | 3 | -1 | — | MASI |

## Tickers

* only in OLD (18): dropped from the map entirely
  * `CFLT` — was in: clouddatabases
  * `CTRA` — was in: commenergygaslng
  * `CVGW` — was in: consumerfarmdirect
  * `DVS` — was in: commmetalssilver
  * `EXAS` — was in: healthcarediagnostics
  * `FDP` — was in: commagrisofts, consumerfarmdirect
  * `GTLS` — was in: energycleanhydrogen, environmentalairquality
  * `LC` — was in: fintechlending
  * `MASI` — was in: wearablesmedical, wearablessmartwatches
  * `MEG` — was in: environmentalwaste
  * `NVVE` — was in: evsfleets
  * `ORGN` — was in: environmentalagriculture, environmentalclimate
  * `PSTG` — was in: bigdatainfrastructure, hardwarestorage
  * `SATS` — was in: spacesatellites, telecomsatcom
  * `SEE` — was in: nanotechproducts
  * `STKL` — was in: nutritionaltprotein
  * `UDMY` — was in: educationcurriculum, educationplatforms, educationworkforce
  * `UGRO` — was in: agricultureindoorfarming
* only in NEW (1): newly on the map
  * `SNDK` — now in: aidata, bigdatainfrastructure, hardwaredatacenters, hardwareelectronics, hardwareindustrialiot, hardwarepcsdevices, hardwarestorage, iothardware, semismemory
* present in both but subtheme set changed (0):
