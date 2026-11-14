GIT to FreshPorts converter
===========================

Used to convert GIT commit entries into XML files digestible by the FreshPorts backend

Installation:
```shell script
pkg install python3 py314-lxml py314-pygit2
```

Running:
```shell script
python3 git-to-freshports-xml.py --repo ports --path /path/to/git/repo --branch main \
    --commit-range FROM..TO --spooling /path/to/spooling --output /path/to/xml/results
```

Getting help:
```shell script
python3 git-to-freshports-xml.py --help
```

Running unit tests:
```shell script
pkg install py314-pytest
python3 -m pytest tests/
```
