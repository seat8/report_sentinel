import pytest
from pathlib import Path
from report_sentinel import run_tpt_report_downloader, check_last_report_exists, main, load_config
import datetime as dt
import pytz
from freezegun import freeze_time
from unittest.mock import MagicMock


@pytest.fixture
def dummy_config(tmp_path):
    main_py = tmp_path / "fake_main.py"
    main_py.write_text("print('pretend TPTDailyReportDownloader ran')")
    print(f"the main without str:{main_py}")
    print(f"the main with str:{str(main_py)}")

    return {
        "report_paths": [str(tmp_path)],
        "smtp_server": ["localhost", 465],
        "smtp_username": "user",
        "smtp_password": "pass",
        "sender": "sender@test.com",
        "recipients": ["recipients@test.com"],
        "errors_recipients": ["recipients@test.com"],
        "tpt_venv": str(tmp_path / ".venv"),
        "tpt_project_dir": str(tmp_path),
        "main_script_path": str(main_py),
    }


@pytest.fixture
def hijack_runner(mocker, dummy_config):
    fake_main_script = dummy_config["main_script_path"]
    # mock_run = mocker.patch("report_sentinel.subprocess.run")
    mock_run = mocker.patch("report_sentinel.subprocess.run", autospec=True)
    # mock_run.return_value = MagicMock(stdout="Success")
    mock_run.return_value = MagicMock(stdout="Success", autospec=True)

    # Create fake venv directory
    # mocker.patch("report_sentinel.venv.create")
    # venv_dir = Path(__file__).resolve().parent / ".venv"
    # venv_dir.mkdir(exist_ok=True)

    venv_dir = Path(dummy_config['tpt_venv'])
    venv_dir.mkdir(exist_ok=True)

    run_tpt_report_downloader(config=dummy_config)

    # This ensures all downstream tests assume subprocess.run worked
    yield mock_run


# Using it in a downstream test ti see how it can use hijack_runner
def test_followup_reads_result(hijack_runner, tmp_path):
    # TODO: remove the test at the end of the day
    #  Pretend the generator created this file
    output_path = tmp_path / "generated_result.txt"
    output_path.write_text("42")

    # Your actual logic might read this, e.g.:
    result = output_path.read_text()
    assert result == "42"

    # confirm subprocess.run was called before this step
    assert hijack_runner.called


def test_setup_and_run_invokes_main(mocker, dummy_config):
    mock_run = mocker.patch("report_sentinel.subprocess.run")
    mocker.patch("report_sentinel.venv.create")
    venv_dir = Path(__file__).resolve().parent / ".venv"
    venv_dir.mkdir(exist_ok=True)

    run_tpt_report_downloader(config=dummy_config)

    # Verify subprocess.run was called to invoke main.py
    assert mock_run.call_count >= 1
    args = mock_run.call_args[0][0]

    assert "python" in args[0]  # .venv/bin/python
    assert "fake_main.py" in args[1]


current_time_et = dt.datetime.now(pytz.utc).astimezone(
    pytz.timezone("US/Eastern")
)


# Setting up for the test_data in the test suite - already done that in conftest
class TestCheckReportiDir:
    # def test_report_exists(self, setup_test_files: Path) -> None:
    #     # NOTE: remove it
    #     """Test that check_report_dir returns True when report exists"""
    #     assert check_last_report_exists(setup_test_files) is True

    def test_before_cutoff_with_yesterdays_report(self, create_report):
        """Should find yesterday's report before 5PM"""
        # Create yesterday's report
        yesterday = current_time_et - dt.timedelta(days=1)
        report = create_report(yesterday)

        fake_time = current_time_et.replace(hour=12, minute=0)
        with freeze_time(fake_time):  # Before 5PM ET
            assert check_last_report_exists(report.parent) is True

    def test_after_cutoff_with_todays_report(self, create_report):
        """Should find today's report after 5PM"""
        # Create today report
        today = current_time_et
        report = create_report(today)

        fake_time = current_time_et.replace(hour=18, minute=0)
        with freeze_time(fake_time):  # After 5PM ET
            assert check_last_report_exists(report.parent) is True

    def test_missing_report(self, tmp_path):
        """Should return False when report is missing"""
        fake_time = current_time_et.replace(hour=12, minute=0)
        with freeze_time(fake_time):
            assert check_last_report_exists(tmp_path) is False

    def test_timezone_boundary_behaviour(self, tmp_path, create_report):
        """Verify exact 5PM ET boundary behaviour"""
        # Create both yesterday's and today's reports
        yesterday = current_time_et - dt.timedelta(days=1)
        yesterday_str = yesterday.strftime("%d-%m-%Y")
        today = current_time_et
        today_str = today.strftime("%d-%m-%Y")
        today_report = create_report(today)
        yesterday_report = create_report(yesterday)

        # 1 minute before cutoff (4:59PM ET)
        fake_time = current_time_et.replace(hour=16, minute=59)
        with freeze_time(fake_time):  # After 5PM ET
            assert check_last_report_exists(yesterday_report.parent) is True
            assert Path(tmp_path / f"{yesterday_str}.csv").exists()

        # Exactly at cutoff (5:00PM ET)
        fake_time = current_time_et.replace(hour=17, minute=0)
        with freeze_time(fake_time):  # After 5PM ET
            assert check_last_report_exists(today_report.parent) is True
            assert Path(tmp_path / f"{today_str}.csv").exists()

        # 1 minute after cutoff (5:01PM ET)
        fake_time = current_time_et.replace(hour=17, minute=1)
        with freeze_time(fake_time):
            assert check_last_report_exists(today_report.parent) is True
            assert Path(tmp_path / f"{today_str}.csv").exists()

    def test_late_night_execution(self, tmp_path, create_report):
        """Verify behaviour for late-night runs"""
        today = current_time_et
        today_report = create_report(today)
        today_str = today.strftime("%d-%m-%Y")

        fake_time = current_time_et.replace(hour=23, minute=0)
        with freeze_time(fake_time):
            assert check_last_report_exists(tmp_path) is True
            assert Path(tmp_path / f"{today_str}.csv").exists()


class TestWorkFlow:
    def test_desired_unhappy_scenario(
        self, mocker, dummy_config, hijack_runner, create_report
    ) -> None:
        """Success case - report exists - not latest possible report"""
        # Setup
        yesterday = current_time_et - dt.timedelta(days=1)
        # report = Path(dummy_config['report_paths'][0]) / f"{yesterday.strftime("%d-%m-%Y")}.csv"
        # report.touch()
        report = create_report(yesterday)

        # Mock dep
        mocker.patch("report_sentinel.load_config", return_value=dummy_config)
        # mock_smtp = mocker.patch("report_sentinel.smtplib.SMTP", autospec=True)
        mock_smtp_ssl = mocker.patch("report_sentinel.smtplib.SMTP_SSL")
        # mock_smtp = mocker.patch("smtplib.SMTP", autospec=True)

        # Set up the mock for the context manager
        mock_smtp_instance = mock_smtp_ssl.return_value.__enter__.return_value

        # Execute (before cutoff - expects yesterday's report)
        fake_time = current_time_et.replace(hour=18, minute=0)
        with freeze_time(fake_time):
            main(dummy_config)
        # Verify alert and reprocessing
        assert mock_smtp_instance.send_message.called
        assert hijack_runner.called

    def test_desired_happy_scenario(
        self, mocker, dummy_config, create_report, hijack_runner
    ) -> None:
        """Success case - report exists - latest possible report"""
        # Setup
        date = current_time_et
        # yesterday = current_time_et - dt.timedelta(days=1)
        # report = Path(dummy_config['report_paths'][0]) / f"{yesterday.strftime("%d-%m-%Y")}.csv"
        # report.touch()
        report = create_report(date)

        # Mock dep
        mocker.patch("report_sentinel.load_config", return_value=dummy_config)
        # mock_smtp = mocker.patch("report_sentinel.smtplib.SMTP", autospec=True)
        mock_smtp_ssl = mocker.patch("report_sentinel.smtplib.SMTP_SSL")
        # mock_smtp = mocker.patch("smtplib.SMTP", autospec=True)
        mock_run = mocker.patch("report_sentinel.subprocess.run")

        # Set up the mock for the context manager
        mock_smtp_instance = mock_smtp_ssl.return_value.__enter__.return_value

        # Execute (before cutoff - expects yesterday's report)
        fake_time = current_time_et.replace(hour=18, minute=0)
        with freeze_time(fake_time):
            main(dummy_config)
        # Verify alert and reprocessing
        # assert mock_smtp_instance.send_message.called
        mock_smtp_instance.send_message.assert_not_called()
        # assert hijack_runner.called
        mock_run.assert_not_called()

    def test_missing_report_flow(self, mocker, dummy_config, hijack_runner):
        """Complete failure-to-recovery workflow"""
        # Mock dependencies
        mocker.patch("report_sentinel.load_config", return_value=dummy_config)
        mock_smtp_ssl = mocker.patch("report_sentinel.smtplib.SMTP_SSL")
        mock_run = mocker.patch("report_sentinel.subprocess.run")

        # Set up the mock for the context manager
        mock_smtp_instance = mock_smtp_ssl.return_value.__enter__.return_value

        # Execute (before cutoff - expects yesterday's report)
        fake_time = current_time_et.replace(hour=12, minute=0)
        with freeze_time(fake_time):
            main(dummy_config)
        # Verify alert and reprocessing
        assert mock_smtp_instance.send_message.called
        assert hijack_runner.called

    # def test_runner_integration(self, hijack_runner, dummy_config):
    #     """Verify runner executes expected commands"""
    #     assert run_tpt_report_downloader(dummy_config) is True

    #     cmd = hijack_runner.call_args[0][0]
    #     assert all(
    #         part in cmd[2]
    #         for part in ["source", "bin/activate", "main.py"]
    #     )
