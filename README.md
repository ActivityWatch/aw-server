aw-server
============

[![Build Status](https://github.com/ActivityWatch/aw-server/workflows/Build/badge.svg?branch=master)](https://github.com/ActivityWatch/aw-server/actions?query=workflow%3ABuild+branch%3Amaster)
[![Coverage Status](https://codecov.io/gh/ActivityWatch/aw-server/branch/master/graph/badge.svg)](https://codecov.io/gh/ActivityWatch/aw-server)


ActivityWatch server, for secure storage and retrieval of all your Quantified Self data.

**Note:** In the future this will no longer be the default server used by ActivityWatch, instead we will be using [aw-server-rust](https://github.com/ActivityWatch/aw-server-rust/). The fate of this repo is uncertain, but it will likely be around and maintained for a while (as a reference implementation, for prototyping, etc).


## Build and Install

To install program and dependencies, Poetry is required. You'll want to activate a `venv` before building.

```bash
make build
```

The `aw-server` binary should now be available to you in your PATH (if it is set correctly).

## Usage

Run aw-server:

```bash
aw-server
```

## Development

If you want to run aw-server in development, you probably want to run a
development instance beside your personal (stable) instance. You can do
this by giving aw-server the `--testing` flag. This will start the server
on another port and use a separate datastore.

```bash
aw-server --testing
```


## API Examples

You can also get a very decent API browser by browsing to `localhost:5600` after starting the server.

There are also some API examples in the [documentation](https://docs.activitywatch.net/en/latest/api.html).

