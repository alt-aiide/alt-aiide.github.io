# ALT-AIIDE website

Jekyll site for the (satirical) ALT-AIIDE conference, hosted on GitHub Pages.
See `designdoc.md` for the brief.

## Layout

| Path | What it is |
| --- | --- |
| `papers/*.pdf` | The "accepted" papers. Served as-is and linked from each card. |
| `scripts/extract_papers.py` | Pulls title, authors, affiliations and abstract out of each PDF and writes `_data/papers.yml`. |
| `_data/papers.yml` | **Generated.** Don't edit by hand; re-run the script. |
| `_data/hype_overrides.yml` | Hand-written hype blurbs keyed by PDF filename (optional; papers without one get a generic blurb). |
| `index.html`, `_layouts/default.html` | The page. Papers are rendered from `site.data.papers`. |
| `assets/` | CSS, JS (mini Battleship, typed tagline, novelty meter) and SVG art. |

## Updating the paper list

Needs Python 3 with PyYAML, plus poppler-utils (`pdftohtml`), e.g. `sudo apt install poppler-utils`.

```sh
# add/remove/replace PDFs in papers/, then:
python3 scripts/extract_papers.py
```

The script prints each paper's extracted title, authors, abstract length and tags,
plus warnings if something looked off. Papers are listed in natural filename order
(`paper2` before `paper10`). Commit the regenerated `_data/papers.yml` — GitHub Pages
does not run the script.

Extraction relies on the AAAI template layout (title in the largest font, bold author
names below it, abstract under a bold "Abstract" heading). If a paper uses a different
layout, check its entry in `_data/papers.yml`.

## Previewing locally

```sh
sudo apt install ruby-dev build-essential   # once, for native gem extensions
bundle install
bundle exec jekyll serve
```

Then open http://localhost:4000.

## Deploying

Push to GitHub and enable Pages (Settings → Pages → deploy from branch). If the site
is served from a project repo (`https://<user>.github.io/<repo>/`), set `baseurl: /<repo>`
in `_config.yml`.
