def classFactory(iface):
    from .poi_collector import POICollectorPlugin
    return POICollectorPlugin(iface)
