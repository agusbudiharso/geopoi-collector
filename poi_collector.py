# -*- coding: utf-8 -*-
import json
import math
from qgis.PyQt.QtCore import Qt, QVariant, QEventLoop, QTimer, QUrl, QByteArray
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QMessageBox, QSpinBox, QCheckBox, QProgressBar,
    QFileDialog
)
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsField, QgsFields, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsWkbTypes, QgsVectorFileWriter,
    QgsNetworkAccessManager
)


class POICollectorDialog(QDialog):
    POINT_CATEGORIES = [
        "hospital", "clinic", "pharmacy", "school", "university",
        "place_of_worship", "bank", "atm", "restaurant", "cafe",
        "marketplace", "fuel", "police", "fire_station", "government",
        "hotel", "tourism"
    ]

    LINE_CATEGORIES = [
        "roads", "rivers", "railways", "paths", "coastline"
    ]

    POLYGON_CATEGORIES = [
        "buildings", "landuse", "water", "forest", "residential",
        "industrial", "commercial", "park"
    ]

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("GeoPOI Collector")
        self.resize(590, 500)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "<b>GeoPOI Collector</b><br>"
            "Collect Point, Line, and Polygon features from OpenStreetMap; "
            "Google Places remains available for Point features."
        ))

        row = QHBoxLayout()
        row.addWidget(QLabel("Geometry type:"))
        self.geometry_type = QComboBox()
        self.geometry_type.addItems(["Point", "Line", "Polygon"])
        self.geometry_type.currentIndexChanged.connect(self._update_mode_ui)
        row.addWidget(self.geometry_type)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Provider:"))
        self.provider = QComboBox()
        self.provider.addItems(["OpenStreetMap (Overpass)", "Google Places API"])
        self.provider.currentIndexChanged.connect(self._update_provider_ui)
        row.addWidget(self.provider)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Search area:"))
        self.area_mode = QComboBox()
        self.area_mode.addItems(["Current map canvas extent", "Selected polygon layer"])
        row.addWidget(self.area_mode)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Category:"))
        self.category = QComboBox()
        row.addWidget(self.category)
        layout.addLayout(row)

        self.category_note = QLabel()
        layout.addWidget(self.category_note)

        row = QHBoxLayout()
        self.api_label = QLabel("Google API Key:")
        row.addWidget(self.api_label)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Required only for Google Places")
        row.addWidget(self.api_key)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.radius_label = QLabel("Google radius per grid (meters):")
        row.addWidget(self.radius_label)
        self.radius = QSpinBox()
        self.radius.setRange(500, 50000)
        self.radius.setValue(3000)
        self.radius.setSingleStep(500)
        row.addWidget(self.radius)
        layout.addLayout(row)

        self.only_inside = QCheckBox("Clip/filter results to the search area")
        self.only_inside.setChecked(True)
        layout.addWidget(self.only_inside)

        self.auto_save = QCheckBox("Automatically save to GeoPackage")
        self.auto_save.setChecked(False)
        layout.addWidget(self.auto_save)

        row = QHBoxLayout()
        self.out_path = QLineEdit()
        self.out_path.setPlaceholderText("Choose .gpkg file (optional)")
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._choose_output)
        row.addWidget(self.out_path)
        row.addWidget(self.browse_btn)
        layout.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.btn = QPushButton("Collect Features")
        self.btn.clicked.connect(self.run_fetch)
        layout.addWidget(self.btn)

        layout.addWidget(QLabel(
            "<small>OpenStreetMap/Overpass is used for Point, Line, and Polygon features. "
            "Google Places supports Point features only and requires your own API key.</small>"
        ))

        self._update_mode_ui()

    def _update_mode_ui(self):
        geom = self.geometry_type.currentText()
        self.category.clear()
        if geom == "Point":
            self.category.addItems(self.POINT_CATEGORIES)
            self.category_note.setText("<small>Select a POI category.</small>")
            self.provider.setEnabled(True)
        elif geom == "Line":
            self.category.addItems(self.LINE_CATEGORIES)
            self.category_note.setText("<small>Line features are collected from OpenStreetMap/Overpass.</small>")
            self.provider.setCurrentIndex(0)
            self.provider.setEnabled(False)
        else:
            self.category.addItems(self.POLYGON_CATEGORIES)
            self.category_note.setText("<small>Polygon features are collected from closed OpenStreetMap ways.</small>")
            self.provider.setCurrentIndex(0)
            self.provider.setEnabled(False)
        self._update_provider_ui()

    def _update_provider_ui(self):
        google = self.geometry_type.currentText() == "Point" and self.provider.currentIndex() == 1
        self.api_label.setEnabled(google)
        self.api_key.setEnabled(google)
        self.radius_label.setEnabled(google)
        self.radius.setEnabled(google)

    def _choose_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save GeoPackage", "", "GeoPackage (*.gpkg)"
        )
        if path:
            if not path.lower().endswith(".gpkg"):
                path += ".gpkg"
            self.out_path.setText(path)

    def _target_geometry_wgs84(self):
        canvas = self.iface.mapCanvas()
        project = QgsProject.instance()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

        if self.area_mode.currentIndex() == 0:
            extent = canvas.extent()
            src_crs = canvas.mapSettings().destinationCrs()
            tr = QgsCoordinateTransform(src_crs, wgs84, project)
            p1 = tr.transform(QgsPointXY(extent.xMinimum(), extent.yMinimum()))
            p2 = tr.transform(QgsPointXY(extent.xMaximum(), extent.yMaximum()))
            xmin, xmax = sorted([p1.x(), p2.x()])
            ymin, ymax = sorted([p1.y(), p2.y()])
            geom = QgsGeometry.fromPolygonXY([[
                QgsPointXY(xmin, ymin), QgsPointXY(xmax, ymin),
                QgsPointXY(xmax, ymax), QgsPointXY(xmin, ymax),
                QgsPointXY(xmin, ymin)
            ]])
            return geom, (xmin, ymin, xmax, ymax)

        layer = self.iface.activeLayer()
        if (not layer or layer.type() != layer.VectorLayer or
                QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.GeometryType.PolygonGeometry):
            raise Exception("Activate a polygon layer first.")

        feats = list(layer.selectedFeatures()) or list(layer.getFeatures())
        if not feats:
            raise Exception("The polygon layer has no features.")

        geom = QgsGeometry.unaryUnion([f.geometry() for f in feats])
        if layer.crs() != wgs84:
            tr = QgsCoordinateTransform(layer.crs(), wgs84, project)
            geom.transform(tr)
        b = geom.boundingBox()
        return geom, (b.xMinimum(), b.yMinimum(), b.xMaximum(), b.yMaximum())

    def _network_post(self, url, payload, headers, timeout_ms=60000, error_prefix="Network request"):
        request = QNetworkRequest(QUrl(url))
        for name, value in headers.items():
            request.setRawHeader(QByteArray(name), QByteArray(value))

        manager = QgsNetworkAccessManager.instance()
        reply = manager.post(request, payload)
        loop = QEventLoop()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        reply.finished.connect(loop.quit)
        timer.start(timeout_ms)
        loop.exec()

        if not timer.isActive():
            reply.abort()
            reply.deleteLater()
            raise Exception(f"{error_prefix} timed out after {timeout_ms // 1000} seconds.")

        timer.stop()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        body = bytes(reply.readAll())
        error_code = reply.error()
        error_text = reply.errorString()
        reply.deleteLater()

        if error_code != QNetworkReply.NetworkError.NoError:
            detail = body.decode("utf-8", errors="ignore").strip()
            status_text = f" HTTP {status}" if status else ""
            if detail:
                raise Exception(f"{error_prefix}{status_text}: {detail[:400]}")
            raise Exception(f"{error_prefix}{status_text}: {error_text}")

        return body

    @staticmethod
    def _osm_point_tag(category):
        catmap = {
            "hospital": ('amenity', 'hospital'), "clinic": ('amenity', 'clinic'),
            "pharmacy": ('amenity', 'pharmacy'), "school": ('amenity', 'school'),
            "university": ('amenity', 'university'), "place_of_worship": ('amenity', 'place_of_worship'),
            "bank": ('amenity', 'bank'), "atm": ('amenity', 'atm'),
            "restaurant": ('amenity', 'restaurant'), "cafe": ('amenity', 'cafe'),
            "marketplace": ('amenity', 'marketplace'), "fuel": ('amenity', 'fuel'),
            "police": ('amenity', 'police'), "fire_station": ('amenity', 'fire_station'),
            "government": ('office', 'government'), "hotel": ('tourism', 'hotel'),
            "tourism": ('tourism', '')
        }
        return catmap.get(category, ('amenity', category))

    @staticmethod
    def _osm_linear_tag(category):
        return {
            "roads": ('highway', ''),
            "rivers": ('waterway', 'river'),
            "railways": ('railway', ''),
            "paths": ('highway', 'path'),
            "coastline": ('natural', 'coastline')
        }[category]

    @staticmethod
    def _osm_polygon_tag(category):
        return {
            "buildings": ('building', ''),
            "landuse": ('landuse', ''),
            "water": ('natural', 'water'),
            "forest": ('landuse', 'forest'),
            "residential": ('landuse', 'residential'),
            "industrial": ('landuse', 'industrial'),
            "commercial": ('landuse', 'commercial'),
            "park": ('leisure', 'park')
        }[category]

    @staticmethod
    def _tag_expression(key, value):
        return f'["{key}"]' if value == "" else f'["{key}"="{value}"]'

    def _overpass(self, query, timeout_ms=90000):
        data = QUrl.toPercentEncoding(query)
        payload = QByteArray(b"data=") + data
        headers = {
            b"Content-Type": b"application/x-www-form-urlencoded; charset=UTF-8",
            b"User-Agent": b"GeoPOI-Collector/1.1.0"
        }
        raw_response = self._network_post(
            "https://overpass-api.de/api/interpreter", payload, headers,
            timeout_ms=timeout_ms, error_prefix="OpenStreetMap Overpass"
        )
        return json.loads(raw_response.decode("utf-8"))

    def _fetch_osm_points(self, bbox, category):
        xmin, ymin, xmax, ymax = bbox
        key, value = self._osm_point_tag(category)
        tag = self._tag_expression(key, value)
        s, w, n, e = ymin, xmin, ymax, xmax
        query = f"""
        [out:json][timeout:60];
        (
          node{tag}({s},{w},{n},{e});
          way{tag}({s},{w},{n},{e});
          relation{tag}({s},{w},{n},{e});
        );
        out center tags;
        """
        obj = self._overpass(query)
        out = []
        for el in obj.get("elements", []):
            if "lat" in el and "lon" in el:
                lat, lon = el["lat"], el["lon"]
            elif "center" in el:
                lat, lon = el["center"].get("lat"), el["center"].get("lon")
            else:
                continue
            if lat is None or lon is None:
                continue
            tags = el.get("tags", {})
            out.append({
                "provider": "OSM", "id": str(el.get("id", "")),
                "name": tags.get("name", ""),
                "category": value or tags.get(key, key),
                "address": self._osm_address(tags), "lat": float(lat),
                "lon": float(lon), "rating": None, "reviews": None
            })
        return out

    def _fetch_osm_lines(self, bbox, category):
        xmin, ymin, xmax, ymax = bbox
        key, value = self._osm_linear_tag(category)
        tag = self._tag_expression(key, value)
        s, w, n, e = ymin, xmin, ymax, xmax
        query = f"""
        [out:json][timeout:90];
        way{tag}({s},{w},{n},{e});
        out geom tags;
        """
        obj = self._overpass(query, timeout_ms=120000)
        rows = []
        for el in obj.get("elements", []):
            coords = el.get("geometry", [])
            if len(coords) < 2:
                continue
            points = [QgsPointXY(float(c["lon"]), float(c["lat"])) for c in coords if "lat" in c and "lon" in c]
            if len(points) < 2:
                continue
            tags = el.get("tags", {})
            rows.append({
                "provider": "OSM", "id": str(el.get("id", "")),
                "name": tags.get("name", ""),
                "category": value or tags.get(key, key),
                "osm_type": "way", "geometry": QgsGeometry.fromPolylineXY(points)
            })
        return rows

    def _fetch_osm_polygons(self, bbox, category):
        xmin, ymin, xmax, ymax = bbox
        key, value = self._osm_polygon_tag(category)
        tag = self._tag_expression(key, value)
        s, w, n, e = ymin, xmin, ymax, xmax
        query = f"""
        [out:json][timeout:90];
        way{tag}({s},{w},{n},{e});
        out geom tags;
        """
        obj = self._overpass(query, timeout_ms=120000)
        rows = []
        for el in obj.get("elements", []):
            coords = el.get("geometry", [])
            if len(coords) < 4:
                continue
            points = [QgsPointXY(float(c["lon"]), float(c["lat"])) for c in coords if "lat" in c and "lon" in c]
            if len(points) < 4:
                continue
            # Only closed OSM ways are safe to interpret as polygons.
            if points[0].x() != points[-1].x() or points[0].y() != points[-1].y():
                continue
            tags = el.get("tags", {})
            rows.append({
                "provider": "OSM", "id": str(el.get("id", "")),
                "name": tags.get("name", ""),
                "category": value or tags.get(key, key),
                "osm_type": "way", "geometry": QgsGeometry.fromPolygonXY([points])
            })
        return rows

    @staticmethod
    def _osm_address(tags):
        parts = []
        for k in ["addr:housenumber", "addr:street", "addr:suburb", "addr:city"]:
            v = tags.get(k)
            if v:
                parts.append(v)
        return ", ".join(parts)

    def _grid_centers(self, bbox, radius_m):
        xmin, ymin, xmax, ymax = bbox
        mid_lat = (ymin + ymax) / 2.0
        step_m = max(radius_m * 1.35, 500)
        dlat = step_m / 111320.0
        dlon = step_m / (111320.0 * max(math.cos(math.radians(mid_lat)), 0.2))
        pts = []
        y = ymin
        while y <= ymax:
            x = xmin
            while x <= xmax:
                pts.append((y, x))
                x += dlon
            y += dlat
        if not pts:
            pts = [((ymin + ymax) / 2, (xmin + xmax) / 2)]
        return pts

    def _fetch_google(self, bbox, category, api_key, radius_m):
        if not api_key:
            raise Exception("Enter your Google Places API key.")
        centers = self._grid_centers(bbox, radius_m)
        results = {}
        self.progress.setRange(0, max(len(centers), 1))
        type_map = {
            "hospital": "hospital", "clinic": "medical_clinic", "pharmacy": "pharmacy",
            "school": "school", "university": "university", "place_of_worship": "place_of_worship",
            "bank": "bank", "atm": "atm", "restaurant": "restaurant", "cafe": "cafe",
            "marketplace": "market", "fuel": "gas_station", "police": "police",
            "fire_station": "fire_station", "government": "government_office",
            "hotel": "hotel", "tourism": "tourist_attraction"
        }
        included_type = type_map.get(category, category)
        for i, (lat, lon) in enumerate(centers, start=1):
            body = {
                "includedTypes": [included_type], "maxResultCount": 20,
                "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": float(radius_m)}}
            }
            raw = QByteArray(json.dumps(body).encode("utf-8"))
            headers = {
                b"Content-Type": b"application/json",
                b"X-Goog-Api-Key": api_key.encode("utf-8"),
                b"X-Goog-FieldMask": b"places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.primaryType"
            }
            raw_response = self._network_post(
                "https://places.googleapis.com/v1/places:searchNearby", raw, headers,
                timeout_ms=60000, error_prefix="Google Places"
            )
            obj = json.loads(raw_response.decode("utf-8"))
            for p in obj.get("places", []):
                loc = p.get("location", {})
                pid = p.get("id", "")
                if not pid or "latitude" not in loc or "longitude" not in loc:
                    continue
                dn = p.get("displayName", {})
                results[pid] = {
                    "provider": "Google", "id": pid, "name": dn.get("text", ""),
                    "category": p.get("primaryType", included_type), "address": p.get("formattedAddress", ""),
                    "lat": float(loc["latitude"]), "lon": float(loc["longitude"]),
                    "rating": p.get("rating"), "reviews": p.get("userRatingCount")
                }
            self.progress.setValue(i)
        return list(results.values())

    def _make_point_layer(self, rows, area_geom=None, layer_name="GeoPOI_Result"):
        layer = QgsVectorLayer("Point?crs=EPSG:4326", layer_name, "memory")
        pr = layer.dataProvider()
        fields = QgsFields()
        for name, typ in [
            ("provider", QVariant.String), ("poi_id", QVariant.String), ("name", QVariant.String),
            ("category", QVariant.String), ("address", QVariant.String), ("latitude", QVariant.Double),
            ("longitude", QVariant.Double), ("rating", QVariant.Double), ("reviews", QVariant.Int)
        ]:
            fields.append(QgsField(name, typ))
        pr.addAttributes(fields)
        layer.updateFields()
        feats = []
        for r in rows:
            g = QgsGeometry.fromPointXY(QgsPointXY(r["lon"], r["lat"]))
            if self.only_inside.isChecked() and area_geom is not None and not area_geom.contains(g):
                continue
            f = QgsFeature(layer.fields())
            f.setGeometry(g)
            f.setAttributes([
                r.get("provider", ""), r.get("id", ""), r.get("name", ""), r.get("category", ""),
                r.get("address", ""), r.get("lat"), r.get("lon"), r.get("rating"), r.get("reviews")
            ])
            feats.append(f)
        pr.addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer, len(feats)

    def _make_osm_geometry_layer(self, rows, geometry_type, area_geom=None, layer_name="GeoOSM_Result"):
        uri = "LineString?crs=EPSG:4326" if geometry_type == "Line" else "Polygon?crs=EPSG:4326"
        layer = QgsVectorLayer(uri, layer_name, "memory")
        pr = layer.dataProvider()
        fields = QgsFields()
        fields.append(QgsField("provider", QVariant.String))
        fields.append(QgsField("osm_id", QVariant.String))
        fields.append(QgsField("osm_type", QVariant.String))
        fields.append(QgsField("name", QVariant.String))
        fields.append(QgsField("category", QVariant.String))
        pr.addAttributes(fields)
        layer.updateFields()

        feats = []
        for r in rows:
            g = QgsGeometry(r["geometry"])
            if self.only_inside.isChecked() and area_geom is not None:
                if not g.intersects(area_geom):
                    continue
                clipped = g.intersection(area_geom)
                if clipped.isEmpty():
                    continue
                g = clipped
            f = QgsFeature(layer.fields())
            f.setGeometry(g)
            f.setAttributes([
                r.get("provider", "OSM"), r.get("id", ""), r.get("osm_type", "way"),
                r.get("name", ""), r.get("category", "")
            ])
            feats.append(f)

        pr.addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer, len(feats)

    def _save_layer_gpkg(self, layer, path):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer.name()
        options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
        ctx = QgsProject.instance().transformContext()
        err, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(layer, path, ctx, options)
        if err != QgsVectorFileWriter.WriterError.NoError:
            raise Exception(f"Failed to save GeoPackage: {msg}")

    def run_fetch(self):
        self.btn.setEnabled(False)
        try:
            area_geom, bbox = self._target_geometry_wgs84()
            geometry_type = self.geometry_type.currentText()
            category = self.category.currentText().strip()
            if not category:
                raise Exception("No category selected.")

            self.progress.setValue(0)
            provider_name = "OSM"

            if geometry_type == "Point":
                if self.provider.currentIndex() == 0:
                    self.progress.setRange(0, 0)
                    rows = self._fetch_osm_points(bbox, category)
                else:
                    provider_name = "Google"
                    rows = self._fetch_google(bbox, category, self.api_key.text().strip(), self.radius.value())
                layer_name = f"GeoPOI_{provider_name}_{category}"
                layer, count = self._make_point_layer(rows, area_geom, layer_name)
            elif geometry_type == "Line":
                self.progress.setRange(0, 0)
                rows = self._fetch_osm_lines(bbox, category)
                layer_name = f"GeoOSM_Line_{category}"
                layer, count = self._make_osm_geometry_layer(rows, "Line", area_geom, layer_name)
            else:
                self.progress.setRange(0, 0)
                rows = self._fetch_osm_polygons(bbox, category)
                layer_name = f"GeoOSM_Polygon_{category}"
                layer, count = self._make_osm_geometry_layer(rows, "Polygon", area_geom, layer_name)

            if self.auto_save.isChecked():
                path = self.out_path.text().strip()
                if not path:
                    raise Exception("Choose a GeoPackage output file first.")
                self._save_layer_gpkg(layer, path)

            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            noun = "features" if geometry_type != "Point" else "POIs"
            msg = f"{count} {noun} were added to the QGIS layer."
            if geometry_type == "Polygon":
                msg += "\nPolygon mode currently uses closed OSM ways for reliable geometry creation."
            if self.auto_save.isChecked():
                msg += "\nSaved to: " + self.out_path.text().strip()
            else:
                msg += "\nTo save permanently: right-click the layer → Export → Save Features As."
            QMessageBox.information(self, "Completed", msg)
        except Exception as e:
            QMessageBox.critical(self, "GeoPOI Collector", str(e))
        finally:
            self.btn.setEnabled(True)


class POICollectorPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dlg = None

    def initGui(self):
        self.action = QAction("GeoPOI Collector", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToVectorMenu("&GeoPOI Collector", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginVectorMenu("&GeoPOI Collector", self.action)
            self.iface.removeToolBarIcon(self.action)

    def run(self):
        self.dlg = POICollectorDialog(self.iface, self.iface.mainWindow())
        self.dlg.exec()
