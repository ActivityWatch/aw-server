aw-server
============

[![Build Status](https://travis-ci.org/ActivityWatch/aw-server.svg?branch=master)](https://travis-ci.org/ActivityWatch/aw-server)

ActivityWatch server, for secure storage and retrieval of all your Quantified Self data.


## Install

Install program and dependencies:

```bash
sudo python3 setup.py install 
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
on another port and use a seperate datastore.

```bash
aw-server --testing
```


## API Examples

You can also get a very decent API browser by browsing to `localhost:5600` after starting the server.

There are also some API examples in the [documentation](https://activitywatch.readthedocs.io/en/latest/api-reference.html).


