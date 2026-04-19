import csv
import datetime
import logging
import os
import pathlib
from abc import ABC, abstractmethod
from typing import List, Tuple

import markdown
import sendgrid
from dotenv import load_dotenv

from jcvb._consts import JCVB_PUBLIC, REPO_ROOT
from jcvb._consts import JCVB_ROOT

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

_NEWSLETTERS_DIR = JCVB_ROOT / "newsletter"
_SENT_NEWSLETTERS_DIR = JCVB_PUBLIC / "newsletters"
_NEXT_NEWSLETTER_PATH = _NEWSLETTERS_DIR / "Next-Newsletter.md"
_DISTRIBUTION_TO_EMAIL = "tkutcher@johncarroll.org"

_MAIN_DISTRIBUTION_LIST_CSV = REPO_ROOT / "distribution-list.csv"

_TEST_DISTRIBUTION_LIST_CSV = _NEWSLETTERS_DIR / "distribution-list-test.csv"

_TKUTCHER_COM_EMAIL_FROM = "jcvb@tkutcher.com"
_ANVILOR_COM_EMAIL_FROM = "jcvb@anvilor.com"

_EMAIL_FROM = _ANVILOR_COM_EMAIL_FROM  # TEMP


def _read_next_newsletter_md() -> str:
    with open(_NEXT_NEWSLETTER_PATH, "r") as f:
        return f.read()


def _read_next_newsletter_html() -> str:
    return markdown.markdown(_read_next_newsletter_md())


def _file_newsletter_as_sent(date: datetime.date) -> None:
    filename = f"{date.isoformat()}-JCVB-Newsletter.md"
    with open(_SENT_NEWSLETTERS_DIR / filename, "w") as f:
        f.write(_read_next_newsletter_md())


def _newsletter_subject(date: datetime.date, suffix="") -> str:
    suffix = f" - {suffix}" if suffix else ""
    return f"🏐 JC Volleyball {date.strftime('%m/%d')} Newsletter{suffix}"


def _send_newsletter_to_emails(
    sg: sendgrid.SendGridAPIClient,
    to_email: str,
    recipients: list[tuple[str, str]],
    subject: str = None,
    file_as_sent=False,
) -> None:
    today = datetime.date.today()
    subject = _newsletter_subject(today) if subject is None else subject
    message = sendgrid.Mail(
        from_email=sendgrid.Email(_EMAIL_FROM),
        to_emails=[sendgrid.To(email=to_email)],
        subject=subject,
        html_content=_read_next_newsletter_html(),
    )
    tracking_settings = sendgrid.TrackingSettings(
        click_tracking=sendgrid.ClickTracking(enable=False, enable_text=False)
    )
    message.tracking_settings = tracking_settings
    for recipient in recipients:
        message.add_bcc(sendgrid.Bcc(email=recipient[1], name=recipient[0]))
    response = sg.client.mail.send.post(request_body=message.get())
    logging.info(f"Sent newsletter - SendGrid Response {response.status_code}")
    if file_as_sent:
        _file_newsletter_as_sent(today)


class DistributionList(ABC):
    """Abstract base class for distribution lists."""

    @abstractmethod
    def get_recipients(self) -> List[Tuple[str, str]]:
        """Returns a list of (name, email) tuples."""
        pass


class FileDistributionList(DistributionList):
    """Distribution list that reads from a CSV file."""

    def __init__(self, file_path: pathlib.Path) -> None:
        self._file_path = file_path

    def get_recipients(self) -> List[Tuple[str, str]]:
        recipients: List[Tuple[str, str]] = []
        with open(self._file_path, "r") as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for name, email in reader:
                recipients.append((name, email))
        return recipients


class CustomDistributionList(DistributionList):
    """Distribution list with manually provided recipients."""

    def __init__(self, recipients: List[Tuple[str, str]]) -> None:
        self._recipients = recipients

    def get_recipients(self) -> List[Tuple[str, str]]:
        return self._recipients.copy()


class CombinedDistributionList(DistributionList):
    """Distribution list that combines multiple distribution lists."""

    def __init__(self, *distribution_lists: DistributionList) -> None:
        self._distribution_lists = distribution_lists

    def get_recipients(self) -> List[Tuple[str, str]]:
        all_recipients = []
        seen_emails = set()

        for dist_list in self._distribution_lists:
            for name, email in dist_list.get_recipients():
                # Avoid duplicates based on email address
                if email not in seen_emails:
                    all_recipients.append((name, email))
                    seen_emails.add(email)

        return all_recipients


class NewsletterDistributor:
    def __init__(
        self,
        sg: sendgrid.SendGridAPIClient,
        to_email: str,
        distribution_list: DistributionList,
    ) -> None:
        self._sg = sg
        self._to_email = to_email
        self._distribution_list = distribution_list

    def distribute_newsletter(self, file_as_sent=True, subject=None) -> None:
        _send_newsletter_to_emails(
            self._sg,
            to_email=self._to_email,
            recipients=self._distribution_list.get_recipients(),
            subject=subject,
            file_as_sent=file_as_sent,
        )


if __name__ == "__main__":
    load_dotenv()
    SG_API_KEY = os.environ.get("TK_SG_API_KEY")
    ANVILOR_SG_API_KEY = os.environ.get("ANVILOR_SG_API_KEY")
    API_KEY = ANVILOR_SG_API_KEY
    _DISTRIBUTION_LIST_CSV = _MAIN_DISTRIBUTION_LIST_CSV

    file_distribution = FileDistributionList(_DISTRIBUTION_LIST_CSV)
    distribution_list = CombinedDistributionList(
        file_distribution,
        CustomDistributionList([]),
    )

    _test_distribution_list = CustomDistributionList(
        [
            ("Tim", "tkutcher@outlook.com"),
        ]
    )

    distributor = NewsletterDistributor(
        sg=sendgrid.SendGridAPIClient(api_key=API_KEY),
        to_email=_DISTRIBUTION_TO_EMAIL,
        distribution_list=distribution_list,
        # distribution_list=_test_distribution_list,
    )
    distributor.distribute_newsletter(
        file_as_sent=True,
    )
