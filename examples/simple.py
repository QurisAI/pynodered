from pprint import pprint

from pynodered import node_red, NodeProperty, NodeContext

class Counter:
    def __init__(self):
        self.n = 0
    def inc(self):
        self.n += 1

@node_red(category="pynodered")
def counter(node, msg):

    with NodeContext(node.node_data, 'counter', Counter()) as counter:
        counter.inc()
        msg['payload'] = counter.n

    return msg

@node_red(category="pynodered")
def lower_case(node, msg):
    msg['payload'] = msg['payload'].lower()
    return msg


fn = "function:function(v) {var minimumLength=$('#node-input-number').length?$('#node-input-number').val(" \
     "):this.number; return v.length > minimumLength } "


def tf(msg):
    return [{"payload": msg['payload']}]


@node_red(category="pynodered",
          inputs=0,
          button=True,
          name="test",
          button_data="{'foo': 'foobar'}",
          outputs=1)
def test(node, msg):
    node.set_output(0, msg['payload'], 'foo')
    return msg


@node_red(category="pynodered",
          properties=dict(number=NodeProperty("number", value="1", validate='int'),
                          number2=NodeProperty("Number1", value="2", validate='regexp:/^[a-z]+$/'),
                          number3=NodeProperty("Number2", value="2", validate=fn),
                          myname=NodeProperty("Myname", value="2"),
                          script=NodeProperty("Script", value="Yoo", input_type="textarea", rows=10),
                          ms=NodeProperty("MS", value="1", input_type="multi_select", values=['1', '2', '3', "4", "5"],
                                          rows=1),
                          ),
          outputs=4,
          title="My Name",
          inputs=1,
          input_label="Foobar",
          default_output=1,
          color="#BAD",
          output_labels=["One", "Two"],
          label=["number2"],
          label_style="node_label_italic",
          align="center",
          palette_label=None,
          enable_trace=True,
          trace_function=tf,
          button=True
          )
def repeat(node, msg):
    # pprint(msg)
    # print(node.node_id)
    # pprint(node.node_data)
    # pprint(node.flow_data)
    # pprint(node.global_data)
    exec(node.script.value, globals(), locals())
    # msg['dashboard']['value'] = 'konijntje'
    # msg['dashboard']['type'] = 'text'
    # print(node.payload)
    # pprint(node.__dict__)
    # print(node.topic)
    if 'hits' in node.global_data:
        node.global_data['hits'] += 1
    else:
        node.global_data['hits'] = 1
    node.global_data['shit'] = 'AOeuao'
    # print(node.global_data)
    node.flow_data['hits'] = node.global_data['hits'] % 5
    node.global_data['hits'] += 1
    msg['payload'] += " " + str(node.global_data['hits'])
    out = {}
    # pprint(msg['_trace'])
    x = 1
    y = 2
    z = node.global_data['hits']
    # node.select_output(2)
    node.set_output(1, z, 'foo')
    node.set_output(2, y, 'bar')
    node.set_output(3, x, 'baz')

    print(node.msg_id)
    # node.set_status('red', 'ring', 'blablabla aap', 10)
    # pprint(node.__dict__)
    # msg['selected_output'] = 2
    # out['payload'] = 'foo'

    return out
    msg['payload'] = msg['payload'] * int(node.number.value)
    if 'blablablabla' not in node.global_data:
        node.global_data['blablablabla'] = "AA"
    else:
        node.global_data['blablablabla'] += "AA"
    if 'blablablabla' not in node.flow_data:
        node.flow_data['blablablabla'] = "BBB"
    else:
        node.flow_data['blablablabla'] += "BBB"
    if 'blablablabla' not in node.node_data:
        node.node_data['blablablabla'] = "CCCC"
    else:
        node.node_data['blablablabla'] += "CCCC"
    msg['payload'] = "Foobar" + node.node_data['blablablabla']

    # pprint(node.node_data)
    if 'output' in node.node_data:
        msg['selected_output'] = (node.node_data['output'] + 1) % 2
    else:
        msg['selected_output'] = 0
    node.node_data['output'] = msg['selected_output']
    pprint(msg)
    # pprint(node.node_data)
    return msg

