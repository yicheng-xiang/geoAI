"""Metric buffer coverage analysis for registered facility point datasets."""

import json

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from data_quality import validate_and_clean_point_table
from location_search import LocationSearchError, search_hong_kong_location
from point_datasets import PointDatasetError, load_point_dataset, resolve_point_columns
from tool_results import tool_error, tool_success


ANALYSIS_CRS = "EPSG:2326"
OUTPUT_CRS = "EPSG:4326"
MAX_BUFFER_RADIUS_M = 50_000.0


def _filter_facilities(dataframe, type_column, facility_types, allow_all=False):
    if not facility_types:
        if allow_all:
            return dataframe.copy(), None
        return None, (
            "EMPTY_FACILITY_FILTER",
            "facility_types must contain at least one facility category.",
        )

    matches = []
    normalized_types = dataframe[type_column].astype(str).str.strip()
    for requested_type in facility_types:
        requested = str(requested_type).strip()
        if requested:
            matches.append(
                dataframe[normalized_types.str.contains(
                    requested, case=False, regex=False, na=False,
                )]
            )
    filtered = pd.concat(matches).drop_duplicates() if matches else dataframe.iloc[0:0]
    if filtered.empty:
        return None, (
            "NO_MATCHED_FACILITIES",
            f"No facility assets matched {facility_types}.",
        )
    return filtered, None


def _name_column(dataframe):
    return next(
        (column for column in dataframe.columns if "NAME" in str(column).upper()),
        None,
    )


def _feature_collection(frame, columns):
    if frame.empty:
        return {"type": "FeatureCollection", "features": []}
    return json.loads(frame[columns].to_crs(OUTPUT_CRS).to_json())


def buffer_facility_coverage(
    state,
    latitude=None,
    longitude=None,
    radius_m=500,
    dataset_id="all_facilities",
    facility_types=None,
    location_name=None,
    location_query=None,
    replace_existing=True,
    exclude_feature_ids=None,
):
    """Count registered facilities covered by a metric buffer around a WGS84 point."""
    geocoding = None
    if latitude is None and longitude is None:
        if not location_query:
            return tool_error(
                "MISSING_BUFFER_CENTER",
                "Provide either location_query or both WGS84 latitude and longitude.",
            )
        try:
            geocoding = search_hong_kong_location(location_query)
        except LocationSearchError as exc:
            return tool_error(exc.code, exc.message, exc.data)
        latitude = geocoding["latitude"]
        longitude = geocoding["longitude"]
        location_name = geocoding["name"]
    elif latitude is None or longitude is None:
        return tool_error(
            "INCOMPLETE_CENTER_COORDINATES",
            "Both WGS84 latitude and longitude are required when either coordinate is supplied.",
        )

    try:
        center_latitude = float(latitude)
        center_longitude = float(longitude)
        radius = float(radius_m)
    except (TypeError, ValueError):
        return tool_error(
            "INVALID_BUFFER_PARAMETERS",
            "latitude, longitude, and radius_m must be numeric values.",
        )

    if not -90 <= center_latitude <= 90 or not -180 <= center_longitude <= 180:
        return tool_error(
            "INVALID_CENTER_COORDINATES",
            "The buffer center must use valid WGS84 longitude and latitude coordinates.",
        )
    if radius <= 0 or radius > MAX_BUFFER_RADIUS_M:
        return tool_error(
            "INVALID_BUFFER_RADIUS",
            f"radius_m must be greater than 0 and no more than {int(MAX_BUFFER_RADIUS_M):,} metres.",
        )

    districts = state["gdf"].to_crs(OUTPUT_CRS)
    xmin, ymin, xmax, ymax = districts.total_bounds
    if not (xmin <= center_longitude <= xmax and ymin <= center_latitude <= ymax):
        return tool_error(
            "CENTER_OUTSIDE_STUDY_AREA",
            "The supplied center coordinates fall outside the registered Hong Kong study area.",
            {"study_bounds": [float(xmin), float(ymin), float(xmax), float(ymax)]},
        )

    try:
        dataset, dataframe = load_point_dataset(state, dataset_id)
    except PointDatasetError as exc:
        return tool_error(exc.code, exc.message)
    if dataframe.empty:
        return tool_error("EMPTY_DATASET", f"Dataset [{dataset_id}] is empty.")

    try:
        latitude_column, longitude_column, type_column = resolve_point_columns(dataframe)
    except PointDatasetError as exc:
        return tool_error(exc.code, exc.message)

    study_bounds = districts.to_crs(dataset["crs"]).total_bounds
    cleaned, point_quality = validate_and_clean_point_table(
        dataframe,
        latitude_column,
        longitude_column,
        type_column,
        source_crs=dataset["crs"],
        study_bounds=study_bounds,
    )
    if cleaned.empty:
        return tool_error(
            "NO_VALID_POINT_RECORDS",
            "No valid facility records remain after data quality validation.",
            {"quality": point_quality},
        )

    filtered, filter_error = _filter_facilities(
        cleaned,
        type_column,
        facility_types or [],
        allow_all=dataset_id == "session_upload",
    )
    if filter_error:
        return tool_error(*filter_error, data={"quality": point_quality})

    if exclude_feature_ids and 'source_feature_id' in filtered:
        filtered = filtered.loc[~filtered.source_feature_id.isin(exclude_feature_ids)].copy()

    points_wgs84 = gpd.GeoDataFrame(
        filtered.copy(),
        geometry=gpd.points_from_xy(filtered[longitude_column], filtered[latitude_column]),
        crs=dataset["crs"],
    ).to_crs(OUTPUT_CRS)
    points_metric = points_wgs84.to_crs(ANALYSIS_CRS)
    center_wgs84 = gpd.GeoSeries(
        [Point(center_longitude, center_latitude)], crs=OUTPUT_CRS,
    )
    center_metric = center_wgs84.to_crs(ANALYSIS_CRS).iloc[0]
    buffer_metric = center_metric.buffer(radius)

    distances = points_metric.geometry.distance(center_metric)
    covered_mask = distances <= radius
    matched_wgs84 = points_wgs84.loc[covered_mask].copy()
    matched_wgs84["distance_m"] = distances.loc[covered_mask].round(3).to_numpy()
    matched_wgs84["analysis_role"] = "facility_within_buffer"

    name_column = _name_column(matched_wgs84)
    if name_column is None:
        matched_wgs84["NAME"] = [f"Facility {index + 1}" for index in range(len(matched_wgs84))]
        name_column = "NAME"

    location_label = str(location_name or location_query or "Selected location").strip() or "Selected location"
    buffer_wgs84 = gpd.GeoDataFrame(
        [{
            "NAME": f"{radius:g} m buffer around {location_label}",
            "analysis_role": "buffer_area",
            "radius_m": radius,
            "matched_count": int(covered_mask.sum()),
            "geometry": buffer_metric,
        }],
        crs=ANALYSIS_CRS,
    ).to_crs(OUTPUT_CRS)
    center_frame = gpd.GeoDataFrame(
        [{
            "NAME": location_label,
            "FACILITY_TYPE": "Analysis center",
            "analysis_role": "buffer_center",
            "latitude": center_latitude,
            "longitude": center_longitude,
            "geocoder_source": geocoding.get("provider") if geocoding else "User-supplied coordinate",
            "geometry": center_wgs84.iloc[0],
        }],
        crs=OUTPUT_CRS,
    )

    point_columns = [name_column, type_column, "distance_m", "analysis_role", "geometry"]
    matched_geojson = _feature_collection(matched_wgs84, point_columns)
    buffer_geojson = _feature_collection(
        buffer_wgs84,
        ["NAME", "analysis_role", "radius_m", "matched_count", "geometry"],
    )
    center_geojson = _feature_collection(
        center_frame,
        [
            "NAME", "FACILITY_TYPE", "analysis_role", "latitude", "longitude",
            "geocoder_source", "geometry",
        ],
    )
    combined_geojson = {
        "type": "FeatureCollection",
        "features": (
            buffer_geojson["features"]
            + matched_geojson["features"]
            + center_geojson["features"]
        ),
    }

    matched_count = int(covered_mask.sum())
    point_quality.update({
        "filtered_records": int(len(filtered)),
        "matched_to_buffer": matched_count,
        "outside_buffer": int(len(filtered) - matched_count),
    })
    statistics = [
        {
            "name": str(row[name_column]),
            "facility_type": str(row[type_column]),
            "distance_m": round(float(row["distance_m"]), 3),
            "latitude": round(float(row.geometry.y), 7),
            "longitude": round(float(row.geometry.x), 7),
        }
        for _, row in matched_wgs84.iterrows()
    ]
    analysis = {
        "method": "buffer_coverage",
        "dataset_id": dataset_id,
        "facility_types": list(facility_types or []),
        "location_name": location_label,
        "center": {
            "latitude": center_latitude,
            "longitude": center_longitude,
        },
        "radius_m": radius,
        "matched_count": matched_count,
        "spatial_predicate": "distance_lte_radius",
        "source_crs": dataset["crs"],
        "analysis_crs": ANALYSIS_CRS,
        "output_crs": OUTPUT_CRS,
        "replace_existing": bool(replace_existing),
    }
    if geocoding:
        analysis["geocoding"] = geocoding
    quality = {
        "center": {
            "passed": True,
            "source_crs": OUTPUT_CRS,
            "inside_study_bounds": True,
            "resolution": "official_location_search" if geocoding else "user_supplied_coordinates",
        },
        "points": point_quality,
    }
    if dataset_id == "session_upload":
        analysis.update({
            "source_filename": dataset.get("filename"),
            "source_sha256": dataset.get("sha256"),
        })
        quality["upload"] = dataset.get("quality", {})

    shared_analysis = dict(analysis)
    visualization_layers = [
        {
            "id": "buffer_area",
            "kind": "polygon",
            "geojson": buffer_geojson,
            "analysis": {
                **shared_analysis,
                "visual_role": "buffer_area",
                "column": "analysis_role",
                "category_colors": {"buffer_area": "#93c5fd"},
                "polygon_style": {
                    "fill_opacity": 0.05,
                    "stroke_color": "#60a5fa",
                    "stroke_opacity": 0.22,
                    "stroke_width_px": 1.0,
                },
            },
        },
    ]
    if matched_count:
        unique_types = [str(value) for value in matched_wgs84[type_column].dropna().unique()]
        visualization_layers.append({
            "id": "buffer_facilities",
            "kind": "point",
            "geojson": matched_geojson,
            "analysis": {
                **shared_analysis,
                "visual_role": "matched_facilities",
                "category_colors": {name: ["#d97772", "#4c86b5", "#54a088", "#9672b4"][i % 4]
                                    for i, name in enumerate(sorted(unique_types))},
                "point_style": {
                    "symbol": "school" if any("school" in name.lower() for name in unique_types) else "facility",
                    "radius_px": 5.0,
                    "fill_opacity": 0.88,
                    "stroke_color": "#ffffff",
                    "stroke_opacity": 0.96,
                    "stroke_width_px": 1.2,
                },
            },
        })
    visualization_layers.append({
        "id": "buffer_center",
        "kind": "point",
        "geojson": center_geojson,
        "analysis": {
            **shared_analysis,
            "visual_role": "buffer_center",
            "category_colors": {"Analysis center": "#3b9ab2"},
            "point_style": {
                "symbol": "location",
                "radius_px": 8.0,
                "fill_opacity": 1.0,
                "stroke_color": "#ffffff",
                "stroke_opacity": 1.0,
                "stroke_width_px": 1.5,
            },
        },
    })

    result_data = {
        "analysis": analysis,
        "summary": {
            "location_name": location_label,
            "radius_m": radius,
            "matched_count": matched_count,
            "filtered_facility_count": int(len(filtered)),
        },
        "statistics": statistics,
        "geojson": combined_geojson,
        "visualization_layers": visualization_layers,
        "quality": quality,
    }
    state["last_analysis"] = result_data
    return tool_success(
        f"Buffer coverage analysis completed: {matched_count} matching facilities found "
        f"within {radius:g} metres of {location_label}.",
        code="BUFFER_COVERAGE_COMPLETED",
        data=result_data,
    )
