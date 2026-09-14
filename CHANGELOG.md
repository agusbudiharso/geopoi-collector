# Changelog

## 1.1.0 — 2026-09-12
- Added a Geometry Type selector: Point, Line, and Polygon.
- Preserved the existing Point workflow for OpenStreetMap and Google Places.
- Added OpenStreetMap/Overpass Line collection for roads, rivers, railways, paths, and coastline.
- Added OpenStreetMap/Overpass Polygon collection for buildings, landuse, water, forest, residential, industrial, commercial, and park features.
- Added spatial clipping/filtering for Line and Polygon results.
- Added GeoPackage export for all supported geometry types.
- Kept compatibility metadata for QGIS 3.22–4.99 and qgis.PyQt/Qt6-safe imports.
- Polygon mode intentionally uses closed OSM ways only in this release to avoid unreliable multipolygon relation reconstruction.

## 1.0.7 — 2026-09-12
- Rebuilt the installable package with explicit `qgisMaximumVersion=4.99` metadata.
- Version bumped so QGIS does not keep identifying the older 1.0.5 installation.
- Confirmed that Python GUI imports use the version-independent `qgis.PyQt` namespace.
- Kept `exec()` calls for Qt6 compatibility.
- No changes to POI workflow, providers, categories, or output schema.

## 1.0.6 — 2026-09-11
- Declared compatibility with QGIS 4.x by setting the supported QGIS range to 3.22–4.99.
- Retained the Qt6-compatible code validated in v1.0.5.
- No changes to plugin workflow, POI categories, data providers, or output schema.

## 1.0.5 — 2026-09-10
- Updated Qt/PyQt and QGIS enum references reported by the QGIS Qt6 compatibility checker.
- Replaced deprecated `exec_()` calls with `exec()`.
- No changes to the plugin workflow, POI categories, data providers, or output schema.

## 1.0.4
- Switched HTTP networking to QGIS QgsNetworkAccessManager for QGIS proxy compatibility and repository publication readiness.
- No changes to the plugin workflow, POI categories, or output schema.

## 1.0.3 — 2026-09-09
- Converted the complete user interface to English for public release.
- Retained the stable category drop-down workflow.
- Updated English documentation for GitHub distribution.

## 1.0.2 — 2026-09-09
- Restored the simple category drop-down used in the original plugin.
- Users no longer need to type category names manually.
- No experimental features added.

## 1.0.0
- Initial public development release.
