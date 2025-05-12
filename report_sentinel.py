"""
report_sentinel.py

Report monitoring and reprocessing.

Checks each dir in config['report_paths'] for the expected report file.
If a report is missing, sends an alert, triggers reprocessing, and
stops further processing for this run.
"""
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
import venv

import yaml
import smtplib
import datetime as dt
from pathlib import Path
import subprocess

import logging
import datetime as dt
from yaml.scanner import ScannerError
import pytz

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s %(message)s",
    handlers=[
        # NOTE: To save logs, uncomment the below line
        # logging.FileHandler("report_sentinel.log"),
        logging.StreamHandler()
    ]
)


def load_config(
    file_path: "str|Path" = Path(__file__).parent / 'config.yaml'
) -> "dict[str, Any]":
    """Reads the config file present in the directory"""
    try:
        with open(Path(file_path), "r") as file_:
            config: "dict[str, Any]" = yaml.safe_load(file_)
        return config
    except FileNotFoundError:
        raise FileNotFoundError("The provided config path does not exist")
    except ScannerError:
        raise ScannerError(
            "The provided yaml file is not in the correct format"
        )


def send_email(
    smtp_server: "tuple[str, int]", sender: str, recipients: str,
    username: str, password: str, subject: str, body: str,
    attachments: "list[tuple[bytes, str]]" = []
) -> None:
    """Sends the provided email using the given parameters"""
    # Parent message object
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)
    # Adding the text part of the message
    msg.attach(MIMEText(body))
    # Add the attachment to the message
    # NOTE: in case of SSL, comment one or the other. - DEBUG
    # with smtplib.SMTP(smtp_server[0], port=smtp_server[1]) as smtp:
    with smtplib.SMTP_SSL(smtp_server[0], port=smtp_server[1]) as smtp:
        smtp.login(username, password)
        smtp.send_message(msg)


def run_tpt_report_downloader(config: "dict[str, Any]") -> "bool|None":
    """
    Execute TPT report downloader in its virtual environment
    Merges best practices from both implementations with enhanced error
    handling

    Args:
        config: Dictionary containing config params

    Returns:
        bool: True if execution succeeded, False otherwise
    """
    try:
        # Resolve all paths upfront with proper validation
        base_dir = Path(__file__).resolve().parent  # report_sentinel dir
        target_dir = Path(config["main_script_path"]).expanduser()
        venv_dir = (target_dir).resolve().parent / ".venv"

        python_bin = venv_dir / "bin/python"

        main_py = target_dir / "main.py"
        if not main_py.is_absolute():
            main_py = (base_dir / main_py).resolve()
        if not main_py.exists():
            logging.error(f"{main_py} not found")

        # Create venv if needed
        if not venv_dir.exists():
            logging.info(f"Creating venv for {venv_dir}")
            venv.create(venv_dir, with_pip=True)
            # Install dependencies if requirements.txt exists
            req_file = target_dir / "requirements.txt"
            if req_file.exists():
                print("Installing library requirements.")
                subprocess.run(
                    [
                        str(python_bin), "-m", "pip", "install", "-r",
                        str(req_file)
                    ],
                    check=True
                )

        logging.info(f"Runner activated at: {main_py}")
        result = subprocess.run(
            [str(python_bin), str(main_py)],
            check=True,
            cwd=target_dir,  # Run from project dir
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # timeout=300  # 5 minute timeout
        )
        logging.debug(f"TPT output: {result.stdout}")
        return True
    except subprocess.TimeoutExpired:
        logging.error("TPT downloader timed out after 5 minutes")
    except subprocess.CalledProcessError as e:
        logging.error(f"TPT failed (code {e.returncode}): {e.stderr}")
    except Exception as e:
        logging.error(f"Unexpected TPT error: {str(e)}")
    except KeyboardInterrupt:
        logging.debug("Stopped runner")
    return False


def get_expected_report_date() -> dt.date:
    """
    Calculate last possible report date (previous day 5PM ET cutoff)

    Returns:
        dt.date: The previous day date if current time is before 5pm ET,
        otherwise returns today's date.
    """
    # Current time in ET
    now = dt.datetime.now(pytz.utc).astimezone(
        pytz.timezone("US/Eastern")
    )
    if now.hour < 17:
        return (now - dt.timedelta(days=1)).date()
    else:
        return now.date()


def check_last_report_exists(report_dir: Path) -> bool:
    """Check if expected report exists in directory"""
    expected_file = (
        report_dir / f"{get_expected_report_date().strftime('%d-%m-%Y')}.csv"
    )
    return expected_file.exists()


def main(config: "dict[str, Any]") -> None:
    """
    Main function

    Args:
        config: Configuration gotten from config.yaml, uses dict struct.

    Intended for periodic (cron) execution
    """
    smtp_server = config["smtp_server"]
    sender = config["sender"]
    recipients = config["recipients"]
    username = config["smtp_username"]
    password = config["smtp_password"]
    subject = ("Last Possible Report Missing")
    try:
        for report_dir in config['report_paths']:
            path = Path(report_dir)
            if not check_last_report_exists(path):
                body = (
                    f"The last possible report in directory: {path}"
                    " is missing and automated reprocessing will be triggered"
                    " to attempt recovery"
                )
                logging.warning(body)
                send_email(
                    smtp_server, sender, recipients, username, password,
                    subject, body
                )
                logging.debug("Email sent.")
                run_tpt_report_downloader(config)
                return  # Stop after first reprocessing;
                # next cron run will check it again
    except Exception as e:
        logging.critical(f"Execution failed: {str(e)}")


if __name__ == "__main__":
    config = load_config('config.yaml')
    main(config)
