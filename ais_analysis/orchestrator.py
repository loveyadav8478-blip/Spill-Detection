from data.schemas import (
    AISFilterInput,
    DashboardResponse
)

from ais_analysis.pipeline import (
    run_ais_pipeline
)

# Connect Hindcast output with AIS analysis.

def run_ais_after_hindcast(
    detection_output,
    hindcast_output,
    raw_ais_pings
):

    ais_input = AISFilterInput(
        spill_id=hindcast_output.spill_id,

        # Main values used by your existing AIS logic
        origin_estimate=(
            hindcast_output.origin_estimate
        ),

        # Optional for future advanced analysis
        backward_path=(
            hindcast_output.backward_path
        )
    )

    filter_output, ais_score_output = (
        run_ais_pipeline(
            input_data=ais_input
        )
    )

    return ais_score_output