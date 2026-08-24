import pandas as pd

def filter_by_time(df: pd.DataFrame, spill_time, duration_minutes: int):
    # Ensure BaseDateTime is datetime series
    df["BaseDateTime"] = pd.to_datetime(df["BaseDateTime"])
    
    # Strip timezone from BaseDateTime if present, or make spill_time tz-naive
    if df["BaseDateTime"].dt.tz is not None:
        df["BaseDateTime"] = df["BaseDateTime"].dt.tz_localize(None)
        
    if hasattr(spill_time, "tzinfo") and spill_time.tzinfo is not None:
        spill_time = spill_time.replace(tzinfo=None)

    # Perform time window filtering
    time_delta = pd.Timedelta(minutes=duration_minutes)
    start_time = spill_time - time_delta
    end_time = spill_time + time_delta

    return df[(df["BaseDateTime"] >= start_time) & (df["BaseDateTime"] <= end_time)]