# Tidal Music service

![GitHub](https://img.shields.io/github/license/FUMR/tidal-async?style=flat-square)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000?style=flat-square)](https://github.com/psf/black)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow?style=flat-square)](https://conventionalcommits.org)

## Development
### Install dependencies
```sh
# Install all dependencies
poetry install

# Install linters (Unlinted PRs won't be approved)
poetry run pre-commit install

# Install commit-msg linters (PRs with wrong commit names will be squashed)
poetry run pre-commit install --hook-type commit-msg
```
