# UV Migration

## Goal

Switch from poetry to uv.

## Tasks:

- [x] Get server working with uv
- [ ] Update README.md with new instructions

## How to use uv

### Install `uv`

`pip install uv` or `brew install uv`.

### Create a virtualenv

```sh
uv venv
```

### Activate it

```sh
source .venv/bin/activate
```

### Install Deps

```sh
uv sync
```
