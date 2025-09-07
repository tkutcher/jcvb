import csv
import datetime
import logging
import os
import pathlib

import markdown
import sendgrid
from dotenv import load_dotenv

from jcvb._consts import JCVB_PUBLIC
from jcvb._consts import JCVB_ROOT

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

_NEWSLETTERS_DIR = JCVB_ROOT / "newsletters"
_SENT_NEWSLETTERS_DIR = JCVB_PUBLIC / "newsletters"
_DISTRIBUTION_LIST_CSV = _NEWSLETTERS_DIR / "distribution-list.csv"
_NEXT_NEWSLETTER_PATH = _NEWSLETTERS_DIR / "Next-Newsletter.md"


def _read_next_newsletter_md() -> str:
    with open(_NEXT_NEWSLETTER_PATH, "r") as f:
        return f.read()


def _read_next_newsletter_html() -> str:
    return markdown.markdown(_read_next_newsletter_md())


def _file_newsletter_as_sent(date: datetime.date) -> None:
    filename = f"{date.isoformat()}-JCVB-Newsletter.md"
    with open(_SENT_NEWSLETTERS_DIR / filename, "w") as f:
        f.write(_read_next_newsletter_md())


def _send_newsletter_to_emails(
    sg: sendgrid.SendGridAPIClient,
    to_email: str,
    recipients: list[tuple[str, str]],
    file_as_sent=False,
) -> None:
    today = datetime.date.today()
    message = sendgrid.Mail(
        from_email=sendgrid.Email("jcvb@tkutcher.com"),
        to_emails=[sendgrid.To(email=to_email)],
        subject=f"🏐JC Volleyball {today.strftime('%m/%d')} Newsletter",
        html_content=_read_next_newsletter_html(),
    )
    for recipient in recipients:
        message.add_bcc(sendgrid.Bcc(email=recipient[1], name=recipient[0]))
    response = sg.client.mail.send.post(request_body=message.get())
    logging.info(f"Sent newsletter - SendGrid Response {response.status_code}")
    if file_as_sent:
        _file_newsletter_as_sent(today)


class NewsletterDistributor:
    def __init__(
        self,
        sg: sendgrid.SendGridAPIClient,
        to_email: str,
        distribution_list_path: pathlib.Path = _DISTRIBUTION_LIST_CSV,
    ) -> None:
        self._sg = sg
        self._to_email = to_email
        self._distribution_list_path = distribution_list_path

    def distribute_newsletter(self, file_as_sent=True):
        _send_newsletter_to_emails(
            self._sg,
            to_email=self._to_email,
            recipients=self._read_distribution_list(),
            file_as_sent=file_as_sent,
        )

    def _read_distribution_list(self) -> list[tuple[str, str]]:
        to_emails: list[tuple[str, str]] = []
        with open(self._distribution_list_path, "r") as f:
            reader = csv.reader(f)
            next(reader)
            for name, email in reader:
                to_emails.append((name, email))
        return to_emails


if __name__ == "__main__":
    load_dotenv()
    distributor = NewsletterDistributor(
        sg=sendgrid.SendGridAPIClient(api_key=os.environ.get("TK_SG_API_KEY")),
        to_email="tkutcher@johncarroll.org",
        distribution_list_path=_DISTRIBUTION_LIST_CSV,
    )
    distributor.distribute_newsletter(
        file_as_sent=True,
    )
