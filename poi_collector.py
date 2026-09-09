
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
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("GeoPOI Collector")
        self.resize(560, 420)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "<b>GeoPOI Collector</b><br>"
            "Collect Points of Interest from OpenStreetMap or Google Places API."
        ))

        row = QHBoxLayout()
        row.addWidget(QLabel("Provider:"))
        self.provider = QComboBox()
        self.provider.addItems(["OpenStreetMap (Overpass)", "Google Places API"])
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
        self.category.addItems([
            "hospital",
            "clinic",
            "pharmacy",
            "school",
            "university",
            "place_of_worship",
            "bank",
            "atm",
            "restaurant",
            "cafe",
            "marketplace",
            "fuel",
            "police",
            "fire_station",
            "government",
            "hotel",
            "tourism"
        ])
        row.addWidget(self.category)
        layout.addLayout(row)

        layout.addWidget(QLabel(
            "<small>Select a POI category from the list.</small>"
        ))

        row = QHBoxLayout()
        row.addWidget(QLabel("Google API Key:"))
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Required only for Google Places")
        row.addWidget(self.api_key)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Google radius per grid (meters):"))
        self.radius = QSpinBox()
        self.radius.setRange(500, 50000)
        self.radius.setValue(3000)
        self.radius.setSingleStep(500)
        row.addWidget(self.radius)
        layout.addLayout(row)

        self.only_inside = QCheckBox("Remove points outside the search area")
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

        self.btn = QPushButton("Collect POI")
        self.btn.clicked.connect(self.run_fetch)
        layout.addWidget(self.btn)

        layout.addWidget(QLabel(
            "<small>Catatan: OpenStreetMap cocok untuk pengumpulan data terbuka. "
            "Google Places memerlukan API key milik Anda dan tunduk pada ketentuan Google Maps Platform.</small>"
        ))

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
        if not layer or layer.type() != layer.VectorLayer or QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.GeometryType.PolygonGeometry:
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

    def _fetch_osm(self, bbox, category):
        xmin, ymin, xmax, ymax = bbox
        # Map friendly names to OSM tags
        catmap = {
            "hospital": ('amenity', 'hospital'),
            "clinic": ('amenity', 'clinic'),
            "pharmacy": ('amenity', 'pharmacy'),
            "school": ('amenity', 'school'),
            "university": ('amenity', 'university'),
            "place_of_worship": ('amenity', 'place_of_worship'),
            "bank": ('amenity', 'bank'),
            "atm": ('amenity', 'atm'),
            "restaurant": ('amenity', 'restaurant'),
            "cafe": ('amenity', 'cafe'),
            "marketplace": ('amenity', 'marketplace'),
            "fuel": ('amenity', 'fuel'),
            "police": ('amenity', 'police'),
            "fire_station": ('amenity', 'fire_station'),
            "government": ('office', 'government'),
            "hotel": ('tourism', 'hotel'),
            "tourism": ('tourism', '')
        }
        key, value = catmap.get(category, ('amenity', category))
        tag = f'["{key}"]' if value == "" else f'["{key}"="{value}"]'
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
        data = QUrl.toPercentEncoding(query)
        payload = QByteArray(b"data=") + data
        headers = {
            b"Content-Type": b"application/x-www-form-urlencoded; charset=UTF-8",
            b"User-Agent": b"GeoPOI-Collector/1.0.5"
        }
        raw_response = self._network_post(
            "https://overpass-api.de/api/interpreter",
            payload,
            headers,
            timeout_ms=90000
        )
        obj = json.loads(raw_response.decode("utf-8"))

        out = []
        for el in obj.get("elements", []):
            if "lat" in el and "lon" in el:
                lat, lon = el["lat"], el["lon"]
            elif "center" in el:
                lat, lon = el["center"].get("lat"), el["center"].get("lon")
            else:
                continue
            tags = el.get("tags", {})
            out.append({
                "provider": "OSM",
                "id": str(el.get("id", "")),
                "name": tags.get("name", ""),
                "category": value or tags.get(key, key),
                "address": self._osm_address(tags),
                "lat": float(lat),
                "lon": float(lon),
                "rating": None,
                "reviews": None
            })
        return out

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
        # spacing ~ 1.4 radius gives overlap
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
        # ensure at least center
        if not pts:
            pts = [((ymin+ymax)/2, (xmin+xmax)/2)]
        return pts

    def _fetch_google(self, bbox, category, api_key, radius_m):
        if not api_key:
            raise Exception("Enter your Google Places API key.")

        centers = self._grid_centers(bbox, radius_m)
        results = {}
        self.progress.setRange(0, max(len(centers), 1))

        type_map = {
            "hospital": "hospital",
            "clinic": "medical_clinic",
            "pharmacy": "pharmacy",
            "school": "school",
            "university": "university",
            "place_of_worship": "place_of_worship",
            "bank": "bank",
            "atm": "atm",
            "restaurant": "restaurant",
            "cafe": "cafe",
            "marketplace": "market",
            "fuel": "gas_station",
            "police": "police",
            "fire_station": "fire_station",
            "government": "government_office",
            "hotel": "hotel",
            "tourism": "tourist_attraction"
        }
        included_type = type_map.get(category, category)

        for i, (lat, lon) in enumerate(centers, start=1):
            body = {
                "includedTypes": [included_type],
                "maxResultCount": 20,
                "locationRestriction": {
                    "circle": {
                        "center": {"latitude": lat, "longitude": lon},
                        "radius": float(radius_m)
                    }
                }
            }
            raw = QByteArray(json.dumps(body).encode("utf-8"))
            headers = {
                b"Content-Type": b"application/json",
                b"X-Goog-Api-Key": api_key.encode("utf-8"),
                b"X-Goog-FieldMask": b"places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.primaryType"
            }
            raw_response = self._network_post(
                "https://places.googleapis.com/v1/places:searchNearby",
                raw,
                headers,
                timeout_ms=60000,
                error_prefix="Google Places"
            )
            obj = json.loads(raw_response.decode("utf-8"))

            for p in obj.get("places", []):
                loc = p.get("location", {})
                pid = p.get("id", "")
                if not pid or "latitude" not in loc or "longitude" not in loc:
                    continue
                dn = p.get("displayName", {})
                results[pid] = {
                    "provider": "Google",
                    "id": pid,
                    "name": dn.get("text", ""),
                    "category": p.get("primaryType", included_type),
                    "address": p.get("formattedAddress", ""),
                    "lat": float(loc["latitude"]),
                    "lon": float(loc["longitude"]),
                    "rating": p.get("rating"),
                    "reviews": p.get("userRatingCount")
                }
            self.progress.setValue(i)

        return list(results.values())

    def _make_layer(self, rows, area_geom=None, layer_name="GeoPOI_Result"):
        layer = QgsVectorLayer("Point?crs=EPSG:4326", layer_name, "memory")
        pr = layer.dataProvider()
        fields = QgsFields()
        fields.append(QgsField("provider", QVariant.String))
        fields.append(QgsField("poi_id", QVariant.String))
        fields.append(QgsField("name", QVariant.String))
        fields.append(QgsField("category", QVariant.String))
        fields.append(QgsField("address", QVariant.String))
        fields.append(QgsField("latitude", QVariant.Double))
        fields.append(QgsField("longitude", QVariant.Double))
        fields.append(QgsField("rating", QVariant.Double))
        fields.append(QgsField("reviews", QVariant.Int))
        pr.addAttributes(fields)
        layer.updateFields()

        feats = []
        for r in rows:
            pt = QgsPointXY(r["lon"], r["lat"])
            g = QgsGeometry.fromPointXY(pt)
            if self.only_inside.isChecked() and area_geom is not None and not area_geom.contains(g):
                continue
            f = QgsFeature(layer.fields())
            f.setGeometry(g)
            f.setAttributes([
                r.get("provider",""), r.get("id",""), r.get("name",""),
                r.get("category",""), r.get("address",""),
                r.get("lat"), r.get("lon"), r.get("rating"), r.get("reviews")
            ])
            feats.append(f)

        pr.addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return len(feats)

    def _save_layer_gpkg(self, layer, path):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer.name()
        options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
        ctx = QgsProject.instance().transformContext()
        err, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, path, ctx, options
        )
        if err != QgsVectorFileWriter.WriterError.NoError:
            raise Exception(f"Failed to save GeoPackage: {msg}")

    def run_fetch(self):
        self.btn.setEnabled(False)
        try:
            area_geom, bbox = self._target_geometry_wgs84()
            category = self.category.currentText().strip()
            if not category:
                raise Exception("No POI category selected.")

            self.progress.setValue(0)

            if self.provider.currentIndex() == 0:
                self.progress.setRange(0, 0)
                rows = self._fetch_osm(bbox, category)
            else:
                rows = self._fetch_google(
                    bbox, category,
                    self.api_key.text().strip(),
                    self.radius.value()
                )

            self.progress.setRange(0, 100)
            provider_name = "OSM" if self.provider.currentIndex() == 0 else "Google"
            layer_name = "GeoPOI_" + provider_name + "_" + category

            count = self._make_layer(rows, area_geom, layer_name=layer_name)
            layer = QgsProject.instance().mapLayersByName(layer_name)[-1]

            if self.auto_save.isChecked():
                path = self.out_path.text().strip()
                if not path:
                    raise Exception("Choose a GeoPackage output file first.")
                self._save_layer_gpkg(layer, path)

            self.progress.setValue(100)

            msg = f"{count} POIs were added to the QGIS layer."
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
