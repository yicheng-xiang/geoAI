import json
import geopandas as gpd
import numpy as np
import pandas as pd

from classification import quantile_breaks
from color_palettes import sample_palette
from data_quality import validate_and_clean_point_table, validate_polygon_dataset
from point_datasets import PointDatasetError, load_point_dataset, resolve_point_columns
from tool_results import tool_error, tool_success

AREA_CRS = "EPSG:2326"
OUTPUT_CRS = "EPSG:4326"
SUPPORTED_METRICS = {"count", "density_per_km2"}


def _filter_facilities(df, type_column, facility_types, allow_all=False):
    if not facility_types:
        if allow_all:
            return df.copy(), None
        return None, (
            "EMPTY_FACILITY_FILTER",
            "facility_types must contain at least one facility category.",
        )

    matched_rows = []
    normalized_types = df[type_column].astype(str).str.strip()
    for requested_type in facility_types:
        requested = str(requested_type).strip()
        if not requested:
            continue
        mask = normalized_types.str.contains(requested, case=False, regex=False, na=False)
        matched_rows.append(df[mask])

    filtered = pd.concat(matched_rows).drop_duplicates() if matched_rows else df.iloc[0:0]
    if filtered.empty:
        return None, (
            "NO_MATCHED_FACILITIES",
            f"No facility assets matched {facility_types}.",
        )
    return filtered, None


def _equal_interval_count_breaks(values, k):
    """Return compact integer intervals with at least two values per class when possible."""
    if values.empty:
        return []
    minimum = int(values.min())
    maximum = int(values.max())
    integer_span = maximum - minimum + 1
    requested = min(3, max(1, int(k)))
    bin_count = min(requested, max(1, integer_span // 2))
    base_size, remainder = divmod(integer_span, bin_count)
    breaks = []
    cursor = minimum
    for index in range(bin_count):
        cursor += base_size + (1 if index < remainder else 0) - 1
        breaks.append(cursor)
        cursor += 1
    return breaks


def _sample_bin_colors(cmap_name, actual_k):
    return sample_palette(cmap_name, actual_k)


def _district_identity(districts):
    id_column = "OBJECTID" if "OBJECTID" in districts.columns else None
    name_column = next(
        (column for column in ["ENAME", "DISTRICT", "NAME", "ENG_NAME"] if column in districts.columns),
        None,
    )
    district_ids = districts[id_column] if id_column else districts.index.astype(str)
    district_names = districts[name_column].astype(str) if name_column else district_ids.astype(str)
    return district_ids, district_names


def aggregate_points_to_districts(
    state,
    dataset_id="all_facilities",
    facility_types=None,
    metric="count",
    cmap="YlOrRd",
    k=5,
    replace_existing=False,
):
    """Count facilities by district or calculate facilities per square kilometer."""
    if metric not in SUPPORTED_METRICS:
        return tool_error(
            "UNSUPPORTED_METRIC",
            f"metric must be one of {sorted(SUPPORTED_METRICS)}; received {metric!r}.",
        )

    try:
        dataset, dataframe = load_point_dataset(state, dataset_id)
    except PointDatasetError as exc:
        return tool_error(exc.code, exc.message)

    districts = state["gdf"].copy()
    current_district_quality = validate_polygon_dataset(districts, OUTPUT_CRS)
    if not current_district_quality["passed"]:
        return tool_error(
            "INVALID_DISTRICT_GEOMETRY",
            "; ".join(current_district_quality["errors"]),
            {"quality": current_district_quality},
        )
    district_quality = state.get("quality", {}).get("districts", current_district_quality)
    if districts.crs != OUTPUT_CRS:
        districts = districts.to_crs(OUTPUT_CRS)

    if dataframe.empty:
        return tool_error("EMPTY_DATASET", f"Dataset [{dataset_id}] is empty.")

    try:
        latitude, longitude, facility_type = resolve_point_columns(dataframe)
    except PointDatasetError as exc:
        return tool_error(exc.code, exc.message)

    cleaned, point_quality = validate_and_clean_point_table(
        dataframe,
        latitude,
        longitude,
        facility_type,
        source_crs=dataset["crs"],
        study_bounds=districts.total_bounds,
    )
    if cleaned.empty:
        return tool_error(
            "NO_VALID_POINT_RECORDS",
            "No valid facility records remain after data quality validation.",
            {"quality": point_quality},
        )

    filtered, filter_error = _filter_facilities(
        cleaned,
        facility_type,
        facility_types or [],
        allow_all=dataset_id == "session_upload",
    )
    if filter_error:
        return tool_error(*filter_error, data={"quality": point_quality})

    points = gpd.GeoDataFrame(
        filtered,
        geometry=gpd.points_from_xy(filtered[longitude], filtered[latitude]),
        crs=dataset["crs"],
    )
    if points.crs != districts.crs:
        points = points.to_crs(districts.crs)

    joined = gpd.sjoin(points, districts, how="inner", predicate="within")
    counts = joined.groupby("index_right").size()
    districts["facility_count"] = 0
    if not counts.empty:
        districts.loc[counts.index, "facility_count"] = counts.astype(int)

    area_km2 = districts.to_crs(AREA_CRS).geometry.area / 1_000_000
    districts["area_km2"] = area_km2.astype(float)
    districts["density_per_km2"] = (
        districts["facility_count"] / districts["area_km2"]
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    districts["metric_value"] = (
        districts["facility_count"].astype(float)
        if metric == "count"
        else districts["density_per_km2"].astype(float)
    )

    district_ids, district_names = _district_identity(districts)
    districts["district_id"] = district_ids
    districts["district_name"] = district_names
    state["gdf"] = districts

    values = districts["metric_value"]
    positive_values = values[values > 0]
    zero_color = "#e2e8f0"

    if metric == "count":
        breaks = _equal_interval_count_breaks(positive_values, k)
        classification_breaks = [float(value) for value in breaks]
        actual_k = len(breaks)
        bin_colors = _sample_bin_colors(cmap, actual_k) if actual_k else []
        classification_name = "Equal interval"
    else:
        classification_name = "Quantiles"
        if positive_values.empty:
            actual_k = 0
            bin_colors = []
            classification_breaks = []
        else:
            classification_breaks = quantile_breaks(positive_values, k)
            actual_k = len(classification_breaks)
            bin_colors = _sample_bin_colors(cmap, actual_k)

    matched_point_count = int(joined.index.nunique())
    point_quality["filtered_records"] = int(len(filtered))
    point_quality["matched_to_district"] = matched_point_count
    point_quality["unmatched_to_district"] = int(len(filtered) - matched_point_count)

    statistics = [
        {
            "district_id": str(row.district_id),
            "district_name": row.district_name,
            "count": int(row.facility_count),
            "area_km2": round(float(row.area_km2), 6),
            "density_per_km2": round(float(row.density_per_km2), 6),
            "metric_value": round(float(row.metric_value), 6),
        }
        for row in districts[
            ["district_id", "district_name", "facility_count", "area_km2", "density_per_km2", "metric_value"]
        ].itertuples(index=False)
    ]

    geojson_columns = [
        "district_id", "district_name", "facility_count", "area_km2",
        "density_per_km2", "metric_value", "geometry",
    ]
    geojson = json.loads(districts[geojson_columns].to_crs(OUTPUT_CRS).to_json())
    analysis = {
        "method": "point_in_polygon",
        "dataset_id": dataset_id,
        "facility_types": list(facility_types or []),
        "metric": metric,
        "unit": "facilities" if metric == "count" else "facilities_per_km2",
        "spatial_predicate": "within",
        "source_crs": dataset["crs"],
        "area_crs": AREA_CRS,
        "output_crs": OUTPUT_CRS,
        "classification": classification_name,
        "classification_intervals": actual_k,
        "classification_breaks": classification_breaks,
        "colormap": cmap,
        "palette": list(bin_colors),
        "zero_color": zero_color,
        "replace_existing": bool(replace_existing),
    }
    result_quality = {"districts": district_quality, "points": point_quality}
    if dataset_id == "session_upload":
        analysis.update({
            "source_filename": dataset.get("filename"),
            "source_sha256": dataset.get("sha256"),
        })
        result_quality["upload"] = dataset.get("quality", {})
    result_data = {
        "analysis": analysis,
        "statistics": statistics,
        "geojson": geojson,
        "quality": result_quality,
    }
    state["last_analysis"] = result_data

    metric_description = "raw count" if metric == "count" else "facilities per square kilometer"
    return tool_success(
        f"Spatial aggregation completed using {metric_description}: "
        f"{len(filtered)} valid filtered records, {matched_point_count} matched to districts, "
        f"and {point_quality['unmatched_to_district']} unmatched.",
        code="SPATIAL_ANALYSIS_COMPLETED",
        data=result_data,
    )
