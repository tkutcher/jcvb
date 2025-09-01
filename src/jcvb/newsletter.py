import markdown
from jcvb._consts import JCVB_ROOT

_NEWSLETTERS_DIR = JCVB_ROOT / "newsletters"


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
    newsletter = JCVBNewsletter("2025-08-31")
    html = newsletter.get_as_html()
    print(html)
