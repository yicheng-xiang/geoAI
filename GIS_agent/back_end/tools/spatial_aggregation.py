import os

import geopandas as gpd
import mapclassify
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from data_catalog import resolve_csv_path
from layer_styles import refresh_clean_legend

plt.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

CONTINUOUS_CMAPS = {"Greens", "Blues", "Purples", "Reds", "Oranges", "YlOrRd", "viridis"}


def _resolve_csv_columns(df):
    lat_cols = [c for c in df.columns if "LAT" in c.upper()]
    lon_cols = [c for c in df.columns if "LON" in c.upper() or "LNG" in c.upper()]
    type_cols = [
        c for c in df.columns
        if "TYPE" in c.upper() or "FACILITY" in c.upper() or "CLASS" in c.upper()
    ]
    if not lat_cols or not lon_cols or not type_cols:
        return None, None, None
    return lat_cols[0], lon_cols[0], type_cols[0]


def _filter_facilities(df, actual_type, facility_types):
    if not facility_types:
        return None, "Error: facility_types array is empty. Provide at least one facility category to aggregate."

    df = df.copy()
    df[actual_type] = df[actual_type].astype(str).str.strip()

    matched_rows = []
    for requested_type in facility_types:
        req_upper = str(requested_type).strip().upper()
        mask = df[actual_type].str.upper().str.contains(req_upper, na=False)
        matched_rows.append(df[mask])

    filtered_df = pd.concat(matched_rows).drop_duplicates() if matched_rows else df.iloc[0:0]
    if filtered_df.empty:
        return None, (
            f"Error: No facility assets matched the requested types {facility_types}. "
            "Spatial aggregation and choropleth rendering were skipped."
        )
    return filtered_df, None


def _clear_polygon_layers(ax):
    for collection in list(ax.collections):
        if type(collection).__name__ == "PolyCollection":
            collection.remove()


def _build_classifier(values, k):
    unique_count = values.nunique()
    actual_k = max(1, min(k, unique_count))

    try:
        classifier = mapclassify.Quantiles(values, k=actual_k)
    except Exception:
        classifier = mapclassify.FisherJenks(values, k=actual_k)

    return classifier, len(classifier.bins)


def _sample_bin_colors(cmap_name, actual_k):
    cmap_obj = plt.get_cmap(cmap_name)
    if cmap_name in CONTINUOUS_CMAPS:
        return cmap_obj(np.linspace(0.25, 0.85, actual_k))
    return [cmap_obj(i / (actual_k - 1) if actual_k > 1 else 0.5) for i in range(actual_k)]


def _build_integer_legend_labels(count_series, classifier, actual_k):
    """
    Build non-overlapping closed integer interval labels for discrete facility counts.
    Example: 0 - 10, 11 - 20, 21 - 30
    """
    counts = count_series.astype(int)
    bin_assignments = np.asarray(classifier(counts))

    labels = []
    prev_upper = None

    for i in range(actual_k):
        in_bin = counts[bin_assignments == i]

        if i == 0:
            lower = int(counts.min())
        else:
            lower = prev_upper + 1

        if in_bin.empty:
            upper = lower
        else:
            upper = max(lower, int(in_bin.max()))

        if lower == upper:
            labels.append(f"{lower}")
        else:
            labels.append(f"{lower} - {upper}")
        prev_upper = upper

    return labels


def aggregate_points_to_districts(
    state,
    csv_name="AllTogether.csv",
    facility_types=None,
    cmap="YlOrRd",
    k=5,
):
    """
    Spatial aggregation tool: count filtered point assets per administrative district
    via spatial join, then render a quantitative choropleth with English legend labels.
    """
    gdf = state["gdf"]
    ax = state["ax"]
    facility_types = facility_types or []

    csv_path = resolve_csv_path(csv_name)
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Database asset file not found at: {csv_path}")

    df = pd.read_csv(csv_path)
    if df.empty:
        return f"Error: Target CSV [{csv_name}] is empty. Spatial aggregation was skipped."

    actual_lat, actual_lon, actual_type = _resolve_csv_columns(df)
    if actual_lat is None:
        return (
            "Error: CSV is missing standard spatial coordinate or facility type fields. "
            "Spatial aggregation was skipped."
        )

    filtered_df, error_msg = _filter_facilities(df, actual_type, facility_types)
    if error_msg:
        return error_msg

    points_gdf = gpd.GeoDataFrame(
        filtered_df,
        geometry=gpd.points_from_xy(filtered_df[actual_lon], filtered_df[actual_lat]),
        crs="EPSG:4326",
    )

    districts = gdf.copy()
    if districts.crs is None:
        districts = districts.set_crs("EPSG:4326")
    if points_gdf.crs != districts.crs:
        points_gdf = points_gdf.to_crs(districts.crs)

    joined = gpd.sjoin(points_gdf, districts, how="inner", predicate="within")
    counts = joined.groupby("index_right").size()

    districts["facility_count"] = 0
    if not counts.empty:
        districts.loc[counts.index, "facility_count"] = counts.values.astype(int)

    state["gdf"] = districts

    _clear_polygon_layers(ax)

    count_series = districts["facility_count"]
    classifier, actual_k = _build_classifier(count_series, k)
    bin_ids = classifier(count_series)
    bin_colors = _sample_bin_colors(cmap, actual_k)
    row_colors = [bin_colors[bid] for bid in bin_ids]

    districts.plot(
        color=row_colors,
        ax=ax,
        edgecolor="#e2e8f0",
        linewidth=0.4,
        zorder=1,
    )

    legend_labels = _build_integer_legend_labels(count_series, classifier, actual_k)
    for i, label_text in enumerate(legend_labels):
        ax.plot(
            [], [],
            color=bin_colors[i],
            label=label_text,
            marker="s",
            linestyle="None",
            markersize=10,
            zorder=1,
        )

    legend_title = f"Facility Density ({', '.join(facility_types)})"
    refresh_clean_legend(
        ax,
        title=legend_title,
        fontsize=9,
        ncol=1,
    )

    total_points = len(filtered_df)
    districts_touched = int((districts["facility_count"] > 0).sum())
    total_districts = len(districts)

    return (
        f"Success: Spatial aggregation completed. {total_points} filtered facility assets "
        f"were spatially joined and counted across {total_districts} administrative districts "
        f"({districts_touched} districts contain at least one asset). "
        f"Quantitative choropleth rendered for types [{', '.join(facility_types)}] "
        f"using {actual_k} classification intervals."
    )
