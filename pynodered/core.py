import collections
import copy
import json
import logging
import os
from pathlib import Path
from pprint import pprint

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class PynoderedException(Exception):
    pass


def replace_quotes_on_marked_strings(s):
    return s.replace('"@!@', '').replace('@!@"', '')


class NodeProperty(object):
    """a Node property. This is usually use to declare field in a class deriving from RNBaseNode.
    """

    def __init__(self, title=None, type="", value="", required=False, input_type="text", values=None, validate=None,
                 rows=1):
        self.type = type
        self.value = value  # default value
        self.values = values  # values for a select to pick from
        self.title = title
        self.validate = validate
        self.required = required
        self.input_type = input_type
        self.rows = rows

    def as_dict(self, *args):
        self.title = self.title or self.name
        if len(args) == 0:
            args = {"name", "title", "type", "value", "title", "required", "input_type", "validate", "rows"}

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


class ContextData:
    """ Dictionary that keeps track of which entries have changed, changed data only returns thos that have a new value
    """

    def __init__(self, data):
        self._old_data = copy.deepcopy(data)
        self._new_data = dict()

    def __getitem__(self, item):
        if item in self._new_data:
            return self._new_data[item]
        else:
            return self._old_data.get(item)

    def __setitem__(self, key, value):
        if self._old_data.get(key) != value:
            self._new_data[key] = value

    def __len__(self):
        return len(self._old_data) + len([a for a in self._old_data if a not in self._new_data])

    def __str__(self):
        return str(self._old_data) + " --> " + str(self._new_data)

    def has_key(self, k):
        return k in self._old_data or k in self._new_data

    def keys(self):
        return list(set(self._old_data.keys() + self._new_data.keys()))

    def values(self):
        return self._new_data.values() + [self._old_data[a] for a in self._old_data if a not in self._new_data]

    def __contains__(self, item):
        return item in self._new_data or item in self._old_data

    def __iter__(self):
        for x in self.keys():
            yield x

    def clear(self):
        self._new_data = dict()

    def changed_data(self):
        data = {a: self._new_data[a] for a in self._new_data if
                not (a in self._old_data and self._old_data[a] == self._new_data[a])}
        return data


class RNBaseNode(metaclass=FormMetaClass):
    """ Base class for Red-Node nodes. All user-defined nodes should derived from it.
    The child classes must implement the work(self, msg=None) method.
    """

    rednode_template = "httprequest"

    def __init__(self):
        self._status = None
        self._selected_output = self.default_output
        self._outputs = {}
        self.global_data = None
        self.node_data = None
        self.flow_data = None
        self.node_id = None
        self._msg = None
        self._topic = None
        self._trace = {}

    def get_msg_id(self):
        if '_msgid' in self._msg:
            return self._msg['_msgid']

    def get_payload(self):
        if 'payload' in self._msg:
            return self._msg['payload']

    def get_topic(self):
        self._topic

    def set_topic(self, value):
        self._topic = value

    def _re_init(self):
        self._clear_outputs()
        self._clear_status()
        self._clear_selected_output()

    def set_status(self, fill="grey", shape="dot", text="", timeout=10):
        self._status = {'fill': fill, 'shape': shape, 'text': text, 'timeout': timeout}

    def _clear_status(self):
        self._status = None

    def select_output(self, output=None):
        self._clear_outputs()
        if output is None:
            self._selected_output = self.default_output
        elif not (0 <= int(output) < int(self.outputs)):
            raise ValueError("Selected output not valid")
        else:
            self._selected_output = output

    def set_output_raw(self, output, msg):
        if not (0 <= int(output) < int(self.outputs)):
            raise ValueError("Selected output not valid")
        self._clear_selected_output()
        if msg is None:
            del self._outputs[int(output)]
        else:
            self._outputs[int(output)] = msg

    def set_output(self, output, payload=None, topic=None):
        if not (0 <= int(output) < int(self.outputs)):
            raise ValueError("Selected output not valid")
        self._clear_selected_output()
        if payload is None:
            del self._outputs[int(output)]
        else:
            self._outputs[int(output)] = {'payload': payload}
            if topic is not None:
                self._outputs[int(output)]['topic'] = topic

    def _clear_outputs(self):
        self._outputs = {}

    def _clear_selected_output(self):
        self._select_output = self.default_output

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
            form += '<div class="form-row">\
                     <label for="node-input-%(name)s"><i class="icon-tag"></i> %(title)s</label>'
            if property.input_type == "text":
                form += """ <input type="text" id="node-input-%(name)s" placeholder="%(title)s"> """
            elif property.input_type == "textarea":
                form += """ <textarea id="node-input-%(name)s" placeholder="%(title)s" rows="%(rows)s">
                       </textarea>"""
            elif property.input_type == "password":
                form += """ <input type="password" id="node-input-%(name)s" placeholder="%(title)s"> """
            elif property.input_type == "checkbox":
                form += """ <input type="checkbox" id="node-input-%(name)s" placeholder="%(title)s"> """
            elif property.input_type == "select":
                form += """ <select id="node-input-%(name)s"> """
                for val in property.values:
                    form += '<option value="{0}" {1}>{0}</option>\n'.format(val,
                                                                            'selected="selected"' if val == property.value else "")
                form += "</select>\n"
            elif property.input_type == "multi_select":
                form += """ <select id="node-input-%(name)s" multiple size="%(rows)s"> """
                for val in property.values:
                    form += '<option value="{0}" {1}>{0}</option>\n'.format(val,
                                                                            'selected="selected"' if val in property.value else "")
                form += "</select>\n"
            else:
                raise Exception("Unknown input type")
            form += "</div>\n"
            form %= property.as_dict()
        label_text = ""
        if len(cls.output_labels) >= 1:
            count = 0
            for a_label in cls.output_labels:
                label_text += "if (index === {}) return \"{}\";\n".format(count, a_label)
                count += 1
            label_text += "else return \"\";"

        template = open(in_path).read()

        property_names = [p.name for p in cls.properties]

        if cls.button:
            button_str = """
            {
                onclick: function() {
                    $.ajax({
                        url: "%(name)s/"+this.id,
                        type:"POST",
                        success: function(resp) {
                            RED.notify("Successfully injected: ","success");
                        },
                        error: function(jqXHR,textStatus,errorThrown) {
                            alert(errorThrown);
                            if (jqXHR.status === 404) {
                                RED.notify("<strong>Error</strong>: %(name)s node not deployed","error");
                            } else if (jqXHR.status === 500) {
                                RED.notify("<strong>Error</strong>: %(name)s reset failed, see log for details.","error");
                            } else if (jqXHR.status === 0) {
                                RED.notify("<strong>Error</strong>: no response from server","error");
                            } else {
                                RED.notify("<strong>Error</strong>: unexpected error: ("+jqXHR.status+") "+textStatus,"error");
                            }
                        }
                    });
                    }
                    }
            """ % {'name': cls.name}
        else:
            button_str = "false"

        label_string = '[' + ",".join(["this." + lbl for lbl in cls.label if lbl in property_names]) + "]"
        template %= {
            'port': port,
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
            'button': button_str,
            'defaults': replace_quotes_on_marked_strings(json.dumps(defaults)),
            'form': form,
            'button_bool': str(cls.button).lower(),
            'button_data': cls.button_data
        }

        logging.info("writing {}".format(out_path))
        open(out_path, 'w').write(template)

    def add_trace_info(self, data):
        if type(data) == dict:
            self._trace.update(data)
        else:
            raise TypeError

    def run(self, msg, config, context):
        self._re_init()
        self._msg = msg
        self._topic = msg.get('topic')
        self.global_data = ContextData(context.get("global", []))
        self.node_data = ContextData(context.get("node", []))
        self.flow_data = ContextData(context.get("flow", []))
        self.node_id = config.get('id')
        for p in self.properties:
            p.value = config.get(p.name)
        if self.enable_trace and '_trace' not in msg:
            msg['_trace'] = []

        rv = self.work(msg)
        if self.enable_trace and '_trace' not in rv:
            rv['_trace'] = msg['_trace']

        rv['topic'] = self._topic
        rv['context'] = {}
        rv["context"]['global'] = self.global_data.changed_data()
        rv["context"]['node'] = self.node_data.changed_data()
        rv["context"]['flow'] = self.flow_data.changed_data()

        tf_res = []
        if self.trace_function is not None:
            tf_res = self.trace_function(self.msg)
        if self._outputs != {}:
            if self.enable_trace:
                for x in self._outputs:
                    trace_data = {"node_id": self.node_id, "node_name": self.name, "output": x}
                    if x < len(self.output_labels):
                        trace_data["output_label"] = self.output_labels[x]
                    trace_data.update(tf_res)
                    trace_data.update(self._trace)
                    self._outputs[x]['_trace'] = rv['_trace'] + [trace_data]
            rv['outputs'] = self._outputs
        elif self._selected_output is not None:
            rv['selected_output'] = self._selected_output
            if self.enable_trace:
                trace_data = {"node_id": self.node_id, "node_name": self.name, "output": self._selected_output}
                if self._select_output < len(self.output_labels):
                    trace_data["output_label"] = self.output_labels[self._selected_output]
                trace_data.update(tf_res)
                trace_data.update(self._trace)
                rv['_trace'] = rv['_trace'] + [trace_data]
                # rv['_trace'].append([self.node_id, self.name, self._selected_output,
                # self.output_labels[self._select_output]] + tf_res + self._trace)
        else:
            raise PynoderedException("No output selected")
        if self._status:
            rv['status'] = self._status
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
        del self.mem[msg['_msgid']]


def node_red(name=None, title=None, category="default", description=None, join=None, baseclass=RNBaseNode,
             properties=None, icon=None, color=None, outputs=1, output_labels=None, label=None, default_output=0,
             label_style="node_label", align="left", inputs=1, input_label=None, palette_label=None, enable_trace=True,
             trace_function=None, button=None, button_data=None):
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
    default_output is the output if no output is selected through msg['selected_output'] counting from 0
    trace_fuction is a function that takes a msg and returns a list of items, to add to the _trace parameter of msg
    enable_trace  add data to the _trace of msg
    button (bool) add a button to the node
    button_data the data that is sent a json object to node if the button is pressed
    palette_label is the name of the node as shown in the palette
    inputs is the amount of inputs (0, 1 ) the node hase
    input_label is the name shown as a hover over the input
    align is th alignment of the text on the node

    outputs can be selected in three was. returning the msg with the (altered) payload will send it on the default
    output setting msg['selected_output'] will send the msg on the output selected
    msgs can be sent on multiple outputs by defining a dictionary with an outputs entry and an numerical index to which
    the message is assigned to be sent.
       e.g. output['outputs'][1] = "message 1" ;  output['outputs'][3] = "message 3"
        output numbers start counting from 0

    """

    def wrapper(func):
        attrs = {}
        attrs['name'] = name if name is not None else func.__name__
        attrs['palette_label'] = palette_label if palette_label is not None else attrs['name']
        attrs['title'] = title if title is not None else attrs['name']
        attrs['description'] = description if description is not None else func.__doc__
        attrs['category'] = getattr(baseclass, "category", category)  # take in the baseclass if possible
        attrs['icon'] = icon if icon is not None else 'function'
        attrs['outputs'] = outputs if outputs is not None and int(outputs) >= 0 else 1
        attrs['inputs'] = inputs if inputs in [0, 1] else 1
        attrs['input_label'] = input_label if input_label is not None else ""
        attrs['label'] = label if type(label) == list else []
        attrs['output_labels'] = output_labels if type(output_labels) == list else []
        attrs['label_style'] = label_style if label_style is not None else "node_label"
        attrs['align'] = align if align is not None else "left"
        attrs['enable_trace'] = bool(enable_trace)
        attrs['button'] = bool(button)
        attrs['button_data'] = button_data if button else None
        if output_labels is not None and len(output_labels) > outputs:
            raise PynoderedException("Invalid number of labels")
        attrs['default_output'] = default_output if type(default_output) == int and 0 <= default_output < outputs else 1
        attrs['trace_function'] = staticmethod(trace_function) if callable(trace_function) and enable_trace else None
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
