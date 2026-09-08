import json

import geopandas as gpd
import pandas as pd

from classification import quantile_breaks
from color_palettes import literal_color, sample_palette
from data_quality import validate_and_clean_point_table
from point_datasets import PointDatasetError, load_point_dataset, resolve_point_columns
from tool_results import tool_error, tool_success


MAX_RENDERED_FACILITY_TYPES = 20


def _district_name_column(gdf):
    return next(
        (candidate for candidate in ["ENAME", "DISTRICT", "NAME", "ENG_NAME"] if candidate in gdf.columns),
        None,
    )


def _resolve_choropleth_column(gdf, column):
    columns_upper = [name.upper() for name in gdf.columns]
    requested = str(column).upper()
    if requested not in {"CNAME", "名称", "区名", "CHINESE", "C_NAME"} and requested in columns_upper:
        return gdf.columns[columns_upper.index(requested)]
    for candidate in ["DISTRICT", "ENAME", "D_NAME", "NAME", "ENG_NAME"]:
        if candidate in columns_upper:
            return gdf.columns[columns_upper.index(candidate)]
    text_fields = gdf.select_dtypes(include=["object"]).columns.tolist()
    return text_fields[0] if text_fields else gdf.columns[0]


def draw_choropleth(state, column="OBJECTID", cmap="tab20", k=5, replace_existing=False):
    """Prepare a district choropleth as structured GeoJSON and browser style metadata."""
    gdf = state["gdf"]
    if str(cmap).lower() in {"black", "binary", "gray", "greys", "#000000"}:
        cmap = "tab20"
    actual_col = _resolve_choropleth_column(gdf, column)
    unique_count = int(gdf[actual_col].nunique())
    is_categorical = not pd.api.types.is_numeric_dtype(gdf[actual_col]) or unique_count <= 10

    if is_categorical:
        unique_values = sorted(gdf[actual_col].dropna().unique())
        colors = sample_palette(cmap, len(unique_values))
        category_colors = {str(value): color for value, color in zip(unique_values, colors)}
        breaks = []
        log_message = f"Administrative choropleth prepared from category column [{actual_col}]."
    else:
        breaks = quantile_breaks(gdf[actual_col], k)
        colors = sample_palette(cmap, len(breaks))
        category_colors = {}
        log_message = f"Numeric choropleth prepared using quantiles on column [{actual_col}]."

    name_column = _district_name_column(gdf)
    district_names = gdf[name_column].astype(str) if name_column else gdf.index.astype(str)
    statistics = []
    for district_name, value in zip(district_names, gdf[actual_col]):
        if pd.isna(value):
            value = None
        elif hasattr(value, "item"):
            value = value.item()
        statistics.append({"district_name": str(district_name), "value": value})

    geojson_frame = gdf[[actual_col, "geometry"]].copy()
    geojson_frame["district_name"] = district_names
    if not is_categorical:
        geojson_frame["metric_value"] = pd.to_numeric(gdf[actual_col], errors="coerce")
    result_data = {
        "analysis": {
            "method": "district_choropleth",
            "dataset_id": "hong_kong_districts",
            "column": actual_col,
            "value_type": "categorical" if is_categorical else "numeric",
            "colormap": cmap,
            "palette": colors,
            "category_colors": category_colors,
            "classification_breaks": breaks,
            "classification_intervals": len(colors),
            "replace_existing": bool(replace_existing),
            "output_crs": "EPSG:4326",
        },
        "statistics": statistics,
        "geojson": json.loads(geojson_frame.to_crs("EPSG:4326").to_json()),
        "quality": state.get("quality", {}),
    }
    state["last_analysis"] = result_data
    return tool_success(log_message, code="CHOROPLETH_COMPLETED", data=result_data)


def add_points_layer(
    state,
    dataset_id="all_facilities",
    facility_types=None,
    cmap="Set1",
    replace_existing=False,
):
    """Prepare validated facility points as GeoJSON and browser symbol metadata."""
    try:
        dataset, dataframe = load_point_dataset(state, dataset_id)
    except PointDatasetError as exc:
        return tool_error(exc.code, exc.message)
    if dataframe.empty:
        return tool_error("EMPTY_DATASET", f"Dataset [{dataset_id}] is empty.")
    try:
        latitude, longitude, facility_type = resolve_point_columns(dataframe)
    except PointDatasetError as exc:
        return tool_error(exc.code, exc.message)

    district_bounds = state["gdf"].to_crs(dataset["crs"]).total_bounds
    cleaned, quality = validate_and_clean_point_table(
        dataframe, latitude, longitude, facility_type,
        source_crs=dataset["crs"], study_bounds=district_bounds,
    )
    if cleaned.empty:
        return tool_error(
            "NO_VALID_POINT_RECORDS", "No valid facility records remain after data quality validation.",
            {"quality": quality},
        )

    filtered = cleaned.copy()
    if facility_types:
        matches = []
        for requested_type in facility_types:
            mask = cleaned[facility_type].str.upper().str.contains(
                str(requested_type).upper(), regex=False, na=False,
            )
            matches.append(cleaned[mask])
        if matches:
            filtered = pd.concat(matches).drop_duplicates()
    elif dataset_id != "session_upload":
        return tool_error(
            "EMPTY_FACILITY_FILTER", "Facility filtering types array is empty.", {"quality": quality},
        )
    if filtered.empty:
        return tool_error(
            "NO_MATCHED_FACILITIES", f"No entities matched criteria {facility_types}.", {"quality": quality},
        )

    unique_types = list(filtered[facility_type].unique())
    if len(unique_types) > MAX_RENDERED_FACILITY_TYPES:
        return tool_error(
            "TOO_MANY_FACILITY_TYPES",
            f"The point layer contains {len(unique_types)} facility types; filter or group them to "
            f"{MAX_RENDERED_FACILITY_TYPES} or fewer before rendering.",
            {"quality": quality, "facility_type_count": len(unique_types)},
        )

    requested_literal = literal_color(cmap)
    prompt = str(state.get("user_prompt", ""))
    if not requested_literal and ("BLACK" in prompt.upper() or "黑色" in prompt):
        requested_literal = "#000000"
    colors = [requested_literal] * len(unique_types) if requested_literal else sample_palette(cmap, len(unique_types))

    points = gpd.GeoDataFrame(
        filtered,
        geometry=gpd.points_from_xy(filtered[longitude], filtered[latitude]),
        crs=dataset["crs"],
    )
    quality["filtered_records"] = int(len(filtered))
    statistics = [
        {"facility_type": str(name), "count": int(count)}
        for name, count in filtered[facility_type].value_counts().items()
    ]
    analysis = {
        "method": "facility_filter",
        "dataset_id": dataset_id,
        "facility_types": list(facility_types or []),
        "colormap": cmap,
        "category_colors": {str(name): color for name, color in zip(unique_types, colors)},
        "point_style": {
            "radius_px": 3.1 if len(filtered) > 75 else 3.4 if len(filtered) > 30 else 3.8,
            "fill_opacity": 0.78,
            "stroke_color": "#334155",
            "stroke_opacity": 0.95,
            "stroke_width_px": 1.0,
        },
        "replace_existing": bool(replace_existing),
        "source_crs": dataset["crs"],
        "output_crs": "EPSG:4326",
    }
    result_quality = {"points": quality}
    if dataset_id == "session_upload":
        analysis.update({
            "source_filename": dataset.get("filename"),
            "source_sha256": dataset.get("sha256"),
        })
        result_quality["upload"] = dataset.get("quality", {})
    result_data = {
        "analysis": analysis,
        "statistics": statistics,
        "geojson": json.loads(points.to_crs("EPSG:4326").to_json()),
        "quality": result_quality,
    }
    state["last_analysis"] = result_data
    return tool_success(
        f"Prepared {len(filtered)} point records across {len(unique_types)} facility type(s) "
        "with synchronized browser legend metadata.",
        code="POINT_LAYER_COMPLETED", data=result_data,
    )
