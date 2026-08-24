from pathlib import Path


def delete_file(file_path: str | Path) -> None:
    """
    Safely delete a temporary uploaded file.
    """

    path = Path(file_path)

    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"Failed to delete temporary file: {path}"
        ) from exc