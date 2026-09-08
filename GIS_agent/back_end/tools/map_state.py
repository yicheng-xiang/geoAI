from pathlib import Path

import geopandas as gpd

from data_catalog import get_vector_dataset, get_vector_path
from data_quality import validate_and_repair_polygon_dataset


HK_DISTRICTS = get_vector_dataset("hong_kong_districts")
DATA_PATH = Path(get_vector_path("hong_kong_districts"))


def init_map_state():
    """Load validated analysis data and initialize browser-facing map metadata."""
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Hong Kong district dataset was not found: {DATA_PATH}")
    districts = gpd.read_file(DATA_PATH)
    districts, quality = validate_and_repair_polygon_dataset(districts, HK_DISTRICTS["crs"])
    if not quality["passed"]:
        raise ValueError(
            "Hong Kong district dataset failed quality validation: "
            + "; ".join(quality["after_repair"]["errors"])
        )
    if not quality["after_repair"]["crs_matches_catalog"]:
        districts = districts.to_crs(HK_DISTRICTS["crs"])
    return {
        "gdf": districts,
        "web_layers": {},
        "web_map": {
            "title": None,
            "show_compass": True,
            "show_gridlines": False,
            "scale_bar_km": 10,
        },
        "quality": {"districts": quality},
    }
