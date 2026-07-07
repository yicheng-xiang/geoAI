import os

DATA_ROOT = r"D:\geoAI\GIS_agent\data"

VECTOR_DATASETS = {
    "hong_kong_districts": {
        "path": os.path.join(DATA_ROOT, "HKDistrict18.shp"),
        "crs": "EPSG:4326",
        "description": "Hong Kong 18-district administrative boundaries.",
        "kind": "polygon",
    },
    "osm_land_polygons": {
        "path": os.path.join(
            DATA_ROOT,
            "land-polygons-complete-4326",
            "land-polygons-complete-4326",
            "land_polygons.shp",
        ),
        "crs": "EPSG:4326",
        "description": "High-resolution OSM land polygons for basemap rendering.",
        "kind": "polygon",
    },
}

TABULAR_DATASETS = {
    "all_facilities": {
        "filename": "AllTogether.csv",
        "path": os.path.join(DATA_ROOT, "AllTogether.csv"),
        "description": "Facility point table with latitude, longitude, and facility type.",
        "kind": "csv",
    },
}


def get_vector_dataset(name):
    if name not in VECTOR_DATASETS:
        raise KeyError(f"Unknown vector dataset: {name}")
    return VECTOR_DATASETS[name]


def get_vector_path(name):
    return get_vector_dataset(name)["path"]


def get_tabular_dataset(name):
    if name not in TABULAR_DATASETS:
        raise KeyError(f"Unknown tabular dataset: {name}")
    return TABULAR_DATASETS[name]


def get_tabular_path(name):
    return get_tabular_dataset(name)["path"]


def resolve_csv_path(csv_name):
    """
    Resolve a CSV path from either a registered dataset filename or a direct file
    name under DATA_ROOT. This keeps existing tool signatures stable while moving
    dataset management into one central registry.
    """
    for dataset in TABULAR_DATASETS.values():
        if dataset["filename"].lower() == csv_name.lower():
            return dataset["path"]
    return os.path.join(DATA_ROOT, csv_name)
