# Modularization: Bricks

Brickworks allows you to build your application out of individual Python modules called bricks.
Each brick should encapsulate a specific functionality, making the codebase easier to understand, maintain and reuse.


## Start your project
Brickworks requires your project to have a `pyproject.yaml`.

It is recommended to use a dependency management tool like [Poetry](https://python-poetry.org/) or [uv](https://docs.astral.sh/uv/), which will create the `pyproject.yaml` for you and help you manage your projects dependencies.

```bash
poetry init
poetry add brickworks
```

or

```bash
uv init
uv add brickworks
```


## Create your first brick

To create a brick you can use the command line tool that comes with Brickworks: Mason.

```bash
mason brick create mybrick --namespace app
```

This will create the `app` package, containing the `mybrick` module and register your new brick in the `pyproject.toml`.
The folder structure will look like this:

```text
pyproject.toml
app/
    __init__.py
    mybrick/
        __init__.py
        brick.json
        models/
            __init__.py
        routers/
            __init__.py
        schemas/
            __init__.py
```

Afterwards run the install command of your chosen dependency management tool, e.g.:

```bash
uv pip install -e .
```

or

```bash
poetry install
```

This will ensure your new brick is discoverable by brickworks.

## brick.json

The `brick.json` file helps Brickworks discover various parts of your brick. Here you can register your routers and any middlewares you might want to add.

```json
{
  "routers": ["app.mybrick.routers.mybrick_router"],
  "middlewares": [],
  "loadme": []
}
```

Middlewares are run after any Brickworks internal middlewares (e.g. session and CORS middleware), meaning you already have a database session and auth context available.

The loadme section, allows you to specify any Python modules that should be loaded on startup. This is useful for making sure signals are connected on startup of the application.
