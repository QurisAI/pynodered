import argparse
from asyncore import dispatcher
import copy
import importlib
import inspect
import json
import logging
import sys
from pathlib import Path

from flask import Flask
from jsonrpc.backend.flask import api
from jsonrpc.backend.flask import JSONRPCAPI
from jsonrpc.utils import DatetimeDecimalEncoder
from pynodered.core import silent_node_waiting

# https://media.readthedocs.org/pdf/json-rpc/latest/json-rpc.pdf

werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.ERROR)

class MyFlaskJSONRPCAPI(JSONRPCAPI):
    @staticmethod
    def _serialize(s):
        return json.dumps(s, cls=MyEncoder)

class MyEncoder(DatetimeDecimalEncoder):
    def default(self, o):
        if hasattr(o, 'serialize'):
            return o.serialize()
        return super().default(o)

# api = MyFlaskJSONRPCAPI()

app = Flask(__name__)
app.register_blueprint(api.as_blueprint())


userDir = Path.home() / ".node-red" 
def node_directory(package_name):
    return Path(userDir) / "node_modules" / package_name  # assume this also work on MacOS and Windows...


def main():
    parser = argparse.ArgumentParser(prog='pynodered')
    parser.add_argument('--noinstall', action="store_true",
                        help="do not install javascript files to save startup time. It is only necessary to install "
                             "the files once or whenever a python function change")
    parser.add_argument('--port',
                        help="port to use by Flask to run the Python server handling the request from Node-RED",
                        default=5051)
    parser.add_argument('--userDir', default=Path.home() / ".node-red" )
    parser.add_argument('filenames', help='list of python file names or module names', nargs='+')
    args = parser.parse_args(sys.argv[1:])

    global userDir
    userDir = args.userDir

    # register files:
    packages = dict()

    package_tpl = {
        "name": "pynodered",
        "version": "0.2",
        "description": "Nodes written in Python",
        "dependencies": {"follow-redirects": "1.5.10"},
        "keywords": ["node-red"],
        "node-red": {
            "nodes": {}
        }
    }

    registered = 0

    for path in args.filenames:
        logging.info("Path: {}".format(path))

        # import the module by file or by name
        if path.endswith(".py"):
            path = Path(path)
            if path.stem.startswith("_"):
                continue
            # import a file
            module_name = "pynodered.imported_modules." + path.stem
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sys.modules[module_name] = module
        else:
            # import a module
            module = importlib.import_module(path)

        # prepare the package json file
        if hasattr(module, "package"):
            if not isinstance(module.package, dict) or 'name' not in module.package:
                raise Exception(
                    "the 'package' attribute in the module must be a dict defining at least the 'name' of the module "
                    "in Node-RED")
            package_name = module.package['name']
            if package_name not in packages:
                packages[package_name] = copy.deepcopy(package_tpl)  # load default values
                packages[package_name].update(module.package)  # update them with module.package
        else:
            package_name = 'pynodered'  # default name
            if package_name not in packages:
                packages[package_name] = copy.deepcopy(package_tpl)  # load default values

        node_dir = node_directory(package_name)

        # now look for the functions and classes

        for name, obj in inspect.getmembers(module, inspect.isclass):
            if hasattr(obj, "install") and hasattr(obj, "work") and hasattr(obj, "run") and hasattr(obj, "name"):
                logging.info("From {} register {}".format(name, obj.name))
                if not args.noinstall:
                    obj.install(node_dir, args.port)
                    logging.info("Install {}".format(name))
                    packages[package_name]["node-red"]["nodes"][obj.name] = obj.name + '.js'

                api.dispatcher.add_method(silent_node_waiting(obj, 'run'), obj.name)

                registered += 1

                # obj can run an http_server if it has one
                if hasattr(obj, "http_server"):
                    obj.http_server(app)

    if registered == 0:
        raise Exception("Zero function or class to register to Node-RED has been found. Check your python files")

    if not args.noinstall:
        for package_name in packages:
            with open(node_directory(package_name) / "package.json", "w") as f:
                json.dump(packages[package_name], f)

    # print('ROUTES')
    # for rule in app.url_map.iter_rules():
    #     # Filter out rules we can't navigate to in a browser
    #     # and rules that require parameters
    #     print(rule.methods,rule.endpoint)

    app.run(host='127.0.0.1', port=args.port)#, debug=True)


if __name__ == '__main__':
    main()
