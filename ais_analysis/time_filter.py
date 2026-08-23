import pandas as pd


def filter_by_time(
    df: pd.DataFrame,
    spill_time,
    duration_minutes: int = 60
):
    """
    Filter AIS records within a specified time window
    starting from the spill time.
    """

    spill_time = pd.to_datetime(spill_time)

    end_time = spill_time + pd.Timedelta(
        minutes=duration_minutes
    )

    filtered_df = df[
        (df["BaseDateTime"] >= spill_time) &
        (df["BaseDateTime"] <= end_time)
    ].copy()

    return filtered_df