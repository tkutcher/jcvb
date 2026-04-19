import pathlib

TK_ROOT = pathlib.Path("/Users/tkutcher/TK")

TK_VAULT_ROOT = TK_ROOT / "tk-vault"
JCVB_ROOT = TK_VAULT_ROOT / "orgs" / "JCVB"
JCVB_PUBLIC = JCVB_ROOT / "public"

REPO_ROOT = pathlib.Path(__file__).parents[2]
