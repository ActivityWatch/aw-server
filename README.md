aw-server
============

ActivityWatch Server, for secure storage and retrieval of all your QS data. (security is in progress)


## Install

Install dependencies:

    sudo python3 setup.py install 

Run aw-server:

    aw-server


## Examples

Some simple examples, they assume you have the server running on the default port on localhost.


Get all data for a given activity type:

    curl http://localhost:5000/api/0/activity/test -X GET -v


Store an event: 

    curl http://localhost:5000/api/0/activity/test -d '{"label": ["test-activity"], note: "Just a test"}' -H "Content-Type: application/json" -X POST -v


## Event-hierarchy

 - **Event**
   Has at least a start-time
    - **Activity**
      Has both a start-time and end-time
        - Input (ex: afk or not, keypresses, mouse-move deltas)
        - Window (top-level tabs)
        - Tabs
    - More to come
