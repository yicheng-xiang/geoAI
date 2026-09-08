import pandas as pd


def validate_polygon_dataset(gdf, expected_crs=None):
    geometry = gdf.geometry
    null_geometry = int(geometry.isna().sum())
    empty_geometry = int(geometry.is_empty.sum())
    valid_geometry_mask = geometry.notna() & ~geometry.is_empty
    invalid_geometry = int((~geometry[valid_geometry_mask].is_valid).sum())
    geometry_types = {
        str(name): int(count)
        for name, count in geometry.geom_type.value_counts(dropna=False).items()
    }

    actual_crs = gdf.crs.to_string() if gdf.crs is not None else None
    crs_matches_catalog = bool(
        actual_crs and expected_crs and gdf.crs == expected_crs
    ) if expected_crs else actual_crs is not None
    non_polygon = sum(
        count for geom_type, count in geometry_types.items()
        if geom_type not in {"Polygon", "MultiPolygon"}
    )

    errors = []
    if actual_crs is None:
        errors.append("CRS metadata is missing.")
    if null_geometry:
        errors.append(f"{null_geometry} geometries are null.")
    if empty_geometry:
        errors.append(f"{empty_geometry} geometries are empty.")
    if invalid_geometry:
        errors.append(f"{invalid_geometry} geometries are invalid.")
    if non_polygon:
        errors.append(f"{non_polygon} geometries are not Polygon/MultiPolygon.")

    return {
        "total_features": int(len(gdf)),
        "actual_crs": actual_crs,
        "expected_crs": expected_crs,
        "crs_matches_catalog": crs_matches_catalog,
        "null_geometry": null_geometry,
        "empty_geometry": empty_geometry,
        "invalid_geometry": invalid_geometry,
        "geometry_types": geometry_types,
        "errors": errors,
        "passed": not errors,
    }


def validate_and_repair_polygon_dataset(gdf, expected_crs=None):
    """Detect invalid polygons, repair them explicitly, and retain both reports."""
    initial_report = validate_polygon_dataset(gdf, expected_crs)
    repaired = gdf.copy()
    repaired_count = initial_report["invalid_geometry"]
    if repaired_count:
        repaired.geometry = repaired.geometry.make_valid()
    final_report = validate_polygon_dataset(repaired, expected_crs)
    return repaired, {
        "initial": initial_report,
        "after_repair": final_report,
        "repaired_geometries": repaired_count,
        "passed": final_report["passed"],
    }


def validate_and_clean_point_table(
    df,
    latitude_column,
    longitude_column,
    type_column,
    source_crs="EPSG:4326",
    study_bounds=None,
):
    working = df.copy()
    raw_latitude = working[latitude_column]
    raw_longitude = working[longitude_column]

    null_latitude = raw_latitude.isna() | raw_latitude.astype(str).str.strip().eq("")
    null_longitude = raw_longitude.isna() | raw_longitude.astype(str).str.strip().eq("")
    latitude = pd.to_numeric(raw_latitude, errors="coerce")
    longitude = pd.to_numeric(raw_longitude, errors="coerce")
    non_numeric = (latitude.isna() & ~null_latitude) | (longitude.isna() & ~null_longitude)
    null_coordinates = null_latitude | null_longitude
    invalid_range = (
        (~latitude.between(-90, 90) | ~longitude.between(-180, 180))
        & latitude.notna()
        & longitude.notna()
    )

    outside_study_bounds = pd.Series(False, index=working.index)
    if study_bounds is not None:
        xmin, ymin, xmax, ymax = study_bounds
        outside_study_bounds = (
            (~longitude.between(xmin, xmax) | ~latitude.between(ymin, ymax))
            & latitude.notna()
            & longitude.notna()
            & ~invalid_range
        )

    facility_type = working[type_column].astype("string").str.strip()
    null_type = facility_type.isna() | facility_type.eq("")
    duplicate_records = working.duplicated(
        subset=[latitude_column, longitude_column, type_column], keep="first"
    )

    valid_mask = ~(
        null_coordinates
        | non_numeric
        | invalid_range
        | outside_study_bounds
        | null_type
    )
    cleaned = working.loc[valid_mask].copy()
    cleaned[latitude_column] = latitude.loc[valid_mask].astype(float)
    cleaned[longitude_column] = longitude.loc[valid_mask].astype(float)
    cleaned[type_column] = facility_type.loc[valid_mask].astype(str)

    report = {
        "source_crs": source_crs,
        "total_records": int(len(working)),
        "valid_records": int(valid_mask.sum()),
        "excluded_records": int((~valid_mask).sum()),
        "null_coordinates": int(null_coordinates.sum()),
        "non_numeric_coordinates": int(non_numeric.sum()),
        "invalid_coordinate_range": int(invalid_range.sum()),
        "outside_study_bounds": int(outside_study_bounds.sum()),
        "null_facility_type": int(null_type.sum()),
        "duplicate_records": int(duplicate_records.sum()),
        "study_bounds": [float(value) for value in study_bounds] if study_bounds is not None else None,
        "issues_detected": bool((~valid_mask).any() or duplicate_records.any()),
        "passed": bool(valid_mask.any()),
    }
    return cleaned, report
