from pathlib import Path

DATA_ROOT = (Path(__file__).resolve().parents[2] / "data").resolve()

VECTOR_DATASETS = {
    "hong_kong_districts": {
        "path": DATA_ROOT / "HKDistrict18.shp",
        "crs": "EPSG:4326",
        "description": "Hong Kong 18-district administrative boundaries.",
        "kind": "polygon",
    },
    "osm_land_polygons": {
        "path": (
            DATA_ROOT
            / "land-polygons-complete-4326"
            / "land-polygons-complete-4326"
            / "land_polygons.shp"
        ),
        "crs": "EPSG:4326",
        "description": "High-resolution OSM land polygons for basemap rendering.",
        "kind": "polygon",
    },
}

TABULAR_DATASETS = {
    "all_facilities": {
        "path": DATA_ROOT / "AllTogether.csv",
        "crs": "EPSG:4326",
        "description": "Facility point table with latitude, longitude, and facility type.",
        "kind": "csv",
    },
}


def _validated_dataset(registry, dataset_id, dataset_kind):
    if dataset_id not in registry:
        raise KeyError(f"Unknown registered {dataset_kind} dataset: {dataset_id}")

    dataset = dict(registry[dataset_id])
    resolved_path = Path(dataset["path"]).resolve()
    if resolved_path != DATA_ROOT and DATA_ROOT not in resolved_path.parents:
        raise ValueError(f"Registered dataset escapes DATA_ROOT: {dataset_id}")

    dataset["id"] = dataset_id
    dataset["path"] = str(resolved_path)
    return dataset


def get_vector_dataset(dataset_id):
    return _validated_dataset(VECTOR_DATASETS, dataset_id, "vector")


def get_vector_path(dataset_id):
    return get_vector_dataset(dataset_id)["path"]


def get_tabular_dataset(dataset_id):
    return _validated_dataset(TABULAR_DATASETS, dataset_id, "tabular")


def get_tabular_path(dataset_id):
    return get_tabular_dataset(dataset_id)["path"]
