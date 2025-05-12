import shutil
from pathlib import Path
import datetime as dt
from typing import Generator
import pytest


@pytest.fixture
def report_dir(test_data_dir: Path) -> Path:
    """Fixture for report directory path, could be a list of path too"""
    return test_data_dir / "reports"


@pytest.fixture
def test_data_dir() -> Path:
    """Fixture for test data directory for integration tests"""
    return Path(__file__).parent / "test_data"


# @pytest.fixture
# def tmp_report_dir(tmp_path):
#     """Fixture providing a temporary report directory for unit tests"""
#     return tmp_path / "reports"


@pytest.fixture
def setup_test_files(report_dir: Path) -> Generator[Path, None, None]:
    # NOTE: Remove after
    # Cretate dir if it does not exist
    report_dir.mkdir(parents=True, exist_ok=True)
    # Create test files
    yesterday = (dt.datetime.now() - dt.timedelta(days=1)).strftime("%d-%m-%Y")
    today = dt.datetime.now().strftime("%d-%m-%Y")
    # Create yesterday's report (should exist)
    (report_dir / f"{yesterday}.csv").touch()

    yield report_dir
    # Teardown - remove test files
    # shutil.rmtree(report_dir)


@pytest.fixture
def create_report(tmp_path: Path):
    """File creator for the report files"""
    def _create(date: dt.date) -> Path:
        file_path = tmp_path / f"{date.strftime('%d-%m-%Y')}.csv"
        file_path.touch()
        return file_path
    yield _create
