import pandas as pd


def load_ais_data(file_path: str):
    """
    Load AIS data and prepare the BaseDateTime column.
    """

    df = pd.read_csv(file_path)

    # Convert AIS timestamp to datetime
    df["BaseDateTime"] = pd.to_datetime(df["BaseDateTime"])

    # Sort records by time
    df = df.sort_values("BaseDateTime")

    return df