# GeoPOI Collector

GeoPOI Collector is a QGIS plugin for collecting vector features directly into QGIS.

## Version 1.1.0

### Point
- OpenStreetMap / Overpass
- Google Places API
- Categories: hospital, clinic, pharmacy, school, university, place of worship, bank, ATM, restaurant, cafe, marketplace, fuel, police, fire station, government, hotel, tourism

### Line — OpenStreetMap / Overpass
- Roads
- Rivers
- Railways
- Paths
- Coastline

### Polygon — OpenStreetMap / Overpass
- Buildings
- Landuse
- Water
- Forest
- Residential
- Industrial
- Commercial
- Park

The search area can be the current QGIS canvas extent or an active polygon layer. Results can be clipped/filtered to the search area and optionally saved to GeoPackage.

Google Places supports Point features only and requires the user's own API key. The plugin does not scrape Google Maps.

### Polygon note
Version 1.1.0 intentionally builds polygons from **closed OSM ways**. Complex OSM multipolygon relations are not reconstructed in this release, avoiding invalid or misleading geometry during the first stable multi-geometry extension.

## Compatibility
- QGIS 3.22–4.99 (metadata target)
- Uses `qgis.PyQt` for Qt5/Qt6 portability

## License
GNU GPL v2 or later.
