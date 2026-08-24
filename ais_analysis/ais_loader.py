import pandas as pd

def load_ais_data(file_path: str = "data/ais/ais_dataset.csv") -> pd.DataFrame:
    df = pd.read_csv(file_path)

    # Standardize column names to PascalCase if needed
    column_mapping = {
        "mmsi": "MMSI",
        "base_date_time": "BaseDateTime",
        "lat": "LAT",
        "lon": "LON",
        "sog": "SOG",
        "cog": "COG",
        "heading": "Heading",
        "vessel_name": "VesselName",
        "imo": "IMO",
        "call_sign": "CallSign",
        "vessel_type": "VesselType",
        "status": "Status",
        "length": "Length",
        "width": "Width",
        "draft": "Draft",
        "cargo": "Cargo",
        "transceiver_class": "TransceiverClass"
    }
    df = df.rename(columns=column_mapping)

    # Convert timestamps and sort chronologically
    df["BaseDateTime"] = pd.to_datetime(df["BaseDateTime"])
    df = df.sort_values("BaseDateTime").reset_index(drop=True)

    return df