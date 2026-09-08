"""Resolve only explicitly allowed point datasets for GIS tools."""

import os

import pandas as pd

from data_catalog import get_tabular_dataset


SESSION_UPLOAD_DATASET_ID = "session_upload"
ALLOWED_POINT_DATASET_IDS = ("all_facilities", SESSION_UPLOAD_DATASET_ID)


class PointDatasetError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_point_columns(dataframe):
    latitude_columns = [column for column in dataframe.columns if "LAT" in column.upper()]
    longitude_columns = [
        column for column in dataframe.columns
        if "LON" in column.upper() or "LNG" in column.upper()
    ]
    type_columns = [
        column for column in dataframe.columns
        if "TYPE" in column.upper() or "FACILITY" in column.upper() or "CLASS" in column.upper()
    ]
    if not latitude_columns or not longitude_columns or not type_columns:
        raise PointDatasetError(
            "MISSING_SPATIAL_FIELDS",
            "Dataset is missing latitude, longitude, or facility type fields.",
        )
    return latitude_columns[0], longitude_columns[0], type_columns[0]


def load_point_dataset(state, dataset_id):
    """Load a catalog dataset or the current session upload, never a path argument."""
    if dataset_id in state.get('temporary_datasets', {}):
        dataset = state['temporary_datasets'][dataset_id]
        return {k: v for k, v in dataset.items() if k != 'dataframe'}, dataset['dataframe'].copy()
    if dataset_id == SESSION_UPLOAD_DATASET_ID:
        uploaded = state.get("uploaded_dataset")
        if not uploaded or uploaded.get("id") != SESSION_UPLOAD_DATASET_ID:
            raise PointDatasetError(
                "SESSION_UPLOAD_NOT_FOUND",
                "No Excel dataset has been uploaded in this browser session.",
            )
        dataset = {
            key: uploaded[key]
            for key in (
                "id", "filename", "kind", "crs", "columns", "quality", "sha256", "uploaded_at"
            )
            if key in uploaded
        }
        return dataset, uploaded["dataframe"].copy()

    if dataset_id != "all_facilities":
        raise PointDatasetError(
            "UNREGISTERED_DATASET",
            f"Unknown registered point dataset: {dataset_id}",
        )

    try:
        dataset = get_tabular_dataset(dataset_id)
    except (KeyError, ValueError) as exc:
        raise PointDatasetError("UNREGISTERED_DATASET", str(exc)) from exc
    if not os.path.exists(dataset["path"]):
        raise PointDatasetError(
            "DATASET_NOT_FOUND",
            f"Registered dataset file not found: {dataset_id}",
        )
    dataframe = pd.read_csv(dataset["path"])
    return dataset, dataframe
