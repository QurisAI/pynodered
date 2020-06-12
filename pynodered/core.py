import collections
import copy
import json
import os
from pathlib import Path


class PynoderedException(Exception):
    pass


def replace_quotes_on_marked_strings(s):
    return s.replace('"@!@', '').replace('@!@"', '')


class NodeProperty(object):
    """a Node property. This is usually use to declare field in a class deriving from RNBaseNode.
    """

    def __init__(self, title=None, type="", value="", required=False, input_type="text", values=None, validate=None):
        self.type = type
        self.value = value  # default value
        self.values = values  # values for a select to pick from
        self.title = title
        self.validate = validate
        self.required = required
        self.input_type = input_type

    def as_dict(self, *args):
        self.title = self.title or self.name
        if len(args) == 0:
            args = {"name", "title", "type", "value", "title", "required", "input_type", "validate"}

        return {a: getattr(self, a) for a in args if getattr(self, a) is not None}


class FormMetaClass(type):
    def __new__(cls, name, base, attrs):
        new_class = super(FormMetaClass, cls).__new__(cls, name, base, attrs)

        properties = list()
        for name, attr in attrs.items():
            if isinstance(attr, NodeProperty):
                attr.name = name
                properties.append(attr)
        # sorting manually corresponds to the definition order of Fields.
        new_class.properties = properties
        return new_class


class RNBaseNode(metaclass=FormMetaClass):
    """Base class for Red-Node nodes. All user-defined nodes should derived from it.
    The child classes must implement the work(self, msg=None) method.
    """

    # label_style = None
    rednode_template = "httprequest"

    # based on SFNR code (GPL v3)
    @classmethod
    def install(cls, node_dir, port):

        try:
            os.mkdir(node_dir)
        except OSError:
            pass
        for property in cls.properties:
            new_validate = None
            if property.validate is None:
                pass
            elif property.validate == 'int':
                new_validate = "RED.validators.number()"
            elif property.validate.startswith('regexp:'):
                regexp = property.validate.split(":", 1)[1]
                new_validate = "RED.validators.regex({})".format(regexp)
            elif property.validate.startswith('function:'):
                function = property.validate.split(":", 1)[1]
                new_validate = "{}".format(function)

            if new_validate:
                # json doesn't allow us to write unquoted strings to the output, so we have to remove them manually
                # also note that double quotes will be escaped, so use single quotes only #todo fix the json encoding
                property.validate = "@!@{}@!@".format(new_validate)
            else:
                property.validate = None

        for ext in ['js', 'html']:
            in_path = Path(__file__).parent / "templates" / ("{}.{}.in".format(cls.rednode_template, ext))
            out_path = node_dir / ("{}.{}".format(cls.name, ext))

            cls._install_template(str(in_path), str(out_path), node_dir, port)

    # based on SFNR code (GPL)
    @classmethod
    def _install_template(cls, in_path, out_path, node_dir, port):

        defaults = {}
        form = ""

        for property in cls.properties:
            defaults[property.name] = property.as_dict('value', 'required', 'type', 'validate')
            form += '<div class="form-row">'

            if property.input_type == "text":
                form += """
                   <label for="node-input-%(name)s"><i class="icon-tag"></i> %(title)s</label>
                   <input type="text" id="node-input-%(name)s" placeholder="%(title)s">
                   </div>""" % property.as_dict()
            elif property.input_type == "password":
                form += """
                   <label for="node-input-%(name)s"><i class="icon-tag"></i> %(title)s</label>
                   <input type="password" id="node-input-%(name)s" placeholder="%(title)s">
                   """ % property.as_dict()
            elif property.input_type == "checkbox":
                form += """
                   <label for="node-input-%(name)s"><i class="icon-tag"></i> %(title)s</label>
                   <input type="checkbox" id="node-input-%(name)s" placeholder="%(title)s">
                   """ % property.as_dict()
            elif property.input_type == "select":
                form += """
                    <label for="node-input-%(name)s"><i class="icon-tag"></i> %(title)s</label>
                    <select id="node-input-%(name)s">
                    """ % property.as_dict()
                for val in property.values:
                    form += '<option value="{0}" {1}>{0}</option>\n'.format(val,
                                                                            'selected="selected"' if val == property.value else "")
                form += "</select>"
            else:
                raise Exception("Unknown input type")
            form += "</div>"

        label_text = ""
        if len(cls.output_labels) >= 1:
            count = 0
            for a_label in cls.output_labels:
                label_text += "if (index === {}) return \"{}\";\n".format(count, a_label)
                count += 1
            label_text += "else return \"\";"

        t = open(in_path).read()
        # pprint([ c.__dict__ for c in cls.properties])

        property_names = [p.name for p in cls.properties]

        label_string = '[' + ",".join(["this." + lbl for lbl in cls.label if lbl in property_names]) + "]"
        t = t % {'port': port,
                 'name': cls.name,
                 'title': cls.title,
                 'icon': cls.icon,
                 'color': cls.color,
                 'outputs': cls.outputs,
                 'inputs': cls.inputs,
                 'palette_label': cls.palette_label,
                 'input_label': cls.input_label,
                 'category': cls.category,
                 'description': cls.description,
                 'labels_text': label_text,
                 'label_style': cls.label_style,
                 'align': cls.align,
                 'label': label_string,
                 'defaults': replace_quotes_on_marked_strings(json.dumps(defaults)),
                 'form': form
                 }

        print("writing {}".format(out_path))

        open(out_path, 'w').write(t)

    def run(self, msg, config, context):
        # Make a copy of the storage data as we want to write only the values that actually changed
        self.global_data = copy.deepcopy(context.get("global", []))
        self.node_data = copy.deepcopy(context.get("node", []))
        self.flow_data = copy.deepcopy(context.get("flow", []))

        self.node_id = config.get('id')
        for p in self.properties:
            p.value = config.get(p.name)
        rv = self.work(msg)

        rv['context'] = {}
        old_global_data = context.get("global", [])
        old_node_data = context.get("node", [])
        old_flow_data = context.get("flow", [])
        rv['context']['global'] = rv['context']['global'] = rv['context']['node'] = {}
        for x in self.global_data:
            if old_global_data.get(x) != self.global_data.get(x):
                rv["context"]['global'][x] = self.global_data.get(x)

        for x in self.flow_data:
            if old_flow_data.get(x) != self.flow_data.get(x):
                rv['context']['global'][x] = self.flow_data.get(x)

        for x in self.node_data:
            if old_node_data.get(x) != self.node_data.get(x):
                rv['context']['node'][x] = self.node_data.get(x)

        if 'selected_output' not in rv:
            rv['selected_output'] = self.default_output

        return rv


class NodeWaiting(Exception):
    pass


def silent_node_waiting(f):
    def applicator(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except NodeWaiting:
            return None  # silent_node_waiting

    return applicator


class Join(object):
    """implement a join properties for class deriving from RNBaseNode. This class handles waiting until a sufficient
    number of messages with the excepted_topics arrive. While waiting the Join instance raise NodeWaiting exception
    which is understood by the server which then silently inform node-red to continue without error. Once all the
    message with the expected topics are arrived, the instance return the messages list in the order of
    expected_topics.
"""

    def __init__(self, expected_topics):
        self.mem = collections.defaultdict(dict)
        self.expected_topics = expected_topics

    def __call__(self, msg):
        self.push(msg)
        if not self.ready(msg):
            raise NodeWaiting
        return self.pop(msg)

    def push(self, msg):
        self.mem[msg['_msgid']][msg['topic']] = msg['payload']

    def ready(self, msg):
        for topic in self.expected_topics:
            if topic not in self.mem[msg['_msgid']]:
                return False
        return True

    def get_messages(self, msg):
        return [self.mem[msg['_msgid']][topic] for topic in self.expected_topics]

    def pop(self, msg):
        msgs = self.mem.pop(msg['_msgid'])
        return [msgs[topic] for topic in self.expected_topics]

    def clean(self, msg):
        del self._cache[msg['_msgid']]


def node_red(name=None, title=None, category="default", description=None, join=None, baseclass=RNBaseNode,
             properties=None, icon=None, color=None, outputs=1, output_labels=None, label=None, default_output=0,
             label_style="node_label", align="left", inputs=1, input_label=None, palette_label=None):
    """decorator to make a python function available in node-red. The function must take two arguments, node and msg.
    msg is a dictionary with all the pairs of keys and value sent by node-red. Most interesting keys are 'payload',
    'topic' and 'msgid_'. The node argument is an instance of the underlying class created by this decorator. It can
    be useful when you have a defined a common subclass of RNBaseNode that provided specific features for your
    application (usually database connection and similar).

    icon is a name of a file sans the .svg/.png extension
    color is the colour code of the node specified as string e.g. #FFAABB or as a rgb(R,G,B) triplet
    outputs is the number of outputs a node has
    output_labels is the texts shown when hovered over the output
    label is a list of values from node properties to show on the node itself. The names refer to the variable name
        of the property
    default_output is the output n no output is selected through msg['selected_output'] counting from 0
    """

    def wrapper(func):
        attrs = {}
        attrs['name'] = name if name is not None else func.__name__
        attrs['palette_label'] = palette_label if palette_label is not None else func.__name__
        attrs['title'] = title if title is not None else attrs['name']
        attrs['description'] = description if description is not None else func.__doc__
        attrs['category'] = getattr(baseclass, "category", category)  # take in the baseclass if possible
        attrs['icon'] = icon if icon is not None else 'function'
        attrs['outputs'] = outputs if outputs is not None else 1
        attrs['inputs'] = inputs if inputs is not None else 1
        attrs['input_label'] = input_label if input_label is not None else ""
        attrs['label'] = label if type(label) == list else []
        attrs['output_labels'] = output_labels if type(output_labels) == list else []
        attrs['label_style'] = label_style if label_style is not None else "node_label"
        attrs['align'] = align if align is not None else "left"
        if output_labels is not None and len(output_labels) > outputs:
            raise PynoderedException("Invalid number of labels")
        attrs['default_output'] = default_output if type(default_output) == int and 0 <= default_output < outputs else 1

        try:
            if isinstance(color, str):
                attrs['color'] = color
            else:
                attrs['color'] = "rgb({},{},{})".format(color[0], color[1],
                                                        color[2]) if color is not None else "rgb(231,231,174)"
        except (IndexError, TypeError):
            attrs['color'] = color

        if join is not None:
            if isinstance(join, Join):
                attrs['join'] = join
            elif isinstance(join, collections.Sequence):
                attrs['join'] = Join(join)
            else:
                raise Exception("join must be a Join object or a sequence of topic (str)")

        if properties is not None:
            if not isinstance(properties, dict):
                raise Exception("properties must be a dictionary with key the variable name and value a NodeProperty")
            for k in properties:
                attrs[k] = properties[k]

        attrs['work'] = func
        cls = FormMetaClass(attrs['name'], (baseclass,), attrs)

        return cls

    return wrapper

# @node_red(name="myname", title="mytitle")
# def mynode(msg=None):
#     """madoc"""
#     print(msg)

# print(mynode)
