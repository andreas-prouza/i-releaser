# ibm-i-deployment

# Development set-up

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

Below you will find a list of directories, the containing files and the description.

* etc
    Configurations
* log
* modules
    Core scripts
* meta
    Meta-files (json) containing the deployment information
* scripts
    Can be used for defined steps in you workflow process
* unit-tests



## etc (configurations)

* constants.py
  
    Contains all constants used in the scripts like:
    
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

This folder contains all internal modules which are necessary to run this framework.

This is a collection of classes and functions.

E.g.: ```meta_file.py``` (Meta_File class) which will handle all stuff with meta files:
* save & read json files
* several checks
* stores object structures
* execution history of each object
* etc.

## scripts

All scripts in this folder can be used in any json-config file where a cmd can be defined.


# Configurations

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