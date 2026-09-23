# What real Astana mobility data can we use within an hour? (issue #24)

Checked 2026-09-23 from outside Kazakhstan, curl with a browser User-Agent and 10–60 s timeouts. "Verified" means the request was made today and the status or count is quoted.

The current model is on branch `sim-astana-ui-20260923-135841` (`akim/ui/src/mobility.ts`, `population.ts`). It uses 2,000 synthetic residents. Each one's home and work are random points inside a district polygon, with a synthetic departure time. Trips are routed on a bundled real OSM street graph (`astana-roads.json`). Speeds, demand weights, capacities and intervention factors are assumptions; the code says so in a comment in `mobility.ts`.

## Bottom line

**No real Astana travel-time, congestion, OD or transit-schedule data can be fetched without a key within an hour.**
- There is no public Astana GTFS.
- OSM has no Astana bus route relations.
- The Astana bus/transport portals do not resolve from here.
- Every traffic API needs a key.

The realistic 1-hour upgrade is to ground the inputs in real data and keep the flows synthetic:
- real population density for homes (Kontur, open)
- real OSM speed limits and lanes for edge speeds and capacity
- optionally, real geocoded road accidents for a safety overlay
- optionally, Google Routes or TomTom travel times to calibrate "before" minutes, if a teammate creates a key in about 10 minutes

## Ranked options

| # | Source | Access | Licence | Coverage / format / freshness | Replaces in model | Verified |
|---|---|---|---|---|---|---|
| 1 | **Kontur Population, Kazakhstan** (HDX), H3 hexagons of 400 m with population | No key, direct S3 download (`kontur_population_KZ_20231101.gpkg.gz`, 14.9 MB) | CC BY 4.0 | Whole country, GeoPackage, snapshot 2023-11-01 | `population.ts`: sample `home` points weighted by real hex population instead of uniformly inside district polygons | HDX `package_show` returned 200 and listed the resource |
| 2 | **OSM tags on the existing street graph** (`maxspeed`, `lanes`, `highway` class) through the Overpass mirror `maps.mail.ru` | No key | ODbL (attribution) | Astana bbox 50.98–51.30 N, 71.20–71.65 E. 2,922 motorway to tertiary ways, of which 1,299 (44 %) carry `maxspeed`. Data timestamp 2026-09-23T11:24Z | `mobility.ts`: free-flow speed and capacity per edge from real tags, with a class default where a tag is missing, instead of assumed speeds | Overpass `out count` returned 200. `overpass-api.de` still returns 406 from our network, as noted in the akim README |
| 3 | **OSM work/leisure destinations** (offices, shops, schools, universities, malls) through the same mirror | No key | ODbL | Point/POI JSON, live | `population.ts`: sample `work`/`leisure` from real POI clusters | Mirror verified as above. POI counts not pulled |
| 4 | **gis.kgp.kz DTP FeatureServer** (geocoded road accidents, Legal Statistics Committee), already in INVENTORY #284 and #364 | No key, ArcGIS REST | Government open data, terms not stated | Points with date and type. **1,540 accidents in the Astana bbox for 2026**; the national max date is 2026-09-21 | Not a flow input. Adds an accident-hotspot overlay or a safety metric per segment | `returnCountOnly` with the Astana envelope returned 200 `{"count":1540}` |
| 5 | **Google Maps Routes API / Distance Matrix** with `departure_time`, which gives traffic-aware durations | API key and a billing account (free monthly credit) | Google ToS: may display, may not store or cache beyond limits | Any OD pair, JSON, live and predictive traffic | Calibrate "before" `minutes` for about 20–50 representative OD pairs at 08:00 on real congested travel times (fits the BPR/speed factors) | Not called, since no key. About 10 min to set up if someone has a card on a GCP account |
| 6 | **TomTom Traffic Flow Segment Data / Routing** | Free developer key (sign-up, free daily quota) | TomTom ToS | Per-point current vs free-flow speed, JSON, live | Real congestion ratio on arterials to set "before" congestion | `api.tomtom.com/.../flowSegmentData` returned 401 without a key (endpoint up) |
| 7 | **OSRM public demo** (`router.project-osrm.org`) | No key, demo only (no heavy use) | ODbL data | Free-flow OSM routing | Sanity check that our graph routing matches a standard router. No traffic | Returned 200 for an Astana route |
| 8 | **Astana LRT in OSM** | No key | ODbL | 2 `light_rail` relations "Astana LRT / Tarlan Astana: Nurly Zhol ↔ Airport", operator City Transportation Systems, `opening_date=2026` | Could add one real transit line (geometry and stops) as a "bus/rail" mode option. No timetable | Overpass returned 200 |
| 9 | **2GIS Routing / Traffic API** | Key only through a demo request to 2GIS sales (days) | Commercial | Best KZ coverage including traffic | Would replace everything above, but not within an hour | `routing.api.2gis.com` returned 400 without a key |

## Checked and not usable within an hour

- **Astana GTFS: none exists publicly.** The MobilityDatabase catalogue (`feeds_v2.csv`, 6,603 feeds) has 0 Kazakhstan entries. The Transitland API needs a key (401).
- **OSM bus routes for Astana: 0 `route=bus` relations** in the bbox. There are about 964 stop and platform nodes, but no route topology, so we cannot build a bus network from OSM.
- **Astana operator and portal hosts**: `smart.astana.kz`, `api.smart.astana.kz`, `astanalrt.kz`, `astanabus.kz`, `sitibus.kz`, `tabys.kz` and `tpass.kz` did not resolve or timed out (000). The akim README already lists `api.smart.astana.kz` as KZ-only. Retry from the venue network. `avtobys.kz` and `onay.kz` return 200 but are payment/marketing pages with a reCAPTCHA and no open API.
- **CityBus (`citybus.tha.kz/settings`)** lists 11 cities and **Astana is not one of them**. The token is reCAPTCHA-gated anyway (INVENTORY #408).
- **Yandex traffic / Yandex Rasp**: there is no public traffic API. The ToS forbids scraping the jams tile layer. Rasp (key, INVENTORY row 394) covers intercity timetables only.
- **data.egov.kz**: the portal/catalogue tier returned HTTP 500 today, so we could not search the Transport category for Astana-specific sets. The known transport sets are intercity or international bus registers (INVENTORY #391 and #392) and road construction (#367), not urban flows.
- **stat.gov.kz "Перевезено пассажиров" (element 5355)**: live (200, XLSX), but a national total by mode, not per city. It is useless for commute flows and fine only for a "context" number.
- **OD matrices, road counts, mobile-operator mobility**: nothing public found. Uber Movement is discontinued and never covered Astana.

## Recommendation

Spend the hour on options 1 and 2, and add 4 if time remains:

1. Download the Kontur gpkg. Filter hexes to the Astana bbox or district polygons (`ogr2ogr` or a small Python script). Export `[lng, lat, pop]` JSON of about 1–3k hexes. In `population.ts`, pick each resident's home hex with probability ∝ pop, then jitter inside the hex.
2. Pull `maxspeed`/`lanes`/`highway` for the ways already in `astana-roads.json` from the mail.ru Overpass mirror. Store per-edge speed and capacity. Fall back by class, for example 60/50/40/30 km/h.
3. Keep departure times and the work-destination choice synthetic. Label them as such in the UI: "homes: Kontur 2023 population; speeds: OSM; trips: modelled".

Take option 5 or 6 only if a teammate already has a Google Cloud billing account or can register for TomTom in under 10 minutes. It is the only path to real "before" travel times. Never commit the key: pass it through an env var and cache the responses.

## Sources (all requested 2026-09-23)

- Kontur on HDX: `https://data.humdata.org/api/3/action/package_show?id=kontur-population-kazakhstan`
- Overpass mirror: `https://maps.mail.ru/osm/tools/overpass/api/interpreter` (queries: `rel[type=route][route~bus|trolleybus|light_rail|tram|minibus]`, `way[highway~motorway..tertiary][maxspeed]`, bbox 50.98,71.2,51.3,71.65)
- DTP: `https://gis.kgp.kz/arcgis/rest/services/KPSSU/DTP/FeatureServer/0/query?where=yr%3D2026&geometry=71.2,50.98,71.65,51.3&geometryType=esriGeometryEnvelope&inSR=4326&returnCountOnly=true&f=json`
- MobilityDatabase catalogue: `https://files.mobilitydatabase.org/feeds_v2.csv`
- CityBus: `https://citybus.tha.kz/settings`
- stat.gov.kz: `https://stat.gov.kz/api/iblock/element/5355/file/ru/`
- Existing verification notes: `akim/INVENTORY.md` (#284, #364, #391, #392, #408), `akim/README.md` (gotchas 8–9, keys table)
