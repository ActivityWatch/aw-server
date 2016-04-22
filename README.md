actwa-server
============

Server for storage of all your QS data.

## Install

Install dependencies:

    sudo pip3 install -r requirements.txt

Run module:

    python3 .


## Examples

Some simple examples, they assume you have the server running on the default port on localhost.


Get all data for a given activity type:

    curl http://localhost:5000/api/0/activity/test -X GET -v


Store an event: 

    curl http://localhost:5000/api/0/activity/test -d '{"label": ["test-activity"], note: "Just a test"}' -H "Content-Type: application/json" -X POST -v


