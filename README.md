aw-server
============

ActivityWatch server, for secure storage and retrieval of all your QS data.

**NOTE:** Work in progress, contributions and feedback warmly welcome!

## About

ActivityWatch is a set of applications that act as a system. This application, the ActivityWatch server, could be considered the primary piece of software with which all others interact.

What the system does is handle collection and retreival of all kinds of logging data (relating to your life, your computer or any type of record). aw-server is the safe repository where you store your data, it is not a place for modification (providing data integrity), once a record is created, it is intended to be immutable.


### Security


One of the reasons this project was started was due to the fact that I was missing security in how my Quantified Self data was stored. Data needs to be collected on many devices, and be stored at a central and secure location. Since we want to be able to provide a safe storage service for initial users who do not have the time to run a server of their own, we will provide a feature such that we will only have the users encrypted data, without information of the contents (with exception for some relatively unimportant metadata such as allocated storage space, sessions, clients, and number of entries).

**NOTE:** Security features discussed here are all considered work in progress and this software is not yet fit for exposure to the internet. Only allow connections from localhost!


## Install

Install program and dependencies:

```bash
sudo python3 setup.py install 
```

Run aw-server:

```bash
aw-server
```


## Examples

Some simple examples, they assume you have the server running on the default port on localhost.


Get all data for a given activity type:

```bash
curl http://localhost:5600/api/0/activity/test -X GET -v
```

Store an event: 

```bash
curl http://localhost:5600/api/0/activity/test -d '{"label": ["test-activity"], note: "Just a test"}' -H "Content-Type: application/json" -X POST -v
```

## Event-hierarchy

 - **Event**
   Has at least a start-time
    - **Activity**
      Has both a start-time and end-time
        - Input (ex: afk or not, keypresses, mouse-move deltas)
        - Window (top-level tabs)
        - Tabs
    - More to come
