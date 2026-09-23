# Astana map provenance

Snapshot: 2026-09-23.

- Basemap: [OpenStreetMap](https://www.openstreetmap.org/copyright), standard HTTPS tiles with visible attribution. Leaflet supports pan, zoom and district selection. No bulk tile downloads or offline tile cache.
- Districts: [Kazakhstan National Geoportal WFS](https://map.gov.kz/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=geonode:border_districts&outputFormat=application/json&srsName=EPSG:4326&CQL_FILTER=kato%20LIKE%20%2771%25%27). `src/astana-districts.json` retains the six districts' multipolygons, holes, KATO and Russian name; coordinates rounded to six decimals. Eleven multipart records correspond to six unique districts. Sarayshyk is shown without a game score because the scenario models five districts.
- Streets: © OpenStreetMap contributors, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). `src/astana-roads.json` is a derived street graph and is shared under ODbL. It stores projected coordinates and adjacency lists for the largest connected component in each modeled district. Original geometry vertices are preserved; only primary, secondary and tertiary streets within the snapshot bounding box are included. This is a simplified simulation network, not pedestrian or driving navigation.

## Reproduce street graph

Request this query from `https://overpass-api.de/api/interpreter` and save the JSON locally:

```text
[out:json][timeout:45];
way["highway"~"^(residential|tertiary|secondary|primary|unclassified|pedestrian|footway|living_street)$"](51.08,71.30,51.22,71.58);
out geom;
```

Then, from `akim/ui`:

```sh
npx tsx scripts/prepare-roads.ts /path/to/overpass-roads.json
npm test
```

The preprocessing filters the response to the three street classes above and clips vertices against real district geometry. Residents' homes, work/study/errand and leisure destinations are randomly assigned street vertices with a reproducible seed. Journeys follow connected segments. Ages, names, destinations, timings, transport behavior and opinions are fictional. The graph ignores one-way restrictions and access rules. The daily animation uses simplified routes; the optional mobility comparison adds the assumed routing costs and loads described below.

## Complaint gazetteer

`server/astana-places.json` is also derived from the same OSM response and shared under ODbL. It groups 1,112 named streets using available Kazakh/Russian/English and alternative names. Coordinates are real geometry vertices near each street's mean position. Reproduce with:

```sh
npx tsx scripts/prepare-gazetteer.ts /path/to/overpass-roads.json
```

`server/locations.ts` matches aliases and common inflections before Jev chooses among at most eight candidates plus “unlocated”. District candidates use the bundled district centers. A pin represents an approximate point on the named street or district, not the precise complaint location. Unknown or ambiguous places remain unlocated. The source bounding box is incomplete for the wider city.

## Mobility assumptions

`src/mobility.ts` compares the same 2,000 morning commutes before and after eligible measures. Initial mode shares: 50% car, 30% bus, 20% walk. Free speeds: 32, 18 and 4.5 km/h. Bus wait: 7 minutes. Congestion multiplier: `1 + 0.15 × min(3, flow / capacity)^4`, with 18 synthetic vehicle equivalents per edge and bus weight 0.08. Junction delay: 0.15 minutes (M2: 0.05).

M1: bus speed 22 km/h, wait 4 minutes, 10 percentage points of the target district population switch from car to bus, car capacity 13.5. M3: idealized transit speed 26 km/h, wait 3 minutes, 30 percentage points switch from car. Exact constants are scenario assumptions, unrelated to measured street capacity or real transit timetables. Two rerouting passes use weighted Dijkstra, followed by final load/cost evaluation. This is not an equilibrium assignment. “Congested” denotes modeled load above assumed capacity, not observed traffic.

Street connectivity is real; demand, mode choice, traffic and policy response are fictional. Separate district components omit cross-district journeys, and pedestrian/bus movements share the simplified main-street graph. LRT is represented only by assumed transit benefits, not a newly drawn railway. The simulation must not be used as a calibrated engineering forecast.
