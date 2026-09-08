# GeoPOI Collector

GeoPOI Collector is a QGIS plugin for collecting Points of Interest (POIs) as GIS point layers.

## Data providers
- **OpenStreetMap / Overpass API** — no API key required.
- **Google Places API** — optional; requires the user's own API key.

The plugin does **not** scrape the Google Maps website.

## Features
- Search using the current QGIS map canvas extent.
- Search using a polygon layer.
- Simple category drop-down; users do not need to type category codes.
- Categories include hospitals, clinics, pharmacies, schools, universities, places of worship, banks, ATMs, restaurants, cafés, marketplaces, fuel stations, police, fire stations, government offices, hotels and tourism.
- Optional filtering to remove points outside the search area.
- Optional direct saving to GeoPackage.
- Output attributes include provider, POI ID, name, category, address, latitude, longitude, rating and review count where available.

## Installation
1. Open QGIS.
2. Go to **Plugins → Manage and Install Plugins**.
3. Select **Install from ZIP**.
4. Choose the GeoPOI Collector ZIP package.
5. Enable **GeoPOI Collector**.

## Usage
Open **Vector → GeoPOI Collector** or use the plugin toolbar button.

1. Choose a provider.
2. Choose the search area.
3. Select a POI category from the drop-down.
4. For Google Places, enter your own valid API key.
5. Click **Collect POI**.

The result is added to QGIS as an EPSG:4326 point layer.

## Saving results
Enable **Automatically save to GeoPackage**, or right-click the resulting layer and choose:
**Export → Save Features As…**

## Data-provider notes
OpenStreetMap data is subject to the OpenStreetMap licence and attribution requirements.
The public Overpass service may time out on very large requests.

Google Places usage is subject to Google Maps Platform terms, quotas, billing,
attribution, storage/caching and other applicable policies. Users are responsible
for compliance with those terms.

## Compatibility
QGIS 3.22 or later.

## License
GNU General Public License v2 or later.

## Author
**Agus Santoso Budiharso**  
Universitas Prisma Manado
