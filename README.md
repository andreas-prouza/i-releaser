# ibm-i-deployment

# Set-Up

```sh
yum install python39 python39-devel python39-wheel python39-six python39-setuptools
```

```sh
mkdir ibm-i-deployment
cd ibm-i-deployment
```

```sh
python -m venv --system-site-packages ./.venv
source .venv/bin/activate
pip install --upgrade pip
```

# Directory structure

## etc (configurationsd)

* constants.py
  
    Contains all constants

  * codepage
  * directory names
  * file name templates

* deploy_version.json
  
    History of deployed versions

* logger_config.py
  
    Logger configuration (filename, debug level, ...)
  
* object_commands.json
  
    Specify commands to get run for specific objects
  
* stage_commands.json

    Specify commands to get run for specific stage
  
* stages.json

    Define stage workflow and its attributes

## modules

This folder contains all modules which are necessary to run process the workflow.

This is a collection of classes and functions.

E.g.: Meta_File class which will handle all stuff with meta files:
* save & read json files
* several checks
* stores object structures
* execution history of each object
* etc.

## attribute "cmd"

The command can be a shell command.

It can also be a function of a python script.
The syntax for this is:

```"cmd": "{script-name}.{function-name}"```

E.g.:

```"cmd": "pre.pre_cmd"```

This will execute from script ```pre.py``` the function ```pre_cmd```.


# Coverage

https://coverage.readthedocs.io/en/6.0/source.html