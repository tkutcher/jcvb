import os

from dotenv import load_dotenv
import markdown
import csv

import sendgrid

from jcvb._consts import JCVB_ROOT

_NEWSLETTERS_DIR = JCVB_ROOT / "newsletters"
_DISTRIBUTION_LIST_CSV = _NEWSLETTERS_DIR / "distribution-list.csv"


def _read_distribution_list_csv():
    with open(_DISTRIBUTION_LIST_CSV, "r") as f:
        reader = csv.reader(f)
        return list(reader)[1:]


class JCVBNewsletter:
    def __init__(self, iso_date: str):
        self._iso_date = iso_date
        self._filepath = _NEWSLETTERS_DIR / f"{iso_date}-JCVB-Newsletter.md"
        self._md_content: str = ""
        self.read_md_content()

    def read_md_content(self) -> None:
        """Read in the markdown content to the"""
        with open(self._filepath, "r", encoding="utf-8") as f:
            self._md_content = f.read()

    def get_as_html(self) -> str:
        return markdown.markdown(self._md_content)


if __name__ == "__main__":
    load_dotenv()
    sg = sendgrid.SendGridAPIClient(api_key=os.environ.get("TK_SG_API_KEY"))
    newsletter = JCVBNewsletter("2025-08-31")
    message = sendgrid.Mail(
        from_email=sendgrid.Email("jcvb@tkutcher.com"),
        to_emails=sendgrid.To("tkutcher@outlook.com"),
        subject="🏐 JCVB Newsletter",
        html_content=newsletter.get_as_html(),
    )
    response = sg.client.mail.send.post(request_body=message.get())
    print(response.body)
