import pathlib

# Temp - just running locally on this one machine.
TK_GDRIVE_ROOT = pathlib.Path(
    "/Users/tkutcher/Library/CloudStorage/GoogleDrive-tkutcher@outlook.com/My Drive"
)


TK_VAULT_ROOT = TK_GDRIVE_ROOT / "tk-vault"
JCVB_ROOT = TK_VAULT_ROOT / "orgs" / "JCVB"
JCVB_PUBLIC = JCVB_ROOT / "public"
