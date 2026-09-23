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

The preprocessing filters the response to the three street classes above and clips vertices against real district geometry. Residents' homes, work/study/errand and leisure destinations are randomly assigned street vertices with a reproducible seed. Journeys follow connected segments. Ages, names, destinations, timings, transport behavior and opinions are fictional. The graph ignores one-way restrictions, access rules, routing costs and traffic.
