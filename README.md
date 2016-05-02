aw-server
============

ActivityWatch server, for secure storage and retrieval of all your Quantified Self data and more.

**NOTE:** Work in progress, contributions and feedback warmly welcome!


## About

[ActivityWatch](https://github.com/ActivityWatch/) is a set of applications that act as a system. This application, the ActivityWatch server (aw-server for short), could be considered the primary piece of software with which all others interact.

What the system does is handle collection and retreival of all kinds of logging data (relating to your life, your computer or any type of record). aw-server is the safe repository where you store your data, it is not a place for modification (providing data integrity), once a record is created, it is intended to be immutable.


### Reason for existence

There are plenty of companies offering services which do collection of Quantified Self data with goals ranging from increasing personal producivity to understanding the people that managers manage (organizational productivity). However, all known services suffer from a significant disadvantage, the users data is in the hands of the service providers hands which leads to the problem of trust. Every customer of these companies have their data in untrusted hands. This is a significant problem, but the true reason that we decided to do something about it was that existing solutions were inadequate. They focused on short-term insight, a goal worthy in itself, but we also want long-term understanding. Making the software completely free and open source so anyone can {use, audit, improve, extend} it seemed like the only reasonable alternative.


### Data philosophy

Raw data is the best data when it comes to Quantified Self, you want to be able to access all the data in it's entirety, and then do your assumptions based on said raw data (using a single datasource such as keyboard and mouse input is only a heuristic for if the user is AFK or not). This is not what is done today by existing services, they store summarized data, simplifications of the data gathered since the raw data isn't needed for what they are trying to do right now. But we can't predict what we would like to know in the future, and it is therefore of importance that we get the raw data now, before it disappears into the aether.


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

 - **Event**, has at least one timestamp (usually time of event, but could also be a series timestamps where the event was otherwise identical)
    - **Activity**, has exactly two timestamps (start time, end time) which imply a duration/timeinterval
        - Input (ex: afk or not, keypresses, mouse-move deltas)
        - Window (top-level tabs)
        - Tabs
    - More to come
