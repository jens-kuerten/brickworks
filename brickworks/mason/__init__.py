import logging
import sys

import typer
import uvicorn

from brickworks.core.constants import BASE_DIR
from brickworks.core.server import create_app
from brickworks.mason.brick_app import brick_app
from brickworks.mason.db_app import db_app

logging.basicConfig(level=logging.INFO)

app = typer.Typer()

sys.path.append(str(BASE_DIR))

app.add_typer(db_app, name="db", help="Database commands")
app.add_typer(brick_app, name="brick", help="Brick commands")


@app.command()
def runserver(host: str = "0.0.0.0", port: int = 8000) -> None:  # nosec
    server = create_app()
    uvicorn.run(server, host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
