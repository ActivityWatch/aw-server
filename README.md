actwa-server
============

Server for storage of all your QS data.

## Examples

Some simple examples, they assume you have the server running on the default port on localhost.

    curl http://localhost:5000/api/0/activity/test -d 'data={"label": ["test-activity"], note: "Just a test"}' -X PUT -v
