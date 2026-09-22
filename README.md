# desidata

**Load Indian datasets from [desidata.in](https://www.desidata.in) in one line.**

```python
import desidata

df = desidata.load("gender-policy-of-nabard-question-and-answer-dataset")
```

That's it — no URL copying, no sign-in, no API key. You get a pandas
DataFrame of cleaned, India-focused public data: economy, agriculture,
health, education, transport, demographics and more.

## Install

```bash
pip install desidata
```

The core package has **zero dependencies**, so it installs instantly.
`load()` needs pandas (almost always already installed) and will tell you
exactly what to run if it is missing:

```bash
pip install desidata pandas
```

## Usage

```python
import desidata

# Search the catalogue from Python
results = desidata.search("census")
for row in results:
    print(row["slug"], row["category"], row["rows"])

# Browse everything, or one category
all_datasets = desidata.catalog()
economy = desidata.catalog(category="Economy")

# Metadata for one dataset
info = desidata.info("gender-policy-of-nabard-question-and-answer-dataset")
print(info["name"], info["size"], info["downloads"])

# Load as a DataFrame (kwargs pass through to pandas.read_csv)
df = desidata.load("gender-policy-of-nabard-question-and-answer-dataset")
df = desidata.load("some-dataset", dtype={"year": int}, parse_dates=["date"])

# Raw bytes, or save straight to disk
data = desidata.download("some-dataset")            # bytes
path = desidata.download("some-dataset", "a.csv")   # writes the file
```

Full dataset URLs work anywhere a slug does — paste straight from the browser:

```python
desidata.load("https://www.desidata.in/datasets/gender-policy-of-nabard-question-and-answer-dataset")
```

### Caching

Loads are cached in `~/.desidata/cache` for 24 hours, so re-loading in a
notebook (or in a classroom on weak wifi) is instant and offline-safe.

```python
desidata.load("some-dataset", refresh=True)  # bypass the cache
desidata.clear_cache()                       # wipe all cached files
```

Set `DESIDATA_CACHE_DIR` to move the cache somewhere else.

## Command line

```bash
desidata search nabard
desidata info gender-policy-of-nabard-question-and-answer-dataset
desidata catalog --category Agriculture
desidata download gender-policy-of-nabard-question-and-answer-dataset -o nabard.csv
desidata clear-cache
```

## Error handling

Every error the package raises subclasses `desidata.DesiDataError`:

| Exception | Meaning |
| --- | --- |
| `DesiDataNotFound` | That dataset doesn't exist (HTTP 404) |
| `DesiDataConnectionError` | Network/DNS/timeout failure |
| `DesiDataServerError` | desidata.in returned an unexpected error |

```python
try:
    df = desidata.load("some-slug")
except desidata.DesiDataNotFound:
    print("Check the slug with desidata.search(...)")
```

## Development

```bash
git clone https://github.com/krishnakaushik195/desidata-py
cd desidata-py
pip install -e .[dev]
pytest                    # offline unit tests
RUN_LIVE=1 pytest tests/test_live.py -v   # integration tests against the real site
```

Environment overrides used by tests and local development:

| Variable | Purpose |
| --- | --- |
| `DESIDATA_BASE_URL` | Point the client at a local/dev server |
| `DESIDATA_CACHE_DIR` | Relocate the cache |
| `DESIDATA_TIMEOUT` | Default request timeout in seconds |

## Releasing

Maintainers only:

```bash
pip install --upgrade build twine
python -m build
twine upload dist/*
```

## Licence

MIT — see [LICENSE](LICENSE). The data itself belongs to its sources; each
dataset page on [desidata.in](https://www.desidata.in) lists its source and licence.
