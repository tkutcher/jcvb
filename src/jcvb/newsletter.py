import csv
import datetime
import logging
import os

import markdown
import sendgrid
from dotenv import load_dotenv

from jcvb._consts import JCVB_PUBLIC
from jcvb._consts import JCVB_ROOT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

_NEWSLETTERS_DIR = JCVB_ROOT / "newsletters"
_SENT_NEWSLETTERS_DIR = JCVB_PUBLIC / "newsletters"
_DISTRIBUTION_LIST_CSV = _NEWSLETTERS_DIR / "distribution-list.csv"
_NEXT_NEWSLETTER_PATH = _NEWSLETTERS_DIR / "Next-Newsletter.md"


def _read_distribution_list_csv():
    with open(_DISTRIBUTION_LIST_CSV, "r") as f:
        reader = csv.reader(f)
        return list(reader)[1:]


def _read_next_newsletter_md() -> str:
    with open(_NEXT_NEWSLETTER_PATH, "r") as f:
        return f.read()


def _read_next_newsletter_html() -> str:
    return markdown.markdown(_read_next_newsletter_md())


def _file_newsletter_as_sent(date: datetime.date) -> None:
    filename = f"{date.isoformat()}-JCVB-Newsletter.md"
    with open(_SENT_NEWSLETTERS_DIR / filename, "w") as f:
        f.write(_read_next_newsletter_md())


def _send_newsletter_to_emails(sg: sendgrid.SendGridAPIClient, to_emails) -> None:
    today = datetime.date.today()
    message = sendgrid.Mail(
        from_email=sendgrid.Email("jcvb@tkutcher.com"),
        to_emails=to_emails,
        subject=f"🏐JC Volleyball {today.strftime('%m/%d')} Newsletter",
        html_content=_read_next_newsletter_html(),
    )
    response = sg.client.mail.send.post(request_body=message.get())
    logging.info(f"Sent newsletter - SendGrid Response {response.status_code}")


class NewsletterDistributor:
    def __init__(self, sg: sendgrid.SendGridAPIClient, dry_run_email: str) -> None:
        self._sg = sg
        self._dry_run_email = dry_run_email
        self._distribution = _read_distribution_list_csv()

    def dry_run(self):
        _send_newsletter_to_emails(self._sg, self._dry_run_email)

    # noinspection PyMethodMayBeStatic
    def file_as_sent(self):
        _file_newsletter_as_sent(datetime.date.today())


if __name__ == "__main__":
    load_dotenv()
    distributor = NewsletterDistributor(
        sg=sendgrid.SendGridAPIClient(api_key=os.environ.get("TK_SG_API_KEY")),
        dry_run_email="tkutcher@outlook.com",
    )
    distributor.dry_run()
    distributor.file_as_sent()
